#!/usr/bin/env python3
"""Single read path for a lessons-index row: the one ID-cell regex, the two
on-disk index shapes, and the `--next-id` allocation union.

A lessons-index row's first cell carries a lesson id in one of three forms —
bare (`LL-NNN`), bold (`**LL-NNN**`), or linked (`[LL-NNN](path)`) — and this
module defines the ONE regex (`LESSON_ROW_RE`) that recognizes all three, so
every other reader (`reconcile_lessons.py`, `flip_lesson_status.py`) imports
it instead of carrying its own near-duplicate.

Two index shapes exist on disk, and this module reads both:

  - `"generated"` -- a hub, overflow leaf, or Archive shard the generator
    writes: a `Generated:` line followed directly by the row table, with no
    `## Master Table` heading. The hub, its overflow leaves and its Archive
    shards are resolved via `generate_backlog_index`'s own naming helpers
    (`_index_naming`, `_list_disk_generated_files`), imported here rather
    than re-derived.
  - `"legacy"` -- the pre-generator shape: a `## Master Table` heading,
    optionally followed further down by a `## Rule Promotion Log` table,
    which is never a lesson row. Retiring the generated writer does not
    retire this reader: a project that has not yet migrated still carries
    the legacy shape on disk, and both a migration-refusal check and a
    before/after comparison need to be able to read it.

Every parse counts rows as it walks and collects ids as a LIST before
reducing to a set, so an id claimed by more than one row or file is
reported by id with every path (and line) that claims it -- never silently
collapsed to whichever copy a dict-keyed read happened to keep last.

Public surface: `LESSON_ROW_RE`, `LESSON_FILE_RE`, `format_id`,
`lesson_files`, `unreadable_lesson_files`, `describe_unreadable`,
`duplicate_ids`, `detect_index_shape`,
`parse_legacy_master_table`, `parse_generated_table`, `Row`,
`generated_index_files`, `parse_index`, `ParsedIndex`,
`collect_all_known_ids`, `compute_next_id`, `list_lessons_by_status`,
`resolve_owners`, and a CLI (`--config`, `--next-id`, `--json`, `--status`,
`--owners`).

The two read views answer the curate workflow's questions without a one-off
script. `--status VALUE` lists each lesson whose frontmatter status equals
VALUE. `--owners` resolves each lesson's `promoted-to:` ids to the backlog
item file (by id prefix, in the backlog and its `Archive/`) and prints that
item's status, or `MISSING` when no file matches. Both read the lesson files
through the CRLF-safe `lessons_index_scan` reader.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared modules from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import load_config
from generate_backlog_index import _index_naming, _list_disk_generated_files
from markdown_parser import (
    is_section_boundary,
    split_row_cells,
    split_row_cells_code_aware,
)
from worktree_scan import sibling_dirs

# The single ID-cell regex: bare, bold, linked, any digit count. Group 1 is
# the digits only. Every other reader in this project imports this rather
# than carrying its own near-duplicate.
LESSON_ROW_RE = re.compile(r"^\|\s*(?:\*\*)?(?:\[)?LL-(\d+)(?:\]\([^)]*\))?(?:\*\*)?\s*\|")

# `LL-{NNN}-{Domain}-{Topic}.md` -> NNN. Anchored so a file merely mentioning
# an id elsewhere in its name is not counted.
LESSON_FILE_RE = re.compile(r"^LL-(\d+)\b")

# Windows `MAX_PATH`, and the prefix that lifts it for one path.
WINDOWS_MAX_PATH = 260
_EXTENDED_PREFIX = "\\\\?\\"

MASTER_TABLE_HEADING_RE = re.compile(r"^##\s+Master Table\s*$", re.MULTILINE)
PROMOTION_LOG_HEADING_RE = re.compile(r"^##\s+Rule Promotion Log\s*$", re.MULTILINE)
GENERATED_LINE_RE = re.compile(r"^Generated:", re.MULTILINE)
_HEADER_ID_CELL_RE = re.compile(r"^\|\s*ID\s*\|", re.MULTILINE)
_SEPARATOR_ROW_RE = re.compile(r"^\|[-\s|]+\|")


def format_id(number: int) -> str:
    """Render an integer lesson number in canonical zero-padded `LL-NNN` form."""
    return f"LL-{number:03d}"


@dataclass
class Row:
    """One table row from a lessons index, kept even when malformed.

    `id` is -1 for a row whose first cell carries no parseable `LL-` id
    (`LESSON_ROW_RE` did not match) -- the row is still returned, flagged
    malformed, rather than silently dropped. `source` is the file the row
    came from when the caller supplied one; a bare `parse_legacy_master_table`
    / `parse_generated_table` call over a content string with no `source`
    argument leaves it `None`. `line` is 1-based -- the same number an
    editor or a `{source}:{line}` display would show, never a 0-based
    offset.
    """

    id: int
    cells: list
    source: object
    line: int
    malformed: bool = False
    reason: str = ""


@dataclass
class ParsedIndex:
    """The result of reading a project's lessons index, whichever shape it is on disk."""

    shape: str
    rows: list
    per_file_row_counts: dict = field(default_factory=dict)
    duplicates: dict = field(default_factory=dict)


