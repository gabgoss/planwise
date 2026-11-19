#!/usr/bin/env python3
"""Tests for relocating PRESERVE-classed orphaned agent mirrors during --upgrade.

`upgrade_io.relocate_preserved_agent_mirrors()` moves a customized mirror out
of `.claude/agents/` into `upgrade-transfers/{from}-to-{to}/`, under
`upgrade.customization_handoff: report+relocate` only. Each test builds the
PRESERVE finding with the real `sweep_orphaned_agent_mirrors()`, so the helper
is exercised on the row shape the sweep emits. Covers the report block, and
the review of an agent transfer against the shipped `agents/` folder.

Run with:  python -m unittest tests/test_agent_mirror_relocation.py
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import doctor_sweeps
import init_project as ip
import transfer_review
import upgrade_io
import upgrade_mirror_report

from conftest import _verdict

FROM_V = "1.0.6"
TO_V = "1.0.7"
PAIR = f"{FROM_V}-to-{TO_V}"
SHIPPED_BODY = "---\ndescription: fixture agent\n---\nShipped body.\n"
CUSTOM_BODY = "---\ndescription: fixture agent\n---\nShipped body.\n# Extra\nUser-added block.\n"
# A body long enough for the structural classifier to analyze, for the review test.
REVIEWED_BODY = (
    "---\ndescription: fixture agent\n---\n\n# Fixture agent\n\n"
    "## Alpha step\n\n"
    "Every alpha write must name its owner before the writer runs.\n"
    "The owner field records who approved the write and when it happened.\n"
    "A missing owner stops the write and prints the alpha error text.\n\n"
    "## Beta step\n\n"
    "Every beta read must quote the source line before the reader acts.\n"
    "The quote field records which file and which line the reader used.\n"
    "A missing quote stops the read and prints the beta error text.\n"
)


class _RelocationFixture(unittest.TestCase):
    """A temporary project with `.claude/agents/`, a shipped `agents/` folder
    and an optional `config.yaml` carrying the handoff setting."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_agentreloc_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.agents_dir = self.project_root / ".claude" / "agents"
        self.agents_src_dir = self.plugin_root / "agents"
        self.agents_dir.mkdir(parents=True)
        self.agents_src_dir.mkdir(parents=True)
        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )
        self.filename = ip.FORMERLY_MIRRORED_AGENTS[0]
        self.transfer_dir = self.project_root / self.cfg.planwise_root / "upgrade-transfers" / PAIR
        self.backup_dir = self.project_root / self.cfg.planwise_root / "upgrade-backups" / PAIR

    def set_handoff(self, value: str) -> None:
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f"upgrade:\n  customization_handoff: {value}\n", encoding="utf-8")

    def install(self, body: str, shipped: "str | None" = SHIPPED_BODY) -> Path:
        if shipped is not None:
            (self.agents_src_dir / self.filename).write_text(shipped, encoding="utf-8")
        dst = self.agents_dir / self.filename
        dst.write_text(body, encoding="utf-8")
        return dst

    def sweep(self, verdict=None) -> list[dict]:
        """Run the real sweep. `verdict` replaces the structural classifier."""
        if verdict is None:
            return ip.sweep_orphaned_agent_mirrors(self.cfg)
        with mock.patch.object(doctor_sweeps, "_classify_diverged", return_value=verdict):
            return ip.sweep_orphaned_agent_mirrors(self.cfg)

    def customized_sweep(self) -> list[dict]:
        return self.sweep(_verdict("HAS_UNIQUE", "unique", unique_blocks=["# Extra"]))

    def relocate(self, findings: list[dict]) -> list[dict]:
        return upgrade_io.relocate_preserved_agent_mirrors(self.cfg, findings, FROM_V, TO_V)

    def only(self, findings: list[dict]) -> dict:
        matches = [f for f in findings if f["filename"] == self.filename]
        self.assertEqual(len(matches), 1)
        return matches[0]


