#!/usr/bin/env python3
"""Detect and reconcile backlog archival drift, read from the item files.

The backlog index is a build artifact. `generate_backlog_index.py --write`
renders every row, and every row's File link, from the item files on disk.
The one fact the generator cannot fix is where an item file sits: it renders
the link from the file's current location. So the invariant this module
audits is a property of the item files alone:

    a COMPLETE/CLOSED item file must live in `Archive/`.

An item can reach COMPLETE/CLOSED outside `update_backlog.py --status` (a
session closeout that hand-edits the frontmatter, or a direct write). Its file
then stays in the top-level backlog dir, and the next regeneration renders a
correct row that points at the wrong place. This module detects that case and,
on request, moves the file.

The audit reads item files and never an index. It therefore works the same on
a generated index (where closed items render only into Archive shards, never
the hub) and on a legacy hand-maintained index. A legacy index's stale links
are the migrator's concern, not this tool's.

Two operations:
  - detect_drift(config): read-only. Scans `{backlog_dir}/*.md` and
    `{archive_dir}/*.md` for item files, with the same iterator the generator
    uses, and reads each file's frontmatter `status:` with the generator's
    own frontmatter reader. A COMPLETE/CLOSED item in the backlog dir is
    drift (`needs_move`). Anomalies are reported and never acted on: an open
    item inside `Archive/`, a file with no parseable frontmatter status, two
    files carrying one id, or a closed item whose filename already exists in
    `Archive/`.
  - reconcile(config): re-scans the item files fresh (race-safe against a
    concurrent writer that may have moved a file since a prior detect call)
    and moves each still-drifted file into `Archive/` with
    `update_backlog.archive_item_files`. It never edits or writes any index
    file. It prints the regenerate command so the caller can rebuild the
    index from the new file locations.

A file whose status could not be read is never moved. Detection never writes.
"""

import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader + sibling primitives
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from constants import CLOSED_STATUSES
from generate_backlog_index import (
    GeneratorError,
    _iter_item_files,
    _normalize_id_text,
    _read_frontmatter_map,
    _strip_quotes,
)
from reconcile_common import format_drift_report, run_reconcile_cli
from update_backlog import archive_item_files


def _read_item(path: Path) -> tuple[str | None, str | None]:
    """Return (id, status) from one item file's frontmatter.

    Uses the generator's own reader, so the audit sees the status exactly as
    the generator renders it. Either value is None when it cannot be read.
    A non-numeric id is kept as its raw text so a duplicate check still sees it.
    """
    try:
        fm_map = _read_frontmatter_map(path)
    except (GeneratorError, OSError, UnicodeDecodeError):
        return None, None

    status = _strip_quotes(fm_map.get("status", "").strip()) or None

    raw_id = fm_map.get("id", "")
    try:
        item_id = _normalize_id_text(raw_id)
    except GeneratorError:
        item_id = _strip_quotes(raw_id.strip()) or None
    return item_id, status


