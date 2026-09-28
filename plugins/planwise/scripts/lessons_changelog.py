#!/usr/bin/env python3
"""Guarded writer for the lessons changelog: `--append` one entry, `--split`
re-packs an over-budget changelog family and renumbers an unstable one.

Numbering is stable ascending. The oldest entry of the whole family (the
main file, its `-Archive-{YYYY}` part, and any further `-Part-NN` parts)
is Entry 1, the newest has the highest number, and a number never changes
once assigned. The files stay newest-first on the page, so the numbers
strictly descend top to bottom through the family. `--append` assigns
max + 1 to the new entry and prepends it under the backlink line.

A family whose numbers do not strictly descend in that order is unstable
(a positional scheme, or a mix of schemes). `--append` refuses it.
`--split`, and the upgrade routine through `plan_split`, renumbers it once
by family position: the oldest entry becomes Entry 1. A stable family is
never renumbered, and a move between files never rewrites a heading.

Every write, a one-file `--append` included, backs up every existing file
it replaces or removes, byte-exact, through the upgrade routine's
first-pre-image-wins helper, writes each file an entry moves into before
the file it leaves, and restores every touched file on any failure. Each
file keeps its own BOM and newline style, and a file whose entries do not
change is never rewritten. Every planned file is read back through the
parser before anything is written, and a file that would not read back as
the entries planned for it is refused, naming the entry.

Both modes refuse while the lessons index beside the family is not
generated: the migrator still owns the family then. `lessons_migration.py`
calls `plan_split` on an already-generated index; `migrate_lessons_index.py
--report` calls `plan_split_with_info`, the function it wraps, and the
migrator lays out a new family through `render_family`, this module's own
engine.

Usage:
    lessons_changelog.py --config CONFIG (--append TEXT | --append-file PATH | --split)
                          [--dry-run] [--json] [--date YYYY-MM-DD]

Exit codes: 0 = wrote (or a clean `--dry-run`, or nothing to do); 1 =
refused (an index that is not generated, foreign content outside any
`## Entry` section, an unstable family on `--append`, a malformed or
repeated new entry, a malformed `--date`, a layout that would not read
back, or a write that failed and was rolled back); 2 = the main changelog
file does not exist yet.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_budget import _measure
from backlog_index_schema import _changelog_filename, _index_naming
from config_loader import load_config
from migrate_backlog_support import BACKLINK_RE
from migrate_lessons_support import (
    _FENCE_RE,
    Refusal,
    _archive_naming,
    _fenced_lines,
    changelog_part_filename,
    classify_shape,
    newline_of,
)
from read_limits import READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN, estimate_tokens
from reconcile_common import read_text_preserving_newlines as read_text

_OLDER_RE = re.compile(r"^Older entries: \[[^\]]*\]\([^)]*\)$")
_ENTRY_HEADING_RE = re.compile(r"^## Entry (\d+)(.*)$")
_ENTRY_NUMBER_RE = re.compile(r"(## Entry )\d+")
_ARCHIVE_YEAR_RE = re.compile(r"-Archive-(\d{4})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BOM = "﻿"


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


# --------------------------------------------------------------------------
# Parse: one changelog-shaped file -> (entries, trailing "Older entries:" pointer)
# --------------------------------------------------------------------------

def _entry_headings(lines: list) -> list:
    """`(index, number, suffix)` for every unfenced `## Entry N` line in
    `lines`, in order. A line may keep a trailing `\\r`. The one delimiter
    rule: `_fenced_lines` (imported, never re-derived) makes a heading-shaped
    line inside a fenced block body text."""
    fenced = _fenced_lines(lines)
    out = []
    for j, line in enumerate(lines):
        m = None if fenced[j] else _ENTRY_HEADING_RE.match(line.strip())
        if m:
            out.append((j, int(m.group(1)), m.group(2)))
    return out


def _parse_changelog_body(text: str, label: str, older_re=None) -> tuple:
    """Parse one on-disk changelog file into `([(num, suffix, body), ...],
    trailing_pointer)`, in file order (newest first). `suffix` is whatever
    followed the entry number on its heading line, kept verbatim so a move
    never rewrites a heading. The file opens with one backlink line, or two
    for an archive part 1.

    Entries are delimited ONLY by an unfenced `## Entry N` line
    (`_entry_headings`). Every other line past the first heading --
    `## Drift Record`, a fenced `## Context`, anything -- is body text of
    the entry it falls in. The trailing pointer is recognised only where
    the writer puts it: `older_re` is given for the main file alone, and
    only a last non-blank line it matches is the pointer; any other line
    stays body text. Before the first heading only a backlink is
    recognised; anything else raises `Refusal` naming `label` and the
    1-based line."""
    norm = text.removeprefix(BOM).replace("\r\n", "\n")
    lines = norm.split("\n")
    i, n = 0, len(lines)
    consumed = 0
    while i < n and BACKLINK_RE.match(lines[i].strip()):
        consumed += 1
        i += 1
        if i < n and lines[i] == "":
            i += 1
    if consumed == 0:
        found = lines[0] if lines else ""
        raise Refusal(f"{label} line 1: expected a backlink line, found {found!r}")
    body_lines = lines[i:]
    end = len(body_lines)
    while end > 0 and body_lines[end - 1] == "":
        end -= 1
    trailing_pointer = ""
    if end > 0 and older_re is not None and older_re.match(body_lines[end - 1].strip()):
        trailing_pointer = body_lines[end - 1].strip()
        body_lines = body_lines[: end - 1]
        while body_lines and body_lines[-1] == "":
            body_lines.pop()
    body_end = i + len(body_lines)
    headings = [(j - i, num, suffix) for j, num, suffix in _entry_headings(lines) if i <= j < body_end]
    first = headings[0][0] if headings else len(body_lines)
    for j in range(first):
        if body_lines[j].strip():
            raise Refusal(f"{label} line {i + j + 1}: text outside any '## Entry' section: {body_lines[j]!r}")
    entries = []
    for h, (start, num, suffix) in enumerate(headings):
        bstart = start + 1
        if bstart < len(body_lines) and body_lines[bstart] == "":
            bstart += 1
        stop = headings[h + 1][0] if h + 1 < len(headings) else len(body_lines)
        blines = body_lines[bstart:stop]
        while blines and blines[-1] == "":
            blines.pop()
        entries.append((num, suffix, "\n".join(blines)))
    return entries, trailing_pointer


def _heading_numbers(text: str) -> list:
    """Every entry number in `text`, in file order, found by the parser's
    own delimiter rule WITHOUT a parse: nothing here can refuse."""
    return [num for _j, num, _s in _entry_headings(text.removeprefix(BOM).split("\n"))]


def _is_stable(numbers: list) -> bool:
    """True when `numbers` (family order, newest first) strictly descend."""
    return all(a > b for a, b in pairwise(numbers))


def _renumbered(entries: list) -> list:
    """`entries` newest first, renumbered by position: the oldest is 1."""
    total = len(entries)
    return [(total - i, suffix, body) for i, (_num, suffix, body) in enumerate(entries)]


def _renumber_text(text: str, numbers) -> str:
    """`text` with each unfenced `## Entry N` heading's number replaced by
    the next value of the iterator `numbers`, and every other byte kept:
    the BOM, the newline style, a heading's own suffix, and every body."""
    lines = text.split("\n")
    probe = [lines[0].removeprefix(BOM)] + lines[1:]
    for j, _num, _suffix in _entry_headings(probe):
        new = next(numbers)
        lines[j] = _ENTRY_NUMBER_RE.sub(lambda m, new=new: f"{m.group(1)}{new}", lines[j], count=1)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Render and plan
