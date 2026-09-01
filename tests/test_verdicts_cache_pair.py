#!/usr/bin/env python3
"""Regression fixtures for the verdict cache's version-pair resolution.

The interactive fan-out writes its comparator verdicts to
``upgrade-conflicts/{from}-to-{to}/verdicts.json`` and the ``--upgrade``
writer reads them back through `_load_verdicts_cache()` (`upgrade_io.py`).
Before this fix the reader re-derived the pair independently and a path
miss degraded to ``{}`` with no output, so a pair that resolved differently
between the fan-out and the writer (a plugin cache refreshed mid-session)
discarded the whole fan-out silently -- indistinguishable from the headless
"no fan-out happened" baseline.

Three reader states are pinned, exactly as the acceptance criteria name them:
  * absent cache          -> ``{}``, silent (the headless baseline is preserved)
  * mismatched-pair cache -> ``{}``, stderr warning naming the expected and
                              the found path
  * matching cache        -> consumed
plus the run-level pin: `_run_upgrade(cfg, expected_pair=...)` refuses (exit
2, nothing written) when the handler's pinned pair disagrees with the live
resolution, records the pair in the banner, and retires the cache at the
SAME path the readers resolved (`verdicts_cache_path()`). The CLI surface
(`--upgrade-pair FROM-to-TO`) is exercised through a subprocess so the
parser-level validation is what is proven, not a re-implementation of it.

Run with:  python -m pytest tests/test_verdicts_cache_pair.py -q
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
from upgrade_io import _load_verdicts_cache, verdicts_cache_path  # noqa: E402

from conftest import _UpgradeArtifactsFixtureBase  # noqa: E402

INIT_PROJECT = (
    Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "init_project.py"
)

FROM, TO = "1.0.0", "1.1.0"
OTHER_TO = "1.0.9"

CACHE_ENTRY = {
    "agent-authoring.md": {
        "classification": "SUBSET", "confidence": "contained", "unique_blocks": [],
        "home_hints": {}, "source": "agent", "shared_blocks": 1,
        "total_installed_blocks": 1, "installed_only_chars": 0,
        "unique_sample_tokens": [], "notes": "", "installed_sha256": "0" * 64,
    }
}


class TestVerdictsCacheThreeStates(_UpgradeArtifactsFixtureBase):
    """`_load_verdicts_cache()`: absent / mismatched pair / matching."""

    def _write_cache(self, to_version: str, name: str = "verdicts.json") -> Path:
        path = self.conflict_dir(FROM, to_version) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(CACHE_ENTRY), encoding="utf-8")
        return path

    def _load(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            loaded = _load_verdicts_cache(self.cfg, FROM, TO)
        return loaded, stderr.getvalue()

    def test_path_helper_is_the_single_derivation(self):
        self.assertEqual(
            verdicts_cache_path(self.cfg, FROM, TO),
            self.conflict_dir(FROM, TO) / "verdicts.json",
        )

    def test_absent_cache_is_silent_empty(self):
        loaded, err = self._load()
        self.assertEqual(loaded, {})
        self.assertEqual(err, "", "the headless baseline must stay silent")

    def test_absent_cache_with_empty_conflicts_root_is_silent(self):
        (self.project_root / self.cfg.planwise_root / "upgrade-conflicts").mkdir(parents=True)
        loaded, err = self._load()
        self.assertEqual(loaded, {})
        self.assertEqual(err, "")

    def test_matching_cache_is_consumed(self):
        self._write_cache(TO)
        loaded, err = self._load()
        self.assertEqual(loaded, CACHE_ENTRY)
        self.assertEqual(err, "")

    def test_mismatched_pair_cache_warns_naming_both_paths(self):
        stray = self._write_cache(OTHER_TO)
        loaded, err = self._load()
        self.assertEqual(loaded, {}, "another pair's verdicts must never be consumed")
        self.assertIn("Warning", err)
        self.assertIn(f"{FROM}-to-{TO}", err, "the warning names the resolved pair")
        self.assertIn(str(verdicts_cache_path(self.cfg, FROM, TO)), err, "expected path named")
        self.assertIn(str(stray), err, "found path named")
        self.assertIn("inline primitive", err)

    def test_mismatched_pair_lists_every_stray_cache(self):
        a = self._write_cache("1.0.8")
        b = self._write_cache(OTHER_TO)
        _, err = self._load()
        self.assertIn(str(a), err)
        self.assertIn(str(b), err)

    def test_retired_cache_under_another_pair_is_not_a_stray(self):
        """A `.consumed` file is a retired cache from an earlier run, not a
        fan-out that landed at the wrong pair -- it must not trigger the warning."""
        self._write_cache(OTHER_TO, name="verdicts.json.consumed")
        loaded, err = self._load()
        self.assertEqual(loaded, {})
        self.assertEqual(err, "")

    def test_matching_cache_wins_over_a_stray_without_warning(self):
        self._write_cache(TO)
        self._write_cache(OTHER_TO)
        loaded, err = self._load()
        self.assertEqual(loaded, CACHE_ENTRY)
        self.assertEqual(err, "", "a present matching cache is simply consumed")


class TestStrayCacheWarningReachesTheWriter(_UpgradeArtifactsFixtureBase):
    """The artifact-refresh writer surfaces the warning (it reads through the
    same helper) -- the whole point is that the miss is no longer silent."""

    def test_upgrade_artifacts_warns_on_stray_cache(self):
        body = "# Rule\n\nIdentical body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        self.write_installed_rule(body, ".claude/agents/**")
        stray = self.conflict_dir(FROM, OTHER_TO) / "verdicts.json"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text(json.dumps(CACHE_ENTRY), encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.run_upgrade(FROM, TO)
        self.assertIn(str(stray), stderr.getvalue())
        self.assertTrue(stray.exists(), "the stray cache is left in place, never consumed")


class TestUpgradePairPin(_UpgradeArtifactsFixtureBase):
    """`_run_upgrade(cfg, expected_pair=...)`: the handler's pinned pair."""

    def setUp(self):
        super().setUp()
        if not ip.HAS_YAML:
            self.skipTest("requires PyYAML (--upgrade hard-requires it)")
        # Minimal upgradeable fixture: pinned 1.0.0, target 1.1.0, identical
        # rule so the artifact refresh has nothing to dispose.
        self.cfg.plugin_version = TO
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_dir / "config.yaml"
        self.config_path.write_text(f'plugin_version: "{FROM}"\n', encoding="utf-8")
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))
        body = "# Rule\n\nIdentical body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        self.write_installed_rule(body, ".claude/agents/**")

    def _run(self, expected_pair):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ip._run_upgrade(self.cfg, expected_pair=expected_pair)
        return code, out.getvalue(), err.getvalue()

    def test_matching_pin_runs_and_banner_records_the_pair(self):
        code, out, _ = self._run((FROM, TO))
        self.assertEqual(code, 0)
        self.assertIn(f"Upgrade pair: {FROM}-to-{TO}", out)
        self.assertIn("matches --upgrade-pair", out)
        self.assertIn(str(verdicts_cache_path(self.cfg, FROM, TO)), out)
        self.assertIn("verdict cache absent", out)
        self.assertIn(f'plugin_version: "{TO}"', self.config_path.read_text(encoding="utf-8"))

    def test_headless_run_still_records_the_pair(self):
        code, out, _ = self._run(None)
        self.assertEqual(code, 0)
        self.assertIn(f"Upgrade pair: {FROM}-to-{TO}", out)
        self.assertNotIn("--upgrade-pair", out)

    def test_banner_reports_present_cache_and_retires_it_at_the_same_path(self):
        cache = verdicts_cache_path(self.cfg, FROM, TO)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("{}", encoding="utf-8")
        code, out, _ = self._run((FROM, TO))
        self.assertEqual(code, 0)
        self.assertIn("verdict cache present", out)
        self.assertFalse(cache.exists())
        self.assertTrue(cache.with_name("verdicts.json.consumed").exists())

    def test_mismatched_pin_refuses_before_any_write(self):
        before_config = self.config_path.read_bytes()
        stray = self.conflict_dir(FROM, OTHER_TO) / "verdicts.json"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("{}", encoding="utf-8")

        code, out, err = self._run((FROM, OTHER_TO))

        self.assertEqual(code, 2)
        self.assertIn("Upgrade refused", err)
        self.assertIn(f"{FROM}-to-{OTHER_TO}", err, "names the handler's pinned pair")
        self.assertIn(f"{FROM}-to-{TO}", err, "names the live resolution")
        self.assertEqual(out, "", "no banner -- nothing ran")
        self.assertEqual(self.config_path.read_bytes(), before_config, "config untouched")
        planwise_root = self.project_root / self.cfg.planwise_root
        for surface in ("upgrade-backups", "upgrade-transfers"):
            self.assertFalse((planwise_root / surface).exists(), f"{surface} must not be created")
        self.assertTrue(stray.exists(), "the other pair's cache is neither consumed nor retired")

    def test_mismatched_pin_refuses_even_when_already_up_to_date(self):
        """The already-up-to-date branch writes too (root repoint, feedback
        dir); a moved pair must block it as well."""
        self.config_path.write_text(f'plugin_version: "{TO}"\n', encoding="utf-8")
        before = self.config_path.read_bytes()
        code, out, err = self._run((FROM, TO))
        self.assertEqual(code, 2)
        self.assertIn("Upgrade refused", err)
        self.assertEqual(out, "")
        self.assertEqual(self.config_path.read_bytes(), before)


class TestUpgradePairCli(unittest.TestCase):
    """`--upgrade-pair` is validated by the parser before anything runs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="upgrade_pair_cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, str(INIT_PROJECT), "--name", "Fixture",
             "--project-root", str(self.tmp), *extra],
            capture_output=True, text=True, timeout=60,
        )

    def test_malformed_pair_is_a_parser_error(self):
        proc = self._run("--upgrade", "--upgrade-pair", "nonsense")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("--upgrade-pair", proc.stderr)
        self.assertIn("FROM-to-TO", proc.stderr)

    def test_pair_without_upgrade_is_a_parser_error(self):
        proc = self._run("--upgrade-pair", f"{FROM}-to-{TO}")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("--upgrade-pair only applies together with --upgrade", proc.stderr)

    def test_well_formed_pair_reaches_the_upgrade_gate(self):
        """No config.yaml at the project root: the run stops at the writer's
        own preflight ("run /planwise init before --upgrade"), proving the
        flag parsed and dispatch reached _run_upgrade()."""
        proc = self._run("--upgrade", "--upgrade-pair", f"{FROM}-to-{TO}")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("does not exist", proc.stderr)
        self.assertNotIn("--upgrade-pair", proc.stderr)


if __name__ == "__main__":
    unittest.main()
