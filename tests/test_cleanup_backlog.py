#!/usr/bin/env python3
"""Unit tests for cleanup_backlog.py's status read under escaped pipes.

`cleanup_index` removes COMPLETE/CLOSED rows by reading cell 3 as the Status.
Under the old naive `line.split("|")` an escaped pipe in the Feature cell put
the Priority there instead. Priority is never COMPLETE or CLOSED, so this path
failed safe — the closed row simply survived every cleanup pass forever rather
than being deleted wrongly. It is still a defect: the row is unreachable by the
tool that exists to remove it.

These tests pin both directions — a closed escaped row is now removed, and an
open escaped row is still kept.

Run with:  python -m pytest tests/test_cleanup_backlog.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from cleanup_backlog import cleanup_index  # noqa: E402
from markdown_parser import split_row_cells  # noqa: E402


INDEX_HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)
ESCAPED_FEATURE = r"Run `git diff --name-only \| grep dir` first"


class TestCleanupWithEscapedPipes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cleanup_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.index_path = self.tmp / "00-Index-Backlog.md"

    def write_index(self, rows: str) -> Path:
        self.index_path.write_text(INDEX_HEADER + rows, encoding="utf-8")
        return self.index_path

    def ids_remaining(self) -> list[str]:
        ids = []
        for line in self.index_path.read_text(encoding="utf-8").split("\n"):
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = split_row_cells(stripped)
            if cells and cells[0] not in ("ID", "") and not set(cells[0]) <= {"-"}:
                ids.append(cells[0])
        return ids

    def test_closed_escaped_row_is_removed(self):
        self.write_index(
            f"| 062 | {ESCAPED_FEATURE} | High | COMPLETE | DOC | - | [01](a.md) |\n"
            "| 063 | Plain open | Low | NOT_STARTED | DOC | 10 | [01](b.md) |\n"
        )

        removed = cleanup_index(self.index_path)

        self.assertEqual(removed, 1)
        self.assertEqual(self.ids_remaining(), ["063"])

    def test_open_escaped_row_is_kept(self):
        self.write_index(
            f"| 062 | {ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 | [01](a.md) |\n"
            "| 063 | Plain closed | Low | CLOSED | DOC | - | [01](b.md) |\n"
        )

        removed = cleanup_index(self.index_path)

        self.assertEqual(removed, 1)
        self.assertEqual(self.ids_remaining(), ["062"])

    def test_kept_escaped_row_survives_verbatim(self):
        self.write_index(
            f"| 062 | {ESCAPED_FEATURE} | High | NOT_STARTED | DOC | 45 | [01](a.md) |\n"
            "| 063 | Plain closed | Low | CLOSED | DOC | - | [01](b.md) |\n"
        )

        cleanup_index(self.index_path)

        text = self.index_path.read_text(encoding="utf-8")
        self.assertIn(r"\|", text)
        row = next(
            split_row_cells(line)
            for line in text.split("\n")
            if line.strip().startswith("| 062")
        )
        self.assertEqual(row[1], "Run `git diff --name-only | grep dir` first")
        self.assertEqual(row[3], "NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
