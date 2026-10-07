#!/usr/bin/env python3
"""Single read path for the plans index and the Master Plans it describes.

Three readers live here, so every consumer (generator, drift audit, migrator)
reads the same way and none keeps a private copy of a row regex:

  (a) Master Plan field readers: `normalize_status`, `read_master_plan_fields`.
      A missing field is `None`. Nothing here invents a value.
  (b) The disk walk: `enumerate_master_plans` finds every Master Plan by a
      depth-bounded walk of the plans directory, and `master_plan_path_for`
      is its inverse for an index row.
  (c) The index-table parser: `parse_index_table` reads past HTML comments,
      blank lines and prose, accepts bare, bold, linked and backticked cells
      and escaped pipes, counts every row before keying, and names a repeated
      Path in `duplicates` instead of keeping the last one. `detect_index_shape`
      classifies an index file as `generated`, `legacy` or `empty`.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from markdown_parser import split_row_cells

MASTER_PLAN_SUFFIX = "-Master-Plan.md"
META_MASTER_PLAN_SUFFIX = "-META-Master-Plan.md"
META_DIR_PREFIX = "Meta-"
EXEC_DIR_PREFIX = "Exec-"
META_NAME_SUFFIX = " (Meta / Discovery)"
EXEC_NAME_SUFFIX = " (Exec)"

COLUMN_COUNT = 6

# ---------------------------------------------------------------------------
# (a) Master Plan field readers
# ---------------------------------------------------------------------------

_LEADING_NON_ALNUM_RE = re.compile(r"^[^A-Za-z0-9]+")
# The token run starts with a capital and holds capitals, digits and
# underscores. It must end at a character that is neither alphanumeric nor `_`,
# so `Complete` (title case) is not misread as the one-letter token `C`, and
# `ON_hold` is not cut back to `ON`.
_TOKEN_RUN_RE = re.compile(r"[A-Z][A-Z0-9_]*(?![A-Za-z0-9_])")
_STATUS_LINE_RE = re.compile(r"^\*\*Status:\*\*[ \t]*(\S.*)$", re.MULTILINE)
_CREATED_RE = re.compile(r"\*\*Created:\*\*[ \t]*(\d{4}-\d{2}-\d{2})")
_FOOTER_LINE_RE = re.compile(r"^\*Last Updated:.*$", re.MULTILINE)
_HEADER_UPDATED_LINE_RE = re.compile(r"^\*\*Last Updated:\*\*.*$", re.MULTILINE)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalize_status(raw: str) -> str | None:
    """Reduce a raw `**Status:**` value or index Status cell to its leading token.

    Strips leading characters that are not letters or digits (an emoji, `*`,
    `_`, spaces), takes the leading run of capitals, digits and underscores
    that starts with a capital, and drops trailing underscores. Punctuation
    after the run (`COMPLETE.`, the `(` in `COMPLETE (2026-...`) is outside the
    run, so it drops. A run that a lowercase letter follows is no token, so
    `Complete` and `ON_hold` give `None`. Returns `None` when no run remains:
    a lone emoji, lowercase text, an empty value.
    """
    if not raw:
        return None
    stripped = _LEADING_NON_ALNUM_RE.sub("", raw)
    match = _TOKEN_RUN_RE.match(stripped)
    if match is None:
        return None
    return match.group(0).rstrip("_") or None


@dataclass(frozen=True)
class MasterPlanFields:
    """The fields a Master Plan states about itself. A missing field is `None`."""

    path: Path
    status_token: str | None
    status_raw: str | None
    created: str | None
    last_updated: str | None


def _first_date(line: str) -> str | None:
    match = _DATE_RE.search(line)
    return match.group(0) if match else None


def read_master_plan_fields(path: Path) -> MasterPlanFields:
    """Read a Master Plan's status, created date and last-updated date.

    - Status: the first line starting `**Status:**`. `status_raw` is the text
      after the label and `status_token` is its normalized token.
    - Created: the first `**Created:** YYYY-MM-DD` anywhere in the file. The
      header block can run past any fixed line count, so the search is never
      limited to the first N lines.
    - Last Updated: the first date in the LAST line that starts `*Last
      Updated:` (line-anchored), else the first date in the first line that
      starts `**Last Updated:**`. The anchor means a comment appended after
      the footer, which may quote a `*Last Updated: ...*` fragment mid-line,
      cannot move the date.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    status_match = _STATUS_LINE_RE.search(content)
    status_raw = status_match.group(1).strip() if status_match else None
    status_token = normalize_status(status_raw) if status_raw else None

    created_match = _CREATED_RE.search(content)
    created = created_match.group(1) if created_match else None

    last_updated = None
    footers = _FOOTER_LINE_RE.findall(content)
    if footers:
        last_updated = _first_date(footers[-1])
    if last_updated is None:
        header_match = _HEADER_UPDATED_LINE_RE.search(content)
        if header_match:
            last_updated = _first_date(header_match.group(0))

    return MasterPlanFields(
        path=path,
        status_token=status_token,
        status_raw=status_raw,
        created=created,
        last_updated=last_updated,
    )


