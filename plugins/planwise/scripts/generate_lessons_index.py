#!/usr/bin/env python3
"""Scan lesson-file frontmatter and render the Lessons Learned index rows.

Every lesson file's YAML frontmatter is the single source of truth for its
index row. This module reads that frontmatter and renders it; it never
writes a lesson file, and it never invents a value for a missing required
key -- a missing key is reported and the run aborts, because a generator
that quietly patches a gap is indistinguishable from one that lost data.

This module covers the full generator: text-level frontmatter extraction,
the 10-column row, hub-vs-Archive membership, the header/counter/footer
text, and the legacy-index predicate (the scan/render half), plus the
per-file token-budget splitter, the hub and Archive-shard file builders,
`--dry-run`/`--check`/`--write`/`--json`/`--replace-legacy`, drift
classification against the on-disk generated set, and the atomic write.

## Hub membership

Hub membership is decided by frontmatter `status:` alone (`HUB_STATUSES`),
never by which directory a file happens to sit in. A lesson whose directory
disagrees with its status (a hub-status lesson filed under `Archive/`, or a
non-hub-status lesson left at top level) is recorded as a location anomaly
and still routed by its status.

## Frontmatter is read at the text level, never through a typed YAML load

A typed load resolves an unquoted, zero-padded numeric id to an integer
under YAML 1.1's implicit-octal rule, silently losing its padding and its
canonical form. `id:` and every other frontmatter value are read as raw
text via `frontmatter_parser.parse_frontmatter_map` instead, exactly the
discipline `generate_backlog_index`'s own item scanner already applies.

## CRLF frontmatter

`reconcile_common.read_text_preserving_newlines` preserves a file's own
line endings verbatim -- for a CRLF-shipped lesson file that means every
line keeps its trailing `\r`. `frontmatter_parser.split_frontmatter_block`
locates the frontmatter fence with an LF-only pattern (`"---\n"` /
`"\n---\n"`), so it cannot find the fence at all in a CRLF file unless line
endings are normalised first. This module normalises `\r\n` to `\n` right
after the preserving read, before the split -- `parse_frontmatter_map`'s
own per-line `.strip()`/`.rstrip()` then guarantees no stray `\r` survives
into any extracted value.

## The File cell's relative-link convention

`File` is `[NNN](relative path)`, computed with `_relative_link` from the
directory of the generated file a row is rendered into, to the lesson's
real on-disk location -- never a hardcoded prefix. The SAME lesson file
therefore renders a different relative path depending on which generated
file the row sits in: a hub row emits from the lessons directory itself, an
Archive-shard row emits from its `Archive/` subdirectory. `render_row`
takes that directory as an explicit `emit_dir` argument rather than
assuming one, so both cases go through the identical code path.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows consoles default stdout to cp1252, which cannot encode the em
# dashes and curly quotes several lesson titles carry.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config_loader import load_config
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from generate_backlog_index import (
    HUB_TOKEN_BUDGET,
    MEASUREMENT_BASIS,
    TITLE_MAX_LEN,
    _atomic_write_files,
    _budget_fields,
    _changelog_filename,
    _escape_cell,
    _generated_line,
    _hub_filename,
    _hub_leaf_entries,
    _id_range,
    _index_naming,
    _list_disk_generated_files,
    _measure,
    _relative_link,
    _shard_filename,
    _shipped_bytes,
    detect_line_ending,
    is_generated_index_file,
    render_shards_section,
    truncate_title,
)
from parse_lessons import (
    LESSON_FILE_RE,
    LESSON_ROW_RE,
    compute_next_id,
    detect_index_shape,
    duplicate_ids,
    format_id,
    lesson_files,
    parse_generated_table,
    parse_index,
)
from read_limits import READ_TOKEN_WARN, estimate_tokens
from reconcile_common import read_text_preserving_newlines

# --------------------------------------------------------------------------
# Column layout
#
# Position is asserted here by named constant, not by a comment next to a
# list literal, mirroring generate_backlog_index's own schema module -- a
# shift that only a comment recorded would not fail until something
# downstream silently read the wrong column.
# --------------------------------------------------------------------------

COL_ID = 0
COL_TITLE = 1
COL_CATEGORY = 2
COL_SEVERITY = 3
COL_LANGUAGE = 4
COL_TECHNOLOGY = 5
COL_DOMAIN = 6
COL_SOURCE = 7
COL_STATUS = 8
COL_FILE = 9
COLUMN_COUNT = 10

HEADER_CELLS = [
    "ID", "Title", "Category", "Severity", "Language", "Technology",
    "Domain", "Source", "Status", "File",
]

assert len(HEADER_CELLS) == COLUMN_COUNT
assert HEADER_CELLS[COL_ID] == "ID"
assert HEADER_CELLS[COL_TITLE] == "Title"
assert HEADER_CELLS[COL_CATEGORY] == "Category"
assert HEADER_CELLS[COL_SEVERITY] == "Severity"
assert HEADER_CELLS[COL_LANGUAGE] == "Language"
assert HEADER_CELLS[COL_TECHNOLOGY] == "Technology"
assert HEADER_CELLS[COL_DOMAIN] == "Domain"
assert HEADER_CELLS[COL_SOURCE] == "Source"
assert HEADER_CELLS[COL_STATUS] == "Status"
assert HEADER_CELLS[COL_FILE] == "File"
assert COL_STATUS == 8               # a reader may key off status at a literal index
assert COL_FILE == COLUMN_COUNT - 1  # a reader may key off file at len(cells)-1

# The nine keys every lesson file's frontmatter must carry. `date:`,
# `applied-as:`, `promoted-to:`, `promoted-date:` and any unknown key are
# read (if present) and ignored -- this generator never writes them back.
REQUIRED_KEYS = (
    "id", "title", "category", "severity", "language",
    "technology", "domain", "source", "status",
)

# Hub membership: decided by status alone, never by directory (see the
# module docstring). Everything else shards to an Archive-century file.
HUB_STATUSES = frozenset({"documented", "orphaned"})

# Fallback declared-status set when config.yaml carries no `lesson_statuses:`
# key at all. `HUB_STATUSES` (a subset) stays the hub-routing rule either way.
_DEFAULT_LESSON_STATUSES = ("documented", "orphaned", "promoted", "applied", "rule")


def _resolve_valid_statuses(config: dict) -> frozenset:
    """The declared `lesson_statuses:` set, or `_DEFAULT_LESSON_STATUSES`
    when the key is absent from `config.yaml` entirely -- printing one
    stderr note naming the fallback. Without this, `config.get(...) or []`
    resolves a missing key to an empty `frozenset()`, and since nothing is
    ever a member of an empty set, EVERY lesson's status fails the
    membership check and the whole run refuses -- a project whose
    config.yaml predates this key must still generate cleanly. A key that
    IS present but set to an empty list is left empty, not defaulted: that
    is a deliberate project choice, and silently overriding it would hide
    a real misconfiguration instead of reporting it.
    """
    raw = config.get("lesson_statuses")
    if raw is None:
        print(
            "Note: config.yaml declares no lesson_statuses; falling back "
            f"to the default set ({', '.join(_DEFAULT_LESSON_STATUSES)}).",
            file=sys.stderr,
        )
        return frozenset(_DEFAULT_LESSON_STATUSES)
    return frozenset(raw)


class LessonsGeneratorError(Exception):
    """A scan/render condition that must abort before any row renders (a
    missing required key, an unreadable id, an undeclared status), or the
    signal `is_legacy_index` raises for a write path to refuse on unless a
    caller explicitly opts to replace a legacy-shaped on-disk index.
    """


# --------------------------------------------------------------------------
# Frontmatter extraction (mirrors generate_backlog_index's item scanner,
# re-written for the lessons schema and its list-shaped fields)
# --------------------------------------------------------------------------

# Ported from score_backlog.py's `_strip_inline_comment` (not imported --
# score_backlog pulls in scoring-only imports this module has no use for),
# then made quote-aware here. `parse_frontmatter_map` hands back a key's raw
# value text verbatim, trailing comment included -- unlike a typed YAML
# load, which strips a comment at the tokenizer level regardless of
# position. Without this, a flow-form list like `technology: [python,
# yaml]  # two` would carry the comment into the last entry. Applied
# line-by-line so a block-form multi-line value (each `- item` on its own
# line) strips a per-line comment without disturbing sibling lines.
#
# Quote-awareness: a raw value may open with a matching `'`/`"` (a
# block-list line may prefix it with `- ` first). Per YAML, a `#` inside a
# quoted scalar is text, never a comment start -- only a `#` appearing
# AFTER the closing quote can begin a comment. An unquoted value keeps the
# plain rule: the first ` #`/`\t#` starts a comment.
_TRAILING_COMMENT_RE = re.compile(r"[ \t]+#.*$")


def _find_closing_quote(value: str, quote: str):
    """Index of `value`'s closing `quote` (which opens `value[0]`), honouring
    `\\"`/`\\\\` escapes inside a double-quoted scalar and `''`-doubling
    inside a single-quoted one. `None` if the quote never closes."""
    i = 1
    n = len(value)
    while i < n:
        ch = value[i]
        if quote == '"' and ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == quote:
            if quote == "'" and i + 1 < n and value[i + 1] == "'":
                i += 2
                continue
            return i
        i += 1
    return None


def _strip_comment_from_line(line: str) -> str:
    """Strip a trailing YAML inline comment from one line, quote-aware."""
    stripped = line.lstrip()
    lead_len = len(line) - len(stripped)
    marker_len = 0
    if stripped[:1] == "-":
        rest = stripped[1:]
        marker_len = 1 + (len(rest) - len(rest.lstrip()))
    value_start = lead_len + marker_len
    value = line[value_start:]
    if value[:1] in ("'", '"'):
        close = _find_closing_quote(value, value[0])
        if close is not None:
            head = line[: value_start + close + 1]
            tail = _TRAILING_COMMENT_RE.sub("", line[value_start + close + 1 :])
            return head + tail
        # Unterminated quote -- nothing after it is comment territory.
        return line
    return _TRAILING_COMMENT_RE.sub("", line)


def _strip_inline_comment(raw: str) -> str:
    """Strip a trailing YAML inline comment from each line of `raw`,
    quote-aware (see the module comment above this function)."""
    return "\n".join(_strip_comment_from_line(line) for line in raw.split("\n"))


def _unescape_double_quoted(inner: str) -> str:
    """Unescape `\\"` to `"` and `\\\\` to `\\` inside a double-quoted
    scalar's already-unquoted inner text, single pass so escape order
    cannot be misread as it would be under sequential `str.replace`."""
    out = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == "\\" and i + 1 < n and inner[i + 1] in ('"', "\\"):
            out.append(inner[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present, and
    unescape the scalar's own escape sequences: a double-quoted value
    unescapes `\\"` and `\\\\`, and a single-quoted value unescapes `''`
    to a literal `'`. An unquoted value passes through unchanged."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1]
        if text[0] == '"':
            return _unescape_double_quoted(inner)
        return inner.replace("''", "'")
    return text


_ID_VALUE_RE = re.compile(r"^(?:LL-)?0*(\d+)$")


def _normalize_id_text(raw: str) -> int:
    """Normalise a frontmatter `id:` value to its integer form.

    Accepts a bare digit string, an `LL-`-prefixed form, and a quoted
    form of either. `format_id` renders the canonical `LL-{n:03d}` text
    back out at render time -- this function is never the render step.
    """
    text = _strip_quotes(raw.strip()).strip()
    match = _ID_VALUE_RE.match(text)
    if not match:
        raise LessonsGeneratorError(f"non-numeric id value {raw!r}")
    return int(match.group(1))


_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")


def _split_flow_list_items(inner: str) -> list:
    """Split a flow-list's bracket-stripped inner text on top-level commas,
    quote-aware: a comma inside a `'...'`/`"..."` item is text, never a
    separator, per the same `_find_closing_quote` rule the comment strip
    uses."""
    items = []
    i = 0
    n = len(inner)
    start = 0
    while i < n:
        ch = inner[i]
        if ch in ("'", '"'):
            close = _find_closing_quote(inner[i:], ch)
            i = i + close + 1 if close is not None else i + 1
            continue
        if ch == ",":
            items.append(inner[start:i])
            i += 1
            start = i
            continue
        i += 1
    items.append(inner[start:])
    return items


def _parse_list_field(raw: str) -> list:
    """Parse a `language:`/`technology:`/`domain:`-shaped frontmatter value
    into a list of strings.

    Handles both the flow form written on the key's own line
    (``language: [python, yaml]``) and the block form spread over indented
    `- ` lines, since `parse_frontmatter_map` hands back either shape as
    the key's raw, un-typed value text. Each item is quote-stripped and
    unescaped with the same `_strip_quotes` helper the scalar fields use,
    so a quoted item never keeps its quote characters in the rendered
    cell. The caller comma-joins the result for the rendered cell.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [
            _strip_quotes(part.strip())
            for part in _split_flow_list_items(inner)
            if part.strip()
        ]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_strip_quotes(match.group(1).strip()))
    return items


