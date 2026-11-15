#!/usr/bin/env python3
"""Unit tests for the plans-index keys `config_loader.load_config` resolves.

`_plans_index` is the plans index file: `{_plans_dir}/00-Index-Plans.md` by
default, or the name `project.index_files.plans` gives. `plan_statuses` is the
Master Plan `**Status:**` vocabulary: the project's own list when it states a
non-empty list of strings, else `DEFAULT_PLAN_STATUSES`. The template's
`plan_statuses:` block must equal that default, so a fresh project and an
unconfigured one agree.

Each test builds a temp planwise tree and loads it through `--config` injected
into `sys.argv`, the way `tests/test_reconcile_plans.py` does. None reads the
live project's config.

Run with:  python -m pytest tests/test_config_loader_plans.py -q
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

TEMPLATE = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "config.yaml.template"

EXPECTED_DEFAULT = [
    "NOT_STARTED",
    "PLANNING",
    "READY_TO_EXECUTE",
    "REVIEWED",
    "APPROVED",
    "NEEDS_FIXES",
    "IN_PROGRESS",
    "BLOCKED",
    "COMPLETE",
    "CLOSED",
]

BASE_YAML = """project:
  name: "PlansConfigFixture"
  plans_dir: "Plans"
"""


def template_plan_statuses(text: str) -> list[str]:
    block = config_gen.extract_top_level_block(text, "plan_statuses")
    if block is None:
        return []
    return re.findall(r"^\s*-\s*([A-Za-z_]+)\s*$", block, re.MULTILINE)


class _LoadedConfigCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="config_loader_plans_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.planwise_dir.mkdir(parents=True)

    def load(self, yaml_text: str) -> dict:
        config_file = self.planwise_dir / "config.yaml"
        config_file.write_text(yaml_text, encoding="utf-8")
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["test_config_loader_plans", "--config", str(config_file)]
        return config_loader.load_config()


class TestPlansIndexPath(_LoadedConfigCase):
    def test_default_is_the_plans_dir_index(self):
        config = self.load(BASE_YAML)
        self.assertEqual(config["_plans_index"], config["_plans_dir"] / "00-Index-Plans.md")

    def test_index_files_plans_overrides_the_filename(self):
        config = self.load(BASE_YAML + "  index_files:\n    plans: Custom.md\n")
        self.assertEqual(config["_plans_index"], config["_plans_dir"] / "Custom.md")

    def test_the_index_follows_a_custom_plans_dir(self):
        config = self.load('project:\n  name: "X"\n  plans_dir: "Work/Plans"\n')
        self.assertEqual(config["_plans_index"], self.planwise_dir / "Work" / "Plans" / "00-Index-Plans.md")

    def test_other_index_files_keys_do_not_move_the_plans_index(self):
        config = self.load(BASE_YAML + "  index_files:\n    backlog: B.md\n")
        self.assertEqual(config["_plans_index"].name, "00-Index-Plans.md")
        self.assertEqual(config["_index_path"].name, "B.md")

    def test_the_lessons_and_backlog_paths_are_unchanged(self):
        config = self.load(BASE_YAML + '  lessons_dir: "LL"\n')
        self.assertEqual(config["_index_path"].name, "00-Index-Backlog.md")
        self.assertEqual(config["_lessons_index"].name, "00-Index-LessonsLearned.md")


class TestPlanStatusesDefault(_LoadedConfigCase):
    def test_the_default_constant_holds_the_ten_values_in_order(self):
        self.assertEqual(list(config_loader.DEFAULT_PLAN_STATUSES), EXPECTED_DEFAULT)

    def test_an_absent_key_gets_the_default(self):
        config = self.load(BASE_YAML)
        self.assertEqual(config["plan_statuses"], list(config_loader.DEFAULT_PLAN_STATUSES))

    def test_a_project_list_replaces_the_default(self):
        config = self.load(BASE_YAML + "plan_statuses:\n  - DRAFT\n  - LIVE\n")
        self.assertEqual(config["plan_statuses"], ["DRAFT", "LIVE"])

    def test_a_project_list_that_extends_the_default_is_kept_whole(self):
        extended = EXPECTED_DEFAULT + ["PARKED"]
        config = self.load(BASE_YAML + "plan_statuses:\n" + "".join(f"  - {s}\n" for s in extended))
        self.assertEqual(config["plan_statuses"], extended)

    def test_an_empty_key_gets_the_default(self):
        config = self.load(BASE_YAML + "plan_statuses:\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)

    def test_an_empty_list_gets_the_default(self):
        config = self.load(BASE_YAML + "plan_statuses: []\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)

    def test_a_scalar_value_gets_the_default(self):
        config = self.load(BASE_YAML + "plan_statuses: COMPLETE\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)

    def test_a_list_with_a_non_string_gets_the_default(self):
        config = self.load(BASE_YAML + "plan_statuses:\n  - DRAFT\n  - 7\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)

    def warning_lines(self, yaml_text: str) -> tuple[dict, list[str]]:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            config = self.load(yaml_text)
        return config, stderr.getvalue().splitlines()

    def test_a_non_string_entry_prints_one_line_naming_the_key_and_the_entry(self):
        config, lines = self.warning_lines(BASE_YAML + "plan_statuses:\n  - DRAFT\n  - 7\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)
        self.assertEqual(len(lines), 1)
        self.assertIn("plan_statuses", lines[0])
        self.assertIn("7", lines[0])

    def test_a_bare_yaml_boolean_entry_is_named_in_the_warning(self):
        config, lines = self.warning_lines(BASE_YAML + "plan_statuses:\n  - DRAFT\n  - ON\n")
        self.assertEqual(config["plan_statuses"], EXPECTED_DEFAULT)
        self.assertEqual(len(lines), 1)
        self.assertIn("plan_statuses", lines[0])
        self.assertIn("True", lines[0])

    def test_a_valid_list_and_an_absent_key_print_nothing(self):
        for text in (BASE_YAML + "plan_statuses:\n  - DRAFT\n  - LIVE\n", BASE_YAML):
            with self.subTest(text=text):
                self.assertEqual(self.warning_lines(text)[1], [])

    def test_the_result_is_a_copy_not_the_module_constant(self):
        config = self.load(BASE_YAML)
        config["plan_statuses"].append("MUTATED")
        self.assertNotIn("MUTATED", config_loader.DEFAULT_PLAN_STATUSES)
        self.assertEqual(list(config_loader.DEFAULT_PLAN_STATUSES), EXPECTED_DEFAULT)

    def test_the_simple_parser_reads_the_list_when_pyyaml_is_absent(self):
        with mock.patch.object(config_loader, "HAS_YAML", False):
            config = self.load(BASE_YAML + "plan_statuses:\n  - DRAFT\n  - LIVE\n")
            self.assertEqual(config["plan_statuses"], ["DRAFT", "LIVE"])
            absent = self.load(BASE_YAML)
            self.assertEqual(absent["plan_statuses"], EXPECTED_DEFAULT)


class TestTemplateMatchesTheDefault(unittest.TestCase):
    def setUp(self):
        self.template_text = TEMPLATE.read_text(encoding="utf-8")

    def test_template_list_equals_the_default_constant(self):
        self.assertEqual(template_plan_statuses(self.template_text), list(config_loader.DEFAULT_PLAN_STATUSES))

    def test_template_key_appears_once_at_the_top_level(self):
        self.assertEqual(len(re.findall(r"^plan_statuses:", self.template_text, re.MULTILINE)), 1)

    def test_template_places_plan_statuses_after_lesson_statuses(self):
        text = self.template_text
        self.assertLess(text.index("\nlesson_statuses:"), text.index("\nplan_statuses:"))
        self.assertLess(text.index("\nplan_statuses:"), text.index("\nbuild_commands:"))

    def test_template_comment_names_all_three_vocabularies(self):
        block = config_gen.extract_top_level_block(self.template_text, "plan_statuses")
        self.assertIsNotNone(block)
        self.assertIn("IS read at run time", block)
        head = self.template_text.split("\nlesson_statuses:", 1)[0]
        for name in ("statuses:", "lesson_statuses:", "plan_statuses:"):
            self.assertIn(name, head)
        self.assertIn("Three status vocabularies", head)

    def test_extractor_fires_on_a_known_bad_template(self):
        """Direction dry-run: the same extractor must see a missing value."""
        mutated = self.template_text.replace("  - CLOSED\n\nbuild_commands:", "\nbuild_commands:", 1)
        self.assertEqual(template_plan_statuses(mutated), EXPECTED_DEFAULT[:-1])

    def test_the_extractor_sees_the_full_list_on_the_shipped_template(self):
        self.assertEqual(len(template_plan_statuses(self.template_text)), 10)


if __name__ == "__main__":
    unittest.main()
