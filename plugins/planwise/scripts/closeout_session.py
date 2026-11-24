#!/usr/bin/env python3
"""Close one session's plan files -- safely and idempotently.

`/planwise run` Phase 4 closes a session by editing several plan files that
must agree. This script is the guarded writer for those edits. It reads the
session's Recovery file and writes four kinds of change:

  * the status lines: the Recovery `**Session Status:**` and the orchestration
    `**Status:**` become COMPLETE. `--sprint-status` and `--master-status` set
    the sprint plan and Master Plan `**Status:**` to the value the orchestrator
    decided. Each value must be in the config's `plan_statuses`. Only the
    status token moves, as in `flip_plan_status.py`, which supplies the
    locator and the refusals.
  * the Master Plan `## Session Completion Tracking` row for this session:
    status `✅ COMPLETE`, the summary path and the date.
  * the Recovery `## Cross-Task Coordination Flags` rows. Each flag goes to the
    one front door its Downstream Consumer resolves to:
      - a task or session whose orchestration file exists on disk: that
        orchestration file, under `## Pre-Known Cross-Task Coordination Flags`;
      - a task or session not scaffolded yet: its sprint plan, under
        `## Carried-Forward Coordination Flags`;
      - a follow-up plan not yet written (a consumer naming a plan and no id):
        this Master Plan, under `## Carried-Forward Coordination Flags`.
    Each flag becomes a row of one `### From {session} — recorded {date}`
    block, created when missing. A row already in the block is not added again.
    An existing block for the session with no table (an older list shape) is
    refused, never duplicated.

Without `--apply` the run only reports: it writes nothing. A run refuses, and
writes nothing even with `--apply`, when:

  * a status is outside `plan_statuses`, or a Status line cannot be located;
  * no tracking row matches the session's sprint and session numbers;
  * a flag id repeats, or a Downstream Consumer resolves to no front door, to
    several, or names a sprint whose sessions are already scaffolded;
  * a file has mixed line endings or is not UTF-8, or changed since it was read.

Line endings are never translated: a CRLF file stays CRLF, an LF file stays LF.
The plans index is not written. Run `generate_plans_index.py --write` after.

Exit codes: 0 = clean (including a dry run); 1 = a refusal or a failed write.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import load_config
from flip_plan_status import locate_status_span
from markdown_parser import split_row_cells
from reconcile_common import write_text_preserving_newlines

_SESSION_ID_RE = re.compile(r"^(?P<abbrev>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*?)-S(?P<sprint>\d{2})-(?P<session>\d{2})$")
_ID_IN_TEXT_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?P<abbrev>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*?)-S(?P<sprint>\d{2})"
    r"(?:-(?P<session>\d{2}))?(?:-(?P<task>\d{2}))?(?![A-Za-z0-9])"
)
_SESSION_STATUS_RE = re.compile(r"^\*\*Session Status:\*\*[ \t]*(\S.*)$", re.MULTILINE)
_FLAG_NUMBER_RE = re.compile(r"^F?(\d+)$")
_STATUS_PREFIX = "**Status:** "
_COMPLETE_ROW_STATUS = "✅ COMPLETE"

_TRACKING_HEADING = "Session Completion Tracking"
_FLAGS_HEADING = "Cross-Task Coordination Flags"
_PRE_KNOWN_HEADING = "Pre-Known Cross-Task Coordination Flags"
_CARRIED_HEADING = "Carried-Forward Coordination Flags"

_PRE_KNOWN_INTRO = (
    "These flags were surfaced and reconciled by upstream session orchestrators. Treat each settled measurement "
    "as a validated record: re-measure it for staleness, never re-argue it. Treat each figure about a live "
    "artifact as a baseline that moves with the source: re-measure at dispatch. Treat each carried inference or "
    "recommendation as an input that a downstream gate may overturn."
)

_ORCH_COLUMNS = ("Flag #", "Source Task", "Consuming Task", "Observation", "Recommended Action", "Routed")
_SPRINT_COLUMNS = ("Flag #", "Source Task", "Consuming Session", "Observation", "Recommended Action")
_MASTER_COLUMNS = ("Flag #", "Source Task", "Destination", "Observation", "Recommended Action")


class CloseoutRefusal(Exception):
    """A condition under which the run writes nothing. Not the migration `Refusal` class."""


class Workspace:
    """The files one run reads and edits, held as LF text with each file's line-ending style remembered."""

    def __init__(self) -> None:
        self.original: dict[Path, bytes] = {}
        self.text: dict[Path, str] = {}
        self.crlf: dict[Path, bool] = {}

    def load(self, path: Path) -> str:
        if path not in self.text:
            try:
                data = path.read_bytes()
                raw = data.decode("utf-8")
            except OSError as exc:
                raise CloseoutRefusal(f"cannot read {path}: {exc}") from None
            except UnicodeDecodeError:
                raise CloseoutRefusal(f"{path} is not UTF-8 text -- edit it by hand") from None
            crlf = raw.count("\r\n")
            if crlf and raw.count("\n") != crlf:
                raise CloseoutRefusal(f"{path} has mixed line endings -- fix them by hand")
            self.original[path] = data
            self.crlf[path] = bool(crlf)
            self.text[path] = raw.replace("\r\n", "\n")
        return self.text[path]

    def final(self, path: Path) -> str:
        text = self.text[path]
        return text.replace("\n", "\r\n") if self.crlf[path] else text

    def changed(self) -> list[Path]:
        return [p for p in self.text if self.final(p).encode("utf-8") != self.original[p]]


