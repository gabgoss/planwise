#!/usr/bin/env python3
"""Unit tests for score_backlog.py's index write-back under escaped pipes.

`write_scores_to_index` hand-rolls its own parse of each row so it can rebuild
the line in place. Under the old naive `line.split("|")` an escaped pipe in the
Feature cell shifted every segment right by one, with two consequences that a
clean-input-only test could never surface:

  - the COMPLETE/CLOSED guard read the Priority cell, so it never fired and a
    closed item was scored as if open;
  - the write itself landed on the Abbrev cell, replacing `DOC` with the score.

The row was also dropped by the shared reader, so the item silently vanished
from every prioritisation pass while the headline count still looked complete.

These tests run the write-back against both a clean row and an escaped row and
assert the two produce the same column assignment — demonstrably correct, not
merely different.

Run with:  python -m pytest tests/test_score_backlog.py -q
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from markdown_parser import split_row_cells  # noqa: E402
from score_backlog import parse_index_table, write_scores_to_index  # noqa: E402


HEADER_WITH_SCORE = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)
HEADER_WITHOUT_SCORE = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Files |\n"
    "|-----|---------|----------|--------|--------|-------|\n"
)

ESCAPED_FEATURE = r"Run `git diff --name-only \| grep dir` first"
PLAIN_FEATURE = "Run a diff and grep it first"


def _row_cells(content: str, item_id: str) -> list[str]:
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_row_cells(stripped)
        if cells and cells[0] == item_id:
            return cells
    raise AssertionError(f"row {item_id} not found")


class TestWriteBackWithScoreColumn(unittest.TestCase):
    def _index(self, feature: str, status: str = "NOT_STARTED") -> str:
        return (
            HEADER_WITH_SCORE
            + f"| 062 | {feature} | High | {status} | DOC | - | [01](BB-062.md) |\n"
        )

    def test_score_lands_in_score_column_not_abbrev(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45})
        cells = _row_cells(out, "062")

        self.assertEqual(cells[2], "High")            # Priority intact
        self.assertEqual(cells[3], "NOT_STARTED")     # Status intact
        self.assertEqual(cells[4], "DOC")             # Abbrev NOT clobbered
        self.assertEqual(cells[5], "45")              # Score written here
        self.assertEqual(cells[6], "[01](BB-062.md)")

    def test_escaped_and_clean_rows_agree_column_for_column(self):
        escaped = _row_cells(
            write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45}), "062"
        )
        clean = _row_cells(
            write_scores_to_index(self._index(PLAIN_FEATURE), {"062": 45}), "062"
        )
        for idx in (0, 2, 3, 4, 5, 6):
            self.assertEqual(clean[idx], escaped[idx], f"column {idx} diverged")

    def test_closed_guard_fires_on_an_escaped_row(self):
        # The guard used to read Priority ("High"), never match COMPLETE, and
        # score a closed item as open.
        out = write_scores_to_index(
            self._index(ESCAPED_FEATURE, status="COMPLETE"), {"062": 45}
        )
        self.assertEqual(_row_cells(out, "062")[5], "-")

    def test_escaping_survives_the_write_verbatim(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45})
        self.assertIn(r"\|", out)
        self.assertEqual(
            _row_cells(out, "062")[1], "Run `git diff --name-only | grep dir` first"
        )

    def test_row_is_not_dropped_by_the_reader(self):
        items = parse_index_table(self._index(ESCAPED_FEATURE))
        self.assertEqual([i["id"] for i in items], ["062"])
        self.assertEqual(items[0]["status"], "NOT_STARTED")
        self.assertEqual(items[0]["abbrev"], "DOC")

    def test_sibling_rows_unaffected(self):
        content = (
            HEADER_WITH_SCORE
            + "| 061 | Before | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
            + f"| 062 | {ESCAPED_FEATURE} | High | NOT_STARTED | DOC | - | [01](b.md) |\n"
            + "| 063 | After | Low | NOT_STARTED | DOC | - | [01](c.md) |\n"
        )
        out = write_scores_to_index(content, {"061": 10, "062": 45, "063": 20})

        self.assertEqual(_row_cells(out, "061")[5], "10")
        self.assertEqual(_row_cells(out, "062")[5], "45")
        self.assertEqual(_row_cells(out, "063")[5], "20")
        for item_id in ("061", "062", "063"):
            self.assertEqual(_row_cells(out, item_id)[4], "DOC")


class TestWriteBackInsertingScoreColumn(unittest.TestCase):
    """The 6-column index gets a Score column inserted before Files."""

    def _index(self, feature: str) -> str:
        return (
            HEADER_WITHOUT_SCORE
            + f"| 062 | {feature} | High | NOT_STARTED | DOC | [01](BB-062.md) |\n"
        )

    def test_insert_keeps_columns_aligned_on_an_escaped_row(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45})
        cells = _row_cells(out, "062")

        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[2], "High")
        self.assertEqual(cells[3], "NOT_STARTED")
        self.assertEqual(cells[4], "DOC")
        self.assertEqual(cells[5], "45")
        self.assertEqual(cells[6], "[01](BB-062.md)")

    def test_header_and_separator_gain_the_column(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45})
        header = next(
            line for line in out.split("\n") if line.strip().startswith("| ID")
        )
        self.assertIn("Score", header)
        self.assertEqual(len(split_row_cells(header)), 7)

    def test_escaped_and_clean_rows_agree_after_insert(self):
        escaped = _row_cells(
            write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": 45}), "062"
        )
        clean = _row_cells(
            write_scores_to_index(self._index(PLAIN_FEATURE), {"062": 45}), "062"
        )
        for idx in (0, 2, 3, 4, 5, 6):
            self.assertEqual(clean[idx], escaped[idx], f"column {idx} diverged")


if __name__ == "__main__":
    unittest.main()
