#!/usr/bin/env python3
"""Unit tests (TDD) for the orphaned-agent-mirror sweep.

Split from the rule de-scope + migration monolith along its Spec fixture
boundary. Covers the sweep that detects agent-mirror files left behind by a
removed/renamed source agent, its pruning behaviour, and the regression
coverage for that surface. Its own fixture base, `_AgentMirrorFixtureBase`,
is genuinely seam-local (used nowhere else in the split) and so stays in this
module rather than moving to conftest.py; it parallels `_MigrationFixtureBase`
(rules) but agents carry no `paths:` field. Shares the `_verdict` and
`_snapshot_tree` cross-seam helpers with sibling modules this monolith was
split into; those live in conftest.py.

Run with:  python -m unittest tests/test_agent_mirror_sweep.py
"""

import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import doctor_sweeps  # noqa: E402 -- patch-target home for sweep_orphaned_agent_mirrors()

from conftest import _snapshot_tree, _verdict  # noqa: E402


class _AgentMirrorFixtureBase(unittest.TestCase):
    """Builds a temporary project tree with an installed .claude/agents/ dir
    and a shipped plugin agents/ dir, for exercising
    sweep_orphaned_agent_mirrors() and the folded-in agent half of
    _run_prune_stale().

    Parallels _MigrationFixtureBase (rules), but agents carry no `paths:`
    frontmatter key, so the preserve-vs-remove comparison is a whole-file
    identity norm -- no paths-template plumbing needed here.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_agentmirror_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"

        self.agents_dir = self.project_root / ".claude" / "agents"
        self.agents_src_dir = self.plugin_root / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.agents_src_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

    # -- helpers ------------------------------------------------------------

    def write_shipped_agent(self, filename: str, body: str) -> Path:
        dst = self.agents_src_dir / filename
        dst.write_text(body, encoding="utf-8")
        return dst

    def write_installed_agent(self, filename: str, body: str) -> Path:
        dst = self.agents_dir / filename
        dst.write_text(body, encoding="utf-8")
        return dst

    def pin_version_gate_ok(self) -> None:
        """Pin the version-state gate to 'ok', mirroring
        TestDoctorStaleSweep's inline pattern, so the prune writer proceeds
        past the preflight into the sweep/removal logic."""
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )


class TestOrphanedAgentMirrorSweep(_AgentMirrorFixtureBase):
    """sweep_orphaned_agent_mirrors() -- the read-only orphaned-agent-mirror
    sweep. Parallels TestDoctorStaleSweep's sweep half, swapped onto
    FORMERLY_MIRRORED_AGENTS / .claude/agents/ instead of DESCOPED_RULES /
    .claude/rules/planwise/. Each test below pins one preserve-vs-remove
    verdict branch -- the disposition is fixed by the rule, not inferred.

    NOT YET IMPLEMENTED: sweep_orphaned_agent_mirrors() does not exist yet,
    so every test in this class is expected to fail (AttributeError) until
    it is written -- that failure is the tests-first proof.
    """

    def test_byte_identical_mirror_is_removable_fast_path(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        before = _snapshot_tree(self.project_root)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            side_effect=AssertionError("fast path must not consult the primitive"),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(installed.exists(), "the sweep is read-only -- never deletes")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "the bare sweep must leave the installed tree byte-for-byte unchanged",
        )

    def test_stale_subset_diverged_body_is_removable(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged", return_value=_verdict("SUBSET", "contained")
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "REMOVABLE")
        self.assertTrue(installed.exists(), "the sweep is read-only -- never deletes")

    def test_has_unique_body_is_preserved_with_unique_blocks(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        shipped_body = "---\ndescription: fixture agent\n---\nShipped body.\n"
        installed_body = (
            "---\ndescription: fixture agent\n---\nShipped body.\n# Extra\nUser-added block.\n"
        )
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)
        before = installed.read_bytes()

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(matches[0]["unique_blocks"], ["# Extra"])
        self.assertEqual(
            installed.read_bytes(), before, "PRESERVE must never mutate the file"
        )

    def test_has_unique_frontmatter_only_is_preserved_not_spliced(self):
        """A customized model:/tools:/maxTurns: pin, body identical -- the key
        conservative guard: agents get NO frontmatter-splice guard (that
        machinery was deleted along with the rule-precedent splice helper).
        PRESERVE, whole file, byte-for-byte, no rewrite."""
        filename = ip.FORMERLY_MIRRORED_AGENTS[3]
        body = "Shared agent body.\nSecond line.\n"
        shipped_text = f"---\ndescription: fixture agent\nmodel: sonnet\n---\n{body}"
        installed_text = f"---\ndescription: fixture agent\nmodel: opus\nmaxTurns: 40\n---\n{body}"
        self.write_shipped_agent(filename, shipped_text)
        installed = self.write_installed_agent(filename, installed_text)
        before = installed.read_bytes()

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["model: opus"]),
        ):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertEqual(
            installed.read_bytes(), before,
            "a frontmatter-only divergence must never be rewritten or spliced",
        )
        self.assertFalse(
            hasattr(ip, "_apply_agent_frontmatter_guard"),
            "the deleted rule-precedent splice guard must not be reintroduced for agents",
        )

    def test_notes_flagged_subset_is_preserved_not_removable(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[4]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        notes_text = "tolerated a sub-noise-floor installed-only fragment"
        verdict = _verdict("SUBSET", "contained", notes=notes_text)
        with mock.patch.object(doctor_sweeps, "_classify_diverged", return_value=verdict):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "a subset with non-empty notes must NOT be REMOVABLE, even at "
            "exact/contained confidence",
        )
        self.assertTrue(installed.exists())

    def test_shipped_reference_missing_is_preserved(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        installed = self.write_installed_agent(
            filename, "---\ndescription: fixture agent\n---\nNo shipped reference.\n"
        )
        # No write_shipped_agent() call -- the shipped plugin copy is absent.

        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(installed.exists())

    def test_unreadable_installed_file_is_preserved_no_crash(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        self.write_shipped_agent(filename, "---\ndescription: fixture agent\n---\nBody.\n")
        installed = self.agents_dir / filename
        # An invalid UTF-8 byte sequence -- read_text(encoding="utf-8") must
        # raise UnicodeDecodeError, which the sweep must catch and preserve
        # rather than crash on.
        installed.write_bytes(b"---\ndescription: fixture agent\n---\n\xff\xfe not utf-8\n")

        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["verdict"], "PRESERVE")
        self.assertTrue(installed.exists())

    def test_not_installed_file_is_silently_skipped(self):
        # Nothing written to .claude/agents/ for any FORMERLY_MIRRORED_AGENTS
        # entry -- none of them is a broken install, so no finding at all.
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(findings, [])

    def test_degraded_structural_compare_unavailable_is_preserved(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        shipped_body = "---\ndescription: fixture agent\n---\nBody line one.\nGrown extra line.\n"
        installed_body = "---\ndescription: fixture agent\n---\nBody line one.\n"
        self.write_shipped_agent(filename, shipped_body)
        installed = self.write_installed_agent(filename, installed_body)

        degraded = types.SimpleNamespace(
            classification="HAS_UNIQUE", confidence="unique", unique_blocks=[],
            shared_blocks=0, total_installed_blocks=0, installed_only_chars=0,
            unique_sample_tokens=[], source=ip._DEGRADED_VERDICT_SOURCE,
            notes="structural_compare unavailable; degraded to preserve",
        )
        with mock.patch.object(doctor_sweeps, "_classify_diverged", return_value=degraded):
            findings = ip.sweep_orphaned_agent_mirrors(self.cfg)

        matches = [f for f in findings if f["filename"] == filename]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0]["verdict"], "PRESERVE",
            "degraded / not-analyzed must never yield a confident REMOVABLE",
        )
        self.assertTrue(installed.exists())


class TestOrphanedAgentMirrorPrune(_AgentMirrorFixtureBase):
    """The folded-in agent half of _run_prune_stale(): one opt-in writer
    that sweeps both stale de-scoped rules and orphaned agent mirrors in
    the same pass, reusing the same per-run backup folder, PRUNED.md log,
    and version gate. Parallels TestDoctorStaleSweep's writer half.

    NOT YET IMPLEMENTED: _run_prune_stale() does not yet call
    sweep_orphaned_agent_mirrors() at all, so every REMOVABLE-agent
    scenario below currently leaves the fixture file untouched -- that
    failure to unlink/backup/log is the tests-first proof.
    """

    def test_version_gate_refusal_leaves_agent_tree_untouched(self):
        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        # No config.yaml written -- the version-state gate is "uninitialized".
        before = _snapshot_tree(self.project_root)

        # Prove the fixture is a genuine REMOVABLE candidate first (this call
        # alone forces the tests-first failure, since sweep_orphaned_agent_
        # mirrors() does not exist yet).
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(
            [f["verdict"] for f in findings if f["filename"] == filename], ["REMOVABLE"]
        )

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "a gate refusal must never delete anything")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "a gate refusal must leave the installed tree byte-for-byte unchanged",
        )

    def test_prune_writes_pre_image_backup_before_unlinking_agent(self):
        import datetime

        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        original_content = installed.read_bytes()
        self.pin_version_gate_ok()

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(
            installed.exists(), "a REMOVABLE orphaned agent mirror must be unlinked"
        )

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        backup = out_dir / filename
        self.assertTrue(
            backup.exists(), "a pre-image backup must be written before unlink"
        )
        self.assertEqual(backup.read_bytes(), original_content)

        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn("## Removed", pruned_text)
        self.assertIn(filename, pruned_text)

    def test_prune_unlink_failure_marks_remove_failed_no_orphan_backup(self):
        import datetime

        filename = ip.FORMERLY_MIRRORED_AGENTS[2]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        self.pin_version_gate_ok()

        original_unlink = Path.unlink

        def _raising_unlink(self_path, *args, **kwargs):
            if self_path == installed:
                raise OSError("mock: cannot remove")
            return original_unlink(self_path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", _raising_unlink):
            result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertTrue(installed.exists(), "a failed unlink must leave the file in place")

        today = datetime.date.today().isoformat()
        out_dir = (
            self.project_root / self.cfg.planwise_root
            / "upgrade-backups" / f"prune-{today}"
        )
        pruned_text = (out_dir / "PRUNED.md").read_text(encoding="utf-8")
        preserved_section = pruned_text.split("## Preserved", 1)[1]
        self.assertIn(
            "[REMOVE_FAILED] — could not remove", preserved_section,
            "a failed unlink must be reported as REMOVE_FAILED, not REMOVABLE",
        )
        self.assertIn(filename, preserved_section)
        self.assertFalse(
            (out_dir / filename).exists(),
            "the orphan pre-image backup must be cleaned up after a failed unlink",
        )

    def test_per_run_log_never_overwritten_same_day_gets_suffix(self):
        import datetime

        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[3]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        self.write_installed_agent(filename, body)

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)

        filename2 = ip.FORMERLY_MIRRORED_AGENTS[4]
        body2 = "---\ndescription: fixture agent\n---\nA second untouched agent body.\n"
        self.write_shipped_agent(filename2, body2)
        self.write_installed_agent(filename2, body2)

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result2, 0)

        today = datetime.date.today().isoformat()
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        first_dir = backups_root / f"prune-{today}"
        second_dir = backups_root / f"prune-{today}-2"

        self.assertTrue(first_dir.exists())
        self.assertTrue(
            second_dir.exists(), "a second same-day run must get a uniquified folder"
        )
        first_pruned = (first_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename, first_pruned)
        self.assertNotIn(
            filename2, first_pruned,
            "the first run's log must be untouched by the second run",
        )
        second_pruned = (second_dir / "PRUNED.md").read_text(encoding="utf-8")
        self.assertIn(filename2, second_pruned)

    def test_idempotent_second_run_already_removed_no_findings(self):
        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)

        result1 = ip._run_prune_stale(self.cfg)
        self.assertEqual(result1, 0)
        self.assertFalse(installed.exists())

        # Second sweep: the file is already gone, so it must produce no
        # finding at all -- not an error, not a re-report.
        findings = ip.sweep_orphaned_agent_mirrors(self.cfg)
        self.assertEqual(
            [f for f in findings if f["filename"] == filename], [],
            "an already-removed mirror must produce no finding on re-sweep",
        )

        result2 = ip._run_prune_stale(self.cfg)
        self.assertEqual(
            result2, 0, "a second run over an already-clean tree must not error"
        )


class TestOrphanedAgentMirrorRegressionsAndSurface(_AgentMirrorFixtureBase):
    """Constant-independence, no-cross-talk, CLI surface, and
    reused-primitive regressions for the orphaned-agent-mirror sweep/prune.

    NOT YET IMPLEMENTED: every scenario below is expected to fail until
    sweep_orphaned_agent_mirrors() exists and _run_prune_stale() is
    extended to call it.
    """

    def test_sweep_references_only_formerly_mirrored_agents_constant(self):
        import inspect

        self.assertFalse(
            hasattr(ip, "INSTALLED_AGENTS"),
            "the deleted mirror-install constant must not be reintroduced",
        )
        source = inspect.getsource(ip.sweep_orphaned_agent_mirrors)
        self.assertNotIn(
            "INSTALLED_AGENTS", source,
            "the sweep must reference only FORMERLY_MIRRORED_AGENTS, never "
            "the removed INSTALLED_AGENTS -- guards the NameError class",
        )
        self.assertIn("FORMERLY_MIRRORED_AGENTS", source)

    def test_no_cross_talk_between_agent_writer_and_rule_tree(self):
        self.pin_version_gate_ok()

        # A REMOVABLE agent mirror ...
        agent_filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        agent_body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(agent_filename, agent_body)
        installed_agent = self.write_installed_agent(agent_filename, agent_body)

        # ... alongside an untouched .claude/rules/planwise/ tree that the
        # agent writer must never reach into.
        rules_dir = self.project_root / ".claude" / "rules" / "planwise"
        rules_dir.mkdir(parents=True, exist_ok=True)
        sentinel_rule = rules_dir / "sentinel-rule.md"
        sentinel_text = "---\ndescription: sentinel\n---\nUntouched.\n"
        sentinel_rule.write_text(sentinel_text, encoding="utf-8")

        # ... and an actively-shipped agent (NOT in the frozen orphan list)
        # that must never be touched even though it lives in the same
        # .claude/agents/ directory as the mirrors being pruned.
        active_agent = self.agents_dir / "general-purpose.md"
        active_text = "---\ndescription: active agent\n---\nLive.\n"
        active_agent.write_text(active_text, encoding="utf-8")

        result = ip._run_prune_stale(self.cfg)

        self.assertEqual(result, 0)
        self.assertFalse(
            installed_agent.exists(), "the REMOVABLE agent mirror must be pruned"
        )
        self.assertTrue(
            sentinel_rule.exists(),
            "the agent writer must never touch .claude/rules/** -- no cross-talk",
        )
        self.assertEqual(sentinel_rule.read_text(encoding="utf-8"), sentinel_text)
        self.assertTrue(
            active_agent.exists(),
            "the writer must only ever touch files named in "
            "FORMERLY_MIRRORED_AGENTS, never an arbitrary installed agent",
        )
        self.assertEqual(active_agent.read_text(encoding="utf-8"), active_text)

    def test_bare_doctor_prints_readonly_orphan_finding_deletion_opt_in(self):
        import contextlib
        import io

        self.pin_version_gate_ok()

        filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        body = "---\ndescription: fixture agent\n---\nUntouched agent body.\n"
        self.write_shipped_agent(filename, body)
        installed = self.write_installed_agent(filename, body)
        before = _snapshot_tree(self.project_root)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = ip._run_doctor(self.cfg)
        stdout = buf.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "orphaned agent mirror sweep", stdout,
            "bare doctor must print the read-only orphaned-agent-mirror finding",
        )
        self.assertTrue(
            any(filename in line and "REMOVABLE" in line for line in stdout.splitlines()),
            "the doctor path must print a REMOVABLE row for the orphaned mirror",
        )
        self.assertTrue(installed.exists(), "bare doctor must never delete -- read-only")
        self.assertEqual(
            _snapshot_tree(self.project_root), before,
            "bare doctor must never write or delete",
        )

        # Deletion is opt-in, under --prune-stale, not the bare doctor path.
        result = ip._run_prune_stale(self.cfg)
        self.assertEqual(result, 0)
        self.assertFalse(
            installed.exists(),
            "the same finding must be actionable via the opt-in --prune-stale writer",
        )

    def test_writer_calls_reused_primitives_not_duplicated_logic(self):
        import inspect

        source = inspect.getsource(ip.sweep_orphaned_agent_mirrors)
        for primitive in (
            "_classify_diverged", "is_subset", "is_safe_to_remove",
            "_destructively_removable",
        ):
            self.assertIn(
                primitive, source,
                f"sweep_orphaned_agent_mirrors() must call the reused primitive "
                f"{primitive}() rather than duplicate comparison logic",
            )


if __name__ == "__main__":
    unittest.main()
