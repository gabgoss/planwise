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
— and the hub-side file's Archive-parts listing is updated to name it, in
the hub's own existing listing form when it already carries one (`Parts: `,
the current writer's own form, or `Archive parts: `, an earlier migrator's
form — the two recognised on read; see `_parse_existing_listing`), else
the writer's own default form. Line endings are preserved: reading and
writing go through `reconcile_common`'s newline-preserving pair, so a CRLF
file stays CRLF, and a newly created century file matches the family's
own newline style (read from the hub).

Usage:
    promotion_log.py --config CONFIG --lesson LL-NNN --artifact TEXT
                      --file PATH [--date YYYY-MM-DD] [--dry-run] [--json]

Both modes refuse while the lessons index beside the family is not
generated: the migrator still owns the family then, exactly as
`lessons_changelog.py` refuses (`migrate_lessons_support.classify_shape`,
via `lessons_changelog.index_refusal`, imported once rather than
re-derived here).

Every write that replaces or grows an existing file -- an ordinary append
into an already-relocated century/hub file, century-file creation, and a
hub listing repair alike -- goes through `lessons_migration.
write_with_dispositions`, the same backup-then-log path
`lessons_changelog.py` uses: any file the call would replace is backed up
byte-exact first, under `upgrade-backups/manual-promotion-log-{day}/
lessons/`, where `{day}` is the day of the write, never `--date`, which
stamps the row only (first pre-image of the day wins, later same-day writes get a
numbered `.N.bak` sibling); a failure restores every touched file and
removes whatever this call created, and the caller sees a clean REFUSED
message, never a raw traceback; a success logs one DISPOSITIONS row per
file touched. An append routed to the hub itself brings that listing in
line with the century files on disk in the same write, and so does an
append into an existing century file when the hub's listing is stale or
missing. That append reads the hub to check its `Parts:` listing. A hub
that cannot be read (for example, not valid UTF-8) refuses the append
with REFUSED and writes nothing, the same as century-file creation and a
duplicate-row repair do. A re-run also repairs a hub listing a century file's
existence has outgrown, in its existing form, even when the row itself is
already logged — and a call that refuses for any other reason (a
duplicate, an unreadable index) writes nothing unless the listing was
truly stale.

Exit codes: 0 = appended (or a clean `--dry-run`); 1 = refused (the lessons
index is not generated, a duplicate tuple, a malformed cell, malformed
existing content in the target file, or a backup/write failure -- always
rolled back first); 2 = the hub-side file does not exist (the family was
never migrated/seeded).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import _index_naming
from config_loader import load_config
from migrate_lessons_support import (
    Refusal,
    _existing_archive_parts,
    _promotion_log_filename,
    century_log_filenames,
    log_destination,
    newline_of,
    render_promotion_logs,
    row_cells,
)
from parse_lessons import format_id
from reconcile_common import read_text_preserving_newlines

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


def _valid_date(value: str) -> bool:
    """True when `value` is `YYYY-MM-DD` AND a real calendar date, so
    `2026-02-30` is refused rather than stamped into a row."""
    from datetime import date

    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _read_text(path: Path) -> str:
    """`path`'s text, line endings preserved. An unreadable or non-UTF-8
    file raises `Refusal` naming it, so the caller prints the REFUSED
    message instead of a traceback."""
    try:
        return read_text_preserving_newlines(path)
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"{path} could not be read: {exc}") from exc


def _say(code: int, msg: str, json_mode: bool, err: bool = False) -> int:
    print(msg, file=sys.stderr if (err or json_mode) else sys.stdout)
    return code


def _validate_cell(name: str, value: str) -> str | None:
    """None when `value` is a legal cell: non-empty, on one line, and any
    `|` in it is already escaped (`\\|`) by the caller. Otherwise the
    refusal detail. A line break would split the rendered row across two
    table lines."""
    if not value.strip():
        return f"--{name} is empty"
    if "\n" in value or "\r" in value:
        return f"--{name} {value!r} carries a line break — a table row must stay on one line"
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


