#!/usr/bin/env python3
"""`plan_statuses` is a migratable top-level config key.

The plans index generator reads `plan_statuses:` at run time (it renders the
Status Legend from it), and the shipped `config.yaml.template` carries the
block. `config_gen.MIGRATABLE_TOP_LEVEL_KEYS` decides which template keys
`--migrate` adds to an existing project's config, so a key missing from that
list never reaches a project that predates it. These tests pin the key onto the
list beside `lesson_statuses`, and prove the merge adds a missing block and
leaves a customised one byte for byte.

Every test builds an isolated temp tree from the shipped template and none read
or mutate the live project's config.

Run with:  python -m pytest tests/test_plan_statuses_config.py -q
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import init_project as ip

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

DEFAULT_STATUSES = [
    "NOT_STARTED", "PLANNING", "READY_TO_EXECUTE", "REVIEWED", "APPROVED",
    "NEEDS_FIXES", "IN_PROGRESS", "BLOCKED", "COMPLETE", "CLOSED",
]

CONFIG_WITHOUT_THE_BLOCK = """# A project config written before plan_statuses existed.
project:
  name: "Sample"
  planwise_root: "planwise"
  plans_dir: "Plans"

lesson_statuses:
  - documented
  - promoted
"""

CONFIG_WITH_A_CUSTOM_BLOCK = """# A project config that customised its plan vocabulary.
project:
  name: "Sample"
  planwise_root: "planwise"
  plans_dir: "Plans"

# Our own plan lifecycle -- keep this comment.
plan_statuses:
  - DRAFT
  - SHIPPED
"""


class TestPlanStatusesIsMigratable(unittest.TestCase):
    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required for the config merge")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_plan_statuses_"))
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

    def test_the_key_sits_directly_after_lesson_statuses(self):
        keys = config_gen.MIGRATABLE_TOP_LEVEL_KEYS
        self.assertIn("plan_statuses", keys)
        self.assertEqual(keys.index("plan_statuses"), keys.index("lesson_statuses") + 1)

    def test_a_config_without_the_block_gains_it_through_migrate(self):
        self._write(CONFIG_WITHOUT_THE_BLOCK)
        _path, added, present = ip.migrate_config(self.cfg)
        self.assertIn("plan_statuses", added)
        self.assertIn("lesson_statuses", present)
        result = self._read()
        self.assertTrue(
            result.startswith(CONFIG_WITHOUT_THE_BLOCK),
            "the user's bytes survive and the block is appended",
        )
        self.assertEqual(yaml.safe_load(result)["plan_statuses"], DEFAULT_STATUSES)

    def test_a_custom_block_is_kept_byte_for_byte(self):
        self._write(CONFIG_WITH_A_CUSTOM_BLOCK)
        _path, added, present = ip.migrate_config(self.cfg)
        self.assertNotIn("plan_statuses", added)
        self.assertIn("plan_statuses", present)
        result = self._read()
        self.assertTrue(result.startswith(CONFIG_WITH_A_CUSTOM_BLOCK))
        self.assertEqual(
            len(re.findall(r"^plan_statuses:", result, re.MULTILINE)),
            1,
            "the template block must not be appended beside it",
        )
        self.assertEqual(yaml.safe_load(result)["plan_statuses"], ["DRAFT", "SHIPPED"])

    def test_a_second_migrate_changes_nothing(self):
        self._write(CONFIG_WITHOUT_THE_BLOCK)
        ip.migrate_config(self.cfg)
        once = self._read()
        _path, added, _present = ip.migrate_config(self.cfg)
        self.assertNotIn("plan_statuses", added)
        self.assertEqual(self._read(), once)


if __name__ == "__main__":
    unittest.main()