def _same_dir(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def detect_drift(config: dict) -> dict:
    """Compare each item file's frontmatter status against its location.

    Read-only. Never writes, and never reads an index. Returns:
        {"drifts": [{"id", "status", "file", "reason", "needs_move"}, ...],
         "anomalies": [{"id", "status", "file", "reason"}, ...]}
    `file` is the item file's basename.
    """
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]
    index_path = config["_index_path"]

    scanned = []
    anomalies = []
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        in_archive = archive_dir.exists() and _same_dir(path.parent, archive_dir)
        item_id, status = _read_item(path)
        if status is None:
            anomalies.append(
                {
                    "id": item_id or "?",
                    "status": "?",
                    "file": path.name,
                    "reason": "no parseable frontmatter status — never moved",
                }
            )
            continue
        scanned.append(
            {"id": item_id, "status": status, "path": path, "in_archive": in_archive}
        )

    # Two files carrying one id: which one is the item is a human decision.
    # Neither file is moved.
    paths_by_id: dict = {}
    for item in scanned:
        if item["id"] is not None:
            paths_by_id.setdefault(item["id"], []).append(item)
    ambiguous = {item_id for item_id, group in paths_by_id.items() if len(group) > 1}

    drifts = []
    for item in scanned:
        path = item["path"]
        base = {"id": item["id"] or "?", "status": item["status"], "file": path.name}

        if item["id"] in ambiguous:
            others = [
                p["path"].name for p in paths_by_id[item["id"]] if p["path"] != path
            ]
            anomalies.append(
                {**base, "reason": f"id also carried by {', '.join(others)} — never moved"}
            )
            continue

        closed = item["status"].upper() in CLOSED_STATUSES
        if closed and not item["in_archive"]:
            if (archive_dir / path.name).exists():
                anomalies.append(
                    {
                        **base,
                        "reason": "a file of the same name already exists in "
                        "Archive/ — never moved",
                    }
                )
                continue
            drifts.append(
                {**base, "reason": "closed item file not in Archive/", "needs_move": True}
            )
        elif not closed and item["in_archive"]:
            anomalies.append(
                {**base, "reason": "open item file inside Archive/ — never moved"}
            )

    return {"drifts": drifts, "anomalies": anomalies}


def reconcile(config: dict) -> int:
    """Re-scan the item files and move only those still drifted.

    Race-safe: recomputes drift from the files on disk rather than trusting an
    earlier detect result, so a file a concurrent writer already moved is left
    alone. Anomalies are never acted on. Each move goes through
    `archive_item_files`, whose per-file result is reported as-is, so a failed
    move is printed as a failure and not counted.

    Never edits or writes any index file. When a file moved, prints the
    regenerate command, since the index still links to the old location
    until the generator runs.

    Returns the number of item files moved.
    """
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    result = detect_drift(config)
    to_move = [d["file"] for d in result["drifts"] if d.get("needs_move")]
    if not to_move:
        return 0

    moved = 0
    for filename, success, message in archive_item_files(
        backlog_dir, archive_dir, to_move
    ):
        if success and message == "moved to Archive":
            moved += 1
        prefix = "  +" if success else "  !"
        print(f"{prefix} {filename}: {message}")

    if moved:
        generator = Path(__file__).resolve().parent / "generate_backlog_index.py"
        config_path = config["_planwise_root"] / "config.yaml"
        print(
            "Regenerate the index so its links follow the moved file(s):\n"
            f'  python "{generator}" --config "{config_path}" --write'
        )
    return moved


def _format_report(result: dict) -> str:
    """Render a human-readable drift + anomaly report."""
    return format_drift_report(
        result,
        no_drift_message="No archival drift detected. Every closed backlog item file is in Archive/.",
        no_drift_only_message="No archival drift detected.",
        drift_header=f"Archival drift detected ({len(result['drifts'])} closed item file(s) not in Archive/):",
        drift_line=lambda d: f"  - {d['id']} ({d['status']}): {d['file']} — {d['reason']}",
        anomaly_line=lambda a: f"  - {a['id']} ({a['status']}): {a['file']} — {a['reason']}",
    )


def main():
    run_reconcile_cli(
        description=(
            "Detect and reconcile backlog archival drift: a COMPLETE/CLOSED item "
            "file outside Archive/. Reads item files, never an index. --write "
            "moves files only and never writes an index."
        ),
        load_config=lambda: load_config(Path(__file__)),
        resolve_index_path=lambda config: config["_index_path"],
        missing_index_message=lambda index_path: f"Error: Backlog index not found at {index_path}",
        detect_drift=detect_drift,
        reconcile=reconcile,
        format_report=_format_report,
        json_prefix="reconcile-backlog-",
        write_message=lambda n: f"Moved {n} file(s) to Archive/.",
    )


if __name__ == "__main__":
    main()
