#!/usr/bin/env python3
"""A script rejects a command-line flag it does not declare.

Each script used to parse with `parse_known_args` and discard the leftovers, so a
misspelled flag exited 0 with no warning and the requested work did not happen.
These tests run every main-parse script as a subprocess with a flag no script
declares and assert exit 2 and argparse's `unrecognized arguments` line. They
also prove the two deliberate pre-parses still tolerate the whole command line.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_unknown_flag_rejected.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import config_loader

BOGUS = "--no-such-flag"
UNRECOGNIZED = f"unrecognized arguments: {BOGUS}"

# (script, leading arguments the parser needs before it reaches the leftover check)
MAIN_PARSE_SCRIPTS = [
    ("generate_plans_index", []),
    ("generate_backlog_index", []),
    ("generate_lessons_index", []),
    ("lint_verification_gates", ["."]),
    ("parse_backlog", []),
    ("parse_lessons", ["--config", "config.yaml"]),
    ("reconcile_backlog", []),
    ("reconcile_backlog", ["--body-status"]),
    ("reconcile_plans", []),
    ("reconcile_lessons", []),
    ("score_backlog", []),
    ("update_backlog", ["--id", "1"]),
]


class _ScratchBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="unknown_flag_test_")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_script(self, name, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / f"{name}.py"), *args],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )


class TestMainParseRejectsUnknownFlag(_ScratchBase):
    def test_each_main_parse_script_exits_2_on_an_unknown_flag(self):
        for name, leading in MAIN_PARSE_SCRIPTS:
            with self.subTest(script=name, leading=leading):
                result = self.run_script(name, *leading, BOGUS)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(UNRECOGNIZED, result.stderr)

    def test_a_rejected_run_writes_nothing(self):
        for name, leading in MAIN_PARSE_SCRIPTS:
            with self.subTest(script=name, leading=leading):
                self.run_script(name, *leading, BOGUS)
                self.assertEqual(list(self.tmp.iterdir()), [])

    def test_a_misspelled_resolution_flag_is_refused_by_update_backlog(self):
        result = self.run_script(
            "update_backlog", "--id", "664", "--status", "COMPLETE", "--resolution-flie", "x.md"
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrecognized arguments: --resolution-flie x.md", result.stderr)

    def test_list_plans_keeps_its_exit_0_contract_and_prints_the_marker(self):
        result = self.run_script("list_plans", BOGUS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(UNRECOGNIZED, result.stderr)
        self.assertIn("PLANWISE_LIST_FALLBACK:", result.stdout)

    def test_a_malformed_mode_flag_no_longer_falls_through_to_the_default_mode(self):
        result = self.run_script("reconcile_backlog", "--body-status=1")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrecognized arguments: --body-status=1", result.stderr)


class TestDeclaredFlagsStillAccepted(_ScratchBase):
    def test_config_is_accepted_by_the_scripts_that_read_it_back_from_argv(self):
        missing = str(self.tmp / "nope.yaml")
        for name in ("parse_backlog", "update_backlog"):
            with self.subTest(script=name):
                leading = ["--id", "1"] if name == "update_backlog" else []
                result = self.run_script(name, "--config", missing, *leading)
                self.assertNotIn("unrecognized arguments", result.stderr)
                self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_help_exits_0_for_every_main_parse_script(self):
        for name, _ in MAIN_PARSE_SCRIPTS:
            with self.subTest(script=name):
                result = self.run_script(name, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)


class TestPreParsesStillTolerateTheWholeCommandLine(unittest.TestCase):
    def test_config_pre_parse_ignores_every_other_flag(self):
        argv = ["x.py", "--status", "COMPLETE", BOGUS, "--config", "elsewhere.yaml", "positional"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(config_loader._get_config_path_from_args(), Path("elsewhere.yaml"))

    def test_mode_pre_parse_ignores_every_other_flag(self):
        import reconcile_backlog

        calls = []
        argv = ["x.py", "--body-status", "--write", BOGUS]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(reconcile_backlog, "_run_body_status_cli", lambda: calls.append("body")),
        ):
            reconcile_backlog.main()
        self.assertEqual(calls, ["body"])


if __name__ == "__main__":
    unittest.main()
