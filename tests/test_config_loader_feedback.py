#!/usr/bin/env python3
"""Direct unit tests for config_loader's `get_feedback_config()` accessor.

`config_loader.get_feedback_config` extracts the `feedback:` config block
consumed by `/planwise feedback`. It mirrors `get_upgrade_config` exactly --
same absent/null/malformed-block handling, same `_as_bool_flag` coercion --
so the pattern pinned here mirrors `TestUpgradeConfigFoundation` in
tests/test_rule_descope_migration.py.

Run with:  python -m pytest tests/test_config_loader_feedback.py -q
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402


class TestFeedbackConfigFoundation(unittest.TestCase):
    """Foundation invariants for the `feedback:` config surface.

    Plain TestCase on purpose: these are pure constant/function assertions
    that need none of a temp project tree.
    """

    _DEFAULTS = {
        "enabled": False,
        "repo": "gabgoss/planwise",
        "include_environment": True,
    }

    def test_get_feedback_config_defaults_on_absent_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_feedback_config({}),
            self._DEFAULTS,
            "get_feedback_config({}) must return the conservative defaults",
        )

    def test_get_feedback_config_defaults_on_non_dict_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_feedback_config({"feedback": "not-a-dict"}),
            self._DEFAULTS,
            "A non-dict feedback: block must also fall back to defaults",
        )

    def test_get_feedback_config_string_booleans_not_truthy_coerced(self):
        import config_loader as cl

        result = cl.get_feedback_config(
            {"feedback": {"enabled": "false", "include_environment": "false"}}
        )
        self.assertFalse(
            result["enabled"],
            'a quoted "false" must mean False, not bool-truthy True',
        )
        self.assertFalse(result["include_environment"])
        result = cl.get_feedback_config({"feedback": {"enabled": "true"}})
        self.assertTrue(result["enabled"])

    def test_get_feedback_config_non_string_repo_falls_back_to_default(self):
        import config_loader as cl

        result = cl.get_feedback_config({"feedback": {"repo": None}})
        self.assertEqual(
            result["repo"],
            "gabgoss/planwise",
            "a non-string repo must fall back to the literal default",
        )
        result = cl.get_feedback_config({"feedback": {"repo": "   "}})
        self.assertEqual(
            result["repo"],
            "gabgoss/planwise",
            "a blank repo must fall back to the literal default",
        )

    def test_get_feedback_config_honors_user_supplied_values(self):
        import config_loader as cl

        result = cl.get_feedback_config(
            {
                "feedback": {
                    "enabled": True,
                    "repo": "myorg/fork",
                    "include_environment": False,
                }
            }
        )
        self.assertEqual(
            result,
            {"enabled": True, "repo": "myorg/fork", "include_environment": False},
            "a fully-populated feedback: block must be honored, not defaulted",
        )

    def test_feedback_in_migratable_top_level_keys(self):
        self.assertIn(
            "feedback",
            ip.MIGRATABLE_TOP_LEVEL_KEYS,
            "MIGRATABLE_TOP_LEVEL_KEYS must include 'feedback' so --migrate "
            "backfills the block into existing configs",
        )

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to parse the template")
    def test_template_feedback_defaults_match_loader_defaults(self):
        """The shipped config.yaml.template's feedback: block must agree with
        get_feedback_config()'s own defaults, so the two cannot drift apart."""
        import yaml

        template_path = (
            Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        )
        data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        self.assertIs(data["feedback"]["enabled"], False)
        self.assertEqual(data["feedback"]["repo"], "gabgoss/planwise")
        self.assertIs(data["feedback"]["include_environment"], True)


class TestFeedbackDirDerivation(unittest.TestCase):
    """Direct unit tests for `config_loader.load_config()`'s `_feedback_dir`
    derivation -- the same unconditional-default shape as `_plans_dir` /
    `_backlog_dir` / `_lessons_dir`, added alongside those in the same block.

    Each test writes a minimal config.yaml to a temp `planwise/` directory and
    invokes `load_config()` with an explicit `--config` argument (mocked into
    `sys.argv`), the documented explicit-override path `load_config()` itself
    supports -- this bypasses the upward cwd/script-path search entirely.
    """

    def test_feedback_dir_defaults_to_Feedback_when_absent(self):
        import config_loader as cl

        with tempfile.TemporaryDirectory() as tmp:
            planwise_root = Path(tmp) / "planwise"
            planwise_root.mkdir()
            config_path = planwise_root / "config.yaml"
            config_path.write_text('project:\n  name: "TestProject"\n', encoding="utf-8")

            with mock.patch.object(sys, "argv", ["prog", "--config", str(config_path)]):
                config = cl.load_config()

            self.assertEqual(
                config["_feedback_dir"],
                planwise_root / "Feedback",
                "absent project.feedback_dir must derive to {planwise_root}/Feedback",
            )

    def test_feedback_dir_honors_explicit_value(self):
        import config_loader as cl

        with tempfile.TemporaryDirectory() as tmp:
            planwise_root = Path(tmp) / "planwise"
            planwise_root.mkdir()
            config_path = planwise_root / "config.yaml"
            config_path.write_text(
                'project:\n  name: "TestProject"\n  feedback_dir: custom-feedback\n',
                encoding="utf-8",
            )

            with mock.patch.object(sys, "argv", ["prog", "--config", str(config_path)]):
                config = cl.load_config()

            self.assertEqual(config["_feedback_dir"], planwise_root / "custom-feedback")

    def test_feedback_dir_honors_explicit_legacy_feedback_drafts_value(self):
        """Question 5's 'leave and re-point' disposition: an explicit
        project.feedback_dir already pointing at the legacy feedback-drafts/
        directory must be honored exactly like any other explicit value --
        this is the REQUIRED case per FDL-S01-01's Resolved Gated Branches."""
        import config_loader as cl

        with tempfile.TemporaryDirectory() as tmp:
            planwise_root = Path(tmp) / "planwise"
            planwise_root.mkdir()
            config_path = planwise_root / "config.yaml"
            config_path.write_text(
                'project:\n  name: "TestProject"\n  feedback_dir: feedback-drafts\n',
                encoding="utf-8",
            )

            with mock.patch.object(sys, "argv", ["prog", "--config", str(config_path)]):
                config = cl.load_config()

            self.assertEqual(config["_feedback_dir"], planwise_root / "feedback-drafts")


