#!/usr/bin/env python3
"""Tests for the Token Saver recalibration `_run_upgrade` runs after a successful upgrade.

The writer calibrates once, after the pin commit, when the config reads Token Saver on
and `--no-calibrate` was not passed. A calibration failure never fails the upgrade.
`token_saver.calibrate` is patched in every test, so no `claude` process starts.

Run with:  python -m pytest -q -c <plugin repo>/pytest.ini <plugin repo>/tests/test_upgrade_calibration.py
"""

import io
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import context_calibration
import init_project as ip
import token_saver
from test_token_saver import _ProjectFixtureBase

_BANNER = (
    "Token Saver recalibrated: runner overhead 11 -> 22, "
    "orchestrator overhead 33 -> 44"
)


class TestRunUpgradeCalibration(_ProjectFixtureBase):
    _PINNED_VERSION = "1.0.3"
    _TARGET_VERSION = "1.0.4"

    def setUp(self):
        super().setUp()
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML required for _run_upgrade tests")
        (self.project_root / ".claude" / "rules" / "planwise").mkdir(parents=True, exist_ok=True)

    def _config(self, token_saver_on: bool, runner: int = 11, orchestrator: int = 33) -> None:
        self.write_config(
            f'plugin_version: "{self._PINNED_VERSION}"\n'
            "project:\n"
            "  name: FixtureProject\n"
            "context:\n"
            "  plan_tier: pro\n"
            "  context_window: 200000\n"
            f"  token_saver: {'true' if token_saver_on else 'false'}\n"
            f"  token_saver_runner_overhead: {runner}\n"
            f"  token_saver_orchestrator_overhead: {orchestrator}\n"
        )

    @staticmethod
    def _failed_capture(**kwargs):
        """The real calibrate, with a /context capture that returns nothing: it writes the fallback overheads."""
        return context_calibration.calibrate(capture=lambda *_args: None, **kwargs)

    def _overheads(self) -> dict:
        text = self.config_path().read_text(encoding="utf-8")
        return {k: re.search(rf"(?m)^\s*{k}:\s*(\S+)", text).group(1)
                for k in ("token_saver_runner_overhead", "token_saver_orchestrator_overhead")}

    def _upgrade(self, no_calibrate: bool = False, side_effect=None):
        cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self._TARGET_VERSION,
            no_calibrate=no_calibrate,
        )
        result = {
            "token_saver_runner_overhead": 22,
            "token_saver_orchestrator_overhead": 44,
            "uncalibrated": False,
        }
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(token_saver, "calibrate", return_value=result,
                              side_effect=side_effect) as calibrate,
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            code = ip._run_upgrade(cfg)
        return code, out.getvalue(), calibrate

    def test_token_saver_on_calibrates_once_in_the_project_and_prints_the_banner(self):
        self._config(token_saver_on=True)
        code, out, calibrate = self._upgrade()
        self.assertEqual(code, 0)
        self.assertEqual(calibrate.call_count, 1)
        self.assertEqual(calibrate.call_args.kwargs["cwd"], self.project_root)
        self.assertIn(_BANNER, out.splitlines())
        self.assertLess(out.index(_BANNER), out.index("Upgrade complete."))

    def test_no_calibrate_flag_never_calls_calibrate(self):
        self._config(token_saver_on=True)
        code, out, calibrate = self._upgrade(no_calibrate=True)
        self.assertEqual(code, 0)
        calibrate.assert_not_called()
        self.assertNotIn("Token Saver recalibrated", out)

    def test_token_saver_off_never_calls_calibrate(self):
        self._config(token_saver_on=False)
        code, out, calibrate = self._upgrade()
        self.assertEqual(code, 0)
        calibrate.assert_not_called()
        self.assertNotIn("Token Saver recalibrated", out)

    def test_calibrate_failure_does_not_fail_the_upgrade(self):
        self._config(token_saver_on=True)
        code, out, calibrate = self._upgrade(side_effect=RuntimeError("boom"))
        self.assertEqual(code, 0)
        self.assertEqual(calibrate.call_count, 1)
        self.assertIn("Token Saver calibration skipped: boom", out)
        self.assertIn("Upgrade complete.", out)

    def test_failed_capture_keeps_the_measured_overheads(self):
        self._config(token_saver_on=True)
        before = self.config_path().read_bytes()
        code, out, calibrate = self._upgrade(side_effect=self._failed_capture)
        self.assertEqual(code, 0)
        self.assertEqual(calibrate.call_count, 1)
        self.assertEqual(self._overheads(), {"token_saver_runner_overhead": "11",
                                             "token_saver_orchestrator_overhead": "33"})
        self.assertIn("Token Saver calibration failed; kept the measured overheads.", out.splitlines())
        self.assertNotIn("fell back to defaults", out)
        after = self.config_path().read_bytes()
        self.assertNotEqual(after, before)  # the pin commit still landed
        self.assertNotIn(b"capture failed", after)

    def test_failed_capture_on_a_never_measured_project_writes_the_fallback(self):
        self._config(token_saver_on=True, runner=0, orchestrator=0)
        code, out, _calibrate = self._upgrade(side_effect=self._failed_capture)
        self.assertEqual(code, 0)
        self.assertEqual(self._overheads(), {
            "token_saver_runner_overhead": str(context_calibration.FALLBACK_RUNNER_OVERHEAD),
            "token_saver_orchestrator_overhead": str(context_calibration.FALLBACK_ORCHESTRATOR_OVERHEAD)})
        self.assertIn("fell back to defaults", out)
        self.assertNotIn("kept the measured overheads", out)


if __name__ == "__main__":
    unittest.main()
