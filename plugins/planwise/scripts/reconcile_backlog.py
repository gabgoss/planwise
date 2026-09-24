#!/usr/bin/env python3
"""Detect and reconcile backlog item-file drift, read from the item files.

Two independent modes share one CLI. The default mode audits archival
drift (a closed item file outside `Archive/`). The `--body-status` mode
audits a legacy body status line left in an item's header block. Each mode
has its own detect/reconcile pair; neither ever writes an index.

Archival mode
-------------

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

Body status mode (`--body-status`)
----------------------------------

An item's status lives in its frontmatter `status:` field only. Older item
writers also emitted a legacy body status line (`**Status:** VALUE`) under
the title, which nothing keeps in sync. The invariant this mode audits:

    an item file carries no `**Status:**` line in its header block.

The header block is the run of lines after the first H1 (`# `) line that
follows the frontmatter, up to the first line that is exactly `---` or
starts with `## `. Lines inside a fenced code block never count: a fenced
line is never the H1, never closes the block, and is never a hit. A
header-block line that starts with `**Status:**` at column 0 is drift,
whether or not it agrees with frontmatter. Each drift carries a `kind`:
`disagrees` (the body value's first token differs from frontmatter
`status:`) or `redundant` (it agrees today). A file with no such line
reports nothing: absence is the goal state, not an anomaly.

Anomalies are reported and never stripped: a header-block status line in a
file whose frontmatter `status:` cannot be read; two or more header-block
status lines in one file; and a file with no H1 title whose region before
the first `## ` heading holds a column-0 status line outside a fence (the
header block is undefined there).

  - detect_body_status(config): read-only. Same item-file iterator and
    frontmatter reader as the archival mode.
  - reconcile_body_status(config): re-scans every file fresh at write time
    (race-safe), and removes exactly the one drifted line together with its
    own line terminator (`\\n` or `\\r\\n`), preserving every other byte. It
    never edits frontmatter, never touches an anomaly file, never collapses
    the surrounding blank lines, and never writes an index.
"""

import argparse
import re
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
import reconcile_common
from frontmatter_parser import BOM_CHAR, split_frontmatter_block
from reconcile_common import format_drift_report, run_reconcile_cli
from update_backlog import _frontmatter_id, archive_item_files

# Failed-move accounting for the last `reconcile()` call, so `main()` can
# fail the command when a consented move didn't succeed -- without adding a
# failure-signaling hook to `reconcile_common.run_reconcile_cli`, which the
# plans/lessons reconcilers also share and whose `reconcile(config) -> int`
# contract (a plain "rows changed" count, per `write_message`) stays
# unchanged. Reset at the start of every `reconcile()` call.
_last_reconcile_failures: list[tuple[str, str]] = []

# Failed-write accounting for the last `reconcile_body_status()` call, kept
# separate from the archival list above so neither mode can fail the other.
# Reset at the start of every `reconcile_body_status()` call and in `main()`.
_last_body_status_failures: list[tuple[str, str]] = []

# A legacy body status line. The value group never crosses a line
# terminator: `[^\r\n]*` keeps a CRLF file's `\r` out of the captured value.
_BODY_STATUS_RE = re.compile(r"\*\*Status:\*\*([^\r\n]*)")

# CommonMark fenced code block delimiters (matched with `fullmatch`).
_FENCE_OPEN_RE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_FENCE_CLOSE_RE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")


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


# --------------------------------------------------------------------------
# Body status mode
# --------------------------------------------------------------------------


def _body_start_index(text: str) -> int:
    """Return the 0-based index of the first line after the closing `---`.

    Uses the shared frontmatter splitter, so the block boundary matches the
    one every other reader sees. The splitter expects `\\n` terminators, so it
    runs on a CRLF-normalized copy; normalizing `\\r\\n` to `\\n` changes no
    `\\n` count, so the index is the same in the raw text. Returns 0 when the
    file has no well-formed frontmatter block.
    """
    parts = split_frontmatter_block(text.replace("\r\n", "\n"))
    if parts is None:
        return 0
    frontmatter_text, _body = parts
    # The frontmatter text holds `count("\n") + 1` lines. They sit after the
    # opening `---` (index 0), so the closing `---` is at `count + 2` and the
    # first line after it is at `count + 3`.
    return frontmatter_text.count("\n") + 3


