#!/usr/bin/env python3
"""Flip a Master Plan's `**Status:**` token -- safely and idempotently.

The plans index is generated, so the Master Plan's own `**Status:**` line is
the one thing a person edits to change a plan's row. This script is the
guarded writer for that line. Each mapped Path is resolved to its Master Plan
through `parse_plans.enumerate_master_plans`, and only the status TOKEN of the
first `**Status:**` line is rewritten.

The load-bearing property is the REFUSALS, not the rewrite. A plan is refused,
and its file left untouched, when:

  * its Path matches zero Master Plans, or more than one;
  * the target is outside the config's `plan_statuses`, or the map gives the
    same Path two different statuses;
  * the Status token cannot be located, or the value reads as multi-word
    (`IN PROGRESS`, `Not started`) or glues text onto the token (`IN-PROGRESS`);
  * the Master Plan, or a folder between the plans directory and it, is a
    symlink or junction, or the file changed since it was read.

A plan already at the target is reported `unchanged` and not rewritten.

Write discipline, so the diff stays auditable:

  * Only the token span moves. A leading emoji or `*` stays, and so does all
    the trailing prose. The span is the capital run that
    `parse_plans.normalize_status` reads, WITHOUT its trailing underscores (a
    closing italic `_` stays), or the leading word of a title-case value such
    as `Complete`.
  * `status_value_refusal(value)` reports, without writing, whether a raw
    Status value is one the writer would flip. `plan_path_refusal(plans_dir,
    path)` does the same for a Path: the same Master Plan lookup and link
    check the writer runs.
  * Line endings are never translated (CRLF stays CRLF).
  * The date the reader uses is bumped to today: the last `*Last Updated:`
    footer line, else the `**Last Updated:**` header line. With neither, the
    dates are left alone and the run says so.
  * Each plan is handled on its own: an OSError on one is reported as FAILED
    and the rest still run.

Exit codes: 0 = clean; 1 = a Path was refused, a write failed, or the map is
unreadable.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
import recovery_surfaces
from config_loader import load_config
from parse_plans import (
    _DATE_RE,
    _FOOTER_LINE_RE,
    _HEADER_UPDATED_LINE_RE,
    _LEADING_NON_ALNUM_RE,
    _STATUS_LINE_RE,
    _TOKEN_RUN_RE,
    enumerate_master_plans,
    master_plan_path_for,
)
from reconcile_common import write_text_preserving_newlines

_WORD_RUN_RE = re.compile(r"[A-Za-z0-9_]+")
_FIRST_WORD_RE = re.compile(r"\S+\s*")
_COMMENT_RE = re.compile(r"\s#.*$")
_MARKUP_TAIL_RE = re.compile(r"[*`]+$")
_MARKUP_HEAD_RE = re.compile(r"[*`]+")

EPILOG = """\
MAP_FILE: one `{Path as in the index}: {STATUS}` per line, read as UTF-8
(a BOM is accepted). The Path ends in a slash, as the index prints it.

  MyPlan/: COMPLETE
  MyPlan/Exec-Rollout/: BLOCKED

Comments: a line whose first non-space character is `#`, or the text from a
` #` (whitespace, then `#`) to the end of an entry, is dropped. This happens
BEFORE the line is split at its first `:`. A `#` glued inside a Path
(`C#Port/`) stays part of it. Blank lines are ignored.

Repeats: `Alpha` and `Alpha/` name one Path. The same Path with the same
status twice is applied once, with a note. The same Path with different
statuses is refused, naming each line, and nothing is written for it.

Exit 1 when any Path is refused or fails, or the map is not UTF-8.
"""


def _normalize_plan_path(plan_path: str) -> str:
    """The map's form of a Path: forward slashes and a trailing slash, so `Alpha` and `Alpha/` are one."""
    plan_path = plan_path.replace("\\", "/")
    return plan_path if plan_path.endswith("/") else plan_path + "/"


