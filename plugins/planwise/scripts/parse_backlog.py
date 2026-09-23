#!/usr/bin/env python3
"""Parse the backlog index markdown and output filtered items."""

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from constants import CLOSED_STATUSES, HOLD_STATUSES
from generate_backlog_index import _index_naming, is_generated_index_file, shard_for
from markdown_parser import (
    id_number,
    normalize_id,
    parse_markdown_table,
)

# The heading a hand-authored legacy index carries above its table.
# generate_backlog_index.py's hub/overflow-leaf/Archive-shard output never
# emits this heading -- its table starts at the file's own first
# `| ID | ... |` row. `with_section_heading` (defined below -- public, no
# leading underscore) splices it onto content that lacks it, so
# `parse_markdown_table`'s existing header/separator/stop-condition walk
# handles both shapes without a second table-walking path.
# `score_backlog.py` imports `with_section_heading` directly to apply the
# same splice to its own reader/writer, rather than re-deriving the
# pattern. This constant itself keeps its leading underscore -- it is
# imported nowhere else.
_BACKLOG_SECTION_HEADER = "## Backlog Items"


def with_section_heading(content: str) -> str:
    """Prepend `_BACKLOG_SECTION_HEADER` when `content` doesn't carry it.

    A hand-authored index already has it; a generated hub, overflow leaf,
    or Archive shard never does.
    """
    if _BACKLOG_SECTION_HEADER in content:
        return content
    return f"{_BACKLOG_SECTION_HEADER}\n\n{content}"


def _parse_row_blocks_cell(raw: str) -> list[str]:
    """Parse a 9-column generated row's Blocks cell into a list of id
    strings, exactly as rendered.

    Mirrors ``generate_backlog_index._render_blocks_cell``'s own format --
    the only shape this cell is ever written in: ``""`` for no blocks, or
    ``"[007, 009]"`` for one or more. Ids are returned exactly as rendered
    (zero-padded, un-normalized); ``build_blocked_by_map`` normalizes at
    consumption, matching ``_dependency_row_processor``'s own zfill'd-on-
    write / normalized-on-read convention.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    inner = text.strip("[]")
    return [part.strip() for part in inner.split(",") if part.strip()]


def _backlog_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a backlog table row into an item dict.

    Score and Files are read position-RELATIVE to the row's own width
    (``cells[-2]`` / ``cells[-1]``), matching score_backlog.py's existing
    convention and generate_backlog_index.py's own asserted contract
    (``COL_SCORE == COLUMN_COUNT - 2``, ``COL_FILE == COLUMN_COUNT - 1``) --
    a 7- or 9-column row resolves correctly with no per-width branch. The
    leading four columns (ID, Title, Priority, Status) stay at their
    absolute positions 0-3: update_backlog.py:41 pins Status at index 3
    across every shape, so a relative read there would disagree with the
    one writer that already exists.

    A 6-column row -- the oldest legacy shape -- carries no Score column
    at all; ``cells[-2]`` on a 6-cell row would misread the Abbrev cell as
    Score, so that width keeps its own branch: Score is absent (0) and
    Files is still the last cell.

    A 9-column generated row also carries a Blocks cell at ``cells[-3]``
    (``generate_backlog_index.COL_BLOCKS == COLUMN_COUNT - 3``), parsed into
    ``item["blocks"]`` via ``_parse_row_blocks_cell``. Neither legacy width
    (6 or 7 columns) has a Blocks cell at all, so both keep ``blocks: []``.
    """
    if len(cells) < 6:
        return None

    if len(cells) >= 7:
        try:
            score = int(cells[-2]) if cells[-2] else 0
        except ValueError:
            score = 0
    else:
        score = 0
    files_raw = cells[-1]
    blocks = _parse_row_blocks_cell(cells[-3]) if len(cells) >= 9 else []

    file_links = re.findall(r"\[(\d+)\]\(([^)]+)\)", files_raw)
    files = [{"label": label, "path": path} for label, path in file_links]

    return {
        "id": cells[0],
        "feature": cells[1],
        "priority": cells[2],
        "status": cells[3],
        "abbrev": cells[4],
        "score": score,
        "files": files,
        "blocks": blocks,
    }


