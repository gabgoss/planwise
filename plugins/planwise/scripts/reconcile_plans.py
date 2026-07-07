#!/usr/bin/env python3
"""Detect and reconcile plans-index status drift against each plan's Master Plan.

The plans index is a denormalized cache: each row's Status column is a copy of
its Master Plan's own `**Status:**` field, written at some earlier point in
time. If a plan's Master Plan is updated without the index being refreshed to
match, the index row goes stale. This module is the single, testable source of
that drift logic so multiple callers (e.g. a listing command and a doctor/
health-check command) can detect and, on request, reconcile the same way
instead of each re-implementing the comparison.

Two operations:
  - detect_drift(config): read-only. Resolves each index row's Master Plan via
    the row's Path column, compares statuses using a normalized "base token"
    (so a gated-completion note suffix does not register as false drift), and
    reports rows whose Master Plan cannot be found as anomalies rather than
    drift.
  - reconcile(config): re-reads the index fresh (race-safe against a
    concurrent writer that may have healed a row since a prior detect call),
    and writes the Status + Last Updated cells of any row still drifted,
    mirroring the Master Plan's own status and last-updated date.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config

_HEADER_RE = re.compile(r"\|\s*Abbrev\s*\|")
_SEPARATOR_RE = re.compile(r"\|[-\s|]+\|")
_STATUS_FIELD_RE = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.MULTILINE)
# The date may be followed by the closing `*` OR an annotation before it
# (e.g. `*Last Updated: 2026-03-19 (Session-02 COMPLETE)*`), so do not require
# the `*` immediately after the date — the fixed-width date group is boundary
# enough. Requiring a trailing `*` here silently drops annotated footers and
# falls back to today.
_LAST_UPDATED_RE = re.compile(r"^\*Last Updated:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _plans_index_path(config: dict) -> Path:
    """Resolve the plans index file path from config.

    Reuses config_loader's resolved `_plans_dir` and reads
    `project.index_files.plans` for the filename (default: 00-Index-Plans.md).
    """
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    index_files = project.get("index_files", {}) if isinstance(project.get("index_files"), dict) else {}
    filename = index_files.get("plans", "00-Index-Plans.md")
    return config["_plans_dir"] / filename


def _master_plan_filename(abbrev: str, meta: bool = False) -> str:
    """Build the Master Plan filename for a plan.

    Regular execution plans name their Master Plan `{Abbrev}-Master-Plan.md`;
    Discovery/Meta plans name theirs `{Abbrev}-META-Master-Plan.md`.
    """
    return f"{abbrev}-META-Master-Plan.md" if meta else f"{abbrev}-Master-Plan.md"


def _is_meta_row(row: dict) -> bool:
    """True when a Plans-index row's Path marks it a Discovery/Meta plan.

    Discovery/Meta plans live under a `Meta-{Abbrev}/` directory (the final
    non-empty Path segment starts with `Meta-`) and name their Master Plan
    `{Abbrev}-META-Master-Plan.md` rather than `{Abbrev}-Master-Plan.md`. This
    marker gates the `-META-` resolution fallback so a genuinely-missing
    regular Master Plan still reports as an anomaly instead of silently probing
    a second filename.
    """
    segments = [s for s in row.get("path", "").split("/") if s]
    return bool(segments) and segments[-1].startswith("Meta-")


def _relative_master_plan_path(config: dict, row: dict) -> str:
    """Build a project-relative display path for anomaly reporting.

    Uses the raw (unresolved) project.plans_dir string rather than the
    absolute filesystem path, so reports stay portable across machines. Names
    the `-META-` convention for Meta-marked rows so a genuinely-missing
    Discovery/Meta Master Plan reports the filename it should actually have.
    """
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    plans_rel = project.get("plans_dir", "Plans")
    filename = _master_plan_filename(row["abbrev"], meta=_is_meta_row(row))
    return f"{plans_rel}/{row['path']}{filename}"


def resolve_master_plan_path(config: dict, row: dict) -> Path:
    """Resolve a Plans-index row's Master Plan file path (absolute, for file I/O).

    Joins the resolved plans directory with the row's Path column (which
    already ends in `/` and may nest) and the Master Plan filename. Tries the
    regular `{Abbrev}-Master-Plan.md` first; when that file does not exist AND
    the row's Path marks it a Discovery/Meta plan, falls back to the
    `{Abbrev}-META-Master-Plan.md` convention those plans use. A genuinely-
    missing regular Master Plan (Path not Meta-marked) returns the primary
    path, which the caller reports as an anomaly.
    """
    plan_dir = config["_plans_dir"] / row["path"]
    primary = plan_dir / _master_plan_filename(row["abbrev"])
    if not primary.exists() and _is_meta_row(row):
        meta_path = plan_dir / _master_plan_filename(row["abbrev"], meta=True)
        if meta_path.exists():
            return meta_path
    return primary


def parse_plans_index(content: str) -> list[dict]:
    """Parse the Plans index markdown table into a list of row dicts.

    The table's header starts with an Abbrev column (not ID), so the generic
    shared table parser's ID-column header detection does not apply here;
    this parses the pipe table directly, mirroring its cell-splitting style.

    Returns dicts with keys: abbrev, name, status, created, last_updated,
    path, line_number (index into content.split("\\n"), used by reconcile()
    to edit the row's cells in place).
    """
    lines = content.split("\n")

    header_idx = None
    for i, line in enumerate(lines):
        if _HEADER_RE.match(line.strip()):
            header_idx = i
            break
    if header_idx is None:
        return []

    separator_idx = header_idx + 1
    if separator_idx >= len(lines) or not _SEPARATOR_RE.match(lines[separator_idx].strip()):
        return []

    rows = []
    for i in range(separator_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 6:
            continue
        abbrev = cells[0]
        if not abbrev or re.match(r"^-+$", abbrev):
            continue
        rows.append(
            {
                "abbrev": abbrev,
                "name": cells[1],
                "status": cells[2],
                "created": cells[3],
                "last_updated": cells[4],
                "path": cells[5],
                "line_number": i,
            }
        )
    return rows


def base_token(status: str) -> str:
    """Normalize a status string to its comparison token.

    The base token is the first whitespace-delimited word, uppercased, with
    any wrapping markdown emphasis (`**`, `*`, `__`) stripped. A trailing note
    suffix (e.g. " -- awaiting user action" or " - some note") is naturally
    excluded since it is separated from the token by whitespace.
    Example: "IN_PROGRESS -- awaiting user transfer" -> "IN_PROGRESS".
    Example: "**COMPLETE** (2026-01-01) -- shipped" -> "COMPLETE".
    """
    stripped = status.strip() if status else ""
    if not stripped:
        return ""
    token = stripped.split()[0].upper()
    return token.strip("*_")


def read_master_plan_status(mp_path: Path) -> tuple[str | None, str | None]:
    """Read a Master Plan's Status field and Last Updated footer date.

    Returns (status, last_updated) — either may be None if the file has no
    parseable field. Does not raise if the file is missing; callers should
    check existence first.
    """
    if not mp_path.exists():
        return None, None
    content = mp_path.read_text(encoding="utf-8")
    status_match = _STATUS_FIELD_RE.search(content)
    status = status_match.group(1).strip() if status_match else None
    date_match = _LAST_UPDATED_RE.search(content)
    last_updated = date_match.group(1) if date_match else None
    return status, last_updated


def _pad_cell(old_cell: str, new_value: str) -> str:
    """Replace a table cell's value while preserving its surrounding whitespace padding."""
    leading = len(old_cell) - len(old_cell.lstrip())
    trailing = len(old_cell) - len(old_cell.rstrip())
    if trailing == 0:
        return " " * leading + new_value
    return " " * leading + new_value + " " * trailing


def _evaluate_row(config: dict, row: dict) -> dict:
    """Evaluate a single Plans-index row against its Master Plan.

    Single source of the detect/reconcile comparison so neither caller
    duplicates it. Returns a dict tagged with kind "drift", "anomaly", or
    "ok", carrying whatever fields that kind needs downstream.
    """
    mp_path = resolve_master_plan_path(config, row)
    if not mp_path.exists():
        return {
            "kind": "anomaly",
            "abbrev": row["abbrev"],
            "reason": "Master Plan not found",
            "expected_path": _relative_master_plan_path(config, row),
        }

    mp_status, mp_last_updated = read_master_plan_status(mp_path)
    if mp_status is None:
        return {
            "kind": "anomaly",
            "abbrev": row["abbrev"],
            "reason": "Master Plan has no Status field",
            "expected_path": _relative_master_plan_path(config, row),
        }

    if base_token(row["status"]) == base_token(mp_status):
        return {"kind": "ok"}

    # The index Status cell holds a single enum token; reconcile writes
    # mp_status back verbatim, and callers render it in a one-line drift
    # banner. Store the NORMALIZED base token, not the raw Master Plan Status
    # line — real Master Plans annotate that line heavily (e.g.
    # "COMPLETE — all 7 sprints done 2026-06-01 (...)", or a markdown-bolded
    # "**COMPLETE**"), and writing the raw string would corrupt the one-token
    # cell (and break any exact-token --active filter that reads it back).
    return {
        "kind": "drift",
        "abbrev": row["abbrev"],
        "index_status": row["status"],
        "mp_status": base_token(mp_status),
        "mp_last_updated": mp_last_updated,
        "path": row["path"],
        "line_number": row["line_number"],
    }


def detect_drift(config: dict) -> dict:
    """Compare each Plans-index row's Status against its Master Plan's Status.

    Read-only. Never writes. Returns:
        {"drifts": [{"abbrev", "index_status", "mp_status", "mp_last_updated",
                     "path"}, ...],
         "anomalies": [{"abbrev", "reason", "expected_path"}, ...]}
    """
    index_path = _plans_index_path(config)
    content = index_path.read_text(encoding="utf-8")
    rows = parse_plans_index(content)

    drifts = []
    anomalies = []
    for row in rows:
        evaluation = _evaluate_row(config, row)
        kind = evaluation["kind"]
        if kind == "drift":
            drifts.append(
                {k: v for k, v in evaluation.items() if k not in ("kind", "line_number")}
            )
        elif kind == "anomaly":
            anomalies.append({k: v for k, v in evaluation.items() if k != "kind"})

    return {"drifts": drifts, "anomalies": anomalies}


def reconcile(config: dict) -> int:
    """Re-read the index and write only rows still drifted against their Master Plan.

    Race-safe: reads the index fresh from disk and recomputes drift against
    that just-read copy rather than trusting a previously computed result, so
    a row healed by a concurrent writer between detect and write is read as
    non-drifted and left untouched. Anomaly rows (missing Master Plan, or a
    Master Plan with no Status field) are never written.

    For each still-drifted row, sets Status to the Master Plan's status
    normalized to its base enum token (so an annotated Master-Plan Status line
    does not corrupt the one-token index cell) and Last Updated by mirroring
    the Master Plan's own `*Last Updated: {YYYY-MM-DD}*` footer date (accepting
    an annotation after the date), falling back to today only when no parseable
    date is found. Every other column, the row's surrounding whitespace
    padding, and the file's original line endings are preserved.

    Returns the number of rows written.
    """
    index_path = _plans_index_path(config)
    # Read with newline="" so the file's original line endings survive into
    # `content` untranslated; splitting on "\n" then leaves a trailing "\r" on
    # each line of a CRLF file, which the "\n".join round-trip restores exactly
    # on write. Without this, universal-newline read + text-mode write would
    # rewrite every line to the platform's os.linesep — a whole-file diff, and
    # a "preserve non-table lines exactly" violation on this destructive path.
    with open(index_path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    rows = parse_plans_index(content)
    lines = content.split("\n")

    written = 0
    for row in rows:
        evaluation = _evaluate_row(config, row)
        if evaluation["kind"] != "drift":
            continue

        new_status = evaluation["mp_status"]
        new_last_updated = evaluation["mp_last_updated"] or date.today().isoformat()

        line = lines[row["line_number"]]
        parts = line.split("|")
        if len(parts) < 7:
            continue
        parts[3] = _pad_cell(parts[3], new_status)
        parts[5] = _pad_cell(parts[5], new_last_updated)
        lines[row["line_number"]] = "|".join(parts)
        written += 1

    if written:
        # newline="" writes the reconstructed text verbatim (no os.linesep
        # translation), preserving the original CRLF/LF exactly.
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))

    return written


