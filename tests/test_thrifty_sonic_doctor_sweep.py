#!/usr/bin/env python3
"""Unit tests for doctor_cli._sweep_thrifty_sonic(): the read-only check that
env.CLAUDE_CODE_THRIFTY_SONIC equals "false" in both the project's
.claude/settings.json and the user-global ~/.claude/settings.json (Stage 15b of
`/planwise doctor`).

Pins the contract: a correct file yields no finding, an absent file/env/key is
"missing", any other value is "wrong value", an unparseable file is
"invalid JSON", settings.local.json is never read, nothing is ever written, and
the sweep is wired into the live doctor path.

Run with:  python -m pytest tests/test_thrifty_sonic_doctor_sweep.py -q
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_cli
import init_project as ip

KEY = "CLAUDE_CODE_THRIFTY_SONIC"


class TestThriftySonicDoctorSweep(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="planwise_ts_sweep_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        self.plugin_root = self.tmp / "cache" / "planwise-marketplace" / "planwise" / "1.0.3"
        for d in (self.home, self.project, self.plugin_root):
            d.mkdir(parents=True)
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_settings = self.home / ".claude" / "settings.json"
        self.project_settings = self.project / ".claude" / "settings.json"
        self.local_settings = self.project / ".claude" / "settings.local.json"
        self.cfg = ip.InitConfig(
            project_name="TestProject",
            project_root=self.project,
            plugin_root=self.plugin_root,
            install_scope=ip.InstallScope("project"),
        )

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _by_path(self, findings: list[dict]) -> dict:
        return {f["settings_path"]: f["klass"] for f in findings}

    def test_both_correct_yields_no_findings(self):
        for p in (self.user_settings, self.project_settings):
            self._write(p, json.dumps({"env": {KEY: "false"}}))
        self.assertEqual(doctor_cli._sweep_thrifty_sonic(self.cfg), [])

    def test_absent_files_are_missing(self):
        got = self._by_path(doctor_cli._sweep_thrifty_sonic(self.cfg))
        self.assertEqual(got, {self.project_settings: "missing", self.user_settings: "missing"})

    def test_env_block_or_key_absent_is_missing(self):
        self._write(self.user_settings, json.dumps({"theme": "dark"}))
        self._write(self.project_settings, json.dumps({"env": {"OTHER": "1"}}))
        got = self._by_path(doctor_cli._sweep_thrifty_sonic(self.cfg))
        self.assertEqual(got, {self.project_settings: "missing", self.user_settings: "missing"})

    def test_wrong_value_names_the_value(self):
        self._write(self.user_settings, json.dumps({"env": {KEY: "true"}}))
        self._write(self.project_settings, json.dumps({"env": {KEY: "false"}}))
        findings = doctor_cli._sweep_thrifty_sonic(self.cfg)
        self.assertEqual(self._by_path(findings), {self.user_settings: "wrong value"})
        self.assertIn("'true'", findings[0]["detail"])

    def test_invalid_json_is_reported_not_repaired(self):
        self._write(self.user_settings, "{not json")
        self._write(self.project_settings, json.dumps({"env": {KEY: "false"}}))
        got = self._by_path(doctor_cli._sweep_thrifty_sonic(self.cfg))
        self.assertEqual(got, {self.user_settings: "invalid JSON"})
        self.assertEqual(self.user_settings.read_text(encoding="utf-8"), "{not json")

    def test_local_settings_never_counts(self):
        """A correct settings.local.json must not satisfy the project target."""
        self._write(self.local_settings, json.dumps({"env": {KEY: "false"}}))
        self._write(self.user_settings, json.dumps({"env": {KEY: "false"}}))
        got = self._by_path(doctor_cli._sweep_thrifty_sonic(self.cfg))
        self.assertEqual(got, {self.project_settings: "missing"})

    def test_sweep_never_writes(self):
        self._write(self.user_settings, json.dumps({"env": {KEY: "true"}}))
        before = self.user_settings.read_bytes()
        self.assertTrue(doctor_cli._sweep_thrifty_sonic(self.cfg))
        self.assertEqual(self.user_settings.read_bytes(), before)
        self.assertFalse(self.project_settings.exists(), "the sweep must not create a missing file")

    def test_stage15b_wired_into_doctor_path(self):
        self.cfg.plugin_version = "1.0.3"
        config_dir = self.project / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text('plugin_version: "1.0.3"\n', encoding="utf-8")
        self._write(self.user_settings, json.dumps({"env": {KEY: "true"}}))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("thrifty-sonic env var sweep", stdout)
        self.assertIn("drift in 2 of 2 settings file(s)", stdout)
        self.assertIn("Step 4.7", stdout)
        self.assertIn("doctor is read-only and never rewrites settings", stdout)


if __name__ == "__main__":
    unittest.main()
