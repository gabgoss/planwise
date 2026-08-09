#!/usr/bin/env python3
"""Regression tests for the plugin_root / plugin_version repoint-on-upgrade fix.

`_run_upgrade()` used to bump `plugin_version:` as its commit point but never
touch `plugin_root:`. `migrate_config()` is purely additive (it only fills in
a key that is ABSENT), so an already-present `plugin_root` was untouchable by
it. After a marketplace version bump, config ended up pinning the NEW version
while `plugin_root` still pointed at the PREVIOUS version's cache directory —
a drift-detection deadlock for any handler that trusted config's `plugin_root`
to read `.claude-plugin/plugin.json` (bounded by the marketplace cache
reaper: once the superseded directory is collected, `plugin_root` dangles
instead of merely pointing at a wrong-but-real version), and silent version
skew for every OTHER handler that resolves scripts through config's
`plugin_root` (backlog scoring, token-saver calibrate, doctor, list/reconcile).

These tests pin the contract that closes it:

  * The upgrade commit point (`_commit_upgrade_pin()`) repoints `plugin_root`
    and bumps `plugin_version` together in ONE write, so the pair can never
    land half-committed — an aborted upgrade (unparseable config, PyYAML
    missing, a failed migrate phase, or a write that would corrupt the file)
    leaves BOTH untouched.
  * `_repoint_plugin_root()` is a standalone, comment-preserving line editor
    with the same shape as `_bump_plugin_version()` (line-level regex edit,
    text-append fallback, parse-checked write) — usable on its own.
  * An "already up to date" upgrade run (pinned version == installed) still
    repoints a stale `plugin_root` on its own, single-key write — the
    residual case a version-bump-only commit point can never reach because
    the version gate exits before the commit point runs at all.
  * `_doctor_version_gate()` flags a dangling `plugin_root` (points at a
    directory that no longer exists) and a version-mismatched `plugin_root`
    (points at a real directory pinned to a different version) even when the
    top-level version pin itself looks current — and version drift still
    takes precedence when both are wrong at once.

Fixture tree mirrors `_UpgradeArtifactsFixtureBase` in
test_rule_descope_migration.py: `INSTALLED_RULES` is patched to empty so
`_run_upgrade()` can be driven end-to-end without needing every real shipped
rule file on disk, and the real shipped `config.yaml.template` is copied in
so `migrate_config()` has a genuine template to read.

Run with:  python -m pytest tests/test_plugin_root_repoint.py -q
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

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
import init_project as ip  # noqa: E402

try:
    import yaml  # noqa: E402

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False


class _RepointFixtureBase(unittest.TestCase):
    """Builds a temp project + two fake plugin install trees: the LIVE one
    (`self.plugin_root`, pinned to `self.plugin_root_version`) and a STALE
    one (`self.old_plugin_root`, simulating a superseded cache directory a
    config's `plugin_root:` might still point at)."""

    LIVE_VERSION = "1.1.0"
    OLD_VERSION = "1.0.0"

    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required for plugin_root repoint tests")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_root_repoint_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin-cache" / self.LIVE_VERSION
        self.old_plugin_root = self.tmp / "plugin-cache" / self.OLD_VERSION
        self.planwise_dir = self.project_root / "planwise"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        self.old_plugin_root.mkdir(parents=True, exist_ok=True)

        self._write_plugin_json(self.plugin_root, self.LIVE_VERSION)
        self._write_plugin_json(self.old_plugin_root, self.OLD_VERSION)

        # A genuine shipped template, so migrate_config() has real content.
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))

        self.cfg = ip.InitConfig(
            project_name="RepointFixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self.LIVE_VERSION,
        )

        # Scope the rule-refresh loop to nothing, mirroring
        # _UpgradeArtifactsFixtureBase — this test suite is about the
        # config-write commit point, not artifact disposition.
        rules_patch = mock.patch.object(ip, "INSTALLED_RULES", [])
        rules_patch.start()
        self.addCleanup(rules_patch.stop)

    @staticmethod
    def _write_plugin_json(root: Path, version: str) -> None:
        claude_plugin_dir = root / ".claude-plugin"
        claude_plugin_dir.mkdir(parents=True, exist_ok=True)
        (claude_plugin_dir / "plugin.json").write_text(
            json.dumps({"version": version}), encoding="utf-8"
        )

    def config_path(self) -> Path:
        return self.planwise_dir / "config.yaml"

    def write_config(self, text: str) -> Path:
        path = self.config_path()
        path.write_text(text, encoding="utf-8")
        return path

    def read_config(self) -> str:
        return self.config_path().read_text(encoding="utf-8")

    def load_config(self) -> dict:
        return yaml.safe_load(self.read_config()) or {}

    def _posix(self, p: Path) -> str:
        return str(p).replace("\\", "/")

    def config_text(self, plugin_root: Path, plugin_version: str) -> str:
        return (
            f'plugin_root: "{self._posix(plugin_root)}"\n'
            f'plugin_version: "{plugin_version}"\n'
        )

    def run_upgrade_quiet(self) -> int:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ip._run_upgrade(self.cfg)
        self._last_stdout = buf.getvalue()
        return code


