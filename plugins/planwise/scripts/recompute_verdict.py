#!/usr/bin/env python3
"""Recompute a RED, YELLOW or GREEN verdict from a findings file's own counts.

Rule enforced: references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md
§1.16.1 "Under-classification — recompute verdict from finding counts". The
orchestrator recomputes the label from the counts and never reads it off the
agent's summary line:

    RED     when broken + contradiction > 0
    YELLOW  else when drift + missing > 0
    GREEN   otherwise

Input: one findings file. It must state each of the four counts once and one
verdict line. Accepted count forms, case-insensitive, with optional markdown
emphasis or a list bullet in front:
    broken: 2      BROKEN=2      **Drift:** 0
    | missing | 1 |   (a two-cell table row: name, then an integer)
Accepted verdict forms: "verdict: RED", "**Verdict:** YELLOW", "Verdict = GREEN".

Exit: 0 when the reported verdict equals the recomputed one; 1 on a mismatch,
printing both values; 2 on a usage error, an unreadable file, a missing or
conflicting count, or a missing or conflicting verdict line.

What it cannot see: whether the counts themselves are right. A file that
under-counts its own findings recomputes to the same soft label, so the counts
still need checking against the enumerated findings. It reads only the four
counts above; a verdict scale with other labels or other count names is out
of its scope.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

from markdown_parser import split_row_cells

COUNT_NAMES = ("broken", "contradiction", "drift", "missing")

_COUNT_RE = re.compile(
    r"^[^\w\n]*(broken|contradiction|drift|missing)[^\w\n]*?[:=][^\w\n]*(\d+)\b",
    re.IGNORECASE,
)
_VERDICT_RE = re.compile(
    r"^[^\w\n]*verdict[^\w\n]*?[:=][^\w\n]*(RED|YELLOW|GREEN)\b",
    re.IGNORECASE,
)


def recompute(counts: dict[str, int]) -> str:
    """The §1.16.1 label for the four counts."""
    if counts["broken"] + counts["contradiction"] > 0:
        return "RED"
    if counts["drift"] + counts["missing"] > 0:
        return "YELLOW"
    return "GREEN"


def read_findings(text: str) -> tuple[dict[str, int], str | None, list[str]]:
    """Return (counts, reported verdict, problems) for the findings text.

    A problem is a missing count, a count stated twice with two values, or a
    verdict stated twice with two values.
    """
    found: dict[str, set[int]] = {name: set() for name in COUNT_NAMES}
    verdicts: set[str] = set()
    for line in text.splitlines():
        m = _COUNT_RE.match(line)
        if m:
            found[m.group(1).lower()].add(int(m.group(2)))
            continue
        v = _VERDICT_RE.match(line)
        if v:
            verdicts.add(v.group(1).upper())
            continue
        if line.lstrip().startswith("|"):
            cells = split_row_cells(line)
            if len(cells) == 2 and cells[0].strip("*` ").lower() in COUNT_NAMES and cells[1].strip("*` ").isdigit():
                found[cells[0].strip("*` ").lower()].add(int(cells[1].strip("*` ")))
    problems: list[str] = []
    counts: dict[str, int] = {}
    for name, values in found.items():
        if not values:
            problems.append(f"count {name} not found")
        elif len(values) > 1:
            problems.append(f"count {name} stated with values {sorted(values)}")
        else:
            counts[name] = values.pop()
    if len(verdicts) > 1:
        problems.append(f"verdict stated as {sorted(verdicts)}")
    reported = verdicts.pop() if len(verdicts) == 1 else None
    if reported is None and not problems:
        problems.append("verdict line not found")
    return counts, reported, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recompute a findings file's verdict from its counts (§1.16.1)."
    )
    parser.add_argument("findings", help="findings file holding the four counts and a verdict line")
    args = parser.parse_args(argv)
    path = Path(args.findings)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"recompute_verdict: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    counts, reported, problems = read_findings(text)
    if problems or reported is None:
        for item in problems or ["verdict line not found"]:
            print(f"{path}: {item}", file=sys.stderr)
        return 2
    canonical = recompute(counts)
    summary = ", ".join(f"{k}={counts[k]}" for k in COUNT_NAMES)
    if reported != canonical:
        print(f"{path}: verdict mismatch: reported={reported}, recomputed={canonical} ({summary})")
        return 1
    print(f"{path}: verdict {reported} matches the counts ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
