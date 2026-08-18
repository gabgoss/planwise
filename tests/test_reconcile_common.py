#!/usr/bin/env python3
"""Unit tests for the reconcile_plans/reconcile_backlog shared scaffolding.

`reconcile_common.py` provides `write_json_result`, `format_drift_report`,
`read_text_preserving_newlines`/`write_text_preserving_newlines`, and
`run_reconcile_cli` — the scaffolding both `reconcile_plans.py` and
`reconcile_backlog.py` reuse instead of each re-implementing the same
detect/reconcile CLI wiring.

These tests pin: `write_json_result`'s JSON round-trip and prefix use,
`format_drift_report`'s four banner shapes (no drift/no anomalies, drift
only, anomalies only, both together with the blank-line separator), the
newline-preserving read/write round-trip on both LF and CRLF content, and
`run_reconcile_cli`'s missing-index exit, detect/report dispatch, and
--write/--json dispatch — using stand-in detect/reconcile/format functions
rather than the real plans/backlog domain logic (which is pinned against the
real callers by test_reconcile_plans.py / test_reconcile_backlog.py).

Run with:  python -m pytest tests/test_reconcile_common.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from reconcile_common import (  # noqa: E402
    format_drift_report,
    read_text_preserving_newlines,
    run_reconcile_cli,
    write_json_result,
    write_text_preserving_newlines,
)


class TestWriteJsonResult(unittest.TestCase):
    def test_writes_result_under_the_given_prefix_and_round_trips(self):
        result = {"drifts": [{"abbrev": "FOO"}], "anomalies": []}

        path = write_json_result(result, "reconcile-common-test-")

        self.assertIn("reconcile-common-test-", path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), result)


class TestFormatDriftReport(unittest.TestCase):
    """Uses stand-in messages/renderers distinct from either real caller's
    wording, so these tests pin the shared shape rather than accidentally
    re-pinning reconcile_plans'/reconcile_backlog's own banner text.
    """

    def _format(self, result):
        return format_drift_report(
            result,
            no_drift_message="No drift.",
            no_drift_only_message="No status drift.",
            drift_header=f"Drift ({len(result['drifts'])}):",
            drift_line=lambda d: f"  - {d['name']}",
            anomaly_line=lambda a: f"  - {a['name']}",
        )

    def test_no_drift_no_anomalies_returns_the_short_message(self):
        result = {"drifts": [], "anomalies": []}
        self.assertEqual(self._format(result), "No drift.")

    def test_drift_only(self):
        result = {"drifts": [{"name": "A"}], "anomalies": []}
        self.assertEqual(self._format(result), "Drift (1):\n  - A")

    def test_anomalies_only_uses_the_no_drift_only_line(self):
        result = {"drifts": [], "anomalies": [{"name": "B"}]}
        self.assertEqual(
            self._format(result), "No status drift.\n\nAnomalies (1):\n  - B"
        )

    def test_drift_and_anomalies_are_blank_line_separated(self):
        result = {"drifts": [{"name": "A"}], "anomalies": [{"name": "B"}]}
        self.assertEqual(
            self._format(result), "Drift (1):\n  - A\n\nAnomalies (1):\n  - B"
        )

    def test_multiple_rows_of_each_kind(self):
        result = {
            "drifts": [{"name": "A"}, {"name": "B"}],
            "anomalies": [{"name": "C"}, {"name": "D"}],
        }
        self.assertEqual(
            self._format(result),
            "Drift (2):\n  - A\n  - B\n\nAnomalies (2):\n  - C\n  - D",
        )


class TestPreservingNewlines(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_common_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_crlf_round_trips_byte_exact(self):
        path = self.tmp / "crlf.txt"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("a\r\nb\r\n")

        content = read_text_preserving_newlines(path)
        self.assertEqual(content, "a\r\nb\r\n")

        write_text_preserving_newlines(path, content.replace("a", "x"))

        raw = path.read_bytes()
        self.assertEqual(raw, b"x\r\nb\r\n")

    def test_lf_round_trips_without_crlf_translation(self):
        path = self.tmp / "lf.txt"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("a\nb\n")

        content = read_text_preserving_newlines(path)
        write_text_preserving_newlines(path, content)

        raw = path.read_bytes()
        self.assertEqual(raw, b"a\nb\n")
        self.assertNotIn(b"\r\n", raw)


class _CliFixtureBase(unittest.TestCase):
    """Drives run_reconcile_cli with stand-in detect/reconcile/format_report
    functions and a controllable sys.argv, so these tests exercise the
    scaffold's dispatch logic in isolation from any real index format.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_common_cli_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.index_path = self.tmp / "index.md"

        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def run_cli(self, argv, **overrides):
        sys.argv = ["test_reconcile_common"] + argv
        kwargs = dict(
            description="Test CLI",
            load_config=lambda: {},
            resolve_index_path=lambda config: self.index_path,
            missing_index_message=lambda p: f"Error: index not found at {p}",
            detect_drift=lambda config: {"drifts": [], "anomalies": []},
            reconcile=lambda config: 0,
            format_report=lambda result: "report",
            json_prefix="reconcile-common-cli-test-",
        )
        kwargs.update(overrides)
        run_reconcile_cli(**kwargs)


class TestRunReconcileCliMissingIndex(_CliFixtureBase):
    def test_exits_1_when_index_path_does_not_exist(self):
        # self.index_path is never created.
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli([])
        self.assertEqual(ctx.exception.code, 1)


class TestRunReconcileCliDetectMode(_CliFixtureBase):
    def test_prints_the_format_report_output(self):
        self.index_path.write_text("x", encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.run_cli(
                [],
                detect_drift=lambda config: {"drifts": [{"a": 1}], "anomalies": []},
                format_report=lambda result: f"n={len(result['drifts'])}",
            )

        self.assertIn("n=1", out.getvalue())

    def test_json_flag_writes_and_prints_json_path(self):
        self.index_path.write_text("x", encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.run_cli(
                ["--json"],
                detect_drift=lambda config: {"drifts": [], "anomalies": []},
            )

        self.assertIn("JSON:", out.getvalue())


class TestRunReconcileCliWriteMode(_CliFixtureBase):
    def test_write_flag_calls_reconcile_and_prints_count(self):
        self.index_path.write_text("x", encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.run_cli(["--write"], reconcile=lambda config: 3)

        self.assertIn("Reconciled 3 row(s).", out.getvalue())

    def test_write_plus_json_dumps_a_fresh_detect_after_reconcile(self):
        self.index_path.write_text("x", encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.run_cli(
                ["--write", "--json"],
                reconcile=lambda config: 1,
                detect_drift=lambda config: {"drifts": [], "anomalies": []},
            )

        printed = out.getvalue()
        self.assertIn("Reconciled 1 row(s).", printed)
        self.assertIn("JSON:", printed)

    def test_write_without_json_does_not_call_detect_drift(self):
        # --write alone must not invoke detect_drift at all (only the
        # --write + --json combination does, for the post-write dump).
        self.index_path.write_text("x", encoding="utf-8")

        def _boom(config):
            raise AssertionError("detect_drift must not be called")

        with contextlib.redirect_stdout(io.StringIO()):
            self.run_cli(["--write"], reconcile=lambda config: 0, detect_drift=_boom)


if __name__ == "__main__":
    unittest.main()
