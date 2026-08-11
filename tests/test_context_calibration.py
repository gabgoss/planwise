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

    def test_derive_overheads_from_breakdown(self):
        ts = _engine()
        report = ts.parse_context_report(CONTEXT_REPORT_FIXTURE)
        overheads = ts.derive_overheads(report)
        runner = overheads["runner_overhead"]
        orchestrator = overheads["orchestrator_overhead"]
        # runner_overhead = active footprint (conservative proxy).
        self.assertGreaterEqual(runner, 25000)
        self.assertLessEqual(runner, 26500)
        # orchestrator_overhead = active footprint minus Messages (8).
        self.assertLess(
            orchestrator,
            runner,
            "orchestrator_overhead must be active footprint minus Messages",
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