# Two listing forms are recognised on a hub's Archive-parts line: `Parts: `
# (the current writer's own form, `migrate_lessons_support.
# render_promotion_logs`, comma-space separated, visible link text equal to
# the href) and `Archive parts: ` (an earlier migrator's form -- not
# produced anywhere in the current tree, but still carried by a hub that
# was migrated under it, middle-dot separated, visible link text just the
# href's filename). The seed (`seed/00-PromotionLog-LessonsLearned.md`)
# carries no listing line at all, since a fresh family starts with zero
# Archive parts. No third form has been found in either.
_LISTING_PREFIXES = ("Archive parts: ", "Parts: ")
_LISTING_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")


def _parse_existing_listing(line: str):
    """`(prefix, separator, style)` read back from `line` when it is an
    Archive-parts listing line, else None. `style` is `'full'` (the first
    link's visible text equals its href -- the current writer's form) or
    `'basename'` (the visible text is just the href's filename -- the
    earlier form); a link matching neither falls back to `'full'` rather
    than guessing a third scheme. `separator` is read from between the
    first two links when there are at least two, else the writer's own
    default (`, `) -- so a single-entry listing still repairs in the
    writer's own separator once it grows a second part."""
    for prefix in _LISTING_PREFIXES:
        if not line.startswith(prefix):
            continue
        rest = line[len(prefix):]
        links = list(_LISTING_LINK_RE.finditer(rest))
        if not links:
            return prefix, ", ", "full"
        text, href = links[0].group(1), links[0].group(2)
        style = "basename" if text == Path(href).name and text != href else "full"
        sep = rest[links[0].end():links[1].start()] if len(links) > 1 else ", "
        return prefix, sep, style
    return None


def _listing_hrefs(hub_text: str):
    """The hrefs, in order, that the hub's Archive-parts listing line names
    (the same line `_with_parts_listing` rewrites: the first line after the
    first that `_parse_existing_listing` recognises), or None when the hub
    carries no listing line. Line endings play no part in the answer."""
    for line in hub_text.replace("\r\n", "\n").split("\n")[1:]:
        parsed = _parse_existing_listing(line)
        if parsed is not None:
            return [m.group(2) for m in _LISTING_LINK_RE.finditer(line[len(parsed[0]):])]
    return None


def _with_parts_listing(hub_text: str, nl: str, archive_parts: list) -> str:
    """`hub_text` with its Archive-parts listing line reflecting
    `archive_parts`. A listing line already present is rewritten IN PLACE,
    on its own existing line, keeping its own prefix, its own separator
    and its own link-text style (`_parse_existing_listing`) -- never
    replaced by the writer's own default form and never duplicated onto a
    second line. Only when the hub carries no listing line at all does a
    fresh one get the writer's default form (`Parts: `, comma-space
    separated, link text equal to the href) inserted right after the
    backlink. A hub of one uniform line ending whose listing already names
    exactly `archive_parts` comes back byte-identical. A hub that mixes
    line endings does not (every line is rejoined with `nl`), so a caller
    deciding "nothing to repair" must use `_stale_parts_repair`, not
    equality."""
    lines = hub_text.replace("\r\n", "\n").split("\n")
    existing_idx = None
    prefix, sep, style = "Parts: ", ", ", "full"
    for i in range(1, len(lines)):
        parsed = _parse_existing_listing(lines[i])
        if parsed is not None:
            existing_idx = i
            prefix, sep, style = parsed
            break

    def _link(p: str) -> str:
        text = Path(p).name if style == "basename" else p
        return f"[{text}]({p})"

    new_line = f"{prefix}{sep.join(_link(p) for p in archive_parts)}" if archive_parts else None
    new_lines = list(lines)
    if existing_idx is not None:
        if new_line is None:
            del new_lines[existing_idx]
        else:
            new_lines[existing_idx] = new_line
    elif new_line is not None:
        new_lines.insert(1, new_line)
    return nl.join(new_lines)


