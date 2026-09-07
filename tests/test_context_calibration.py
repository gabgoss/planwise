#!/usr/bin/env python3
"""Unit tests for the Token Saver calibration engine (context_calibration.py).

Covers the `/context`-report -> overheads -> thresholds pipeline and the
capture/calibrate write-back flow:

  * parse_context_report(text) parses a captured `/context` report into a
    per-category dict, computes a `total_active` that EXCLUDES the
    "System tools (deferred)" row, and attributes plugin token usage by summing
    the Agents + Skills rows whose Source begins with "Plugin".
  * derive_overheads(breakdown) and derive_thresholds(session_target,
    runner_overhead) compute the runner/orchestrator overheads and the derived
    per-task ceiling / critical / warn thresholds.
  * calibrate() with a failed capture writes the conservative fallback overheads,
    flags the thresholds as uncalibrated, and does not crash.
  * capture_context() routes through powershell.exe on Windows (a real console
    is required for `/context` to render) and shells out directly on POSIX.
  * calibrate() treats a non-report (conversational) reply the same as a failed
    capture, rather than writing a zeroed, falsely-"calibrated" overhead.

Run with:  python -m pytest tests/test_context_calibration.py
"""

import re
import shutil
import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from conftest import _engine  # noqa: E402

# A real captured `/context` report, pasted verbatim. Parser rules:
#   * "System tools (deferred)" is EXCLUDED from total_active.
#   * 25.7k -> 25700, 386 -> 386, ~80 -> 80, "< 20" -> 20.
#   * Plugin attribution sums Agents + Skills rows whose Source starts "Plugin".
CONTEXT_REPORT_FIXTURE = """## Context Usage
**Model:** claude-opus-4-8[1m]
**Tokens:** 25.7k / 1m (3%)
### Estimated usage by category
| Category | Tokens | Percentage |
| System prompt | 2.6k | 0.3% |
| System tools | 19.1k | 1.9% |
| System tools (deferred) | 16.4k | 1.6% |
| Custom agents | 386 | 0.0% |
| Memory files | 2k | 0.2% |
| Skills | 1.7k | 0.2% |
| Messages | 8 | 0.0% |
| Free space | 974.3k | 97.4% |
### Custom Agents
| Agent Type | Source | Tokens |
| planwise:fix-agent | Plugin | 86 |
| planwise:plan-reviewer | Plugin | 117 |
| planwise:structural-reviewer | Plugin | 99 |
| planwise:task-runner | Plugin | 84 |
### Skills
| Skill | Source | Tokens |
| planwise | Plugin (planwise) | ~80 |
| deep-research | Built-in | ~160 |
"""


