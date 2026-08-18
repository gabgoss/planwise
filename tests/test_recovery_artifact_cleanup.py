#!/usr/bin/env python3
"""Unit tests (TDD) for recovery-artifact cleanup: the `Recovery artifacts:`
banner aggregation, the four-class taxonomy, formerly-managed
(manifest-shrinkage) detection, and the `--prune-upgrade-leftovers` writer's
class-scoped deletion + log-path non-collision with the pre-existing
`--prune-stale` writer.

Surface-don't-patch: exercises `artifact_upgrade._scan_recovery_artifacts()`
/ `_emit_recovery_artifacts_banner()` / `_split_formerly_managed()` /
`RECOVERY_ARTIFACT_CLASSES` and `doctor_cli._run_prune_upgrade_leftovers()`
as landed -- no module under `plugins/planwise/` is edited here.

Reuses `_MigrationFixtureBase` from conftest.py for its tmp-tree InitConfig
rather than the heavier `_UpgradeArtifactsFixtureBase` (its
INSTALLED_RULES-patched rule/agent tree): these landing surfaces operate on
`{planwise_root}/upgrade-*/` directory trees directly and never touch
installed rules or agents.

Run with:  python -m unittest tests/test_recovery_artifact_cleanup.py
"""

import contextlib
import datetime
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import artifact_upgrade  # noqa: E402 -- patch-target home for the scan/banner/split functions under test
import doctor_cli  # noqa: E402 -- patch-target home for the prune writer's shutil

from conftest import _MigrationFixtureBase  # noqa: E402


class _RecoveryArtifactFixtureMixin:
    """Fixture helpers for populating `{planwise_root}/upgrade-*/` trees.

    Mixed into `_MigrationFixtureBase` subclasses below, which already supply
    self.cfg / self.project_root / self.plugin_root from a tmp tree.
    """

    def _planwise_root(self) -> Path:
        return self.project_root / self.cfg.planwise_root

    def write_backup(self, pair: str, rel: str = "somefile.md",
                      content: bytes = b"pre-image\n") -> Path:
        dst = self._planwise_root() / "upgrade-backups" / pair / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
        return dst

    def write_transfer(self, pair: str, rel: str = "somefile.md",
                        content: str = "transferred\n") -> Path:
        dst = self._planwise_root() / "upgrade-transfers" / pair / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        return dst

    def write_conflict_sidecar(self, pair: str, rel: str = "somefile.md.new",
                                content: str = "shipped\n") -> Path:
        dst = self._planwise_root() / "upgrade-conflicts" / pair / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        return dst

    def write_issue_draft(self, pair: str, filename: str = "draft.md",
                           content: str = "draft body\n") -> Path:
        dst = self._planwise_root() / "upgrade-conflicts" / pair / "issue-drafts" / filename
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        return dst

    def write_consumed_cache(self, pair: str) -> Path:
        dst = self._planwise_root() / "upgrade-conflicts" / pair / "verdicts.json.consumed"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("{}", encoding="utf-8")
        return dst

    def write_gate_ok_config(self) -> Path:
        """config.yaml pinning plugin_version to the fixture cfg's (default)
        0.0.0, with no plugin_root: key, so _doctor_version_gate() resolves
        "ok" and the opt-in prune writers proceed instead of refusing."""
        config_path = self._planwise_root() / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )
        return config_path


