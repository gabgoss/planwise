#!/usr/bin/env python3
"""Unit tests (TDD) for the rule de-scope + migration + linter contract -- core.

These tests are written BEFORE the implementation. They pin the compatibility
contract that the de-scope migration must satisfy:

  * INSTALLED_RULES is trimmed to ONLY the four `.claude/**`-scoped rules.
  * DESCOPED_RULES enumerates the sixteen author-time rules removed from the
    install set (handler-loaded from references/ instead).
  * migrate_installed_rules(cfg, from_version, to_version) removes an installed
    de-scoped rule when it is provably redundant: normalized body matches the
    shipped body (with paths: equal to the resolved OLD default, or the
    preserve opt-out disabled), or a high-confidence stale SUBSET with a clean
    notes field. A customization-bearing copy (HAS_UNIQUE, or a SUBSET whose
    notes flag tolerated installed-only content) is gated on the effective
    `upgrade.customization_handoff`: `report+relocate` verified-transfers the
    customization to the upgrade transfer helper's preservation home and only
    then backs up and removes the stale file; any other value (including the
    absent-key fallback, `report`) preserves it byte-for-byte with a re-home
    notice. A failed transfer or backup means NO removal. The migration never
    defaults to suggesting deletion of a preserved file.
  * lint_rule_overscope(cfg) flags plan-scoped rules (with a size/line field)
    without mutating anything on disk.

This module holds the migration core (rule partitioning, migration branch
dispositions, the overscope linter, upgrade-config foundation, and the
normalize-for-diff degraded fallback). It is one of five sibling modules this
monolith was split into by fixture boundary; the other four --
test_upgrade_artifacts.py, test_doctor_sweeps.py, test_customization_handoff.py,
and test_agent_mirror_sweep.py -- cover upgrade-artifact disposition, the
doctor stale-rule sweep, customization handoff / destructive-write gating, and
the orphaned-agent-mirror sweep respectively. Fixtures and helpers shared by
two or more of the five live in conftest.py.

Run with:  python -m unittest tests/test_rule_descope_migration.py

Until init_project.py grows the new symbols, every test below errors with an
AttributeError on the missing symbol (migrate_installed_rules,
lint_rule_overscope, DESCOPED_RULES, RESCOPE_MIGRATION_VERSION, or the trimmed
INSTALLED_RULES). That is the intended TDD red state, not a fixture bug.
"""

import json
import shutil
import sys
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_sweeps
import init_project as ip
import rule_descope_migration
from rule_divergence import _extract_paths_value, rule_history_digest
from upgrade_io import _installed_hash

from conftest import (
    EXPECTED_DESCOPED_ALL,
    _flatten_report,
    _MigrationFixtureBase,
    _report_section,
    _snapshot_tree,
    _verdict,
)

KEPT_RULES = {
    "agent-authoring.md",
    "skill-authoring.md",
    "rule-authoring.md",
    "artifact-self-containment.md",
}

# The sixteen author-time rules removed from the install set. Each is paired
# with the paths: template it carried BEFORE de-scoping, so the migration can
# reconstruct the OLD default and compare against the installed file.
EXPECTED_DESCOPED_PLANS = {
    "session-planning-protocol.md",
    "session-plan-requirements.md",
    "session-context-budget.md",
    "session-execution-protocol.md",
    "scaffolding-hygiene.md",
    "discovery-and-exit-criteria.md",
    "ei-fidelity.md",
    "schema-pin-requirement.md",
    "task-content-fidelity.md",
    "verification-gates.md",
    "verify-against-shipped-artifact.md",
    "verification-task-authoring.md",
}
# EXPECTED_DESCOPED_ALL itself now lives in conftest.py (imported above): the
# _MigrationFixtureBase fixture (also relocated there) has its own reference
# to it in write_shipped(), and a free-variable lookup resolves in the module
# where the function is DEFINED -- so the set must be visible in conftest's
# own namespace, not just re-derivable here.
EXPECTED_DESCOPED = EXPECTED_DESCOPED_PLANS | EXPECTED_DESCOPED_ALL


class TestRulePartition(_MigrationFixtureBase):
    """The INSTALLED_RULES trim and the DESCOPED_RULES enumeration."""

    def test_installed_rules_trimmed_to_four_claude_scoped(self):
        installed_names = {entry[0] for entry in ip.INSTALLED_RULES}
        self.assertEqual(
            installed_names,
            KEPT_RULES,
            "INSTALLED_RULES must contain ONLY the four .claude/**-scoped rules "
            "after de-scoping",
        )
        # None of the de-scoped rules may linger in the install set.
        self.assertFalse(
            installed_names & EXPECTED_DESCOPED,
            "No de-scoped rule may remain in INSTALLED_RULES",
        )
        # The kept rules must NOT be plan-scoped templates.
        for filename, paths_template in ip.INSTALLED_RULES:
            self.assertNotIn("{plans_path}", paths_template)

    def test_descoped_rules_enumeration(self):
        descoped = ip.DESCOPED_RULES
        names = {entry[0] for entry in descoped}
        self.assertEqual(
            names,
            EXPECTED_DESCOPED,
            "DESCOPED_RULES must list exactly the 16 de-scoped filenames",
        )
        self.assertEqual(len(descoped), 16, "DESCOPED_RULES must have 16 entries")

        templates = {entry[0]: entry[1] for entry in descoped}
        for filename in EXPECTED_DESCOPED_PLANS:
            self.assertEqual(
                templates[filename],
                "{plans_path}",
                f"{filename} must pair with the {{plans_path}} old template",
            )
        for filename in EXPECTED_DESCOPED_ALL:
            self.assertEqual(
                templates[filename],
                "{all_paths}",
                f"{filename} must pair with the {{all_paths}} old template",
            )

    def test_partition_is_disjoint_and_covers_old_install_set(self):
        installed_names = {entry[0] for entry in ip.INSTALLED_RULES}
        descoped_names = {entry[0] for entry in ip.DESCOPED_RULES}
        self.assertFalse(
            installed_names & descoped_names,
            "INSTALLED_RULES and DESCOPED_RULES must be disjoint",
        )
        self.assertEqual(
            installed_names | descoped_names,
            KEPT_RULES | EXPECTED_DESCOPED,
            "Together the two sets must cover the full pre-de-scope install set",
        )


