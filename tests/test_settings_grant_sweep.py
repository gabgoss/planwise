#!/usr/bin/env python3
"""Unit tests for doctor_cli._sweep_settings_grants(): the read-only
settings.json/settings.local.json `additionalDirectories` grant
classification sweep (Stage 15 of `/planwise doctor`).

Complements tests/test_additional_dirs_dedup.py: that file regression-tests
init_project.py's configure_settings() WRITE-time dedup (parent-aware,
already covers stale-pin pruning at write time — do not duplicate those
five tests here, they remain this task's verdict evidence). This file
covers doctor_cli.py's separate READ-only classification sweep, which never
writes and classifies existing grants into "version-agnostic parent"
(already correct — no finding), "version-pinned live", and "version-pinned
dangling or orphan-marked".

Reuses the same versioned-plugin-cache fixture shape as
test_additional_dirs_dedup.py so `cfg.plugin_root` / `cfg.plugin_root.parent`
model a real marketplace cache layout.

Run with:  python -m pytest tests/test_settings_grant_sweep.py -q
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow `import doctor_cli` / `import init_project` whether pytest is run
# from the repo root or the test is executed directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_cli  # noqa: E402 -- the module under test (_sweep_settings_grants is not re-exported by init_project)
import init_project as ip  # noqa: E402 -- for InitConfig and the wired-in _run_doctor() check


def _make_cfg(project_root: Path, plugin_root: Path, scope: str = "project") -> ip.InitConfig:
    """Build a minimal InitConfig pointing at arbitrary temp dirs."""
    return ip.InitConfig(
        project_name="TestProject",
        project_root=project_root,
        plugin_root=plugin_root,
        install_scope=ip.InstallScope(scope),
    )


class TestSettingsGrantSweep(unittest.TestCase):
    """doctor_cli._sweep_settings_grants(): read-only classification of
    plugin-cache additionalDirectories entries into the three grant classes."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="planwise_grant_sweep_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # Same versioned plugin-cache layout as test_additional_dirs_dedup.py:
        #   …/planwise-marketplace/planwise/1.0.3/   <- plugin_root (live, version-pinned)
        #   …/planwise-marketplace/planwise/          <- plugin_root.parent (family root)
        self.plugin_root = self.tmp / "cache" / "planwise-marketplace" / "planwise" / "1.0.3"
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        self.family_root = str(self.plugin_root.parent)
        self.live_root = str(self.plugin_root)

        self.project_root = self.tmp / "project"
        self.project_root.mkdir()
        self.dot_claude = self.project_root / ".claude"
        self.dot_claude.mkdir()
        self.settings_path = self.dot_claude / "settings.json"
        self.local_settings_path = self.dot_claude / "settings.local.json"

        self.cfg = _make_cfg(self.project_root, self.plugin_root)

    # ------------------------------------------------------------------
    # Helper: write an additionalDirectories-bearing settings file
    # ------------------------------------------------------------------

    def _write_settings(self, path: Path, dirs: list) -> None:
        path.write_text(
            json.dumps({"permissions": {"additionalDirectories": dirs}}, indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # "version-agnostic parent" — already the correct target shape,
    # never returned as a finding.
    # ------------------------------------------------------------------

    def test_family_root_grant_is_not_a_finding(self):
        self._write_settings(self.settings_path, [self.family_root])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(findings, [], "an already-correct family-root grant must produce no finding")

    def test_broader_ancestor_grant_is_not_a_finding(self):
        broader = str(self.plugin_root.parent.parent)  # …/planwise-marketplace
        self._write_settings(self.settings_path, [broader])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(
            findings, [], "a grant broader than the family root must also produce no finding"
        )

    # ------------------------------------------------------------------
    # "version-pinned live" — names the currently-pinned version, still
    # on disk.
    # ------------------------------------------------------------------

    def test_version_pinned_live_grant_is_classified(self):
        self._write_settings(self.settings_path, [self.live_root])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["klass"], "version-pinned live")
        self.assertEqual(findings[0]["detail"], "still the currently-pinned version")
        self.assertEqual(findings[0]["entry"], self.live_root)
        self.assertEqual(findings[0]["settings_path"], self.settings_path)

    # ------------------------------------------------------------------
    # "version-pinned dangling or orphan-marked" — two sub-cases: the
    # path no longer exists, or it exists but is a superseded sibling.
    # ------------------------------------------------------------------

    def test_dangling_pinned_grant_is_classified(self):
        dangling = str(self.plugin_root.parent / "0.9.9")  # never created on disk
        self._write_settings(self.settings_path, [dangling])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["klass"], "version-pinned dangling or orphan-marked")
        self.assertEqual(findings[0]["detail"], "path does not exist")

    def test_superseded_sibling_still_on_disk_is_classified_orphan(self):
        stale = self.plugin_root.parent / "1.0.2"
        stale.mkdir(parents=True, exist_ok=True)
        self._write_settings(self.settings_path, [str(stale)])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["klass"], "version-pinned dangling or orphan-marked")
        self.assertEqual(
            findings[0]["detail"], f"superseded by the currently-pinned {self.live_root}"
        )

    # ------------------------------------------------------------------
    # Entries outside the plugin-cache path family are never touched or
    # reported.
    # ------------------------------------------------------------------

    def test_unrelated_grant_is_never_reported(self):
        unrelated = "/some/unrelated/project/docs"
        self._write_settings(self.settings_path, [unrelated])
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(
            findings, [], "a grant outside the plugin-cache path family must never be reported"
        )

    # ------------------------------------------------------------------
    # Both settings.json and settings.local.json are swept.
    # ------------------------------------------------------------------

    def test_both_settings_files_are_swept(self):
        dangling = str(self.plugin_root.parent / "0.9.9")
        stale = self.plugin_root.parent / "1.0.2"
        stale.mkdir(parents=True, exist_ok=True)
        self._write_settings(self.settings_path, [dangling])
        self._write_settings(self.local_settings_path, [str(stale)])

        findings = doctor_cli._sweep_settings_grants(self.cfg)

        self.assertEqual(len(findings), 2)
        by_path = {f["settings_path"]: f for f in findings}
        self.assertEqual(
            by_path[self.settings_path]["klass"], "version-pinned dangling or orphan-marked"
        )
        self.assertEqual(by_path[self.settings_path]["detail"], "path does not exist")
        self.assertEqual(
            by_path[self.local_settings_path]["detail"],
            f"superseded by the currently-pinned {self.live_root}",
        )

    # ------------------------------------------------------------------
    # No settings file, or no additionalDirectories entries -> empty.
    # ------------------------------------------------------------------

    def test_no_settings_file_returns_empty(self):
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(findings, [])

    def test_settings_with_no_additional_dirs_returns_empty(self):
        self.settings_path.write_text(json.dumps({"env": {}}) + "\n", encoding="utf-8")
        findings = doctor_cli._sweep_settings_grants(self.cfg)
        self.assertEqual(findings, [])

    # ------------------------------------------------------------------
    # No-silent-write invariant: classification must never mutate the
    # settings file(s) it reads, regardless of how many findings it
    # produces.
    # ------------------------------------------------------------------

    def test_sweep_never_writes_settings_file(self):
        dirs = [self.live_root, str(self.plugin_root.parent / "0.9.9"), "/unrelated/docs"]
        self._write_settings(self.settings_path, dirs)
        before = self.settings_path.read_bytes()

        findings = doctor_cli._sweep_settings_grants(self.cfg)

        self.assertTrue(
            findings, "fixture must produce at least one finding to make this a meaningful check"
        )
        after = self.settings_path.read_bytes()
        self.assertEqual(
            after, before, "the settings-grant sweep must never mutate the settings file it reads"
        )

    # ------------------------------------------------------------------
    # Wired into the live --doctor path (Stage 15), not merely defined.
    # ------------------------------------------------------------------

    def test_stage15_wired_into_doctor_path(self):
        import contextlib
        import io

        dangling = str(self.plugin_root.parent / "0.9.9")
        self._write_settings(self.settings_path, [dangling])

        # Pin the version-state gate to "ok" so _run_doctor() proceeds past
        # the preflight into the diagnostic stages.
        self.cfg.plugin_version = "1.0.3"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        before = self.settings_path.read_bytes()

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "settings-grant sweep", stdout,
            "Stage 15 must be invoked by _run_doctor(), not merely defined",
        )
        self.assertIn(dangling, stdout)
        self.assertIn("version-pinned dangling or orphan-marked", stdout)
        self.assertIn("doctor is read-only and never rewrites settings", stdout)
        self.assertEqual(
            self.settings_path.read_bytes(), before,
            "the doctor path (bare --doctor) must never write settings.json",
        )


if __name__ == "__main__":
    unittest.main()
