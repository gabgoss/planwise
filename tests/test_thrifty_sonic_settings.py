#!/usr/bin/env python3
"""Tests for init_project.configure_thrifty_sonic().

Pins the contract: CLAUDE_CODE_THRIFTY_SONIC="false" lands in BOTH the project's
.claude/settings.json and the user-global ~/.claude/settings.json whatever the
install scope, each file is merged independently (a malformed file never blocks
the other), unrelated keys survive, and settings.local.json is never touched.
configure_settings() keeps its single-scope behavior for the existing env vars.

Run with:  python -m pytest tests/test_thrifty_sonic_settings.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip

KEY = "CLAUDE_CODE_THRIFTY_SONIC"


class TestConfigureThriftySonic(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="planwise_ts_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        self.plugin_root = self.tmp / "cache" / "planwise-marketplace" / "planwise" / "1.0.5"
        for d in (self.home, self.project, self.plugin_root):
            d.mkdir(parents=True)
        patcher = mock.patch.object(ip.Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_settings = self.home / ".claude" / "settings.json"
        self.project_settings = self.project / ".claude" / "settings.json"
        self.local_settings = self.project / ".claude" / "settings.local.json"

    def _cfg(self, scope: str = "project") -> ip.InitConfig:
        return ip.InitConfig(
            project_name="TestProject",
            project_root=self.project,
            plugin_root=self.plugin_root,
            install_scope=ip.InstallScope(scope),
        )

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_both_files_created_when_absent_for_every_scope(self):
        for scope in ("project", "user", "local"):
            with self.subTest(scope=scope):
                for p in (self.user_settings, self.project_settings):
                    p.unlink(missing_ok=True)
                results = ip.configure_thrifty_sonic(self._cfg(scope))
                self.assertEqual({s for _, s in results}, {"added"})
                self.assertEqual(self._read(self.user_settings)["env"][KEY], "false")
                self.assertEqual(self._read(self.project_settings)["env"][KEY], "false")

    def test_local_settings_never_touched(self):
        self.local_settings.parent.mkdir(parents=True)
        self.local_settings.write_text('{"env": {"X": "1"}}\n', encoding="utf-8")
        ip.configure_thrifty_sonic(self._cfg("local"))
        self.assertEqual(self._read(self.local_settings), {"env": {"X": "1"}})

    def test_unrelated_keys_preserved(self):
        self.user_settings.parent.mkdir(parents=True)
        self.user_settings.write_text(
            json.dumps({"theme": "dark", "env": {"OTHER": "1"}, "permissions": {"allow": ["a"]}}),
            encoding="utf-8",
        )
        ip.configure_thrifty_sonic(self._cfg())
        data = self._read(self.user_settings)
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["env"], {"OTHER": "1", KEY: "false"})
        self.assertEqual(data["permissions"], {"allow": ["a"]})

    def test_wrong_value_is_corrected_and_correct_value_is_unchanged(self):
        self.user_settings.parent.mkdir(parents=True)
        self.user_settings.write_text(json.dumps({"env": {KEY: "true"}}), encoding="utf-8")
        self.project_settings.parent.mkdir(parents=True)
        self.project_settings.write_text(json.dumps({"env": {KEY: "false"}}), encoding="utf-8")
        before = self.project_settings.read_text(encoding="utf-8")
        status = {p: s for p, s in ip.configure_thrifty_sonic(self._cfg())}
        self.assertEqual(status[self.user_settings], "corrected")
        self.assertEqual(status[self.project_settings], "unchanged")
        self.assertEqual(self._read(self.user_settings)["env"][KEY], "false")
        self.assertEqual(self.project_settings.read_text(encoding="utf-8"), before)

    def test_malformed_file_skipped_other_file_still_written(self):
        self.user_settings.parent.mkdir(parents=True)
        self.user_settings.write_text("{not json", encoding="utf-8")
        with mock.patch("sys.stderr"):
            status = {p: s for p, s in ip.configure_thrifty_sonic(self._cfg())}
        self.assertEqual(status[self.user_settings], "skipped")
        self.assertEqual(self.user_settings.read_text(encoding="utf-8"), "{not json")
        self.assertEqual(status[self.project_settings], "added")
        self.assertEqual(self._read(self.project_settings)["env"][KEY], "false")

    def test_configure_settings_leaves_existing_env_vars_single_scope(self):
        """AGENT_TEAMS stays in the one install-scope file; THRIFTY_SONIC is not its job."""
        ip.configure_settings(self._cfg("project"))
        self.assertEqual(self._read(self.project_settings)["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"], "1")
        self.assertNotIn(KEY, self._read(self.project_settings)["env"])
        self.assertFalse(self.user_settings.exists())


if __name__ == "__main__":
    unittest.main()
