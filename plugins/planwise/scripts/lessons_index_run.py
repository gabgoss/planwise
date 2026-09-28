"""Lessons index generator — exit-code mapping, report printers, and the report and write pipelines."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import (
    TITLE_MAX_LEN,
    _atomic_write_files,
    _list_disk_generated_files,
    detect_line_ending,
)
from lessons_index_budget import detect_location_anomalies
from lessons_index_build import build_lessons_index_files
from lessons_index_companion_drift import _scan_integrity_findings
from lessons_index_drift import _counter_floor
from lessons_index_legacy import _legacy_headings_to_drop, is_legacy_index
from lessons_index_scan import scan_lessons
from lessons_index_schema import LessonsGeneratorError, _resolve_valid_statuses
from parse_lessons import compute_next_id
from reconcile_common import read_text_preserving_newlines

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
    hub without `--replace-legacy`, as REFUSED (2); a report mode (the
    default, `--dry-run`, `--check`) treats a legacy-shaped hub as REFUSED
    too, since a legacy hub cannot be read as generated; every other mode
    (and every other finding) is ordinary DRIFT_OR_ANOMALY (1). A missing
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
    elif any(f["class"] == "legacy-shape" for f in findings):
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

    write_findings = _scan_integrity_findings(result)
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
        if is_legacy and not replace_legacy:
            print(
                f"Run /planwise upgrade to migrate {index_path} first (the migrator relocates the "
                "changelog, the promotion log and the hand-written sections with backups), or pass "
                "--replace-legacy to overwrite it without that migration.",
                file=sys.stderr,
            )
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
