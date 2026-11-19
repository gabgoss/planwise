"""Tests for the layer-comparison lint checks in ``lint_gate_checks_layers``.

Check 54 gets one known-bad fixture that must produce a finding naming it (the
mutation control) and the same fixture repaired, which must produce none for it (the
positive control). The fixtures are built in temporary directories.
"""

import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_layers as layers_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan

HEADER = "| Priority | File | KiB | ~Tokens | Purpose |\n|---|---|---:|---:|---|\n"


def _task(rows=(), steps="1. Read `docs/x.md`.\n", output="`out/result.md`"):
    table = HEADER + "".join(f"{row}\n" for row in rows) if rows else ""
    return (
        "# Task: Fixture\n\n"
        f"**Output:** {output}\n\n"
        "## Objective\n\nDo the work.\n\n"
        f"## Required Context\n\n{table}\n"
        f"## Execution Steps\n\n{steps}\n"
    )


def _row(cell, purpose="purpose"):
    return f"| 1 | {cell} | 1.0 | ~0.3K | {purpose} |"


def _lint(text, name="TASK-01-Fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
        with redirect_stderr(StringIO()):
            return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == 54]


class TestCheck54StepReadsWithoutRow(unittest.TestCase):
    def test_bad_read_with_no_required_context_row(self):
        findings = _lint(_task([_row("`other/y.md` — whole")]))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(54, "WARNING")])
        self.assertIn("docs/x.md", findings[0]["message"])

    def test_bad_read_with_no_required_context_table(self):
        self.assertEqual(len(_lint(_task())), 1)

    def test_good_task_with_no_required_context_heading_is_skipped(self):
        text = _task().replace("## Required Context", "## Background", 1)
        self.assertEqual(_lint(text), [])

    def test_good_row_present(self):
        self.assertEqual(_lint(_task([_row("`docs/x.md` — whole")])), [])

    def test_good_row_names_a_longer_path_that_ends_with_the_read(self):
        self.assertEqual(_lint(_task([_row("`repo/docs/x.md` — whole")])), [])

    def test_bad_row_names_only_a_substring_of_the_file_name(self):
        self.assertEqual(len(_lint(_task([_row("`docs/xx.md` — whole")]))), 1)

    def test_good_row_with_a_heading_qualifier(self):
        self.assertEqual(_lint(_task([_row("`docs/x.md#Summary` — one section")])), [])

    def test_good_command_row_whose_scope_names_the_path(self):
        row = _row("Grep `pattern='Check'` `path='docs/x.md'`", "command corpus")
        self.assertEqual(_lint(_task([row])), [])

    def test_good_row_names_a_folder_that_holds_the_read(self):
        self.assertEqual(_lint(_task([_row("`docs/` — every file")])), [])

    def test_good_output_path_is_exempt(self):
        text = _task(steps="1. Write `out/result.md`.\n")
        self.assertEqual(_lint(text), [])

    def test_good_placeholder_path_is_exempt(self):
        self.assertEqual(_lint(_task(steps="1. Read `{plan_path}/docs/x.md`.\n")), [])

    def test_good_glob_path_is_exempt(self):
        self.assertEqual(_lint(_task(steps="1. Read `docs/*.md`.\n")), [])

    def test_good_bare_folder_span_is_ignored(self):
        self.assertEqual(_lint(_task(steps="1. Move the file to `Archive/` when done.\n")), [])

    def test_good_non_path_span_is_ignored(self):
        self.assertEqual(_lint(_task(steps="1. Run `git status` and note e.g. `v1.2`.\n")), [])

    def test_bad_path_argument_of_a_tool_call(self):
        steps = "1. Run `Grep pattern='abc' path='docs/z.md'`.\n"
        findings = _lint(_task(steps=steps))
        self.assertEqual(len(findings), 1)
        self.assertIn("docs/z.md", findings[0]["message"])

    def test_good_wrong_line_is_skipped(self):
        self.assertEqual(_lint(_task(steps="1. WRONG: read `docs/x.md` by hand.\n")), [])

    def test_good_base_marker_line_is_skipped(self):
        steps = "1. Read `docs/x.md` for `ES_S01_BASE`.\n"
        self.assertEqual(_lint(_task(steps=steps)), [])

    def test_fenced_read_is_not_seen(self):
        steps = "1. Run:\n```\nRead `docs/x.md`\n```\n"
        self.assertEqual(_lint(_task(steps=steps)), [])

    def test_one_finding_per_path(self):
        steps = "1. Read `docs/x.md`.\n2. Read `docs/x.md` again.\n"
        self.assertEqual(len(_lint(_task(steps=steps))), 1)

    def test_two_paths_give_two_findings(self):
        steps = "1. Read `docs/x.md` and `docs/y.md`.\n"
        self.assertEqual(len(_lint(_task(steps=steps))), 2)

    def test_a_file_that_is_not_a_task_is_not_read(self):
        text = _task().replace("# Task: Fixture", "# Notes: Fixture", 1)
        self.assertEqual(_lint(text), [])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in layers_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in layers_module.CHECKS]
        self.assertEqual(names, ["check54"])

    def test_severity_constant_matches_the_linter(self):
        self.assertEqual(layers_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(layers_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_layers.py").read_text(encoding="utf-8")
        self.assertNotIn("import lint_verification_gates", source)
        self.assertNotIn("from lint_verification_gates", source)


if __name__ == "__main__":
    unittest.main()
