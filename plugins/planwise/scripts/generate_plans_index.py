#!/usr/bin/env python3
"""Render, check and write the plans index from each plan's Master Plan.

Every Master Plan states its own status, created date and last-updated date.
This module reads those files (through `parse_plans`) and renders one index
file from them. It is the only writer of that file. It never edits a Master
Plan.

## The rendered file

One file, six columns (`Abbrev`, `Name`, `Status`, `Created`, `Last Updated`,
`Path`), one row per Master Plan the disk walk finds, then a `Status Legend`
generated from `config["plan_statuses"]`. Rows sort by (Created, Path) with a
missing Created last, so a second run is byte-identical. Every cell passes
through `_escape_cell`. The Status cell is the normalized status token.

## Refusals and exit codes

- `--write` refuses to overwrite a hand-authored (legacy-shaped) index unless
  `--replace-legacy` is given, refuses a non-empty index that is neither
  hand-authored nor generated (`--replace-legacy` never overrides that), and
  refuses when the render measures over `HUB_TOKEN_BUDGET`. All exit 2 and
  write nothing. A missing, zero-byte or blank index writes.
- `--write` still writes when the tree carries an anomaly (an unknown or missing
  status, two Master Plans with one Path, an unreadable file), then exits 1. The
  index never lags the tree.
- `--check` compares the on-disk file with a fresh render and exits 1 on any
  finding. A legacy-shaped index exits 2. `--dry-run` (the default) renders and
  reports without writing.

## Budget

The index is one file and is never split. The budget is measured on the file
that ships (title, `Generated:` line, table and legend), on the CRLF worst case.
A render over budget is refused, and the refusal is the signal to shard.

The generic index helpers (measurement, escaping, atomic write, line-ending
detection) are imported through the `generate_backlog_index` facade.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from config_loader import load_config
from generate_backlog_index import (
    HUB_TOKEN_BUDGET,
    _atomic_write_files,
    _budget_fields,
    _escape_cell,
    _generated_line,
    _index_naming,
    _measure,
    detect_line_ending,
)
from parse_plans import (
    detect_index_shape,
    enumerate_master_plans,
    parse_index_table,
    read_master_plan_fields,
)
from reconcile_common import read_text_preserving_newlines

__all__ = [
    "PLAN_STATUS_MEANINGS",
    "CheckResult",
    "PlansRender",
    "RenderedRow",
    "RowFindings",
    "WriteResult",
    "check_plans_index",
    "diff_index_rows",
    "index_matches_render",
    "is_generated_plans_index_file",
    "main",
    "plans_index_path",
    "render_plans_index",
    "write_plans_index",
]

INDEX_TITLE = "# Plans Index"
INDEX_INTRO = (
    "> Generated from each plan's Master Plan by generate_plans_index.py. "
    "Edit the Master Plan's **Status:** line, then run the generator."
)
TABLE_HEADER = "| Abbrev | Name | Status | Created | Last Updated | Path |"
TABLE_SEPARATOR = "|--------|------|--------|---------|--------------|------|"
LEGEND_HEADING = "## Status Legend"
LEGEND_HEADER = "| Status | Meaning |"
LEGEND_SEPARATOR = "|--------|---------|"
PROJECT_DEFINED = "(project-defined)"

# The row fields, in column order. `stale-row` findings name one of these.
FIELDS = ("abbrev", "name", "status", "created", "last_updated", "path")

# What each shipped status value means. A configured value absent from this
# table renders `(project-defined)` in the legend.
PLAN_STATUS_MEANINGS = {
    "NOT_STARTED": "Plan created but no work begun",
    "PLANNING": "Discovery or session planning in progress",
    "READY_TO_EXECUTE": "Plan files authored; ready for `/planwise run`",
    "REVIEWED": "Reviewed by `/planwise review`; no verdict recorded yet",
    "APPROVED": "Review verdict: validated for execution",
    "NEEDS_FIXES": "Review verdict: findings to fix before execution",
    "IN_PROGRESS": "Active execution underway",
    "BLOCKED": "Waiting on external dependency",
    "COMPLETE": "All sprints and sessions finished",
    "CLOSED": "Archived — no further work expected",
}

_GENERATED_LINE_RE = re.compile(r"^Generated:.*$", re.MULTILINE)


def _finding(kind: str, message: str, **extra) -> dict:
    return {"class": kind, "message": message, **extra}


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def plans_index_path(config: dict) -> Path:
    """The plans index file the project's config names."""
    return Path(config["_plans_index"])


