#!/usr/bin/env python3
"""Regression tests for init when PyYAML is not importable.

A config that cannot be read is not an empty config. Before the fix, an init
run without PyYAML left `user_cfg` empty, read `plugin_version` as `0.0.0` and
printed a false drift row. These tests pin the honest behaviour:

  * no `plugin_version` drift row is printed,
  * exactly one `Skipped (action required)` row says gap detection is degraded
    and names the interpreter that could not import PyYAML,
  * the manifest loader reports why its empty return is degraded,
  * the upgrade entry point refuses (exit 2) before any write and prints no
    drift row. This last test passes both before and after the fix.

Run with:  python -m pytest tests/test_init_missing_pyyaml.py -q
"""

import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import config_loader
import init_project

OLD_CONFIG = 'plugin_version: "0.0.1"\n'


class _NoPyYamlBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="init_no_pyyaml_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.planwise_dir.mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(OLD_CONFIG, encoding="utf-8")
        # init writes under the user's home; keep every runner off the real one.
        patcher = mock.patch.object(Path, "home", return_value=self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.tmp), "USERPROFILE": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for module in (init_project, artifact_upgrade, config_loader):
            patcher = mock.patch.object(module, "HAS_YAML", False)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_init(self) -> str:
        argv = ["init_project.py", "--name", "NoPyYamlFixture", "--project-root", str(self.tmp)]
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            try:
                init_project.main()
            except SystemExit as exc:
                self.assertIn(exc.code, (0, None))
        return buf.getvalue()


class TestInitWithoutPyYaml(_NoPyYamlBase):
    def test_no_false_plugin_version_drift_row_when_pyyaml_absent(self):
        out = self.run_init()

        self.assertIn("Skipped (action required):", out)
        self.assertNotIn("key: plugin_version", out)
        self.assertNotIn("pinned plugin_version", out)

    def test_exactly_one_degraded_row_names_interpreter(self):
        out = self.run_init()

        rows = [ln for ln in out.splitlines() if "PyYAML" in ln and "gap detection" in ln]
        self.assertEqual(len(rows), 1, out)
        self.assertIn(sys.executable, rows[0])


class TestManifestLoaderWithoutPyYaml(_NoPyYamlBase):
    def test_load_artifact_manifest_reports_degraded_reason_when_pyyaml_absent(self):
        manifest = artifact_upgrade.load_artifact_manifest(init_project.get_plugin_root())

        self.assertEqual(manifest["artifacts"], [])
        self.assertTrue(manifest.get("degraded_reason"))


class TestUpgradeEntryWithoutPyYaml(_NoPyYamlBase):
    def test_upgrade_entry_refuses_without_pyyaml_and_prints_no_drift_row(self):
        before = self.config_path.read_bytes()
        cfg = init_project.InitConfig(
            project_name="NoPyYamlFixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )
        out, err = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = artifact_upgrade._run_upgrade(cfg)

        self.assertEqual(code, 2)
        self.assertNotIn("plugin_version", out.getvalue())
        self.assertEqual(self.config_path.read_bytes(), before)


BARE_PIP = re.compile(r"(?<!-m )\bpip3? install pyyaml", re.IGNORECASE)


class TestPyYamlInstallCommand(unittest.TestCase):
    def _command_for(self, lock_name):
        import pyyaml_remedy

        with tempfile.TemporaryDirectory(prefix="pyyaml_remedy_") as tmp:
            if lock_name:
                (Path(tmp) / lock_name).write_text("", encoding="utf-8")
            return pyyaml_remedy.pyyaml_install_command(Path(tmp))

    def test_uv_lock_selects_uv_add(self):
        self.assertEqual(self._command_for("uv.lock"), "uv add --dev pyyaml")

    def test_poetry_lock_selects_poetry_add(self):
        self.assertEqual(self._command_for("poetry.lock"), "poetry add --group dev pyyaml")

    def test_pipfile_lock_selects_pipenv_install(self):
        self.assertEqual(self._command_for("Pipfile.lock"), "pipenv install --dev pyyaml")

    def test_no_lock_file_selects_explicit_interpreter_pip(self):
        self.assertEqual(self._command_for(None), f'"{sys.executable}" -m pip install pyyaml')


class TestRemedyWiring(_NoPyYamlBase):
    def test_degraded_row_fix_names_interpreter_and_never_the_bare_form(self):
        out = self.run_init()

        fix_lines = [ln for ln in out.splitlines() if "install PyYAML into" in ln]
        self.assertEqual(len(fix_lines), 1, out)
        self.assertIn(sys.executable, fix_lines[0])
        self.assertIn("-m pip install pyyaml", fix_lines[0])
        self.assertIsNone(BARE_PIP.search(out), out)

    def test_upgrade_refusal_message_names_interpreter_and_keeps_prefix(self):
        cfg = init_project.InitConfig(
            project_name="NoPyYamlFixture",
            project_root=self.tmp,
            plugin_root=init_project.get_plugin_root(),
        )
        out, err = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = artifact_upgrade._run_upgrade(cfg)

        message = err.getvalue()
        self.assertEqual(code, 2)
        self.assertTrue(message.startswith("Upgrade failed: PyYAML is required for --upgrade."), message)
        self.assertIn(sys.executable, message)
        self.assertIn(f'"{sys.executable}" -m pip install pyyaml', message)
        self.assertIsNone(BARE_PIP.search(message), message)


if __name__ == "__main__":
    unittest.main()