def _extended_length(entry):
    """`entry` behind the Windows `\\\\?\\` extended-length prefix, or None off
    Windows and for a path that already carries it."""
    if os.name != "nt":
        return None
    text = os.path.abspath(os.fspath(entry))
    if text.startswith(_EXTENDED_PREFIX):
        return None
    if text.startswith("\\\\"):
        return Path(_EXTENDED_PREFIX + "UNC" + text[1:])
    return Path(_EXTENDED_PREFIX + text)


def _readable_file(entry):
    """The path to read `entry` through, or None when it is not a regular file.

    `Path.is_file()` returns False, with no exception, for a path of
    `WINDOWS_MAX_PATH` characters or more while Windows long paths are off.
    The extended-length form of the same path is not subject to that limit,
    so it is tried second and returned in place of `entry` when it succeeds.
    """
    if entry.is_file():
        return entry
    long_form = _extended_length(entry)
    if long_form is not None and long_form.is_file():
        return long_form
    return None


def _lesson_entries(lessons_dir, archive_dir):
    """`(id, entry)` for every `LL-NNN*.md` name in either directory's listing,
    whether or not the entry can be read as a file."""
    for directory in (lessons_dir, archive_dir):
        if directory is None or not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.suffix.lower() != ".md":
                continue
            match = LESSON_FILE_RE.match(entry.name)
            if match:
                yield int(match.group(1)), entry


def lesson_files(lessons_dir, archive_dir) -> list:
    """Every `LL-NNN*.md` file under `lessons_dir` and `archive_dir` (each
    scanned non-recursively) as a LIST of `(id, path)` pairs, sorted by
    path -- never a dict, so two files claiming the same id are both kept
    for `duplicate_ids` to report instead of one silently overwriting the
    other on the way in (count rows before keying).

    A file whose path is too long for Windows (see `_readable_file`) is
    returned under its extended-length path. One that still cannot be read
    as a file is absent here and listed by `unreadable_lesson_files`.
    """
    pairs = []
    for lesson_id, entry in _lesson_entries(lessons_dir, archive_dir):
        readable = _readable_file(entry)
        if readable is not None:
            pairs.append((lesson_id, readable))
    pairs.sort(key=lambda pair: str(pair[1]))
    return pairs


def unreadable_lesson_files(lessons_dir, archive_dir) -> list:
    """`(id, path)` for every `LL-NNN*.md` name the directory listing shows
    that `lesson_files` leaves out because it cannot be read as a regular
    file. A directory carrying such a name is not listed: it is a different
    cause."""
    return [(lesson_id, entry) for lesson_id, entry in _lesson_entries(lessons_dir, archive_dir)
            if _readable_file(entry) is None and not entry.is_dir()]


def describe_unreadable(entry) -> str:
    """One sentence naming why a listed lesson file cannot be read. It names
    the Windows path-length limit only when the path reaches that limit."""
    length = len(os.fspath(entry))
    sentence = f"{entry.name} is in the directory listing but cannot be read as a file (its path is {length} characters)"
    if length >= WINDOWS_MAX_PATH:
        sentence += (f"; Windows stops at {WINDOWS_MAX_PATH} characters while long paths are off, so enable "
                     "LongPathsEnabled, run from a shorter path, or give --config a \\\\?\\ extended-length path")
    return sentence + "."


def duplicate_ids(pairs: list) -> dict:
    """Every id claimed by more than one file in `pairs`, with all its paths."""
    by_id: dict = {}
    for lesson_id, path in pairs:
        by_id.setdefault(lesson_id, []).append(path)
    return {lesson_id: paths for lesson_id, paths in by_id.items() if len(paths) > 1}


