"""Shebang Python files carry the executable bit, and the pre-commit hook sets it.

Ruff's EXE001 fails a Python file that starts with `#!` but is not
executable. Ruff cannot read the bit on Windows, so the rule passes locally
and fails only on the Linux CI runner. A Windows clone also runs with
core.filemode=false, so git stores every new file as 100644.

Two guards close the gap. `.githooks/pre-commit` marks each staged shebang
file executable. This test reads the git index on any platform and fails on
a shebang file stored as 100644. The hook cases run it in a scratch repo
under `tempfile.mkdtemp()`, removed in `tearDown`.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".githooks" / "pre-commit"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def _index_modes(repo):
    """Map each tracked path to its index mode."""
    modes = {}
    for entry in _git(repo, "ls-files", "-s", "-z").decode("utf-8").split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            modes[path] = meta.split()[0]
    return modes


class ShebangModeTests(unittest.TestCase):
    def test_every_tracked_shebang_python_file_is_executable(self):
        checked = 0
        bad = []
        for path, mode in _index_modes(REPO).items():
            if not path.endswith(".py"):
                continue
            with open(REPO / path, "rb") as handle:
                if handle.read(2) != b"#!":
                    continue
            checked += 1
            if mode != "100755":
                bad.append(path)
        self.assertGreater(checked, 0, "no shebang file found: the index read saw nothing")
        self.assertEqual(
            bad, [],
            "shebang files stored as 100644; fix with: git update-index --chmod=+x -- <path>, "
            "or enable the hook once: git config core.hooksPath .githooks",
        )

    def test_the_hook_itself_is_executable(self):
        self.assertEqual(_index_modes(REPO).get(".githooks/pre-commit"), "100755")

    def test_the_hook_checks_out_with_lf_endings(self):
        attrs = _git(REPO, "check-attr", "eol", "--", ".githooks/pre-commit").decode("utf-8")
        self.assertTrue(attrs.strip().endswith("eol: lf"), attrs)
        self.assertNotIn(b"\r\n", HOOK.read_bytes())


class PreCommitHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shebang_hook_test_"))
        self.repo = self.tmp / "repo"
        (self.repo / ".githooks").mkdir(parents=True)
        hook = self.repo / ".githooks" / "pre-commit"
        shutil.copyfile(HOOK, hook)
        os.chmod(hook, 0o755)  # git on Linux and macOS ignores a hook that is not executable on disk
        _git(self.repo, "init", "-q", "-b", "main")
        for key, value in (("user.email", "t@example.com"), ("user.name", "t"),
                           ("core.autocrlf", "false"), ("core.filemode", "false"),
                           ("core.hooksPath", ".githooks")):
            _git(self.repo, "config", key, value)
        _git(self.repo, "add", ".githooks/pre-commit")
        _git(self.repo, "update-index", "--chmod=+x", ".githooks/pre-commit")
        _git(self.repo, "commit", "-q", "--no-verify", "-m", "hook")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        (self.repo / name).write_bytes(text.encode("utf-8"))

    def committed_mode(self, path):
        return _git(self.repo, "ls-tree", "HEAD", "--", path).decode("utf-8").split()[0]

    def test_a_new_shebang_file_commits_as_executable(self):
        self.write("tool.py", "#!/usr/bin/env python3\nprint(1)\n")
        self.write("plain.py", "x = 1\n")
        _git(self.repo, "add", "tool.py", "plain.py")
        _git(self.repo, "commit", "-q", "-m", "add")
        self.assertEqual(self.committed_mode("tool.py"), "100755")
        self.assertEqual(self.committed_mode("plain.py"), "100644")

    def test_a_pathspec_commit_also_gets_the_bit(self):
        self.write("tool.py", "#!/usr/bin/env python3\n")
        _git(self.repo, "add", "tool.py")
        _git(self.repo, "commit", "-q", "-m", "add", "--", "tool.py")
        self.assertEqual(self.committed_mode("tool.py"), "100755")

    def test_a_space_in_the_name_is_handled(self):
        self.write("my tool.py", "#!/usr/bin/env python3\n")
        _git(self.repo, "add", "my tool.py")
        _git(self.repo, "commit", "-q", "-m", "add")
        self.assertEqual(self.committed_mode("my tool.py"), "100755")


if __name__ == "__main__":
    unittest.main()