def _fence_opener(line: str) -> tuple[str, int] | None:
    """Return (fence char, run length) when `line` opens a fenced code block.

    CommonMark rules: 0-3 spaces of indent, then a run of 3 or more
    backticks or 3 or more tildes. A backtick opener's info string may not
    contain a backtick (so inline code at line start is not a fence).
    """
    match = _FENCE_OPEN_RE.fullmatch(line)
    if match is None:
        return None
    run, info = match.group(1), match.group(2)
    if run[0] == "`" and "`" in info:
        return None
    return run[0], len(run)


def _closes_fence(line: str, fence: tuple[str, int]) -> bool:
    """True when `line` closes `fence`: same char, a run at least as long,
    0-3 spaces of indent, and only whitespace after the run."""
    match = _FENCE_CLOSE_RE.fullmatch(line)
    if match is None:
        return False
    run = match.group(1)
    return run[0] == fence[0] and len(run) >= fence[1]


def _scan_body_status(text: str) -> dict:
    """Classify column-0 `**Status:**` lines against the header-block rule.

    Pure function over raw text, shared by the detect and write paths.
    Splits on `\\n` only (never `splitlines()`, which also splits on form
    feeds and Unicode separators and would shift line indices); one trailing
    `\\r` is ignored for classification only, and so is a leading BOM on the
    first line. Fenced code blocks follow the CommonMark opener and closer
    rules; an unterminated fence runs to the end of the file. Returns:

        {"header_hits": [(line_index, value), ...],
         "header_hits_with_cr": [line_index, ...],
         "has_h1": bool,
         "pre_h2_hits_without_h1": [(line_index, value), ...]}

    `line_index` is 0-based. `header_hits_with_cr` lists the header hits
    that still hold a `\\r` after one trailing `\\r` is set aside: the value
    stops at that `\\r`, so the reported value is not the whole line.
    `pre_h2_hits_without_h1` is filled only when the file has no H1 title:
    the column-0 status lines found before the first `## ` heading, where
    the header block is undefined.
    """
    lines = text.split("\n")
    fence = None
    has_h1 = False
    seen_h2 = False
    header_hits = []
    cr_hits = []
    pre_h2_hits = []

    for index in range(_body_start_index(text), len(lines)):
        raw = lines[index]
        line = raw[:-1] if raw.endswith("\r") else raw
        if index == 0:
            # Classification only: the write path keeps the raw BOM.
            line = line.lstrip(BOM_CHAR)

        # A fence line (opener, content or closer) is never the H1, never a
        # close, and never a hit. Inside a fence only a closer is checked.
        if fence is not None:
            if _closes_fence(line, fence):
                fence = None
            continue
        opener = _fence_opener(line)
        if opener is not None:
            fence = opener
            continue

        if not has_h1:
            if line.startswith("# "):
                has_h1 = True
                continue
            if line.startswith("## "):
                seen_h2 = True
            elif not seen_h2:
                match = _BODY_STATUS_RE.match(line)
                if match:
                    pre_h2_hits.append((index, match.group(1)))
            continue

        # Inside the header block, which the first `---` or `## ` closes.
        if line == "---":
            break
        if line.startswith("## "):
            break
        match = _BODY_STATUS_RE.match(line)
        if match:
            header_hits.append((index, match.group(1)))
            if "\r" in line:
                cr_hits.append(index)

    return {
        "header_hits": header_hits,
        "header_hits_with_cr": cr_hits,
        "has_h1": has_h1,
        "pre_h2_hits_without_h1": [] if has_h1 else pre_h2_hits,
    }


def _body_status_token(value: str) -> str:
    """Return the body value's first token, normalized for comparison.

    Drops `*` and backticks, then trailing `.,;:`, and upper-cases the
    result. An empty value yields "".
    """
    parts = value.split()
    if not parts:
        return ""
    token = parts[0].replace("*", "").replace("`", "").rstrip(".,;:")
    return token.upper()


def _item_path(config: dict, entry: dict) -> Path:
    directory = config["_archive_dir"] if entry["in_archive"] else config["_backlog_dir"]
    return directory / entry["file"]


