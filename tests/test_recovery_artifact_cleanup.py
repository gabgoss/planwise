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
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import doctor_cli
import doctor_sweeps
import init_project as ip
import recovery_surfaces

from conftest import _MigrationFixtureBase


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
        today = datetime.datetime.now().astimezone().date().isoformat()
        return self._planwise_root() / "upgrade-prune-logs" / f"upgrade-leftovers-{today}{suffix}"

    def test_prune_upgrade_leftovers_log_does_not_collide_with_prune_stale_log(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR)  # a prunable surface, so a log is actually written

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stale_exit = ip._run_prune_stale(self.cfg)
            leftovers_exit = ip._run_prune_upgrade_leftovers(self.cfg)

        self.assertEqual((stale_exit, leftovers_exit), (0, 0))

        today = datetime.datetime.now().astimezone().date().isoformat()
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
        with mock.patch.object(doctor_cli.shutil, "rmtree", rmtree_failing_partway), \
                contextlib.redirect_stdout(buf):
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


class TestBannerAnswersTheHousekeepingQuestion(_RecoveryArtifactFixtureMixin,
                                               _MigrationFixtureBase):
    """The class label says what a surface IS and when it is safe to act.
    It does not rule out the worse possibility a user has to consider when
    reading an unfamiliar directory list: that one of these is load-bearing
    and deleting it breaks the install. The banner closes by saying so, so
    the transfers-vs-backups question is answerable without opening the
    handler."""

    PAIR = "1.0.0-to-1.1.0"

    def _banner(self, surfaces) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(surfaces)
        return buf.getvalue()

    def test_populated_banner_closes_with_the_housekeeping_line(self):
        self.write_backup(self.PAIR)
        self.write_transfer(self.PAIR)

        stdout = self._banner(artifact_upgrade._scan_recovery_artifacts(self.cfg))

        self.assertIn(
            "Nothing above is loaded as a rule or needed for planwise to run", stdout
        )
        self.assertIn("housekeeping only", stdout)

    def test_the_line_comes_after_every_surface(self):
        # "Nothing ABOVE" is only true if it is last.
        self.write_backup(self.PAIR)
        self.write_transfer(self.PAIR)

        stdout = self._banner(artifact_upgrade._scan_recovery_artifacts(self.cfg))
        lines = [ln for ln in stdout.splitlines() if ln.strip()]

        self.assertIn("housekeeping only", lines[-1])

    def test_empty_banner_omits_the_line(self):
        # Nothing to reassure the user about when no surface exists.
        stdout = self._banner(artifact_upgrade._scan_recovery_artifacts(self.cfg))

        self.assertIn("None found.", stdout)
        self.assertNotIn("housekeeping", stdout)


