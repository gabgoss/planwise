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

## Module map

This file is a facade: the code lives in ten sibling modules, and every name
they define that other code imports is re-exported through `__all__`, so an importer of
`generate_lessons_index` sees one flat namespace. `lessons_index_schema` holds
the column layout, required keys, and `LessonsGeneratorError`.
`lessons_index_scan` holds frontmatter extraction and `scan_lessons`.
`lessons_index_render` holds row, header, and table-body rendering.
`lessons_index_budget` holds hub and shard partition and the token-budget
splitter. `lessons_index_legacy` holds the legacy-index predicate.
`lessons_index_build` holds hub, leaf, and shard file assembly.
`lessons_index_drift` holds the `--check` comparison.
`lessons_index_run` holds exit-code mapping, report printers, and the report
and write pipelines. `lessons_index_companion` holds categorization and
companion rendering. `lessons_index_companion_drift` holds the companion
shape parse, drift check, and integrity scan. Only the companion CLI entry
point, its helpers, and `main` stay in this file.

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows consoles default stdout to cp1252, which cannot encode the em
# dashes and curly quotes several lesson titles carry.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config_loader import load_config
from generate_backlog_index import (
    HUB_TOKEN_BUDGET,
    MEASUREMENT_BASIS,
    _atomic_write_files,
    _budget_fields,
    _changelog_filename,
    _index_naming,
    _measure,
    _shipped_bytes,
    is_generated_index_file,
    render_shards_section,
    truncate_title,
)
from lessons_index_budget import (
    detect_location_anomalies,
    is_hub_lesson,
    partition_lessons,
    shard_for,
    split_lessons_to_budget,
)
from lessons_index_build import (
    _hub_continuation_wrapper,
    build_lessons_hub_files,
    build_lessons_index_files,
    build_lessons_shard_files,
    hub_wrapper_tokens,
)
from lessons_index_companion import (
    _COMPANION_ANY_HEADING_RE,
    _COMPANION_GENERATED_RE,
    _COMPANION_HEADING_RE,
    _COMPANION_ID_CELL_RE,
    _COMPANION_LEGACY_HEADING_RE,
    _COMPANION_LEGACY_LAST_UPDATED_RE,
    _COMPANION_TO_RE,
    _FENCE_RE,
    _LANDED_STATUSES,
    _SEVERITY_ORDER,
    COMPANION_FILENAME,
    DEFAULT_CATEGORIZATION,
    NOTES_FILENAME,
    CategorizationError,
    _bucket_matches,
    _companion_path,
    _companion_row,
    _companion_table_header,
    _first_sub_bucket_match,
    _ordered_buckets,
    _render_companion_row,
    _render_companion_table,
    _resolve_categorization,
    _row_sort_key,
    _validate_categorization,
    _validate_id,
    classify_lesson,
    has_categorization_block,
    partition_companion,
    render_companion_body,
    render_companion_file,
    render_companion_footer,
    render_companion_header,
)
from lessons_index_companion_drift import (
    _check_companion_drift,
    _clip,
    _companion_headings_to_drop,
    _companion_line_ending,
    _companion_table_ids,
    _first_difference,
    _fresh_companion_rows,
    _mask_generated,
    _parse_companion_shape,
    _scan_integrity_findings,
    is_generated_companion,
    is_legacy_companion,
)
from lessons_index_drift import (
    _ANOMALY_CLASSES,
    _COUNTER_LINE_RE,
    _check_lessons_drift,
    _counter_floor,
    _format_lessons_check_report,
    _split_findings,
    _wrapper_text,
)
from lessons_index_legacy import (
    _LEGACY_HEADING_FENCE_RE,
    _LEGACY_HEADING_RE,
    _legacy_headings_to_drop,
    is_legacy_index,
)
from lessons_index_render import (
    _PROMOTION_LOG_HUB_RE,
    _footer_line,
    _promotion_log_filename,
    _render_file_cell,
    _render_lessons_table_body,
    render_counter_line,
    render_header,
    render_header_block,
    render_row,
    render_separator,
)
from lessons_index_run import (
    _WRITE_REFUSAL_CLASSES,
    LessonsDisposition,
    _cmd_write_lessons,
    _file_summary,
    _print_file_report,
    _print_truncation_summary,
    _run_lessons_report_pipeline,
    lessons_exit_code_for,
)
from lessons_index_scan import (
    _ID_VALUE_RE,
    _LIST_ITEM_RE,
    _TRAILING_COMMENT_RE,
    LessonScanResult,
    _check_id_mismatch,
    _extract_fields,
    _find_closing_quote,
    _iter_lesson_files,
    _normalize_id_text,
    _parse_list_field,
    _read_frontmatter_map,
    _split_flow_list_items,
    _strip_comment_from_line,
    _strip_inline_comment,
    _strip_quotes,
    _unescape_double_quoted,
    scan_lessons,
)
from lessons_index_schema import (
    _DEFAULT_LESSON_STATUSES,
    COL_CATEGORY,
    COL_DOMAIN,
    COL_FILE,
    COL_ID,
    COL_LANGUAGE,
    COL_SEVERITY,
    COL_SOURCE,
    COL_STATUS,
    COL_TECHNOLOGY,
    COL_TITLE,
    COLUMN_COUNT,
    HEADER_CELLS,
    HUB_STATUSES,
    REQUIRED_KEYS,
    LessonsGeneratorError,
    _resolve_valid_statuses,
)
from markdown_parser import split_row_cells
from parse_lessons import format_id
from read_limits import READ_TOKEN_WARN, estimate_tokens
from reconcile_common import read_text_preserving_newlines

