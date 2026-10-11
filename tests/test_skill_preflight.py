#!/usr/bin/env python3
"""Tests for scripts/skill_preflight.py (the router behind the skill's injected line).

The router runs as a subprocess, as the skill runs it, with `cwd` set to a temp
fixture root so branch a) of the config resolution finds `planwise/config.yaml`.
None of these tests read or write the live project.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_skill_preflight.py
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

sys.dont_write_bytecode = True

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS_DIR / "skill_preflight.py"
SKILL_MD = REPO_DIR / "plugins" / "planwise" / "skills" / "planwise" / "SKILL.md"

sys.path.insert(0, str(SCRIPTS_DIR))

import config_loader
from generate_plans_index import TABLE_SEPARATOR, render_plans_index

CONFIG_YAML = """project:
  name: "PreflightFixtureProject"
  plans_dir: "Plans"
  index_files:
    plans: "00-Index-Plans.md"
"""

BEGIN = "<!-- planwise:list:begin -->"
END = "<!-- planwise:list:end -->"
FALLBACK = "PLANWISE_LIST_FALLBACK:"
NO_DRIFT = "No drift detected. All index rows match their Master Plan status."
ROUTING_ROW = re.compile(r"^\| `([a-z-]+)` \| ", re.MULTILINE)


def _row(abbrev, name, status):
    return f"| {abbrev} | {name} | {status} | 2026-01-01 | 2026-01-01 | {name}/ |\n"


def run_router(args, cwd):
    """Run the router the way the skill does and return the completed process."""
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd),
        timeout=60,
        check=False,
    )


def run_router_in_process_probe(args, cwd):
    """Call `skill_preflight.main(args)` in a fresh interpreter. Returns (stdout, list_plans_imported)."""
    code = (
        "import contextlib, io, json, sys\n"
        "sys.dont_write_bytecode = True\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import skill_preflight\n"
        "buf = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf):\n"
        f"    skill_preflight.main({list(args)!r})\n"
        "print(json.dumps([buf.getvalue(), 'list_plans' in sys.modules]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd),
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"probe failed: {proc.stderr}")
    stdout, imported = json.loads(proc.stdout.strip().split("\n")[-1])
    return stdout, imported


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skill_preflight_test_")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True)
        (self.planwise_dir / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")

    def build_plans(self, plans):
        """Write a generated-shape index plus one Master Plan per (abbrev, name, status)."""
        config = config_loader.load_config(config_path=self.planwise_dir / "config.yaml")
        frame = render_plans_index(config).frame
        rows = "".join(_row(a, n, s) for a, n, s in plans)
        text = frame.replace(TABLE_SEPARATOR + "\n", TABLE_SEPARATOR + "\n" + rows, 1)
        (self.plans_dir / "00-Index-Plans.md").write_text(text, encoding="utf-8")
        for abbrev, name, status in plans:
            mp_dir = self.plans_dir / name
            mp_dir.mkdir(parents=True, exist_ok=True)
            body = f"# {abbrev} Master Plan\n\n**Status:** {status}\n**Created:** 2026-01-01\n\n*Last Updated: 2026-01-01*\n"
            (mp_dir / f"{abbrev}-Master-Plan.md").write_text(body, encoding="utf-8")


class TestListRoute(_Fixture):
    def setUp(self):
        super().setUp()
        self.build_plans([("AAA", "Alpha", "COMPLETE"), ("BBB", "Beta", "IN_PROGRESS")])

    def test_list_prints_markers_banner_and_table(self):
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        lines = proc.stdout.split("\n")
        self.assertEqual(lines[0], BEGIN)
        self.assertEqual(proc.stdout.count(BEGIN), 1)
        self.assertEqual(proc.stdout.count(END), 1)
        self.assertLess(proc.stdout.index(BEGIN), proc.stdout.index(END))
        self.assertIn(NO_DRIFT, proc.stdout)
        self.assertIn("| AAA | Alpha | COMPLETE |", proc.stdout)
        self.assertIn("| BBB | Beta | IN_PROGRESS |", proc.stdout)
        self.assertNotIn(FALLBACK, proc.stdout)

    def test_list_active_filters_and_keeps_banner(self):
        proc = run_router(["list", "--active", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(BEGIN, proc.stdout)
        self.assertIn(END, proc.stdout)
        self.assertIn("1 active plan(s) shown", proc.stdout)
        self.assertIn("| BBB | Beta | IN_PROGRESS |", proc.stdout)
        self.assertNotIn("| AAA |", proc.stdout)
        self.assertIn("drift audit", proc.stdout)

    def test_list_no_check_drops_banner(self):
        proc = run_router(["list", "--active", "--no-check"], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(BEGIN, proc.stdout)
        self.assertIn(END, proc.stdout)
        self.assertNotIn("drift audit", proc.stdout)
        self.assertNotIn("No drift detected", proc.stdout)
        self.assertIn("1 active plan(s) shown", proc.stdout)

    def test_flag_order_and_unknown_flag(self):
        proc = run_router(["list", "--no-check", "--bogus"], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("drift audit", proc.stdout)
        self.assertIn("2 plan(s) shown", proc.stdout)

    def test_leading_empty_values_are_dropped(self):
        proc = run_router(["", "list", "--no-check"], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(BEGIN, proc.stdout)
        self.assertNotIn("drift audit", proc.stdout)

    def test_unexpanded_placeholder_flags_are_dropped(self):
        proc = run_router(["list", "$flag1", "$flag2"], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(BEGIN, proc.stdout)
        self.assertIn("drift audit", proc.stdout)
        self.assertIn("2 plan(s) shown", proc.stdout)


class TestSilentRoutes(_Fixture):
    """Every non-list input prints nothing, exits 0 and writes nothing to stderr."""

    CASES: ClassVar[dict[str, list[str]]] = {
        "no args": [],
        "N0 three empty strings": ["", "", ""],
        "single empty string": [""],
        "literal $0": ["$0"],
        "literal positionals": ["$0", "$1", "$2"],
        "literal named placeholders": ["$sub", "$flag1", "$flag2"],
        "whitespace only": ["  ", "", ""],
        "run": ["run", "", ""],
        "help": ["help", "", ""],
        "help with flags": ["help", "--active", "--no-check"],
        "flags without a subcommand": ["--active", "--no-check", ""],
        "list is not the first token": ["run", "list", ""],
        "bogus subcommand": ["bogus", "", ""],
        "apostrophe in a value": ["lessons", "don't", ""],
    }

    def test_silent_cases(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        for label, args in self.CASES.items():
            with self.subTest(case=label):
                proc = run_router(args, self.tmp)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(proc.stderr, "")

    def test_silent_cases_with_no_planwise_tree(self):
        bare = Path(tempfile.mkdtemp(prefix="skill_preflight_bare_")).resolve()
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        for label, args in self.CASES.items():
            with self.subTest(case=label):
                proc = run_router(args, bare)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(proc.stderr, "")


class TestSilentForEveryRoutedSubcommand(_Fixture):
    """The silence claim holds over the live routing table, not a hand-written list."""

    @classmethod
    def routed_subcommands(cls):
        return set(ROUTING_ROW.findall(SKILL_MD.read_text(encoding="utf-8")))

    def test_extraction_finds_list_and_at_least_two_members(self):
        subs = self.routed_subcommands()
        self.assertIn("list", subs)
        self.assertGreaterEqual(len(subs), 2)

    def test_positive_control_list_prints_the_begin_marker(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.stdout.split("\n")[0], BEGIN)
        stdout, imported = run_router_in_process_probe(["list", "", "--no-check"], self.tmp)
        self.assertTrue(stdout.startswith(BEGIN))
        self.assertTrue(imported)

    def test_every_other_subcommand_is_silent_and_imports_nothing(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        others = sorted(self.routed_subcommands() - {"list"})
        self.assertTrue(others)
        for sub in others:
            for args in ([sub, "", ""], [sub, "--active", "--no-check"]):
                with self.subTest(args=args):
                    proc = run_router(args, self.tmp)
                    self.assertEqual(proc.returncode, 0)
                    self.assertEqual(proc.stdout, "")
                    self.assertEqual(proc.stderr, "")
                    stdout, imported = run_router_in_process_probe(args, self.tmp)
                    self.assertEqual(stdout, "")
                    self.assertFalse(imported)

    def test_empty_bogus_and_apostrophe_inputs_are_silent(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        for args in (["", "", ""], ["bogus", "", ""], ["lessons", "don't", ""]):
            with self.subTest(args=args):
                proc = run_router(args, self.tmp)
                self.assertEqual(proc.stdout, "")
                stdout, imported = run_router_in_process_probe(args, self.tmp)
                self.assertEqual(stdout, "")
                self.assertFalse(imported)


class TestFallbackRoutes(_Fixture):
    def fallback_lines(self, stdout):
        return [ln for ln in stdout.split("\n") if ln.startswith(FALLBACK)]

    def test_list_in_empty_directory_prints_one_fallback_between_markers(self):
        empty = Path(tempfile.mkdtemp(prefix="skill_preflight_empty_")).resolve()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        proc = run_router(["list", "", ""], empty)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        lines = [ln for ln in proc.stdout.split("\n") if ln]
        self.assertEqual(lines[0], BEGIN)
        self.assertEqual(lines[-1], END)
        found = self.fallback_lines(proc.stdout)
        self.assertEqual(len(found), 1)
        self.assertIn("config.yaml not found", found[0])
        self.assertEqual(lines[1], found[0])

    def test_unreadable_config_still_prints_marker_and_exits_zero(self):
        (self.planwise_dir / "config.yaml").unlink()
        (self.planwise_dir / "config.yaml").mkdir()
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(BEGIN, proc.stdout)
        self.assertIn(END, proc.stdout)
        self.assertEqual(len(self.fallback_lines(proc.stdout)), 1)

    def test_missing_index_prints_marker(self):
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        found = self.fallback_lines(proc.stdout)
        self.assertEqual(len(found), 1)
        self.assertIn("Plans index not found at", found[0])
        self.assertEqual(proc.stderr, "")


if __name__ == "__main__":
    unittest.main()
