#!/usr/bin/env python3
"""Relocation helpers for `migrate_lessons_index.py`.

Three things the migrator used to refuse now move into the changelog or the
notes file, byte for byte: a Master Table row whose id resolves to no lesson
file; a Rule Promotion Log table it does not recognise, or a row that is not
three or four cells; a foreign file already at the changelog, promotion-log
or notes path. This module plans text and writes nothing, except
`keep_foreign_copies`. The renderer rewrites line endings, so a foreign text
is held out as a stand-in while the changelog renders (`hold`) and put back
afterwards (`release`).
"""
import re
import shutil

import migrate_lessons_support as sup
from reconcile_common import read_text_preserving_newlines as read_text

FOLD_TITLE = "Pre-migration changelog file (migrated {date})"
UNRESOLVED_HEADING = "Master Table row with no lesson file"
FOREIGN_LOG_HEADING = "Pre-migration promotion-log file"
COPY_SUFFIX = ".pre-migration.bak"

# The details `sup.walk_promotion_log` words for the refusals that relocate.
_TABLE_RE = re.compile(r"^promotion-log line (\d+) ")
_CELLS_RE = re.compile(r"^promotion-log row at line (\d+) does not resolve to 3 or 4 cells")
_OPEN, _CLOSE = chr(0xFDD0), chr(0xFDD1)  # noncharacters: never in real text


def unresolved_row_section(row_line: str, reason: str) -> dict:
    """The section for one Master Table row: `reason`, then the row unchanged."""
    return {"heading": UNRESOLVED_HEADING, "body": f"\n{reason}\n\n{row_line.rstrip(chr(13) + chr(10))}\n"}


def _is_header(line: str) -> bool:
    return line.strip().lower().replace(" ", "").startswith("|date|")


def _walked(text: str, lines: list) -> list:
    """The line indexes `walk_promotion_log` walks: its section, less the counter."""
    regions = sup.locate_regions(text)
    section = regions["sections"].get(sup.PROMOTION_LOG_HEADING)
    if section is None:
        return []
    counters = [(s, e) for kind, _name, s, e in regions["spans"] if kind == "counter"]
    offset = sum(len(ln) + 1 for ln in lines[:section["line_start"] + 1])
    walked = []
    for idx in range(section["line_start"] + 1, section["line_end"]):
        if not any(s <= offset < e for s, e in counters):
            walked.append(idx)
        offset += len(lines[idx]) + 1
    return walked


def split_log_refusals(text: str, log_refusals: list, kept: list) -> list:
    """Append to `kept` the refusals that stay refusals, and return the
    `(line_no, raw_line)` pairs of those that relocate. A refusal's span is
    what the walk consumed with it, inside its own section: a table's `|`
    lines, or a row and its continuation lines. A table refused for its
    separator keeps the header line the walk consumed before it."""
    lines = text.split("\n")
    walked = _walked(text, lines)
    moved, seen = [], set()
    for fix, detail in log_refusals:
        table, cells = _TABLE_RE.match(detail), _CELLS_RE.match(detail)
        start = int((table or cells).group(1)) - 1 if table or cells else -1
        if fix != sup.FIX_LOG_ROW or start not in walked:
            kept.append((fix, detail))
            continue
        pos = end = walked.index(start)
        while end + 1 < len(walked) and (
                lines[walked[end + 1]].lstrip().startswith("|") if table
                else lines[walked[end + 1]].strip() and not lines[walked[end + 1]].lstrip().startswith("|")):
            end += 1
        span = walked[pos:end + 1]
        if table and "follows the recognised header" in detail:
            span = [i for i in reversed(walked[:pos]) if _is_header(lines[i])][:1] + span
        moved += [(n + 1, lines[n]) for n in span if n not in seen]
        seen.update(span)
    return moved


def hold(raw: str, held: dict) -> str:
    """A one-line stand-in as long as `raw` in bytes, so layout budgets it."""
    token = f"{_OPEN}{len(held)}{_CLOSE}"
    shown = token + "x" * max(0, len(raw.encode("utf-8")) - len(token.encode("utf-8")))
    held[shown] = raw
    return shown