# ---------------------------------------------------------------------------
# (b) The disk walk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanEntry:
    """One Master Plan file found on disk.

    `path` is the Master Plan's directory relative to the plans directory,
    with POSIX separators and a trailing `/`. It is never prefixed with the
    plans directory itself.
    """

    path: str
    abbrev: str
    name: str
    file: Path


def _abbrev_from_filename(filename: str, allow_meta: bool) -> str | None:
    if allow_meta and filename.endswith(META_MASTER_PLAN_SUFFIX):
        return filename[: -len(META_MASTER_PLAN_SUFFIX)] or None
    if filename.endswith(META_MASTER_PLAN_SUFFIX):
        return None
    if filename.endswith(MASTER_PLAN_SUFFIX):
        return filename[: -len(MASTER_PLAN_SUFFIX)] or None
    return None


def _entries_in_directory(plans_dir: Path, directory: Path, name: str, allow_meta: bool) -> list[PlanEntry]:
    rel = directory.relative_to(plans_dir).as_posix() + "/"
    entries = []
    for candidate in sorted(directory.iterdir()):
        if not candidate.is_file():
            continue
        abbrev = _abbrev_from_filename(candidate.name, allow_meta)
        if abbrev is not None:
            entries.append(PlanEntry(path=rel, abbrev=abbrev, name=name, file=candidate))
    return entries


def enumerate_master_plans(plans_dir: Path) -> list[PlanEntry]:
    """Find every Master Plan under `plans_dir` by a depth-bounded walk.

    - Depth 1: `{Plan}/{Abbrev}-Master-Plan.md`.
    - Depth 2: `{Plan}/{Meta-*|Exec-*}/{Abbrev}-Master-Plan.md` or
      `{Abbrev}-META-Master-Plan.md`. A depth-2 folder whose name starts with
      neither prefix is ignored.
    - Every other depth is ignored, which keeps a nested test fixture out.

    Abbrev is the filename with `-META-Master-Plan.md` removed, else with
    `-Master-Plan.md` removed. Name is the top-level plan folder, plus
    ` (Meta / Discovery)` under a `Meta-` folder or ` (Exec)` under an `Exec-`
    folder. Two Master Plan files in one directory give two entries with one
    Path, for the caller to report. The result is sorted by Path.
    """
    plans_dir = Path(plans_dir)
    if not plans_dir.is_dir():
        return []
    entries: list[PlanEntry] = []
    for plan in sorted(plans_dir.iterdir()):
        if not plan.is_dir():
            continue
        entries.extend(_entries_in_directory(plans_dir, plan, plan.name, allow_meta=False))
        for child in sorted(plan.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith(META_DIR_PREFIX):
                suffix = META_NAME_SUFFIX
            elif child.name.startswith(EXEC_DIR_PREFIX):
                suffix = EXEC_NAME_SUFFIX
            else:
                continue
            entries.extend(_entries_in_directory(plans_dir, child, plan.name + suffix, allow_meta=True))
    return sorted(entries, key=lambda entry: (entry.path, entry.file.name))


def master_plan_path_for(plans_dir: Path, path: str, abbrev: str) -> Path:
    """The Master Plan file an index row names: the walk's inverse.

    The filename rule matches the walk's per depth. Only a two-segment Path
    whose last segment starts `Meta-` or `Exec-` accepts both
    `{Abbrev}-Master-Plan.md` and `{Abbrev}-META-Master-Plan.md`. Every other
    Path, a top-level `Meta-` folder included, accepts only the plain name.
    Where both names are accepted, the folder's own name comes first (the META
    name under `Meta-`, the plain name under `Exec-`), and the other name wins
    only when it exists and the first does not. Nothing is checked beyond
    that: the caller tests whether the returned file exists.
    """
    directory = Path(plans_dir) / path
    plain_file = directory / f"{abbrev}{MASTER_PLAN_SUFFIX}"
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) != 2:
        return plain_file
    if segments[1].startswith(META_DIR_PREFIX):
        first, second = directory / f"{abbrev}{META_MASTER_PLAN_SUFFIX}", plain_file
    elif segments[1].startswith(EXEC_DIR_PREFIX):
        first, second = plain_file, directory / f"{abbrev}{META_MASTER_PLAN_SUFFIX}"
    else:
        return plain_file
    if not first.exists() and second.exists():
        return second
    return first


