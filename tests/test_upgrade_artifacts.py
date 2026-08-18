#!/usr/bin/env python3
"""Unit tests (TDD) for upgrade-artifact disposition during a version upgrade.

Split from the rule de-scope + migration monolith along its Spec fixture
boundary. Covers upgrade_artifacts()'s per-rule disposition table (refresh,
preserve, sidecar, remove), the verdict-notes and resolved-paths gates that
steer it, the customization transfer-then-remove sequencing at the classic
regression site, the verdict/notes gate combinations, and the degraded
fallback `_classify_diverged` takes when the structural_compare module is
unavailable. Shares its fixture base and cross-seam helpers with the sibling
modules this monolith was split into; those live in conftest.py.

Run with:  python -m unittest tests/test_upgrade_artifacts.py
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import rule_descope_migration  # noqa: E402 -- patch-target home for migrate_installed_rules()
import artifact_upgrade  # noqa: E402 -- patch-target home for upgrade_artifacts()/_run_upgrade()
import doctor_sweeps  # noqa: E402 -- patch-target home for one cross-seam _classify_diverged degraded-fallback case

from conftest import (  # noqa: E402
    _MigrationFixtureBase,
    _UpgradeArtifactsFixtureBase,
    _report_section,
    _snapshot_tree,
    _verdict,
)


class TestUpgradeArtifactsDisposition(_UpgradeArtifactsFixtureBase):
    """One test per Sites 2/3 disposition branch of upgrade_artifacts()."""

    def test_conflict_subset_refreshes_in_place_no_sidecar(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])

        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated),
            ip.normalize_rule_for_diff(shipped_raw),
            "Refreshed body must equal the shipped body (normalized)",
        )
        self.assertEqual(
            ip._extract_paths_value(updated), custom_paths,
            "The per-project paths: must be preserved across the refresh",
        )
        sidecar = (
            self.conflict_dir() / ".claude" / "rules" / "planwise"
            / f"{self.RULE_FILENAME}.new"
        )
        self.assertFalse(sidecar.exists(), "A SUBSET refresh must NOT write a .new sidecar")

    def test_conflict_has_unique_transfers_customization_then_adopts_shipped(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        # Automated, transfer-first: the customization is moved out FIRST,
        # verified, and only then is shipped adopted in place — the installed
        # copy is NOT left untouched (that was the old sidecar-and-stop policy).
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw),
            "HAS_UNIQUE rule must be adopted to shipped once its customization is transferred",
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)
        self.assertIn(str(installed), refreshed)
        self.assertEqual(refreshed_subsets, [], "adoption via transfer is NOT a stale-subset auto-adopt")
        self.assertEqual(conflicts, [], "a successfully transferred HAS_UNIQUE is not a conflict")

        self.assertEqual(len(transferred), 1)
        dst_path, transfer_path = transferred[0]
        self.assertEqual(dst_path, str(installed))
        transfer_file = Path(transfer_path)
        self.assertEqual(
            transfer_file.parent,
            self.transfer_dir(),
            "transfer target is {planwise_root}/upgrade-transfers/<from>-to-<to>/ "
            "(a dormant preservation dir outside .claude/rules/)",
        )
        transferred_text = transfer_file.read_text(encoding="utf-8")
        self.assertIn("# Extra", transferred_text)
        self.assertIn("User-added block.", transferred_text)

        index_path = self.conflict_dir() / "INDEX.md"
        self.assertFalse(
            index_path.exists(),
            "no unresolved conflict remains once the customization is transferred and adopted",
        )

    def test_has_unique_failed_transfer_preserves_and_writes_sidecar(self):
        """The failed-transfer carve-out: when the customization cannot be
        VERIFIED-written to the upgrade-transfers preservation file, the
        installed copy must be preserved byte-for-byte (never adopt/remove
        without a verified transfer) and the conservative shipped sidecar
        written."""
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        shipped = self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(artifact_upgrade, "_transfer_customization", return_value=None):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertEqual(
            installed.read_bytes(), before,
            "A failed transfer must preserve the installed file byte-for-byte",
        )
        self.assertNotIn(str(installed), refreshed)
        self.assertEqual(transferred, [], "a failed transfer must not be reported as transferred")
        self.assertTrue(conflicts, "a failed transfer must fall back to the conflict branch")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        sidecar = Path(sidecar_path)
        self.assertTrue(sidecar.exists(), ".new sidecar must be written on a failed transfer")
        self.assertEqual(sidecar.read_text(encoding="utf-8"), shipped.read_text(encoding="utf-8"))

    def test_byte_identical_skips_primitive(self):
        body = "# Rule\n\nIdentical body.\n"
        paths_value = ".claude/agents/**"
        self.write_shipped_rule(body, paths_value)
        installed_rule = self.write_installed_rule(body, paths_value)

        original = artifact_upgrade._classify_diverged
        artifact_upgrade._classify_diverged = mock.Mock(
            side_effect=AssertionError("fast path must not consult the primitive")
        )
        self.addCleanup(setattr, artifact_upgrade, "_classify_diverged", original)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertEqual(refreshed_subsets, [])
        self.assertIn(str(installed_rule), unchanged)


class TestMigrationVerdictNotesAndPathsGates(_MigrationFixtureBase):
    """Site-1 (migrate_installed_rules) safety fixes: the notes gate, the
    paths-preserve opt-out on a diverged (not just fast-path) body, the real
    structural_compare primitive on a genuine strict-prefix subset, the
    upgrade-backups/DISPOSITIONS.md pre-image, per-file OSError containment,
    and the degraded-mode ("NOT analyzed") wording.

    Like TestMigrationBranches, no fixture here sets `customization_handoff`,
    so the customization-bearing preserve assertions pin the conservative
    absent-key fallback (`report`). The `report+relocate` transfer-then-remove
    flow is pinned in TestSite1TransferThenRemove.
    """

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def test_notes_gate_preserves_diverged_subset(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(), "A notes-flagged SUBSET must be preserved, not removed"
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and notes_text in entry for entry in preserved),
            "The preserved notice must surface the verdict's notes text",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "A notes-flagged SUBSET must NOT appear under removed",
        )

    def test_diverged_stale_subset_paths_preserve_opt_out_default(self):
        filename = "verify-against-shipped-artifact.md"
        shipped_body = "# Verify Against Shipped Artifact\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Verify Against Shipped Artifact\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, installed_body, custom_paths)
        before = installed.read_bytes()

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A diverged stale-subset body with customized paths: must be kept "
            "when the preserve opt-out is enabled (the default)",
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "preserve opt-out covers paths" in entry
                for entry in preserved
            ),
            "The preserved notice must explain the paths opt-out covers the "
            "diverged body too",
        )

    def test_diverged_stale_subset_paths_opt_out_disabled_removed_with_info(self):
        filename = "verification-gates.md"
        shipped_body = "# Verification Gates\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Verification Gates\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, installed_body, custom_paths)
        self.write_upgrade_config(descope_preserve_paths_edits=False)

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "With the preserve opt-out disabled, a diverged stale-subset body "
            "with customized paths: must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        matches = [entry for entry in removed if filename in entry]
        self.assertTrue(matches, f"{filename} must be reported under removed")
        self.assertTrue(
            any("INFO" in entry for entry in matches),
            "The removed notice must carry the [INFO] token for the dropped paths: edit",
        )

    def test_real_primitive_subset_rule_removed_site1(self):
        # NO seam patching — exercises the real structural_compare primitive.
        filename = "verification-task-authoring.md"
        old_template = "{plans_path}"
        shipped_old_body = "# Verification Task Authoring\n\nOriginal line.\n"
        shipped_grown_body = shipped_old_body + "Grown extra line.\n"
        self.write_shipped(filename, shipped_grown_body)

        default_paths = self.old_default_for(filename)
        # Build the installed file the way install_rules() actually would:
        # update_frontmatter() on the (old, placeholder-carrying) shipped text.
        shipped_old_text = self._rule_text(shipped_old_body, old_template)
        installed_text = ip.update_frontmatter(shipped_old_text, default_paths)
        installed = self.rules_dir / filename
        installed.write_text(installed_text, encoding="utf-8")
        self.assertEqual(
            ip._extract_paths_value(installed_text), default_paths,
            "Fixture sanity: update_frontmatter must produce the resolved default",
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "A real strict-prefix subset (paths matching the old default) must "
            "be removed by the real classifier, with no verdict override",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(any(filename in entry for entry in removed))

    def test_backup_and_dispositions_written_on_site1_removal(self):
        filename = "session-planning-protocol.md"
        body = "# Session Planning Protocol\n\nBody content line.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(filename, body, self.old_default_for(filename))
        before = installed.read_bytes()
        to_version = self._to_version()

        ip.migrate_installed_rules(self.cfg, "0.0.0", to_version)

        self.assertFalse(installed.exists())
        backup_dir = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"0.0.0-to-{to_version}"
        )
        backup_file = backup_dir / ".claude" / "rules" / "planwise" / filename
        self.assertTrue(
            backup_file.exists(), "Site-1 removal must mirror the pre-image under upgrade-backups/"
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue(
            (backup_dir / "DISPOSITIONS.md").exists(),
            "DISPOSITIONS.md must be written alongside the backup",
        )

    def test_site1_containment_skips_unreadable_entry_and_continues(self):
        # A directory in place of the installed file forces read_text() to
        # raise OSError — the per-file containment must record it as skipped
        # and continue to the next (normal) fixture without raising.
        dir_filename = "callout-conventions.md"
        dir_path = self.rules_dir / dir_filename
        dir_path.mkdir(parents=True, exist_ok=True)

        normal_filename = "schema-pin-requirement.md"
        body = "# Schema Pin\n\nBody.\n"
        self.write_shipped(normal_filename, body)
        normal_installed = self.write_installed(
            normal_filename, body, self.old_default_for(normal_filename)
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            normal_installed.exists(),
            "The normal fixture must still be dispositioned despite the other's failure",
        )
        skipped = _report_section(report, "skipped")
        self.assertTrue(
            any(
                dir_filename in entry and "disposition failed" in entry
                for entry in skipped
            ),
            "The unreadable directory entry must be reported as skipped, not raise",
        )

    def test_degraded_mode_site1_preserved_not_analyzed(self):
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "Degraded mode must preserve, never remove")
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        matches = [entry for entry in preserved if filename in entry]
        self.assertTrue(matches)
        self.assertTrue(
            any("NOT analyzed" in entry for entry in matches),
            "Degraded-mode preserve notice must say the copy was NOT analyzed",
        )
        self.assertFalse(
            any("0 customized block(s)" in entry for entry in matches),
            "Degraded mode must never claim '0 customized block(s)' "
            "(analysis never ran)",
        )


class TestSite1TransferThenRemove(_MigrationFixtureBase):
    """The de-scope migration's customization_handoff gate: a
    customization-bearing de-scoped rule (HAS_UNIQUE, or a SUBSET whose notes
    flag tolerated installed-only content) transfers-then-removes under
    `customization_handoff: report+relocate` (the shipped template default),
    and preserves in place under the conservative modes or on ANY
    transfer/backup failure. The paths-edit preserve opt-out
    (`descope_preserve_paths_edits`, default true) takes PRECEDENCE over the
    handoff gate: a paths-customized copy is preserved in place even when the
    body also carries a customization — never weaker protection for the
    more-customized file. The migration reuses the artifact refresh
    writer's `_transfer_customization()` helper and destination convention —
    pinned here so the migration path can never drift onto a second transfer
    writer or a different destination.
    """

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def _transfer_dir(self) -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-transfers"
            / f"0.0.0-to-{self._to_version()}"
        )

    def _backup_dir(self) -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"0.0.0-to-{self._to_version()}"
        )

    def test_has_unique_transferred_then_removed_under_relocate(self):
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
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Under report+relocate a HAS_UNIQUE de-scoped rule must be removed "
            "after its customization is transferred",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(
            transfer_file.exists(),
            "The customization must land at the transfer helper's destination "
            "(upgrade-transfers/{from}-to-{to}/)",
        )
        self.assertIn(
            installed_body,
            transfer_file.read_text(encoding="utf-8"),
            "The transfer file must carry the full installed body",
        )
        backup_file = (
            self._backup_dir() / ".claude" / "rules" / "planwise" / filename
        )
        self.assertTrue(
            backup_file.exists(),
            "Removal must be preceded by a pre-image backup under upgrade-backups/",
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue(
            (self._backup_dir() / "DISPOSITIONS.md").exists(),
            "The removal must be logged to DISPOSITIONS.md",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed),
            "The removed notice must say the customization was transferred",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertFalse(
            any(filename in entry for entry in preserved),
            "A transferred-then-removed file must not also appear under preserved",
        )

    def test_notes_flagged_subset_transferred_then_removed_under_relocate(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        self.write_upgrade_config(customization_handoff="report+relocate")
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Under report+relocate a notes-flagged SUBSET (customization-bearing) "
            "must be removed after its customization is transferred",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(transfer_file.exists())
        self.assertIn(installed_body, transfer_file.read_text(encoding="utf-8"))
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed)
        )

    def test_report_mode_preserves_untouched_no_transfer_no_removal(self):
        filename = "ei-fidelity.md"
        shipped_body = "# EI Fidelity\n\nShipped body.\n"
        installed_body = "# EI Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "Under report (conservative) mode a HAS_UNIQUE de-scoped rule must "
            "be preserved in place",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "report mode must never write a transfer file",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(any(filename in entry for entry in preserved))

    def test_transfer_failure_means_no_removal(self):
        filename = "verification-gates.md"
        shipped_body = "# Verification Gates\n\nShipped body.\n"
        installed_body = "# Verification Gates\n\nShipped body.\n# Extra\nCustom.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(rule_descope_migration, "_transfer_customization", return_value=None):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A failed transfer must mean NO removal — never destroy the only "
            "copy of a customization",
        )
        self.assertEqual(installed.read_bytes(), before)
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "transfer failed" in entry
                for entry in preserved
            ),
            "The preserved notice must report the failed transfer",
        )

    def test_backup_failure_means_no_removal(self):
        filename = "verify-against-shipped-artifact.md"
        shipped_body = "# Verify Against Shipped Artifact\n\nShipped body.\n"
        installed_body = (
            "# Verify Against Shipped Artifact\n\nShipped body.\n# Extra\nCustom.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(rule_descope_migration, "_write_backup_preimage", return_value=False):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A failed pre-removal backup must mean NO removal",
        )
        self.assertEqual(installed.read_bytes(), before)
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(
            transfer_file.exists(),
            "The verified transfer precedes the backup, so the transfer file "
            "exists even when the backup then fails",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "backup" in entry for entry in preserved),
            "The preserved notice must report the failed backup",
        )

    def test_paths_and_body_customized_preserved_under_relocate_with_optout_default(self):
        # Regression (R1 finding 1): a rule customized in BOTH paths: AND body
        # must never get WEAKER protection than one customized in paths: alone.
        # With descope_preserve_paths_edits at its default (true, key absent),
        # the paths-opt-out takes precedence over customization_handoff:
        # report+relocate must NOT transfer-then-remove — preserve untouched.
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        before = installed.read_bytes()
        # Only customization_handoff set; descope_preserve_paths_edits absent
        # -> defaults to true via get_upgrade_config().
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A paths+body-customized rule must be preserved in place under "
            "report+relocate while the paths-edit preserve opt-out is on — "
            "the more-customized file must never get weaker protection than "
            "the less-customized one",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "The paths-opt-out precedence means NO transfer file is written",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(any(filename in entry for entry in removed))
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "paths-customized" in entry
                for entry in preserved
            ),
            "The preserve notice must attribute the preservation to the paths: "
            "customization (existing notice convention)",
        )

    def test_paths_and_body_customized_notes_flagged_subset_also_preserved(self):
        # Same precedence for the OTHER customization-bearing branch (a
        # notes-flagged SUBSET): the paths-opt-out wins over report+relocate.
        filename = "session-planning-protocol.md"
        shipped_body = "# Session Planning Protocol\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Planning Protocol\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict(
                "SUBSET", "exact",
                notes="installed-only tokens tolerated as sub-noise-floor fragments"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists())
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(self._transfer_dir().exists())
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "paths-customized" in entry for entry in preserved)
        )

    def test_paths_and_body_customized_relocated_when_optout_disabled(self):
        # Counterpart: with descope_preserve_paths_edits explicitly false, the
        # paths: customization no longer blocks the handoff gate — under
        # report+relocate the body customization transfers and the file is
        # removed (same flow as a paths-matching HAS_UNIQUE).
        filename = "discovery-and-exit-criteria.md"
        shipped_body = "# Discovery and Exit Criteria\n\nShipped body.\n"
        installed_body = (
            "# Discovery and Exit Criteria\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, "src/custom/**"   # customized paths: line
        )
        self.write_upgrade_config(
            customization_handoff="report+relocate",
            descope_preserve_paths_edits=False,
        )

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "With the paths-edit opt-out disabled, report+relocate transfers "
            "then removes a paths+body-customized rule",
        )
        transfer_file = self._transfer_dir() / filename
        self.assertTrue(transfer_file.exists())
        self.assertIn(installed_body, transfer_file.read_text(encoding="utf-8"))
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry and "transferred" in entry for entry in removed)
        )

    def test_reorg_subset_still_preserved_under_relocate(self):
        filename = "session-execution-protocol.md"
        shipped_body = (
            "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed_body = "# Session Execution Protocol\n\nSection B.\nSection A.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A reorg-confidence SUBSET is a confidence gap, not a genuine "
            "customization — it must stay preserved even under report+relocate",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "A reorg-inconclusive verdict must never trigger a transfer",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "inconclusive" in entry.lower()
                for entry in preserved
            )
        )

    def test_degraded_not_analyzed_still_preserved_under_relocate(self):
        filename = "task-content-fidelity.md"
        shipped_body = "# Task Content Fidelity\n\nShipped body.\n"
        installed_body = (
            "# Task Content Fidelity\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "The degraded not-analyzed stand-in must preserve even under "
            "report+relocate — there is no verdict evidence to transfer on",
        )
        self.assertEqual(installed.read_bytes(), before)
        self.assertFalse(
            self._transfer_dir().exists(),
            "Degraded mode must never write a transfer file",
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry and "NOT analyzed" in entry for entry in preserved)
        )

    def test_sweep_stays_read_only_under_relocate(self):
        filename = "callout-conventions.md"
        shipped_body = "# Callout Conventions\n\nShipped body.\n"
        installed_body = (
            "# Callout Conventions\n\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )
        self.write_upgrade_config(customization_handoff="report+relocate")
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.sweep_stale_descoped_rules(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(
            installed.exists(),
            "The doctor sweep is read-only regardless of customization_handoff "
            "— only the upgrade migration and the opt-in pruner write",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "report+relocate must not leak into the read-only sweep: the tree "
            "must be byte-for-byte unchanged",
        )


class TestUpgradeArtifactsVerdictNotesAndGates(_UpgradeArtifactsFixtureBase):
    """Sites 2/3 (upgrade_artifacts) disposition gates under the automated
    transfer-first policy: a notes-flagged SUBSET transfers-then-adopts (the
    tolerated fragment is moved to a project-owned file before shipped is
    adopted), a pure reorg-confidence agent subset auto-adopts via the
    frontmatter-preservation guard, the any-confidence rule refresh gate, the
    normalized-equal fast path, the real structural_compare primitive,
    upgrade-backups/DISPOSITIONS.md, sidecar/INDEX cleanup, per-file OSError
    containment, and degraded mode (never analyzed -> preserve + sidecar,
    nothing adopted or transferred).
    """

    def test_notes_gate_site2_rule_transfers_then_refreshes(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)
        notes_text = (
            "installed-only tokens present in sub-noise-floor fragments "
            "(tolerated as noise)"
        )

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact", notes=notes_text),
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        # A notes-flagged SUBSET is customization-bearing: the tolerated
        # installed-only fragment is transferred to a project-owned file
        # FIRST, then shipped is adopted in place (paths: preserved).
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw),
            "A notes-flagged SUBSET rule must be refreshed to shipped after transfer",
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)
        self.assertIn(str(installed), refreshed)
        self.assertNotIn(
            str(installed), refreshed_subsets,
            "a transferred adoption is NOT counted as a clean stale-subset adopt",
        )
        self.assertEqual(conflicts, [], "a successful transfer resolves the would-be conflict")
        self.assertEqual(len(transferred), 1)
        dst_path, transfer_path = transferred[0]
        self.assertEqual(dst_path, str(installed))
        transferred_text = Path(transfer_path).read_text(encoding="utf-8")
        self.assertIn(
            "Shipped superset body.", transferred_text,
            "the transfer file must carry the installed content (the notes fragment carrier)",
        )
        self.assertIn(notes_text, transferred_text,
                      "the transfer file must surface the verdict's notes")

    def test_reorg_subset_rule_refreshes_in_place(self):
        shipped_body = "# Rule\n\nSection A.\nSection B.\n"
        installed_body = "# Rule\n\nSection B.\nSection A.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertIn(
            str(installed), refreshed,
            "Rules keep the any-confidence SUBSET gate — a reorg subset still refreshes",
        )
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw)
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)

    def test_normalized_equal_byte_different_paths_rule_uses_fast_path(self):
        body = "# Rule\n\nIdentical normalized body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        installed_rule = self.write_installed_rule(body, ".claude/agents/**, custom/**")

        original = artifact_upgrade._classify_diverged
        artifact_upgrade._classify_diverged = mock.Mock(
            side_effect=AssertionError("fast path must not consult the primitive")
        )
        self.addCleanup(setattr, artifact_upgrade, "_classify_diverged", original)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertIn(str(installed_rule), unchanged)
        self.assertNotIn(str(installed_rule), refreshed)

    def test_real_primitive_subset_rule_refreshes(self):
        # NO seam patching — exercises the real structural_compare primitive.
        shipped_body = "# Rule\n\nShipped body.\nGrown extra line.\n"
        installed_body = "# Rule\n\nShipped body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        shipped_dst = self.write_shipped_rule(shipped_body)
        shipped_raw = shipped_dst.read_text(encoding="utf-8")
        installed = self.write_installed_rule(installed_body, custom_paths)

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertIn(str(installed), refreshed)
        self.assertIn(str(installed), refreshed_subsets)
        self.assertEqual(conflicts, [])
        updated = installed.read_text(encoding="utf-8")
        self.assertEqual(
            ip.normalize_rule_for_diff(updated), ip.normalize_rule_for_diff(shipped_raw)
        )
        self.assertEqual(ip._extract_paths_value(updated), custom_paths)

    def test_backup_and_dispositions_written_on_site2_rule_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, custom_paths)
        before = installed.read_bytes()

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            self.run_upgrade()

        backup_dir = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / "1.0.0-to-1.1.0"
        )
        backup_file = backup_dir / ".claude" / "rules" / "planwise" / self.RULE_FILENAME
        self.assertTrue(
            backup_file.exists(), "Site-2 adoption must mirror the pre-image under upgrade-backups/"
        )
        self.assertEqual(backup_file.read_bytes(), before)
        self.assertTrue((backup_dir / "DISPOSITIONS.md").exists())

    def test_stale_sidecar_removed_on_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")

        sidecar = (
            self.conflict_dir() / ".claude" / "rules" / "planwise"
            / f"{self.RULE_FILENAME}.new"
        )
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text("stale sidecar from an interrupted prior run", encoding="utf-8")
        self.assertTrue(sidecar.exists())

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertIn(str(installed), refreshed)
        self.assertFalse(
            sidecar.exists(), "A resolved adoption must remove the stale .new sidecar"
        )

    def test_stale_index_pruned_when_no_conflicts_remain(self):
        body = "# Rule\n\nIdentical body.\n"
        paths_value = ".claude/agents/**"
        self.write_shipped_rule(body, paths_value)
        self.write_installed_rule(body, paths_value)

        conflict_dir = self.conflict_dir()
        conflict_dir.mkdir(parents=True, exist_ok=True)
        index_path = conflict_dir / "INDEX.md"
        index_path.write_text("# stale index from a prior resolved run\n", encoding="utf-8")

        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
            self.run_upgrade()
        )

        self.assertEqual(conflicts, [])
        self.assertFalse(
            index_path.exists(),
            "A stale INDEX.md with no remaining .new sidecars must be pruned",
        )

    def test_site3_containment_skips_unreadable_rule_and_continues(self):
        second_rule = "second-rule.md"
        with mock.patch.object(
            artifact_upgrade, "INSTALLED_RULES",
            [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE),
             (second_rule, self.RULE_PATHS_TEMPLATE)],
        ):
            self.write_shipped_rule("# Rule\n\nShipped body.\n")
            # Directory in place of the installed file forces read_text() to
            # raise OSError for this entry only.
            dir_dst = self.rules_dst_dir / self.RULE_FILENAME
            dir_dst.mkdir(parents=True, exist_ok=True)

            second_shipped = self.refs_dir / second_rule
            second_shipped.write_text(
                self._rule_text("# Second Rule\n\nBody.\n", self.RULE_PATHS_TEMPLATE),
                encoding="utf-8",
            )

            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        second_installed = self.rules_dst_dir / second_rule
        self.assertTrue(
            second_installed.exists(),
            "The other rule must still be processed (fresh install) despite "
            "the directory entry's failure",
        )
        self.assertIn(str(second_installed), refreshed)

    def test_degraded_mode_upgrade_artifacts_nothing_refreshed(self):
        shipped_rule_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_rule_body = "# Rule\n\nShipped superset body.\n"
        custom_paths = ".claude/agents/**, custom/**"
        self.write_shipped_rule(shipped_rule_body)
        installed_rule = self.write_installed_rule(installed_rule_body, custom_paths)
        before_rule = installed_rule.read_bytes()

        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = (
                self.run_upgrade()
            )

        self.assertEqual(installed_rule.read_bytes(), before_rule)
        self.assertNotIn(str(installed_rule), refreshed)
        self.assertEqual(refreshed_subsets, [])
        self.assertEqual(len(conflicts), 1)


class TestClassifyDivergedDegradedFallback(unittest.TestCase):
    """Unit-level pin for the degraded-install verdict `_classify_diverged`
    manufactures when structural_compare is unavailable at call time."""

    def test_classify_diverged_degraded_on_missing_structural_compare(self):
        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            verdict = ip._classify_diverged("installed body", "shipped body")

        self.assertEqual(verdict.classification, "HAS_UNIQUE")
        self.assertTrue(
            getattr(verdict, "notes", ""),
            "The degraded stand-in verdict must carry a non-empty notes field",
        )


