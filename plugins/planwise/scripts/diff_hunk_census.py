#!/usr/bin/env python3
"""Hunk census of a candidate file against its control.

Usage: python -B diff_hunk_census.py <control> <candidate>

Reads both files as bytes and splits them into lines that keep their
endings. Runs difflib over those lines, so git's autocrlf view plays no
part. Classifies each hunk as a (added), d (deleted) or c (changed).
Prints one line per d and c hunk, then a summary line:

    d=<n> c=<n> a=<n>

Exit codes: 0 when d=0, 1 when d>0, 2 on usage error or a missing path.
"""

import difflib
import sys

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__


def read_lines(path):
    with open(path, "rb") as handle:
        return handle.read().splitlines(keepends=True)


def census(control, candidate):
    """Return (rows, counts) for two lists of byte lines."""
    matcher = difflib.SequenceMatcher(None, control, candidate, autojunk=False)
    counts = {"a": 0, "d": 0, "c": 0}
    rows = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"insert": "a", "delete": "d", "replace": "c"}[tag]
        counts[kind] += 1
        if kind in ("d", "c"):
            rows.append(
                f"{kind} control:{i1 + 1}-{i2} candidate:{j1 + 1}-{j2}"
                if kind == "c"
                else f"{kind} control:{i1 + 1}-{i2}"
            )
    return rows, counts


def main(argv):
    if len(argv) != 2:
        print("usage: diff_hunk_census.py <control> <candidate>", file=sys.stderr)
        return 2
    try:
        control = read_lines(argv[0])
        candidate = read_lines(argv[1])
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rows, counts = census(control, candidate)
    for row in rows:
        print(row)
    print(f"d={counts['d']} c={counts['c']} a={counts['a']}")
    return 1 if counts["d"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