# --------------------------------------------------------------------------

def canonical_body(text: str) -> str:
    """An entry body as the parser reads it back: no BOM, `\\n` newlines,
    no blank line at either end. `--append`, the duplicate check and the
    migrator all hand the engine bodies in this form."""
    return text.removeprefix(BOM).replace("\r\n", "\n").strip("\n")


def _render_entries(entries: list) -> str:
    return "".join(f"## Entry {num}{suffix}\n\n{body}\n\n" for num, suffix, body in entries)


def _archive_base(naming, changelog_name: str) -> str:
    """Every archive filename's stem before `-Archive-{YYYY}`, taken from
    `_archive_naming` -- the writer's own namer -- so the locator finds
    exactly the files the writer names, whatever the index is called."""
    stem = Path(_changelog_filename(_archive_naming(naming, changelog_name, "0000"))).stem
    return stem.removesuffix("-Archive-0000")


def _names(naming, index_name: str, archive_year: str) -> dict:
    changelog_name = _changelog_filename(naming)
    a_naming = _archive_naming(naming, changelog_name, archive_year)
    archive = rf"{re.escape(_archive_base(naming, changelog_name))}-Archive-\d{{4}}{re.escape(naming.suffix)}"
    return {"index": index_name, "changelog": changelog_name, "a_naming": a_naming,
            "archive": _changelog_filename(a_naming),
            "older_re": re.compile(rf"^Older entries: \[({archive})\]\(\1\)$")}


