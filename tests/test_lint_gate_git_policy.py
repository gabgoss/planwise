"""Tests for the read-only git policy of the verification-gate linter.

Covers ``git_refusal`` and ``hardened_git_argv_env`` directly, and
``run_command`` end to end against a throwaway repository built under a
temporary directory outside the shipped plugin tree.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from lint_gate_git_policy import git_refusal, hardened_git_argv_env
from lint_verification_gates import run_command

GIT = shutil.which("git")

ADMITTED = [
    ["git", "status"],
    ["git", "status", "--porcelain"],
    ["git", "-C", "somedir", "status", "--porcelain"],
    ["git", "-C", "a", "-C", "b", "diff", "--stat"],
    ["git", "diff", "--no-ext-diff", "--name-only"],
    ["git", "log", "--oneline", "-5"],
    ["git", "ls-files"],
    ["git", "rev-parse", "HEAD"],
    ["git", "show", "HEAD:README.md"],
    # After "--" every token is a path, not an option.
    ["git", "diff", "--", "--output"],
]

REFUSED = [
    (["git"], "no subcommand"),
    (["git", "-c", "x=y", "status"], "global option -c"),
    (["git", "--git-dir=x", "status"], "global option --git-dir"),
    (["git", "--exec-path", "status"], "global option --exec-path"),
    (["git", "-C"], "-C without a directory"),
    (["git", "-C", "-c", "status"], "-C naming an option"),
    (["git", "commit", "-m", "x"], "writing subcommand commit"),
    (["git", "push"], "subcommand push"),
    (["git", "checkout", "."], "subcommand checkout"),
    (["git", "config", "user.name", "x"], "subcommand config"),
    (["git", "diff", "--output=f"], "--output"),
    (["git", "diff", "--output", "f"], "--output with a separate value"),
    (["git", "diff", "--out=f"], "abbreviated --output"),
    (["git", "diff", "--ext-diff"], "--ext-diff"),
    (["git", "diff", "--ext"], "abbreviated --ext-diff"),
    (["git", "show", "--textconv"], "--textconv"),
    (["git", "log", "--show-signature"], "--show-signature"),
]


class TestGitRefusal(unittest.TestCase):
    def test_read_only_queries_are_admitted(self):
        for argv in ADMITTED:
            with self.subTest(argv=argv):
                self.assertIsNone(git_refusal(argv))

    def test_everything_else_is_refused_with_a_reason(self):
        for argv, label in REFUSED:
            with self.subTest(case=label):
                reason = git_refusal(argv)
                self.assertIsInstance(reason, str)
                self.assertTrue(reason)

    def test_refused_commands_are_not_executed(self):
        for argv, label in REFUSED:
            with self.subTest(case=label):
                result = run_command(argv)
                self.assertFalse(result["executed"])
                self.assertEqual(result["disposition"], "UNCERTAIN")

    def test_the_no_variants_are_not_mistaken_for_the_refused_flags(self):
        self.assertIsNone(git_refusal(["git", "log", "--no-ext-diff", "--no-textconv"]))

    def test_refusal_message_is_count_free(self):
        reason = git_refusal(["git", "commit"])
        self.assertIn("is not on the read-only allowlist", reason)
        self.assertNotIn("four", reason)


class TestHardenedInvocation(unittest.TestCase):
    def test_config_and_diff_flags_are_inserted_and_user_tokens_kept(self):
        argv, _ = hardened_git_argv_env(["git", "-C", "d", "diff", "--stat", "--", "f"])
        self.assertEqual(
            argv,
            [
                "git", "-c", "core.fsmonitor=false", "-c", "core.pager=cat",
                "-C", "d", "diff", "--no-ext-diff", "--no-textconv",
                "--stat", "--", "f",
            ],
        )

    def test_status_gets_config_but_no_diff_flags(self):
        argv, _ = hardened_git_argv_env(["git", "status", "--porcelain"])
        self.assertEqual(
            argv,
            ["git", "-c", "core.fsmonitor=false", "-c", "core.pager=cat",
             "status", "--porcelain"],
        )

    def test_log_and_show_get_the_diff_flags(self):
        for sub in ("log", "show"):
            with self.subTest(sub=sub):
                argv, _ = hardened_git_argv_env(["git", sub])
                self.assertIn("--no-ext-diff", argv)
                self.assertIn("--no-textconv", argv)

    def test_environment_disables_optional_locks_and_drops_external_diff(self):
        with patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": "evil", "GIT_OPTIONAL_LOCKS": "1"}):
            _, env = hardened_git_argv_env(["git", "status"])
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertNotIn("GIT_EXTERNAL_DIFF", env)


@unittest.skipUnless(GIT, "git is not installed")
class TestRunAgainstARealRepository(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self.tracked = self.repo / "a.txt"
        self.tracked.write_text("one\n", encoding="utf-8")
        self._git("add", "a.txt")
        self._git(
            "-c", "user.name=t", "-c", "user.email=t@example.invalid",
            "commit", "-q", "-m", "init",
        )

    def _git(self, *args):
        subprocess.run([GIT, "-C", str(self.repo), *args], check=True, capture_output=True)

    def _index_digest(self):
        return hashlib.sha256((self.repo / ".git" / "index").read_bytes()).hexdigest()

    def test_status_is_executed(self):
        (self.repo / "new.txt").write_text("x\n", encoding="utf-8")
        result = run_command(["git", "-C", str(self.repo), "status", "--porcelain"])
        self.assertTrue(result["executed"], result)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("new.txt", result["stdout"])

    def test_each_admitted_subcommand_is_executed(self):
        commands = [
            ["diff", "--stat"],
            ["log", "--oneline", "-1"],
            ["ls-files"],
            ["rev-parse", "HEAD"],
            ["show", "--stat", "HEAD"],
        ]
        for tail in commands:
            with self.subTest(tail=tail):
                result = run_command(["git", "-C", str(self.repo), *tail])
                self.assertTrue(result["executed"], result)
                self.assertEqual(result["returncode"], 0, result["stderr"])

    def _make_index_stat_stale(self):
        # Same content, different mtime: a plain `git status` re-hashes the
        # file and rewrites the index entry, so it would change the index.
        stat = self.tracked.stat()
        os.utime(self.tracked, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    def test_control_plain_git_status_does_rewrite_the_index(self):
        self._make_index_stat_stale()
        before = self._index_digest()
        subprocess.run(
            [GIT, "-C", str(self.repo), "status", "--porcelain"],
            check=True, capture_output=True,
        )
        self.assertNotEqual(self._index_digest(), before, "the control could not see an index write")

    def test_linter_status_leaves_the_index_untouched(self):
        self._make_index_stat_stale()
        before_digest = self._index_digest()
        before_mtime = (self.repo / ".git" / "index").stat().st_mtime_ns
        result = run_command(["git", "-C", str(self.repo), "status", "--porcelain"])
        self.assertTrue(result["executed"], result)
        self.assertEqual(self._index_digest(), before_digest)
        self.assertEqual((self.repo / ".git" / "index").stat().st_mtime_ns, before_mtime)


if __name__ == "__main__":
    unittest.main()
