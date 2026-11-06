"""Tests for the in-process decision of a native Grep tool-call gate.

Covers ``parse_grep_call``, ``run_grep_call`` and ``measured_value`` directly,
and the linter end to end for a plan whose only gates are ``Grep`` lines. Every
tree is built under a temporary directory outside the shipped plugin tree.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_gate_grep_tool as grep_tool
from lint_gate_git_policy import git_refusal
from lint_gate_grep_tool import measured_value, parse_grep_call, run_grep_call
from lint_verification_gates import (
    ExtractedCommand,
    _lint,
    coverage_line,
    execute_command,
    lint_plan,
    resolve_argv,
)

GIT = shutil.which("git")

SAMPLE = "alpha one\nbeta two\ngamma alpha alpha\ndelta\nalpha beta\ngamma\n"


def _argv(*parts):
    return ["Grep", *parts]


def _params(*parts):
    params, refusal = parse_grep_call(_argv(*parts))
    assert params is not None, refusal
    return params


class TestParse(unittest.TestCase):
    def test_minimal_call_takes_the_defaults(self):
        params = _params("pattern=alpha")
        self.assertEqual(params["output_mode"], "files_with_matches")
        self.assertIsNone(params["path"])
        self.assertIsNone(params["glob"])
        self.assertTrue(params["line_numbers"])
        self.assertFalse(params["ignore_case"])
        self.assertFalse(params["multiline"])

    def test_every_accepted_parameter_is_read(self):
        params = _params(
            "pattern=alpha", "path=src", "output_mode=content", "glob=*.md",
            "-i=true", "-n=false", "multiline=true",
        )
        self.assertEqual(params["path"], "src")
        self.assertEqual(params["output_mode"], "content")
        self.assertEqual(params["glob"], "*.md")
        self.assertTrue(params["ignore_case"])
        self.assertFalse(params["line_numbers"])
        self.assertTrue(params["multiline"])

    def test_an_unknown_parameter_is_refused_by_name(self):
        for name in ("type", "head_limit", "-A", "-B", "-C", "context", "offset"):
            with self.subTest(name=name):
                params, refusal = parse_grep_call(_argv("pattern=x", f"{name}=1"))
                self.assertIsNone(params)
                self.assertIn(repr(name), refusal)

    def test_an_argument_not_written_name_equals_value_is_refused(self):
        params, refusal = parse_grep_call(_argv("pattern=x", "src"))
        self.assertIsNone(params)
        self.assertIn("name=value", refusal)

    def test_a_repeated_parameter_is_refused(self):
        params, refusal = parse_grep_call(_argv("pattern=x", "pattern=y"))
        self.assertIsNone(params)
        self.assertIn("twice", refusal)

    def test_a_missing_pattern_is_refused(self):
        for parts in ((), ("pattern=",), ("path=src",)):
            with self.subTest(parts=parts):
                params, refusal = parse_grep_call(_argv(*parts))
                self.assertIsNone(params)
                self.assertIn("no pattern", refusal)

    def test_a_bad_output_mode_or_boolean_is_refused(self):
        self.assertIsNone(parse_grep_call(_argv("pattern=x", "output_mode=lines"))[0])
        self.assertIsNone(parse_grep_call(_argv("pattern=x", "-i=yes"))[0])

    def test_a_call_that_is_not_grep_is_refused(self):
        self.assertIsNone(parse_grep_call(["grep", "pattern=x"])[0])
        self.assertIsNone(parse_grep_call([])[0])

    def test_an_uncompilable_pattern_is_refused_as_ripgrep_only_syntax(self):
        for pattern in ("(", "[a-", "*abc", "[[:alpha:]]", r"\p{L}", "(?<name>x)"):
            with self.subTest(pattern=pattern):
                params, refusal = parse_grep_call(_argv(f"pattern={pattern}"))
                self.assertIsNone(params)
                self.assertIn("ripgrep-only syntax", refusal)

    def test_a_construct_only_python_accepts_is_refused_too(self):
        cases = {
            "(?=x)": "lookaround",
            "(?!x)": "lookaround",
            "(?<=x)y": "lookaround",
            "(?<!x)y": "lookaround",
            "(?>x)": "atomic group",
            r"(a)\1": "backreference",
            "a++": "possessive",
            "a*+": "possessive",
            "a?+": "possessive",
        }
        for pattern, word in cases.items():
            with self.subTest(pattern=pattern):
                params, refusal = parse_grep_call(_argv(f"pattern={pattern}"))
                self.assertIsNone(params)
                self.assertIn(word, refusal)

    def test_ordinary_ripgrep_patterns_are_accepted(self):
        for pattern in (r"foo\d+", "(?i)abc", "(?:a|b)+", r"\++", "a+?", "a??", r"[\]x]", r"\\n", "x{2,3}"):
            with self.subTest(pattern=pattern):
                params, refusal = parse_grep_call(_argv(f"pattern={pattern}"))
                self.assertIsNotNone(params, refusal)

    def test_a_newline_needs_multiline(self):
        for pattern in (r"a\nb", "a\nb"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(parse_grep_call(_argv(f"pattern={pattern}"))[0])
                self.assertIsNotNone(parse_grep_call(_argv(f"pattern={pattern}", "multiline=true"))[0])

    def test_a_glob_the_matcher_cannot_decide_is_refused(self):
        for glob in ("!*.md", "*.md *.txt", "src/", "*.{md", "[abc"):
            with self.subTest(glob=glob):
                params, refusal = parse_grep_call(_argv("pattern=x", f"glob={glob}"))
                self.assertIsNone(params)
                self.assertIn("glob", refusal)


class TestFileTarget(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.sample = self.root / "sample.txt"
        # Raw bytes: write_text would turn each LF into CRLF on Windows.
        self.sample.write_bytes(SAMPLE.encode("utf-8"))

    def _run(self, *parts, **kwargs):
        params = _params(*parts)
        result, refusal = run_grep_call(params, cwd=self.root, **kwargs)
        self.assertIsNone(refusal)
        return params, result

    def test_count_is_matching_lines_not_occurrences(self):
        params, result = self._run("pattern=alpha", "path=sample.txt", "output_mode=count")
        self.assertEqual(result["stdout"], f"{self.sample.as_posix()}:3\n")
        self.assertEqual(measured_value(params, result["stdout"]), 3)

    def test_files_with_matches_names_the_file(self):
        params, result = self._run("pattern=alpha", "path=sample.txt")
        self.assertEqual(result["stdout"], f"{self.sample.as_posix()}\n")
        self.assertEqual(measured_value(params, result["stdout"]), 1)

    def test_content_shows_line_numbers_without_a_path_prefix(self):
        params, result = self._run("pattern=alpha", "path=sample.txt", "output_mode=content")
        self.assertEqual(
            result["stdout"], "1:alpha one\n3:gamma alpha alpha\n5:alpha beta\n"
        )
        self.assertEqual(measured_value(params, result["stdout"]), 3)

    def test_content_without_line_numbers(self):
        _, result = self._run(
            "pattern=^beta", "path=sample.txt", "output_mode=content", "-n=false"
        )
        self.assertEqual(result["stdout"], "beta two\n")

    def test_no_match_is_a_measured_zero_in_every_mode(self):
        for mode in ("count", "content", "files_with_matches"):
            with self.subTest(mode=mode):
                params, result = self._run("pattern=zzz", "path=sample.txt", f"output_mode={mode}")
                self.assertTrue(result["executed"])
                self.assertEqual(result["stdout"], "")
                self.assertEqual(measured_value(params, result["stdout"]), 0)

    def test_case_sensitive_by_default_and_insensitive_on_request(self):
        params, result = self._run("pattern=ALPHA", "path=sample.txt", "output_mode=count")
        self.assertEqual(measured_value(params, result["stdout"]), 0)
        params, result = self._run("pattern=ALPHA", "path=sample.txt", "output_mode=count", "-i=true")
        self.assertEqual(measured_value(params, result["stdout"]), 3)

    def test_a_glob_does_not_filter_an_explicit_file(self):
        params, result = self._run(
            "pattern=alpha", "path=sample.txt", "output_mode=count", "glob=*.md"
        )
        self.assertEqual(measured_value(params, result["stdout"]), 3)

    def test_multiline_count_is_matches_and_content_shows_spanned_lines(self):
        params, result = self._run(
            r"pattern=alpha one\nbeta two", "path=sample.txt", "output_mode=count", "multiline=true"
        )
        self.assertEqual(measured_value(params, result["stdout"]), 1)
        _, result = self._run(
            r"pattern=alpha one\nbeta two", "path=sample.txt", "output_mode=content", "multiline=true"
        )
        self.assertEqual(result["stdout"], "1:alpha one\n2:beta two\n")

    def test_multiline_dot_matches_a_newline(self):
        params, result = self._run(
            "pattern=alpha one.*beta two", "path=sample.txt", "output_mode=count", "multiline=true"
        )
        self.assertEqual(measured_value(params, result["stdout"]), 1)

    def test_a_crlf_file_keeps_its_carriage_return_for_the_dollar_anchor(self):
        crlf = self.root / "crlf.txt"
        crlf.write_bytes(b"one\r\ntwo\r\n")
        params, result = self._run("pattern=one$", "path=crlf.txt", "output_mode=count")
        self.assertEqual(measured_value(params, result["stdout"]), 0)
        params, result = self._run(r"pattern=one\r?$", "path=crlf.txt", "output_mode=count")
        self.assertEqual(measured_value(params, result["stdout"]), 1)
        _, result = self._run("pattern=one", "path=crlf.txt", "output_mode=content")
        self.assertEqual(result["stdout"], "1:one\n")

    def test_a_binary_file_is_skipped(self):
        binary = self.root / "blob.bin"
        binary.write_bytes(b"alpha\x00alpha\n")
        params, result = self._run("pattern=alpha", "path=blob.bin", "output_mode=count")
        self.assertEqual(measured_value(params, result["stdout"]), 0)

    def test_a_missing_path_is_refused_not_measured_as_zero(self):
        result, refusal = run_grep_call(_params("pattern=x", "path=nope.txt"), cwd=self.root)
        self.assertIsNone(result)
        self.assertIn("does not exist", refusal)

    def test_an_absolute_path_is_searched(self):
        params, result = self._run(
            "pattern=alpha", f"path={self.sample.as_posix()}", "output_mode=count"
        )
        self.assertEqual(measured_value(params, result["stdout"]), 3)

    def test_a_search_past_its_deadline_is_refused(self):
        params = _params("pattern=alpha", "output_mode=count")
        result, refusal = run_grep_call(params, cwd=self.root, timeout=-1)
        self.assertIsNone(result)
        self.assertIn("did not finish", refusal)

    def test_stderr_states_how_many_files_were_searched(self):
        _, result = self._run("pattern=alpha", "path=sample.txt", "output_mode=count")
        self.assertIn("searched 1 files", result["stderr"])


class TestDirectoryOutsideGit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "tree"
        (self.root / "sub" / ".hidden").mkdir(parents=True)
        (self.root / "top.md").write_text("needle\n", encoding="utf-8")
        (self.root / "sub" / "deep.txt").write_text("needle\nneedle\n", encoding="utf-8")
        (self.root / "sub" / ".hidden" / "h.md").write_text("needle\n", encoding="utf-8")
        (self.root / "ignored.log").write_text("needle\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        if grep_tool._has_git_marker(self.root):
            self.skipTest("the temporary directory sits inside a git work tree")

    def _count(self, *parts):
        params = _params("pattern=needle", f"path={self.root.as_posix()}", "output_mode=count", *parts)
        result, refusal = run_grep_call(params)
        self.assertIsNone(refusal)
        return measured_value(params, result["stdout"]), result

    def test_every_file_is_walked_and_gitignore_is_not_consulted(self):
        total, result = self._count()
        self.assertEqual(total, 5)
        self.assertIn("searched 5 files", result["stderr"])

    def test_a_basename_glob_matches_at_any_depth(self):
        total, _ = self._count("glob=*.md")
        self.assertEqual(total, 2)

    def test_a_glob_with_a_slash_is_anchored_to_the_search_root(self):
        self.assertEqual(self._count("glob=sub/*.txt")[0], 2)
        self.assertEqual(self._count("glob=*.txt")[0], 2)
        self.assertEqual(self._count("glob=deep/*.txt")[0], 0)

    def test_recursive_and_brace_globs(self):
        self.assertEqual(self._count("glob=**/h.md")[0], 1)
        self.assertEqual(self._count("glob=*.{md,txt}")[0], 4)

    def test_directory_content_lines_carry_the_file_path(self):
        params = _params(
            "pattern=needle", f"path={self.root.as_posix()}/sub", "output_mode=content", "glob=deep.txt"
        )
        result, _ = run_grep_call(params)
        deep = (self.root / "sub" / "deep.txt").as_posix()
        self.assertEqual(result["stdout"], f"{deep}:1:needle\n{deep}:2:needle\n")


@unittest.skipUnless(GIT, "git is not installed")
class TestDirectoryInsideGit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run([GIT, "-C", str(self.repo), "init", "-q"], check=True, capture_output=True)
        (self.repo / ".gitignore").write_text("ignored/\n.ruff_cache/\n", encoding="utf-8")
        (self.repo / "tracked.md").write_text("needle\n", encoding="utf-8")
        (self.repo / ".claude" / "rules").mkdir(parents=True)
        (self.repo / ".claude" / "rules" / "hidden.md").write_text("needle\n", encoding="utf-8")
        (self.repo / "ignored").mkdir()
        (self.repo / "ignored" / "x.txt").write_text("needle\n", encoding="utf-8")
        (self.repo / ".ruff_cache").mkdir()
        (self.repo / ".ruff_cache" / "c.txt").write_text("needle\n", encoding="utf-8")
        (self.repo / "pkg").mkdir()
        (self.repo / "pkg" / "inner.md").write_text("needle\n", encoding="utf-8")

    def _files(self, path):
        params = _params("pattern=needle", f"path={path.as_posix()}")
        result, refusal = run_grep_call(params)
        self.assertIsNone(refusal)
        return sorted(Path(line).relative_to(self.repo).as_posix() for line in result["stdout"].splitlines())

    def test_hidden_files_are_searched_and_ignored_files_are_not(self):
        self.assertEqual(
            self._files(self.repo),
            [".claude/rules/hidden.md", "pkg/inner.md", "tracked.md"],
        )

    def test_a_subdirectory_is_listed_from_its_own_root(self):
        self.assertEqual(self._files(self.repo / "pkg"), ["pkg/inner.md"])

    def test_an_ignored_directory_yields_nothing(self):
        params = _params("pattern=needle", f"path={(self.repo / '.ruff_cache').as_posix()}", "output_mode=count")
        result, refusal = run_grep_call(params)
        self.assertIsNone(refusal)
        self.assertEqual(measured_value(params, result["stdout"]), 0)
        self.assertIn("searched 0 files", result["stderr"])

    def test_a_file_deleted_from_disk_but_still_listed_is_not_counted(self):
        subprocess.run([GIT, "-C", str(self.repo), "add", "tracked.md"], check=True, capture_output=True)
        (self.repo / "tracked.md").unlink()
        self.assertNotIn("tracked.md", self._files(self.repo))

    def test_the_listing_commands_are_admitted_by_the_git_policy(self):
        self.assertIsNone(git_refusal(["git", "-C", "d", "ls-files", "-co", "--exclude-standard", "-z"]))
        self.assertIsNone(git_refusal(["git", "-C", "d", "rev-parse", "--is-inside-work-tree"]))

    def test_git_that_cannot_start_refuses_instead_of_walking_ignored_files(self):
        with patch.object(grep_tool.subprocess, "run", side_effect=OSError("no git")):
            result, refusal = run_grep_call(_params("pattern=needle", f"path={self.repo.as_posix()}"))
        self.assertIsNone(result)
        self.assertIn(".gitignore could not be honoured", refusal)

    def test_a_search_never_rewrites_the_index(self):
        subprocess.run([GIT, "-C", str(self.repo), "add", "tracked.md"], check=True, capture_output=True)
        before = (self.repo / ".git" / "index").read_bytes()
        self._files(self.repo)
        self.assertEqual((self.repo / ".git" / "index").read_bytes(), before)


class TestMeasuredValue(unittest.TestCase):
    def test_count_sums_the_field_after_the_last_colon(self):
        params = _params("pattern=x", "output_mode=count")
        self.assertEqual(measured_value(params, "C:/a/b.md:2\nC:/a/c.md:5\n"), 7)

    def test_an_unreadable_count_line_is_not_a_zero(self):
        params = _params("pattern=x", "output_mode=count")
        self.assertIsNone(measured_value(params, "not a count\n"))

    def test_other_modes_count_output_lines(self):
        self.assertEqual(measured_value(_params("pattern=x"), "a\nb\nc\n"), 3)
        self.assertEqual(measured_value(_params("pattern=x", "output_mode=content"), "1:a\n2:b\n"), 2)

    def test_a_content_line_holding_a_unicode_separator_is_one_line(self):
        params = _params("pattern=x", "output_mode=content")
        self.assertEqual(measured_value(params, "1:a\u2028b\n"), 1)

    def test_no_parameters_means_no_value(self):
        self.assertIsNone(measured_value(None, "1\n"))


def _write_plan(plan_root, fence_lines):
    body = "".join(f"> {line}\n" for line in fence_lines)
    (plan_root / "TASK-01-Fixture.md").write_text(
        "# Task: Fixture\n\n"
        "## Verification Commands\n\n"
        "> [!verify] Before / After Commands\n"
        "> **After:** *(runner)*\n"
        "> ```bash\n" + body + "> ```\n",
        encoding="utf-8",
    )


class TestLinterEndToEnd(unittest.TestCase):
    def _plan(self, fence_lines, target="X\nY\nX\n"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan_root = Path(tmp.name)
        (plan_root / "target.md").write_text(target, encoding="utf-8")
        _write_plan(plan_root, fence_lines)
        return plan_root

    def test_a_plan_of_only_count_gates_is_fully_covered(self):
        plan_root = self._plan(
            [
                "Grep pattern='X' path='target.md' output_mode='count'   # expect >=1",
                "Grep pattern='Y' path='target.md' output_mode='count'   # expect >=1",
            ]
        )
        _, context = _lint(plan_root, True)
        self.assertEqual(coverage_line(context), "Coverage: checked 2 of 2 gates; 0 refused.")

    def test_the_decided_value_feeds_the_vacuous_gate_check(self):
        plan_root = self._plan(["Grep pattern='X' path='target.md' output_mode='count'   # expect >=1"])
        findings = lint_plan(plan_root)
        checks = [(f["check"], f["severity"]) for f in findings if f["check"] == 1]
        self.assertEqual(checks, [(1, "ERROR")])
        self.assertIn("measurement is 2", next(f["message"] for f in findings if f["check"] == 1))

    def test_an_unknown_parameter_is_reported_uncertain_with_its_reason(self):
        plan_root = self._plan(["Grep pattern='X' path='target.md' type='md'   # expect >=1"])
        findings = lint_plan(plan_root)
        reasons = [f["message"] for f in findings if f["check"] is None]
        self.assertEqual(len(reasons), 1)
        self.assertIn("'type'", reasons[0])
        _, context = _lint(plan_root, True)
        self.assertTrue(coverage_line(context).startswith("Coverage: NOT CHECKED -- 0 of 1 gates ran"))

    def test_an_uncompilable_pattern_is_reported_with_its_reason(self):
        plan_root = self._plan(["Grep pattern='(' path='target.md' output_mode='count'   # expect >=1"])
        reasons = [f["message"] for f in lint_plan(plan_root) if f["check"] is None]
        self.assertEqual(len(reasons), 1)
        self.assertIn("ripgrep-only syntax", reasons[0])

    def test_a_file_search_starts_no_subprocess(self):
        plan_root = self._plan([])
        text = "Grep pattern='X' path='target.md' output_mode='count'"
        command = ExtractedCommand(
            file="t.md", path=plan_root / "t.md", line=1, block="After",
            command=text, comment="# expect >=1",
        )
        self.assertEqual(resolve_argv(text)[0][0], "Grep")
        with patch("subprocess.run", side_effect=AssertionError("spawned")):
            result = execute_command(command, plan_root=plan_root)
        self.assertTrue(result["executed"])
        self.assertEqual(measured_value(_params("pattern=X", "output_mode=count"), result["stdout"]), 2)

    def test_a_missing_target_is_reported_uncertain(self):
        plan_root = self._plan([])
        command = ExtractedCommand(
            file="t.md", path=plan_root / "t.md", line=1, block="After",
            command="Grep pattern='X' path='absent.md' output_mode='count'", comment="# expect >=1",
        )
        result = execute_command(command, plan_root=plan_root)
        self.assertFalse(result["executed"])
        self.assertIn("does not exist", result["reason"])

    def test_the_allowlist_is_unchanged_by_the_tool_call_route(self):
        import lint_verification_gates as linter

        self.assertNotIn("Grep", linter.ALLOWED_EXECUTABLES)


if __name__ == "__main__":
    unittest.main()