def _file_name(pos: int, names: dict) -> str:
    if pos == 0:
        return names["changelog"]
    return names["archive"] if pos == 1 else changelog_part_filename(names["a_naming"], pos)


def _pointer(names: dict) -> str:
    return f"Older entries: [{names['archive']}]({names['archive']})"


def _render(pos: int, entries: list, names: dict, older: bool = False) -> str:
    """One family file as `\\n` text: `pos` 0 is the main file (with the
    `Older entries:` pointer when `older`), 1 the archive part 1 (backlinks
    to the changelog and the hub), and 2+ a `-Part-NN` continuation."""
    backlink = f"[← {names['index']}]({names['index']})"
    if pos == 0:
        return f"{backlink}\n\n{_render_entries(entries)}" + (f"{_pointer(names)}\n" if older else "")
    if pos == 1:
        head = f"[← {names['changelog']}]({names['changelog']})\n\n{backlink}"
    else:
        head = f"[← {names['archive']}]({names['archive']})"
    return f"{head}\n\n{_render_entries(entries)}"


def _tokens(text: str) -> int:
    return _measure(text.removeprefix(BOM).replace("\r\n", "\n"))[1]


def _fence_runs(body: str) -> tuple:
    """`(opens, closes)` of one entry body read alone, each a list of
    `(char, width)`: every fence opener that never closes inside the body,
    and every bare fence run. `_fenced_lines` pairs fences across a whole
    file, so an opener left open here pairs with a matching bare run in
    any LATER entry of the same file and folds the headings between into
    this entry."""
    lines = body.split("\n")
    fenced = _fenced_lines(lines)
    opens, closes = [], []
    for j, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if m:
            run = (m.group(1)[0], len(m.group(1)))
            if not m.group(2).strip():
                closes.append(run)
            if not fenced[j] and not (run[0] == "`" and "`" in m.group(2)):
                opens.append(run)
    return opens, closes


def _closes_any(closes: list, pending: list) -> bool:
    return any(c == pc and w >= pw for c, w in closes for pc, pw in pending)


def _layout(entries: list, names: dict) -> list:
    """Pure. `entries` is the WHOLE family, newest first, each `(num,
    suffix, body)`. Packs from scratch every time, so the same entries
    always give the same layout. Returns `[(pos, [entries], bytes), ...]`,
    main first, `bytes` being the file's measured size: the main file keeps
    as many of the newest entries as fit under `READ_TOKEN_WARN` (always at
    least one), and the rest pack greedily into archive parts under
    `READ_PAGE_CAP_TOKENS`, one whole entry at a time. A file holding a
    single entry larger than its budget keeps it whole: no layout can do
    better. A file also ends before an entry that would close a fence an
    earlier entry of that file leaves open, so every file reads back as the
    entries planned for it.

    Each entry is measured once and the file sizes are running sums: the
    measure is additive over concatenation, so the layout is the one a
    re-measure of every candidate file would give."""
    sizes = [_measure(_render_entries([e]))[0] for e in entries]
    head = {key: _measure(_render(max(key, 0), [], names, key < 0))[0] for key in (-1, 0, 1, 2)}
    runs = [_fence_runs(body) for _n, _s, body in entries]
    n, limit, pending = len(entries), len(entries), []
    for i, (opens, closes) in enumerate(runs):
        if _closes_any(closes, pending):
            limit = i
            break
        pending += opens
    if limit == n and estimate_tokens(head[0] + sum(sizes)) < READ_TOKEN_WARN:
        return [(0, list(entries), head[0] + sum(sizes))]
    kept, used = 1, sizes[0]
    while kept < min(limit, n - 1) and estimate_tokens(head[-1] + used + sizes[kept]) < READ_TOKEN_WARN:
        used += sizes[kept]
        kept += 1
    layout = [(0, list(entries[:kept]), head[-1 if kept < n else 0] + used)]
    group, used, pending = [], 0, []
    for i in range(kept, n):
        pos = len(layout)
        opens, closes = runs[i]
        if group and (_closes_any(closes, pending)
                      or estimate_tokens(head[min(pos, 2)] + used + sizes[i]) >= READ_PAGE_CAP_TOKENS):
            layout.append((pos, group, head[min(pos, 2)] + used))
            group, used, pending = [], 0, []
        group.append(entries[i])
        used += sizes[i]
        pending += opens
    if group:
        layout.append((len(layout), group, head[min(len(layout), 2)] + used))
    return layout


