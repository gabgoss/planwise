#!/usr/bin/env python3
"""Regression tests for the lessons-scaffolding bootstrap (init + upgrade).

Pins the contract: a single idempotent routine (bootstrap_lessons_artifacts)
seeds the lessons index AND renders 00-Categorization-By-Domain.md, is wired
into BOTH fresh init and _run_upgrade(), and never overwrites an existing
(possibly user-customised) file. The categorization file gates
/planwise lessons curate and promote-batch; the legacy fresh-init-only render
left upgrade-adopted projects without it, hard-gating those commands.

Run with:  python -m unittest scripts/test_lessons_bootstrap.py
"""

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether unittest is launched from the repo root
# (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import init_project as ip  # noqa: E402


# A minimal lessons-index seed file _seed_lessons_index copies from the plugin.
SEED_LESSONS_INDEX = "# Lessons Learned — Master Index\n\n| ID | Title |\n|----|-------|\n"

# A config.yaml.template carrying a context block (used by migrate_config in
# the _run_upgrade path). No `categorization:` block — the realistic
# upgrade-from-old shape, so the render falls back to DEFAULT_CATEGORIZATION.
TEMPLATE = """# Project Configuration
plugin_root: "{plugin-root}"
plugin_version: "{plugin-version}"
project:
  name: "{project-name}"
  install_scope: "{install-scope}"
  planwise_root: "{planwise-root}"
  plans_dir: "{plans-dir}"
  backlog_dir: "{backlog-dir}"
  lessons_dir: "{lessons-dir}"
  index_files:
    plans: "00-Index-Plans.md"
    backlog: "00-Index-Backlog.md"
    lessons: "00-Index-LessonsLearned.md"

context:
  plan_tier: "{plan-tier}"
  context_window: {context-window}

scoring:
  priority_high: 30
"""


class _BootstrapFixture(unittest.TestCase):
    """Temp project + a minimal plugin root carrying the seed index file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_lessons_bootstrap_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.planwise_dir = self.project_root / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_root.mkdir(parents=True, exist_ok=True)

        # Plugin seed dir + the lessons index seed _seed_lessons_index copies.
        seed_dir = self.plugin_root / "seed"
        seed_dir.mkdir(parents=True, exist_ok=True)
        (seed_dir / "00-Index-LessonsLearned.md").write_text(
            SEED_LESSONS_INDEX, encoding="utf-8"
        )

        # Plugin template (used by migrate_config in the _run_upgrade path).
        (self.plugin_root / "config.yaml.template").write_text(
            TEMPLATE, encoding="utf-8"
        )

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

    def cat_path(self) -> Path:
        return self.lessons_dir / "00-Categorization-By-Domain.md"

    def index_path(self) -> Path:
        return self.lessons_dir / "00-Index-LessonsLearned.md"

    def config_path(self) -> Path:
        return self.planwise_dir / "config.yaml"


class TestBootstrapRoutine(_BootstrapFixture):
    """bootstrap_lessons_artifacts is idempotent and non-destructive."""

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for render_categorization_file")

    def test_creates_both_when_missing(self):
        self.assertFalse(self.cat_path().exists())
        self.assertFalse(self.index_path().exists())

        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(
            boot.index_result,
            ip.ConfigResult.CREATED,
            "missing lessons index must be seeded",
        )
        self.assertIn(
            boot.cat_result,
            (ip.ConfigResult.CREATED, ip.ConfigResult.CREATED_FROM_DEFAULT),
            "missing categorization file must be rendered",
        )
        self.assertTrue(boot.created_any)
        self.assertTrue(self.cat_path().exists())
        self.assertTrue(self.index_path().exists())

    def test_idempotent_second_call_is_noop(self):
        ip.bootstrap_lessons_artifacts(self.cfg)
        cat_before = self.cat_path().read_text(encoding="utf-8")
        index_before = self.index_path().read_text(encoding="utf-8")

        boot2 = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot2.index_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertEqual(boot2.cat_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertFalse(
            boot2.created_any, "a second call must report nothing created"
        )
        self.assertEqual(self.cat_path().read_text(encoding="utf-8"), cat_before)
        self.assertEqual(
            self.index_path().read_text(encoding="utf-8"), index_before
        )

    def test_preserves_user_customised_files_verbatim(self):
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        custom_cat = "# MY HAND-EDITED CATEGORIZATION\n\nDo not touch.\n"
        custom_index = "# MY HAND-EDITED INDEX\n"
        self.cat_path().write_text(custom_cat, encoding="utf-8")
        self.index_path().write_text(custom_index, encoding="utf-8")

        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot.cat_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertEqual(boot.index_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertEqual(self.cat_path().read_text(encoding="utf-8"), custom_cat)
        self.assertEqual(
            self.index_path().read_text(encoding="utf-8"), custom_index
        )


class TestRunUpgradeBackfill(_BootstrapFixture):
    """_run_upgrade() backfills the categorization file on an upgrade-adopted
    project (the legacy fresh-init-only render never created it) and preserves
    an existing one."""

    _PINNED = "1.0.3"
    _TARGET = "1.0.4"

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for _run_upgrade")
        # upgrade_artifacts globs .claude/rules/planwise — create it empty so
        # the glob doesn't fail before the backfill runs (mirrors the sibling
        # _run_upgrade token-saver fixture).
        (self.project_root / ".claude" / "rules" / "planwise").mkdir(
            parents=True, exist_ok=True
        )

    def _write_upgrade_config(self):
        self.config_path().write_text(
            f'plugin_version: "{self._PINNED}"\n'
            "project:\n"
            "  name: FixtureProject\n"
            "  planwise_root: planwise\n"
            "  lessons_dir: LessonsLearned\n"
            "  index_files:\n"
            "    lessons: 00-Index-LessonsLearned.md\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n",
            encoding="utf-8",
        )

    def _cfg(self) -> ip.InitConfig:
        return ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self._TARGET,
        )

    @staticmethod
    def _run_silently(cfg: ip.InitConfig) -> int:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            return ip._run_upgrade(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    def test_upgrade_backfills_missing_categorization(self):
        self._write_upgrade_config()
        self.assertFalse(self.cat_path().exists())

        rc = self._run_silently(self._cfg())

        self.assertEqual(rc, 0, "_run_upgrade must succeed")
        self.assertTrue(
            self.cat_path().exists(),
            "upgrade must backfill 00-Categorization-By-Domain.md",
        )
        self.assertTrue(
            self.index_path().exists(),
            "upgrade must also seed the lessons index when missing",
        )

    def test_upgrade_preserves_existing_categorization(self):
        self._write_upgrade_config()
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        custom = "# USER CATEGORIZATION — keep me verbatim\n"
        self.cat_path().write_text(custom, encoding="utf-8")

        rc = self._run_silently(self._cfg())

        self.assertEqual(rc, 0)
        self.assertEqual(
            self.cat_path().read_text(encoding="utf-8"),
            custom,
            "upgrade must NOT overwrite an existing categorization file",
        )


if __name__ == "__main__":
    unittest.main()
