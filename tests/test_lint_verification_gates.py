#!/usr/bin/env python3
"""Unit tests for the vacuous-verification-gate linter's seven checks.

This suite is written against `lint_verification_gates.py`, a module that
does NOT exist yet on this branch. It MUST fail on import/collection when
this file is first written -- a green run at this point would mean the
suite is not exercising the module under test, not that the module is
correct. Sprint-02's later tasks implement the module (the extractor and
the allowlisted read-only executor, then the seven checks and the CLI)
against the contract fixed here; this file is not to be edited to make the
import succeed once they do.

Contract this suite binds the implementation to (documented here since no
module exists yet to read the contract off of):

  ALLOWED_EXECUTABLES
      A frozenset/set of exactly the four allowlisted executable basenames:
      "grep", "wc", "ls", "test". Nothing else, ever.

  run_command(argv: list[str]) -> dict
      Executes argv directly (no shell, no string interpolation) when
      argv[0]'s basename is in ALLOWED_EXECUTABLES, returning
        {"executed": True, "returncode": int, "stdout": str, "stderr": str}.
      Otherwise refuses unconditionally -- no keyword argument, flag, or
      environment variable re-enables execution of a disallowed executable
      -- and returns
        {"executed": False, "disposition": "UNCERTAIN",
         "reason": "<text containing 'could not be checked'>"}.

  lint_plan(plan_root: pathlib.Path, execute: bool = True) -> list[dict]
      Walks plan_root, extracts every command from task files' Verification
      Commands Before/After blocks and from EI exit criteria, and returns
      one dict per finding:
        {"check": int (1-7) or None, "severity": "ERROR" | "WARNING" | "UNCERTAIN",
         "file": str, "message": str}
      Checks 2-6 are static analysis over extracted command text and fire
      identically whether execute is True or False. Checks 1 and 7 require
      running the command; a gate whose executable the allowlist refuses is
      reported as its own UNCERTAIN finding ("could not be checked"),
      never silently treated as passing and never omitted.

Fixture corpus this suite asserts against: `tests/fixtures/verification_gates/`
(13 self-contained miniature plan trees + README.md, the authoritative
fixture -> check -> expected-finding -> severity map).

Run with:  python -m pytest tests/test_lint_verification_gates.py -q
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

# This import is expected to fail until the module lands (Sprint-02 Tasks
# 03-04). A ModuleNotFoundError here is the tests-first proof this task
# exists to produce -- do not add a stub to silence it.
from lint_verification_gates import (  # noqa: E402
    ALLOWED_EXECUTABLES,
    _count_line_and_occurrence_totals,
    extract_commands,
    lint_plan,
    run_command,
)

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "verification_gates"


def _lint_fixture(name, execute=True):
    """Run lint_plan against one named fixture directory under FIXTURES_ROOT."""
    return lint_plan(FIXTURES_ROOT / name, execute=execute)


def _checks_present(findings):
    return sorted(f["check"] for f in findings if f["check"] is not None)


def _severities_for_check(findings, check):
    return sorted(f["severity"] for f in findings if f["check"] == check)


def _hash_tree(root):
    """A stable content hash over every file under root, path included, so a
    single byte moving anywhere in the tree changes the digest."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


class TestPerCheckShapes(unittest.TestCase):
    """One fixture per check (README.md Group A), each tuned so exactly one
    check fires. Every test asserts both that a finding was produced AND
    that its severity is correct -- asserting only "a finding appeared"
    would pass a linter that classified every defect as INFO."""

    def test_check1_vacuous_after_gate_is_error(self):
        findings = _lint_fixture("shape_01_vacuous_after_gate")
        self.assertEqual(_checks_present(findings), [1])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "ERROR")

    def test_check2_missing_pre_edit_baseline_is_warning(self):
        findings = _lint_fixture("shape_02_missing_pre_edit_baseline")
        self.assertEqual(_checks_present(findings), [2])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "WARNING")

    def test_check3_bre_ere_mismatch_is_error(self):
        # Two gates fire: the classic no -E case and the absorbed variant
        # (grep -c counts lines, not matches).
        findings = _lint_fixture("shape_03_bre_ere_mismatch")
        self.assertEqual(_checks_present(findings), [3, 3])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 3), ["ERROR", "ERROR"])

    def test_check4_self_matching_sweep_is_error(self):
        findings = _lint_fixture("shape_04_self_matching_sweep")
        self.assertEqual(_checks_present(findings), [4])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "ERROR")

    def test_check5_stale_ownership_is_error(self):
        findings = _lint_fixture("shape_05_stale_ownership")
        self.assertEqual(_checks_present(findings), [5])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "ERROR")

    def test_check6_substring_own_vocabulary_is_warning(self):
        findings = _lint_fixture("shape_06_substring_own_vocabulary")
        self.assertEqual(_checks_present(findings), [6])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "WARNING")

    def test_check7_contradicted_before_baseline_is_error(self):
        # Two Before-block baselines disagree with the live tree.
        findings = _lint_fixture("shape_07_contradicted_before_baseline")
        self.assertEqual(_checks_present(findings), [7, 7])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 7), ["ERROR", "ERROR"])