def _render_checked(pos: int, group: list, names: dict, older: bool) -> str:
    """`_render`, then the text read back through the parser. A file that
    would not read back as exactly `group` -- a heading folded into a
    fence, a body line taken for the pointer, a heading-shaped body line --
    raises `Refusal` naming the file and the first entry that would change,
    before anything is written."""
    name = _file_name(pos, names)
    text = _render(pos, group, names, older)
    try:
        back = _parse_changelog_body(text, name, names["older_re"] if pos == 0 else None)[0]
    except Refusal as exc:
        raise Refusal(f"{name}: the planned file would not read back ({exc}); nothing was written") from exc
    if back != group:
        k = next((i for i, (a, b) in enumerate(zip(group, back)) if a != b), min(len(group), len(back)))
        num = (group[k] if k < len(group) else back[k])[0]
        raise Refusal(f"{name}: the planned file would not read back as the entries planned for it: Entry {num} "
                      f"would change ({len(group)} entries planned, {len(back)} read back); nothing was written")
    return text


def render_family(entries: list, naming, index_name: str, year: str) -> list:
    """`[(filename, text), ...]`, main first, `\\n` text: `entries` (the
    whole family, newest first, bodies in `canonical_body` form) laid out,
    rendered and read back by this module's engine. The migrator writes a
    new family through it, so the next `plan_split` finds nothing to move."""
    names = _names(naming, index_name, year)
    layout = _layout(entries, names)
    return [(_file_name(pos, names), _render_checked(pos, group, names, pos == 0 and len(layout) > 1))
            for pos, group, _b in layout]


def _oversized(layout: list, names: dict) -> list:
    """Each layout file still over its own budget -- always a file holding
    one entry larger than the budget by itself."""
    out = []
    for pos, group, nbytes in layout:
        budget = READ_TOKEN_WARN if pos == 0 else READ_PAGE_CAP_TOKENS
        tokens = estimate_tokens(nbytes)
        if tokens >= budget:
            out.append({"file": _file_name(pos, names), "entry": group[0][0], "tokens": tokens,
                        "budget": budget})
    return out


def _write_order(paths: list, old_home: list, new_home: list, added: int) -> list:
    """`paths` (layout order) reordered so each file an entry moves INTO is
    written before the file that entry leaves: a failure part-way then
    leaves an entry in two files, never in none. `old_home[k]` is the file
    old entry k sat in, `new_home[k + added]` the file it lands in. The
    two layouts are order-preserving partitions of one sequence, so the
    constraints never cycle; ties go back to front."""
    after = {p: set() for p in paths}
    for k, src in enumerate(old_home):
        dst = new_home[k + added]
        if src != dst and src in after and dst in after:
            after[src].add(dst)
    ordered, left = [], list(paths)
    while left:
        ready = [p for p in reversed(left) if not (after[p] & set(left))]
        pick = ready[0] if ready else left[-1]
        ordered.append(pick)
        left.remove(pick)
    return ordered


def _plan_writes(family: dict, entries: list, added: int = 0) -> tuple:
    """Lay out `entries` (the whole new family, newest first; its last
    `len(entries) - added` items are the parsed family's entries in order,
    possibly renumbered) and diff the layout against the files on disk.
    Returns `(plan, oversized)`; `plan` is None when every file already
    holds its planned entries -- the converged case, where the only files
    still over budget each hold one entry that is larger by itself. Raises
    `Refusal` when a file it would write does not read back
    (`_render_checked`)."""
    names = family["names"]
    layout = _layout(entries, names)
    lessons_dir = family["lessons_dir"]
    per_file = {f["path"]: f for f in family["per_file"]}
    main_style = (family["per_file"][0]["bom"], family["per_file"][0]["nl"])
    texts = {}
    for pos, group, _nbytes in layout:
        path = lessons_dir / _file_name(pos, names)
        older = pos == 0 and len(layout) > 1
        on_disk = per_file.get(path)
        if on_disk is not None and on_disk["entries"] == group and (
                pos != 0 or on_disk["pointer"] == (_pointer(names) if older else "")):
            continue  # untouched: left byte-identical
        bom, nl = (on_disk["bom"], on_disk["nl"]) if on_disk is not None else main_style
        text = _render_checked(pos, group, names, older)
        texts[path] = bom + (text if nl == "\n" else text.replace("\n", nl))
    planned = {lessons_dir / _file_name(pos, names) for pos, _g, _b in layout}
    remove = [p for p in family["files"] if p not in planned]
    oversized = _oversized(layout, names)
    if not texts and not remove:
        return None, oversized
    old_home = [f["path"] for f in family["per_file"] for _e in f["entries"]]
    new_home = [lessons_dir / _file_name(pos, names) for pos, group, _b in layout for _e in group]
    order = _write_order(list(texts), old_home, new_home, added)
    return {"outputs": [(p, texts[p]) for p in order], "remove": remove,
            "targets": [p for p in order if p.is_file()] + remove,
            "kind": "split", "parts": len(layout), "entries": len(entries), "renumbered": 0}, oversized


