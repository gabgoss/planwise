#!/usr/bin/env python3
"""Direct unit tests for config_loader's `get_feedback_config()` accessor.

`config_loader.get_feedback_config` extracts the `feedback:` config block
consumed by `/planwise feedback`. It mirrors `get_upgrade_config` exactly --
same absent/null/malformed-block handling, same `_as_bool_flag` coercion --
so the pattern pinned here mirrors `TestUpgradeConfigFoundation` in
tests/test_rule_descope_migration.py.

Run with:  python -m pytest tests/test_config_loader_feedback.py -q
"""

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
