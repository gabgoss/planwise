"""Lessons index generator — the --check comparison and its report."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import _list_disk_generated_files
from lessons_index_schema import COL_STATUS, COL_TITLE, COLUMN_COUNT, HEADER_CELLS
from parse_lessons import LESSON_ROW_RE, format_id, parse_generated_table, parse_index
from reconcile_common import read_text_preserving_newlines

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
