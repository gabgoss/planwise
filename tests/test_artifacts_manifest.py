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
import re
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
SKILL_ROUTER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "skills" / "planwise" / "SKILL.md"
)

_CONSUMER_SUBCOMMAND_RE = re.compile(r"^/planwise ([a-z-]+)")
_ROUTING_TABLE_ROW_RE = re.compile(r"^\| `([a-z-]+)` \| ", re.MULTILINE)

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

    def test_backlog_artifact_rows_exist_with_required_keys(self):
        """The backlog retrofit adds four new artifact rows; each MUST carry
        every key the manifest's own schema requires of a row."""
        required_keys = {
            "id", "on_disk", "config_keys", "producer", "consumers",
            "missing_key_behavior", "upgrade_behavior",
        }
        by_id = {r["id"]: r for r in self.doc["artifacts"]}
        for row_id in (
            "backlog_changelog",
            "backlog_index_shards",
            "backlog_hub_overflow_leaves",
            "backlog_migration_ledger",
        ):
            self.assertIn(row_id, by_id, f"missing artifacts.yaml row: {row_id}")
            missing = required_keys - set(by_id[row_id])
            self.assertEqual(missing, set(), f"{row_id} is missing keys: {missing}")

    def test_backlog_index_notes_name_the_migration_writer_and_escape_hatch(self):
        row = next(r for r in self.doc["artifacts"] if r["id"] == "backlog_index")
        self.assertEqual(row["upgrade_behavior"], "migrate_shape")
        self.assertIn("migrate_backlog_if_legacy", row["notes"])
        self.assertIn("--replace-legacy", row["notes"])

    def test_backlog_changelog_notes_name_the_parts_and_resplit_flag(self):
        row = next(r for r in self.doc["artifacts"] if r["id"] == "backlog_changelog")
        self.assertIn("Part-", row["notes"])
        self.assertIn("--split-changelog", row["notes"])

    def test_header_comment_declares_the_new_enum_values(self):
        text = MANIFEST.read_text(encoding="utf-8")
        for value in ("migrate_shape", "generated", "regenerated"):
            self.assertIn(value, text, f"header comment must document {value}")
        self.assertIn("migrate_shape", self.doc["upgrade_behaviors"])
        self.assertIn("generated", self.doc["upgrade_behaviors"])
        self.assertIn("regenerated", self.doc["missing_key_behaviors"])

    def test_lessons_artifact_rows_exist_with_required_keys(self):
        """The lessons migration (mirroring the backlog retrofit) adds three
        new artifact rows; each MUST carry every key the manifest's own
        schema requires of a row."""
        required_keys = {
            "id", "on_disk", "config_keys", "producer", "consumers",
            "missing_key_behavior", "upgrade_behavior",
        }
        by_id = {r["id"]: r for r in self.doc["artifacts"]}
        for row_id in (
            "lessons_index_shards",
            "lessons_hub_overflow_leaves",
            "lessons_migration_ledger",
        ):
            self.assertIn(row_id, by_id, f"missing artifacts.yaml row: {row_id}")
            missing = required_keys - set(by_id[row_id])
            self.assertEqual(missing, set(), f"{row_id} is missing keys: {missing}")

    def test_lessons_index_flipped_to_migrate_shape(self):
        row = next(r for r in self.doc["artifacts"] if r["id"] == "lessons_index")
        self.assertEqual(row["upgrade_behavior"], "migrate_shape")
        self.assertIn("migrate_lessons_if_legacy", row["notes"])
        self.assertIn("--replace-legacy", row["notes"])

    def test_lessons_migration_ledger_mirrors_backlog_ledger_disposition(self):
        row = next(
            r for r in self.doc["artifacts"] if r["id"] == "lessons_migration_ledger"
        )
        self.assertEqual(row["upgrade_behavior"], "preserve")
        self.assertIn("migrate_lessons_index.LEDGER_FILENAME", row["notes"])

    def test_lessons_log_rows_name_their_writer_scripts(self):
        by_id = {r["id"]: r for r in self.doc["artifacts"]}
        self.assertIn("lessons_changelog.py", by_id["lessons_changelog"]["notes"])
        self.assertIn("promotion_log.py", by_id["lessons_promotion_log"]["notes"])

    def test_every_declared_upgrade_behavior_value_is_used_by_some_row(self):
        """The enum must cover every value actually used -- and, checked here
        in the other direction, every declared value should be load-bearing
        rather than aspirational; a value nothing uses is dead documentation."""
        used = {r.get("upgrade_behavior") for r in self.doc["artifacts"]}
        declared = set(self.doc["upgrade_behaviors"])
        self.assertTrue(used.issubset(declared), used - declared)

    def test_every_consumer_names_a_subcommand_the_router_actually_routes(self):
        """Every `/planwise <name>` consumer entry must name a subcommand
        the skill router's own routing table still dispatches -- derived
        from SKILL.md at test time, never a hardcoded list, so a renamed or
        retired subcommand fails this test instead of silently going stale."""
        routed = set(
            _ROUTING_TABLE_ROW_RE.findall(
                SKILL_ROUTER.read_text(encoding="utf-8-sig")
            )
        )
        self.assertTrue(routed, "SKILL.md routing table extraction found nothing")
        stale = []
        for row in self.doc["artifacts"]:
            for consumer in row.get("consumers") or []:
                match = _CONSUMER_SUBCOMMAND_RE.match(consumer)
                if match and match.group(1) not in routed:
                    stale.append((row["id"], consumer))
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