# ---------------------------------------------------------------------------
# Step 6 — /context parser
# ---------------------------------------------------------------------------
class TestContextParser(unittest.TestCase):
    """parse_context_report parses the captured report and attributes plugins."""

    def test_total_active_excludes_deferred_tools(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        total = report["total_active"]
        # ~25.7K, the header total, which excludes "System tools (deferred)".
        self.assertGreaterEqual(total, 25000)
        self.assertLessEqual(total, 26500)
        # The deferred row (16.4k) must NOT be folded into total_active.
        self.assertLess(
            total,
            25700 + 16400 - 1000,
            "total_active must exclude the System tools (deferred) row",
        )

    def test_per_category_dict_populated(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        categories = report["categories"]
        self.assertEqual(categories.get("System prompt"), 2600)
        self.assertEqual(categories.get("System tools"), 19100)
        self.assertEqual(categories.get("Memory files"), 2000)
        self.assertEqual(categories.get("Messages"), 8)

    def test_plugin_attribution_sums_plugin_rows(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        attributed = ts.attribution(report, plugin="planwise")
        # Agents: 86 + 117 + 99 + 84 = 386; Skills: planwise (~80) Plugin row.
        # deep-research (Built-in) is excluded. Total ~= 466.
        self.assertGreaterEqual(attributed, 450)
        self.assertLessEqual(attributed, 480)

    def test_escaped_pipe_in_a_category_row_does_not_shift_columns(self):
        # A category label containing an escaped pipe used to split into an
        # extra cell, so the token figure was read from the percentage column
        # (or dropped entirely).
        ts = _engine()
        report = ts.parse_context_report(
            CONTEXT_REPORT_FIXTURE.replace(
                "| Memory files | 2k | 0.2% |",
                r"| Memory files \| notes | 2k | 0.2% |",
            )
        )
        self.assertEqual(report["categories"].get("Memory files | notes"), 2000)
        # Sibling rows still read correctly.
        self.assertEqual(report["categories"].get("System tools"), 19100)
        self.assertEqual(report["categories"].get("Messages"), 8)

    def test_escaped_pipe_in_an_agent_row_keeps_token_column(self):
        ts = _engine()
        report = ts.parse_context_report(
            CONTEXT_REPORT_FIXTURE.replace(
                "| planwise:fix-agent | Plugin | 86 |",
                r"| planwise:fix-agent \| v2 | Plugin | 86 |",
            )
        )
        agent = next(
            a for a in report["agents"] if a["name"] == "planwise:fix-agent | v2"
        )
        self.assertEqual(agent["source"], "Plugin")
        self.assertEqual(agent["tokens"], 86)


# ---------------------------------------------------------------------------
# Step 7 — Derivation formulas
# ---------------------------------------------------------------------------
class TestDerivation(unittest.TestCase):
    """derive_overheads + derive_thresholds compute the budget math."""

    def test_derive_overheads_filters_by_plugin_attribution(self):
        """derive_overheads() must equal the attribution-filtered sum, not
        the unfiltered total_active, on a report mixing plugin AND
        non-plugin (Built-in) rows.

        CONTEXT_REPORT_FIXTURE mixes sources: the four Custom Agents rows
        and the `planwise` Skill row are all `Plugin`-sourced (386 + 80 =
        466); the `deep-research` Skill row is `Built-in` (~160) and must be
        excluded. The pre-migration formula (`runner_overhead =
        total_active`, ~25700) would fail every assertion below.
        """
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        overheads = ts.derive_overheads(report)
        attributed = ts.attribution(report)
        self.assertEqual(
            overheads["runner_overhead"],
            attributed,
            "runner_overhead must equal the attribution-filtered sum",
        )
        # The Built-in deep-research row (~160) must be excluded: the
        # filtered sum stays well under the unfiltered total_active (~25700).
        self.assertLess(overheads["runner_overhead"], 1000)
        self.assertNotEqual(
            overheads["runner_overhead"],
            report["total_active"],
            "the old unfiltered formula (runner_overhead = total_active) "
            "must no longer hold",
        )

    def test_derive_overheads_from_breakdown(self):
        """runner_overhead is the attribution-filtered Agents+Skills sum.

        Migration note (superseded pin -> replacement): this test used to
        assert `25000 <= runner <= 26500` -- the whole snapshot's unfiltered
        `total_active`, from when `derive_overheads()` set
        `runner_overhead = total_active`. Per the module's migration note
        (`context_calibration.py` docstring), `attribution()` is now wired
        into the derivation so `runner_overhead` measures THIS plugin's own
        footprint instead of the whole installation's ambient cost.
        Attribution filtering drops the value from ~25700 to the
        plugin-sourced Agents+Skills sum (~466 on this fixture), well below
        the old 25000-26500 band, so the superseded assertion now fails by
        construction -- replaced below with the filtered-sum contract. This
        is a deliberate behavior change, not pin churn.
        """
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        overheads = ts.derive_overheads(report)
        runner = overheads["runner_overhead"]
        orchestrator = overheads["orchestrator_overhead"]
        # runner_overhead = attribution-filtered sum (~466), NOT the
        # unfiltered total_active (~25700) the superseded pin asserted.
        attributed = ts.attribution(report)
        self.assertEqual(runner, attributed)
        self.assertGreaterEqual(runner, 450)
        self.assertLessEqual(runner, 480)
        self.assertLess(
            runner,
            report["total_active"],
            "runner_overhead must be the attribution-filtered sum, well "
            "below the unfiltered total_active the superseded pin asserted",
        )
        # orchestrator_overhead = filtered sum minus Messages (8), the same
        # relationship as before -- only the base value changed.
        self.assertLess(
            orchestrator,
            runner,
            "orchestrator_overhead must be the filtered sum minus Messages",
        )
        self.assertEqual(runner - orchestrator, 8)

    def test_derive_thresholds_low_overhead(self):
        ts = _engine()
        thresholds = ts.derive_thresholds(150000, 26000)
        # available = 150000 - 26000 - 6000 = 118000
        self.assertEqual(thresholds["available_per_task"], 118000)
        # critical = available - 10000 = 108000
        self.assertEqual(thresholds["critical"], 108000)
        # warn = min(40000, round(0.5*available)) = 40000
        self.assertEqual(thresholds["warn"], 40000)

    def test_derive_thresholds_high_overhead(self):
        ts = _engine()
        thresholds = ts.derive_thresholds(150000, 70000)
        # available = 150000 - 70000 - 6000 = 74000
        self.assertEqual(thresholds["available_per_task"], 74000)
        # critical = available - 10000 = 64000
        self.assertEqual(thresholds["critical"], 64000)
        # warn = min(40000, round(0.5*74000)) = min(40000, 37000) = 37000
        self.assertEqual(thresholds["warn"], 37000)


# ---------------------------------------------------------------------------
# Step 8 — Capture-failure fallback
# ---------------------------------------------------------------------------
class TestCaptureFailureFallback(unittest.TestCase):
    """calibrate() with a failed capture writes conservative fallbacks."""

    def test_capture_none_writes_conservative_fallback(self):
        ts = _engine()

        # Stub capture: simulate a missing CLI by returning None.
        def _stub_capture(*_args, **_kwargs):
            return None

        result = ts.calibrate(capture=_stub_capture)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "Failed capture must fall back to runner_overhead=54000",
        )
        self.assertEqual(
            result.get("token_saver_orchestrator_overhead"),
            60000,
            "Failed capture must fall back to orchestrator_overhead=60000",
        )
        # A flag/marker that the thresholds are uncalibrated.
        self.assertFalse(
            result.get("calibrated", True),
            "A failed capture must mark the result uncalibrated",
        )


# ---------------------------------------------------------------------------
# R2 migration: session-start range + injected-rule key + checked-writer
# routing on a successful capture
# ---------------------------------------------------------------------------
class TestCalibrateNewKeysOnSuccessfulCapture(unittest.TestCase):
    """calibrate() on a successful capture writes the R2-added keys.

    `token_saver_session_start_range` must be a `{min, median, max}`
    mapping (never a bare scalar), and `token_saver_injected_rules_estimate`
    must be present and distinct from the flat runner/orchestrator
    overheads it used to be folded into.
    """

    @staticmethod
    def _stub_capture(*_args, **_kwargs):
        return CONTEXT_REPORT_FIXTURE

    def test_session_start_range_has_min_median_max(self):
        ts = _engine()
        result = ts.calibrate(capture=self._stub_capture)
        range_value = result.get("token_saver_session_start_range")
        self.assertIsInstance(
            range_value,
            dict,
            "token_saver_session_start_range must be a {min, median, max} "
            "mapping, not a bare scalar",
        )
        self.assertIn("min", range_value)
        self.assertIn("median", range_value)
        self.assertIn("max", range_value)
        # A single capture stores the one reading in all three slots.
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        total_active = report["total_active"]
        self.assertEqual(range_value["min"], total_active)
        self.assertEqual(range_value["median"], total_active)
        self.assertEqual(range_value["max"], total_active)

    def test_injected_rules_estimate_present_and_distinct(self):
        ts = _engine()
        result = ts.calibrate(capture=self._stub_capture)
        injected = result.get("token_saver_injected_rules_estimate")
        self.assertIsNotNone(injected)
        # "Memory files" category row (2k -> 2000 per the fixture).
        self.assertEqual(injected, 2000)
        # Distinct from the flat runner/orchestrator overheads it used to
        # be folded into (rather than reported as its own figure).
        self.assertNotEqual(injected, result.get("token_saver_runner_overhead"))
        self.assertNotEqual(injected, result.get("token_saver_orchestrator_overhead"))

    def test_write_back_routes_through_checked_writer(self):
        """Regression guard for the committed contract: every write-back
        MUST still route through write_config_checked(), even after the R2
        derivation change added two new written keys.
        """
        import context_calibration
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory(prefix="tc_calibrate_") as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text("context:\n  token_saver: true\n", encoding="utf-8")
            with patch.object(context_calibration, "write_config_checked") as mock_write:
                context_calibration.calibrate(
                    config_path=config_path, capture=self._stub_capture
                )
            mock_write.assert_called_once()


# ---------------------------------------------------------------------------
# Windows shim resolution + parse guard for headless non-report reply
# ---------------------------------------------------------------------------
class TestCaptureContextWindowsInvocation(unittest.TestCase):
    """capture_context() routes through powershell.exe on Windows.

    `/context` only renders when a real console is attached; launched directly
    from pipe stdio (Git Bash / MSYS / a console-less parent) it falls through as
    a prompt and returns conversational text.  powershell.exe attaches a console,
    so the report renders — it also resolves the `claude` shim itself, so no
    shutil.which / shell=True is needed on Windows.
    """

    def test_windows_routes_through_powershell(self):
        import context_calibration
        from unittest.mock import MagicMock, patch

        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(context_calibration.os, "name", "nt"), \
             patch.object(context_calibration.subprocess, "run", return_value=fake_proc) as mock_run:
            result = context_calibration.capture_context(r"C:\plugins\planwise", "/some/cwd")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        self.assertEqual(cmd[0], "powershell.exe",
                         "capture_context must launch via powershell.exe on Windows")
        self.assertIn("-NoProfile", cmd)
        self.assertIn("-Command", cmd)
        inner = cmd[-1]
        self.assertIn("/context", inner,
                      "the powershell -Command must invoke claude -p /context")
        self.assertIn(r"C:\plugins\planwise", inner,
                      "the powershell -Command must pass the plugin dir")
        self.assertFalse(call_args[1].get("shell"),
                         "powershell.exe is launched directly; shell must be False")
        self.assertIsNotNone(result)

    def test_posix_uses_shell_false(self):
        import context_calibration
        from unittest.mock import MagicMock, patch

        fake_bin = "/usr/local/bin/claude"
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(context_calibration.os, "name", "posix"), \
             patch.object(context_calibration.shutil, "which", return_value=fake_bin), \
             patch.object(context_calibration.subprocess, "run", return_value=fake_proc) as mock_run:
            result = context_calibration.capture_context("/some/plugin", "/some/cwd")

        call_args = mock_run.call_args
        self.assertFalse(call_args[1].get("shell"),
                         "capture_context must pass shell=False on POSIX")
        self.assertIsNotNone(result)

    def test_windows_context_is_sole_prompt_argument_and_wrapper_present(self):
        """Capture-shape regression guard (pins existing correct behavior;
        it does not verify a change).

        `/context` must remain the SOLE content of the `-p` prompt argument
        on the Windows branch, and the powershell.exe console-attachment
        wrapper must remain in place. Embedding `/context` after other
        content is answered conversationally instead of rendering the
        report (parses to total_active=0, see TestCalibrateParseGuard
        below); unwinding the powershell.exe wrapper re-opens the
        console-attachment defect it exists to close -- a future
        "simplification" of either must fail here.
        """
        import context_calibration
        from unittest.mock import MagicMock, patch

        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(context_calibration.os, "name", "nt"), \
             patch.object(context_calibration.subprocess, "run", return_value=fake_proc) as mock_run:
            context_calibration.capture_context(r"C:\plugins\planwise", "/some/cwd")

        cmd = mock_run.call_args[0][0]
        # The console-attaching powershell.exe wrapper must still be present.
        self.assertEqual(cmd[0], "powershell.exe",
                         "the powershell.exe console-attachment wrapper must not be removed")
        inner = cmd[-1]
        match = re.search(r'-p\s+"([^"]*)"', inner)
        self.assertIsNotNone(match, 'the inner command must invoke -p "..."')
        self.assertEqual(
            match.group(1),
            "/context",
            "/context must be the SOLE content of the -p prompt argument",
        )

    def test_posix_context_is_sole_prompt_argument(self):
        """Capture-shape regression guard (pins existing correct behavior;
        it does not verify a change): on POSIX, `/context` is argv[2], the
        exact and sole content of that argv slot -- not concatenated with
        other text.
        """
        import context_calibration
        from unittest.mock import MagicMock, patch

        fake_bin = "/usr/local/bin/claude"
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.stdout = CONTEXT_REPORT_FIXTURE

        with patch.object(context_calibration.os, "name", "posix"), \
             patch.object(context_calibration.shutil, "which", return_value=fake_bin), \
             patch.object(context_calibration.subprocess, "run", return_value=fake_proc) as mock_run:
            context_calibration.capture_context("/some/plugin", "/some/cwd")

        cmd = mock_run.call_args[0][0]
        self.assertEqual(
            cmd,
            [fake_bin, "-p", "/context", "--plugin-dir", "/some/plugin"],
            "/context must be the sole, exact content of the -p argv slot",
        )


class TestCalibrateParseGuard(unittest.TestCase):
    """calibrate() treats a non-report (conversational) reply as a failed capture.

    headless `claude -p "/context"` may return plain prose instead of the
    structured `/context` report.  Such a reply has no `**Tokens:**` header and
    no category table.  calibrate() must fall back to the conservative overheads
    (runner=54000 / orchestrator=60000, calibrated=False) — NOT write
    runner_overhead=0 flagged calibrated:True.
    """

    CONVERSATIONAL_REPLY = (
        "Sure! The /context command shows your current context usage. "
        "It displays how many tokens are in use across different categories "
        "such as system prompt, tools, memory files, and messages."
    )

    def test_conversational_reply_falls_back_to_conservative(self):
        ts = _engine()

        def _stub_conversational(*_args, **_kwargs):
            return self.CONVERSATIONAL_REPLY

        result = ts.calibrate(capture=_stub_conversational)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "A conversational reply (no Tokens: header, no categories) must fall "
            "back to runner_overhead=54000",
        )
        self.assertEqual(
            result.get("token_saver_orchestrator_overhead"),
            60000,
            "A conversational reply must fall back to orchestrator_overhead=60000",
        )
        self.assertFalse(
            result.get("calibrated", True),
            "A conversational reply must mark the result uncalibrated",
        )

    # A partial/garbled report: a `### category` table with ONLY the excluded
    # rows (deferred tools + free space) and NO `**Tokens:**` header.  It parses
    # to non-empty categories but total_active=0, so a guard keyed only on
    # "no header AND no categories" would let it through and write
    # runner_overhead=0 (== total_active) flagged calibrated:True — exactly the
    # edge the acceptance criterion says to prevent.
    DEGENERATE_REPORT = (
        "## Context Usage\n"
        "### Estimated usage by category\n"
        "| Category | Tokens | Percentage |\n"
        "| System tools (deferred) | 16.4k | 1.6% |\n"
        "| Free space | 974.3k | 97.4% |\n"
    )

    def test_zero_active_total_falls_back_not_calibrated(self):
        ts = _engine()

        # Sanity: the fixture parses to non-empty categories but total_active 0.
        report = ts.parse_context_report(self.DEGENERATE_REPORT)
        self.assertTrue(report["categories"], "fixture must have category rows")
        self.assertEqual(
            report["total_active"],
            0,
            "fixture must yield total_active=0 (only deferred/free-space rows)",
        )

        def _stub_degenerate(*_args, **_kwargs):
            return self.DEGENERATE_REPORT

        result = ts.calibrate(capture=_stub_degenerate)
        self.assertEqual(
            result.get("token_saver_runner_overhead"),
            54000,
            "A report yielding total_active=0 must fall back — never write "
            "runner_overhead=0 flagged calibrated:True",
        )
        self.assertFalse(
            result.get("calibrated", True),
            "A zero-active-total report must be marked uncalibrated",
        )


class TestStructuralFloor(unittest.TestCase):
    """derive_structural_floor() derives the per-subcommand floor from a tree.

    The floor counts the skill body + handler body + that handler's own
    "always load" references, and EXCLUDES the base-context references the
    skill merely links — per-Read transcript attribution shows those never
    load, so counting them would store ~22.5K tok/invocation of phantom cost
    into a live budget input.
    """

    def _tree(self, handler_body, always_load_files=()):
        """Build a minimal plugin tree on disk and return its root."""
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "skills" / "planwise").mkdir(parents=True)
        (root / "handlers").mkdir()
        (root / "references").mkdir()
        # Skill body: 3 newlines.
        (root / "skills" / "planwise" / "SKILL.md").write_text(
            "a\nb\nc\n", encoding="utf-8"
        )
        (root / "handlers" / "demo.md").write_text(handler_body, encoding="utf-8")
        for name, body in always_load_files:
            (root / "references" / name).write_text(body, encoding="utf-8")
        # A base-context reference that nothing may count.
        (root / "references" / "callout-conventions.md").write_text(
            "x\n" * 5000, encoding="utf-8"
        )
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_always_load_references_extracts_the_declared_set(self):
        """always_load_references() reads the handler's own always-load block."""
        ts = _engine()
        body = (
            "## Required References\n\n"
            "**Base references** (`markdown-conventions.md`) are pre-injected by SKILL.md.\n\n"
            "**Demo-specific references (always load):**\n"
            "1. Read `references/alpha.md`\n"
            "2. Read `references/beta.md` -- with trailing prose\n\n"
            "**Conditional references:**\n"
            "- If X: Read `references/gamma.md`\n\n"
            "---\n"
        )
        self.assertEqual(
            ts.always_load_references(body),
            ["alpha.md", "beta.md"],
            "Only the always-load block counts; conditional and base refs must not",
        )

    def test_always_load_absent_yields_empty(self):
        """A handler with no always-load block contributes no references."""
        ts = _engine()
        body = "## Required References\n\n**Conditional references:**\n- Read `references/g.md`\n\n---\n"
        self.assertEqual(ts.always_load_references(body), [])

    def test_floor_sums_skill_handler_and_always_load(self):
        """The floor is skill + handler + always-load, by newline count and bytes."""
        ts = _engine()
        handler = (
            "h1\nh2\n"
            "**Demo-specific references (always load):**\n"
            "1. Read `references/alpha.md`\n\n"
            "---\n"
        )
        root = self._tree(handler, [("alpha.md", "r1\nr2\nr3\n")])
        floor = ts.derive_structural_floor(root)
        demo = floor["subcommands"]["demo"]

        skill_lines = 3
        handler_lines = handler.count("\n")
        self.assertEqual(demo["lines"], skill_lines + handler_lines + 3)
        self.assertEqual(demo["always_load"], ["alpha.md"])
        self.assertEqual(
            demo["tokens"],
            int(round(demo["bytes"] / ts.STRUCTURAL_FLOOR_BYTES_PER_TOKEN)),
            "Tokens must come from bytes, never from a per-line rate",
        )

    def test_floor_excludes_the_base_context(self):
        """The linked base context must NOT be counted, however large it is."""
        ts = _engine()
        handler = "h1\n\n---\n"
        root = self._tree(handler)
        floor = ts.derive_structural_floor(root)
        demo = floor["subcommands"]["demo"]

        # callout-conventions.md is 10,000 bytes in the fixture tree.
        self.assertLess(
            demo["bytes"],
            1000,
            "A base-context reference the skill only LINKS must not enter the floor",
        )
        self.assertTrue(floor["excludes_base_context"])

    def test_floor_is_tree_labelled(self):
        """A floor figure without its tree label is unusable — carry the label."""
        ts = _engine()
        root = self._tree("h\n\n---\n")
        floor = ts.derive_structural_floor(root)
        self.assertEqual(floor["tree"], str(root))
        self.assertTrue(floor["derived_on"])
        self.assertEqual(
            floor["bytes_per_token"], ts.STRUCTURAL_FLOOR_BYTES_PER_TOKEN
        )

    def test_floor_degrades_on_a_missing_tree(self):
        """A missing/None tree yields an empty floor, never a crash."""
        ts = _engine()
        self.assertEqual(ts.derive_structural_floor(None)["subcommands"], {})
        self.assertEqual(
            ts.derive_structural_floor("/nonexistent/plugin/root")["subcommands"], {}
        )

    def test_format_floor_is_single_line_flow_mapping(self):
        """The rendered value stays on one line for the targeted write-back."""
        ts = _engine()
        root = self._tree("h\n\n---\n")
        rendered = ts._format_floor(ts.derive_structural_floor(root))
        self.assertTrue(rendered.startswith("{") and rendered.endswith("}"))
        self.assertNotIn("\n", rendered)
        self.assertIn("demo:", rendered)
        self.assertIn("excludes_base_context: true", rendered)
        self.assertEqual(ts._format_floor({}), "{}")

    def test_calibrate_carries_the_floor_on_the_fallback_path(self):
        """A failed capture must still yield a tree-derived floor.

        The floor comes from the tree, not the capture — a failed /context
        capture says nothing about how much instruction text an invocation
        carries, so it must not blank the floor.
        """
        ts = _engine()
        root = self._tree(
            "h1\n**Demo-specific references (always load):**\n"
            "1. Read `references/alpha.md`\n\n---\n",
            [("alpha.md", "r\n" * 10)],
        )
        result = ts.calibrate(plugin_root=root, capture=lambda *_a, **_k: None)
        self.assertFalse(result["calibrated"])
        floor = result["token_saver_structural_floor"]
        self.assertIn("demo", floor["subcommands"])
        self.assertGreater(floor["subcommands"]["demo"]["tokens"], 0)

    def test_calibrate_routes_the_floor_through_the_checked_writer(self):
        """The floor write must go through _write_back, not a bypass write.

        Regression guard for the checked-writer contract: every calibration
        value reaches config.yaml through the same parse-checked path.
        """
        ts = _engine()
        root = self._tree("h\n\n---\n")
        seen = {}

        # calibrate() resolves `_write_back` in its OWN defining module, so the
        # patch has to land there — patching the re-exporting facade would not
        # intercept the call and the test would pass vacuously.
        engine = sys.modules["context_calibration"]
        original = engine._write_back
        try:
            engine._write_back = lambda path, values: seen.update(values)
            ts.calibrate(
                config_path=root / "config.yaml",
                plugin_root=root,
                capture=lambda *_a, **_k: None,
            )
        finally:
            engine._write_back = original

        self.assertIn(
            "token_saver_structural_floor",
            seen,
            "The structural floor must be written through the checked writer",
        )
        self.assertNotIn("\n", seen["token_saver_structural_floor"])


if __name__ == "__main__":
    unittest.main()
