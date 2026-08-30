#!/usr/bin/env python3
"""Unit tests (TDD) for the doctor stale-rule sweep and divergence lint.

Split from the rule de-scope + migration monolith along its Spec fixture
boundary. Covers the stale-descoped-rule sweep the doctor runs post-migration,
the installed-vs-shipped divergence linter (which reuses the upgrade-artifacts
fixture because its temp-tree layout and its INSTALLED_RULES scoping needs are
identical), and the verdict-override cache's shape and freshness gating.
Shares its fixture base and cross-seam helpers with the sibling modules this
monolith was split into; those live in conftest.py.

Run with:  python -m unittest tests/test_doctor_sweeps.py
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import doctor_sweeps  # noqa: E402 -- patch-target home for the doctor sweeps

from conftest import (  # noqa: E402
    _MigrationFixtureBase,
    _UpgradeArtifactsFixtureBase,
    _snapshot_tree,
    _verdict,
)


class TestInjectionFamilyRollup(_MigrationFixtureBase):
    """lint_rule_overscope()'s R1 extension: compute_injection_families() and
    its config-key ceiling reader (_read_injection_ceiling()).

    Reuses _MigrationFixtureBase for its `.claude/rules/planwise/` tree and
    InitConfig -- write_installed() already writes a rule file at an
    arbitrary `paths:` value, which is exactly what a family-grouping test
    needs (one glob per family, no EXPECTED_DESCOPED_ALL involvement).
    """

    def _backlog_glob(self) -> str:
        return f"{self.cfg.planwise_root}/{self.cfg.backlog_dir}/**"

    def _write_config_ceiling(self, ceiling: int) -> None:
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f"context:\n  token_saver_injection_ceiling: {ceiling}\n",
            encoding="utf-8",
        )

    def test_zero_report_on_empty_fixture(self):
        result = doctor_sweeps.compute_injection_families(self.cfg, [])
        self.assertEqual(result["families"], [])
        self.assertEqual(result["ceiling"], doctor_sweeps._INJECTION_CEILING_DEFAULT)

    def test_two_glob_families_grouped_with_totals_under_default_ceiling(self):
        self.write_installed(
            "plans-scoped.md", "Small plans-scoped rule.\n", self.plans_paths_value
        )
        self.write_installed(
            "backlog-scoped.md", "Small backlog-scoped rule.\n", self._backlog_glob()
        )

        flagged = doctor_sweeps.lint_rule_overscope(self.cfg)
        self.assertEqual(len(flagged), 2, "both fixture rules must be flagged")

        result = doctor_sweeps.compute_injection_families(self.cfg, flagged)

        self.assertEqual(result["ceiling"], doctor_sweeps._INJECTION_CEILING_DEFAULT)
        self.assertEqual(len(result["families"]), 2, "each glob is its own family")
        globs = {fam["glob"] for fam in result["families"]}
        self.assertEqual(globs, {self.plans_paths_value, self._backlog_glob()})
        for fam in result["families"]:
            self.assertEqual(fam["rule_count"], 1)
            expected_item = next(
                f for f in flagged if f["matched_glob"] == fam["glob"]
            )
            self.assertEqual(fam["total_lines"], expected_item["line_count"])
            self.assertEqual(fam["total_tokens"], expected_item["approx_tokens"])
            self.assertFalse(
                fam["over_ceiling"],
                "a two-line fixture rule must sit far under the 40000 default",
            )

    def test_family_over_ceiling_flag_fires_only_past_the_configured_ceiling(self):
        self._write_config_ceiling(200)
        self.write_installed(
            "small-plans.md", "One line.\n", self.plans_paths_value
        )
        # ~200 lines / ~1.7 KB — bytes-estimated to several hundred tokens, so
        # it clears the small configured ceilings below under the bytes-per-token
        # estimator (a 50-line body no longer would).
        large_body = "\n".join(f"line {i}" for i in range(200)) + "\n"
        self.write_installed("large-backlog.md", large_body, self._backlog_glob())

        flagged = doctor_sweeps.lint_rule_overscope(self.cfg)
        result = doctor_sweeps.compute_injection_families(self.cfg, flagged)

        self.assertEqual(result["ceiling"], 200)
        by_glob = {fam["glob"]: fam for fam in result["families"]}
        self.assertFalse(
            by_glob[self.plans_paths_value]["over_ceiling"],
            "the small family must stay within the configured ceiling",
        )
        self.assertTrue(
            by_glob[self._backlog_glob()]["over_ceiling"],
            "the large family must be flagged over the configured ceiling",
        )
        # Worst-first ordering: the over-ceiling family sorts first.
        self.assertEqual(result["families"][0]["glob"], self._backlog_glob())

    def test_read_injection_ceiling_default_when_config_absent(self):
        self.assertEqual(
            doctor_sweeps._read_injection_ceiling(self.cfg),
            doctor_sweeps._INJECTION_CEILING_DEFAULT,
        )

    def test_read_injection_ceiling_reads_configured_value(self):
        self._write_config_ceiling(12345)
        self.assertEqual(doctor_sweeps._read_injection_ceiling(self.cfg), 12345)

    def test_family_rollup_wired_into_doctor_path(self):
        import contextlib
        import io

        self.write_installed(
            "small-plans.md", "One line.\n", self.plans_paths_value
        )
        # ~200 lines / ~1.7 KB — bytes-estimated to several hundred tokens, so
        # it clears the small configured ceilings below under the bytes-per-token
        # estimator (a 50-line body no longer would).
        large_body = "\n".join(f"line {i}" for i in range(200)) + "\n"
        self.write_installed("large-backlog.md", large_body, self._backlog_glob())

        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n'
            "context:\n  token_saver_injection_ceiling: 100\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Injection families", stdout,
            "the per-family rollup must be printed by the live --doctor path, "
            "not merely computed",
        )
        self.assertIn(self._backlog_glob(), stdout)
        self.assertTrue(
            any(
                self._backlog_glob() in line
                for line in stdout.splitlines()
            ),
            "the over-ceiling family's glob must appear in the report",
        )
        self.assertIn("OVER CEILING", stdout)
        self.assertIn("within ceiling", stdout)


class TestDoctorStaleSweep(_MigrationFixtureBase):
    """sweep_stale_descoped_rules() + _run_prune_stale() + the _run_doctor()
    Stage 8 call site.

    The one-shot migrate_installed_rules() version gate is spent for any
    install already past RESCOPE_MIGRATION_VERSION, so these are the only
    remaining reach into stale de-scoped rules: a read-only sweep (recommends
    a disposition) and a separate opt-in writer (--prune-stale). Mirrors
    TestMigrationBranches' `ip._classify_diverged` monkeypatch seam so branch
    selection is tested independently of the structural_compare primitive.
    """

    def test_post_boundary_stale_subset_removable_and_tree_unchanged(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        # Post-boundary precondition: the one-shot migration's version gate
        # is already spent for this install.
        self.cfg.plugin_version = "1.0.4"
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1, f"{filename} must produce exactly one finding")
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(
            installed.exists(), "The bare sweep is read-only — it must never delete"
        )
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The bare sweep must leave the installed tree byte-for-byte unchanged",
        )

    def test_identical_leftover_removable_exact_fast_path(self):
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertEqual(matches[0]["confidence"], "exact")
        self.assertTrue(installed.exists(), "The sweep never deletes")

    def test_has_unique_is_preserved_with_unique_blocks(self):
        filename = "session-context-budget.md"
        shipped_body = "# Session Context Budget\n\nShipped body.\n"
        installed_body = (
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(matches[0]["unique_blocks"], ["# Extra"])
        self.assertEqual(
            installed.read_bytes(), before, "PRESERVE must never mutate the file"
        )

    def test_reorg_subset_is_preserved_not_auto_removed(self):
        filename = "session-execution-protocol.md"
        shipped_body = (
            "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed_body = "# Session Execution Protocol\n\nSection B.\nSection A.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "A reorg-confidence SUBSET is not auto-removable — it must escalate",
        )
        self.assertTrue(installed.exists())

    def test_prefix_rename_fingerprint_is_relocated(self):
        descoped_name = "callout-conventions.md"
        renamed = self.rules_dir / f"myproj-{descoped_name}"
        renamed.write_text(
            "# Callout Conventions\n\nPrefix-renamed workaround.\n", encoding="utf-8"
        )

        findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == renamed.name]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "RELOCATE")
        self.assertEqual(matches[0]["confidence"], "fingerprint")

    def test_prune_stale_removes_only_removable_and_writes_prunedmd(self):
        import datetime

        removable_filename = "session-planning-protocol.md"
        removable_body = "# Session Planning Protocol\n\nUntouched body.\n"
        self.write_shipped(removable_filename, removable_body)
        removable = self.write_installed(
            removable_filename, removable_body, self.old_default_for(removable_filename)
        )

        # No shipped reference written for this one — the "reference
        # unavailable, cannot prove stale" branch resolves it to PRESERVE.
        preserve_filename = "ei-fidelity.md"
        preserve_body = "# EI Fidelity\n\nNo shipped reference to compare against.\n"
        preserve = self.write_installed(
            preserve_filename, preserve_body, self.old_default_for(preserve_filename)
        )

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(removable.exists(), "A REMOVABLE finding must be unlinked")
        self.assertTrue(preserve.exists(), "A PRESERVE finding must never be unlinked")

        today = datetime.date.today().isoformat()
        pruned = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / "PRUNED.md"
        )
        self.assertTrue(pruned.exists())
        text = pruned.read_text(encoding="utf-8")
        self.assertIn("## Removed", text)
        self.assertIn(removable_filename, text)
        self.assertIn("## Preserved", text)
        self.assertIn(preserve_filename, text)

    def test_stage8_wired_into_doctor_path(self):
        import contextlib
        import io

        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        # A second file with genuine unique content (HAS_UNIQUE -> PRESERVE),
        # so the doctor path's PRESERVE action line is exercised too.
        preserve_filename = "session-context-budget.md"
        preserve_shipped_body = "# Session Context Budget\n\nShipped body.\n"
        preserve_installed_body = (
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(preserve_filename, preserve_shipped_body)
        preserve_installed = self.write_installed(
            preserve_filename, preserve_installed_body, self.old_default_for(preserve_filename)
        )

        # Pin the version-state gate to "ok" (pinned == installed) so
        # _run_doctor() proceeds past the preflight into Stage 8.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        before = _snapshot_tree(self.project_root)

        def _classify_side_effect(installed_norm, shipped_norm):
            if "Extra" in installed_norm:
                return _verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"])
            return _verdict("SUBSET", "contained")

        buf = io.StringIO()
        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", side_effect=_classify_side_effect
        ):
            with contextlib.redirect_stdout(buf):
                exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "stale de-scoped rule sweep", stdout,
            "Stage 8 must be invoked by _run_doctor(), not merely defined",
        )
        self.assertTrue(
            any(filename in line and "REMOVABLE" in line for line in stdout.splitlines()),
            "The doctor path must print a REMOVABLE row for the stale subset",
        )
        self.assertIn(
            "action:  remove with /planwise doctor --prune-stale", stdout,
            "REMOVABLE rows must print the documented action line",
        )
        self.assertIn(
            "action:  re-home to .claude/rules/<project>/<name>.md — do NOT delete", stdout,
            "PRESERVE rows must print the documented action line too",
        )
        self.assertTrue(installed.exists())
        self.assertTrue(preserve_installed.exists())
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The doctor path (bare --doctor) must never write or delete",
        )

    def test_notes_flagged_subset_preserved_and_survives_prune(self):
        import datetime

        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        # SUBSET + "contained" is otherwise safe-to-remove — the non-empty
        # notes field is the ONLY thing that must flip this to PRESERVE.
        notes_text = "tolerated a sub-noise-floor installed-only fragment"
        verdict = _verdict("SUBSET", "contained", notes=notes_text)
        with mock.patch.object(doctor_sweeps, "_classify_diverged", return_value=verdict):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "A subset with non-empty notes must NOT be REMOVABLE, even at "
            "exact/contained confidence",
        )
        self.assertIn(notes_text, matches[0]["reason"])
        self.assertTrue(installed.exists(), "The bare sweep is read-only")

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        with mock.patch.object(doctor_sweeps, "_classify_diverged", return_value=verdict):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(
            installed.exists(), "A notes-flagged subset must survive --prune-stale"
        )
        today = datetime.date.today().isoformat()
        pruned = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / "PRUNED.md"
        )
        text = pruned.read_text(encoding="utf-8")
        preserved_section = text.split("## Preserved", 1)[1]
        self.assertIn(
            filename, preserved_section,
            "The notes-flagged file must be listed under Preserved, not Removed",
        )

    def test_prune_writes_pre_image_backup_alongside_prunedmd(self):
        import datetime

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        original_content = installed.read_bytes()

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(installed.exists(), "A REMOVABLE finding must be unlinked")

        today = datetime.date.today().isoformat()
        backup = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}" / filename
        )
        self.assertTrue(
            backup.exists(),
            "A pre-image backup must be written alongside PRUNED.md before deletion",
        )
        self.assertEqual(
            backup.read_bytes(), original_content,
            "The backup must be an exact pre-image of the removed file",
        )

    def test_prune_stale_refuses_when_version_gate_not_ok(self):
        """No config.yaml -> the version-state gate is 'uninitialized'; the
        writer must refuse rather than sweep or delete anything."""
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        before = _snapshot_tree(self.project_root)

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "A gate refusal must never delete anything")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "A gate refusal must leave the installed tree byte-for-byte unchanged",
        )
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        self.assertFalse(
            backups_root.exists(), "A gate refusal must not create any prune folder"
        )

    def test_prune_unlink_failure_marks_remove_failed_no_orphan_backup(self):
        import datetime

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        # Pin the version-state gate to "ok" so _run_prune_stale() proceeds
        # past the preflight into the sweep/removal logic.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        original_unlink = Path.unlink

        def _raising_unlink(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: cannot remove")
            return original_unlink(self_path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", _raising_unlink):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "A failed unlink must leave the file in place")

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        preserved_section = pruned_text.split("## Preserved", 1)[1]
        self.assertIn(
            "[REMOVE_FAILED] — could not remove", preserved_section,
            "A failed unlink must be reported as REMOVE_FAILED, not REMOVABLE",
        )
        self.assertIn(filename, preserved_section)
        self.assertFalse(
            (out_dir / filename).exists(),
            "The orphan pre-image backup must be cleaned up after a failed unlink",
        )

    def test_second_prune_run_same_day_gets_uniquified_folder(self):
        import datetime

        # Pin the version-state gate to "ok" for both runs.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nUntouched body.\n"
        self.write_shipped(filename, body)
        self.write_installed(filename, body, self.old_default_for(filename))

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)

        # A second REMOVABLE file so the second same-day run has something to prune.
        filename2 = "markdown-conventions.md"
        body2 = "# Markdown Conventions\n\nUntouched body.\n"
        self.write_shipped(filename2, body2)
        self.write_installed(filename2, body2, self.old_default_for(filename2))

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result2, 0)

        today = datetime.date.today().isoformat()
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        first_dir = backups_root / f"prune-{today}"
        second_dir = backups_root / f"prune-{today}-2"

        self.assertTrue(first_dir.exists())
        self.assertTrue(
            second_dir.exists(), "A second same-day run must get a uniquified folder"
        )
        first_pruned = (first_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename, first_pruned)
        self.assertNotIn(
            filename2, first_pruned,
            "The first run's log must be untouched by the second run",
        )
        second_pruned = (second_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename2, second_pruned)


class TestInstalledDivergenceLint(_UpgradeArtifactsFixtureBase):
    """lint_installed_divergence() + the _run_doctor() Stage 9 call site.

    Generalizes TestDoctorStaleSweep's pattern from DESCOPED_RULES to the
    still-installed set (INSTALLED_RULES). Reuses
    _UpgradeArtifactsFixtureBase because its temp tree layout and its
    INSTALLED_RULES monkeypatch scope already match what
    lint_installed_divergence() walks — no new fixture needed.
    """

    def test_installed_rule_stale_subset_recommends_upgrade(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "the diverged installed rule must produce a finding")
        self.assertEqual(matches[0]["kind"], "rule")
        self.assertEqual(matches[0]["classification"], "SUBSET")
        self.assertIn("/planwise upgrade", matches[0]["recommendation"])
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The lint is read-only — it must never mutate the installed tree",
        )

    def test_installed_rule_has_unique_still_recommends_decide_callout(self):
        # A rule keeps the pre-existing decide-callout advice for a
        # HAS_UNIQUE verdict.
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["kind"], "rule")
        self.assertEqual(matches[0]["classification"], "HAS_UNIQUE")
        self.assertIn(
            "Choosing a Home for a Rule Customization", matches[0]["recommendation"]
        )

    def test_subset_with_notes_does_not_promise_unconditional_auto_adopt(self):
        # Regression (R1 finding 6): a notes-flagged SUBSET must not get the
        # unconditional "(auto-adopts shipped)" wording — the writer's own
        # auto-adopt gate (`is_subset(verdict) and not verdict.notes`) does
        # not fire on a non-empty notes field.
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)
        notes_text = "installed-only tokens tolerated as sub-noise-floor fragments"

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["classification"], "SUBSET")
        self.assertNotIn(
            "(auto-adopts shipped)", matches[0]["recommendation"],
            "a notes-flagged subset must not promise unconditional auto-adoption",
        )
        self.assertIn("customization_handoff", matches[0]["recommendation"])

    def test_non_utf8_installed_file_reported_unverifiable_not_crashed(self):
        # Regression (R1 findings 2 + 4): a non-UTF-8 installed file must
        # never crash the always-exit-0 doctor path — it must be reported as
        # an explicit unverifiable row instead of raising UnicodeDecodeError.
        self.write_shipped_rule("# Rule\n\nShipped body.\n")
        installed = self.rules_dst_dir / self.RULE_FILENAME
        # Write bytes that are invalid UTF-8 (a lone 0xFF byte).
        installed.write_bytes(b"---\ndescription: fixture rule\npaths: "
                               + self.RULE_PATHS_TEMPLATE.encode("utf-8")
                               + b"\n---\n# Rule\n\xff\xfe garbled\n")

        findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "an unreadable installed file must still be reported")
        self.assertEqual(matches[0]["classification"], "UNVERIFIABLE")
        self.assertIn("unreadable", matches[0]["recommendation"])

    def test_non_utf8_installed_file_doctor_path_exits_cleanly(self):
        import contextlib
        import io

        self.write_shipped_rule("# Rule\n\nShipped body.\n")
        (self.rules_dst_dir / self.RULE_FILENAME).write_bytes(
            b"---\ndescription: fixture rule\npaths: "
            + self.RULE_PATHS_TEMPLATE.encode("utf-8")
            + b"\n---\n# Rule\n\xff\xfe garbled\n"
        )
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)

        self.assertEqual(exit_code, 0, "bare --doctor must always exit 0, even over an unreadable file")
        self.assertIn("UNVERIFIABLE", buf.getvalue())

    def test_bom_identical_installed_file_not_reported(self):
        # Regression (R1 finding 3): both sides must be read with utf-8-sig
        # so a BOM'd-but-untouched installed file is not falsely flagged
        # HAS_UNIQUE (a BOM defeats normalize_rule_for_diff's frontmatter
        # detection under plain utf-8).
        body = "# Rule\n\nUntouched body.\n"
        self.write_shipped_rule(body)
        installed = self.write_installed_rule(body, self.RULE_PATHS_TEMPLATE)
        installed.write_bytes(b"\xef\xbb\xbf" + installed.read_bytes())  # prepend UTF-8 BOM

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            side_effect=AssertionError("a BOM-only difference must never reach the primitive"),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(matches, [], "a BOM'd-but-untouched file must NOT be reported")

    def test_missing_shipped_reference_reported_unverifiable_no_all_clear(self):
        # Regression (R1 finding 4): a missing shipped reference (broken/
        # partial install) must surface an explicit unverifiable row rather
        # than a silent skip that would let the caller's all-clear line print.
        installed = self.write_installed_rule(
            "# Rule\n\nSome body.\n", self.RULE_PATHS_TEMPLATE
        )
        # Deliberately do NOT call write_shipped_rule() — no shipped reference.

        findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1, "a missing shipped reference must produce a finding")
        self.assertEqual(matches[0]["classification"], "UNVERIFIABLE")
        self.assertIn("shipped reference unavailable", matches[0]["recommendation"])
        self.assertNotEqual(findings, [], "must never silently reduce to the all-clear state")

    def test_degraded_not_analyzed_verdict_reported_explicitly(self):
        # Regression (R1 finding 5): the degraded not-analyzed stand-in
        # (structural_compare unavailable) must produce an explicit
        # NOT_ANALYZED row, never a confident HAS_UNIQUE recommendation.
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            findings = ip.lint_installed_divergence(self.cfg)

        matches = [f for f in findings if f["path"] == str(installed)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["classification"], "NOT_ANALYZED")
        self.assertNotEqual(
            matches[0]["classification"], "HAS_UNIQUE",
            "an un-analyzed file must never be reported as a confident HAS_UNIQUE verdict",
        )
        self.assertIn("not analyzed", matches[0]["recommendation"].lower())

    def test_normalized_identical_copy_skipped_fast_path(self):
        body = "# Rule\n\nUntouched body.\n"
        self.write_shipped_rule(body)
        self.write_installed_rule(body, self.RULE_PATHS_TEMPLATE)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.lint_installed_divergence(self.cfg)

        self.assertEqual(findings, [], "A normalized-identical copy must not be reported")

    def test_stage9_wired_into_doctor_path(self):
        import contextlib
        import io

        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, self.RULE_PATHS_TEMPLATE)

        # Pin the version-state gate to "ok" (pinned == installed) so
        # _run_doctor() proceeds past the preflight into Stage 8 / Stage 9.
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        before = _snapshot_tree(self.project_root)

        buf = io.StringIO()
        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            with contextlib.redirect_stdout(buf):
                exit_code = ip._run_doctor(self.cfg)

        stdout = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "installed rule divergence lint", stdout,
            "Stage 9 must be invoked by _run_doctor(), not merely defined",
        )
        self.assertTrue(
            any(str(installed) in line and "SUBSET" in line for line in stdout.splitlines()),
            "The doctor path must print a SUBSET row for the diverged installed rule",
        )
        self.assertIn("recommend /planwise upgrade", stdout)
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "The doctor path (bare --doctor) must never write or delete",
        )


class TestVerdictOverrideShapeAndFreshness(unittest.TestCase):
    """_load_verdict_override(): malformed-entry containment (never crash) and
    the installed_sha256 freshness binding (missing/stale hash => ignored)."""

    INSTALLED_RAW = "---\ndescription: x\n---\n# Rule\n\nInstalled body.\n"

    def _sha(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _valid_entry(self, **overrides) -> dict:
        entry = {
            "classification": "SUBSET",
            "confidence": "contained",
            "unique_blocks": [],
            "shared_blocks": 3,
            "total_installed_blocks": 3,
            "installed_only_chars": 0,
            "unique_sample_tokens": [],
            "source": "agent",
            "notes": "",
            "installed_sha256": self._sha(self.INSTALLED_RAW),
        }
        entry.update(overrides)
        return entry

    def test_non_dict_entries_degrade_to_none_without_crashing(self):
        for bad in ("a plain string", ["a", "list"], 42, None, 3.14, True):
            with self.subTest(entry=bad):
                self.assertIsNone(
                    ip._load_verdict_override({"f.md": bad}, "f.md", self.INSTALLED_RAW),
                    f"a non-dict verdicts.json entry ({bad!r}) must degrade to "
                    "None (inline primitive), never crash",
                )

    def test_missing_installed_sha256_is_ignored(self):
        entry = self._valid_entry()
        del entry["installed_sha256"]
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW),
            "an entry with no installed_sha256 must be ignored (no freshness proof)",
        )

    def test_stale_installed_sha256_is_ignored(self):
        entry = self._valid_entry(installed_sha256=self._sha("different bytes now"))
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW),
            "a hash computed against different bytes must invalidate the override",
        )

    @unittest.skipUnless(ip.HAS_STRUCTURAL_COMPARE, "requires structural_compare")
    def test_matching_installed_sha256_returns_agent_verdict(self):
        verdict = ip._load_verdict_override(
            {"f.md": self._valid_entry()}, "f.md", self.INSTALLED_RAW
        )
        self.assertIsNotNone(verdict, "a fresh, well-formed entry must deserialize")
        self.assertEqual(verdict.classification, "SUBSET")
        self.assertEqual(verdict.source, "agent")

    def test_malformed_dict_entry_degrades_to_none(self):
        # dict-shaped but missing the required classification/confidence keys.
        entry = {"installed_sha256": self._sha(self.INSTALLED_RAW), "notes": ""}
        self.assertIsNone(
            ip._load_verdict_override({"f.md": entry}, "f.md", self.INSTALLED_RAW)
        )


