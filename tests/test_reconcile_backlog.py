#!/usr/bin/env python3
"""Unit tests for backlog-index archival drift detection and reconciliation.

`reconcile_backlog.detect_drift(config)` checks every COMPLETE/CLOSED backlog
row against the archival invariant — a closed item's file must live under
`Archive/` and its index link must point there — reporting rows that violate it
(file present but unarchived, or link not repointed) as drift and rows whose
linked file exists in neither location as anomalies (deleted/renamed).
`reconcile_backlog.reconcile(config)` re-reads the index fresh and heals only
rows still drifted, moving stranded files into `Archive/` + repointing links,
and never touches an anomaly row.

These tests pin: the stranding reproduction (a COMPLETE row whose file is still
in the top-level backlog dir with a non-Archive link — the exact shape found
live), the move+relink heal, an already-archived row registering as non-drift
and being left untouched, an open row never flagged, a missing linked file
registering as an anomaly (never fabricated by reconcile), race-safety
(reconcile re-reads and will not re-move a row a concurrent writer already
healed), a relink-only case (file moved but link stale), a CLOSED (not just
COMPLETE) status also archiving, and CRLF line-ending preservation on the
destructive write.

Each test builds an isolated temp planwise tree (config.yaml + backlog index +
item files); none read or mutate the live project's backlog.

Run with:  python -m pytest scripts/test_reconcile_backlog.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
from reconcile_backlog import detect_drift, reconcile  # noqa: E402
from parse_backlog import parse_backlog_table  # noqa: E402


CONFIG_YAML_FIXTURE = """project:
  name: "BacklogReconcileFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

INDEX_HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)