def detect_index_shape(content: str) -> str:
    """Classify an on-disk lessons index as `"legacy"`, `"generated"`, or `"empty"`.

    `"legacy"`: a `## Master Table` or `## Rule Promotion Log` heading is
    present -- the pre-generator shape.
    `"generated"`: no legacy heading, but a `Generated:` line and a table
    header row (`| ID | ...`) are both present -- the generator's own
    shape, where the table sits at the top of the file under the
    `Generated:` line rather than under a section heading.
    `"empty"`: neither -- a fresh or unrecognized file.
    """
    if MASTER_TABLE_HEADING_RE.search(content) or PROMOTION_LOG_HEADING_RE.search(content):
        return "legacy"
    if GENERATED_LINE_RE.search(content) and _HEADER_ID_CELL_RE.search(content):
        return "generated"
    return "empty"


def _walk_rows(section: str, base_line: int, source) -> list:
    """The rows of `_walk_table`, without its stop index."""
    return _walk_table(section, base_line, source)[0]


def _walk_table(section: str, base_line: int, source) -> tuple:
    """Walk a table region line by line, splitting on "\\n" only -- never
    `str.splitlines()`, which treats a lone bare CR as a line break and
    would cut a row carrying one (mid-cell content, not a line terminator)
    in two. Boundary detection reuses `markdown_parser.is_section_boundary`,
    so a blank line inside the table body does NOT end the walk: only a
    `## ` heading, or a `---` rule once the header separator has been seen,
    does. Every row is kept, including a malformed one (no parseable id, or
    a cell count that does not match the header) -- flagged rather than
    dropped, so a caller can report it instead of silently losing it.
    `Row.line` is 1-based (the file's own first line is line 1), matching
    every editor and every other line number this project reports.

    Returns `(rows, stop_idx)`. `stop_idx` is the 0-based index within
    `section` of the boundary line that ended the walk, or `None` when the
    walk reached the end of `section`.
    """
    lines = section.split("\n")
    rows = []
    header_seen = False
    separator_seen = False
    header_cell_count = 0
    stop_idx = None
    for idx, raw_line in enumerate(lines):
        probe = raw_line.strip()
        if is_section_boundary(probe, separator_seen=separator_seen):
            stop_idx = idx
            break
        if not header_seen and _HEADER_ID_CELL_RE.match(probe):
            header_seen = True
            header_cell_count = len(split_row_cells(probe))
            continue
        if header_seen and not separator_seen and _SEPARATOR_ROW_RE.match(probe):
            separator_seen = True
            continue
        if separator_seen and probe.startswith("|"):
            # +1: `base_line` and `idx` are both 0-based offsets, but
            # `Row.line` is documented and consumed as a 1-based line
            # number (every `{source}:{line}` display this project prints
            # assumes it).
            line_no = base_line + idx + 1
            cells = split_row_cells(probe)
            match = LESSON_ROW_RE.match(probe)
            if not match:
                rows.append(
                    Row(
                        id=-1, cells=cells, source=source, line=line_no,
                        malformed=True, reason="row has no parseable LL- id cell",
                    )
                )
                continue
            row_id = int(match.group(1))
            if header_cell_count and len(cells) != header_cell_count:
                # Retry with the code-aware split; accept only an exact match.
                retried = split_row_cells_code_aware(probe)
                if len(retried) == header_cell_count:
                    rows.append(Row(id=row_id, cells=retried, source=source, line=line_no))
                    continue
                rows.append(
                    Row(
                        id=row_id, cells=cells, source=source, line=line_no,
                        malformed=True,
                        reason=(
                            f"expected {header_cell_count} cells, found {len(cells)} "
                            "(a | inside backticks is the usual cause; "
                            "escape it as \\| or close the backtick)"
                        ),
                    )
                )
                continue
            rows.append(Row(id=row_id, cells=cells, source=source, line=line_no))
    return rows, stop_idx


def parse_legacy_master_table(content: str, source=None) -> list:
    """Parse the `## Master Table` region of a legacy-shaped lessons index.

    Bounded to the region between the `## Master Table` heading and the
    next `## ` heading (a following `## Rule Promotion Log` table is never
    read as a lesson row) or end of file. Walked directly, line by line
    (see `_walk_rows`). Returns `[]` when no `## Master Table` heading
    exists.
    """
    heading = MASTER_TABLE_HEADING_RE.search(content)
    if not heading:
        return []
    base_line = content[: heading.end()].count("\n")
    rest = content[heading.end():]
    return _walk_rows(rest, base_line, source)


