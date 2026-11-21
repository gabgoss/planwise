"""Tests for the layer-comparison lint checks in ``lint_gate_checks_layers``.

Check 54 gets one known-bad fixture that must produce a finding naming it (the
mutation control) and the same fixture repaired, which must produce none for it (the
positive control). The fixtures are built in temporary directories.

Checks 57 and 58 read three layers of a rendered plan, so their fixture is a two-sprint
plan that ``scaffold_plan.render_all`` renders, the real producer of all three layers.
Each case copies that tree, changes one cell, and lints the copy.
"""

import shutil
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
import scaffold_plan
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


PARSE_REL = "Sprint-01-LedgerCore/Session-01-ReadPath/Outputs/QZX-parse.md"
SPRINT_ONE = "Sprint-01-LedgerCore"
SPRINT_TWO = "Sprint-02-LedgerExtras"
SPRINT_ONE_PLAN = f"{SPRINT_ONE}/QZX-S01-Sprint-Plan.md"
SPRINT_TWO_PLAN = f"{SPRINT_TWO}/QZX-S02-Sprint-Plan.md"
ORCHESTRATION_ONE = f"{SPRINT_ONE}/Session-01-ReadPath/QZX-S01-01-Orchestration.md"
TASK_ONE_TWO = f"{SPRINT_ONE}/Session-01-ReadPath/QZX-S01-01-02-Opus-IndexRows.md"
TASK_TWO_ONE = f"{SPRINT_TWO}/Session-01-Extras/QZX-S02-01-01-Sonnet-UseParse.md"
# The cells below are the producer's own rendering of task 2's dependency on task 1.
INDEX_ROW = "| 2 | IndexRows: Step 2 of the ledger | Opus | ~22K | 01 |"
USE_ROW_CELL = "| ~21K | cross-sprint: QZX-S01-01-01 |"
REFS_LINE = f"**Cross-Sprint Refs:** ['{PARSE_REL}']\n"


def _fixture_task(number, name, agent, deps, outputs, rc_path="src/orchard/ledger.py", **extra):
    task = {
        "number": number, "name": name, "title": f"Step {number} of the ledger", "agent": agent,
        "estimate_k": 20 + number, "depends_on": deps, "outputs": outputs,
        "required_context": [{"priority": 1, "path": rc_path, "kib": 4.0, "tokens_k": 1.5, "purpose": "the module"}],
    }
    task.update(extra)
    return task


def _plan_spec():
    """Invented sample vocabulary: two sprints, one session each. Sprint two's one task reads a
    file that sprint one's first task produces, so it carries a ``cross-sprint:`` dependency
    and a ``Cross-Sprint Refs`` field."""
    return {
        "plan_name": "OrchardLedger", "abbrev": "QZX", "created": "2030-01-15", "ordering": "Sprint one then two",
        "sprints": [
            {"number": 1, "name": "LedgerCore", "purpose": "Build the core", "sessions": [
                {"number": 1, "name": "ReadPath", "objective": "Read the ledger", "mode": "DELEGATED",
                 "prerequisite": "None (first session)",
                 "tasks": [_fixture_task(1, "ParseRows", "Sonnet", [], ["src/orchard/parse.py", "Outputs/QZX-parse.md"]),
                           _fixture_task(2, "IndexRows", "Opus", [1], ["src/orchard/index.py"])]}]},
            {"number": 2, "name": "LedgerExtras", "purpose": "Extend the core", "sessions": [
                {"number": 1, "name": "Extras", "objective": "Use the parser", "mode": "DELEGATED",
                 "prerequisite": "Sprint one",
                 "tasks": [_fixture_task(1, "UseParse", "Sonnet", ["cross-sprint: QZX-S01-01-01"], ["src/orchard/use.py"],
                                         rc_path=PARSE_REL, cross_sprint_refs=[PARSE_REL])]}]},
        ],
    }


