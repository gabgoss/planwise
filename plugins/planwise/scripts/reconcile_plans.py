#!/usr/bin/env python3
"""Detect and reconcile plans-index drift against each plan's Master Plan.

The plans index is generated from the Master Plans on disk by
`generate_plans_index.py`. This module is a thin audit over that generator, so
the audit and the writer can never disagree about what a row should say. It
keeps no row parser of its own: the index is read by `parse_plans`, and the
expected rows come from the generator's render.

Two operations:
  - detect_drift(config): read-only. Reads the index on disk, renders the index
    the generator would write, and compares the two by Path. Findings:
    `missing-row` and `stale-row` (one per differing field) go to `drifts`.
    `orphan-row`, `duplicate-row`, `unparsed-rows` and the render's own status
    anomalies go to `anomalies`. A hand-authored (legacy-shaped) index is
    reported as `legacy-shape` and never compared.
  - reconcile(config): re-reads the index fresh (race-safe against a concurrent
    writer), and when the index differs from the render, hands the write to the
    generator. This module never computes a cell.

The audit refuses to report a clean result over a comparison it could not
make. When the index or the tree holds rows and none of them were compared, or
when part of the index could not be parsed, `main` exits 3. A legacy-shaped
index exits 2. A missing index with no Master Plans on disk exits 1.
"""

import argparse
import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from generate_plans_index import (
    diff_index_rows,
    index_matches_render,
    plans_index_path,
    render_plans_index,
    write_plans_index,
)
from parse_plans import (
    detect_index_shape,
    enumerate_master_plans,
    master_plan_path_for,
    normalize_status,
    parse_index_table,
)
from reconcile_common import (
    format_drift_report,
    read_text_preserving_newlines,
    write_json_result,
)

JSON_PREFIX = "reconcile-plans-"

_ROW_CLASSES = ("missing-row", "orphan-row", "stale-row")


class LegacyIndexError(Exception):
    """The on-disk index is hand-authored and must be migrated, not rewritten."""


class WriteRefusedError(Exception):
    """The generator refused the write. The message names the refusal and nothing was written."""


def _legacy_message(index_path: Path) -> str:
    return (
        f"Error: {index_path} is a hand-authored plans index — run /planwise upgrade "
        "to migrate it before auditing it"
    )


def parse_plans_index(content: str) -> list[dict]:
    """Parse the plans index table into a list of row dicts.

    Delegates to `parse_plans.parse_index_table`, which reads past HTML
    comments and blank lines and accepts bare, bold, linked and escaped cells.

    Returns dicts with keys: abbrev, name, status, created, last_updated,
    path, line_number (a 0-based index into content.split("\\n")).
    """
    return [
        {
            "abbrev": row.abbrev,
            "name": row.name,
            "status": row.status_raw,
            "created": row.created,
            "last_updated": row.last_updated,
            "path": row.path,
            "line_number": row.line_number - 1,
        }
        for row in parse_index_table(content).rows
    ]


def base_token(status: str) -> str:
    """Normalize a status string to its leading token, or `""` when it has none.

    Example: "IN_PROGRESS -- awaiting user transfer" -> "IN_PROGRESS".
    Example: "✅ **COMPLETE (2026-01-01) -- shipped" -> "COMPLETE".
    """
    return normalize_status(status) or ""


def resolve_master_plan_path(config: dict, row: dict) -> Path:
    """Resolve an index row's Master Plan file path (absolute, for file I/O).

    A Path whose last segment starts `Meta-` names `{Abbrev}-META-Master-Plan.md`.
    Every other Path names `{Abbrev}-Master-Plan.md`. The caller tests whether
    the returned file exists.
    """
    return master_plan_path_for(config["_plans_dir"], row["path"], row["abbrev"])


def _display_path(config: dict, file: Path) -> str:
    """A portable display path: the configured plans directory name plus the file's place under it."""
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    plans_rel = project.get("plans_dir", "Plans")
    try:
        relative = file.relative_to(Path(config["_plans_dir"])).as_posix()
    except ValueError:
        return file.as_posix()
    return f"{plans_rel}/{relative}"


def _cell_or_none(value: str):
    return None if value in ("", "-") else value


def _drift_record(finding: dict, disk_by_line: dict, rendered_by_path: dict) -> dict:
    """One `drifts` entry. A status finding carries the keys older readers expect."""
    rendered_row = rendered_by_path.get(finding["path"])
    source_row = disk_by_line.get(finding.get("line")) or rendered_row
    record = {
        "class": finding["class"],
        "abbrev": source_row.abbrev if source_row else "-",
        "path": finding["path"],
    }
    if finding["class"] == "stale-row":
        record.update(field=finding["field"], disk=finding["disk"], rendered=finding["rendered"], line=finding["line"])
        if finding["field"] == "status":
            record.update(
                index_status=finding["disk"],
                mp_status=finding["rendered"],
                mp_last_updated=_cell_or_none(rendered_row.last_updated) if rendered_row else None,
            )
    record["message"] = finding["message"]
    return record


