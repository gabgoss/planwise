#!/usr/bin/env python3
"""Scan backlog item frontmatter and render/check/write the Backlog Items index.

Every item file's YAML frontmatter is the single source of truth for its
index row. This module reads that frontmatter and renders it; it never
writes an item file, and it never invents a value for a missing required
key -- a missing key is reported and the run aborts, because a generator
that quietly patches a gap is indistinguishable from one that lost data.

Four stages, one file: scan + render (the 9-column row), shard + budget
(splitting a large table into hub/shard files under a per-file token
budget), score (filling the Score cell via `score_backlog.compute_score`,
the one scoring implementation), and check/write (the CLI: `--dry-run`
measures, `--check` compares the on-disk hub/shards against what
frontmatter would produce, `--write` atomically regenerates all of them).

Two carve-outs `--check` never treats as a failure, because both change on
their own without any item file changing:

  - The hub's `Generated: YYYY-MM-DD` line changes every day by
    construction and is excluded from every comparison below it.
  - A row whose ONLY differing cell is Score is classified `stale-score`,
    not ordinary drift, and never fails `--check`'s exit code -- two of the
    eight scoring factors are time- and graph-dependent (item age, and
    blocks-count filtered to currently-open targets), so a score drifts
    daily and whenever a *different* item's status changes, without this
    item's own frontmatter changing at all.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import namedtuple
from datetime import datetime
from pathlib import Path

# Windows consoles default stdout to cp1252, which cannot encode the em
# dashes and curly quotes several item titles carry.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import get_scoring_weights, load_config
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from markdown_parser import is_section_boundary, split_row_cells
from read_limits import READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN, estimate_tokens
from reconcile_common import format_drift_report, read_text_preserving_newlines
from score_backlog import _strip_inline_comment, compute_score, count_archived_by_abbrev

# --------------------------------------------------------------------------
# Column layout
#
# Position is asserted here by named constant, not by a comment next to a
# list literal -- several existing scripts read this table by cell position,
# and a shift that only a comment recorded would not fail until something
# downstream silently read the wrong column.
# --------------------------------------------------------------------------

COL_ID = 0
COL_TITLE = 1
COL_PRIORITY = 2
COL_STATUS = 3
COL_DOMAIN = 4
COL_CREATED = 5
COL_BLOCKS = 6
COL_SCORE = 7
COL_FILE = 8
COLUMN_COUNT = 9

HEADER_CELLS = [
    "ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File",
]

# The header text is the readable spec; these assertions are the enforced
# one. If a future edit moves a column, this fails at import time instead of
# at whatever downstream script reads the shifted cell.
assert len(HEADER_CELLS) == COLUMN_COUNT
assert HEADER_CELLS[COL_ID] == "ID"
assert HEADER_CELLS[COL_TITLE] == "Title"
assert HEADER_CELLS[COL_PRIORITY] == "Priority"
assert HEADER_CELLS[COL_STATUS] == "Status"
assert HEADER_CELLS[COL_DOMAIN] == "Domain"
assert HEADER_CELLS[COL_CREATED] == "Created"
assert HEADER_CELLS[COL_BLOCKS] == "Blocks"
assert HEADER_CELLS[COL_SCORE] == "Score"
assert HEADER_CELLS[COL_FILE] == "File"

# Existing scripts don't all read these columns the same way today. Some
# key off position relative to the row's own length (len(cells)-1 for File,
# len(cells)-2 for Score) -- the two asserts below protect exactly that
# contract, so a column appended after File fails here instead of silently
# shifting what those readers see. Others (parse_backlog.py, score_backlog.py)
# read an ABSOLUTE index into the legacy 6/7-column layout and locate the
# table by finding a "## Backlog Items" heading this module's generated
# files do not emit -- those readers are not compatible with this 9-column
# layout at all, by absolute position or by table-location, and no
# assertion here can make them so. Reconciling them to this layout is a
# separate rework, not a consequence of anything asserted below.
assert COL_STATUS == 3               # a reader keys off status at a literal index 3
assert COL_SCORE == COLUMN_COUNT - 2  # a writer keys off score at len(cells)-2
assert COL_FILE == COLUMN_COUNT - 1   # a reader keys off file at len(cells)-1

# The seven keys the item-file template requires. "blocks" may legitimately
# be an empty list; every other key must resolve to a non-empty scalar.
REQUIRED_KEYS = ("id", "title", "priority", "status", "abbrev", "created", "blocks")

TITLE_MAX_LEN = 120

_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")

# The default/legacy filename stem, kept as a live module constant because
# it is also the fallback naming basis below when no project config is in
# play (this module's own pure-function tests build fixtures against it
# directly). The REAL naming a live project uses is derived from its
# configured `index_files.backlog` path via `_index_naming` below (Finding
# F5) -- never this hardcoded constant -- so a project whose index is not
# named "00-Index-Backlog.md" gets a hub/shard/overflow-leaf naming the
# rest of the toolchain (`config["_index_path"]`, `config["_archive_dir"]`)
# actually agrees with, instead of one no other script would recognize.
INDEX_FILE_STEM = "Index-Backlog"

# The hub's pointer to the changelog (Execution Step 4, user decision (a)):
# a single byte-identical line on every run, carrying no date, so `--check`
# compares it like any other generated line instead of it vanishing
# silently the first time `--write` regenerates the hub. Its filename is
# derived from `naming` by `_changelog_filename`, defined next to
# `_hub_filename`/`_shard_filename` below (closeout review Finding 1) --
# never a hardcoded constant, so a custom `index_files.backlog` gets a
# changelog name `migrate_backlog_index.artifact_paths` agrees with,
# instead of always "00-Changelog-Backlog.md" regardless of project naming.

IndexNaming = namedtuple("IndexNaming", ["hub_name", "hub_stem", "suffix", "archive_stem"])

# The fallback naming: what every namer below produces when no project
# config is available (a bare pure-function call, as this module's own
# tests make). Equivalent to what `_index_naming` derives from an
# `index_path` of `00-Index-Backlog.md`.
_DEFAULT_INDEX_NAMING = IndexNaming(
    hub_name=f"00-{INDEX_FILE_STEM}.md",
    hub_stem=f"00-{INDEX_FILE_STEM}",
    suffix=".md",
    archive_stem=INDEX_FILE_STEM,
)


def _index_naming(index_path: Path) -> IndexNaming:
    """Derive every generated filename shape from the project's configured
    index path -- the hub name, its overflow-leaf stem, and the Archive
    shard stem all come from this ONE source (Finding F5), so a custom
    `index_files.backlog` in config.yaml (e.g. `Backlog-Index.md`) is
    honored instead of a hardcoded `00-Index-Backlog.md` no other script in
    the project would recognize. `archive_stem` strips a leading `00-`
    (the hub's own "generated artifact" marker): an Archive shard has never
    carried that prefix, and stripping it structurally rather than via a
    second hardcoded constant is what keeps the namer and the scanner's
    skip-filter (`is_generated_index_file`, built from this same tuple)
    unable to drift apart.
    """
    hub_name = index_path.name
    hub_stem = index_path.stem
    suffix = index_path.suffix
    archive_stem = hub_stem.removeprefix("00-")
    return IndexNaming(hub_name=hub_name, hub_stem=hub_stem, suffix=suffix, archive_stem=archive_stem)


def _generated_index_file_pattern(naming: IndexNaming) -> re.Pattern:
    """One regex built from the SAME `naming` the hub/shard namers below
    use, so the scanner's skip-filter and the namers cannot drift apart by
    construction (the property the old hardcoded-constant version claimed
    but did not fully hold -- Finding F2: the id-range group here is
    `\\d{3,}`, matching every digit width `_hub_filename`/`_shard_filename`'s
    `:03d` formatting can ever produce, not the too-narrow `\\d{3}` a
    4+-digit id such as 1000 fell outside of).
    """
    range_pattern = r"-\d{3,}-\d{3,}"
    return re.compile(
        r"^(?:"
        + re.escape(naming.hub_name)
        + r"|" + re.escape(naming.hub_stem) + range_pattern + re.escape(naming.suffix)
        + r"|" + re.escape(naming.archive_stem) + range_pattern + re.escape(naming.suffix)
        + r")$"
    )


def is_generated_index_file(name: str, naming: IndexNaming | None = None) -> bool:
    """True for any filename this module itself emits under `naming` (the
    hub, a hub overflow leaf, or an Archive shard). None of these is ever
    an item file. `naming` defaults to the fallback stem
    (`_DEFAULT_INDEX_NAMING`) when the caller has no project config in
    play -- a real CLI run always passes the config-derived naming instead.
    """
    return bool(_generated_index_file_pattern(naming or _DEFAULT_INDEX_NAMING).match(name))


class GeneratorError(Exception):
    """A condition that must abort generation before any row renders."""


# --------------------------------------------------------------------------
# Frontmatter extraction
#
# `frontmatter_parser` is the one shared split/parse primitive every script
# in this tree already goes through -- reused here rather than re-derived.
# Deliberately NOT layered on top of a YAML-typed parse: PyYAML's implicit
# resolvers turn an unquoted all-octal-digit id like "061" into the int 49,
# and turn an unquoted `created:` value into a `datetime.date`. Both are
# silent value corruption for a renderer whose job is to reproduce the
# author's literal text, so the fields that must stay exact are read at the
# text level via `parse_frontmatter_map` instead of through a YAML loader.
# --------------------------------------------------------------------------


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _normalize_id_text(raw: str) -> str:
    """Zero-pad a frontmatter id/blocks-entry to the 3-digit stored form."""
    digits = _strip_quotes(raw.strip())
    if not digits.isdigit():
        raise GeneratorError(f"non-numeric id value {raw!r}")
    return digits.zfill(3)


def _parse_list_field(raw: str) -> list:
    """Parse a `blocks:`-shaped frontmatter value into a list of id strings.

    Handles both the flow form written on the key's own line
    (``blocks: [007, 009]``) and the block form spread over indented `- `
    lines, since `parse_frontmatter_map` hands back either shape as the
    key's raw, un-typed value text.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [_normalize_id_text(part) for part in inner.split(",") if part.strip()]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_normalize_id_text(match.group(1)))
    return items


def _read_frontmatter_map(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    parts = split_frontmatter_block(content)
    if parts is None:
        raise GeneratorError(f"{path}: no well-formed frontmatter block")
    raw_text, _body = parts
    fm_map = parse_frontmatter_map(raw_text)
    if fm_map is None:
        raise GeneratorError(f"{path}: frontmatter block could not be parsed")
    return fm_map


def _extract_fields(path: Path, raw_map: dict) -> dict:
    """Turn a raw {key: value-text} map into the seven typed fields.

    Raises when a required key is absent, or present but empty -- the
    generator reports a missing key and stops; it never fills one in.
    """
    missing = [key for key in REQUIRED_KEYS if key not in raw_map]
    if missing:
        raise GeneratorError(
            f"{path}: missing required frontmatter key(s): {', '.join(missing)}"
        )

    fields: dict = {}
    for key in ("title", "priority", "status", "abbrev", "created"):
        raw_value = raw_map[key]
        if key == "created":
            # A trailing YAML inline comment on `created:` survives past
            # `parse_frontmatter_map`'s text-level read (score_backlog.py's
            # `_strip_inline_comment` docstring) and would otherwise ship as
            # part of the rendered Created cell.
            raw_value = _strip_inline_comment(raw_value)
        value = _strip_quotes(raw_value.strip())
        if not value:
            raise GeneratorError(f"{path}: frontmatter key '{key}' is empty")
        fields[key] = value

    # `id` and `blocks` get the same inline-comment strip as `created`,
    # ported from score_backlog._strip_inline_comment: `blocks: [007, 009]
    # # two` would otherwise drop the trailing edge, and the generator's
    # edge set must equal the scorer's on every item.
    fields["id"] = _normalize_id_text(_strip_inline_comment(raw_map["id"]))
    fields["blocks"] = _parse_list_field(_strip_inline_comment(raw_map["blocks"]))
    fields["_path"] = path
    return fields


def _scan_one_file(path: Path) -> dict:
    raw_map = _read_frontmatter_map(path)
    return _extract_fields(path, raw_map)


def _iter_item_files(backlog_dir: Path, archive_dir: Path, index_path: Path):
    """Yield every item file under the active and archived backlog dirs.

    Both directories are scanned: an archived item still needs an index
    row, and scoping the scan to the active directory alone would silently
    drop every archived item from the index. A "00-"-prefixed file is a
    generated artifact of the backlog tooling itself (the index, its
    changelog), never an item, and is skipped by that convention.

    An Archive shard this module itself generates
    (`Index-Backlog-NNN-NNN.md`) carries no "00-" prefix and lands inside
    `archive_dir`, which this loop globs with `*.md` -- so it is caught
    instead by `is_generated_index_file`, the same predicate the hub/shard
    namers derive their filenames from. Without this, the scan immediately
    after a `--write` would re-ingest every shard as though it were an item
    file lacking frontmatter, and abort the whole generation -- `--check`
    could never return clean after a `--write`.
    """
    naming = _index_naming(index_path)
    seen: set = set()
    for directory in (backlog_dir, archive_dir):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name.startswith("00-") or is_generated_index_file(path.name, naming):
                continue
            resolved = path.resolve()
            if resolved == index_path.resolve() or resolved in seen:
                continue
            seen.add(resolved)
            yield path


def scan_backlog(backlog_dir: Path, archive_dir: Path, index_path: Path) -> list:
    """Scan every item file and return its extracted fields, id-sorted.

    Every file is checked before any error is raised, so one run reports
    every offending item rather than only the first one found. A repeated
    id across two DIFFERENT item files (a sub-item mistakenly reusing its
    parent's id, or a half-moved archive copy left in both `Backlog/` and
    `Backlog/Archive/`) is refused HERE, at scan time, naming both paths and
    the id -- never allowed to reach rendering. Left unrefused, the
    duplicate would render two rows for one id: `--write` would ship both
    silently, and `--check`'s later duplicate-row quarantine (Finding F2)
    would remove the id from its own fresh-render comparison entirely,
    surfacing as a `KeyError` rather than a reported anomaly (Finding F1 of
    the pre-commit review). Refusing before any row renders is the same
    "never fabricate, never half-ship" discipline every other GeneratorError
    in this scanner already applies to a missing key or a dangling `blocks:`
    entry.
    """
    errors = []
    items = []
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        try:
            items.append(_scan_one_file(path))
        except GeneratorError as exc:
            errors.append(str(exc))

    paths_by_id: dict = {}
    for item in items:
        paths_by_id.setdefault(item["id"], []).append(item["_path"])
    for item_id, paths in paths_by_id.items():
        if len(paths) > 1:
            joined = ", ".join(str(p) for p in paths)
            errors.append(
                f"duplicate id {item_id}: claimed by {len(paths)} item files: {joined}"
            )

    if errors:
        raise GeneratorError("\n".join(errors))
    items.sort(key=lambda item: int(item["id"]))
    return items


# --------------------------------------------------------------------------
# Blocks-edge resolution
# --------------------------------------------------------------------------


def build_blocks_index(items: list) -> dict:
    return {item["id"]: set(item["blocks"]) for item in items}


def validate_blocks_resolve(items: list, known_ids: set) -> None:
    """Abort naming the file and the id when a `blocks:` entry is dangling.

    A bare id that names no scanned item is a data error, never a silent
    drop -- the edge it describes would otherwise disappear from the index
    with no trace that it was ever there.
    """
    errors = []
    for item in items:
        for target in item["blocks"]:
            if target not in known_ids:
                errors.append(
                    f"{item['_path']}: blocks: entry '{target}' names no known item"
                )
    if errors:
        raise GeneratorError("\n".join(errors))


def detect_reciprocal_edges(blocks_index: dict) -> list:
    """Return each unordered pair of ids that block one another.

    A reciprocal edge -- A blocks B and B blocks A -- makes two items block
    each other forever the moment either reopens, so it is reported as an
    anomaly rather than silently accepted, reversed, or dropped. Deciding
    which side of such a pair is the data error is a data-correction call
    outside this generator's scope; this function only detects and names
    the pair.
    """
    seen: set = set()
    edges = []
    for a, targets in blocks_index.items():
        for b in targets:
            if a in blocks_index.get(b, set()):
                pair = frozenset((a, b))
                if pair not in seen:
                    seen.add(pair)
                    edges.append(tuple(sorted((a, b))))
    return edges


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _escape_cell(text: str) -> str:
    """Escape an unescaped pipe so the cell survives table round-tripping.

    A cell containing a literal `|` -- including one inside a code span,
    e.g. a shell pipeline quoted in a title -- must come back out through
    `split_row_raw` as the same number of cells it went in as. Only the
    presence of a raw pipe triggers the substitution; a pipe-free cell
    returns untouched.
    """
    if "|" not in text:
        return text
    return _UNESCAPED_PIPE_RE.sub(r"\\|", text)


def truncate_title(title: str, max_len: int = TITLE_MAX_LEN):
    """Truncate `title` to `max_len` chars at a word boundary.

    Returns (rendered_title, was_truncated). Truncation happens on the raw
    title, before escaping, so a cut can never land inside an escape
    sequence.
    """
    if len(title) <= max_len:
        return title, False
    cut = title.rfind(" ", 0, max_len + 1)
    if cut <= 0:
        cut = max_len
    return title[:cut].rstrip(), True


def _relative_file_path(path: Path, backlog_dir: Path) -> str:
    try:
        rel = path.relative_to(backlog_dir)
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


def _render_blocks_cell(blocks: list) -> str:
    if not blocks:
        return ""
    return "[" + ", ".join(blocks) + "]"


def _render_file_cell(item_id: str, path: Path, backlog_dir: Path) -> str:
    return f"[{item_id}]({_relative_file_path(path, backlog_dir)})"


def render_row(item: dict, backlog_dir: Path):
    """Render one item's fields into a 9-cell table row.

    Returns (row_text, title_was_truncated). The Score cell reads
    `item["score"]`, which `compute_scores_for_items` must have populated
    before this is called -- a numeric string for an open item, `"-"` for a
    closed one (the score_backlog.py convention this mirrors: a closed item
    is not part of active priority triage). A missing key here means the
    caller forgot that step, so it is read with no default -- a KeyError is
    the correct failure, not a silently blank cell.
    """
    rendered_title, was_truncated = truncate_title(item["title"])
    cells = [""] * COLUMN_COUNT
    cells[COL_ID] = item["id"]
    cells[COL_TITLE] = _escape_cell(rendered_title)
    cells[COL_PRIORITY] = item["priority"]
    cells[COL_STATUS] = item["status"]
    cells[COL_DOMAIN] = item["abbrev"]
    cells[COL_CREATED] = item["created"]
    cells[COL_BLOCKS] = _render_blocks_cell(item["blocks"])
    cells[COL_SCORE] = item["score"]
    cells[COL_FILE] = _render_file_cell(item["id"], item["_path"], backlog_dir)
    assert len(cells) == COLUMN_COUNT
    row = "|" + "|".join(f" {cell} " for cell in cells) + "|"
    return row, was_truncated


def render_header() -> str:
    return "|" + "|".join(f" {cell} " for cell in HEADER_CELLS) + "|"


def render_separator() -> str:
    return "|" + "|".join(["---"] * COLUMN_COUNT) + "|"


# --------------------------------------------------------------------------
# Hub/shard partition and budget enforcement
#
# Sharding is the generator's whole size guarantee, not a readability setting:
# every file this module produces MUST measure under its own per-file budget
# before it is ever handed to a writer -- `HUB_TOKEN_BUDGET` for the hub and
# its overflow leaves, `READ_TOKEN_WARN` for an Archive shard. The
# measurement basis is `read_limits`'s own byte-ratio instrument -- the same
# one the Read-tool gate itself uses -- never TOKENS_PER_LINE, which
# under-estimates this dense-table corpus by roughly 28x -- a per-line band
# derived from prose, not from pipe-and-code-heavy single-line table rows.
# The bytes it is fed are the CRLF worst case (`_shipped_bytes`): a Windows
# checkout with `core.autocrlf=true` adds one byte per line to what the Read
# tool loads, so a budget that must hold on every checkout counts that byte
# whatever the line endings of the checkout running the generator.
# --------------------------------------------------------------------------

# Statuses this corpus's config.yaml declares CLOSED (`statuses:` list also
# carries NOT_STARTED, PLANNING, IN_PROGRESS, BLOCKED -- all open). Hub
# membership is decided by this field at run time, never by which directory
# a file happens to sit in and never by a hardcoded open-item count.
CLOSED_STATUSES = frozenset({"COMPLETE", "CLOSED"})

# The hub is the file most readers open first, and its target is a margin
# under the Read-tool page cap, not merely "under the warn threshold": every
# hub-family file (the hub and each overflow leaf) keeps at least
# HUB_HEADROOM_FACTOR x headroom under READ_PAGE_CAP_TOKENS. The budget is
# derived from that target rather than chosen beside it, so the two cannot
# drift apart. Archive shards keep `READ_TOKEN_WARN`, which is shared with
# other consumers and is deliberately not lowered here.
HUB_HEADROOM_FACTOR = 2
HUB_TOKEN_BUDGET = READ_PAGE_CAP_TOKENS // HUB_HEADROOM_FACTOR

# The instrument this measures against, by name, for every report this
# module emits: `read_limits.estimate_tokens` with no model/content override
# resolves to `DEFAULT_BYTES_PER_TOKEN` (2.6 bytes/token) -- the same
# gate-conservative default the Read-tool page-cap gate itself computes
# against, not a per-line band -- applied to the CRLF worst-case byte count.
MEASUREMENT_BASIS = (
    "read_limits.estimate_tokens(bytes) at its default ratio "
    "(model=None -> DEFAULT_BYTES_PER_TOKEN=2.6 bytes/token), where bytes is "
    "the CRLF worst case: UTF-8 bytes plus one per line"
)


def shard_for(item_id) -> int:
    """Return the ID-century shard number: (id - 1) // 100.

    A pure function of the id alone -- no lookup table, no registry has to
    stay in sync with which century a given id belongs to.
    """
    return (int(item_id) - 1) // 100


def is_open_item(item: dict) -> bool:
    """True unless `item["status"]` is one of the corpus's closed states."""
    return item["status"] not in CLOSED_STATUSES


def partition_items(items: list) -> tuple:
    """Split id-sorted `items` into the open (hub) list and closed items
    grouped by `shard_for` century.

    An item moves from hub to shard the moment its status closes; no item
    appears in both, and neither group is derived from which directory the
    item's file happens to live in.
    """
    open_items = []
    by_century: dict = {}
    for item in items:
        if is_open_item(item):
            open_items.append(item)
        else:
            by_century.setdefault(shard_for(item["id"]), []).append(item)
    return open_items, by_century


def compute_scores_for_items(items: list, archive_dir: Path, config: dict) -> None:
    """Fill each item's `score` field in place, via the one scoring
    implementation (`score_backlog.compute_score`) -- never a second copy.

    Feeds it a thin row/frontmatter-shaped adapter built from this module's
    own text-level scanned fields, never `score_backlog.read_item_frontmatter`'s
    YAML-typed load (which mis-types an unquoted all-octal-digit id like
    `061` to the int 49 -- see the scanner section above). `file_count` is
    always 1: this schema renders exactly one File link per row, unlike the
    legacy multi-file-per-row Files column `compute_score` was written
    against. `feature` is fed the item's raw, untruncated title -- the
    Bug/Fix keyword factor is a data question, not a rendering one, and
    truncation is display-only.

    A closed item's score is rendered `"-"`, matching score_backlog.py's own
    convention (`_score_row_processor`'s caller never computes one for a
    CLOSED/COMPLETE row): a closed item is not part of active priority
    triage, and computing a perpetually age-drifting number nobody reads
    would manufacture drift with no purpose.
    """
    weights = get_scoring_weights(config)
    archive_counts = count_archived_by_abbrev(archive_dir)
    open_item_ids = {item["id"] for item in items if is_open_item(item)}
    for item in items:
        if not is_open_item(item):
            item["score"] = "-"
            continue
        row_shaped = {
            "priority": item["priority"],
            "feature": item["title"],
            "status": item["status"],
            "file_count": 1,
            "abbrev": item["abbrev"],
        }
        frontmatter_shaped = {
            "blocks": item["blocks"],
            "created": item["created"],
        }
        item["score"] = str(
            compute_score(row_shaped, frontmatter_shaped, archive_counts, weights, open_item_ids).total
        )


def render_table_body(items: list, backlog_dir: Path) -> tuple:
    """Render one table (header + separator + one row per item).

    Returns (body_text, truncated_ids). Reuses `render_header`/`render_row`
    exactly, so a sharded/budgeted table renders byte-identical rows to an
    unsharded run.
    """
    lines = [render_header(), render_separator()]
    truncated_ids = []
    for item in items:
        row, was_truncated = render_row(item, backlog_dir)
        lines.append(row)
        if was_truncated:
            truncated_ids.append(item["id"])
    return "\n".join(lines) + "\n", truncated_ids


def _shipped_bytes(text: str) -> int:
    """The byte count `text` occupies on a CRLF checkout: its UTF-8 bytes
    plus one per `\\n`, because a Windows checkout with `core.autocrlf=true`
    adds one byte per line to what the Read tool actually loads.

    Every render in this module is `\\n`-only internally, so this is exact
    for a CRLF checkout and over-counts an LF checkout by one byte per line
    -- the safe direction. It is deliberately independent of the line
    endings of the checkout running the generator: a `--check` on the other
    convention must compute the same split boundaries, or it would report
    drift that no item caused. Additive over concatenation, like the plain
    UTF-8 length it extends.
    """
    return len(text.encode("utf-8")) + text.count("\n")


def _measure(body: str) -> tuple:
    """Return (num_bytes, tokens) for `body` via MEASUREMENT_BASIS."""
    num_bytes = _shipped_bytes(body)
    tokens = estimate_tokens(num_bytes)
    return num_bytes, tokens


def _id_range(items: list) -> tuple:
    ids = [int(item["id"]) for item in items]
    return min(ids), max(ids)


def split_items_to_budget(
    items: list, backlog_dir: Path, wrapper_tokens: int = 0, budget: int = READ_TOKEN_WARN
) -> list:
    """Recursively split `items` until every rendered table, PLUS the
    wrapper text its caller will assemble around it, is under `budget`
    tokens -- the enforced per-file budget. It defaults to READ_TOKEN_WARN
    (deliberately the warn level, not the 25,000 hard cap, so a produced
    file never even warns); `build_hub_files` passes the tighter
    HUB_TOKEN_BUDGET for the hub family.

    `wrapper_tokens` is a conservative reserve for the bytes/tokens the
    caller adds around this table body before shipping it: leaf 0's
    `Generated:` line plus the full `## Shards` directory (`build_hub_files`),
    a continuation leaf's backlink line, or a shard's backlink line
    (`build_shard_files`). The split decision below measures `body tokens +
    wrapper_tokens` against budget, not the bare body -- matching what will
    actually be assembled and shipped. Defaults to 0 for a caller with no
    wrapper (this module's own tests call this directly as a pure function
    over a bare table). Because `estimate_tokens` rounds up and
    `_shipped_bytes` adds exactly across concatenation (both the UTF-8
    length and the per-line CRLF byte are additive, so the CRLF worst-case
    basis leaves this proof unchanged), `estimate_tokens(body_bytes) +
    estimate_tokens(wrapper_bytes) >= estimate_tokens(body_bytes +
    wrapper_bytes)` always -- so accepting a leaf here on the token SUM is
    never less conservative than measuring the assembled bytes directly,
    which is exactly what makes the post-assembly check in each caller an
    assertion rather than a live branch (see their docstrings).

    Returns a list of leaves, each `(subset, body, num_bytes, tokens,
    truncated_ids)`, all under budget -- `tokens` is the BARE body's count,
    not body+wrapper, matching every existing caller (including this
    module's own tests, which assert `tokens < budget` on the bare body).
    This is the enforcement mechanism: a file that would exceed budget is
    split and re-measured, not shipped with a violation reported.
    Splitting a leaf that is already a single row raises GeneratorError
    naming that row -- the pathological case no split can fix (body alone,
    plus the wrapper reserve, still at or over budget), refused rather than
    shipped over budget.
    """
    body, truncated = render_table_body(items, backlog_dir)
    num_bytes, tokens = _measure(body)
    if tokens + wrapper_tokens < budget:
        return [(items, body, num_bytes, tokens, truncated)]
    if len(items) == 1:
        item = items[0]
        raise GeneratorError(
            f"{item['_path']}: item {item['id']} alone renders to {tokens} "
            f"tokens ({num_bytes} bytes; basis: {MEASUREMENT_BASIS}) plus a "
            f"{wrapper_tokens}-token wrapper reserve -- exceeds the "
            f"{budget}-token budget and cannot be reduced by "
            f"sharding further"
        )
    mid = len(items) // 2
    return (
        split_items_to_budget(items[:mid], backlog_dir, wrapper_tokens, budget)
        + split_items_to_budget(items[mid:], backlog_dir, wrapper_tokens, budget)
    )


def _hub_filename(naming: IndexNaming, min_id: int, max_id: int, index: int) -> str:
    """Leaf 0 is the canonical hub filename; every later leaf is an
    overflow continuation named by its own id range -- the hub is bounded
    by open-item count, which is not bounded by construction, so it must be
    able to shard too.
    """
    if index == 0:
        return naming.hub_name
    return f"{naming.hub_stem}-{min_id:03d}-{max_id:03d}{naming.suffix}"


def _shard_filename(naming: IndexNaming, min_id: int, max_id: int) -> str:
    return f"{naming.archive_stem}-{min_id:03d}-{max_id:03d}{naming.suffix}"


_CHANGELOG_HUB_RE = re.compile(r"^00-Index-(.+)$")


def _changelog_filename(naming: IndexNaming) -> str:
    """The one namer for the changelog file: what the hub's footer points
    at, and what `migrate_backlog_index.artifact_paths` creates -- both
    scripts import this function rather than deriving the name twice, so
    they cannot disagree on it (closeout review Finding 1).

    When the hub follows the `00-Index-{X}{suffix}` shape, the changelog is
    `00-Changelog-{X}{suffix}`. For the default/live project's own
    `00-Index-Backlog.md`, X = "Backlog", giving the existing
    `00-Changelog-Backlog.md` this function must never rename. A hub that
    does not follow that shape (a custom `project.index_files.backlog`,
    e.g. `Backlog-Index.md`) falls back to `00-{hub_stem}-Changelog{suffix}`.
    """
    match = _CHANGELOG_HUB_RE.match(naming.hub_stem)
    if match:
        return f"00-Changelog-{match.group(1)}{naming.suffix}"
    return f"00-{naming.hub_stem}-Changelog{naming.suffix}"


def _footer_line(naming: IndexNaming) -> str:
    return f"[Changelog]({_changelog_filename(naming)})\n"


def _relative_link(from_dir: Path, to_path: Path) -> str:
    rel = os.path.relpath(to_path, start=from_dir)
    return str(rel).replace("\\", "/")


def render_shards_section(shard_files: list) -> str:
    """Render the hub's '## Shards' directory: one row per Archive shard
    file, each linking to it and naming its id range.

    The caller places this AFTER the Backlog Items table (Execution Step
    7): `## ` starts a new section, and `markdown_parser.is_section_boundary`
    ends any table walk on sight of one, so this text must never sit above
    the table or every existing hub reader breaks.
    """
    lines = ["## Shards", "", "| Range | File |", "|---|---|"]
    for entry in shard_files:
        label = f"{entry['min_id']:03d}-{entry['max_id']:03d}"
        lines.append(f"| {label} | [{entry['path']}]({entry['path']}) |")
    return "\n".join(lines) + "\n"


def _budget_fields(num_bytes: int, tokens: int, budget: int) -> dict:
    """The per-file measurement fields every generated-file entry carries:
    the CRLF worst-case byte count, its token estimate, the basis, the
    budget this file was split against, the headroom under that budget,
    and the headline ratio -- how many times over the Read-tool page cap
    covers this file (two decimals). `tokens` is never 0 here: every
    generated file carries at least a wrapper line.
    """
    return {
        "bytes": num_bytes,
        "tokens": tokens,
        "basis": MEASUREMENT_BASIS,
        "budget": budget,
        "headroom": budget - tokens,
        "page_cap_ratio": round(READ_PAGE_CAP_TOKENS / tokens, 2),
    }


def build_shard_files(
    by_century: dict,
    backlog_dir: Path,
    archive_dir: Path,
    naming: IndexNaming,
    budget: int = READ_TOKEN_WARN,
) -> list:
    """Render every closed-item century group as one or more shard files
    under `Archive/`, splitting further only if a single century's table
    itself exceeds `budget` (bounded at 100 rows by construction, so this is
    rare, but not assumed impossible).

    Each shard file backlinks to the hub (bidirectional links, Execution
    Step 6). The backlink line is the wrapper `split_items_to_budget` is
    given a reserve for (Finding F1): without it, the split decision
    measured the bare table body while this function measured body +
    backlink, so a body just under budget could still push the assembled
    file over it, in every mode, with no split ever offered. `naming`
    (Finding F5) names the hub itself and every shard's own filename stem
    from the project's actual configured index path, never a hardcoded
    constant. Returns one dict per file: path (relative to backlog_dir,
    "Archive/..."), content, rows, bytes, tokens, basis, budget, headroom,
    page_cap_ratio, split, min_id, max_id, truncated_ids.
    """
    files = []
    hub_path = backlog_dir / naming.hub_name
    backlink_target = _relative_link(archive_dir, hub_path)
    backlink_line = f"[Back to Backlog Index]({backlink_target})\n\n"
    wrapper_tokens = estimate_tokens(_shipped_bytes(backlink_line))
    for century in sorted(by_century):
        items = by_century[century]
        leaves = split_items_to_budget(items, backlog_dir, wrapper_tokens, budget)
        split = len(leaves) > 1
        for subset, body, _num_bytes, _tokens, truncated in leaves:
            min_id, max_id = _id_range(subset)
            filename = _shard_filename(naming, min_id, max_id)
            # Derived from the SAME `archive_dir` the backlink above already
            # uses, relative to `backlog_dir` -- never a hardcoded "Archive/"
            # prefix (the CR5 residual this closes): with a non-default
            # `archive_dir`, that hardcoded prefix wrote the shard somewhere
            # `_list_disk_generated_files`/`--check` never looks, even though
            # every OTHER path in this module was already config-derived.
            shard_path = _relative_link(backlog_dir, archive_dir / filename)
            content = backlink_line + body
            num_bytes_final = _shipped_bytes(content)
            tokens_final = estimate_tokens(num_bytes_final)
            if tokens_final >= budget:
                # Unreachable on any input the splitter above accepted: the
                # reserve above IS this exact backlink line's token cost, so
                # `split_items_to_budget` already refused (or split further)
                # any body for which body_tokens + wrapper_tokens >= budget
                # -- see its docstring for the ceiling-superadditivity
                # proof. Kept as a defensive assertion, not a live branch:
                # it would only fire if this line's own computation diverged
                # from the reserve computed above.
                raise GeneratorError(
                    f"{shard_path}: adding the backlink line pushed "
                    f"the file to {tokens_final} tokens (basis: "
                    f"{MEASUREMENT_BASIS}), >= the {budget}-token "
                    f"budget despite a {wrapper_tokens}-token reserve at "
                    f"split time -- this should be unreachable; report it "
                    f"as a bug in the reserve calculation, not as an "
                    f"unshardable row"
                )
            files.append({
                "path": shard_path,
                "content": content,
                "rows": len(subset),
                **_budget_fields(num_bytes_final, tokens_final, budget),
                "split": split,
                "min_id": min_id,
                "max_id": max_id,
                "truncated_ids": truncated,
            })
    return files


def _hub_leaf_entries(leaves: list, naming: IndexNaming) -> list:
    """The `## Shards`-directory entries for every hub OVERFLOW leaf
    (index > 0) a split produced -- min_id/max_id/path, the same shape
    `build_shard_files` already produces for an Archive shard, so
    `render_shards_section` needs no special-casing to list both kinds in
    one directory (Finding F4).
    """
    entries = []
    for index, (subset, _body, _num_bytes, _tokens, _truncated) in enumerate(leaves):
        if index == 0 or not subset:
            continue
        min_id, max_id = _id_range(subset)
        entries.append({
            "min_id": min_id,
            "max_id": max_id,
            "path": _hub_filename(naming, min_id, max_id, index),
        })
    return entries


def _generated_line() -> str:
    """Leaf 0's first line. The ISO date is fixed-width, so its byte count
    never depends on which day it renders."""
    today = datetime.now().astimezone().date()
    return f"Generated: {today.isoformat()}\n\n"


def _continuation_wrapper(naming: IndexNaming) -> str:
    """The backlink line every hub overflow leaf opens with."""
    return f"[Back to Backlog Index]({naming.hub_name})\n\n"


def hub_wrapper_tokens(
    shards_section: str, naming: IndexNaming, generated_line: str | None = None
) -> int:
    """The wrapper-token reserve `build_hub_files` gives the splitter: the
    LARGER of leaf 0's wrapper (`Generated:` line + the `## Shards`
    directory + the changelog footer, exactly as leaf 0 is assembled) and
    a continuation leaf's backlink line, measured on the CRLF worst-case
    basis. One definition, so the reserve the splitter is given and the
    wrapper leaf 0 actually ships cannot drift apart.
    """
    if generated_line is None:
        generated_line = _generated_line()
    leaf0_wrapper = generated_line + "\n" + shards_section + "\n" + _footer_line(naming)
    wrapper_bytes = max(
        _shipped_bytes(leaf0_wrapper),
        _shipped_bytes(_continuation_wrapper(naming)),
    )
    return estimate_tokens(wrapper_bytes)


def build_hub_files(
    open_items: list,
    backlog_dir: Path,
    shard_files: list,
    naming: IndexNaming,
    budget: int = HUB_TOKEN_BUDGET,
) -> list:
    """Render the hub as one or more files, splitting by `budget` (the
    hub-family budget, HUB_TOKEN_BUDGET, by default) if the open set alone
    exceeds it -- the open-item count is not bounded by construction.

    Leaf 0 carries the '## Shards' directory (after its table), listing
    BOTH the Archive shards (`shard_files`) AND any hub overflow leaf this
    very split produces (Finding F4) -- without the second half, a
    split-off hub leaf is unreachable from leaf 0, the only file most
    readers ever open, and its rows are silently invisible to anyone who
    never thinks to look for a same-directory sibling file. Any later
    overflow leaf backlinks to leaf 0. Returns entries in the same shape as
    `build_shard_files` (without min_id/max_id, since the hub is one
    logical unit; overflow leaves are still named by id range). `naming`
    (Finding F5) supplies every filename this function produces or links
    to, from the project's actual configured index path.

    The split decision (`split_items_to_budget`) is given a wrapper-token
    reserve (Finding F1, `hub_wrapper_tokens`) sized from the LARGER of
    leaf 0's wrapper (`Generated:` line + the full `## Shards` directory +
    the changelog footer) and a continuation leaf's short backlink line.
    Because the directory also depends on the split's OWN leaf boundaries
    (Finding F4), the directory and the split are iterated to a fixed
    point: the first split runs against the Archive-only directory (a leaf
    cannot list its own overflow siblings before the split that creates
    them exists); each later round rebuilds the directory from the current
    leaves and re-splits against that directory's reserve, until the leaf
    count stops changing.

    Why this converges, and why a stable count is enough: the splitter
    halves at a fixed midpoint, so every possible split lies on one halving
    tree over `open_items`, and a run is fully described by the set of tree
    nodes it splits (leaf count = split nodes + 1). A larger reserve splits
    a superset of the nodes a smaller one split. Each round's leaves refine
    the previous round's. Splitting leaf 0 adds new directory rows.
    Splitting an overflow leaf replaces its one directory row with two or
    more rows over narrower id ranges. The first replacement row keeps the
    old minimum id and the last keeps the old maximum id, and every row
    carries its own framing, so the replacement rows are longer in total
    than the row they replace. The directory therefore never shrinks, and
    neither does the reserve, from round to round. The leaf count is
    therefore non-decreasing and bounded by `len(open_items)`, and two
    rounds with equal counts split the same node set -- identical
    boundaries, so the directory built from the earlier round lists
    exactly the leaves the later round ships. The loop is still bounded
    at `len(open_items) + 1` rounds and raises GeneratorError past that
    bound, and leaf 0's directory is asserted equal to the shipped
    overflow leaves before assembly, so a violated argument refuses
    instead of shipping links to files that do not exist.
    """
    generated_line = _generated_line()
    continuation_wrapper = _continuation_wrapper(naming)
    footer_line = _footer_line(naming)

    def _split(section: str) -> list:
        reserve = hub_wrapper_tokens(section, naming, generated_line)
        return split_items_to_budget(open_items, backlog_dir, reserve, budget)

    leaves = _split(render_shards_section(shard_files))
    max_rounds = len(open_items) + 1
    for _round in range(max_rounds):
        hub_entries = _hub_leaf_entries(leaves, naming)
        shards_section = render_shards_section(shard_files + hub_entries)
        next_leaves = _split(shards_section)
        converged = len(next_leaves) == len(leaves)
        leaves = next_leaves
        if converged:
            break
    else:
        raise GeneratorError(
            f"{naming.hub_name}: the hub directory and its overflow split did "
            f"not reach a stable leaf count within {max_rounds} rounds -- "
            f"report it as a bug in the directory fixed point"
        )
    if hub_entries != _hub_leaf_entries(leaves, naming):
        raise GeneratorError(
            f"{naming.hub_name}: the '## Shards' directory lists overflow "
            f"leaves that differ from the leaves being shipped -- this should "
            f"be unreachable; report it as a bug in the directory fixed point"
        )
    wrapper_tokens = hub_wrapper_tokens(shards_section, naming, generated_line)

    split = len(leaves) > 1
    files = []
    for index, (subset, body, _num_bytes, _tokens, truncated) in enumerate(leaves):
        min_id, max_id = _id_range(subset) if subset else (0, 0)
        filename = _hub_filename(naming, min_id, max_id, index)
        if index == 0:
            # Excluded from every `--check` comparison below (see the module
            # docstring's carve-outs): it changes every day by construction,
            # never because an item changed, so comparing it would report
            # drift on every single run regardless of the corpus.
            # Footer after `## Shards` (Execution Step 4): never between a
            # table heading and its rows, and only on leaf 0 -- the canonical
            # hub, the changelog's one intended pointer. An overflow leaf
            # carries no `## Shards` directory of its own and needs none.
            content = generated_line + body + "\n" + shards_section + "\n" + footer_line
        else:
            content = continuation_wrapper + body
        num_bytes_final = _shipped_bytes(content)
        tokens_final = estimate_tokens(num_bytes_final)
        if tokens_final >= budget:
            # Unreachable on any input the splitter above accepted, for the
            # same ceiling-superadditivity reason `build_shard_files` states
            # at its own mirror of this raise -- kept as a defensive
            # assertion, never a live branch.
            raise GeneratorError(
                f"{filename}: adding the directory/backlink section pushed "
                f"the file to {tokens_final} tokens (basis: "
                f"{MEASUREMENT_BASIS}), >= the {budget}-token "
                f"budget despite a {wrapper_tokens}-token reserve at split "
                f"time -- this should be unreachable; report it as a bug "
                f"in the reserve calculation, not as an unshardable row"
            )
        files.append({
            "path": filename,
            "content": content,
            "rows": len(subset),
            **_budget_fields(num_bytes_final, tokens_final, budget),
            "split": split,
            "truncated_ids": truncated,
        })
    return files


def build_index_files(
    items: list, backlog_dir: Path, archive_dir: Path, naming: IndexNaming | None = None
) -> dict:
    """Partition, shard, and budget-enforce the full backlog into a hub +
    Archive shard file set, entirely in memory.

    `naming` (Finding F5) is the project's real config-derived naming; it
    defaults to the fallback stem (`_DEFAULT_INDEX_NAMING`) for a bare
    pure-function call with no project config in play (this module's own
    tests call it this way).

    Returns {"files": [...], "truncated_ids": [...]}. Every file entry
    carries the (relative_path, content) pair a later atomic-write stage
    (this task does not write anything to disk) needs, plus the per-file
    measurement report: rows, bytes, tokens, basis, budget, headroom,
    page_cap_ratio, split. Each family is split against its own budget,
    passed explicitly here: READ_TOKEN_WARN for Archive shards and
    HUB_TOKEN_BUDGET for the hub and its overflow leaves.
    """
    naming = naming or _DEFAULT_INDEX_NAMING
    open_items, by_century = partition_items(items)
    shard_files = build_shard_files(
        by_century, backlog_dir, archive_dir, naming, budget=READ_TOKEN_WARN
    )
    hub_files = build_hub_files(
        open_items, backlog_dir, shard_files, naming, budget=HUB_TOKEN_BUDGET
    )

    all_files = hub_files + shard_files
    truncated_ids = []
    for entry in all_files:
        truncated_ids.extend(entry.get("truncated_ids", []))

    return {"files": all_files, "truncated_ids": truncated_ids}


# --------------------------------------------------------------------------
# Exit-code mapping -- defined once, routed through from every mode
# --------------------------------------------------------------------------


class Disposition:
    """The one exit-code mapping every mode routes through.

    `REFUSED` (2) covers anything the generator cannot render into a valid
    index at all -- a `GeneratorError` from scanning (missing required key),
    from `blocks:` resolution (a dangling id), or from budget enforcement (a
    single row that cannot fit) -- in EVERY mode, `--check`/`--dry-run`
    included, because there is nothing valid to compare or measure. The
    reciprocal `blocks:` edge is the one pinned exception: it is not a
    `GeneratorError` (detection always succeeds and reports it), so a report
    mode still reaches measurement and exits `DRIFT_OR_ANOMALY` (1) naming
    it; only `--write` treats it as `REFUSED` (2) and writes nothing.
    Ordinary drift or a row/file anomaly found by `--check` is 1.
    `stale-score` alone never fails the exit code -- see the module
    docstring's carve-outs.
    """

    CLEAN = 0
    DRIFT_OR_ANOMALY = 1
    REFUSED = 2


def exit_code_for(*, write_mode: bool, reciprocal_edge: bool, drift_or_anomaly: bool) -> int:
    """Apply the `Disposition` mapping. `refused` (a `GeneratorError`) is
    handled by its own `except` block at each call site, which returns
    `Disposition.REFUSED` directly without reaching this function -- there
    is nothing left to measure once one has been raised.
    """
    if reciprocal_edge:
        return Disposition.REFUSED if write_mode else Disposition.DRIFT_OR_ANOMALY
    if drift_or_anomaly:
        return Disposition.DRIFT_OR_ANOMALY
    return Disposition.CLEAN


# --------------------------------------------------------------------------
# Drift detection -- `--check` compares the on-disk hub/shards against what
# item frontmatter would produce right now.
# --------------------------------------------------------------------------


def _read_disk_table(content: str) -> tuple:
    """Parse one generated file's item rows into `{id: cell_list}`.

    Reuses `markdown_parser.split_row_cells`, the same canonical row-cell
    splitter `score_backlog.py` uses, rather than re-deriving pipe-split
    logic -- upstream's own guard requirement is a TWO-part parity: every
    row's cell count MUST equal the header's (a malformed row, caught
    below), AND parsed-row count MUST equal table-row count. The second
    half is what a same-id duplicate row violates: a naive `{id: cells}`
    dict write silently collapses two physical rows into one entry, so
    `rows_by_id` alone can never expose that collapse -- this function
    counts every table row line it walks (`table_row_count`, valid or
    malformed) and tracks first-seen ids explicitly, so a repeated id is
    caught regardless of which copy is clean and which is corrupted, and
    regardless of which one physically comes last. Parsing stops at the
    first blank line or a `## `-prefixed heading, so neither the
    `Generated:` line above the table nor the `## Shards` directory below
    it is ever mistaken for an item row.

    Returns `(rows_by_id, anomalies, duplicate_ids)`. `rows_by_id` maps
    item id -> its COLUMN_COUNT-length cell list, for every id that
    appeared EXACTLY once; a repeated id is excluded from `rows_by_id`
    entirely -- never last-wins, never silently healed -- and named instead
    in `anomalies` and returned in `duplicate_ids` (a set), so a caller
    comparing against known items can recognize "this id's disk row is
    quarantined by a duplicate anomaly" rather than misreading its absence
    from `rows_by_id` as an ordinary missing row.
    """
    rows_by_id: dict = {}
    anomalies: list = []
    seen_ids: set = set()
    duplicate_ids: set = set()
    header_seen = False
    separator_seen = False
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            if header_seen:
                break
            continue
        if is_section_boundary(stripped, separator_seen=separator_seen):
            break
        if not stripped.startswith("|"):
            if header_seen:
                break
            continue
        if not header_seen:
            header_seen = True
            continue
        if not separator_seen:
            separator_seen = True
            continue
        cells = split_row_cells(line)
        if len(cells) != COLUMN_COUNT:
            anomalies.append(
                f"malformed row (cell count {len(cells)} != {COLUMN_COUNT}): {stripped[:80]}"
            )
            continue
        item_id = cells[COL_ID]
        if item_id in seen_ids:
            duplicate_ids.add(item_id)
            rows_by_id.pop(item_id, None)
            continue
        seen_ids.add(item_id)
        rows_by_id[item_id] = cells
    for item_id in sorted(duplicate_ids):
        anomalies.append(
            f"duplicate row for id {item_id}: the same id appears more than "
            "once in this table -- neither copy is trusted"
        )
    return rows_by_id, anomalies, duplicate_ids


def _list_disk_generated_files(backlog_dir: Path, archive_dir: Path, naming: IndexNaming) -> list:
    """Every on-disk file matching `is_generated_index_file` under `naming`
    (Finding F5 -- the project's real config-derived naming, never a
    hardcoded stem, so a custom `archive_dir` is actually looked in and a
    custom hub name is actually recognized), hub or Archive shard, whether
    or not this run's fresh set still produces it. The stale ones --
    present here but absent from the fresh set -- are what `--check`
    reports as drift and `--write` removes as part of the same atomic
    replace (never any other file, never an item file).
    """
    found = []
    for directory in (backlog_dir, archive_dir):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if is_generated_index_file(path.name, naming):
                found.append(path)
    return found


def detect_line_ending(backlog_dir: Path, archive_dir: Path, naming: IndexNaming) -> str:
    """Detect the existing generated-file line-ending convention, once per
    `--write` run, so the hub and every shard share the SAME one.

    `build_index_files` always renders with `\\n` internally -- unchanged by
    this function, and unchanged by anything below it. This is purely a
    `--write`-time conversion applied to the staged bytes right before they
    are written, per Step 8's "write through the newline-preserving
    helpers": that requirement is to preserve the file's EXISTING style,
    not merely to avoid *translating* whichever style the write happens to
    use, so detection has to run before the convert-and-write.

    Reads the existing hub first via `read_text_preserving_newlines` (no
    universal-newline translation) -- the canonical file, named via
    `naming.hub_name` (Finding F5). Falls back to the first on-disk file
    `is_generated_index_file` matches when the hub does not exist yet (a
    shard can exist without a hub only in a transient state). Returns
    `"\\n"` when nothing generated exists at all -- there is no existing
    convention to preserve, so a first-ever `--write` is free to pick
    either, and `\\n` is what `build_index_files` already renders.
    """
    hub_path = backlog_dir / naming.hub_name
    candidate = hub_path if hub_path.exists() else None
    if candidate is None:
        for path in _list_disk_generated_files(backlog_dir, archive_dir, naming):
            candidate = path
            break
    if candidate is None:
        return "\n"
    content = read_text_preserving_newlines(candidate)
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    return "\r\n" if crlf_count >= lf_count else "\n"


def _is_numeric_score(value: str) -> bool:
    """True for a Score cell that parses as an integer -- what every OPEN
    item's cell is supposed to hold. `"-"` (the CLOSED-item convention),
    an empty cell, and free text (`"abc"`) are all non-numeric.
    """
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _check_drift(
    items: list, report: dict, backlog_dir: Path, archive_dir: Path, naming: IndexNaming
) -> dict:
    """Compare the freshly computed file set against on-disk content.

    Returns `{"drift": [...], "anomaly": [...], "stale_score": [...]}` --
    the three classes Step 2/3 requires. `drift`/`anomaly` entries are
    `{"id", "reason"}` dicts; `stale_score` entries are `{"id", "on_disk",
    "fresh"}` dicts, so a report can show what actually moved (`57 -> 59`)
    rather than only naming the id -- an id-only line cannot distinguish an
    ordinary age-driven nudge from a wholesale corruption or a scoring
    regression landing in the same benign-looking bucket. Never writes --
    `--write` re-derives its own fresh set independently rather than
    reusing this comparison, so a `--check` run has no side effect on the
    eventual `--write`.

    A file whose only difference from the fresh render is its line-ending
    style (CRLF on disk vs. the `\n` `build_index_files` always renders
    internally) is never reported as drift: `_read_disk_table` calls
    `str.strip()`/`split_row_cells` per line, both of which drop a trailing
    `\r` before comparing cell values, so a CRLF file and an LF file with
    otherwise-identical rows parse to identical cell lists. Proven directly,
    not merely reasoned about -- see Outputs run 7 (rewrite an on-disk hub
    to CRLF, `--check` still exits 0).

    A Score-only difference is `stale-score` ONLY when the on-disk Score is
    itself numeric on an open item; a non-numeric on-disk Score (`-`,
    blank, `abc`) on an OPEN item is `drift` instead -- a CLOSED item's `-`
    matches the fresh render exactly (both sides render `-`) and never
    reaches this branch at all, so this narrowing never fires on the
    convention it is not aimed at.

    A repeated id is quarantined and reported as a single anomaly whether
    the two copies sit in the SAME file (`_read_disk_table`'s own
    within-file duplicate detection, Finding F2) or in TWO DIFFERENT
    generated files (Finding F3 -- e.g. a stale hub copy of an item whose
    correct row has already moved to its Archive shard; each file alone
    carries only one clean-looking row for the id, so no single
    `_read_disk_table` call ever sees the collision, and the old
    last-wins-across-files assignment into `disk_by_id` read it clean).
    """
    known_ids = {item["id"] for item in items}
    open_ids = {item["id"] for item in items if is_open_item(item)}

    fresh_by_id: dict = {}
    fresh_file_by_id: dict = {}
    for entry in report["files"]:
        rows, _errs, _dup = _read_disk_table(entry["content"])
        for item_id, cells in rows.items():
            fresh_by_id[item_id] = cells
            fresh_file_by_id[item_id] = entry["path"]

    fresh_paths = {(backlog_dir / entry["path"]).resolve() for entry in report["files"]}
    disk_files = _list_disk_generated_files(backlog_dir, archive_dir, naming)
    stale_paths = {p for p in disk_files if p.resolve() not in fresh_paths}

    disk_by_id: dict = {}
    disk_file_by_id: dict = {}
    disk_files_seen: dict = {}  # id -> [rel_path, ...], every file it appeared in (F3)
    quarantined_ids: set = set()  # duplicate ids -- already anomaly-reported below
    drift: list = []
    anomaly: list = []
    stale_score: list = []

    for path in stale_paths:
        rel = _relative_file_path(path, backlog_dir)
        drift.append({
            "id": rel,
            "reason": "stale generated file, not in the currently generated set",
        })

    for path in disk_files:
        if path in stale_paths:
            # Its removal is already reported above; a stale file's own rows
            # are not also diffed here -- `--write` deletes the whole file,
            # so a per-row anomaly about ids it happens to carry would be
            # reporting noise about content that is about to disappear.
            continue
        rel = _relative_file_path(path, backlog_dir)
        content = read_text_preserving_newlines(path)
        if rel == naming.hub_name:
            if _footer_line(naming).strip() not in content:
                drift.append({
                    "id": rel,
                    "reason": "changelog footer is missing from the hub",
                })
            else:
                changelog_path = backlog_dir / _changelog_filename(naming)
                if not changelog_path.exists():
                    drift.append({
                        "id": rel,
                        "reason": (
                            f"changelog footer points to {changelog_path.name}, "
                            "but that file does not exist"
                        ),
                    })
        rows, errs, dup_ids = _read_disk_table(content)
        for err in errs:
            anomaly.append({"id": rel, "reason": err})
        quarantined_ids |= dup_ids
        for item_id, cells in rows.items():
            disk_files_seen.setdefault(item_id, []).append(rel)
            disk_by_id[item_id] = cells
            disk_file_by_id[item_id] = rel

    # Cross-file duplicates (Finding F3): an id whose CLEAN (non-within-file
    # -duplicated) rows came from more than one generated file. Quarantine
    # and report exactly once, naming every file involved.
    for item_id, files_seen in disk_files_seen.items():
        distinct_files = sorted(set(files_seen))
        if len(distinct_files) > 1:
            quarantined_ids.add(item_id)
            anomaly.append({
                "id": item_id,
                "reason": (
                    f"duplicate row for id {item_id}: appears in more than "
                    f"one generated file ({', '.join(distinct_files)}) -- "
                    "neither copy is trusted"
                ),
            })
    for item_id in quarantined_ids:
        disk_by_id.pop(item_id, None)
        disk_file_by_id.pop(item_id, None)

    for item_id, disk_cells in disk_by_id.items():
        if item_id not in known_ids:
            anomaly.append({
                "id": item_id,
                "reason": (
                    f"row present in {disk_file_by_id[item_id]} but its item "
                    "file no longer resolves"
                ),
            })
            continue
        fresh_cells = fresh_by_id.get(item_id)
        if fresh_cells is None or disk_cells == fresh_cells:
            continue
        same_file = disk_file_by_id[item_id] == fresh_file_by_id[item_id]
        only_score_differs = same_file and all(
            d == f for i, (d, f) in enumerate(zip(disk_cells, fresh_cells)) if i != COL_SCORE
        )
        disk_score = disk_cells[COL_SCORE]
        if only_score_differs and (item_id not in open_ids or _is_numeric_score(disk_score)):
            stale_score.append({
                "id": item_id,
                "on_disk": disk_score,
                "fresh": fresh_cells[COL_SCORE],
            })
        elif only_score_differs:
            # Score-only, but non-numeric on an OPEN item: missing data, not
            # aged data -- narrowed out of stale-score (Finding F3b) so a
            # hand-cleared or corrupted Score cell cannot hide behind the
            # carve-out that exists for ordinary time-driven drift.
            drift.append({
                "id": item_id,
                "reason": (
                    f"Score cell '{disk_score}' is non-numeric on an open "
                    f"item (on-disk: {disk_file_by_id[item_id]}, current: "
                    f"{fresh_file_by_id[item_id]})"
                ),
            })
        else:
            drift.append({
                "id": item_id,
                "reason": (
                    f"row disagrees with frontmatter (on-disk: "
                    f"{disk_file_by_id[item_id]}, current: {fresh_file_by_id[item_id]})"
                ),
            })

    missing_ids = known_ids - disk_by_id.keys() - quarantined_ids
    for item_id in sorted(missing_ids, key=int):
        drift.append({
            "id": item_id,
            "reason": f"no on-disk row yet (would be added to {fresh_file_by_id[item_id]})",
        })

    return {"drift": drift, "anomaly": anomaly, "stale_score": stale_score}


def _format_check_report(result: dict) -> str:
    """Render the human-readable `--check` banner: the shared drift/anomaly
    shape from `reconcile_common.format_drift_report`, plus a stale-score
    section that is never itself a failure.
    """
    banner = format_drift_report(
        {"drifts": result["drift"], "anomalies": result["anomaly"]},
        no_drift_message="No drift detected. The index matches item frontmatter.",
        no_drift_only_message="No drift detected.",
        drift_header=f"Drift detected ({len(result['drift'])} row(s) out of sync with frontmatter):",
        drift_line=lambda d: f"  - {d['id']}: {d['reason']}",
        anomaly_line=lambda a: f"  - {a['id']}: {a['reason']}",
    )
    lines = [banner]
    if result["stale_score"]:
        lines.append("")
        lines.append(
            f"Stale scores ({len(result['stale_score'])}, benign and self-healing "
            "-- not a --check failure):"
        )
        for entry in result["stale_score"]:
            lines.append(f"  - {entry['id']}: {entry['on_disk']} -> {entry['fresh']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Atomic multi-file write
# --------------------------------------------------------------------------


def _atomic_write_files(files_to_write: dict, files_to_delete: list) -> None:
    """Write every fresh file and remove every stale one as a single unit:
    hub and every shard together, or not at all.

    Phase 1 stages each new file's content into a temp file beside its
    final location (same directory, so `os.replace` below is atomic on that
    file). Nothing that already exists is touched during staging. Backups
    of every final path this call is about to touch (write or delete) are
    captured before the commit phase begins. Phase 2 -- the commit -- calls
    `os.replace` for every staged file and then removes every stale file.
    `os.replace` is atomic per file but cannot replace a file another
    process holds open; if it (or the delete) raises partway through the
    commit phase, every change this call already committed is rolled back
    from the captured backups, and any temp file that never reached the
    rename step is discarded -- so a mid-write failure leaves the prior
    on-disk state intact rather than a half-regenerated set where the hub
    lists shards that were never written.
    """
    staged = []  # (tmp_path, final_path)
    try:
        for final_path, content in files_to_write.items():
            final_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(final_path.parent), prefix=final_path.name + ".", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            staged.append((Path(tmp_name), final_path))
    except OSError:
        for tmp_path, _final in staged:
            tmp_path.unlink(missing_ok=True)
        raise

    backups: dict = {}
    for _tmp_path, final_path in staged:
        backups[final_path] = final_path.read_bytes() if final_path.exists() else None
    for final_path in files_to_delete:
        backups[final_path] = final_path.read_bytes() if final_path.exists() else None

    committed_replaces: list = []
    committed_deletes: list = []
    try:
        for tmp_path, final_path in staged:
            os.replace(tmp_path, final_path)
            committed_replaces.append(final_path)
        for final_path in files_to_delete:
            if final_path.exists():
                final_path.unlink()
            committed_deletes.append(final_path)
    except OSError:
        for final_path in committed_replaces:
            original = backups.get(final_path)
            if original is None:
                final_path.unlink(missing_ok=True)
            else:
                final_path.write_bytes(original)
        for final_path in committed_deletes:
            original = backups.get(final_path)
            if original is not None:
                final_path.write_bytes(original)
        for tmp_path, final_path in staged:
            if final_path not in committed_replaces:
                tmp_path.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run_report_pipeline(
    backlog_dir: Path, archive_dir: Path, index_path: Path, naming: IndexNaming, config: dict
):
    """Shared by `--check` and `--dry-run`/default: scan -> resolve ->
    detect the reciprocal-edge anomaly -> score -> build_index_files ->
    measure. Never refuses early on the reciprocal edge -- a report mode
    always reaches measurement; only `--write` may stop before it. Raises
    `GeneratorError` for the caller to translate into `REFUSED`.

    Returns (items, reciprocal_edges, report).
    """
    items = scan_backlog(backlog_dir, archive_dir, index_path)
    known_ids = {item["id"] for item in items}
    validate_blocks_resolve(items, known_ids)
    blocks_index = build_blocks_index(items)
    reciprocal = detect_reciprocal_edges(blocks_index)
    compute_scores_for_items(items, archive_dir, config)
    report = build_index_files(items, backlog_dir, archive_dir, naming)
    return items, reciprocal, report


def _print_file_report(report: dict) -> None:
    for entry in report["files"]:
        print(
            f"{entry['path']}: {entry['rows']} rows, {entry['bytes']} bytes, "
            f"{entry['tokens']} tokens, budget {entry['budget']}, "
            f"headroom {entry['headroom']}, page_cap_ratio "
            f"{entry['page_cap_ratio']} (basis: {entry['basis']})"
        )


def _file_summary(report: dict) -> list:
    return [
        {k: v for k, v in entry.items() if k not in ("content", "truncated_ids")}
        for entry in report["files"]
    ]


def _reciprocal_anomalies(items: list, reciprocal: list) -> list:
    paths_by_id = {item["id"]: item["_path"] for item in items}
    return [
        {
            "id": f"{a},{b}",
            "reason": (
                f"reciprocal blocks edge -- {a} ({paths_by_id[a]}) and {b} "
                f"({paths_by_id[b]}) each block the other"
            ),
        }
        for a, b in reciprocal
    ]


def _cmd_write(
    backlog_dir: Path,
    archive_dir: Path,
    index_path: Path,
    naming: IndexNaming,
    config: dict,
    *,
    json_out: bool,
) -> int:
    """`--write`: re-scans fresh (the only scan this command performs, so it
    is by construction the race-safe "re-read immediately before healing"
    Step 7 requires), refuses before touching disk on any unresolved
    condition, then atomically regenerates the hub and every shard and
    removes any stale generated file the fresh set no longer produces.
    Never touches an item file (the generator reads frontmatter and
    writes only the index) -- every path this
    function writes or deletes comes from `report["files"]` or
    `_list_disk_generated_files`, both scoped to `is_generated_index_file`.
    """
    try:
        items = scan_backlog(backlog_dir, archive_dir, index_path)
        known_ids = {item["id"] for item in items}
        validate_blocks_resolve(items, known_ids)
    except GeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return Disposition.REFUSED

    blocks_index = build_blocks_index(items)
    reciprocal = detect_reciprocal_edges(blocks_index)
    if reciprocal:
        for entry in _reciprocal_anomalies(items, reciprocal):
            print(f"Anomaly: {entry['reason']}. Refusing to write.", file=sys.stderr)
        return Disposition.REFUSED

    compute_scores_for_items(items, archive_dir, config)

    try:
        report = build_index_files(items, backlog_dir, archive_dir, naming)
    except GeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return Disposition.REFUSED

    fresh_paths = {(backlog_dir / entry["path"]).resolve() for entry in report["files"]}
    stale = [
        p for p in _list_disk_generated_files(backlog_dir, archive_dir, naming)
        if p.resolve() not in fresh_paths
    ]
    files_to_write = {backlog_dir / entry["path"]: entry["content"] for entry in report["files"]}

    # The changelog is not a generated index artifact (it's never in
    # report["files"]), so it's never touched here except this one
    # header-only bootstrap when the footer's own target is missing --
    # never overwrites an existing changelog (closeout review Finding 1c).
    changelog_path = backlog_dir / _changelog_filename(naming)
    if not changelog_path.exists():
        files_to_write[changelog_path] = f"[← {naming.hub_name}]({naming.hub_name})\n"

    # Preserve the EXISTING on-disk convention rather than always shipping
    # the `\n` `build_index_files` renders internally -- detected once per
    # run so the hub and every shard agree, and applied only to the staged
    # bytes here, never to the in-memory report/--json/--dry-run output.
    line_ending = detect_line_ending(backlog_dir, archive_dir, naming)
    if line_ending != "\n":
        files_to_write = {
            path: content.replace("\n", line_ending)
            for path, content in files_to_write.items()
        }

    try:
        _atomic_write_files(files_to_write, stale)
    except OSError as exc:
        # Rollback inside _atomic_write_files already succeeded (or it
        # would have re-raised something else); this is the write itself
        # failing, e.g. a shard held open by another process on Windows.
        # Report and refuse rather than let the traceback read as if
        # `--check` had found drift.
        path = getattr(exc, "filename", None) or "unknown path"
        print(f"Error: write failed and was rolled back ({path}): {exc}", file=sys.stderr)
        return Disposition.REFUSED

    for item_id in report["truncated_ids"]:
        print(
            f"Warning: title truncated to {TITLE_MAX_LEN} chars for item {item_id}",
            file=sys.stderr,
        )
    for p in stale:
        print(f"Removed stale generated file: {p}")

    if json_out:
        print(json.dumps(
            {"written": _file_summary(report), "removed": [str(p) for p in stale]}, indent=2
        ))
    else:
        print(f"Wrote {len(files_to_write)} file(s), removed {len(stale)} stale generated file(s).")
    return Disposition.CLEAN


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan backlog item frontmatter and render/check/write the Backlog Items index."
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Render and measure without writing anything. This is also the "
            "default behavior when no mode flag is given."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Compare the on-disk hub/shards against what item frontmatter "
            "would produce right now; report drift/anomaly/stale-score and "
            "exit non-zero on drift or anomaly (never on stale-score alone)."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Atomically regenerate the hub and every shard, and remove any "
            "stale generated file. Refuses (exit 2) rather than writing on "
            "any unresolved condition -- a missing required key, an "
            "unresolvable blocks: id, an unshardable row, or a reciprocal "
            "blocks: cycle."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Print the per-file sharding/budget report (path, rows, bytes, "
            "tokens, measurement basis, budget, headroom, page_cap_ratio, "
            "split) as JSON instead of "
            "the flat table; for --check, adds the drift/anomaly/stale-score "
            "result."
        ),
    )
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]
    index_path = config["_index_path"]
    # Finding F5: every generated filename this run produces or recognizes
    # comes from THIS project's actual configured index path, computed once
    # and threaded through every mode -- never the hardcoded fallback stem
    # a bare pure-function call (this module's own tests) still defaults to.
    naming = _index_naming(index_path)

    if args.write:
        return _cmd_write(backlog_dir, archive_dir, index_path, naming, config, json_out=args.json)

    try:
        items, reciprocal, report = _run_report_pipeline(
            backlog_dir, archive_dir, index_path, naming, config
        )
    except GeneratorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return Disposition.REFUSED

    for item_id in report["truncated_ids"]:
        print(
            f"Warning: title truncated to {TITLE_MAX_LEN} chars for item {item_id}",
            file=sys.stderr,
        )

    reciprocal_anomalies = _reciprocal_anomalies(items, reciprocal)
    for entry in reciprocal_anomalies:
        print(f"Anomaly: {entry['reason']}.", file=sys.stderr)

    if args.check:
        result = _check_drift(items, report, backlog_dir, archive_dir, naming)
        result["anomaly"] = reciprocal_anomalies + result["anomaly"]
        drift_or_anomaly = bool(result["drift"]) or bool(result["anomaly"])
        code = exit_code_for(
            write_mode=False, reciprocal_edge=bool(reciprocal), drift_or_anomaly=drift_or_anomaly
        )
        if args.json:
            payload = {
                "files": _file_summary(report),
                "drift": result["drift"],
                "anomaly": result["anomaly"],
                "stale_score": result["stale_score"],
            }
            print(json.dumps(payload, indent=2))
        else:
            _print_file_report(report)
            print()
            print(_format_check_report(result))
        return code

    code = exit_code_for(write_mode=False, reciprocal_edge=bool(reciprocal), drift_or_anomaly=False)
    if args.json:
        print(json.dumps(_file_summary(report), indent=2))
        return code

    _print_file_report(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
