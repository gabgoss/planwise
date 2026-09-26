#!/usr/bin/env python3
"""Recognise-or-refuse scans and tree-state checks for `migrate_backlog_index.py`.

`scan_index` walks the whole index, to end of file, and names every line
that regeneration would drop and the migrator does not move. It also returns
the edges of a legacy `## Dependencies` table, so the caller can compare
each edge with item frontmatter, and, on request, the soft-dependency
bullets under that heading. `git_state` reports the working-tree
state. It treats a git-ignored input as an unknown state, because git
cannot vouch for a file it ignores.
"""
import re
import subprocess
from pathlib import Path

import migrate_backlog_repairs as repairs
import migrate_backlog_support as sup

METADATA_PREFIXES = ("**Purpose:**", "**Last Updated:**")  # preamble lines with no item content
SHARDS, DEPENDENCIES = "## Shards", "## Dependencies"
_RANGE_RE = re.compile(r"^\d{3,}-\d{3,}$")
_LINK_ONLY_RE = re.compile(r"^\[[^\]]+\]\([^)]+\)$")


def _table_end(lines: list, start: int) -> int:
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        i += 1
    return i


def _table_header_ok(lines: list, start: int, end: int, expected: list) -> bool:
    header = [c.lower() for c in sup.row_cells(lines[start])]
    return header == expected and start + 1 < end and bool(sup.SEP_RE.match(lines[start + 1].strip()))


def _dependency_table(lines: list, start: int, end: int, problems: list, edges: list) -> None:
    if not _table_header_ok(lines, start, end, ["id", "blocks"]):
        problems.append(f"line {start + 1}: unrecognised table under '{DEPENDENCIES}' (expected '| ID | Blocks |')")
        return
    for i in range(start + 2, end):
        cells = sup.row_cells(lines[i])
        ok = len(cells) == 2 and sup.plain(cells[0]).isdigit() and sup.blocks_text_ok(cells[1])
        if not ok:
            problems.append(f"line {i + 1}: unrecognised '{DEPENDENCIES}' row {lines[i].strip()[:60]!r}")
            continue
        source = sup.plain(cells[0]).zfill(3)
        edges += [(i + 1, source, target) for target in sup.ids_in(cells[1])]


def _shards_table(lines: list, start: int, end: int, problems: list) -> None:
    if not _table_header_ok(lines, start, end, ["range", "file"]):
        problems.append(f"line {start + 1}: unrecognised table under '{SHARDS}' (expected '| Range | File |')")
        return
    for i in range(start + 2, end):
        cells = sup.row_cells(lines[i])
        if len(cells) != 2 or not _RANGE_RE.match(cells[0]) or not _LINK_ONLY_RE.match(cells[1]):
            problems.append(f"line {i + 1}: unrecognised '{SHARDS}' row {lines[i].strip()[:60]!r}")


def _dependency_notes(lines: list, candidates: set, problems: list) -> list:
    """Sort the non-table lines under `## Dependencies` into soft-dependency
    bullets, bold heading lines (structural, dropped), and problems."""
    masked = [lines[i].rstrip("\r") if i in candidates else "" for i in range(len(lines))]
    found, covered = [], set()
    for line_no, owner, body in repairs.dependency_bullets(masked):
        count = body.count("\n") + 1
        covered.update(range(line_no, line_no + count))
        found.append({"kind": "bullet", "line": line_no + 1, "count": count, "owner": owner, "text": body})
    for i in sorted(candidates - covered):
        if repairs._BOLD_HEADING_RE.match(masked[i]):
            found.append({"kind": "heading", "line": i + 1, "count": 1, "owner": None, "text": masked[i].strip()})
        else:
            problems.append(f"line {i + 1}: text under '{DEPENDENCIES}', {lines[i].strip()[:60]!r}")
    return sorted(found, key=lambda entry: entry["line"])


