#!/usr/bin/env python3
"""Unit tests for check_plan_plugin_paths.py, the gate that flags a plan's
markdown naming a versioned plugin-cache script path that differs from the
pinned plugin_version.

Each test builds a fixture tree in a temporary directory under the system temp
root and invokes the script's real main() with an injected argv, so argument
parsing, the scan, the coverage line and the exit-code paths all run.

Covers: a must-fail control (stale path, exit 1) and a must-pass control
(version-free path, exit 0); the pinned version; a back-slash path; skipped
record files; the ratio warning (only beside a stale path); and the three exit 2
cases (empty plan folder, no plugin_version, missing config).

Run with:  python -m pytest tests/test_check_plan_plugin_paths.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_plan_plugin_paths

PINNED = "1.0.5.4"
STALE = "1.0.5.3"

CONFIG_WITH_VERSION = f"""project:
  name: "CheckPlanPluginPathsFixtureProject"
  backlog_dir: "Backlog"
  plans_dir: "Plans"
  index_files:
    backlog: "00-Index-Backlog.md"
plugin_version: "{PINNED}"
"""

CONFIG_WITHOUT_VERSION = """project:
  name: "CheckPlanPluginPathsFixtureProject"
  backlog_dir: "Backlog"
  plans_dir: "Plans"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

_PREFIX = "python -B C:/Users/example/.claude/plugins/cache/planwise-marketplace/planwise/"
_SUFFIX = "/scripts/measure_files.py {output files} --model sonnet"


def _command(version: str, sep: str = "/") -> str:
    """Build the command from pieces so this file never holds a contiguous path."""
    text = _PREFIX + version + _SUFFIX
    return text if sep == "/" else text.replace("/", sep)


def _run_main(argv_tail: list[str]) -> tuple[str, str, object]:
    """Invoke check_plan_plugin_paths.main() with an injected argv.

    Returns (stdout, stderr, exit_code). main() always calls sys.exit().
    """
    saved_argv = sys.argv
    sys.argv = ["check_plan_plugin_paths"] + argv_tail
    out, err = io.StringIO(), io.StringIO()
    exit_code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                check_plan_plugin_paths.main()
            except SystemExit as e:
                exit_code = e.code
    finally:
        sys.argv = saved_argv
    return out.getvalue(), err.getvalue(), exit_code


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plugin_paths_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = self.tmp / "config.yaml"
        self.config.write_text(CONFIG_WITH_VERSION, encoding="utf-8")
        self.plan = self.tmp / "plan"
        self.plan.mkdir()

    def write(self, rel: str, text: str) -> Path:
        path = self.plan / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_check(self, target: Path | None = None, config: Path | None = None):
        argv = ["--config", str(config or self.config), str(target or self.plan)]
        return _run_main(argv)


class TestControls(_Fixture):
    def test_must_fail_control_stale_path(self):
        # Shape of a real verification line from an existing task file.
        self.write("Task-01.md", "Run:\n" + _command(STALE) + "\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[STALE]"), 1)
        self.assertIn(f"names {STALE}, pinned {PINNED}", out)

    def test_must_pass_control_version_free_path(self):
        self.write(
            "Task-01.md",
            'Run:\npython -B "{plugin_root}/scripts/measure_files.py" {output files} --model sonnet\n',
        )
        out, _, code = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "Coverage: scanned 1 files; 0 versioned paths; 0 stale.")

    def test_pinned_version_passes(self):
        self.write("Task-01.md", _command(PINNED) + "\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "Coverage: scanned 1 files; 1 versioned paths; 0 stale.")

    def test_backslash_form_is_stale(self):
        self.write("Task-01.md", _command(STALE, sep="\\") + "\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[STALE]"), 1)

    def test_three_part_version_is_matched(self):
        self.write("Task-01.md", _command("1.0.5") + "\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("names 1.0.5, pinned", out)

    def test_single_file_target(self):
        path = self.write("Task-01.md", _command(STALE) + "\n")
        out, _, code = self.run_check(target=path)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "Coverage: scanned 1 files; 1 versioned paths; 1 stale.")


class TestSkippedFiles(_Fixture):
    def test_outputs_reviews_recovery_summary_are_skipped(self):
        stale = _command(STALE) + "\n"
        self.write("Task-01.md", "clean\n")
        self.write("Outputs/notes.md", stale)
        self.write("Reviews/review.md", stale)
        self.write("Plan-Recovery.md", stale)
        self.write("Plan-Summary.md", stale)
        out, _, code = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "Coverage: scanned 1 files; 0 versioned paths; 0 stale.")


class TestRatioWarning(_Fixture):
    def test_ratio_line_beside_stale_path(self):
        self.write("Task-01.md", _command(STALE) + "\nTarget: 17,500 Sonnet tokens per Part.\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[RATIO]"), 1)
        self.assertIn('"17,500 Sonnet tokens"', out)

    def test_ratio_variants_match(self):
        self.write("Task-01.md", _command(STALE) + "\n~25K Sonnet-tokens and 13.7K sonnet tokens\n")
        out, _, _ = self.run_check()
        self.assertEqual(out.count("[RATIO]"), 2)

    def test_no_ratio_line_without_stale_path(self):
        self.write("Task-01.md", "Target: 17,500 Sonnet tokens per Part.\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(out.count("[RATIO]"), 0)


class TestNotChecked(_Fixture):
    def test_empty_plan_folder(self):
        out, _, code = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("NOT CHECKED", out)

    def test_plan_folder_with_only_skipped_files(self):
        self.write("Outputs/notes.md", _command(STALE) + "\n")
        out, _, code = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("NOT CHECKED", out)

    def test_missing_plan_path(self):
        out, _, code = self.run_check(target=self.tmp / "absent")
        self.assertEqual(code, 2)
        self.assertIn("NOT CHECKED", out)

    def test_config_without_plugin_version(self):
        self.write("Task-01.md", "clean\n")
        bare = self.tmp / "bare.yaml"
        bare.write_text(CONFIG_WITHOUT_VERSION, encoding="utf-8")
        out, _, code = self.run_check(config=bare)
        self.assertEqual(code, 2)
        self.assertIn("NOT CHECKED", out)

    def test_missing_config_file(self):
        self.write("Task-01.md", "clean\n")
        out, _, code = self.run_check(config=self.tmp / "absent.yaml")
        self.assertEqual(code, 2)
        self.assertIn("NOT CHECKED", out)


if __name__ == "__main__":
    unittest.main()
