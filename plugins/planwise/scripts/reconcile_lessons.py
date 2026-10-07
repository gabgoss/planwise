#!/usr/bin/env python3
"""Detect and reconcile lessons-index "Next available ID" counter drift.

The lessons index carries a `**Next available ID:** LL-{NNN}` line that is a
denormalized cache of one fact: the highest lesson ID that exists anywhere. It
has exactly one writer — capture mode, which bumps it after writing a lesson.
Every other route that creates a lesson (a hand-authored closeout capture, a
task-runner producing one as a sprint deliverable) leaves it untouched, and no
read path reconciles it. The curate workflow *reads* the line as a sanity
boundary, so a stale counter is consumed as authoritative by the very workflow
best positioned to notice. The next capture then reads a value below the true
max and either reuses an existing ID or forces a manual fix.

This module is the single, testable source of that drift logic so multiple
callers (`doctor`, `lessons curate`, `lessons capture`) detect it the same way
instead of each re-deriving the comparison — the lessons-index analogue of
`reconcile_plans.py` (plans index) and `reconcile_backlog.py` (backlog index).

The invariant: the stated counter equals `max(LL-NNN across the working lessons
directory, `Archive/`, and the index Master Table) + 1`, or `LL-001` when no
lesson exists anywhere. All three sources are unioned — a lesson archived at
capture is absent from the working directory, and a Master-Table row can outlive
a deleted file, so no single source is authoritative alone.

Three operations:
  - compute_next_id(config): read-only. Returns the true next ID plus the
    per-source breakdown behind it. Delegates to `parse_lessons.compute_next_id`.
  - detect_drift(config): read-only. Reports a counter that is BEHIND the true
    next ID as drift, and reports five separate conditions as anomalies — a
    missing counter line, a counter AHEAD of the true next ID, a Master-Table
    row whose file exists in neither directory, a lesson file on disk with
    no Master-Table row, and a lesson id claimed by more than one file on disk.
  - reconcile(config): re-reads the index fresh (race-safe against a concurrent
    writer that may have bumped the counter since a prior detect call) and
    rewrites the counter line's value only when it is still behind and the
    index is a legacy Master Table; a generated index is never edited here.

The ID-cell regex (`MASTER_ROW_RE`) and the lesson-filename regex
(`LESSON_FILE_RE`) are defined once, in `parse_lessons.py`, and imported here
rather than carried as a near-duplicate.

> The counter only ever moves FORWARD. A counter *ahead* of the true max is
  reported as an anomaly and never lowered: an ID can be retired deliberately
  (a lesson deleted along with its row), and reusing a retired ID would break
  every cross-reference that still names it. Likewise, an anomaly is never
  healed — a Master-Table row with no file, or a file with no row, needs a human
  to decide which side is right, and fabricating either would invent content.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from parse_lessons import (
    LESSON_FILE_RE,
    LESSON_ROW_RE,
    detect_index_shape,
    duplicate_ids,
    format_id,
    lesson_files,
    parse_index,
    parse_legacy_master_table,
)
from parse_lessons import compute_next_id as _parse_lessons_compute_next_id

# Re-exported for backward-compatible external access (a caller or test that
# still reads reconcile_lessons.LESSON_FILE_RE) even though this module no
# longer uses it directly — the definition lives once, in parse_lessons.py.
__all__ = [
    "LESSON_FILE_RE",
    "MASTER_ROW_RE",
    "compute_next_id",
    "detect_drift",
    "reconcile",
]

# Import-bound alias — the single ID-cell regex is defined once, in
# parse_lessons.py; this module never carries its own near-duplicate.
MASTER_ROW_RE = LESSON_ROW_RE

# The counter line. Group 1 is everything up to the digits and is preserved
# verbatim on write; only the digits are replaced, so the line's original
# trailing whitespace and line ending survive untouched.
COUNTER_RE = re.compile(
    r"^([ \t]*(?:\*\*)?Next available ID:(?:\*\*)?[ \t]*)LL-(\d+)", re.MULTILINE
)


def _dir_lesson_ids(directory: Path | None) -> dict:
    """Map {int id: filename} for `LL-NNN*.md` files directly in `directory`.

    Thin wrapper over `parse_lessons.lesson_files`, kept dict-shaped
    (first-seen-wins) because every existing caller reads this as a lookup
    table. A duplicate id within `directory` is NOT reported here: the
    whole on-disk corpus (working directory plus `Archive/` together) is
    checked independently in `_sources`/`detect_drift`, which report it as
    the `duplicate_id` anomaly (count rows before keying, never collapse
    into one entry). A missing directory (no `Archive/` yet on a young
    project) yields {}.
    """
    found: dict[int, str] = {}
    if directory is None:
        return found
    for lesson_id, path in lesson_files(directory, None):
        found.setdefault(lesson_id, path.name)
    return found


def _master_table_ids(config: dict, content: str) -> set:
    """Extract every lesson ID the on-disk index carries as a row, shape-aware.

    On a `legacy` index, delegates to `parse_lessons.parse_legacy_master_table`,
    scoped to the `## Master Table` heading region so a row in another table
    that happens to lead with a lesson ID (the Rule Promotion Log) is never
    read as a Master-Table entry.

    On a `generated` index, the rows live across the whole generated family
    (hub, overflow leaves, Archive shards), not in a `## Master Table`
    heading the generator never writes — reading only `content` (the hub
    file alone) would therefore see zero rows and every lesson would read as
    `file_without_row`. Delegates instead to `parse_lessons.parse_index`,
    which already walks the whole family.

    On an `empty` index (no lessons yet, or an unrecognized file), no shape
    has a row set to read, so this returns the empty set.
    """
    # `row.id != -1` alone in both branches, matching `compute_next_id`:
    # a malformed row whose id cell WAS parseable (a cell-count mismatch,
    # not a missing id) still claims that id for allocation purposes.
    shape = detect_index_shape(content)
    if shape == "generated":
        parsed = parse_index(config)
        return {row.id for row in parsed.rows if row.id != -1}
    if shape == "legacy":
        rows = parse_legacy_master_table(content)
        return {row.id for row in rows if row.id != -1}
    return set()


def _sources(config: dict) -> dict:
    """Read the three ID sources. Returns working/archive/master + the index
    text, plus the on-disk duplicate-id map (a lesson id claimed by more
    than one file, working directory and `Archive/` combined)."""
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")
    archive_dir = (lessons_dir / "Archive") if lessons_dir else None

    content = index_path.read_text(encoding="utf-8") if index_path and index_path.exists() else ""

    working_pairs = lesson_files(lessons_dir, None)
    archive_pairs = lesson_files(None, archive_dir)
    dup_on_disk = duplicate_ids(working_pairs + archive_pairs)

    return {
        "working": _dir_lesson_ids(lessons_dir),
        "archive": _dir_lesson_ids(archive_dir),
        "master": _master_table_ids(config, content),
        "content": content,
        "duplicates_on_disk": dup_on_disk,
    }


def compute_next_id(config: dict) -> dict:
    """Compute the true next lesson ID from the union of every known source.

    Delegates to `parse_lessons.compute_next_id` — the union-of-sources
    derivation is defined once there. Read-only. Returns:
        {"next": int, "next_id": "LL-NNN", "max_found": int | None,
         "found_in": [source names carrying that max],
         "counts": {"working": N, "archive": N, "master": N, "generated": N}}
    `max_found` is None and `next` is 1 on a fresh project with no lessons
    anywhere — the seed index's starting `LL-001` is then correct, not drifted.
    """
    return _parse_lessons_compute_next_id(config)


def detect_drift(config: dict) -> dict:
    """Compare the stated counter against the true next ID; collect anomalies.

    Read-only. Never writes. Returns:
        {"drifts": [{"field", "stated", "expected", "max_found", "found_in",
                     "reason"}],
         "anomalies": [{"kind", "id", "file", "reason"}, ...],
         "next_id": "LL-NNN"}
    `drifts` holds at most one entry — the counter is a single field — but stays
    a list so the JSON shape matches the plans/backlog reconcilers every caller
    already reads. Only a counter that is BEHIND the true next ID is drift; a
    counter ahead of it is an anomaly (see the module docstring). `anomalies`
    also reports a missing counter line, a Master-Table row whose file exists
    in neither directory, a lesson file on disk with no Master-Table row, and
    a lesson id claimed by more than one file on disk (`duplicate_id`).
    """
    src = _sources(config)
    working, archive, master = set(src["working"]), set(src["archive"]), src["master"]
    computed = compute_next_id(config)
    expected = computed["next"]

    drifts = []
    anomalies = []

    # --- The counter itself -------------------------------------------------
    match = COUNTER_RE.search(src["content"])
    if match is None:
        anomalies.append(
            {
                "kind": "missing_counter_line",
                "id": None,
                "file": None,
                "reason": (
                    "index has no 'Next available ID:' line — nothing to reconcile "
                    f"against; the true next ID is {computed['next_id']}"
                ),
            }
        )
    else:
        stated = int(match.group(2))
        if stated < expected:
            drifts.append(
                {
                    "field": "next_available_id",
                    "stated": format_id(stated),
                    "expected": computed["next_id"],
                    "max_found": (
                        format_id(computed["max_found"])
                        if computed["max_found"] is not None
                        else None
                    ),
                    "found_in": computed["found_in"],
                    "reason": (
                        "counter is behind the highest lesson ID found "
                        f"({format_id(computed['max_found'])} in "
                        f"{', '.join(computed['found_in'])}) — a lesson was authored "
                        "outside capture mode"
                    ),
                }
            )
        elif stated > expected:
            anomalies.append(
                {
                    "kind": "counter_ahead",
                    "id": format_id(stated),
                    "file": None,
                    "reason": (
                        f"counter is ahead of the true next ID ({computed['next_id']}) "
                        "— an ID may have been retired; never lowered automatically"
                    ),
                }
            )

    # --- Cross-source consistency ------------------------------------------
    on_disk = working | archive
    for lesson_id in sorted(master - on_disk):
        anomalies.append(
            {
                "kind": "row_without_file",
                "id": format_id(lesson_id),
                "file": None,
                "reason": "master-table row has no lesson file in the lessons dir or Archive/",
            }
        )
    for lesson_id in sorted(on_disk - master):
        anomalies.append(
            {
                "kind": "file_without_row",
                "id": format_id(lesson_id),
                "file": src["working"].get(lesson_id) or src["archive"].get(lesson_id),
                "reason": "lesson file on disk has no master-table row",
            }
        )

    # --- Duplicate ids on disk -----------------------------------------------
    # Count rows before keying: a lesson id claimed by more than one file is
    # reported by id, with every path — never last-wins, never collapsed into
    # one entry.
    for lesson_id in sorted(src["duplicates_on_disk"]):
        paths = src["duplicates_on_disk"][lesson_id]
        anomalies.append(
            {
                "kind": "duplicate_id",
                "id": format_id(lesson_id),
                "file": ", ".join(p.name for p in paths),
                "reason": f"{len(paths)} lesson files claim {format_id(lesson_id)} — reported by id, never last-wins",
            }
        )

    return {"drifts": drifts, "anomalies": anomalies, "next_id": computed["next_id"]}


def reconcile(config: dict) -> dict:
    """Re-read the index and bump the counter only if it is still behind.

    Race-safe: reads the index fresh from disk and recomputes the true next ID
    against that just-read copy rather than trusting a previously computed
    result, so a counter already bumped by a concurrent capture between detect
    and write is read as non-drifted and left untouched.

    Only the counter line's digits are rewritten; the label, its surrounding
    whitespace, every other line, and the file's original line endings are
    preserved (read/write with newline="" so a CRLF index round-trips
    untranslated, matching the plans/backlog reconcilers' destructive-write
    discipline). Anomalies are never healed and the counter never moves
    backwards.

    Returns {"written": bool, "from": "LL-NNN" | None, "to": "LL-NNN" | None}.
    (The sibling reconcilers return a row count; a single-field counter has no
    meaningful count, so the before/after values are returned instead.)

    Shape-aware: when the on-disk index is a legacy Master Table, the
    forward-only counter heal above is unchanged. When the index is a
    generated file, the counter line is written by the generator on its next
    run, so this function edits nothing and instead returns the regenerate
    command as the generic condition — never a plan schedule.
    """
    index_path = config.get("_lessons_index")
    if index_path is None or not index_path.exists():
        return {"written": False, "from": None, "to": None}

    with open(index_path, "r", encoding="utf-8", newline="") as fh:
        content = fh.read()

    if detect_index_shape(content) == "generated":
        return {
            "written": False,
            "from": None,
            "to": None,
            "regenerate_command": (
                "the index is generated; nothing to edit here — run "
                "generate_lessons_index.py --config <config> --write to refresh it"
            ),
        }

    expected = compute_next_id(config)["next"]
    match = COUNTER_RE.search(content)
    if match is None:
        return {"written": False, "from": None, "to": None}

    stated = int(match.group(2))
    if stated >= expected:
        return {"written": False, "from": format_id(stated), "to": format_id(stated)}

    start, end = match.span()
    updated = content[:start] + match.group(1) + format_id(expected) + content[end:]

    with open(index_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(updated)

    return {"written": True, "from": format_id(stated), "to": format_id(expected)}


def _format_report(result: dict) -> str:
    """Render a human-readable drift + anomaly report."""
    drifts = result["drifts"]
    anomalies = result["anomalies"]
    lines = []

    if not drifts and not anomalies:
        return (
            "No counter drift detected. The lessons index 'Next available ID' "
            f"matches the highest lesson ID on disk and in the master table "
            f"({result['next_id']})."
        )

    if drifts:
        lines.append("Counter drift detected (lessons index 'Next available ID' is stale):")
        for d in drifts:
            lines.append(f"  - stated {d['stated']} — expected {d['expected']}: {d['reason']}")
    else:
        lines.append("No counter drift detected.")

    if anomalies:
        lines.append("")
        lines.append(f"Anomalies ({len(anomalies)}):")
        for a in anomalies:
            label = a["id"] or "index"
            suffix = f" [{a['file']}]" if a.get("file") else ""
            lines.append(f"  - {label}{suffix} — {a['reason']}")

    return "\n".join(lines)


def _write_json(result: dict) -> str:
    """Write the detect result to a JSON temp file and return its path."""
    tmp_dir = tempfile.mkdtemp(prefix="reconcile-lessons-")
    json_path = os.path.join(tmp_dir, "drift.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return json_path


def main():
    parser = argparse.ArgumentParser(
        description="Detect and reconcile lessons-index 'Next available ID' counter drift."
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml; overrides default config search.")
    parser.add_argument("--write", action="store_true", help="Bump a stale counter (re-reads the index immediately before writing).")
    parser.add_argument("--json", action="store_true", help="Additionally write a JSON temp file and print its path.")
    parser.add_argument("--next-id", action="store_true", help="Print the true next lesson ID (computed from the union of all sources, NOT read from the counter line) and exit.")

    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    lessons_dir = config.get("_lessons_dir")
    index_path = config.get("_lessons_index")

    if lessons_dir is None or index_path is None:
        print(
            "Error: config.yaml declares no project.lessons_dir — nothing to reconcile.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not index_path.exists():
        print(f"Error: Lessons index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    if args.next_id:
        print(compute_next_id(config)["next_id"])
        return

    if args.write:
        outcome = reconcile(config)
        if outcome["written"]:
            print(f"Reconciled the counter: {outcome['from']} → {outcome['to']}.")
        elif outcome.get("regenerate_command"):
            print(outcome["regenerate_command"])
        else:
            print("Nothing to reconcile — the counter is not behind.")
        if args.json:
            print(f"JSON: {_write_json(detect_drift(config))}")
        return

    result = detect_drift(config)
    print(_format_report(result))

    if args.json:
        print(f"JSON: {_write_json(result)}")


if __name__ == "__main__":
    main()