def scan_index(text: str, header_idx: int, extract_notes: bool = False):
    """Return (problems, dependency edges, dependency notes). Recognised
    content: one `# ` title and metadata lines in the preamble; the items
    table; a Shards table; a Dependencies table; `---`; blank lines; the
    footer. Every other line, anywhere in the file, is a problem naming its
    line number. With `extract_notes`, a `- ` bullet under `## Dependencies`
    is returned as a note (kind "bullet") instead, and a bold heading line
    there is structural (kind "heading"); the list is empty otherwise."""
    lines = text.split("\n")
    problems, edges, seen, candidates = [], [], set(), set()
    section, titled, i = None, False, 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("## "):
            known = s in (sup.LEGACY_HEADING, SHARDS, DEPENDENCIES) and s not in seen
            section = s if known else "?"
            if not known:
                problems.append(f"line {i + 1}: section {s!r}")
            seen.add(s)
            i += 1
            continue
        if i == header_idx:
            i = _table_end(lines, i)
            continue
        if s.startswith("|") and section in (SHARDS, DEPENDENCIES):
            end = _table_end(lines, i)
            if section == DEPENDENCIES:
                _dependency_table(lines, i, end, problems, edges)
            else:
                _shards_table(lines, i, end, problems)
            i = end
            continue
        if section is None and s.startswith("# ") and not titled:
            titled = True
        elif s in ("", "---") or s.startswith("*Last Updated:"):
            pass
        elif section is None and s.startswith(METADATA_PREFIXES):
            pass
        elif section is None:
            problems.append(f"line {i + 1}: preamble text {s[:60]!r}")
        elif section == sup.LEGACY_HEADING:
            where = "between '## Backlog Items' and its table" if i < header_idx else "after the table"
            problems.append(f"line {i + 1}: text {where}, {s[:60]!r}")
        elif section == DEPENDENCIES and extract_notes:
            candidates.add(i)
        elif section != "?":
            problems.append(f"line {i + 1}: text under '{section}', {s[:60]!r}")
        i += 1
    notes = _dependency_notes(lines, candidates, problems) if candidates else []
    return problems, edges, notes


def missing_edges(edges: list, items: dict) -> list:
    """Name every Dependencies edge absent from its source item's frontmatter `blocks:`."""
    by_id = {item["id"]: item for item in items.values()}
    return [f"line {line_no}: {src} blocks {dst}" for line_no, src, dst in edges
            if dst not in by_id.get(src, {}).get("blocks", ())]


def tree_gate(dirty: set, plan: dict, paths: tuple, index_path: Path, force: bool):
    """Return a refusal message, or None when the run may proceed. An
    interrupted migration of this index exempts exactly the paths it owns:
    the index, the changelog, the ledger, each item file the plan writes,
    and each path the interrupted run's journal says it was replacing."""
    if not dirty or force:
        return None
    owned = set()
    journal = sup.journal_paths(paths[1]) if len(paths) > 1 else set()
    if plan["interrupted"] or journal:
        owned = {p.resolve() for p in (index_path, *paths[:2])} | {d["path"] for d in plan["dests"]} | journal
        owned |= {p.resolve() for p, _text in plan.get("outputs", ())}
    others = sorted(str(p) for p in dirty - owned)
    if not others:
        return None
    return (f"working tree has uncommitted changes outside this migration ({len(others)} path(s), "
            f"e.g. {', '.join(others[:3])}); commit/stash first or pass --force.")


def write_gate(project_root: Path, inputs: list, allow_untracked: bool, force: bool):
    """The migration's git gates for a write with no migration plan, such as
    a changelog re-split: return (refusal or None, warning or None)."""
    dirty, reason = git_state(project_root, inputs)
    if dirty is None:
        if allow_untracked:
            return None, f"WARNING: proceeding without a git safety net -- {reason}."
        return (f"cannot determine the working-tree state -- {reason}. Commit the changelog files to git "
                "first, or pass --allow-untracked-tree."), None
    return tree_gate(dirty, {"interrupted": False, "dests": []}, (), None, force), None


def git_state(project_root: Path, inputs: list):
    """Return (set of resolved dirty paths, reason). The set is None when git
    cannot tell: no repo, a git error, git missing, or an input git ignores."""
    def git(*argv, stdin=None):
        return subprocess.run(["git", "-C", str(project_root), *argv], input=stdin, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=30)
    try:
        top = git("rev-parse", "--show-toplevel")
        proc = git("status", "--porcelain", "-z", "--untracked-files=all") if top.returncode == 0 else top
        listing = "".join(f"{Path(p).resolve().as_posix()}\n" for p in inputs)
        ignored = git("check-ignore", "--stdin", stdin=listing) if proc.returncode == 0 else proc
    except FileNotFoundError:
        return None, "git is not installed or not on PATH"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git could not run ({exc})"
    for result in (proc, ignored):
        if result.returncode not in (0, 1) or (result is proc and result.returncode != 0):
            first = (result.stderr.strip().splitlines() or ["no error text"])[0]
            return None, f"git exited {result.returncode}: {first}"
    if ignored.returncode == 0:
        hits = ignored.stdout.strip().splitlines()
        return None, f"git ignores {len(hits)} input path(s) of this migration, e.g. {hits[0]}"
    root, dirty, entries, i = Path(top.stdout.strip()), set(), proc.stdout.split("\0"), 0
    while i < len(entries):
        entry, i = entries[i], i + 1
        if len(entry) > 3:
            dirty.add((root / entry[3:]).resolve())
            if entry[0] in "RC" and i < len(entries):
                dirty.add((root / entries[i]).resolve())
                i += 1
    return dirty, ""
