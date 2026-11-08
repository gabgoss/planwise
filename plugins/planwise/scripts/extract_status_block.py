#!/usr/bin/env python3
"""Bounded status-block extractor for a subagent transcript.

Recovers a status block that never routed back to the orchestrator
(references/dispatch-boundary-evidence.md §4). The transcript
(`agent-*.jsonl`) is the full subagent conversation, so it is read one line
at a time and only the last matching line is kept. The whole file is never
held in memory, and nothing but the matches is printed.

Usage:
    extract_status_block.py <agent-*.jsonl> --pattern <regex>

The caller supplies the field pattern. There is no default, because the
pattern must name the fields of the status-block contract the dispatch used,
and a pattern naming a field the contract does not define can never match.
Give it a small capture window, for example
    '(TASK_STATUS:|TASK_ID:|OUTPUT_FILES:)[^\\\\]{0,120}'
so a match stops at the next JSON escape rather than running to the line end.

The block is every match on the LAST line that matches. Earlier matching
lines are usually the spawn prompt's own template echoed back, so taking the
first match recovers the prompt rather than the report.

Output: one count line first ("scanned N lines, K matching"), then each
match of the last matching line, one per line.
Exit 0 with the block printed, 1 when no line matches, 2 when the file
cannot be read or the pattern does not compile.

What it cannot see: a field split across two transcript lines, and a block
whose fields fall outside the supplied pattern. The recovered block is
corroboration only. Measure every load-bearing field on disk before
accepting a task on it.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path


def last_block(path: Path, pattern: re.Pattern[str]) -> tuple[int, int, list[str]]:
    """Scan the file line by line and return (lines, matching lines, last block).

    The last block is the list of matches on the last matching line, or an
    empty list when no line matches. Only one line is held at a time.
    """
    scanned = 0
    matching = 0
    block: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for line in fh:
            scanned += 1
            found = [m.group(0) for m in pattern.finditer(line.rstrip("\r\n"))]
            if found:
                matching += 1
                block = found
    return scanned, matching, block


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the last status-block match in a subagent transcript."
    )
    parser.add_argument("transcript", help="path to the agent-*.jsonl transcript")
    parser.add_argument(
        "--pattern",
        required=True,
        help="field regex; every match on the last matching line is printed",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        pattern = re.compile(args.pattern)
    except re.error as exc:
        print(f"extract: pattern does not compile: {exc}", file=sys.stderr)
        return 2
    path = Path(args.transcript)
    try:
        scanned, matching, block = last_block(path, pattern)
    except OSError as exc:
        print(f"extract: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    print(f"scanned {scanned} lines, {matching} matching")
    if not block:
        print("extract: no match")
        return 1
    for item in block:
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
