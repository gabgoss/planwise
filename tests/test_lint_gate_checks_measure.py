"""Tests for the measurement-rule lint checks in ``lint_gate_checks_measure``.

Each check gets one known-bad fixture that must produce a finding naming it (the
mutation control) and the same fixture repaired, which must produce none for it (the
positive control). The fixtures are built in temporary directories.
"""

import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_measure as measure_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan

KIB_TEN = "x" * 10240  # a 10.0 KiB file


def _task(context_rows=(), verification=""):
    rows = "".join(f"{row}\n" for row in context_rows)
    table = "| Priority | File | KiB | ~Tokens | Purpose |\n|---|---|---:|---:|---|\n" + rows if rows else ""
    return (
        "# Task: Fixture\n\n"
        "**Output:** `out/result.md`\n\n"
        "## Objective\n\nDo the work.\n\n"
        f"## Required Context\n\n{table}\n"
        "## Execution Steps\n\n1. Read the file.\n\n"
        f"{verification}"
    )


def _verification(before="", after=""):
    return (
        "## Verification Commands\n\n"
        f"**Before (runner):**\n```\n{before}\n```\n"
        f"**After (runner):**\n```\n{after}\n```\n"
    )


def _lint(check, text, files=None, name="TASK-01-Fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
        for rel, body in (files or {}).items():
            target = Path(tmp) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8", newline="\n")
        with redirect_stderr(StringIO()):
            return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


def _context(root: Path):
    class _Context:
        plan_root = root

        def markdown_files(self):
            return sorted(p for p in root.rglob("*.md") if p.is_file())

    return _Context()


class TestCheck48RequiredContextSize(unittest.TestCase):
    def _row(self, cell="`data.md` — whole", kib="10.0", tokens="—"):
        return f"| 1 | {cell} | {kib} | {tokens} | purpose |"

    def test_bad_size_miss_above_tolerance(self):
        findings = _lint(48, _task([self._row(kib="2.0")]), files={"data.md": KIB_TEN})
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(48, "WARNING")])

    def test_good_size_matches(self):
        self.assertEqual(_lint(48, _task([self._row(kib="10.0")]), files={"data.md": KIB_TEN}), [])

    def test_good_size_inside_tolerance(self):
        self.assertEqual(_lint(48, _task([self._row(kib="9.0")]), files={"data.md": KIB_TEN}), [])

    def test_whole_in_the_kib_cell_is_a_whole_file_row(self):
        findings = _lint(48, _task([self._row(cell="`data.md`", kib="2.0 (whole)")]), files={"data.md": KIB_TEN})
        self.assertEqual(len(findings), 1)

    def test_section_slice_row_is_out_of_reach(self):
        for cell, kib in (
            ("`data.md` — §2 only", "2.0"),
            ("`data.md` — by `Grep`, then `offset`/`limit`", "2.0"),
            ("`data.md`", "2.0 (slice of 10.0 whole)"),
        ):
            findings = _lint(48, _task([self._row(cell=cell, kib=kib)]), files={"data.md": KIB_TEN})
            self.assertEqual(findings, [], (cell, kib))

    def test_tokens_used_only_when_kib_is_empty(self):
        bad = _lint(48, _task([self._row(kib="—", tokens="~1.0K")]), files={"data.md": KIB_TEN})
        self.assertEqual(len(bad), 1)
        both = _lint(48, _task([self._row(kib="10.0", tokens="~1.0K")]), files={"data.md": KIB_TEN})
        self.assertEqual(both, [])

    def test_project_root_path_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cloned-repos" / "x").mkdir(parents=True)
            (root / "cloned-repos" / "x" / "big.md").write_text(KIB_TEN, encoding="utf-8")
            plan = root / "plan"
            plan.mkdir()
            (plan / "TASK-01-Fixture.md").write_text(
                _task([self._row(cell="`cloned-repos/x/big.md` — whole", kib="2.0")]), encoding="utf-8", newline="\n"
            )
            summary = measure_module.measure_summary(_context(plan))
        self.assertEqual((summary["examined"], summary["skipped"], summary["measured"]), (1, 0, 1))

    def test_summary_line_counts_skipped_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task([self._row(), self._row(cell="`missing.md` — whole")]), encoding="utf-8", newline="\n"
            )
            summary = measure_module.measure_summary(_context(Path(tmp)))
        self.assertEqual(summary["line"], "rows examined 2, skipped 1 (unresolved), measured 1")

    def test_zero_measured_reads_not_checked_never_clean(self):
        findings = _lint(48, _task([self._row(cell="`missing.md` — whole")]))
        self.assertEqual([f["severity"] for f in findings], ["UNCERTAIN"])
        self.assertIn("NOT CHECKED", findings[0]["message"])

    def test_no_rows_is_silent(self):
        self.assertEqual(_lint(48, _task()), [])

    def test_summary_is_written_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            (Path(tmp) / "TASK-01-Fixture.md").write_text(_task([self._row()]), encoding="utf-8", newline="\n")
            captured = StringIO()
            with redirect_stderr(captured):
                lint_plan(Path(tmp), execute=False)
        self.assertIn("rows examined 1, skipped 0 (unresolved), measured 1", captured.getvalue())