def parse_generated_table(content: str, source=None) -> list:
    """Parse the top-of-file table of a generated lessons-index file (hub,
    overflow leaf, or Archive shard).

    A generated file carries no `## Master Table` heading -- the table
    sits directly under a `Generated:` line -- so it is located by its own
    header row (`| ID | ...`) rather than by a section heading, then walked
    directly line by line (see `_walk_rows`), never spliced through
    `markdown_parser.parse_markdown_table`, which drops a malformed row
    instead of returning it flagged. Returns `[]` when no header row
    exists.
    """
    header_match = _HEADER_ID_CELL_RE.search(content)
    if not header_match:
        return []
    line_start = content.rfind("\n", 0, header_match.start()) + 1
    base_line = content[:line_start].count("\n")
    rest = content[line_start:]
    return _walk_rows(rest, base_line, source)


def generated_table_tail(content: str) -> list:
    """Every pipe-led line after the line that ends the top-of-file table
    of a generated lessons-index file, as `(line_no, stripped_line)` with a
    1-based `line_no`. The walk is `parse_generated_table`'s own, so the
    tail starts exactly where its rows stop. Empty when the file has no
    header row or the walk reaches the end of the file.
    """
    header_match = _HEADER_ID_CELL_RE.search(content)
    if not header_match:
        return []
    line_start = content.rfind("\n", 0, header_match.start()) + 1
    base_line = content[:line_start].count("\n")
    section_lines = content[line_start:].split("\n")
    _rows, stop_idx = _walk_table(content[line_start:], base_line, None)
    if stop_idx is None:
        return []
    tail = []
    for idx in range(stop_idx + 1, len(section_lines)):
        stripped = section_lines[idx].strip()
        if stripped.startswith("|"):
            tail.append((base_line + idx + 1, stripped))
    return tail


def generated_index_files(lessons_dir, archive_dir, index_path) -> list:
    """Hub union overflow leaves union Archive shards for a generated
    lessons index, resolved through `generate_backlog_index`'s own naming
    helpers -- never re-derived here.
    """
    naming = _index_naming(index_path)
    return _list_disk_generated_files(lessons_dir, archive_dir, naming)


def parse_index(config: dict) -> ParsedIndex:
    """Read a project's lessons index, whichever shape it is on disk.

    `"legacy"`: the `## Master Table` region of the single index file.
    `"generated"`: every file `generated_index_files` names (hub, overflow
    leaves, Archive shards), rows collected across all of them.
    `"empty"`: no rows.

    Rows are counted as they are walked, never keyed into a dict first, so
    `duplicates` reports every row id seen more than once -- across files
    for the generated shape, or within the one legacy table -- by id, with
    every file:line that carries it.
    """
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")
    archive_dir = (lessons_dir / "Archive") if lessons_dir else None

    content = index_path.read_text(encoding="utf-8") if index_path and index_path.exists() else ""
    shape = detect_index_shape(content)

    rows = []
    per_file_row_counts: dict = {}

    if shape == "legacy":
        legacy_rows = parse_legacy_master_table(content, source=index_path)
        rows.extend(legacy_rows)
        if index_path is not None:
            per_file_row_counts[str(index_path)] = len(legacy_rows)
    elif shape == "generated":
        files = (
            generated_index_files(lessons_dir, archive_dir, index_path)
            if lessons_dir is not None and index_path is not None
            else []
        )
        for path in files:
            file_content = path.read_text(encoding="utf-8")
            file_rows = parse_generated_table(file_content, source=path)
            rows.extend(file_rows)
            per_file_row_counts[str(path)] = len(file_rows)

    seen: dict = {}
    for row in rows:
        if row.id == -1:
            continue
        label = f"{row.source}:{row.line}" if row.source is not None else str(row.line)
        seen.setdefault(row.id, []).append(label)
    duplicates = {lesson_id: labels for lesson_id, labels in seen.items() if len(labels) > 1}

    return ParsedIndex(shape=shape, rows=rows, per_file_row_counts=per_file_row_counts, duplicates=duplicates)