class TestInvariantExemption(unittest.TestCase):
    """The corpus's false-positive guard (README.md Group B). Six of the
    seven check tests above would still pass a linter that flags every
    verification gate unconditionally -- this is the one that would not.
    Do not weaken this to "few findings"; it must be exactly zero."""

    def test_invariant_preservation_fixture_produces_zero_findings(self):
        findings = _lint_fixture("invariant_preservation")
        self.assertEqual(findings, [])


class TestRegressionFixtures(unittest.TestCase):
    """Five real gates quoted in the originating backlog item (README.md
    Group C). Every regression_R* fixture reproduces its command verbatim,
    so each also carries a Check-2 co-finding by construction -- none of
    the real gates carried a pre-edit annotation, and adding one to silence
    Check 2 would break the verbatim reproduction."""

    def test_regression_r1_count_gate_two_flags_check1_and_check2(self):
        findings = _lint_fixture("regression_R1_count_gate_two")
        self.assertEqual(_checks_present(findings), [1, 2])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 1), ["ERROR"])
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])

    def test_regression_r2_count_gate_eleven_flags_check1_and_check2(self):
        findings = _lint_fixture("regression_R2_count_gate_eleven")
        self.assertEqual(_checks_present(findings), [1, 2])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 1), ["ERROR"])
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])

    def test_regression_r3_count_gate_four_flags_check1_and_check2(self):
        findings = _lint_fixture("regression_R3_count_gate_four")
        self.assertEqual(_checks_present(findings), [1, 2])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 1), ["ERROR"])
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])

    def test_regression_r4_bre_returns_zero_flags_checks_1_2_and_3(self):
        # The one fixture carrying three findings: BRE-broken (Check 3),
        # also vacuous against `expect 0` (Check 1), and unannotated
        # (Check 2) -- all three are real properties of the recorded
        # instance, not test-authoring accidents.
        findings = _lint_fixture("regression_R4_bre_returns_zero")
        self.assertEqual(_checks_present(findings), [1, 2, 3])
        self.assertEqual(len(findings), 3)
        self.assertEqual(_severities_for_check(findings, 1), ["ERROR"])
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])
        self.assertEqual(_severities_for_check(findings, 3), ["ERROR"])

    def test_regression_r5_self_matching_sweep_flags_check4_and_check2(self):
        findings = _lint_fixture("regression_R5_self_matching_sweep")
        self.assertEqual(_checks_present(findings), [2, 4])
        self.assertEqual(len(findings), 2)
        self.assertEqual(_severities_for_check(findings, 4), ["ERROR"])
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])