class TestCheck49DiffMatcherWithoutCounts(unittest.TestCase):
    BAD = "git diff 1bc4e0a -- a.md | grep -c '^+[^+]'"
    NAME_ONLY = "git diff --name-only 1bc4e0a -- a.md | wc -l"
    PORCELAIN = "git status --porcelain -- a.md | grep -c '^??'"

    def test_bad_matcher_without_counts(self):
        findings = _lint(49, _task(verification=_verification(after=self.BAD)))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(49, "ERROR")])

    def test_good_with_name_only_count(self):
        text = _task(verification=_verification(after=f"{self.BAD}\n{self.NAME_ONLY}"))
        self.assertEqual(_lint(49, text), [])

    def test_good_with_porcelain_count(self):
        text = _task(verification=_verification(after=f"{self.BAD}\n{self.PORCELAIN}"))
        self.assertEqual(_lint(49, text), [])

    def test_count_in_another_block_does_not_count(self):
        text = _task(verification=_verification(before=self.NAME_ONLY, after=self.BAD))
        self.assertEqual(len(_lint(49, text)), 1)

    def test_diff_without_a_matcher_is_not_read(self):
        self.assertEqual(_lint(49, _task(verification=_verification(after="git diff --stat 1bc4e0a -- a.md"))), [])

    def test_wrong_line_is_skipped(self):
        self.assertEqual(_lint(49, _task(verification=_verification(after=f"# WRONG {self.BAD}"))), [])


class TestCheck50BaseGate(unittest.TestCase):
    NUMSTAT = "git diff --numstat $X_BASE -- a.md"
    RESOLVE = "git cat-file -e $X_BASE"
    COUNT = "git diff --name-only $X_BASE -- a.md | wc -l"

    def test_bad_base_without_resolve_step(self):
        findings = _lint(50, _task(verification=_verification(after=f"{self.NUMSTAT}\n{self.COUNT}")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(50, "WARNING")])
        self.assertIn("cat-file -e", findings[0]["message"])

    def test_good_base_with_resolve_and_count(self):
        text = _task(verification=_verification(before=self.RESOLVE, after=f"{self.NUMSTAT}\n{self.COUNT}"))
        self.assertEqual(_lint(50, text), [])

    def test_angle_bracket_operand_is_read(self):
        text = _task(verification=_verification(after=f"git diff --numstat <X_BASE> -- a.md\n{self.COUNT}"))
        self.assertEqual(len(_lint(50, text)), 1)

    def test_bad_literal_base_placeholder(self):
        text = _task(verification=_verification(before=self.RESOLVE, after="git diff --numstat {BASE} -- a.md"))
        findings = [f for f in _lint(50, text) if "{BASE}" in f["message"]]
        self.assertEqual(len(findings), 1)

    def test_bad_base_diff_without_spanned_file_count(self):
        text = _task(verification=_verification(before=self.RESOLVE, after=self.NUMSTAT))
        findings = _lint(50, text)
        self.assertEqual(len(findings), 1)
        self.assertIn("spanned-file count", findings[0]["message"])

    def test_good_with_porcelain_count_instead(self):
        text = _task(verification=_verification(
            before=self.RESOLVE, after=f"{self.NUMSTAT}\ngit status --porcelain -- a.md | grep -c '^??'"
        ))
        self.assertEqual(_lint(50, text), [])

    def test_diff_reported_by_check_49_is_not_reported_again(self):
        text = _task(verification=_verification(before=self.RESOLVE, after="git diff $X_BASE -- a.md | grep -c '^+'"))
        self.assertEqual(_lint(50, text), [])
        self.assertEqual(len(_lint(49, text)), 1)

    def test_a_non_task_file_is_not_read(self):
        text = "# Notes\n\n" + _verification(after=self.NUMSTAT)
        self.assertEqual(_lint(50, text, name="Notes.md"), [])


class TestCheck51CharCountInByteIdentity(unittest.TestCase):
    BAD = "PRE=$(awk '/^Last/ {print length($0)}' a.md)\n[ \"$PRE\" -eq \"$POST\" ]"
    GOOD = "PRE=$(wc -c < a.md)\n[ \"$PRE\" -eq \"$POST\" ]"

    def test_bad_awk_length_in_byte_equality(self):
        findings = _lint(51, _task(verification=_verification(after=self.BAD)))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(51, "ERROR")])
        self.assertIn("measure-aggregate-provenance.md", findings[0]["message"])

    def test_good_byte_instrument(self):
        self.assertEqual(_lint(51, _task(verification=_verification(after=self.GOOD))), [])

    def test_bad_shell_length_operand(self):
        after = "N=${#TEXT}\n[ \"$N\" -eq 58562 ]"
        self.assertEqual(len(_lint(51, _task(verification=_verification(after=after)))), 1)

    def test_bad_len_over_decoded_string(self):
        after = "python -c \"print(len(open('a.md').read()))\"\ntest \"$A\" == \"$B\""
        self.assertEqual(len(_lint(51, _task(verification=_verification(after=after)))), 1)

    def test_good_len_over_raw_bytes(self):
        after = "python -c \"print(len(open('a.md','rb').read()))\"\ntest \"$A\" == \"$B\""
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])

    def test_good_operand_without_an_equality_assertion(self):
        after = "awk '{print length($0)}' a.md"
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])

    def test_good_array_count_is_not_a_string_length(self):
        after = "N=${#FILES[@]}\n[ \"$N\" -eq 3 ]"
        self.assertEqual(_lint(51, _task(verification=_verification(after=after))), [])


