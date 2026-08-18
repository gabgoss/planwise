#!/usr/bin/env python3
"""Unit tests (TDD) for customization handoff gating and destructive-write order.

Split from the rule de-scope + migration monolith along its Spec fixture
boundary. Covers the `upgrade.customization_handoff` gate that decides whether
a customization-bearing installed rule is transferred-then-removed or
preserved byte-for-byte, the destructive-write ordering and backup invariants
that guard against ever losing a preserved file, the not-analyzed marker, the
verdict-cache consumption path, and the motivating six-rule regression that
first exercised this whole contract end to end. Shares its fixture base and
cross-seam helpers with the sibling modules this monolith was split into;
those live in conftest.py.

Run with:  python -m unittest tests/test_customization_handoff.py
"""

import shutil
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import rule_descope_migration  # noqa: E402 -- patch-target home for migrate_installed_rules()
import artifact_upgrade  # noqa: E402 -- patch-target home for upgrade_artifacts()/_run_upgrade()

from conftest import (  # noqa: E402
    _MigrationFixtureBase,
    _UpgradeArtifactsFixtureBase,
    _report_section,
    _verdict,
)


class TestCustomizationHandoffGating(_UpgradeArtifactsFixtureBase):
    """upgrade.customization_handoff gates the automated transfer-then-adopt
    path: report (also the absent-key default) and report+issue are
    conservative (preserve + sidecar, no transfer, no adoption);
    report+relocate enables the automated flow (pinned by the transfer tests
    in TestUpgradeArtifactsDisposition)."""

    def _run_has_unique_rule(self):
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()
        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            result = self.run_upgrade()
        return installed, before, result

    def test_absent_config_defaults_to_conservative_report(self):
        installed, before, result = self._run_has_unique_rule()
        refreshed, unchanged, conflicts, untracked, refreshed_subsets, transferred = result

        self.assertEqual(installed.read_bytes(), before,
                         "report mode must preserve the installed file byte-for-byte")
        self.assertEqual(transferred, [], "report mode must NOT transfer")
        self.assertNotIn(str(installed), refreshed, "report mode must NOT adopt shipped")
        self.assertTrue(conflicts, "report mode must surface the file as a conflict")
        dst_path, sidecar_path = conflicts[0]
        self.assertEqual(dst_path, str(installed))
        self.assertTrue(Path(sidecar_path).exists(), "a .new sidecar must be written")
        self.assertFalse(
            self.transfer_dir().exists(),
            "report mode must not create the upgrade-transfers dir",
        )

    def test_explicit_report_is_conservative(self):
        self.write_upgrade_config(customization_handoff="report")
        installed, before, result = self._run_has_unique_rule()
        _, _, conflicts, _, _, transferred = result
        self.assertEqual(installed.read_bytes(), before)
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

    def test_report_issue_is_conservative_for_disposition(self):
        self.write_upgrade_config(customization_handoff="report+issue")
        installed, before, result = self._run_has_unique_rule()
        _, _, conflicts, _, _, transferred = result
        self.assertEqual(installed.read_bytes(), before,
                         "report+issue must dispose like report (issue routing is "
                         "handler-side, never a writer-side adoption license)")
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

