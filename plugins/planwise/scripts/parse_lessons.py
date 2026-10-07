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
`lesson_files`, `duplicate_ids`, `detect_index_shape`,
`parse_legacy_master_table`, `parse_generated_table`, `Row`,
`generated_index_files`, `parse_index`, `ParsedIndex`,
`collect_all_known_ids`, `compute_next_id`, and a CLI
(`--config`, `--next-id`, `--json`).
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
from config_loader import load_config
from generate_backlog_index import _index_naming, _list_disk_generated_files
from markdown_parser import is_section_boundary, split_row_cells

# The single ID-cell regex: bare, bold, linked, any digit count. Group 1 is
# the digits only. Every other reader in this project imports this rather
# than carrying its own near-duplicate.
LESSON_ROW_RE = re.compile(r"^\|\s*(?:\*\*)?(?:\[)?LL-(\d+)(?:\]\([^)]*\))?(?:\*\*)?\s*\|")

# `LL-{NNN}-{Domain}-{Topic}.md` -> NNN. Anchored so a file merely mentioning
# an id elsewhere in its name is not counted.
LESSON_FILE_RE = re.compile(r"^LL-(\d+)\b")

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


def lesson_files(lessons_dir, archive_dir) -> list:
    """Every `LL-NNN*.md` file under `lessons_dir` and `archive_dir` (each
    scanned non-recursively) as a LIST of `(id, path)` pairs, sorted by
    path -- never a dict, so two files claiming the same id are both kept
    for `duplicate_ids` to report instead of one silently overwriting the
    other on the way in (count rows before keying).
    """
    pairs = []
    for directory in (lessons_dir, archive_dir):
        if directory is None or not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.suffix.lower() != ".md":
                continue
            match = LESSON_FILE_RE.match(entry.name)
            if match:
                pairs.append((int(match.group(1)), entry))
    pairs.sort(key=lambda pair: str(pair[1]))
    return pairs


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
    """
    lines = section.split("\n")
    rows = []
    header_seen = False
    separator_seen = False
    header_cell_count = 0
    for idx, raw_line in enumerate(lines):
        probe = raw_line.strip()
        if is_section_boundary(probe, separator_seen=separator_seen):
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
                rows.append(
                    Row(
                        id=row_id, cells=cells, source=source, line=line_no,
                        malformed=True,
                        reason=f"expected {header_cell_count} cells, found {len(cells)}",
                    )
                )
                continue
            rows.append(Row(id=row_id, cells=cells, source=source, line=line_no))
    return rows


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


def compute_next_id(config: dict) -> dict:
    """The true next lesson id: `max(disk union the generated index family
    union a legacy Master Table) + 1`, or 1 when every source is empty.

    Returns the shape every existing caller already reads -- `next`,
    `next_id`, `max_found`, `found_in`, `counts` -- with the `found_in`
    labels `"working directory"`, `"Archive/"` and `"master table"`
    unchanged, plus `"generated index"` for the generated shape, so an
    existing caller's assertions keep holding.
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

    all_ids = working_ids | archive_ids | master_ids | generated_ids
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


def _format_duplicates_report(known: dict) -> str:
    lines = []
    if known["duplicates_on_disk"]:
        lines.append("Duplicate lesson ids on disk:")
        for lesson_id in sorted(known["duplicates_on_disk"]):
            paths = known["duplicates_on_disk"][lesson_id]
            lines.append(f"  {format_id(lesson_id)}: {', '.join(paths)}")
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
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    lessons_dir = config.get("_lessons_dir")
    if lessons_dir is None:
        print(
            "Error: config.yaml declares no project.lessons_dir -- nothing to parse.",
            file=sys.stderr,
        )
        return 1

    known = collect_all_known_ids(config)
    has_duplicates = bool(known["duplicates_on_disk"] or known["duplicates_in_index"])

    if args.next_id:
        result = compute_next_id(config)
        print(result["next_id"])
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
