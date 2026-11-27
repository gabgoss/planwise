#!/usr/bin/env python3
"""Backlog-index generator tests: `--check` and its drift and anomaly reports.

These tests pin: `--check`'s four classes (clean, drift, anomaly,
stale-score); a non-numeric score on an open item read as drift; a malformed
or duplicate on-disk row reported and never healed; the reason given for a
truncated table; a stale generated file and a missing Archive shard named as
drift; and the single truncated-title warning line.

Split from `test_generate_backlog_index.py`, whose docstring maps every moved
class to its file.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index_drift.py
"""

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import score_backlog
from generate_backlog_index_fixtures import (
    _GeneratorFixtureBase,
)
from markdown_parser import split_row_cells


class TestCheckFourClasses(_GeneratorFixtureBase):
    """--check's four classes, reproduced permanently from the
    discrimination runs recorded during this session's development."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01",
                         blocks=["001"])
        self.write_item("003", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="DOC", created="2025-06-01",
                         archived=True, filename="BB-003-01-DOC-Fixture.md")

    def test_clean_after_write(self):
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)

    def test_drift_named_on_frontmatter_change(self):
        self.run_main("--write")

        # Frontmatter is the source of truth -- mutating it directly on
        # disk is exactly what --check exists to catch as drift.
        item_path = self.backlog_dir / "BB-001-01-BUG-Fixture.md"
        text = item_path.read_text(encoding="utf-8")
        item_path.write_text(text.replace("priority: High", "priority: Low"), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("row disagrees with frontmatter", out)

    def test_anomaly_reported_never_healed(self):
        self.run_main("--write")
        (self.backlog_dir / "BB-002-01-INFRA-Fixture.md").unlink()

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("002", out)
        self.assertIn("no longer resolves", out)

        # --write must not fabricate the missing row from the stale cells.
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        hub_text = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        self.assertNotIn("| 002 |", hub_text)

    def test_stale_score_reported_and_exit_zero(self):
        # Rebuild item 001 with a `created:` recent enough that the age
        # factor has room to move without hitting weights["age_cap"], so
        # advancing the clock changes ONLY the Score cell.
        #
        # CR6 repair: this used to patch `score_backlog.datetime` with a
        # plain `MagicMock`. `compute_score`'s age factor also runs
        # `isinstance(created, datetime)` on that SAME module-level name --
        # with a MagicMock in that position, `created` (always a plain
        # string here) makes that isinstance call raise `TypeError`, which
        # the factor's own `except (ValueError, TypeError): pass` silently
        # swallows, zeroing the age contribution for EVERY item scored
        # during the patch -- not "advancing the clock" at all. The test
        # still reported "Stale scores" because item 002's age factor (already
        # capped at `weights["age_cap"]` under the real clock) dropped to 0
        # once swallowed, a Score-only move for the WRONG reason; item 001,
        # this test's actual subject, never moved. A real `datetime`
        # subclass overriding only `now()` keeps `isinstance` working (a
        # string still correctly fails the check, never raises), so the age
        # factor runs for real and the clock genuinely advances.
        recent = datetime.now().astimezone().date() - timedelta(days=3)
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG",
                         created=recent.isoformat())
        self.run_main("--write")

        advanced_date = recent + timedelta(days=13)

        class _FixedNow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.combine(advanced_date, datetime.min.time())

        with patch.object(score_backlog, "datetime", _FixedNow):
            code, out, _err = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)
        self.assertIn("Stale scores", out)
        self.assertIn("benign and self-healing", out)
        # The SUBJECT item (001) is the one that actually moved -- the
        # swallowed-TypeError defect this repairs made 002 appear to move
        # instead, for an unrelated reason (its already-capped age factor
        # dropping to zero), while 001 never moved at all.
        self.assertIn("- 001:", out)
        self.assertNotIn("- 002:", out)


class TestCRLFMalformedRowAnomaly(_GeneratorFixtureBase):
    """A hand-edited generated file's row can end up with the wrong cell
    count. --check must report it as an anomaly, never heal it in place,
    and --write must replace it with the row rendered fresh from
    frontmatter -- never with cells salvaged from the broken row. Built
    from explicit CRLF bytes: Path.write_text normalizes to os.linesep, so
    a CRLF fixture authored that way would test the platform, not the
    code."""

    def test_check_reports_anomaly_and_write_replaces_from_frontmatter(self):
        self.write_item("001", title="Good row", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.run_main("--write")

        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        text = hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        patched = []
        for line in lines:
            if line.strip().startswith("| 001 |"):
                cells = split_row_cells(line)
                cells.pop(gbi.COL_DOMAIN)  # drop one cell -- shifts every later column
                patched.append("|" + "|".join(f" {c} " for c in cells) + "|")
            else:
                patched.append(line)
        crlf_bytes = "\r\n".join(patched).encode("utf-8")
        hub_path.write_bytes(crlf_bytes)

        # Assert the line-ending property on the bytes actually written,
        # not on the string that produced them.
        self.assertIn(b"\r\n", crlf_bytes)
        self.assertEqual(crlf_bytes.count(b"\n"), crlf_bytes.count(b"\r\n"))

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("malformed row", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        rewritten = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        row_001 = next(
            split_row_cells(line) for line in rewritten.split("\n")
            if line.strip().startswith("| 001 |")
        )
        self.assertEqual(len(row_001), gbi.COLUMN_COUNT)
        # Never salvaged from the broken row -- the Domain cell (dropped
        # above) is restored from frontmatter, not left missing or blank.
        self.assertEqual(row_001[gbi.COL_DOMAIN], "BUG")


class TestStaleGeneratedFileDriftAndRemoval(_GeneratorFixtureBase):
    """The only delete this generator performs: a stale generated file (on
    disk, matching its own naming predicate, but absent from the freshly
    computed set) is drift for --check and removed by --write -- and
    nothing else is ever touched. This is the load-bearing guarantee."""

    def test_check_names_it_write_removes_only_it(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("990", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-990-01-PROC-Fixture.md")
        self.run_main("--write")

        planted = self.archive_dir / "Index-Backlog-500-500.md"
        planted.write_text(
            "[Back to Backlog Index](../00-Index-Backlog.md)\n\nstale\n", encoding="utf-8"
        )
        # Named "00-"-prefixed like this module's other generated artifacts
        # (e.g. a changelog), so the scanner skips it too and the run never
        # aborts on it -- but its name does NOT match is_generated_index_file,
        # so it must never be reported or removed.
        unrelated = self.archive_dir / "00-Other-Artifact.md"
        unrelated.write_text("unrelated file, not generated, not an item\n", encoding="utf-8")
        unrelated_before = unrelated.read_bytes()
        item_files_before = {
            p: p.read_bytes() for p in self.backlog_dir.rglob("*.md")
            if not gbi.is_generated_index_file(p.name)
        }

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("Index-Backlog-500-500.md", out)
        self.assertIn("stale generated file", out)
        self.assertNotIn("Other-Artifact", out)

        code, out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertIn("Removed stale generated file", out)
        self.assertIn("Index-Backlog-500-500.md", out)

        self.assertFalse(planted.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(unrelated.read_bytes(), unrelated_before)
        for path, before in item_files_before.items():
            self.assertEqual(path.read_bytes(), before)


class TestDuplicateRowIsAnomaly(_GeneratorFixtureBase):
    """Finding F2: a same-id duplicate row on disk must never read as
    clean, whichever copy is corrupted and wherever it physically sits --
    the old `{id: cells}` dict silently collapsed two rows into one entry
    (last-wins), so both an identical duplicate and a corrupted-first
    duplicate used to pass --check clean."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"

    def _clean_row_001(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        clean_line = next(line for line in lines if line.strip().startswith("| 001 |"))
        return lines, clean_line

    def test_corrupted_first_duplicate_is_one_anomaly_never_last_wins(self):
        lines, clean_line = self._clean_row_001()
        cells = split_row_cells(clean_line)
        cells[gbi.COL_PRIORITY] = "Low"
        cells[gbi.COL_STATUS] = "COMPLETE"
        corrupted_line = "|" + "|".join(f" {c} " for c in cells) + "|"
        insert_at = lines.index(clean_line)
        lines.insert(insert_at, corrupted_line)  # corrupted copy planted BEFORE the clean one
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        duplicate_lines = [line for line in out.split("\n") if "duplicate" in line and "001" in line]
        self.assertEqual(len(duplicate_lines), 1)
        self.assertIn("duplicate row for id 001", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        rewritten = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        rows_001 = [line for line in rewritten.split("\n") if line.strip().startswith("| 001 |")]
        self.assertEqual(len(rows_001), 1)

    def test_identical_duplicate_is_also_an_anomaly(self):
        lines, clean_line = self._clean_row_001()
        insert_at = lines.index(clean_line)
        lines.insert(insert_at, clean_line)  # an exact duplicate of the clean row
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("duplicate row for id 001", out)


class TestStaleScoreShowsValuesAndNonNumericOpenIsDrift(_GeneratorFixtureBase):
    """Finding F3: the stale-score report must show both the on-disk and
    fresh Score values, not only the id, and a non-numeric on-disk Score
    on an OPEN item is drift -- missing/corrupted data, never ordinary
    time-driven aging -- while a CLOSED item's `-` convention (both sides
    already render `-`) never even reaches that branch."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("003", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="DOC", created="2025-06-01",
                         archived=True, filename="BB-003-01-DOC-Fixture.md")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"

    def _set_item_001_score(self, new_score):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        patched = []
        for line in lines:
            if line.strip().startswith("| 001 |"):
                cells = split_row_cells(line)
                cells[gbi.COL_SCORE] = new_score
                patched.append("|" + "|".join(f" {c} " for c in cells) + "|")
            else:
                patched.append(line)
        self.hub_path.write_text("\n".join(patched), encoding="utf-8")

    def test_numeric_on_disk_score_reports_both_values(self):
        self._set_item_001_score("999")

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("999 -> ", out)

        code, out, _err = self.run_main("--check", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["stale_score"]), 1)
        self.assertEqual(payload["stale_score"][0]["on_disk"], "999")
        self.assertTrue(payload["stale_score"][0]["fresh"].isdigit())

    def test_non_numeric_score_on_open_item_is_drift(self):
        self._set_item_001_score("-")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("non-numeric on an open item", out)
        self.assertNotIn("Stale scores", out)

    def test_closed_item_dash_score_is_never_drift(self):
        # Item 003 is closed -- its fresh render is ALSO "-", so an
        # unmodified closed row never reaches the Score-only comparison
        # branch, let alone the non-numeric-on-open narrowing.
        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)


class TestCrossFileDuplicateRowIsAnomaly(_GeneratorFixtureBase):
    """CR3 (Finding 3): a same-id row split across TWO different generated
    files (a stale hub copy of an item whose correct row already moved to
    its Archive shard) must be quarantined and reported exactly once,
    naming every file involved -- neither `_read_disk_table` call alone
    ever sees the collision on its own, so the old last-file-wins
    assignment into `disk_by_id` read it clean."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("150", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-150-01-PROC-Fixture.md")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"
        self.shard_path = self.archive_dir / "Index-Backlog-150-150.md"

    def _plant_stale_hub_copy_of_150(self):
        shard_text = self.shard_path.read_text(encoding="utf-8")
        shard_row = next(
            line for line in shard_text.split("\n") if line.strip().startswith("| 150 |")
        )
        stale_row = shard_row.replace("COMPLETE", "IN_PROGRESS")

        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        insert_at = next(i for i, line in enumerate(lines) if line.strip().startswith("| 001 |"))
        lines.insert(insert_at + 1, stale_row)
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

    def test_check_names_150_and_both_files(self):
        self._plant_stale_hub_copy_of_150()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("duplicate row for id 150", out)
        self.assertIn("00-Index-Backlog.md", out)
        self.assertIn("Archive/Index-Backlog-150-150.md", out)

    def test_write_leaves_exactly_one_150_row(self):
        self._plant_stale_hub_copy_of_150()

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        hub_rows = [
            line for line in self.hub_path.read_text(encoding="utf-8").split("\n")
            if line.strip().startswith("| 150 |")
        ]
        shard_rows = [
            line for line in self.shard_path.read_text(encoding="utf-8").split("\n")
            if line.strip().startswith("| 150 |")
        ]
        self.assertEqual(len(hub_rows) + len(shard_rows), 1)


# A plugin-repo commit that predates the truncated-table reason -- used only to
# load the PRE-fix `_check_drift` for the dry-run proof below.
_PRE_FIX_DRIFT_SHA = "934c7831a086c2914a6f9e2268a7d9a7c8a1aae0"


def _load_pre_fix_check_drift(sha):
    """Load `_check_drift` from `backlog_index_drift.py` as it stood at
    `sha` -- the module that owns the table walk, before the truncated-table
    reason existed -- so a test can show the OLD "no on-disk row yet" text
    was reported for a case the fix now reports correctly.
    """
    plugin_repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "-C", str(plugin_repo), "show",
         f"{sha}:plugins/planwise/scripts/backlog_index_drift.py"],
        capture_output=True, text=True, check=True,
    )
    scripts_dir = plugin_repo / "plugins" / "planwise" / "scripts"
    namespace = {
        "__name__": "pre_fix_backlog_index_drift",
        "__file__": str(scripts_dir / "backlog_index_drift.py"),
    }
    exec(  # noqa: S102 -- loads a historical git blob of this module to run its pre-fix function for regression comparison, not external/untrusted input
        compile(result.stdout, "pre_fix_backlog_index_drift.py", "exec"), namespace
    )
    return namespace["_check_drift"]


