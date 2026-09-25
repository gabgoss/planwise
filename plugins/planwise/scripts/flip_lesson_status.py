#!/usr/bin/env python3
"""Flip a lesson file's frontmatter `status:` — safely and idempotently.

This script no longer opens the lessons index at all. The lessons directory
and its `Archive/` come from `config.yaml`, and each mapped id is resolved
straight to its own lesson FILE through `parse_lessons.lesson_files`. The
status word is rewritten inside that file's own frontmatter, not in an
index row.

The load-bearing property is still NOT the rewrite. It is the REFUSALS:

  * an id claimed by zero lesson files, or by more than one, is refused
    outright — a missing or ambiguous target must never be guessed at;
  * a file already at the target status is skipped, not rewritten;
  * a file at a landed status (`rule` / `applied`) is NEVER downgraded to
    an earlier status, even when the caller's map says so — a landed lesson
    that a stale map wants to un-land is a caller bug, and silently obeying
    it destroys the audit trail the Rule Promotion Log depends on;
  * a file with no parseable `status:` line inside its frontmatter bounds
    is reported rather than skipped in silence.

Every decision is printed. A run that changes nothing prints why for each
id, so the operator can tell "already correct" apart from "never matched".

Two write-discipline guarantees make the diff auditable, because the audit
trail is the whole point of the refusals above:

  * **Only the status WORD is rewritten.** The rest of the `status:` line
    is spliced back byte-for-byte, so any trailing carriage return on that
    line survives untouched.
  * **Line endings are never translated.** Reading and writing through
    ``reconcile_common``'s newline-preserving pair keeps a CRLF file CRLF
    and an LF file LF. A plain ``read_text``/``write_text`` pair round-trips
    through Python's universal-newline translation and rewrites EVERY line
    to the running platform's ``os.linesep`` — turning a one-word flip into
    a whole-file diff on the very lines the refusals just declined to touch.

## Finding the frontmatter bounds on a CRLF file

`frontmatter_parser.split_frontmatter_block` locates the `---` fences with
an LF-only pattern, so it cannot find the fence at all in a raw CRLF file.
This module never calls it: it walks the file's own lines (each may carry a
trailing `\r`, split on `\n` alone, exactly like the newline-preserving read
this script already uses) and compares each fence line with its own
trailing `\r` stripped for the comparison only. The returned splice always
targets the ORIGINAL line, `\r` included, so a CRLF file's line endings
survive the rewrite untouched.

Usage:
    flip_lesson_status.py --config CONFIG MAP_FILE [--dry-run]

MAP_FILE is one `LL-{NNN}: status` per line; `#` comments and blank lines
ignored:

    # landed upstream, verified by content grep
    LL-{NNN}: rule
    LL-{NNN+1}: promoted

Exit codes: 0 = clean; 1 = at least one id not found, ambiguous, unparseable
or refused (investigate before trusting the run).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Sibling-module import. The newline-preserving read/write pair is the
# shared destructive-write discipline (see reconcile_common's module
# docstring); it is defined once there and reused by every script that
# rewrites a user's file in place, rather than re-derived per script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from generate_lessons_index import _strip_quotes
from parse_lessons import format_id, lesson_files
from reconcile_common import (
    read_text_preserving_newlines,
    write_text_preserving_newlines,
)

VALID = ("documented", "promoted", "rule", "applied", "orphaned")
LANDED = ("rule", "applied")

# Matches a frontmatter `status:` line and captures only the value WORD
# (group 2) so the splice below can replace exactly that span. `\s` in
# Python's `re` module matches `\r`, so `\S+` never swallows a line's
# trailing carriage return — the CRLF fixture test in
# tests/test_flip_lesson_status.py pins this directly.
_STATUS_VALUE_RE = re.compile(r"^(\s*status:\s*)(\S+)")


def _frontmatter_bounds_by_line(lines: list[str]) -> tuple[int, int] | None:
    """Return `(start, end)` line indices bounding the frontmatter block —
    `lines[start]` and `lines[end]` are the two `---` fence lines, each
    compared with its own trailing `\\r` stripped. `None` when `lines[0]`
    is not a fence line, or no closing fence is found.
    """
    if not lines or lines[0].rstrip("\r") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r") == "---":
            return 0, i
    return None


def _flip_status_in_frontmatter(raw: str, new_status: str) -> tuple[str, str] | None:
    """Return `(current_status, spliced_text)`, or `None` when no parseable
    `status:` line exists inside the frontmatter bounds. `spliced_text` has
    ONLY the status word replaced — everything else in `raw`, every line
    ending included, is copied back verbatim. Never writes anything; the
    caller decides whether the flip is allowed before committing it.

    The captured value is unquoted with `generate_lessons_index._strip_quotes`
    (the same quote rules the generator applies when reading frontmatter,
    imported rather than duplicated) before it is compared against `VALID`/
    `LANDED`/`want` — a quoted `status: "rule"` reads unquoted as `rule` and
    the LANDED refusal below sees it correctly, instead of comparing the
    literal `'"rule"'` against an unquoted tuple and silently missing every
    quoted value. The rewrite always WRITES THE NEW VALUE UNQUOTED: the
    replaced span is the raw captured token (quotes included, when
    present), so a quoted old value's quotes are dropped along with it
    rather than round-tripped — simpler than re-deriving a quote style to
    preserve, and it matches how the generator itself renders every other
    frontmatter value it writes.
    """
    lines = raw.split("\n")
    bounds = _frontmatter_bounds_by_line(lines)
    if bounds is None:
        return None
    start, end = bounds
    for i in range(start + 1, end):
        m = _STATUS_VALUE_RE.match(lines[i])
        if m:
            current = _strip_quotes(m.group(2))
            lines[i] = lines[i][: m.start(2)] + new_status + lines[i][m.end(2) :]
            return current, "\n".join(lines)
    return None


def parse_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise SystemExit(f"{path}:{n}: expected 'LL-NNN: status', got {raw!r}")
        lid, status = (p.strip() for p in line.split(":", 1))
        m = re.fullmatch(r"LL-(\d+)", lid)
        if not m:
            raise SystemExit(f"{path}:{n}: bad lesson id {lid!r}")
        lid = format_id(int(m.group(1)))
        if status not in VALID:
            raise SystemExit(f"{path}:{n}: status {status!r} not in {VALID}")
        mapping[lid] = status
    return mapping


def main() -> int:
    argv = sys.argv[1:]
    dry_run = False
    positionals: list[str] = []
    unknown: list[str] = []
    config_arg: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--config":
            if i + 1 < len(argv):
                config_arg = argv[i + 1]
            i += 2
            continue
        if arg == "--dry-run":
            dry_run = True
            i += 1
            continue
        if arg.startswith("--"):
            unknown.append(arg)
            i += 1
            continue
        positionals.append(arg)
        i += 1
    # An unrecognized flag must never be swallowed: this script's only
    # safety rail is --dry-run, and silently ignoring a misspelled one
    # ("--dryrun") turns a requested preview into an unrequested write.
    if unknown:
        raise SystemExit(
            f"unknown option(s): {', '.join(unknown)} — the only supported "
            f"flags are --config and --dry-run\n{__doc__}"
        )
    if config_arg is None or len(positionals) != 1:
        raise SystemExit(__doc__)

    config = load_config(Path(__file__))
    lessons_dir = config.get("_lessons_dir")
    if lessons_dir is None:
        raise SystemExit("config.yaml declares no project.lessons_dir")
    archive_dir = lessons_dir / "Archive"

    target = parse_map(Path(positionals[0]))

    id_to_paths: dict[int, list[Path]] = {}
    for lesson_id, path in lesson_files(lessons_dir, archive_dir):
        id_to_paths.setdefault(lesson_id, []).append(path)

    changed: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    writes: dict[Path, str] = {}

    for lid, want in target.items():
        numeric_id = int(lid.split("-", 1)[1])
        paths = id_to_paths.get(numeric_id, [])
        if len(paths) != 1:
            reason = (
                f"REFUSED: {len(paths)} lesson files claim this id — "
                "resolve the duplicate by hand"
                if paths
                else "REFUSED: no lesson file found for this id"
            )
            skipped.append((lid, reason))
            continue
        path = paths[0]
        raw = read_text_preserving_newlines(path)
        result = _flip_status_in_frontmatter(raw, want)
        if result is None:
            skipped.append((lid, "no parseable status: line in frontmatter — check by hand"))
            continue
        current, spliced = result
        if current == want:
            skipped.append((lid, f"already {want}"))
            continue
        if current in LANDED and want not in LANDED:
            skipped.append((lid, f"REFUSED: will not downgrade landed {current!r} -> {want!r}"))
            continue
        changed.append((lid, current, want))
        writes[path] = spliced

    if not dry_run:
        for path, spliced in writes.items():
            write_text_preserving_newlines(path, spliced)

    print(f"{'would change' if dry_run else 'changed'}: {len(changed)}")
    for lid, a, b in changed:
        print(f"  {lid}: {a} -> {b}")
    if skipped:
        print(f"skipped: {len(skipped)}")
        for lid, why in skipped:
            print(f"  {lid}: {why}")

    if changed and not dry_run:
        script_dir = Path(__file__).resolve().parent
        print(
            f"Regenerate the index: python {script_dir}/generate_lessons_index.py "
            f"--config {config_arg} --write"
        )

    problems = sum(1 for _, why in skipped if why.startswith(("REFUSED", "no parseable")))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
