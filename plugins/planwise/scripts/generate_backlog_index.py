#!/usr/bin/env python3
"""Scan backlog item frontmatter and render/check/write the Backlog Items index.

Every item file's YAML frontmatter is the single source of truth for its
index row. This module reads that frontmatter and renders it; it never
writes an item file, and it never invents a value for a missing required
key -- a missing key is reported and the run aborts, because a generator
that quietly patches a gap is indistinguishable from one that lost data.

The stages now live in seven sibling modules, split along the seams their
section banners draw. This module re-exports every name they define by
explicit name (`__all__` below), so no caller needs to change:

  - `backlog_index_schema` -- the 9-column layout, the required keys, and
    the config-derived hub, shard, and changelog filenames.
  - `backlog_index_scan` -- frontmatter extraction, the item-file scan, and
    blocks-edge resolution.
  - `backlog_index_render` -- cell and row rendering into one table body.
  - `backlog_index_budget` -- hub/shard partition, scoring via
    `score_backlog.compute_score` (the one scoring implementation), and
    the per-file token budget.
  - `backlog_index_build` -- hub and Archive shard file assembly.
  - `backlog_index_disk` -- the on-disk file listing, line-ending
    detection, and the atomic multi-file write.
  - `backlog_index_drift` -- the `--check` comparison and its report.

This module keeps the CLI (`--dry-run` measures, `--check` compares the
on-disk hub/shards against what frontmatter would produce, `--write`
atomically regenerates all of them) and `Disposition`, the one exit-code
mapping every mode routes through.

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
import sys
from pathlib import Path

# Windows consoles default stdout to cp1252, which cannot encode the em
# dashes and curly quotes several item titles carry.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_budget import (
    CLOSED_STATUSES,
    HUB_HEADROOM_FACTOR,
    HUB_TOKEN_BUDGET,
    MEASUREMENT_BASIS,
    _id_range,
    _measure,
    _shipped_bytes,
    compute_scores_for_items,
    is_open_item,
    partition_items,
    shard_for,
    split_items_to_budget,
)
from backlog_index_build import (
    _budget_fields,
    _continuation_wrapper,
    _generated_line,
    _hub_leaf_entries,
    _relative_link,
    build_hub_files,
    build_index_files,
    build_shard_files,
    hub_wrapper_tokens,
    render_shards_section,
)
from backlog_index_disk import (
    _atomic_write_files,
    _list_disk_generated_files,
    detect_line_ending,
)
from backlog_index_drift import (
    _check_drift,
    _format_check_report,
    _is_numeric_score,
    _read_disk_table,
)
from backlog_index_render import (
    _UNESCAPED_PIPE_RE,
    _escape_cell,
    _relative_file_path,
    _render_blocks_cell,
    _render_file_cell,
    render_header,
    render_row,
    render_separator,
    render_table_body,
    truncate_title,
)
from backlog_index_scan import (
    _LIST_ITEM_RE,
    _extract_fields,
    _iter_item_files,
    _normalize_id_text,
    _parse_list_field,
    _read_frontmatter_map,
    _scan_one_file,
    _strip_quotes,
    build_blocks_index,
    detect_reciprocal_edges,
    scan_backlog,
    validate_blocks_resolve,
)
from backlog_index_schema import (
    _CHANGELOG_HUB_RE,
    _DEFAULT_INDEX_NAMING,
    COL_BLOCKS,
    COL_CREATED,
    COL_DOMAIN,
    COL_FILE,
    COL_ID,
    COL_PRIORITY,
    COL_SCORE,
    COL_STATUS,
    COL_TITLE,
    COLUMN_COUNT,
    HEADER_CELLS,
    INDEX_FILE_STEM,
    REQUIRED_KEYS,
    TITLE_MAX_LEN,
    GeneratorError,
    IndexNaming,
    _changelog_filename,
    _footer_line,
    _generated_index_file_pattern,
    _hub_filename,
    _index_naming,
    _shard_filename,
    is_generated_index_file,
)
from config_loader import get_scoring_weights, load_config
from read_limits import READ_TOKEN_WARN, estimate_tokens

__all__ = [
    "CLOSED_STATUSES",
    "COLUMN_COUNT",
    "COL_BLOCKS",
    "COL_CREATED",
    "COL_DOMAIN",
    "COL_FILE",
    "COL_ID",
    "COL_PRIORITY",
    "COL_SCORE",
    "COL_STATUS",
    "COL_TITLE",
    "Disposition",
    "GeneratorError",
    "HEADER_CELLS",
    "HUB_HEADROOM_FACTOR",
    "HUB_TOKEN_BUDGET",
    "INDEX_FILE_STEM",
    "IndexNaming",
    "MEASUREMENT_BASIS",
    "READ_TOKEN_WARN",
    "REQUIRED_KEYS",
    "TITLE_MAX_LEN",
    "_CHANGELOG_HUB_RE",
    "_DEFAULT_INDEX_NAMING",
    "_LIST_ITEM_RE",
    "_UNESCAPED_PIPE_RE",
    "_atomic_write_files",
    "_budget_fields",
    "_changelog_filename",
    "_check_drift",
    "_cmd_write",
    "_continuation_wrapper",
    "_escape_cell",
    "_extract_fields",
    "_file_summary",
    "_footer_line",
    "_format_check_report",
    "_generated_index_file_pattern",
    "_generated_line",
    "_hub_filename",
    "_hub_leaf_entries",
    "_id_range",
    "_index_naming",
    "_is_numeric_score",
    "_iter_item_files",
    "_list_disk_generated_files",
    "_measure",
    "_normalize_id_text",
    "_parse_list_field",
    "_print_file_report",
    "_read_disk_table",
    "_read_frontmatter_map",
    "_reciprocal_anomalies",
    "_relative_file_path",
    "_relative_link",
    "_render_blocks_cell",
    "_render_file_cell",
    "_run_report_pipeline",
    "_scan_one_file",
    "_shard_filename",
    "_shipped_bytes",
    "_strip_quotes",
    "build_blocks_index",
    "build_hub_files",
    "build_index_files",
    "build_shard_files",
    "compute_scores_for_items",
    "detect_line_ending",
    "detect_reciprocal_edges",
    "estimate_tokens",
    "exit_code_for",
    "get_scoring_weights",
    "hub_wrapper_tokens",
    "is_generated_index_file",
    "is_open_item",
    "main",
    "os",
    "partition_items",
    "render_header",
    "render_row",
    "render_separator",
    "render_shards_section",
    "render_table_body",
    "scan_backlog",
    "shard_for",
    "split_items_to_budget",
    "truncate_title",
    "validate_blocks_resolve",
]


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
