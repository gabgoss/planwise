#!/usr/bin/env python3
"""Unit tests for markdown_parser's escape-aware table splitting.

Markdown table rows used to be split on the literal `|` character. A cell
containing an escaped pipe — `` `git diff --name-only \\| grep dir` ``, the
correct way to write a shell pipeline inside a table cell — produced one extra
field and shifted every subsequent column right by one. The two code paths then
failed differently and silently:

  - readers handed 8 cells to a processor expecting 7, so the row was dropped
    with no warning and no distinguishing signal between "N items exist" and
    "N+1 exist and one was unreadable";
  - writers mutated a positional index, so a status write landed on the Priority
    cell and a score write landed on the Abbrev cell.

These tests pin the fix on both halves: the raw view must round-trip verbatim so
`"|".join(...)` stays byte-for-byte faithful for writers, and the cell view must
assign an escaped row's columns identically to a clean row's for readers. They
also pin the guard that makes a short read loud rather than silent.

Run with:  python -m pytest tests/test_markdown_parser.py -q
"""

import io
import contextlib
import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from markdown_parser import (  # noqa: E402
    count_cells,
    parse_markdown_table,
    split_row_cells,
    split_row_raw,
    warn_on_unparsed_rows,
)


CLEAN_ROW = (
    "| 062 | Diff-scoped gates must name a reason "
    "| High | NOT_STARTED | DOC | 45 | [01](BB-062.md) |"
)
ESCAPED_ROW = (
    r"| 062 | Use `git diff --name-only \| grep dir` here "
    r"| High | NOT_STARTED | DOC | 45 | [01](BB-062.md) |"
)


class TestSplitRowRaw(unittest.TestCase):
    """The writers' view: segments verbatim, join round-trips byte-for-byte."""

    def test_clean_row_round_trips(self):
        self.assertEqual("|".join(split_row_raw(CLEAN_ROW)), CLEAN_ROW)

    def test_escaped_row_round_trips(self):
        # The critical property for every write-back loop: mutating one segment
        # and rejoining must not rewrite the author's escaping.
        self.assertEqual("|".join(split_row_raw(ESCAPED_ROW)), ESCAPED_ROW)

    def test_escaped_row_has_same_segment_count_as_clean(self):
        self.assertEqual(len(split_row_raw(ESCAPED_ROW)), len(split_row_raw(CLEAN_ROW)))

    def test_escape_is_preserved_not_unescaped(self):
        segments = split_row_raw(ESCAPED_ROW)
        self.assertIn(r"\|", segments[2])

    def test_write_into_status_segment_leaves_other_columns_intact(self):
        # Cell 3 (Status) is raw segment 4. Under the old naive split this index
        # held the Priority cell on an escaped row.
        parts = split_row_raw(ESCAPED_ROW)
        parts[4] = " COMPLETE "
        rewritten = "|".join(parts)
        cells = split_row_cells(rewritten)
        self.assertEqual(cells[2], "High")        # Priority untouched
        self.assertEqual(cells[3], "COMPLETE")    # Status written
        self.assertEqual(cells[4], "DOC")         # Abbrev untouched
        self.assertEqual(cells[6], "[01](BB-062.md)")


