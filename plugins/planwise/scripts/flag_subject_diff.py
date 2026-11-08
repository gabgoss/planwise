#!/usr/bin/env python3
"""Match each carried-forward flag to a destination row by subject, not by id.

A sprint plan's ``## Carried-Forward Coordination Flags`` section records the
flags it routes to later sessions. Each consuming session's orchestration file
should carry every flag addressed to it under ``## Pre-Known Cross-Task
Coordination Flags``. Flag ids are sender-scoped and collide freely, so an id
match is not an arrival check. This script compares the subject text instead.

Usage::

    python -B flag_subject_diff.py --sprint-plan <plan.md> \\
        --orchestration <orchestration.md> --session <session id>

Method:

* Carried rows are the table rows inside the sprint plan's Carried-Forward
  section whose consuming-session column (a header cell containing
  "consum") names ``--session`` as a whole token, case-insensitively.
* A row's subject is the cell under a header named "Subject", "Observation"
  or "Topic". A table with none of those headers takes the first cell after
  the id cell.
* Subjects are compared after case folding and whitespace collapsing. A
  carried row matches when some destination row carries the same subject.

Exit codes: 0 every carried row matched, 1 unmatched rows listed, 2 an input
section is missing or a file cannot be read.

What this check cannot see: a destination row whose subject was reworded
reads as unmatched (the safe direction, a human confirms it). A table whose
consuming-session column is absent contributes no carried rows, and the
script prints how many such tables it skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from dispatch_preflight import unfenced
from markdown_parser import split_row_cells

CARRIED_HEADING = "carried-forward coordination flags"
DESTINATION_HEADING = "pre-known cross-task coordination flags"
SUBJECT_HEADERS = ("subject", "observation", "topic")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?\Z")
_SPACE_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Fold case and collapse every whitespace run to one space."""
    return _SPACE_RE.sub(" ", text).strip().casefold()


def names_session(cell: str, session: str) -> bool:
    """True when ``session`` appears in ``cell`` as a whole token.

    A prefix such as ``ABC-`` may precede it. A word character or a dash and a
    digit may not follow it, so ``AB-1`` never selects ``AB-10`` or ``AB-1-02``.
    """
    pattern = r"(?<!\w)" + re.escape(normalise(session)) + r"(?!\w|-\d)"
    return re.search(pattern, normalise(cell)) is not None


def section_lines(text: str, heading: str) -> list[str] | None:
    """Return the lines under the first heading whose text contains ``heading``.

    The section ends at the next heading of the same or a higher level, so
    nested subsections stay inside it. Fenced code is dropped before the
    heading search, so a heading inside a fence is never found. ``None`` means
    the heading is absent.
    """
    lines = unfenced(text.splitlines())
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and heading in normalise(m.group(2)):
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return None
    out: list[str] = []
    for line in lines[start:]:
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return out


def tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """Group consecutive table lines into ``(header cells, body rows)`` pairs."""
    found = []
    block: list[str] = []
    for line in lines + [""]:
        if line.lstrip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 2:
            header = split_row_cells(block[0])
            rows = [split_row_cells(row) for row in block[1:]]
            rows = [r for r in rows if not all(_SEPARATOR_CELL_RE.match(c) for c in r if c)]
            found.append((header, rows))
        block = []
    return found


def subject_index(header: list[str]) -> int:
    """Index of the subject column: a named header, else the cell after the id."""
    for i, cell in enumerate(header):
        if normalise(cell) in SUBJECT_HEADERS:
            return i
    return 1


def carried_rows(lines: list[str], session: str) -> tuple[list[tuple[str, str]], int]:
    """Return ``([(id, subject)], skipped table count)`` for one session."""
    rows: list[tuple[str, str]] = []
    skipped = 0
    for header, body in tables(lines):
        consumer = next((i for i, c in enumerate(header) if "consum" in normalise(c)), None)
        if consumer is None:
            skipped += 1
            continue
        subj = subject_index(header)
        for cells in body:
            if len(cells) <= max(consumer, subj):
                continue
            if names_session(cells[consumer], session):
                rows.append((cells[0], cells[subj]))
    return rows, skipped


def destination_subjects(lines: list[str]) -> list[str]:
    """Every destination row's normalised subject."""
    subjects = []
    for header, body in tables(lines):
        subj = subject_index(header)
        subjects.extend(normalise(cells[subj]) for cells in body if len(cells) > subj)
    return subjects


def unmatched(carried: list[tuple[str, str]], destination: list[str]) -> list[tuple[str, str]]:
    """Carried rows whose normalised subject no destination row carries."""
    present = set(destination)
    return [(fid, subj) for fid, subj in carried if normalise(subj) not in present]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sprint-plan", required=True, type=Path)
    parser.add_argument("--orchestration", required=True, type=Path)
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a console code page cannot crash the verdict

    try:
        plan_text = args.sprint_plan.read_text(encoding="utf-8")
        orch_text = args.orchestration.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}")
        return 2
    plan_lines = section_lines(plan_text, CARRIED_HEADING)
    if plan_lines is None:
        print(f"error: no '## Carried-Forward Coordination Flags' heading in {args.sprint_plan}")
        return 2
    orch_lines = section_lines(orch_text, DESTINATION_HEADING)
    if orch_lines is None:
        print(f"error: no '## Pre-Known Cross-Task Coordination Flags' heading in {args.orchestration}")
        return 2

    carried, skipped = carried_rows(plan_lines, args.session)
    destination = destination_subjects(orch_lines)
    print(f"carried rows for session {args.session}: {len(carried)}")
    print(f"destination rows: {len(destination)}")
    print(f"carried tables skipped (no consuming-session column): {skipped}")
    missing = unmatched(carried, destination)
    if not missing:
        print("all carried rows matched by subject")
        return 0
    print(f"unmatched carried rows: {len(missing)}")
    for fid, subj in missing:
        print(f"  {fid}: {subj}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