# ---------------------------------------------------------------------------
# (c) The index-table parser and the shape classifier
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^\|\s*Abbrev\s*\|")
_HEADER_LINE_RE = re.compile(r"^[ \t]*\|[ \t]*Abbrev[ \t]*\|", re.MULTILINE)
_GENERATED_LINE_RE = re.compile(r"^Generated:", re.MULTILINE)
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]*-[\s:|-]*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
OUTSIDE_REGION_REASON = "outside-table-region"
_HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
_BOLD_RE = re.compile(r"^\*\*(.+)\*\*$")
_LINK_RE = re.compile(r"^\[([^\]]*)\]\([^)]*\)$")
_CODE_RE = re.compile(r"^`([^`]*)`$")
_MAX_UNWRAP_ROUNDS = 6


class TableLine(NamedTuple):
    """A table-shaped line and its 1-based line number."""

    line_number: int
    text: str


class UnparsedLine(NamedTuple):
    """A table-shaped line that yielded no row, with the reason."""

    line_number: int
    reason: str
    text: str


class SkippedLine(NamedTuple):
    """A comment, blank, separator or prose line inside the table region.

    `kind` is `comment`, `blank`, `separator` or `prose`.
    """

    line_number: int
    kind: str
    text: str


class DuplicatePath(NamedTuple):
    """A Path that appears on more than one row, with every line number."""

    path: str
    line_numbers: tuple


@dataclass(frozen=True)
class PlanRow:
    """One parsed index row. `cells` holds the six logical cells as read."""

    line_number: int
    abbrev: str
    name: str
    status_raw: str
    status_token: str | None
    created: str
    last_updated: str
    path: str
    cells: tuple


@dataclass(frozen=True)
class IndexTable:
    """The result of reading an index file. Every row is kept in file order."""

    rows: list
    table_lines: list
    unparsed: list
    skipped: list
    duplicates: list
    header_line: int | None


def _unwrap_cell(cell: str) -> str:
    """Peel bold, link and backtick wrappers, in any combination, off a cell."""
    value = cell.strip()
    for _ in range(_MAX_UNWRAP_ROUNDS):
        for pattern in (_BOLD_RE, _LINK_RE, _CODE_RE):
            match = pattern.match(value)
            if match:
                value = match.group(1).strip()
                break
        else:
            break
    return value


def _row_from_cells(line_number: int, cells: list[str]) -> PlanRow | str:
    """Build a row, or return the reason the six cells cannot make one."""
    abbrev = _unwrap_cell(cells[0])
    path = _unwrap_cell(cells[5])
    if not abbrev:
        return "empty-abbrev"
    if not path:
        return "empty-path"
    if not path.endswith("/"):
        path += "/"
    status_raw = cells[2]
    return PlanRow(
        line_number=line_number,
        abbrev=abbrev,
        name=cells[1],
        status_raw=status_raw,
        status_token=normalize_status(status_raw),
        created=cells[3],
        last_updated=cells[4],
        path=path,
        cells=tuple(cells),
    )


def _find_duplicates(rows: list[PlanRow]) -> list[DuplicatePath]:
    """Group rows by Path after the walk. Rows are counted, never collapsed."""
    seen: dict[str, list[int]] = {}
    for row in rows:
        seen.setdefault(row.path, []).append(row.line_number)
    return [DuplicatePath(path, tuple(numbers)) for path, numbers in seen.items() if len(numbers) > 1]


def _count_outside_region(line_number: int, line: str, table_lines: list, unparsed: list) -> None:
    """Record a six-cell line outside the table region, unless it is a header or separator row."""
    stripped = line.strip()
    if _HEADER_RE.match(stripped):
        return
    cells = split_row_cells(stripped)
    if len(cells) != COLUMN_COUNT or all(_SEPARATOR_CELL_RE.match(cell) for cell in cells):
        return
    table_lines.append(TableLine(line_number, line))
    unparsed.append(UnparsedLine(line_number, OUTSIDE_REGION_REASON, line))


