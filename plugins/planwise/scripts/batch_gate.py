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

    labels --expect <task file> <output file> [--expect ...]
        Check each output against its own task file instead of against the
        other outputs. Use it for a layer whose briefs prescribe different
        "###" tables, where the plain diff reads a correct layer as divergent.
        The required labels are the backticked labels of the task file's
        "**Required headings:**" field: every backticked span on the field
        line, then the first backticked span of each bullet that follows it.
        A label with a "#" marker ("## Scope") must match a heading of that
        level exactly. A label without one ("Scope") matches the heading text
        at levels 2 to 4. A marker outside levels 2 to 4 is a usage error.
        Extra headings in an output are ignored. Prints the pair count first.
        Exit 0 when every output carries every required label. Exit 1 on any
        dropped label, listing it as "lacks:" under its output. Exit 2 on a
        usage error, an unreadable file, or a task file that lists no
        backticked label (an empty expected set cannot gate). The positional
        form and --expect do not combine.

    items --ids <list file> <files...>
        Each required item id has exactly one owner across the batch, and the
        output names the MISSING and DUPLICATE members (verify-verdict-source.md
        §4, the stage this file owns). The list file holds one id per line;
        blank lines and lines starting with "#" are skipped. Prints the id and
        file counts first. Exit 0 clean, 1 on any MISSING or DUPLICATE member,
        2 on an empty id list, a usage error or an unreadable file.

        A file claims an id when the id leads the first cell of a pipe-table
        row, or the text of an ATX heading, outside fenced code blocks. An id
        is DUPLICATE when two or more files claim it, when one table holds two
        rows for it, or when one file has two headings for it. A repeat mention
        inside the owning file, or in a later table's other cells, is not a
        duplicate. An id that no file claims falls back to file-level
        ownership, so a bullet or prose output still gates: it is DUPLICATE
        when two or more files mention it. An id mentioned nowhere is MISSING.

What the checks cannot see:
    - labels compares heading text only. It does not see bolded prose labels,
      setext headings, or headings inside a callout-prefixed ("> ```") fence,
      and it does not compare heading order. With --expect it also does not
      see an output that adds a heading its task did not ask for.
    - items matches an id as a whole token (not glued to a letter, digit, "_"
      or "-"). It reads only the first cell of a table row, so an id that
      leads a later cell is a cross-reference, never a claim. It cannot tell
      a genuine second item from a second row that restates the first.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from collections.abc import Iterator
from pathlib import Path

from markdown_parser import split_row_cells

_HEADING_RE = re.compile(r"(#{2,4})[ \t]+")
_ANY_HEADING_RE = re.compile(r"#{1,6}[ \t]+")
_SEPARATOR_CELL_RE = re.compile(r"\s*:?-+:?\s*")
_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")


def _read_lines(path: Path) -> list[str]:
    """Return the file's lines with line endings removed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [line.rstrip("\r\n") for line in text.splitlines()]


def _unfenced(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield (index, line) for each line outside a plain fenced code block.

    The fence lines themselves are skipped. The index lets a caller see that
    a fence cut a run of consecutive lines in two.
    """
    fence: str | None = None
    for i, line in enumerate(lines):
        fm = _FENCE_RE.match(line)
        if fm:
            run = fm.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not line[fm.end():].strip():
                fence = None
            continue
        if fence is None:
            yield i, line


def section_labels(lines: list[str]) -> set[str]:
    """Return the set of level-2 to level-4 heading labels outside plain fences."""
    labels: set[str] = set()
    for _, line in _unfenced(lines):
        hm = _HEADING_RE.match(line)
        if hm:
            text = line[hm.end():].strip()
            if text:
                labels.add(f"{hm.group(1)} {text}")
    return labels


def _split_label(label: str) -> tuple[str, str]:
    """Split a label into (marker, text). The marker is "" for a bare text label."""
    m = re.match(r"(#{1,6})\s+(.*\S)\s*$", label.strip())
    if m:
        return m.group(1), re.sub(r"\s+", " ", m.group(2))
    return "", re.sub(r"\s+", " ", label.strip())


def required_labels(task_lines: list[str]) -> list[str]:
    """Return the required heading labels a task file's "**Required headings:**" field lists.

    Takes every backticked span on the field line (an HTML comment on the line is
    ignored), then the first backticked span of each bullet directly below it.
    """
    labels: list[str] = []
    for start, line in _unfenced(task_lines):
        if not line.lstrip().startswith("**Required headings:**"):
            continue
        field = re.sub(r"<!--.*?-->", "", line.split(":**", 1)[1])
        labels.extend(m.strip() for m in re.findall(r"`([^`]+)`", field) if m.strip())
        for follow in task_lines[start + 1:]:
            if not re.match(r"\s*[-*+]\s", follow):
                break
            spans = re.findall(r"`([^`]+)`", follow)
            if spans and spans[0].strip():
                labels.append(spans[0].strip())
        break
    return labels


def missing_required(required: list[str], labels: set[str]) -> list[str]:
    """Return the required labels that no heading in `labels` satisfies.

    A required label with a "#" marker needs a heading of that exact level and
    text. A bare label needs a heading with that text at any level in `labels`.
    """
    texts = {_split_label(label)[1] for label in labels}
    exact = {f"{m} {t}" for m, t in (_split_label(label) for label in labels)}
    lacks: list[str] = []
    for label in required:
        marker, text = _split_label(label)
        found = f"{marker} {text}" in exact if marker else text in texts
        if not found:
            lacks.append(label)
    return lacks


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


def _plain(cell: str) -> str:
    """Strip the markup a table cell or heading wraps around a leading id."""
    for mark in ("`", "**", "[", "]"):
        cell = cell.replace(mark, "")
    return cell.strip().lstrip("*_ \t")


