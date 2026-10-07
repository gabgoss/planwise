#!/usr/bin/env python3
"""Regression tests for the lessons-scaffolding bootstrap (init + upgrade).

Pins the contract: a single idempotent routine (bootstrap_lessons_artifacts)
seeds the lessons index AND renders 00-Categorization-By-Domain.md, is wired
into BOTH fresh init and _run_upgrade(), and never overwrites an existing
(possibly user-customised) file. The categorization file gates
/planwise lessons curate and promote-batch; the legacy fresh-init-only render
left upgrade-adopted projects without it, hard-gating those commands.

The categorization render itself goes through
`generate_lessons_index.render_companion_file` (called as a library with an
empty lesson set), not a hand-rolled bucket-table builder, so the seeded
file is the generator's own zero-lesson shape: bucket/sub-bucket headings
each carrying `(0)`, a `Generated:` line, a `**Companion to:**` line, and
the `[Notes](...)`/`[Changelog](...)` footer pointers.

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
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip

# A minimal lessons-index seed file _seed_lessons_index copies from the plugin.
SEED_LESSONS_INDEX = "# Lessons Learned — Master Index\n\n| ID | Title |\n|----|-------|\n"

# The lessons index's two companion seed openers _seed_lessons_index also
# copies, byte-built the same minimal way as SEED_LESSONS_INDEX above.
SEED_LESSONS_CHANGELOG = "[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)\n"
SEED_LESSONS_PROMOTION_LOG = (
    "[← 00-Index-LessonsLearned.md](00-Index-LessonsLearned.md)\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n"
    "|---|---|---|---|\n"
)

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
        (seed_dir / "00-Changelog-LessonsLearned.md").write_text(
            SEED_LESSONS_CHANGELOG, encoding="utf-8"
        )
        (seed_dir / "00-PromotionLog-LessonsLearned.md").write_text(
            SEED_LESSONS_PROMOTION_LOG, encoding="utf-8"
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

    def changelog_path(self) -> Path:
        return self.lessons_dir / "00-Changelog-LessonsLearned.md"

    def promotion_log_path(self) -> Path:
        return self.lessons_dir / "00-PromotionLog-LessonsLearned.md"

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
            [result for result, _ in boot.index_results],
            [ip.ConfigResult.CREATED] * 3,
            "missing lessons index and both companions must be seeded",
        )
        self.assertIn(
            boot.cat_result,
            (ip.ConfigResult.CREATED, ip.ConfigResult.CREATED_FROM_DEFAULT),
            "missing categorization file must be rendered",
        )
        self.assertTrue(boot.created_any)
        self.assertTrue(self.cat_path().exists())
        self.assertTrue(self.index_path().exists())
        self.assertTrue(self.changelog_path().exists())
        self.assertTrue(self.promotion_log_path().exists())

    def test_rendered_companion_is_the_generator_zero_lesson_shape(self):
        """The seeded file goes through render_companion_file, not a
        hand-rolled builder: every DEFAULT_CATEGORIZATION bucket heading
        carries `(0)`, plus the generated header/footer furniture."""
        ip.bootstrap_lessons_artifacts(self.cfg)
        content = self.cat_path().read_text(encoding="utf-8")

        self.assertIn("Generated:", content)
        self.assertIn("**Companion to:**", content)
        for bucket_id, bucket_name in (
            ("A", "Database / SQL"),
            ("B", "Application Code"),
            ("C", "Planwise / Process"),
            ("D", "Tooling / Ergonomics"),
        ):
            self.assertIn(f"## {bucket_id}. {bucket_name} (0)", content)
        self.assertIn("[Notes](00-Categorization-Notes-LessonsLearned.md)", content)
        self.assertIn("[Changelog](00-Changelog-LessonsLearned.md)", content)
        # The old hand-rolled shape is gone: no header bump line or
        # curate-populated placeholder text.
        self.assertNotIn("**Last Updated:**", content)
        self.assertNotIn("Cross-cutting observations", content)

    def test_idempotent_second_call_is_noop(self):
        ip.bootstrap_lessons_artifacts(self.cfg)
        cat_before = self.cat_path().read_text(encoding="utf-8")
        index_before = self.index_path().read_text(encoding="utf-8")
        changelog_before = self.changelog_path().read_text(encoding="utf-8")
        promotion_log_before = self.promotion_log_path().read_text(encoding="utf-8")

        boot2 = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(
            [result for result, _ in boot2.index_results],
            [ip.ConfigResult.SKIPPED_EXISTS] * 3,
        )
        self.assertEqual(boot2.cat_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertFalse(
            boot2.created_any, "a second call must report nothing created"
        )
        self.assertEqual(self.cat_path().read_text(encoding="utf-8"), cat_before)
        self.assertEqual(
            self.index_path().read_text(encoding="utf-8"), index_before
        )
        self.assertEqual(
            self.changelog_path().read_text(encoding="utf-8"), changelog_before
        )
        self.assertEqual(
            self.promotion_log_path().read_text(encoding="utf-8"),
            promotion_log_before,
        )

    def test_backfills_only_the_missing_companion(self):
        """A project that already has the index and changelog, but not the
        promotion log (adopted before this seed existed), backfills only
        the missing file — never touches the two that already exist."""
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        custom_index = "# PRE-EXISTING INDEX\n"
        custom_changelog = "# PRE-EXISTING CHANGELOG\n"
        self.index_path().write_text(custom_index, encoding="utf-8")
        self.changelog_path().write_text(custom_changelog, encoding="utf-8")
        self.assertFalse(self.promotion_log_path().exists())

        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        results_by_name = {
            Path(rel).name: result for result, rel in boot.index_results
        }
        self.assertEqual(
            results_by_name["00-Index-LessonsLearned.md"],
            ip.ConfigResult.SKIPPED_EXISTS,
        )
        self.assertEqual(
            results_by_name["00-Changelog-LessonsLearned.md"],
            ip.ConfigResult.SKIPPED_EXISTS,
        )
        self.assertEqual(
            results_by_name["00-PromotionLog-LessonsLearned.md"],
            ip.ConfigResult.CREATED,
        )
        self.assertTrue(boot.created_any)
        self.assertEqual(self.index_path().read_text(encoding="utf-8"), custom_index)
        self.assertEqual(
            self.changelog_path().read_text(encoding="utf-8"), custom_changelog
        )
        self.assertTrue(self.promotion_log_path().exists())

    def test_preserves_user_customised_files_verbatim(self):
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        custom_cat = "# MY HAND-EDITED CATEGORIZATION\n\nDo not touch.\n"
        custom_index = "# MY HAND-EDITED INDEX\n"
        custom_changelog = "# MY HAND-EDITED CHANGELOG\n"
        custom_promotion_log = "# MY HAND-EDITED PROMOTION LOG\n"
        self.cat_path().write_text(custom_cat, encoding="utf-8")
        self.index_path().write_text(custom_index, encoding="utf-8")
        self.changelog_path().write_text(custom_changelog, encoding="utf-8")
        self.promotion_log_path().write_text(custom_promotion_log, encoding="utf-8")

        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot.cat_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertEqual(
            [result for result, _ in boot.index_results],
            [ip.ConfigResult.SKIPPED_EXISTS] * 3,
        )
        self.assertEqual(self.cat_path().read_text(encoding="utf-8"), custom_cat)
        self.assertEqual(
            self.index_path().read_text(encoding="utf-8"), custom_index
        )
        self.assertEqual(
            self.changelog_path().read_text(encoding="utf-8"), custom_changelog
        )
        self.assertEqual(
            self.promotion_log_path().read_text(encoding="utf-8"),
            custom_promotion_log,
        )


class TestSeedLessonsIndexCustomHubName(_BootstrapFixture):
    """_seed_lessons_index derives its two companion filenames from the
    project's configured `index_files.lessons`, through the generator's own
    naming helpers — never the fixed `00-Changelog-LessonsLearned.md` /
    `00-PromotionLog-LessonsLearned.md` pair. Regression for a project that
    sets a custom hub name: before the fix, the companions were always
    seeded under the fixed default names regardless of what config.yaml
    named the hub."""

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for config_loader.resolve_index_target")
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.config_path().write_text(
            "project:\n"
            "  planwise_root: planwise\n"
            "  lessons_dir: LessonsLearned\n"
            "  index_files:\n"
            "    lessons: 00-Index-MyLessons.md\n",
            encoding="utf-8",
        )

    def test_companions_named_from_custom_hub(self):
        results = ip._seed_lessons_index(self.cfg)

        names = {Path(rel).name for _, rel in results}
        self.assertEqual(
            names,
            {
                "00-Index-MyLessons.md",
                "00-Changelog-MyLessons.md",
                "00-PromotionLog-MyLessons.md",
            },
        )
        self.assertTrue((self.lessons_dir / "00-Index-MyLessons.md").exists())
        self.assertTrue((self.lessons_dir / "00-Changelog-MyLessons.md").exists())
        self.assertTrue((self.lessons_dir / "00-PromotionLog-MyLessons.md").exists())
        # The fixed default names must NOT be created.
        self.assertFalse(self.index_path().exists())
        self.assertFalse(self.changelog_path().exists())
        self.assertFalse(self.promotion_log_path().exists())


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


class TestCategorizationNotesSeed(_BootstrapFixture):
    """The notes file the companion's footer links to is seeded once,
    beside the companion, and never overwritten."""

    def notes_path(self) -> Path:
        return self.lessons_dir / "00-Categorization-Notes-LessonsLearned.md"

    def test_seeded_with_the_minimal_shape(self):
        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot.notes_result, ip.ConfigResult.CREATED)
        self.assertTrue(boot.notes_rel.endswith("LessonsLearned/00-Categorization-Notes-LessonsLearned.md"))
        lines = self.notes_path().read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[0], "[← 00-Categorization-By-Domain.md](00-Categorization-By-Domain.md)")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "# Lessons Learned — Categorization Notes")
        self.assertIn("generated from", lines[4])
        self.assertIn("## Cross-cutting observations", lines)
        edge = lines.index("## Classification edge cases")
        self.assertLess(lines.index("## Cross-cutting observations"), edge)
        self.assertEqual(lines[edge + 2], "| ID | Why it could fit elsewhere | Final bucket |")
        self.assertEqual(lines[edge + 3], "|---|---|---|")
        self.assertEqual(lines[edge + 4:], [""])

    def test_second_call_is_skipped_and_byte_identical(self):
        ip.bootstrap_lessons_artifacts(self.cfg)
        before = self.notes_path().read_bytes()

        boot2 = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot2.notes_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertFalse(boot2.created_any)
        self.assertEqual(self.notes_path().read_bytes(), before)

    def test_existing_notes_preserved_verbatim(self):
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        custom = "# MY NOTES\n\n- an observation\n"
        self.notes_path().write_text(custom, encoding="utf-8")

        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot.notes_result, ip.ConfigResult.SKIPPED_EXISTS)
        self.assertEqual(self.notes_path().read_text(encoding="utf-8"), custom)


class TestBootstrapBadCategorization(_BootstrapFixture):
    """A categorization block that fails validation is SKIPPED_BAD_CONFIG,
    never an exception out of bootstrap_lessons_artifacts."""

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for render_categorization_file")
        self.config_path().write_text(
            "project:\n"
            "  name: FixtureProject\n"
            "categorization:\n"
            "  buckets:\n"
            "  - id: A\n"
            "    name: Alpha\n"
            "  - name: Missing id\n"
            "  decision_tree_order: [A]\n"
            "  default_bucket: A\n",
            encoding="utf-8",
        )

    def test_bucket_missing_id_is_skipped_bad_config(self):
        boot = ip.bootstrap_lessons_artifacts(self.cfg)

        self.assertEqual(boot.cat_result, ip.ConfigResult.SKIPPED_BAD_CONFIG)
        self.assertFalse(self.cat_path().exists())


class TestDefaultCategorizationReexport(unittest.TestCase):
    def test_one_object_across_all_three_modules(self):
        import generate_lessons_index as gli
        import lessons_bootstrap as lb

        self.assertIs(lb.DEFAULT_CATEGORIZATION, gli.DEFAULT_CATEGORIZATION)
        self.assertIs(ip.DEFAULT_CATEGORIZATION, gli.DEFAULT_CATEGORIZATION)


if __name__ == "__main__":
    unittest.main()
