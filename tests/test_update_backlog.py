#!/usr/bin/env python3
"""Unit tests for update_backlog.py: the `--status` path, archival and the
`--approve-placement` writer.

The backlog index is a build artifact that generate_backlog_index.py
--write produces from every item file's frontmatter, so update_backlog.py
never writes to it. `--status` syncs the item file's own YAML `status:`
field (through `sync_yaml_status`) and, for COMPLETE/CLOSED, moves the file
into `Archive/` -- it never rewrites an index link.

update_backlog.py used to archive an item's file as a side effect of a
status transition ONLY: main() early-returned at `old_status == new_status`
before the archival branch. So an item whose row reached COMPLETE/CLOSED
outside that transition (a closeout hand-edit, or a no-op re-run) was
stranded in the top-level backlog dir forever. These tests exercise the
actual CLI entry point (main() with an injected argv, so the real
early-return path runs) and pin the fix:
  - `--status COMPLETE` on an already-COMPLETE row whose file is stranded
    moves the file into `Archive/` (no longer a no-op);
  - the status write itself stays a true no-op on that path (no frontmatter
    churn -- only the archival file location is reconciled);
  - archival is idempotent (a second run reports "already in Archive" and
    changes nothing);
  - the normal NOT_STARTED -> COMPLETE transition still archives (the
    refactor did not regress the happy path);
  - the index itself is never written -- by any operation, on
    any of these paths.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

The `--create` and CLI-surface tests live in test_update_backlog_create.py,
and the `--fixed-in` tests in test_update_backlog_fixed_in.py. All three
files build on update_backlog_fixture.py, which pytest does not collect.

Run with:  python -m pytest tests/test_update_backlog.py -q
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for update_backlog_fixture

import update_backlog
from parse_backlog import parse_backlog_table
from update_backlog_fixture import _UpdateBacklogFixtureBase


class TestIdempotentArchival(_UpdateBacklogFixtureBase):
    def test_already_complete_stranded_gets_healed(self):
        # Row is ALREADY COMPLETE, file stranded in the top-level dir.
        # `--status COMPLETE` used to no-op here; now it heals the file
        # location. The index itself is never touched.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file(
            "stranded-INFRA-item.md", status="COMPLETE", archived=False, item_id="046"
        )
        before = self.read_index_text()

        out = self.run_update("046", "COMPLETE")

        self.assertIn("already has status COMPLETE", out)  # status write was a no-op
        self.assertFalse((self.backlog_dir / "stranded-INFRA-item.md").exists())
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(self.read_index_text(), before)  # the index is never rewritten

    def test_status_write_stays_noop(self):
        # On the already-COMPLETE path, only the archival file location is
        # reconciled -- the frontmatter is never rewritten at all. Prove it
        # with a byte-for-byte comparison of the file's own content, taken
        # before the move and read back after it (from its new location).
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        item = self.write_item_file(
            "stranded-INFRA-item.md", status="COMPLETE", archived=False, item_id="046"
        )
        before_bytes = item.read_bytes()

        self.run_update("046", "COMPLETE")

        moved = self.archive_dir / "stranded-INFRA-item.md"
        self.assertEqual(moved.read_bytes(), before_bytes)
        self.assertFalse(item.exists())

    def test_second_run_is_idempotent(self):
        # After the first heal, a second --status COMPLETE run changes nothing.
        self.write_index(
            "| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\n"
        )
        self.write_item_file(
            "stranded-INFRA-item.md", status="COMPLETE", archived=False, item_id="046"
        )

        self.run_update("046", "COMPLETE")  # heals
        after_first = self.read_index_text()

        out = self.run_update("046", "COMPLETE")  # idempotent no-op
        self.assertIn("already in Archive", out)
        self.assertEqual(self.read_index_text(), after_first)  # index unchanged
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())

    def test_transition_still_archives(self):
        # Regression guard: the normal NOT_STARTED -> COMPLETE transition still
        # archives the file and syncs the frontmatter. The index is untouched.
        self.write_index(
            "| 060 | Wont fix | Low | NOT_STARTED | PROC | 10 | [01](closed-PROC-item.md) |\n"
        )
        self.write_item_file(
            "closed-PROC-item.md", status="NOT_STARTED", archived=False, item_id="060"
        )
        before = self.read_index_text()

        out = self.run_update("060", "COMPLETE")

        self.assertIn("NOT_STARTED → COMPLETE", out)
        self.assertTrue((self.archive_dir / "closed-PROC-item.md").exists())
        self.assertFalse((self.backlog_dir / "closed-PROC-item.md").exists())
        moved = self.archive_dir / "closed-PROC-item.md"
        self.assertIn("status: COMPLETE", moved.read_text(encoding="utf-8"))
        self.assertEqual(self.read_index_text(), before)


class TestEscapedPipeRows(_UpdateBacklogFixtureBase):
    """A Feature cell may legitimately contain an escaped pipe. Under the old
    naive split that shifted every column right by one, the row-locator read
    the Priority cell for Status and the Score cell for Files — so an
    escaped-pipe row's file link was never found at all, and neither the
    frontmatter sync nor the archival move ever reached it."""

    ESCAPED_FEATURE = r"Run `git diff --name-only \| grep dir` first"

    def test_status_transition_leaves_the_index_untouched_and_syncs_frontmatter(self):
        self.write_index(
            f"| 062 | {self.ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 "
            "| [01](escaped-DOC-item.md) |\n"
        )
        item = self.write_item_file(
            "escaped-DOC-item.md", status="NOT_STARTED", archived=False, item_id="062"
        )
        before = self.read_index_text()

        out = self.run_update("062", "IN_PROGRESS")

        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        self.assertIn("status: IN_PROGRESS", item.read_text(encoding="utf-8"))
        # The author's escaping survives byte-for-byte -- nothing rewrote the row.
        self.assertEqual(self.read_index_text(), before)

    def test_archival_moves_the_file_despite_the_escaped_pipe_row(self):
        # A row's own escaped pipe never affects archival now -- the lookup
        # is by the item file's own frontmatter id, never by parsing the
        # row's Files cell.
        self.write_index(
            f"| 062 | {self.ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 "
            "| [01](escaped-DOC-item.md) |\n"
        )
        self.write_item_file(
            "escaped-DOC-item.md", status="NOT_STARTED", archived=False, item_id="062"
        )
        before = self.read_index_text()

        self.run_update("062", "COMPLETE")

        self.assertFalse((self.backlog_dir / "escaped-DOC-item.md").exists())
        self.assertTrue((self.archive_dir / "escaped-DOC-item.md").exists())
        self.assertEqual(self.read_index_text(), before)

    def test_feature_text_is_readable_and_row_is_not_dropped(self):
        self.write_index(
            f"| 062 | {self.ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 "
            "| [01](escaped-DOC-item.md) |\n"
            "| 063 | Plain feature | Low | NOT_STARTED | DOC | 10 | [01](plain-DOC-item.md) |\n"
        )
        rows = parse_backlog_table(self.read_index_text())

        self.assertEqual([r["id"] for r in rows], ["062", "063"])  # neither dropped
        self.assertEqual(
            rows[0]["feature"], "Run `git diff --name-only | grep dir` first"
        )

    def test_sibling_rows_and_the_index_are_unaffected(self):
        self.write_index(
            "| 061 | Before | Low | NOT_STARTED | DOC | 10 | [01](before.md) |\n"
            f"| 062 | {self.ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 "
            "| [01](escaped-DOC-item.md) |\n"
            "| 063 | After | Low | NOT_STARTED | DOC | 10 | [01](after.md) |\n"
        )
        self.write_item_file(
            "escaped-DOC-item.md", status="NOT_STARTED", archived=False, item_id="062"
        )
        before = self.read_index_text()

        self.run_update("062", "BLOCKED")

        self.assertEqual(self.read_index_text(), before)


class TestArchivalIsDrivenByFrontmatterId(_UpdateBacklogFixtureBase):
    """Archival is driven by the item's own on-disk frontmatter id, never by
    parsing the hub's Files column. A file the row's Files column also
    happens to point at, but whose OWN frontmatter id disagrees with the
    row, belongs to a different item and is left untouched.
    """

    ROW = (
        "| 141 | Owns one file | Medium | COMPLETE | INFRA | - | "
        "[01](resolvable-INFRA-item.md) [02](unrelated-item.md) |\n"
    )

    def test_only_the_matching_id_file_is_moved(self):
        self.write_index(self.ROW)
        self.write_item_file(
            "resolvable-INFRA-item.md", status="COMPLETE", archived=False, item_id="141"
        )
        # The Files column also links this file, but its OWN id is a
        # different item -- it must never be touched by item 141's archival.
        self.write_item_file(
            "unrelated-item.md", status="NOT_STARTED", archived=False, item_id="200"
        )
        before = self.read_index_text()

        out = self.run_update("141", "COMPLETE")

        self.assertIn("resolvable-INFRA-item.md: moved to Archive", out)
        self.assertNotIn("unrelated-item.md", out)
        self.assertTrue((self.archive_dir / "resolvable-INFRA-item.md").exists())
        self.assertFalse((self.backlog_dir / "resolvable-INFRA-item.md").exists())
        self.assertTrue((self.backlog_dir / "unrelated-item.md").exists())
        self.assertEqual(self.read_index_text(), before)

    def test_second_run_stays_idempotent(self):
        self.write_index(self.ROW)
        self.write_item_file(
            "resolvable-INFRA-item.md", status="COMPLETE", archived=False, item_id="141"
        )

        self.run_update("141", "COMPLETE")
        after_first = self.read_index_text()

        out = self.run_update("141", "COMPLETE")

        self.assertEqual(self.read_index_text(), after_first)
        self.assertIn("already in Archive", out)


class TestIndexNeverWritten(_UpdateBacklogFixtureBase):
    """None of update_backlog.py's three operations -- status sync,
    --create, archival -- write to the index; it is a generated artifact.
    Both an LF and a CRLF index are proven byte-identical after each
    operation, so a latent write-back cannot hide behind a line-ending
    coincidence (a `read_text`/`write_text` round-trip would retranslate
    every line to the platform's `os.linesep`, which a same-content
    comparison alone would not catch on the platform that already matches).

    Fixtures are written with `write_bytes`, never `write_text` --
    `write_text` applies the platform's own `os.linesep` translation, so a
    fixture built with it would match the platform by construction and
    leave the test vacuous everywhere.
    """

    INDEX_HEADER_BYTES = (
        b"# Backlog Index\n"
        b"\n"
        b"## Backlog Items\n"
        b"\n"
        b"| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
        b"|-----|---------|----------|--------|--------|-------|-------|\n"
    )

    def write_index_bytes(self, rows: bytes, *, crlf: bool = False) -> bytes:
        content = self.INDEX_HEADER_BYTES + rows
        if crlf:
            content = content.replace(b"\n", b"\r\n")
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_bytes(content)
        return content

    def index_bytes(self) -> bytes:
        return (self.backlog_dir / "00-Index-Backlog.md").read_bytes()

    # --- Path 1: the status-update path -----------------------------------

    STATUS_ROW = b"| 050 | Some item | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"

    def test_status_update_leaves_an_lf_index_byte_identical(self):
        before = self.write_index_bytes(self.STATUS_ROW)
        self.write_item_file("item.md", status="NOT_STARTED", archived=False, item_id="050")

        self.run_update("050", "IN_PROGRESS")

        self.assertEqual(self.index_bytes(), before)

    def test_status_update_leaves_a_crlf_index_byte_identical(self):
        before = self.write_index_bytes(self.STATUS_ROW, crlf=True)
        self.write_item_file("item.md", status="NOT_STARTED", archived=False, item_id="050")

        self.run_update("050", "IN_PROGRESS")

        self.assertEqual(self.index_bytes(), before)

    # --- Path 2: the --create path ------------------------------------------

    def _create_099(self) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "A newly created item",
                "--priority", "High",
                "--abbrev", "TEST",
                "--files", "new-TEST-item.md",
            ]
        )

    def test_create_leaves_an_lf_index_byte_identical(self):
        before = self.write_index_bytes(b"")

        _, _, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(self.index_bytes(), before)

    def test_create_leaves_a_crlf_index_byte_identical(self):
        before = self.write_index_bytes(b"", crlf=True)

        _, _, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(self.index_bytes(), before)

    # --- Path 3: the archival path ------------------------------------------

    ARCHIVAL_ROW = (
        b"| 046 | Drift reconcile | Medium | COMPLETE | INFRA | - "
        b"| [01](stranded-INFRA-item.md) |\n"
    )

    def test_archival_leaves_an_lf_index_byte_identical(self):
        before = self.write_index_bytes(self.ARCHIVAL_ROW)
        self.write_item_file(
            "stranded-INFRA-item.md", status="COMPLETE", archived=False, item_id="046"
        )

        self.run_update("046", "COMPLETE")

        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(self.index_bytes(), before)

    def test_archival_leaves_a_crlf_index_byte_identical(self):
        before = self.write_index_bytes(self.ARCHIVAL_ROW, crlf=True)
        self.write_item_file(
            "stranded-INFRA-item.md", status="COMPLETE", archived=False, item_id="046"
        )

        self.run_update("046", "COMPLETE")

        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(self.index_bytes(), before)


class TestSyncYamlStatusReporting(_UpdateBacklogFixtureBase):
    """sync_yaml_status must report which of its four outcomes fired,
    not collapse "nothing needed changing" and "could not act" into one
    bare bool. Each outcome names the path it examined.
    """

    def test_frontmatter_with_status_key_reports_changed(self):
        path = self.tmp / "with-status.md"
        path.write_text(
            "---\nid: 099\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        self.assertEqual(result.path, path)
        self.assertIn("status: COMPLETE", path.read_text(encoding="utf-8"))

    def test_missing_frontmatter_is_reported_and_names_the_path(self):
        path = self.tmp / "no-fence.md"
        path.write_text("# item\n\nNo frontmatter fence at all.\n", encoding="utf-8")

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "no_frontmatter")
        self.assertEqual(result.path, path)
        # Left byte-unchanged -- an unreported failure must not also mutate.
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "# item\n\nNo frontmatter fence at all.\n",
        )

    def test_frontmatter_without_status_key_is_reported(self):
        path = self.tmp / "no-status-key.md"
        original = "---\nid: 099\ncreated: 2026-07-06\n---\n\n# item\n"
        path.write_text(original, encoding="utf-8")

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "no_status_key")
        self.assertEqual(result.path, path)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_missing_file_is_reported_as_absent(self):
        path = self.tmp / "does-not-exist.md"

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "absent_file")
        self.assertEqual(result.path, path)

    def test_crlf_fixture_changes_only_the_status_lines_bytes(self):
        """Built from explicit bytes, not Path.write_text -- write_text
        normalizes to os.linesep and would make this pass on Windows for
        the wrong reason (testing the platform, not the code)."""
        crlf_fixture = (
            b"---\r\n"
            b"id: 099\r\n"
            b"status: NOT_STARTED\r\n"
            b"created: 2026-07-06\r\n"
            b"---\r\n"
            b"\r\n"
            b"# item\r\n"
        )
        path = self.tmp / "crlf-item.md"
        path.write_bytes(crlf_fixture)

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        updated = path.read_bytes()
        expected = crlf_fixture.replace(b"status: NOT_STARTED", b"status: COMPLETE")
        self.assertEqual(updated, expected)
        # Every line ending stayed CRLF -- no line was silently translated to LF.
        self.assertEqual(updated.count(b"\n"), updated.count(b"\r\n"))

    def test_bom_prefixed_file_syncs_successfully_and_keeps_the_bom(self):
        path = self.tmp / "bom-item.md"
        path.write_text(
            "﻿---\nid: 099\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        updated = path.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith("﻿---\n"))
        self.assertIn("status: COMPLETE", updated)

    def test_a_triple_dash_inside_a_value_does_not_truncate_the_frontmatter(self):
        # A bare substring search for "---" would match the one inside the
        # title value and treat it as the closing fence, before ever
        # reaching the real status: line.
        path = self.tmp / "dashes-in-title.md"
        path.write_text(
            '---\nid: 099\ntitle: "A --- B"\nstatus: NOT_STARTED\n'
            "created: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        updated = path.read_text(encoding="utf-8")
        self.assertIn('title: "A --- B"', updated)
        self.assertIn("status: COMPLETE", updated)
        self.assertIn("created: 2026-07-06", updated)
        self.assertIn("# item", updated)

    def test_empty_status_value_does_not_delete_the_next_key(self):
        # `\s*` matches a newline too, so on an EMPTY status value the old
        # regex kept consuming through the line break and swallowed the
        # WHOLE next key line into the replaced span, deleting it.
        path = self.tmp / "empty-status.md"
        path.write_text(
            "---\nid: 099\nstatus: \npriority: High\ncreated: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        updated = path.read_text(encoding="utf-8")
        self.assertIn("status: COMPLETE", updated)
        self.assertIn("priority: High", updated)
        self.assertIn("created: 2026-07-06", updated)

    def test_status_with_no_space_before_the_newline_does_not_delete_the_next_key(self):
        # Same bug, no-space variant: "status:\n" with nothing at all after
        # the colon.
        path = self.tmp / "no-space-status.md"
        path.write_text(
            "---\nid: 099\nstatus:\npriority: High\ncreated: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        result = update_backlog.sync_yaml_status(path, "COMPLETE")

        self.assertEqual(result.outcome, "changed")
        updated = path.read_text(encoding="utf-8")
        self.assertIn("status: COMPLETE", updated)
        self.assertIn("priority: High", updated)


class TestDiskBasedStatusLookup(_UpdateBacklogFixtureBase):
    """`--status` locates an item's file by its own frontmatter id, never by
    reading the hub -- so a closed item (Archive/-only, no hub row), a leaf
    item (not folded into the hub at all), and an item whose hub row is
    stale must all still work.
    """

    def test_status_works_on_a_closed_item_with_no_hub_row(self):
        # Closed items render only into an Archive shard, never the hub --
        # the hub here carries no row for this id at all.
        self.write_index("")
        item = self.write_item_file(
            "archived-INFRA-item.md", status="COMPLETE", archived=True, item_id="081"
        )

        out = self.run_update("081", "COMPLETE")

        self.assertIn("already has status COMPLETE", out)
        self.assertTrue(item.exists())  # already archived -- idempotent no-op

    def test_status_works_on_a_leaf_item_absent_from_the_hub(self):
        # The hub carries an unrelated row only -- as an overflow leaf would
        # leave this id. The lookup is disk-based, so that is no obstacle.
        self.write_index(
            "| 200 | Unrelated | Low | NOT_STARTED | DOC | 5 | [01](unrelated.md) |\n"
        )
        item = self.write_item_file(
            "leaf-INFRA-item.md", status="NOT_STARTED", item_id="082"
        )

        out = self.run_update("082", "IN_PROGRESS")

        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        self.assertIn("status: IN_PROGRESS", item.read_text(encoding="utf-8"))

    def test_undo_after_a_stale_hub_changes_the_frontmatter(self):
        # The hub still shows the OLD status (unregenerated) -- the file's
        # own frontmatter is what --status reads and rewrites, never the
        # stale row.
        self.write_index(
            "| 083 | Stale row | Low | COMPLETE | DOC | - | [01](stale-item.md) |\n"
        )
        item = self.write_item_file(
            "stale-item.md", status="IN_PROGRESS", item_id="083"
        )

        out = self.run_update("083", "NOT_STARTED")

        self.assertIn("IN_PROGRESS → NOT_STARTED", out)
        self.assertIn("status: NOT_STARTED", item.read_text(encoding="utf-8"))


class TestReopening(_UpdateBacklogFixtureBase):
    """Setting an open status on a file that sits in Archive/ moves it back
    out -- the closed <=> Archive/ invariant reconcile_backlog.py audits
    holds in either direction.
    """

    def test_reopening_moves_the_file_out_of_archive(self):
        self.write_index("")
        item = self.write_item_file(
            "closed-INFRA-item.md", status="COMPLETE", archived=True, item_id="080"
        )

        out = self.run_update("080", "NOT_STARTED")

        self.assertIn("COMPLETE → NOT_STARTED", out)
        self.assertFalse(item.exists())
        reopened = self.backlog_dir / "closed-INFRA-item.md"
        self.assertTrue(reopened.exists())
        self.assertIn("status: NOT_STARTED", reopened.read_text(encoding="utf-8"))

    def test_an_ordinary_open_to_open_transition_never_touches_archive(self):
        # A file already in backlog_dir has nothing to reopen -- no noise,
        # no Archive/ directory created.
        self.write_index("")
        item = self.write_item_file("open-item.md", status="NOT_STARTED", item_id="084")

        out = self.run_update("084", "IN_PROGRESS")

        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        self.assertIn("status: IN_PROGRESS", item.read_text(encoding="utf-8"))
        self.assertFalse(self.archive_dir.exists())


class TestFailedSyncNeverArchives(_UpdateBacklogFixtureBase):
    """Frontmatter is the only record of status now, so a failed sync is a
    failed command: exit non-zero, print no "Updated ... status" line, and
    never move the file.
    """

    def test_status_less_file_exits_nonzero_and_is_not_moved(self):
        self.write_index(
            "| 070 | Some item | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        item = self.backlog_dir / "item.md"
        item.write_text(
            "---\nid: 070\ncreated: 2026-07-06\n---\n\n# item\n", encoding="utf-8"
        )
        before = item.read_bytes()

        out, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "070", "--status", "COMPLETE"]
        )

        self.assertEqual(code, 1)
        self.assertNotIn("Updated item", out)
        self.assertIn("item.md", err)
        self.assertIn("no_status_key", err)
        self.assertEqual(item.read_bytes(), before)
        self.assertFalse(self.archive_dir.exists())

    def test_bom_prefixed_file_updates_successfully_end_to_end(self):
        # `sync_yaml_status` used to have its OWN non-BOM-tolerant fence
        # check, so a file `_find_items_by_id` located fine (via the
        # BOM-tolerant `_read_frontmatter_map`) then failed at the write.
        # Both are BOM-tolerant now, so the whole --status command succeeds
        # and the BOM survives the rewrite.
        self.write_index(
            "| 072 | BOM item | Low | NOT_STARTED | DOC | - | [01](bom-item.md) |\n"
        )
        item = self.backlog_dir / "bom-item.md"
        item.write_text(
            "﻿---\nid: 072\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# item\n",
            encoding="utf-8",
        )

        out, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "072", "--status", "COMPLETE"]
        )

        self.assertIsNone(code)
        self.assertEqual(err, "")
        self.assertIn("NOT_STARTED → COMPLETE", out)
        self.assertFalse(item.exists())  # archived on the COMPLETE transition
        moved = self.archive_dir / "bom-item.md"
        self.assertTrue(moved.exists())
        updated = moved.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith("﻿---\n"))
        self.assertIn("status: COMPLETE", updated)


class TestStatusEqualsForm(_UpdateBacklogFixtureBase):
    """Claude Code refuses the separate-word `--status COMPLETE` close command
    inside a worktree, so the documented close command joins the value with
    `=`. argparse already accepts that form: these cases pin that it closes
    and archives an item exactly as the separate-word form does."""

    def _write_open_item(self, item_id: str, filename: str) -> Path:
        self.write_index(
            f"| {item_id} | Equals item | Low | NOT_STARTED | DOC | - | [01]({filename}) |\n"
        )
        return self.write_item_file(filename, "NOT_STARTED", item_id=item_id)

    def test_status_equals_complete_archives_the_item(self):
        item = self._write_open_item("073", "equals-item.md")

        out, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "073", "--status=COMPLETE"]
        )

        self.assertIsNone(code, err)
        self.assertIn("NOT_STARTED → COMPLETE", out)
        self.assertFalse(item.exists())
        moved = self.archive_dir / "equals-item.md"
        self.assertTrue(moved.exists())
        self.assertIn("status: COMPLETE", moved.read_text(encoding="utf-8"))

    def test_status_equals_complete_with_resolution_file_appends_the_text(self):
        item = self._write_open_item("074", "equals-resolution.md")
        resolution = self.tmp / "resolution.md"
        resolution.write_text("every acceptance criterion was already met\n", encoding="utf-8")

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--id", "074",
                "--status=COMPLETE",
                "--resolution-file", str(resolution),
            ]
        )

        self.assertIsNone(code, err)
        self.assertFalse(item.exists())
        moved = (self.archive_dir / "equals-resolution.md").read_text(encoding="utf-8")
        self.assertEqual(moved.count(update_backlog.RESOLUTION_HEADING), 1)
        self.assertIn("every acceptance criterion was already met", moved)


class TestArchiveOverwriteGuard(_UpdateBacklogFixtureBase):
    """`archive_item_files` and `restore_item_files` both refuse to
    overwrite an existing destination, rather than letting `shutil.move`
    silently replace it."""

    def test_archive_item_files_refuses_an_existing_destination(self):
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        src = self.backlog_dir / "dup.md"
        dst = self.archive_dir / "dup.md"
        src.write_text("source copy\n", encoding="utf-8")
        dst.write_text("archived copy\n", encoding="utf-8")

        results = update_backlog.archive_item_files(
            self.backlog_dir, self.archive_dir, ["dup.md"]
        )

        self.assertEqual(len(results), 1)
        _filename, success, message = results[0]
        self.assertFalse(success)
        self.assertIn("refused", message)
        self.assertEqual(src.read_text(encoding="utf-8"), "source copy\n")
        self.assertEqual(dst.read_text(encoding="utf-8"), "archived copy\n")

    def test_restore_item_files_refuses_an_existing_destination(self):
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        src = self.archive_dir / "dup.md"
        dst = self.backlog_dir / "dup.md"
        src.write_text("archived copy\n", encoding="utf-8")
        dst.write_text("backlog copy\n", encoding="utf-8")

        results = update_backlog.restore_item_files(
            self.backlog_dir, self.archive_dir, ["dup.md"]
        )

        self.assertEqual(len(results), 1)
        _filename, success, message = results[0]
        self.assertFalse(success)
        self.assertIn("refused", message)
        self.assertEqual(src.read_text(encoding="utf-8"), "archived copy\n")
        self.assertEqual(dst.read_text(encoding="utf-8"), "backlog copy\n")


class TestDuplicateIdRefusal(_UpdateBacklogFixtureBase):
    """`--status` refuses when two files share one id -- the same anomaly
    reconcile_backlog.py's detect_drift treats as never-acted-on -- rather
    than non-atomically rewriting several files for one id."""

    def test_status_refuses_when_two_files_share_one_id(self):
        self.write_index("")
        a = self.write_item_file("first-copy.md", status="NOT_STARTED", item_id="090")
        b = self.write_item_file("second-copy.md", status="NOT_STARTED", item_id="090")

        _out, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "090", "--status", "COMPLETE"]
        )

        self.assertEqual(code, 1)
        self.assertIn(a.name, err)
        self.assertIn(b.name, err)
        self.assertIn("status: NOT_STARTED", a.read_text(encoding="utf-8"))
        self.assertIn("status: NOT_STARTED", b.read_text(encoding="utf-8"))
        self.assertFalse(self.archive_dir.exists())


class TestBlockedMoveNeverRewritesFrontmatter(_UpdateBacklogFixtureBase):
    """A move that cannot succeed (destination already occupied) is caught
    BEFORE the frontmatter write, so a refused move never leaves the
    source file's status changed with nothing to show for it."""

    def test_status_transition_refused_when_archive_destination_exists(self):
        self.write_index("")
        item = self.write_item_file("item.md", status="NOT_STARTED", item_id="095")
        # A stray file of the same name already sits in Archive/ -- the
        # move COMPLETE would require is impossible.
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        (self.archive_dir / "item.md").write_text("occupied\n", encoding="utf-8")
        before = item.read_bytes()

        _out, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "095", "--status", "COMPLETE"]
        )

        self.assertEqual(code, 1)
        self.assertIn("item.md", err)
        # Order: the destination collision is caught BEFORE the frontmatter
        # write, so the source file's own status is untouched.
        self.assertEqual(item.read_bytes(), before)
        self.assertIn(
            "occupied", (self.archive_dir / "item.md").read_text(encoding="utf-8")
        )