class TestLeftoverSweepReportsBytes(_RecoveryArtifactFixtureMixin,
                                    _MigrationFixtureBase):
    """A file count says how much there is to review. Only a byte total says
    how much a prune reclaims, and the two do not track each other."""

    PAIR = "1.0.0-to-1.1.0"

    def test_every_finding_carries_a_byte_total_matching_its_files(self):
        self.write_backup(self.PAIR, content=b"x" * 300)
        self.write_transfer(self.PAIR, content="y" * 40)

        findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)

        by_surface = {f["surface"]: f for f in findings}
        self.assertEqual(by_surface["upgrade-backups"]["bytes"], 300)
        self.assertEqual(by_surface["upgrade-transfers"]["bytes"], 40)

    def test_count_and_bytes_are_independent(self):
        # Many tiny files against one large one: a count-only report would
        # rank these the wrong way round for a caller deciding what to prune.
        for i in range(5):
            self.write_consumed_cache(f"1.0.{i}-to-1.1.0")
        self.write_backup(self.PAIR, content=b"z" * 5000)

        findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
        inert = [f for f in findings if f["klass"] == "inert"]
        backups = [f for f in findings if f["klass"] == "safe-to-discard"]

        self.assertEqual(sum(f["count"] for f in inert), 5)
        self.assertEqual(sum(f["count"] for f in backups), 1)
        self.assertGreater(
            sum(f["bytes"] for f in backups), sum(f["bytes"] for f in inert),
            "the single large backup must outweigh five tiny cache markers",
        )

    def test_a_stat_failure_undercounts_rather_than_aborting(self):
        # A read-only diagnostic must still report when one file refuses a
        # stat mid-sweep — specifically the explicit `f.stat().st_size` call
        # `_bytes_of()` guards with its own try/except OSError.
        #
        # On Python 3.13+, Path.is_file() (used by the sweep's own rglob
        # filter, BEFORE _bytes_of ever runs) routes internally through
        # self.stat(follow_symlinks=follow_symlinks) -- a bare
        # mock.patch.object(Path, "stat", ...) intercepts that call too, and
        # since is_file()'s caller has no try/except, the simulated OSError
        # escaped uncaught and aborted the whole sweep before the code under
        # test was ever reached. The discriminator below narrows the mock to
        # the explicit, no-argument `.stat()` call _bytes_of() makes: pathlib
        # internals always pass `follow_symlinks` explicitly, so an empty
        # args/kwargs pair is diagnostic of the guarded call site, never of
        # is_file()'s internal one.
        self.write_backup(self.PAIR, content=b"x" * 100)
        real_stat = Path.stat

        def flaky_stat(self_path, *args, **kwargs):
            if self_path.name == "somefile.md" and not args and not kwargs:
                raise OSError("simulated stat failure")
            return real_stat(self_path, *args, **kwargs)

        with mock.patch.object(Path, "stat", flaky_stat):
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["count"], 1, "the file is still counted")
        self.assertEqual(findings[0]["bytes"], 0, "its size degrades to zero, not a crash")

    def test_format_bytes_uses_binary_units(self):
        self.assertEqual(doctor_sweeps.format_bytes(512), "512 B")
        self.assertEqual(doctor_sweeps.format_bytes(1536), "1.5 KiB")
        self.assertEqual(doctor_sweeps.format_bytes(3 * 1024 * 1024), "3.0 MiB")


class TestIndexPreImagesAreNotSafeToDiscard(_RecoveryArtifactFixtureMixin,
                                            _MigrationFixtureBase):
    """An index-migration pre-image under `{backlog,lessons,plans}/` is the
    only restore point for the files the migration rewrote. It reports as
    review-then-discard on its own line, and no prune ever deletes it."""

    PAIR = "1.0.0-to-1.1.0"
    REFRESH = ".claude/rules/planwise/x.md"
    INDEX = "plans/00-Index-Plans.md"

    def _write_log(self) -> Path:
        return self.write_backup(self.PAIR, "DISPOSITIONS.md", b"log\n")

    def _prune(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)

    def test_index_migration_backup_classified_review_then_discard(self):
        self.write_backup(self.PAIR, self.INDEX)
        self._write_log()

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual([klass for _p, _c, klass in surfaces], ["review-then-discard"])
        self.assertEqual(surfaces[0][1], 1, "DISPOSITIONS.md is never counted")
        self.assertTrue(surfaces[0][0].endswith("/{backlog,lessons,plans}/"))

    def test_refresh_backup_still_safe_to_discard(self):
        self.write_backup(self.PAIR, self.REFRESH)
        self._write_log()

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)

        self.assertEqual([(c, k) for _p, c, k in surfaces], [(1, "safe-to-discard")])

    def test_scan_and_sweep_agree_on_classes(self):
        self.write_backup(self.PAIR, self.REFRESH)
        self.write_backup(self.PAIR, "backlog/BB-001-x.md")
        self.write_backup(self.PAIR, "lessons/00-Index-LessonsLearned.md")
        self.write_backup(self.PAIR, self.INDEX)
        self._write_log()

        scan = {}
        for _p, count, klass in artifact_upgrade._scan_recovery_artifacts(self.cfg):
            scan[klass] = scan.get(klass, 0) + count
        sweep = {}
        for f in doctor_sweeps.sweep_upgrade_leftovers(self.cfg):
            sweep[f["klass"]] = sweep.get(f["klass"], 0) + f["count"]

        self.assertEqual(scan, {"safe-to-discard": 1, "review-then-discard": 3})
        self.assertEqual(scan, sweep)

    def test_prune_safe_to_discard_leaves_index_subdir_and_its_log(self):
        self.write_gate_ok_config()
        refresh = self.write_backup(self.PAIR, self.REFRESH)
        index = self.write_backup(self.PAIR, self.INDEX)
        log = self._write_log()

        self._prune()

        self.assertFalse(refresh.exists(), "the refresh pre-image is pruned")
        self.assertTrue(index.exists(), "an index pre-image is never pruned")
        self.assertTrue(log.exists(), "the log stays while an index pre-image remains")
        self.assertTrue(index.parent.is_dir())

    def test_prune_clears_dispositions_and_empty_dirs_when_nothing_recoverable_remains(self):
        self.write_gate_ok_config()
        refresh = self.write_backup(self.PAIR, self.REFRESH)
        self._write_log()
        self.write_consumed_cache(self.PAIR)

        self._prune()

        root = self._planwise_root()
        self.assertFalse(refresh.exists())
        self.assertFalse((root / "upgrade-backups" / self.PAIR).exists(),
                         "the pair directory goes with its DISPOSITIONS.md")
        self.assertFalse((root / "upgrade-backups").exists(),
                         "the empty upgrade-backups/ parent is removed")
        self.assertFalse((root / "upgrade-conflicts").exists(),
                         "the empty upgrade-conflicts/ parent is removed")

    def test_banner_labels_pre_images(self):
        self.write_backup(self.PAIR, self.INDEX)
        self.write_backup(self.PAIR, self.REFRESH)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(
                artifact_upgrade._scan_recovery_artifacts(self.cfg))
        lines = buf.getvalue().splitlines()

        index_line = [ln for ln in lines if "{backlog,lessons,plans}" in ln]
        self.assertEqual(len(index_line), 1)
        self.assertIn("1 pre-image(s)", index_line[0])
        self.assertIn("the only restore point", index_line[0])
        self.assertIn("review against the migration ledger first", index_line[0])
        refresh_line = [ln for ln in lines if "safe-to-discard" in ln]
        self.assertEqual(len(refresh_line), 1)
        self.assertNotIn("the only restore point", refresh_line[0])