def release(text: str, held: dict) -> str:
    for shown, raw in held.items():
        text = text.replace(shown, raw)
    return text


def _fence(raw: str, nl: str, shown: str | None = None) -> str:
    """`raw` (or its stand-in `shown`) in a fence longer than any backtick
    run in `raw`, so a heading inside it stays text."""
    fence = "`" * max(4, 1 + max((len(run) for run in re.findall(r"`+", raw)), default=0))
    return f"{fence}markdown{nl}{raw if shown is None else shown}{nl}{fence}{nl}"


def _folds(text: str, lead: str, nl: str) -> list:
    """`(name, fenced text)` for each fenced block that follows a line
    matching the regex `lead`; `name` is its `n` group, if it has one."""
    pattern = lead + re.escape(nl * 2) + r"(?P<f>`{4,})markdown" + re.escape(nl) + r"(?P<t>.*?)" \
        + re.escape(nl) + r"(?P=f)" + re.escape(nl)
    return [(m.groupdict().get("n"), m.group("t")) for m in re.finditer(pattern, text, re.DOTALL)]


def earlier_changelog(path, today: str) -> str:
    """The changelog family's text (main file and archive parts) if an earlier
    run wrote this migration's relocated entry there, else ""."""
    files = [path, *sorted(path.parent.glob(f"{path.stem}-*{path.suffix}"))]
    text = "\n".join(read_text(p) for p in files if p.is_file())
    return text if sup._RELOCATED_TITLE.format(date=today) in text else ""


def foreign_text(path, planned_text: str, hub_name: str, today: str, nl: str):
    """None when `path` may be written as planned: absent, header-only, or
    already the planned text. Otherwise the foreign text to fold in, from
    this migration's own earlier fold when the file holds one."""
    if not path.exists():
        return None
    existing = read_text(path)
    if sup.header_only(existing, hub_name) or existing == planned_text:
        return None
    own = _folds(existing, re.escape(FOLD_TITLE.format(date=today)), nl)
    return existing if not own else own[0][1]


def _log_cells(line: str):
    """The cells of a promotion-log data row (three or four, a lesson id in
    the second), `()` for an empty placeholder row, else None."""
    s = line.strip()
    cells = sup.row_cells(s) if s.startswith("|") and s.endswith("|") else []
    if cells and sup.is_placeholder_row(cells):
        return ()
    lesson = re.search(r"LL-(\d+)", cells[1]) if len(cells) in (3, 4) else None
    return tuple(cells) if lesson and int(lesson.group(1)) >= 1 else None


def _split_log_text(text: str, hub_name: str) -> tuple:
    """`(rows, residue)` of a promotion-log file's text: the cells of each
    data row, and the text no row, placeholder row or generated opener
    accounts for. A text with no data row is all residue."""
    rows, left = [], []
    for n, line in enumerate(text.split("\n")):
        s, cells = line.strip(), _log_cells(line)
        if cells:
            rows.append(cells)
        elif cells is None and not (s == f"[← {hub_name}]({hub_name})" or sup._PARTS_LINE_RE.match(s)
                                    or _is_header(s) or sup._LOG_SEP_RE.match(s)):
            left.append((n + 1, line))
    return rows, (text if not rows and text.strip() else sup.promotion_log_residue(left)[0])