class TestRelocatePreservedAgentMirrors(_RelocationFixture):
    def test_report_plus_relocate_moves_customized_mirror(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY)
        findings = self.customized_sweep()
        self.assertEqual(self.only(findings)["verdict"], "PRESERVE")

        row = self.only(self.relocate(findings))

        self.assertEqual(row["verdict"], "TRANSFERRED")
        self.assertFalse(dst.exists(), "the mirror must leave .claude/agents/")
        transfer = Path(row["transfer_path"])
        self.assertEqual(transfer.parent, self.transfer_dir)
        text = transfer.read_text(encoding="utf-8")
        self.assertIn("source_kind: agent", text)
        self.assertIn(f"source_filename: {self.filename}", text)
        self.assertTrue(text.endswith(CUSTOM_BODY), "the full installed body is carried over")

    def test_transfer_has_pre_image_backup_and_disposition_row(self):
        self.set_handoff("report+relocate")
        self.install(CUSTOM_BODY)

        self.relocate(self.customized_sweep())

        backup = self.backup_dir / ".claude" / "agents" / self.filename
        self.assertEqual(backup.read_text(encoding="utf-8"), CUSTOM_BODY)
        log = (self.backup_dir / "DISPOSITIONS.md").read_text(encoding="utf-8")
        self.assertIn(str(Path(".claude") / "agents" / self.filename), log)
        self.assertIn("customization transferred", log)

    def test_report_handoff_leaves_the_mirror(self):
        self.set_handoff("report")
        dst = self.install(CUSTOM_BODY)
        findings = self.customized_sweep()

        result = self.relocate(findings)

        self.assertEqual(self.only(result)["verdict"], "PRESERVE")
        self.assertEqual(dst.read_text(encoding="utf-8"), CUSTOM_BODY)
        self.assertFalse(self.transfer_dir.exists(), "report writes no transfer file")
        self.assertFalse(self.backup_dir.exists(), "report writes no backup")

    def test_missing_config_defaults_to_report(self):
        dst = self.install(CUSTOM_BODY)

        result = self.relocate(self.customized_sweep())

        self.assertEqual(self.only(result)["verdict"], "PRESERVE")
        self.assertTrue(dst.exists())
        self.assertFalse(self.transfer_dir.exists())

    def test_mirror_without_shipped_counterpart_stays_preserve(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY, shipped=None)
        findings = self.sweep()
        self.assertEqual(self.only(findings)["verdict"], "PRESERVE")

        result = self.relocate(findings)

        self.assertEqual(self.only(result)["verdict"], "PRESERVE")
        self.assertTrue(dst.exists())
        self.assertFalse(self.transfer_dir.exists())

    def test_unreadable_mirror_stays_preserve(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY)
        dst.write_bytes(b"\xff\xfe\x00 not utf-8 \x80\x81")
        findings = self.sweep()
        self.assertEqual(self.only(findings)["verdict"], "PRESERVE")

        result = self.relocate(findings)

        self.assertEqual(self.only(result)["verdict"], "PRESERVE")
        self.assertTrue(dst.exists())
        self.assertFalse(self.transfer_dir.exists())

    def test_removable_row_is_not_touched(self):
        self.set_handoff("report+relocate")
        dst = self.install(SHIPPED_BODY)
        findings = self.sweep()
        self.assertEqual(self.only(findings)["verdict"], "REMOVABLE")

        result = self.relocate(findings)

        self.assertEqual(result, findings)
        self.assertTrue(dst.exists(), "only the doctor prune removes a REMOVABLE mirror")
        self.assertFalse(self.transfer_dir.exists())

    def test_failed_transfer_leaves_the_mirror(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY)
        findings = self.customized_sweep()

        with mock.patch.object(upgrade_io, "_transfer_customization", return_value=None):
            row = self.only(self.relocate(findings))

        self.assertEqual(row["verdict"], "PRESERVE")
        self.assertIn("automatic transfer failed", row["reason"])
        self.assertEqual(dst.read_text(encoding="utf-8"), CUSTOM_BODY)
        self.assertFalse(self.backup_dir.exists(), "no backup before a verified transfer")

    def test_failed_backup_leaves_the_mirror(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY)
        findings = self.customized_sweep()

        with mock.patch.object(upgrade_io, "_write_backup_preimage", return_value=False):
            row = self.only(self.relocate(findings))

        self.assertEqual(row["verdict"], "PRESERVE")
        self.assertIn("backup failed", row["reason"])
        self.assertEqual(dst.read_text(encoding="utf-8"), CUSTOM_BODY)
        self.assertFalse(self.backup_dir.joinpath("DISPOSITIONS.md").exists(),
                         "no disposition row for a move that did not happen")

    def test_failed_unlink_leaves_the_mirror_and_logs_nothing(self):
        self.set_handoff("report+relocate")
        dst = self.install(CUSTOM_BODY)
        findings = self.customized_sweep()

        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            row = self.only(self.relocate(findings))

        self.assertEqual(row["verdict"], "PRESERVE")
        self.assertIn("removal failed", row["reason"])
        self.assertTrue(dst.exists())
        self.assertFalse(self.backup_dir.joinpath("DISPOSITIONS.md").exists())