class TestAllowlistRefusal(unittest.TestCase):
    """The plan's only Critical-rated risk (EI Sec.5): the linter reads
    commands out of arbitrary markdown and runs them. Refusal is tested
    first, before any check logic, per Sec.5's own ordering, and the suite
    asserts there is no bypass: no flag, no debug mode, no environment
    variable re-enables execution."""

    def test_allowlist_is_exactly_the_four_named_executables(self):
        self.assertEqual(set(ALLOWED_EXECUTABLES), {"grep", "wc", "ls", "test"})

    def test_allowlisted_executable_is_executed(self):
        result = run_command(["wc", "-l", str(FIXTURES_ROOT / "README.md")])
        self.assertTrue(result["executed"])
        self.assertEqual(result["returncode"], 0)

    def test_disallowed_executable_is_refused_not_executed(self):
        result = run_command(["curl", "-s", "http://example.invalid"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["disposition"], "UNCERTAIN")

    def test_python_is_not_on_the_allowlist(self):
        # Nothing outside grep/wc/ls/test -- not even the interpreter
        # running the linter itself.
        self.assertNotIn("python", ALLOWED_EXECUTABLES)
        result = run_command(["python", "-c", "print(1)"])
        self.assertFalse(result["executed"])

    def test_no_keyword_flag_bypasses_the_allowlist(self):
        for bypass_kwarg in ("force", "unsafe", "allow_all", "debug", "override", "bypass_allowlist"):
            with self.assertRaises(TypeError):
                run_command(["curl", "-s", "http://example.invalid"], **{bypass_kwarg: True})

    def test_no_env_var_bypasses_the_allowlist(self):
        plausible_bypass_vars = {
            "LINT_ALLOW_EXEC": "1",
            "LINT_VERIFICATION_GATES_UNSAFE": "1",
            "ALLOW_UNSAFE_EXEC": "1",
            "VGL_DEBUG": "1",
        }
        with patch.dict(os.environ, plausible_bypass_vars):
            result = run_command(["curl", "-s", "http://example.invalid"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["disposition"], "UNCERTAIN")

    def test_plan_level_gate_with_disallowed_executable_is_reported_unrunnable(self):
        # A synthetic mini-plan built in a temp dir -- not part of the
        # checked-in corpus, which Task 01 owns -- exercising a gate whose
        # executable the allowlist refuses.
        with tempfile.TemporaryDirectory() as tmp:
            plan_root = Path(tmp)
            (plan_root / "TASK-01-Unrunnable.md").write_text(
                "# Task: Unrunnable\n\n"
                "## Verification Commands\n\n"
                "> [!verify] Before / After Commands\n"
                "> **Before:** *(runner)*\n"
                "> ```bash\n"
                "> curl -s http://example.invalid/data.json\n"
                "> ```\n"
                "> **After:** *(runner)*\n"
                "> ```bash\n"
                "> curl -s http://example.invalid/data.json   # expect 1\n"
                "> # pre-edit: 0 -> expect 1\n"
                "> ```\n",
                encoding="utf-8",
            )
            findings = lint_plan(plan_root)
        self.assertTrue(any(f["severity"] == "UNCERTAIN" for f in findings))
        self.assertTrue(any("could not be checked" in f.get("message", "") for f in findings))


class TestReadOnlyBehavior(unittest.TestCase):
    """Every allowlisted executable is read-only by nature (EI Sec.5) -- a
    full lint run over the whole corpus must not leave a single byte
    changed anywhere in the fixture tree."""

    def test_full_corpus_lint_leaves_tree_byte_identical(self):
        before = _hash_tree(FIXTURES_ROOT)
        for fixture_dir in sorted(p for p in FIXTURES_ROOT.iterdir() if p.is_dir()):
            lint_plan(fixture_dir)
        after = _hash_tree(FIXTURES_ROOT)
        self.assertEqual(before, after)


class TestExecutorDisabled(unittest.TestCase):
    """Checks 1 and 7 need real execution; Checks 2-6 are static analysis
    over extracted command text and must work with the executor turned off
    (EI Sec.3: "the five static checks must work with the executor
    disabled"). Check1's and Check7's own shape fixtures are deliberately
    excluded here -- they cannot fire with execute=False."""

    def test_check2_fires_with_executor_disabled(self):
        findings = _lint_fixture("shape_02_missing_pre_edit_baseline", execute=False)
        self.assertIn(2, _checks_present(findings))
        self.assertEqual(_severities_for_check(findings, 2), ["WARNING"])

    def test_check3_fires_with_executor_disabled(self):
        findings = _lint_fixture("shape_03_bre_ere_mismatch", execute=False)
        self.assertEqual(_checks_present(findings), [3, 3])
        self.assertEqual(_severities_for_check(findings, 3), ["ERROR", "ERROR"])

    def test_check4_fires_with_executor_disabled(self):
        findings = _lint_fixture("shape_04_self_matching_sweep", execute=False)
        self.assertIn(4, _checks_present(findings))
        self.assertEqual(_severities_for_check(findings, 4), ["ERROR"])

    def test_check5_fires_with_executor_disabled(self):
        findings = _lint_fixture("shape_05_stale_ownership", execute=False)
        self.assertIn(5, _checks_present(findings))
        self.assertEqual(_severities_for_check(findings, 5), ["ERROR"])

    def test_check6_fires_with_executor_disabled(self):
        findings = _lint_fixture("shape_06_substring_own_vocabulary", execute=False)
        self.assertIn(6, _checks_present(findings))
        self.assertEqual(_severities_for_check(findings, 6), ["WARNING"])


class TestRefusedCommandIsUncertainNeverPass(unittest.TestCase):
    """A check that could not be run returns UNCERTAIN, never PASS (EI
    Sec.5's closing line) -- a refused command is reported as unrunnable,
    never as a silent pass."""

    def test_refused_command_disposition_is_uncertain_not_pass(self):
        result = run_command(["rm", "-rf", "/tmp/should-never-run"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["disposition"], "UNCERTAIN")
        self.assertNotEqual(result["disposition"], "PASS")

    def test_refused_command_message_states_it_could_not_be_checked(self):
        result = run_command(["rm", "-rf", "/tmp/should-never-run"])
        self.assertIn("could not be checked", result["reason"])


class TestNestedSubheadingInsideSection(unittest.TestCase):
    """A markdown subheading nested inside an already-open ``## Verification
    Commands`` section (a natural ``### Gate N: ...`` label before the
    Before/After blockquote) must not null out the extractor's section
    state -- the section stays open through it, and every command after the
    subheading is still extracted."""

    def test_subheading_before_blockquote_does_not_drop_the_after_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_root = Path(tmp)
            (plan_root / "target.md").write_text("X\n", encoding="utf-8")
            (plan_root / "TASK-01-NestedHeading.md").write_text(
                "# Task: NestedHeading\n\n"
                "## Verification Commands\n\n"
                "### Gate 1: line count\n\n"
                "> [!verify] Before / After Commands\n"
                "> **Before:** *(runner)*\n"
                "> ```bash\n"
                "> wc -l target.md\n"
                "> ```\n"
                "> **After:** *(runner)*\n"
                "> ```bash\n"
                "> grep -c 'X' target.md   # expect >=1\n"
                "> # pre-edit: 1 → expect >=1\n"
                "> ```\n",
                encoding="utf-8",
            )
            commands = extract_commands(plan_root)
            findings = lint_plan(plan_root)
        self.assertEqual(len(commands), 2)
        self.assertIn(1, _checks_present(findings))


class TestPlaceholderInsideQuotedSpan(unittest.TestCase):
    """A template placeholder living inside a quoted grep pattern -- the
    normal place for one to live -- must still be recognised as a
    placeholder, and a gate built from it must not be linted as a real
    gate."""

    def test_placeholder_inside_single_quoted_pattern_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_root = Path(tmp)
            (plan_root / "target.md").write_text("nothing relevant here\n", encoding="utf-8")
            (plan_root / "TASK-01-QuotedPlaceholder.md").write_text(
                "# Task: QuotedPlaceholder\n\n"
                "## Verification Commands\n\n"
                "> [!verify] Before / After Commands\n"
                "> **Before:** *(runner)*\n"
                "> ```bash\n"
                "> wc -l target.md\n"
                "> ```\n"
                "> **After:** *(runner)*\n"
                "> ```bash\n"
                "> grep -c '{ABBREV}_S{NN}_BASE' target.md   # expect >=1\n"
                "> ```\n",
                encoding="utf-8",
            )
            commands = extract_commands(plan_root)
            findings = lint_plan(plan_root)
        after_gates = [c for c in commands if c.command.startswith("grep")]
        self.assertEqual(len(after_gates), 1)
        self.assertTrue(after_gates[0].is_placeholder)
        self.assertEqual(findings, [])


class TestCountLineAndOccurrenceTotalsRegex(unittest.TestCase):
    """`_count_line_and_occurrence_totals` must evaluate a grep pattern as
    the regex grep actually runs, not as a literal substring -- a pattern
    carrying an escaped metacharacter (an escaped literal dot, the normal
    way to match a `.` in a file name) is exactly the case a literal search
    gets wrong."""

    def test_escaped_dot_pattern_matches_as_a_literal_dot_not_a_raw_backslash(self):
        result = _count_line_and_occurrence_totals(
            r"task-file\.md", "See task-file.md and other-file.md here."
        )
        self.assertEqual(result, (1, 1))

    def test_escaped_dot_pattern_counts_lines_and_occurrences_across_two_lines(self):
        text = (
            "task-file.md is named on this line.\n"
            "no match on this line.\n"
            "task-file.md is named again on this line.\n"
        )
        result = _count_line_and_occurrence_totals(r"task-file\.md", text)
        self.assertEqual(result, (2, 2))


class TestCheck3AbsorptionFiresOnEscapedMetacharacterPattern(unittest.TestCase):
    """Check 3's absorption sub-check must fire on a grep pattern using an
    escaped metacharacter, which the old literal-substring implementation
    could never match at all -- silently suppressing the finding."""

    def test_absorption_branch_fires_error_on_escaped_dot_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_root = Path(tmp)
            (plan_root / "counts.md").write_text(
                "foo.bar and foo.bar together.\n"
                "just foo.bar alone here.\n"
                "nothing on this line.\n",
                encoding="utf-8",
            )
            (plan_root / "TASK-01-EscapedMetacharAbsorption.md").write_text(
                "# Task: EscapedMetacharAbsorption\n\n"
                "## Verification Commands\n\n"
                "> [!verify] Before / After Commands\n"
                "> **Before:** *(runner)*\n"
                "> ```bash\n"
                "> wc -l counts.md\n"
                "> ```\n"
                "> **After:** *(runner)*\n"
                "> ```bash\n"
                "> grep -c 'foo\\.bar' counts.md   # expect 3\n"
                "> # pre-edit: 0 → expect 3\n"
                "> ```\n",
                encoding="utf-8",
            )
            findings = lint_plan(plan_root, execute=False)
        self.assertEqual(_checks_present(findings), [3])
        self.assertEqual(_severities_for_check(findings, 3), ["ERROR"])


if __name__ == "__main__":
    unittest.main()