def fold_promotion_logs(sections: list, rows: list, lessons_dir, naming, nl: str, earlier: str, held: dict) -> tuple:
    """Fold each foreign file at a planned promotion-log path into the plan.
    A data row joins `rows` once. The rest of the text, or all of it when
    there is no row, becomes a residue section appended to `sections`. Text
    an earlier run folded (in the changelog text `earlier`) folds again, so
    a resume plans the same sections. Returns `(outputs, names, twins)`: the
    files to write, the names that gained content, and each appended
    section with its text held out for the renderer."""
    names, twins, done, folded = [], [], set(), set()
    known = {tuple(r["cells"]) + ("",) * (4 - len(r["cells"])) for r in rows}
    prior = _folds(earlier, re.escape(f"### {FOREIGN_LOG_HEADING} ") + r"(?P<n>[^\r\n]+)", nl)

    def absorb(name: str, text: str) -> None:
        found, residue = _split_log_text(text, naming.hub_name)
        gained = False
        for cells in found:
            key = cells + ("",) * (4 - len(cells))
            if key not in known:
                known.add(key)
                rows.append({"line": max((r["line"] for r in rows), default=0) + 1, "cells": cells,
                             "lesson_id": int(re.search(r"LL-(\d+)", cells[1]).group(1)),
                             "short": len(cells) == 3, "fragmented": False})
                gained = True
        if residue and (name, residue) not in folded:
            folded.add((name, residue))
            heading = f"{FOREIGN_LOG_HEADING} {name}"
            sections.append((heading, nl + _fence(residue, nl)))
            twins.append((heading, "\n" + _fence(residue, "\n", hold(residue, held))))
            gained = True
        if gained and name not in names:
            names.append(name)

    while True:
        fresh = [(n, t) for n, t in sup.render_promotion_logs(rows, naming, nl, lessons_dir) if n not in done]
        if not fresh:
            break
        for name, planned in fresh:
            done.add(name)
            path = lessons_dir / name
            disk = read_text(path) if path.exists() else ""
            texts = [disk] if disk and disk != planned and not sup.header_only(disk, naming.hub_name) else []
            for text in texts + [raw for n, raw in prior if n == name and raw not in texts]:
                absorb(name, text)
    for name, raw in prior:
        if name not in done:
            absorb(name, raw)
    return sup.render_promotion_logs(rows, naming, nl, lessons_dir), names, twins


def keep_foreign_copies(lessons_dir, names: list) -> list:
    """Copy each existing file in `names` to `{name}{COPY_SUFFIX}` beside it.
    The first copy wins, so a resume never replaces it with rewritten text.
    Returns `(file, copy, written)` per file, `written` False for a copy an
    earlier run kept."""
    kept = []
    for name in names:
        src, dst = lessons_dir / name, lessons_dir / (name + COPY_SUFFIX)
        if src.is_file():
            written = not dst.exists()
            if written:
                shutil.copy2(src, dst)
            kept.append((src, dst, written))
    return kept


def companion_dated_heading(existing_text: str, today: str) -> str:
    """`existing_text`, then the dated heading the companion text follows."""
    nl = sup.newline_of(existing_text)
    head = existing_text if existing_text.endswith("\n") or not existing_text else existing_text + nl
    return f"{head}{nl}## Companion migrated {today}{nl}{nl}"


def merge_into_notes(notes_text: str, companion_text: str, today: str) -> str:
    """The notes file after the hand-written companion moves into it. A
    notes file already holding this migration's merge stays as it is."""
    if f"## Companion migrated {today}" in notes_text and notes_text.endswith(companion_text):
        return notes_text
    return companion_dated_heading(notes_text, today) + companion_text


def as_relocations(sections: list, nl: str) -> list:
    """`(heading, body)` pairs with `nl` newlines."""
    return [(s["heading"], s["body"].replace("\n", nl)) for s in sections]


def unresolved_sections(text: str, unresolved: list) -> list:
    """One section per `(row, detail)` pair, the row verbatim from `text`."""
    lines = text.split("\n")
    return [unresolved_row_section(lines[row.line - 1], detail) for row, detail in unresolved]


def render_with_fold(path, segments: list, hub_name: str, today: str, nl: str, names: list, folds: list,
                     held: dict) -> list:
    """The changelog files for `segments`, held texts put back. A foreign
    file at `path` folds into `segments` as the newest entry first. Its name
    joins `names` and the text `verify_written` must find joins `folds`."""
    outputs = sup.render_changelog(segments, hub_name, nl, today) if segments else []
    planned = dict(outputs).get(path.name)
    foreign = None if planned is None else foreign_text(path, release(planned, held), hub_name, today, nl)
    if foreign is not None:
        segments.insert(0, FOLD_TITLE.format(date=today) + "\n\n" + _fence(foreign, "\n", hold(foreign, held)))
        names.append(path.name)
        folds.append(foreign)
        outputs = sup.render_changelog(segments, hub_name, nl, today)
    return [(name, release(text, held)) for name, text in outputs]
