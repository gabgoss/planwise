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
    _read_frontmatter_map,
    _strip_quotes,
)
from reconcile_common import format_drift_report, run_reconcile_cli
from update_backlog import _frontmatter_id, archive_item_files

# Failed-move accounting for the last `reconcile()` call, so `main()` can
# fail the command when a consented move didn't succeed -- without adding a
# failure-signaling hook to `reconcile_common.run_reconcile_cli`, which the
# plans/lessons reconcilers also share and whose `reconcile(config) -> int`
# contract (a plain "rows changed" count, per `write_message`) stays
# unchanged. Reset at the start of every `reconcile()` call.
_last_reconcile_failures: list[tuple[str, str]] = []


def _read_item(path: Path) -> tuple[str | None, str | None, str | None]:
    """Return (display_id, compare_key, status) from one item file's frontmatter.

    Uses the generator's own reader, so the audit sees the status exactly as
    the generator renders it. Any value is None when it cannot be read.

    `display_id` is the frontmatter id's own stored text, quote-stripped and
    trimmed but otherwise UN-normalized -- it is what a human reading the
    report, or a handler/doctor stage parsing `--json`, expects: the same
    zero-padded convention the generator and `--next-id` use everywhere else
    (frontmatter, filenames, the generated index). It is never fed through
    `normalize_id`, which deliberately strips leading zeros for COMPARISON
    and would print "46" where every other surface prints "046".

    `compare_key` is `_frontmatter_id` -- the SAME `normalize_id`-based rule
    `update_backlog.py`'s own disk lookups use -- for EQUALITY ONLY, so a
    file storing "PFX-005" and one storing "005" are still recognized as one
    id for duplicate detection, even though their displayed ids differ.
    """
    try:
        fm_map = _read_frontmatter_map(path)
    except (GeneratorError, OSError, UnicodeDecodeError):
        return None, None, None

    status = _strip_quotes(fm_map.get("status", "").strip()) or None
    raw_id = fm_map.get("id")
    display_id = _strip_quotes(str(raw_id).strip()) or None if raw_id is not None else None
    compare_key = _frontmatter_id(fm_map)
    return display_id, compare_key, status


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
        display_id, compare_key, status = _read_item(path)
        if status is None:
            anomalies.append(
                {
                    "id": display_id or "?",
                    "status": "?",
                    "file": path.name,
                    "reason": "no parseable frontmatter status — never moved",
                }
            )
            continue
        scanned.append(
            {
                "id": display_id,
                "key": compare_key,
                "status": status,
                "path": path,
                "in_archive": in_archive,
            }
        )

    # Two files carrying one id: which one is the item is a human decision.
    # Neither file is moved. Grouped by the NORMALIZED comparison key, not
    # the displayed id, so a "PFX-005" file and a "005" file still collide
    # even though each keeps its own displayed id below.
    paths_by_key: dict = {}
    for item in scanned:
        if item["key"] is not None:
            paths_by_key.setdefault(item["key"], []).append(item)
    ambiguous = {key for key, group in paths_by_key.items() if len(group) > 1}

    drifts = []
    for item in scanned:
        path = item["path"]
        base = {"id": item["id"] or "?", "status": item["status"], "file": path.name}

        if item["key"] in ambiguous:
            others = [
                p["path"].name for p in paths_by_key[item["key"]] if p["path"] != path
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
    `archive_item_files`, whose per-file result is reported as-is; a failed
    move is printed as a failure, not counted, and recorded into
    `_last_reconcile_failures` so `main()` can fail the command for it (the
    return value itself stays a plain "moved" count -- the shared
    `run_reconcile_cli` scaffold's `write_message(n)` contract, which the
    plans/lessons reconcilers also rely on, is unchanged).

    Never edits or writes any index file. When a file moved, prints the
    regenerate command, since the index still links to the old location
    until the generator runs.

    Returns the number of item files moved.
    """
    global _last_reconcile_failures
    _last_reconcile_failures = []

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
        elif not success:
            _last_reconcile_failures.append((filename, message))
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
    # Cleared here too, not only in reconcile(): a detect-mode call (no
    # --write) never calls reconcile() at all, so without this reset a
    # PRIOR invocation's recorded failures (same process, e.g. two --write
    # calls in one test run) would otherwise leak into an unrelated,
    # later, non-writing call and fail it for a move it never attempted.
    global _last_reconcile_failures
    _last_reconcile_failures = []

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

    # `run_reconcile_cli` returns normally (implicit exit 0) whether or not
    # `reconcile()`'s consented moves all succeeded -- it only ever exits
    # non-zero for a missing index. A failed move (OSError, or a refused
    # destination) must fail the command too, so check what `reconcile()`
    # recorded on its way out rather than adding a failure-signaling
    # parameter to the shared scaffold.
    if _last_reconcile_failures:
        print(
            f"Error: {len(_last_reconcile_failures)} move(s) failed:",
            file=sys.stderr,
        )
        for filename, message in _last_reconcile_failures:
            print(f"  {filename}: {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