def _read_frontmatter_map(path: Path) -> dict:
    raw_content = read_text_preserving_newlines(path)
    # See the module docstring's CRLF section: split_frontmatter_block's
    # fence check is LF-only, so a CRLF file's line endings are normalised
    # before the split.
    content = raw_content.replace("\r\n", "\n")
    parts = split_frontmatter_block(content)
    if parts is None:
        raise LessonsGeneratorError(f"{path}: no well-formed frontmatter block")
    raw_text, _body = parts
    fm_map = parse_frontmatter_map(raw_text)
    if fm_map is None:
        raise LessonsGeneratorError(f"{path}: frontmatter block could not be parsed")
    return fm_map


def _extract_fields(path: Path, raw_map: dict, valid_statuses: frozenset) -> dict:
    """Turn a raw {key: value-text} map into the nine typed fields.

    Raises when a required key is absent or empty, or when `status:` is
    not one of the project's declared lesson statuses -- the generator
    reports and stops; it never fills one in.
    """
    missing = [key for key in REQUIRED_KEYS if key not in raw_map]
    if missing:
        raise LessonsGeneratorError(
            f"{path}: missing required frontmatter key(s): {', '.join(missing)}"
        )

    # Strip a trailing inline comment from every raw value before any
    # further parse -- one pass covers id, the scalar fields, and both
    # list-field shapes.
    stripped = {key: _strip_inline_comment(value) for key, value in raw_map.items()}

    fields: dict = {}
    for key in ("title", "category", "severity", "source", "status"):
        value = _strip_quotes(stripped[key].strip())
        if not value:
            raise LessonsGeneratorError(f"{path}: frontmatter key '{key}' is empty")
        fields[key] = value

    if fields["status"] not in valid_statuses:
        raise LessonsGeneratorError(
            f"{path}: status {fields['status']!r} is not a declared lesson "
            f"status ({sorted(valid_statuses)})"
        )

    try:
        fields["id"] = _normalize_id_text(stripped["id"])
    except LessonsGeneratorError as exc:
        raise LessonsGeneratorError(
            f"{path}: unreadable id value {raw_map['id']!r} ({exc})"
        ) from exc

    for key in ("language", "technology", "domain"):
        fields[key] = _parse_list_field(stripped[key])

    fields["_path"] = path
    return fields


