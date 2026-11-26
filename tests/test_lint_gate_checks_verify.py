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


def _lint_files(check, files):
    """Write each ``{relative path: text}`` entry into a plan tree and lint it."""
    with tempfile.TemporaryDirectory() as tmp:
        for rel, text in files.items():
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


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


class TestWrongLabelIsReadFromTheNote(unittest.TestCase):
    """The word WRONG exempts a gate only as a label. A pattern or a target
    that merely holds the word leaves the gate checked."""

    CALL = "Grep  pattern='{pattern}'  path='{path}'  output_mode='count'{note}\n\n"

    def _call(self, pattern="^## Results", path="report.md", note=""):
        return _lint(30, QUIET, extra=self.CALL.format(pattern=pattern, path=path, note=note))

    def test_check30_fires_on_a_pattern_that_holds_the_word(self):
        findings = _lint(30, ["grep -c '^## WRONG' refs/x.md   # expect 1"])
        self.assertEqual(_pairs(findings), [(30, "WARNING")])

    def test_check30_labelled_command_stays_silent(self):
        self.assertEqual(_lint(30, ["grep -c '^## Results' report.md   # WRONG: expect 1"]), [])

    def test_check30_fires_on_a_native_call_whose_pattern_holds_the_word(self):
        self.assertEqual(_pairs(self._call(pattern="^## WRONG")), [(30, "WARNING")])

    def test_check30_fires_on_a_native_call_whose_target_holds_the_word(self):
        self.assertEqual(_pairs(self._call(path="refs/WRONG-cases.md")), [(30, "WARNING")])

    def test_check30_labelled_native_call_stays_silent(self):
        self.assertEqual(self._call(note="   # WRONG: no date"), [])

    def test_check33_fires_on_a_writer_whose_target_holds_the_word(self):
        findings = _lint(33, ["ruff check --fix plugins/WRONG_cases.py   # expect All checks passed"])
        self.assertEqual(_pairs(findings), [(33, "ERROR")])

    def test_check33_labelled_writer_stays_silent(self):
        self.assertEqual(_lint(33, ["ruff check --fix plugins/x.py   # WRONG: writes the live tree"]), [])

    def test_check35_fires_on_a_target_that_holds_the_word(self):
        gate = ["grep -c 'date.today' src/WRONG_clock.py   # expect 0"]
        findings = _lint(35, gate, extra=TestCheck35AbsenceGateOverMandatedProse.MANDATE)
        self.assertEqual(_pairs(findings), [(35, "WARNING")])

    def test_check35_fires_on_a_pattern_that_holds_the_word(self):
        mandate = "The module docstring must explain why `WRONG_MODE` is absent.\n\n"
        findings = _lint(35, ["grep -c 'WRONG_MODE' src/clock.py   # expect 0"], extra=mandate)
        self.assertEqual(_pairs(findings), [(35, "WARNING")])

    def test_check35_labelled_mandate_line_is_still_ignored(self):
        mandate = "WRONG: the module docstring must explain why `date.today` is absent.\n\n"
        self.assertEqual(_lint(35, TestCheck35AbsenceGateOverMandatedProse.GATE, extra=mandate), [])

    def test_check35_fires_when_the_mandate_line_names_a_target_that_holds_the_word(self):
        mandate = "The docstring of `src/WRONG_clock.py` must explain why `date.today` is absent.\n\n"
        findings = _lint(35, ["grep -c 'date.today' src/WRONG_clock.py   # expect 0"], extra=mandate)
        self.assertEqual(_pairs(findings), [(35, "WARNING")])

    def test_check35_label_still_counts_when_the_gate_token_is_the_word(self):
        mandate = "WRONG: the module docstring must explain why `WRONG` is absent.\n\n"
        self.assertEqual(_lint(35, ["grep -c 'WRONG' src/clock.py   # expect 0"], extra=mandate), [])


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

    def test_bad_pattern_holding_the_word_wrong_is_not_a_label(self):
        gate = ["grep -rn WRONG refs | grep -v legacy   # expect 4"]
        self.assertEqual(_pairs(_lint(37, gate)), [(37, "WARNING")])


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