class TestFeedbackDirCreationAndBackfill(unittest.TestCase):
    """Direct unit tests for init_project.py's `create_directories()` and the
    `--migrate` backfill helper `_backfill_feedback_dir()`."""

    def _make_cfg(self, project_root: Path, **overrides):
        plugin_root = Path(ip.__file__).resolve().parent.parent
        kwargs = dict(
            project_name="TestProject",
            project_root=project_root,
            plugin_root=plugin_root,
            planwise_root="planwise",
            plans_dir="Plans",
            backlog_dir="Backlog",
            lessons_dir="LessonsLearned",
            feedback_dir="Feedback",
            install_scope=ip.InstallScope.PROJECT,
            plan_tier="pro",
            plugin_version="0.0.0",
            token_saver=False,
        )
        kwargs.update(overrides)
        return ip.InitConfig(**kwargs)

    def test_create_directories_creates_feedback_dir_alongside_the_other_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            cfg = self._make_cfg(project_root)

            created = ip.create_directories(cfg)

            feedback_dir = project_root / "planwise" / "Feedback"
            self.assertTrue(feedback_dir.is_dir())
            self.assertIn(str(feedback_dir.relative_to(project_root)), created)

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to parse/write the config")
    def test_backfill_feedback_dir_defaults_to_Feedback_when_no_legacy_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            planwise_dir = project_root / "planwise"
            planwise_dir.mkdir()
            config_path = planwise_dir / "config.yaml"
            config_path.write_text(
                'project:\n  name: "TestProject"\n  plans_dir: Plans\n'
                '  backlog_dir: Backlog\n  lessons_dir: LessonsLearned\n',
                encoding="utf-8",
            )
            cfg = self._make_cfg(project_root)

            notice = ip._backfill_feedback_dir(cfg, config_path)

            self.assertIsNone(notice, "no legacy directory present -- no notice expected")
            text = config_path.read_text(encoding="utf-8")
            self.assertIn('feedback_dir: "Feedback"', text)

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to parse/write the config")
    def test_backfill_feedback_dir_repoints_to_nonempty_legacy_dir_with_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            planwise_dir = project_root / "planwise"
            planwise_dir.mkdir()
            legacy_dir = planwise_dir / "feedback-drafts"
            legacy_dir.mkdir()
            (legacy_dir / "draft.md").write_text("hi", encoding="utf-8")
            config_path = planwise_dir / "config.yaml"
            config_path.write_text(
                'project:\n  name: "TestProject"\n  plans_dir: Plans\n'
                '  backlog_dir: Backlog\n  lessons_dir: LessonsLearned\n',
                encoding="utf-8",
            )
            cfg = self._make_cfg(project_root)

            notice = ip._backfill_feedback_dir(cfg, config_path)

            self.assertIsNotNone(notice, "a non-empty legacy feedback-drafts/ must print a notice")
            self.assertIn("feedback-drafts", notice)
            text = config_path.read_text(encoding="utf-8")
            self.assertIn('feedback_dir: "feedback-drafts"', text)
            # Never-moves guarantee: the legacy draft is untouched.
            self.assertTrue((legacy_dir / "draft.md").exists())
            self.assertEqual((legacy_dir / "draft.md").read_text(encoding="utf-8"), "hi")


class TestGeneratedConfigNoUnsubstitutedPlaceholder(unittest.TestCase):
    """Regression test for the scope-expansion defect found and fixed
    2026-09-01: config.yaml.template's `feedback_dir: "{feedback-dir}"`
    placeholder was declared before config_gen.py rendered it anywhere, so a
    fresh /planwise init wrote the literal placeholder string into
    config.yaml while creating the real Feedback/ directory on disk -- config
    and disk disagreed, and _feedback_dir resolved to a nonexistent path. The
    full 557-test suite was green throughout, because nothing swept the
    generated file for unsubstituted placeholders. This sweeps the GENERAL
    {lowercase-hyphenated} form, not just feedback_dir, so the next templated
    key cannot reintroduce this defect class silently.
    """

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to render/parse the template")
    def test_generate_config_leaves_no_unsubstituted_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "planwise").mkdir()
            plugin_root = Path(ip.__file__).resolve().parent.parent
            cfg = ip.InitConfig(
                project_name="TestProject",
                project_root=project_root,
                plugin_root=plugin_root,
                planwise_root="planwise",
                plans_dir="Plans",
                backlog_dir="Backlog",
                lessons_dir="LessonsLearned",
                feedback_dir="Feedback",
                install_scope=ip.InstallScope.PROJECT,
                plan_tier="pro",
                plugin_version="0.0.0",
                token_saver=False,
            )

            result, config_rel = ip.generate_config(cfg)

            self.assertEqual(result, ip.ConfigResult.CREATED)
            config_path = project_root / config_rel
            text = config_path.read_text(encoding="utf-8")

            leftover = re.findall(r"\{[a-z]+(?:-[a-z]+)*\}", text)
            self.assertEqual(
                leftover, [],
                f"unsubstituted placeholder(s) remain in generated config.yaml: {leftover}",
            )
            self.assertIn('feedback_dir: "Feedback"', text)


if __name__ == "__main__":
    unittest.main()