def detect_body_status(config: dict) -> dict:
    """Find every legacy body status line left in an item's header block.

    Read-only. Never writes, and never reads an index. Returns:
        {"drifts": [{"id", "status", "body_status", "kind", "file",
                     "in_archive", "line", "reason", "needs_strip"}, ...],
         "anomalies": [{"id", "status", "file", "in_archive", "line",
                        "reason"}, ...]}
    `file` is the item file's basename and `line` is 1-based. `kind` is
    "disagrees" or "redundant". An anomaly's `status` is "?" when the
    frontmatter status cannot be read.
    """
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]
    index_path = config["_index_path"]

    drifts = []
    anomalies = []
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        in_archive = archive_dir.exists() and _same_dir(path.parent, archive_dir)
        display_id, _compare_key, status = _read_item(path)
        base = {
            "id": display_id or "?",
            "status": status or "?",
            "file": path.name,
            "in_archive": in_archive,
        }

        try:
            text = reconcile_common.read_text_preserving_newlines(path)
        except (OSError, UnicodeDecodeError) as exc:
            anomalies.append(
                {**base, "line": None, "reason": f"file could not be read ({exc}) — never stripped"}
            )
            continue

        scan = _scan_body_status(text)

        if not scan["has_h1"]:
            stray = scan["pre_h2_hits_without_h1"]
            if stray:
                anomalies.append(
                    {
                        **base,
                        "line": stray[0][0] + 1,
                        "reason": "no H1 title, so the header block is undefined, but a "
                        "column-0 status line precedes the first ## heading — never stripped",
                    }
                )
            continue

        hits = scan["header_hits"]
        if not hits:
            continue

        if status is None:
            anomalies.append(
                {
                    **base,
                    "line": hits[0][0] + 1,
                    "reason": "header-block status line in a file whose frontmatter "
                    "status cannot be read — never stripped",
                }
            )
            continue

        if len(hits) > 1:
            numbers = ", ".join(str(index + 1) for index, _value in hits)
            anomalies.append(
                {
                    **base,
                    "line": hits[0][0] + 1,
                    "reason": f"{len(hits)} header-block status lines (lines {numbers}) "
                    "— never stripped",
                }
            )
            continue

        index, value = hits[0]
        if scan["header_hits_with_cr"]:
            anomalies.append(
                {
                    **base,
                    "line": index + 1,
                    "reason": "status line holds a bare carriage return (\\r) mid-line, so "
                    "the reported value is not the whole line — never stripped",
                }
            )
            continue

        body_status = value.strip()
        if _body_status_token(body_status) == status.upper():
            kind = "redundant"
            reason = "redundant body status line — frontmatter is the only status field"
        else:
            kind = "disagrees"
            reason = "body status line disagrees with frontmatter"
        drifts.append(
            {
                "id": base["id"],
                "status": status,
                "body_status": body_status,
                "kind": kind,
                "file": path.name,
                "in_archive": in_archive,
                "line": index + 1,
                "reason": reason,
                "needs_strip": True,
            }
        )

    return {"drifts": drifts, "anomalies": anomalies}


def reconcile_body_status(config: dict) -> int:
    """Re-scan the item files and strip each header-block status line still drifted.

    Race-safe: recomputes drift from the files on disk, then re-reads and
    re-scans each file immediately before writing it, and acts only when the
    file still holds exactly one header-block status line and a readable
    frontmatter status. Removes that one line together with its own
    terminator and writes every other byte back unchanged, through the
    newline-preserving read/write pair. Anomalies are never touched.

    A failed write is printed, not counted, and recorded into
    `_last_body_status_failures` so `main()` can fail the command for it.
    Never edits or writes any index file.

    Returns the number of status lines stripped.
    """
    global _last_body_status_failures
    _last_body_status_failures = []

    result = detect_body_status(config)
    stripped = 0
    for drift in result["drifts"]:
        path = _item_path(config, drift)
        try:
            text = reconcile_common.read_text_preserving_newlines(path)
            scan = _scan_body_status(text)
            _display_id, _compare_key, status = _read_item(path)
            if (
                not scan["has_h1"]
                or len(scan["header_hits"]) != 1
                or scan["header_hits_with_cr"]
                or status is None
            ):
                continue
            index, _value = scan["header_hits"][0]
            lines = text.split("\n")
            if index == len(lines) - 1:
                # Last line with no terminator of its own: drop its bytes
                # only, so the previous line keeps its terminator.
                lines[index] = ""
            else:
                # The element carries its own trailing `\r`, if any, so the
                # re-join drops the line and exactly its own terminator.
                del lines[index]
            reconcile_common.write_text_preserving_newlines(path, "\n".join(lines))
        except (OSError, UnicodeDecodeError) as exc:
            _last_body_status_failures.append((drift["file"], str(exc)))
            print(f"  ! {drift['file']}: {exc}")
            continue
        stripped += 1
        print(f"  + {drift['file']}: stripped line {index + 1}")
    return stripped


