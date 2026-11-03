#!/usr/bin/env python3
"""List the open plan and backlog files that name a changed reference file.

After a change edits a rule or reference file, every open plan or backlog
item that cites it is re-verified at closeout. A plan whose status is
COMPLETE is archival and is never rewritten
(`references/verify-before-cite.md` section 9.B.18).

Usage:
    change_closeout.py --changed <basename>... [--changed-file <file>]
                       --plans <dir> --backlog <dir>

A plan is the directory that holds a `*-Master-Plan.md` file. Its status is
the first word of that file's `**Status:**` line. A file under two plan
directories belongs to the deeper one. A backlog item is one `*.md` file
under `--backlog`, and its status is its frontmatter `status:` value.

"Open" means every status that is not finished, read from the plugin's own
vocabularies rather than a list kept here. A plan is open when its status is
in `list_plans.ACTIVE_STATUSES` (PLANNING, READY_TO_EXECUTE, REVIEWED,
APPROVED, NEEDS_FIXES, IN_PROGRESS). A backlog item is open when its status
is in `constants.OPEN_STATUSES` (NOT_STARTED, IN_PROGRESS, PLANNING,
BLOCKED). Any other status (COMPLETE, CLOSED, an unknown word, an empty
value, or no status at all) is skipped and counted on a `skipped:` line, so
an unexpected status is visible and never listed.

A file names a basename when the basename appears with no name character
(a letter, digit, `_`, `-` or `.`) before it and no letter, digit or `_`
after it. So `verify-before-cite.md` matches `references/verify-before-cite.md`
but not `old-verify-before-cite.md`.

Output, LF-only: one `<path>: <status>: <basename>` line per hit, sorted,
then the `skipped:` lines, then one `scanned:` summary line.

Exit codes: 0 always after a scan, whatever it lists; 2 usage error or a
missing directory.
"""

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from constants import OPEN_STATUSES as BACKLOG_OPEN_STATUSES
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from list_plans import ACTIVE_STATUSES as PLAN_OPEN_STATUSES

MASTER_PLAN_GLOB = "*-Master-Plan.md"
NO_STATUS = "(none)"
_STATUS_LINE_RE = re.compile(r"^\*\*Status:\*\*[ \t]*([A-Za-z_]+)", re.MULTILINE)


def _emit(lines: list[str]) -> None:
    """Write lines to stdout with LF endings on every platform."""
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    sys.stdout.flush()


def _read(path: Path) -> str:
    """Read a text file in text mode, so a CRLF checkout reads as LF."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def basename_regex(basename: str) -> re.Pattern:
    """Match `basename` with no name character before it and no word character after it."""
    return re.compile(r"(?<![A-Za-z0-9_.\-])" + re.escape(basename) + r"(?![A-Za-z0-9_])")


def master_plan_status(text: str) -> str:
    """Return the first word of the `**Status:**` line, upper-cased, or NO_STATUS."""
    match = _STATUS_LINE_RE.search(text)
    return match.group(1).upper() if match else NO_STATUS


def backlog_status(text: str) -> str:
    """Return the frontmatter `status:` value, unquoted and upper-cased, or NO_STATUS."""
    split = split_frontmatter_block(text)
    fm = parse_frontmatter_map(split[0]) if split else None
    if not fm or not fm.get("status", "").strip():
        return NO_STATUS
    words = fm["status"].strip().strip("'\"").split()
    return words[0].upper() if words else NO_STATUS


def is_master_plan(path: Path) -> bool:
    """True for `<X>-Master-Plan.md`, false for its `-Master-Plan-Part-N-` siblings."""
    return path.name.endswith("-Master-Plan.md")


def find_plans(plans_dir: Path) -> dict[Path, str]:
    """Map each plan directory to the status read from its Master Plan."""
    plans: dict[Path, str] = {}
    for master in sorted(plans_dir.rglob(MASTER_PLAN_GLOB)):
        if is_master_plan(master):
            plans[master.parent] = master_plan_status(_read(master))
    return plans


def owning_plan(path: Path, plan_dirs: list[Path]) -> Path | None:
    """Return the deepest plan directory that holds `path`, or None."""
    owners = [d for d in plan_dirs if d in path.parents]
    return max(owners, key=lambda d: len(d.parts)) if owners else None


def scan(changed: list[str], plans_dir: Path, backlog_dir: Path) -> dict:
    """Scan the plans and backlog trees and return hits, skip counts and totals."""
    patterns = [(name, basename_regex(name)) for name in changed]
    hits: list[tuple[str, str, str]] = []
    skipped: dict[str, int] = {}

    def record(path: Path, status: str) -> None:
        text = _read(path)
        for name, rx in patterns:
            if rx.search(text):
                hits.append((path.as_posix(), status, name))

    plans = find_plans(plans_dir)
    for status in plans.values():
        if status not in PLAN_OPEN_STATUSES:
            skipped[status] = skipped.get(status, 0) + 1
    plan_dirs = list(plans)
    unowned = 0
    for path in sorted(plans_dir.rglob("*.md")):
        owner = owning_plan(path, plan_dirs)
        if owner is None:
            unowned += 1
        elif plans[owner] in PLAN_OPEN_STATUSES:
            record(path, plans[owner])

    items = 0
    for path in sorted(backlog_dir.rglob("*.md")):
        items += 1
        status = backlog_status(_read(path))
        if status in BACKLOG_OPEN_STATUSES:
            record(path, status)
        else:
            skipped[status] = skipped.get(status, 0) + 1
    return {"hits": sorted(hits), "skipped": skipped, "plans": len(plans),
            "items": items, "unowned": unowned}


def read_changed(args: argparse.Namespace) -> list[str]:
    """Collect the changed basenames from `--changed` and `--changed-file`."""
    names = list(args.changed or [])
    if args.changed_file:
        names.extend(ln.strip() for ln in _read(Path(args.changed_file)).splitlines())
    out: list[str] = []
    for name in names:
        base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if base and base not in out:
            out.append(base)
    return out


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, scan, and print the closeout list."""
    parser = argparse.ArgumentParser(description="List open plans and backlog items naming a changed file.")
    parser.add_argument("--changed", nargs="+", help="changed file basenames")
    parser.add_argument("--changed-file", help="a file holding one basename per line")
    parser.add_argument("--plans", required=True, help="the plans directory")
    parser.add_argument("--backlog", required=True, help="the backlog directory")
    args = parser.parse_args(argv)
    changed = read_changed(args)
    if not changed:
        parser.error("no changed basename given")
    plans_dir, backlog_dir = Path(args.plans), Path(args.backlog)
    for label, folder in (("--plans", plans_dir), ("--backlog", backlog_dir)):
        if not folder.is_dir():
            _emit([f"error: {label} {folder.as_posix()} is not a directory"])
            return 2
    result = scan(changed, plans_dir, backlog_dir)
    lines = [f"{path}: {status}: {name}" for path, status, name in result["hits"]]
    lines += [f"skipped: {status} {n}" for status, n in sorted(result["skipped"].items())]
    lines.append(
        f"scanned: {result['plans']} plans, {result['items']} backlog files, "
        f"{result['unowned']} plan-tree files outside any plan; {len(result['hits'])} hits"
    )
    _emit(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