def _iter_lesson_files(lessons_dir: Path, archive_dir: Path, naming) -> list:
    """Every lesson file directly under `lessons_dir` and `Archive/` (each
    scanned non-recursively, BOTH directories always), as a list of
    `(path, in_archive)` pairs. Discovery goes through
    `parse_lessons.lesson_files` -- the same numbered-id, case-insensitive
    `.md` reader every other module in this project imports -- rather than
    a bare `glob('LL-*.md')`, which also matches a non-numbered name like
    `LL-template.md`: that file has no `LL-\\d+` id to extract, so scanning
    it either mis-scans as a lesson or (missing the required frontmatter
    keys) refuses the whole run over a file that was never a lesson. A
    generated index artifact this module itself would emit (the hub, an
    overflow leaf, or an Archive shard) is skipped -- it is never a lesson
    file.
    """
    pairs = []
    for id_path_pairs, in_archive in (
        (lesson_files(lessons_dir, None), False),
        (lesson_files(None, archive_dir), True),
    ):
        for _lesson_id, path in id_path_pairs:
            if is_generated_index_file(path.name, naming):
                continue
            pairs.append((path, in_archive))
    return pairs


def _check_id_mismatch(path: Path, frontmatter_id: int):
    """None, or a dict naming a lesson whose filename number disagrees
    with its own frontmatter `id:`."""
    match = LESSON_FILE_RE.match(path.name)
    if match is None:
        return None
    filename_id = int(match.group(1))
    if filename_id != frontmatter_id:
        return {"path": path, "filename_id": filename_id, "frontmatter_id": frontmatter_id}
    return None


@dataclass
class LessonScanResult:
    """The result of scanning every lesson file: the extracted, id-sorted
    fields, every filename/frontmatter id mismatch found, and every id
    claimed by more than one file (an anomaly recorded here, not raised --
    a later write path maps it to a refusal).
    """

    items: list
    id_mismatches: list = field(default_factory=list)
    duplicate_ids: dict = field(default_factory=dict)


def scan_lessons(
    lessons_dir: Path, archive_dir: Path, index_path: Path, valid_statuses: frozenset
) -> LessonScanResult:
    """Scan every lesson file and return its extracted fields, id-sorted.

    Every file is checked before any error is raised, so one run reports
    every offending file rather than only the first one found.
    """
    naming = _index_naming(index_path)
    errors = []
    items = []
    id_mismatches = []
    for path, in_archive in _iter_lesson_files(lessons_dir, archive_dir, naming):
        try:
            raw_map = _read_frontmatter_map(path)
            fields = _extract_fields(path, raw_map, valid_statuses)
        except LessonsGeneratorError as exc:
            errors.append(str(exc))
            continue
        fields["_in_archive"] = in_archive
        mismatch = _check_id_mismatch(path, fields["id"])
        if mismatch is not None:
            id_mismatches.append(mismatch)
        items.append(fields)

    if errors:
        raise LessonsGeneratorError("\n".join(errors))

    pairs = [(item["id"], item["_path"]) for item in items]
    dups = duplicate_ids(pairs)

    items.sort(key=lambda item: item["id"])
    return LessonScanResult(items=items, id_mismatches=id_mismatches, duplicate_ids=dups)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_file_cell(item_id: int, path: Path, emit_dir: Path) -> str:
    padded = f"{item_id:03d}"
    return f"[{padded}]({_relative_link(emit_dir, path)})"


def render_row(item: dict, emit_dir: Path):
    """Render one lesson's fields into a 10-cell table row.

    Returns (row_text, title_was_truncated). `emit_dir` is the directory
    of the generated file this row is rendered into -- see the module
    docstring's File-cell section.
    """
    rendered_title, was_truncated = truncate_title(item["title"])
    cells = [""] * COLUMN_COUNT
    cells[COL_ID] = format_id(item["id"])
    cells[COL_TITLE] = _escape_cell(rendered_title)
    cells[COL_CATEGORY] = _escape_cell(item["category"])
    cells[COL_SEVERITY] = _escape_cell(item["severity"])
    cells[COL_LANGUAGE] = _escape_cell(", ".join(item["language"]))
    cells[COL_TECHNOLOGY] = _escape_cell(", ".join(item["technology"]))
    cells[COL_DOMAIN] = _escape_cell(", ".join(item["domain"]))
    cells[COL_SOURCE] = _escape_cell(item["source"])
    cells[COL_STATUS] = _escape_cell(item["status"])
    cells[COL_FILE] = _render_file_cell(item["id"], item["_path"], emit_dir)
    assert len(cells) == COLUMN_COUNT
    row = "|" + "|".join(f" {cell} " for cell in cells) + "|"
    return row, was_truncated


def render_header() -> str:
    return "|" + "|".join(f" {cell} " for cell in HEADER_CELLS) + "|"


def render_separator() -> str:
    return "|" + "|".join(["---"] * COLUMN_COUNT) + "|"


# --------------------------------------------------------------------------
# Membership and partition
# --------------------------------------------------------------------------


def is_hub_lesson(item: dict) -> bool:
    return item["status"] in HUB_STATUSES


def shard_for(lesson_id) -> int:
    """The ID-century shard number: (id - 1) // 100. A pure function of
    the id alone, mirrored from generate_backlog_index's own `shard_for`
    rather than imported (the backlog and lessons partitions key off
    different fields).
    """
    return (int(lesson_id) - 1) // 100


def partition_lessons(items: list) -> tuple:
    """Split id-sorted `items` into the hub list and the non-hub items
    grouped by `shard_for` century. A lesson's directory is never read as
    a routing input; only `status:` decides.
    """
    hub_items = []
    by_century: dict = {}
    for item in items:
        if is_hub_lesson(item):
            hub_items.append(item)
        else:
            by_century.setdefault(shard_for(item["id"]), []).append(item)
    return hub_items, by_century


def detect_location_anomalies(items: list) -> list:
    """A lesson whose directory disagrees with its status: a hub-status
    lesson filed under `Archive/`, or a non-hub-status lesson left at top
    level. Routed by status regardless (see `partition_lessons`); this
    only records the disagreement for a later check to report.
    """
    anomalies = []
    for item in items:
        if is_hub_lesson(item) == item["_in_archive"]:
            anomalies.append({
                "path": item["_path"],
                "status": item["status"],
                "in_archive": item["_in_archive"],
            })
    return anomalies


# --------------------------------------------------------------------------
# Header, counter, footer
# --------------------------------------------------------------------------

_PROMOTION_LOG_HUB_RE = re.compile(r"^00-Index-(.+)$")


def _promotion_log_filename(naming) -> str:
    """The one namer for the promotion-log file, the same shape as
    `_changelog_filename`: `00-Index-{X}{suffix}` -> `00-PromotionLog-{X}
    {suffix}`; a hub that does not follow that shape falls back to
    `00-{hub_stem}-PromotionLog{suffix}`.
    """
    match = _PROMOTION_LOG_HUB_RE.match(naming.hub_stem)
    if match:
        return f"00-PromotionLog-{match.group(1)}{naming.suffix}"
    return f"00-{naming.hub_stem}-PromotionLog{naming.suffix}"


def render_counter_line(next_id: int) -> str:
    return f"**Next available ID:** {format_id(next_id)}\n"


def render_header_block(next_id: int) -> str:
    """`_generated_line()`, then the counter line, then a blank line. The
    generated hub carries no `## Master Table` heading -- the table sits
    directly under this block. `next_id` is the derived value from
    `parse_lessons.compute_next_id`, floored (never lowered) against
    whatever counter is already on disk by `_counter_floor` -- the caller
    passes the floored value in, this function never reads a line itself.
    """
    return _generated_line() + render_counter_line(next_id) + "\n"