def _format_report(result: dict) -> str:
    """Render a human-readable drift + anomaly report."""
    drifts = result["drifts"]
    anomalies = result["anomalies"]
    lines = []

    if not drifts and not anomalies:
        return "No drift detected. All index rows match their Master Plan status."

    if drifts:
        lines.append(f"Drift detected ({len(drifts)} row(s) out of sync with Master Plan status):")
        for d in drifts:
            lines.append(f"  - {d['abbrev']}: index={d['index_status']} -> Master Plan={d['mp_status']}")
    else:
        lines.append("No status drift detected.")

    if anomalies:
        if lines:
            lines.append("")
        lines.append(f"Anomalies ({len(anomalies)}):")
        for a in anomalies:
            lines.append(f"  - {a['abbrev']}: {a['reason']} (expected: {a['expected_path']})")

    return "\n".join(lines)


def _write_json(result: dict) -> str:
    """Write the detect result to a JSON temp file and return its path."""
    tmp_dir = tempfile.mkdtemp(prefix="reconcile-plans-")
    json_path = os.path.join(tmp_dir, "drift.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return json_path


def main():
    parser = argparse.ArgumentParser(
        description="Detect and reconcile plans-index status drift against each plan's Master Plan."
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml; overrides default config search.")
    parser.add_argument("--write", action="store_true", help="Reconcile drifted rows (re-reads the index immediately before writing).")
    parser.add_argument("--json", action="store_true", help="Additionally write a JSON temp file and print its path.")

    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    index_path = _plans_index_path(config)

    if not index_path.exists():
        print(f"Error: Plans index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    if args.write:
        written = reconcile(config)
        print(f"Reconciled {written} row(s).")
        if args.json:
            result = detect_drift(config)
            json_path = _write_json(result)
            print(f"JSON: {json_path}")
        return

    result = detect_drift(config)
    print(_format_report(result))

    if args.json:
        json_path = _write_json(result)
        print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