def read_map(path: Path) -> tuple[dict[str, str], dict[str, list[tuple[int, str]]], list[str]]:
    """Read the map. Returns `(mapping, conflicts, notes)`.

    A Path (normalized, so `Alpha` and `Alpha/` are one) given the same status
    twice is kept once and noted. A Path given different statuses lands in
    `conflicts` as its `(line number, status)` list and not in `mapping`."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise SystemExit(f"{path}: the map file must be UTF-8 text (not UTF-16 or ANSI)") from None
    mapping: dict[str, str] = {}
    seen: dict[str, list[tuple[int, str]]] = {}
    notes: list[tuple[str, str]] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = _COMMENT_RE.sub("", raw).strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise SystemExit(f"{path}:{n}: expected 'Path: STATUS', got {raw!r}")
        plan_path, status = (p.strip() for p in line.split(":", 1))
        if not plan_path or not status:
            raise SystemExit(f"{path}:{n}: expected 'Path: STATUS', got {raw!r}")
        plan_path = _normalize_plan_path(plan_path)
        lines_for_path = seen.setdefault(plan_path, [])
        same = next((m for m, s in lines_for_path if s == status), None)
        if same is not None:
            notes.append((plan_path, f"duplicate map line {n} (same as line {same}) -- applied once"))
        lines_for_path.append((n, status))
        mapping.setdefault(plan_path, status)
    conflicts = {p: ls for p, ls in seen.items() if len({s for _, s in ls}) > 1}
    for plan_path in conflicts:
        del mapping[plan_path]
    return mapping, conflicts, [f"  {p}: {text}" for p, text in notes if p not in conflicts]


def parse_map(path: Path) -> dict[str, str]:
    """The Path-to-status mapping, without any Path the map contradicts."""
    return read_map(path)[0]


def _bump_date(text: str, today: str) -> tuple[str, bool]:
    """Replace the date on the line the reader uses. `(text, False)` when no
    such line carries a date, so the caller can say the dates were left alone."""
    footers = list(_FOOTER_LINE_RE.finditer(text))
    candidates = [footers[-1]] if footers else []
    header = _HEADER_UPDATED_LINE_RE.search(text)
    if header:
        candidates.append(header)
    for line_match in candidates:
        date = _DATE_RE.search(line_match.group(0))
        if date:
            start = line_match.start() + date.start()
            return text[:start] + today + text[start + len(date.group(0)) :], True
    return text, False


def _span_in_value(value: str) -> tuple[str, int] | str:
    """Decide the rewrite span inside one raw Status value: `(token, offset)`
    where `offset` is the token's start in `value`, or a refusal reason.

    The span is the token WITHOUT its trailing underscores. A closing italic
    `_` is markup, so it stays byte-for-byte; the reader strips it anyway.

    What may follow the token and stay as prose: the end of the value, or
    whitespace and then a non-alphanumeric character (`—`, `(`, `- `). Text
    glued to the token refuses. Closing markup (`*` or a backtick) is skipped
    only when it mirrors the markup that opens the token directly (`**X**`,
    `` `X` ``). Whitespace then a letter refuses, because a bolded first word
    (`**IN** PROGRESS`) is a multi-word status. Whitespace then a digit is
    prose (`COMPLETE 2026-10-01`), which the reader also reads as one token.
    The one exception is a number followed directly by a capital word
    (`IN 2 PROGRESS`): that still looks like a status split by a number, so
    it refuses, and the refusal says so. The other exception is an
    underscore identifier (`ON_hold since March`): it is one name, and the
    word after it is prose."""
    prefix = _LEADING_NON_ALNUM_RE.match(value)
    prefix_len = len(prefix.group(0)) if prefix else 0
    rest = value[prefix_len:]
    token = _TOKEN_RUN_RE.match(rest) or _WORD_RUN_RE.match(rest)
    if token is None:
        return f"cannot find a status token in {value.strip()!r}"
    run = token.group(0)
    core = run.rstrip("_")
    after = rest[len(run) :]
    opener = _MARKUP_TAIL_RE.search(value[:prefix_len].rstrip("_"))
    closer = _MARKUP_HEAD_RE.match(after)
    tail = after
    if opener and closer and closer.group(0) == opener.group(0)[::-1]:
        tail = after[closer.end() :]
    if tail and not tail[0].isspace():
        return f"{value.strip()!r} glues text onto the status token -- edit by hand"
    follow = tail.lstrip()
    if follow and "_" not in core:
        if follow[0].isdigit():
            first_word = _FIRST_WORD_RE.match(follow)
            if _TOKEN_RUN_RE.match(follow[first_word.end() :]):
                return f"{value.strip()!r} reads as a multi-word status, with a number between its words -- edit by hand"
        elif follow[0].isalnum():
            return f"{value.strip()!r} reads as a multi-word status -- edit by hand"
    return core, prefix_len


def status_value_refusal(value: str) -> str | None:
    """Return None when the writer can flip this raw Status value (group 1 of
    `_STATUS_LINE_RE`), else a short refusal reason. Side-effect free. This is
    the same decision `locate_status_span` makes, not a second copy of it."""
    result = _span_in_value(value)
    return result if isinstance(result, str) else None


def locate_status_span(raw: str) -> tuple[str, int, int] | str:
    """Return `(current_token, span_start, span_end)` for the first
    `**Status:**` line, or a refusal reason string. Never writes anything."""
    match = _STATUS_LINE_RE.search(raw)
    if match is None:
        return "no **Status:** line found"
    result = _span_in_value(match.group(1))
    if isinstance(result, str):
        return result
    core, offset = result
    start = match.start(1) + offset
    return core, start, start + len(core)


def _master_plans_by_path(plans_dir: Path) -> dict[str, list]:
    by_path: dict[str, list] = {}
    for entry in enumerate_master_plans(plans_dir):
        by_path.setdefault(entry.path, []).append(entry)
    return by_path


def _entry_refusal(entries: list) -> str | None:
    """The refusal when `entries` (the Master Plans one Path resolves to) is not exactly one."""
    if len(entries) == 1:
        return None
    if entries:
        return f"{len(entries)} Master Plans claim this Path -- resolve by hand"
    return "no Master Plan found for this Path"


def _plan_file(plans_dir: Path, plan_path: str, entry) -> Path:
    file = master_plan_path_for(plans_dir, plan_path, entry.abbrev)
    return file if file.exists() else entry.file


def _link_refusal(plans_dir: Path, file: Path) -> str | None:
    """The refusal when `file`, or a folder between `plans_dir` and it, is a symlink or junction. The plans
    directory itself is the configured root and is not checked. Uses the shared `recovery_surfaces.is_link`,
    so the writer and every other surface read a link the same way. An entry that cannot be examined refuses."""
    try:
        parts = file.relative_to(plans_dir).parts
        chain = [plans_dir.joinpath(*parts[:depth]) for depth in range(1, len(parts) + 1)]
    except ValueError:
        chain = [file]
    for part in chain:
        try:
            linked = recovery_surfaces.is_link(part)
        except OSError as exc:
            return f"cannot examine {part}: {exc} -- edit the real file by hand"
        if linked:
            return f"{part} is a symlink or junction -- edit the real file by hand"
    return None


def plan_path_refusal(plans_dir: Path, path: str) -> str | None:
    """Return None when the writer can reach the Master Plan for this Path in `plans_dir`, else a short
    refusal reason: zero or several Master Plans on the Path, or a link on the way to the file. Side-effect
    free. This is the same lookup and link check `main` runs for each mapped Path, not a second copy of
    them. It says nothing about the Status value (see `status_value_refusal`) or the file's contents."""
    plans_dir = Path(plans_dir)
    plan_path = _normalize_plan_path(path)
    entries = _master_plans_by_path(plans_dir).get(plan_path, [])
    reason = _entry_refusal(entries)
    if reason is not None:
        return reason
    return _link_refusal(plans_dir, _plan_file(plans_dir, plan_path, entries[0]))


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="flip_plan_status.py",
        description="Flip a Master Plan's **Status:** token, keeping the prose and line endings.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, help="path to the project's config.yaml")
    parser.add_argument("map_file", metavar="MAP_FILE", help="one 'Path: STATUS' per line")
    parser.add_argument("--dry-run", action="store_true", help="report the changes without writing")
    args = parser.parse_args()

    config = load_config(Path(__file__))
    plans_dir = Path(config["_plans_dir"])
    valid = list(config["plan_statuses"])
    target, conflicts, notes = read_map(Path(args.map_file))

    by_path = _master_plans_by_path(plans_dir)

    today = datetime.datetime.now().astimezone().date().isoformat()
    lines: list[str] = []
    pending: list[tuple[int, Path, bytes, str]] = []  # (line index, file, bytes read, new text)
    counts = {"changed": 0, "unchanged": 0, "refused": 0, "failed": 0}

    def refuse(plan_path: str, why: str) -> None:
        lines.append(f"  {plan_path}: REFUSED: {why}")
        counts["refused"] += 1

    lines.extend(notes)
    for plan_path, given in conflicts.items():
        refuse(plan_path, "the map gives different statuses: " + ", ".join(f"line {n} {s}" for n, s in given))

    for plan_path, want in target.items():
        entries = by_path.get(plan_path, [])
        reason = _entry_refusal(entries)
        if reason is not None:
            refuse(plan_path, reason)
            continue
        if want not in valid:
            refuse(plan_path, f"{want!r} is not in plan_statuses {valid}")
            continue
        file = _plan_file(plans_dir, plan_path, entries[0])
        reason = _link_refusal(plans_dir, file)
        if reason is not None:
            refuse(plan_path, reason)
            continue
        try:
            data = _read_bytes(file)
            raw = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            lines.append(f"  {plan_path}: FAILED: cannot read {file}: {exc}")
            counts["failed"] += 1
            continue
        result = locate_status_span(raw)
        if isinstance(result, str):
            refuse(plan_path, result)
            continue
        current, start, end = result
        if current == want:
            lines.append(f"  {plan_path}: unchanged (already {want})")
            counts["unchanged"] += 1
            continue
        spliced, bumped = _bump_date(raw[:start] + want + raw[end:], today)
        note = "" if bumped else " (no dated Last Updated line; dates left alone)"
        pending.append((len(lines), file, data, spliced))
        lines.append(f"  {plan_path}: {current} -> {want}{note}")
        counts["changed"] += 1

    if not args.dry_run:
        for index, file, data, spliced in pending:
            name = lines[index].split(":", 1)[0].strip()
            try:
                if _read_bytes(file) != data:
                    lines[index] = f"  {name}: REFUSED: {file} changed since read -- re-run"
                    counts["changed"] -= 1
                    counts["refused"] += 1
                    continue
                write_text_preserving_newlines(file, spliced)
            except OSError as exc:
                lines[index] = f"  {name}: FAILED: {file}: {exc}"
                counts["changed"] -= 1
                counts["failed"] += 1

    print(f"{'would change' if args.dry_run else 'changed'}: {counts['changed']}")
    print(f"unchanged: {counts['unchanged']}  refused: {counts['refused']}  failed: {counts['failed']}")
    for line in lines:
        print(line)

    if counts["changed"] and not args.dry_run:
        plugin_root = Path(__file__).resolve().parent.parent
        print(
            f'regenerate the index: python "{plugin_root.as_posix()}/scripts/generate_plans_index.py" '
            f'--config "{args.config}" --write'
        )

    return 1 if counts["refused"] or counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