def is_generated_plans_index_file(name: str, config: dict) -> bool:
    """True only for the plans index file's own name."""
    return name == plans_index_path(config).name


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedRow:
    """One row as rendered: the six cell values (unescaped) and its source file."""

    abbrev: str
    name: str
    status: str
    created: str
    last_updated: str
    path: str
    file: str

    @property
    def cells(self) -> tuple:
        return (self.abbrev, self.name, self.status, self.created, self.last_updated, self.path)

    def line(self) -> str:
        return "| " + " | ".join(_escape_cell(cell) for cell in self.cells) + " |"


@dataclass(frozen=True)
class PlansRender:
    """The result of `render_plans_index`.

    `text` uses `\\n` line endings. `frame` is the same text with no rows, which
    `--check` compares against the disk to find a change to anything but the rows.
    `num_bytes` and `tokens` measure `text` on the CRLF worst case.
    """

    text: str
    frame: str
    rows: list
    anomalies: list
    warnings: list
    num_bytes: int
    tokens: int


def _assemble(rows: list, statuses: list) -> str:
    parts = [
        f"{INDEX_TITLE}\n\n",
        _generated_line(),
        f"{INDEX_INTRO}\n\n",
        f"{TABLE_HEADER}\n{TABLE_SEPARATOR}\n",
    ]
    parts.extend(f"{row.line()}\n" for row in rows)
    parts.append(f"\n{LEGEND_HEADING}\n\n{LEGEND_HEADER}\n{LEGEND_SEPARATOR}\n")
    for status in statuses:
        meaning = PLAN_STATUS_MEANINGS.get(status, PROJECT_DEFINED)
        parts.append(f"| {_escape_cell(status)} | {_escape_cell(meaning)} |\n")
    return "".join(parts)


def _status_cell(fields, rel: str, statuses: list, anomalies: list) -> str:
    """The Status cell: the normalized token, or the raw first word, or `-`."""
    if fields.status_raw is None:
        anomalies.append(_finding("missing-status", f"{rel}: the Master Plan has no **Status:** line", file=rel))
        return "-"
    token = fields.status_token
    if token is None:
        token = fields.status_raw.split()[0].strip("*_") or "-"
    if token not in statuses:
        anomalies.append(
            _finding(
                "unknown-status",
                f"{rel}: Status line {fields.status_raw!r} reads {token!r}, which is not in plan_statuses",
                file=rel,
                raw=fields.status_raw,
                status=token,
            )
        )
    return token


