#!/usr/bin/env python3
"""Match each carried-forward flag to a destination row by subject, not by id.

A sprint plan's ``## Carried-Forward Coordination Flags`` section records the
flags it routes to later sessions. Each consuming session's orchestration file
should carry every flag addressed to it under ``## Pre-Known Cross-Task
Coordination Flags``, and each task file should carry the flags that name it
under its own section of that title. Flag ids are sender-scoped and collide
freely, so an id match is not an arrival check. This script compares the
subject text instead, across both hops.

Usage::

    python -B flag_subject_diff.py --sprint-plan <plan.md> \\
        --orchestration <orchestration.md> --session <session id>

Method:

* Carried rows are the table rows inside the sprint plan's Carried-Forward
  section whose consuming-session column (a header cell containing
  "consum") names ``--session`` as a whole token, case-insensitively. A full
  session id ``{Abbrev}-S{XX}-{YY}`` also selects a cell that writes the short
  form ``S{XX}-{YY}``, because a table commonly writes the short form.
* A row's subject is the cell under a header named "Subject", "Observation"
  or "Topic". A table with none of those headers takes the first cell after
  the id cell.
* Subjects are compared after case folding and whitespace collapsing. A
  carried row matches when some destination row carries the same subject.
  A row that misses the subject but is named by its sender is a reworded hit:
  it counts as routed, prints in its own block for a human to confirm, and
  never changes the exit code. In the first hop the carried row and a
  destination row must carry the same id and the same source (a header cell
  containing "source"). In the second hop the task file must carry the
  back-reference ``Flag {id} from {source}`` that the task-file template writes
  as each bullet's lead. The pair is sender-qualified, so this is not the
  id-alone match that sender-scoped ids rule out. A table with no source column
  gets subject-only matching.
* The plan's Carried-Forward section and the orchestration's Pre-Known section
  are optional. Each is an empty source when its heading is absent: the script
  prints a ``note:`` line and the rows of that source count as zero. A task
  file is searched whole, so it needs no particular heading.
* Second hop: every sibling task file of the orchestration (a file named
  ``{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md``) is checked against the
  orchestration's own Pre-Known rows. A row names a task when its consuming
  cell holds the full task id as a whole token, or reads ``Task 3`` or
  ``Task 03``. The row is routed when its subject appears anywhere in the task
  file, a substring test, so a flag counts whether the file writes it as a
  bullet, a note or a gate. Rows that name no task are listed for hand routing
  and never change the exit code.

Exit codes: 0 every carried row matched and every named task carries its
flags, 1 a miss in either hop, 2 a file cannot be read.

What this check cannot see: a destination row whose subject was reworded and
which also drops the ``Flag {id} from {source}`` reference reads as unmatched
(the safe direction, a human confirms it). In a task file the loose direction
also holds: a subject or reference mentioned for another reason, such as in an
example or a comment, counts as routed. A table whose
consuming-session column is absent contributes no carried rows, and the
script prints how many such tables it skipped. When no row names the session
but a table with a consuming-session column holds rows, the script prints a
``warning:`` line in place of the all-matched line, because the table may write
the session id in a form it cannot read. The exit code stays 0, since a session
with no carried rows is common. A consuming cell that lists
several tasks as one number run (``Tasks 01, 03``) names only the first, so
write one ``Task NN`` per task or a full task id.
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
# A full session id {Abbrev}-S{XX}-{YY}; group 1 is the short form S{XX}-{YY}.
_SHORT_SESSION_RE = re.compile(r"^[a-z0-9]+-(s\d{2}-\d{2})\Z")
# {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md, per templates/task-file.md.
_TASK_FILE_RE = re.compile(
    r"^([A-Za-z0-9]+-S\d{2}-\d{2}-(\d{2}))-(?:Haiku|Sonnet|Opus)-[^/\\]+\.md\Z"
)


def normalise(text: str) -> str:
    """Fold case and collapse every whitespace run to one space."""
    return _SPACE_RE.sub(" ", text).strip().casefold()


def names_session(cell: str, session: str) -> bool:
    """True when ``session`` appears in ``cell`` as a whole token.

    A prefix such as ``ABC-`` may precede it. A word character or a dash and a
    digit may not follow it, so ``AB-1`` never selects ``AB-10`` or ``AB-1-02``.
    A full session id of the shape ``{Abbrev}-S{XX}-{YY}`` also matches its short
    form ``S{XX}-{YY}`` when no word character or dash precedes it, so
    ``S06-02`` names ``RFH-S06-02`` while ``XYZ-S06-02`` does not.
    """
    wanted = normalise(session)
    cell_text = normalise(cell)
    pattern = r"(?<!\w)" + re.escape(wanted) + r"(?!\w|-\d)"
    if re.search(pattern, cell_text) is not None:
        return True
    short = _SHORT_SESSION_RE.match(wanted)
    if short is None:
        return False
    short_pattern = r"(?<![\w-])" + re.escape(short.group(1)) + r"(?!\w|-\d)"
    return re.search(short_pattern, cell_text) is not None


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


def source_index(header: list[str]) -> int | None:
    """Index of the sender column (a header cell containing "source"), else ``None``."""
    return next((i for i, c in enumerate(header) if "source" in normalise(c)), None)


def _source_cell(cells: list[str], index: int | None) -> str | None:
    """The normalised sender cell, or ``None`` when there is no column or the cell is empty."""
    if index is None or index >= len(cells):
        return None
    return normalise(cells[index]) or None


def carried_rows(lines: list[str], session: str) -> tuple[list[tuple[str, str, str | None]], int]:
    """Return ``([(id, subject, source)], skipped table count)`` for one session.

    ``source`` is the normalised sender cell, or ``None`` for a table with no
    source column.
    """
    rows: list[tuple[str, str, str | None]] = []
    skipped = 0
    for header, body in tables(lines):
        consumer = next((i for i, c in enumerate(header) if "consum" in normalise(c)), None)
        if consumer is None:
            skipped += 1
            continue
        subj = subject_index(header)
        src = source_index(header)
        for cells in body:
            if len(cells) <= max(consumer, subj):
                continue
            if names_session(cells[consumer], session):
                rows.append((cells[0], cells[subj], _source_cell(cells, src)))
    return rows, skipped


def carried_table_rows(lines: list[str]) -> int:
    """Count the body rows of every table that has a consuming-session column."""
    total = 0
    for header, body in tables(lines):
        if any("consum" in normalise(c) for c in header):
            total += len(body)
    return total


def destination_rows(lines: list[str]) -> list[tuple[str, str | None, str]]:
    """Every destination row as ``(normalised id, normalised source or None, normalised subject)``."""
    rows = []
    for header, body in tables(lines):
        subj = subject_index(header)
        src = source_index(header)
        rows.extend(
            (normalise(cells[0]), _source_cell(cells, src), normalise(cells[subj]))
            for cells in body
            if len(cells) > subj
        )
    return rows


def classify_carried(
    carried: list[tuple[str, str, str | None]], destination: list[tuple[str, str | None, str]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split carried rows into ``(reworded, missing)``.

    A row whose normalised subject some destination row carries is matched and
    appears in neither list. A row that misses the subject but has a destination
    row with the same id and the same non-empty source is reworded. Any other row
    is missing. A table with no source column gives subject-only matching.
    """
    present = {subj for _, _, subj in destination}
    pairs = {(fid, src) for fid, src, _ in destination if src is not None}
    reworded: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    for fid, subj, src in carried:
        if normalise(subj) in present:
            continue
        if src is not None and (normalise(fid), src) in pairs:
            reworded.append((fid, subj))
        else:
            missing.append((fid, subj))
    return reworded, missing