# --------------------------------------------------------------------------
# Gather the whole on-disk family
# --------------------------------------------------------------------------

def _existing_archive_main(lessons_dir: Path, stem: str) -> Path | None:
    """The one `{stem}-Archive-{YYYY}.md` file on disk: exactly four year
    digits and nothing else, so a `-Part-NN` continuation or a stray
    `-Archive-2026_bak.md` never matches. `None` when no archive exists.
    With several years on disk the highest is the active archive; an older
    year's files are never read or rewritten."""
    archive_re = re.compile(rf"^{re.escape(stem)}-Archive-\d{{4}}\.md$")
    candidates = sorted(p for p in lessons_dir.glob(f"{stem}-Archive-*.md") if archive_re.match(p.name))
    return candidates[-1] if candidates else None


def _archive_parts(lessons_dir: Path, stem: str, year: str) -> list:
    """Every `{stem}-Archive-{year}-Part-NN.md` on disk with NN >= 2, in
    numeric order, found by glob -- a missing part in the middle never
    hides the parts after it."""
    part_re = re.compile(rf"^{re.escape(stem)}-Archive-{year}-Part-(\d{{2,}})\.md$")
    found = []
    for p in lessons_dir.glob(f"{stem}-Archive-{year}-Part-*.md"):
        m = part_re.match(p.name)
        if m and int(m.group(1)) >= 2:
            found.append((int(m.group(1)), p))
    return [p for _k, p in sorted(found)]


def _locate_family_files(index_path: Path, changelog_name: str, year: str | None = None) -> tuple:
    """Every file in the family that exists on disk, in file order (main,
    archive part 1, further parts), located by naming convention ALONE --
    no file is opened, let alone parsed. The archive names come from the
    writer's own namer (`_archive_base`). Returns `(files, archive_year)`:
    `files` is `[]` when the main file itself does not exist yet;
    `archive_year` is the year embedded in an existing archive filename
    (part 1, else the newest orphan `-Part-NN`), or `year` (default: this
    run's own date's year) when no archive exists yet."""
    year = year or _today()[:4]
    lessons_dir = Path(index_path).parent
    main_path = lessons_dir / changelog_name
    if not main_path.is_file():
        return [], year
    stem = _archive_base(_index_naming(Path(index_path)), changelog_name)
    archive_main = _existing_archive_main(lessons_dir, stem)
    if archive_main is not None:
        archive_year = _ARCHIVE_YEAR_RE.search(archive_main.stem).group(1)
    else:
        orphan_re = re.compile(rf"^{re.escape(stem)}-Archive-(\d{{4}})-Part-\d{{2,}}\.md$")
        years = sorted(m.group(1) for p in lessons_dir.glob(f"{stem}-Archive-*-Part-*.md")
                       if (m := orphan_re.match(p.name)))
        archive_year = years[-1] if years else year
    files = [main_path] + ([archive_main] if archive_main else [])
    return files + _archive_parts(lessons_dir, stem, archive_year), archive_year


def _within_budget(texts: list) -> bool:
    """True when every family file measures within its own budget, from its
    raw text ALONE -- never parsed (the backlog resplit's measure-before-
    parse order). The main file (index 0) against `READ_TOKEN_WARN`, every
    archive/part file against `READ_PAGE_CAP_TOKENS`: the layout's limits."""
    return all(_tokens(t) < (READ_TOKEN_WARN if i == 0 else READ_PAGE_CAP_TOKENS)
               for i, t in enumerate(texts))


