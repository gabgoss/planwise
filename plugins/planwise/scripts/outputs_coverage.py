#!/usr/bin/env python3
"""Check an Outputs/ directory listing against the task files that consume it.

Two subcommands share one directory listing as their denominator.

  named  --outputs DIR --tasks FILE... --side producer|receiver
      Every file in DIR must be named by explicit path in a Required Context
      table row of at least one task file. An unnamed file is a finding.
      producer: exit 1 when any file is unnamed. receiver: print the same list
      and exit 0, because the preflight side is advisory.

  count  --outputs DIR --tasks FILE...
      A count claim such as "the eleven outputs" (digits or spelled out) must
      equal the file count. Exit 0 when every claim equals it, 1 when a claim
      differs (claims listed with both numbers).

The listing uses os.scandir and ignores dot-files such as .gitkeep. The listing
count prints first, so an empty directory reads differently from a clean one.

What it cannot see: a file named only by prose or by a glob, a claim phrased
without the word output/outputs/output files, and a path written with a
different basename than the file on disk.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

from markdown_parser import split_row_cells

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
_NUM = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
_CLAIM_RE = re.compile(
    r"\b" + _NUM + r"\s+(?:[A-Za-z-]+\s+)?(?:outputs?|output\s+files?)\b",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")


def list_outputs(directory: str) -> list[str]:
    """Names of regular, non-dot files directly in directory (os.scandir)."""
    names = []
    with os.scandir(directory) as it:
        for entry in it:
            if entry.is_file() and not entry.name.startswith("."):
                names.append(entry.name)
    return sorted(names)


def _read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()


def required_context_cells(path: str) -> list[str]:
    """Every cell of every table row under a Required Context heading."""
    cells: list[str] = []
    inside = False
    level = 0
    for line in _read_lines(path):
        m = _HEADING_RE.match(line)
        if m:
            lvl = len(line) - len(line.lstrip("#"))
            if "required context" in m.group(1).lower():
                inside, level = True, lvl
            elif inside and lvl <= level:
                inside = False
            continue
        if inside and line.lstrip().startswith("|"):
            cells.extend(split_row_cells(line))
    return cells


def find_unnamed(names: list[str], task_files: list[str]) -> list[str]:
    cells = [c for t in task_files for c in required_context_cells(t)]
    unnamed = []
    for n in names:
        # A whole file token: not preceded or followed by another name character.
        pat = re.compile(r"(?<![\w.-])" + re.escape(n) + r"(?![\w-]|\.\w)")
        if not any(pat.search(c) for c in cells):
            unnamed.append(n)
    return unnamed


def find_claims(task_files: list[str]) -> list[tuple[str, int, str, int]]:
    """(file, line number, claim text, claimed number) for each count claim."""
    out = []
    for t in task_files:
        for i, line in enumerate(_read_lines(t), 1):
            for m in _CLAIM_RE.finditer(line):
                tok = m.group(1).lower()
                n = int(tok) if tok.isdigit() else _NUMBER_WORDS[tok]
                out.append((t, i, m.group(0), n))
    return out


def cmd_named(args: argparse.Namespace) -> int:
    names = list_outputs(args.outputs)
    print(f"listing: {len(names)} files in {args.outputs}; task files: {len(args.tasks)}")
    unnamed = find_unnamed(names, args.tasks)
    for n in unnamed:
        print(f"unnamed: {n}")
    if not unnamed:
        print("all listed files are named by explicit path")
        return 0
    print(f"{len(unnamed)} unnamed ({args.side})")
    return 1 if args.side == "producer" else 0


def cmd_count(args: argparse.Namespace) -> int:
    names = list_outputs(args.outputs)
    print(f"listing: {len(names)} files in {args.outputs}; task files: {len(args.tasks)}")
    claims = find_claims(args.tasks)
    bad = [c for c in claims if c[3] != len(names)]
    print(f"claims seen: {len(claims)}")
    for t, line, text, n in bad:
        print(f"{t}:{line}: claim '{text}' says {n}, listing has {len(names)}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check an Outputs/ listing against the task files that consume it.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("named", help="every listed file is named by a Required Context row")
    p.add_argument("--outputs", required=True)
    p.add_argument("--tasks", nargs="+", required=True)
    p.add_argument("--side", choices=("producer", "receiver"), required=True)
    p.set_defaults(func=cmd_named)
    c = sub.add_parser("count", help="count claims equal the file count")
    c.add_argument("--outputs", required=True)
    c.add_argument("--tasks", nargs="+", required=True)
    c.set_defaults(func=cmd_count)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