class TestSafeSurfaceNamesTheIndexExclusion(_RecoveryArtifactFixtureMixin,
                                            _MigrationFixtureBase):
    """The safe-to-discard path must not read as a glob over the index subdirs."""

    PAIR = "1.0.0-to-1.1.0"

    def test_safe_surface_label_names_the_three_excluded_subdirs(self):
        self.write_backup(self.PAIR, ".claude/rules/planwise/x.md")
        self.write_backup(self.PAIR, "plans/00-Index-Plans.md")

        surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        safe = [p for p, _c, k in surfaces if k == "safe-to-discard"]

        self.assertEqual(len(safe), 1)
        self.assertFalse(safe[0].endswith("/*/"), "a bare glob also matches the index subdirs")
        self.assertIn("excluding the backlog/, lessons/ and plans/ subfolders", safe[0])

    def test_safe_surface_banner_line_carries_the_exclusion(self):
        self.write_backup(self.PAIR, ".claude/rules/planwise/x.md")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            artifact_upgrade._emit_recovery_artifacts_banner(
                artifact_upgrade._scan_recovery_artifacts(self.cfg))

        line = [ln for ln in buf.getvalue().splitlines() if "safe-to-discard" in ln]
        self.assertEqual(len(line), 1)
        self.assertIn("excluding the backlog/, lessons/ and plans/ subfolders", line[0])