class TestDestructiveWriteOrderingAndBackupGates(_UpgradeArtifactsFixtureBase):
    """Failed backup => no destructive write; failed adoption write (after a
    verified transfer) => conflict + NO false DISPOSITIONS row; transfer
    collisions uniquify instead of clobbering."""

    def test_backup_failure_blocks_rule_subset_adoption(self):
        shipped_body = "# Rule\n\nShipped superset body.\nExtra shipped-only line.\n"
        installed_body = "# Rule\n\nShipped superset body.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ), mock.patch.object(artifact_upgrade, "_write_backup_preimage", return_value=False):
            refreshed, _, conflicts, _, refreshed_subsets, _ = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "failed backup must block the adoption write")
        self.assertNotIn(str(installed), refreshed)
        self.assertEqual(refreshed_subsets, [])
        self.assertTrue(conflicts, "the blocked adoption must surface as a conflict")

    def test_backup_failure_blocks_transfer_then_adopt(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(artifact_upgrade, "_write_backup_preimage", return_value=False):
            refreshed, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "even with a verified transfer, a failed backup blocks adoption")
        self.assertEqual(transferred, [])
        self.assertTrue(conflicts)

    def test_adoption_write_failure_is_conflict_with_no_false_log_row(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        installed = self.write_installed_rule(installed_body, ".claude/agents/**")
        before = installed.read_bytes()

        original_write_text = Path.write_text

        def _raising_write_text(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: adoption write failed")
            return original_write_text(self_path, *args, **kwargs)

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ), mock.patch.object(Path, "write_text", _raising_write_text):
            refreshed, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(installed.read_bytes(), before,
                         "the failed adoption must leave the installed file untouched")
        self.assertEqual(transferred, [],
                         "a failed adoption is NOT reported as transferred")
        self.assertNotIn(str(installed), refreshed)
        self.assertTrue(conflicts, "the failed adoption must surface as a conflict")

        # The transfer file WAS written (before the failure) — the conflict
        # is recoverable from it; and no false "adopted" DISPOSITIONS row.
        transfer_files = (
            list(self.transfer_dir().iterdir()) if self.transfer_dir().exists() else []
        )
        self.assertTrue(transfer_files, "the pre-adoption transfer file must survive")
        dispositions = (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / "1.0.0-to-1.1.0" / "DISPOSITIONS.md"
        )
        if dispositions.exists():
            self.assertNotIn(
                "adopted shipped (customization transferred)",
                dispositions.read_text(encoding="utf-8"),
                "a failed adoption write must not append a false adoption row",
            )

    def test_transfer_collision_uniquifies_never_clobbers(self):
        self.enable_relocate()
        shipped_body = "# Rule\n\nShipped body.\n"
        installed_body = "# Rule\n\nShipped body.\n# Extra\nUser-added block.\n"
        self.write_shipped_rule(shipped_body)
        self.write_installed_rule(installed_body, ".claude/agents/**")

        tdir = self.transfer_dir()
        tdir.mkdir(parents=True, exist_ok=True)
        stem = Path(self.RULE_FILENAME).stem
        suffix = Path(self.RULE_FILENAME).suffix
        first = tdir / self.RULE_FILENAME
        second = tdir / f"{stem}-1.0.0-to-1.1.0{suffix}"
        first.write_text("pre-existing transfer ONE", encoding="utf-8")
        second.write_text("pre-existing transfer TWO", encoding="utf-8")

        with mock.patch.object(
            artifact_upgrade, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            _, _, conflicts, _, _, transferred = self.run_upgrade()

        self.assertEqual(len(transferred), 1)
        new_transfer = Path(transferred[0][1])
        self.assertEqual(
            new_transfer.name, f"{stem}-1.0.0-to-1.1.0-2{suffix}",
            "the collision loop must uniquify with a numeric suffix",
        )
        self.assertEqual(first.read_text(encoding="utf-8"), "pre-existing transfer ONE",
                         "a pre-existing transfer file must never be clobbered")
        self.assertEqual(second.read_text(encoding="utf-8"), "pre-existing transfer TWO")
        self.assertIn("User-added block.", new_transfer.read_text(encoding="utf-8"))
        self.assertEqual(conflicts, [])


class TestNotAnalyzedMarker(unittest.TestCase):
    """The degraded stand-in is detected by its explicit source marker only —
    a genuine agent verdict of the same SHAPE must never be captured."""

    def test_degraded_standin_carries_explicit_marker(self):
        with mock.patch.dict(sys.modules, {"structural_compare": None}):
            verdict = ip._classify_diverged("installed body", "shipped body")
        self.assertEqual(verdict.source, ip._DEGRADED_VERDICT_SOURCE)
        self.assertTrue(ip._verdict_not_analyzed(verdict))

    def test_genuine_agent_has_unique_with_notes_is_not_captured(self):
        genuine = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique",
            unique_blocks=[], notes="one tolerated fragment: 'local exemption'",
            source="agent",
        )
        self.assertFalse(
            ip._verdict_not_analyzed(genuine),
            "a genuine agent verdict (HAS_UNIQUE, no unique_blocks, non-empty "
            "notes) must NOT be shape-matched as not-analyzed",
        )

    def test_inline_primitive_verdict_is_not_captured(self):
        inline = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique",
            unique_blocks=[], notes="tolerated fragments", source="inline",
        )
        self.assertFalse(ip._verdict_not_analyzed(inline))