class TestMirrorReportBlock(_RelocationFixture):
    def emit(self, relocate=None) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            upgrade_mirror_report.emit_mirror_sweep(
                self.cfg,
                lambda _cfg: self.customized_sweep(),
                relocate,
            )
        return buf.getvalue()

    def test_block_prints_transferred_row_with_destination(self):
        self.set_handoff("report+relocate")
        self.install(CUSTOM_BODY)

        out = self.emit(lambda c, f: upgrade_io.relocate_preserved_agent_mirrors(
            c, f, FROM_V, TO_V))

        self.assertIn("Orphaned agent mirrors: 1", out)
        self.assertIn("TRANSFERRED", out)
        self.assertIn(f"moved to {self.transfer_dir}", out)
        self.assertNotIn("PRESERVE", out)

    def test_block_without_relocate_prints_preserve_row(self):
        self.install(CUSTOM_BODY)

        out = self.emit()

        self.assertIn("PRESERVE", out)
        self.assertNotIn("TRANSFERRED", out)

    def test_a_raising_relocate_never_raises_to_the_caller(self):
        self.install(CUSTOM_BODY)
        stderr = io.StringIO()

        def boom(_cfg, _findings):
            raise RuntimeError("boom")

        with contextlib.redirect_stderr(stderr):
            out = self.emit(boom)

        self.assertEqual(out, "")
        self.assertIn("orphaned agent mirror sweep raised unexpectedly", stderr.getvalue())


