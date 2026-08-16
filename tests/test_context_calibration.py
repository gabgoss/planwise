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


if __name__ == "__main__":
    unittest.main()