def _gather(index_path: Path, year: str | None = None) -> dict:
    """Locate and read every file in the family; nothing is parsed yet.
    `year` stamps a new archive (`_locate_family_files`). Raises
    `FileNotFoundError` if the main file is missing (the caller turns that
    into a naming refusal)."""
    naming = _index_naming(index_path)
    changelog_name = _changelog_filename(naming)
    lessons_dir = Path(index_path).parent
    files, archive_year = _locate_family_files(index_path, changelog_name, year)
    if not files:
        raise FileNotFoundError(str(lessons_dir / changelog_name))
    return {"naming": naming, "index_name": Path(index_path).name, "changelog_name": changelog_name,
            "files": files, "texts": [read_text(p) for p in files], "archive_year": archive_year,
            "lessons_dir": lessons_dir, "names": _names(naming, Path(index_path).name, archive_year)}


def _parse_family(family: dict) -> dict:
    """Parse every gathered file. Raises `Refusal` if any file carries
    foreign content. Adds `per_file` (each file's entries, trailing
    pointer, BOM and newline style) and the flattened `entries`."""
    per_file = []
    for k, (path, text) in enumerate(zip(family["files"], family["texts"])):
        entries, pointer = _parse_changelog_body(text, str(path), family["names"]["older_re"] if k == 0 else None)
        per_file.append({"path": path, "entries": entries, "pointer": pointer,
                         "bom": BOM if text.startswith(BOM) else "", "nl": newline_of(text)})
    family["per_file"] = per_file
    family["entries"] = [e for f in per_file for e in f["entries"]]
    return family


def plan_split_with_info(config: dict, index_path: Path, year: str | None = None) -> tuple:
    """`(plan, info)`. `plan` is None when there is nothing to do; else
    `{"outputs": [(Path, text)] in write order, "remove", "targets", "kind",
    "parts", "entries", "renumbered"}`. `info` is `{"renumber": bool,
    "oversized": [{"file", "entry", "tokens", "budget"}]}`.

    A stable family within budget is decided from raw text alone and never
    parsed, so it can never be refused. An unstable family within budget is
    renumbered in place (`kind` "renumber"): only its heading numbers
    change. An over-budget family is parsed, renumbered when unstable, and
    re-laid out (`kind` "split"); when the best layout is what is already
    on disk, the family has converged and `plan` is None, with each
    oversized single entry in `info`. `year` stamps a new archive, as
    `--date` does for `--append`. Never writes."""
    family = _gather(index_path, year)
    numbers = [num for text in family["texts"] for num in _heading_numbers(text)]
    stable = _is_stable(numbers)
    info = {"renumber": not stable, "oversized": []}
    if _within_budget(family["texts"]):
        if stable:
            return None, info
        counter = iter(range(len(numbers), 0, -1))
        outputs = []
        for path, text in zip(family["files"], family["texts"]):
            new = _renumber_text(text, counter)
            if new != text:
                outputs.append((path, new))
        return {"outputs": outputs, "remove": [], "targets": [p for p, _t in outputs], "kind": "renumber",
                "parts": len(family["files"]), "entries": len(numbers), "renumbered": len(numbers)}, info
    _parse_family(family)
    entries = family["entries"] if stable else _renumbered(family["entries"])
    plan, info["oversized"] = _plan_writes(family, entries)
    if plan is not None and not stable:
        plan["renumbered"] = len(entries)
    return plan, info


def plan_split(config: dict, index_path: Path):
    """The `--split` plan (`plan_split_with_info`'s plan alone).
    `lessons_migration.py` calls this on the branch that finds an
    already-generated index. Never writes."""
    return plan_split_with_info(config, index_path)[0]


# --------------------------------------------------------------------------
# --append guards
# --------------------------------------------------------------------------

def _append_refusal(body: str) -> str | None:
    """Why the new entry's text would corrupt the family on the next parse,
    naming the offending line, or None. An unfenced `## Entry N` line would
    become a phantom entry; a fence that never closes would pair with a
    fence in an older entry and fold the headings between into this one; an
    unfenced `Older entries:` line reads as the file's own pointer."""
    lines = body.split("\n")
    fenced = _fenced_lines(lines)
    for j, line in enumerate(lines):
        if fenced[j]:
            continue
        where = f"line {j + 1} of the new entry's text"
        if _ENTRY_HEADING_RE.match(line.strip()):
            return f"{where} is an unfenced '## Entry N' heading, which would split off a phantom entry: {line!r}"
        m = _FENCE_RE.match(line)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            return f"{where} opens a code fence that never closes: {line!r}"
        if _OLDER_RE.match(line.strip()):
            return f"{where} is an 'Older entries:' pointer line, which only the writer places: {line!r}"
    return None


