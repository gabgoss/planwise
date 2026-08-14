#!/usr/bin/env python3
"""Flip the Status cell of lessons-index Master Table rows — safely and idempotently.

The planwise lessons workflows (`curate --phase=promote`, `promote-batch` capture)
both prescribe "update the Status column in the Master Table" as a hand edit. At
batch scale that is dozens of long table rows, each needing a unique anchor — the
exact shape where a hand edit silently rewrites the wrong row, or downgrades a row
that was already correct.

The load-bearing property is NOT the rewrite. It is the REFUSALS:

  * a row already at the target status is skipped, not rewritten;
  * a row at a landed status (`rule` / `applied`) is NEVER downgraded to `promoted`
    or `documented`, even when the caller's map says so — a landed lesson that a
    stale map wants to un-land is a caller bug, and silently obeying it destroys the
    audit trail the Rule Promotion Log depends on;
  * a mapped id with no row, or a row with no parseable Status cell, is reported
    rather than skipped in silence.

Every decision is printed. A run that changes nothing prints why for each id, so the
operator can tell "already correct" apart from "never matched".

Usage:
    flip_lesson_status.py INDEX_FILE MAP_FILE [--dry-run]

MAP_FILE is one `LL-{NNN}: status` per line; `#` comments and blank lines ignored:

    # landed upstream, verified by content grep
    LL-{NNN}: rule
    LL-{NNN+1}: promoted

Exit codes: 0 = clean; 1 = at least one id not found or unparseable (investigate
before trusting the run).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VALID = ("documented", "promoted", "rule", "applied")
LANDED = ("rule", "applied")

ROW_RE = re.compile(r"^\|\s*\*{0,2}(LL-\d{3})\*{0,2}\s*\|")
TAIL_RE = re.compile(r"\|\s*\*{0,2}(documented|promoted|rule|applied)\*{0,2}\s*\|\s*$")


def parse_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise SystemExit(f"{path}:{n}: expected 'LL-NNN: status', got {raw!r}")
        lid, status = (p.strip() for p in line.split(":", 1))
        if not re.fullmatch(r"LL-\d{3}", lid):
            raise SystemExit(f"{path}:{n}: bad lesson id {lid!r}")
        if status not in VALID:
            raise SystemExit(f"{path}:{n}: status {status!r} not in {VALID}")
        mapping[lid] = status
    return mapping


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv[1:]
    if len(args) != 2:
        raise SystemExit(__doc__)

    index, target = Path(args[0]), parse_map(Path(args[1]))
    lines = index.read_text(encoding="utf-8").split("\n")

    changed: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    unseen = set(target)

    for i, line in enumerate(lines):
        m = ROW_RE.match(line)
        if not m or m.group(1) not in target:
            continue
        lid = m.group(1)
        unseen.discard(lid)
        tail = TAIL_RE.search(line)
        if not tail:
            skipped.append((lid, "row has no parseable Status cell — check by hand"))
            continue
        current, want = tail.group(1), target[lid]
        if current == want:
            skipped.append((lid, f"already {want}"))
            continue
        if current in LANDED and want not in LANDED:
            skipped.append((lid, f"REFUSED: will not downgrade landed {current!r} -> {want!r}"))
            continue
        lines[i] = line[: tail.start()] + f"| {want} |"
        changed.append((lid, current, want))

    if not dry_run and changed:
        index.write_text("\n".join(lines), encoding="utf-8")

    print(f"{'would change' if dry_run else 'changed'}: {len(changed)}")
    for lid, a, b in changed:
        print(f"  {lid}: {a} -> {b}")
    if skipped:
        print(f"skipped: {len(skipped)}")
        for lid, why in skipped:
            print(f"  {lid}: {why}")
    if unseen:
        print(f"NOT FOUND IN MASTER TABLE: {sorted(unseen)}")

    problems = len(unseen) + sum(
        1 for _, why in skipped if why.startswith(("REFUSED", "row has no"))
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