def _optional_section(text: str, heading: str, title: str, source: Path) -> list[str]:
    """Lines of an optional section; an absent heading prints a note and is empty."""
    lines = section_lines(text, heading)
    if lines is None:
        print(f"note: no '## {title}' heading in {source}; treated as an empty source")
        return []
    return lines


def task_files(orchestration: Path) -> list[tuple[str, int, Path]]:
    """Sibling task files of the orchestration as ``(task id, ordinal, path)``."""
    found = []
    for path in sorted(orchestration.parent.iterdir()):
        m = _TASK_FILE_RE.match(path.name)
        if m and path.is_file():
            found.append((m.group(1), int(m.group(2)), path))
    return found


def task_rows(orch_lines: list[str]) -> list[tuple[str, str, str, str | None]]:
    """Every Pre-Known row with a consuming cell, as ``(id, subject, consumer, source)``."""
    rows: list[tuple[str, str, str, str | None]] = []
    for header, body in tables(orch_lines):
        consumer = next((i for i, c in enumerate(header) if "consum" in normalise(c)), None)
        if consumer is None:
            continue
        subj = subject_index(header)
        src = source_index(header)
        for cells in body:
            if len(cells) > max(consumer, subj):
                rows.append((cells[0], cells[subj], cells[consumer], _source_cell(cells, src)))
    return rows


