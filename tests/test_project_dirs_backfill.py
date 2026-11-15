#!/usr/bin/env python3
"""Tests for the upgrade backfill of the `project:` path keys.

`project` is not one of MIGRATABLE_TOP_LEVEL_KEYS, so `migrate_config()` never
adds a key inside it. A config that predates `planwise_root`, `plans_dir` or
`backlog_dir` therefore kept resolving those folders through the config
loader's silent defaults. `config_gen.merge_project_subkeys()` is the pure text
edit that writes the missing keys, and `config_gen.backfill_project_dirs()` is
the file-level helper that `/planwise upgrade` (both exits of `_run_upgrade`)
and `init --migrate` call.

Pinned here:
  - missing keys are added with the values the loader already resolves, so the
    edit changes no resolved folder;
  - an existing key is never overwritten, and a second run is byte-identical;
  - comments, blank lines and key order survive (a text edit, not a YAML dump);
  - `feedback_dir`, `lessons_dir` and `archive_dir` are not added by this helper;
  - a config with no multi-line `project:` block is left untouched;
  - the helper is wired into both exits of `_run_upgrade` and into `--migrate`.

Run with:  python -m pytest tests/test_project_dirs_backfill.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import config_gen
import config_loader
import init_project as ip

try:
    import yaml

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False

PROJECT_LACKING_ALL = (
    "# header comment\n"
    "project:\n"
    '  name: "Fixture"\n'
    "  # keep this comment\n"
    "  index_files:\n"
    "    backlog: 00-Index-Backlog.md\n"
    "\n"
    "context:\n"
    "  plan_tier: pro\n"
)

ADDED_ALL = [
    "project.planwise_root",
    "project.plans_dir",
    "project.backlog_dir",
]


class TestMergeProjectSubkeys(unittest.TestCase):
    def test_adds_all_three_keys_at_the_end_of_the_block(self):
        merged, added = config_gen.merge_project_subkeys(PROJECT_LACKING_ALL, "planwise")

        self.assertEqual(added, ADDED_ALL)
        self.assertEqual(
            merged,
            "# header comment\n"
            "project:\n"
            '  name: "Fixture"\n'
            "  # keep this comment\n"
            "  index_files:\n"
            "    backlog: 00-Index-Backlog.md\n"
            '  planwise_root: "planwise"\n'
            '  plans_dir: "Plans"\n'
            '  backlog_dir: "Backlog"\n'
            "\n"
            "context:\n"
            "  plan_tier: pro\n",
        )

    def test_the_value_for_planwise_root_is_the_folder_the_caller_names(self):
        merged, _added = config_gen.merge_project_subkeys(PROJECT_LACKING_ALL, "docs-planning")

        self.assertIn('  planwise_root: "docs-planning"\n', merged)

    def test_a_second_run_adds_nothing_and_returns_identical_text(self):
        once, _ = config_gen.merge_project_subkeys(PROJECT_LACKING_ALL, "planwise")

        twice, added = config_gen.merge_project_subkeys(once, "planwise")

        self.assertEqual(added, [])
        self.assertEqual(twice, once)

    def test_an_existing_key_is_never_overwritten(self):
        text = (
            "project:\n"
            '  name: "Fixture"\n'
            "  backlog_dir: Tasks\n"
            '  plans_dir: "Roadmaps"\n'
        )

        merged, added = config_gen.merge_project_subkeys(text, "planwise")

        self.assertEqual(added, ["project.planwise_root"])
        self.assertIn("  backlog_dir: Tasks\n", merged)
        self.assertIn('  plans_dir: "Roadmaps"\n', merged)
        self.assertNotIn('"Backlog"', merged)
        self.assertNotIn('"Plans"', merged)

    def test_a_key_that_is_present_with_an_empty_value_is_left_alone(self):
        text = "project:\n  name: x\n  backlog_dir:\n  plans_dir: Plans\n  planwise_root: planwise\n"

        merged, added = config_gen.merge_project_subkeys(text, "planwise")

        self.assertEqual(added, [])
        self.assertEqual(merged, text)

    def test_a_deeper_indented_key_of_the_same_name_does_not_count_as_present(self):
        text = (
            "project:\n"
            "  name: x\n"
            "  index_files:\n"
            "    backlog_dir: nested\n"
            "  plans_dir: Plans\n"
            "  planwise_root: planwise\n"
        )

        merged, added = config_gen.merge_project_subkeys(text, "planwise")

        self.assertEqual(added, ["project.backlog_dir"])
        self.assertIn('  backlog_dir: "Backlog"\n', merged)
        self.assertIn("    backlog_dir: nested\n", merged)

    def test_feedback_lessons_and_archive_dirs_are_not_added(self):
        merged, _added = config_gen.merge_project_subkeys(PROJECT_LACKING_ALL, "planwise")

        self.assertNotIn("feedback_dir", merged)
        self.assertNotIn("lessons_dir", merged)
        self.assertNotIn("archive_dir", merged)

    def test_the_merged_text_still_parses_and_keeps_every_original_value(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required")
        merged, _added = config_gen.merge_project_subkeys(PROJECT_LACKING_ALL, "planwise")

        before = yaml.safe_load(PROJECT_LACKING_ALL)
        after = yaml.safe_load(merged)

        for key, value in before["project"].items():
            self.assertEqual(after["project"][key], value)
        self.assertEqual(after["context"], before["context"])

    def test_no_project_block_leaves_the_text_untouched(self):
        text = 'plugin_version: "1.0.0"\ncontext:\n  plan_tier: pro\n'

        merged, added = config_gen.merge_project_subkeys(text, "planwise")

        self.assertEqual((merged, added), (text, []))

    def test_an_inline_flow_project_mapping_is_left_untouched(self):
        text = 'project: {name: "Fixture"}\ncontext:\n  plan_tier: pro\n'

        merged, added = config_gen.merge_project_subkeys(text, "planwise")

        self.assertEqual((merged, added), (text, []))


class _ProjectFixtureBase(unittest.TestCase):
    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_project_dirs_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        self.planwise_dir = self.project_root / "planwise"
        self.planwise_dir.mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.cfg = ip.InitConfig(
            project_name="Fixture",
            project_root=self.project_root,
            plugin_root=Path(ip.__file__).resolve().parent.parent,
            plugin_version="0.0.0",
        )

    def write_config(self, text: str) -> None:
        self.config_path.write_text(text, encoding="utf-8")

    def read_bytes(self) -> bytes:
        return self.config_path.read_bytes()


class TestBackfillProjectDirs(_ProjectFixtureBase):
    def test_it_writes_the_keys_and_names_them_in_the_notice(self):
        self.write_config(PROJECT_LACKING_ALL)

        notice = config_gen.backfill_project_dirs(self.cfg, self.config_path)

        self.assertIsNotNone(notice)
        for key in ADDED_ALL:
            self.assertIn(key, notice)
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["backlog_dir"], "Backlog")
        self.assertEqual(data["project"]["plans_dir"], "Plans")
        self.assertEqual(data["project"]["planwise_root"], "planwise")

    def test_a_second_run_returns_none_and_leaves_the_bytes_alone(self):
        self.write_config(PROJECT_LACKING_ALL)
        config_gen.backfill_project_dirs(self.cfg, self.config_path)
        after_first = self.read_bytes()

        notice = config_gen.backfill_project_dirs(self.cfg, self.config_path)

        self.assertIsNone(notice)
        self.assertEqual(self.read_bytes(), after_first)

    def test_a_config_that_already_has_every_key_is_not_rewritten(self):
        text = (
            "project:\n"
            '  planwise_root: "planwise"\n'
            '  plans_dir: "Plans"\n'
            '  backlog_dir: "Backlog"\n'
        )
        self.write_config(text)
        before = self.read_bytes()

        notice = config_gen.backfill_project_dirs(self.cfg, self.config_path)

        self.assertIsNone(notice)
        self.assertEqual(self.read_bytes(), before)

    def test_a_missing_config_returns_none(self):
        self.assertIsNone(config_gen.backfill_project_dirs(self.cfg, self.config_path))
        self.assertFalse(self.config_path.exists())

    def test_the_edit_changes_no_folder_the_loader_resolves(self):
        self.write_config('project:\n  name: "Fixture"\n')
        keys = ("_planwise_root", "_backlog_dir", "_archive_dir", "_plans_dir", "_feedback_dir")
        before = config_loader.load_config(config_path=self.config_path)

        notice = config_gen.backfill_project_dirs(self.cfg, self.config_path)
        after = config_loader.load_config(config_path=self.config_path)

        self.assertIsNotNone(notice)
        for key in keys:
            self.assertEqual(after[key], before[key], key)

    def test_the_loader_and_the_backfill_read_one_defaults_table(self):
        self.assertEqual(config_loader.PROJECT_DIR_DEFAULTS["backlog_dir"], "Backlog")
        self.assertEqual(config_loader.PROJECT_DIR_DEFAULTS["plans_dir"], "Plans")
        self.assertIs(config_gen.PROJECT_DIR_DEFAULTS, config_loader.PROJECT_DIR_DEFAULTS)


class TestInitMigrateWiring(_ProjectFixtureBase):
    def test_migrate_adds_the_keys_and_prints_the_notice(self):
        self.write_config(PROJECT_LACKING_ALL)
        buf = io.StringIO()

        with contextlib.redirect_stdout(buf):
            code = ip._run_migrate(self.cfg)

        self.assertEqual(code, 0)
        self.assertIn("Project directories: added project.planwise_root", buf.getvalue())
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["backlog_dir"], "Backlog")


class TestUpgradeWiring(_ProjectFixtureBase):
    """Both exits of `_run_upgrade` call the backfill: the real upgrade and the
    already-up-to-date early return."""

    LIVE_VERSION = "1.1.0"
    OLD_VERSION = "1.0.0"

    def setUp(self):
        super().setUp()
        self.plugin_root = self.tmp / "plugin-cache" / self.LIVE_VERSION
        (self.plugin_root / ".claude-plugin").mkdir(parents=True)
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": self.LIVE_VERSION}), encoding="utf-8"
        )
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))
        self.cfg = ip.InitConfig(
            project_name="Fixture",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self.LIVE_VERSION,
        )
        patch = mock.patch.object(artifact_upgrade, "INSTALLED_RULES", [])
        patch.start()
        self.addCleanup(patch.stop)

    def config_text(self, version: str) -> str:
        root = str(self.plugin_root).replace("\\", "/")
        return (
            f'plugin_root: "{root}"\n'
            f'plugin_version: "{version}"\n'
            "project:\n"
            '  name: "Fixture"\n'
            "  lessons_dir: LessonsLearned\n"
        )

    def run_upgrade(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ip._run_upgrade(self.cfg)
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_a_real_upgrade_backfills_the_keys(self):
        self.write_config(self.config_text(self.OLD_VERSION))

        out = self.run_upgrade()

        self.assertIn("Project directories: added", out)
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["planwise_root"], "planwise")
        self.assertEqual(data["project"]["plans_dir"], "Plans")
        self.assertEqual(data["project"]["backlog_dir"], "Backlog")
        self.assertEqual(data["plugin_version"], self.LIVE_VERSION)

    def test_the_already_up_to_date_branch_backfills_the_keys_too(self):
        self.write_config(self.config_text(self.LIVE_VERSION))

        out = self.run_upgrade()

        self.assertIn("Already up to date.", out)
        self.assertIn("Project directories: added", out)
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["backlog_dir"], "Backlog")

    def test_a_second_upgrade_is_silent_and_changes_no_bytes(self):
        self.write_config(self.config_text(self.OLD_VERSION))
        self.run_upgrade()
        after_first = self.read_bytes()

        out = self.run_upgrade()

        self.assertNotIn("Project directories:", out)
        self.assertEqual(self.read_bytes(), after_first)


if __name__ == "__main__":
    unittest.main()