def parse_backlog_table(content: str) -> list[dict]:
    """Parse the Backlog Items markdown table into a list of dicts.

    Accepts both on-disk shapes without special-casing either: a
    hand-authored legacy index (6- or 7-column rows under an explicit
    "## Backlog Items" heading), and a generate_backlog_index.py-produced
    hub, hub overflow leaf, or Archive shard (9-column rows with no
    section heading at all). ``with_section_heading`` normalizes the
    second shape onto the first before the shared table walker runs.
    ``with_section_heading`` is public because ``score_backlog.py`` imports
    it directly rather than re-deriving the splice.

    A row whose cell count differs from the header's now aborts the parse
    outright (``strict=True``) instead of being warned about and silently
    dropped -- two rows in this repo stayed wrong for months under the old
    warn-and-skip behavior, invisible to every prioritisation pass. The
    parsed-row count is then asserted against the table's own row count as
    a second, independent check: this should be unreachable once
    ``strict``'s cell-count gate is doing its job, and exists only to
    catch a bug in the row processor itself (e.g. a header so malformed
    its own cell count reads as too low), not a malformed data row.
    """
    stats: dict = {}
    items = parse_markdown_table(
        with_section_heading(content),
        _BACKLOG_SECTION_HEADER,
        _backlog_row_processor,
        stats=stats,
        strict=True,
    )
    if len(items) != stats["rows_present"]:
        print(
            f"Error: parsed {len(items)} row(s) but {stats['rows_present']} "
            f"were present in the '{_BACKLOG_SECTION_HEADER}' table -- a row "
            f"was silently dropped despite strict parsing. This indicates a "
            f"bug in the row processor, not a malformed row (those now abort "
            f"directly).",
            file=sys.stderr,
        )
        sys.exit(1)
    return items


def _dependency_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a dependency table row into a dep dict."""
    if len(cells) < 2:
        return None
    blocker_id = cells[0].zfill(3)
    blocked_raw = cells[1]
    blocked_ids = [b.strip().zfill(3) for b in blocked_raw.split(",")]
    return {
        "blocker_id": blocker_id,
        "blocked_ids": blocked_ids,
    }


def parse_dependencies_table(content: str) -> list[dict]:
    """Parse the Dependencies table from the index.

    Returns list of dicts with keys: blocker_id, blocked_ids (list of str).
    Only parses hard blockers -- stops at "Soft dependencies" or next section.
    Read-if-present: a generated hub never carries a ``## Dependencies``
    section, so ``require_section=False`` returns an empty list rather than
    erroring, and ``build_blocked_by_map`` unions whatever this returns with
    the row-level Blocks column instead of depending on it existing.
    """
    return parse_markdown_table(
        content, "## Dependencies", _dependency_row_processor,
        stop_before="**Soft dependencies", require_section=False,
    )


# --------------------------------------------------------------------------
# Hub + overflow-leaf + Archive-shard resolution.
#
# A generate_backlog_index.py corpus is never one file: open items live in
# the hub `00-Index-Backlog.md` and, once the hub exceeds its token budget,
# in hub overflow leaves beside it; closed items live in Archive shards
# grouped by `shard_for(id) = (id-1)//100`. `is_generated_index_file` and
# `shard_for` are imported directly from generate_backlog_index.py, never
# re-derived, so the reader and the generator cannot drift on what counts
# as a generated filename or which century an id belongs to.
#
# PINNED: a row's File cell (`item["files"][*]["path"]`) is ALWAYS relative
# to `backlog_dir`, regardless of which of these files the row was read
# from -- including a row read out of an Archive shard, whose own file
# lives one directory deeper (`backlog_dir/Archive/...`). Resolve every
# File cell as `backlog_dir / path`, never relative to the shard/leaf file
# that yielded the row. See `references/backlog-schema.md`'s File-column
# note for the accepted cost this pins (a human clicking the link from
# inside a shard lands one directory too deep).
# --------------------------------------------------------------------------


def _enumerate_generated_files(directory: Path, naming) -> list[Path]:
    """Every on-disk file under `directory` that `is_generated_index_file`
    recognizes under `naming` -- the hub plus its overflow leaves when
    `directory` is `backlog_dir`, or every Archive shard when `directory`
    is `archive_dir`. A hand-authored legacy index also matches (its name
    equals `naming.hub_name` by construction), so this enumerates a
    single-file legacy corpus unchanged. Sorted for a deterministic read
    order.
    """
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and is_generated_index_file(path.name, naming)
    )


def _read_backlog_items(path: Path) -> list[dict]:
    """Parse one file's Backlog Items table -- hub, leaf, shard, or a
    hand-authored legacy index. Returns [] for a file that no longer
    exists rather than raising, since callers enumerate a directory
    listing that can race a concurrent write.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_backlog_table(content)


