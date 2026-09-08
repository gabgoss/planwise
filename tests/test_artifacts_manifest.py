#!/usr/bin/env python3
"""Integrity tests for plugins/planwise/manifests/artifacts.yaml.

Nothing in scripts/ validates a row's `upgrade_behavior` or
`missing_key_behavior` against the enums the manifest itself declares — the
only behavioural consumer is the `refresh_or_sidecar` filter — so a row
carrying a value outside the enum is a silent documentation defect. This
module makes the enum membership mechanical, and dry-runs its own check in
both directions (a mutated in-memory manifest MUST be flagged; the shipped
one MUST be clean) so a green result is evidence rather than a tautology.

Run with:  python -m unittest tests/test_artifacts_manifest.py
"""

import copy
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover — PyYAML is a dev dependency here
    yaml = None

MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "manifests" / "artifacts.yaml"
)

ENUM_FIELDS = {
    "upgrade_behavior": "upgrade_behaviors",
    "missing_key_behavior": "missing_key_behaviors",
}


def undeclared_behaviors(doc: dict) -> list[tuple[str, str, str]]:
    """Return (row id, field, value) for every row whose enum-typed field
    carries a value the manifest's own `*_behaviors:` list does not declare,
    or omits the field entirely (reported with value "<missing>")."""
    findings: list[tuple[str, str, str]] = []
    for field, enum_key in ENUM_FIELDS.items():
        declared = set(doc.get(enum_key) or [])
        for row in doc.get("artifacts") or []:
            value = row.get(field, "<missing>")
            if value not in declared:
                findings.append((row.get("id", "<no id>"), field, str(value)))
    return findings


@unittest.skipIf(yaml is None, "PyYAML not installed")
class TestArtifactsManifestEnums(unittest.TestCase):
    def setUp(self):
        self.doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_parses_with_both_enums_declared(self):
        for enum_key in ENUM_FIELDS.values():
            self.assertIsInstance(self.doc.get(enum_key), list, enum_key)
            self.assertTrue(self.doc[enum_key], f"{enum_key} must not be empty")

    def test_every_row_carries_declared_behaviors(self):
        self.assertEqual(
            undeclared_behaviors(self.doc), [],
            "every artifacts.yaml row's upgrade_behavior / missing_key_behavior "
            "must be a member of the enum the manifest declares at the top",
        )

    def test_row_ids_are_unique(self):
        ids = [row.get("id") for row in self.doc["artifacts"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate ids: {ids}")

    def test_check_fires_on_a_known_bad_manifest(self):
        """Direction dry-run: the same predicate MUST flag a mutated copy,
        otherwise the clean result above proves nothing."""
        bad = copy.deepcopy(self.doc)
        bad["artifacts"][0]["upgrade_behavior"] = "not_a_real_behavior"
        del bad["artifacts"][1]["missing_key_behavior"]
        findings = undeclared_behaviors(bad)
        self.assertEqual(
            {(f[1], f[2]) for f in findings},
            {("upgrade_behavior", "not_a_real_behavior"),
             ("missing_key_behavior", "<missing>")},
        )

    def test_context_block_notes_name_every_upgrade_time_writer(self):
        """The context block has three upgrade-time writers of different
        kinds; the row's notes must name all three so a reader never has to
        re-derive them from the scripts."""
        row = next(r for r in self.doc["artifacts"] if r["id"] == "context_block")
        self.assertEqual(row["upgrade_behavior"], "migrate_only")
        for writer in ("migrate_config()", "_flip_token_saver_on()", "calibrate()"):
            self.assertIn(writer, row["notes"], f"context_block notes must name {writer}")

    def test_upgrade_block_notes_record_the_audit(self):
        row = next(r for r in self.doc["artifacts"] if r["id"] == "upgrade_block")
        self.assertEqual(row["upgrade_behavior"], "migrate_only")
        self.assertIn("migrate_config()", row["notes"])


if __name__ == "__main__":
    unittest.main()
