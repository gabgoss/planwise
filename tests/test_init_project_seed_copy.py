#!/usr/bin/env python3
"""Unit test for init_project.copy_seed_files' changelog seed.

Pre-write repair, Execution Step 4 (user decision (a)): the generator's hub
footer points at `00-Changelog-Backlog.md`, so a fresh `/planwise init` must
seed that file alongside the index, or the footer's link dangles on a
project that has never run the generator.

Run with:  python -m pytest tests/test_init_project_seed_copy.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project
from config_gen import InitConfig


class TestCopySeedFilesIncludesChangelog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_project_seed_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "planwise" / "Backlog").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "LessonsLearned").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "Plans").mkdir(parents=True, exist_ok=True)

        self.cfg = InitConfig(
            project_name="seed-copy-fixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )

    def test_fresh_init_copies_the_changelog_seed(self):
        copied = init_project.copy_seed_files(self.cfg)

        self.assertIn("planwise/Backlog/00-Changelog-Backlog.md", copied)
        dst = self.tmp / "planwise" / "Backlog" / "00-Changelog-Backlog.md"
        self.assertTrue(dst.exists())
        self.assertIn("00-Index-Backlog.md", dst.read_text(encoding="utf-8"))

    def test_existing_changelog_is_never_overwritten(self):
        dst = self.tmp / "planwise" / "Backlog" / "00-Changelog-Backlog.md"
        dst.write_text("existing history\n", encoding="utf-8")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertNotIn("planwise/Backlog/00-Changelog-Backlog.md", copied)
        self.assertEqual(dst.read_text(encoding="utf-8"), "existing history\n")


class TestCopySeedFilesIncludesLessonsCompanions(unittest.TestCase):
    """A fresh init must seed the lessons index's two generated-shape
    companions (changelog, promotion log) alongside the index itself, or
    the generated hub's footer pointers dangle on a project that has never
    run the generator — the same gap TestCopySeedFilesIncludesChangelog
    covers for the backlog side."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_project_seed_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "planwise" / "Backlog").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "LessonsLearned").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "Plans").mkdir(parents=True, exist_ok=True)

        self.cfg = InitConfig(
            project_name="seed-copy-fixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )

    def test_fresh_init_copies_both_lessons_companion_seeds(self):
        copied = init_project.copy_seed_files(self.cfg)

        self.assertIn("planwise/LessonsLearned/00-Changelog-LessonsLearned.md", copied)
        self.assertIn(
            "planwise/LessonsLearned/00-PromotionLog-LessonsLearned.md", copied
        )
        changelog = self.tmp / "planwise" / "LessonsLearned" / "00-Changelog-LessonsLearned.md"
        promotion_log = (
            self.tmp / "planwise" / "LessonsLearned" / "00-PromotionLog-LessonsLearned.md"
        )
        self.assertTrue(changelog.exists())
        self.assertTrue(promotion_log.exists())
        self.assertIn("00-Index-LessonsLearned.md", changelog.read_text(encoding="utf-8"))
        self.assertIn(
            "00-Index-LessonsLearned.md", promotion_log.read_text(encoding="utf-8")
        )

    def test_existing_lessons_companions_are_never_overwritten(self):
        changelog = self.tmp / "planwise" / "LessonsLearned" / "00-Changelog-LessonsLearned.md"
        promotion_log = (
            self.tmp / "planwise" / "LessonsLearned" / "00-PromotionLog-LessonsLearned.md"
        )
        changelog.write_text("existing changelog history\n", encoding="utf-8")
        promotion_log.write_text("existing promotion log history\n", encoding="utf-8")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertNotIn(
            "planwise/LessonsLearned/00-Changelog-LessonsLearned.md", copied
        )
        self.assertNotIn(
            "planwise/LessonsLearned/00-PromotionLog-LessonsLearned.md", copied
        )
        self.assertEqual(
            changelog.read_text(encoding="utf-8"), "existing changelog history\n"
        )
        self.assertEqual(
            promotion_log.read_text(encoding="utf-8"),
            "existing promotion log history\n",
        )


if __name__ == "__main__":
    unittest.main()