def collect_all_known_ids(config: dict) -> dict:
    """The full id picture for a project: every id on disk, every id the
    current on-disk index shape carries (as `"index"` when generated,
    `"legacy"` when legacy), and every duplicate found in either place.
    """
    lessons_dir = config.get("_lessons_dir")
    archive_dir = (lessons_dir / "Archive") if lessons_dir else None

    pairs = lesson_files(lessons_dir, archive_dir)
    disk_ids = {lesson_id for lesson_id, _ in pairs}
    dup_on_disk = duplicate_ids(pairs)
    dup_on_disk_str = {
        lesson_id: [str(p) for p in paths] for lesson_id, paths in dup_on_disk.items()
    }

    parsed = parse_index(config)
    # `row.id != -1` alone: a malformed row whose id WAS parseable (a
    # cell-count mismatch, not a missing id cell) still claims that id.
    # Excluding it here would let a malformed row's id silently reappear
    # as "unclaimed" in this picture, even though `compute_next_id` (the
    # allocator) already counts it.
    valid_rows = [row for row in parsed.rows if row.id != -1]
    if parsed.shape == "legacy":
        legacy_ids = {row.id for row in valid_rows}
        index_ids: set = set()
    else:
        index_ids = {row.id for row in valid_rows}
        legacy_ids = set()

    return {
        "disk": disk_ids,
        "index": index_ids,
        "legacy": legacy_ids,
        "duplicates_on_disk": dup_on_disk_str,
        "duplicates_in_index": parsed.duplicates,
    }


def _linked_worktree_ids(config: dict) -> set:
    """The lesson ids, file names and index rows, that the lessons folders of
    the other linked worktrees hold. Empty on no git or a single worktree.

    Another worktree's files may be mid-write or unreadable. That must not stop
    allocation here, so a failed read is named on stderr and skipped.
    """
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")
    if lessons_dir is None:
        return set()
    ids: set = set()
    for folder in sibling_dirs(lessons_dir):
        try:
            ids |= {lesson_id for lesson_id, _ in lesson_files(folder, folder / "Archive")}
            if index_path is None or not index_path.is_relative_to(lessons_dir):
                continue
            sibling_index = folder / index_path.relative_to(lessons_dir)
            parsed = parse_index({"_lessons_dir": folder, "_lessons_index": sibling_index})
            ids |= {row.id for row in parsed.rows if row.id != -1}
        except (OSError, UnicodeDecodeError) as exc:
            print(
                f"Warning: could not read all lesson ids in linked worktree folder {folder}: {exc}",
                file=sys.stderr,
            )
    return ids


def compute_next_id(config: dict, *, include_siblings: bool = False) -> dict:
    """The true next lesson id: `max(disk union the generated index family
    union a legacy Master Table) + 1`, or 1 when every source is empty.

    With `include_siblings`, the union also covers the lessons folders of the
    other linked git worktrees (`worktree_scan.sibling_dirs`). Only an id
    allocator passes it: the committed counter and the drift check stay a
    function of this tree alone. The scope is local folders only. No remote
    branch is read, and no git or a single worktree adds nothing.

    Returns the shape every existing caller already reads -- `next`,
    `next_id`, `max_found`, `found_in`, `counts` -- with the `found_in`
    labels `"working directory"`, `"Archive/"` and `"master table"`
    unchanged, plus `"generated index"` for the generated shape and
    `"linked worktree"` for a max that another worktree holds. `counts`
    covers this tree only.
    """
    lessons_dir = config.get("_lessons_dir")
    archive_dir = (lessons_dir / "Archive") if lessons_dir else None

    working_ids = {lesson_id for lesson_id, _ in lesson_files(lessons_dir, None)}
    archive_ids = {lesson_id for lesson_id, _ in lesson_files(None, archive_dir)}

    parsed = parse_index(config)
    # `row.id != -1` alone -- NOT `and not row.malformed`. `LESSON_ROW_RE`
    # matched this row and produced a real id; a cell-count mismatch (the
    # only other way `_walk_rows` sets `malformed`, besides an unparseable
    # id cell already excluded by `id != -1`) is a shape defect, not a
    # reason to let the id it claims silently allocate again.
    valid_rows = [row for row in parsed.rows if row.id != -1]
    if parsed.shape == "legacy":
        master_ids = {row.id for row in valid_rows}
        generated_ids: set = set()
    else:
        generated_ids = {row.id for row in valid_rows}
        master_ids = set()

    linked_ids = _linked_worktree_ids(config) if include_siblings else set()

    all_ids = working_ids | archive_ids | master_ids | generated_ids | linked_ids
    max_found = max(all_ids) if all_ids else None
    found_in = []
    if max_found is not None:
        if max_found in working_ids:
            found_in.append("working directory")
        if max_found in archive_ids:
            found_in.append("Archive/")
        if max_found in master_ids:
            found_in.append("master table")
        if max_found in generated_ids:
            found_in.append("generated index")
        if max_found in linked_ids:
            found_in.append("linked worktree")

    return {
        "next": (max_found + 1) if max_found is not None else 1,
        "next_id": format_id((max_found + 1) if max_found is not None else 1),
        "max_found": max_found,
        "found_in": found_in,
        "counts": {
            "working": len(working_ids),
            "archive": len(archive_ids),
            "master": len(master_ids),
            "generated": len(generated_ids),
        },
    }