class TestUpgradeRunRelocation(unittest.TestCase):
    """`_run_upgrade()` relocates a customized mirror on both of its exits, and
    the recovery banner of the real-upgrade branch counts the transfer."""

    LIVE_VERSION = "1.1.0"
    OLD_VERSION = "1.0.0"
    FILENAME = "fix-agent.md"
    SHIPPED = "# Fix agent\n\nShipped body.\n"
    CUSTOM = SHIPPED + "# Mine\nUser-added block.\n"

    def setUp(self):
        if not ip.HAS_YAML:
            self.skipTest("PyYAML required for --upgrade")
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_agentreloc_run_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.agents_dir = self.project_root / ".claude" / "agents"
        (self.project_root / "planwise").mkdir(parents=True)
        (self.plugin_root / ".claude-plugin").mkdir(parents=True)
        (self.plugin_root / "agents").mkdir(parents=True)
        self.agents_dir.mkdir(parents=True)
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"version": self.LIVE_VERSION}), encoding="utf-8")
        template = Path(ip.__file__).resolve().parent.parent / "config.yaml.template"
        shutil.copy(str(template), str(self.plugin_root / "config.yaml.template"))
        (self.plugin_root / "agents" / self.FILENAME).write_text(self.SHIPPED, encoding="utf-8")
        self.cfg = ip.InitConfig(
            project_name="RelocFixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
            plugin_version=self.LIVE_VERSION,
        )
        patcher = mock.patch.object(artifact_upgrade, "INSTALLED_RULES", [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def pin(self, version: str, handoff: str) -> None:
        root = str(self.plugin_root).replace("\\", "/")
        (self.project_root / "planwise" / "config.yaml").write_text(
            f'plugin_root: "{root}"\nplugin_version: "{version}"\n'
            f"upgrade:\n  customization_handoff: {handoff}\n", encoding="utf-8")

    def run_upgrade(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ip._run_upgrade(self.cfg)
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_real_upgrade_moves_mirror_before_the_recovery_banner_counts_it(self):
        self.pin(self.OLD_VERSION, "report+relocate")
        mirror = self.agents_dir / self.FILENAME
        mirror.write_text(self.CUSTOM, encoding="utf-8")

        out = self.run_upgrade()

        pair = f"{self.OLD_VERSION}-to-{self.LIVE_VERSION}"
        transfer = self.project_root / "planwise" / "upgrade-transfers" / pair / self.FILENAME
        self.assertIn("Upgrade complete.", out)
        self.assertFalse(mirror.exists())
        self.assertEqual(transfer.read_text(encoding="utf-8").endswith(self.CUSTOM), True)
        self.assertIn(f"moved to {transfer}", out)
        mirror_at = out.index("Orphaned agent mirrors: 1")
        banner_at = out.index("Recovery artifacts:")
        self.assertLess(mirror_at, banner_at, "the sweep runs before the recovery aggregation")
        banner = out[banner_at:]
        self.assertIn("upgrade-transfers", banner)
        self.assertIn("review-then-discard", banner)

    def test_up_to_date_branch_moves_mirror_too(self):
        self.pin(self.LIVE_VERSION, "report+relocate")
        mirror = self.agents_dir / self.FILENAME
        mirror.write_text(self.CUSTOM, encoding="utf-8")

        out = self.run_upgrade()

        pair = f"{self.LIVE_VERSION}-to-{self.LIVE_VERSION}"
        transfer = self.project_root / "planwise" / "upgrade-transfers" / pair / self.FILENAME
        self.assertIn("Already up to date", out)
        self.assertFalse(mirror.exists())
        self.assertTrue(transfer.is_file())
        self.assertIn("TRANSFERRED", out)

    def test_report_handoff_keeps_the_mirror_on_the_real_upgrade_branch(self):
        self.pin(self.OLD_VERSION, "report")
        mirror = self.agents_dir / self.FILENAME
        mirror.write_text(self.CUSTOM, encoding="utf-8")

        out = self.run_upgrade()

        self.assertTrue(mirror.exists())
        self.assertIn("PRESERVE", out)
        self.assertNotIn("TRANSFERRED", out)


class TestAgentTransferReview(_RelocationFixture):
    def test_agent_transfer_resolves_against_shipped_agents_folder(self):
        self.set_handoff("report+relocate")
        # The shipped agent has since absorbed the customization: same body.
        self.install(REVIEWED_BODY, shipped=REVIEWED_BODY)
        transfer = upgrade_io._transfer_customization(
            self.cfg, self.filename, "agent", REVIEWED_BODY,
            _verdict("HAS_UNIQUE", "unique", unique_blocks=[]), FROM_V, TO_V)
        self.assertIsNotNone(transfer)

        rows = transfer_review.review_transfers(self.cfg)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["shipped"], f"agents/{self.filename}")
        self.assertEqual(rows[0]["status"], transfer_review.STATUS_NOW_UPSTREAM)

    def test_agent_transfer_does_not_fall_back_to_references(self):
        self.install(SHIPPED_BODY, shipped=None)
        refs = self.plugin_root / "references"
        refs.mkdir()
        (refs / self.filename).write_text(SHIPPED_BODY, encoding="utf-8")
        upgrade_io._transfer_customization(
            self.cfg, self.filename, "agent", SHIPPED_BODY,
            _verdict("HAS_UNIQUE", "unique", unique_blocks=[]), FROM_V, TO_V)

        rows = transfer_review.review_transfers(self.cfg)

        self.assertEqual(rows[0]["status"], transfer_review.STATUS_NO_COUNTERPART)

    def test_rule_transfer_still_resolves_against_references(self):
        refs = self.plugin_root / "references"
        refs.mkdir()
        (refs / "some-rule.md").write_text(SHIPPED_BODY, encoding="utf-8")
        upgrade_io._transfer_customization(
            self.cfg, "some-rule.md", "rule", SHIPPED_BODY,
            _verdict("HAS_UNIQUE", "unique", unique_blocks=[]), FROM_V, TO_V)

        rows = transfer_review.review_transfers(self.cfg)

        self.assertEqual(rows[0]["shipped"], "references/some-rule.md")


if __name__ == "__main__":
    unittest.main()