def _format_body_status_report(result: dict) -> str:
    """Render a human-readable body status drift + anomaly report."""
    return format_drift_report(
        result,
        no_drift_message=(
            "No body status drift detected. No item file carries a header-block status line."
        ),
        no_drift_only_message="No body status drift detected.",
        drift_header=(
            f"Body status drift detected ({len(result['drifts'])} header-block "
            "status line(s) to strip):"
        ),
        drift_line=lambda d: (
            f"  - {d['id']} ({d['status']}): {d['file']} line {d['line']} — "
            f"body says {d['body_status']} ({d['kind']})"
        ),
        anomaly_line=lambda a: (
            f"  - {a['id']} ({a['status']}): {a['file']} line {a['line']} — {a['reason']}"
        ),
    )


def _run_body_status_cli() -> None:
    run_reconcile_cli(
        description=(
            "Detect and strip legacy body status lines: a `**Status:**` line in a "
            "backlog item's header block, where frontmatter `status:` is the only "
            "status field. Reads item files, never an index. --write strips only "
            "the drifted line and never writes an index."
        ),
        load_config=lambda: load_config(Path(__file__)),
        resolve_index_path=lambda config: config["_index_path"],
        missing_index_message=lambda index_path: f"Error: Backlog index not found at {index_path}",
        detect_drift=detect_body_status,
        reconcile=reconcile_body_status,
        format_report=_format_body_status_report,
        json_prefix="reconcile-backlog-body-status-",
        write_message=lambda n: f"Stripped {n} body status line(s).",
    )

    # Same reasoning as the archival failure check in main(): the shared
    # scaffold returns normally whether or not every consented write
    # succeeded, so a failed write fails the command here.
    if _last_body_status_failures:
        print(
            f"Error: {len(_last_body_status_failures)} body status write(s) failed:",
            file=sys.stderr,
        )
        for filename, message in _last_body_status_failures:
            print(f"  {filename}: {message}", file=sys.stderr)
        sys.exit(1)


class _ModeParseError(Exception):
    """Raised instead of exiting when the mode pre-parser rejects an arg."""


class _TolerantModeParser(argparse.ArgumentParser):
    """A pre-parser that never exits the process on a parse error."""

    def error(self, message):
        raise _ModeParseError(message)


def main():
    # Cleared here too, not only in reconcile(): a detect-mode call (no
    # --write) never calls reconcile() at all, so without this reset a
    # PRIOR invocation's recorded failures (same process, e.g. two --write
    # calls in one test run) would otherwise leak into an unrelated,
    # later, non-writing call and fail it for a move it never attempted.
    global _last_reconcile_failures, _last_body_status_failures
    _last_reconcile_failures = []
    _last_body_status_failures = []

    # Mode switch, pre-parsed on its own so the shared scaffold stays
    # unchanged. `allow_abbrev=False`: only the exact flag selects the mode,
    # so an abbreviation that used to be ignored still is. A form the
    # pre-parser rejects (such as `--body-status=1`) never exits here: it
    # falls through to the default mode, which ignores it as it always has.
    mode_parser = _TolerantModeParser(add_help=False, allow_abbrev=False)
    mode_parser.add_argument("--body-status", action="store_true")
    try:
        mode_args, _ = mode_parser.parse_known_args()
        body_status = mode_args.body_status
    except _ModeParseError:
        body_status = False
    if body_status:
        _run_body_status_cli()
        return

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