# ---------------------------------------------------------------------------
# End-to-end: a stale plugin_root gets repointed alongside the version bump
# ---------------------------------------------------------------------------
class TestUpgradeCommitPointRepointsRoot(_RepointFixtureBase):

    def test_upgrade_repoints_root_and_bumps_version_together(self):
        self.write_config(self.config_text(self.old_plugin_root, self.OLD_VERSION))

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        data = self.load_config()
        self.assertEqual(data["plugin_version"], self.LIVE_VERSION)
        self.assertEqual(Path(data["plugin_root"]), Path(self._posix(self.plugin_root)))
        self.assertIn("Plugin root repointed", self._last_stdout)

    def test_already_up_to_date_still_repoints_a_stale_root(self):
        """The residual case a version-bump-only commit point can never
        reach: the version gate would otherwise exit before ever running."""
        self.write_config(self.config_text(self.old_plugin_root, self.LIVE_VERSION))

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        data = self.load_config()
        self.assertEqual(data["plugin_version"], self.LIVE_VERSION, "version must not change")
        self.assertEqual(Path(data["plugin_root"]), Path(self._posix(self.plugin_root)))
        self.assertIn("plugin_root repointed", self._last_stdout.lower())

    def test_already_up_to_date_with_no_root_drift_writes_nothing(self):
        before = self.config_text(self.plugin_root, self.LIVE_VERSION)
        self.write_config(before)

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.read_config(), before, "a true no-op must not touch the file")
        self.assertIn("Already up to date.", self._last_stdout)


# ---------------------------------------------------------------------------
# The current-version branch must not silently drop an explicit --token-saver
# ---------------------------------------------------------------------------
class TestTokenSaverHonoredOnCurrentVersionBranch(_RepointFixtureBase):
    """The token_saver flip below the version gate never runs when the pin is
    already current. Because that branch is reachable (it is what repoints a
    stale root), a caller who passed --token-saver would otherwise have the
    flag silently ignored."""

    def config_text_with_token_saver(self, plugin_root: Path, plugin_version: str) -> str:
        return (
            f'plugin_root: "{self._posix(plugin_root)}"\n'
            f'plugin_version: "{plugin_version}"\n'
            "context:\n"
            "  token_saver: false\n"
        )

    def test_token_saver_flips_on_the_repoint_only_branch(self):
        self.write_config(
            self.config_text_with_token_saver(self.old_plugin_root, self.LIVE_VERSION)
        )
        self.cfg.token_saver = True

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        data = self.load_config()
        self.assertIs(data["context"]["token_saver"], True, "--token-saver must not be dropped")
        self.assertEqual(Path(data["plugin_root"]), Path(self._posix(self.plugin_root)))
        self.assertEqual(data["plugin_version"], self.LIVE_VERSION, "version must not change")
        self.assertIn("Token Saver enabled.", self._last_stdout)

    def test_token_saver_flips_when_nothing_else_needs_doing(self):
        self.write_config(
            self.config_text_with_token_saver(self.plugin_root, self.LIVE_VERSION)
        )
        self.cfg.token_saver = True

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        data = self.load_config()
        self.assertIs(data["context"]["token_saver"], True)
        self.assertEqual(Path(data["plugin_root"]), Path(self._posix(self.plugin_root)))
        self.assertIn("Token Saver enabled.", self._last_stdout)

    def test_absent_token_saver_key_is_a_silent_no_op(self):
        """No context block to flip: the run still repoints and must not fail."""
        self.write_config(self.config_text(self.old_plugin_root, self.LIVE_VERSION))
        self.cfg.token_saver = True

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            Path(self.load_config()["plugin_root"]), Path(self._posix(self.plugin_root))
        )
        self.assertNotIn("Token Saver enabled.", self._last_stdout)

    def test_no_flag_leaves_token_saver_alone(self):
        before = self.config_text_with_token_saver(self.plugin_root, self.LIVE_VERSION)
        self.write_config(before)

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.read_config(), before, "no flag, no drift -> no write at all")