def index_refusal(index_path: Path) -> str | None:
    """Why the lessons index beside the family bars a changelog write, or
    None when it is generated. Beside a hand-authored, unrecognised or
    missing index the family is still the migrator's to fill: a write here
    would make a header-only seed non-empty, and the migration would then
    refuse that file as foreign. Keyed on the migrator's own shape
    classifier, `migrate_lessons_support.classify_shape`."""
    try:
        shape, detail = classify_shape(read_text(index_path))
    except FileNotFoundError:
        return f"the lessons index {index_path} does not exist"
    except (OSError, UnicodeDecodeError) as exc:
        return f"the lessons index {index_path} could not be read: {exc}"
    return None if shape == "generated" else f"the lessons index {index_path} is {shape}, not generated ({detail})"


def _valid_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# Write: backups, safe order, rollback
# --------------------------------------------------------------------------

def _write_with_backups(plan: dict, config: dict, backup_dir: Path, day: str, action: str) -> tuple:
    """Back up, write and, on failure, roll back through
    `lessons_migration.write_with_dispositions` -- the same backup-then-log
    path `promotion_log.py`'s century-file creation and stale-listing
    repair share, never a second scheme invented here. Returns `(ok,
    report)`."""
    import lessons_migration  # deferred: lessons_migration imports this module

    header = ("# Manual changelog write dispositions\n\n"
             "Pre-change copies of every file this write replaced or removed live\n"
             "alongside this log, mirroring their lessons-directory paths.\n\n")
    return lessons_migration.write_with_dispositions(
        plan, config, backup_dir, day, action,
        "re-run the same lessons_changelog.py command", header)


