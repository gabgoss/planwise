#!/usr/bin/env python3
"""Regression test for the `_run_upgrade()` top-level failure guard.

Proves two things a unit test that calls `_run_upgrade()` directly cannot:

1. Reachability — the guard sits on the LIVE `--upgrade` dispatch path.
   `init_project.main()` is invoked exactly as the real CLI would (patched
   `sys.argv`, real argparse parsing, real InitConfig construction) — never
   `artifact_upgrade._run_upgrade()` in isolation. A guard that wrapped an
   orphaned helper the dispatch never reaches would leave this test's forced
   exception propagating WITHOUT the partial-upgrade message ever printing.
2. The resume story — not just that the guard fires, but that the
   already-refreshed file from the failed run stays refreshed and is
   skipped (not re-written) on the very next run, and the version pin is
   provably untouched by the aborted run.

Only the pin-commit step (the LAST step inside the guarded block) is
fault-injected; artifact refresh runs for real first, so the "already-
refreshed files are idempotent" half of the guard message is exercised, not
just asserted. Rule de-scope migration and the overscope advisory are
stubbed to no-ops — their own correctness is covered by
test_rule_descope_migration.py and test_doctor_sweeps.py respectively; this
file's only job is the guard + resume contract.

Run with:  python -m pytest tests/test_upgrade_guard_resume.py -q
"""

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import artifact_upgrade  # noqa: E402 -- patch-target home for the guarded call site