class _BacklogFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree: config.yaml + backlog index +
    item files, so detect_drift/reconcile run against a hermetic copy instead
    of the live project's backlog index.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)

        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML_FIXTURE, encoding="utf-8"
        )

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_reconcile_backlog",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()

    def write_index(self, rows_markdown: str) -> Path:
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_text(INDEX_HEADER + rows_markdown, encoding="utf-8")
        return path

    def write_item_file(self, filename: str, archived: bool = False) -> Path:
        """Create a backlog item file in the top-level dir or under Archive/."""
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(
            f"---\nid: X\nstatus: COMPLETE\n---\n\n# {filename}\n", encoding="utf-8"
        )
        return path

    def read_index_text(self) -> str:
        return (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")

    def file_link_for(self, item_id: str) -> str:
        rows = parse_backlog_table(self.read_index_text())
        row = next(r for r in rows if r["id"] == item_id)
        return row["files"][0]["path"]


class TestReconcileBacklog(_BacklogFixtureBase):
    """Full detect_drift / reconcile test matrix."""

    def test_detect_finds_stranded_complete_row(self):
        # Reproduction: a COMPLETE row whose file is still in the top-level
        # backlog dir, with a non-Archive index link (the exact stranding found
        # live for a closeout-hand-edited item).
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file("stranded-INFRA-item.md", archived=False)

        result = detect_drift(self.config)

        self.assertEqual(len(result["drifts"]), 1)
        self.assertEqual(result["anomalies"], [])
        drift = result["drifts"][0]
        self.assertEqual(drift["id"], "046")
        self.assertEqual(drift["file"], "stranded-INFRA-item.md")
        self.assertTrue(drift["needs_move"])
        self.assertTrue(drift["needs_relink"])

    def test_reconcile_moves_and_relinks(self):
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file("stranded-INFRA-item.md", archived=False)

        written = reconcile(self.config)

        self.assertEqual(written, 1)
        # File physically moved into Archive/.
        self.assertFalse((self.backlog_dir / "stranded-INFRA-item.md").exists())
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        # Index link repointed under Archive/.
        self.assertEqual(self.file_link_for("046"), "Archive/stranded-INFRA-item.md")
        # No drift remains.
        self.assertEqual(detect_drift(self.config)["drifts"], [])

    def test_already_archived_untouched(self):
        # A correctly-archived COMPLETE row: no drift, and reconcile is a no-op.
        self.write_index(
            "| 045 | Done | High | COMPLETE | DOC | - | [01](Archive/archived-DOC-item.md) |\n"
        )
        self.write_item_file("archived-DOC-item.md", archived=True)

        self.assertEqual(detect_drift(self.config)["drifts"], [])
        before = self.read_index_text()
        written = reconcile(self.config)
        self.assertEqual(written, 0)
        self.assertEqual(self.read_index_text(), before)

    def test_open_row_never_flagged(self):
        # An open item legitimately lives in the top-level dir — never drift.
        self.write_index(
            "| 048 | In flight | Medium | IN_PROGRESS | INFRA | 25 | [01](open-INFRA-item.md) |\n"
        )
        self.write_item_file("open-INFRA-item.md", archived=False)

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])
        self.assertEqual(reconcile(self.config), 0)

    def test_missing_file_is_anomaly(self):
        # A CLOSED row whose linked file exists in neither location is an
        # anomaly (deleted/renamed) — reported, not drift, and reconcile must
        # not fabricate it or write anything.
        self.write_index(
            "| 099 | Ghost | Low | COMPLETE | BUG | - | [01](Archive/ghost-BUG-item.md) |\n"
        )
        # Intentionally write no item file under either location.

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["id"], "099")
        self.assertIn("not found", result["anomalies"][0]["reason"].lower())

        before = self.read_index_text()
        self.assertEqual(reconcile(self.config), 0)
        self.assertEqual(self.read_index_text(), before)

    def test_reconcile_only_still_drifted(self):
        # Race safety: a row detect found drifted may already have been healed
        # on disk by a concurrent writer. reconcile must re-read and leave it
        # untouched rather than error re-moving a file that is already archived.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file("stranded-INFRA-item.md", archived=False)

        pre = detect_drift(self.config)
        self.assertEqual(len(pre["drifts"]), 1)

        # Simulate a concurrent writer healing the row before reconcile runs:
        # move the file and repoint the link.
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(
            str(self.backlog_dir / "stranded-INFRA-item.md"),
            str(self.archive_dir / "stranded-INFRA-item.md"),
        )
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](Archive/stranded-INFRA-item.md) |\n"
        )

        self.assertEqual(reconcile(self.config), 0)
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())

    def test_relink_only_when_file_already_moved(self):
        # File already in Archive/ but the index link is still non-Archive
        # (a half-done manual fix). Drift = relink only; reconcile repoints the
        # link without erroring on a move.
        self.write_index(
            "| 044 | Half fixed | High | COMPLETE | DOC | - | [01](relinked-DOC-item.md) |\n"
        )
        self.write_item_file("relinked-DOC-item.md", archived=True)

        drift = detect_drift(self.config)["drifts"][0]
        self.assertFalse(drift["needs_move"])
        self.assertTrue(drift["needs_relink"])

        self.assertEqual(reconcile(self.config), 1)
        self.assertEqual(self.file_link_for("044"), "Archive/relinked-DOC-item.md")

    def test_closed_status_also_archives(self):
        # CLOSED (resolved-without-implementation), not just COMPLETE, is an
        # archive status — a stranded CLOSED row must also be healed.
        self.write_index(
            "| 060 | Wont fix | Low | CLOSED | PROC | - | [01](closed-PROC-item.md) |\n"
        )
        self.write_item_file("closed-PROC-item.md", archived=False)

        self.assertEqual(len(detect_drift(self.config)["drifts"]), 1)
        self.assertEqual(reconcile(self.config), 1)
        self.assertTrue((self.archive_dir / "closed-PROC-item.md").exists())

    def test_reconcile_preserves_crlf_line_endings(self):
        # The destructive write must preserve the file's original line endings.
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        crlf_content = (
            "# Backlog Index\r\n\r\n"
            "## Backlog Items\r\n\r\n"
            "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\r\n"
            "|-----|---------|----------|--------|--------|-------|-------|\r\n"
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\r\n"
        )
        with open(index_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(crlf_content)
        self.write_item_file("stranded-INFRA-item.md", archived=False)

        written = reconcile(self.config)
        self.assertEqual(written, 1)

        raw = index_path.read_bytes()
        self.assertIn(b"\r\n", raw)
        # No bare LF introduced: every LF must be part of a CRLF pair.
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        self.assertEqual(self.file_link_for("046"), "Archive/stranded-INFRA-item.md")


if __name__ == "__main__":
    unittest.main()