def _failed(report, js: bool) -> int:
    return _say(1, f"REFUSED: {report.state}: {report.detail}\nbackups: {report.backup_dir}\nfix: {report.fix}",
                js, err=True)


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--append")
    g.add_argument("--append-file", type=Path)
    g.add_argument("--split", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today (the archive's year stamp)")
    args = p.parse_args(argv)
    js = args.json

    if args.date is not None and not _valid_date(args.date):
        return _say(1, f"REFUSED: --date {args.date!r} is not YYYY-MM-DD", js, err=True)
    config = load_config(Path(__file__), config_path=args.config)
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")
    if lessons_dir is None or index_path is None:
        return _say(1, "REFUSED: config.yaml declares no project.lessons_dir", js, err=True)
    index_path = Path(index_path)
    day = args.date or _today()
    backups_root = Path(config["_planwise_root"]) / "upgrade-backups"

    script_dir = Path(__file__).resolve().parent
    seed_cmd = f"python {script_dir / 'migrate_lessons_index.py'} --config {args.config} --write"
    split_cmd = f"python {script_dir / 'lessons_changelog.py'} --config {args.config} --split"

    def _missing(exc) -> int:
        return _say(2, f"REFUSED: the lessons changelog does not exist at {exc}; "
                      f"run /planwise upgrade (or {seed_cmd}) to migrate the lessons index and "
                      "seed it, or /planwise init on a fresh project", js, err=True)

    why = index_refusal(index_path)
    if why:
        return _say(1, f"REFUSED: {why}; run /planwise upgrade to migrate the lessons index first (the "
                       "migration writes this changelog family itself), then re-run this command", js, err=True)

    if args.split:
        # plan_split_with_info measures the family by raw bytes before it
        # ever parses a line, so a stable within-budget family reaches
        # "changelog within budget" without a parse.
        try:
            plan, info = plan_split_with_info(config, index_path, day[:4])
        except FileNotFoundError as exc:
            return _missing(exc)
        except (Refusal, UnicodeDecodeError) as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        if plan is None:
            if not info["oversized"]:
                return _say(0, "changelog within budget", js)
            big = "; ".join(f"{o['file']} holds Entry {o['entry']} alone at {o['tokens']} tokens "
                            f"(budget {o['budget']})" for o in info["oversized"])
            return _say(0, f"changelog already split as far as it can be: {big}", js)
        if args.dry_run:
            payload = {"kind": plan["kind"], "renumbered": plan["renumbered"],
                       "outputs": [str(p) for p, _t in plan["outputs"]],
                       "remove": [str(p) for p in plan["remove"]]}
            if js:
                print(json.dumps(payload, indent=2))
            else:
                print("\n".join([f"would write {p.name}" for p, _t in plan["outputs"]]
                                + [f"would remove {p.name}" for p in plan["remove"]]))
            return 0
        backup_dir = backups_root / f"manual-split-{day}" / "lessons"
        ok, report = _write_with_backups(plan, config, backup_dir, day, "lessons-changelog-split")
        if not ok:
            return _failed(report, js)
        regen = f"python {script_dir / 'generate_lessons_index.py'} --config {args.config} --check"
        if js:
            print(json.dumps({"written": len(plan["outputs"]), "removed": len(plan["remove"]),
                              "renumbered": plan["renumbered"], "backup_dir": str(backup_dir)}, indent=2))
        else:
            if plan["renumbered"]:
                print(f"RENUMBERED: {plan['renumbered']} entries by position (the oldest is Entry 1).")
            if plan["kind"] == "split":
                print(f"WROTE: {len(plan['outputs'])} changelog part(s), re-split within budget.")
            else:
                print(f"WROTE: {len(plan['outputs'])} changelog file(s); only heading numbers changed.")
            print(f"Backups: {backup_dir}")
            print(f"Confirm the pointer still resolves: {regen}")
        return 0

    # --append always needs the family's own entries (to compute the next
    # number and to prepend under), so this path always parses.
    try:
        family = _parse_family(_gather(index_path, day[:4]))
    except FileNotFoundError as exc:
        return _missing(exc)
    except (Refusal, UnicodeDecodeError) as exc:
        return _say(1, f"REFUSED: {exc}", js, err=True)
    numbers = [num for num, _s, _b in family["entries"]]
    if not _is_stable(numbers):
        return _say(1, "REFUSED: the changelog's entry numbers do not strictly descend from the newest "
                       f"entry to the oldest ({', '.join(str(n) for n in numbers[:8])}"
                       f"{', ...' if len(numbers) > 8 else ''}), so a new number would extend a mixed "
                       f"scheme; renumber the family once with {split_cmd} (or /planwise upgrade), "
                       "then append", js, err=True)

    if args.append is not None:
        new_text = args.append
    else:
        try:
            new_text = args.append_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return _say(1, f"REFUSED: could not read --append-file {args.append_file}: {exc}", js, err=True)
    new_body = canonical_body(new_text)
    if not new_body.strip():
        return _say(1, "REFUSED: the new entry's text is empty", js, err=True)
    why = _append_refusal(new_body)
    if why:
        return _say(1, f"REFUSED: {why}", js, err=True)

    if family["entries"] and canonical_body(family["entries"][0][2]) == new_body:
        return _say(1, f"REFUSED: the newest entry, Entry {numbers[0]}, already holds this text; "
                       "a retried --append would add it twice", js, err=True)

    new_number = (numbers[0] if numbers else 0) + 1
    # Every other heading in a family reads `## Entry N — {date or title}`;
    # a bare `## Entry N` was the one shape with no suffix at all. The
    # schema (`references/lessons-schema.md` Changelog Contract) requires
    # only `## Entry N`, so a suffix is not forbidden -- this uses the
    # append's own date (`day`, above: `--date`, else today), the same
    # value that stamps the archive year and the backup directory.
    entries = [(new_number, f" — {day}", new_body)] + family["entries"]
    try:
        plan, _oversized_now = _plan_writes(family, entries, added=1)
    except Refusal as exc:
        return _say(1, f"REFUSED: {exc}", js, err=True)
    outputs, remove = plan["outputs"], plan["remove"]

    if args.dry_run:
        payload = {"entry": new_number, "outputs": [str(p) for p, _t in outputs],
                   "remove": [str(p) for p in remove]}
        if js:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Would add Entry {new_number} and write: " + ", ".join(p.name for p, _t in outputs))
        return 0

    # Every append, a one-file one included, backs up its pre-image first.
    backup_dir = backups_root / f"manual-append-{day}" / "lessons"
    ok, report = _write_with_backups(plan, config, backup_dir, day, "lessons-changelog-append")
    if not ok:
        return _failed(report, js)

    main_path = family["files"][0]
    if js:
        print(json.dumps({"entry": new_number, "wrote": [str(p) for p, _t in outputs],
                          "removed": [str(p) for p in remove], "backup_dir": str(backup_dir)}, indent=2))
    else:
        print(f"Added Entry {new_number} to {main_path}")
        state = "changelog_split" if len(outputs) > 1 or remove else "generated"
        print(f"state: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