class TestResidueOnlyPairIsReportedAndRemoved(_RecoveryArtifactFixtureMixin,
                                              _MigrationFixtureBase):
    """A pair holding only DISPOSITIONS.md and empty subdirs has nothing
    recoverable: the sweep reports it and the writer removes it."""

    PAIR = "1.0.0-to-1.1.0"

    def _residue(self) -> Path:
        self.write_backup(self.PAIR, "DISPOSITIONS.md", b"log\n")
        pair = self._planwise_root() / "upgrade-backups" / self.PAIR
        (pair / "plans").mkdir()
        (pair / "backlog" / "nested").mkdir(parents=True)
        return pair

    def _prune(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        return buf.getvalue()

    def test_scan_and_sweep_report_the_residue_pair_as_safe_to_discard(self):
        self._residue()

        scan = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        sweep = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)

        self.assertEqual([k for _p, _c, k in scan], ["safe-to-discard"])
        self.assertEqual([f["klass"] for f in sweep], ["safe-to-discard"])

    def test_prune_removes_the_residue_pair_and_both_empty_parents(self):
        self.write_gate_ok_config()
        self._residue()
        self.write_consumed_cache(self.PAIR)

        self._prune()

        root = self._planwise_root()
        self.assertFalse((root / "upgrade-backups").exists())
        self.assertFalse((root / "upgrade-conflicts").exists())

    def test_prune_keeps_a_pair_that_still_holds_an_index_file(self):
        self.write_gate_ok_config()
        pair = self._residue()
        index = self.write_backup(self.PAIR, "lessons/deep/00-Index-LessonsLearned.md")

        self._prune()

        self.assertTrue(index.exists())
        self.assertTrue((pair / "DISPOSITIONS.md").exists())


class TestIndexPreImageHasItsOwnMeaningAndAction(_RecoveryArtifactFixtureMixin,
                                                 _MigrationFixtureBase):
    """The index pre-image surface is not "transferred customizations", and
    its action is not the transfer-resolution step."""

    PAIR = "1.0.0-to-1.1.0"
    OLD_MEANING = "transferred customizations awaiting re-homing"

    def test_doctor_report_uses_the_pre_image_meaning_and_action(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR, "plans/00-Index-Plans.md")
        self.write_transfer(self.PAIR)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ip._run_doctor(self.cfg)
        text = buf.getvalue()

        block = text.split("index-migration pre-images)", 1)[1].split("~ ", 1)[0]
        self.assertIn(recovery_surfaces.INDEX_MEANING, block)
        self.assertIn(recovery_surfaces.INDEX_ACTION, block)
        self.assertNotIn(self.OLD_MEANING, block)
        self.assertNotIn("Step 4", block)
        self.assertIn(self.OLD_MEANING, text, "the transfer surface keeps its meaning")

    def test_preserved_section_uses_the_pre_image_meaning(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR, "plans/00-Index-Plans.md")
        self.write_backup(self.PAIR, ".claude/rules/planwise/x.md")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ip._run_prune_upgrade_leftovers(self.cfg)
        log = next((self._planwise_root() / "upgrade-prune-logs").glob(
            "*/PRUNED-LEFTOVERS.md")).read_text(encoding="utf-8")

        preserved = log.split("## Preserved", 1)[1]
        self.assertIn(recovery_surfaces.INDEX_MEANING, preserved)
        self.assertNotIn(self.OLD_MEANING, preserved)