def _write_backed_up(outputs: list, config: dict, backups_root: Path, day: str, action: str) -> tuple:
    """Write `outputs` (`[(path, text), ...]`) all-or-nothing, through
    `lessons_migration.write_with_dispositions` -- the same backup-then-log
    path every `lessons_changelog.py` write already goes through, never a
    second scheme invented here. Any file this call would replace is
    backed up byte-exact under `backups_root` first; a failure restores
    every touched file to its pre-image and removes whatever this call
    created; a success adds one DISPOSITIONS row per file it touched,
    under the `manual-promotion-log-{day}` directory, `day` being the day
    of the write (the caller's `write_day`). Returns `(ok, report)`; a failed
    `report` becomes a clean REFUSED message (`_failed`), never a raw
    traceback."""
    import lessons_migration  # deferred: avoids a circular import at module load

    backup_dir = backups_root / f"manual-promotion-log-{day}" / "lessons"
    plan = {"outputs": outputs, "remove": []}
    header = ("# Manual promotion-log write dispositions\n\n"
             "Pre-change copies of every file this write replaced or removed live\n"
             "alongside this log, mirroring their lessons-directory paths.\n\n")
    return lessons_migration.write_with_dispositions(
        plan, config, backup_dir, day, action,
        "re-run the same promotion_log.py command", header)


def _failed(report, js: bool) -> int:
    return _say(1, f"REFUSED: {report.state}: {report.detail}\nbackups: {report.backup_dir}\nfix: {report.fix}",
               js, err=True)


def _century_outputs(dest_path: Path, dest_name: str, hub_path: Path, naming,
                     lesson_id: int, date: str, artifact: str, file_: str) -> tuple:
    """The two `(path, text)` outputs a century-file creation writes: the
    opener `render_promotion_logs` produces for a single-row destination --
    never hand-typed -- carrying this promotion's one row, and the hub with
    its Archive-parts listing updated to name it (added to whatever century
    files already exist on disk -- `dest_path` itself does not exist yet,
    so it never shows up in that scan on its own), in the hub's own
    existing listing form when it already carries one, else the writer's
    own default form. Both use the family's
    own newline style, read from the hub (`newline_of`), so a CRLF family
    stays CRLF end to end. Only computes text; `_write_backed_up` is what
    actually writes, atomically, and the caller creates the Archive
    directory. Raises `Refusal` when the hub cannot be read."""
    hub_text = _read_text(hub_path)
    nl = newline_of(hub_text)
    new_row = {"line": 0, "lesson_id": lesson_id,
              "cells": (date, format_id(lesson_id), artifact, file_)}
    rendered = dict(render_promotion_logs([new_row], naming, nl))
    archive_parts = sorted(set(_existing_archive_parts(hub_path.parent, naming)) | {dest_name})
    new_hub_text = _with_parts_listing(hub_text, nl, archive_parts)
    return (dest_path, rendered[dest_name]), (hub_path, new_hub_text)


