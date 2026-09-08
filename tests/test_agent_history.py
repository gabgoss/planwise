#!/usr/bin/env python3
"""The historical-shipped-body discriminator for orphaned agent mirrors.

The divergence classifier assumes shipped files only ever grow, so a release
that relocates content OUT of an agent turns every stale mirror into a
superset of shipped — the signature of a customization — and the sweep
returns PRESERVE/unique for provably stale shipped content forever. The
shipped manifests/agent-history.json carries a digest of every body each
formerly-mirrored agent has ever shipped with; an installed body matching
any of them is REMOVABLE at confidence "historical-exact".

These tests pin: the fast path fires without consulting the structural
primitive; CRLF mirrors still match; an unmatched superset stays PRESERVE
and says WHY (shipped shrank, no history matched); a missing manifest
degrades to the pre-manifest verdicts; the opt-in prune writer removes a
historical-exact finding; and the shipped manifest is current for every
listed agent (the regeneration reminder).

Run with:  python -m unittest tests/test_agent_history.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import doctor_sweeps  # noqa: E402

from conftest import _verdict  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

OLD_BODY = "---\ndescription: fixture agent\n---\nBody line one.\nCheck body A.\nCheck body B.\n"
CURRENT_BODY = "---\ndescription: fixture agent\n---\nBody line one.\n"  # shrank: checks folded out
EDITED_BODY = OLD_BODY + "# My local tweak\nKeep this.\n"


class _HistoryFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agent_history_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        self.plugin_root = self.tmp / "plugin"
        self.agents_dir = self.project_root / ".claude" / "agents"
        self.agents_src_dir = self.plugin_root / "agents"
        self.agents_dir.mkdir(parents=True)
        self.agents_src_dir.mkdir(parents=True)
        self.filename = ip.FORMERLY_MIRRORED_AGENTS[1]
        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.plugin_root,
        )

    def write_manifest(self, agents: dict[str, list[str]]) -> Path:
        path = self.plugin_root / doctor_sweeps.AGENT_HISTORY_MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1, "agents": agents}), encoding="utf-8")
        return path

    def sweep_one(self) -> dict:
        matches = [f for f in ip.sweep_orphaned_agent_mirrors(self.cfg) if f["filename"] == self.filename]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def pin_version_gate_ok(self) -> None:
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )


class TestHistoricalExactDiscriminator(_HistoryFixture):
    def test_old_shipped_body_is_removable_without_consulting_the_primitive(self):
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        installed = self.agents_dir / self.filename
        installed.write_text(OLD_BODY, encoding="utf-8")
        self.write_manifest({self.filename: [doctor_sweeps.history_digest(OLD_BODY)]})

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            side_effect=AssertionError("historical-exact is a fast path; the primitive must not run"),
        ):
            finding = self.sweep_one()

        self.assertEqual(finding["verdict"], "REMOVABLE")
        self.assertEqual(finding["confidence"], "historical-exact")
        self.assertIn("previously shipped body", finding["reason"])
        self.assertTrue(installed.exists(), "the sweep is read-only")

    def test_crlf_mirror_matches_lf_history(self):
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        (self.agents_dir / self.filename).write_bytes(OLD_BODY.replace("\n", "\r\n").encode("utf-8"))
        self.write_manifest({self.filename: [doctor_sweeps.history_digest(OLD_BODY)]})

        finding = self.sweep_one()

        self.assertEqual(finding["verdict"], "REMOVABLE")
        self.assertEqual(finding["confidence"], "historical-exact")

    def test_edited_superset_stays_preserve_and_names_the_shrink(self):
        """Direction dry-run for the discriminator: a body that is NOT in the
        history must not flip — and the reason must say the shipped body
        shrank so a consumer can tell refactor-blindness from a real edit."""
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        (self.agents_dir / self.filename).write_text(EDITED_BODY, encoding="utf-8")
        self.write_manifest({self.filename: [doctor_sweeps.history_digest(OLD_BODY)]})

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["# My local tweak"]),
        ):
            finding = self.sweep_one()

        self.assertEqual(finding["verdict"], "PRESERVE")
        self.assertIn("smaller than the installed copy", finding["reason"])
        self.assertIn("no previously shipped body matched", finding["reason"])

    def test_missing_manifest_degrades_to_previous_behaviour(self):
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        (self.agents_dir / self.filename).write_text(OLD_BODY, encoding="utf-8")
        # No manifest written.

        with mock.patch.object(
            doctor_sweeps, "_classify_diverged",
            return_value=_verdict("HAS_UNIQUE", "unique", unique_blocks=["Check body A."]),
        ):
            finding = self.sweep_one()

        self.assertEqual(finding["verdict"], "PRESERVE",
                         "without history a superset must stay PRESERVE — never a confident REMOVABLE")
        self.assertIn("agent-history manifest is unavailable", finding["reason"])

    def test_malformed_manifest_is_ignored_not_fatal(self):
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        (self.agents_dir / self.filename).write_text(OLD_BODY, encoding="utf-8")
        path = self.plugin_root / doctor_sweeps.AGENT_HISTORY_MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")

        self.assertEqual(doctor_sweeps.load_agent_history(self.plugin_root), {})
        with mock.patch.object(doctor_sweeps, "_classify_diverged",
                               return_value=_verdict("HAS_UNIQUE", "unique")):
            self.assertEqual(self.sweep_one()["verdict"], "PRESERVE")

    def test_prune_stale_removes_a_historical_exact_finding(self):
        (self.agents_src_dir / self.filename).write_text(CURRENT_BODY, encoding="utf-8")
        installed = self.agents_dir / self.filename
        installed.write_text(OLD_BODY, encoding="utf-8")
        self.write_manifest({self.filename: [doctor_sweeps.history_digest(OLD_BODY)]})
        self.pin_version_gate_ok()

        self.assertEqual(ip._run_prune_stale(self.cfg), 0)

        self.assertFalse(installed.exists(), "a historical-exact mirror is pruned by the opt-in writer")


class TestShippedManifestIsCurrent(unittest.TestCase):
    """The regeneration guard: every listed agent's CURRENT shipped body must
    be in the manifest, so an agent edit cannot land without
    `python tools/gen_agent_history.py`."""

    def setUp(self):
        self.manifest_path = PLUGIN / doctor_sweeps.AGENT_HISTORY_MANIFEST
        self.assertTrue(self.manifest_path.is_file(), f"missing {self.manifest_path}")
        self.doc = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def test_schema_and_normalization_are_declared(self):
        self.assertEqual(self.doc["schema_version"], 1)
        self.assertIn("history_digest", self.doc["normalization"])

    def test_every_listed_agent_has_its_current_body_recorded(self):
        history = doctor_sweeps.load_agent_history(PLUGIN)
        for filename in doctor_sweeps.FORMERLY_MIRRORED_AGENTS:
            live = PLUGIN / "agents" / filename
            if not live.is_file():
                continue  # an agent no longer shipped keeps only its history
            digest = doctor_sweeps.history_digest(live.read_text(encoding="utf-8-sig"))
            self.assertIn(
                digest, history.get(filename, set()),
                f"agents/{filename} was edited without regenerating the agent-history "
                f"manifest — run: python tools/gen_agent_history.py",
            )

    def test_loader_and_generator_agree_on_the_digest_function(self):
        """One normalization, defined once: a CRLF and an LF rendering of the
        same text digest identically, and a one-byte edit does not."""
        text = "a\nb\n"
        self.assertEqual(doctor_sweeps.history_digest(text),
                         doctor_sweeps.history_digest(text.replace("\n", "\r\n")))
        self.assertNotEqual(doctor_sweeps.history_digest(text),
                            doctor_sweeps.history_digest(text + "c\n"))


if __name__ == "__main__":
    unittest.main()