def _footer_line(naming) -> str:
    """The two fixed footer pointers: a changelog link, then a promotion-
    log link. Neither file is ever written by this generator.
    """
    return (
        f"[Changelog]({_changelog_filename(naming)})\n"
        f"[Promotion Log]({_promotion_log_filename(naming)})\n"
    )


# --------------------------------------------------------------------------
# Legacy-shape predicate
# --------------------------------------------------------------------------


def is_legacy_index(content: str) -> bool:
    """True when `content` is a legacy-shaped lessons index (a
    `## Master Table` or `## Rule Promotion Log` heading present in the
    hub path) -- delegates entirely to `parse_lessons.detect_index_shape`,
    never re-derived. A write path refuses on this result unless a caller
    explicitly opts to replace a legacy-shaped index.
    """
    return detect_index_shape(content) == "legacy"


_LEGACY_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _legacy_headings_to_drop(content: str) -> list:
    """Every `## ` heading in a legacy hub's raw content that
    `--replace-legacy` silently drops -- every H2 except `## Master
    Table`, whose row DATA migrates into the generated table (the heading
    structure around it does not, and neither does anything else). A real
    project's legacy hub typically accumulates hand-written prose sections
    here -- Naming Convention, Status Definitions, Quick Reference, Lesson
    File Template, Archive, the Rule Promotion Log pointer note -- that
    this generator has no migration path for (a later session relocates
    them); this function migrates nothing itself, it only names what is
    about to be lost so the operator sees it, on a legacy-hub refusal and
    on the `--replace-legacy` run that actually drops them.
    """
    return [
        heading.strip() for heading in _LEGACY_HEADING_RE.findall(content)
        if heading.strip() != "Master Table"
    ]


# --------------------------------------------------------------------------
# Table-body rendering (mirrors generate_backlog_index's render_table_body,
# re-written to call this module's own render_row/render_header/
# render_separator instead of the backlog renderer)
# --------------------------------------------------------------------------


def _render_lessons_table_body(items: list, emit_dir: Path) -> tuple:
    """Render `items` into one table body: header, separator, one row per
    item, each through `render_row` (see the module docstring's File-cell
    section for what `emit_dir` controls). Returns (body_text,
    truncated_ids) -- `truncated_ids` is every id whose Title cell was
    truncated, in canonical `LL-NNN` form, matching what a report entry's
    `truncated_ids` field carries.
    """
    lines = [render_header(), render_separator()]
    truncated_ids = []
    for item in items:
        row, was_truncated = render_row(item, emit_dir)
        lines.append(row)
        if was_truncated:
            truncated_ids.append(format_id(item["id"]))
    return "\n".join(lines) + "\n", truncated_ids


# --------------------------------------------------------------------------
# Per-file token budget: the splitter with the wrapper reserve
# --------------------------------------------------------------------------


def split_lessons_to_budget(
    items: list, from_dir: Path, wrapper_tokens: int = 0, budget: int = READ_TOKEN_WARN
) -> list:
    """Mirrors generate_backlog_index.split_items_to_budget, re-written to
    render through this module's own `_render_lessons_table_body` (which
    calls `render_row`) instead of the backlog renderer.

    Recursively splits `items` until the rendered table body, PLUS the
    caller's `wrapper_tokens` reserve, is under `budget`: the split
    decision measures body-plus-wrapper, the same quantity the
    shipped file will actually carry, never the bare body alone. A single
    item that alone (plus the wrapper reserve) cannot fit under budget
    raises `LessonsGeneratorError` naming its id -- no file is ever shipped
    over budget. Returns a list of leaves, each `(subset, body, num_bytes,
    tokens, truncated_ids)`; `tokens` is the BARE body's token count, not
    body+wrapper, matching `split_items_to_budget`'s own contract.
    """
    body, truncated = _render_lessons_table_body(items, from_dir)
    num_bytes, tokens = _measure(body)
    if tokens + wrapper_tokens < budget:
        return [(items, body, num_bytes, tokens, truncated)]
    if len(items) == 1:
        item = items[0]
        raise LessonsGeneratorError(
            f"{item['_path']}: lesson {format_id(item['id'])} alone renders "
            f"to {tokens} tokens ({num_bytes} bytes; basis: "
            f"{MEASUREMENT_BASIS}) plus a {wrapper_tokens}-token wrapper "
            f"reserve -- exceeds the {budget}-token budget and cannot be "
            f"reduced by sharding further"
        )
    mid = len(items) // 2
    return (
        split_lessons_to_budget(items[:mid], from_dir, wrapper_tokens, budget)
        + split_lessons_to_budget(items[mid:], from_dir, wrapper_tokens, budget)
    )


# --------------------------------------------------------------------------
# Hub and shard file assembly
# --------------------------------------------------------------------------


def _hub_continuation_wrapper(naming) -> str:
    """The backlink line every hub overflow leaf opens with."""
    return f"[Back to Lessons Index]({naming.hub_name})\n\n"


def hub_wrapper_tokens(
    shards_section: str, naming, next_id: int, header_block: str | None = None
) -> int:
    """Mirrors generate_backlog_index.hub_wrapper_tokens -- re-written
    because its signature does not fit the lessons wrapper: the lessons
    header block carries a computed counter line (`render_header_block`)
    that backlog's bare `Generated:` line does not, and the footer
    is two fixed pointers (Changelog, Promotion Log) rather than backlog's
    one. Same shape otherwise: the LARGER of leaf 0's full wrapper (header
    block + the '## Shards' directory + the footer) and a continuation
    leaf's backlink line, on the CRLF worst-case basis -- one definition,
    so the reserve the splitter is given and the wrapper leaf 0 actually
    ships cannot drift apart.
    """
    if header_block is None:
        header_block = render_header_block(next_id)
    leaf0_wrapper = header_block + "\n" + shards_section + "\n" + _footer_line(naming)
    wrapper_bytes = max(
        _shipped_bytes(leaf0_wrapper),
        _shipped_bytes(_hub_continuation_wrapper(naming)),
    )
    return estimate_tokens(wrapper_bytes)