class TestPruneNeverFollowsALink(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """A symlink or junction inside an upgrade-backups pair must never lead
    the prune out of the planwise root."""

    PAIR = "1.0.0-to-1.1.0"
    REFRESH = ".claude/rules/planwise/x.md"

    def _prune(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        return buf.getvalue()

    def _outside(self) -> Path:
        outside = self.project_root / "outside-target"
        outside.mkdir()
        (outside / "victim.md").write_text("keep\n", encoding="utf-8")
        return outside

    def _symlink_or_skip(self, link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation is not permitted here: {exc}")

    def test_detector_flagged_subdirectory_is_not_descended_into(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, self.REFRESH)
        behind = self.write_backup(self.PAIR, "linked/victim.md")

        def fake(p):
            return Path(p).name == "linked"

        with mock.patch.object(recovery_surfaces, "is_link", side_effect=fake):
            self._prune()

        self.assertFalse(real.exists(), "the real refresh file is still pruned")
        self.assertTrue(behind.exists(), "nothing behind a linked directory is deleted")

    def test_detector_flagged_pair_root_is_not_attempted(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, self.REFRESH)

        def fake(p):
            return Path(p).name == self.PAIR

        with mock.patch.object(recovery_surfaces, "is_link", side_effect=fake):
            out = self._prune()

        self.assertTrue(real.exists())
        self.assertNotIn("Removing", out)
        self.assertNotIn("REMOVE_FAILED", out)

    def test_copy_files_still_refuses_a_linked_source(self):
        src = self._planwise_root() / "upgrade-backups" / self.PAIR
        src.mkdir(parents=True)
        with mock.patch.object(recovery_surfaces, "is_link", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()) as buf, self.assertRaises(OSError):
            recovery_surfaces.copy_files([], src, self.project_root / "dst", lambda a, b: None)
        self.assertIn("REFUSED", buf.getvalue())

    def test_junction_pair_root_and_subdirectory_leave_the_target_untouched(self):
        if os.name != "nt":
            self.skipTest("junctions exist only on Windows")
        self.write_gate_ok_config()
        outside = self._outside()
        real = self.write_backup(self.PAIR, self.REFRESH)
        pair = self._planwise_root() / "upgrade-backups" / self.PAIR
        other = self._planwise_root() / "upgrade-backups" / "2.0.0-to-2.1.0"
        for link, target in ((pair / "linked", outside), (other, outside)):
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                  capture_output=True, text=True, check=False)
            if made.returncode:
                self.skipTest(f"junction creation failed: {made.stderr or made.stdout}")

        out = self._prune()

        self.assertFalse(real.exists(), "the real refresh file is still pruned")
        self.assertTrue((outside / "victim.md").exists())
        self.assertTrue(other.exists(), "the junctioned pair root is left in place")
        self.assertNotIn("REMOVE_FAILED", out)

    def test_symlinked_pair_root_leaves_the_target_untouched(self):
        self.write_gate_ok_config()
        outside = self._outside()
        self._symlink_or_skip(self._planwise_root() / "upgrade-backups" / self.PAIR, outside)

        out = self._prune()

        self.assertTrue((outside / "victim.md").exists())
        self.assertNotIn("Removing", out)

    def test_symlinked_subdirectory_leaves_the_target_untouched(self):
        self.write_gate_ok_config()
        outside = self._outside()
        real = self.write_backup(self.PAIR, self.REFRESH)
        self._symlink_or_skip(
            self._planwise_root() / "upgrade-backups" / self.PAIR / "linked", outside)

        self._prune()

        self.assertFalse(real.exists())
        self.assertTrue((outside / "victim.md").exists())


def _iterdir_denied(name: str):
    """A `Path.iterdir` replacement that raises PermissionError for `name`."""
    real = Path.iterdir

    def fake(self):
        if self.name == name:
            raise PermissionError(13, "denied", str(self))
        return real(self)

    return mock.patch.object(Path, "iterdir", fake)


class TestUnreadableEntryIsSurfacedNotFatal(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """One unreadable or locked entry must neither abort a surface nor read as empty."""

    PAIR = "1.0.0-to-1.1.0"

    def _prune(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        return buf.getvalue()

    def _pair(self) -> Path:
        return self._planwise_root() / "upgrade-backups" / self.PAIR

    def test_classify_lists_the_unreadable_directory_and_does_not_raise(self):
        self.write_backup(self.PAIR, "x.md")
        self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stderr(io.StringIO()):
            groups = recovery_surfaces.classify_backup_pair(self._pair())
            clearable = recovery_surfaces.pair_is_clearable(self._pair())
        self.assertEqual([p.name for p in groups["unreadable"]], ["locked"])
        self.assertEqual([p.name for p in groups["refresh"]], ["x.md"])
        self.assertFalse(clearable, "a pair with an unreadable entry is never cleared whole")

    def test_unreadable_only_pair_is_not_promoted_to_residue(self):
        self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stderr(io.StringIO()):
            groups = recovery_surfaces.classify_backup_pair(self._pair())
        self.assertEqual(groups["refresh"], [])

    def test_upgrade_scan_and_doctor_sweep_survive_an_unreadable_directory(self):
        self.write_backup(self.PAIR, "x.md")
        self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stderr(io.StringIO()):
            surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
        self.assertEqual(sum(c for _p, c, _k in surfaces), 2)
        self.assertEqual(sum(f["count"] for f in findings), 2)

    def test_prune_with_an_unreadable_directory_keeps_it_and_finishes(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, "x.md")
        inner = self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stderr(io.StringIO()):
            self._prune()
        self.assertFalse(real.exists())
        self.assertTrue(inner.exists(), "nothing behind an unreadable directory is deleted")

    def test_lstat_failure_is_unreadable_never_a_plain_directory(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, "x.md")
        inner = self.write_backup(self.PAIR, "locked/inner.md")
        real_lstat = os.lstat

        def fake(p, *a, **k):
            if Path(p).name == "locked":
                raise PermissionError(13, "denied", str(p))
            return real_lstat(p, *a, **k)

        with mock.patch.object(recovery_surfaces.os, "lstat", fake), \
                contextlib.redirect_stderr(io.StringIO()):
            groups = recovery_surfaces.classify_backup_pair(self._pair())
            self._prune()
        self.assertEqual([p.name for p in groups["unreadable"]], ["locked"])
        self.assertFalse(real.exists())
        self.assertTrue(inner.exists())


class TestClearEmptyParentsNeverAbortsThePrune(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """A failure while tidying pairs the prune never touched must not lose the log."""

    PAIR = "1.0.0-to-1.1.0"

    def test_unreadable_untouched_pair_does_not_stop_the_log(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, "x.md")
        self.write_conflict_sidecar("2.0.0-to-2.1.0", "locked/a.md.new")
        buf = io.StringIO()
        with _iterdir_denied("2.0.0-to-2.1.0"), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertFalse(real.exists())
        logs = list((self._planwise_root() / "upgrade-prune-logs").glob("*/PRUNED-LEFTOVERS.md"))
        self.assertEqual(len(logs), 1, "the log is written once anything was deleted")

    def test_glob_failure_is_swallowed_and_reported(self):
        top = self._planwise_root() / "upgrade-backups"
        (top / "1.0.0-to-1.1.0").mkdir(parents=True)

        def boom(self, pattern):
            raise PermissionError(13, "denied", str(self))

        buf = io.StringIO()
        with mock.patch.object(Path, "glob", boom), contextlib.redirect_stdout(buf):
            recovery_surfaces.clear_empty_parents(self._planwise_root())
        self.assertIn("NOT CLEARED", buf.getvalue())
        self.assertTrue((top / "1.0.0-to-1.1.0").is_dir())


class TestJunctionIsRefusedOnEveryPython(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """`Path.is_junction` exists only on Python 3.12+; a junction must still be refused."""

    PAIR = "1.0.0-to-1.1.0"

    def _junction_or_skip(self, link: Path, target: Path) -> None:
        if os.name != "nt":
            self.skipTest("junctions exist only on Windows")
        link.parent.mkdir(parents=True, exist_ok=True)
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, text=True, check=False)
        if made.returncode:
            self.skipTest(f"junction creation failed: {made.stderr or made.stdout}")

    def _setup(self):
        outside = self.project_root / "outside-target"
        outside.mkdir()
        (outside / "victim.md").write_text("keep\n", encoding="utf-8")
        real = self.write_backup(self.PAIR, "x.md")
        pair = self._planwise_root() / "upgrade-backups" / self.PAIR
        self._junction_or_skip(pair / "linked", outside)
        return outside, real, pair

    def test_is_link_sees_a_real_junction_without_path_is_junction(self):
        _outside, _real, pair = self._setup()
        with mock.patch.object(Path, "is_junction", None):
            self.assertTrue(recovery_surfaces.is_link(pair / "linked"))
            self.assertFalse(recovery_surfaces.is_link(pair))

    def test_prune_refuses_a_junction_without_path_is_junction(self):
        self.write_gate_ok_config()
        outside, real, _pair = self._setup()
        self.write_backup(self.PAIR, "lessons/pre.md")  # forces the partial prune
        buf = io.StringIO()
        with mock.patch.object(Path, "is_junction", None), contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertFalse(real.exists())
        self.assertTrue((outside / "victim.md").exists())

    def test_symlink_reparse_tag_marks_a_link(self):
        target = self._planwise_root() / "attr-probe"
        target.mkdir(parents=True)
        with mock.patch.object(Path, "is_junction", None), \
                _lstat_reparse("attr-probe", _TAG_SYMLINK):
            self.assertTrue(recovery_surfaces.is_link(target))


_TAG_SYMLINK = 0xA000000C
_TAG_MOUNT_POINT = 0xA0000003
_TAG_CLOUD = 0x9000001A  # IO_REPARSE_TAG_CLOUD_6, a OneDrive Files-On-Demand placeholder


def _lstat_reparse(name: str, tag: int):
    """Make `os.lstat` report a reparse point carrying `tag` for entries named `name`."""
    import stat as stat_mod
    real_lstat = os.lstat

    class _St:
        def __init__(self, st):
            self.st_mode = st.st_mode
            self.st_file_attributes = stat_mod.FILE_ATTRIBUTE_REPARSE_POINT
            self.st_reparse_tag = tag

    def fake(p, *a, **k):
        st = real_lstat(p, *a, **k)
        return _St(st) if Path(p).name == name else st

    return mock.patch.object(recovery_surfaces.os, "lstat", fake)


class TestOnlyLinkReparseTagsAreLinks(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """A cloud placeholder or dedup file is a reparse point, not a link."""

    PAIR = "1.0.0-to-1.1.0"

    def test_cloud_placeholder_tag_is_not_a_link(self):
        target = self._planwise_root() / "cloud-probe"
        target.mkdir(parents=True)
        with mock.patch.object(Path, "is_junction", None), \
                _lstat_reparse("cloud-probe", _TAG_CLOUD):
            self.assertFalse(recovery_surfaces.is_link(target))

    def test_symlink_and_mount_point_tags_are_links(self):
        target = self._planwise_root() / "tag-probe"
        target.mkdir(parents=True)
        for tag in (_TAG_SYMLINK, _TAG_MOUNT_POINT):
            with self.subTest(tag=hex(tag)), mock.patch.object(Path, "is_junction", None), \
                    _lstat_reparse("tag-probe", tag):
                self.assertTrue(recovery_surfaces.is_link(target))

    def test_cloud_tagged_pair_is_classified_swept_and_pruned_like_a_plain_pair(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, "x.md")
        pair = self._planwise_root() / "upgrade-backups" / self.PAIR
        buf = io.StringIO()
        with mock.patch.object(Path, "is_junction", None), \
                _lstat_reparse(self.PAIR, _TAG_CLOUD), contextlib.redirect_stdout(buf):
            groups = recovery_surfaces.classify_backup_pair(pair)
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertEqual([p.name for p in groups["refresh"]], ["x.md"])
        self.assertEqual(groups["links"], [])
        self.assertEqual([f["klass"] for f in findings], ["safe-to-discard"])
        self.assertNotIn("REMOVE_FAILED", buf.getvalue())
        self.assertFalse(real.exists())


class TestLinkedEntriesAreNeverSafeToDiscard(_RecoveryArtifactFixtureMixin,
                                             _MigrationFixtureBase):
    """A link is reported as review-then-discard, says it was not followed,
    and the prune never attempts it."""

    PAIR = "1.0.0-to-1.1.0"

    def _fake_pair_root_link(self):
        return mock.patch.object(recovery_surfaces, "is_link",
                                 side_effect=lambda p: Path(p).name == self.PAIR)

    def test_linked_pair_root_is_held_not_refresh(self):
        real = self.write_backup(self.PAIR, "x.md")
        pair = real.parent
        with self._fake_pair_root_link():
            groups = recovery_surfaces.classify_backup_pair(pair)
        self.assertEqual(groups["refresh"], [])
        self.assertEqual(groups["links"], [pair])

    def test_sweep_and_scan_report_a_linked_pair_root_but_not_as_safe(self):
        self.write_backup(self.PAIR, "x.md")
        with self._fake_pair_root_link():
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
            surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([f["klass"] for f in findings], ["review-then-discard"])
        self.assertIn("not followed", findings[0]["surface"])
        self.assertIn("link", findings[0]["reason"])
        self.assertEqual([k for _p, _c, k in surfaces], ["review-then-discard"])

    def test_prune_never_attempts_a_linked_pair_root(self):
        self.write_gate_ok_config()
        real = self.write_backup(self.PAIR, "x.md")
        buf = io.StringIO()
        with self._fake_pair_root_link(), contextlib.redirect_stdout(buf):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        out = buf.getvalue()
        self.assertTrue(real.exists())
        self.assertNotIn("REFUSED", out)
        self.assertNotIn("Removing", out)
        self.assertEqual(
            list((self._planwise_root() / "upgrade-prune-logs").glob("*/PRUNED-LEFTOVERS.md")),
            [], "nothing was removed, so no log is written")

    def test_linked_subdirectory_is_held_beside_the_refresh_files(self):
        self.write_backup(self.PAIR, "x.md")
        self.write_backup(self.PAIR, "linked/victim.md")
        with mock.patch.object(recovery_surfaces, "is_link",
                               side_effect=lambda p: Path(p).name == "linked"):
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
        self.assertEqual(sorted((f["klass"], f["count"]) for f in findings),
                         [("review-then-discard", 1), ("safe-to-discard", 1)])


class TestUnreadableEntriesReachTheSurfaces(_RecoveryArtifactFixtureMixin,
                                            _MigrationFixtureBase):
    """An entry that cannot be listed may hide an index pre-image, so the
    doctor sweep, the doctor report and the upgrade scan each name it."""

    PAIR = "1.0.0-to-1.1.0"

    def test_unreadable_only_pair_gets_a_review_finding(self):
        self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stderr(io.StringIO()):
            findings = doctor_sweeps.sweep_upgrade_leftovers(self.cfg)
            surfaces = artifact_upgrade._scan_recovery_artifacts(self.cfg)
        self.assertEqual([(f["klass"], f["count"]) for f in findings],
                         [("review-then-discard", 1)])
        self.assertIn("unreadable", findings[0]["reason"])
        self.assertEqual([(k, c) for _p, c, k in surfaces], [("review-then-discard", 1)])

    def test_doctor_report_prints_the_unreadable_finding(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR, "locked/inner.md")
        buf = io.StringIO()
        with _iterdir_denied("locked"), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            ip._run_doctor(self.cfg)
        self.assertIn("unreadable entries, not followed", buf.getvalue())

    def test_the_upgrade_banner_text_says_what_the_count_includes(self):
        self.assertIn("unreadable", recovery_surfaces.INDEX_BANNER_TEXT)
        self.assertIn("link", recovery_surfaces.INDEX_BANNER_TEXT)

    def test_unreadable_pair_is_never_prunable(self):
        self.write_gate_ok_config()
        inner = self.write_backup(self.PAIR, "locked/inner.md")
        with _iterdir_denied("locked"), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertTrue(inner.exists())


class TestPruneClassifiesEachPairOnce(_RecoveryArtifactFixtureMixin, _MigrationFixtureBase):
    """The sweep classifies a pair once and the prune classifies it once more."""

    PAIR = "1.0.0-to-1.1.0"

    def _counting(self, calls: list):
        real = recovery_surfaces.classify_backup_pair

        def wrapper(*a, **k):
            calls.append(a[0])
            return real(*a, **k)

        return (mock.patch.object(recovery_surfaces, "classify_backup_pair", wrapper),
                mock.patch.object(doctor_cli, "classify_backup_pair", wrapper),
                mock.patch.object(doctor_sweeps, "classify_backup_pair", wrapper))

    def test_partial_prune_classifies_the_pair_twice_in_total(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR, "x.md")
        self.write_backup(self.PAIR, "lessons/pre.md")
        calls: list = []
        a, b, c = self._counting(calls)
        with a, b, c, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertEqual(len(calls), 2, "one sweep pass and one prune pass")

    def test_unreadable_line_prints_once_per_prune(self):
        self.write_gate_ok_config()
        self.write_backup(self.PAIR, "x.md")
        self.write_backup(self.PAIR, "locked/inner.md")
        err = io.StringIO()
        with _iterdir_denied("locked"), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            self.assertEqual(ip._run_prune_upgrade_leftovers(self.cfg), 0)
        self.assertEqual(err.getvalue().count("UNREADABLE"), 1)

    def test_pair_is_clearable_accepts_a_classification(self):
        self.write_backup(self.PAIR, "x.md")
        pair = self._planwise_root() / "upgrade-backups" / self.PAIR
        groups = recovery_surfaces.classify_backup_pair(pair)
        self.assertTrue(recovery_surfaces.pair_is_clearable(groups))
        groups["index"].append(pair / "lessons" / "pre.md")
        self.assertFalse(recovery_surfaces.pair_is_clearable(groups))
        self.assertTrue(recovery_surfaces.pair_is_clearable(pair))


if __name__ == "__main__":
    unittest.main()
