#!/usr/bin/env python3
"""config.yaml resolution must never read a foreign project's config.

`find_config_upward()` walks the ancestors of the invocation directory and
each ancestor's immediate children, and stops at the checkout root (the first
directory that holds a `.git` file or folder). From a directory with no planwise config
(a temp dir, a fresh checkout) that chain crosses directories the project
does not own, and any `config.yaml` an unrelated tool left there used to be
resolved and read as this project's — a plausible plans table for the wrong
project, with no warning. These tests pin the documented gate: a) direct,
b) one level down, a planwise marker on every accepted candidate, and a
fail-loud exit when nothing qualifies.

Run with:  python -m unittest tests/test_config_resolution.py
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader

PLANWISE_CONFIG = (
    "project:\n"
    "  name: Fixture\n"
    "  planwise_root: planwise\n"
    "  plans_dir: Plans\n"
    "  backlog_dir: Backlog\n"
    "  lessons_dir: LessonsLearned\n"
)
FOREIGN_CONFIG = "tool: something-else\nverbose: true\n"


class _ResolutionFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cfg_resolution_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class TestFindConfigUpward(_ResolutionFixture):
    def test_no_config_anywhere_returns_none(self):
        start = self.tmp / "work" / "deeper"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start, stop_at=self.tmp))

    def test_foreign_config_in_the_chain_is_skipped(self):
        """The defect: a config.yaml with no planwise marker sits on an
        ancestor. It must be skipped, not resolved."""
        self.write("config.yaml", FOREIGN_CONFIG)
        self.write("sibling-tool/config.yaml", FOREIGN_CONFIG)
        start = self.tmp / "work" / "deeper"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start, stop_at=self.tmp))

    def test_planwise_config_one_level_down_is_found(self):
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        found = config_loader.find_config_upward(self.tmp, stop_at=self.tmp)
        self.assertEqual(found, expected)

    def test_planwise_config_in_an_ancestor_is_found(self):
        """The documented upward search survives: invoking from a
        subdirectory of the project still resolves the project's config."""
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        start = self.tmp / "src" / "pkg"
        start.mkdir(parents=True)
        self.assertEqual(config_loader.find_config_upward(start, stop_at=self.tmp), expected)

    def test_planwise_config_wins_over_a_foreign_sibling(self):
        self.write("other-tool/config.yaml", FOREIGN_CONFIG)
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        self.assertEqual(config_loader.find_config_upward(self.tmp, stop_at=self.tmp), expected)

    def test_marker_accepts_bom_and_trailing_comment(self):
        bom = self.write("a/config.yaml", "﻿project:  # the project block\n  name: X\n")
        self.assertTrue(config_loader._is_planwise_config(bom))

    def test_marker_rejects_nested_or_prose_project_key(self):
        nested = self.write("b/config.yaml", "settings:\n  project: nope\n")
        self.assertFalse(config_loader._is_planwise_config(nested))
        unreadable = self.tmp / "c" / "config.yaml"
        unreadable.parent.mkdir(parents=True)
        unreadable.write_bytes(b"\xff\xfe\x00not text")
        self.assertFalse(config_loader._is_planwise_config(unreadable))


def _git(cwd: Path, *args: str) -> None:
    """Run one real git command in `cwd`, with an identity that needs no global config."""
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class TestWalkStopsAtTheCheckoutRoot(_ResolutionFixture):
    """The upward walk must not leave the checkout it started in.

    A linked worktree holds a `.git` FILE at its root. A walk that ignores it
    climbs out of the worktree and loads the main checkout's config, which the
    worktree does not own.
    """

    def test_dot_git_file_stops_the_walk_before_an_outer_config(self):
        """A `.git` file at an inner directory bounds the walk (no real git needed)."""
        self.write("outer/planwise/config.yaml", PLANWISE_CONFIG)
        self.write("outer/inner/.git", "gitdir: elsewhere\n")
        start = self.tmp / "outer" / "inner" / "src"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start))

    def test_dot_git_folder_stops_the_walk_before_an_outer_config(self):
        self.write("outer/planwise/config.yaml", PLANWISE_CONFIG)
        (self.tmp / "outer" / "inner" / ".git").mkdir(parents=True)
        start = self.tmp / "outer" / "inner" / "src"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start))

    def test_config_in_the_checkout_root_itself_is_still_found(self):
        """The root that holds `.git` is checked before the walk stops."""
        expected = self.write("repo/planwise/config.yaml", PLANWISE_CONFIG)
        (self.tmp / "repo" / ".git").mkdir()
        start = self.tmp / "repo" / "src" / "pkg"
        start.mkdir(parents=True)
        self.assertEqual(config_loader.find_config_upward(start), expected.resolve())


@unittest.skipUnless(shutil.which("git"), "git is not on PATH")
class TestLinkedWorktreeConfigResolution(_ResolutionFixture):
    """A real `git worktree add` fixture: the worktree has no planwise config
    and the main checkout, which holds an untracked one, sits above it."""

    def setUp(self):
        super().setUp()
        self.main = self.tmp / "main"
        self.main.mkdir()
        _git(self.main, "init")
        self.write("main/README.md", "fixture\n")
        _git(self.main, "add", "README.md")
        _git(self.main, "commit", "-m", "init")
        self.worktree = self.main / ".claude" / "worktrees" / "w1"
        _git(self.main, "worktree", "add", str(self.worktree), "-b", "w1")
        self.main_config = self.write("main/planwise/config.yaml", PLANWISE_CONFIG)
        self.assertTrue((self.worktree / ".git").is_file(), "a linked worktree holds a .git file")

    def test_worktree_without_a_config_never_reaches_the_main_checkout_config(self):
        self.assertIsNone(config_loader.find_config_upward(self.worktree))

    def test_worktree_subfolder_finds_the_worktree_own_config(self):
        expected = self.write("main/.claude/worktrees/w1/planwise/config.yaml", PLANWISE_CONFIG)
        start = self.worktree / "src" / "pkg"
        start.mkdir(parents=True)
        self.assertEqual(config_loader.find_config_upward(start), expected.resolve())

    def test_load_config_from_a_worktree_exits_instead_of_loading_the_main_config(self):
        scripts = self.worktree / "scripts"
        scripts.mkdir()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.worktree)
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["script.py"]), \
             contextlib.redirect_stderr(stderr), \
             self.assertRaises(SystemExit) as ctx:
            config_loader.load_config(script_path=scripts / "x.py")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("config.yaml not found", stderr.getvalue())


class TestLoadConfigFailsLoud(_ResolutionFixture):
    def test_no_resolvable_config_exits_nonzero_with_the_init_hint(self):
        """With nothing resolvable, load_config() must exit 1 and say so —
        never fall through to a config found by inference."""
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["script.py"]), \
             mock.patch.object(config_loader, "find_config_upward", return_value=None), \
             contextlib.redirect_stderr(stderr), \
             self.assertRaises(SystemExit) as ctx:
            config_loader.load_config(script_path=self.tmp / "scripts" / "x.py")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("config.yaml not found", stderr.getvalue())
        self.assertIn("/planwise init", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