def build_lessons_hub_files(
    hub_items: list, lessons_dir: Path, shard_entries: list, naming, next_id: int,
    budget: int = HUB_TOKEN_BUDGET,
) -> list:
    """Mirrors generate_backlog_index.build_hub_files, re-written to render
    through this module's own splitter/renderer and to carry the lessons
    header block and two-pointer footer instead of backlog's.

    Leaf 0 carries the header block (`render_header_block`), the
    table, the '## Shards' directory (Archive shards plus every hub
    overflow leaf this split produces), and the two footer pointers. The
    directory's size depends on the split's own leaf boundaries, and the
    split depends on the directory's size (via the wrapper reserve), so the
    two are iterated to a fixed point exactly as `build_hub_files` does --
    see its docstring for why this converges and why a stable leaf count is
    enough to trust it. After convergence: the completeness assertion
    (every hub item appears in exactly one leaf, no item lost or
    duplicated) is a raise, not a warning, and the post-assembly
    `_measure(assembled_leaf) < budget` check on every leaf is a can't-fire
    assertion when the reserve above was computed correctly -- kept as a
    raise all the same.

    `next_id` is threaded through explicitly (not in the pinned signature
    below) because the header block's counter line needs it and nothing
    else in this call graph computes it.
    """
    header_block = render_header_block(next_id)
    continuation_wrapper = _hub_continuation_wrapper(naming)
    footer_line = _footer_line(naming)

    def _split(section: str) -> list:
        reserve = hub_wrapper_tokens(section, naming, next_id, header_block)
        return split_lessons_to_budget(hub_items, lessons_dir, reserve, budget)

    leaves = _split(render_shards_section(shard_entries))
    max_rounds = len(hub_items) + 1
    for _round in range(max_rounds):
        leaf_entries = _hub_leaf_entries(leaves, naming)
        shards_section = render_shards_section(shard_entries + leaf_entries)
        next_leaves = _split(shards_section)
        converged = len(next_leaves) == len(leaves)
        leaves = next_leaves
        if converged:
            break
    else:
        raise LessonsGeneratorError(
            f"{naming.hub_name}: the hub directory and its overflow split "
            f"did not reach a stable leaf count within {max_rounds} rounds "
            f"-- report it as a bug in the directory fixed point"
        )
    if leaf_entries != _hub_leaf_entries(leaves, naming):
        raise LessonsGeneratorError(
            f"{naming.hub_name}: the '## Shards' directory lists overflow "
            f"leaves that differ from the leaves being shipped -- this "
            f"should be unreachable; report it as a bug in the directory "
            f"fixed point"
        )

    # Completeness: every hub item appears in exactly one leaf.
    covered_ids = []
    for subset, *_rest in leaves:
        covered_ids.extend(item["id"] for item in subset)
    expected_ids = [item["id"] for item in hub_items]
    if sorted(covered_ids) != sorted(expected_ids):
        raise LessonsGeneratorError(
            f"{naming.hub_name}: hub split lost or duplicated items -- "
            f"expected {sorted(expected_ids)}, covered {sorted(covered_ids)}"
        )

    split = len(leaves) > 1
    files = []
    for index, (subset, body, _num_bytes, _tokens, truncated) in enumerate(leaves):
        min_id, max_id = _id_range(subset) if subset else (0, 0)
        filename = _hub_filename(naming, min_id, max_id, index)
        if index == 0:
            content = header_block + body + "\n" + shards_section + "\n" + footer_line
        else:
            content = continuation_wrapper + body
        num_bytes_final, tokens_final = _measure(content)
        if tokens_final >= budget:
            # Can't-fire assertion: unreachable on any input the
            # splitter above accepted, because the reserve given to it was
            # this exact wrapper's token cost.
            raise LessonsGeneratorError(
                f"{filename}: adding the directory/footer section pushed "
                f"the file to {tokens_final} tokens (basis: "
                f"{MEASUREMENT_BASIS}), >= the {budget}-token budget "
                f"despite a wrapper reserve computed at split time -- this "
                f"should be unreachable; report it as a bug in the reserve "
                f"calculation, not as an unshardable row"
            )
        files.append({
            "path": filename,
            "content": content,
            "rows": len(subset),
            "kind": "hub" if index == 0 else "hub-leaf",
            **_budget_fields(num_bytes_final, tokens_final, budget),
            "split": split,
            "min_id": min_id,
            "max_id": max_id,
            "truncated_ids": truncated,
        })
    return files


def build_lessons_shard_files(
    by_century: dict, lessons_dir: Path, archive_dir: Path, naming,
    budget: int = READ_TOKEN_WARN,
) -> list:
    """Mirrors generate_backlog_index.build_shard_files: one Archive-century
    file per group, split further only if a single century's table itself
    exceeds `budget`. Each shard opens with a backlink to the hub, derived
    from `naming` (never hardcoded), and rows render with `archive_dir` as
    their `emit_dir` -- see the module docstring's File-cell section: a
    shard row's File link differs from the same lesson's hub-row link.
    """
    files = []
    hub_path = lessons_dir / naming.hub_name
    backlink_target = _relative_link(archive_dir, hub_path)
    backlink_line = f"[Back to Lessons Index]({backlink_target})\n\n"
    wrapper_tokens = estimate_tokens(_shipped_bytes(backlink_line))
    for century in sorted(by_century):
        items = by_century[century]
        leaves = split_lessons_to_budget(items, archive_dir, wrapper_tokens, budget)
        split = len(leaves) > 1
        for subset, body, _num_bytes, _tokens, truncated in leaves:
            min_id, max_id = _id_range(subset)
            filename = _shard_filename(naming, min_id, max_id)
            shard_path = _relative_link(lessons_dir, archive_dir / filename)
            content = backlink_line + body
            num_bytes_final, tokens_final = _measure(content)
            if tokens_final >= budget:
                raise LessonsGeneratorError(
                    f"{shard_path}: adding the backlink line pushed the "
                    f"file to {tokens_final} tokens (basis: "
                    f"{MEASUREMENT_BASIS}), >= the {budget}-token budget "
                    f"despite a {wrapper_tokens}-token reserve at split "
                    f"time -- this should be unreachable; report it as a "
                    f"bug in the reserve calculation, not as an "
                    f"unshardable row"
                )
            files.append({
                "path": shard_path,
                "content": content,
                "rows": len(subset),
                "kind": "shard",
                **_budget_fields(num_bytes_final, tokens_final, budget),
                "split": split,
                "min_id": min_id,
                "max_id": max_id,
                "truncated_ids": truncated,
            })
    return files


def build_lessons_index_files(
    items: list, lessons_dir: Path, archive_dir: Path, naming, next_id: int
) -> dict:
    """Mirrors generate_backlog_index.build_index_files: partition, shard,
    and budget-enforce the full lessons set into a hub(+overflow) plus
    Archive-shard file set, entirely in memory. Each family is split
    against its own budget: READ_TOKEN_WARN for Archive shards,
    HUB_TOKEN_BUDGET for the hub and its overflow leaves.
    """
    hub_items, by_century = partition_lessons(items)
    shard_files = build_lessons_shard_files(
        by_century, lessons_dir, archive_dir, naming, budget=READ_TOKEN_WARN
    )
    hub_files = build_lessons_hub_files(
        hub_items, lessons_dir, shard_files, naming, next_id, budget=HUB_TOKEN_BUDGET
    )
    all_files = hub_files + shard_files
    truncated_ids = []
    for entry in all_files:
        truncated_ids.extend(entry.get("truncated_ids", []))
    return {"files": all_files, "truncated_ids": truncated_ids}


# --------------------------------------------------------------------------
# --check: drift classification
#
# The `Generated:` line is never part of any row's cells (it sits above the
# table header this walk starts from), so it never enters any comparison
# below -- structurally excluded, not filtered out by name.
# --------------------------------------------------------------------------

_COUNTER_LINE_RE = re.compile(r"\*\*Next available ID:\*\*\s*LL-(\d+)")


def _counter_floor(index_path: Path, derived_next: int) -> int:
    """The counter a `--write` actually ships: `max(derived_next, the
    counter value already on disk)`. The on-disk line is read only as a
    FLOOR here, never as a source of which ids are known -- the derivation
    in `parse_lessons.compute_next_id` stays the sole source for that. This
    is what makes the counter forward-only: removing the highest-numbered
    lesson file after a `--write` lowers `derived_next`, but the next
    `--write` still floors at the value already shipped, so the counter
    itself never moves backward.
    """
    if index_path is None or not index_path.exists():
        return derived_next
    raw_content = read_text_preserving_newlines(index_path)
    match = _COUNTER_LINE_RE.search(raw_content)
    if match is None:
        return derived_next
    on_disk_counter = int(match.group(1))
    return max(derived_next, on_disk_counter)