# ---------------------------------------------------------------------------
# Atomicity: every abort path leaves BOTH keys untouched
# ---------------------------------------------------------------------------
class TestAbortedUpgradeLeavesPairUntouched(_RepointFixtureBase):

    def test_unparseable_config_leaves_both_keys_untouched(self):
        before = self.config_text(self.old_plugin_root, self.OLD_VERSION) + "broken: [unclosed\n"
        self.write_config(before)

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 2)
        self.assertEqual(self.read_config(), before, "an unparseable config must be left alone")

    def test_pyyaml_missing_leaves_both_keys_untouched(self):
        before = self.config_text(self.old_plugin_root, self.OLD_VERSION)
        self.write_config(before)

        with mock.patch.object(ip, "HAS_YAML", False):
            exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 2)
        self.assertEqual(self.read_config(), before)

    def test_migrate_phase_failure_leaves_both_keys_untouched(self):
        before = self.config_text(self.old_plugin_root, self.OLD_VERSION)
        self.write_config(before)
        (self.plugin_root / "config.yaml.template").unlink()  # migrate_config() -> FileNotFoundError

        exit_code = self.run_upgrade_quiet()

        self.assertEqual(exit_code, 2)
        self.assertEqual(self.read_config(), before)

    def test_commit_point_write_failure_rolls_back_both_edits(self):
        """Direct test of _commit_upgrade_pin()'s atomicity: a value that
        would corrupt the YAML on the SECOND edit must also undo the FIRST
        edit already applied to the in-memory buffer — because both live in
        one write_config_checked() call, not two."""
        before = self.config_text(self.old_plugin_root, self.OLD_VERSION)
        path = self.write_config(before)

        # An embedded quote breaks the written plugin_root line's YAML
        # quoting; write_config_checked()'s post-write parse check must
        # catch it and restore the pre-write bytes.
        corrupting_root = Path('bad"root')

        with self.assertRaises(config_loader.ConfigWriteError):
            ip._commit_upgrade_pin(path, "9.9.9", corrupting_root)

        self.assertEqual(
            self.read_config(), before,
            "a rolled-back commit-point write must leave BOTH keys unchanged, "
            "including the version edit that had already been applied to the "
            "in-memory buffer before the write",
        )


# ---------------------------------------------------------------------------
# _repoint_plugin_root() — standalone, comment-preserving, same shape as
# _bump_plugin_version()
# ---------------------------------------------------------------------------
ANNOTATED = """# Project config
plugin_root: "/plugins/planwise/1.0.4"
plugin_version: "1.0.4"       # do not hand-edit — /planwise upgrade owns this

project:
  name: Annotated
"""


class TestRepointPluginRootStandalone(_RepointFixtureBase):

    def test_happy_path_edits_the_line_in_place(self):
        path = self.write_config(ANNOTATED)
        ip._repoint_plugin_root(path, self.plugin_root)

        self.assertEqual(Path(self.load_config()["plugin_root"]), Path(self._posix(self.plugin_root)))
        result = self.read_config()
        self.assertIn("# do not hand-edit — /planwise upgrade owns this", result)
        self.assertIn("project:\n  name: Annotated", result)

    def test_fallback_appends_when_key_absent(self):
        legacy = ANNOTATED.replace('plugin_root: "/plugins/planwise/1.0.4"\n', "")
        path = self.write_config(legacy)
        ip._repoint_plugin_root(path, self.plugin_root)

        result = self.read_config()
        self.assertTrue(result.startswith(legacy), "the fallback must append, never re-emit the file")
        self.assertEqual(Path(self.load_config()["plugin_root"]), Path(self._posix(self.plugin_root)))

    def test_corrupting_value_is_rolled_back(self):
        path = self.write_config(ANNOTATED)
        with self.assertRaises(config_loader.ConfigWriteError):
            ip._repoint_plugin_root(path, Path('bad"root'))
        self.assertEqual(self.read_config(), ANNOTATED)


# ---------------------------------------------------------------------------
# Doctor: plugin_root dangling / version-mismatch flags
# ---------------------------------------------------------------------------
class TestDoctorPluginRootChecks(_RepointFixtureBase):

    def test_flags_dangling_plugin_root(self):
        nonexistent = self.tmp / "plugin-cache" / "0.9.0-gone"
        self.write_config(self.config_text(nonexistent, self.LIVE_VERSION))

        gate = ip._doctor_version_gate(self.cfg)

        self.assertEqual(gate["state"], "root_dangling")
        self.assertIn("does not exist", gate["report"])
        self.assertIn("/planwise upgrade", gate["report"])

    def test_flags_plugin_root_version_mismatch(self):
        self.write_config(self.config_text(self.old_plugin_root, self.LIVE_VERSION))

        gate = ip._doctor_version_gate(self.cfg)

        self.assertEqual(gate["state"], "root_mismatch")
        self.assertIn(self.OLD_VERSION, gate["report"])
        self.assertIn(self.LIVE_VERSION, gate["report"])

    def test_ok_when_pin_and_root_both_match(self):
        self.write_config(self.config_text(self.plugin_root, self.LIVE_VERSION))

        gate = ip._doctor_version_gate(self.cfg)

        self.assertEqual(gate["state"], "ok")

    def test_skips_root_check_when_key_absent(self):
        self.write_config(f'plugin_version: "{self.LIVE_VERSION}"\n')

        gate = ip._doctor_version_gate(self.cfg)

        self.assertEqual(gate["state"], "ok", "a missing plugin_root key must not be flagged")

    def test_version_drift_takes_precedence_over_a_dangling_root(self):
        nonexistent = self.tmp / "plugin-cache" / "0.9.0-gone"
        self.write_config(self.config_text(nonexistent, self.OLD_VERSION))

        gate = ip._doctor_version_gate(self.cfg)

        self.assertEqual(
            gate["state"], "drift",
            "version drift must be reported before the root is ever inspected",
        )


if __name__ == "__main__":
    unittest.main()