class TestRecoveryArtifactsAggregation(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """`_scan_recovery_artifacts()` + `_emit_recovery_artifacts_banner()`:
    report-what-exists over whichever surfaces are actually populated."""

    PAIR = "1.0.0-to-1.1.0"

    def test_two_of_four_surfaces_reports_exactly_those_two(self):
        # The forensic-primary case (Notes): backups fire unconditionally,
        # transfers only on genuine customization -- a session with no
        # customization-bearing divergence populates only these two.
        self.write_backup(self.PAIR)
        self.write_transfer(self.PAIR)

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual(len(surfaces), 2)
        classes = {klass for _path, _count, klass in surfaces}
        self.assertEqual(classes, {"safe-to-discard", "review-then-discard"})

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(surfaces)
        stdout = buf.getvalue()
        self.assertIn("Recovery artifacts:", stdout)
        self.assertIn("safe-to-discard: " + artifact_upgrade.RECOVERY_ARTIFACT_CLASSES["safe-to-discard"], stdout)
        self.assertIn("review-then-discard: " + artifact_upgrade.RECOVERY_ARTIFACT_CLASSES["review-then-discard"], stdout)
        self.assertNotIn("action-required:", stdout)
        self.assertNotIn("inert:", stdout)

    def test_all_four_named_surfaces_reports_all_four_with_correct_classes(self):
        # The four surfaces named 1:1 against RECOVERY_ARTIFACT_CLASSES'
        # four keys (issue-drafts is a distinct action-required ROW, pinned
        # separately in TestRecoveryArtifactTaxonomy -- kept out of "the
        # four" here to match this file's per-class enumeration).
        self.write_backup(self.PAIR)
        self.write_transfer(self.PAIR)
        self.write_conflict_sidecar(self.PAIR)
        self.write_consumed_cache(self.PAIR)

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual(len(surfaces), 4)
        by_class = {klass: count for _path, count, klass in surfaces}
        self.assertEqual(
            by_class,
            {"safe-to-discard": 1, "review-then-discard": 1, "action-required": 1, "inert": 1},
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(surfaces)
        stdout = buf.getvalue()
        for klass in artifact_upgrade.RECOVERY_ARTIFACT_CLASSES:
            self.assertIn(klass + ": " + artifact_upgrade.RECOVERY_ARTIFACT_CLASSES[klass], stdout)

    def test_zero_surfaces_reports_zero_report_sentence(self):
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual(surfaces, [])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(surfaces)
        stdout = buf.getvalue()
        self.assertIn("Recovery artifacts:", stdout)
        self.assertIn("None found.", stdout)
        for klass in artifact_upgrade.RECOVERY_ARTIFACT_CLASSES:
            self.assertNotIn(klass + ":", stdout)

    def test_aggregates_counts_across_multiple_prior_pairs(self):
        # Leftovers accumulate per upgrade COUNT, not version distance --
        # two different pairs' backups must roll into ONE reported line.
        self.write_backup("1.0.0-to-1.1.0", rel="a.md")
        self.write_backup("1.1.0-to-1.2.0", rel="b.md")

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual(len(surfaces), 1)
        _path, count, klass = surfaces[0]
        self.assertEqual(klass, "safe-to-discard")
        self.assertEqual(count, 2, "counts from both pairs must sum into one surface line")

    def test_dispositions_md_excluded_from_backup_count(self):
        self.write_backup(self.PAIR, rel="a.md")
        (self._planwise_root() / "upgrade-backups" / self.PAIR / "DISPOSITIONS.md").write_text(
            "# disposition log\n", encoding="utf-8"
        )

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual(len(surfaces), 1)
        _path, count, _klass = surfaces[0]
        self.assertEqual(count, 1, "DISPOSITIONS.md is bookkeeping, not a recovery artifact")


class TestRecoveryArtifactTaxonomy(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """Per-surface-type classification, each pinned in isolation."""

    PAIR = "1.0.0-to-1.1.0"

    def test_recovery_artifact_classes_dict_exact_keys(self):
        self.assertEqual(
            set(artifact_upgrade.RECOVERY_ARTIFACT_CLASSES.keys()),
            {"action-required", "review-then-discard", "safe-to-discard", "inert"},
        )

    def test_backup_classified_safe_to_discard(self):
        self.write_backup(self.PAIR)
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([klass for _p, _c, klass in surfaces], ["safe-to-discard"])

    def test_transfer_classified_review_then_discard(self):
        self.write_transfer(self.PAIR)
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([klass for _p, _c, klass in surfaces], ["review-then-discard"])

    def test_conflict_sidecar_classified_action_required(self):
        self.write_conflict_sidecar(self.PAIR)
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([klass for _p, _c, klass in surfaces], ["action-required"])

    def test_issue_drafts_classified_action_required(self):
        self.write_issue_draft(self.PAIR)
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([klass for _p, _c, klass in surfaces], ["action-required"])

    def test_consumed_cache_classified_inert(self):
        self.write_consumed_cache(self.PAIR)
        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([klass for _p, _c, klass in surfaces], ["inert"])

    def test_sidecar_and_issue_drafts_are_two_distinct_action_required_rows(self):
        # upgrade-conflicts/{pair}/ carries two content kinds that share the
        # action-required class but are reported as separate rows/paths, per
        # the binding artifact-shape ground truth (issue-drafts/ nests under
        # the pair dir; it is not a bare top-level surface).
        self.write_conflict_sidecar(self.PAIR)
        self.write_issue_draft(self.PAIR)

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual(len(surfaces), 2, "sidecars and issue-drafts must be separate rows")
        classes = {klass for _p, _c, klass in surfaces}
        self.assertEqual(classes, {"action-required"})
        paths = {path for path, _c, _k in surfaces}
        self.assertTrue(any(p.endswith("issue-drafts/") for p in paths))
        self.assertTrue(any(not p.endswith("issue-drafts/") for p in paths))


class TestFormerlyManagedShrinkage(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """`_split_formerly_managed()` (NR-9): only positive backup-mirror
    evidence distinguishes "formerly managed" from generic untracked -- no
    manifest snapshot exists anywhere in the codebase to diff against."""

    PAIR = "1.0.0-to-1.1.0"

    def test_backup_mirror_evidence_marks_formerly_managed(self):
        vanished = self.project_root / ".claude" / "rules" / "planwise" / "vanished-rule.md"
        mirror = self._planwise_root() / "upgrade-backups" / self.PAIR / ".claude" / "rules" / "planwise" / "vanished-rule.md"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text("prior body\n", encoding="utf-8")

        still_untracked, formerly_managed = artifact_upgrade._split_formerly_managed(
            self.cfg, [str(vanished)]
        )

        self.assertEqual(still_untracked, [])
        self.assertEqual(formerly_managed, [str(vanished)])

    def test_no_mirror_stays_generic_untracked(self):
        user_file = self.project_root / ".claude" / "rules" / "planwise" / "my-own-notes.md"
        # No backup mirror written anywhere -- absent positive evidence, this
        # must stay in the generic bucket rather than being assumed managed.

        still_untracked, formerly_managed = artifact_upgrade._split_formerly_managed(
            self.cfg, [str(user_file)]
        )

        self.assertEqual(still_untracked, [str(user_file)])
        self.assertEqual(formerly_managed, [])

    def test_mixed_list_partitions_both_directions_together(self):
        vanished = self.project_root / ".claude" / "rules" / "planwise" / "vanished-rule.md"
        mirror = self._planwise_root() / "upgrade-backups" / self.PAIR / ".claude" / "rules" / "planwise" / "vanished-rule.md"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text("prior body\n", encoding="utf-8")
        user_file = self.project_root / ".claude" / "rules" / "planwise" / "my-own-notes.md"

        still_untracked, formerly_managed = artifact_upgrade._split_formerly_managed(
            self.cfg, [str(vanished), str(user_file)]
        )

        self.assertEqual(still_untracked, [str(user_file)])
        self.assertEqual(formerly_managed, [str(vanished)])


class TestPruneUpgradeLeftoversScope(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """`--prune-upgrade-leftovers` (`doctor_cli._run_prune_upgrade_leftovers`):
    taxonomy-scoped deletion (inert + safe-to-discard only) and non-collision
    with the pre-existing `--prune-stale` writer's log directory."""

    PAIR = "1.0.0-to-1.1.0"

    def test_action_required_and_review_then_discard_survive_prune_while_inert_and_safe_to_discard_are_removed(self):
        self.write_gate_ok_config()
        backup = self.write_backup(self.PAIR)
        transfer = self.write_transfer(self.PAIR)
        sidecar = self.write_conflict_sidecar(self.PAIR)
        draft = self.write_issue_draft(self.PAIR)
        consumed = self.write_consumed_cache(self.PAIR)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_prune_upgrade_leftovers(self.cfg)

        self.assertEqual(exit_code, 0)
        self.assertFalse(
            backup.parent.exists(), "safe-to-discard (backups) must be pruned"
        )
        self.assertFalse(
            consumed.exists(), "inert (consumed verdict cache) must be pruned"
        )
        self.assertTrue(
            transfer.exists(), "review-then-discard (transfers) must NEVER be pruned"
        )
        self.assertTrue(
            sidecar.exists(), "action-required (conflict sidecar) must NEVER be pruned"
        )
        self.assertTrue(
            draft.exists(), "action-required (issue-drafts) must NEVER be pruned"
        )

        log = self._leftovers_log_dir() / "PRUNED-LEFTOVERS.md"
        self.assertTrue(log.exists())
        log_text = log.read_text(encoding="utf-8")
        self.assertIn("## Removed (2)", log_text)
        self.assertIn("## Preserved (3)", log_text)

    def _leftovers_log_dir(self, suffix=""):
        today = datetime.date.today().isoformat()
        return self._planwise_root() / "upgrade-prune-logs" / f"upgrade-leftovers-{today}{suffix}"

    def test_prune_upgrade_leftovers_log_does_not_collide_with_prune_stale_log(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR)  # a prunable surface, so a log is actually written

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stale_exit = ip._run_prune_stale(self.cfg)
            leftovers_exit = ip._run_prune_upgrade_leftovers(self.cfg)

        self.assertEqual((stale_exit, leftovers_exit), (0, 0))

        today = datetime.date.today().isoformat()
        stale_log = self._planwise_root() / "upgrade-backups" / f"prune-{today}" / "PRUNED.md"
        leftovers_log = self._leftovers_log_dir() / "PRUNED-LEFTOVERS.md"

        self.assertTrue(stale_log.exists(), "the pre-existing --prune-stale log must be written")
        self.assertTrue(leftovers_log.exists(), "the new --prune-upgrade-leftovers log must be written")
        self.assertNotEqual(
            stale_log.parent, leftovers_log.parent,
            "the two writers must never share a log directory",
        )

    def test_leftover_prune_log_root_is_outside_every_swept_root(self):
        """Regression: the log root must NOT live under `upgrade-backups/`.

        It did originally, and because this writer prunes surfaces that live
        INSIDE `upgrade-backups/`, a pruned pair was copied to
        `upgrade-backups/<log>/upgrade-backups/{pair}` and the original
        deleted -- reclaiming nothing, and hiding the copy from the sweep's
        `*-to-*` glob permanently. Assert both halves: the pair really leaves
        the swept namespace, and the preserved copy lands outside it.
        """
        self.write_gate_ok_config()
        backup = self.write_backup(self.PAIR)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)

        backups_root = self._planwise_root() / "upgrade-backups"
        self.assertFalse(backup.parent.exists(), "the pruned pair must be gone from upgrade-backups/")
        self.assertEqual(
            list(backups_root.glob("*-to-*")), [],
            "no *-to-* surface may survive anywhere under upgrade-backups/ after the prune",
        )
        log_dir = self._leftovers_log_dir()
        self.assertTrue((log_dir / "PRUNED-LEFTOVERS.md").exists())
        self.assertNotIn(
            backups_root, log_dir.parents,
            "the prune log root must be disjoint from the swept upgrade-backups/ root",
        )
        # The pre-removal copy is preserved, just outside the swept namespace.
        self.assertTrue(any(log_dir.rglob("*.md")), "the pre-removal copy must survive under the log root")

    def test_noop_prune_creates_no_log_directory_at_all(self):
        """Regression: a run with nothing prunable must leave no directory behind.

        The log folder was created up front, so every no-op run dropped a
        numbered empty dir (`-2`, `-3`, ...) into the tree the feature exists
        to keep tidy -- and `parents=True` created the root on projects that
        never had one.
        """
        self.write_gate_ok_config()
        self.write_transfer(self.PAIR)      # review-then-discard -- never prunable
        self.write_conflict_sidecar(self.PAIR)  # action-required -- never prunable

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)

        self.assertFalse(
            (self._planwise_root() / "upgrade-prune-logs").exists(),
            "a no-op prune must not create its log root",
        )
        self.assertIn("Nothing to prune", buf.getvalue())

    def test_same_day_rerun_of_leftover_prune_gets_numeric_suffix_not_clobber(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            first_exit = ip._run_prune_upgrade_leftovers(self.cfg)
            # A second prunable surface must exist for the rerun to write a log
            # at all -- the first run legitimately consumed everything.
            self.write_consumed_cache(self.PAIR)
            second_exit = ip._run_prune_upgrade_leftovers(self.cfg)

        self.assertEqual((first_exit, second_exit), (0, 0))

        first_log = self._leftovers_log_dir() / "PRUNED-LEFTOVERS.md"
        second_log = self._leftovers_log_dir("-2") / "PRUNED-LEFTOVERS.md"

        self.assertTrue(first_log.exists(), "the first run's log must survive the second run")
        self.assertTrue(second_log.exists(), "a same-day rerun must get a numeric suffix, not clobber")

    def test_partial_removal_failure_preserves_the_pre_removal_copy(self):
        """Regression (data loss): a part-way `rmtree` must NOT delete the backup.

        The copy and the removal originally shared one `try`, and the handler
        deleted the backup on ANY OSError. So when `rmtree` failed mid-tree --
        the ordinary Windows locked/read-only-file case -- the already-deleted
        source files were gone AND their only copies were wiped. The copy is
        the sole record of whatever removal already destroyed; it must survive.
        """
        self.write_gate_ok_config()
        backup = self.write_backup(self.PAIR)
        pair_dir = backup.parent

        real_rmtree = doctor_cli.shutil.rmtree

        def rmtree_failing_partway(path, *a, **kw):
            path = Path(path)
            if path == pair_dir:
                # Delete part of the tree, then fail -- exactly what a locked
                # file partway through a real rmtree does.
                for victim in sorted(p for p in path.rglob("*") if p.is_file()):
                    victim.unlink()
                    break
                raise OSError("simulated locked file partway through removal")
            return real_rmtree(path, *a, **kw)

        buf = io.StringIO()
        with mock.patch.object(doctor_cli.shutil, "rmtree", rmtree_failing_partway):
            with contextlib.redirect_stdout(buf):
                self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)

        log_dir = self._leftovers_log_dir()
        preserved = list(log_dir.rglob("*.md"))
        self.assertTrue(
            [p for p in preserved if p.name != "PRUNED-LEFTOVERS.md"],
            "the pre-removal copy MUST survive a part-way removal failure -- "
            "it is the only record of the files removal already deleted",
        )
        log_text = (log_dir / "PRUNED-LEFTOVERS.md").read_text(encoding="utf-8")
        self.assertIn("## Removed (0)", log_text)
        self.assertIn("REMOVE_FAILED", log_text)
        self.assertIn("pre-removal copy is preserved", log_text)

    def test_classes_argument_narrows_but_can_never_widen_the_prune_scope(self):
        """The handler confirms one class at a time, so the writer must honor a
        subset -- and must still refuse the two never-deletable classes even
        when they are passed explicitly."""
        self.write_gate_ok_config()
        backup = self.write_backup(self.PAIR)
        consumed = self.write_consumed_cache(self.PAIR)
        transfer = self.write_transfer(self.PAIR)
        sidecar = self.write_conflict_sidecar(self.PAIR)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # Narrow to inert only, while ALSO asking for the two forbidden
            # classes -- the intersection must drop them silently.
            exit_code = ip._run_prune_upgrade_leftovers(
                self.cfg, {"inert", "action-required", "review-then-discard"})

        self.assertEqual(exit_code, 0)
        self.assertFalse(consumed.exists(), "the confirmed inert class must be pruned")
        self.assertTrue(backup.parent.exists(), "an unconfirmed prunable class must be kept")
        self.assertTrue(transfer.exists(), "review-then-discard is never deletable, even if passed")
        self.assertTrue(sidecar.exists(), "action-required is never deletable, even if passed")


if __name__ == "__main__":
    unittest.main()