# The fixture lines below are verbatim lines of real plan files, except where a
# comment says CONSTRUCTED. The plan file each line came from is named in the
# class docstring, and no fixture file name carries a plan id.
COUNT_PIN_LINE = "- [ ] `SURFACE_NAMES` has 21 members and `declarations` sits directly after `plugin_types`"
TWO_SIDED_LINE = (
    "   - **Step 4b, after Step 4.** Read `relevance.py`: `candidates`, and the `dts` and `init` blocks it reads. "
    "Add a block that reads `diff.get(\"declarations\")`. Emit one candidate per consumer in the `declarations` "
    "entry of `consumers.json` in two cases: both sides are present and their `sha256` values differ "
    "(change `changed`), or `new` is present and `old` is absent (change `added`). Use the row shape of the "
    "`dts` and `init` blocks, key `sha256`, and evidence `old {sha8} -> new {sha8}`, with `n/a` for a missing "
    "side. A diff with no `declarations` key, or with equal `sha256` values, emits nothing (D10: read with `.get`)."
)
TWO_SIDED_PASS_LINE = (
    "- [ ] The twin has a top-level `init` with `added`, `removed`, `changed`, `unavailable`, `old`, `new`; "
    "`plugins` shape differences are normalised away."
)
FIRST_WRITE_LINE = """3. **The preflight gate**, one short block per handler, placed immediately before the handler's first write: `plan.md` before Step 3 (folder creation); `run.md` at the start of Phase 1 before any Recovery write; `lessons.md` at the top of every mode that writes a lesson file (one shared "Index shape gate" subsection the modes point at, which may extend the existing Lessons-Index Write Convention); `backlog.md` replacing the Phase 1 `--check` STOP with the preflight (keep the STOP semantics, and replace the existing exit-2 sentence rather than adding beside it). The block: run `python "{plugin_root}/scripts/index_shape_preflight.py" --config "{planwise_root}/config.yaml"`; when `any_legacy` is true, one `AskUserQuestion`: "The {names} index is still hand-authored. Migrate it now (the upgrade backs up every file it rewrites, under `{planwise_root}/upgrade-backups/`) or stop?"; on migrate, run the upgrade handler's Step 2.4 command at the pinned version (`--upgrade-pair {plugin_version}-to-{plugin_version}`) and continue; on stop, STOP. Auto-Mode class: `critical` (never migrate unattended; report and stop). Each block is under 1 KiB."""


def _doc(*lines, task=False):
    """A plan file: a ``# Task:`` heading for a task file, else a plain heading."""
    heading = "# Task: Fixture" if task else "# Notes"
    return heading + "\n\n" + "\n".join(lines) + "\n"


class TestCheck63CountPinWithoutInstrument(unittest.TestCase):
    """The must-fail line is a criterion of a Sprint-Plan, task and Orchestration file of one real plan."""

    def test_bad_count_pin_in_a_task_file(self):
        findings = _lint_files(63, {"TASK-01-Surface.md": _doc(COUNT_PIN_LINE, task=True)})
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(63, "WARNING", 3)])
        self.assertIn("`SURFACE_NAMES`", findings[0]["message"])
        self.assertIn("A pinned count names the artifact and version it was read from", findings[0]["message"])

    def test_bad_count_pin_in_a_sprint_plan_file(self):
        findings = _lint_files(63, {"Sprint-Plan.md": _doc(COUNT_PIN_LINE)})
        self.assertEqual(_pairs(findings), [(63, "WARNING")])

    def test_bad_on_a_crlf_file(self):
        text = _doc(COUNT_PIN_LINE).replace("\n", "\r\n")
        self.assertEqual(len(_lint_files(63, {"Sprint-Plan.md": text})), 1)

    # CONSTRUCTED: no real line holds an instrument beside a count pin, so the
    # pass arm appends one to the real line.
    def test_good_instrument_on_the_same_line(self):
        line = COUNT_PIN_LINE + " (21 measured 2026-11-20 with len(SURFACE_NAMES) at base)"
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": _doc(line)}), [])

    def test_good_wc_instrument(self):
        line = COUNT_PIN_LINE + " (`wc -l` of the listing)"
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": _doc(line)}), [])

    def test_good_subject_is_a_file(self):
        line = "- [ ] `consumers.json` has 21 members"
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": _doc(line)}), [])

    def test_good_count_pin_inside_a_fenced_block(self):
        text = _doc("```text", COUNT_PIN_LINE, "```")
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": text}), [])

    def test_good_line_labelled_wrong(self):
        line = COUNT_PIN_LINE + "   # WRONG: the count came from a comment"
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": _doc(line)}), [])

    def test_good_file_under_an_outputs_folder(self):
        self.assertEqual(_lint_files(63, {"Session-01/Outputs/Summary.md": _doc(COUNT_PIN_LINE)}), [])

    def test_good_count_outside_a_checkbox(self):
        line = "The tuple `SURFACE_NAMES` has 21 members."
        self.assertEqual(_lint_files(63, {"Sprint-Plan.md": _doc(line)}), [])


