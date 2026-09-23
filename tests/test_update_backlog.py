#!/usr/bin/env python3
"""Unit tests for update_backlog.py under generation.

The backlog index is a build artifact that generate_backlog_index.py
--write produces from every item file's frontmatter, so update_backlog.py
never writes to it. `--status` syncs the item file's own YAML `status:`
field (through `sync_yaml_status`) and, for COMPLETE/CLOSED, moves the file
into `Archive/` -- it never rewrites an index link. `--create` writes a new
item's BLI file and nothing else, and rejects a `--feature` over the
120-character title cap rather than truncating it.

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
  - the index itself is never written -- by any of the three operations, on
    any of these paths.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest tests/test_update_backlog.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index
import update_backlog
from parse_backlog import parse_backlog_table

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

    def write_item_file(
        self, filename: str, status: str, archived: bool = False, item_id: str = "X"
    ) -> Path:
        """Write an item file with `item_id` in its own frontmatter `id:`.

        `update_backlog.py` now locates an item's file by matching this
        field against `--id`, never by the hub's Files column -- a caller
        that wants `--status`/`--create` to find the file MUST pass the
        real numeric id the test exercises. The "X" default only serves
        fixtures that never drive a lookup by id.
        """
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(
            f"---\nid: {item_id}\nstatus: {status}\ncreated: 2026-07-06\n---\n\n# {filename}\n",
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

    def _run_main(self, argv_tail: list[str]) -> tuple[str, str, object]:
        """Invoke update_backlog.main() with a raw argv tail.

        Returns (stdout, stderr, exit_code). exit_code is None when main()
        returned normally instead of calling sys.exit().
        """
        saved_argv = sys.argv
        sys.argv = ["update_backlog"] + argv_tail
        out, err = io.StringIO(), io.StringIO()
        exit_code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    update_backlog.main()
                except SystemExit as e:
                    exit_code = e.code
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue(), exit_code

    def read_index_text(self) -> str:
        return (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")

    def row(self, item_id: str) -> dict:
        rows = parse_backlog_table(self.read_index_text())
        return next(r for r in rows if r["id"] == item_id)


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


class TestBacklogCliSurface(_UpdateBacklogFixtureBase):
    """CLI-level behavior of main(): input validation and the --create path.

    TestIdempotentArchival and TestEscapedPipeRows both exercise the
    status-update path's archival semantics; this class covers the
    surrounding CLI surface neither one touches — rejected input, a
    non-archival status transition, and item creation.
    """

    def test_invalid_status_is_rejected_without_changing_the_file(self):
        self.write_index(
            "| 046 | Drift reconcile | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        self.write_item_file("item.md", status="NOT_STARTED", archived=False)
        before = self.read_index_text()

        _, err, code = self._run_main(
            ["--config", str(self.config_path), "--id", "046", "--status", "BOGUS"]
        )

        self.assertEqual(code, 1)
        self.assertIn("Invalid status", err)
        self.assertEqual(self.read_index_text(), before)  # no partial write

    def test_missing_id_is_rejected_by_argument_parsing(self):
        self.write_index(
            "| 046 | Drift reconcile | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            ["--config", str(self.config_path), "--status", "IN_PROGRESS"]
        )

        self.assertEqual(code, 2)  # argparse's own usage-error exit code
        self.assertIn("--id", err)
        self.assertEqual(self.read_index_text(), before)

    def test_non_archival_transition_does_not_touch_archive(self):
        self.write_index(
            "| 050 | Some item | Medium | NOT_STARTED | INFRA | - | [01](item.md) |\n"
        )
        item = self.write_item_file(
            "item.md", status="NOT_STARTED", archived=False, item_id="050"
        )
        before = self.read_index_text()

        out, _, code = self._run_main(
            ["--config", str(self.config_path), "--id", "050", "--status", "IN_PROGRESS"]
        )

        self.assertIsNone(code)
        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        self.assertIn("status: IN_PROGRESS", item.read_text(encoding="utf-8"))
        self.assertEqual(self.read_index_text(), before)
        # A non-archival status leaves the file in place and never even
        # creates the Archive directory.
        self.assertTrue((self.backlog_dir / "item.md").exists())
        self.assertFalse(self.archive_dir.exists())

    def test_create_writes_only_the_bli_file(self):
        self.write_index("")  # header + separator only, no data rows
        before = self.read_index_text()

        out, _, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "New reconciliation guard",
                "--priority", "High",
                "--abbrev", "TEST",
                "--files", "new-TEST-item.md",
            ]
        )

        self.assertIsNone(code)
        self.assertIn("Created backlog item 099", out)
        self.assertIn("generate_backlog_index.py --write", out)

        bli_path = self.backlog_dir / "new-TEST-item.md"
        self.assertTrue(bli_path.exists())
        rendered = bli_path.read_text(encoding="utf-8")
        self.assertIn("id: 099", rendered)
        self.assertIn("status: NOT_STARTED", rendered)  # --status omitted -> default
        self.assertIn("priority: High", rendered)
        self.assertIn("abbrev: TEST", rendered)

        # --create never appends an index row -- the index is a build
        # artifact generate_backlog_index.py --write produces.
        self.assertEqual(self.read_index_text(), before)

    def test_create_rejects_a_duplicate_id_without_writing_a_file(self):
        self.write_index(
            "| 099 | Existing | High | NOT_STARTED | TEST | - | [01](existing-TEST-item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "dup-TEST-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.read_index_text(), before)
        self.assertFalse((self.backlog_dir / "dup-TEST-item.md").exists())

    def test_create_rejects_a_bare_duplicate_against_an_existing_prefixed_row(self):
        # The existing row is stored in PREFIXED form. Pin id_format
        # explicitly to "bare" so the new item's ID renders bare ("099")
        # instead of following the index's own predominant (prefixed) form --
        # otherwise the duplicate guard could pass for the wrong reason (an
        # exact string match on "PFX-099" == "PFX-099"). With the new ID
        # forced bare, the guard can only catch the clash by normalizing
        # "PFX-099" and "099" to the same numeric component (normalize_id),
        # which is exactly the contract under regression here.
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: bare\n", encoding="utf-8"
        )
        self.write_index(
            "| PFX-099 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )
        before = self.read_index_text()

        _, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "dup-TEST-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.read_index_text(), before)
        self.assertFalse((self.backlog_dir / "dup-TEST-item.md").exists())


class TestTitleCapAndRenderedBody(_UpdateBacklogFixtureBase):
    """The 120-character title-cap funnel at --create (never a silent
    truncation), and the two `_render_bli_file` divergence fixes: no body
    `**Status:**` line, and `## Related` in link form."""

    def _create(self, feature: str, filename: str = "cap-TEST-item.md") -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", feature,
                "--priority", "High",
                "--abbrev", "TEST",
                "--files", filename,
            ]
        )

    def test_feature_over_120_chars_is_rejected_and_writes_nothing(self):
        self.write_index("")
        feature = "x" * 121

        _out, err, code = self._create(feature)

        self.assertEqual(code, 1)
        self.assertIn("121", err)
        self.assertIn("120", err)
        self.assertFalse((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_feature_at_120_chars_is_accepted(self):
        self.write_index("")
        feature = "x" * 120

        _out, err, code = self._create(feature)

        self.assertIsNone(code)
        self.assertEqual(err, "")
        self.assertTrue((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_feature_at_120_raw_chars_with_a_quote_is_rejected_after_escaping(self):
        # 120 raw characters, one of them a `"` -- the generator's own
        # `_strip_quotes` never unescapes an inner `\"`, so escaping this
        # for frontmatter storage grows it to 121 characters, over the cap
        # the generator renders and truncates against. Accepting it here on
        # the raw length would let it pass this rejection and still get
        # silently truncated on the next `--write`.
        self.write_index("")
        feature = "x" * 119 + '"'

        _out, err, code = self._create(feature)

        self.assertEqual(code, 1)
        self.assertIn("121", err)  # the escaped length
        self.assertIn("120", err)  # both the raw length and the cap
        self.assertFalse((self.backlog_dir / "cap-TEST-item.md").exists())

    def test_created_item_carries_no_body_status_line(self):
        self.write_index("")

        self._create("A short feature")

        rendered = (self.backlog_dir / "cap-TEST-item.md").read_text(encoding="utf-8")
        self.assertNotIn("**Status:**", rendered)
        self.assertIn("**Priority:**", rendered)
        self.assertIn("**Domain:**", rendered)

    def test_related_section_uses_link_form_not_a_backticked_filename(self):
        self.write_index("")

        self._create("A short feature")

        rendered = (self.backlog_dir / "cap-TEST-item.md").read_text(encoding="utf-8")
        self.assertIn("[cap-TEST-item.md](cap-TEST-item.md)", rendered)
        self.assertNotIn("`cap-TEST-item.md`", rendered)

    def test_create_against_a_generated_heading_less_index_exits_0_and_leaves_it_byte_identical(self):
        generated_index = (
            b"Generated: 2026-01-01\n\n"
            b"| ID  | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
            b"|-----|-------|----------|--------|--------|---------|--------|-------|------|\n"
        )
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        index_path.write_bytes(generated_index)

        _out, _err, code = self._create("A generated-index create")

        self.assertIsNone(code)
        self.assertEqual(index_path.read_bytes(), generated_index)
        self.assertTrue((self.backlog_dir / "cap-TEST-item.md").exists())


class TestIdFormatConfigValidation(_UpdateBacklogFixtureBase):
    """The four branches of the optional top-level `id_format` config key.

    An unrecognized value is announced on stderr and still falls back to
    "bare" — the permissive behavior is deliberate, so the warning must not
    change the outcome, raise, or produce a non-zero exit. The three
    recognized branches (absent, "prefixed", "bare") must stay silent.

    Every fixture seeds the index with a PREFIXED row (read-only, for
    inference and the duplicate check). The frontmatter `id:` line itself is
    ALWAYS bare regardless of which branch runs: the generator's own
    frontmatter reader (`_normalize_id_text`) requires a pure-digit value
    and raises on a prefixed one (proven against the live generator --
    `--check` on a `--create`d item under `id_format: prefixed` exits
    non-zero), so `create_backlog_item` renders the bare form into
    frontmatter no matter what id_format resolves to. What each branch still
    discriminates is silence vs. a WARNING on stderr for an unrecognized
    value -- not the written id.
    """

    def _create_099(self) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Id format branch probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "idfmt-TEST-item.md",
            ]
        )

    def _seed_prefixed_index(self) -> None:
        self.write_index(
            "| PFX-050 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )

    def _created_file_text(self) -> str:
        return (self.backlog_dir / "idfmt-TEST-item.md").read_text(encoding="utf-8")

    def test_absent_id_format_infers_the_predominant_form_silently(self):
        self._seed_prefixed_index()  # config carries no id_format key

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")  # no warning on the inference path
        # Frontmatter is always bare -- see the class docstring.
        self.assertIn("id: 099", self._created_file_text())
        self.assertNotIn("id: PFX-099", self._created_file_text())

    def test_prefixed_id_format_is_accepted_silently(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")
        # Frontmatter is always bare -- see the class docstring.
        self.assertIn("id: 099", self._created_file_text())
        self.assertNotIn("id: PFX-099", self._created_file_text())

    def test_bare_id_format_is_accepted_silently(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: bare\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        _, err, code = self._create_099()

        self.assertIsNone(code)
        self.assertEqual(err, "")
        text = self._created_file_text()
        self.assertNotIn("id: PFX-099", text)  # the explicit pin beat inference
        self.assertIn("id: 099", text)

    def test_unrecognized_id_format_warns_and_still_falls_back_to_bare(self):
        # "prefix" is the near-miss typo the warning exists to catch.
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefix\n", encoding="utf-8"
        )
        self._seed_prefixed_index()

        out, err, code = self._create_099()

        # Announced, not fatal: no exception, no non-zero exit, file written.
        self.assertIsNone(code)
        self.assertIn("Created backlog item 099", out)

        # The warning names both the offending value and the accepted set.
        self.assertIn("WARNING", err)
        self.assertIn("'prefix'", err)
        self.assertIn("prefixed", err)
        self.assertIn("bare", err)

        # Behavior is unchanged — still the legacy bare form.
        text = self._created_file_text()
        self.assertNotIn("id: PFX-099", text)
        self.assertIn("id: 099", text)
        self.assertTrue((self.backlog_dir / "idfmt-TEST-item.md").exists())


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
        filename, success, message = results[0]
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
        filename, success, message = results[0]
        self.assertFalse(success)
        self.assertIn("refused", message)
        self.assertEqual(src.read_text(encoding="utf-8"), "archived copy\n")
        self.assertEqual(dst.read_text(encoding="utf-8"), "backlog copy\n")


class TestCreateCollisionSources(_UpdateBacklogFixtureBase):
    """--create's duplicate-id guard must see an id wherever it lives: a
    generated Archive shard, a hub overflow leaf, or a real item file that
    hasn't been folded into any generated index file yet."""

    SOURCE_TABLE = (
        "| ID | Title | Priority | Status | Abbrev | Score | File |\n"
        "|----|-------|----------|--------|--------|-------|------|\n"
        "| 100 | Existing elsewhere | Medium | COMPLETE | INFRA | - | "
        "[shard-item.md](shard-item.md) |\n"
    )

    def _naming(self):
        return generate_backlog_index._index_naming(
            self.backlog_dir / "00-Index-Backlog.md"
        )

    def _create_100(self, files: str) -> tuple[str, str, object]:
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "100",
                "--feature", "Duplicate attempt",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", files,
            ]
        )

    def test_rejects_id_present_only_in_an_archive_shard(self):
        self.write_index("")  # the hub itself carries no row for this id
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shard = generate_backlog_index._shard_filename(self._naming(), 100, 199)
        (self.archive_dir / shard).write_text(self.SOURCE_TABLE, encoding="utf-8")

        _out, err, code = self._create_100("dup-shard-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-shard-item.md").exists())

    def test_rejects_id_present_only_in_an_overflow_leaf(self):
        self.write_index("")  # the hub itself carries no row for this id
        leaf = generate_backlog_index._hub_filename(self._naming(), 100, 199, 1)
        (self.backlog_dir / leaf).write_text(self.SOURCE_TABLE, encoding="utf-8")

        _out, err, code = self._create_100("dup-leaf-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-leaf-item.md").exists())

    def test_rejects_id_present_only_in_an_unregenerated_item_file(self):
        self.write_index("")  # no generated file mentions this id at all
        self.write_item_file(
            "unregenerated-item.md", status="NOT_STARTED", item_id="100"
        )

        _out, err, code = self._create_100("dup-fresh-item.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "dup-fresh-item.md").exists())


class TestCreateExistingFileIdVerification(_UpdateBacklogFixtureBase):
    """--create with an existing --files target verifies the existing
    file's OWN frontmatter id before claiming it -- a stale or mistyped
    --files argument must never silently misattribute another item's file.
    """

    def test_rejects_when_existing_file_carries_a_different_id(self):
        self.write_index("")
        existing = self.backlog_dir / "claimed-item.md"
        existing.write_text(
            "---\nid: 050\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# x\n",
            encoding="utf-8",
        )
        before = existing.read_bytes()

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Claim someone else's file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "claimed-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("claimed-item.md", err)
        self.assertEqual(existing.read_bytes(), before)

    def test_rejects_when_existing_files_frontmatter_cannot_be_read(self):
        self.write_index("")
        existing = self.backlog_dir / "unreadable-item.md"
        existing.write_text("no frontmatter fence at all\n", encoding="utf-8")
        before = existing.read_bytes()

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Claim an unreadable file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "unreadable-item.md",
            ]
        )

        self.assertEqual(code, 1)
        self.assertIn("unreadable-item.md", err)
        self.assertEqual(existing.read_bytes(), before)

    def test_accepts_and_reports_created_when_existing_file_already_carries_the_id(self):
        self.write_index("")
        existing = self.backlog_dir / "already-mine.md"
        existing.write_text(
            "---\nid: 099\nstatus: NOT_STARTED\ncreated: 2026-07-06\n---\n\n# x\n",
            encoding="utf-8",
        )
        before = existing.read_bytes()

        out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "099",
                "--feature", "Re-run create on my own file",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "already-mine.md",
            ]
        )

        self.assertIsNone(code)
        self.assertEqual(err, "")
        self.assertIn("Created backlog item 099", out)
        self.assertEqual(existing.read_bytes(), before)  # never overwritten


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