# A backlog owner id as a lesson's `promoted-to:` value spells it. The value is
# one id (`BB-NNN`) or several joined by commas (`BB-NNN, BB-NNN`), and a bare
# comma-joined value is not a flow or block list, so `_parse_list_field` reads
# it as empty. One findall covers every shape.
_OWNER_ID_RE = re.compile(r"(?:BB|BLI)-\d+")


def list_lessons_by_status(config: dict, status: str | None) -> list:
    """Every lesson whose frontmatter `status:` equals `status`, id-sorted, from
    the working directory and `Archive/`. `status=None` returns every lesson.

    Each record is `{"id", "status", "path", "promoted_to"}`. The scan is the
    CRLF-safe `scan_lessons` reader, and `promoted_to` is the list of owner ids
    read from the same file's `promoted-to:` value. Raises
    `LessonsGeneratorError` naming every lesson file whose frontmatter cannot be
    read, the same refusal the index generator gives.

    The three imports are function-local: `lessons_index_scan` imports this
    module at its top level, so a top-level import here would be circular.
    """
    from lessons_index_scan import (
        _read_frontmatter_map,
        _strip_inline_comment,
        scan_lessons,
    )
    from lessons_index_schema import _resolve_valid_statuses

    lessons_dir = config["_lessons_dir"]
    scanned = scan_lessons(
        lessons_dir, lessons_dir / "Archive", config["_lessons_index"], _resolve_valid_statuses(config)
    )
    records = []
    for item in scanned.items:
        if status is not None and item["status"] != status:
            continue
        raw_map = _read_frontmatter_map(item["_path"])
        promoted = _strip_inline_comment(raw_map.get("promoted-to", ""))
        records.append(
            {
                "id": item["id"],
                "status": item["status"],
                "path": item["_path"],
                "promoted_to": _OWNER_ID_RE.findall(promoted),
            }
        )
    return records


def resolve_owners(config: dict, records: list) -> list:
    """One entry per lesson in `records`: `{"id", "owners": [...]}`. Each owner is
    `{"id", "status", "path"}`, resolved by id prefix through
    `parse_backlog.find_item_file` (it matches `BB-<NNN>-*.md` in the backlog and
    its `Archive/`). A missing file gives `status "MISSING"` and `path None`. An
    existing file whose frontmatter carries no `status:` gives `"UNKNOWN"`.
    """
    from item_frontmatter import read_item_frontmatter
    from parse_backlog import find_item_file

    resolved = []
    for record in records:
        owners = []
        for owner_id in record["promoted_to"]:
            path = find_item_file(owner_id, config)
            if path is None:
                owners.append({"id": owner_id, "status": "MISSING", "path": None})
                continue
            status = str(read_item_frontmatter(path).get("status") or "UNKNOWN")
            owners.append({"id": owner_id, "status": status, "path": path})
        resolved.append({"id": record["id"], "owners": owners})
    return resolved


def _format_status_lines(records: list) -> list:
    return [f"{format_id(r['id'])}\t{r['status']}\t{Path(r['path']).as_posix()}" for r in records]


def _format_owner_lines(resolved: list) -> list:
    lines = []
    for entry in resolved:
        label = format_id(entry["id"])
        if not entry["owners"]:
            lines.append(f"{label}\t(none)")
            continue
        for owner in entry["owners"]:
            path = Path(owner["path"]).as_posix() if owner["path"] is not None else "-"
            lines.append(f"{label}\t{owner['id']}\t{owner['status']}\t{path}")
    return lines