# row-shape names two sub-conditions: a row's cell count differing
# from the header, and the parsed-row count differing from the table-row
# count. The second can only happen via a dict-keyed read that silently
# collapses two physical rows into one entry -- `parse_lessons.py` never
# does this (it returns a LIST, walked and counted directly; see its module
# docstring), so that sub-condition is structurally impossible here, proven
# by construction rather than checked live. The first sub-condition is
# `Row.malformed` below, from `parse_lessons._walk_rows`.
#
# The full drift-class table, kept beside the code that produces each row:
#
#   stale-title            Title cell differs                          1
#   stale-status            Status cell differs                         1
#   stale-cell              any other cell differs (column named)       1
#   stale-counter            on-disk counter is BELOW the computed value  1
#   counter_ahead (anomaly)  on-disk counter is ABOVE the computed value  1
#                            (an id may have been retired; the counter is
#                            never lowered -- mirrors reconcile_lessons's
#                            own `counter_ahead` kind and treatment)
#   missing-row              a lesson file has no row                    1
#   extra-row                a row has no lesson file                    1
#   stale-generated-file     an on-disk generated file is not in the      1
#                            fresh set, or a fresh file is absent on disk
#   stale-wrapper            a generated file's non-table content        1
#                            (a footer pointer, the `## Shards` directory,
#                            a header cell, a continuation backlink)
#                            differs from the fresh render -- row-level
#                            classes keep precedence, because a row's own
#                            line is excluded from this comparison entirely
#   misplaced-row            a row sits in a different generated file      1
#                            than the fresh render puts it in, naming the
#                            id and both files
#   row-shape (anomaly)      a row's cell count differs from the header,   1
#                            or the parsed-row count differs from the
#                            table-row count
#   duplicate-id (anomaly)   two lesson files claim one id, or one id    1 (2 on
#                            has two rows                                --write)
#   id-mismatch (anomaly)    a lesson file's filename number disagrees   1 (2 on
#                            with its own frontmatter `id:`               --write)
#   location-anomaly         a directory/status disagreement              1
#                            (reported, never healed)
#   legacy-shape             the hub path holds a `## Master Table` or   1 (2 on
#                            `## Rule Promotion Log` heading             --write w/o
#                                                                        --replace-legacy)
#
# A row reorder within one file is NOT detected: `_wrapper_text` excludes
# every data-row line from the `stale-wrapper` comparison (row content is
# already compared by id, independent of position), so two rows swapping
# places produces identical wrapper text on both sides. If reorder
# detection is ever added, its class is `stale-wrapper` -- not a dedicated
# `row-order` class -- for the same reason no new class is minted for any
# other non-table difference.


def _wrapper_text(content: str) -> str:
    """`content` with every data-row line (`LESSON_ROW_RE` match), the
    `Generated:` line, and the counter line removed -- everything a
    generated file carries OUTSIDE its table rows AND outside the counter,
    which has its own dedicated `stale-counter`/`counter_ahead` classes:
    the header/separator row, the `## Shards` directory, the footer
    pointers, or a continuation leaf's backlink. Used only for the
    `stale-wrapper` comparison: comparing this instead of the raw file
    means a row-level class (stale-title, and so on) never ALSO reports
    stale-wrapper for the same edit, because the row's own line is not
    part of what this function returns -- and a counter-only edit never
    double-reports as stale-wrapper alongside stale-counter/counter_ahead,
    for the same reason.
    """
    return "\n".join(
        line for line in content.split("\n")
        if not LESSON_ROW_RE.match(line)
        and not line.startswith("Generated:")
        and not _COUNTER_LINE_RE.match(line)
    )


def _check_lessons_drift(
    items: list, report: dict, lessons_dir: Path, archive_dir: Path,
    index_path: Path, naming, next_id: int, config: dict, location_anomalies: list,
    duplicate_ids: dict, id_mismatches: list = (),
) -> tuple:
    """Compare the on-disk generated set (read once, through
    `parse_lessons.parse_index`) against the freshly computed `report`.
    `duplicate_ids` is `scan_lessons`'s own result (two lesson FILES
    claiming one id) -- reported here so a report mode sees it, not only
    `--write`. `id_mismatches` is likewise `scan_lessons`'s own result (a
    lesson file whose filename number disagrees with its own frontmatter
    `id:`) -- collected there but, before this fix, never surfaced to any
    caller; reported here the same way, in every report mode.

    Returns `(findings, shape)`. Each finding is `{"class", "id", "detail"}`
    naming the id or path per the drift-class table above `_wrapper_text`.
    When the on-disk shape is not `"generated"` (legacy or empty), the
    comparison is not meaningful row-by-row: a `legacy-shape` finding
    (when legacy) plus a `missing-row` finding for every known lesson is
    the expected pre-cutover reading, not a defect.
    """
    findings = []

    for anomaly in location_anomalies:
        findings.append({
            "class": "location-anomaly",
            "id": str(anomaly["path"]),
            "detail": f"status={anomaly['status']} in_archive={anomaly['in_archive']}",
        })

    # A lesson file whose filename number disagrees with its own
    # frontmatter `id:` -- reported by path, naming both ids, in every
    # report mode; `--write` refuses on it (see _WRITE_REFUSAL_CLASSES).
    for mismatch in id_mismatches:
        findings.append({
            "class": "id-mismatch", "id": str(mismatch["path"]),
            "detail": (
                f"filename says {format_id(mismatch['filename_id'])}, "
                f"frontmatter says {format_id(mismatch['frontmatter_id'])}"
            ),
        })

    # An on-disk duplicate id (two lesson FILES claiming one id) is
    # reported here, from the scan result -- independent of what the
    # on-disk index rows show, and regardless of shape, so a duplicate
    # planted before the second file's row was ever generated still
    # surfaces in every report mode, not only on `--write`.
    for lesson_id, paths in duplicate_ids.items():
        findings.append({
            "class": "duplicate-id", "id": format_id(lesson_id),
            "detail": f"claimed by {', '.join(str(p) for p in paths)}",
        })

    raw_content = read_text_preserving_newlines(index_path) if index_path.exists() else ""
    counter_match = _COUNTER_LINE_RE.search(raw_content)
    if counter_match:
        on_disk_counter = int(counter_match.group(1))
        if on_disk_counter < next_id:
            findings.append({
                "class": "stale-counter",
                "id": naming.hub_name,
                "detail": (
                    f"on-disk counter {format_id(on_disk_counter)} != "
                    f"computed {format_id(next_id)}"
                ),
            })
        elif on_disk_counter > next_id:
            # Mirrors reconcile_lessons.detect_drift's own "counter_ahead"
            # anomaly -- same kind name, same id/detail shape, same
            # non-blocking treatment: an id may have been retired
            # deliberately, and the counter is never lowered to match.
            findings.append({
                "class": "counter_ahead",
                "id": format_id(on_disk_counter),
                "detail": (
                    f"counter is ahead of the true next ID ({format_id(next_id)}) "
                    "-- an id may have been retired; never lowered automatically"
                ),
            })

    parsed = parse_index(config)

    if parsed.shape != "generated":
        if parsed.shape == "legacy":
            findings.append({
                "class": "legacy-shape",
                "id": naming.hub_name,
                "detail": "hub carries a legacy heading (## Master Table or ## Rule Promotion Log)",
            })
        for item in items:
            findings.append({
                "class": "missing-row",
                "id": format_id(item["id"]),
                "detail": "no on-disk generated row (index is not generated-shaped)",
            })
        return findings, parsed.shape

    known_ids = {item["id"] for item in items}
    fresh_by_id: dict = {}
    fresh_file_by_id: dict = {}
    for entry in report["files"]:
        for row in parse_generated_table(entry["content"], source=entry["path"]):
            if row.malformed:
                continue
            fresh_by_id[row.id] = row.cells
            fresh_file_by_id[row.id] = entry["path"]

    fresh_paths = {(lessons_dir / entry["path"]).resolve() for entry in report["files"]}
    disk_files = _list_disk_generated_files(lessons_dir, archive_dir, naming)
    disk_paths_resolved = {p.resolve() for p in disk_files}
    disk_content_by_path = {
        p.resolve(): p.read_text(encoding="utf-8") for p in disk_files
    }
    for path in disk_files:
        if path.resolve() not in fresh_paths:
            findings.append({
                "class": "stale-generated-file", "id": str(path),
                "detail": "on-disk generated file is not in the fresh set",
            })
    for entry in report["files"]:
        abs_path = (lessons_dir / entry["path"]).resolve()
        if abs_path not in disk_paths_resolved:
            findings.append({
                "class": "stale-generated-file", "id": entry["path"],
                "detail": "fresh file is absent on disk",
            })
        else:
            # Whole-file comparison, minus data rows and the
            # `Generated:` line -- catches a pointer edit, a removed
            # `## Shards` line, or a renamed header cell, none of which
            # the per-id row comparison below can see.
            if _wrapper_text(disk_content_by_path[abs_path]) != _wrapper_text(entry["content"]):
                findings.append({
                    "class": "stale-wrapper", "id": entry["path"],
                    "detail": "non-table content (a pointer, the '## Shards' "
                    "directory, a header cell, or a backlink) differs from "
                    "the fresh render",
                })

    disk_by_id: dict = {}
    disk_file_by_id: dict = {}
    for row in parsed.rows:
        if row.malformed:
            findings.append({
                "class": "row-shape", "id": f"{row.source}:{row.line}",
                "detail": row.reason,
            })
            continue
        disk_by_id[row.id] = row.cells
        disk_file_by_id[row.id] = str(row.source)

    for lesson_id, locations in parsed.duplicates.items():
        findings.append({
            "class": "duplicate-id", "id": format_id(lesson_id),
            "detail": f"appears more than once: {', '.join(locations)}",
        })
        disk_by_id.pop(lesson_id, None)
        disk_file_by_id.pop(lesson_id, None)

    for item_id, disk_cells in disk_by_id.items():
        if item_id not in known_ids:
            findings.append({
                "class": "extra-row", "id": format_id(item_id),
                "detail": f"row in {disk_file_by_id[item_id]} has no lesson file",
            })
            continue
        # A row that sits in a different generated file than the
        # fresh render puts it in -- checked by location, independent of
        # whether the row's cells also differ (a verbatim move can leave
        # every cell byte-identical to what shipped before the move).
        fresh_home = fresh_file_by_id.get(item_id)
        if fresh_home is not None:
            disk_home_abs = Path(disk_file_by_id[item_id]).resolve()
            fresh_home_abs = (lessons_dir / fresh_home).resolve()
            if disk_home_abs != fresh_home_abs:
                findings.append({
                    "class": "misplaced-row", "id": format_id(item_id),
                    "detail": (
                        f"on disk in {disk_file_by_id[item_id]}, the fresh "
                        f"render places it in {fresh_home}"
                    ),
                })
        fresh_cells = fresh_by_id.get(item_id)
        if fresh_cells is None or disk_cells == fresh_cells:
            continue
        if disk_cells[COL_TITLE] != fresh_cells[COL_TITLE]:
            findings.append({"class": "stale-title", "id": format_id(item_id), "detail": "Title cell differs"})
        elif disk_cells[COL_STATUS] != fresh_cells[COL_STATUS]:
            findings.append({"class": "stale-status", "id": format_id(item_id), "detail": "Status cell differs"})
        else:
            diff_idx = next(i for i in range(COLUMN_COUNT) if disk_cells[i] != fresh_cells[i])
            findings.append({
                "class": "stale-cell", "id": format_id(item_id),
                "detail": f"{HEADER_CELLS[diff_idx]} cell differs",
            })

    missing_ids = sorted(known_ids - disk_by_id.keys() - set(parsed.duplicates.keys()))
    for item_id in missing_ids:
        findings.append({
            "class": "missing-row", "id": format_id(item_id),
            "detail": f"no on-disk row yet (would be in {fresh_file_by_id.get(item_id, '?')})",
        })

    return findings, parsed.shape