class TestCheck64TwoSidedSpecWithoutRemovedCell(unittest.TestCase):
    """The must-fail line is a spec line of one real task file. The pass line is a criterion of another plan."""

    def test_bad_changed_and_added_with_no_removed_cell(self):
        findings = _lint_files(64, {"TASK-01-Diff.md": _doc(TWO_SIDED_LINE, task=True)})
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(64, "WARNING", 3)])

    def test_bad_on_a_crlf_file(self):
        text = _doc(TWO_SIDED_LINE, task=True).replace("\n", "\r\n")
        self.assertEqual(len(_lint_files(64, {"TASK-01-Diff.md": text})), 1)

    def test_bad_line_in_an_orchestration_file(self):
        findings = _lint_files(64, {"S01-01-Orchestration.md": _doc(TWO_SIDED_LINE)})
        self.assertEqual(_pairs(findings), [(64, "WARNING")])

    def test_good_line_names_the_removed_cell(self):
        self.assertEqual(_lint_files(64, {"TASK-01-Diff.md": _doc(TWO_SIDED_PASS_LINE, task=True)}), [])

    def test_good_fenced_sample(self):
        text = _doc("```markdown", TWO_SIDED_LINE, "```", task=True)
        self.assertEqual(_lint_files(64, {"TASK-01-Diff.md": text}), [])

    def test_good_line_labelled_wrong(self):
        line = TWO_SIDED_LINE + " WRONG: no removed cell"
        self.assertEqual(_lint_files(64, {"TASK-01-Diff.md": _doc(line, task=True)}), [])

    def test_good_file_is_neither_a_task_nor_an_orchestration_file(self):
        self.assertEqual(_lint_files(64, {"Sprint-Plan.md": _doc(TWO_SIDED_LINE)}), [])

    def test_good_file_under_an_outputs_folder(self):
        text = _doc(TWO_SIDED_LINE, task=True)
        self.assertEqual(_lint_files(64, {"Session-01/Outputs/TASK-01-Diff.md": text}), [])


class TestCheck65FirstWritePlacementWithoutWriteList(unittest.TestCase):
    """The must-fail line is a step of one real task file."""

    def test_bad_gate_before_the_first_write_with_no_write_list(self):
        findings = _lint_files(65, {"TASK-01-Gate.md": _doc(FIRST_WRITE_LINE, task=True)})
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(65, "WARNING", 3)])
        self.assertIn("writes in order", findings[0]["message"])

    def test_bad_on_a_crlf_file(self):
        text = _doc(FIRST_WRITE_LINE, task=True).replace("\n", "\r\n")
        self.assertEqual(len(_lint_files(65, {"TASK-01-Gate.md": text})), 1)

    def test_bad_fires_once_for_each_line(self):
        text = _doc(FIRST_WRITE_LINE, "", FIRST_WRITE_LINE, task=True)
        self.assertEqual(len(_lint_files(65, {"TASK-01-Gate.md": text})), 2)

    # CONSTRUCTED: no real plan file holds the satisfier, so the pass arm adds
    # one line to the real line.
    def test_good_file_lists_writes_in_order(self):
        order = "writes in order: Step 0.2 item 4 (Recovery), item 5 (Outputs/), then Step 4.3 (index)"
        text = _doc(FIRST_WRITE_LINE, order, task=True)
        self.assertEqual(_lint_files(65, {"TASK-01-Gate.md": text}), [])

    def test_good_satisfier_may_sit_before_the_hit(self):
        order = "Writes in execution order: Recovery, then Outputs."
        text = _doc(order, FIRST_WRITE_LINE, task=True)
        self.assertEqual(_lint_files(65, {"TASK-01-Gate.md": text}), [])

    def test_good_fenced_sample(self):
        text = _doc("```markdown", FIRST_WRITE_LINE, "```", task=True)
        self.assertEqual(_lint_files(65, {"TASK-01-Gate.md": text}), [])

    def test_good_line_labelled_wrong(self):
        line = "WRONG: " + FIRST_WRITE_LINE
        self.assertEqual(_lint_files(65, {"TASK-01-Gate.md": _doc(line, task=True)}), [])

    def test_good_file_is_not_a_task_file(self):
        self.assertEqual(_lint_files(65, {"Sprint-Plan.md": _doc(FIRST_WRITE_LINE)}), [])


