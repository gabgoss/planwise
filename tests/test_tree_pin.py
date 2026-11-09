"""Tests for scripts/tree_pin.py: stamp a scratch repo, change it, compare.

Every repository and stamp file lives under `tempfile.mkdtemp()` and is
removed in `tearDown`; nothing is written under the plugin repo.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "tree_pin.py"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class TreePinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tree_pin_test_"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "core.autocrlf", "false")
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "a.txt").write_text("a\n", encoding="utf-8")
        (self.repo / "other.txt").write_text("o\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "init")
        self.out = self.tmp / "pins" / "stamp.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pin(self, *args):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              capture_output=True, check=False)
        return proc.returncode, proc.stdout.decode("utf-8")

    def stamp(self, *subtrees):
        extra = [arg for sub in subtrees for arg in ("--subtree", sub)]
        code, out = self.run_pin("stamp", "--repo", str(self.repo), *extra, "--out", str(self.out))
        self.assertEqual(code, 0, out)
        return out

    def compare(self):
        return self.run_pin("compare", str(self.out), "--repo", str(self.repo))

    def test_unchanged_tree_compares_equal(self):
        self.stamp("sub")
        code, out = self.compare()
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("stamps equal: head "))
        self.assertNotIn("\r", out)

    def test_stamp_file_records_head_branch_and_status(self):
        self.stamp("sub")
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(data["branch"], "main")
        self.assertEqual(len(data["head"]), 40)
        self.assertEqual(data["subtrees"], ["sub"])
        self.assertEqual(data["status"], {"sub": ""})

    def test_new_commit_differs_and_exits_1(self):
        self.stamp()
        (self.repo / "other.txt").write_text("changed\n", encoding="utf-8")
        _git(self.repo, "commit", "-q", "-am", "second")
        code, out = self.compare()
        self.assertEqual(code, 1, out)
        self.assertIn("differs: head: ", out)
        self.assertIn("stamps differ: 1 field(s); redo the read", out)

    def test_untracked_file_in_subtree_differs_and_exits_1(self):
        self.stamp("sub")
        (self.repo / "sub" / "new.txt").write_text("n\n", encoding="utf-8")
        code, out = self.compare()
        self.assertEqual(code, 1, out)
        self.assertIn("differs: status sub: + ?? sub/new.txt", out)

    def test_change_outside_the_subtree_is_not_a_difference(self):
        self.stamp("sub")
        (self.repo / "loose.txt").write_text("x\n", encoding="utf-8")
        code, out = self.compare()
        self.assertEqual(code, 0, out)

    def test_branch_switch_differs(self):
        self.stamp()
        _git(self.repo, "checkout", "-q", "-b", "side")
        code, out = self.compare()
        self.assertEqual(code, 1, out)
        self.assertIn("differs: branch: main -> side", out)

    def test_already_dirty_paths_edited_again_differ(self):
        # The porcelain line stays ` M sub/a.txt` and `?? sub/new.txt` across the
        # window; only the recorded content hash can see the second edit.
        (self.repo / "sub" / "a.txt").write_text("first edit\n", encoding="utf-8")
        (self.repo / "sub" / "new.txt").write_text("n1\n", encoding="utf-8")
        self.stamp("sub")
        (self.repo / "sub" / "a.txt").write_text("second edit\n", encoding="utf-8")
        (self.repo / "sub" / "new.txt").write_text("n2\n", encoding="utf-8")
        code, out = self.compare()
        self.assertEqual(code, 1, out)
        self.assertIn("differs: content sub: sub/a.txt", out)
        self.assertIn("differs: content sub: sub/new.txt", out)
        self.assertNotIn("differs: status", out)

    def test_file_inside_an_untracked_directory_is_hashed(self):
        (self.repo / "sub" / "fresh").mkdir()
        (self.repo / "sub" / "fresh" / "f.txt").write_text("1\n", encoding="utf-8")
        self.stamp("sub")
        (self.repo / "sub" / "fresh" / "f.txt").write_text("2\n", encoding="utf-8")
        code, out = self.compare()
        self.assertEqual(code, 1, out)
        self.assertIn("differs: content sub: sub/fresh/f.txt", out)

    def test_dirty_path_left_alone_still_compares_equal(self):
        (self.repo / "sub" / "a.txt").write_text("edit\n", encoding="utf-8")
        self.stamp("sub")
        code, out = self.compare()
        self.assertEqual(code, 0, out)

    def test_out_inside_the_repo_is_refused(self):
        inside = self.repo / "stamp.json"
        code, out = self.run_pin("stamp", "--repo", str(self.repo), "--out", str(inside))
        self.assertEqual(code, 2)
        self.assertIn("inside the stamped repository", out)
        self.assertFalse(inside.exists())

    def test_unreadable_stamp_file_exits_2(self):
        code, out = self.run_pin("compare", str(self.tmp / "missing.json"), "--repo", str(self.repo))
        self.assertEqual(code, 2)
        self.assertIn("error: cannot read stamp file", out)


if __name__ == "__main__":
    unittest.main()
