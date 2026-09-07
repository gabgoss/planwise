#!/usr/bin/env python3
"""Detect and reconcile backlog-index archival drift.

Archival of a COMPLETE/CLOSED backlog item — moving its file into `Archive/`
and repointing the index link — is a state-coupled step in `update_backlog.py`:
a closed item's file must live under `Archive/` and its index link must point
there. But an item can reach COMPLETE/CLOSED *outside* that script (a session
closeout that hand-edits the index row + frontmatter, or a direct write),
leaving the file stranded in the top-level backlog dir with an index link that
never repointed. Nothing on the read side detects it, so the stranding is
invisible until someone eyeballs the directory.

This module is the single, testable source of that drift logic so multiple
callers (`doctor`, `backlog`) can detect and, on request, reconcile the same
way instead of each re-implementing the comparison — the backlog-index analogue
of `reconcile_plans.py`'s plans-index drift reconcile.

Two operations:
  - detect_drift(config): read-only. For each CLOSED-status row, checks that
    every linked file exists under `Archive/` and that its index link is
    prefixed `Archive/`. Reports rows violating that invariant (file present but
    unarchived, or link not repointed) as drift, and rows whose linked file
    exists in neither location as anomalies (deleted/renamed — reported, never
    fabricated).
  - reconcile(config): re-reads the index fresh (race-safe against a concurrent
    writer that may have healed a row since a prior detect call), moves any
    still-stranded file into `Archive/` and repoints its index link, and never
    touches an anomaly row.

The actual move + link-repoint primitives are reused from `update_backlog.py`
(`archive_item_files`, `update_index_links_to_archive`) so there is one source
of that behavior shared with the `--status`-call idempotent archival path.
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
from parse_backlog import parse_backlog_table
from reconcile_common import (
    format_drift_report,
    read_text_preserving_newlines,
    run_reconcile_cli,
    write_text_preserving_newlines,
)
from update_backlog import archive_item_files, update_index_links_to_archive


def _classify_file(link: str, backlog_dir: Path, archive_dir: Path) -> dict:
    """Classify one linked file of a CLOSED row against the archival invariant.

    Returns a dict with keys: kind ("ok" | "drift" | "anomaly"), file
    (basename), needs_move, needs_relink. `link` is the path exactly as written
    in the index Files column (e.g. "BB-{NNN}-...md" or "Archive/BB-{NNN}-...md").
    """
    basename = link.rsplit("/", 1)[-1]
    in_archive = (archive_dir / basename).exists()
    in_toplevel = (backlog_dir / basename).exists()
    link_archived = link.startswith("Archive/")

    if in_archive and link_archived:
        kind = "ok"
    elif not in_archive and not in_toplevel:
        kind = "anomaly"
    else:
        kind = "drift"

    return {
        "kind": kind,
        "file": basename,
        # Move only when the file is still in the top level and not yet archived.
        "needs_move": in_toplevel and not in_archive,
        "needs_relink": not link_archived,
    }


def detect_drift(config: dict) -> dict:
    """Compare each CLOSED backlog row's file location/link against the invariant.

    Read-only. Never writes. Returns:
        {"drifts": [{"id", "status", "file", "reason", "needs_move",
                     "needs_relink"}, ...],
         "anomalies": [{"id", "status", "file", "reason"}, ...]}
    Only COMPLETE/CLOSED rows are checked — an open item legitimately lives in
    the top-level backlog dir.
    """
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    content = index_path.read_text(encoding="utf-8")
    items = parse_backlog_table(content)

    drifts = []
    anomalies = []
    for item in items:
        if item["status"].upper() not in CLOSED_STATUSES:
            continue
        for f in item["files"]:
            c = _classify_file(f["path"], backlog_dir, archive_dir)
            if c["kind"] == "ok":
                continue
            if c["kind"] == "anomaly":
                anomalies.append(
                    {
                        "id": item["id"],
                        "status": item["status"],
                        "file": c["file"],
                        "reason": "linked file not found in backlog dir or Archive/",
                    }
                )
                continue

            reason_parts = []
            if c["needs_move"]:
                reason_parts.append("file not in Archive/")
            if c["needs_relink"]:
                reason_parts.append("index link not repointed to Archive/")
            drifts.append(
                {
                    "id": item["id"],
                    "status": item["status"],
                    "file": c["file"],
                    "reason": "; ".join(reason_parts),
                    "needs_move": c["needs_move"],
                    "needs_relink": c["needs_relink"],
                }
            )

    return {"drifts": drifts, "anomalies": anomalies}


def reconcile(config: dict) -> int:
    """Re-read the index and heal only rows still drifted against the invariant.

    Race-safe: reads the index fresh from disk and recomputes drift against that
    just-read copy rather than trusting a previously computed result, so a row
    healed by a concurrent writer between detect and write is read as
    non-drifted and left untouched. Anomaly rows (linked file missing entirely)
    are never touched — a deleted/renamed file is not fabricated.

    For each still-drifted row, moves any file still outside `Archive/` into it
    and repoints only the index links whose file was actually confirmed in
    `Archive/` — never an "anomaly" link, whose file exists in neither
    location. The row-wide link rewrite is fed a per-file classification
    rather than re-deriving one: an "ok"/"drift" file starts out recorded
    with the classifier's prediction, then any file handed to
    `archive_item_files` has that prediction OVERLAID with the mover's actual
    per-file result, so a move that raises (permission error, locked file,
    disk full) is reflected as a failure rather than as the optimistic
    prediction that never came true. An anomaly link excluded from
    `move_basenames` stays excluded from the relink too; blanket-prefixing
    either kind onto a link whose file was never actually archived would
    produce a path that can never exist. Every other column, the row's
    surrounding whitespace padding, and the file's original line endings are
    preserved (read/write via reconcile_common's newline="" helpers so a CRLF
    index round-trips untranslated, matching reconcile_plans'
    destructive-write discipline).

    Returns the number of rows (items) reconciled.
    """
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    content = read_text_preserving_newlines(index_path)
    items = parse_backlog_table(content)

    reconciled = 0
    for item in items:
        if item["status"].upper() not in CLOSED_STATUSES:
            continue

        move_basenames = []
        needs_relink = False
        # Per-file (basename -> (success, message)) results shaped like
        # archive_item_files' own return, fed straight into
        # update_index_links_to_archive so its per-link gate sees the same
        # anomaly/drift verdict this loop just computed instead of
        # re-deriving (or losing) it. Values recorded here for a file about
        # to be moved are the classifier's PREDICTION — overlaid below with
        # the mover's ACTUAL result once archive_item_files has run, so a
        # raised exception (permission error, locked file, disk full) is
        # never masked by an optimistic "moved to Archive" that never
        # actually happened.
        link_results: dict[str, tuple[bool, str]] = {}
        for f in item["files"]:
            c = _classify_file(f["path"], backlog_dir, archive_dir)
            if c["kind"] == "anomaly":
                link_results[c["file"]] = (
                    False,
                    "linked file not found in backlog dir or Archive/",
                )
                continue  # never reconciled or relinked
            # "ok" and "drift" both end this pass with the file in Archive/ —
            # "ok" is already there; "drift" either sits there already
            # (relink-only) or is about to be moved there below, pending the
            # mover's actual confirmation.
            link_results[c["file"]] = (
                True,
                "moved to Archive" if c["needs_move"] else "already in Archive",
            )
            if c["kind"] != "drift":
                continue  # "ok" needs nothing further
            if c["needs_move"]:
                move_basenames.append(c["file"])
            if c["needs_relink"]:
                needs_relink = True

        if not move_basenames and not needs_relink:
            continue

        if move_basenames:
            # Overlay the mover's ACTUAL per-file result onto the
            # classifier's prediction — a raised exception must win over the
            # optimistic guess above, or a failed move still gets its link
            # prefixed onto a path that was never actually archived.
            for basename, success, message in archive_item_files(
                backlog_dir, archive_dir, move_basenames
            ):
                link_results[basename] = (success, message)
        if needs_relink:
            content, _, _ = update_index_links_to_archive(
                content,
                item["id"],
                [(name, ok, msg) for name, (ok, msg) in link_results.items()],
            )
        reconciled += 1

    if reconciled:
        write_text_preserving_newlines(index_path, content)

    return reconciled


def _format_report(result: dict) -> str:
    """Render a human-readable drift + anomaly report."""
    return format_drift_report(
        result,
        no_drift_message="No archival drift detected. All closed backlog rows are archived.",
        no_drift_only_message="No archival drift detected.",
        drift_header=f"Archival drift detected ({len(result['drifts'])} closed row(s) whose file is not archived):",
        drift_line=lambda d: f"  - {d['id']} ({d['status']}): {d['file']} — {d['reason']}",
        anomaly_line=lambda a: f"  - {a['id']} ({a['status']}): {a['file']} — {a['reason']}",
    )


def main():
    run_reconcile_cli(
        description="Detect and reconcile backlog-index archival drift (closed rows not archived).",
        load_config=lambda: load_config(Path(__file__)),
        resolve_index_path=lambda config: config["_index_path"],
        missing_index_message=lambda index_path: f"Error: Backlog index not found at {index_path}",
        detect_drift=detect_drift,
        reconcile=reconcile,
        format_report=_format_report,
        json_prefix="reconcile-backlog-",
    )


if __name__ == "__main__":
    main()
