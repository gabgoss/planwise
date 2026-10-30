#!/usr/bin/env python3
"""Tests for scripts/skill_preflight.py (the router behind the skill's injected line).

The router runs as a subprocess, as the skill runs it, with `cwd` set to a temp
fixture root so branch a) of the config resolution finds `planwise/config.yaml`.
None of these tests read or write the live project.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_skill_preflight.py
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.dont_write_bytecode = True

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS_DIR / "skill_preflight.py"
SKILL_MD = REPO_DIR / "plugins" / "planwise" / "skills" / "planwise" / "SKILL.md"

sys.path.insert(0, str(SCRIPTS_DIR))

import config_loader
import skill_preflight
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
UPGRADE_BEGIN = "<!-- planwise:upgrade:begin -->"
UPGRADE_END = "<!-- planwise:upgrade:end -->"
UPGRADE_FALLBACK = "PLANWISE_UPGRADE_FALLBACK:"
PLAN_BEGIN = "<!-- planwise:plan:begin -->"
PLAN_END = "<!-- planwise:plan:end -->"
PLAN_FALLBACK = "PLANWISE_PLAN_FALLBACK:"
PLAN_FIELD_KEYS = (
    "plugin_root",
    "project.planwise_root",
    "project.plans_dir",
    "project.lessons_dir",
    "project.index_files.lessons",
)
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


def run_router_module_probe(args, cwd, modules):
    """Call `skill_preflight.main(args)` in a fresh interpreter. Returns (stdout, {module: imported})."""
    code = (
        "import contextlib, io, json, sys\n"
        "sys.dont_write_bytecode = True\n"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "import skill_preflight\n"
        "buf = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf):\n"
        f"    skill_preflight.main({list(args)!r})\n"
        f"print(json.dumps([buf.getvalue(), {{m: m in sys.modules for m in {list(modules)!r}}}]))\n"
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
        self.assertIn("plan", self.routed_subcommands())  # the exclusion below must not hide a removed row
        others = sorted(self.routed_subcommands() - {"list", "upgrade", "plan"})
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


class TestUpgradeCard(_Fixture):
    """`upgrade` prints the preflight card, or one fallback line, and loads nothing for other input."""

    def run_in_process(self, args, cwd):
        """Call `skill_preflight.run(args)` here, with `cwd` as the working directory. Returns (stdout, result)."""
        previous = Path.cwd()
        os.chdir(cwd)
        self.addCleanup(os.chdir, previous)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = skill_preflight.run(args)
        return buf.getvalue(), result

    def test_no_config_prints_the_fallback_line_and_no_card(self):
        bare = Path(tempfile.mkdtemp(prefix="skill_preflight_bare_")).resolve()
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        stdout, result = self.run_in_process(["upgrade", "", ""], bare)
        self.assertEqual(result, 0)
        lines = [ln for ln in stdout.splitlines() if ln]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(UPGRADE_FALLBACK))
        self.assertIn("config.yaml not found", lines[0])
        self.assertNotIn(UPGRADE_BEGIN, stdout)

    def test_preflight_failure_prints_one_fallback_and_the_end_marker(self):
        import upgrade_preflight

        with mock.patch.object(upgrade_preflight, "run", side_effect=RuntimeError("boom")):
            stdout, result = self.run_in_process(["upgrade", "", ""], self.tmp)
        self.assertEqual(result, 0)
        self.assertEqual(
            [ln for ln in stdout.splitlines() if ln],
            [f"{UPGRADE_FALLBACK} RuntimeError: boom", UPGRADE_END],
        )

    def test_upgrade_does_not_import_list_plans(self):
        stdout, imported = run_router_module_probe(["upgrade", "", ""], self.tmp, ["list_plans"])
        self.assertIn(UPGRADE_BEGIN, stdout)
        self.assertFalse(imported["list_plans"])

    def test_other_routed_subcommands_do_not_import_upgrade_preflight(self):
        subs = TestSilentForEveryRoutedSubcommand.routed_subcommands() - {"upgrade"}
        self.assertIn("list", subs)
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        for sub in sorted(subs):
            with self.subTest(sub=sub):
                _, imported = run_router_module_probe([sub, "", ""], self.tmp, ["upgrade_preflight"])
                self.assertFalse(imported["upgrade_preflight"])

    def test_card_bytes_decode_as_utf8_under_a_cp1252_stdout(self):
        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML + 'plugin_version: "0.0.1"\n', encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "upgrade", "", ""],
            capture_output=True, cwd=str(self.tmp), env=env, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0)
        text = proc.stdout.decode("utf-8")
        self.assertIn(UPGRADE_BEGIN, text)
        self.assertIn(UPGRADE_END, text)
        card = text[text.index(UPGRADE_BEGIN):]
        self.assertTrue("—" in card or "…" in card)


class TestPlanConfigGate(_Fixture):
    """`plan` prints the handler's Config Gate between markers, or one fallback line, and exits 0."""

    PLAN_CONFIG_YAML = (
        "project:\n"
        '  name: "PreflightFixtureProject"\n'
        '  planwise_root: "planwise"\n'
        '  plans_dir: "Plans"\n'
        '  lessons_dir: "LessonsLearned"\n'
        "  index_files:\n"
        '    plans: "00-Index-Plans.md"\n'
        '    lessons: "00-Index-LessonsLearned.md"\n'
        f"plugin_root: '{(REPO_DIR / 'plugins' / 'planwise').as_posix()}'\n"
    )

    def setUp(self):
        super().setUp()
        (self.planwise_dir / "config.yaml").write_text(self.PLAN_CONFIG_YAML, encoding="utf-8")

    @staticmethod
    def block_lines(stdout):
        return [ln for ln in stdout.splitlines() if ln]

    @staticmethod
    def field_values(lines):
        return dict(ln.split(": ", 1) for ln in lines[1:-1])

    def test_block_carries_the_config_path_and_the_five_fields(self):
        proc = run_router(["plan", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        lines = self.block_lines(proc.stdout)
        self.assertEqual(lines[0], PLAN_BEGIN)
        self.assertEqual(lines[-1], PLAN_END)
        self.assertNotIn(PLAN_FALLBACK, proc.stdout)
        keys = [ln.split(": ", 1)[0] for ln in lines[1:-1]]
        for key in ("config", *PLAN_FIELD_KEYS):
            with self.subTest(key=key):
                self.assertEqual(keys.count(key), 1)
        values = self.field_values(lines)
        self.assertEqual(Path(values["config"]).resolve(), (self.planwise_dir / "config.yaml").resolve())
        self.assertEqual(Path(values["plugin_root"]).resolve(), (REPO_DIR / "plugins" / "planwise").resolve())
        self.assertEqual(values["project.planwise_root"], "planwise")
        self.assertEqual(values["project.plans_dir"], "Plans")
        self.assertEqual(values["project.lessons_dir"], "LessonsLearned")
        self.assertEqual(values["project.index_files.lessons"], "00-Index-LessonsLearned.md")
        self.assertEqual(values["plans_path"], "planwise/Plans")
        self.assertEqual(values["lessons_path"], "planwise/LessonsLearned")
        self.assertLess(len(proc.stdout), 30000)

    def test_no_config_prints_one_fallback_line_then_the_end_marker(self):
        bare = Path(tempfile.mkdtemp(prefix="skill_preflight_bare_")).resolve()
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        proc = run_router(["plan", "", ""], bare)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(
            self.block_lines(proc.stdout),
            [PLAN_BEGIN, f"{PLAN_FALLBACK} FileNotFoundError: config.yaml not found", PLAN_END],
        )

    def test_malformed_config_prints_a_parse_error_fallback(self):
        cases = {
            "with the project marker": "project:\n  name: [unclosed\n",
            "without the project marker": "plugin_version: [unclosed\n  : : {\n",
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                (self.planwise_dir / "config.yaml").write_text(text, encoding="utf-8")
                proc = run_router(["plan", "", ""], self.tmp)
                self.assertEqual(proc.returncode, 0)
                self.assertNotIn("Traceback", proc.stderr)
                lines = self.block_lines(proc.stdout)
                self.assertEqual(len(lines), 3)
                self.assertEqual((lines[0], lines[2]), (PLAN_BEGIN, PLAN_END))
                self.assertTrue(lines[1].startswith(PLAN_FALLBACK))
                self.assertIn("config.yaml parse error at ", lines[1])

    def test_config_warning_never_reaches_the_block(self):
        # `plan_statuses: [1]` makes config_loader.load_config warn on stderr.
        (self.planwise_dir / "config.yaml").write_text(
            self.PLAN_CONFIG_YAML + "plan_statuses: [1]\n", encoding="utf-8")
        proc = run_router(["plan", "", ""], self.tmp)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        self.assertNotIn("Warning", proc.stdout)
        self.assertEqual(self.block_lines(proc.stdout)[-1], PLAN_END)

    def test_plan_imports_neither_list_plans_nor_upgrade_preflight(self):
        stdout, imported = run_router_module_probe(
            ["plan", "", ""], self.tmp, ["list_plans", "upgrade_preflight"])
        self.assertIn(PLAN_BEGIN, stdout)
        self.assertEqual(imported, {"list_plans": False, "upgrade_preflight": False})

    def test_stray_flags_render_the_same_block(self):
        plain = run_router(["plan", "", ""], self.tmp)
        flagged = run_router(["plan", "--active", ""], self.tmp)
        self.assertEqual(flagged.returncode, 0)
        self.assertIn(PLAN_BEGIN, flagged.stdout)
        self.assertEqual(flagged.stdout, plain.stdout)

    def test_block_bytes_decode_as_utf8_under_a_cp1252_stdout(self):
        (self.planwise_dir / "config.yaml").write_text(
            self.PLAN_CONFIG_YAML.replace("LessonsLearned", "Lessons—Learned"), encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "plan", "", ""],
            capture_output=True, cwd=str(self.tmp), env=env, timeout=60, check=False)
        self.assertEqual(proc.returncode, 0)
        text = proc.stdout.decode("utf-8")
        self.assertIn("project.lessons_dir: Lessons—Learned", text)
        self.assertIn(PLAN_END, text)


class TestPlanGateResolutionAndRawFields(_Fixture):
    """The block follows the handler's resolution order and prints the raw config values."""

    PLAN_CONFIG_YAML = TestPlanConfigGate.PLAN_CONFIG_YAML
    block_lines = staticmethod(TestPlanConfigGate.block_lines)
    field_values = staticmethod(TestPlanConfigGate.field_values)

    def setUp(self):
        super().setUp()
        (self.planwise_dir / "config.yaml").write_text(self.PLAN_CONFIG_YAML, encoding="utf-8")

    def render(self):
        proc = run_router(["plan", "", ""], self.tmp)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        lines = self.block_lines(proc.stdout)
        self.assertEqual((lines[0], lines[-1]), (PLAN_BEGIN, PLAN_END))
        return lines

    def test_unmarked_planwise_config_wins_over_a_marked_sibling(self):
        # A flow-style `project:` block carries no line-start marker, and the handler checks this file first.
        (self.planwise_dir / "config.yaml").write_text("project: {plans_dir: Plans}\n", encoding="utf-8")
        docs = self.tmp / "docs"
        docs.mkdir()
        (docs / "config.yaml").write_text(self.PLAN_CONFIG_YAML, encoding="utf-8")
        values = self.field_values(self.render())
        self.assertEqual(Path(values["config"]).resolve(), (self.planwise_dir / "config.yaml").resolve())

    def test_marked_sibling_is_found_one_level_down(self):
        (self.planwise_dir / "config.yaml").unlink()
        docs = self.tmp / "docs"
        docs.mkdir()
        (docs / "config.yaml").write_text(self.PLAN_CONFIG_YAML, encoding="utf-8")
        values = self.field_values(self.render())
        self.assertEqual(Path(values["config"]).resolve(), (docs / "config.yaml").resolve())

    def test_root_level_config_is_not_a_candidate(self):
        (self.planwise_dir / "config.yaml").unlink()
        (self.tmp / "config.yaml").write_text(self.PLAN_CONFIG_YAML, encoding="utf-8")
        self.assertEqual(
            self.render(),
            [PLAN_BEGIN, f"{PLAN_FALLBACK} FileNotFoundError: config.yaml not found", PLAN_END],
        )

    def test_absent_fields_print_their_default_with_a_suffix(self):
        (self.planwise_dir / "config.yaml").write_text(
            'project:\n  name: "PreflightFixtureProject"\n', encoding="utf-8")
        values = self.field_values(self.render())
        lessons_index = config_loader.INDEX_NAME_DEFAULTS["lessons"]
        expected = {
            "project.planwise_root": "planwise (default)",
            "project.plans_dir": "Plans (default)",
            "project.lessons_dir": "(not set)",
            "project.index_files.lessons": f"{lessons_index} (default)",
            "plans_path": "planwise/Plans",
            "lessons_path": "(not set)",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(values[key], value)
        self.assertTrue(values["plugin_root"].endswith(" (default)"))

    def test_stale_plugin_root_prints_the_configured_value(self):
        stale = (self.tmp / "no-such-plugin").as_posix()
        (self.planwise_dir / "config.yaml").write_text(
            self.PLAN_CONFIG_YAML.replace((REPO_DIR / "plugins" / "planwise").as_posix(), stale),
            encoding="utf-8")
        values = self.field_values(self.render())
        self.assertEqual(values["plugin_root"], f"{stale} (missing on disk)")

    def test_non_utf8_config_prints_a_parse_error_fallback(self):
        (self.planwise_dir / "config.yaml").write_bytes(b"project:\n  name: caf\xe9 \xff\n")
        lines = self.render()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith(PLAN_FALLBACK))
        self.assertIn("config.yaml parse error at ", lines[1])


class TestVersionNoticeRoute(_Fixture):
    """The injected line also carries the version notice, for every subcommand."""

    @staticmethod
    def shipped():
        manifest = REPO_DIR / "plugins" / "planwise" / ".claude-plugin" / "plugin.json"
        return json.loads(manifest.read_text(encoding="utf-8"))["version"]

    def pin(self, version):
        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML + f'plugin_version: "{version}"\n', encoding="utf-8")

    def test_non_list_prints_the_behind_notice(self):
        self.pin("0.0.1")
        for args in (["run", "", ""], ["", "", ""], ["help", "--active", ""]):
            with self.subTest(args=args):
                proc = run_router(args, self.tmp)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(
                    proc.stdout,
                    f"planwise: dispatching from {self.shipped()}, config pins 0.0.1"
                    " — run /planwise upgrade to refresh\n",
                )

    def test_config_warning_never_reaches_the_injected_line(self):
        # `plan_statuses: [1]` makes config_loader.load_config warn on stderr.
        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML + 'plan_statuses: [1]\nplugin_version: "0.0.1"\n', encoding="utf-8")
        notice = (
            f"planwise: dispatching from {self.shipped()}, config pins 0.0.1"
            " — run /planwise upgrade to refresh\n"
        )
        for args in (["run", "", ""], ["", "", ""]):
            with self.subTest(args=args):
                proc = run_router(args, self.tmp)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stderr, "")
                self.assertEqual(proc.stdout, notice)

    def test_config_warning_with_equal_pin_prints_nothing_at_all(self):
        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML + f'plan_statuses: [1]\nplugin_version: "{self.shipped()}"\n',
            encoding="utf-8")
        proc = run_router(["run", "", ""], self.tmp)
        self.assertEqual((proc.stdout, proc.stderr), ("", ""))

    def test_equal_versions_print_nothing_for_non_list(self):
        self.pin(self.shipped())
        proc = run_router(["run", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")

    def test_list_keeps_its_markers_after_the_notice(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        self.pin("0.0.1")
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.returncode, 0)
        lines = proc.stdout.split("\n")
        self.assertTrue(lines[0].startswith("planwise: dispatching from "))
        self.assertEqual(lines[1], BEGIN)
        self.assertEqual(proc.stdout.count(BEGIN), 1)
        self.assertEqual(proc.stdout.count(END), 1)
        self.assertIn("| AAA | Alpha | COMPLETE |", proc.stdout)
        self.assertNotIn(FALLBACK, proc.stdout)

    def test_list_with_equal_versions_still_starts_with_begin(self):
        self.build_plans([("AAA", "Alpha", "COMPLETE")])
        self.pin(self.shipped())
        proc = run_router(["list", "", ""], self.tmp)
        self.assertEqual(proc.stdout.split("\n")[0], BEGIN)

    def test_broken_config_prints_no_traceback(self):
        (self.planwise_dir / "config.yaml").write_text(
            "plugin_version: [unclosed\n  : : {\n", encoding="utf-8")
        for args in (["run", "", ""], ["", "", ""]):
            with self.subTest(args=args):
                proc = run_router(args, self.tmp)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertNotIn("Traceback", proc.stderr)

    def test_import_failure_of_the_notice_prints_nothing_extra(self):
        self.pin("0.0.1")
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
            "sys.modules['version_notice'] = None\n"
            "import skill_preflight\n"
            "sys.exit(skill_preflight.main(['run']))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-B", "-c", code], capture_output=True, text=True,
            encoding="utf-8", cwd=str(self.tmp), timeout=60, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertNotIn("Traceback", proc.stderr)


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
