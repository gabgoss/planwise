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
    is_section_boundary,
    parse_markdown_table,
    split_row_cells,
    split_row_raw,
    warn_on_unparsed_rows,
)
from markdown_parser import find_row_by_id, pad_cell  # noqa: E402


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


class TestParseMarkdownTableCallbackContract(unittest.TestCase):
    """The processor contract: what a row_processor callback receives, when it
    is called, and how faithfully its return value passes through to the
    caller. Complements TestRaggedRowGuard, which pins the malformed-row
    exclusion machinery itself rather than the callback's calling contract."""

    HEADER = "| ID  | Feature | Priority |\n|-----|---------|----------|\n"

    def test_happy_path_invokes_processor_per_data_row(self):
        doc = (
            "## Items\n\n" + self.HEADER +
            "| 001 | first | High |\n"
            "| 002 | second | Low |\n"
        )
        calls = []

        def processor(cells, line_number, header_info):
            calls.append(cells)
            return {"id": cells[0], "feature": cells[1]}

        items = parse_markdown_table(doc, "## Items", processor)

        self.assertEqual(
            items,
            [
                {"id": "001", "feature": "first"},
                {"id": "002", "feature": "second"},
            ],
        )
        self.assertEqual(len(calls), 2)

    def test_processor_receives_header_info_and_line_number(self):
        doc = "## Items\n\n" + self.HEADER + "| 001 | first | High |\n"
        received = {}

        def processor(cells, line_number, header_info):
            received["header_info"] = header_info
            received["line_number"] = line_number
            return {"id": cells[0]}

        parse_markdown_table(doc, "## Items", processor)

        self.assertFalse(received["header_info"]["has_score_column"])
        self.assertEqual(received["header_info"]["cell_count"], 3)
        self.assertIn("ID", received["header_info"]["header_text"])
        # line_number indexes the whole document, not just the section.
        row_line = doc.split("\n")[received["line_number"]]
        self.assertEqual(row_line.strip(), "| 001 | first | High |")

    def test_section_header_scoping_ignores_rows_outside_target_section(self):
        doc = (
            "## Other Items\n\n" + self.HEADER +
            "| 900 | wrong section | Low |\n\n"
            "## Target Items\n\n" + self.HEADER +
            "| 001 | right section | High |\n"
        )
        items = parse_markdown_table(
            doc, "## Target Items", lambda cells, ln, hi: {"id": cells[0]}
        )
        self.assertEqual(items, [{"id": "001"}])

    def test_non_table_lines_between_rows_are_skipped_not_processed(self):
        doc = (
            "## Items\n\n" + self.HEADER +
            "\n"
            "Some prose describing the table that is not itself a row.\n"
            "| 001 | fine | High |\n"
        )
        calls = []
        items = parse_markdown_table(
            doc, "## Items",
            lambda cells, ln, hi: calls.append(cells) or {"id": cells[0]},
        )
        self.assertEqual(items, [{"id": "001"}])
        # The blank line and the prose line never reached the processor.
        self.assertEqual(len(calls), 1)

    def test_empty_table_returns_empty_list(self):
        doc = "## Items\n\n" + self.HEADER
        items = parse_markdown_table(
            doc, "## Items", lambda cells, ln, hi: {"id": cells[0]}
        )
        self.assertEqual(items, [])

    def test_malformed_row_is_never_handed_to_the_processor(self):
        doc = (
            "## Items\n\n" + self.HEADER +
            "| 001 | fine | High |\n"
            "| 002 | too | many | cells |\n"
            "| 003 | fine too | Low |\n"
        )
        calls = []
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            items = parse_markdown_table(
                doc, "## Items",
                lambda cells, ln, hi: calls.append(cells) or {"id": cells[0]},
            )
        # The processor is invoked for the two well-formed rows only — the
        # malformed row is filtered out before it ever reaches the callback.
        self.assertEqual([c[0] for c in calls], ["001", "003"])
        self.assertEqual(items, [{"id": "001"}, {"id": "003"}])

    def test_callback_return_shape_passes_through_unchanged(self):
        # parse_markdown_table imposes no schema on the returned dict — the
        # processor's return value reaches the caller verbatim.
        doc = "## Items\n\n" + self.HEADER + "| 001 | first | High |\n"

        def processor(cells, line_number, header_info):
            return {
                "nested": {"id": cells[0]},
                "computed": len(cells),
                "extra": ("a", "b"),
            }

        items = parse_markdown_table(doc, "## Items", processor)
        self.assertEqual(
            items,
            [{"nested": {"id": "001"}, "computed": 3, "extra": ("a", "b")}],
        )

    def test_processor_returning_none_skips_the_row(self):
        doc = (
            "## Items\n\n" + self.HEADER +
            "| 001 | keep | High |\n"
            "| 002 | drop | Low |\n"
        )
        items = parse_markdown_table(
            doc, "## Items",
            lambda cells, ln, hi: {"id": cells[0]} if cells[1] == "keep" else None,
        )
        self.assertEqual(items, [{"id": "001"}])