def _glob_one(plans_dir: Path, name: str) -> Path:
    hits = sorted(plans_dir.glob(f"**/{name}"))
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise CloseoutRefusal(f"{len(hits)} files named {name} -- resolve by hand")
    raise CloseoutRefusal(f"no file named {name} under {plans_dir}")


def _locate_status(text: str, session_line: bool) -> tuple[str, int, int] | str:
    """`(token, start, end)` of the status token on the Status line, or a refusal reason."""
    if not session_line:
        return locate_status_span(text)
    match = _SESSION_STATUS_RE.search(text)
    if match is None:
        return "no **Session Status:** line found"
    result = locate_status_span(_STATUS_PREFIX + match.group(1))
    if isinstance(result, str):
        return result
    token, start, end = result
    shift = match.start(1) - len(_STATUS_PREFIX)
    return token, start + shift, end + shift


def set_status(ws: Workspace, path: Path, want: str, valid: list[str], *, session_line: bool = False) -> str:
    """Set one Status token. Returns `changed` or `unchanged`. Raises `CloseoutRefusal`."""
    if want not in valid:
        raise CloseoutRefusal(f"{want!r} is not in plan_statuses {valid}")
    text = ws.load(path)
    result = _locate_status(text, session_line)
    if isinstance(result, str):
        raise CloseoutRefusal(f"{path.name}: {result}")
    current, start, end = result
    if current == want:
        return "unchanged"
    ws.text[path] = text[:start] + want + text[end:]
    return "changed"