def render_plans_index(config: dict) -> PlansRender:
    """Render the plans index from the Master Plans on disk. Writes nothing."""
    plans_dir = Path(config["_plans_dir"])
    statuses = list(config["plan_statuses"])
    anomalies: list = []
    warnings: list = []
    built: list = []
    for entry in enumerate_master_plans(plans_dir):
        rel = entry.file.relative_to(plans_dir).as_posix()
        try:
            fields = read_master_plan_fields(entry.file)
        except (OSError, UnicodeDecodeError) as exc:
            anomalies.append(_finding("unreadable-file", f"{rel}: cannot read the Master Plan ({exc})", file=rel))
            built.append(RenderedRow(entry.abbrev, entry.name, "-", "-", "-", entry.path, rel))
            continue
        for label, value in (("Created", fields.created), ("Last Updated", fields.last_updated)):
            if value is None:
                warnings.append(
                    _finding("missing-field", f"{rel}: no {label} date", file=rel, field=label.lower().replace(" ", "_"))
                )
        built.append(
            RenderedRow(
                abbrev=entry.abbrev,
                name=entry.name,
                status=_status_cell(fields, rel, statuses, anomalies),
                created=fields.created or "-",
                last_updated=fields.last_updated or "-",
                path=entry.path,
                file=rel,
            )
        )
    rows = sorted(built, key=lambda row: (row.created == "-", row.created, row.path, row.file))

    files_by_path: dict = {}
    for row in rows:
        files_by_path.setdefault(row.path, []).append(row.file)
    for path, files in files_by_path.items():
        if len(files) > 1:
            anomalies.append(
                _finding(
                    "duplicate-row",
                    f"{path} is the Path of {len(files)} Master Plans: {', '.join(files)}",
                    path=path,
                    files=files,
                )
            )

    text = _assemble(rows, statuses)
    num_bytes, tokens = _measure(text)
    return PlansRender(
        text=text,
        frame=_assemble([], statuses),
        rows=rows,
        anomalies=anomalies,
        warnings=warnings,
        num_bytes=num_bytes,
        tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


class RowFindings(list):
    """The row findings, as a list. `compared` counts the Paths on both sides."""

    compared: int = 0


def diff_index_rows(disk_rows: list, rendered_rows: list, disk_lines: dict | None = None) -> RowFindings:
    """Compare the on-disk rows with the rendered rows, keyed by Path.

    Rows are grouped by Path after counting, never collapsed into a dict, so a
    Path on disk twice is named. Repeated rows of one Path are paired by
    position. Findings: `missing-row` (rendered, not on disk), `orphan-row` (on
    disk, not rendered), `stale-row` (one per differing field) and
    `duplicate-row` (a Path on disk more than once, with every line number).
    When `disk_lines` maps a line number to its text, a row whose cells match
    but whose line text differs is a `stale-row` on `line-format`.
    """
    disk_by_path: dict = {}
    for row in disk_rows:
        disk_by_path.setdefault(row.path, []).append(row)
    rendered_paths = {row.path for row in rendered_rows}

    findings = RowFindings()
    compared = 0
    seen: dict = {}
    for row in rendered_rows:
        index = seen.get(row.path, 0)
        seen[row.path] = index + 1
        on_disk = disk_by_path.get(row.path, [])
        if index >= len(on_disk):
            findings.append(
                _finding(
                    "missing-row",
                    f"{row.path} is rendered from {row.file} but has no row on disk"
                    if index == 0
                    else f"{row.path} renders {index + 1} times but appears on disk {len(on_disk)} times",
                    path=row.path,
                )
            )
            continue
        if index == 0:
            compared += 1
        disk = on_disk[index]
        stale = False
        for name, disk_value, value in zip(FIELDS, disk.cells, row.cells):
            if disk_value != value:
                stale = True
                findings.append(
                    _finding(
                        "stale-row",
                        f"{row.path} field {name}: disk {disk_value!r}, rendered {value!r}",
                        path=row.path,
                        field=name,
                        disk=disk_value,
                        rendered=value,
                        line=disk.line_number,
                    )
                )
        if not stale and disk_lines is not None and disk_lines.get(disk.line_number) != row.line():
            findings.append(
                _finding(
                    "stale-row",
                    f"{row.path} line {disk.line_number}: the cells match but the line is formatted differently",
                    path=row.path,
                    field="line-format",
                    disk=disk_lines.get(disk.line_number),
                    rendered=row.line(),
                    line=disk.line_number,
                )
            )
    for path, rows in disk_by_path.items():
        lines = [row.line_number for row in rows]
        if path not in rendered_paths:
            for row in rows:
                findings.append(
                    _finding(
                        "orphan-row",
                        f"{path} is on disk at line {row.line_number} but no Master Plan renders it",
                        path=path,
                        line=row.line_number,
                    )
                )
        if len(rows) > 1:
            findings.append(
                _finding(
                    "duplicate-row",
                    f"{path} appears on disk {len(rows)} times, at lines {', '.join(str(n) for n in lines)}",
                    path=path,
                    lines=lines,
                )
            )
    findings.compared = compared
    return findings


@dataclass
class CheckResult:
    """The result of `check_plans_index`. `exit_code` is the `--check` exit code."""

    exit_code: int
    shape: str
    findings: list
    anomalies: list
    warnings: list
    compared: int
    render: PlansRender
    exists: bool = field(default=True)


def _mask(text: str) -> str:
    return _GENERATED_LINE_RE.sub("Generated: (masked)", text)


def _first_line_difference(disk_lines: list, render_lines: list):
    """The first differing pair of (line number, text) items, or `None`."""
    for index in range(max(len(disk_lines), len(render_lines))):
        disk = disk_lines[index] if index < len(disk_lines) else None
        rendered = render_lines[index] if index < len(render_lines) else None
        if disk is None or rendered is None or disk[1] != rendered[1]:
            return disk, rendered
    return None


def _shape_findings(disk: str, table, render: PlansRender, rows_clean: bool) -> list:
    """Findings for a difference in anything but the rows, and for row order."""
    masked_disk, masked_render = _mask(disk), _mask(render.text)
    if masked_disk == masked_render:
        return []
    findings: list = []
    table_numbers = {line.line_number for line in table.table_lines}
    disk_residue = [(n, text) for n, text in enumerate(masked_disk.split("\n"), 1) if n not in table_numbers]
    frame_residue = list(enumerate(_mask(render.frame).split("\n"), 1))
    difference = _first_line_difference(disk_residue, frame_residue)
    if difference is not None:
        disk_item, rendered_item = difference
        findings.append(
            _finding(
                "stale-shape",
                f"outside the rows, the first difference is at disk line {disk_item[0] if disk_item else 'end of file'}: "
                f"disk {disk_item[1] if disk_item else None!r}, rendered {rendered_item[1] if rendered_item else None!r}",
                line=disk_item[0] if disk_item else None,
                disk=disk_item[1] if disk_item else None,
                rendered=rendered_item[1] if rendered_item else None,
            )
        )
    disk_paths = {row.path for row in table.rows}
    rendered_paths = {row.path for row in render.rows}
    if [r.path for r in table.rows if r.path in rendered_paths] != [r.path for r in render.rows if r.path in disk_paths]:
        findings.append(_finding("stale-shape", "the rows are in a different order than the render"))
    if not findings and rows_clean:
        difference = _first_line_difference(
            list(enumerate(masked_disk.split("\n"), 1)), list(enumerate(masked_render.split("\n"), 1))
        )
        disk_item, rendered_item = difference
        findings.append(
            _finding(
                "stale-shape",
                f"the file differs from the render and no row finding explains it, first at disk line "
                f"{disk_item[0] if disk_item else 'end of file'}",
                line=disk_item[0] if disk_item else None,
                disk=disk_item[1] if disk_item else None,
                rendered=rendered_item[1] if rendered_item else None,
            )
        )
    return findings


def _legacy_message(index_path: Path) -> str:
    return (
        f"Error: {index_path} is a hand-authored plans index — run /planwise upgrade to migrate it "
        "before reading it as generated"
    )


def _over_budget_finding(render: PlansRender) -> dict:
    return _finding(
        "over-budget",
        f"the rendered index measures {render.num_bytes} bytes ({render.tokens} tokens), "
        f"over the {HUB_TOKEN_BUDGET}-token budget",
        bytes=render.num_bytes,
        tokens=render.tokens,
        budget=HUB_TOKEN_BUDGET,
    )


def check_plans_index(config: dict) -> CheckResult:
    """The `--check` logic: compare the on-disk index with a fresh render.

    Exit 0 means the file equals the render (the `Generated:` line masked) and
    the tree has no anomaly. Exit 1 means any finding or anomaly. Exit 2 means
    the on-disk index is legacy-shaped and was not compared.
    """
    index_path = plans_index_path(config)
    render = render_plans_index(config)
    exists = index_path.is_file()
    disk = read_text_preserving_newlines(index_path).replace("\r\n", "\n") if exists else ""
    shape = detect_index_shape(disk)
    if shape == "legacy":
        finding = _finding("legacy-shape", _legacy_message(index_path), index=str(index_path))
        return CheckResult(2, shape, [finding], render.anomalies, render.warnings, 0, render, exists)

    findings: list = []
    if not exists:
        findings.append(_finding("missing-index", f"{index_path} does not exist"))
    table = parse_index_table(disk)
    disk_lines = {line.line_number: line.text for line in table.table_lines}
    row_findings = diff_index_rows(table.rows, render.rows, disk_lines)
    findings.extend(row_findings)
    for line in table.unparsed:
        findings.append(
            _finding(
                "unparsed-row",
                f"line {line.line_number} is table-shaped but yields no row ({line.reason})",
                line=line.line_number,
                reason=line.reason,
            )
        )
    if exists:
        findings.extend(_shape_findings(disk, table, render, rows_clean=not findings))
    if render.tokens > HUB_TOKEN_BUDGET:
        findings.append(_over_budget_finding(render))
    code = 1 if findings or render.anomalies else 0
    return CheckResult(code, shape, findings, render.anomalies, render.warnings, row_findings.compared, render, exists)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _payload(index_path: Path, shape: str, render: PlansRender, findings: list, compared: int | None) -> dict:
    payload = {"index": str(index_path), "shape": shape, "rows": len(render.rows)}
    if compared is not None:
        payload["compared"] = compared
    payload["findings"] = findings
    payload["anomalies"] = render.anomalies
    payload["warnings"] = render.warnings
    payload.update(_budget_fields(render.num_bytes, render.tokens, HUB_TOKEN_BUDGET))
    return payload


def _report(index_path: Path, shape: str, render: PlansRender, findings: list, compared: int | None) -> str:
    head = f"Plans index {index_path}: {len(render.rows)} rows rendered"
    if compared is not None:
        head += f", {compared} compared with the file on disk"
    head += f" ({shape}); {render.num_bytes} bytes, {render.tokens} of {HUB_TOKEN_BUDGET} tokens."
    lines = [head]
    for label, items in (("anomaly", render.anomalies), ("finding", findings), ("warning", render.warnings)):
        lines.extend(f"  {label} {item['class']}: {item['message']}" for item in items)
    if not render.anomalies and not findings:
        lines.append("  no anomalies and no findings")
    return "\n".join(lines)


def _drop_listing(disk: str) -> str:
    lines = disk.replace("\r\n", "\n").split("\n")
    comments = sum(1 for line in lines if line.lstrip().startswith("<!--"))
    headings = [line.strip() for line in lines if line.startswith("## ") and line.strip() != LEGEND_HEADING]
    out = ["--replace-legacy is dropping this hand-written content:", f"  {comments} comment line(s)"]
    out.extend(f"  {heading}" for heading in headings)
    return "\n".join(out)


@dataclass(frozen=True)
class WriteResult:
    """The result of `write_plans_index`.

    `exit_code` is the `--write` exit code: 0 clean, 1 written with a tree
    anomaly, 2 refused. `written` says whether any byte reached the disk.
    `refusal` is the refusal message, or `None` when the write went ahead.
    `drop_listing` names the hand-written content a `replace_legacy` write drops,
    or is `None`. `shape` is the on-disk shape the write found.
    """

    exit_code: int
    written: bool
    refusal: str | None
    render: PlansRender
    shape: str
    drop_listing: str | None = None


def index_matches_render(disk: str, render: PlansRender) -> bool:
    """True when the index text equals the render, the `Generated:` line masked and CRLF read as LF."""
    return _mask(disk.replace("\r\n", "\n")) == _mask(render.text)


def write_plans_index(config: dict, *, replace_legacy: bool = False) -> WriteResult:
    """Write the index from a fresh render. Prints nothing and raises nothing on a refusal.

    Refuses, and writes nothing, when the file on disk is hand-authored and
    `replace_legacy` is false, when it is non-empty and neither hand-authored
    nor generated (`replace_legacy` never overrides that), or when the render
    measures over the budget. A missing, zero-byte or blank file writes. The
    refusal message is in the result. A tree anomaly does not stop the write: it
    sets exit code 1.
    """
    index_path = plans_index_path(config)
    render = render_plans_index(config)
    plans_dir = Path(config["_plans_dir"])
    disk = read_text_preserving_newlines(index_path) if index_path.is_file() else ""
    shape = detect_index_shape(disk)
    if shape == "legacy" and not replace_legacy:
        refusal = (
            f"Error: {index_path} is a hand-authored plans index. Run /planwise upgrade to migrate it first, "
            "or pass --replace-legacy to overwrite it and drop its hand-written content. Nothing was written."
        )
        return WriteResult(2, False, refusal, render, shape)
    if shape == "empty" and disk.strip():
        refusal = (
            f"Error: {index_path} is neither a hand-authored nor a generated plans index, so it may hold "
            "content this write would destroy. Nothing was written. Inspect it with "
            "`migrate_plans_index.py --report`, then move it aside or migrate it."
        )
        return WriteResult(2, False, refusal, render, shape)
    if render.tokens > HUB_TOKEN_BUDGET:
        refusal = (
            f"Error: the rendered plans index measures {render.num_bytes} bytes ({render.tokens} tokens), "
            f"over the {HUB_TOKEN_BUDGET}-token budget. Nothing was written. "
            "The index is one file, so shard or shorten it before writing."
        )
        return WriteResult(2, False, refusal, render, shape)
    ending = detect_line_ending(plans_dir, plans_dir, _index_naming(index_path))
    _atomic_write_files({index_path: render.text.replace("\n", ending)}, [])
    listing = _drop_listing(disk) if shape == "legacy" else None
    return WriteResult(1 if render.anomalies else 0, True, None, render, shape, listing)


def _cmd_write(config: dict, replace_legacy: bool, json_out: bool) -> int:
    """The `--write` CLI: `write_plans_index` plus its printed report."""
    index_path = plans_index_path(config)
    result = write_plans_index(config, replace_legacy=replace_legacy)
    if result.refusal is not None:
        print(result.refusal, file=sys.stderr)
        return result.exit_code
    if result.drop_listing is not None:
        print(result.drop_listing, file=sys.stderr)
    if json_out:
        payload = _payload(index_path, result.shape, result.render, [], None)
        payload["written"] = True
        print(json.dumps(payload, indent=2))
    else:
        print(f"Wrote {index_path}.")
        print(_report(index_path, result.shape, result.render, [], None))
    return result.exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render, check and write the plans index from each plan's Master Plan."
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the render and the report without writing. This is the default when no mode flag is given.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the index on disk with a fresh render. Exit 1 on any finding, 2 on a hand-authored index.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the index. Refuses (exit 2) on a hand-authored index without --replace-legacy, "
        "and when the render is over budget. Exits 1 after writing when the tree has an anomaly.",
    )
    parser.add_argument("--json", action="store_true", help="Print the report and budget fields as JSON.")
    parser.add_argument(
        "--replace-legacy",
        action="store_true",
        help="Allow --write to overwrite a hand-authored index. Prefer /planwise upgrade, which migrates it first.",
    )
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))
    index_path = plans_index_path(config)

    if args.write:
        return _cmd_write(config, args.replace_legacy, args.json)

    if args.check:
        result = check_plans_index(config)
        if result.exit_code == 2:
            print(_legacy_message(index_path), file=sys.stderr)
        if args.json:
            print(json.dumps(_payload(index_path, result.shape, result.render, result.findings, result.compared), indent=2))
        elif result.exit_code != 2:
            print(_report(index_path, result.shape, result.render, result.findings, result.compared))
        return result.exit_code

    render = render_plans_index(config)
    disk = read_text_preserving_newlines(index_path) if index_path.is_file() else ""
    shape = detect_index_shape(disk)
    findings = [_over_budget_finding(render)] if render.tokens > HUB_TOKEN_BUDGET else []
    if args.json:
        print(json.dumps(_payload(index_path, shape, render, findings, None), indent=2))
    else:
        print(render.text)
        print(_report(index_path, shape, render, findings, None))
    return 1 if findings or render.anomalies else 0


if __name__ == "__main__":
    sys.exit(main())
