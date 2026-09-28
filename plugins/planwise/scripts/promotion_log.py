#!/usr/bin/env python3
"""Guarded writer for the Rule Promotion Log: append one row.

The promotion log is five files (`migrate_lessons_support.log_destination`
routes a lesson id to its century file or the hub-side file). This script
is the one caller allowed to grow any of them by hand — it refuses a
duplicate `(lesson, artifact)` tuple, a malformed cell, and only the one
family-level condition a caller cannot fix by running this script again:
the hub-side file missing (the family was never migrated/seeded). A
century file that does not exist yet but whose hub-side sibling does (a
fresh id range, or a project whose family was migrated before this range
ever had a row) is CREATED on first use, with the same opener
`migrate_lessons_support.render_promotion_logs` writes — never hand-typed
— and the hub-side file's `Parts:` listing is updated to name it, in the
same format that renderer would produce. Line endings are preserved:
reading and writing go through `reconcile_common`'s newline-preserving
pair, so a CRLF file stays CRLF, and a newly created century file matches
the family's own newline style (read from the hub).

Usage:
    promotion_log.py --config CONFIG --lesson LL-NNN --artifact TEXT
                      --file PATH [--date YYYY-MM-DD] [--dry-run] [--json]

Exit codes: 0 = appended (or a clean `--dry-run`); 1 = refused (a duplicate
tuple, a malformed cell, or malformed existing content in the target file);
2 = the hub-side file does not exist (the family was never migrated/seeded).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import _index_naming
from config_loader import load_config
from migrate_lessons_support import (
    Refusal,
    _promotion_log_filename,
    log_destination,
    newline_of,
    render_promotion_logs,
    row_cells,
)
from parse_lessons import format_id
from reconcile_common import (
    read_text_preserving_newlines,
    write_text_preserving_newlines,
)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
_LESSON_ARG_RE = re.compile(r"^LL-(\d+)$")
_SEP_RE = re.compile(r"^\|[-\s|:]+\|$")
_LESSON_CELL_RE = re.compile(r"LL-(\d+)")


def _read_rows(text: str, dest_path: Path) -> list:
    """Every data row of an already-relocated promotion-log file: after its
    header separator, one `{Date, Lesson ID, Artifact Created, File}` row
    per line, tolerant of a blank line or a `Parts:` listing line before the
    separator. `migrate_lessons_support.walk_promotion_log` is built to
    extract rows from a LEGACY monolithic hub's `## Rule Promotion Log`
    section (`locate_regions`-based, keyed on that heading); a dedicated,
    already-relocated file carries no such heading at all -- confirmed
    against the shipped seed (`seed/00-PromotionLog-LessonsLearned.md`) and
    `render_promotion_logs`'s own output, neither of which ever emits one --
    so that function always returns `[]` here and cannot be reused for this
    shape. Returns `[{"line", "cells", "lesson_id"}, ...]`, 1-based line
    numbers. Raises `Refusal` naming `dest_path` and the line on a row that
    does not resolve to 3 or 4 cells, or has no parseable `LL-` id."""
    lines = text.replace("\r\n", "\n").split("\n")
    sep_hits = [i for i, ln in enumerate(lines) if _SEP_RE.match(ln.strip())]
    if not sep_hits:
        raise Refusal(f"{dest_path} has no recognised promotion-log table header/separator")
    rows = []
    for i in range(sep_hits[0] + 1, len(lines)):
        raw = lines[i]
        if not raw.strip() or not raw.lstrip().startswith("|"):
            continue
        cells = row_cells(raw)
        if len(cells) not in (3, 4):
            raise Refusal(f"{dest_path} line {i + 1} does not resolve to 3 or 4 cells: {raw!r}")
        m = _LESSON_CELL_RE.search(cells[1])
        if not m:
            raise Refusal(f"{dest_path} line {i + 1} has no parseable LL- id in its Lesson ID cell: {raw!r}")
        rows.append({"line": i + 1, "cells": tuple(cells), "lesson_id": int(m.group(1))})
    return rows


def _today() -> str:
    from datetime import datetime

    return datetime.now().astimezone().date().isoformat()


def _say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def _validate_cell(name: str, value: str) -> str | None:
    """None when `value` is a legal cell: non-empty, and any `|` in it is
    already escaped (`\\|`) by the caller. Otherwise the refusal detail."""
    if not value.strip():
        return f"--{name} is empty"
    if _UNESCAPED_PIPE_RE.search(value):
        return f"--{name} {value!r} carries an unescaped '|' — escape it as '\\|' first"
    return None


def _normalize_cell(value: str) -> str:
    """The form a stored cell and a fresh `--artifact` argument both compare
    equal under for the duplicate check: whitespace-trimmed, so `" x "` and
    `"x"` collide. `row_cells` already strips a value read back off disk
    (`_read_rows`'s `cells`); a fresh CLI argument is not stripped before
    this comparison without it, so the two sides silently disagreed on a
    duplicate that differs only in surrounding whitespace."""
    return value.strip()


def _render_row(date: str, lesson_id: int, artifact: str, file_: str) -> str:
    return f"| {date} | {format_id(lesson_id)} | {artifact} | {file_} |"


def _insert_after_last_row(text: str, rows: list, new_line: str) -> str:
    """Splice `new_line` in immediately after the last existing data row (or
    the separator, when the table has zero rows yet), preserving every other
    line -- including this file's own line endings -- byte for byte.

    `text` is split on its CRLF-normalized line breaks -- the same
    normalization `_read_rows` used to number `rows` in the first place --
    then rejoined with the file's own line ending. Splitting raw CRLF text
    on a bare `"\\n"` would leave each line's own trailing `\\r` in place,
    and rejoining those with `nl == "\\r\\n"` would then double it into
    `"\\r\\r\\n"` on every pre-existing line, not just the inserted one."""
    nl = newline_of(text)
    lines = text.replace("\r\n", "\n").split("\n")
    if rows:
        insert_after = max(r["line"] for r in rows) - 1  # 0-based index of the last row's line
    else:
        sep_hits = [i for i, ln in enumerate(lines) if _SEP_RE.match(ln.strip())]
        if not sep_hits:
            raise Refusal("the target file has no recognised promotion-log table header/separator")
        insert_after = sep_hits[0]
    lines.insert(insert_after + 1, new_line)
    return nl.join(lines)


_CENTURY_PROBE_IDS = (1, 51, 76, 101)  # one id per Archive century band


def _existing_archive_parts(lessons_dir: Path, naming) -> list:
    """The Archive century filenames that exist on disk right now, sorted
    ascending -- the same set and order `render_promotion_logs` lists in a
    hub's `Parts:` line. Derived by asking `log_destination` -- never
    hardcoding the band boundaries or the stem -- for one representative
    id per band, then checking which of those files are present."""
    names = {log_destination(i, naming) for i in _CENTURY_PROBE_IDS}
    return sorted(n for n in names if (lessons_dir / n).is_file())


def _with_parts_listing(hub_text: str, nl: str, archive_parts: list) -> str:
    """`hub_text` with its `Parts:` line reflecting `archive_parts`, in the
    same format `render_promotion_logs` renders (a `, `-joined list of
    `[name](name)` links) and the same placement -- the line right after
    the backlink. Added when the family has just grown its first Archive
    part, replaced when one already lists a different set, and never
    touching the header or the rows below it."""
    lines = hub_text.replace("\r\n", "\n").split("\n")
    body = [ln for ln in lines[1:] if not ln.startswith("Parts: ")]
    new_lines = [lines[0]]
    if archive_parts:
        listing = ", ".join(f"[{p}]({p})" for p in archive_parts)
        new_lines.append(f"Parts: {listing}")
    new_lines += body
    return nl.join(new_lines)


def _create_century_file(dest_path: Path, dest_name: str, hub_path: Path, hub_name: str,
                         naming, lesson_id: int, date: str, artifact: str, file_: str) -> None:
    """Create a missing Archive century file with the opener
    `render_promotion_logs` produces for a single-row destination -- never
    hand-typed -- carrying this promotion's one row, then update the
    hub-side file's `Parts:` listing to name it. Both writes use the
    family's own newline style, read from the hub (`newline_of`), so a
    CRLF family stays CRLF end to end."""
    hub_text = read_text_preserving_newlines(hub_path)
    nl = newline_of(hub_text)
    new_row = {"line": 0, "lesson_id": lesson_id,
              "cells": (date, format_id(lesson_id), artifact, file_)}
    rendered = dict(render_promotion_logs([new_row], naming, nl))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_preserving_newlines(dest_path, rendered[dest_name])
    archive_parts = _existing_archive_parts(hub_path.parent, naming)
    write_text_preserving_newlines(hub_path, _with_parts_listing(hub_text, nl, archive_parts))


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--lesson", required=True, help="LL-NNN")
    p.add_argument("--artifact", required=True)
    p.add_argument("--file", required=True, dest="file_")
    p.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    js = args.json

    m = _LESSON_ARG_RE.match(args.lesson.strip())
    if not m:
        return _say(1, f"REFUSED: --lesson {args.lesson!r} is not LL-NNN", js, err=True)
    lesson_id = int(m.group(1))

    date = args.date or _today()
    problems = []
    if args.date is not None and not _ISO_DATE_RE.match(args.date):
        problems.append(f"--date {args.date!r} is not YYYY-MM-DD")
    for name, value in (("artifact", args.artifact), ("file", args.file_)):
        detail = _validate_cell(name, value)
        if detail:
            problems.append(detail)
    if problems:
        return _say(1, "REFUSED: " + "; ".join(problems), js, err=True)

    config = load_config(Path(__file__), config_path=args.config)
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")
    if lessons_dir is None or index_path is None:
        return _say(1, "REFUSED: config.yaml declares no project.lessons_dir", js, err=True)

    naming = _index_naming(Path(index_path))
    try:
        dest_name = log_destination(lesson_id, naming)
    except Refusal as exc:
        return _say(1, f"REFUSED: {exc}", js, err=True)
    dest_path = Path(lessons_dir) / dest_name

    script_dir = Path(__file__).resolve().parent
    seed_cmd = f"python {script_dir / 'migrate_lessons_index.py'} --config {args.config} --write"
    hub_name = _promotion_log_filename(naming)
    hub_path = Path(lessons_dir) / hub_name

    if not hub_path.is_file():
        detail = (f"the promotion-log file for {args.lesson} does not exist at {dest_path}; "
                  f"run /planwise upgrade (or, from this tree, {seed_cmd}) to migrate the lessons "
                  "index and create the Archive century files, or /planwise init on a fresh project")
        return _say(2, f"REFUSED: {detail}", js, err=True)

    # A missing Archive century file whose hub-side sibling exists is a fresh id
    # range, or a family migrated before this range ever had a row -- created
    # on first use below, never refused. Only the hub itself missing (already
    # handled above) means the family was never migrated/seeded at all.
    creating = not dest_path.is_file()
    if creating:
        rows = []
    else:
        text = read_text_preserving_newlines(dest_path)
        try:
            rows = _read_rows(text, dest_path)
        except Refusal as exc:
            return _say(1, f"REFUSED: {dest_path} already carries malformed content: {exc}", js, err=True)

    for row in rows:
        if row["lesson_id"] == lesson_id and _normalize_cell(row["cells"][2]) == _normalize_cell(args.artifact):
            return _say(1, f"REFUSED: {args.lesson} / {args.artifact!r} is already logged at "
                          f"{dest_path} line {row['line']}", js, err=True)

    new_line = _render_row(date, lesson_id, args.artifact, args.file_)

    if args.dry_run:
        action = "would-create-and-append" if creating else "would-append"
        payload = {"lesson": args.lesson, "artifact": args.artifact, "file": args.file_,
                  "target": str(dest_path), "row": new_line, "action": action}
        if js:
            print(json.dumps(payload, indent=2))
        else:
            verb = "create and append to" if creating else "append to"
            print(f"Would {verb} {dest_path}:\n  {new_line}")
        return 0

    if creating:
        _create_century_file(dest_path, dest_name, hub_path, hub_name,
                             naming, lesson_id, date, args.artifact, args.file_)
    else:
        try:
            new_text = _insert_after_last_row(text, rows, new_line)
        except Refusal as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        write_text_preserving_newlines(dest_path, new_text)

    regen = f"python {script_dir / 'generate_lessons_index.py'} --config {args.config} --write"
    payload = {"lesson": args.lesson, "artifact": args.artifact, "file": args.file_,
              "target": str(dest_path), "row": new_line, "action": "appended"}
    if js:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Appended 1 row to {dest_path}")
        print(f"Regenerate the index: {regen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