class TestUpgradeGuardResume(unittest.TestCase):
    """Forces a non-OSError in the last guarded step (the pin commit) via
    the real `--upgrade` dispatch entry point, then proves the resume story
    on a second, unpatched run.
    """

    RULE_FILENAME = "fixture-rule.md"
    RULE_PATHS_TEMPLATE = ".claude/agents/**"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="upgrade_guard_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        (self.project_root / "planwise").mkdir(parents=True)
        (self.plugin_root / ".claude-plugin").mkdir(parents=True)
        (self.plugin_root / "references").mkdir(parents=True)

        # Pin the fixture project one version behind the fixture plugin, so
        # the full upgrade path runs rather than the "already up to date"
        # early return.
        (self.project_root / "planwise" / "config.yaml").write_text(
            'plugin_version: "1.0.4"\n', encoding="utf-8"
        )
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text(
            '{"version": "1.0.5"}\n', encoding="utf-8"
        )
        real_template = (
            Path(__file__).resolve().parent.parent / "plugins" / "planwise"
            / "config.yaml.template"
        )
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))

        # One fixture rule, absent from the installed tree -- the "fresh
        # install" branch of upgrade_artifacts() refreshes it on run 1 and
        # must find it unchanged (a no-op) on run 2.
        (self.plugin_root / "references" / self.RULE_FILENAME).write_text(
            f"---\ndescription: fixture rule\npaths: {self.RULE_PATHS_TEMPLATE}\n---\n"
            "Fixture rule body.\n",
            encoding="utf-8",
        )
        self.installed_rule_path = (
            self.project_root / ".claude" / "rules" / "planwise" / self.RULE_FILENAME
        )
        self.config_path = self.project_root / "planwise" / "config.yaml"

        # Route the dispatch's plugin-root lookup to this fixture tree
        # instead of the real shipped plugin -- this is the ONLY thing
        # patched about environment resolution; --upgrade dispatch, arg
        # parsing, and InitConfig construction all run for real.
        get_root_patch = mock.patch.object(ip, "get_plugin_root", return_value=self.plugin_root)
        get_root_patch.start()
        self.addCleanup(get_root_patch.stop)

        rules_patch = mock.patch.object(
            artifact_upgrade, "INSTALLED_RULES", [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE)]
        )
        rules_patch.start()
        self.addCleanup(rules_patch.stop)

        # Steps 4 and 5 are out of scope for this guard/resume test (their
        # own correctness is covered by test_rule_descope_migration.py and
        # test_doctor_sweeps.py) -- stubbed to a no-op so only artifact
        # refresh (step 3) and the pin commit (step 6) do real work.
        migrate_rules_patch = mock.patch.object(
            artifact_upgrade, "migrate_installed_rules",
            return_value={"removed": [], "preserved": []},
        )
        migrate_rules_patch.start()
        self.addCleanup(migrate_rules_patch.stop)

        overscope_patch = mock.patch.object(artifact_upgrade, "lint_rule_overscope", return_value=[])
        overscope_patch.start()
        self.addCleanup(overscope_patch.stop)

    def _invoke_upgrade(self):
        """Run init_project.main() exactly as the real `--upgrade` CLI
        would, with stdout/stderr captured.

        Returns (stdout_text, stderr_text, exc). `exc` is the SystemExit on
        a normal exit, or whatever exception propagated out of main() on an
        unhandled failure (never re-raised here, so the caller can assert on
        the captured output and the exception together).
        """
        argv = [
            "init_project.py",
            "--project-root", str(self.project_root),
            "--name", "FixtureProject",
            "--upgrade",
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        exc = None
        with mock.patch.object(sys, "argv", argv), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                ip.main()
            except SystemExit as se:
                exc = se
            except Exception as e:  # the guard's bare `raise` surfaces here
                exc = e
        return stdout.getvalue(), stderr.getvalue(), exc

    def test_forced_exception_reports_and_resumes(self):
        # --- Run 1: the pin commit (the LAST guarded step) raises a
        # non-OSError. Everything before it -- including the real artifact
        # refresh -- runs for real first.
        with mock.patch.object(
            artifact_upgrade, "_commit_upgrade_pin", side_effect=RuntimeError("boom")
        ):
            stdout, stderr, exc = self._invoke_upgrade()

        # Never swallowed -- report-and-re-signal, not report-and-return: the
        # ORIGINAL exception (not a SystemExit substitute) reaches the
        # dispatch entry point's caller, which is what makes the real
        # process exit non-zero (CPython's default for an unhandled
        # exception) rather than a status the guard invented.
        self.assertIsInstance(
            exc, RuntimeError,
            f"guard must re-signal the original exception, never swallow it; stderr:\n{stderr}",
        )
        self.assertEqual(str(exc), "boom")

        self.assertIn(
            "partial upgrade — re-run to resume; already-refreshed files are "
            "idempotent and the version pin is unchanged",
            stderr,
        )
        self.assertIn("Upgrade failed: boom", stderr)

        # The artifact refresh (step 3) ran BEFORE the injected failure --
        # the fresh-install branch wrote the fixture rule for real.
        self.assertTrue(
            self.installed_rule_path.exists(),
            "artifact refresh must have completed before the pin-commit guard fired",
        )
        self.assertIn("Refreshed: 1", stdout)

        # The pin is untouched -- _commit_upgrade_pin never actually ran.
        self.assertIn('plugin_version: "1.0.4"', self.config_path.read_text(encoding="utf-8"))

        # --- Run 2: unpatched. Proceeds past the previously-refreshed file
        # (now reported Unchanged, not re-written) and completes the pin
        # commit for real -- the idempotency claim exercised, not merely
        # asserted.
        before_mtime = self.installed_rule_path.stat().st_mtime_ns
        stdout2, stderr2, exc2 = self._invoke_upgrade()

        self.assertIsInstance(exc2, SystemExit, f"stderr:\n{stderr2}")
        self.assertEqual(exc2.code, 0, f"expected a clean exit; stderr:\n{stderr2}")
        self.assertIn("Unchanged: 1", stdout2)
        self.assertEqual(
            self.installed_rule_path.stat().st_mtime_ns, before_mtime,
            "the already-refreshed file must not be re-written on the resume run",
        )
        self.assertIn('plugin_version: "1.0.5"', self.config_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