def _run_lesson_view(config: dict, status: str | None, owners: bool, write_json: bool) -> int:
    """The `--status` and `--owners` read views. Exit 0 on a clean read, 2 for an
    undeclared status, 1 when a lesson file's frontmatter cannot be read."""
    from lessons_index_schema import LessonsGeneratorError, _resolve_valid_statuses

    valid = _resolve_valid_statuses(config)
    if status is not None and status not in valid:
        print(
            f"Error: --status={status!r} is not a declared lesson status ({', '.join(sorted(valid))}).",
            file=sys.stderr,
        )
        return 2
    try:
        records = list_lessons_by_status(config, status)
    except LessonsGeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    resolved = resolve_owners(config, records) if owners else None
    if not records:
        print(f"No lessons with status {status}." if status is not None else "No lessons found.")
    elif resolved is not None:
        print("\n".join(_format_owner_lines(resolved)))
    else:
        print("\n".join(_format_status_lines(records)))

    if write_json:
        payload = {"status": status, "lessons": records}
        if resolved is not None:
            payload["owners"] = resolved
        print(f"JSON: {_write_json(payload)}")
    return 0


def _format_duplicates_report(known: dict) -> str:
    lines = []
    if known["duplicates_on_disk"]:
        lines.append("Duplicate lesson ids on disk:")
        for lesson_id in sorted(known["duplicates_on_disk"]):
            paths = known["duplicates_on_disk"][lesson_id]
            scripts_dir = Path(__file__).resolve().parent.as_posix()
            fix = (
                f'. Fix: python "{scripts_dir}/reconcile_lessons.py" --renumber {format_id(lesson_id)}'
                f" <next free id> --file {Path(str(paths[0])).name}"
            )
            lines.append(f"  {format_id(lesson_id)}: {', '.join(paths)}{fix}")
    if known["duplicates_in_index"]:
        lines.append("Duplicate row ids in the index:")
        for lesson_id in sorted(known["duplicates_in_index"]):
            locations = known["duplicates_in_index"][lesson_id]
            lines.append(f"  {format_id(lesson_id)}: {', '.join(locations)}")
    if not lines:
        return "No duplicate lesson ids found."
    return "\n".join(lines)


def _json_default(obj):
    if isinstance(obj, set):
        return sorted(obj)
    return str(obj)


def _write_json(result: dict) -> str:
    tmp_dir = tempfile.mkdtemp(prefix="parse-lessons-")
    json_path = os.path.join(tmp_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=_json_default)
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Single read path for a lessons index: parse either "
        "on-disk shape, report duplicate ids, and compute the true next "
        "lesson id."
    )
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml.")
    parser.add_argument("--next-id", action="store_true", help="Print the true next lesson id and exit.")
    parser.add_argument("--json", action="store_true", help="Additionally write a JSON report and print its path.")
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        metavar="VALUE",
        help="List every lesson whose frontmatter status equals VALUE (exit 2 for an undeclared status). "
        "One `LL-NNN<TAB>status<TAB>path` line each.",
    )
    parser.add_argument(
        "--owners",
        action="store_true",
        help="Resolve each lesson's promoted-to ids to their backlog files and print each owner's status "
        "(`MISSING` when no file matches). Combine with --status to limit the lessons.",
    )
    args = parser.parse_args()

    config = load_config(Path(__file__))
    lessons_dir = config.get("_lessons_dir")
    if lessons_dir is None:
        print(
            "Error: config.yaml declares no project.lessons_dir -- nothing to parse.",
            file=sys.stderr,
        )
        return 1

    if args.status is not None or args.owners:
        return _run_lesson_view(config, args.status, args.owners, args.json)

    known = collect_all_known_ids(config)
    has_duplicates = bool(known["duplicates_on_disk"] or known["duplicates_in_index"])

    if args.next_id:
        result = compute_next_id(config, include_siblings=True)
        print(result["next_id"])
        local = compute_next_id(config)
        if local["next"] != result["next"]:
            print(
                f"Note: a linked worktree holds {format_id(result['max_found'])}. "
                f"This tree alone would give {local['next_id']}.",
                file=sys.stderr,
            )
        if has_duplicates:
            print(_format_duplicates_report(known), file=sys.stderr)
        if args.json:
            print(f"JSON: {_write_json(result)}")
        return 1 if has_duplicates else 0

    print(_format_duplicates_report(known))
    if args.json:
        print(f"JSON: {_write_json(known)}")
    return 1 if has_duplicates else 0


if __name__ == "__main__":
    sys.exit(main())