def names_task(cell: str, task_id: str, ordinal: int) -> bool:
    """True when ``cell`` holds the full task id as a token, or ``Task N``."""
    if names_session(cell, task_id):
        return True
    pattern = rf"(?<!\w)tasks?\s*#?0*{ordinal}(?!\w)"
    return re.search(pattern, normalise(cell)) is not None


def names_reference(task_text: str, flag_id: str, source: str) -> bool:
    """True when the task text holds the back-reference ``Flag {id} from {source}``.

    Both operands are normalised and matched as whole tokens, so ``Flag 1 from
    up-01`` never selects ``Flag 11 from up-01`` or ``Flag 1 from up-010``.
    """
    fid = re.escape(normalise(flag_id))
    pattern = rf"(?<!\w)flag\s*#?\s*{fid}\s+from\s+{re.escape(source)}(?!\w|-\d)"
    return re.search(pattern, task_text) is not None


def unrouted(
    rows: list[tuple[str, str, str, str | None]], task_text: str, task_id: str, ordinal: int
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Split the rows naming the task into ``(reworded, missing)``.

    A row whose subject the task file carries is routed and appears in neither
    list. A row that misses the subject but whose source cell gives a
    ``Flag {id} from {source}`` reference in the task file is reworded. Any
    other row is missing.
    """
    reworded: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    for fid, subj, consumer, src in rows:
        if not names_task(consumer, task_id, ordinal):
            continue
        if normalise(subj) and normalise(subj) in task_text:
            continue
        if src is not None and names_reference(task_text, fid, src):
            reworded.append((fid, subj))
        else:
            missing.append((fid, subj))
    return reworded, missing


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
    plan_lines = _optional_section(plan_text, CARRIED_HEADING, "Carried-Forward Coordination Flags", args.sprint_plan)
    orch_lines = _optional_section(orch_text, DESTINATION_HEADING, "Pre-Known Cross-Task Coordination Flags", args.orchestration)

    carried, skipped = carried_rows(plan_lines, args.session)
    destination = destination_rows(orch_lines)
    print(f"carried rows for session {args.session}: {len(carried)}")
    print(f"destination rows: {len(destination)}")
    print(f"carried tables skipped (no consuming-session column): {skipped}")
    status = 0
    reworded, missing = classify_carried(carried, destination)
    table_rows = carried_table_rows(plan_lines)
    if not carried and table_rows:
        print(
            f"warning: 0 of {table_rows} carried rows name session {args.session}; "
            "if the table writes the session id in another form, this check could "
            "not see them -- diff by hand"
        )
    elif not missing:
        print("all carried rows matched by subject" if not reworded else "all carried rows matched")
    else:
        status = 1
        print(f"unmatched carried rows: {len(missing)}")
        for fid, subj in missing:
            print(f"  {fid}: {subj}")
    print(f"carried rows matched by reference, subject reworded (confirm by hand): {len(reworded)}")
    for fid, subj in reworded:
        print(f"  {fid}: {subj}")

    tasks = task_files(args.orchestration)
    print(f"task files: {len(tasks)}")
    if not tasks:
        return status
    rows = task_rows(orch_lines)
    nameless = [
        (fid, subj)
        for fid, subj, consumer, _ in rows
        if not any(names_task(consumer, tid, n) for tid, n, _ in tasks)
    ]
    print(f"rows naming no task (route by hand): {len(nameless)}")
    for fid, subj in nameless:
        print(f"  {fid}: {subj}")
    misses: list[tuple[str, str, str]] = []
    rewordings: list[tuple[str, str, str]] = []
    for tid, n, path in tasks:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: {exc}")
            return 2
        task_text = normalise(text)
        task_reworded, task_missing = unrouted(rows, task_text, tid, n)
        rewordings.extend((tid, fid, subj) for fid, subj in task_reworded)
        misses.extend((tid, fid, subj) for fid, subj in task_missing)
    print(f"unrouted task flags: {len(misses)}")
    for tid, fid, subj in misses:
        print(f"  {tid}: {fid}: {subj}")
    print(f"task flags routed by reference, subject reworded (confirm by hand): {len(rewordings)}")
    for tid, fid, subj in rewordings:
        print(f"  {tid}: {fid}: {subj}")
    return 1 if misses else status


if __name__ == "__main__":
    sys.exit(main())
