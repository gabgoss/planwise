"""Tests for the gate-command lint checks in ``lint_gate_checks_commands``.

Each check gets one known-bad fixture that must produce exactly one finding
naming it, and one positive fixture that must produce none for it. Every bad
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

import lint_gate_checks_commands as commands_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan


def _write_task(plan_root, fence_lines, extra="", name="TASK-01-Fixture.md", newline="\n"):
    """Write one task file whose After block holds ``fence_lines``."""
    body = "".join(f"> {line}\n" for line in fence_lines)
    text = (
        "# Task: Fixture\n\n"
        + extra
        + "## Verification Commands\n\n"
        "> [!verify] Before / After Commands\n"
        "> **After:** *(runner)*\n"
        "> ```bash\n" + body + "> ```\n"
    )
    with open(Path(plan_root) / name, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", newline))


def _findings_for(plan_root, check, execute=False):
    return [f for f in lint_plan(Path(plan_root), execute=execute) if f["check"] == check]


def _lint_lines(check, fence_lines, extra="", execute=False, newline="\n"):
    with tempfile.TemporaryDirectory() as tmp:
        _write_task(tmp, fence_lines, extra=extra, newline=newline)
        return _findings_for(tmp, check, execute=execute)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class TestCheck18DiffPropertyOverUntrackedPath(unittest.TestCase):
    GATE = "git diff -- {path} | grep -c '^+'   # expect 3"

    def _lint_repo(self, path, lines_before=()):
        with tempfile.TemporaryDirectory() as tmp:
            _git(tmp, "init", "-q")
            (Path(tmp) / "tracked.txt").write_text("one\n", encoding="utf-8")
            (Path(tmp) / "fresh.txt").write_text("one\n", encoding="utf-8")
            _git(tmp, "add", "tracked.txt")
            _write_task(tmp, [*lines_before, self.GATE.format(path=path)])
            return _findings_for(tmp, 18, execute=True)

    def test_bad_untracked_path_is_error(self):
        findings = self._lint_repo("fresh.txt")
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "ERROR")])

    def test_good_tracked_path_is_silent(self):
        self.assertEqual(self._lint_repo("tracked.txt"), [])

    def test_good_path_registered_by_an_earlier_add_is_silent(self):
        self.assertEqual(self._lint_repo("fresh.txt", ["git add -N fresh.txt"]), [])

    def test_git_exit_128_outside_a_repository_is_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "fresh.txt").write_text("one\n", encoding="utf-8")
            _write_task(tmp, [self.GATE.format(path="fresh.txt")])
            findings = _findings_for(tmp, 18, execute=True)
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "UNCERTAIN")])

    def test_tracked_file_outside_the_plan_folder_resolves_through_a_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git(tmp, "init", "-q")
            (Path(tmp) / "outer.txt").write_text("one\n", encoding="utf-8")
            _git(tmp, "add", "outer.txt")
            plan = Path(tmp) / "plan"
            plan.mkdir()
            _write_task(plan, [self.GATE.format(path="outer.txt")])
            findings = _findings_for(plan, 18, execute=True)
        self.assertEqual(findings, [])

    def test_untracked_file_outside_the_plan_folder_is_still_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _git(tmp, "init", "-q")
            (Path(tmp) / "outer.txt").write_text("one\n", encoding="utf-8")
            plan = Path(tmp) / "plan"
            plan.mkdir()
            _write_task(plan, [self.GATE.format(path="outer.txt")])
            findings = _findings_for(plan, 18, execute=True)
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "ERROR")])

    def test_uncheckable_pathspec_tokens_give_no_finding(self):
        # An empty index, so an exclude-only pathspec matches nothing and git
        # would report it untracked if the check asked.
        for token in ("$FILES", "{path}", ":(exclude)x"):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as tmp:
                _git(tmp, "init", "-q")
                _write_task(tmp, [self.GATE.format(path=token)])
                self.assertEqual(_findings_for(tmp, 18, execute=True), [])

    def test_execution_off_reports_uncertain(self):
        findings = _lint_lines(18, [self.GATE.format(path="fresh.txt")])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "UNCERTAIN")])


class TestCheck19IntentToAddBeforeCommentOnlyAssertion(unittest.TestCase):
    def test_bad_add_n_then_comment_only_count(self):
        findings = _lint_lines(19, [
            "git add -N hook.ps1",
            "git diff -- hook.ps1 | grep -E '^\\+[^+]' | grep -vcE '^\\+\\s*#'   # expect 0",
        ])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(19, "ERROR")])

    def test_good_add_n_then_pattern_presence(self):
        findings = _lint_lines(19, [
            "git add -N hook.ps1",
            "git diff -- hook.ps1 | grep -E 'LEAK-[0-9]'   # expect empty",
        ])
        self.assertEqual(findings, [])


class TestCheck20CountGrepChainedWithAnd(unittest.TestCase):
    def test_bad_grep_count_then_and(self):
        findings = _lint_lines(20, ["grep -c 'TODO' notes.md && grep -c 'FIXME' notes.md   # expect 0"])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(20, "WARNING")])

    def test_good_two_separate_commands(self):
        findings = _lint_lines(20, [
            "grep -c 'TODO' notes.md   # expect 0",
            "grep -c 'FIXME' notes.md   # expect 0",
        ])
        self.assertEqual(findings, [])


class TestCheck21DiffGateNotBaselinePinned(unittest.TestCase):
    def test_bad_unpinned_output_filter(self):
        findings = _lint_lines(21, ["git diff --name-only | grep 'scripts/'   # expect empty"])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(21, "ERROR")])
        self.assertIn("output filter", findings[0]["message"])

    def test_bad_head_operand(self):
        findings = _lint_lines(21, ["git diff HEAD -- scripts/   # expect empty"])
        self.assertEqual(len(findings), 1)
        self.assertIn("HEAD", findings[0]["message"])

    def test_bad_success_criteria_span(self):
        extra = "## Success Criteria\n\n- [ ] `git diff --name-only | wc -l` prints 2\n\n"
        findings = _lint_lines(21, ["wc -l notes.md   # expect 3"], extra=extra)
        self.assertEqual([(f["check"], f["line"]) for f in findings], [(21, 5)])

    def test_good_pinned_and_path_scoped(self):
        findings = _lint_lines(21, [
            "git diff --name-only $ABC_S01_BASE -- scripts/ | grep -vE '^scripts/ok/'   # expect empty",
        ])
        self.assertEqual(findings, [])


class TestCheck22PathListReadBeforeCounted(unittest.TestCase):
    READER = "xargs -a paths.txt git status --porcelain --   # expect empty"

    def test_bad_list_read_with_no_count(self):
        findings = _lint_lines(22, [self.READER])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(22, "WARNING")])

    def test_good_list_counted_first(self):
        findings = _lint_lines(22, [
            "xargs -a paths.txt git diff --numstat -- | wc -l   # expect 3",
            self.READER,
        ])
        self.assertEqual(findings, [])


class TestCheck23KeywordCountCoverageDenominator(unittest.TestCase):
    def test_bad_keyword_count_compared_as_total(self):
        findings = _lint_lines(23, [
            "total=$(grep -c 'dispatch' plan.md)",
            "[ \"$tagged\" -ge \"$total\" ]   # expect true",
        ])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(23, "ERROR")])

    def test_bad_keyword_count_beside_proximity_pipeline(self):
        findings = _lint_lines(23, [
            "grep -B1 'dispatch' plan.md | grep -c 'model:'   # expect 4",
            "grep -c 'dispatch' plan.md   # expect 4",
        ])
        self.assertEqual(len(findings), 1)

    def test_good_keyword_count_alone(self):
        findings = _lint_lines(23, ["grep -c 'dispatch' plan.md   # expect 4, a count, not a coverage ratio"])
        self.assertEqual(findings, [])


class TestCheck24BasicGrepEscapedPlusHeaderFilter(unittest.TestCase):
    PREFIX = "git diff $ABC_S01_BASE -- x.py | grep '^+' | "

    def test_bad_basic_escaped_plus_header_filter(self):
        findings = _lint_lines(24, [self.PREFIX + "grep -v '^\\+\\+\\+'   # expect 2"])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(24, "WARNING")])

    def test_good_extended_header_filter(self):
        findings = _lint_lines(24, [self.PREFIX + "grep -Ev '^\\+\\+\\+'   # expect 2"])
        self.assertEqual(findings, [])


class TestCheck25ToleranceWordWithoutBand(unittest.TestCase):
    BAD = "The verifier passes a count that is approximately right.\n\n"
    GOOD = "Counts within tolerance (±2 of 40) pass.\n\n"

    def test_bad_tolerance_word_without_band(self):
        findings = _lint_lines(25, ["wc -l notes.md   # expect 3"], extra=self.BAD)
        self.assertEqual([(f["check"], f["severity"], f["line"]) for f in findings], [(25, "WARNING", 3)])

    def test_bad_on_a_crlf_file(self):
        findings = _lint_lines(25, ["wc -l notes.md   # expect 3"], extra=self.BAD, newline="\r\n")
        self.assertEqual(len(findings), 1)

    def test_good_tolerance_with_band(self):
        findings = _lint_lines(25, ["wc -l notes.md   # expect 3"], extra=self.GOOD)
        self.assertEqual(findings, [])

    def test_good_quoted_mention(self):
        extra = 'Flag a spec that says "approximate" with no band.\n\n'
        self.assertEqual(_lint_lines(25, ["wc -l notes.md   # expect 3"], extra=extra), [])


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in commands_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_severity_constants_match_the_linter(self):
        self.assertEqual(commands_module.SEVERITY_ERROR, lint_module.SEVERITY_ERROR)
        self.assertEqual(commands_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)
        self.assertEqual(commands_module.SEVERITY_UNCERTAIN, lint_module.SEVERITY_UNCERTAIN)

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "ERROR", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(commands_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_commands.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_a_new_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_task(tmp, ["grep -c 'TODO' notes.md && grep -c 'FIXME' notes.md   # expect 0"])
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn("[WARNING] Check 20:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
