#!/usr/bin/env python3
"""Resolve the session that runs after the one closing out, across sprints.

`/planwise run` closeout (Step 4.1) calls this once, before Step 4.3 marks
the current session COMPLETE. The script reads the nearest Master Plan's
`## Session Completion Tracking` table, treats the closing session as
complete, and picks the first later row whose status is not COMPLETE. It
then maps that row to its orchestration file on disk, so the run can end
with a copy-ready command even when the next session sits in the next
sprint.

This script is non-mutating: it reads files and prints one outcome line.

Usage (placeholder forms only):
    python resolve_next_session.py --config {planwise_root}/config.yaml \\
        --orchestration {session-folder}/{Abbrev}-S{XX}-{YY}-Orchestration.md

Output: exactly one of these lines.
    NEXT: /planwise:planwise run @{project-relative orchestration path}
    NEXT_UNSCAFFOLDED: {Sprint cell} {Session cell}
    NEXT: none
When the tracking table or the Master Plan is absent, a `Coverage:` line
follows and names the fallback used. Session order then comes from the
orchestration file names, and status from each orchestration's `Status:`.

Exit code: always 0. The outcome line carries the result.
"""

import argparse
import re
import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from check_prior_sprint_outputs import _parse_tracking_table
from config_loader import load_config

_ORCH_RE = re.compile(r"-S(\d+)-(\d+)-Orchestration\.md$")
_SPRINT_CELL_RE = re.compile(r"Sprint-(\d+)|\bS(\d+)\b")
_SESSION_CELL_RE = re.compile(r"Session-(\d+)|\bS\d+-(\d+)\b")
_STATUS_LINE_RE = re.compile(r"^\**Status:?\**:?\s*(.+)$", re.MULTILINE)

RUN_PREFIX = "/planwise:planwise run @"


def is_complete(status: str) -> bool:
    """True when a status cell or line reads COMPLETE (with any suffix)."""
    lower = status.lower()
    if "incomplete" in lower or "not complete" in lower:
        return False
    return "complete" in lower


def _first_int(match: re.Match | None) -> int | None:
    if match is None:
        return None
    for group in match.groups():
        if group is not None:
            return int(group)
    return None


def session_key(sprint_cell: str, session_cell: str) -> tuple[int, int] | None:
    """Return (sprint, session) numbers from a tracking-table row, or None."""
    sprint = _first_int(_SPRINT_CELL_RE.search(sprint_cell))
    session = _first_int(_SESSION_CELL_RE.search(session_cell))
    if sprint is None or session is None:
        return None
    return sprint, session


def find_master_plan(orchestration: Path) -> Path | None:
    """Return the Master Plan in the nearest ancestor folder that holds one."""
    for folder in orchestration.parents:
        plans = sorted(folder.glob("*-Master-Plan.md"))
        if plans:
            return plans[0]
    return None


def scan_orchestrations(plan_dir: Path) -> dict[tuple[int, int], Path]:
    """Map (sprint, session) to each orchestration file under plan_dir."""
    found: dict[tuple[int, int], Path] = {}
    for path in sorted(plan_dir.glob("Sprint-*/Session-*/*-Orchestration.md")):
        match = _ORCH_RE.search(path.name)
        if match:
            found[(int(match.group(1)), int(match.group(2)))] = path
    return found


def _orchestration_status(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _STATUS_LINE_RE.search(text)
    return match.group(1).strip() if match else ""


def display_path(path: Path, project_root: Path) -> str:
    """Project-relative path with forward slashes, or absolute when outside."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve(orchestration: Path, project_root: Path) -> list[str]:
    """Return the output lines: one outcome line, plus any coverage line."""
    match = _ORCH_RE.search(orchestration.name)
    if match is None or not orchestration.is_file():
        return [
            "NEXT: none",
            (
                f"Coverage: {orchestration.as_posix()} is not an existing "
                "*-S{XX}-{YY}-Orchestration.md file; nothing resolved."
            ),
        ]
    current = (int(match.group(1)), int(match.group(2)))

    master_plan = find_master_plan(orchestration)
    plan_dir = master_plan.parent if master_plan else orchestration.parent.parent.parent
    on_disk = scan_orchestrations(plan_dir)
    rows = None
    if master_plan is not None:
        rows = _parse_tracking_table(
            master_plan.read_text(encoding="utf-8", errors="replace")
        )

    coverage: list[str] = []
    if rows is not None:
        keyed = []
        for cells in rows:
            if len(cells) < 3:
                continue
            key = session_key(cells[0], cells[1])
            if key is not None:
                keyed.append((key, cells[0].strip(), cells[1].strip(), cells[2]))
        positions = [i for i, row in enumerate(keyed) if row[0] == current]
        if positions:
            later = keyed[positions[0] + 1:]
        else:
            later = [row for row in keyed if row[0] > current]
        candidates = [
            (key, f"{sprint} {session}")
            for key, sprint, session, status in later
            if not is_complete(status)
        ]
    else:
        reason = "no Master Plan" if master_plan is None else (
            f"no Session Completion Tracking table in {master_plan.name}"
        )
        coverage.append(
            f"Coverage: {reason}; sessions ordered by orchestration file name, "
            "status read from each orchestration's Status: line."
        )
        candidates = [
            (key, f"Sprint-{key[0]:02d} Session-{key[1]:02d}")
            for key in sorted(on_disk)
            if key > current and not is_complete(_orchestration_status(on_disk[key]))
        ]

    if not candidates:
        return ["NEXT: none", *coverage]
    key, label = candidates[0]
    path = on_disk.get(key)
    if path is None:
        return [f"NEXT_UNSCAFFOLDED: {label}", *coverage]
    return [f"NEXT: {RUN_PREFIX}{display_path(path, project_root)}", *coverage]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the run command for the session after the one "
        "closing out, resolved across sprint boundaries. Never writes."
    )
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument(
        "--orchestration",
        required=True,
        help="The closing session's *-Orchestration.md file",
    )
    args = parser.parse_args()

    config = load_config(Path(__file__))
    project_root: Path = config["_project_root"]

    orchestration = Path(args.orchestration)
    if not orchestration.is_absolute() and not orchestration.exists():
        orchestration = project_root / orchestration
    for line in resolve(orchestration.resolve(), project_root):
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