def detect_drift(config: dict) -> dict:
    """Compare the on-disk plans index with the index the generator would render.

    Read-only. Never writes. Returns:
        {"drifts": [{"class", "abbrev", "path", "message", ...}, ...],
         "anomalies": [{"class", "abbrev", "reason", "expected_path", ...}, ...],
         "compared": int, "total": int, "status": str}

    A `stale-row` for the status field also carries `index_status`,
    `mp_status` and `mp_last_updated`. `compared` counts the Paths present on
    both sides. `total` counts the table-shaped lines in the table region plus
    every six-cell line outside it, or the Master Plans the walk found when the
    file has no such line. `status` is one of
    `legacy-shape`, `could-not-run`, `incomplete`, `index-missing` or `ran`.
    """
    index_path = plans_index_path(config)
    exists = index_path.is_file()
    content = read_text_preserving_newlines(index_path) if exists else ""
    table = parse_index_table(content)

    if detect_index_shape(content) == "legacy":
        anomaly = {
            "class": "legacy-shape",
            "abbrev": "-",
            "reason": "hand-authored plans index; run /planwise upgrade to migrate it",
            "expected_path": str(index_path),
        }
        return {"drifts": [], "anomalies": [anomaly], "compared": 0, "total": len(table.table_lines), "status": "legacy-shape"}

    render = render_plans_index(config)
    findings = diff_index_rows(table.rows, render.rows)
    disk_by_line = {row.line_number: row for row in table.rows}
    rendered_by_path: dict = {}
    for row in render.rows:
        rendered_by_path.setdefault(row.path, row)

    drifts: list = []
    anomalies: list = []
    for finding in findings:
        kind = finding["class"]
        if kind in ("missing-row", "stale-row"):
            drifts.append(_drift_record(finding, disk_by_line, rendered_by_path))
        elif kind == "orphan-row":
            row = disk_by_line[finding["line"]]
            expected = resolve_master_plan_path(config, {"abbrev": row.abbrev, "path": row.path})
            anomalies.append(
                {
                    "class": "orphan-row",
                    "abbrev": row.abbrev,
                    "reason": "Master Plan not found",
                    "expected_path": _display_path(config, expected),
                    "path": row.path,
                    "line": row.line_number,
                }
            )
        elif kind == "duplicate-row":
            first = disk_by_line[finding["lines"][0]]
            expected = resolve_master_plan_path(config, {"abbrev": first.abbrev, "path": first.path})
            anomalies.append(
                {
                    "class": "duplicate-row",
                    "source": "index",
                    "abbrev": first.abbrev,
                    "reason": finding["message"],
                    "expected_path": _display_path(config, expected),
                    "path": first.path,
                    "lines": finding["lines"],
                }
            )

    if table.unparsed:
        lines = [{"line": line.line_number, "reason": line.reason} for line in table.unparsed]
        anomalies.append(
            {
                "class": "unparsed-rows",
                "abbrev": "-",
                "reason": "; ".join(f"line {item['line']} ({item['reason']})" for item in lines),
                "expected_path": str(index_path),
                "lines": lines,
            }
        )

    abbrev_by_file = {row.file: row.abbrev for row in render.rows}
    for anomaly in render.anomalies:
        file = anomaly.get("file")
        if file is None:
            first = rendered_by_path.get(anomaly.get("path"))
            abbrev = first.abbrev if first else "-"
            file = ", ".join(anomaly.get("files", []))
        else:
            abbrev = abbrev_by_file.get(file, "-")
        record = {
            "class": anomaly["class"],
            "abbrev": abbrev,
            "reason": anomaly["message"],
            "expected_path": file or "-",
        }
        if anomaly["class"] == "duplicate-row":
            record.update(source="tree", path=anomaly["path"])
        anomalies.append(record)

    compared = findings.compared
    total = len(table.table_lines) or len(render.rows)
    if total >= 1 and compared == 0:
        status = "could-not-run"
    elif table.unparsed:
        status = "incomplete"
    elif not exists and not render.rows:
        status = "index-missing"
    else:
        status = "ran"
    return {"drifts": drifts, "anomalies": anomalies, "compared": compared, "total": total, "status": status}


