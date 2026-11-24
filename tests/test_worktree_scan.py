#!/usr/bin/env python3
"""Tests for worktree_scan.sibling_dirs and the linked-worktree union in `parse_backlog --next-id`.

`--next-id` used to read only the current tree's backlog, so two linked
worktrees of one repository could allocate the same id. `collect_all_known_ids`
now also reads the backlog and Archive folders of every other linked worktree.

The fixture is a real git repository with a real linked worktree. Each tree's
hub file comes from `generate_backlog_index.main()`, so the reader sees the
producer's own output.

Run with:  python -m pytest tests/test_worktree_scan.py -q
"""

import contextlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index
import parse_backlog
import worktree_scan

CONFIG_YAML_FIXTURE = """project:
  name: "WorktreeScanFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

CURRENT_ID = 5
SIBLING_ID = 120


def _force_remove(func, path, _exc):
    """Clear a read-only bit that blocks a delete on Windows, then retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:
        shutil.rmtree(path, onerror=_force_remove)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestWorktreeScan(unittest.TestCase):
    """A real repository, one real linked worktree, and a hub per tree."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="worktree_scan_test_"))
        self.addCleanup(_rmtree, self.tmp)
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def git(self, repo: Path, *args: str) -> None:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"git {' '.join(args)} failed: {proc.stderr}")

    def make_repo(self, name: str = "repo") -> Path:
        repo = self.tmp / name
        repo.mkdir()
        self.git(repo, "init")
        self.git(
            repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
            "commit", "--allow-empty", "-m", "init",
        )
        return repo

    def add_worktree(self, repo: Path, name: str = "wt") -> Path:
        sibling = self.tmp / name
        self.git(repo, "worktree", "add", "-b", f"{name}-branch", str(sibling))
        return sibling

    def build_tree(self, root: Path, item_id: int) -> Path:
        """Write one item file and generate the hub in `root`. Return the config path."""
        planwise = root / "planwise"
        backlog = planwise / "Backlog"
        (backlog / "Archive").mkdir(parents=True)
        config_path = planwise / "config.yaml"
        config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        (backlog / f"BB-{item_id:03d}-01-BUG-Fixture.md").write_text(
            "---\n"
            f"id: {item_id}\n"
            "title: Fixture item\n"
            "priority: Medium\n"
            "status: NOT_STARTED\n"
            "abbrev: BUG\n"
            "created: 2026-01-01\n"
            "blocks: []\n"
            "---\n\n"
            "# Fixture item\n",
            encoding="utf-8",
        )
        sys.argv = ["generate_backlog_index", "--config", str(config_path), "--write"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = generate_backlog_index.main()
        self.assertEqual(code, 0, f"generator failed: {err.getvalue()}")
        return config_path

    def next_id(self, config_path: Path) -> str:
        sys.argv = ["parse_backlog", "--config", str(config_path), "--next-id"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            parse_backlog.main()
        return out.getvalue().strip()

    def test_next_id_reads_sibling_worktree(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_tree(repo, CURRENT_ID)
        self.build_tree(sibling, SIBLING_ID)
        found = worktree_scan.sibling_dirs(repo / "planwise" / "Backlog")
        self.assertEqual([p.resolve() for p in found], [(sibling / "planwise" / "Backlog").resolve()])
        self.assertEqual(self.next_id(config_path), f"{SIBLING_ID + 1:03d}")

    def test_no_git_folder_returns_empty(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        config_path = self.build_tree(plain, CURRENT_ID)
        # A repository above the temp folder must not be found.
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertEqual(worktree_scan.sibling_dirs(plain / "planwise" / "Backlog"), [])
            self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")

    def test_single_worktree_returns_empty(self):
        repo = self.make_repo()
        config_path = self.build_tree(repo, CURRENT_ID)
        self.assertEqual(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog"), [])
        self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")

    def test_removed_worktree_is_skipped(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_tree(repo, CURRENT_ID)
        self.build_tree(sibling, SIBLING_ID)
        # Positive control: the sibling is visible before its folder is deleted.
        self.assertEqual(len(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog")), 1)
        _rmtree(sibling)  # git still lists the worktree: no `git worktree prune`
        self.assertEqual(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog"), [])
        self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")


if __name__ == "__main__":
    unittest.main()