def _stale_parts_repair(hub_path: Path, naming) -> str | None:
    """The hub's own text with its Archive-parts listing brought in line
    with the century files that actually exist on disk, in its own
    existing form, or None when it already names exactly that set (not
    stale). A century file created outside a normal write here (an earlier
    interrupted run, a hand edit) can leave this drifted; the caller
    repairs it -- backed up, same as any other write -- instead of only
    refusing whatever this run was asked to do. Raises `Refusal` when the
    hub cannot be read."""
    hub_text = _read_text(hub_path)
    nl = newline_of(hub_text)
    archive_parts = _existing_archive_parts(hub_path.parent, naming)
    # Decide staleness from the listing, not the whole text: the repair
    # rejoins every line with one line ending, so a hub that mixes LF and
    # CRLF would never compare equal to its own repair even with a correct
    # listing, and would be rewritten and backed up on every call.
    listed = _listing_hrefs(hub_text)
    if listed is None and not archive_parts:
        return None  # no listing and nothing to list
    if archive_parts and listed == archive_parts:
        return None  # the listing already names exactly the parts on disk
    repaired = _with_parts_listing(hub_text, nl, archive_parts)
    return repaired if repaired != hub_text else None


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

    # `date` stamps the row only. The backup directory and the DISPOSITIONS
    # line carry `write_day`, the day this write actually happens.
    date = args.date or _today()
    write_day = _today()
    problems = []
    if args.date is not None and not _valid_date(args.date):
        problems.append(f"--date {args.date!r} is not a real YYYY-MM-DD calendar date")
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

    # Deferred: avoids a circular import at module load.
    from lessons_changelog import index_refusal
    why = index_refusal(Path(index_path))
    if why:
        return _say(1, f"REFUSED: {why}; run /planwise upgrade to migrate the lessons index first (the "
                      "migration writes the promotion log itself), then re-run this command", js, err=True)

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
    backups_root = Path(config["_planwise_root"]) / "upgrade-backups"

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
        try:
            text = _read_text(dest_path)
        except Refusal as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        try:
            rows = _read_rows(text, dest_path)
        except Refusal as exc:
            return _say(1, f"REFUSED: {dest_path} already carries malformed content: {exc}", js, err=True)

    duplicate = next((row for row in rows if row["lesson_id"] == lesson_id
                      and _normalize_cell(row["cells"][2]) == _normalize_cell(args.artifact)), None)

    # A century file already on disk (an earlier interrupted run, a hand edit)
    # can leave the hub's own `Parts:` listing stale. A live re-run repairs it
    # -- backed up, same as any other write -- even when this call goes on to
    # refuse the append as a duplicate below; `--dry-run` writes nothing, so
    # the repair is skipped there too.
    if duplicate and not creating and not args.dry_run:
        try:
            repaired_hub_text = _stale_parts_repair(hub_path, naming)
        except Refusal as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        if repaired_hub_text is not None:
            ok, report = _write_backed_up([(hub_path, repaired_hub_text)], config, backups_root, write_day,
                                          "promotion-log-listing-repair")
            if not ok:
                return _failed(report, js)
            # The repair rewrote hub_path in place; when the duplicate's own
            # row lives in that same file (ids routed straight to the hub),
            # the repair can shift every line below its listing line, so the
            # refusal below must name the line AFTER the repair, not before.
            if dest_path == hub_path:
                rows = _read_rows(repaired_hub_text, dest_path)
                duplicate = next((row for row in rows if row["lesson_id"] == lesson_id
                                  and _normalize_cell(row["cells"][2]) == _normalize_cell(args.artifact)),
                                 duplicate)

    if duplicate:
        return _say(1, f"REFUSED: {args.lesson} / {args.artifact!r} is already logged at "
                      f"{dest_path} line {duplicate['line']}", js, err=True)

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
        try:
            outputs = list(_century_outputs(dest_path, dest_name, hub_path, naming,
                                            lesson_id, date, args.artifact, args.file_))
        except Refusal as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        # The Archive directory is created only now, next to the write, and
        # a refused write removes it again when this run created it and the
        # rollback left it empty (`rmdir` refuses a non-empty directory).
        made_archive_dir = not dest_path.parent.exists()
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _say(1, f"REFUSED: could not create {dest_path.parent}: {exc}", js, err=True)
        ok, report = _write_backed_up(outputs, config, backups_root, write_day, "promotion-log-century-create")
        if not ok:
            if made_archive_dir:
                with contextlib.suppress(OSError):
                    dest_path.parent.rmdir()
            return _failed(report, js)
    else:
        try:
            new_text = _insert_after_last_row(text, rows, new_line)
        except Refusal as exc:
            return _say(1, f"REFUSED: {exc}", js, err=True)
        # A row routed to the hub itself rewrites the hub, so its Archive-parts
        # listing is brought in line with the century files on disk in the
        # same write (a no-op when it already names exactly that set). A row
        # routed to an existing century file leaves the hub alone unless its
        # listing is stale or missing, in which case the repaired hub joins
        # the same all-or-nothing write.
        outputs = [(dest_path, new_text)]
        if dest_path == hub_path:
            outputs = [(dest_path, _with_parts_listing(new_text, newline_of(text),
                                                       _existing_archive_parts(hub_path.parent, naming)))]
        else:
            try:
                repaired_hub_text = _stale_parts_repair(hub_path, naming)
            except Refusal as exc:
                return _say(1, f"REFUSED: {exc}", js, err=True)
            if repaired_hub_text is not None:
                outputs.append((hub_path, repaired_hub_text))
        # An append into an EXISTING file replaces a user file, exactly like
        # a century-file creation's hub rewrite -- the same backup rule
        # applies, so it goes through the same helper rather than writing
        # bare.
        ok, report = _write_backed_up(outputs, config, backups_root, write_day,
                                      "promotion-log-append")
        if not ok:
            return _failed(report, js)

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