_ANOMALY_CLASSES = frozenset({"row-shape", "duplicate-id", "counter_ahead", "id-mismatch"})


def _split_findings(findings: list) -> tuple:
    """Split the unified findings list into (drift, anomalies) for report
    presentation, mirroring generate_backlog_index's own drift/anomaly
    split: `row-shape` and `duplicate-id` are anomalies, every other class
    is ordinary drift. Both count toward the same exit code."""
    drift = [f for f in findings if f["class"] not in _ANOMALY_CLASSES]
    anomaly = [f for f in findings if f["class"] in _ANOMALY_CLASSES]
    return drift, anomaly


def _format_lessons_check_report(findings: list) -> str:
    if not findings:
        return "No drift detected. The index matches lesson frontmatter."
    drift, anomaly = _split_findings(findings)
    lines = []
    if drift:
        lines.append(f"Drift detected ({len(drift)} finding(s) out of sync with frontmatter):")
        for f in drift:
            lines.append(f"  - [{f['class']}] {f['id']}: {f['detail']}")
    else:
        lines.append("No drift detected.")
    if anomaly:
        if lines:
            lines.append("")
        lines.append(f"Anomalies ({len(anomaly)}):")
        for f in anomaly:
            lines.append(f"  - [{f['class']}] {f['id']}: {f['detail']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Exit-code mapping -- defined once, routed through from every mode
# --------------------------------------------------------------------------


class LessonsDisposition:
    """Mirrors generate_backlog_index.Disposition. Lessons has no
    reciprocal-edge case (there is no Blocks column); the parameter that
    replaces it is the legacy-shape/duplicate-id write refusal.
    """

    CLEAN = 0
    DRIFT_OR_ANOMALY = 1
    REFUSED = 2


_WRITE_REFUSAL_CLASSES = frozenset({"duplicate-id", "id-mismatch"})


def lessons_exit_code_for(*, write_mode: bool, findings: list, replace_legacy: bool = False) -> int:
    """Mirrors generate_backlog_index.exit_code_for. `--write` treats a
    duplicate id, a filename/frontmatter id mismatch, or a legacy-shaped
    hub without `--replace-legacy`, as REFUSED (2); every other mode (and
    every other finding) is ordinary DRIFT_OR_ANOMALY (1). A missing
    required key or an unshardable row
    never reaches this function -- both raise `LessonsGeneratorError`,
    handled by its own `except` block at each call site, exactly as
    `exit_code_for`'s own docstring describes for its `GeneratorError`.
    """
    if not findings:
        return LessonsDisposition.CLEAN
    if write_mode:
        refuses = any(f["class"] in _WRITE_REFUSAL_CLASSES for f in findings) or (
            not replace_legacy and any(f["class"] == "legacy-shape" for f in findings)
        )
        if refuses:
            return LessonsDisposition.REFUSED
    return LessonsDisposition.DRIFT_OR_ANOMALY


# --------------------------------------------------------------------------
# --write
# --------------------------------------------------------------------------


def _print_file_report(report: dict) -> None:
    for entry in report["files"]:
        print(
            f"{entry['path']}: {entry['kind']}, {entry['rows']} rows, "
            f"{entry['bytes']} bytes, {entry['tokens']} tokens, budget "
            f"{entry['budget']}, headroom {entry['headroom']}, "
            f"page_cap_ratio {entry['page_cap_ratio']} (basis: {entry['basis']})"
        )


def _file_summary(report: dict) -> list:
    return [
        {k: v for k, v in entry.items() if k not in ("content", "truncated_ids")}
        for entry in report["files"]
    ]


def _print_truncation_summary(truncated_ids: list) -> None:
    """One stderr line per run naming the truncation COUNT, printed
    only when it is nonzero -- replaces the earlier one-line-per-title
    warning, which buried a real `Error:` line at the live corpus's ~70%
    truncation rate. The ids themselves are unchanged: they still ship in
    the `--json` `"truncated"` list.
    """
    if truncated_ids:
        print(
            f"{len(truncated_ids)} title(s) truncated at {TITLE_MAX_LEN} "
            f'characters; see --json "truncated" for ids',
            file=sys.stderr,
        )


def _run_lessons_report_pipeline(
    lessons_dir: Path, archive_dir: Path, index_path: Path, naming, config: dict
):
    """Shared by every report mode (default/--dry-run and --check, which
    behave identically for this generator): a report mode
    always runs scan -> render -> split -> measure -> compare, and only
    --write may stop early. Raises `LessonsGeneratorError` for the caller
    to translate into REFUSED.

    `next_id_info["next"]` is the pure derived value (never floored) --
    passed on to `_check_lessons_drift` for stale-counter/counter_ahead
    classification. The fresh render passed to `_check_lessons_drift` (and
    to the caller for `--json`/printing) is built from the FLOORED value
    instead (`_counter_floor`), so a report never proposes a rendered
    counter line lower than what is already on disk.
    """
    valid_statuses = _resolve_valid_statuses(config)
    result = scan_lessons(lessons_dir, archive_dir, index_path, valid_statuses)
    next_id_info = compute_next_id(config)
    floored_next = _counter_floor(index_path, next_id_info["next"])
    report = build_lessons_index_files(result.items, lessons_dir, archive_dir, naming, floored_next)
    location_anomalies = detect_location_anomalies(result.items)
    return result, next_id_info, report, location_anomalies


def _cmd_write_lessons(
    lessons_dir: Path, archive_dir: Path, index_path: Path, naming, config: dict,
    *, replace_legacy: bool, json_out: bool,
) -> int:
    """Mirrors generate_backlog_index._cmd_write. Re-scans fresh (the only
    scan this command performs, by construction the race-safe "re-read
    immediately before healing" a write requires), refuses before touching
    disk on any unresolved condition, then atomically regenerates the hub
    (and every overflow leaf) and every shard, removing any stale
    generated file the fresh set no longer produces. Never touches a
    lesson file.
    """
    valid_statuses = _resolve_valid_statuses(config)
    try:
        result = scan_lessons(lessons_dir, archive_dir, index_path, valid_statuses)
    except LessonsGeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return LessonsDisposition.REFUSED

    write_findings = []
    for lesson_id, paths in result.duplicate_ids.items():
        write_findings.append({
            "class": "duplicate-id", "id": format_id(lesson_id),
            "detail": f"claimed by {', '.join(str(p) for p in paths)}",
        })
    for mismatch in result.id_mismatches:
        write_findings.append({
            "class": "id-mismatch", "id": str(mismatch["path"]),
            "detail": (
                f"filename says {format_id(mismatch['filename_id'])}, "
                f"frontmatter says {format_id(mismatch['frontmatter_id'])}"
            ),
        })
    raw_content = read_text_preserving_newlines(index_path) if index_path.exists() else ""
    is_legacy = is_legacy_index(raw_content)
    dropped_headings = _legacy_headings_to_drop(raw_content) if is_legacy else []
    if is_legacy:
        write_findings.append({
            "class": "legacy-shape", "id": naming.hub_name,
            "detail": "hub carries a legacy heading",
        })

    code = lessons_exit_code_for(write_mode=True, findings=write_findings, replace_legacy=replace_legacy)
    if code == LessonsDisposition.REFUSED:
        for f in write_findings:
            print(f"Anomaly: [{f['class']}] {f['id']}: {f['detail']}. Refusing to write.", file=sys.stderr)
        if dropped_headings:
            print(
                "--replace-legacy would drop these hand-written sections "
                "(never migrated -- relocate them first):",
                file=sys.stderr,
            )
            for heading in dropped_headings:
                print(f"  ## {heading}", file=sys.stderr)
        return LessonsDisposition.REFUSED

    if is_legacy and replace_legacy and dropped_headings:
        print("--replace-legacy is dropping these hand-written sections:")
        for heading in dropped_headings:
            print(f"  ## {heading}")

    next_id_info = compute_next_id(config)
    floored_next = _counter_floor(index_path, next_id_info["next"])
    try:
        report = build_lessons_index_files(result.items, lessons_dir, archive_dir, naming, floored_next)
    except LessonsGeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return LessonsDisposition.REFUSED

    fresh_paths = {(lessons_dir / entry["path"]).resolve() for entry in report["files"]}
    stale = [
        p for p in _list_disk_generated_files(lessons_dir, archive_dir, naming)
        if p.resolve() not in fresh_paths
    ]
    files_to_write = {lessons_dir / entry["path"]: entry["content"] for entry in report["files"]}

    line_ending = detect_line_ending(lessons_dir, archive_dir, naming)
    if line_ending != "\n":
        files_to_write = {
            path: content.replace("\n", line_ending) for path, content in files_to_write.items()
        }

    try:
        _atomic_write_files(files_to_write, stale)
    except OSError as exc:
        path = getattr(exc, "filename", None) or "unknown path"
        print(f"Error: write failed and was rolled back ({path}): {exc}", file=sys.stderr)
        return LessonsDisposition.REFUSED

    _print_truncation_summary(report["truncated_ids"])
    for p in stale:
        print(f"Removed stale generated file: {p}")

    if json_out:
        print(json.dumps(
            {"written": _file_summary(report), "removed": [str(p) for p in stale]}, indent=2
        ))
    else:
        print(f"Wrote {len(files_to_write)} file(s), removed {len(stale)} stale generated file(s).")
    return LessonsDisposition.CLEAN


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan lesson-file frontmatter and render/check/write the "
        "Lessons Learned index (hub, overflow leaves, Archive shards)."
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Render and measure without writing anything. This is also the "
        "default behavior when no mode flag is given.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Explicit synonym for the default report: every report mode "
        "always runs the full scan -> render -> split -> measure -> compare "
        "pipeline and reports drift/anomalies; only --write stops "
        "early on a refusal.",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Atomically regenerate the hub, every overflow leaf, and every "
        "shard, and remove any stale generated file. Refuses (exit 2) "
        "rather than writing on any unresolved condition -- a missing "
        "required key, an unshardable row, a duplicate id, or a "
        "legacy-shaped hub without --replace-legacy.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the per-file budget report, findings, shape, and basis "
        "as JSON instead of the flat table.",
    )
    parser.add_argument(
        "--replace-legacy", action="store_true",
        help="Allow --write to overwrite a legacy-shaped on-disk index.",
    )
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    lessons_dir = config["_lessons_dir"]
    index_path = config["_lessons_index"]
    if lessons_dir is None or index_path is None:
        print("Error: config.yaml declares no project.lessons_dir.", file=sys.stderr)
        return 2
    archive_dir = lessons_dir / "Archive"
    naming = _index_naming(index_path)

    if args.write:
        return _cmd_write_lessons(
            lessons_dir, archive_dir, index_path, naming, config,
            replace_legacy=args.replace_legacy, json_out=args.json,
        )

    try:
        result, next_id_info, report, location_anomalies = _run_lessons_report_pipeline(
            lessons_dir, archive_dir, index_path, naming, config
        )
    except LessonsGeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return LessonsDisposition.REFUSED

    _print_truncation_summary(report["truncated_ids"])

    findings, shape = _check_lessons_drift(
        result.items, report, lessons_dir, archive_dir, index_path, naming,
        next_id_info["next"], config, location_anomalies, result.duplicate_ids,
        result.id_mismatches,
    )
    code = lessons_exit_code_for(write_mode=False, findings=findings)

    if args.json:
        drift, anomaly = _split_findings(findings)
        payload = {
            "files": _file_summary(report),
            "truncated": report["truncated_ids"],
            "drift": drift,
            "anomalies": anomaly,
            "shape": shape,
            "basis": MEASUREMENT_BASIS,
        }
        print(json.dumps(payload, indent=2))
        return code

    _print_file_report(report)
    print()
    print(_format_lessons_check_report(findings))
    return code


if __name__ == "__main__":
    sys.exit(main())
