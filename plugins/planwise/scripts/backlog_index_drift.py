"""Backlog index drift check: parses on-disk generated tables, compares them
with a fresh render, and formats the `--check` report.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_budget import is_open_item
from backlog_index_disk import _list_disk_generated_files
from backlog_index_render import _relative_file_path
from backlog_index_schema import (
    COL_ID,
    COL_SCORE,
    COLUMN_COUNT,
    IndexNaming,
    _changelog_filename,
    _footer_line,
)
from markdown_parser import is_section_boundary, split_row_cells
from reconcile_common import format_drift_report, read_text_preserving_newlines

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