def parse_index_table(content: str) -> IndexTable:
    """Read the plans index table, past comments, blank lines and prose.

    The table region starts at the first `| Abbrev |` header row and its
    separator, and runs to the first markdown heading or the end of the file,
    so a legend table under a heading is outside it. Inside the region a line
    whose first non-space character is `|` is table-shaped. Any other line is
    recorded in `skipped` and the walk continues: it never stops at a comment.
    A comment that spans lines is skipped as a whole.

    A table-shaped line needs six cells. A line with another count, or with an
    empty Abbrev or Path, goes to `unparsed` with its reason. Every row is kept
    in file order, and `duplicates` names each Path that more than one row
    carries with all of its line numbers.

    Nothing that looks like a row may fall outside both `rows` and `unparsed`.
    The scan therefore covers the whole file. A line outside the region that
    splits into exactly six cells is added to `table_lines` and `unparsed` with
    the reason `outside-table-region`. A `| Abbrev |` header row and a separator
    row (every cell made of dashes and optional colons) are not counted. A line
    with any other cell count, such as a legend row, is not counted either. A
    file with no header and separator pair has no region, so every six-cell line
    in it counts.
    """
    lines = [line.rstrip("\r") for line in content.split("\n")]
    if lines and lines[-1] == "":
        # The final newline ends the last line. It does not start a blank one.
        lines.pop()

    header_index = None
    for index, line in enumerate(lines):
        if _HEADER_RE.match(line.strip()):
            header_index = index
            break
    separator_index = None
    if header_index is not None:
        candidate = header_index + 1
        if candidate < len(lines) and _SEPARATOR_RE.match(lines[candidate].strip()):
            separator_index = candidate

    rows: list[PlanRow] = []
    table_lines: list[TableLine] = []
    unparsed: list[UnparsedLine] = []
    skipped: list[SkippedLine] = []
    in_comment = False
    in_region = False

    for index, line in enumerate(lines):
        line_number = index + 1
        stripped = line.strip()

        if separator_index is not None and index == separator_index:
            in_region = True
            continue
        if not in_region:
            _count_outside_region(line_number, line, table_lines, unparsed)
            continue
        if in_comment:
            skipped.append(SkippedLine(line_number, "comment", line))
            if "-->" in stripped:
                in_comment = False
            continue
        if _HEADING_RE.match(line):
            in_region = False
            _count_outside_region(line_number, line, table_lines, unparsed)
            continue
        if stripped.startswith("<!--"):
            skipped.append(SkippedLine(line_number, "comment", line))
            in_comment = "-->" not in stripped[len("<!--") :]
            continue
        if not stripped:
            skipped.append(SkippedLine(line_number, "blank", line))
            continue
        if not stripped.startswith("|"):
            skipped.append(SkippedLine(line_number, "prose", line))
            continue
        if _SEPARATOR_RE.match(stripped):
            skipped.append(SkippedLine(line_number, "separator", line))
            continue

        table_lines.append(TableLine(line_number, line))
        cells = split_row_cells(stripped)
        if len(cells) != COLUMN_COUNT:
            unparsed.append(UnparsedLine(line_number, f"cell-count {len(cells)}", line))
            continue
        built = _row_from_cells(line_number, cells)
        if isinstance(built, str):
            unparsed.append(UnparsedLine(line_number, built, line))
            continue
        rows.append(built)

    return IndexTable(
        rows=rows,
        table_lines=table_lines,
        unparsed=unparsed,
        skipped=skipped,
        duplicates=_find_duplicates(rows),
        header_line=header_index + 1 if separator_index is not None else None,
    )


def detect_index_shape(content: str) -> str:
    """Classify a plans index file as `"generated"`, `"legacy"` or `"empty"`.

    `"generated"`: a `Generated:` line and the `| Abbrev |` header row are
    both present. `"legacy"`: the header row is present without a `Generated:`
    line, the shape written by hand. `"empty"`: no header row, a fresh or
    unrecognized file.
    """
    if not _HEADER_LINE_RE.search(content):
        return "empty"
    if _GENERATED_LINE_RE.search(content):
        return "generated"
    return "legacy"
