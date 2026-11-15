#!/usr/bin/env python3
"""`lesson_check_kinds` is a declared, defaulted and migratable top-level key.

The key lists the kinds a lesson's `enforced-by:` answer may name. These tests
pin three surfaces to each other: the loader default
(`config_loader.DEFAULT_LESSON_CHECK_KINDS`), the shipped `config.yaml.template`
block, and `config_gen.MIGRATABLE_TOP_LEVEL_KEYS`, which decides whether
`--migrate` copies the block into an existing project's config.

Each test builds a temp tree and none reads or mutates the live project's config.

Run with:  python -m pytest tests/test_lesson_check_kinds_config.py -q
"""

import contextlib
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import config_loader
import init_project as ip

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
TEMPLATE = PLUGIN / "config.yaml.template"

EXPECTED_DEFAULT = ["hook", "test", "lint", "script"]

BASE_YAML = """project:
  name: "CheckKindsFixture"
  plans_dir: "Plans"
"""

CONFIG_WITHOUT_THE_BLOCK = """# A project config written before lesson_check_kinds existed.
project:
  name: "Sample"
  planwise_root: "planwise"
  plans_dir: "Plans"

lesson_statuses:
  - documented
  - promoted
"""

CONFIG_WITH_A_CUSTOM_BLOCK = """# A project config that customised its check kinds.
project:
  name: "Sample"
  planwise_root: "planwise"
  plans_dir: "Plans"

# Our own kinds -- keep this comment.
lesson_check_kinds:
  - hook
  - review
"""


def template_kinds(text: str) -> list[str]:
    block = config_gen.extract_top_level_block(text, "lesson_check_kinds")
    if block is None:
        return []
    return re.findall(r"^\s*-\s*([A-Za-z_]+)\s*$", block, re.MULTILINE)


