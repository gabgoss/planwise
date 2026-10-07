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

import config_loader
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


class TestCopySeedFilesCustomLessonsHubName(unittest.TestCase):
    """copy_seed_files derives the lessons companion filenames from the
    project's configured `index_files.lessons` (when config.yaml already
    exists at call time) via the same naming helpers `_seed_lessons_index`
    uses — never a fixed pair of companion names."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_project_seed_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "planwise" / "Backlog").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "LessonsLearned").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "Plans").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "config.yaml").write_text(
            "project:\n"
            "  planwise_root: planwise\n"
            "  lessons_dir: LessonsLearned\n"
            "  index_files:\n"
            "    lessons: 00-Index-MyLessons.md\n",
            encoding="utf-8",
        )

        self.cfg = InitConfig(
            project_name="seed-copy-fixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )

    def test_companions_named_from_custom_hub(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for config_loader.resolve_index_target")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertIn("planwise/LessonsLearned/00-Changelog-MyLessons.md", copied)
        self.assertIn("planwise/LessonsLearned/00-PromotionLog-MyLessons.md", copied)
        lessons_dir = self.tmp / "planwise" / "LessonsLearned"
        self.assertTrue((lessons_dir / "00-Index-MyLessons.md").exists())
        self.assertTrue((lessons_dir / "00-Changelog-MyLessons.md").exists())
        self.assertTrue((lessons_dir / "00-PromotionLog-MyLessons.md").exists())
        # The fixed default names must NOT be created.
        self.assertFalse((lessons_dir / "00-Changelog-LessonsLearned.md").exists())
        self.assertFalse((lessons_dir / "00-PromotionLog-LessonsLearned.md").exists())


class TestCopySeedFilesCustomPlansIndexName(unittest.TestCase):
    """copy_seed_files names the plans seed's destination from the project's
    configured `index_files.plans` (when config.yaml already exists at call
    time) and from the generated default otherwise -- never a fixed literal.
    An existing destination is never overwritten."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_project_seed_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "planwise" / "Backlog").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "LessonsLearned").mkdir(parents=True, exist_ok=True)
        (self.tmp / "planwise" / "Plans").mkdir(parents=True, exist_ok=True)
        self.plans_dir = self.tmp / "planwise" / "Plans"

        self.cfg = InitConfig(
            project_name="seed-copy-fixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )

    def _write_config(self, plans_name: str) -> None:
        (self.tmp / "planwise" / "config.yaml").write_text(
            "project:\n"
            "  planwise_root: planwise\n"
            "  plans_dir: Plans\n"
            "  index_files:\n"
            f"    plans: {plans_name}\n",
            encoding="utf-8",
        )

    def test_seed_lands_at_the_configured_name(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for config_loader.resolve_index_target")
        self._write_config("00-Plans-Custom.md")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertIn("planwise/Plans/00-Plans-Custom.md", copied)
        self.assertTrue((self.plans_dir / "00-Plans-Custom.md").exists())
        self.assertFalse((self.plans_dir / "00-Index-Plans.md").exists())

    def test_no_config_seeds_the_default_name(self):
        copied = init_project.copy_seed_files(self.cfg)

        self.assertIn("planwise/Plans/00-Index-Plans.md", copied)
        self.assertTrue((self.plans_dir / "00-Index-Plans.md").exists())

    def test_existing_plans_index_is_never_overwritten(self):
        dst = self.plans_dir / "00-Index-Plans.md"
        dst.write_text("existing plans index\n", encoding="utf-8")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertNotIn("planwise/Plans/00-Index-Plans.md", copied)
        self.assertEqual(dst.read_text(encoding="utf-8"), "existing plans index\n")

    def test_existing_plans_index_at_the_configured_name_is_never_overwritten(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for config_loader.resolve_index_target")
        self._write_config("00-Plans-Custom.md")
        dst = self.plans_dir / "00-Plans-Custom.md"
        dst.write_text("existing custom plans index\n", encoding="utf-8")

        copied = init_project.copy_seed_files(self.cfg)

        self.assertNotIn("planwise/Plans/00-Plans-Custom.md", copied)
        self.assertEqual(dst.read_text(encoding="utf-8"), "existing custom plans index\n")
        self.assertFalse((self.plans_dir / "00-Index-Plans.md").exists())

    def _assert_null_block_falls_back_to_default(self, config_text: str) -> None:
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for config_loader.resolve_index_target")
        (self.tmp / "planwise" / "config.yaml").write_text(config_text, encoding="utf-8")

        self.assertEqual(
            config_loader.resolve_index_target(self.cfg, "plans"),
            ("planwise/Plans", "00-Index-Plans.md"),
        )

    def test_null_project_block_falls_back_to_the_default_name(self):
        self._assert_null_block_falls_back_to_default("project:\n")

    def test_null_index_files_block_falls_back_to_the_default_name(self):
        self._assert_null_block_falls_back_to_default(
            "project:\n  planwise_root: planwise\n  index_files:\n"
        )

    def test_non_dict_index_files_block_falls_back_to_the_default_name(self):
        self._assert_null_block_falls_back_to_default(
            "project:\n  planwise_root: planwise\n  index_files: 00-Plans-Custom.md\n"
        )


if __name__ == "__main__":
    unittest.main()