class _RenderedPlan(unittest.TestCase):
    """Base for the cases that lint a copy of the rendered two-sprint plan with one cell changed."""

    @classmethod
    def setUpClass(cls):
        spec = _plan_spec()
        assert scaffold_plan.lint_spec(spec, scaffold_plan.DEFAULT_TEMPLATES) == []
        cls._tmp = tempfile.TemporaryDirectory()
        cls.template = Path(cls._tmp.name) / "plan"
        files, _rec = scaffold_plan.render_all(spec, scaffold_plan.DEFAULT_TEMPLATES)
        scaffold_plan.write_tree(files, cls.template)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def lint(self, check, *edits):
        """Findings of ``check`` on a copy of the plan after each ``(file, old, new)`` edit.
        Each ``old`` must occur exactly once, so an edit that missed its cell fails loudly."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plan"
            shutil.copytree(self.template, root)
            for rel, old, new in edits:
                path = root / rel
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count(old), 1, f"{rel} holds {old!r} {text.count(old)} times")
                path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
            with redirect_stderr(StringIO()):
                return [f for f in lint_plan(root, execute=False) if f["check"] == check]


class TestCheck57DependsOnLayersDisagree(_RenderedPlan):
    def test_good_all_layers_agree(self):
        self.assertEqual(self.lint(57), [])

    def test_bad_one_sprint_plan_cell_differs(self):
        findings = self.lint(57, (SPRINT_ONE_PLAN, INDEX_ROW, INDEX_ROW.replace("| 01 |", "| - |")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(57, "ERROR")])
        self.assertEqual(findings[0]["file"], TASK_ONE_TWO)
        self.assertIn("QZX-S01-01-02", findings[0]["message"])
        self.assertIn("the Sprint Plan Session Details: -", findings[0]["message"])

    def test_bad_one_orchestration_cell_differs(self):
        findings = self.lint(57, (ORCHESTRATION_ONE, INDEX_ROW, INDEX_ROW.replace("| 01 |", "| 03 |")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(57, "ERROR")])
        self.assertIn("the Orchestration Session Task List: 3", findings[0]["message"])

    def test_bad_the_task_header_differs(self):
        findings = self.lint(57, (TASK_ONE_TWO, "**Depends On:** 01\n", "**Depends On:** -\n"))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(57, "ERROR")])
        self.assertIn("the task header: -", findings[0]["message"])

    def test_bad_a_cross_sprint_entry_dropped_from_the_sprint_plan(self):
        findings = self.lint(57, (SPRINT_TWO_PLAN, USE_ROW_CELL, "| ~21K | - |"))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(57, "ERROR")])
        self.assertEqual(findings[0]["file"], TASK_TWO_ONE)

    def test_bad_the_prefix_differs(self):
        edit = (SPRINT_TWO_PLAN, USE_ROW_CELL, "| ~21K | cross-session: QZX-S01-01-01 |")
        self.assertEqual(len(self.lint(57, edit)), 1)

    def test_good_leading_zero_equals_bare_number(self):
        self.assertEqual(self.lint(57, (SPRINT_ONE_PLAN, INDEX_ROW, INDEX_ROW.replace("| 01 |", "| 1 |"))), [])

    def test_good_a_missing_layer_is_skipped(self):
        renamed = (SPRINT_ONE_PLAN, "## Session Details", "## Session Notes")
        self.assertEqual(self.lint(57, renamed), [])

    def test_bad_the_remaining_layers_still_compare_when_one_is_missing(self):
        renamed = (SPRINT_ONE_PLAN, "## Session Details", "## Session Notes")
        orchestration = (ORCHESTRATION_ONE, INDEX_ROW, INDEX_ROW.replace("| 01 |", "| - |"))
        self.assertEqual(len(self.lint(57, renamed, orchestration)), 1)


class TestCheck58CrossSprintReadWithoutRefsField(_RenderedPlan):
    def test_good_field_present(self):
        self.assertEqual(self.lint(58), [])

    def test_bad_field_missing(self):
        findings = self.lint(58, (TASK_TWO_ONE, REFS_LINE, ""))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(58, "WARNING")])
        self.assertEqual(findings[0]["file"], TASK_TWO_ONE)
        self.assertIn(PARSE_REL, findings[0]["message"])

    def test_good_a_row_under_the_tasks_own_sprint_needs_no_field(self):
        own = f"{SPRINT_TWO}/Session-01-Extras/Outputs/QZX-use.md"
        edits = ((TASK_TWO_ONE, REFS_LINE, ""), (TASK_TWO_ONE, f"| 1 | `{PARSE_REL}` |", f"| 1 | `{own}` |"))
        self.assertEqual(self.lint(58, *edits), [])


TASK_ONE_ONE = f"{SPRINT_ONE}/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md"
# The producer's own rendering of task 2's Output line and its Write-Set row in sprint one.
INDEX_OUTPUT = "**Output:** `src/orchard/index.py`\n"
INDEX_WRITE_ROW = "| `src/orchard/index.py` | QZX-S01-01-02 |"
EXPECTED_PLACEHOLDER = "<!-- FILL: {What the subagent should produce - be specific about format and content} -->"
WRITE_SET_PROSE = "This declaration feeds the Master Plan's"
ALIAS_LEGEND = "`S` = `src/orchard/`\n\n"


def _hook_row(path, task="QZX-S01-01-02"):
    return f"{INDEX_WRITE_ROW}\n| `{path}` | {task} |"


class TestCheck59WriteSetOutputExpectedOutputAgree(_RenderedPlan):
    def only(self, *edits):
        return self.lint(59, *edits)

    def test_good_the_rendered_plan_agrees(self):
        self.assertEqual(self.only(), [])

    def test_bad_a_write_set_path_missing_from_the_output_line(self):
        # The GWP shape: the Write-Set gives a hook file to the task, and its Output line names only the report.
        edits = ((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, _hook_row(".claude/hooks/create.py")),)
        findings = self.only(*edits)
        self.assertEqual([(f["check"], f["severity"], f["file"]) for f in findings], [(59, "ERROR", TASK_ONE_TWO)])
        self.assertIn("'.claude/hooks/create.py'", findings[0]["message"])
        self.assertIn("QZX-S01-01-02", findings[0]["message"])
        self.assertEqual(findings[0]["line"], 7)

    def test_bad_the_output_line_names_only_the_report(self):
        edits = ((TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `Outputs/QZX-index.md`\n"),)
        findings = self.only(*edits)
        self.assertEqual([(f["severity"], f["file"]) for f in findings], [("ERROR", TASK_ONE_TWO)])
        self.assertIn("'src/orchard/index.py'", findings[0]["message"])

    def test_bad_two_tasks_write_one_file_and_neither_output_line_names_it(self):
        rows = f"{INDEX_WRITE_ROW}\n| `.claude/settings.json` | QZX-S01-01-01 |\n| `.claude/settings.json` | QZX-S01-01-02 |"
        findings = self.only((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, rows))
        self.assertEqual(sorted(f["file"] for f in findings), sorted([TASK_ONE_ONE, TASK_ONE_TWO]))
        self.assertEqual({f["severity"] for f in findings}, {"ERROR"})

    def test_good_a_row_for_another_task_is_not_read_as_this_tasks(self):
        edits = ((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, _hook_row("src/orchard/other.py", "QZX-S01-01-01")),)
        findings = self.only(*edits)
        self.assertEqual([f["file"] for f in findings], [TASK_ONE_ONE])

    def test_good_the_output_line_names_the_path_with_a_longer_prefix(self):
        long_output = "**Output:** `repo/src/orchard/index.py`\n"
        self.assertEqual(self.only((TASK_ONE_TWO, INDEX_OUTPUT, long_output)), [])

    def test_good_a_write_set_folder_holds_the_output_file(self):
        edits = ((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, "| `src/orchard/` | QZX-S01-01-02 |"),)
        self.assertEqual(self.only(*edits), [])

    def test_good_an_output_folder_holds_the_write_set_file(self):
        self.assertEqual(self.only((TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `src/orchard/`\n")), [])

    def test_good_a_write_set_glob_is_not_compared(self):
        edits = ((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, _hook_row("src/orchard/*.py")),)
        self.assertEqual(self.only(*edits), [])

    def test_good_an_alias_the_legend_expands_is_covered(self):
        edits = (
            (SPRINT_ONE_PLAN, WRITE_SET_PROSE, f"{ALIAS_LEGEND}{WRITE_SET_PROSE}"),
            (SPRINT_ONE_PLAN, INDEX_WRITE_ROW, "| `S/index.py` | QZX-S01-01-02 |"),
        )
        self.assertEqual(self.only(*edits), [])

    def test_bad_an_alias_the_legend_expands_names_the_full_path(self):
        edits = (
            (SPRINT_ONE_PLAN, WRITE_SET_PROSE, f"{ALIAS_LEGEND}{WRITE_SET_PROSE}"),
            (SPRINT_ONE_PLAN, INDEX_WRITE_ROW, "| `S/index.py` | QZX-S01-01-02 |"),
            (TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `Outputs/QZX-index.md`\n"),
        )
        findings = self.only(*edits)
        self.assertEqual(len(findings), 1)
        self.assertIn("'src/orchard/index.py'", findings[0]["message"])

    def test_good_a_task_with_no_output_line_is_skipped(self):
        edits = ((SPRINT_ONE_PLAN, INDEX_WRITE_ROW, _hook_row(".claude/hooks/create.py")),
                 (TASK_ONE_TWO, INDEX_OUTPUT, ""))
        self.assertEqual(self.only(*edits), [])

    def test_good_a_sprint_plan_with_no_write_set_is_skipped(self):
        edits = ((SPRINT_ONE_PLAN, "## Write-Set <!-- REQUIRED -->", "## Edited Files <!-- REQUIRED -->"),
                 (TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `src/orchard/index.py`, and `src/orchard/extra.py`\n"))
        self.assertEqual(self.only(*edits), [])

    def test_bad_an_output_path_no_write_set_row_covers(self):
        edit = (TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `src/orchard/index.py`, and `src/orchard/extra.py`\n")
        findings = self.only(edit)
        self.assertEqual([(f["severity"], f["file"]) for f in findings], [("WARNING", TASK_ONE_TWO)])
        self.assertIn("'src/orchard/extra.py'", findings[0]["message"])

    def test_good_the_same_output_path_with_a_write_set_row(self):
        edits = ((TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `src/orchard/index.py`, and `src/orchard/extra.py`\n"),
                 (SPRINT_ONE_PLAN, INDEX_WRITE_ROW, _hook_row("src/orchard/extra.py")))
        self.assertEqual(self.only(*edits), [])

    def test_good_an_output_path_inside_an_outputs_folder_needs_no_row(self):
        edit = (TASK_ONE_TWO, INDEX_OUTPUT, "**Output:** `src/orchard/index.py`, and `Outputs/QZX-index.md`\n")
        self.assertEqual(self.only(edit), [])

    def test_bad_an_expected_output_path_neither_output_nor_required_context_names(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "Write `docs/notes.md` and `src/orchard/index.py`.")
        findings = self.only(edit)
        self.assertEqual([(f["severity"], f["file"]) for f in findings], [("WARNING", TASK_ONE_TWO)])
        self.assertIn("'docs/notes.md'", findings[0]["message"])

    def test_good_an_expected_output_path_a_required_context_row_names(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "Match the shape of `src/orchard/ledger.py`.")
        self.assertEqual(self.only(edit), [])

    def test_good_an_expected_output_path_inside_a_fence_is_not_read(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "```text\nWrite `docs/notes.md`.\n```")
        self.assertEqual(self.only(edit), [])

    def test_good_an_expected_output_line_that_negates_is_skipped(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "Never write `docs/notes.md`.")
        self.assertEqual(self.only(edit), [])

    def test_good_an_expected_output_path_inside_a_multi_line_comment_is_not_read(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "<!-- guidance that names\n`docs/notes.md`\nacross lines -->")
        self.assertEqual(self.only(edit), [])

    def test_bad_an_expected_output_path_after_a_closed_comment_on_the_same_line_is_read(self):
        edit = (TASK_ONE_TWO, EXPECTED_PLACEHOLDER, "<!-- note --> Write `docs/notes.md`.")
        self.assertEqual([f["file"] for f in self.only(edit)], [TASK_ONE_TWO])

    def test_good_a_path_under_an_expected_output_sub_heading_is_not_read(self):
        sub_heading = "### References Moved That May Now Be False (Required when the task moves or splits text)\n"
        edit = (TASK_ONE_TWO, sub_heading, f"{sub_heading}\nWrite `docs/notes.md`.\n")
        self.assertEqual(self.only(edit), [])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in layers_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in layers_module.CHECKS]
        self.assertEqual(names, ["check54", "check57", "check58", "check59"])

    def test_severity_constants_match_the_linter(self):
        self.assertEqual(layers_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)
        self.assertEqual(layers_module.SEVERITY_ERROR, lint_module.SEVERITY_ERROR)

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(layers_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_layers.py").read_text(encoding="utf-8")
        self.assertNotIn("import lint_verification_gates", source)
        self.assertNotIn("from lint_verification_gates", source)


if __name__ == "__main__":
    unittest.main()
