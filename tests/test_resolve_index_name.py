#!/usr/bin/env python3
"""Tests for the shared index-name and index-directory resolvers in config_loader.

One null-safe helper (`resolve_index_name`) replaces the two private helpers
that init_project and lessons_bootstrap each carried. The lessons copy raised
AttributeError on a null `project:` or `project.index_files:` block, and both
callers built the index directory from CLI defaults rather than from
config.yaml.

Run with:  python -m pytest tests/test_resolve_index_name.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import lessons_bootstrap
from config_gen import ConfigResult, InitConfig

FAMILIES = ("plans", "backlog", "lessons")
DEFAULTS = {
    "plans": "00-Index-Plans.md",
    "backlog": "00-Index-Backlog.md",
    "lessons": "00-Index-LessonsLearned.md",
}


def _require_yaml(test: unittest.TestCase) -> None:
    try:
        import yaml  # noqa: F401
    except ImportError:
        test.skipTest("PyYAML required for config.yaml parsing")


class TestResolveIndexNamePure(unittest.TestCase):
    """resolve_index_name over an already-parsed dict; needs no PyYAML."""

    def _assert_default_for_every_family(self, config) -> None:
        for family in FAMILIES:
            with self.subTest(family=family):
                self.assertEqual(config_loader.resolve_index_name(config, family), DEFAULTS[family])

    def test_null_project_block_returns_the_defaults(self):
        self._assert_default_for_every_family({"project": None})

    def test_null_index_files_block_returns_the_defaults(self):
        self._assert_default_for_every_family({"project": {"index_files": None}})

    def test_scalar_project_block_returns_the_defaults(self):
        self._assert_default_for_every_family({"project": "planwise"})

    def test_scalar_index_files_block_returns_the_defaults(self):
        self._assert_default_for_every_family({"project": {"index_files": "00-Custom.md"}})

    def test_missing_keys_return_the_defaults(self):
        self._assert_default_for_every_family({})
        self._assert_default_for_every_family({"project": {}})
        self._assert_default_for_every_family({"project": {"index_files": {}}})

    def test_non_dict_config_returns_the_defaults(self):
        for config in (None, [], "text", 7):
            with self.subTest(config=config):
                self._assert_default_for_every_family(config)

    def test_null_empty_and_non_string_values_return_the_defaults(self):
        for bad in (None, "", 0, 3.5, True, ["x.md"], {"a": "b"}):
            with self.subTest(value=bad):
                config = {"project": {"index_files": {f: bad for f in FAMILIES}}}
                self._assert_default_for_every_family(config)

    def test_null_lessons_value_returns_the_lessons_default(self):
        config = {"project": {"index_files": {"lessons": None, "plans": "P.md"}}}
        self.assertEqual(config_loader.resolve_index_name(config, "lessons"), DEFAULTS["lessons"])
        self.assertEqual(config_loader.resolve_index_name(config, "plans"), "P.md")

    def test_configured_names_are_returned_per_family(self):
        config = {
            "project": {
                "index_files": {
                    "plans": "Plans-Hub.md",
                    "backlog": "Backlog-Hub.md",
                    "lessons": "Lessons-Hub.md",
                }
            }
        }
        self.assertEqual(config_loader.resolve_index_name(config, "plans"), "Plans-Hub.md")
        self.assertEqual(config_loader.resolve_index_name(config, "backlog"), "Backlog-Hub.md")
        self.assertEqual(config_loader.resolve_index_name(config, "lessons"), "Lessons-Hub.md")

    def test_unknown_family_raises_value_error(self):
        with self.assertRaises(ValueError):
            config_loader.resolve_index_name({}, "feedback")


class TestResolveIndexDirPure(unittest.TestCase):
    def test_config_directory_wins_over_the_defaults(self):
        config = {"project": {"planwise_root": "docs/pw", "lessons_dir": "Lessons2"}}
        self.assertEqual(
            config_loader.resolve_index_dir(config, "lessons", "planwise", "LessonsLearned"),
            "docs/pw/Lessons2",
        )

    def test_silent_config_falls_back_to_the_defaults(self):
        for config in ({}, {"project": None}, {"project": {"plans_dir": None, "planwise_root": ""}}):
            with self.subTest(config=config):
                self.assertEqual(
                    config_loader.resolve_index_dir(config, "plans", "planwise", "Plans"),
                    "planwise/Plans",
                )

    def test_each_family_reads_its_own_dir_key(self):
        config = {"project": {"plans_dir": "P", "backlog_dir": "B", "lessons_dir": "L"}}
        for family, expected in (("plans", "P"), ("backlog", "B"), ("lessons", "L")):
            with self.subTest(family=family):
                self.assertEqual(
                    config_loader.resolve_index_dir(config, family, "r", "d"), f"r/{expected}"
                )

    def test_unknown_family_raises_value_error(self):
        with self.assertRaises(ValueError):
            config_loader.resolve_index_dir({}, "feedback", "r", "d")


class _ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="resolve_index_name_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.cfg = InitConfig(
            project_name="resolve-index-fixture",
            project_root=self.tmp,
            plugin_root=Path(__file__).resolve().parent.parent / "plugins" / "planwise",
        )


class TestReadConfigMapping(_ProjectFixture):
    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(config_loader.read_config_mapping(self.config_path), {})

    def test_unparsable_file_returns_empty_dict(self):
        _require_yaml(self)
        self.config_path.write_text("project: [unclosed\n  - : :\n", encoding="utf-8")
        self.assertEqual(config_loader.read_config_mapping(self.config_path), {})

    def test_non_mapping_document_returns_empty_dict(self):
        _require_yaml(self)
        self.config_path.write_text("- a\n- b\n", encoding="utf-8")
        self.assertEqual(config_loader.read_config_mapping(self.config_path), {})

    def test_mapping_document_is_returned(self):
        _require_yaml(self)
        self.config_path.write_text("project:\n  name: X\n", encoding="utf-8")
        self.assertEqual(
            config_loader.read_config_mapping(self.config_path), {"project": {"name": "X"}}
        )


class TestResolveIndexTarget(_ProjectFixture):
    def test_missing_config_yields_the_cfg_directories_and_default_names(self):
        for family, dir_name in (("plans", "Plans"), ("backlog", "Backlog"), ("lessons", "LessonsLearned")):
            with self.subTest(family=family):
                self.assertEqual(
                    config_loader.resolve_index_target(self.cfg, family),
                    (f"planwise/{dir_name}", DEFAULTS[family]),
                )

    def test_null_blocks_in_config_yield_the_defaults(self):
        _require_yaml(self)
        for text in ("project:\n", "project:\n  index_files:\n", "project: scalar\n"):
            self.config_path.write_text(text, encoding="utf-8")
            for family, dir_name in (("plans", "Plans"), ("backlog", "Backlog"), ("lessons", "LessonsLearned")):
                with self.subTest(text=text, family=family):
                    self.assertEqual(
                        config_loader.resolve_index_target(self.cfg, family),
                        (f"planwise/{dir_name}", DEFAULTS[family]),
                    )

    def test_config_named_directory_wins_over_the_cfg_default(self):
        _require_yaml(self)
        self.config_path.write_text(
            "project:\n"
            "  planwise_root: planwise\n"
            "  plans_dir: PlansAlt\n"
            "  backlog_dir: BacklogAlt\n"
            "  lessons_dir: LessonsAlt\n"
            "  index_files:\n"
            "    lessons: Lessons-Hub.md\n",
            encoding="utf-8",
        )
        self.assertEqual(
            config_loader.resolve_index_target(self.cfg, "plans"),
            ("planwise/PlansAlt", DEFAULTS["plans"]),
        )
        self.assertEqual(
            config_loader.resolve_index_target(self.cfg, "backlog"),
            ("planwise/BacklogAlt", DEFAULTS["backlog"]),
        )
        self.assertEqual(
            config_loader.resolve_index_target(self.cfg, "lessons"),
            ("planwise/LessonsAlt", "Lessons-Hub.md"),
        )


class TestSeedLessonsIndexUsesConfigDirectory(_ProjectFixture):
    """The --upgrade backfill path seeds into the directory config.yaml names."""

    def test_backfill_lands_in_the_config_named_lessons_directory(self):
        _require_yaml(self)
        self.config_path.write_text(
            "project:\n  planwise_root: planwise\n  lessons_dir: LessonsAlt\n",
            encoding="utf-8",
        )

        results = lessons_bootstrap._seed_lessons_index(self.cfg)

        self.assertEqual([r for r, _ in results], [ConfigResult.CREATED] * 3)
        for _, rel in results:
            self.assertTrue(rel.startswith("planwise/LessonsAlt/"), rel)
            self.assertTrue((self.tmp / rel).exists(), rel)
        self.assertFalse((self.planwise_dir / "LessonsLearned").exists())

    def test_null_project_block_seeds_the_default_names_without_raising(self):
        _require_yaml(self)
        self.config_path.write_text("project:\n", encoding="utf-8")

        results = lessons_bootstrap._seed_lessons_index(self.cfg)

        names = {Path(rel).name for _, rel in results}
        self.assertEqual(
            names,
            {
                "00-Index-LessonsLearned.md",
                "00-Changelog-LessonsLearned.md",
                "00-PromotionLog-LessonsLearned.md",
            },
        )

    def test_null_index_files_block_seeds_the_default_names_without_raising(self):
        _require_yaml(self)
        self.config_path.write_text("project:\n  index_files:\n", encoding="utf-8")

        results = lessons_bootstrap._seed_lessons_index(self.cfg)

        self.assertEqual([r for r, _ in results], [ConfigResult.CREATED] * 3)
        self.assertTrue(
            (self.planwise_dir / "LessonsLearned" / "00-Index-LessonsLearned.md").exists()
        )


class TestRenderCategorizationFileNullBlocks(_ProjectFixture):
    """render_categorization_file shared the crashing lookup; every null shape
    now falls back to the default instead of raising."""

    def _assert_renders_at_default(self, config_text: str) -> None:
        _require_yaml(self)
        self.config_path.write_text(config_text, encoding="utf-8")

        result, rel = lessons_bootstrap.render_categorization_file(self.cfg)

        self.assertEqual(result, ConfigResult.CREATED_FROM_DEFAULT)
        self.assertEqual(rel, "planwise/LessonsLearned/00-Categorization-By-Domain.md")
        self.assertTrue((self.tmp / rel).exists())

    def test_null_project_block(self):
        self._assert_renders_at_default("project:\n")

    def test_null_index_files_block(self):
        self._assert_renders_at_default("project:\n  planwise_root: planwise\n  index_files:\n")

    def test_null_lessons_value(self):
        self._assert_renders_at_default(
            "project:\n  planwise_root: planwise\n  index_files:\n    lessons:\n"
        )

    def test_renders_into_the_config_named_lessons_directory(self):
        _require_yaml(self)
        self.config_path.write_text(
            "project:\n  planwise_root: planwise\n  lessons_dir: LessonsAlt\n",
            encoding="utf-8",
        )

        result, rel = lessons_bootstrap.render_categorization_file(self.cfg)

        self.assertEqual(result, ConfigResult.CREATED_FROM_DEFAULT)
        self.assertEqual(rel, "planwise/LessonsAlt/00-Categorization-By-Domain.md")
        self.assertTrue((self.tmp / rel).exists())


if __name__ == "__main__":
    unittest.main()
