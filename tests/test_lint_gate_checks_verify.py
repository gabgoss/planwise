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


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in verify_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in verify_module.CHECKS]
        self.assertEqual(names, ["check30", "check31", "check32", "check33"])

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


if __name__ == "__main__":
    unittest.main()
