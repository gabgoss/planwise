"""Tests for the task-file gate-text lint checks in ``lint_gate_checks_verify``.

Each check gets one known-bad fixture that must produce exactly one finding
naming it, and one known-good fixture that must produce none for it. Every bad
fixture is written from the rule the check enforces, not from the check's own
docstring. The fixtures are built in temporary directories, so no existing
fixture under ``tests/fixtures/verification_gates`` changes.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_verify as verify_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan


def _write_task(plan_root, fence_lines, extra="", before_lines=(), newline="\n"):
    """Write one task file whose After block holds ``fence_lines``."""
    before = ""
    if before_lines:
        before = (
            "> **Before:** *(runner)*\n> ```bash\n"
            + "".join(f"> {line}\n" for line in before_lines)
            + "> ```\n"
        )
    body = "".join(f"> {line}\n" for line in fence_lines)
    text = (
        "# Task: Fixture\n\n"
        + extra
        + "## Verification Commands\n\n"
        "> [!verify] Before / After Commands\n"
        + before
        + "> **After:** *(runner)*\n"
        "> ```bash\n" + body + "> ```\n"
    )
    with open(Path(plan_root) / "TASK-01-Fixture.md", "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", newline))


def _lint(check, fence_lines, extra="", before_lines=(), newline="\n"):
    with tempfile.TemporaryDirectory() as tmp:
        _write_task(tmp, fence_lines, extra=extra, before_lines=before_lines, newline=newline)
        return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


def _pairs(findings):
    return [(f["check"], f["severity"]) for f in findings]


QUIET = ["ls notes.md   # expect notes.md"]


class TestCheck30GateAnchorWithoutVerifiedMarker(unittest.TestCase):
    def test_bad_heading_anchor_gate_without_date(self):
        findings = _lint(30, ["grep -c '^## Results' report.md   # expect 1"])
        self.assertEqual(_pairs(findings), [(30, "WARNING")])

    def test_good_heading_anchor_gate_with_verified_date(self):
        self.assertEqual(_lint(30, ["grep -c '^## Results' report.md   # expect 1, verified 2026-10-27"]), [])

    def test_good_heading_anchor_marked_unverified(self):
        self.assertEqual(_lint(30, ["grep -c '^## Results' report.md   # expect 1 (unverified)"]), [])

    def test_bad_native_grep_call_without_date(self):
        extra = "Grep  pattern='^## Results'  path='report.md'  output_mode='count'\n\n"
        findings = _lint(30, QUIET, extra=extra)
        self.assertEqual([(f["check"], f["line"]) for f in findings], [(30, 3)])

    def test_before_block_reading_is_not_an_anchor(self):
        findings = _lint(30, QUIET, before_lines=["grep -c '^## Results' report.md   # 1 today"])
        self.assertEqual(findings, [])


class TestCheck31StatusGateNamesNoArtifact(unittest.TestCase):
    BAD = "## Success Criteria\n\n- [ ] Sprint 2 is COMPLETE\n\n"
    GOOD = "## Success Criteria\n\n- [ ] Sprint 2 is COMPLETE in the Session Completion Tracking table of Plan.md\n\n"

    def test_bad_status_gate_names_no_artifact(self):
        findings = _lint(31, QUIET, extra=self.BAD)
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(31, "WARNING", 5)])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(_lint(31, QUIET, extra=self.BAD, newline="\r\n")), 1)

    def test_good_status_gate_names_file_and_table(self):
        self.assertEqual(_lint(31, QUIET, extra=self.GOOD), [])

    def test_good_prose_mention_is_not_a_gate(self):
        extra = "The gate file is COMPLETE, so it is flagged, never edited.\n\n"
        self.assertEqual(_lint(31, QUIET, extra=extra), [])


class TestCheck32FileProducingTaskWithoutSizeGate(unittest.TestCase):
    HEAD = "**Output:** `Outputs/X-Summary.md`\n\n## Expected Output\n\n- the summary\n\n"
    BAD = HEAD + "## Success Criteria\n\n- [ ] The summary exists\n\n"
    GOOD = HEAD + (
        "## Success Criteria\n\n- [ ] The summary exists\n"
        "- [ ] `python measure_files.py Outputs/X-Summary.md --md` reports OK\n\n"
    )

    def test_bad_output_with_no_size_gate(self):
        findings = _lint(32, QUIET, extra=self.BAD)
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(32, "ERROR", 3)])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(_lint(32, QUIET, extra=self.BAD, newline="\r\n")), 1)

    def test_good_measured_size_gate(self):
        self.assertEqual(_lint(32, QUIET, extra=self.GOOD), [])

    def test_good_crlf_measured_size_gate(self):
        self.assertEqual(_lint(32, QUIET, extra=self.GOOD, newline="\r\n"), [])

    def test_no_expected_output_section_is_not_file_producing(self):
        extra = "**Output:** `Outputs/X-Summary.md`\n\n## Success Criteria\n\n- [ ] done\n\n"
        self.assertEqual(_lint(32, QUIET, extra=extra), [])

    def test_fenced_comment_line_does_not_end_success_criteria(self):
        # A "# comment" in a fenced command is not a heading; the size gate after it counts.
        extra = self.HEAD + (
            "## Success Criteria\n\n```bash\n# measure the produced file\n"
            "python measure_files.py Outputs/X-Summary.md --md\n```\n\n"
        )
        self.assertEqual(_lint(32, QUIET, extra=extra), [])

    def test_fenced_output_and_expected_output_sample_is_not_file_producing(self):
        extra = (
            "## Notes\n\n```markdown\n**Output:** `Outputs/X-Summary.md`\n\n"
            "## Expected Output\n```\n\n## Success Criteria\n\n- [ ] done\n\n"
        )
        self.assertEqual(_lint(32, QUIET, extra=extra), [])


class TestCheck33WriterCommandWithoutScratchTarget(unittest.TestCase):
    def test_bad_fixer_on_live_tree(self):
        findings = _lint(33, ["ruff check --fix plugins/x.py   # expect All checks passed"])
        self.assertEqual(_pairs(findings), [(33, "ERROR")])

    def test_good_fixer_on_scratch_copy(self):
        self.assertEqual(_lint(33, ['ruff check --fix "$SCRATCH/x.py"   # expect All checks passed']), [])

    def test_good_dry_run_does_not_write(self):
        self.assertEqual(_lint(33, ["upgrade_run --apply --dry-run plan/   # expect 0 changes"]), [])

    def test_bad_equals_form(self):
        findings = _lint(33, ["formatter --write=all docs/   # expect exit 0"])
        self.assertEqual(len(findings), 1)


class TestCheck35AbsenceGateOverMandatedProse(unittest.TestCase):
    MANDATE = "The module docstring must explain why `date.today` is absent.\n\n"
    GATE = ("grep -c 'date.today' src/clock.py   # expect 0",)

    def test_bad_zero_gate_while_the_brief_mandates_prose(self):
        findings = _lint(35, self.GATE, extra=self.MANDATE)
        self.assertEqual(_pairs(findings), [(35, "WARNING")])
        self.assertIn("date.today", findings[0]["message"])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(_lint(35, self.GATE, extra=self.MANDATE, newline="\r\n")), 1)

    def test_bad_escaped_dot_pattern_and_must_be_wording(self):
        gate = [r"grep -c 'date\.today' notes.md   # MUST be 0"]
        self.assertEqual(_pairs(_lint(35, gate, extra=self.MANDATE)), [(35, "WARNING")])

    def test_good_no_mandate_sentence(self):
        self.assertEqual(_lint(35, self.GATE), [])

    def test_good_target_is_not_prose_bearing(self):
        gate = ["grep -c 'date.today' data.json   # expect 0"]
        self.assertEqual(_lint(35, gate, extra=self.MANDATE), [])

    def test_good_line_labelled_wrong(self):
        gate = ["grep -c 'date.today' src/clock.py   # WRONG: expect 0"]
        self.assertEqual(_lint(35, gate, extra=self.MANDATE), [])

    def test_good_gate_expects_a_hit(self):
        gate = ["grep -c 'date.today' src/clock.py   # expect 1"]
        self.assertEqual(_lint(35, gate, extra=self.MANDATE), [])

    def test_good_regex_pattern_is_not_a_literal_token(self):
        gate = ["grep -cE 'date.today|clock' src/clock.py   # expect 0"]
        self.assertEqual(_lint(35, gate, extra=self.MANDATE), [])

    def test_good_mandate_is_about_another_token(self):
        extra = "The module docstring must explain why `time.sleep` is absent.\n\n"
        self.assertEqual(_lint(35, self.GATE, extra=extra), [])

    def test_good_mandate_inside_a_fenced_block_is_a_sample(self):
        extra = "```text\nThe module docstring must explain why `date.today` is absent.\n```\n\n"
        self.assertEqual(_lint(35, self.GATE, extra=extra), [])


class TestCheck36DigitlessIdentifierClass(unittest.TestCase):
    def test_bad_grep_class_without_a_digit(self):
        findings = _lint(36, ["grep -oE '[a-z_]+' ddl.sql   # expect 15 names"])
        self.assertEqual(_pairs(findings), [(36, "WARNING")])
        self.assertIn("the class [a-z_],", findings[0]["message"])

    def test_bad_on_a_crlf_file(self):
        gate = ["grep -oE '[a-z_]+' ddl.sql   # expect 15 names"]
        self.assertEqual(len(_lint(36, gate, newline="\r\n")), 1)

    def test_bad_uppercase_class_in_a_python_extractor(self):
        gate = ["python -c \"import re; print(re.findall(r'AS\\s+([A-Z_]+)', open('m.sql').read()))\""]
        self.assertEqual(_pairs(_lint(36, gate)), [(36, "WARNING")])

    def test_good_class_with_a_digit_range(self):
        self.assertEqual(_lint(36, ["grep -oE '[a-z0-9_]+' ddl.sql   # expect 15 names"]), [])

    def test_good_word_class_and_digit_escape(self):
        self.assertEqual(_lint(36, ["grep -oE '\\w+' ddl.sql   # expect 15 names"]), [])
        self.assertEqual(_lint(36, ["grep -oE '[A-Za-z_\\d]+' ddl.sql   # expect 15 names"]), [])

    def test_good_negated_class(self):
        self.assertEqual(_lint(36, ["grep -oE '[^a-z_]+' ddl.sql   # expect 3"]), [])

    def test_good_class_without_a_repeat(self):
        self.assertEqual(_lint(36, ["grep -c '[a-z_]x' ddl.sql   # expect 1"]), [])

    def test_good_line_labelled_wrong(self):
        self.assertEqual(_lint(36, ["grep -oE '[a-z_]+' ddl.sql   # WRONG: drops country_3_code"]), [])


class TestCheck37ExclusionOverPathPrefix(unittest.TestCase):
    BAD = "grep -rn pooled_table src | grep -v pooled_table_season   # expect 36"

    def test_bad_exclusion_over_recursive_numbered_output(self):
        findings = _lint(37, [self.BAD])
        self.assertEqual(_pairs(findings), [(37, "WARNING")])
        self.assertIn("pooled_table_season", findings[0]["message"])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(_lint(37, [self.BAD], newline="\r\n")), 1)

    def test_bad_long_flags(self):
        gate = ["grep --recursive --line-number x src | grep --invert-match legacy   # expect 4"]
        self.assertEqual(_pairs(_lint(37, gate)), [(37, "WARNING")])

    def test_good_exclusion_anchored_at_the_line_start(self):
        gate = ["grep -rn pooled_table src | grep -v '^src/legacy/'   # expect 36"]
        self.assertEqual(_lint(37, gate), [])

    def test_good_exclusion_anchored_past_the_prefix(self):
        gate = ["grep -rn pooled_table src | grep -vE ':[0-9]+:.*pooled_table_season'   # expect 36"]
        self.assertEqual(_lint(37, gate), [])

    def test_bad_two_file_operands_print_a_path_prefix(self):
        gate = ["grep -c Reviewer a.md b.md | grep -v a.md   # expect 1"]
        self.assertEqual(_pairs(_lint(37, gate)), [(37, "WARNING")])

    def test_good_exclusion_of_the_count_after_the_path(self):
        gate = ["grep -rc Reviewer refs | grep -v ':0$'   # expect 2"]
        self.assertEqual(_lint(37, gate), [])

    def test_good_exclusion_by_exact_path_with_its_colon(self):
        gate = ["grep -rn Reviewer refs | grep -vE '(refs/a\\.md|refs/b\\.md):'   # expect 4"]
        self.assertEqual(_lint(37, gate), [])

    def test_good_content_filter_after_a_single_file_line_number(self):
        gate = ["grep -n pooled_table src/one.py | grep -v pooled_table_season   # expect 36"]
        self.assertEqual(_lint(37, gate), [])

    def test_good_no_filename_flag_prints_no_path(self):
        gate = ["grep -h '^status:' a.md b.md | sort -u | grep -vE 'DONE|OPEN'   # expect nothing"]
        self.assertEqual(_lint(37, gate), [])

    def test_good_no_inverting_stage(self):
        self.assertEqual(_lint(37, ["grep -n x f.md | grep -c y   # expect 2"]), [])

    def test_good_first_stage_prints_no_prefix(self):
        self.assertEqual(_lint(37, ["grep -c x f.md | grep -v 0   # expect 1"]), [])

    def test_good_inversion_is_the_first_stage(self):
        self.assertEqual(_lint(37, ["grep -rnv x src   # expect 3"]), [])

    def test_good_line_labelled_wrong(self):
        gate = ["grep -rn pooled_table src | grep -v pooled_table_season   # WRONG: drops files"]
        self.assertEqual(_lint(37, gate), [])


class TestCheck38SplitSliceAsParser(unittest.TestCase):
    BAD = "python -c \"print(len(open('nb.py').read().split('params = [')[1].split(']')[0]))\"   # expect 99"

    def test_bad_split_result_indexed_as_a_parser(self):
        findings = _lint(38, [self.BAD])
        self.assertEqual(_pairs(findings), [(38, "WARNING")])
        self.assertIn(".split(", findings[0]["message"])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(_lint(38, [self.BAD], newline="\r\n")), 1)

    def test_good_split_without_an_index(self):
        gate = ["python -c \"print(len(open('f.md').read().split()))\"   # expect 7"]
        self.assertEqual(_lint(38, gate), [])

    def test_bad_frontmatter_slice(self):
        gate = ["python -c \"print(open('a.md').read().split('---')[1])\"   # expect the block"]
        self.assertEqual(_pairs(_lint(38, gate)), [(38, "WARNING")])

    def test_good_basename_split_on_a_slash(self):
        gate = ["python -c \"print('a/b.md'.split('/')[-1])\"   # expect b.md"]
        self.assertEqual(_lint(38, gate), [])

    def test_good_ast_parse(self):
        gate = ["python -c \"import ast; print(len(ast.parse(open('nb.py').read()).body))\"   # expect 4"]
        self.assertEqual(_lint(38, gate), [])

    def test_good_line_labelled_wrong(self):
        gate = [self.BAD.replace("# expect 99", "# WRONG: stops at an unrelated bracket")]
        self.assertEqual(_lint(38, gate), [])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in verify_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in verify_module.CHECKS]
        self.assertEqual(names, ["check30", "check31", "check32", "check33", "check35", "check36", "check37", "check38"],
        )

    def test_severity_constants_match_the_linter(self):
        self.assertEqual(verify_module.SEVERITY_ERROR, lint_module.SEVERITY_ERROR)
        self.assertEqual(verify_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)
        self.assertEqual(verify_module.SEVERITY_UNCERTAIN, lint_module.SEVERITY_UNCERTAIN)

    def test_anchor_blocks_match_the_linter(self):
        self.assertEqual(
            verify_module._ANCHOR_BLOCKS, {lint_module.BLOCK_AFTER, lint_module.BLOCK_EXIT_CRITERION}
        )

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "ERROR", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(verify_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_verify.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_a_new_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_task(tmp, ["ruff check --fix plugins/x.py   # expect All checks passed"])
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("[ERROR] Check 33:", completed.stdout)

    def test_cli_run_as_script_reports_an_extractor_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_task(tmp, ["grep -rn pooled_table src | grep -v pooled_table_season   # expect 36"])
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("[WARNING] Check 37:", completed.stdout, completed.stderr)


if __name__ == "__main__":
    unittest.main()