class TestLessonCheckKindsDefault(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="config_loader_kinds_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.planwise_dir.mkdir(parents=True)

    def load(self, yaml_text: str) -> dict:
        config_file = self.planwise_dir / "config.yaml"
        config_file.write_text(yaml_text, encoding="utf-8")
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["test_lesson_check_kinds_config", "--config", str(config_file)]
        return config_loader.load_config()

    def warning_lines(self, yaml_text: str) -> tuple[dict, list[str]]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            config = self.load(yaml_text)
        return config, stderr.getvalue().splitlines()

    def test_the_default_constant_holds_the_four_values_in_order(self):
        self.assertEqual(list(config_loader.DEFAULT_LESSON_CHECK_KINDS), EXPECTED_DEFAULT)

    def test_an_absent_key_gets_the_default(self):
        config = self.load(BASE_YAML)
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_a_project_list_replaces_the_default(self):
        config = self.load(BASE_YAML + "lesson_check_kinds:\n  - review\n  - audit\n")
        self.assertEqual(config["lesson_check_kinds"], ["review", "audit"])

    def test_a_project_list_that_extends_the_default_is_kept_whole(self):
        extended = EXPECTED_DEFAULT + ["review"]
        config = self.load(BASE_YAML + "lesson_check_kinds:\n" + "".join(f"  - {k}\n" for k in extended))
        self.assertEqual(config["lesson_check_kinds"], extended)

    def test_an_empty_key_gets_the_default(self):
        config = self.load(BASE_YAML + "lesson_check_kinds:\n")
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_an_empty_list_gets_the_default(self):
        config = self.load(BASE_YAML + "lesson_check_kinds: []\n")
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_a_scalar_value_gets_the_default(self):
        config = self.load(BASE_YAML + "lesson_check_kinds: hook\n")
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_a_list_with_a_non_string_gets_the_default(self):
        config = self.load(BASE_YAML + "lesson_check_kinds:\n  - hook\n  - 7\n")
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_a_non_string_entry_prints_one_line_naming_the_key_and_the_entry(self):
        config, lines = self.warning_lines(BASE_YAML + "lesson_check_kinds:\n  - hook\n  - 7\n")
        self.assertEqual(config["lesson_check_kinds"], EXPECTED_DEFAULT)
        self.assertEqual(len(lines), 1)
        self.assertIn("lesson_check_kinds", lines[0])
        self.assertIn("7", lines[0])

    def test_a_valid_list_and_an_absent_key_print_nothing(self):
        for text in (BASE_YAML + "lesson_check_kinds:\n  - hook\n  - review\n", BASE_YAML):
            with self.subTest(text=text):
                self.assertEqual(self.warning_lines(text)[1], [])

    def test_the_result_is_a_copy_not_the_module_constant(self):
        config = self.load(BASE_YAML)
        config["lesson_check_kinds"].append("MUTATED")
        self.assertNotIn("MUTATED", config_loader.DEFAULT_LESSON_CHECK_KINDS)
        self.assertEqual(list(config_loader.DEFAULT_LESSON_CHECK_KINDS), EXPECTED_DEFAULT)

    def test_the_simple_parser_reads_the_list_when_pyyaml_is_absent(self):
        with mock.patch.object(config_loader, "HAS_YAML", False):
            config = self.load(BASE_YAML + "lesson_check_kinds:\n  - hook\n  - review\n")
            self.assertEqual(config["lesson_check_kinds"], ["hook", "review"])
            absent = self.load(BASE_YAML)
            self.assertEqual(absent["lesson_check_kinds"], EXPECTED_DEFAULT)


class TestTemplateDeclaresTheKinds(unittest.TestCase):
    def setUp(self):
        self.template_text = TEMPLATE.read_text(encoding="utf-8")

    def test_template_list_equals_the_default_constant(self):
        self.assertEqual(template_kinds(self.template_text), list(config_loader.DEFAULT_LESSON_CHECK_KINDS))

    def test_template_key_appears_once_at_the_top_level(self):
        self.assertEqual(len(re.findall(r"^lesson_check_kinds:", self.template_text, re.MULTILINE)), 1)

    def test_template_places_the_key_between_lesson_statuses_and_plan_statuses(self):
        text = self.template_text
        self.assertLess(text.index("\nlesson_statuses:"), text.index("\nlesson_check_kinds:"))
        self.assertLess(text.index("\nlesson_check_kinds:"), text.index("\nplan_statuses:"))

    def test_template_comment_says_the_key_is_read_at_run_time(self):
        block = config_gen.extract_top_level_block(self.template_text, "lesson_check_kinds")
        self.assertIsNotNone(block)
        self.assertIn("IS read at run time", block)

    def test_extractor_fires_on_a_known_bad_template(self):
        """Direction dry-run: the same extractor must see a missing value."""
        self.assertIn("  - script\n", self.template_text)
        mutated = self.template_text.replace("  - script\n", "", 1)
        self.assertEqual(len(template_kinds(mutated)), 3)


class TestLessonCheckKindsIsMigratable(unittest.TestCase):
    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required for the config merge")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_lesson_check_kinds_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        (self.project_root / "planwise").mkdir(parents=True)
        self.cfg = ip.InitConfig(
            project_name="Sample",
            project_root=self.project_root,
            plugin_root=PLUGIN,
        )
        self.config_path = self.project_root / "planwise" / "config.yaml"

    def _write(self, text: str) -> None:
        self.config_path.write_text(text, encoding="utf-8")

    def _read(self) -> str:
        return self.config_path.read_text(encoding="utf-8")

    def test_the_key_sits_directly_after_plan_statuses(self):
        keys = config_gen.MIGRATABLE_TOP_LEVEL_KEYS
        self.assertIn("lesson_check_kinds", keys)
        self.assertEqual(keys.index("lesson_check_kinds"), keys.index("plan_statuses") + 1)

    def test_a_config_without_the_block_gains_it_through_migrate(self):
        self._write(CONFIG_WITHOUT_THE_BLOCK)
        _path, added, present = ip.migrate_config(self.cfg)
        self.assertIn("lesson_check_kinds", added)
        self.assertIn("lesson_statuses", present)
        result = self._read()
        self.assertTrue(
            result.startswith(CONFIG_WITHOUT_THE_BLOCK),
            "the user's bytes survive and the block is appended",
        )
        self.assertEqual(yaml.safe_load(result)["lesson_check_kinds"], EXPECTED_DEFAULT)

    def test_a_custom_block_is_kept_byte_for_byte(self):
        self._write(CONFIG_WITH_A_CUSTOM_BLOCK)
        _path, added, present = ip.migrate_config(self.cfg)
        self.assertNotIn("lesson_check_kinds", added)
        self.assertIn("lesson_check_kinds", present)
        result = self._read()
        self.assertTrue(result.startswith(CONFIG_WITH_A_CUSTOM_BLOCK))
        self.assertEqual(
            len(re.findall(r"^lesson_check_kinds:", result, re.MULTILINE)),
            1,
            "the template block must not be appended beside it",
        )
        self.assertEqual(yaml.safe_load(result)["lesson_check_kinds"], ["hook", "review"])

    def test_a_second_migrate_changes_nothing(self):
        self._write(CONFIG_WITHOUT_THE_BLOCK)
        ip.migrate_config(self.cfg)
        once = self._read()
        _path, added, _present = ip.migrate_config(self.cfg)
        self.assertNotIn("lesson_check_kinds", added)
        self.assertEqual(self._read(), once)


if __name__ == "__main__":
    unittest.main()