class TestVerdictCacheConsumption(_UpgradeArtifactsFixtureBase):
    """A successful --upgrade run retires verdicts.json (renamed to
    verdicts.json.consumed) so a stale cached verdict can never fire on a
    later pair or re-run."""

    @unittest.skipUnless(ip.HAS_YAML, "requires PyYAML (--upgrade hard-requires it)")
    def test_cache_consumed_after_successful_run(self):
        import contextlib
        import io

        # Minimal upgradeable fixture: pinned 1.0.0, target 1.1.0, identical
        # rule + agent so the artifact refresh has nothing to dispose.
        self.cfg.plugin_version = "1.1.0"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            'plugin_version: "1.0.0"\n', encoding="utf-8"
        )
        real_template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(real_template), str(self.plugin_root / "config.yaml.template"))

        body = "# Rule\n\nIdentical body.\n"
        self.write_shipped_rule(body, ".claude/agents/**")
        self.write_installed_rule(body, ".claude/agents/**")

        verdicts_path = self.conflict_dir() / "verdicts.json"
        verdicts_path.parent.mkdir(parents=True, exist_ok=True)
        verdicts_path.write_text("{}", encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_upgrade(self.cfg)

        self.assertEqual(exit_code, 0)
        self.assertFalse(
            verdicts_path.exists(),
            "a successful --upgrade must retire the consumed verdicts.json",
        )
        consumed = verdicts_path.with_name("verdicts.json.consumed")
        self.assertTrue(
            consumed.exists(),
            "the cache is renamed to .consumed (inspectable, never re-fired)",
        )


class TestMotivatingSixRuleRegression(_MigrationFixtureBase):
    """Reproduce the live incident that motivated the subset-vs-unique work.

    Six de-scoped rules were installed as older/smaller copies of references
    that had since grown. The exact-match migration preserved ALL SIX as
    "body-customized," leaving the always-on over-scope the de-scope was meant
    to remove. Under the structural verdict, the five copies that carry no
    installed-only content must auto-remove (over-scope cleared), and the one
    that DOES carry installed-only content must be surfaced-and-preserved for
    re-home -- never silently removed, never silently mislabeled "customized"
    and left in place unflagged. The per-branch tests above pin each disposition
    in isolation; this pins the aggregate multi-rule outcome the incident was.
    """

    # The exact filenames from the incident (all present in DESCOPED_RULES).
    _STALE_SUBSETS = (
        "agent-orchestration.md",
        "callout-conventions.md",
        "session-context-budget.md",
        "session-execution-protocol.md",
        "session-plan-requirements.md",
    )
    _CUSTOMIZED = "session-planning-protocol.md"
    _MARKER = "INSTALLEDONLYSTALEPROSE"

    def _to_version(self) -> str:
        return str(ip.RESCOPE_MIGRATION_VERSION)

    def _classify(self, installed_norm, shipped_norm, override=None):
        # The one copy carrying installed-only content classifies HAS_UNIQUE;
        # the five clean older copies classify as high-confidence stale subsets.
        if self._MARKER in installed_norm:
            return _verdict("HAS_UNIQUE", "unique",
                            unique_blocks=["# Stale generic block"])
        return _verdict("SUBSET", "contained")

    def test_six_rule_case_clears_overscope_and_flags_customized(self):
        # Five older/smaller copies: installed body is a strict subset of the
        # grown shipped reference (no installed-only content).
        for filename in self._STALE_SUBSETS:
            shipped = (
                f"# {filename}\n\nShared line one.\nShared line two.\n"
                "Line the reference grew later.\n"
            )
            installed = f"# {filename}\n\nShared line one.\nShared line two.\n"
            self.write_shipped(filename, shipped)
            self.write_installed(
                filename, installed, self.old_default_for(filename))

        # The sixth carries stale generic installed-only prose -- not a project
        # edit, but the machine cannot prove that, so it must be preserved.
        self.write_shipped(
            self._CUSTOMIZED,
            f"# {self._CUSTOMIZED}\n\nShared line one.\n"
            "Line the reference grew later.\n")
        self.write_installed(
            self._CUSTOMIZED,
            f"# {self._CUSTOMIZED}\n\nShared line one.\n"
            f"{self._MARKER} carried over from an old plugin era.\n",
            self.old_default_for(self._CUSTOMIZED))

        with mock.patch.object(rule_descope_migration, "_classify_diverged", side_effect=self._classify):
            report = ip.migrate_installed_rules(self.cfg, "0.0.0", self._to_version())

        removed = _report_section(report, "removed", "deleted")
        preserved = _report_section(report, "preserved", "kept")
        skipped = _report_section(report, "skipped")

        # The five clean stale subsets are all removed -> the always-on
        # over-scope the de-scope targeted is physically cleared.
        for filename in self._STALE_SUBSETS:
            self.assertFalse(
                (self.rules_dir / filename).exists(),
                f"{filename}: a clean stale subset of the grown reference must be "
                "removed, not preserved as 'customized' (the original defect)",
            )
            self.assertTrue(
                any(filename in e and "stale subset" in e for e in removed),
                f"{filename} must be reported removed as a stale subset",
            )
            self.assertFalse(
                any(filename in e for e in preserved),
                f"{filename} must not be reported preserved",
            )

        # The sixth is surfaced-and-preserved for re-home: kept on disk AND
        # flagged with a customization notice (not silently removed, not silent).
        self.assertTrue(
            (self.rules_dir / self._CUSTOMIZED).exists(),
            "the copy carrying installed-only content must be preserved",
        )
        self.assertTrue(
            any(self._CUSTOMIZED in e and "customized block" in e for e in preserved),
            "the preserved copy must be surfaced with a re-home notice",
        )
        self.assertFalse(
            any(self._CUSTOMIZED in e for e in removed),
            "a customization-bearing copy must never be removed",
        )

        # Aggregate: every one of the six was dispositioned (none skipped), and
        # the over-scope is cleared down to exactly the one file needing review.
        for filename in (*self._STALE_SUBSETS, self._CUSTOMIZED):
            self.assertFalse(
                any(filename in e for e in skipped),
                f"{filename} must be dispositioned, not skipped",
            )
        surviving = [
            f for f in (*self._STALE_SUBSETS, self._CUSTOMIZED)
            if (self.rules_dir / f).exists()
        ]
        self.assertEqual(
            surviving, [self._CUSTOMIZED],
            "over-scope cleared: only the customization-bearing copy remains",
        )
        self.assertEqual(
            len([e for e in removed
                 if any(f in e for f in self._STALE_SUBSETS)]),
            5,
            "all five stale subsets reported removed",
        )