class TestPrefixedIdModeEndToEnd(_UpdateBacklogFixtureBase):
    """--create must write a frontmatter id the generator can actually read
    back. Proven against the live generator: `--check` on a prefixed
    frontmatter id (the OLD behavior under id_format: prefixed) exits
    non-zero with `Error: non-numeric id value 'PFX-005'`. So --create now
    always writes the bare form, and the disk lookups (`_find_items_by_id`,
    `_known_ids_from_disk`) recognize whichever form a file actually
    carries via `normalize_id`, never the generator's pure-digit-only
    `_normalize_id_text`.
    """

    def test_create_under_prefixed_id_format_writes_a_bare_frontmatter_id(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self.write_index(
            "| PFX-050 | Existing | High | NOT_STARTED | TEST | - | "
            "[01](existing-TEST-item.md) |\n"
        )

        _out, err, code = self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "060",
                "--feature", "Prefixed mode probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "prefixed-probe-item.md",
            ]
        )

        self.assertIsNone(code)
        self.assertEqual(err, "")
        rendered = (self.backlog_dir / "prefixed-probe-item.md").read_text(encoding="utf-8")
        self.assertIn("id: 060", rendered)
        self.assertNotIn("id: PFX-060", rendered)

        # End-to-end proof: scan_backlog is what --check/--write run over
        # every item file. It raising nothing, and returning the new item,
        # IS the proof that --check/--write would succeed on this file.
        items = generate_backlog_index.scan_backlog(
            self.backlog_dir, self.archive_dir, self.backlog_dir / "00-Index-Backlog.md"
        )
        self.assertIn("060", [item["id"] for item in items])

    def test_status_finds_a_file_by_id_after_create_under_prefixed_id_format(self):
        self.config_path.write_text(
            CONFIG_YAML_FIXTURE + "id_format: prefixed\n", encoding="utf-8"
        )
        self.write_index("")
        self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", "061",
                "--feature", "Prefixed mode lookup probe",
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", "prefixed-lookup-item.md",
            ]
        )

        out = self.run_update("061", "IN_PROGRESS")

        self.assertIn("NOT_STARTED → IN_PROGRESS", out)
        rendered = (self.backlog_dir / "prefixed-lookup-item.md").read_text(encoding="utf-8")
        self.assertIn("status: IN_PROGRESS", rendered)


if __name__ == "__main__":
    unittest.main()