def collect_all_known_ids(config: dict) -> list[str]:
    """Every id visible anywhere: the hub, every hub overflow leaf, and
    every Archive shard. `--next-id` unions across all three (Execution
    Step 5) -- a hub-only max would reissue an id that already exists in a
    shard, the collision this whole resolution exists to prevent.
    """
    naming = _index_naming(config["_index_path"])
    ids: list[str] = []
    for path in _enumerate_generated_files(config["_backlog_dir"], naming):
        ids.extend(item["id"] for item in _read_backlog_items(path))
    for path in _enumerate_generated_files(config["_archive_dir"], naming):
        ids.extend(item["id"] for item in _read_backlog_items(path))
    return ids


def resolve_closed_item_shard(item_id: str, config: dict) -> tuple[Path | None, bool]:
    """Locate the Archive shard file holding a closed item's row.

    `shard_for` computes the id's century, and this checks it against a
    full-century-shaped filename guess (`century*100+1` to
    `century*100+100`) -- no directory listing, no id-to-shard table. The
    guess is exact whenever a century is fully closed (its shard covers
    the century's whole width); it is not exact for a century that still
    interleaves open ids with closed ones, since the generator names a
    shard by its own items' real min/max, not the century's boundary.

    When the guess misses, this falls back to reading every on-disk
    shard's OWN filename-embedded range (a directory listing, never a
    row-by-row content scan) and returns whichever one covers the id --
    reported on stderr rather than silently absorbed, because a missing
    expected shard is the anomaly Execution Step 4 calls out.

    Returns (path_or_None, used_fallback).
    """
    numeric_id = id_number(item_id)
    if numeric_id is None:
        return None, False

    naming = _index_naming(config["_index_path"])
    archive_dir = config["_archive_dir"]
    century = shard_for(numeric_id)
    lo, hi = century * 100 + 1, century * 100 + 100
    guess_name = f"{naming.archive_stem}-{lo:03d}-{hi:03d}{naming.suffix}"
    guess_path = archive_dir / guess_name
    if guess_path.is_file():
        return guess_path, False

    print(
        f"Warning: the computed Archive shard {guess_name} for id {item_id} "
        f"(century {century}) is absent -- falling back to a directory scan.",
        file=sys.stderr,
    )
    range_re = re.compile(
        r"^" + re.escape(naming.archive_stem) + r"-(\d{3,})-(\d{3,})"
        + re.escape(naming.suffix) + r"$"
    )
    for path in _enumerate_generated_files(archive_dir, naming):
        m = range_re.match(path.name)
        if m and int(m.group(1)) <= numeric_id <= int(m.group(2)):
            return path, True

    return None, True


def build_blocked_by_map(
    dependencies: list[dict], items: list[dict]
) -> dict[str, list[str]]:
    """Build reverse dependency map: blocked_item_id -> [open blocker IDs].

    Unions two edge sources: the hand-authored ``## Dependencies`` table
    (``dependencies``), read-if-present via ``parse_dependencies_table``,
    and each item's own 9-column row-level Blocks cell (``item["blocks"]``,
    from ``_backlog_row_processor``). The generator never writes a
    ``## Dependencies`` section (Execution Step 5 of the pre-write
    repairs), so a generated corpus (no such section; ``dependencies`` is
    empty) blocks from the Blocks column alone, exactly as before this
    union was restored. A consumer upgraded from an older release but not
    yet migrated carries a 6/7-column legacy index with no Blocks column at
    all -- its only edges live in ``## Dependencies``, and without this
    union ``--show-blocked`` would report nothing and every blocked item
    would silently become routable. Both sources share the same
    open-blocker-only guard: a CLOSED/COMPLETE blocker's edge is already
    resolved and must not still hold a blocked item back.
    """
    status_map = {normalize_id(item["id"]): item["status"] for item in items}
    blocked_by: dict[str, list[str]] = {}

    for dep in dependencies:
        blocker = normalize_id(dep["blocker_id"])
        if status_map.get(blocker, "") not in CLOSED_STATUSES:
            for blocked_id in dep["blocked_ids"]:
                blocked_by.setdefault(normalize_id(blocked_id), []).append(blocker)

    for item in items:
        blocker = normalize_id(item["id"])
        if status_map.get(blocker, "") in CLOSED_STATUSES:
            continue
        for blocked_id in item.get("blocks", []):
            normalized_blocked = normalize_id(blocked_id)
            existing = blocked_by.setdefault(normalized_blocked, [])
            if blocker not in existing:
                existing.append(blocker)

    return blocked_by


