#!/usr/bin/env python3
"""Regression tests for configure_settings() additionalDirectories dedup.

Pins the contract: the grant uses the version-agnostic plugin-family root
(cfg.plugin_root.parent), dedup is parent-aware and normalized for Windows
separators/case, stale version-pinned siblings are pruned, and unrelated
entries (env, enabledPlugins, pre-existing additionalDirectories) are
preserved verbatim.

Run with:  python -m unittest scripts/test_additional_dirs_dedup.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow `import init_project` whether unittest is launched from the repo root
# (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402


def _make_cfg(project_root: Path, plugin_root: Path, scope: str = "project") -> ip.InitConfig:
    """Build a minimal InitConfig pointing at arbitrary temp dirs."""
    return ip.InitConfig(
        project_name="TestProject",
        project_root=project_root,
        plugin_root=plugin_root,
        install_scope=ip.InstallScope(scope),
    )


class TestAdditionalDirsDedup(unittest.TestCase):
    """configure_settings() grants the version-agnostic family root with
    parent-aware, normalized dedup and non-destructive pruning."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="planwise_ads_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # Simulate a plugin cache layout:
        #   …/planwise-marketplace/planwise/1.0.3/   <- plugin_root (versioned)
        #   …/planwise-marketplace/planwise/          <- plugin_root.parent (family root)
        #   …/planwise-marketplace/                   <- grandparent
        self.plugin_root = self.tmp / "cache" / "planwise-marketplace" / "planwise" / "1.0.3"
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        self.family_root = str(self.plugin_root.parent)  # …/planwise-marketplace/planwise

        self.project_root = self.tmp / "project"
        self.project_root.mkdir()
        self.dot_claude = self.project_root / ".claude"
        self.dot_claude.mkdir()
        self.settings_path = self.dot_claude / "settings.json"

        self.cfg = _make_cfg(self.project_root, self.plugin_root)

    # ------------------------------------------------------------------
    # Helper: write a settings file and run configure_settings()
    # ------------------------------------------------------------------

    def _run(self, settings: dict) -> tuple[str | None, str | None]:
        self.settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        return ip.configure_settings(self.cfg)

    def _read_settings(self) -> dict:
        return json.loads(self.settings_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # (a) Exact family-root path already present → no change (idempotent)
    # ------------------------------------------------------------------

    def test_exact_family_root_present_is_noop(self):
        initial = {
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "permissions": {
                "additionalDirectories": [self.family_root]
            },
        }
        _settings_path, plugin_dir = self._run(initial)

        # plugin_dir must be None — the no-op path
        self.assertIsNone(plugin_dir, "exact match must return plugin_dir=None (idempotent)")

        after = self._read_settings()
        # The list must be exactly the same (no duplicate appended)
        self.assertEqual(
            after["permissions"]["additionalDirectories"],
            [self.family_root],
        )

    # ------------------------------------------------------------------
    # (b) A PARENT of the family root already present → no change
    # ------------------------------------------------------------------

    def test_parent_of_family_root_present_is_noop(self):
        parent_of_family = str(self.plugin_root.parent.parent)  # …/planwise-marketplace
        initial = {
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "permissions": {
                "additionalDirectories": [parent_of_family]
            },
        }
        _settings_path, plugin_dir = self._run(initial)

        self.assertIsNone(plugin_dir, "a broader parent grant must be recognised and return plugin_dir=None")

        after = self._read_settings()
        self.assertEqual(
            after["permissions"]["additionalDirectories"],
            [parent_of_family],
            "parent entry must not be duplicated or replaced",
        )

    # ------------------------------------------------------------------
    # (c) Stale version-pinned sibling → pruned, family root appended
    # ------------------------------------------------------------------

    def test_stale_version_pinned_sibling_is_pruned(self):
        stale_old_version = str(self.plugin_root.parent / "1.0.2")  # prior version path
        initial = {
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "permissions": {
                "additionalDirectories": [stale_old_version]
            },
        }
        _settings_path, plugin_dir = self._run(initial)

        self.assertIsNotNone(plugin_dir, "family root must be granted when only stale pins exist")

        after = self._read_settings()
        dirs = after["permissions"]["additionalDirectories"]

        self.assertIn(self.family_root, dirs, "family root must be present after pruning stale pin")
        self.assertNotIn(stale_old_version, dirs, "stale version-pinned entry must be removed")
        self.assertEqual(len(dirs), 1, "list must contain only the family root")

    # ------------------------------------------------------------------
    # Unrelated entries are preserved in all scenarios
    # ------------------------------------------------------------------

    def test_unrelated_additional_dir_is_preserved(self):
        unrelated = "/some/unrelated/project/docs"
        initial = {
            "env": {
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
                "MY_OTHER_VAR": "hello",
            },
            "permissions": {
                "additionalDirectories": [unrelated]
            },
            "enabledPlugins": {"other-plugin@local": True},
        }
        _settings_path, _plugin_dir = self._run(initial)

        after = self._read_settings()

        # Unrelated additionalDirectories entry must survive
        self.assertIn(unrelated, after["permissions"]["additionalDirectories"])
        # env vars must be preserved (including the pre-existing one)
        self.assertEqual(after["env"].get("MY_OTHER_VAR"), "hello")
        # enabledPlugins must survive untouched
        self.assertEqual(after.get("enabledPlugins"), {"other-plugin@local": True})

    def test_env_agent_teams_var_set(self):
        """Agent Teams env var is always written regardless of additionalDirectories state."""
        _settings_path, _plugin_dir = self._run({})

        after = self._read_settings()
        self.assertEqual(
            after["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"],
            "1",
        )

    # ------------------------------------------------------------------
    # Stale pin + unrelated entry: stale removed, unrelated kept
    # ------------------------------------------------------------------

    def test_stale_pin_pruned_but_unrelated_preserved(self):
        stale = str(self.plugin_root.parent / "0.9.9")
        unrelated = "/my/docs"
        initial = {
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "permissions": {
                "additionalDirectories": [unrelated, stale]
            },
        }
        _settings_path, plugin_dir = self._run(initial)

        self.assertIsNotNone(plugin_dir)

        after = self._read_settings()
        dirs = after["permissions"]["additionalDirectories"]

        self.assertIn(self.family_root, dirs)
        self.assertIn(unrelated, dirs)
        self.assertNotIn(stale, dirs)


if __name__ == "__main__":
    unittest.main()