class TestMigrationBranches(_MigrationFixtureBase):
    """One test per branch of migrate_installed_rules().

    No fixture here writes a `customization_handoff` key, so every
    customization-bearing preserve assertion below pins the conservative
    absent-key fallback (`report`): preserve in place, no transfer, no
    removal. The `report+relocate` transfer-then-remove flow is pinned
    separately in TestSite1TransferThenRemove.
    """

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def test_untouched_rule_is_removed(self):
        filename = "session-planning-protocol.md"
        body = "# Session Planning Protocol\n\nBody content line.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "An untouched de-scoped rule (matching body + old default paths) "
            "must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in removed),
            f"{filename} must be reported under the removed section",
        )

    def test_body_diverged_rule_is_preserved_with_notice(self):
        filename = "ei-fidelity.md"
        shipped_body = "# EI Fidelity\n\nOriginal shipped body.\n"
        edited_body = "# EI Fidelity\n\nUSER EDITED this body line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, edited_body, self.old_default_for(filename)
        )
        before = installed.read_bytes()

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "A body-diverged rule must be kept")
        self.assertEqual(
            installed.read_bytes(), before, "Diverged rule must be byte-for-byte unchanged"
        )
        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in notice),
            f"{filename} must be reported as a conflict/notice, not removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "A diverged rule must NOT appear under removed",
        )

    def test_paths_customized_rule_is_preserved_with_notice(self):
        filename = "callout-conventions.md"
        body = "# Callout Conventions\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", docs/**"
        installed = self.write_installed(filename, body, custom_paths)
        before = installed.read_bytes()

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(), "A paths-customized rule must be kept (body matches but paths differ)"
        )
        self.assertEqual(installed.read_bytes(), before, "Paths-customized rule must be unchanged")
        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in notice),
            f"{filename} (custom paths:) must be reported as a conflict/notice",
        )

    def test_notice_does_not_default_to_suggesting_delete(self):
        filename = "markdown-conventions.md"
        shipped_body = "# Markdown Conventions\n\nShipped.\n"
        edited_body = "# Markdown Conventions\n\nEdited by user.\n"
        self.write_shipped(filename, shipped_body)
        self.write_installed(filename, edited_body, self.old_default_for(filename))

        report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        notice = _report_section(report, "conflict", "notice", "preserved", "kept")
        self.assertTrue(notice, "A diverged rule must surface a notice")
        # The notice for a preserved file must not lead with a 'delete' verdict.
        for entry in notice:
            self.assertNotIn(
                "delete",
                entry.lower(),
                "Preserved-file notices must NOT default to suggesting deletion",
            )

    def test_non_descoped_rule_left_unchanged(self):
        # A project-authored rule that is not in DESCOPED_RULES.
        filename = "nhle-foo.md"
        body = "# Project Rule\n\nProject-authored, not shipped.\n"
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        installed = self.write_installed(filename, body, plan_scope)
        before = installed.read_bytes()

        ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "A non-de-scoped rule must be left in place")
        self.assertEqual(
            installed.read_bytes(),
            before,
            "A non-de-scoped, project-authored rule must be byte-for-byte unchanged",
        )

    def test_migration_is_idempotent(self):
        filename = "schema-pin-requirement.md"
        body = "# Schema Pin\n\nBody.\n"
        self.write_shipped(filename, body)
        self.write_installed(filename, body, self.old_default_for(filename))

        first = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())
        first_removed = _report_section(first, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in first_removed),
            "First run must remove the untouched de-scoped rule",
        )
        snapshot = _snapshot_tree(self.project_root)

        # Second run: nothing left to remove, no error, same end state.
        second = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())
        second_removed = _report_section(second, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in second_removed),
            "Second run must find nothing to remove (idempotent)",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root),
            snapshot,
            "Re-running the migration must not change the tree",
        )

    def test_version_gate_makes_migration_a_noop(self):
        filename = "discovery-and-exit-criteria.md"
        body = "# Discovery\n\nBody.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(
            filename, body, self.old_default_for(filename)
        )
        before = _snapshot_tree(self.project_root)

        # from_version already at/after the rescope migration version -> no-op.
        already_migrated = str(ip.RESCOPE_MIGRATION_VERSION)
        ip.migrate_installed_rules(
            self.cfg, already_migrated, self._to_version()
        )

        self.assertTrue(
            installed.exists(),
            "Version gate: when from_version >= RESCOPE_MIGRATION_VERSION the "
            "migration must touch nothing",
        )
        self.assertEqual(
            _snapshot_tree(self.project_root),
            before,
            "Version-gated no-op must leave the tree byte-for-byte identical",
        )

    # -- verdict-driven disposition cases (monkeypatch seam) -----------------

    def test_subset_of_reflowed_shipped_is_removed(self):
        filename = "session-plan-requirements.md"
        shipped_body = "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n"
        installed_body = "# Session Plan Requirements\n\nOriginal line.\n"
        self.write_shipped(filename, shipped_body)
        installed = self.write_installed(
            filename, installed_body, self.old_default_for(filename)
        )

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "A stale SUBSET (contained confidence) of the grown shipped "
            "reference must be removed",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertTrue(
            any(filename in entry for entry in removed),
            f"{filename} must be reported under removed",
        )

    def test_has_unique_is_preserved_with_block_count(self):
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
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(installed.exists(), "HAS_UNIQUE must be preserved, not removed")
        self.assertEqual(
            installed.read_bytes(), before, "HAS_UNIQUE file must be kept byte-for-byte"
        )
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "1 customized block" in entry
                for entry in preserved
            ),
            f"{filename} must be reported preserved with the unique block count",
        )
        removed = _report_section(report, "removed", "deleted")
        self.assertFalse(
            any(filename in entry for entry in removed),
            "HAS_UNIQUE must never appear under removed",
        )

    def test_reorg_subset_is_preserved_with_inconclusive_notice(self):
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

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=_verdict("SUBSET", "reorg")
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "A reorg SUBSET is headless-inconclusive, not auto-removed",
        )
        self.assertEqual(installed.read_bytes(), before)
        notice = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(
                filename in entry and "inconclusive" in entry.lower()
                for entry in notice
            ),
            f"{filename} must carry a headless-inconclusive notice",
        )

    def test_reorg_subset_from_agent_does_not_send_user_back_to_interactive(self):
        filename = "session-execution-protocol.md"
        self.write_shipped(
            filename, "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed = self.write_installed(
            filename,
            "# Session Execution Protocol\n\nSection B.\nSection A.\n",
            self.old_default_for(filename),
        )
        before = installed.read_bytes()
        agent_verdict = _verdict("SUBSET", "reorg")
        agent_verdict.source = "agent"

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged", return_value=agent_verdict
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertEqual(installed.read_bytes(), before, "still kept, never removed")
        lines = [e for e in _report_section(report, "preserved", "kept") if filename in e]
        self.assertEqual(len(lines), 1)
        self.assertIn("verdict at reorg", lines[0])
        self.assertNotIn("run /planwise upgrade interactively", lines[0])

    def test_cached_reorg_verdict_through_the_loader_gets_the_review_wording(self):
        # Drives the real _load_verdict_override: an agent cache entry at reorg,
        # with and without a `source` key, must never get the "run interactively" text.
        filename = "session-execution-protocol.md"
        self.write_shipped(
            filename, "# Session Execution Protocol\n\nReflowed section A.\nReflowed section B.\n"
        )
        installed = self.write_installed(
            filename,
            "# Session Execution Protocol\n\nSection B.\nSection A.\n",
            self.old_default_for(filename),
        )
        digest = _installed_hash(installed.read_text(encoding="utf-8-sig"))
        for with_source in (True, False):
            with self.subTest(with_source=with_source):
                entry = {
                    "classification": "SUBSET", "confidence": "reorg", "unique_blocks": [],
                    "notes": "", "installed_sha256": digest,
                }
                if with_source:
                    entry["source"] = "agent"
                with mock.patch.object(
                    rule_descope_migration, "_load_verdicts_cache",
                    return_value={filename: entry},
                ):
                    report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())
                lines = [e for e in _report_section(report, "preserved", "kept") if filename in e]
                self.assertEqual(len(lines), 1)
                self.assertIn("verdict at reorg", lines[0])
                self.assertNotIn("run /planwise upgrade interactively", lines[0])

    def test_paths_only_edit_subset_is_removed_with_info(self):
        filename = "scaffolding-hygiene.md"
        body = "# Scaffolding Hygiene\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, body, custom_paths)
        self.write_upgrade_config(descope_preserve_paths_edits=False)

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertFalse(
            installed.exists(),
            "Body-identical, paths-only-edited de-scoped rule must be removed "
            "when the preserve opt-out is disabled",
        )
        removed = _report_section(report, "removed", "deleted")
        matches = [entry for entry in removed if filename in entry]
        self.assertTrue(matches, f"{filename} must be reported under removed")
        self.assertTrue(
            any("INFO" in entry for entry in matches),
            "The removed notice must carry the [INFO] token for a paths-only edit",
        )

    def test_paths_only_edit_opt_out_is_preserved(self):
        filename = "task-content-fidelity.md"
        body = "# Task Content Fidelity\n\nMatching body.\n"
        self.write_shipped(filename, body)
        custom_paths = self.old_default_for(filename) + ", custom/**"
        installed = self.write_installed(filename, body, custom_paths)
        before = installed.read_bytes()
        self.write_upgrade_config(descope_preserve_paths_edits=True)

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        self.assertTrue(
            installed.exists(),
            "Body-identical, paths-only-edited de-scoped rule must be preserved "
            "when the preserve opt-out is enabled",
        )
        self.assertEqual(installed.read_bytes(), before)
        preserved = _report_section(report, "preserved", "kept")
        self.assertTrue(
            any(filename in entry for entry in preserved),
            f"{filename} must be reported preserved (opt-out enabled)",
        )

    # -- forced files: processed on a pair outside the version window -------

    OUTSIDE_FROM = "1.0.4"
    OUTSIDE_TO = "1.0.5"

    def test_forced_has_unique_outside_window_is_preserved_with_notice(self):
        filename = "session-context-budget.md"
        self.write_shipped(filename, "# Session Context Budget\n\nShipped body.\n")
        installed = self.write_installed(
            filename,
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n",
            self.old_default_for(filename),
        )
        before = installed.read_bytes()

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(
                self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
                force_filenames=frozenset({filename}),
            )

        self.assertEqual(installed.read_bytes(), before, "No handoff configured: file stays")
        preserved = _report_section(report, "preserved")
        self.assertTrue(
            any(filename in entry and "re-home" in entry for entry in preserved),
            f"{filename} must carry the re-home notice outside the window",
        )
        self.assertEqual(report["acted_on"], [filename])

    def test_forced_exact_subset_outside_window_is_removed_with_backup(self):
        filename = "session-plan-requirements.md"
        self.write_shipped(
            filename, "# Session Plan Requirements\n\nOriginal line.\nGrown extra line.\n")
        installed = self.write_installed(
            filename, "# Session Plan Requirements\n\nOriginal line.\n",
            self.old_default_for(filename),
        )
        original_bytes = installed.read_bytes()

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("SUBSET", "exact"),
        ):
            report = ip.migrate_installed_rules(
                self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
                force_filenames=frozenset({filename}),
            )

        self.assertFalse(installed.exists(), "A forced exact SUBSET must be removed")
        backup = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"{self.OUTSIDE_FROM}-to-{self.OUTSIDE_TO}"
            / installed.relative_to(self.project_root)
        )
        self.assertTrue(backup.exists(), "The removal must back up the pre-image first")
        self.assertEqual(backup.read_bytes(), original_bytes)
        removed = _report_section(report, "removed")
        self.assertTrue(any(filename in entry for entry in removed))
        self.assertEqual(report["acted_on"], [filename])

    def test_unforced_file_outside_window_is_untouched(self):
        forced_name = "schema-pin-requirement.md"
        other_name = "task-content-fidelity.md"
        body = "# Rule\n\nBody.\n"
        for name in (forced_name, other_name):
            self.write_shipped(name, body)
        forced = self.write_installed(forced_name, body, self.old_default_for(forced_name))
        other = self.write_installed(other_name, body, self.old_default_for(other_name))
        other_before = other.read_bytes()

        report = ip.migrate_installed_rules(
            self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
            force_filenames=frozenset({forced_name}),
        )

        self.assertFalse(forced.exists(), "The named file is acted on")
        self.assertEqual(other.read_bytes(), other_before, "The unnamed file stays byte-identical")
        self.assertEqual(report["acted_on"], [forced_name])
        self.assertFalse(
            any(other_name in entry for entry in _flatten_report(report)),
            "The unnamed file must not appear anywhere in the report",
        )

    def _force_set_outcome(self, filename, entry):
        """Install a diverged copy, build the force set from `entry`, migrate."""
        self.write_shipped(filename, "# Rule\n\nShipped body.\n")
        installed = self.write_installed(
            filename, "# Rule\n\nShipped body.\n# Extra\nUser block.\n",
            self.old_default_for(filename),
        )
        before = installed.read_bytes()
        force = rule_descope_migration.descoped_force_set(self.cfg, {filename: entry})
        report = ip.migrate_installed_rules(
            self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO, force_filenames=force)
        return installed, before, force, report

    def test_malformed_verdict_entry_does_not_force_the_file(self):
        filename = "session-context-budget.md"
        installed, before, force, report = self._force_set_outcome(filename, "garbage")

        self.assertEqual(force, frozenset())
        self.assertEqual(installed.read_bytes(), before)
        self.assertEqual(report["acted_on"], [])

    def test_stale_hash_verdict_entry_does_not_force_the_file(self):
        filename = "session-context-budget.md"
        stale = {
            "classification": "SUBSET", "confidence": "exact",
            "installed_sha256": "0" * 64,
        }
        installed, before, force, report = self._force_set_outcome(filename, stale)

        self.assertEqual(force, frozenset())
        self.assertEqual(installed.read_bytes(), before)
        self.assertEqual(report["acted_on"], [])

    def test_fresh_verdict_entry_forces_the_file(self):
        import upgrade_io

        filename = "session-context-budget.md"
        self.write_shipped(filename, "# Rule\n\nShipped body.\n")
        installed = self.write_installed(
            filename, "# Rule\n\nShipped body.\n# Extra\nUser block.\n",
            self.old_default_for(filename))
        entry = {
            "classification": "HAS_UNIQUE", "confidence": "unique",
            "unique_blocks": ["# Extra"],
            "installed_sha256": upgrade_io._installed_hash(installed),
        }

        force = rule_descope_migration.descoped_force_set(self.cfg, {filename: entry})

        self.assertEqual(force, frozenset({filename}))

    def test_forced_file_whose_backup_fails_is_skipped_not_acted_on(self):
        filename = "schema-pin-requirement.md"
        body = "# Rule\n\nBody.\n"
        self.write_shipped(filename, body)
        installed = self.write_installed(filename, body, self.old_default_for(filename))
        backup = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"{self.OUTSIDE_FROM}-to-{self.OUTSIDE_TO}"
            / installed.relative_to(self.project_root)
        )
        backup.mkdir(parents=True)  # a directory at the backup target fails the copy

        with mock.patch("sys.stderr"):
            report = ip.migrate_installed_rules(
                self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
                force_filenames=frozenset({filename}),
            )

        self.assertTrue(installed.exists(), "No removal without a pre-image")
        self.assertTrue(any(filename in e for e in report["skipped"]))
        self.assertEqual(report["acted_on"], [])

    def test_forced_has_unique_under_relocate_is_transferred_backed_up_and_removed(self):
        filename = "session-context-budget.md"
        self.write_shipped(filename, "# Session Context Budget\n\nShipped body.\n")
        installed = self.write_installed(
            filename,
            "# Session Context Budget\n\nShipped body.\n# Extra\nUser-added block.\n",
            self.old_default_for(filename),
        )
        original_bytes = installed.read_bytes()
        self.write_upgrade_config(customization_handoff="report+relocate")

        with mock.patch.object(
            rule_descope_migration, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            report = ip.migrate_installed_rules(
                self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
                force_filenames=frozenset({filename}),
            )

        self.assertFalse(installed.exists(), "Transferred customization: stale copy removed")
        backup = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"{self.OUTSIDE_FROM}-to-{self.OUTSIDE_TO}"
            / installed.relative_to(self.project_root)
        )
        self.assertEqual(backup.read_bytes(), original_bytes)
        removed = _report_section(report, "removed")
        self.assertTrue(
            any(filename in e and "re-home" in e and "upgrade-transfers" in e
                for e in removed),
            "The removal notice must name the transfer home and carry the re-home text",
        )
        self.assertEqual(report["acted_on"], [filename])

    def test_non_utf8_copy_is_skipped_not_raised_in_or_out_of_window(self):
        filename = "schema-pin-requirement.md"
        self.write_shipped(filename, "# Rule\n\nBody.\n")
        installed = self.rules_dir / filename
        installed.write_bytes(b"---\ndescription: x\n---\n\xff\xfe broken\n")
        before = installed.read_bytes()

        outside = ip.migrate_installed_rules(
            self.cfg, self.OUTSIDE_FROM, self.OUTSIDE_TO,
            force_filenames=frozenset({filename}))
        inside = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        for report in (outside, inside):
            self.assertTrue(any(filename in e for e in report["skipped"]))
            self.assertEqual(report["acted_on"], [])
        self.assertEqual(installed.read_bytes(), before)


class TestLinter(_MigrationFixtureBase):
    """lint_rule_overscope() flags overscoped rules without mutating disk."""

    def test_flags_plan_scoped_rule_only_and_mutates_nothing(self):
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        code_scope = ".claude/**"

        plan_body = "# Plan Scoped Rule\n\n" + ("filler line\n" * 20)
        code_body = "# Code Scoped Rule\n\nShort body.\n"
        self.write_installed("over-scoped-plan.md", plan_body, plan_scope)
        self.write_installed("agent-authoring.md", code_body, code_scope)

        before = _snapshot_tree(self.project_root)
        report = ip.lint_rule_overscope(self.cfg)
        after = _snapshot_tree(self.project_root)

        self.assertEqual(before, after, "lint_rule_overscope must not mutate the disk")

        flagged = _flatten_report(report)
        self.assertTrue(
            any("over-scoped-plan.md" in entry for entry in flagged),
            "The plan-scoped rule must be flagged as overscoped",
        )
        self.assertFalse(
            any("agent-authoring.md" in entry for entry in flagged),
            "The .claude/**-scoped (code-scoped) rule must NOT be flagged",
        )

    def test_report_includes_a_size_or_line_field(self):
        plan_scope = f"{self.cfg.planwise_root}/{self.cfg.plans_dir}/**"
        plan_body = "# Plan Scoped Rule\n\n" + ("filler line\n" * 30)
        self.write_installed("big-plan-rule.md", plan_body, plan_scope)

        report = ip.lint_rule_overscope(self.cfg)

        # Somewhere in the report a size/line metric must accompany the flag.
        def has_numeric(obj):
            if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                return True
            if isinstance(obj, dict):
                return any(has_numeric(v) for v in obj.values()) or any(
                    has_numeric(k) for k in obj
                )
            if isinstance(obj, (list, tuple, set, frozenset)):
                return any(has_numeric(i) for i in obj)
            attrs = getattr(obj, "__dict__", None)
            if attrs:
                return any(has_numeric(v) for v in attrs.values())
            return False

        self.assertTrue(
            has_numeric(report),
            "The overscope report must carry a size/line field (a numeric metric)",
        )


class TestUpgradeConfigFoundation(unittest.TestCase):
    """Foundation invariants for the `upgrade:` config surface.

    Plain TestCase on purpose: these are pure constant/function assertions
    that need none of the migration fixture's temp project tree.
    """

    _DEFAULTS: ClassVar[dict[str, object]] = {
        "customization_handoff": "report",
        "github_issue": False,
        # True preserves today's behavior (a paths-only-edited de-scoped
        # rule is kept); False is the explicit opt-in to removal.
        "descope_preserve_paths_edits": True,
    }

    def test_get_upgrade_config_defaults_on_absent_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_upgrade_config({}),
            self._DEFAULTS,
            "get_upgrade_config({}) must return the conservative defaults",
        )

    def test_get_upgrade_config_defaults_on_non_dict_block(self):
        import config_loader as cl

        self.assertEqual(
            cl.get_upgrade_config({"upgrade": "not-a-dict"}),
            self._DEFAULTS,
            "A non-dict upgrade: block must also fall back to defaults",
        )

    def test_get_upgrade_config_string_booleans_not_truthy_coerced(self):
        import config_loader as cl

        result = cl.get_upgrade_config(
            {"upgrade": {"github_issue": "false", "descope_preserve_paths_edits": "false"}}
        )
        self.assertFalse(
            result["github_issue"],
            'a quoted "false" must mean False, not bool-truthy True',
        )
        self.assertFalse(result["descope_preserve_paths_edits"])
        result = cl.get_upgrade_config({"upgrade": {"github_issue": "true"}})
        self.assertTrue(result["github_issue"])

    def test_get_upgrade_config_null_handoff_falls_back_to_report(self):
        import config_loader as cl

        result = cl.get_upgrade_config({"upgrade": {"customization_handoff": None}})
        self.assertEqual(
            result["customization_handoff"],
            "report",
            "an explicitly-null customization_handoff must fall back to 'report'",
        )

    def test_get_upgrade_config_strips_whitespace_from_handoff(self):
        import config_loader as cl

        result = cl.get_upgrade_config(
            {"upgrade": {"customization_handoff": "  report+relocate  "}}
        )
        self.assertEqual(
            result["customization_handoff"],
            "report+relocate",
            "a customization_handoff value must be returned stripped of "
            "leading/trailing whitespace, not verbatim",
        )

    def test_upgrade_in_migratable_top_level_keys(self):
        self.assertIn(
            "upgrade",
            ip.MIGRATABLE_TOP_LEVEL_KEYS,
            "MIGRATABLE_TOP_LEVEL_KEYS must include 'upgrade' so --migrate "
            "backfills the block into existing configs",
        )

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML to parse the template")
    def test_template_ships_report_relocate_while_absent_key_stays_report(self):
        """The shipped config.yaml.template pins customization_handoff to
        report+relocate EXPLICITLY; the loader's absent-key fallback stays the
        conservative 'report' (pinned by the defaults tests above)."""
        import yaml

        template_path = (
            Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        )
        data = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        self.assertEqual(
            data["upgrade"]["customization_handoff"],
            "report+relocate",
            "the shipped template must opt new installs into the automated "
            "transfer-then-adopt flow explicitly",
        )


class TestNormalizeRuleForDiffFallback(unittest.TestCase):
    """normalize_rule_for_diff must be byte-identical with and without the
    structural_compare module (the degraded-install fallback path)."""

    SAMPLES: ClassVar[list[str]] = [
        "---\npaths: a/**\ndescription: x\n---\n# H\nbody\n",
        "---\ndescription: x\npaths: '{plans_path}/**'\n---\n# H\nbody\n",
        "---\npaths: a/**\n---\nbody only\n",
        "# no frontmatter\nbody\n",
        "---\nunterminated frontmatter\n",
        "",
    ]

    def test_fallback_split_byte_identical(self):
        for sample in self.SAMPLES:
            with_module = ip.normalize_rule_for_diff(sample)
            saved = ip.structural_compare
            try:
                ip.structural_compare = None
                without_module = ip.normalize_rule_for_diff(sample)
            finally:
                ip.structural_compare = saved
            self.assertEqual(
                with_module,
                without_module,
                f"fallback output diverged for sample: {sample!r}",
            )


# A shipped reference carries a one-line `consult-when:` key: index metadata for
# the generated reference library, not rule content. An installed copy written
# before the key existed must still compare equal to the shipped file.
_SHIPPED_WITH_KEY = (
    "---\ndescription: x\nconsult-when: Writing a rule\npaths: a/**\n---\n# H\nbody\n"
)
_SHIPPED_KEY_LAST = "---\ndescription: x\nconsult-when: Writing a rule\n---\n# H\nbody\n"


def test_normalize_ignores_consult_when_key():
    """A copy that differs only by the `consult-when:` line normalizes equal."""
    installed = "---\ndescription: x\npaths: b/**\n---\n# H\nbody\n"
    assert ip.normalize_rule_for_diff(installed) == ip.normalize_rule_for_diff(_SHIPPED_WITH_KEY)
    assert ip.normalize_rule_for_diff("---\ndescription: x\n---\n# H\nbody\n") == (
        ip.normalize_rule_for_diff(_SHIPPED_KEY_LAST))
    assert ip.normalize_rule_for_diff("# H\nbody\n") == (
        ip.normalize_rule_for_diff("---\nconsult-when: Writing a rule\n---\n# H\nbody\n"))


def test_normalize_still_reports_real_edits():
    """A body or description edit still differs once the key is ignored."""
    shipped_norm = ip.normalize_rule_for_diff(_SHIPPED_WITH_KEY)
    body_edit = "---\ndescription: x\npaths: a/**\n---\n# H\nbody edited\n"
    description_edit = "---\ndescription: y\npaths: a/**\n---\n# H\nbody\n"
    assert ip.normalize_rule_for_diff(body_edit) != shipped_norm
    assert ip.normalize_rule_for_diff(description_edit) != shipped_norm


def test_style_rule_verdict_ignores_consult_when_key(tmp_path):
    """The style-rule verdict reads a copy without the key as identical."""
    import style_rules

    shipped = tmp_path / "shipped.md"
    installed = tmp_path / "installed.md"
    shipped.write_text(_SHIPPED_KEY_LAST, encoding="utf-8")
    installed.write_text("---\ndescription: x\n---\n# H\nbody\n", encoding="utf-8")
    assert style_rules._verdict(shipped, installed) == "identical"
    assert style_rules._body_differs(shipped, installed) is False


# -- Real released bodies of the four {all_paths} de-scoped rules -------------
#
# A consumer who installed from a release below RESCOPE_MIGRATION_VERSION holds
# that release's body of each rule_registry.DESCOPED_RULES file. Once the shipped
# reference changes, the copy fails the normalized-identical fast path, so its
# removal rests on manifests/rule-history.json: rule_divergence._classify_diverged
# returns SUBSET at exact confidence for a listed body. The cases below drive the
# real release 1.0.2 bodies (tests/fixtures/descoped_prior_bodies/, frozen) through
# both callers: migrate_installed_rules and the doctor stale-rule sweep.

_SCRIPTS_DIR = Path(ip.__file__).resolve().parent
_SHIPPED_REFERENCES = _SCRIPTS_DIR.parent / "references"
_RULE_HISTORY_JSON = _SCRIPTS_DIR.parent / "manifests" / "rule-history.json"
_PRIOR_BODY_DIR = Path(__file__).resolve().parent / "fixtures" / "descoped_prior_bodies"
_PRIOR_RELEASE = "1.0.2"

# rule_history_digest of every released or recorded prior body of the four
# rule_registry.DESCOPED_RULES {all_paths} files. Copied once from the release
# tags and commit 2977a46; never read from git at test time.
# agent-orchestration-delegated.md did not exist at release 1.0.1.
_PRIOR_BODY_DIGESTS = (
    # (filename, source, digest)
    ("agent-orchestration.md", "release 1.0.1",
     "5b58b9004091c3dc07fe6256efb34be11fb1de3ee981c8b3c5d58f1e1f0aa714"),
    ("agent-orchestration.md", "release 1.0.2",
     "6680ef4c63ecf0c28578a457b75953cfb287adbfebc4b0716ea6c714763d449c"),
    ("agent-orchestration.md", "commit 2977a46",
     "4c49cb6661107e7a1e7e761e85bb66fb1751631bff79baa134adb24fc69320b4"),
    ("agent-orchestration-delegated.md", "release 1.0.2",
     "dfb7cb548f3012063825ab52c82a6bb0e6a1f6a38a950c6c635693e9583e593b"),
    ("agent-orchestration-delegated.md", "commit 2977a46",
     "07a2f8dd9bead65a9f91f01b6ed4481fbf9e80b892e99a9d18bdb7821adb54a9"),
    ("callout-conventions.md", "release 1.0.1",
     "ccc5df0394b51e436a18b883ac9bf3810b2e9fef7d6210d20985bcacadb225a0"),
    ("callout-conventions.md", "release 1.0.2",
     "e109fb2e82852bbe8f0732262baa87beb7dc965da249995823eba81880962b82"),
    ("callout-conventions.md", "commit 2977a46",
     "093943b8cbdbb20f40b317f2445a0eb93a8b71d42a584ea353a7f23a8e5f074e"),
    # markdown-conventions.md shipped one body in releases 1.0.1 and 1.0.2.
    ("markdown-conventions.md", "release 1.0.1",
     "efd65b520f26a26f1afb9fc88c17b84b501be01abab4f398b33118112275c0a7"),
    ("markdown-conventions.md", "release 1.0.2",
     "efd65b520f26a26f1afb9fc88c17b84b501be01abab4f398b33118112275c0a7"),
    ("markdown-conventions.md", "commit 2977a46",
     "9b230c14c29d23682da6eb49cefb23ba3f710e84dad9fe78636825fcfac1e356"),
)

# One added non-blank body line that is neither `paths:` nor `consult-when:`.
_ADDED_LINE = "\nA project-local note the user added to this rule.\n"


class TestReleasedPriorBodies(_MigrationFixtureBase):
    """Each release 1.0.2 body of the four {all_paths} DESCOPED_RULES files,
    through migrate_installed_rules and sweep_stale_descoped_rules."""

    FROM_VERSION = _PRIOR_RELEASE

    def setUp(self):
        super().setUp()
        self.to_version = str(ip.RESCOPE_MIGRATION_VERSION)
        self.history = json.loads(_RULE_HISTORY_JSON.read_text(encoding="utf-8"))["rules"]

    # -- helpers ----------------------------------------------------------

    def _prior(self, filename: str) -> str:
        return (_PRIOR_BODY_DIR / f"{filename}@{_PRIOR_RELEASE}.md").read_text(encoding="utf-8")

    def _shipped(self, filename: str) -> str:
        return (_SHIPPED_REFERENCES / filename).read_text(encoding="utf-8-sig")

    def _fresh_tree(self, filename: str) -> None:
        """Copy the current shipped reference in; clear installed rules and backups."""
        for stale in self.rules_dir.iterdir():
            stale.unlink()
        shutil.rmtree(self.project_root / self.cfg.planwise_root / "upgrade-backups",
                      ignore_errors=True)
        (self.refs_dir / filename).write_text(self._shipped(filename), encoding="utf-8")

    def _install(self, filename: str, body: str, paths_value: "str | None" = None) -> Path:
        """Write the copy the installer writes: the body with its paths: resolved."""
        value = self.all_paths_value if paths_value is None else paths_value
        dst = self.rules_dir / filename
        dst.write_text(ip.update_frontmatter(body, value), encoding="utf-8")
        return dst

    def _backup_of(self, installed: Path) -> Path:
        return (self.project_root / self.cfg.planwise_root / "upgrade-backups"
                / f"{self.FROM_VERSION}-to-{self.to_version}"
                / installed.relative_to(self.project_root))

    def _migrate(self) -> dict:
        return ip.migrate_installed_rules(self.cfg, self.FROM_VERSION, self.to_version)

    def _doctor_finding(self, filename: str) -> dict:
        found = [f for f in ip.sweep_stale_descoped_rules(self.cfg) if f["filename"] == filename]
        self.assertEqual(len(found), 1, f"doctor must report {filename} once")
        return found[0]

    # -- the fixtures and the manifest ---------------------------------------

    def test_fixture_set_covers_every_all_paths_descoped_rule(self):
        all_paths_rules = {name for name, template in ip.DESCOPED_RULES
                           if template == "{all_paths}"}
        self.assertEqual(all_paths_rules, EXPECTED_DESCOPED_ALL)
        on_disk = {p.name.split("@")[0] for p in _PRIOR_BODY_DIR.glob(f"*@{_PRIOR_RELEASE}.md")}
        self.assertEqual(on_disk, EXPECTED_DESCOPED_ALL)
        self.assertEqual({row[0] for row in _PRIOR_BODY_DIGESTS}, EXPECTED_DESCOPED_ALL)
        self.assertEqual(len(_PRIOR_BODY_DIGESTS), 11)

    def test_every_prior_digest_is_listed_in_the_rule_history_manifest(self):
        for filename, source, digest in _PRIOR_BODY_DIGESTS:
            with self.subTest(filename=filename, source=source):
                self.assertIn(digest, self.history.get(filename, []))

    def test_fixture_bodies_match_their_release_digests(self):
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                prior = self._prior(filename)
                self.assertEqual(prior.count("\r"), 0, "fixtures are LF bytes")
                pinned = {d for f, s, d in _PRIOR_BODY_DIGESTS
                          if f == filename and s == f"release {_PRIOR_RELEASE}"}
                self.assertEqual({rule_history_digest(prior)}, pinned)
                # The installed copy digests the same as the released body.
                self.assertEqual(
                    rule_history_digest(ip.update_frontmatter(prior, self.all_paths_value)),
                    rule_history_digest(prior))
                # The prior body is not the current shipped body, so the fast
                # path cannot be what removes it below.
                self.assertNotEqual(ip.normalize_rule_for_diff(prior),
                                    ip.normalize_rule_for_diff(self._shipped(filename)))

    def test_fixture_config_has_no_upgrade_block_so_handoff_is_report(self):
        self.assertFalse((self.project_root / self.cfg.planwise_root / "config.yaml").exists())
        upgrade = rule_descope_migration.get_upgrade_config(
            rule_descope_migration._load_raw_config(self.cfg))
        self.assertEqual(upgrade["customization_handoff"], "report")
        # The absent-key default keeps a paths: edit; the installer's own
        # paths: value matches, so the untouched cases below are not affected.
        self.assertTrue(upgrade["descope_preserve_paths_edits"])

    # -- positive: an untouched prior copy is removed / REMOVABLE ------------

    def test_untouched_prior_copy_is_removed_by_migration_with_backup(self):
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                prior = self._prior(filename)
                installed = self._install(filename, prior)
                self.assertEqual(_extract_paths_value(installed.read_text(encoding="utf-8")),
                                 self.all_paths_value)
                original = installed.read_bytes()
                verdict = rule_descope_migration._classify_diverged(
                    ip.normalize_rule_for_diff(prior),
                    ip.normalize_rule_for_diff(self._shipped(filename)))
                self.assertEqual(
                    (verdict.classification, verdict.confidence, verdict.source, verdict.notes),
                    ("SUBSET", "exact", "shipped-history", ""))

                report = self._migrate()

                self.assertFalse(installed.exists())
                self.assertTrue(any(filename in e and "stale subset" in e
                                    for e in report["removed"]), report)
                self.assertEqual(report["acted_on"], [filename])
                self.assertEqual(self._backup_of(installed).read_bytes(), original)

    def test_untouched_prior_copy_is_removable_in_the_doctor_sweep(self):
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                installed = self._install(filename, self._prior(filename))
                before = installed.read_bytes()

                finding = self._doctor_finding(filename)

                self.assertEqual(finding["verdict"], "REMOVABLE")
                self.assertEqual(finding["confidence"], "exact")
                self.assertTrue(finding["reason"].startswith("stale subset"), finding)
                self.assertEqual(installed.read_bytes(), before, "the sweep is read-only")

    # -- mutation: one added line defeats the history match -----------------

    def test_prior_copy_with_one_added_line_is_kept_by_both_callers(self):
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                prior = self._prior(filename)
                mutated = prior + _ADDED_LINE
                self.assertNotEqual(rule_history_digest(mutated), rule_history_digest(prior))
                self.assertNotIn(rule_history_digest(mutated), self.history[filename])
                installed = self._install(filename, mutated)
                before = installed.read_bytes()

                finding = self._doctor_finding(filename)
                self.assertNotEqual(finding["verdict"], "REMOVABLE", finding)

                report = self._migrate()
                self.assertEqual(installed.read_bytes(), before)
                self.assertFalse(any(filename in e for e in report["removed"]), report)
                self.assertTrue(any(filename in e for e in report["preserved"]), report)

    # -- regression: the current shipped body still takes the fast path ------

    def test_current_shipped_copy_takes_the_fast_path_in_both_callers(self):
        no_primitive = AssertionError("fast path must not consult the primitive")
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                installed = self._install(filename, self._shipped(filename))

                with mock.patch.object(doctor_sweeps, "_classify_diverged",
                                       side_effect=no_primitive):
                    finding = self._doctor_finding(filename)
                self.assertEqual(finding["verdict"], "REMOVABLE")
                self.assertTrue(finding["reason"].startswith("untouched"), finding)

                with mock.patch.object(rule_descope_migration, "_classify_diverged",
                                       side_effect=no_primitive):
                    report = self._migrate()
                self.assertFalse(installed.exists())
                self.assertTrue(any(filename in e and "untouched" in e
                                    for e in report["removed"]), report)

    # -- report+relocate ------------------------------------------------------

    def test_report_relocate_removes_prior_copy_and_transfers_mutated_copy(self):
        self.write_upgrade_config(customization_handoff="report+relocate")
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename, copy="untouched"):
                self._fresh_tree(filename)
                installed = self._install(filename, self._prior(filename))
                report = self._migrate()
                self.assertFalse(installed.exists())
                self.assertTrue(any(filename in e and "stale subset" in e
                                    for e in report["removed"]), report)
            with self.subTest(filename=filename, copy="mutated"):
                self._fresh_tree(filename)
                installed = self._install(filename, self._prior(filename) + _ADDED_LINE)
                original = installed.read_bytes()
                report = self._migrate()
                self.assertFalse(installed.exists())
                self.assertTrue(any(filename in e and "customization transferred" in e
                                    for e in report["removed"]), report)
                self.assertEqual(self._backup_of(installed).read_bytes(), original)

    # -- protective cases ------------------------------------------------------

    def test_paths_edited_prior_copy_is_kept_under_the_preserve_opt_out(self):
        self.write_upgrade_config(descope_preserve_paths_edits=True)
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                installed = self._install(filename, self._prior(filename),
                                          self.all_paths_value + ", custom/**")
                before = installed.read_bytes()
                report = self._migrate()
                self.assertEqual(installed.read_bytes(), before)
                self.assertTrue(any(filename in e and "preserve opt-out" in e
                                    for e in report["preserved"]), report)

    def test_failed_disposition_record_leaves_the_prior_copy_in_place(self):
        for filename in sorted(EXPECTED_DESCOPED_ALL):
            with self.subTest(filename=filename):
                self._fresh_tree(filename)
                installed = self._install(filename, self._prior(filename))
                before = installed.read_bytes()
                with mock.patch.object(rule_descope_migration, "_record_disposition",
                                       return_value=False):
                    report = self._migrate()
                self.assertEqual(installed.read_bytes(), before)
                self.assertTrue(any(filename in e and "backup write failed" in e
                                    for e in report["skipped"]), report)
                self.assertEqual(report["acted_on"], [])
                self.assertFalse(self._backup_of(installed).exists())


