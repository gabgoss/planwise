#!/usr/bin/env python3
"""Check that each behaviour-adding row of a closing-sweep ledger quotes its call site.

Usage:
    python -B check_sweep_ledger.py <ledger.md|->

A closing-sweep ledger answers "invoked from where?" for every deliverable
that lands new behaviour. Such a row must quote a production call site: a
`file:line` (for example `scripts/x.py:12`) and the calling expression in
backticks (text containing `(`, for example `` `x(arg)` ``). A row whose only
evidence is its own definition is not terminal.

A table counts as a ledger table when its header row names a class or a
description column (a header holding `class`, `kind`, `type`, `description`,
`deliverable`, `change` or `behaviour`). A row is behaviour-adding when one of
those cells says the row adds a function, flag, key, parameter, option or
branch, or when a class cell says `behaviour` (or `behavior`). Cells are read
with the shared table splitter, so an escaped `\\|` stays inside its cell.

The first output line is `N behaviour-adding rows checked in M ledger tables`,
so a file with no ledger table reads differently from a clean one.

`-h` or `--help` prints this text and exits 0. `-` reads standard input.

Exit codes: 0 every behaviour-adding row quotes both, 1 a row lacks the
`file:line` or the calling expression (each printed with its line and what it
lacks), 2 usage or an unreadable file (an `Error:` line goes to stderr).
"""
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from markdown_parser import split_row_cells

LEDGER_HEADER_RE = re.compile(r"class|kind|type|description|deliverable|change|behavio", re.IGNORECASE)
ADDS_RE = re.compile(
    r"\b(?:adds?|added|adding|new)\b[^|]{0,60}?\b(?:function|flag|key|parameter|param|option|branch)(?:es|s)?\b",
    re.IGNORECASE,
)
BEHAVIOUR_CLASS_RE = re.compile(r"\bbehaviou?r\b", re.IGNORECASE)
FILE_LINE_RE = re.compile(r"\S+\.\w+:\d+")
CALL_EXPR_RE = re.compile(r"`[^`]*\([^`]*`")
SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _tables(lines):
    """Yield (header_cells, [(line_number, row_text)]) for every pipe table."""
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        if line.lstrip().startswith("|") and SEPARATOR_RE.match(lines[index + 1]):
            header = split_row_cells(line)
            rows = []
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append((index + 1, lines[index]))
                index += 1
            yield header, rows
        else:
            index += 1


def check(text):
    """Return (rows_checked, tables_checked, failures); a failure is (line, row, missing)."""
    rows_checked = 0
    tables_checked = 0
    failures = []
    for header, rows in _tables(text.splitlines()):
        columns = [i for i, name in enumerate(header) if LEDGER_HEADER_RE.search(name)]
        if not columns:
            continue
        tables_checked += 1
        for number, row in rows:
            cells = split_row_cells(row)
            picked = [cells[i] for i in columns if i < len(cells)]
            if not any(ADDS_RE.search(c) or BEHAVIOUR_CLASS_RE.search(c) for c in picked):
                continue
            rows_checked += 1
            joined = " ".join(cells)
            missing = []
            if not FILE_LINE_RE.search(joined):
                missing.append("file:line")
            if not CALL_EXPR_RE.search(joined):
                missing.append("calling expression")
            if missing:
                failures.append((number, row.strip(), missing))
    return rows_checked, tables_checked, failures


def main(argv):
    if argv in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        text = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: check_sweep_ledger cannot read the ledger: {exc}", file=sys.stderr)
        return 2
    rows_checked, tables_checked, failures = check(text)
    print(f"{rows_checked} behaviour-adding rows checked in {tables_checked} ledger tables")
    for number, row, missing in failures:
        print(f"NO CALL SITE line {number} (missing {' and '.join(missing)}): {row}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