@dataclass
class FilterCriteria:
    """Bundle of filter parameters for backlog item selection."""
    status: str | None = None
    priority: str | None = None
    abbrev: str | None = None
    item_id: str | None = None
    include_closed: bool = False
    show_blocked: bool = False


def filter_items(
    items: list[dict],
    criteria: FilterCriteria,
    blocked_by_map: dict[str, list[str]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Filter items by provided criteria. Returns (selectable_items, blocked_items)."""
    filtered = []
    blocked = []
    for item in items:
        if not criteria.include_closed and item["status"] in CLOSED_STATUSES:
            continue
        if criteria.status and item["status"].upper() != criteria.status.upper():
            continue
        if criteria.priority and item["priority"].lower() != criteria.priority.lower():
            continue
        if criteria.abbrev and item["abbrev"].upper() != criteria.abbrev.upper():
            continue
        if criteria.item_id and normalize_id(item["id"]) != normalize_id(criteria.item_id):
            continue

        if not criteria.show_blocked:
            if item["status"].upper() in HOLD_STATUSES:
                blocked.append(item)
                continue
            if blocked_by_map and blocked_by_map.get(normalize_id(item["id"])):
                blocked.append(item)
                continue

        filtered.append(item)

    return filtered, blocked


def format_table(items: list[dict], sort_by: str = "score") -> str:
    """Format items as a readable table."""
    if not items:
        return "No items match filters."

    if sort_by == "score":
        items = sorted(items, key=lambda x: (-x.get("score", 0), x["id"]))
    else:
        items = sorted(items, key=lambda x: x["id"])

    id_w = max(len(item["id"]) for item in items)
    id_w = max(id_w, 2)
    feat_w = max(len(item["feature"]) for item in items)
    feat_w = min(max(feat_w, 7), 55)
    pri_w = max(len(item["priority"]) for item in items)
    pri_w = max(pri_w, 8)
    stat_w = max(len(item["status"]) for item in items)
    stat_w = max(stat_w, 6)
    abbr_w = max(len(item["abbrev"]) for item in items)
    abbr_w = max(abbr_w, 6)
    score_w = 5
    files_w = 5

    header = (
        f"{'ID':<{id_w}} | {'Feature':<{feat_w}} | {'Priority':<{pri_w}} | "
        f"{'Status':<{stat_w}} | {'Abbrev':<{abbr_w}} | {'Score':>{score_w}} | {'Files':<{files_w}}"
    )
    separator = (
        f"{'-' * id_w}-+-{'-' * feat_w}-+-{'-' * pri_w}-+-"
        f"{'-' * stat_w}-+-{'-' * abbr_w}-+-{'-' * score_w}-+-{'-' * files_w}"
    )

    lines = [header, separator]

    for item in items:
        feature = item["feature"]
        if len(feature) > 55:
            feature = feature[:52] + "..."
        file_count = str(len(item["files"]))
        score_str = str(item.get("score", 0))

        lines.append(
            f"{item['id']:<{id_w}} | {feature:<{feat_w}} | {item['priority']:<{pri_w}} | "
            f"{item['status']:<{stat_w}} | {item['abbrev']:<{abbr_w}} | {score_str:>{score_w}} | {file_count:<{files_w}}"
        )

    lines.append(f"\n{len(items)} item(s) found.")
    return "\n".join(lines)


def format_blocked_summary(
    blocked_items: list[dict],
    blocked_by_map: dict[str, list[str]],
    id_to_title: dict[str, str] | None = None,
) -> str:
    """Format a summary of blocked items with their blockers or hold status.

    `id_to_title` is an optional normalize_id-keyed lookup of blocker id ->
    feature title, built by the caller from data it already has in memory
    (the already-parsed item list) -- no second read or parse of the index.
    When absent, or when a given blocker id has no entry, that blocker
    renders as a bare id (`blocked by: 100`) rather than failing; ids alone
    are strictly better than an empty summary, so a missing title is never
    fatal.
    """
    if not blocked_items:
        return ""

    lines = ["", "--- Blocked Items (resolve blockers or holds first) ---"]

    for item in sorted(blocked_items, key=lambda x: (-x.get("score", 0), x["id"])):
        blockers = blocked_by_map.get(normalize_id(item["id"]), [])
        if blockers:
            named = []
            for blocker_id in blockers:
                title = (id_to_title or {}).get(blocker_id)
                if title:
                    if len(title) > 30:
                        title = title[:27] + "..."
                    named.append(f"{blocker_id} ({title})")
                else:
                    named.append(blocker_id)
            reason = f"blocked by: {', '.join(named)}"
        else:
            reason = f"held (status: {item['status']})"
        feature = item["feature"]
        if len(feature) > 45:
            feature = feature[:42] + "..."
        score_str = str(item.get("score", 0))
        lines.append(
            f"  {item['id']} | {feature:<45} | {score_str:>3} pts | {reason}"
        )

    lines.append(f"\n{len(blocked_items)} item(s) blocked.")
    return "\n".join(lines)


def write_json(items: list[dict]) -> str:
    """Write items to a JSON temp file and return the path."""
    tmp_dir = tempfile.mkdtemp(prefix="backlog-")
    json_path = os.path.join(tmp_dir, "items.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return json_path


def main():
    parser = argparse.ArgumentParser(
        description="Parse the backlog index and output filtered items."
    )
    parser.add_argument("--status", help="Filter by status (e.g., NOT_STARTED, IN_PROGRESS)")
    parser.add_argument("--priority", help="Filter by priority (e.g., High, Medium, Low)")
    parser.add_argument("--abbrev", help="Filter by abbreviation")
    parser.add_argument("--id", help="Filter by specific item ID (e.g., 003)")
    parser.add_argument("--include-closed", action="store_true", help="Include COMPLETE and CLOSED items")
    parser.add_argument("--show-blocked", action="store_true", help="Include items blocked by open dependencies")
    parser.add_argument("--sort", choices=["score", "id"], default="score", help="Sort order (default: score descending)")
    parser.add_argument("--next-id", action="store_true", help="Print the next available BLI ID (NNN form, zero-padded) and exit.")

    args, _ = parser.parse_known_args()

    # Load config
    config = load_config(Path(__file__))
    index_path = config["_index_path"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")

    if args.next_id:
        # Union across the hub, every hub overflow leaf, and every Archive
        # shard -- a hub-only max would reissue an id a shard already
        # holds (Execution Step 5).
        all_ids = collect_all_known_ids(config)
        numbers = [n for n in (id_number(i) for i in all_ids) if n is not None]
        max_id = max(numbers, default=0)
        if not numbers and all_ids:
            print(
                f"WARNING: {len(all_ids)} row(s) parsed but none carried a numeric ID; "
                f"allocating 001. Check the index's ID column format.",
                file=sys.stderr,
            )
        print(f"{max_id + 1:03d}")
        return

    # Union across the hub and every hub overflow leaf -- an open item
    # living in a leaf must be visible to every filter, not just a direct
    # hub read. `_enumerate_generated_files` matches a hand-authored legacy
    # index by its own filename too, so a single-file corpus's union is
    # exactly that one file and behaves exactly as before.
    naming = _index_naming(index_path)
    hub_family_files = _enumerate_generated_files(config["_backlog_dir"], naming)
    all_items = []
    for path in hub_family_files:
        all_items.extend(_read_backlog_items(path))

    if args.id and normalize_id(args.id) not in {normalize_id(i["id"]) for i in all_items}:
        # Not in the hub family -- the id may be a closed item living in an
        # Archive shard, invisible to every hub-family file. A miss here
        # (shard_path is None) just means the id genuinely doesn't exist
        # anywhere, and the existing "no items match" path below handles it.
        shard_path, _used_fallback = resolve_closed_item_shard(args.id, config)
        if shard_path is not None:
            all_items.extend(_read_backlog_items(shard_path))

    dependencies = parse_dependencies_table(content)
    blocked_by_map = build_blocked_by_map(dependencies, all_items)

    criteria = FilterCriteria(
        status=args.status,
        priority=args.priority,
        abbrev=args.abbrev,
        item_id=args.id,
        include_closed=args.include_closed,
        show_blocked=args.show_blocked,
    )
    filtered, blocked = filter_items(all_items, criteria, blocked_by_map)

    print(format_table(filtered, sort_by=args.sort))

    if blocked:
        # Built from all_items, already parsed above -- no second read of
        # the index. Missing/duplicate titles degrade to a bare id inside
        # format_blocked_summary rather than raising.
        id_to_title = {normalize_id(i["id"]): i["feature"] for i in all_items}
        print(format_blocked_summary(blocked, blocked_by_map, id_to_title))

    # Combine both buckets: a direct `--id` lookup on a held or dependency-blocked
    # item must still resolve the item's data (status included) so the caller can
    # surface the hold before routing, rather than finding nothing.
    if filtered or blocked:
        json_path = write_json(filtered + blocked)
        print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
