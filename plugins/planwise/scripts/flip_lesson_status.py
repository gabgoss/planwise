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
    rather than skipped in silence;
  * an id carried by MORE THAN ONE row is refused outright — a duplicate lesson id
    means the index is already corrupt, and flipping every copy would bury the
    corruption under a clean-looking exit 0.

Every decision is printed. A run that changes nothing prints why for each id, so the
operator can tell "already correct" apart from "never matched".

Two write-discipline guarantees make the diff auditable, because the audit trail is
the whole point of the refusals above:

  * **Only the status WORD is rewritten.** The surrounding cell is spliced back
    byte-for-byte, so padding, bold markers and any trailing carriage return on that
    line survive untouched.
  * **Line endings are never translated.** Reading and writing through
    ``reconcile_common``'s newline-preserving pair keeps a CRLF file CRLF and an LF
    file LF. A plain ``read_text``/``write_text`` pair round-trips through Python's
    universal-newline translation and rewrites EVERY line to the running platform's
    ``os.linesep`` — turning a one-cell flip into a whole-file diff on the very rows
    the refusals just declined to touch.

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

# Sibling-module import. The newline-preserving read/write pair is the shared
# destructive-write discipline (see reconcile_common's module docstring); it is
# defined once there and reused by every script that rewrites a user's index in
# place, rather than re-derived per script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconcile_common import (  # noqa: E402
    read_text_preserving_newlines,
    write_text_preserving_newlines,
)

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
    argv = sys.argv[1:]
    flags = [a for a in argv if a.startswith("--")]
    # An unrecognized flag must never be swallowed: this script's only safety
    # rail is --dry-run, and silently ignoring a misspelled one ("--dryrun")
    # turns a requested preview into an unrequested write.
    unknown = [f for f in flags if f != "--dry-run"]
    if unknown:
        raise SystemExit(
            f"unknown option(s): {', '.join(unknown)} — the only supported flag "
            f"is --dry-run\n{__doc__}"
        )
    args = [a for a in argv if not a.startswith("--")]
    dry_run = "--dry-run" in flags
    if len(args) != 2:
        raise SystemExit(__doc__)

    index, target = Path(args[0]), parse_map(Path(args[1]))
    lines = read_text_preserving_newlines(index).split("\n")

    # Pre-pass: an id carried by more than one row makes every later decision
    # about that id ambiguous, so count the rows before deciding anything.
    row_counts: dict[str, int] = {}
    for line in lines:
        m = ROW_RE.match(line)
        if m:
            row_counts[m.group(1)] = row_counts.get(m.group(1), 0) + 1

    changed: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    unseen = set(target)

    for i, line in enumerate(lines):
        m = ROW_RE.match(line)
        if not m or m.group(1) not in target:
            continue
        lid = m.group(1)
        if lid not in unseen:
            continue  # already decided on this id's first row
        unseen.discard(lid)
        if row_counts[lid] > 1:
            skipped.append(
                (
                    lid,
                    f"REFUSED: {row_counts[lid]} rows share this id — "
                    "resolve the duplicate by hand",
                )
            )
            continue
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
        # Splice ONLY the status word; everything around it — cell padding,
        # bold markers, and any trailing "\r" this line carries — is copied
        # back verbatim, so an untouched byte stays an untouched byte.
        lines[i] = line[: tail.start(1)] + want + line[tail.end(1) :]
        changed.append((lid, current, want))

    if not dry_run and changed:
        write_text_preserving_newlines(index, "\n".join(lines))

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