class TestCheck52CharacterClassAfterDiffSign(unittest.TestCase):
    CORRECT = "git diff 1bc4e0a -- a.md | grep -E '^[+-]' | grep -vE '^(\\+\\+\\+|---)'"

    def _bad(self, pattern):
        return f"git diff 1bc4e0a -- a.md | grep -c '{pattern}'"

    def test_bad_removed_line_class_form(self):
        findings = _lint(52, _task(verification=_verification(after=self._bad("^-[^-]"))))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(52, "ERROR")])
        self.assertIn("gate-predicate-discrimination.md", findings[0]["message"])
        self.assertIn("§6", findings[0]["message"])

    def test_bad_added_line_class_form(self):
        self.assertEqual(len(_lint(52, _task(verification=_verification(after=self._bad("^+[^+]"))))), 1)

    def test_bad_both_signs_class_form(self):
        after = "git diff 1bc4e0a -- a.md | grep -E '^[+-][^+-]'"
        self.assertEqual(len(_lint(52, _task(verification=_verification(after=after)))), 1)

    def test_good_section_six_correct_form(self):
        self.assertEqual(_lint(52, _task(verification=_verification(after=self.CORRECT))), [])

    def test_good_added_lines_pair(self):
        after = "git diff 1bc4e0a -- a.md | grep '^+' | grep -v '^+++'"
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])

    def test_good_class_pattern_outside_a_diff_is_not_read(self):
        self.assertEqual(_lint(52, _task(verification=_verification(after="grep -c '^-[^-]' a.md"))), [])

    def test_check_24_form_is_not_reported_here(self):
        after = "git diff 1bc4e0a -- a.md | grep -v '^\\+\\+\\+'"
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])
        self.assertEqual(len(_lint(24, _task(verification=_verification(after=after)))), 1)

    def test_wrong_line_is_skipped(self):
        after = "# WRONG " + self._bad("^-[^-]")
        self.assertEqual(_lint(52, _task(verification=_verification(after=after))), [])


class TestCheck53BlobBytesAgainstCheckoutPin(unittest.TestCase):
    BLOB = "git show 1bc4e0a:a.md | wc -c"
    LINES = "git show 1bc4e0a:a.md | wc -l"
    CHECKOUT = "wc -c a.md"

    def test_bad_blob_bytes_against_checkout_pin(self):
        findings = _lint(53, _task(verification=_verification(after=f"{self.BLOB}\n{self.CHECKOUT}")))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(53, "WARNING")])
        self.assertIn("§8.12", findings[0]["message"])

    def test_bad_blob_bytes_against_literal_pin(self):
        after = "[ \"$(git show 1bc4e0a:a.md | wc -c)\" -eq 258364 ]"
        self.assertEqual(len(_lint(53, _task(verification=_verification(after=after)))), 1)

    def test_good_with_blob_line_count(self):
        after = f"{self.BLOB}\n{self.LINES}\n{self.CHECKOUT}"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])

    def test_good_blob_against_blob(self):
        after = f"{self.BLOB}\ngit show 1bc4e0a~1:a.md | wc -c"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])

    def test_good_checkout_on_both_sides(self):
        self.assertEqual(_lint(53, _task(verification=_verification(after=self.CHECKOUT))), [])

    def test_piped_wc_is_not_a_checkout_pin(self):
        after = f"{self.BLOB}\ncat a.md | wc -c"
        self.assertEqual(_lint(53, _task(verification=_verification(after=after))), [])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in measure_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in measure_module.CHECKS]
        self.assertEqual(names, [f"check{number}" for number in range(48, 54)])

    def test_severity_constants_match_the_linter(self):
        for name in ("SEVERITY_ERROR", "SEVERITY_WARNING", "SEVERITY_UNCERTAIN"):
            self.assertEqual(getattr(measure_module, name), getattr(lint_module, name))

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(measure_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_measure.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_the_new_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task(
                    context_rows=["| 1 | `data.md` — whole | 2.0 | — | purpose |"],
                    verification=_verification(after="git diff 1bc4e0a -- a.md | grep -c '^+[^+]'"),
                ),
                encoding="utf-8", newline="\n",
            )
            (Path(tmp) / "data.md").write_text(KIB_TEN, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("[WARNING] Check 48:", completed.stdout, completed.stderr)
        self.assertIn("[ERROR] Check 49:", completed.stdout, completed.stderr)
        self.assertIn("rows examined 1, skipped 0 (unresolved), measured 1", completed.stderr)


if __name__ == "__main__":
    unittest.main()