__all__ = [
    "COLUMN_COUNT",
    "COL_CATEGORY",
    "COL_DOMAIN",
    "COL_FILE",
    "COL_ID",
    "COL_LANGUAGE",
    "COL_SEVERITY",
    "COL_SOURCE",
    "COL_STATUS",
    "COL_TECHNOLOGY",
    "COL_TITLE",
    "COMPANION_FILENAME",
    "DEFAULT_CATEGORIZATION",
    "HEADER_CELLS",
    "HUB_STATUSES",
    "HUB_TOKEN_BUDGET",
    "NOTES_FILENAME",
    "REQUIRED_KEYS",
    "_ANOMALY_CLASSES",
    "_COMPANION_ANY_HEADING_RE",
    "_COMPANION_GENERATED_RE",
    "_COMPANION_HEADING_RE",
    "_COMPANION_ID_CELL_RE",
    "_COMPANION_LEGACY_HEADING_RE",
    "_COMPANION_LEGACY_LAST_UPDATED_RE",
    "_COMPANION_TO_RE",
    "_COUNTER_LINE_RE",
    "_DEFAULT_LESSON_STATUSES",
    "_FENCE_RE",
    "_ID_VALUE_RE",
    "_LANDED_STATUSES",
    "_LEGACY_HEADING_FENCE_RE",
    "_LEGACY_HEADING_RE",
    "_LIST_ITEM_RE",
    "_PROMOTION_LOG_HUB_RE",
    "_SEVERITY_ORDER",
    "_TRAILING_COMMENT_RE",
    "_WRITE_REFUSAL_CLASSES",
    "CategorizationError",
    "LessonScanResult",
    "LessonsDisposition",
    "LessonsGeneratorError",
    "_bucket_matches",
    "_changelog_filename",
    "_check_companion_drift",
    "_check_id_mismatch",
    "_check_lessons_drift",
    "_clip",
    "_cmd_write_lessons",
    "_companion_error",
    "_companion_headings_to_drop",
    "_companion_largest_table",
    "_companion_line_ending",
    "_companion_path",
    "_companion_row",
    "_companion_table_header",
    "_companion_table_ids",
    "_counter_floor",
    "_extract_fields",
    "_file_summary",
    "_find_closing_quote",
    "_first_difference",
    "_first_sub_bucket_match",
    "_footer_line",
    "_format_lessons_check_report",
    "_fresh_companion_rows",
    "_hub_continuation_wrapper",
    "_index_naming",
    "_iter_lesson_files",
    "_legacy_headings_to_drop",
    "_mask_generated",
    "_measure",
    "_normalize_id_text",
    "_ordered_buckets",
    "_parse_companion_shape",
    "_parse_list_field",
    "_print_file_report",
    "_print_truncation_summary",
    "_promotion_log_filename",
    "_read_frontmatter_map",
    "_render_companion_row",
    "_render_companion_table",
    "_render_file_cell",
    "_render_lessons_table_body",
    "_resolve_categorization",
    "_resolve_valid_statuses",
    "_row_sort_key",
    "_run_companion_cli",
    "_run_lessons_report_pipeline",
    "_scan_integrity_findings",
    "_shipped_bytes",
    "_split_findings",
    "_split_flow_list_items",
    "_strip_comment_from_line",
    "_strip_inline_comment",
    "_strip_quotes",
    "_unescape_double_quoted",
    "_validate_categorization",
    "_validate_id",
    "_wrapper_text",
    "build_lessons_hub_files",
    "build_lessons_index_files",
    "build_lessons_shard_files",
    "classify_lesson",
    "companion_exit_code_for",
    "detect_location_anomalies",
    "estimate_tokens",
    "has_categorization_block",
    "hub_wrapper_tokens",
    "is_generated_companion",
    "is_generated_index_file",
    "is_hub_lesson",
    "is_legacy_companion",
    "is_legacy_index",
    "lessons_exit_code_for",
    "main",
    "partition_companion",
    "partition_lessons",
    "render_companion_body",
    "render_companion_file",
    "render_companion_footer",
    "render_companion_header",
    "render_counter_line",
    "render_header",
    "render_header_block",
    "render_row",
    "render_separator",
    "render_shards_section",
    "scan_lessons",
    "shard_for",
    "split_lessons_to_budget",
    "split_row_cells",
    "truncate_title",
]


