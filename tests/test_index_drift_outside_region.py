#!/usr/bin/env python3
"""A generated index table row that sits below a heading such as `## Notes`
is outside the region the drift check walks. Each index drift check (the
backlog and the lessons `--check`) must exit non-zero and name the line when
such a row follows the heading, so the row cannot hide below it.

Two row shapes are driven per index:
  - a full-width row: a real generated row moved below `## Notes`;
  - a six-cell row: a short row (the width of the Plans index) below `## Notes`.

The fixtures reuse the existing generator test bases, so each tree is the
same isolated temp planwise tree those suites build.

Run with:  python -m pytest -q -c pytest.ini tests/test_index_drift_outside_region.py
"""

import sys
from pathlib import Path

import pytest

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import test_generate_backlog_index as tgb
import test_generate_lessons_index as tgl

SIX_CELL_ROW = "| {id} | alpha | beta | gamma | delta | epsilon |"


def _first_line_after_table(text: str) -> int:
    """1-indexed number of the first non-pipe line after the table's first
    pipe line -- the line on which the drift walk stops."""
    seen_table = False
    for number, line in enumerate(text.split("\n"), start=1):
        if line.strip().startswith("|"):
            seen_table = True
        elif seen_table:
            return number
    raise AssertionError("the table has no line after it")


def _line_number_of(text: str, needle: str) -> int:
    """1-indexed number of the first line of `text` that starts with `needle`."""
    for number, line in enumerate(text.split("\n"), start=1):
        if line.startswith(needle):
            return number
    raise AssertionError(f"no line starting with {needle!r}")


class TestBacklogDriftOutsideRegion(tgb._GeneratorFixtureBase):
    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                        status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                        status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        code, _out, _err = self.run_main("--write")
        assert code == 0, "fixture --write must succeed"
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"

    def _move_row_below_notes(self, item_id: str) -> str:
        """Cut item_id's row out of the table, append `## Notes` and the row
        at the end of the hub. Returns the moved row line."""
        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        row = next(line for line in lines if line.startswith(f"| {item_id} |"))
        lines.remove(row)
        lines.extend(["", "## Notes", "", row])
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")
        return row

    def test_full_width_row_below_notes_exits_nonzero_and_names_line_and_id(self):
        self._move_row_below_notes("002")
        text = self.hub_path.read_text(encoding="utf-8")
        stop_line = _first_line_after_table(text)

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1, out)
        self.assertIn(f"table truncated at line {stop_line} ", out)
        self.assertIn("row for id 002 may exist after the split", out)

    @pytest.mark.xfail(
        strict=True,
        reason="code-gate-15 PRODUCTION_RED: backlog --check exits 0 'No drift' for a "
        "short (six-cell) row below a heading; only a full-width row is reported",
    )
    def test_six_cell_row_below_notes_exits_nonzero_and_names_the_line(self):
        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        lines.extend(["", "## Notes", "", SIX_CELL_ROW.format(id="003")])
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")
        text = self.hub_path.read_text(encoding="utf-8")
        row_line = _line_number_of(text, "| 003 |")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1, out)
        self.assertRegex(out, rf"(?<![\d.]){row_line}(?![\d.])")


class TestLessonsDriftOutsideRegion(tgl._GenerateLessonsIndexFixtureBase):
    def setUp(self):
        super().setUp()
        self.write_lesson(1, status="documented")
        self.write_lesson(2, status="documented")
        code, _out, _err = self.run_main("--write")
        assert code == 0, "fixture --write must succeed"
        self.hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"

    def _move_row_below_notes(self) -> int:
        """Cut LL-002's row out of the table and append `## Notes` plus the
        row at the end. Returns the 1-indexed line the row now sits on."""
        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        row = next(line for line in lines if line.startswith("| LL-002 |"))
        lines.remove(row)
        lines.extend(["", "## Notes", "", row])
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))
        return _line_number_of(self.hub_path.read_text(encoding="utf-8"), "| LL-002 |")

    def _append_six_cell_row_below_notes(self) -> int:
        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        lines.extend(["", "## Notes", "", SIX_CELL_ROW.format(id="LL-003")])
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))
        return _line_number_of(self.hub_path.read_text(encoding="utf-8"), "| LL-003 |")

    def test_full_width_row_below_notes_exits_nonzero_and_names_the_id(self):
        self._move_row_below_notes()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1, out)
        self.assertIn("[missing-row] LL-002", out)

    @pytest.mark.xfail(
        strict=True,
        reason="code-gate-15 PRODUCTION_RED: lessons --check names the id of a full-width "
        "row below a heading but never names its line or the line the walk stopped on",
    )
    def test_full_width_row_below_notes_names_the_line(self):
        row_line = self._move_row_below_notes()

        _code, out, _err = self.run_main("--check")

        self.assertRegex(out, rf"(?<![\d.]){row_line}(?![\d.])")

    def test_six_cell_row_below_notes_exits_nonzero(self):
        self._append_six_cell_row_below_notes()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1, out)
        self.assertIn("[stale-wrapper]", out)

    @pytest.mark.xfail(
        strict=True,
        reason="code-gate-15 PRODUCTION_RED: lessons --check reports a six-cell row below "
        "a heading only as a file-level stale-wrapper, with no line number",
    )
    def test_six_cell_row_below_notes_names_the_line(self):
        row_line = self._append_six_cell_row_below_notes()

        _code, out, _err = self.run_main("--check")

        self.assertRegex(out, rf"(?<![\d.]){row_line}(?![\d.])")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
