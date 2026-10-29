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
from unittest import mock

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


class TestCheck18RepositoryDirectoryScope(unittest.TestCase):
    """A ``-C`` directory is asked about only when it lies inside the work tree
    of a repository that holds the plan root."""

    GATE = "git -C {repo} diff --numstat -- f.txt   # expect 1"

    @staticmethod
    def _ls_files_calls(run, repo):
        # Filter on the ls-files query that only Check 18 makes, so a
        # subprocess call from any other part of the linter cannot decide this.
        calls = []
        for call in run.call_args_list:
            argv = list(call.args[0]) if call.args else []
            if (
                "ls-files" in argv and "-C" in argv
                and Path(argv[argv.index("-C") + 1]).resolve() == repo.resolve()
            ):
                calls.append(argv)
        return calls

    def test_directory_outside_the_plan_repositories_is_uncertain_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer, elsewhere = Path(tmp) / "outer", Path(tmp) / "elsewhere"
            plan = outer / "plan"
            plan.mkdir(parents=True)
            elsewhere.mkdir()
            _git(outer, "init", "-q")
            _git(elsewhere, "init", "-q")
            (elsewhere / "f.txt").write_text("one\n", encoding="utf-8")
            _write_task(plan, [self.GATE.format(repo=elsewhere.as_posix())])
            with mock.patch("subprocess.run", wraps=subprocess.run) as run:
                findings = _findings_for(plan, 18, execute=True)
            self.assertEqual(self._ls_files_calls(run, elsewhere), [])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "UNCERTAIN")])
        self.assertIn("does not resolve inside the plan's repositories", findings[0]["message"])

    def test_nested_repository_inside_the_plan_repository_is_still_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "outer"
            plan, nested = outer / "plan", outer / "nested"
            plan.mkdir(parents=True)
            nested.mkdir()
            _git(outer, "init", "-q")
            _git(nested, "init", "-q")
            (nested / "f.txt").write_text("one\n", encoding="utf-8")
            _write_task(plan, [self.GATE.format(repo="nested")])
            findings = _findings_for(plan, 18, execute=True)
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(18, "ERROR")])

    def test_parent_relative_escape_is_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer, elsewhere = Path(tmp) / "outer", Path(tmp) / "elsewhere"
            plan = outer / "plan"
            plan.mkdir(parents=True)
            elsewhere.mkdir()
            _git(outer, "init", "-q")
            _git(elsewhere, "init", "-q")
            _write_task(plan, [self.GATE.format(repo="../../elsewhere")])
            findings = _findings_for(plan, 18, execute=True)
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

    def test_bad_operator_glued_to_the_words(self):
        findings = _lint_lines(20, ["grep -c TODO notes.md&&grep -c FIXME notes.md   # expect 0"])
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(20, "WARNING")])

    def test_good_quoted_and_operator_is_a_pattern(self):
        findings = _lint_lines(20, ["grep -c '&&' notes.md   # expect 0"])
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


class TestTokensAndPipelines(unittest.TestCase):
    """The shared splitter behind Checks 18-24: an operator glued to a word is
    split out, and a quoted operator stays a plain word."""

    def _pipelines(self, text):
        return commands_module._pipelines(commands_module._tokens(text))

    def test_glued_operators_split(self):
        cases = {
            "a;b": [[["a"]], [["b"]]],
            "x&&y": [[["x"]], [["y"]]],
            "git diff -- p | wc -l; echo x": [[["git", "diff", "--", "p"], ["wc", "-l"]], [["echo", "x"]]],
            "a ; b": [[["a"]], [["b"]]],
            "x && y": [[["x"]], [["y"]]],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._pipelines(text), expected)

    def test_quoted_operators_stay_in_their_stage(self):
        cases = {
            "grep -c '&&' f": [[["grep", "-c", "&&", "f"]]],
            "grep -c ';' f": [[["grep", "-c", ";", "f"]]],
            'grep -c "a|b" f': [[["grep", "-c", "a|b", "f"]]],
            "grep -c \\; f": [[["grep", "-c", ";", "f"]]],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self._pipelines(text), expected)

    def test_redirections_keep_their_existing_tokens(self):
        cases = {
            "cmd 2>&1 | wc -l": ["cmd", "2>&1", "|", "wc", "-l"],
            "cmd &>out.txt": ["cmd", "&>out.txt"],
            "cmd >| out.txt": ["cmd", ">|", "out.txt"],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(commands_module._tokens(text), expected)

    def test_pipe_with_stderr_splits_a_stage(self):
        self.assertEqual(self._pipelines("a |& b"), [[["a"], ["b"]]])

    def test_unterminated_quote_does_not_tokenise(self):
        self.assertIsNone(commands_module._tokens("grep -c 'x f"))


class TestIsTaskFile(unittest.TestCase):
    """The first real heading decides, so a ``# note`` inside frontmatter or a
    fenced block before it is not read as the heading."""

    def _is_task(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task.md"
            path.write_text(text, encoding="utf-8")
            return commands_module._is_task_file(path)

    def test_plain_task_heading(self):
        self.assertTrue(self._is_task("# Task: Foo\n\nbody\n"))

    def test_frontmatter_comment_before_the_heading(self):
        self.assertTrue(self._is_task("---\n# note about the file\nagent: Sonnet\n---\n# Task: Foo\n"))

    def test_fenced_comment_before_the_heading(self):
        self.assertTrue(self._is_task("```bash\n# note\n```\n# Task: Foo\n"))

    def test_fence_closed_only_by_its_own_marker(self):
        self.assertTrue(self._is_task("````\n```\n# note\n````\n# Task: Foo\n"))

    def test_other_first_heading_is_not_a_task(self):
        self.assertFalse(self._is_task("---\nid: 1\n---\n# Signoff\n\n# Task: Foo\n"))


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
