#!/usr/bin/env python3
"""Promote-batch Phases 1-2 write no lesson file under --dry-run.

The lessons handler says a promote-batch dry run "short-circuits after Phase 2
and writes nothing", and it names Part 1 section 1 as the authoritative write
scope. Phase 1 still runs under --dry-run, so every lesson-write instruction
from the Phase 1 heading onward must carry its own --dry-run clause, and the
section 1 Write cell for the lesson files must name the Phase 1 write and its
dry-run guard.

Dev-only: lives in tests/, which does not ship.

Run with:  python -m pytest tests/test_promote_batch_dry_run_writes.py -q
"""

import re
from pathlib import Path

PART_1 = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "planwise"
    / "references"
    / "lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md"
)
PHASE_1_HEADING = "## 3. Phase 1"
LESSON_ROW_PREFIX = "| `{lessons_dir}/LL-{NNN}-*.md`"
WRITE_INSTRUCTION = re.compile(r"set `status:|write the `[a-z-]+:`")


def _lines() -> list[str]:
    return PART_1.read_text(encoding="utf-8").splitlines()


def test_every_phase_1_lesson_write_names_dry_run():
    lines = _lines()
    start = next(i for i, line in enumerate(lines) if line.startswith(PHASE_1_HEADING))
    hits = [
        (number, line)
        for number, line in enumerate(lines[start:], start=start + 1)
        if WRITE_INSTRUCTION.search(line)
    ]
    assert hits, "the Phase 1 slice must hold at least one lesson-write instruction"
    unguarded = [number for number, line in hits if "--dry-run" not in line]
    assert not unguarded, f"lesson-write lines with no --dry-run clause: {unguarded}"


def test_lesson_file_write_cell_names_phase_1_and_dry_run():
    rows = [line for line in _lines() if line.startswith(LESSON_ROW_PREFIX)]
    assert len(rows) == 1, f"section 1 must hold exactly one lesson-file row, found {len(rows)}"
    cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
    write_cell = cells[-1]
    assert "Phase 1" in write_cell, "the Write cell must name the Phase 1 write"
    assert "--dry-run" in write_cell, "the Write cell must name the --dry-run guard"
