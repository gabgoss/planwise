#!/usr/bin/env python3
"""The lesson status vocabulary is declared once, in config, and the surfaces
that restate it cannot drift from it.

`config.yaml.template` carries `lesson_statuses:` (declarative — see its own
comment block); the seed lessons index defines what each value means; and
flip_lesson_status.py validates a flip against its own VALID tuple. These
tests are the cross-surface equality that keeps the three in agreement —
the state-detecting gate the config key promises, since no script reads the
key at run time.

Run with:  python -m unittest tests/test_lesson_statuses_config.py
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen  # noqa: E402
import flip_lesson_status  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
TEMPLATE = PLUGIN / "config.yaml.template"
SEED_INDEX = PLUGIN / "seed" / "00-Index-LessonsLearned.md"

DECLARED = ["documented", "promoted", "applied", "rule", "orphaned"]


def template_lesson_statuses(text: str) -> list[str]:
    block = config_gen.extract_top_level_block(text, "lesson_statuses")
    if block is None:
        return []
    return re.findall(r"^\s*-\s*([A-Za-z_]+)\s*$", block, re.MULTILINE)


def seed_status_table(text: str) -> list[str]:
    section = text.split("## Status Definitions", 1)[1].split("\n---", 1)[0]
    return re.findall(r"^\|\s*`([A-Za-z_]+)`\s*\|", section, re.MULTILINE)


class TestLessonStatusVocabulary(unittest.TestCase):
    def setUp(self):
        self.template_text = TEMPLATE.read_text(encoding="utf-8")
        self.seed_text = SEED_INDEX.read_text(encoding="utf-8")

    def test_template_declares_the_vocabulary(self):
        self.assertEqual(template_lesson_statuses(self.template_text), DECLARED)

    def test_template_places_lesson_statuses_beside_statuses(self):
        text = self.template_text
        self.assertLess(text.index("\nstatuses:"), text.index("\nlesson_statuses:"))
        self.assertLess(text.index("\nlesson_statuses:"), text.index("\nbuild_commands:"))

    def test_seed_table_and_template_agree(self):
        """The seed's Status Definitions table defines each value's meaning
        and defers to config for the list; the two sets must be equal."""
        self.assertEqual(set(seed_status_table(self.seed_text)), set(DECLARED))

    def test_flip_script_accepts_only_declared_values(self):
        self.assertTrue(
            set(flip_lesson_status.VALID) <= set(DECLARED),
            f"flip_lesson_status.VALID carries a value config does not declare: "
            f"{set(flip_lesson_status.VALID) - set(DECLARED)}",
        )

    def test_key_is_migrated_into_existing_configs(self):
        self.assertIn("lesson_statuses", config_gen.MIGRATABLE_TOP_LEVEL_KEYS)
        block = config_gen.extract_top_level_block(self.template_text, "lesson_statuses")
        self.assertIsNotNone(block)
        self.assertIn("lesson_statuses:", block)
        self.assertIn("DECLARATIVE", block, "the decision must travel with the key")

    def test_parser_fires_on_a_known_bad_template(self):
        """Direction dry-run: the same extractor must see a missing value."""
        mutated = self.template_text.replace("  - orphaned\n", "", 1)
        self.assertEqual(template_lesson_statuses(mutated), DECLARED[:-1])


if __name__ == "__main__":
    unittest.main()