class TestTruncationWarningIsOneLinePerRun(_GeneratorFixtureBase):
    """Every mode that renders rows names the truncated items on ONE stderr
    line, so a backlog with many over-cap titles cannot bury an `Error:` or
    `Anomaly:` line. A run with no over-cap title prints no warning."""

    def _long_title(self):
        return "word " * 30

    def test_many_truncated_titles_print_one_warning_naming_every_id(self):
        for item_id in ("001", "002", "003"):
            self.write_item(item_id, title=self._long_title())
        self.write_item("004", title="Short title")

        for mode in ("--write", "--check", "--dry-run"):
            with self.subTest(mode=mode):
                _code, _out, err = self.run_main(mode)
                warnings = [ln for ln in err.splitlines() if ln.startswith("Warning:")]
                self.assertEqual(len(warnings), 1, err)
                self.assertIn("3 title(s) truncated to 120 chars", warnings[0])
                self.assertIn("001, 002, 003", warnings[0])
                self.assertNotIn("004", warnings[0])

    def test_no_truncated_title_prints_no_warning(self):
        self.write_item("001", title="Short title")

        _code, _out, err = self.run_main("--write")

        self.assertNotIn("truncated", err)


class TestTruncatedTableReasonReplacesMisleadingText(_GeneratorFixtureBase):
    """BB-380: a stray non-row line splitting an otherwise continuous table
    used to report a genuinely-present row as "no on-disk row yet". Proves
    both halves of the Execution-Time Amendment's dry-run pair: the
    pre-fix `_check_drift` (loaded from the pinned base commit) reports the
    misleading reason, and today's reports the truncated-table reason
    instead, naming the split line and the id found past it."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"
        self._split_table_after_row("001")

    def _split_table_after_row(self, item_id):
        """Insert a stray heading between two table rows -- the BB-380
        defect shape (a heading, a blank line, or any non-pipe line splits
        what should be one continuous table into two)."""
        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        insert_at = next(
            i for i, line in enumerate(lines) if line.strip().startswith(f"| {item_id} |")
        )
        lines.insert(insert_at + 1, "## Note")
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

    def test_dry_run_pair_pre_fix_fails_current_passes(self):
        # Pre-fix half: the pinned base commit's `_check_drift` reports the
        # misleading reason for a row that genuinely exists past the split.
        pre_fix_check_drift = _load_pre_fix_check_drift(_PRE_FIX_DRIFT_SHA)
        with patch.object(gbi, "_check_drift", pre_fix_check_drift):
            pre_fix_code, pre_fix_out, _err = self.run_main("--check")

        self.assertEqual(pre_fix_code, 1)
        self.assertIn("no on-disk row yet", pre_fix_out)
        self.assertNotIn("table truncated", pre_fix_out)

        # Current half: the same on-disk fixture, unpatched, reports the
        # truncated-table reason instead, naming the split line and the id.
        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("table truncated at line", out)
        self.assertIn("row for id 002 may exist after the split", out)
        self.assertNotIn("no on-disk row yet", out)


class TestMissingArchiveShardIsDrift(_GeneratorFixtureBase):
    """BB-381: a generated Archive shard the hub's `## Shards` section
    still lists, but that is absent from disk, must be reported as drift
    on `--check` and recreated byte-identical by `--write` -- never a
    silent no-op, a false "clean" report, or a traceback."""

    def test_missing_shard_is_named_drift_and_write_recreates_it(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("990", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-990-01-PROC-Fixture.md")

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        shard_path = self.archive_dir / "Index-Backlog-990-990.md"
        self.assertTrue(shard_path.exists())
        hub_text = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        self.assertIn("Index-Backlog-990-990.md", hub_text)
        original_bytes = shard_path.read_bytes()
        shard_path.unlink()

        code, out, err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertNotIn("No drift detected", out)
        self.assertNotIn("Traceback", err)
        self.assertIn("990", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertTrue(shard_path.exists())
        self.assertEqual(shard_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