def scan_claims(lines: list[str]) -> tuple[list[list[str]], list[str]]:
    """Return (tables, headings): the claim sites of one file, outside fences.

    tables holds one list per pipe table (a run of consecutive "|" lines), each
    entry the plain first cell of a data row. The separator row is skipped.
    headings holds the plain text of every level-1 to level-6 ATX heading.
    """
    tables: list[list[str]] = []
    headings: list[str] = []
    prev = -2
    current: list[str] | None = None
    for i, line in _unfenced(lines):
        stripped = line.strip()
        if stripped.startswith("|"):
            if current is None or i != prev + 1:
                current = []
                tables.append(current)
            prev = i
            cells = split_row_cells(stripped)
            if not cells or all(_SEPARATOR_CELL_RE.fullmatch(c) for c in cells if c.strip()):
                continue
            current.append(_plain(cells[0]))
            continue
        current = None
        hm = _ANY_HEADING_RE.match(line)
        if hm:
            headings.append(_plain(line[hm.end():]))
    return tables, headings


def judge_items(ids: list[str], texts: dict[str, str]) -> dict[str, dict]:
    """Return {id: {"owners": [(file, kind, n)], "missing": bool, "duplicate": bool}}.

    kind is "rows" (first-cell table rows, n in the busiest table), "headings"
    (ATX headings) or "x" (the file-level mention fallback, n mentions).
    """
    scans = {name: scan_claims(text.splitlines()) for name, text in texts.items()}
    mentions = count_items(ids, texts)
    out: dict[str, dict] = {}
    for item_id in ids:
        lead = re.compile(re.escape(item_id) + r"(?![A-Za-z0-9_-])")
        owners: list[tuple[str, str, int]] = []
        duplicate = False
        claiming: set[str] = set()
        for name, (tables, headings) in scans.items():
            rows = max((sum(1 for c in t if lead.match(c)) for t in tables), default=0)
            heads = sum(1 for h in headings if lead.match(h))
            if rows:
                owners.append((name, "rows", rows))
                duplicate = duplicate or rows > 1
            if heads:
                owners.append((name, "headings", heads))
                duplicate = duplicate or heads > 1
            if rows or heads:
                claiming.add(name)
        if len(claiming) > 1:
            duplicate = True
        if not owners:
            owners = [(name, "x", n) for name, n in mentions[item_id].items()]
            duplicate = len(owners) > 1
        out[item_id] = {"owners": owners, "missing": not owners, "duplicate": duplicate}
    return out


def _cmd_expect(pairs: list[list[str]]) -> int:
    print(f"labels: {len(pairs)} task/output pairs")
    failed = 0
    results: list[tuple[str, list[str], int]] = []
    for task, output in pairs:
        try:
            required = required_labels(_read_lines(Path(task)))
            labels = section_labels(_read_lines(Path(output)))
        except OSError as exc:
            print(f"labels: cannot read {exc.filename or task}: {exc}", file=sys.stderr)
            return 2
        if not required:
            print(
                f"labels: {task} lists no backticked label under \"**Required headings:**\"; "
                "an empty expected set cannot gate",
                file=sys.stderr,
            )
            return 2
        for label in required:
            marker, _ = _split_label(label)
            if marker and len(marker) not in (2, 3, 4):
                print(
                    f"labels: required label {label!r} in {task} is outside levels 2 to 4",
                    file=sys.stderr,
                )
                return 2
        lacks = missing_required(required, labels)
        failed += bool(lacks)
        results.append((output, lacks, len(required)))
    for output, lacks, total in results:
        print(f"  {total - len(lacks)}/{total} required labels  {output}")
    for output, lacks, _ in results:
        if lacks:
            print(f"{output}:")
            for label in lacks:
                print(f"  lacks: {label}")
    if failed:
        print(f"labels: FAIL, {failed} of {len(pairs)} outputs lack a required heading")
        return 1
    print("labels: OK, every output carries its task's required headings")
    return 0


def _cmd_labels(files: list[str], expect: list[list[str]] | None = None) -> int:
    if expect:
        if files:
            print("labels: give output files or --expect pairs, not both", file=sys.stderr)
            return 2
        return _cmd_expect(expect)
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
    verdicts = judge_items(ids, texts)
    missing = [i for i in ids if verdicts[i]["missing"]]
    duplicate = [i for i in ids if verdicts[i]["duplicate"]]
    if missing:
        print("MISSING: " + ", ".join(missing))
    for item_id in duplicate:
        owners = verdicts[item_id]["owners"]
        where = ", ".join(
            f"{name} x{n}" if kind == "x" else f"{name} {kind} {n}" for name, kind, n in owners
        )
        print(f"DUPLICATE: {item_id} ({sum(n for _, _, n in owners)}: {where})")
    if missing or duplicate:
        print(f"items: FAIL, {len(missing)} missing, {len(duplicate)} duplicate")
        return 1
    print(f"items: OK, all {len(ids)} ids have exactly one owner")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Whole-set checks over the outputs of one parallel batch."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_labels = sub.add_parser("labels", help="compare the section-label sets of the outputs")
    p_labels.add_argument("files", nargs="*")
    p_labels.add_argument(
        "--expect",
        nargs=2,
        action="append",
        metavar=("TASK", "OUTPUT"),
        help="check OUTPUT against the required headings of its own TASK file (repeatable)",
    )
    p_items = sub.add_parser("items", help="each required id has exactly one owner")
    p_items.add_argument("--ids", required=True, help="file with one required id per line")
    p_items.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if args.cmd == "labels":
        return _cmd_labels(args.files, args.expect)
    return _cmd_items(args.ids, args.files)


if __name__ == "__main__":
    sys.exit(main())
