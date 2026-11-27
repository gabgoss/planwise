#!/usr/bin/env python3
"""Refuse to run a session whose files still hold scaffold FILL markers.

``check_session_fill.py PATH...``
    Each PATH is a session folder or a plan file. The check counts the rendered
    markers (``<!-- FILL: {name} -->``) in the sections a run cannot start
    without:

    - task file: ``## Objective``, ``## Execution Steps``, ``## Success Criteria``
    - Orchestration: ``## Session Objective``, ``## Success Criteria``

    A section ends at the next H2 outside a fence. Fence lines, fenced content,
    ``>`` lines and inline code spans are not counted, so a filled file may
    quote a marker. Each file with markers prints one ``UNFILLED:`` line, then
    ``fill_check files={m} unfilled={k}`` closes the report.

    Exit 0: no gated section holds a marker. Exit 1: a ``REFUSED:`` line names
    the sprint folder to scaffold. Exit 2: the check did not run. A PATH is
    missing, a file cannot be read, or no task file or Orchestration was found
    (``NOT CHECKED:``).

    Cannot see: a marker left inside a code span, a fence or a ``>`` line;
    sections outside the five above; Recovery, Master Plan and Sprint Plan
    files; a plan nested in a folder PATH. A file with only such leftovers passes here. The scaffold pass's own
    zero-marker gate covers partial fills.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

from scaffold_plan import (
    FILL,
    collect_plan_files,
    file_kind,
    norm_heading,
    read_lf,
)

GATED_SECTIONS = {
    "task": ("Objective", "Execution Steps", "Success Criteria"),
    "orchestration": ("Session Objective", "Success Criteria"),
}
_OPEN, _CLOSE = FILL.split("%s")
# A code span or a marker, whichever starts first. A marker that a span encloses is
# quoted text, and a marker whose own name holds a backtick is still a marker. A span
# may wrap onto a later line of its paragraph, and an escaped backtick opens none.
_SPAN_OR_MARKER_RE = re.compile(
    rf"(?<![`\\])(`+)(?!`)(?s:.+?)(?<!`)\1(?!`)|({re.escape(_OPEN)}.+?{re.escape(_CLOSE)})"
)
_FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
# A list item, a table row or a heading ends the paragraph before it.
_BLOCK_START_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||#{1,6}\s)")
_SPRINT_DIR_RE = re.compile(r"^Sprint-\d+")


def _fence(line):
    """(character, length, info) of a fence line, else None."""
    match = _FENCE_LINE_RE.match(line)
    if not match:
        return None
    run, info = match.group(1), match.group(2).strip()
    # Backticks after a backtick run make it inline code, not a fence.
    if run[0] == "`" and "`" in info:
        return None
    return run[0], len(run), info


def _fence_end(lines, start):
    """Index of the line that closes the fence opened at ``start``, or None.

    A fence with an info string, of the same character and no shorter, opens a
    level, as plan files nest them. Levels that never balance end the fence at
    its first bare closer instead.
    """
    char, length, _info = _fence(lines[start])
    levels, first_bare = [length], None
    for index in range(start + 1, len(lines)):
        fence = _fence(lines[index])
        if fence is None or fence[0] != char or fence[1] < levels[-1]:
            continue
        if fence[2]:
            levels.append(fence[1])
            continue
        if first_bare is None and fence[1] >= length:
            first_bare = index
        levels.pop()
        if not levels:
            return index
    return first_bare


def count_markers(text, sections):
    """Return {section: marker count} for the gated sections that hold markers."""
    gated = {f"## {name}": name for name in sections}
    lines = text.split("\n")
    counts, current, paragraph = {}, None, []

    def close_paragraph():
        found = sum(1 for m in _SPAN_OR_MARKER_RE.finditer("\n".join(paragraph)) if m.group(2))
        if found and current is not None:
            counts[current] = counts.get(current, 0) + found
        paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if _fence(line) is not None:
            close_paragraph()
            end = _fence_end(lines, index)
            # A fence that never closes hides nothing.
            index = index + 1 if end is None else end + 1
            continue
        if line.startswith("## "):
            close_paragraph()
            current = gated.get(norm_heading(line))
        elif not line.strip() or line.lstrip().startswith(">"):
            close_paragraph()
        else:
            if _BLOCK_START_RE.match(line):
                close_paragraph()
            paragraph.append(line)
        index += 1
    close_paragraph()
    return counts


def sprint_name(path):
    """The nearest ancestor folder named ``Sprint-NN...``, or None."""
    return next((p.name for p in path.resolve().parents if _SPRINT_DIR_RE.match(p.name)), None)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check_session_fill.py",
        description="Refuse a session whose files still hold scaffold FILL markers.",
    )
    parser.add_argument("paths", nargs="+", metavar="PATH", help="a session folder or a plan file")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        # A path the console cannot encode must not turn into a traceback that reads as a refusal.
        sys.stdout.reconfigure(errors="replace")

    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(f"ERROR: no such path: {', '.join(missing)}")
        return 2

    checked, unfilled, sprints = 0, 0, []
    for path in collect_plan_files(args.paths):
        sections = GATED_SECTIONS.get(file_kind(str(path)))
        if sections is None:
            continue
        try:
            text = read_lf(path)
        except (OSError, UnicodeError) as exc:
            print(f"ERROR: cannot read {path}: {exc}")
            return 2
        checked += 1
        counts = count_markers(text, sections)
        if not counts:
            continue
        unfilled += 1
        print(f"UNFILLED: {path}: " + " ".join(f"{name}={counts[name]}" for name in sections if name in counts))
        name = sprint_name(path) or "the sprint that holds these files"
        if name not in sprints:
            sprints.append(name)

    if not checked:
        print(f"NOT CHECKED: no task file or Orchestration under {', '.join(args.paths)}")
        return 2
    print(f"fill_check files={checked} unfilled={unfilled}")
    if not unfilled:
        return 0
    print(f"REFUSED: {unfilled} file(s) still hold FILL markers in Objective, Execution Steps or Success Criteria. "
          f"Fix: run /planwise plan --scaffold for {', '.join(sprints)} (for a plan built from bodies files, "
          f"add the missing bodies and build it again), then run the session again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