def _heading_span(text: str, heading: str) -> tuple[int, int] | None:
    """Start and end offsets of the `## heading` section, ending before the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}[^\n]*$", text, re.MULTILINE)
    if match is None:
        return None
    following = re.compile(r"^## ", re.MULTILINE).search(text, match.end())
    return match.start(), following.start() if following else len(text)


def _table_rows(lines: list[str], start: int) -> tuple[int, int] | None:
    """Line indexes `(first data row, end)` of the first table at or after `start`, or None.

    The end index is one past the last row. A table needs a header line and a separator line."""
    index = start
    while index < len(lines) and not lines[index].lstrip().startswith("|"):
        index += 1
    if index + 1 >= len(lines) or not lines[index + 1].lstrip().startswith("|"):
        return None
    first = index + 2
    end = first
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return first, end


def _row_text(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def set_tracking_row(ws: Workspace, master: Path, sprint: int, session: int, summary: str, date: str) -> str:
    """Write the COMPLETE tracking row for this session. Returns `changed` or `unchanged`."""
    text = ws.load(master)
    span = _heading_span(text, _TRACKING_HEADING)
    label = f"Sprint-{sprint:02d} Session-{session:02d}"
    if span is None:
        raise CloseoutRefusal(f"{master.name} has no ## {_TRACKING_HEADING} section")
    lines = text.split("\n")
    heading_line = text.count("\n", 0, span[0])
    rows = _table_rows(lines, heading_line + 1)
    if rows is None or rows[0] > text.count("\n", 0, span[1]) + 1:
        raise CloseoutRefusal(f"{master.name} has no parseable ## {_TRACKING_HEADING} table")
    matches = []
    for index in range(*rows):
        cells = split_row_cells(lines[index])
        sprint_cell = re.search(r"Sprint[-\s]0*(\d+)", cells[0]) if len(cells) > 0 else None
        session_cell = re.search(r"Session[-\s]0*(\d+)", cells[1]) if len(cells) > 1 else None
        if sprint_cell and session_cell and int(sprint_cell.group(1)) == sprint and int(session_cell.group(1)) == session:
            matches.append((index, cells))
    if not matches:
        raise CloseoutRefusal(f"no {_TRACKING_HEADING} row for {label} in {master.name} -- add the session's row")
    if len(matches) > 1:
        raise CloseoutRefusal(f"{len(matches)} {_TRACKING_HEADING} rows for {label} in {master.name} -- resolve by hand")
    index, cells = matches[0]
    cells = [*cells, *["-"] * (5 - len(cells))]
    done = [cells[0], cells[1], _COMPLETE_ROW_STATUS, f"`{summary}`"]
    if cells[:4] == done and cells[4] not in ("", "-"):
        return "unchanged"
    lines[index] = _row_text([*done, date, *cells[5:]])
    ws.text[master] = "\n".join(lines)
    return "changed"


def read_flags(text: str) -> list[dict[str, str]]:
    """The Recovery flag rows. An absent section, an empty table or a placeholder row gives no flags."""
    span = _heading_span(text, _FLAGS_HEADING)
    if span is None:
        return []
    lines = text.split("\n")
    rows = _table_rows(lines, text.count("\n", 0, span[0]) + 1)
    if rows is None or rows[0] > text.count("\n", 0, span[1]) + 1:
        return []
    flags: list[dict[str, str]] = []
    seen: set[int] = set()
    for index in range(*rows):
        cells = split_row_cells(lines[index])
        if not cells or all(cell in ("", "-") for cell in cells):
            continue
        if len(cells) != 5:
            raise CloseoutRefusal(f"flag row {index + 1} has {len(cells)} cells, expected 5")
        number = _FLAG_NUMBER_RE.match(cells[0])
        if number is None:
            raise CloseoutRefusal(f"flag row {index + 1}: Flag # {cells[0]!r} is not a number")
        if int(number.group(1)) in seen:
            raise CloseoutRefusal(f"duplicate flag id {number.group(1)} -- renumber the later row")
        seen.add(int(number.group(1)))
        flags.append(dict(zip(("number", "source", "consumer", "observation", "action"), cells, strict=True)))
    return flags


class Destination:
    """The one front door a flag goes to."""

    def __init__(self, kind: str, path: Path, consuming: str) -> None:
        self.kind = kind  # "orchestration", "sprint" or "master"
        self.path = path
        self.consuming = consuming


def resolve_consumer(plans_dir: Path, consumer: str, master: Path) -> Destination:
    """Resolve a Downstream Consumer cell to exactly one front door, or raise `CloseoutRefusal`."""
    found = {}
    for match in _ID_IN_TEXT_RE.finditer(consumer):
        found[match.group(0)] = match
    if not found:
        if re.search(r"\bplan\b", consumer, re.IGNORECASE):
            return Destination("master", master, consumer.strip())
        raise CloseoutRefusal(f"Downstream Consumer {consumer!r} names no task, session, sprint or plan -- name one")
    sessions = {(m["abbrev"], m["sprint"], m["session"]) for m in found.values()}
    if len(sessions) > 1:
        raise CloseoutRefusal(f"Downstream Consumer {consumer!r} names more than one session -- use one row for each")
    abbrev, sprint, session = next(iter(sessions))
    if session is None:
        scaffolded = sorted(plans_dir.glob(f"**/{abbrev}-S{sprint}-[0-9][0-9]-Orchestration.md"))
        if scaffolded:
            raise CloseoutRefusal(
                f"Downstream Consumer {consumer!r} names a sprint with scaffolded sessions -- name the session"
            )
        return Destination("sprint", _glob_one(plans_dir, f"{abbrev}-S{sprint}-Sprint-Plan.md"), f"{abbrev}-S{sprint}")
    session_id = f"{abbrev}-S{sprint}-{session}"
    orchestrations = sorted(plans_dir.glob(f"**/{session_id}-Orchestration.md"))
    if len(orchestrations) > 1:
        raise CloseoutRefusal(f"{len(orchestrations)} files named {session_id}-Orchestration.md -- resolve by hand")
    if orchestrations:
        tasks = sorted(m.group(0) for m in found.values() if m["task"])
        return Destination("orchestration", orchestrations[0], ", ".join(tasks) if tasks else "session")
    return Destination("sprint", _glob_one(plans_dir, f"{abbrev}-S{sprint}-Sprint-Plan.md"), session_id)


def _table_lines(columns: tuple[str, ...]) -> list[str]:
    return [_row_text(list(columns)), "|" + "|".join("-" * (len(c) + 2) for c in columns) + "|"]


def upsert_flag_block(
    text: str, heading: str, columns: tuple[str, ...], source: str, date: str, rows: list[list[str]], *, before: str,
    intro: str = "",
) -> tuple[str, int]:
    """Add the flag rows to the `### From {source}` block of `## heading`. Returns `(text, rows added)`.

    The section and the block are created when missing. A row whose Flag # is already in the block is skipped."""
    span = _heading_span(text, heading)
    block_heading = f"### From {source} — recorded {date}"
    if span is None:
        body = f"## {heading}\n\n" + (intro + "\n\n" if intro else "")
        body += "\n".join([block_heading, "", *_table_lines(columns), *(_row_text(r) for r in rows)]) + "\n"
        anchor = re.search(rf"^## {re.escape(before)}[^\n]*$", text, re.MULTILINE)
        if anchor is None:
            return text.rstrip("\n") + "\n\n---\n\n" + body, len(rows)
        return text[: anchor.start()] + body + "\n---\n\n" + text[anchor.start() :], len(rows)
    start, end = span
    section = text[start:end]
    block = re.search(rf"^### From {re.escape(source)}(?![A-Za-z0-9-])[^\n]*$", section, re.MULTILINE)
    if block is None:
        rule = re.search(r"\n---[ \t]*\n+\Z", section)
        cut = start + (rule.start() if rule else len(section.rstrip("\n")))
        addition = "\n\n" + "\n".join([block_heading, "", *_table_lines(columns), *(_row_text(r) for r in rows)])
        tail = text[cut:]
        return text[:cut].rstrip("\n") + addition + ("\n" if rule else "") + tail, len(rows)
    following = re.compile(r"^#{1,3} ", re.MULTILINE).search(section, block.end())
    block_end = following.start() if following else len(section)
    segment = section[block.end() : block_end]
    lines = segment.split("\n")
    table = _table_rows(lines, 0)
    if table is None:
        raise CloseoutRefusal(f"the existing '### From {source}' block has no table to append to -- add the flag by hand")
    present = {split_row_cells(lines[i])[0] for i in range(*table) if split_row_cells(lines[i])}
    fresh = [r for r in rows if r[0] not in present]
    if not fresh:
        return text, 0
    lines[table[1] : table[1]] = [_row_text(r) for r in fresh]
    return text[: start + block.end()] + "\n".join(lines) + section[block_end:] + text[end:], len(fresh)


