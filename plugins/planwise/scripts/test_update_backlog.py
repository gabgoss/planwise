#!/usr/bin/env python3
"""Unit tests for update_backlog.py idempotent, state-coupled archival.

update_backlog.py used to archive an item's file (move into `Archive/` +
repoint the index link) ONLY as a side-effect of a status transition: main()
early-returned at `old_status == new_status` before the archival branch. So an
item whose row reached COMPLETE/CLOSED outside that transition (a closeout
hand-edit, or a no-op re-run) was stranded in the top-level backlog dir forever.

These tests exercise the actual CLI entry point (main() with an injected argv,
so the real early-return path runs) and pin the fix:
  - `--status COMPLETE` on an already-COMPLETE row whose file is stranded moves
    the file into `Archive/` and repoints the link (no longer a no-op);
  - the status write itself stays a true no-op on that path (no frontmatter/
    index status churn — only the archival location/link is reconciled);
  - archival is idempotent (a second run reports "already in Archive", link
    already `Archive/`, and changes nothing);
  - the normal NOT_STARTED -> COMPLETE transition still archives (the refactor
    did not regress the happy path).

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest scripts/test_update_backlog.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader  # noqa: E402
import update_backlog  # noqa: E402
from parse_backlog import parse_backlog_table  # noqa: E402


CONFIG_YAML_FIXTURE = """project:
  name: "UpdateBacklogFixtureProject"
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


class _UpdateBacklogFixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="update_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

    def write_index(self, rows_markdown: str) -> Path:
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_text(INDEX_HEADER + rows_markdown, encoding="utf-8")
        return path

    def write_item_file(self, filename: str, status: str, archived: bool = False) -> Path:
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(
            f"---\nid: X\nstatus: {status}\ncreated: 2026-07-06\n---\n\n# {filename}\n",
            encoding="utf-8",
        )
        return path

    def run_update(self, item_id: str, status: str) -> str:
        """Invoke update_backlog.main() via an injected argv; return stdout."""
        saved_argv = sys.argv
        sys.argv = [
            "update_backlog",
            "--config",
            str(self.config_path),
            "--id",
            item_id,
            "--status",
            status,
        ]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                update_backlog.main()
        finally:
            sys.argv = saved_argv
        return buf.getvalue()

    def read_index_text(self) -> str:
        return (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")

    def row(self, item_id: str) -> dict:
        rows = parse_backlog_table(self.read_index_text())
        return next(r for r in rows if r["id"] == item_id)


class TestIdempotentArchival(_UpdateBacklogFixtureBase):
    def test_already_complete_stranded_gets_healed(self):
        # Row is ALREADY COMPLETE, file stranded in the top-level dir with a
        # non-Archive link. `--status COMPLETE` used to no-op here; now it heals.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file("stranded-INFRA-item.md", status="COMPLETE", archived=False)

        out = self.run_update("046", "COMPLETE")

        self.assertIn("already has status COMPLETE", out)  # status write was a no-op
        self.assertFalse((self.backlog_dir / "stranded-INFRA-item.md").exists())
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(self.row("046")["files"][0]["path"], "Archive/stranded-INFRA-item.md")

    def test_status_write_stays_noop(self):
        # On the already-COMPLETE path, only the archival location/link is
        # reconciled — the frontmatter status is NOT re-synced. Seed the item
        # file's frontmatter with a DIFFERENT value and prove it is untouched.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        item = self.write_item_file(
            "stranded-INFRA-item.md", status="NOT_STARTED", archived=False
        )

        self.run_update("046", "COMPLETE")

        # Index status cell unchanged (still COMPLETE), file archived.
        self.assertEqual(self.row("046")["status"], "COMPLETE")
        # Frontmatter status NOT re-synced by the no-op path (no status churn) —
        # the file just moved, so read it from Archive/.
        moved = self.archive_dir / "stranded-INFRA-item.md"
        self.assertIn("status: NOT_STARTED", moved.read_text(encoding="utf-8"))
        self.assertFalse(item.exists())

    def test_second_run_is_idempotent(self):
        # After the first heal, a second --status COMPLETE run changes nothing.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file("stranded-INFRA-item.md", status="COMPLETE", archived=False)

        self.run_update("046", "COMPLETE")  # heals
        after_first = self.read_index_text()

        out = self.run_update("046", "COMPLETE")  # idempotent no-op
        self.assertIn("already in Archive", out)
        self.assertEqual(self.read_index_text(), after_first)  # index unchanged
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())

    def test_transition_still_archives(self):
        # Regression guard: the normal NOT_STARTED -> COMPLETE transition still
        # archives the file, repoints the link, and syncs the frontmatter.
        self.write_index(
            "| 060 | Wont fix | Low | NOT_STARTED | PROC | 10 | [01](closed-PROC-item.md) |\n"
        )
        self.write_item_file("closed-PROC-item.md", status="NOT_STARTED", archived=False)

        out = self.run_update("060", "COMPLETE")

        self.assertIn("NOT_STARTED → COMPLETE", out)
        self.assertTrue((self.archive_dir / "closed-PROC-item.md").exists())
        self.assertEqual(self.row("060")["status"], "COMPLETE")
        self.assertEqual(self.row("060")["files"][0]["path"], "Archive/closed-PROC-item.md")
        moved = self.archive_dir / "closed-PROC-item.md"
        self.assertIn("status: COMPLETE", moved.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
