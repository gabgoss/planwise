#!/usr/bin/env python3
"""Batch gate: whole-set checks over the outputs of one parallel batch.

Runs after every per-task gate has passed and before the consolidator is
dispatched (references/dispatch-batch-gate.md §1). A per-task gate sees one
output, so it cannot see a property that is true only of the set. Two
subcommands cover two such properties:

    labels <files...>
        Compare the section-label sets of the outputs (dispatch-batch-gate.md
        §4, "diff the emitted shapes after"). A label is a level-2 to level-4
        ATX heading, kept with its level marker ("## Scripts"), read outside
        plain fenced code blocks. Prints the file count first.
        Exit 0 when every set is identical. Exit 1 on divergence, listing the
        labels each file adds (not in every file) and lacks (in another file
        but not this one). Exit 2 on a usage error or an unreadable file.

    items --ids <list file> <files...>
        Each required item id appears exactly once across the batch, and the
        output names the MISSING and DUPLICATE members (verify-verdict-source.md
        §4, the stage this file owns). The list file holds one id per line;
        blank lines and lines starting with "#" are skipped. Prints the id and
        file counts first. Exit 0 clean, 1 on any MISSING or DUPLICATE member,
        2 on an empty id list, a usage error or an unreadable file.

What the checks cannot see:
    - labels compares heading text only. It does not see bolded prose labels,
      setext headings, or headings inside a callout-prefixed ("> ```") fence,
      and it does not compare heading order.
    - items counts token occurrences. An id counts wherever it appears as a
      whole token (not glued to a letter, digit, "_" or "-"), so a prose
      mention beside the item's own row counts as a second appearance. It
      cannot tell a cross-reference from a duplicate item.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

_HEADING_RE = re.compile(r"(#{2,4})[ \t]+")
_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")


def _read_lines(path: Path) -> list[str]:
    """Return the file's lines with line endings removed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [line.rstrip("\r\n") for line in text.splitlines()]


def section_labels(lines: list[str]) -> set[str]:
    """Return the set of level-2 to level-4 heading labels outside plain fences."""
    labels: set[str] = set()
    fence: str | None = None
    for line in lines:
        fm = _FENCE_RE.match(line)
        if fm:
            run = fm.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[fm.end():].strip():
                fence = None
            continue
        if fence is not None:
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            text = line[hm.end():].strip()
            if text:
                labels.add(f"{hm.group(1)} {text}")
    return labels


def compare_label_sets(sets: dict[str, set[str]]) -> dict[str, tuple[list[str], list[str]]]:
    """Return {file: (adds, lacks)} for each file whose set differs from the union.

    adds: labels the file carries that some other file lacks.
    lacks: labels another file carries that this file lacks.
    """
    if not sets:
        return {}
    union = set().union(*sets.values())
    common = set.intersection(*sets.values())
    out: dict[str, tuple[list[str], list[str]]] = {}
    for name, labels in sets.items():
        adds = sorted(labels - common)
        lacks = sorted(union - labels)
        if adds or lacks:
            out[name] = (adds, lacks)
    return out


def _id_pattern(item_id: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(item_id) + r"(?![A-Za-z0-9_-])")


def read_id_list(path: Path) -> list[str]:
    """Return the ids in a list file, in order, without blanks, comments or repeats."""
    ids: list[str] = []
    for line in _read_lines(path):
        token = line.strip()
        if token and not token.startswith("#") and token not in ids:
            ids.append(token)
    return ids


def count_items(ids: list[str], texts: dict[str, str]) -> dict[str, dict[str, int]]:
    """Return {id: {file: occurrences}} over the batch, files with zero omitted."""
    counts: dict[str, dict[str, int]] = {}
    for item_id in ids:
        pat = _id_pattern(item_id)
        per_file: dict[str, int] = {}
        for name, text in texts.items():
            n = len(pat.findall(text))
            if n:
                per_file[name] = n
        counts[item_id] = per_file
    return counts


def _cmd_labels(files: list[str]) -> int:
    print(f"labels: {len(files)} files")
    if len(files) < 2:
        print("labels: need at least 2 files to compare", file=sys.stderr)
        return 2
    sets: dict[str, set[str]] = {}
    for f in files:
        key = f if f not in sets else f"{f} (#{len(sets) + 1})"
        try:
            sets[key] = section_labels(_read_lines(Path(f)))
        except OSError as exc:
            print(f"labels: cannot read {f}: {exc}", file=sys.stderr)
            return 2
    for name, labels in sets.items():
        print(f"  {len(labels)} labels  {name}")
    diverged = compare_label_sets(sets)
    if not diverged:
        print("labels: identical")
        return 0
    print(f"labels: DIVERGENT in {len(diverged)} of {len(sets)} files")
    for name, (adds, lacks) in diverged.items():
        print(f"{name}:")
        for label in adds:
            print(f"  adds:  {label}")
        for label in lacks:
            print(f"  lacks: {label}")
    return 1


def _cmd_items(ids_file: str, files: list[str]) -> int:
    try:
        ids = read_id_list(Path(ids_file))
    except OSError as exc:
        print(f"items: cannot read id list {ids_file}: {exc}", file=sys.stderr)
        return 2
    print(f"items: {len(ids)} ids, {len(files)} files")
    if not ids:
        print("items: the id list is empty; nothing to gate", file=sys.stderr)
        return 2
    if not files:
        print("items: no batch files given", file=sys.stderr)
        return 2
    texts: dict[str, str] = {}
    for f in files:
        try:
            texts[f] = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"items: cannot read {f}: {exc}", file=sys.stderr)
            return 2
    counts = count_items(ids, texts)
    missing = [i for i in ids if not counts[i]]
    duplicate = [i for i in ids if sum(counts[i].values()) > 1]
    if missing:
        print("MISSING: " + ", ".join(missing))
    for item_id in duplicate:
        where = ", ".join(f"{name} x{n}" for name, n in counts[item_id].items())
        print(f"DUPLICATE: {item_id} ({sum(counts[item_id].values())}: {where})")
    if missing or duplicate:
        print(f"items: FAIL, {len(missing)} missing, {len(duplicate)} duplicate")
        return 1
    print(f"items: OK, all {len(ids)} ids appear exactly once")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Whole-set checks over the outputs of one parallel batch."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_labels = sub.add_parser("labels", help="compare the section-label sets of the outputs")
    p_labels.add_argument("files", nargs="+")
    p_items = sub.add_parser("items", help="each required id appears exactly once")
    p_items.add_argument("--ids", required=True, help="file with one required id per line")
    p_items.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if args.cmd == "labels":
        return _cmd_labels(args.files)
    return _cmd_items(args.ids, args.files)


if __name__ == "__main__":
    sys.exit(main())