class TestFindRowById(unittest.TestCase):
    """The shared row-locate helper `update_backlog`'s three ID-scans each used
    to duplicate: skip non-row/header/separator lines, match an ID with
    leading zeros stripped, and hand back the first match's index and cell
    view."""

    LINES = (
        "## Backlog Items\n"
        "\n"
        "| ID  | Feature | Priority | Status | Abbrev | Files |\n"
        "|-----|---------|----------|--------|--------|-------|\n"
        "| 001 | first | High | NOT_STARTED | DOC | [01](BB-001.md) |\n"
        "| 002 | second | Low | COMPLETE | DOC | [01](BB-002.md) |\n"
    ).split("\n")

    def test_found_row_returns_index_and_cells(self):
        result = find_row_by_id(self.LINES, "002")
        self.assertIsNotNone(result)
        index, cells = result
        self.assertEqual(
            self.LINES[index].strip(),
            "| 002 | second | Low | COMPLETE | DOC | [01](BB-002.md) |",
        )
        self.assertEqual(cells[0], "002")
        self.assertEqual(cells[1], "second")

    def test_leading_zeros_normalize_on_both_sides(self):
        # A caller passing "02" must still match a row whose own ID cell reads
        # "002" — both sides are compared with leading zeros stripped.
        index, cells = find_row_by_id(self.LINES, "02")
        self.assertEqual(cells[0], "002")

    def test_not_found_returns_none(self):
        self.assertIsNone(find_row_by_id(self.LINES, "999"))

    def test_header_row_is_never_matched(self):
        # The literal ID-column header text must not itself be treated as a
        # match, even though it starts with "|" like every data row.
        self.assertIsNone(find_row_by_id(self.LINES, "ID"))

    def test_malformed_row_with_too_few_cells_is_skipped(self):
        lines = [
            "| ID | Feature | Priority | Status | Abbrev | Files |",
            "|----|---------|----------|--------|--------|-------|",
            "| 001 | only three |",
            "| 002 | fine | High | NOT_STARTED | DOC | [01](x.md) |",
        ]
        index, cells = find_row_by_id(lines, "002")
        self.assertEqual(cells[0], "002")
        self.assertEqual(index, 3)

    def test_non_row_lines_are_skipped(self):
        lines = [
            "Some prose above the table.",
            "",
            "| 001 | fine | High | NOT_STARTED | DOC | [01](x.md) |",
        ]
        index, cells = find_row_by_id(lines, "001")
        self.assertEqual(index, 2)

    def test_escaped_pipe_row_is_found_with_cells_correctly_aligned(self):
        # The row-locate helper must sit on top of split_row_cells, not a
        # naive split, or an escaped-pipe row would misalign every column
        # past the escape and never match by ID at all.
        index, cells = find_row_by_id([ESCAPED_ROW], "062")
        self.assertEqual(index, 0)
        self.assertEqual(cells[3], "NOT_STARTED")
        self.assertEqual(cells[4], "DOC")

    def test_prefixed_row_matches_a_bare_lookup(self):
        # normalize_id reduces both forms to the same numeric key: a caller
        # passing the bare form must still match a row stored in prefixed form.
        lines = [
            "| ID  | Feature | Priority | Status | Abbrev | Files |",
            "|-----|---------|----------|--------|--------|-------|",
            "| PFX-002 | second | Low | COMPLETE | DOC | [01](BB-002.md) |",
        ]
        index, cells = find_row_by_id(lines, "002")
        self.assertEqual(index, 2)
        self.assertEqual(cells[0], "PFX-002")

    def test_bare_row_matches_a_prefixed_lookup(self):
        # And the reverse: a bare-form row must match a prefixed --id lookup.
        lines = [
            "| ID  | Feature | Priority | Status | Abbrev | Files |",
            "|-----|---------|----------|--------|--------|-------|",
            "| 002 | second | Low | COMPLETE | DOC | [01](BB-002.md) |",
        ]
        index, cells = find_row_by_id(lines, "PFX-002")
        self.assertEqual(index, 2)
        self.assertEqual(cells[0], "002")