class TestCheck68LiteralExtractionBound(unittest.TestCase):
    SLICE = "python -c \"print(len(open('ddl.sql').read()[:9000].split()))\"   # expect 15"
    HEAD = "grep -n 'CREATE' ddl.sql | head -n 40 | cut -d: -f1   # expect 15 lines"
    CRITERIA = "## Success Criteria\n\n"

    def _check(self, fence_lines, **kwargs):
        return _lint(68, fence_lines, **kwargs)

    def test_bad_read_slice_with_a_literal_stop(self):
        findings = self._check([self.SLICE])
        self.assertEqual(_pairs(findings), [(68, "WARNING")])
        self.assertIn("slice", findings[0]["message"])

    def test_bad_read_text_slice(self):
        gate = ["python -c \"print(Path('ddl.sql').read_text(encoding='utf-8')[:9000].count('x'))\"   # expect 15"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_head_n_stage_feeding_another_stage(self):
        self.assertEqual(_pairs(self._check([self.HEAD])), [(68, "WARNING")])

    def test_bad_head_dash_count_form(self):
        gate = ["grep -n 'CREATE' ddl.sql | head -40 | cut -d: -f1   # expect 15 lines"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_head_c_bytes_stage(self):
        gate = ["cat ddl.sql | head -c 9000 | grep -c CREATE   # expect 15"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_tail_with_a_literal_count_feeding_another_stage(self):
        gate = ["git log --oneline | tail -n 30 | grep -c fix   # expect 3"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_grep_m_stops_after_a_literal_count(self):
        gate = ["grep -m 20 CREATE ddl.sql | cut -d: -f1   # expect 15 lines"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_grep_max_count_long_form(self):
        gate = ["grep --max-count=20 CREATE ddl.sql   # expect 15 lines"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_native_read_call_with_a_limit(self):
        extra = self.CRITERIA + "Read  file_path='ddl.sql'  offset=1  limit=200\n\n"
        findings = self._check(QUIET, extra=extra)
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(68, "WARNING", 5)])

    def test_bad_on_a_crlf_file(self):
        self.assertEqual(len(self._check([self.SLICE], newline="\r\n")), 1)
        extra = self.CRITERIA + "Read  file_path='ddl.sql'  limit=200\n\n"
        self.assertEqual(len(self._check(QUIET, extra=extra, newline="\r\n")), 1)

    def test_bad_fires_once_for_each_command(self):
        gate = ["grep -m 20 CREATE ddl.sql | head -n 40 | cut -d: -f1   # expect 15 lines"]
        self.assertEqual(len(self._check(gate)), 1)

    def test_good_slice_on_something_that_is_not_a_read_result(self):
        gate = ["python -c \"print(sha[:7])\"   # expect the short sha"]
        self.assertEqual(self._check(gate), [])

    def test_good_slice_on_a_literal_string(self):
        gate = ["python -c \"print('abcdefghij'[:9])\"   # expect abcdefghi"]
        self.assertEqual(self._check(gate), [])

    def test_good_pipeline_ending_in_head_is_display(self):
        gate = ["grep -n 'CREATE' ddl.sql | sort | head -n 5   # the first five, for the reader"]
        self.assertEqual(self._check(gate), [])

    def test_good_pipeline_ending_in_tail_is_display(self):
        gate = ["pytest -q tests 2>&1 | tail -n 5   # the summary"]
        self.assertEqual(self._check(gate), [])

    def test_good_tail_start_offset_is_not_a_count(self):
        gate = ["grep -n x f.md | tail -n +2 | wc -l   # expect 3"]
        self.assertEqual(self._check(gate), [])

    def test_good_len_in_a_comparison_clears_it(self):
        gate = ["python -c \"assert len(open('ddl.sql').read()[:9000].split()) == 15\"   # expect exit 0"]
        self.assertEqual(self._check(gate), [])

    def test_good_wc_l_as_the_last_stage_clears_it(self):
        gate = ["grep -n 'CREATE' ddl.sql | head -n 40 | wc -l   # expect 15"]
        self.assertEqual(self._check(gate), [])

    def test_good_wc_c_as_the_last_stage_clears_it(self):
        gate = ["head -c 9000 ddl.sql | wc -c   # expect 9000"]
        self.assertEqual(self._check(gate), [])

    def test_bad_filter_between_the_cut_and_the_wc(self):
        gate = ["head -n 300 schema.sql | grep -c 'ADD' | wc -l   # expect 73"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_filter_between_a_byte_cut_and_the_wc(self):
        gate = ["head -c 9000 f | grep col | wc -l   # expect 73"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_good_wc_directly_after_the_cut_clears_it(self):
        self.assertEqual(self._check(["head -n 300 schema.sql | wc -l   # expect 300"]), [])

    def test_bad_one_cleared_bound_does_not_clear_a_second(self):
        gate = ["head -n 300 f | wc -l && grep -m 20 CREATE ddl.sql | cut -d: -f1   # expect 15"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_message_and_docstring_name_the_reference_section_in_words(self):
        findings = self._check([self.SLICE])
        title = "An Extraction Is Bounded by Markers and Asserts Its Parsed Length"
        for text in (findings[0]["message"], verify_module.__doc__ or "", verify_module._check68_literal_extraction_bound_without_length_assertion.__doc__):
            text = " ".join(text.split())  # a docstring wraps the title across lines
            self.assertIn("gate-input-set-and-compared-window.md", text)
            self.assertIn(title, text)
            self.assertNotIn("gate-instrument-proof-obligations.md", text)
        source = (SCRIPTS / "lint_gate_checks_verify.py").read_text(encoding="utf-8")
        check68 = source[source.index("def _check68_"):source.index("CHECKS = [")]
        self.assertNotIn("§", check68)

    def test_good_parsed_length_note_clears_it(self):
        gate = [self.HEAD.replace("# expect 15 lines", "# expect 15 lines (parsed length asserted on the next line)")]
        self.assertEqual(self._check(gate), [])

    def test_good_parsed_length_note_clears_a_read_call(self):
        extra = self.CRITERIA + "Read  file_path='ddl.sql'  limit=200   # parsed length 200 lines, checked by wc -l\n\n"
        self.assertEqual(self._check(QUIET, extra=extra), [])

    def test_good_native_read_call_without_a_limit(self):
        extra = self.CRITERIA + "Read  file_path='ddl.sql'  offset=1\n\n"
        self.assertEqual(self._check(QUIET, extra=extra), [])

    def test_good_paged_read_instruction_under_execution_steps(self):
        extra = "## Execution Steps\n\n1. Read  file_path='handlers/plan.md'  offset=400  limit=200\n\n"
        self.assertEqual(self._check(QUIET, extra=extra), [])

    def test_good_paged_read_instruction_under_required_context(self):
        extra = "## Required Context\n\nRead  file_path='handlers/plan.md'  offset=400  limit=200\n\n"
        self.assertEqual(self._check(QUIET, extra=extra), [])

    def test_bad_read_limit_inside_the_verification_commands_block(self):
        findings = self._check(["Read  file_path='ddl.sql'  offset=1  limit=200"])
        self.assertEqual(_pairs(findings), [(68, "WARNING")])

    def test_bad_read_limit_under_a_success_criteria_heading_after_other_sections(self):
        extra = "## Execution Steps\n\n1. do it\n\n## Success Criteria\n\n- [ ] Read  file_path='a.md'  limit=9\n\n"
        self.assertEqual(len(self._check(QUIET, extra=extra)), 1)

    def test_bad_grep_pattern_holding_the_word_wrong_is_not_exempt(self):
        gate = ["head -n 5 f | grep -c 'WRONG'   # expect 1"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_bad_wrong_in_the_pattern_with_a_label_shaped_pattern(self):
        gate = ["head -n 5 f | grep -c '^> WRONG' references/x.md   # expect 1"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_good_wc_long_lines_option_clears_it(self):
        self.assertEqual(self._check(["head -n 50 f | wc --lines   # expect 50"]), [])

    def test_good_wc_long_bytes_option_clears_it(self):
        self.assertEqual(self._check(["head -c 900 f | wc --bytes   # expect 900"]), [])

    def test_bad_len_comparison_in_another_pipeline_does_not_clear_the_bound(self):
        gate = ["python -c \"assert len(a)==3\" && head -n 5 g | grep -c x   # expect 1"]
        self.assertEqual(_pairs(self._check(gate)), [(68, "WARNING")])

    def test_good_len_comparison_in_the_same_pipeline_clears_the_bound(self):
        gate = ["head -n 5 g | python -c \"import sys; assert len(sys.stdin.readlines()) == 5\"   # expect exit 0"]
        self.assertEqual(self._check(gate), [])

    def test_good_parsed_length_note_stays_a_command_level_clearer(self):
        gate = ["python -c \"assert len(a)==3\" && head -n 5 g | grep -c x   # expect 1 (parsed length asserted)"]
        self.assertEqual(self._check(gate), [])

    def test_good_line_labelled_wrong(self):
        gate = [self.HEAD.replace("# expect 15 lines", "# WRONG: the bound hides the tail")]
        self.assertEqual(self._check(gate), [])
        extra = self.CRITERIA + "WRONG: Read  file_path='ddl.sql'  limit=200\n\n"
        self.assertEqual(self._check(QUIET, extra=extra), [])


class TestFenceClosesOnABareMarkerOnly(unittest.TestCase):
    """A fence ends on a bare marker line of its own character, at least as long
    as the opener. A marker line with an info string closes nothing. At the
    opener's own length it starts a nested sample, which takes its own closer."""

    @staticmethod
    def _fenced(*lines):
        return [fenced for _number, _line, fenced in verify_module._fence_marked(list(lines))]

    def test_nested_sample_stays_inside_a_longer_outer_fence(self):
        flags = self._fenced(
            "````markdown", "```bash", "echo hi", "```", "## Heading inside outer", "````", "after"
        )
        self.assertEqual(flags, [True, True, True, True, True, True, False])

    def test_same_length_nested_sample_stays_inside_the_outer_fence(self):
        flags = self._fenced("```", "```bash", "x", "```", "## still inside", "```", "after")
        self.assertEqual(flags, [True, True, True, True, True, True, False])

    def test_schema_pin_block_of_the_task_template_is_one_fence(self):
        # The lines of the shipped task-file template's Schema Pin block.
        flags = self._fenced(
            "```", "**Schema Pin** - ddl.sql#widgets", "```sql", "## DDL comment", "```",
            "Live as of: {YYYY-MM-DD}", "```", "## Execution Steps",
        )
        self.assertEqual(flags, [True] * 7 + [False])

    def test_inline_code_line_inside_a_fence_starts_no_nested_sample(self):
        self.assertEqual(self._fenced("```", "```sql``` is the tag", "```", "after"), [True, True, True, False])

    def test_info_string_of_the_other_character_starts_no_nested_sample(self):
        self.assertEqual(self._fenced("```", "~~~bash", "```", "after"), [True, True, True, False])

    def test_shorter_marker_does_not_close(self):
        self.assertEqual(self._fenced("````", "```", "x", "````", "after"), [True, True, True, True, False])

    def test_other_character_does_not_close(self):
        self.assertEqual(self._fenced("```", "~~~", "x", "```", "after"), [True, True, True, True, False])

    def test_longer_marker_closes(self):
        self.assertEqual(self._fenced("```", "x", "`````", "after"), [True, True, True, False])

    def test_quoted_bare_marker_closes(self):
        self.assertEqual(self._fenced("> ```bash", "> x", "> ```", "after"), [True, True, True, False])

    def test_check68_section_does_not_end_at_a_heading_inside_a_nested_sample(self):
        extra = (
            "## Success Criteria\n\n"
            "````markdown\n```bash\n## a comment in the sample\n```\n````\n\n"
            "Read  file_path='ddl.sql'  limit=200\n\n"
        )
        findings = _lint(68, QUIET, extra=extra)
        self.assertEqual([(f["check"], f["line"]) for f in findings], [(68, 11)])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in verify_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in verify_module.CHECKS]
        self.assertEqual(
            names,
            [
                "check30", "check31", "check32", "check33", "check35", "check36", "check37", "check38",
                "check63", "check64", "check65", "check68",
            ],
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
