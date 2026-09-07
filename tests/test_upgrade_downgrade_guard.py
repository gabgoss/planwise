#!/usr/bin/env python3
"""Regression tests for the script-side downgrade guard on `--upgrade`.

The "did you downgrade?" check used to live ONLY in the upgrade handler.
`_run_upgrade()` treated `pinned != target` as its single go-ahead condition
and never distinguished newer-than from older-than, so invoking an older
plugin cache's `init_project.py --upgrade` directly ran a full upgrade
backwards with no warning and no prompt — refreshing installed artifacts from
the older tree and, since the commit point now pins `plugin_root` alongside
`plugin_version`, repointing the config at that older tree as well. A handler
gate protects only handler-mediated invocations, and this script is a
documented, directly-runnable entry point.

These tests pin the contract that closes it:

  * `_compare_versions()` compares PER COMPONENT AS INTEGERS. Read as text,
    `"1.0.10" < "1.0.9"`, so a lexical test would read the tenth patch release
    of any minor line as a downgrade and refuse a genuine upgrade.
  * Component counts may differ (`0.0.0` is the never-pinned sentinel, a
    hotfix ships as `1.0.5.1`), so the shorter tuple is zero-padded rather
    than compared at unequal width.
  * A backwards run is REFUSED by default, before the migrate phase and
    before the already-up-to-date branch, with NOTHING written. The message
    names the pinned version, the executing plugin's version, and the
    executing plugin root, so the user can see which tree they invoked.
  * `--allow-downgrade` is the explicit opt-in, and a sanctioned downgrade
    still reaches the ordinary commit point — `plugin_version` and
    `plugin_root` land together in one write, never half-committed.
  * Forward and equal-version runs are unaffected.
  * An unparseable version yields no direction, and an unknown direction is
    not a proven backwards one: such a run proceeds exactly as before rather
    than refusing on a guess.

Fixture tree mirrors `_RepointFixtureBase` in test_plugin_root_repoint.py:
`INSTALLED_RULES` is patched to empty so `_run_upgrade()` can be driven
end-to-end without every real shipped rule file on disk, and the real shipped
`config.yaml.template` is copied in so `migrate_config()` has a genuine
template to read.

Run with:  python -m pytest tests/test_upgrade_downgrade_guard.py -q
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
_SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import init_project as ip  # noqa: E402
import artifact_upgrade  # noqa: E402 -- patch-target home for _run_upgrade()

INIT_PROJECT = _SCRIPTS / "init_project.py"
UPGRADE_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "upgrade.md"
)

try:
    import yaml  # noqa: E402

    HAS_YAML = True
except ImportError:  # pragma: no cover - the suite needs PyYAML
    HAS_YAML = False


# ---------------------------------------------------------------------------
# Pure comparison helpers — no fixture needed
# ---------------------------------------------------------------------------
class TestVersionComparisonIsNumericPerComponent(unittest.TestCase):
    """The defect a lexical comparison would introduce is not hypothetical:
    every minor line reaches a tenth patch release eventually, and from that
    release on, a string comparison reports every upgrade as a downgrade."""

    def test_ten_sorts_above_nine_numerically(self):
        # The headline case. Lexically, "1.0.10" < "1.0.9".
        self.assertEqual(artifact_upgrade._compare_versions("1.0.10", "1.0.9"), 1)
        self.assertEqual(artifact_upgrade._compare_versions("1.0.9", "1.0.10"), -1)

    def test_lexical_comparison_would_disagree(self):
        # Pinned here as the contrast case, so a later refactor back to a
        # string compare fails loudly instead of silently inverting.
        self.assertLess("1.0.10", "1.0.9")
        self.assertEqual(artifact_upgrade._compare_versions("1.0.10", "1.0.9"), 1)

    def test_equal_versions_compare_equal(self):
        self.assertEqual(artifact_upgrade._compare_versions("1.0.5", "1.0.5"), 0)

    def test_never_pinned_sentinel_is_below_everything(self):
        self.assertEqual(artifact_upgrade._compare_versions("0.0.0", "1.0.0"), -1)

    def test_four_component_hotfix_sorts_above_the_release_it_patches(self):
        # Zero-padding, not truncation: 1.0.5.1 is NEWER than 1.0.5, and the
        # two must not compare equal just because the widths differ.
        self.assertEqual(artifact_upgrade._compare_versions("1.0.5.1", "1.0.5"), 1)
        self.assertEqual(artifact_upgrade._compare_versions("1.0.5", "1.0.5.1"), -1)

    def test_unparseable_component_yields_no_direction(self):
        self.assertIsNone(artifact_upgrade._version_tuple("1.0.0-beta"))
        self.assertIsNone(artifact_upgrade._version_tuple("v1.0.0"))
        self.assertIsNone(artifact_upgrade._version_tuple(""))
        self.assertIsNone(artifact_upgrade._compare_versions("1.0.0-beta", "1.0.0"))
        self.assertIsNone(artifact_upgrade._compare_versions("1.0.0", "unknown"))

    def test_plain_numeric_versions_parse(self):
        self.assertEqual(artifact_upgrade._version_tuple("1.0.5"), (1, 0, 5))
        self.assertEqual(artifact_upgrade._version_tuple("1.0.5.1"), (1, 0, 5, 1))


# ---------------------------------------------------------------------------
# End-to-end fixture: a temp project plus one executing plugin tree whose
# version the test chooses, so the config pin can sit above, below, or on it.
# ---------------------------------------------------------------------------
class _DowngradeFixtureBase(unittest.TestCase):

    EXECUTING_VERSION = "1.1.0"

    def setUp(self):
        if not HAS_YAML:
            self.skipTest("PyYAML required for downgrade-guard tests")
        self.tmp = Path(tempfile.mkdtemp(prefix="pw_downgrade_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin-cache" / self.EXECUTING_VERSION
        self.planwise_dir = self.project_root / "planwise"
        self.planwise_dir.mkdir(parents=True, exist_ok=True)
        self.plugin_root.mkdir(parents=True, exist_ok=True)

        claude_plugin_dir = self.plugin_root / ".claude-plugin"
        claude_plugin_dir.mkdir(parents=True, exist_ok=True)
        (claude_plugin_dir / "plugin.json").write_text(
            json.dumps({"version": self.EXECUTING_VERSION}), encoding="utf-8"
        )

        # A genuine shipped template, so migrate_config() has real content.
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))

        self.cfg = ip.InitConfig(
            project_name="DowngradeFixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self.EXECUTING_VERSION,
        )

        rules_patch = mock.patch.object(artifact_upgrade, "INSTALLED_RULES", [])
        rules_patch.start()
        self.addCleanup(rules_patch.stop)

    def _posix(self, p: Path) -> str:
        return str(p).replace("\\", "/")

    def config_path(self) -> Path:
        return self.planwise_dir / "config.yaml"

    def write_config(self, pinned_version: str, plugin_root: Path = None) -> str:
        """Write a config pinning `pinned_version`, and return its exact text
        so a caller can assert nothing was written."""
        root = self.plugin_root if plugin_root is None else plugin_root
        text = (
            f'plugin_root: "{self._posix(root)}"\n'
            f'plugin_version: "{pinned_version}"\n'
        )
        self.config_path().write_text(text, encoding="utf-8")
        return text

    def read_config(self) -> str:
        return self.config_path().read_text(encoding="utf-8")

    def load_config(self) -> dict:
        return yaml.safe_load(self.read_config()) or {}

    def run_upgrade(self, allow_downgrade: bool = False) -> int:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ip._run_upgrade(self.cfg, allow_downgrade=allow_downgrade)
        self.stdout = out.getvalue()
        self.stderr = err.getvalue()
        return code


class TestBackwardsRunRefusedByDefault(_DowngradeFixtureBase):

    NEWER_PIN = "1.2.0"

    def test_backwards_run_exits_two_and_writes_nothing(self):
        before = self.write_config(self.NEWER_PIN)

        exit_code = self.run_upgrade()

        self.assertEqual(exit_code, 2)
        self.assertEqual(self.read_config(), before, "a refused run must write nothing")

    def test_refusal_names_pinned_version_executing_version_and_root(self):
        self.write_config(self.NEWER_PIN)

        self.run_upgrade()

        self.assertIn("Upgrade refused", self.stderr)
        self.assertIn(self.NEWER_PIN, self.stderr)
        self.assertIn(self.EXECUTING_VERSION, self.stderr)
        self.assertIn(str(self.plugin_root), self.stderr)
        self.assertIn("--allow-downgrade", self.stderr)

    def test_refusal_precedes_the_migrate_phase(self):
        # migrate_config() is the first writing phase. It must never be
        # reached: the gate sits above it, so a refused run cannot leave a
        # half-merged config behind.
        self.write_config(self.NEWER_PIN)
        with mock.patch.object(artifact_upgrade, "migrate_config") as migrate:
            exit_code = self.run_upgrade()
        self.assertEqual(exit_code, 2)
        migrate.assert_not_called()

    def test_tenth_patch_release_is_an_upgrade_not_a_downgrade(self):
        """The lexical trap, end to end: pinned 1.0.9 against an executing
        1.0.10 is a genuine UPGRADE and must not be refused."""
        self.cfg = ip.InitConfig(
            project_name="DowngradeFixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version="1.0.10",
        )
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": "1.0.10"}), encoding="utf-8"
        )
        self.write_config("1.0.9")

        exit_code = self.run_upgrade()

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Upgrade refused", self.stderr)
        self.assertEqual(self.load_config()["plugin_version"], "1.0.10")

    def test_unparseable_pin_is_not_refused(self):
        # An unknown direction is not a proven backwards one — the run
        # proceeds exactly as it did before the gate existed.
        self.write_config("1.0.0-beta")

        exit_code = self.run_upgrade()

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Upgrade refused", self.stderr)


class TestSanctionedDowngradeWritesBothKeysTogether(_DowngradeFixtureBase):

    NEWER_PIN = "1.2.0"

    def test_opt_in_proceeds_and_commits_version_and_root_together(self):
        # The config starts pinned NEWER and pointed at a stale root, so a
        # half-written commit would be visible as one key moving without the
        # other.
        stale_root = self.tmp / "plugin-cache" / "1.2.0"
        stale_root.mkdir(parents=True, exist_ok=True)
        self.write_config(self.NEWER_PIN, plugin_root=stale_root)

        exit_code = self.run_upgrade(allow_downgrade=True)

        self.assertEqual(exit_code, 0)
        data = self.load_config()
        self.assertEqual(data["plugin_version"], self.EXECUTING_VERSION)
        self.assertEqual(Path(data["plugin_root"]), Path(self._posix(self.plugin_root)))

    def test_opt_in_announces_the_direction_it_is_taking(self):
        self.write_config(self.NEWER_PIN)

        self.run_upgrade(allow_downgrade=True)

        self.assertIn("Downgrade authorized", self.stdout)
        self.assertIn("--allow-downgrade", self.stdout)
        self.assertIn(self.NEWER_PIN, self.stdout)
        self.assertIn(self.EXECUTING_VERSION, self.stdout)


class TestForwardAndEqualRunsUnaffected(_DowngradeFixtureBase):

    OLDER_PIN = "1.0.0"

    def test_forward_run_still_upgrades(self):
        self.write_config(self.OLDER_PIN)

        exit_code = self.run_upgrade()

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Upgrade refused", self.stderr)
        self.assertNotIn("Downgrade authorized", self.stdout)
        self.assertEqual(self.load_config()["plugin_version"], self.EXECUTING_VERSION)

    def test_equal_run_is_still_a_no_op(self):
        before = self.write_config(self.EXECUTING_VERSION)

        exit_code = self.run_upgrade()

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.read_config(), before, "a true no-op must not touch the file")
        self.assertIn("Already up to date.", self.stdout)

    def test_forward_run_with_the_flag_set_is_unchanged(self):
        # The flag authorizes a direction; it does not alter one.
        self.write_config(self.OLDER_PIN)

        exit_code = self.run_upgrade(allow_downgrade=True)

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Downgrade authorized", self.stdout)
        self.assertEqual(self.load_config()["plugin_version"], self.EXECUTING_VERSION)


class TestAllowDowngradeFlagIsUpgradeScoped(unittest.TestCase):
    """`--allow-downgrade` off the `--upgrade` path is a parser error, not a
    silent no-op — a caller must never believe a guard was waived on a run
    where the guard does not exist."""

    def test_flag_without_upgrade_is_a_parser_error(self):
        result = subprocess.run(
            [sys.executable, str(INIT_PROJECT), "--name", "X", "--allow-downgrade"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--allow-downgrade only applies together with --upgrade",
                      result.stderr)

    def test_flag_is_documented_in_help(self):
        result = subprocess.run(
            [sys.executable, str(INIT_PROJECT), "--help"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("--allow-downgrade", result.stdout)


class TestHandlerAndScriptAgree(unittest.TestCase):
    """The handler's interactive gate and the script's refusal are two halves
    of one contract: the handler asks, and the script enforces. If the
    handler's approved branch does not carry the flag the script requires,
    an approved downgrade dies at the writer with nothing written — a
    refusal the user already consented past."""

    def setUp(self):
        self.handler = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")

    def test_handler_carries_the_approval_into_the_writer_invocation(self):
        self.assertIn("--allow-downgrade", self.handler)

    def test_handler_quotes_the_scripts_own_refusal_wording(self):
        # Kept in sync deliberately: the handler tells the user what the
        # script prints, so the two must not drift into contradiction.
        self.assertIn(
            "Upgrade refused: config.yaml pins plugin_version", self.handler
        )

    def test_handler_states_the_numeric_comparison_rule(self):
        self.assertIn("per component", self.handler)
        self.assertIn("1.0.10", self.handler)


if __name__ == "__main__":
    unittest.main()