class TestIsSectionBoundary(unittest.TestCase):
    """The shared boundary predicate `parse_markdown_table` and
    `write_scores_to_index`'s walker both terminate a table section on."""

    def test_blank_line_is_not_a_boundary(self):
        self.assertFalse(is_section_boundary(""))

    def test_heading_is_always_a_boundary(self):
        self.assertTrue(is_section_boundary("## Dependencies"))

    def test_dashes_are_a_boundary_once_the_table_separator_has_been_seen(self):
        self.assertTrue(is_section_boundary("---", separator_seen=True))

    def test_dashes_are_not_a_boundary_before_the_table_separator_row(self):
        # separator_seen=False means the table's own header separator row
        # ("|---|---|") has not been consumed yet -- a "---" text line before
        # that point must not be mistaken for a section-ending rule.
        self.assertFalse(is_section_boundary("---", separator_seen=False))

    def test_ordinary_table_row_is_not_a_boundary(self):
        self.assertFalse(is_section_boundary("| 001 | Feature | High |"))


class TestPadCell(unittest.TestCase):
    """The shared padding-preserving cell replacement `update_backlog` and
    `reconcile_plans` each used to compute inline: keep a cell's surrounding
    whitespace so a rewritten value doesn't reflow the table's alignment."""

    def test_preserves_leading_and_trailing_padding(self):
        self.assertEqual(pad_cell(" NOT_STARTED ", "COMPLETE"), " COMPLETE ")

    def test_preserves_padding_wider_than_the_new_value(self):
        self.assertEqual(pad_cell("   OLD   ", "X"), "   X   ")

    def test_no_trailing_whitespace_yields_no_trailing_whitespace(self):
        # trailing == 0 is a distinct branch in the implementation, taken when
        # the old cell sits at the row's raw edge segment with the closing
        # pipe immediately after it.
        self.assertEqual(pad_cell(" OLD", "NEW"), " NEW")

    def test_no_leading_whitespace_yields_no_leading_whitespace(self):
        self.assertEqual(pad_cell("OLD ", "NEW"), "NEW ")

    def test_empty_old_cell_produces_bare_value(self):
        self.assertEqual(pad_cell("", "NEW"), "NEW")

    def test_all_whitespace_old_cell_is_split_between_leading_and_trailing(self):
        # An all-whitespace old cell must not double-count or drop padding:
        # lstrip and rstrip both consume the whole string, so leading and
        # trailing both equal its full length.
        self.assertEqual(pad_cell("    ", "X"), "    X    ")

    def test_new_value_wider_than_old_padding_still_keeps_both_sides(self):
        self.assertEqual(pad_cell(" a ", "MUCH_LONGER_VALUE"), " MUCH_LONGER_VALUE ")


if __name__ == "__main__":
    unittest.main()
