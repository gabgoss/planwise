#!/usr/bin/env python3
"""Unit tests for how `config_loader.load_config` reads the `project:` block.

A `config.yaml` whose `project:` key has no value parses to None, and one whose
value is a scalar parses to a str. Neither has `.get`, so `load_config` raised
AttributeError on both. It now reads the block through `_project_block`, so
either shape resolves to the default directory names, the same as an absent
key does.

The keys inside the block follow the same rule. A directory key that is null,
empty or not a string used to reach `planwise_root / None` and raise
TypeError. Each now falls back to its default, as does an index file name
and a document that is not a mapping.

Each test builds a temp planwise tree and loads it through the `config_path`
argument. None reads the live project's config.

Run with:  python -m pytest tests/test_config_loader_project_block.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader

VALID_PROJECT = """project:
  name: "ProjectBlockFixture"
  backlog_dir: "BacklogAlt"
  archive_dir: "BacklogAlt/Done"
  plans_dir: "PlansAlt"
  lessons_dir: "LessonsAlt"
  feedback_dir: "FeedbackAlt"
  index_files:
    backlog: Backlog-Hub.md
    plans: Plans-Hub.md
    lessons: Lessons-Hub.md
"""


class _LoadedConfigCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="config_loader_project_block_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.planwise_dir.mkdir(parents=True)

    def load(self, yaml_text: str) -> dict:
        config_file = self.planwise_dir / "config.yaml"
        config_file.write_text(yaml_text, encoding="utf-8")
        return config_loader.load_config(config_path=config_file)

    def assert_default_directories(self, config: dict) -> None:
        root = self.planwise_dir
        self.assertEqual(config["_backlog_dir"], root / "Backlog")
        self.assertEqual(config["_archive_dir"], root / "Backlog" / "Archive")
        self.assertEqual(config["_index_path"], root / "Backlog" / "00-Index-Backlog.md")
        self.assertEqual(config["_plans_dir"], root / "Plans")
        self.assertEqual(config["_plans_index"], root / "Plans" / "00-Index-Plans.md")
        self.assertIsNone(config["_lessons_dir"])
        self.assertIsNone(config["_lessons_index"])
        self.assertEqual(config["_feedback_dir"], root / "Feedback")


class TestNullProjectBlock(_LoadedConfigCase):
    def test_a_bare_project_key_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("project:\n"))

    def test_an_explicit_null_loads_with_the_default_directories(self):
        for text in ("project: null\n", "project: ~\n"):
            with self.subTest(text=text):
                self.assert_default_directories(self.load(text))

    def test_a_null_project_with_sibling_keys_still_loads_them(self):
        config = self.load("project:\nplan_statuses:\n  - DRAFT\n  - LIVE\n")
        self.assert_default_directories(config)
        self.assertEqual(config["plan_statuses"], ["DRAFT", "LIVE"])

    def test_a_null_project_prints_nothing_to_stderr(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.load("project:\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_the_simple_parser_loads_a_bare_project_key_when_pyyaml_is_absent(self):
        with mock.patch.object(config_loader, "HAS_YAML", False):
            self.assert_default_directories(self.load("project:\n"))


class TestScalarProjectBlock(_LoadedConfigCase):
    def test_a_string_project_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("project: planwise\n"))

    def test_a_list_project_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("project:\n  - planwise\n"))

    def test_a_number_project_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("project: 7\n"))


class TestAbsentProjectBlock(_LoadedConfigCase):
    def test_a_config_with_no_project_key_resolves_the_same_defaults(self):
        self.assert_default_directories(self.load("plan_statuses:\n  - DRAFT\n"))


class TestValidProjectBlock(_LoadedConfigCase):
    def test_every_directory_key_resolves_to_its_configured_path(self):
        config = self.load(VALID_PROJECT)
        root = self.planwise_dir
        self.assertEqual(config["_backlog_dir"], root / "BacklogAlt")
        self.assertEqual(config["_archive_dir"], root / "BacklogAlt" / "Done")
        self.assertEqual(config["_index_path"], root / "BacklogAlt" / "Backlog-Hub.md")
        self.assertEqual(config["_plans_dir"], root / "PlansAlt")
        self.assertEqual(config["_plans_index"], root / "PlansAlt" / "Plans-Hub.md")
        self.assertEqual(config["_lessons_dir"], root / "LessonsAlt")
        self.assertEqual(config["_lessons_index"], root / "LessonsAlt" / "Lessons-Hub.md")
        self.assertEqual(config["_feedback_dir"], root / "FeedbackAlt")

    def test_an_unset_archive_dir_follows_the_configured_backlog_dir(self):
        config = self.load('project:\n  name: "X"\n  backlog_dir: "BacklogAlt"\n')
        self.assertEqual(config["_archive_dir"], self.planwise_dir / "BacklogAlt" / "Archive")

    def test_a_valid_block_with_a_null_index_files_still_loads(self):
        config = self.load('project:\n  name: "X"\n  index_files:\n')
        self.assertEqual(config["_index_path"].name, "00-Index-Backlog.md")
        self.assertEqual(config["_plans_index"].name, "00-Index-Plans.md")


class TestUnusableDirectoryValues(_LoadedConfigCase):
    DIRECTORY_KEYS = ("backlog_dir", "archive_dir", "plans_dir", "lessons_dir", "feedback_dir")

    def test_a_null_directory_value_falls_back_to_the_default(self):
        for key in self.DIRECTORY_KEYS:
            with self.subTest(key=key):
                self.assert_default_directories(self.load(f"project:\n  {key}:\n"))

    def test_an_empty_directory_value_falls_back_to_the_default(self):
        for key in self.DIRECTORY_KEYS:
            with self.subTest(key=key):
                self.assert_default_directories(self.load(f'project:\n  {key}: ""\n'))

    def test_a_non_string_directory_value_falls_back_to_the_default(self):
        for key in self.DIRECTORY_KEYS:
            for value in ("7", "[a, b]", "true"):
                with self.subTest(key=key, value=value):
                    self.assert_default_directories(self.load(f"project:\n  {key}: {value}\n"))

    def test_one_null_directory_leaves_the_other_keys_in_force(self):
        config = self.load('project:\n  backlog_dir:\n  plans_dir: "PlansAlt"\n')
        self.assertEqual(config["_backlog_dir"], self.planwise_dir / "Backlog")
        self.assertEqual(config["_plans_dir"], self.planwise_dir / "PlansAlt")

    def test_a_null_backlog_dir_still_drives_the_default_archive_dir(self):
        config = self.load("project:\n  backlog_dir:\n")
        self.assertEqual(config["_archive_dir"], self.planwise_dir / "Backlog" / "Archive")


class TestUnusableIndexFileNames(_LoadedConfigCase):
    def test_a_null_index_file_entry_falls_back_to_the_default_name(self):
        config = self.load(
            'project:\n  lessons_dir: "LL"\n  index_files:\n    backlog:\n    plans:\n    lessons:\n'
        )
        self.assertEqual(config["_index_path"].name, "00-Index-Backlog.md")
        self.assertEqual(config["_plans_index"].name, "00-Index-Plans.md")
        self.assertEqual(config["_lessons_index"].name, "00-Index-LessonsLearned.md")

    def test_a_non_string_index_file_entry_falls_back_to_the_default_name(self):
        config = self.load("project:\n  index_files:\n    backlog: 7\n    plans: [a]\n")
        self.assertEqual(config["_index_path"].name, "00-Index-Backlog.md")
        self.assertEqual(config["_plans_index"].name, "00-Index-Plans.md")

    def test_a_scalar_index_files_block_falls_back_to_the_default_names(self):
        config = self.load("project:\n  index_files: Custom.md\n")
        self.assertEqual(config["_index_path"].name, "00-Index-Backlog.md")
        self.assertEqual(config["_plans_index"].name, "00-Index-Plans.md")


class TestNonMappingDocument(_LoadedConfigCase):
    def test_a_list_document_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("- a\n- b\n"))

    def test_a_scalar_document_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load("just text\n"))

    def test_an_empty_document_loads_with_the_default_directories(self):
        self.assert_default_directories(self.load(""))


class TestProjectNameWarning(_LoadedConfigCase):
    """The name check runs only when the config was found by upward search."""

    def load_by_search(self, yaml_text: str) -> tuple[dict, str]:
        config_file = self.planwise_dir / "config.yaml"
        config_file.write_text(yaml_text, encoding="utf-8")
        stderr = io.StringIO()
        with (
            mock.patch.object(config_loader, "_get_config_path_from_args", return_value=None),
            mock.patch.object(config_loader, "find_config_upward", return_value=config_file),
            contextlib.redirect_stderr(stderr),
        ):
            config = config_loader.load_config()
        return config, stderr.getvalue()

    def test_a_non_string_name_warns_instead_of_raising(self):
        config, warning = self.load_by_search("project:\n  name: 7\n")
        self.assert_default_directories(config)
        self.assertIn("project.name", warning)

    def test_a_null_project_block_warns_about_the_missing_name(self):
        config, warning = self.load_by_search("project:\n")
        self.assert_default_directories(config)
        self.assertIn("project.name", warning)

    def test_a_real_name_prints_no_name_warning(self):
        _, warning = self.load_by_search('project:\n  name: "Real"\n')
        self.assertNotIn("project.name", warning)


if __name__ == "__main__":
    unittest.main()