class TestNoOpHealsBothDirections(_UpdateBacklogFixtureBase):
    """A same-status --status call reconciles the file's location in
    EITHER direction, not just the archive-on-close direction."""

    def test_same_status_call_restores_an_open_item_stranded_in_archive(self):
        self.write_index("")
        item = self.write_item_file(
            "stray-open-item.md", status="IN_PROGRESS", archived=True, item_id="096"
        )

        out = self.run_update("096", "IN_PROGRESS")

        self.assertIn("already has status IN_PROGRESS", out)
        self.assertFalse(item.exists())
        restored = self.backlog_dir / "stray-open-item.md"
        self.assertTrue(restored.exists())


class TestSharedFrontmatterIdNormalizer(unittest.TestCase):
    """update_backlog.py and reconcile_backlog.py must agree on what counts
    as a duplicate id -- both now normalize through `_frontmatter_id`
    (`normalize_id`-based), not through two different rules."""

    def test_prefixed_and_bare_forms_of_one_id_normalize_the_same(self):
        self.assertEqual(
            update_backlog._frontmatter_id({"id": "PFX-005"}),
            update_backlog._frontmatter_id({"id": "005"}),
        )

    def test_known_ids_from_disk_treats_prefixed_and_bare_as_one_id(self):
        tmp = Path(tempfile.mkdtemp(prefix="shared_normalizer_test_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        backlog_dir = tmp / "Backlog"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        archive_dir = backlog_dir / "Archive"
        index_path = backlog_dir / "00-Index-Backlog.md"

        (backlog_dir / "prefixed-item.md").write_text(
            "---\nid: PFX-005\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# x\n",
            encoding="utf-8",
        )

        known = update_backlog._known_ids_from_disk(backlog_dir, archive_dir, index_path)

        # Looked up by the bare form -- proves the stored "PFX-005" and a
        # bare "005" query resolve to the SAME normalized key.
        self.assertIn(update_backlog.normalize_id("005"), known)


class TestApprovePlacement(_UpdateBacklogFixtureBase):
    """`--approve-placement PATH` unions a confirmed destination into the
    item's `placement_approved` frontmatter list. Every item is built by the
    real `--create` producer, so the fixture has the shape a live item has."""

    P1 = ".claude/rules/new-rule.md"
    P2 = "plugins/planwise/references/new-reference.md"

    def _create(self, item_id: str = "301") -> Path:
        self.write_index("")
        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path), "--create", "--id", item_id,
                "--feature", "Placement fixture", "--priority", "Low",
                "--abbrev", "TEST", "--files", f"item-{item_id}.md",
            ]
        )
        self.assertIsNone(code, err)
        return self.backlog_dir / f"item-{item_id}.md"

    def _approve(self, item_id: str, *paths: str, extra: tuple[str, ...] = ()):
        argv = ["--config", str(self.config_path), "--id", item_id]
        for p in paths:
            argv += ["--approve-placement", p]
        return self._run_main(argv + list(extra))

    @staticmethod
    def _frontmatter(path: Path) -> str:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        return text.split("\n---\n", 1)[0]

    def test_first_path_writes_the_key_inside_the_frontmatter(self):
        path = self._create()

        out, err, code = self._approve("301", self.P1)

        self.assertIsNone(code, err)
        self.assertIn(f"Approved placement for item 301: {self.P1}", out)
        self.assertEqual(
            self._frontmatter(path).count(f"placement_approved: [{self.P1}]"), 1
        )
        self.assertEqual(path.read_text(encoding="utf-8").count("placement_approved"), 1)

    def test_second_path_appends_sorted_and_two_flags_write_both(self):
        path = self._create()
        self._approve("301", self.P2)
        self._approve("301", self.P1)
        self.assertIn(f"placement_approved: [{self.P1}, {self.P2}]", self._frontmatter(path))

        other = self._create("302")
        _out, err, code = self._approve("302", self.P2, self.P1)
        self.assertIsNone(code, err)
        self.assertIn(f"placement_approved: [{self.P1}, {self.P2}]", self._frontmatter(other))

    def test_repeat_in_every_spelling_reports_unchanged_and_writes_nothing(self):
        path = self._create()
        self._approve("301", self.P1)
        before = path.read_bytes()
        spellings = {
            "same": self.P1,
            "dot-slash": f"./{self.P1}",
            "backslash": self.P1.replace("/", "\\"),
            "absolute in root": str(self.tmp / self.P1),
        }
        for name, spelling in spellings.items():
            with self.subTest(name):
                out, err, code = self._approve("301", spelling)
                self.assertIsNone(code, err)
                self.assertIn("placement_approved unchanged", out)
                self.assertEqual(path.read_bytes(), before)

    def test_unknown_id_exits_one(self):
        self._create()
        _out, err, code = self._approve("999", self.P1)
        self.assertEqual(code, 1, err)
        self.assertIn("Error:", err)

    def test_item_without_frontmatter_exits_one_and_stays_byte_equal(self):
        path = self._create()
        # Fence removed. The producer writes the platform's line ending (CRLF
        # on Windows, LF on Linux), so the split accepts both.
        path.write_bytes(re.split(rb"(?m)^---\r?\n", path.read_bytes(), maxsplit=2)[2])
        before = path.read_bytes()

        _out, err, code = self._approve("301", self.P1)

        self.assertEqual(code, 1, err)
        self.assertIn("Error:", err)
        self.assertEqual(path.read_bytes(), before)

    def test_writer_error_branch_reports_no_frontmatter(self):
        # An item the locator finds but the writer's own fence read cannot
        # split: the frontmatter opens and never closes after the id line.
        path = self._create()
        before = path.read_bytes()
        original = update_backlog._locate_single_item
        bare = self.tmp / "bare.md"
        bare.write_bytes(b"no frontmatter here\r\n")
        update_backlog._locate_single_item = lambda item_id: (
            bare, self.backlog_dir, self.archive_dir, self.backlog_dir / "00-Index-Backlog.md"
        )
        try:
            _out, err, code = self._approve("301", self.P1)
        finally:
            update_backlog._locate_single_item = original
        self.assertEqual(code, 1, err)
        self.assertIn("no_frontmatter", err)
        self.assertEqual(bare.read_bytes(), b"no frontmatter here\r\n")
        self.assertEqual(path.read_bytes(), before)

    def test_stands_alone_refuses_every_other_mode_flag(self):
        path = self._create()
        before = path.read_bytes()
        cases = {
            "--status": ["--status=COMPLETE"],
            "--create": [
                "--create", "--feature", "F", "--priority", "Low", "--abbrev", "DOC",
                "--files", "new.md",
            ],
            "--mark-needs-plan": ["--mark-needs-plan"],
        }
        for name, extra in cases.items():
            with self.subTest(name):
                _out, err, code = self._approve("301", self.P1, extra=tuple(extra))
                self.assertEqual(code, 1, err)
                self.assertIn("stands alone", err)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((self.backlog_dir / "new.md").exists())

    def test_absolute_path_outside_the_root_and_a_comma_exit_one(self):
        path = self._create()
        before = path.read_bytes()
        outside = str(self.tmp.parent / "elsewhere" / "x.md")
        for name, bad in {"outside root": outside, "comma": "a,b.md"}.items():
            with self.subTest(name):
                _out, err, code = self._approve("301", bad)
                self.assertEqual(code, 1, err)
                self.assertIn("Error:", err)
                self.assertEqual(path.read_bytes(), before)

    def test_block_form_list_is_replaced_without_an_orphan_line(self):
        path = self.backlog_dir / "block-form.md"
        text = (
            "---\r\nid: 303\r\nstatus: NOT_STARTED\r\n"
            f"placement_approved:\r\n  - {self.P1}\r\n  - {self.P2}\r\n"
            "refined: false\r\n---\r\n\r\n# Body\r\n"
        )
        path.write_bytes(text.encode("utf-8"))

        result = update_backlog.set_frontmatter_key(
            path, "placement_approved", f"[{self.P1}, {self.P2}]"
        )

        self.assertEqual(result.outcome, "changed")
        data = path.read_bytes()
        self.assertEqual(data.count(b"placement_approved:"), 1)
        self.assertNotIn(b"  - ", data)
        self.assertIn(b"\r\nrefined: false\r\n---\r\n", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))  # no bare LF

    def test_written_list_reads_back_through_the_item_reader(self):
        from item_frontmatter import read_item_frontmatter

        path = self._create()
        self._approve("301", self.P1, self.P2)

        self.assertEqual(
            sorted(read_item_frontmatter(path)["placement_approved"]), [self.P1, self.P2]
        )


if __name__ == "__main__":
    unittest.main()