def _write_through_generator(config: dict) -> tuple[int, int]:
    """Write the index through the generator. Returns (rows changed, write exit code).

    Re-reads the index fresh, so a row healed since an earlier `detect_drift`
    is not counted. When the file already equals the render (the `Generated:`
    line masked) nothing is written. The count is the number of Paths whose
    row the render adds, drops or changes. When the generator refuses the
    write, this raises `WriteRefusedError` with the generator's message.
    """
    index_path = plans_index_path(config)
    exists = index_path.is_file()
    disk = read_text_preserving_newlines(index_path) if exists else ""
    if detect_index_shape(disk) == "legacy":
        raise LegacyIndexError(_legacy_message(index_path))

    render = render_plans_index(config)
    anomaly_code = 1 if render.anomalies else 0
    if exists and index_matches_render(disk, render):
        return 0, anomaly_code

    findings = diff_index_rows(parse_index_table(disk).rows, render.rows)
    changed = len({finding["path"] for finding in findings if finding["class"] in _ROW_CLASSES})
    result = write_plans_index(config)
    if result.refusal is not None:
        raise WriteRefusedError(result.refusal)
    return changed, result.exit_code


def reconcile(config: dict) -> int:
    """Re-read the index and rewrite it through the generator when it differs from the render.

    Race-safe: the index is read fresh from disk and compared with a fresh
    render, so a row a concurrent writer healed since a prior `detect_drift`
    is not counted and not rewritten. A hand-authored (legacy-shaped) index
    raises `LegacyIndexError` and nothing is written. A write the generator
    refuses, such as an over-budget render, raises `WriteRefusedError`. Every
    written byte comes from the generator's render.

    Returns the number of rows the write added, dropped or changed.
    """
    return _write_through_generator(config)[0]


def _drift_line(drift: dict) -> str:
    if drift["class"] == "missing-row":
        return f"  - {drift['abbrev']}: missing-row {drift['path']} (the tree has a Master Plan the index lacks)"
    if drift.get("field") == "status":
        return f"  - {drift['abbrev']}: index={drift['index_status']} -> Master Plan={drift['mp_status']}"
    return f"  - {drift['abbrev']}: {drift['field']} index={drift['disk']} -> Master Plan={drift['rendered']}"


def _format_report(result: dict) -> str:
    """Render a human-readable drift + anomaly report."""
    rows_out_of_sync = len({d["path"] for d in result["drifts"]})
    return format_drift_report(
        result,
        no_drift_message="No drift detected. All index rows match their Master Plan status.",
        no_drift_only_message="No status drift detected.",
        drift_header=f"Drift detected ({rows_out_of_sync} row(s) out of sync with Master Plan status):",
        drift_line=_drift_line,
        anomaly_line=lambda a: f"  - {a['abbrev']}: {a['reason']} (expected: {a['expected_path']})",
    )


def _print_json(result: dict) -> None:
    print(f"JSON: {write_json_result(result, JSON_PREFIX)}")


def _report_detect(result: dict, index_path: Path, want_json: bool) -> int:
    """Print the detect result and return the exit code the status calls for."""
    status = result["status"]
    compared, total = result["compared"], result["total"]
    if status == "index-missing":
        print(f"Error: Plans index not found at {index_path}", file=sys.stderr)
        return 1
    if status == "legacy-shape":
        print(_legacy_message(index_path), file=sys.stderr)
        code = 2
    elif status == "could-not-run":
        print(f"Drift audit could not run: 0 of {total} rows compared")
        if index_path.is_file():
            print("No index row matched a Master Plan on disk.")
        else:
            print(f"The index is missing and the tree holds {total} Master Plans.")
        code = 3
    elif status == "incomplete" or (compared != total and not result["drifts"] and not result["anomalies"]):
        # The second clause is a guard: rows went uncompared with nothing to report, so no all-clear.
        print(f"Drift audit incomplete: {compared} of {total} rows compared")
        for anomaly in result["anomalies"]:
            if anomaly["class"] == "unparsed-rows":
                for item in anomaly["lines"]:
                    print(f"  - line {item['line']}: table-shaped but yields no row ({item['reason']})")
        code = 3
    else:
        print(_format_report(result))
        print(f"{compared} of {total} rows compared.")
        code = 0
    if want_json:
        _print_json(result)
    return code


def _report_write(config: dict, index_path: Path, want_json: bool) -> int:
    if not index_path.is_file() and not enumerate_master_plans(Path(config["_plans_dir"])):
        print(f"Error: Plans index not found at {index_path}", file=sys.stderr)
        return 1
    try:
        written, code = _write_through_generator(config)
    except (LegacyIndexError, WriteRefusedError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"Reconciled {written} row(s).")
    if want_json:
        _print_json(detect_drift(config))
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and reconcile plans-index drift against each plan's Master Plan."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml; overrides default config search.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Reconcile drifted rows (re-reads the index immediately before writing).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Additionally write a JSON temp file and print its path.",
    )
    # `--config` is declared for `--help` and so an explicit `--config <path>` does not
    # trip `parse_known_args`; `load_config` reads it back out of `sys.argv` itself.
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    index_path = plans_index_path(config)

    if args.write:
        return _report_write(config, index_path, args.json)
    return _report_detect(detect_drift(config), index_path, args.json)


if __name__ == "__main__":
    sys.exit(main())