class TestSplitRowCells(unittest.TestCase):
    """The readers' view: escaped and clean rows agree column for column."""

    def test_clean_row_cell_count(self):
        self.assertEqual(len(split_row_cells(CLEAN_ROW)), 7)

    def test_escaped_row_has_same_cell_count(self):
        self.assertEqual(len(split_row_cells(ESCAPED_ROW)), 7)

    def test_escaped_row_column_assignment_matches_clean(self):
        clean, escaped = split_row_cells(CLEAN_ROW), split_row_cells(ESCAPED_ROW)
        # Demonstrably correct, not merely different: every column except the
        # Feature cell that carries the pipe must be identical.
        for idx in (0, 2, 3, 4, 5, 6):
            self.assertEqual(clean[idx], escaped[idx], f"column {idx} diverged")
        self.assertEqual(escaped[2], "High")
        self.assertEqual(escaped[3], "NOT_STARTED")
        self.assertEqual(escaped[4], "DOC")
        self.assertEqual(escaped[6], "[01](BB-062.md)")

    def test_escaped_pipe_is_unescaped_in_the_cell_value(self):
        # The reader gets the value the author meant; escaping is an artifact of
        # the table format, not part of the data.
        feature = split_row_cells(ESCAPED_ROW)[1]
        self.assertEqual(feature, "Use `git diff --name-only | grep dir` here")
        self.assertNotIn("\\", feature)

    def test_multiple_escaped_pipes_in_one_cell(self):
        row = r"| 001 | a \| b \| c | High | NOT_STARTED | DOC | 5 | [01](x.md) |"
        cells = split_row_cells(row)
        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[1], "a | b | c")
        self.assertEqual(cells[3], "NOT_STARTED")

    def test_escaped_pipes_in_two_different_cells(self):
        row = r"| 001 | a \| b | High | NOT_STARTED | DOC | 5 | [01](x \| y.md) |"
        cells = split_row_cells(row)
        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[1], "a | b")
        self.assertEqual(cells[6], "[01](x | y.md)")

    def test_leading_whitespace_row(self):
        cells = split_row_cells("   " + CLEAN_ROW)
        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[0], "062")

    def test_count_cells_agrees_with_split(self):
        self.assertEqual(count_cells(ESCAPED_ROW), len(split_row_cells(ESCAPED_ROW)))


class TestRaggedRowGuard(unittest.TestCase):
    """A row whose width disagrees with the header must never parse to shifted
    values — it is reported, and the caller can see the shortfall."""

    DOC = (
        "## Backlog Items\n\n"
        "| ID  | Feature | Priority |\n"
        "|-----|---------|----------|\n"
        "| 001 | fine | High |\n"
        "| 002 | too | many | cells |\n"
        "| 003 | fine too | Low |\n"
    )

    def _parse(self, doc, **kwargs):
        stats: dict = {}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows = parse_markdown_table(
                doc, "## Backlog Items",
                lambda cells, ln, hi: {"id": cells[0], "priority": cells[2]},
                stats=stats, **kwargs,
            )
        return rows, stats, err.getvalue()

    def test_ragged_row_is_excluded_not_shifted(self):
        rows, _, _ = self._parse(self.DOC)
        self.assertEqual([r["id"] for r in rows], ["001", "003"])
        # The well-formed rows still read correctly.
        self.assertEqual(rows[0]["priority"], "High")
        self.assertEqual(rows[1]["priority"], "Low")

    def test_stats_expose_the_shortfall(self):
        _, stats, _ = self._parse(self.DOC)
        self.assertEqual(stats["rows_present"], 3)
        self.assertEqual(stats["rows_parsed"], 2)
        self.assertEqual(stats["rows_malformed"], 1)
        self.assertEqual(stats["malformed"][0]["expected"], 3)
        self.assertEqual(stats["malformed"][0]["found"], 4)

    def test_ragged_row_warns_on_stderr(self):
        _, _, err = self._parse(self.DOC)
        self.assertIn("malformed table row", err)
        self.assertIn("expected 3 cells, found 4", err)

    def test_strict_mode_exits(self):
        with self.assertRaises(SystemExit):
            self._parse(self.DOC, strict=True)

    def test_escaped_pipe_row_is_not_flagged_as_ragged(self):
        # The whole point: a legitimately-escaped pipe is no longer a width
        # violation, so the row parses instead of being dropped.
        doc = (
            "## Backlog Items\n\n"
            "| ID  | Feature | Priority |\n"
            "|-----|---------|----------|\n"
            r"| 001 | a \| b | High |" + "\n"
        )
        rows, stats, err = self._parse(doc)
        self.assertEqual(stats["rows_malformed"], 0)
        self.assertEqual(rows[0]["priority"], "High")
        self.assertEqual(err, "")

    def test_clean_table_produces_no_warning(self):
        stats = {"rows_present": 3, "rows_parsed": 3, "rows_malformed": 0}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(warn_on_unparsed_rows(stats, "Backlog Items"), 0)
        self.assertEqual(err.getvalue(), "")

    def test_warn_helper_reports_counts(self):
        stats = {"rows_present": 14, "rows_parsed": 13, "rows_malformed": 1}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(warn_on_unparsed_rows(stats, "Backlog Items"), 1)
        message = err.getvalue()
        self.assertIn("1 of 14", message)
        self.assertIn("13 row(s) reported", message)


if __name__ == "__main__":
    unittest.main()
