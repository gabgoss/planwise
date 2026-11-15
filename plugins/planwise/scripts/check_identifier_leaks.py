#!/usr/bin/env python3
"""List authoring-repo identifiers that leaked into content-bearing artifacts.

Predicate. A shipped artifact carries no name that resolves only inside an
authoring repository. Four pattern families find the candidates, and each hit
is reported under its family name:

  external-id     an external bookkeeping identifier: a lesson, backlog,
                  plugin-backlog or decision prefix followed by a digit, or
                  one of the first four prefixes glued to a capitalised word
                  or a digit (the file-name spelling).
  structure-name  a literal sprint or session folder name with a numeral.
  plan-abbrev     the plan-artifact shape: two to five capitals, a hyphen,
                  then a meta-session, consolidated-context or task-ordinal
                  segment.
  review-finding  a review-finding citation, matched across line breaks.

Generic placeholders never match: a brace-wrapped abbreviation, a
brace-wrapped sprint number and an identifier prefix followed by a brace
placeholder all hold a brace where every family needs a numeral or a capital.

Input. One or more files or directories (a directory is walked), an optional
``--plans-index <path>`` and any number of ``--exempt <path>`` zones. With the
plans index, each plan-abbrev hit is looked up through
``parse_plans.parse_index_table``: an abbreviation the index lists is a
``leak``, any other is a ``sample``. Every other hit, and every hit when no
index is given, prints as a ``candidate``. Hits inside an exempt zone are not
listed. Each zone instead prints its hit-line count per family, so an emptied
or mistyped zone shows 0.

Exit contract. 0 when no ``leak`` and no ``candidate`` remains outside the
exempt zones. 1 otherwise, with each hit printed as file, line, family, class
and token. 2 on a usage error, an unreadable path, or a plans index that is
unreadable or holds no rows.

What it cannot see. It cannot tell an inline-defined label (a compact name
defined in the parenthetical it appears in) from a citation, so that judgment
is left to a reader. It cannot resolve a structure name or an identifier
against a repository, so families other than plan-abbrev stay unclassified.
It reads files on disk, not a diff, so it reports pre-existing hits too. It
skips files that hold a NUL byte, and counts them in the summary.

Rule enforced: ``references/artifact-self-containment.md`` §4 (the identifier
families) and §4.3 (plan-structure names and the plans-index lookup).
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

from parse_plans import parse_index_table

FAMILIES = (
    ("external-id", re.compile(r"(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9]|\b(LL|BB|BLI|PLG)([A-Z][a-z]|[0-9]))")),
    ("structure-name", re.compile(r"Sprint-[0-9]|Session-[0-9]")),
    ("plan-abbrev", re.compile(r"\b[A-Z]{2,5}-(META-S[0-9]|Consolidated-Context|S[0-9]{2}-[0-9]{2}-)")),
    ("review-finding", re.compile(r"Finding[\s#-]*F?[0-9]|\b(closeout|pre-commit)\s+review\b")),
)
FAMILY_NAMES = tuple(name for name, _ in FAMILIES)
CLASSES = ("leak", "sample", "candidate")
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache", ".mypy_cache"})


def iter_files(targets: list[Path]):
    """Yield each target file, and every file under each target directory, in path order."""
    for target in targets:
        if target.is_file():
            yield target
            continue
        for path in sorted(target.rglob("*")):
            if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(target).parts[:-1]):
                yield path


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """Return sorted, de-duplicated ``(line, family, token)`` hits for one file's text."""
    seen: set[tuple[int, str, str]] = set()
    for family, pattern in FAMILIES:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            token = " ".join(match.group(0).split())
            seen.add((line, family, token))
    return sorted(seen)


def load_plans_index(path: Path) -> set[str]:
    """Return the abbreviations a plans index lists. Raise ValueError when it holds no rows."""
    rows = parse_index_table(path.read_text(encoding="utf-8")).rows
    if not rows:
        raise ValueError(f"plans index holds no rows: {path}")
    abbrevs: set[str] = set()
    for row in rows:
        abbrevs.add(row.abbrev)
        abbrevs.add(row.abbrev.partition("-")[0])
    return abbrevs


def classify(family: str, token: str, abbrevs: set[str] | None) -> str:
    """Return ``leak`` or ``sample`` for a looked-up plan-abbrev hit, else ``candidate``."""
    if abbrevs is None or family != "plan-abbrev":
        return "candidate"
    return "leak" if token.partition("-")[0] in abbrevs else "sample"


def zone_of(path: Path, zones: list[tuple[str, Path]]) -> str | None:
    """Return the argument of the first exempt zone that holds ``path``, or None."""
    for label, root in zones:
        if path == root or root in path.parents:
            return label
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List authoring-repo identifiers in content-bearing artifacts (artifact-self-containment.md §4, §4.3)."
    )
    parser.add_argument("paths", nargs="+", help="files or directories to scan")
    parser.add_argument("--plans-index", help="plans index file; classifies plan-abbrev hits as leak or sample")
    parser.add_argument("--exempt", action="append", default=[], help="exempt zone (file or directory); repeatable")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    targets = [Path(raw) for raw in args.paths]
    missing = [raw for raw, target in zip(args.paths, targets) if not target.exists()]
    if missing:
        print(f"error: unreadable path: {', '.join(missing)}", file=sys.stderr)
        return 2
    abbrevs = None
    if args.plans_index:
        try:
            abbrevs = load_plans_index(Path(args.plans_index))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"error: unreadable plans index: {exc}", file=sys.stderr)
            return 2
    zones = [(raw, Path(raw).resolve()) for raw in args.exempt]
    zone_counts = {label: dict.fromkeys(FAMILY_NAMES, 0) for label, _ in zones}
    class_counts = dict.fromkeys(CLASSES, 0)
    line_counts = dict.fromkeys(FAMILY_NAMES, 0)
    scanned = skipped = 0
    for path in iter_files(targets):
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"error: unreadable path: {exc}", file=sys.stderr)
            return 2
        if b"\0" in data:
            skipped += 1
            continue
        scanned += 1
        hits = scan_text(data.decode("utf-8", errors="replace"))
        per_family = {name: len({line for line, family, _ in hits if family == name}) for name in FAMILY_NAMES}
        zone = zone_of(path.resolve(), zones)
        if zone is not None:
            for name, count in per_family.items():
                zone_counts[zone][name] += count
            continue
        for name, count in per_family.items():
            line_counts[name] += count
        for line, family, token in hits:
            verdict = classify(family, token, abbrevs)
            class_counts[verdict] += 1
            print(f"{path.as_posix()}:{line}: [{family}] {verdict}: {token}")
    for label, _ in zones:
        counts = zone_counts[label]
        detail = " ".join(f"{name}={counts[name]}" for name in FAMILY_NAMES)
        print(f"zone {label}: {detail} total={sum(counts.values())}")
    lines_detail = " ".join(f"{name}={line_counts[name]}" for name in FAMILY_NAMES)
    print(f"lines outside zones: {lines_detail}")
    classes_detail = " ".join(f"{name}={class_counts[name]}" for name in CLASSES)
    print(f"summary: {scanned} files scanned, {skipped} binary skipped; {classes_detail}")
    return 1 if class_counts["leak"] or class_counts["candidate"] else 0


if __name__ == "__main__":
    sys.exit(main())
