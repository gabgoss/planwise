#!/usr/bin/env python3
"""Decide whether a dispatched runner is alive from its own JSONL transcript.

Enforces the delegated-orchestration section "Liveness — Establish Death
Before Dispatching a Replacement" (§1.30; the base file
``references/agent-orchestration-delegated.md`` carries the part table that
names the part file holding it). Silence is not evidence of death: a runner is
alive when its transcript line count grows across two samples AND its last
entry's timestamp is recent. One sample proves nothing.

The check reuses the one-liners §1.30 embeds:

    wc -l < "$F"            # sample twice, a minute apart -- growing => alive
    python -c "...json.loads(open(F).readlines()[-1])['timestamp']" "$F"
    date -u -Iseconds       # compare against the line above

Input: a transcript JSONL path, ``--interval`` seconds between the two line
count samples (default 60), and ``--max-age`` seconds for "recent" (default
120).

Exit contract: 0 alive (the count grew and the last timestamp is at most
``--max-age`` old), 3 stalled (no growth, or the last timestamp is older), 2
unreadable (a missing file, or no line with a parseable ``timestamp`` among the
last lines).

What it cannot see: whether a stalled runner is looping or dead (both read
stalled), what the runner wrote to disk (§1.30 says a disk inventory never
answers liveness), or a run journal's ``started``/``result`` lines (§1.30.1).
It never relaunches anything: re-dispatch stays the orchestrator's decision.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

TAIL_LINES = 5


class Unreadable(Exception):
    """The transcript cannot be read or carries no timestamp (exit 2)."""


def line_count(path: Path) -> int:
    """Count newline bytes, as ``wc -l`` does."""
    try:
        return path.read_bytes().count(b"\n")
    except OSError as exc:
        raise Unreadable(f"cannot read {path}: {exc}") from exc


def last_timestamp(path: Path) -> datetime:
    """Return the ``timestamp`` of the last parseable entry among the last lines."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise Unreadable(f"cannot read {path}: {exc}") from exc
    for raw in reversed([ln for ln in lines if ln.strip()][-TAIL_LINES:]):
        try:
            stamp = json.loads(raw)["timestamp"]
            parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError):
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise Unreadable(f"{path}: no entry with a parseable timestamp in the last {TAIL_LINES} lines")


def classify(first: int, second: int, age_seconds: float, max_age: float) -> str:
    """Return 'alive' or 'stalled' from two samples and the last entry's age."""
    return "alive" if second > first and age_seconds <= max_age else "stalled"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcript", help="the dispatched runner's JSONL transcript path")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="seconds between the two line-count samples (default 60)")
    parser.add_argument("--max-age", type=float, default=120.0,
                        help="largest last-entry age in seconds that counts as recent (default 120)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    if args.interval < 0 or args.max_age < 0:
        print("error: --interval and --max-age must be 0 or more", file=sys.stderr)
        return 2
    path = Path(args.transcript)
    try:
        if not path.is_file():
            raise Unreadable(f"{path}: not a file")
        first = line_count(path)
        time.sleep(args.interval)
        second = line_count(path)
        stamp = last_timestamp(path)
    except Unreadable as exc:
        print(f"unreadable: {exc}", file=sys.stderr)
        return 2
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    verdict = classify(first, second, age, args.max_age)
    print(f"{verdict}: {path} lines {first} -> {second} over {args.interval:g}s; "
          f"last entry {stamp.isoformat()} ({age:.0f}s old, max {args.max_age:g}s)")
    return 0 if verdict == "alive" else 3


if __name__ == "__main__":
    sys.exit(main())