def _flag_row(kind: str, flag: dict[str, str], consuming: str) -> list[str]:
    row = [flag["number"], flag["source"], consuming, flag["observation"], flag["action"]]
    return [*row, "pending"] if kind == "orchestration" else row


_BLOCK_SHAPES = {
    "orchestration": (_PRE_KNOWN_HEADING, _ORCH_COLUMNS, "Post-Session Checklist", _PRE_KNOWN_INTRO),
    "sprint": (_CARRIED_HEADING, _SPRINT_COLUMNS, "Change Log", ""),
    "master": (_CARRIED_HEADING, _MASTER_COLUMNS, "References", ""),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="closeout_session.py",
        description=(
            "Close one session's plan files: statuses, the Master Plan tracking row and the coordination flags. "
            "A run without --apply only reports and writes nothing."
        ),
        epilog=(
            "Exit 1 when anything is refused or a write fails. A refused run writes nothing, with or without --apply."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, help="path to the project's config.yaml")
    parser.add_argument("--session", required=True, help="the session id, for example ABC-S01-02")
    parser.add_argument("--apply", action="store_true", help="write the changes (without it the run writes nothing)")
    parser.add_argument("--sprint-status", metavar="STATUS", help="set the sprint plan **Status:** to this value")
    parser.add_argument("--master-status", metavar="STATUS", help="set the Master Plan **Status:** to this value")
    parser.add_argument("--summary-path", metavar="PATH", help="the summary path for the tracking row, relative to the Master Plan folder")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="the date to write (default: today)")
    args = parser.parse_args()

    config = load_config(Path(__file__))
    plans_dir = Path(config["_plans_dir"])
    valid = list(config["plan_statuses"])
    date = args.date or datetime.datetime.now().astimezone().date().isoformat()

    own = _SESSION_ID_RE.match(args.session)
    if own is None:
        print(f"REFUSED: {args.session!r} is not a session id of the form ABC-S01-02")
        return 1
    abbrev, sprint, session = own["abbrev"], own["sprint"], own["session"]

    ws = Workspace()
    lines: list[str] = []
    refusals: list[str] = []

    def attempt(label: str, action) -> object:
        try:
            result = action()
        except CloseoutRefusal as refusal:
            refusals.append(f"  {label}: REFUSED: {refusal}")
            return None
        lines.append(f"  {label}: {result}" if isinstance(result, str) else f"  {label}")
        return result

    try:
        recovery = _glob_one(plans_dir, f"{args.session}-Recovery.md")
        session_dir = recovery.parent
        master_dir = session_dir.parent.parent
        masters = sorted(master_dir.glob("*-Master-Plan.md"))
        if len(masters) != 1:
            raise CloseoutRefusal(f"{len(masters)} Master Plans in {master_dir} -- expected exactly one")
        master = masters[0]
        orchestration = session_dir / f"{args.session}-Orchestration.md"
        sprint_plan = session_dir.parent / f"{abbrev}-S{sprint}-Sprint-Plan.md"
    except CloseoutRefusal as refusal:
        print(f"REFUSED: {refusal}")
        return 1

    attempt(f"{recovery.name} Session Status", lambda: set_status(ws, recovery, "COMPLETE", valid, session_line=True))
    attempt(f"{orchestration.name} Status", lambda: set_status(ws, orchestration, "COMPLETE", valid))
    if args.sprint_status:
        attempt(f"{sprint_plan.name} Status", lambda: set_status(ws, sprint_plan, args.sprint_status, valid))
    if args.master_status:
        attempt(f"{master.name} Status", lambda: set_status(ws, master, args.master_status, valid))
    summary = args.summary_path or (session_dir / "Outputs" / f"{args.session}-Summary.md").relative_to(master_dir).as_posix()
    attempt(
        f"{master.name} tracking row",
        lambda: set_tracking_row(ws, master, int(sprint), int(session), summary, date),
    )

    flags: list[dict[str, str]] = []
    try:
        flags = read_flags(ws.load(recovery))
    except CloseoutRefusal as refusal:
        refusals.append(f"  {recovery.name} flags: REFUSED: {refusal}")
    routes: list[str] = []
    for flag in flags:
        try:
            destination = resolve_consumer(plans_dir, flag["consumer"], master)
        except CloseoutRefusal as refusal:
            refusals.append(f"  flag {flag['number']}: REFUSED: {refusal}")
            continue
        heading, columns, before, intro = _BLOCK_SHAPES[destination.kind]

        def write_flag(flag=flag, destination=destination, heading=heading, columns=columns, before=before, intro=intro):
            text, added = upsert_flag_block(
                ws.load(destination.path), heading, columns, args.session, date,
                [_flag_row(destination.kind, flag, destination.consuming)], before=before, intro=intro,
            )
            ws.text[destination.path] = text
            return "changed" if added else "unchanged"

        attempt(f"flag {flag['number']} -> {destination.path.name}", write_flag)
        routes.append(f"flag {flag['number']} -> {destination.path.relative_to(plans_dir).as_posix()}")

    if refusals:
        print("refused: nothing written")
        for line in [*lines, *refusals]:
            print(line)
        return 1

    changed = ws.changed()
    failed: list[str] = []
    if args.apply:
        for path in changed:
            try:
                if path.read_bytes() != ws.original[path]:
                    failed.append(f"  {path.name}: REFUSED: changed since read -- re-run")
                    continue
                write_text_preserving_newlines(path, ws.final(path))
            except OSError as exc:
                failed.append(f"  {path.name}: FAILED: {exc}")
    print(f"{'changed' if args.apply else 'would change'}: {len(changed) - len(failed)} file(s)")
    for line in lines:
        print(line)
    for route in routes:
        print(f"  {route}")
    for line in failed:
        print(line)
    if not args.apply:
        print("dry run: nothing written. Re-run with --apply to write.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
