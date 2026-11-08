"""Tests for the dispatch-rule lint checks in ``lint_gate_checks_dispatch``.

Each check gets one known-bad fixture that must produce a finding naming it, and
the same fixture repaired, which must produce none for it. The fixtures are built
in temporary directories.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_dispatch as dispatch_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan


def _task(objective="Do the work.", steps="1. Read the file.", output="`out/result.md`",
          context_rows=(), extra=""):
    rows = "".join(f"{row}\n" for row in context_rows)
    table = (
        "| Priority | File | KiB | Purpose |\n|---|---|---:|---|\n" + rows if context_rows else ""
    )
    return (
        "# Task: Fixture\n\n"
        f"**Output:** {output}\n\n"
        f"## Objective\n\n{objective}\n\n"
        f"## Required Context\n\n{table}\n"
        f"## Execution Steps\n\n{steps}\n\n"
        f"{extra}"
    )


def _lint(check, text, name="TASK-01-Fixture.md", newline="\n"):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8", newline=newline)
        return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


class TestCheck42PremisePhrase(unittest.TestCase):
    def test_bad_premise_in_objective(self):
        findings = _lint(42, _task(objective="You will probably find the cause is the cache."))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(42, "WARNING")])

    def test_bad_premise_in_step(self):
        findings = _lint(42, _task(steps="1. Be willing to conclude the count is wrong."))
        self.assertEqual(len(findings), 1)

    def test_good_repaired_as_context(self):
        self.assertEqual(_lint(42, _task(objective="The cache holds 12 files, measured today.")), [])

    def test_good_phrase_in_code_span(self):
        self.assertEqual(_lint(42, _task(steps="1. Flag any sentence with `probably find`.")), [])

    def test_good_phrase_outside_brief_sections(self):
        self.assertEqual(_lint(42, _task(extra="## Notes for Agent\n\nYou will probably find it.\n")), [])

    def test_bad_premise_in_orchestration_spawn_prompt(self):
        text = "# Orchestration\n\n```\nBe willing to conclude the cache is stale.\n```\n"
        findings = _lint(42, text, name="XX-S01-01-Orchestration.md")
        self.assertEqual(len(findings), 1)


class TestCheck43WriteOutsideOutput(unittest.TestCase):
    BAD = "1. Stamp the duplicate in `register/Part-1b.md` as absorbed."

    def test_bad_stamp_to_path_not_in_output(self):
        findings = _lint(43, _task(steps=self.BAD))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(43, "WARNING")])

    def test_good_path_added_to_output(self):
        self.assertEqual(_lint(43, _task(steps=self.BAD, output="`out/result.md`, `register/Part-1b.md`")), [])

    def test_bad_name_is_only_a_substring_of_a_declared_path(self):
        steps = "1. Amend `Core.md` with the result."
        findings = _lint(43, _task(steps=steps, output="`Outputs/RFH-S04-01-02-EiLintCore.md`"))
        self.assertEqual(len(findings), 1)

    def test_good_declared_path_among_several(self):
        steps = "1. Amend `Core.md` with the result."
        self.assertEqual(_lint(43, _task(steps=steps, output="`a/Other.md`, `b/Core.md`")), [])

    def test_good_declared_path_followed_by_punctuation(self):
        steps = "1. Amend `b/Core.md`."
        self.assertEqual(_lint(43, _task(steps=steps, output="`b/Core.md`; `a/Other.md`")), [])

    def test_good_step_without_write_verb(self):
        self.assertEqual(_lint(43, _task(steps="1. Read `register/Part-1b.md`.")), [])

    def test_good_negated_step(self):
        self.assertEqual(_lint(43, _task(steps="1. Do not amend `register/Part-1b.md`.")), [])

    def test_good_no_output_field(self):
        text = _task(steps=self.BAD).replace("**Output:** `out/result.md`\n\n", "")
        self.assertEqual(_lint(43, text), [])


class TestCheck44FigureWithoutDateAndSource(unittest.TestCase):
    BARE = "| 1 | `a/b.py` — 620 lines | 27.3 | the sibling shape |"
    STAMPED = "| 1 | `a/b.py` — 620 lines, measured 2026-11-07 by `measure_files.py` | 27.3 | the sibling shape |"

    def test_bad_figure_with_no_date_or_source(self):
        findings = _lint(44, _task(context_rows=[self.BARE]))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(44, "WARNING")])

    def test_bad_figure_with_date_and_no_source(self):
        row = "| 1 | `a/b.py` — 620 lines, measured 2026-11-07 | 27.3 | the sibling shape |"
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)

    def test_good_figure_with_date_and_source(self):
        self.assertEqual(_lint(44, _task(context_rows=[self.STAMPED])), [])

    def test_good_row_without_a_figure(self):
        row = "| 1 | `a/b.py` | whole | the sibling shape |"
        self.assertEqual(_lint(44, _task(context_rows=[row])), [])

    def test_bad_number_under_a_size_header(self):
        row = "| 1 | `a/b.py` | 27.3 | the sibling shape |"
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)

    PROJECTED = "| 1 | `Outputs/RFH-01-Core.md` — projected ceiling | 15.0 | the reader shape |"

    def test_good_projected_ceiling_row_does_not_fire(self):
        self.assertEqual(_lint(44, _task(context_rows=[self.PROJECTED])), [])

    def test_bad_same_row_without_projected_still_fires(self):
        row = self.PROJECTED.replace(" — projected ceiling", "")
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)

    def test_bad_projected_inside_a_path_does_not_exempt_the_row(self):
        row = "| 1 | `Outputs/projected-sizes.md` — 620 lines | 27.3 | the sibling shape |"
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)

    def test_bad_measured_row_beside_a_projected_row_still_fires(self):
        findings = _lint(44, _task(context_rows=[self.PROJECTED, self.BARE]))
        self.assertEqual(len(findings), 1)


class TestCheck45RemeasureWithoutClauses(unittest.TestCase):
    def test_bad_bare_remeasure(self):
        extra = "<!-- Register rows (projected) -- re-measure at dispatch. -->\n"
        findings = _lint(45, _task(extra=extra))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(45, "WARNING")])

    def test_bad_threshold_without_action(self):
        extra = "Re-measure the pull count at dispatch if it is more than 10% off.\n"
        self.assertEqual(len(_lint(45, _task(extra=extra))), 1)

    def test_good_threshold_and_action(self):
        extra = "Re-measure the pull count at dispatch. If it is more than 10% off, re-roll the budget.\n"
        self.assertEqual(_lint(45, _task(extra=extra)), [])

    def test_good_code_span_mention(self):
        self.assertEqual(_lint(45, _task(extra="The phrase `re-measure at dispatch` is checked.\n")), [])

    def test_good_wrong_labelled_line(self):
        extra = "WRONG: re-measure at dispatch.\n"
        self.assertEqual(_lint(45, _task(extra=extra)), [])


REPORT_OUTPUT = "`Outputs/Report.md`"
EXPECTED_BAD = "## Expected Output\n\nThe report holds 5 sections.\n"
EXPECTED_GOOD = (
    "## Expected Output\n\nThe report holds 5 sections.\n\n"
    "**Required headings:**\n\n- `## Checks`\n- `## Controls Run`\n"
)


class TestCheck46ExpectedOutputWithoutLabels(unittest.TestCase):
    def test_bad_count_claim_without_label_list(self):
        findings = _lint(46, _task(output=REPORT_OUTPUT, extra=EXPECTED_BAD))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(46, "WARNING")])
        self.assertIn("Expected Output", findings[0]["message"])

    def test_good_repaired_with_label_list(self):
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=EXPECTED_GOOD)), [])

    def test_bad_crlf_variant(self):
        findings = _lint(46, _task(output=REPORT_OUTPUT, extra=EXPECTED_BAD), newline="\r\n")
        self.assertEqual(len(findings), 1)

    def test_good_crlf_repaired_variant(self):
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=EXPECTED_GOOD), newline="\r\n"), [])

    def test_good_code_output_without_label_list_does_not_fire(self):
        output = "`scripts/tool.py`, `tests/test_tool.py`"
        self.assertEqual(_lint(46, _task(output=output, extra=EXPECTED_BAD)), [])

    def test_bad_downstream_consumer_without_label_list(self):
        extra = "## Expected Output\n\nThe table is consumed structurally by a downstream task.\n"
        self.assertEqual(len(_lint(46, _task(output=REPORT_OUTPUT, extra=extra))), 1)

    def test_good_no_count_or_consumer(self):
        extra = "## Expected Output\n\nA short report of what changed.\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_bad_field_present_with_no_label(self):
        extra = EXPECTED_BAD + "\n**Required headings:**\n\nNone yet.\n"
        self.assertEqual(len(_lint(46, _task(output=REPORT_OUTPUT, extra=extra))), 1)

    def test_good_labels_on_the_field_line(self):
        extra = EXPECTED_BAD + "\n**Required headings:** `## Checks`, `## Controls Run`\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_good_template_comment_is_not_a_consumer_claim(self):
        extra = (
            "## Expected Output\n\nA short report.\n\n"
            "<!-- Required when this task's output is consumed structurally by a named downstream task -->\n"
        )
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_good_multiline_comment_is_not_a_claim(self):
        extra = "## Expected Output\n\nA short report.\n\n<!-- The report holds 5 sections,\nconsumed by a downstream task. -->\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_bad_claim_after_a_comment_still_fires(self):
        extra = "## Expected Output\n\n<!-- note -->\nThe report holds 5 sections.\n"
        self.assertEqual(len(_lint(46, _task(output=REPORT_OUTPUT, extra=extra))), 1)

    def test_bad_placeholder_labels_are_not_literal(self):
        extra = EXPECTED_BAD + "\n**Required headings:**\n\n- `{## Heading 1}`\n- `{## Heading 2}`\n"
        self.assertEqual(len(_lint(46, _task(output=REPORT_OUTPUT, extra=extra))), 1)

    def test_good_comment_between_field_and_bullets(self):
        extra = EXPECTED_BAD + "\n**Required headings:** <!-- one per line -->\n<!-- keep the order -->\n- `## Checks`\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_good_lead_in_line_between_field_and_bullets(self):
        extra = EXPECTED_BAD + "\n**Required headings:**\n\nThe report carries these:\n\n- `## Checks`\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_good_a_single_file_is_not_a_count_claim(self):
        extra = "## Expected Output\n\nWrite one report file.\n"
        self.assertEqual(_lint(46, _task(output=REPORT_OUTPUT, extra=extra)), [])

    def test_bad_two_files_is_a_count_claim(self):
        extra = "## Expected Output\n\nWrite two report files.\n"
        self.assertEqual(len(_lint(46, _task(output=REPORT_OUTPUT, extra=extra))), 1)


FLAG_HEAD = "| Flag # | Source Task | Consuming Task | Observation | Recommended Action | Routed |\n|---|---|---|---|---|---|\n"
STAMP = "✅ ROUTED 2026-11-08 into RFH-01-Task.md"


def _orchestration(routed, head=FLAG_HEAD):
    return (
        "# Orchestration\n\n## Pre-Known Cross-Task Coordination Flags\n\n"
        f"{head}| 1 | T1 | T2 | saw X | do Y | {routed} |\n\n## Next Section\n"
    )


class TestCheck47FlagRowWithoutStamp(unittest.TestCase):
    NAME = "XX-S01-01-Orchestration.md"

    def test_bad_pending_cell(self):
        findings = _lint(47, _orchestration("pending"), name=self.NAME)
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(47, "WARNING")])

    def test_bad_empty_cell(self):
        self.assertEqual(len(_lint(47, _orchestration(""), name=self.NAME)), 1)

    def test_bad_other_text(self):
        self.assertEqual(len(_lint(47, _orchestration("routed yesterday"), name=self.NAME)), 1)

    def test_good_repaired_with_stamp(self):
        self.assertEqual(_lint(47, _orchestration(STAMP), name=self.NAME), [])

    def test_good_stamp_with_trailing_text(self):
        cell = STAMP + " § Pre-Known Cross-Task Coordination Flags"
        self.assertEqual(_lint(47, _orchestration(cell), name=self.NAME), [])

    def test_bad_crlf_variant(self):
        self.assertEqual(len(_lint(47, _orchestration("pending"), name=self.NAME, newline="\r\n")), 1)

    def test_good_crlf_repaired_variant(self):
        self.assertEqual(_lint(47, _orchestration(STAMP), name=self.NAME, newline="\r\n"), [])

    def test_good_table_without_routed_column_is_absent_not_a_finding(self):
        head = "| Flag # | Source | Observation |\n|---|---|---|\n"
        text = (
            "# Orchestration\n\n## Pre-Known Cross-Task Coordination Flags\n\n"
            f"{head}| 1 | T1 | saw X |\n"
        )
        self.assertEqual(_lint(47, text, name=self.NAME), [])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / self.NAME).write_text(text, encoding="utf-8", newline="\n")
            counts = dispatch_module.subject_counts(_context(Path(tmp)))
        self.assertEqual(counts["flag_tables"], 1)
        self.assertEqual(counts["flag_tables_without_routed_column"], 1)
        self.assertEqual(counts["flag_rows"], 0)

    def test_good_stamp_in_a_code_span(self):
        self.assertEqual(_lint(47, _orchestration(f"`{STAMP}`"), name=self.NAME), [])

    def test_good_stamp_with_variation_selector(self):
        cell = STAMP.replace("✅", "✅️")
        self.assertEqual(_lint(47, _orchestration(cell), name=self.NAME), [])

    def test_adjacent_tables_do_not_merge(self):
        text = (
            "# Orchestration\n\n## Pre-Known Cross-Task Coordination Flags\n\n"
            "### From A\n"
            "| Flag # | Routed |\n|---|---|\n"
            f"| 1 | {STAMP} |\n"
            "### From B\n"
            "| Flag # | Source | Routed |\n|---|---|---|\n"
            f"| 2 | T1 | {STAMP} |\n"
        )
        self.assertEqual(_lint(47, text, name=self.NAME), [])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / self.NAME).write_text(text, encoding="utf-8", newline="\n")
            counts = dispatch_module.subject_counts(_context(Path(tmp)))
        self.assertEqual((counts["flag_tables"], counts["flag_rows"]), (2, 2))

    def test_good_none_row_is_skipped(self):
        text = _orchestration(STAMP).replace("| 1 | T1 |", "| none | T1 |").replace(STAMP, "")
        self.assertEqual(_lint(47, text, name=self.NAME), [])

    def test_good_table_outside_the_flag_section(self):
        text = _orchestration("pending").replace(
            "## Pre-Known Cross-Task Coordination Flags", "## Other Table"
        )
        self.assertEqual(_lint(47, text, name=self.NAME), [])


class TestSubjectCounts(unittest.TestCase):
    def test_counts_distinguish_empty_from_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = dispatch_module.subject_counts(_context(Path(tmp)))
            self.assertEqual(empty["task_files"], 0)
            self.assertEqual(empty["brief_lines"], 0)
            (Path(tmp) / "TASK-01-Fixture.md").write_text(_task(), encoding="utf-8", newline="\n")
            context = _context(Path(tmp))
            counts = dispatch_module.subject_counts(context)
        self.assertEqual(counts["task_files"], 1)
        self.assertGreater(counts["brief_lines"], 0)


def _context(root):
    class _Context:
        plan_root = root

        def markdown_files(self):
            return sorted(p for p in root.rglob("*.md") if p.is_file())

    return _Context()


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in dispatch_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in dispatch_module.CHECKS]
        self.assertEqual(names, [f"check{number}" for number in range(42, 48)])

    def test_severity_constant_matches_the_linter(self):
        self.assertEqual(dispatch_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(dispatch_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_dispatch.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_a_new_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task(objective="You will probably find the cause."), encoding="utf-8", newline="\n"
            )
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("Check 42:", completed.stdout, completed.stderr)
        self.assertIn("[WARNING] Check 42:", completed.stdout)

    def test_cli_reports_checks_46_and_47(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task(output=REPORT_OUTPUT, extra=EXPECTED_BAD), encoding="utf-8", newline="\n"
            )
            (Path(tmp) / "XX-S01-01-Orchestration.md").write_text(
                _orchestration("pending"), encoding="utf-8", newline="\n"
            )
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("[WARNING] Check 46:", completed.stdout, completed.stderr)
        self.assertIn("[WARNING] Check 47:", completed.stdout, completed.stderr)


if __name__ == "__main__":
    unittest.main()