def companion_exit_code_for(findings: list) -> int:
    return LessonsDisposition.DRIFT_OR_ANOMALY if findings else LessonsDisposition.CLEAN


def _companion_largest_table(items: list, cat: dict):
    """(table_id, row_count) for the biggest bucket/sub-bucket table in
    the fresh classification, named in an over-budget write refusal."""
    table = partition_companion(items, cat)
    sizes = []
    for bucket_id, entry in table.items():
        sizes.append((bucket_id, len(entry["parent"])))
        for sub_id, sub_entry in entry["subs"].items():
            sizes.append((sub_id, len(sub_entry["items"])))
    return max(sizes, key=lambda pair: pair[1]) if sizes else (None, 0)


def _companion_error(args, message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    if args.json:
        print(json.dumps({"error": message}, indent=2))
    return LessonsDisposition.REFUSED


def _run_companion_cli(args, lessons_dir: Path, archive_dir: Path, index_path, naming, config: dict) -> int:
    """The `--companion` entry point `main()` dispatches to. Applies the
    same `--dry-run`/`--check`/`--write`/`--json`/`--replace-legacy`
    contract the index uses, targeted at the companion file instead.

    Every refusal exits 2 with an `Error: ...` line on stderr; under
    `--json` it also prints an object carrying an `error` key.
    """
    companion_path = _companion_path(lessons_dir)
    if not has_categorization_block(config):
        print(
            "INFO: config.yaml has no categorization: block; rendering the "
            "companion from the default buckets. Run `init_project.py --migrate` "
            "to add the block to config.yaml.",
            file=sys.stderr,
        )
        config = {**config, "categorization": DEFAULT_CATEGORIZATION}
    try:
        cat = _resolve_categorization(config)
    except LessonsGeneratorError as exc:
        return _companion_error(args, str(exc))

    valid_statuses = _resolve_valid_statuses(config)
    try:
        result = scan_lessons(lessons_dir, archive_dir, index_path, valid_statuses)
    except LessonsGeneratorError as exc:
        return _companion_error(args, str(exc))

    integrity_findings = _scan_integrity_findings(result)
    disk_content = None
    try:
        fresh_content = render_companion_file(result.items, config, naming)
        if companion_path.exists():
            disk_content = read_text_preserving_newlines(companion_path).replace("\r\n", "\n")
            drift_findings = _check_companion_drift(result.items, disk_content, cat, fresh_content)
        else:
            drift_findings = [
                {
                    "class": "missing-row", "id": format_id(item["id"]),
                    "detail": "companion file does not exist yet",
                }
                for item in result.items
            ]
        largest_table = _companion_largest_table(result.items, cat)
    except LessonsGeneratorError as exc:
        return _companion_error(args, str(exc))
    findings = integrity_findings + drift_findings

    num_bytes, tokens = _measure(fresh_content)
    budget_fields = _budget_fields(num_bytes, tokens, READ_TOKEN_WARN)
    over_budget = tokens > READ_TOKEN_WARN

    if args.write:
        if integrity_findings:
            for f in integrity_findings:
                print(f"Anomaly: [{f['class']}] {f['id']}: {f['detail']}. Refusing to write.", file=sys.stderr)
            return _companion_error(
                args, f"{len(integrity_findings)} lesson-id anomaly(ies); fix the lesson "
                "files, then re-run --write.",
            )
        if over_budget:
            table_id, row_count = largest_table
            return _companion_error(
                args, f"companion projects {tokens} tokens (budget "
                f"{READ_TOKEN_WARN}); largest table {table_id} has "
                f"{row_count} rows. Refusing to write.",
            )
        legacy_present = any(f["class"] == "legacy-shape" for f in drift_findings)
        foreign = bool(disk_content and disk_content.strip()) and (
            legacy_present or not is_generated_companion(disk_content)
        )
        if foreign:
            dropped = _companion_headings_to_drop(disk_content, _companion_table_ids(cat))
            if not args.replace_legacy:
                shape = (
                    "legacy-shaped (a **Last Updated:** line or a ## Cross-cutting "
                    "observations heading)" if legacy_present else
                    "not generated-shaped (its header lacks the Generated: line or "
                    "the **Companion to:** line)"
                )
                if dropped:
                    print("--replace-legacy would drop these sections:", file=sys.stderr)
                    for heading in dropped:
                        print(f"  {heading}", file=sys.stderr)
                return _companion_error(
                    args, f"{companion_path} is {shape}. Refusing to overwrite it; "
                    "re-run with --replace-legacy to replace it.",
                )
            for heading in dropped:
                print(f"dropping: {heading}", file=sys.stderr)

        line_ending = _companion_line_ending(companion_path)
        out_content = fresh_content if line_ending == "\n" else fresh_content.replace("\n", line_ending)
        try:
            _atomic_write_files({companion_path: out_content}, [])
        except OSError as exc:
            path = getattr(exc, "filename", None) or "unknown path"
            print(f"Error: write failed and was rolled back ({path}): {exc}", file=sys.stderr)
            return LessonsDisposition.REFUSED
        if args.json:
            print(json.dumps({"written": [str(companion_path)], "budget": budget_fields}, indent=2))
        else:
            print(f"Wrote {companion_path}.")
        return LessonsDisposition.CLEAN

    code = companion_exit_code_for(findings)
    if args.json:
        payload = {
            "companion": str(companion_path),
            "budget": budget_fields,
            "drift": findings,
        }
        print(json.dumps(payload, indent=2))
        return code

    print(
        f"{companion_path}: {tokens} tokens, budget {READ_TOKEN_WARN}, "
        f"page_cap_ratio {budget_fields['page_cap_ratio']} (basis: {MEASUREMENT_BASIS})"
    )
    print()
    if not findings:
        print("No drift detected. The companion matches lesson frontmatter.")
    else:
        print(f"Drift detected ({len(findings)} finding(s)):")
        for f in findings:
            print(f"  - [{f['class']}] {f['id']}: {f['detail']}")
    return code


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
        "pipeline and reports drift/anomalies. A legacy-shaped hub exits 2: "
        "plain mode prints only the migrate-first error, and --json still "
        "prints the report with its legacy-shape finding. --write refuses "
        "before touching disk on any unresolved condition.",
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
        help="Allow --write to overwrite a legacy-shaped on-disk index after its sections have "
        "been relocated. Prefer migrate_lessons_index.py, which relocates them first.",
    )
    parser.add_argument(
        "--companion", action="store_true",
        help="Target the categorization companion "
        "(00-Categorization-By-Domain.md) instead of the lessons index. "
        "The existing --dry-run/--check/--write/--json/--replace-legacy "
        "flags apply to it exactly as they do to the index.",
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

    if args.companion:
        return _run_companion_cli(args, lessons_dir, archive_dir, index_path, naming, config)

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

    if code == LessonsDisposition.REFUSED:
        print(
            f"Error: {index_path} is a hand-authored lessons index — run /planwise upgrade to "
            "migrate it (the migrator relocates the changelog, the promotion log and the "
            "hand-written sections with backups) before reading it as generated",
            file=sys.stderr,
        )
        if not args.json:
            return code

    if args.json:
        # On a legacy hub this still prints, carrying its `legacy-shape`
        # finding for a JSON reader, and then exits 2.
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
