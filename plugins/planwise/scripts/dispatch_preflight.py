#!/usr/bin/env python3
"""Dispatch preflight set checks: output overlap, prerequisites, siblings, decomposition, upstream Outputs.

Five subcommands, each a set comparison that prints the number of subjects
it saw before its verdict. Every subcommand exits 0 when its sets agree, 1
when it lists a difference, and 2 on unreadable or missing input.

``overlap --candidate <task file> [--running <task file>...]``
    Pass ``--running none``, or omit ``--running``, when no other task is
    running, and the check reports ``disjoint``. ``none`` is the empty-set token.
    It is accepted only as the sole value, and ``none`` beside a path exits 2. A candidate task's ``**Output:**`` paths intersect a running task's
    ``**Output:**`` paths. Shared paths are listed per running task.
    ``output_paths`` is a plain function so a scaffold-time layer check can
    import it. Cannot see: two spellings of one path (a relative
    ``Outputs/x.md`` against a longer prefix of the same file) compare unequal.

``prereq --sprint-plan <plan.md> --sprint-folder <plan folder>``
    A prerequisite line that names a quantifier (all, every, any) and also
    enumerates sprints is compared with the member set the quantifier derives
    from the folder listing: every ``Sprint-NN-*`` folder except the plan's
    own, restricted to lower numbers when the line says prior, earlier,
    preceding or before. Sets are compared, never counts. A listing that is
    empty, or that lacks the plan's own Sprint-NN folder, is the wrong folder:
    the check prints ``not run`` and exits 2. A valid listing with no
    quantified line prints ``not checked`` and exits 0, never ``equal``. Cannot see: a
    quantifier scoped by other words ("all dispatch sprints") derives the
    whole listing, so its difference is a candidate for a human to read.

``siblings --since <YYYY-MM-DD> --recoveries <file>... --edit-set <list file>``
    A sibling Recovery whose latest recorded date is on or after ``--since``
    lists, under ``## Files Modified``, a path that the edit or sweep set also
    names. ``--recoveries none`` is the empty set, for a session with no closed
    sibling yet. The list file holds one path per line. Paths match when equal or
    when one ends with the other on a path-component boundary. Cannot see: a
    Recovery that records no date is skipped and counted, never read as clean.

``decomposition --matrix <file> --output <file> [--column N] [--heading-level N] [--heading-prefix P]``
    The set of decomposition rows (column ``N`` of each table row in the
    matrix, default 1) differs from the set of output section headings (level
    ``N``, default 2, optionally only those starting with ``P``). Both
    differences are listed. Names compare after case folding, whitespace
    collapsing, backtick removal and dropping a leading section number.

``upstream --candidate <task file> --plan-root <dir>``
    Each Required Context path into an ``Outputs/`` folder (a code span that
    holds an ``Outputs`` segment and ends in a file extension) is resolved
    against the live listing. Prints ``required-context output paths: N``,
    then one line per path. ``resolved`` means the path exists beside the task
    file or exactly one file of that basename sits in an ``Outputs`` folder
    under the plan root. Otherwise the basename's task-id prefix
    (``ABC-S01-02-03-``) is matched against every ``Outputs`` folder: one hit
    prints ``drift: {row} -> {live path}``, no hit prints ``missing: {row}``
    (the producer has not written the file), and two or more print
    ``ambiguous: {row} -> {list}`` and never pick one. Two files that share
    the basename also print ``ambiguous``. A basename with no task-id prefix
    and no file prints ``unresolved: {row}``. Exit 0 when every path resolved
    (also when N is 0), 1 on any other line, 2 on an unreadable candidate, a
    plan root that is not a folder, or a candidate with no Required Context
    section. Cannot see: an Output named in prose or by a glob or a
    placeholder, a path outside Required Context, and changed content under an
    unchanged name.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True

from markdown_parser import split_row_cells

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?\Z")
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)")
_SPACE_RE = re.compile(r"\s+")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_OUTPUT_LINE_RE = re.compile(r"^\s*\*\*Output:\*\*")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]+\Z")
_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_PREREQ_LINE_RE = re.compile(r"\b(prerequisites?|depends on)\b", re.IGNORECASE)
_QUANTIFIER_RE = re.compile(r"\b(all|every|any)\b", re.IGNORECASE)
_PRIOR_RE = re.compile(r"\b(prior|earlier|preceding|before)\b", re.IGNORECASE)
_SPRINT_LIST_RE = re.compile(
    r"\bSprints?[\s-]*((?:\d+(?:\s*(?:[–—-]|\bto\b)\s*\d+)?(?:\s*(?:,|&|\band\b)\s*)?)+)",
    re.IGNORECASE,
)
# A short form (S01, ES7) stands alone: never the segment of a hyphenated task
# id such as ABC-S04-01. A second short form after a dash or "to" closes a range.
_SHORT_SPRINT_RE = re.compile(
    r"(?<![\w-])E?S(\d{1,2})(?!\w|-\d)(?:\s*(?:[–—-]|\bto\b)\s*E?S(\d{1,2})(?!\w|-\d))?"
)
_RANGE_RE = re.compile(r"(\d+)(?:\s*(?:[–—-]|\bto\b)\s*(\d+))?", re.IGNORECASE)
_FOLDER_RE = re.compile(r"^Sprint-(\d+)")
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")
# A task id: letters and digits, -S, sprint, session, task number, an optional letter, then a hyphen.
_TASK_ID_RE = re.compile(r"^([A-Za-z0-9]+-S\d+-\d+-\d+[A-Za-z]?)-")
_PLACEHOLDER_CHARS = frozenset("*?{}[]<>")


# --- shared parsing ---------------------------------------------------------


def normalise(text: str) -> str:
    """Fold case, drop backticks and collapse whitespace."""
    return _SPACE_RE.sub(" ", text.replace("`", "")).strip().casefold()


def normalise_path(path: str) -> str:
    """Forward slashes, no leading ``./``, no surrounding space."""
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def looks_like_path(token: str) -> bool:
    """A code span is a path when it holds a slash or ends in an extension."""
    token = token.strip()
    if not token or " " in token:
        return False
    return "/" in token or "\\" in token or bool(_EXTENSION_RE.search(token))


def unfenced(lines: list[str]) -> list[str]:
    """Drop fenced code blocks, fence lines included.

    CommonMark rule: a fence opens on three or more backticks or tildes, indented
    at most three spaces. Only a run of the same character, at least as long and
    followed by nothing but spaces, closes it. A backtick opener whose info string
    holds a backtick is not a fence. An unclosed fence runs to the end of input.
    """
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        m = _FENCE_OPEN_RE.match(line)
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = m.group(1)
                continue
            out.append(line)
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
            fence = None
    return out


def section_lines(text: str, heading: str) -> list[str] | None:
    """Lines under the first heading whose text contains ``heading``; ``None`` if absent."""
    lines = unfenced(text.splitlines())
    want = normalise(heading)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and want in normalise(m.group(2)):
            level = len(m.group(1))
            out = []
            for rest in lines[i + 1:]:
                n = _HEADING_RE.match(rest)
                if n and len(n.group(1)) <= level:
                    break
                out.append(rest)
            return out
    return None


def table_rows(lines: list[str]) -> list[list[str]]:
    """Body rows of every table in ``lines``: header and separator rows dropped."""
    rows: list[list[str]] = []
    block: list[str] = []
    for line in lines + [""]:
        if line.lstrip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 2:
            for row in block[1:]:
                cells = split_row_cells(row)
                if cells and not all(_SEPARATOR_CELL_RE.match(c) for c in cells if c):
                    rows.append(cells)
        block = []
    return rows


# --- overlap ----------------------------------------------------------------


def output_paths(text: str) -> set[str] | None:
    """Paths in a task file's ``**Output:**`` line; ``None`` when no such line exists."""
    for line in text.splitlines():
        if _OUTPUT_LINE_RE.match(line):
            return {normalise_path(t) for t in _CODE_SPAN_RE.findall(line) if looks_like_path(t)}
    return None


def overlap(candidate: set[str], running: dict[str, set[str]]) -> dict[str, set[str]]:
    """Shared paths per running task, only for tasks that share at least one."""
    return {name: candidate & paths for name, paths in running.items() if candidate & paths}


def empty_set_token(paths: list[Path], flag: str) -> tuple[list[Path], str | None]:
    """Map a sole ``none`` (any case) to the empty list.

    Returns the paths and ``None``, or the paths and an error line when ``none``
    sits beside other paths, because the caller cannot tell which was meant.
    """
    if not any(str(p).lower() == "none" for p in paths):
        return paths, None
    if len(paths) == 1:
        return [], None
    return paths, f"error: {flag} none is the empty set and cannot be combined with other paths"


def _cmd_overlap(args: argparse.Namespace) -> int:
    running, problem = empty_set_token(args.running, "--running")
    if problem:
        print(problem)
        return 2
    texts = {}
    for path in [args.candidate, *running]:
        try:
            texts[str(path)] = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: {exc}")
            return 2
    parsed = {name: output_paths(text) for name, text in texts.items()}
    missing = [name for name, paths in parsed.items() if paths is None]
    if missing:
        for name in missing:
            print(f"error: no **Output:** line in {name}")
        return 2
    candidate = parsed.pop(str(args.candidate))
    print(f"candidate output paths: {len(candidate)}")
    print(f"running tasks: {len(parsed)}, output paths: {sum(len(p) for p in parsed.values())}")
    shared = overlap(candidate, parsed)
    if not shared:
        print("disjoint: no running task shares an output path")
        return 0
    for name, paths in shared.items():
        print(f"shared with {name}: {len(paths)}")
        for path in sorted(paths):
            print(f"  {path}")
    return 1


# --- prereq -----------------------------------------------------------------


def enumerated_sprints(line: str) -> set[int]:
    """Sprint numbers a line enumerates, ranges expanded."""
    found: set[int] = set()
    for m in _SPRINT_LIST_RE.finditer(line):
        for r in _RANGE_RE.finditer(m.group(1)):
            lo = int(r.group(1))
            hi = int(r.group(2)) if r.group(2) else lo
            found.update(range(min(lo, hi), max(lo, hi) + 1))
    for m in _SHORT_SPRINT_RE.finditer(line):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        found.update(range(min(lo, hi), max(lo, hi) + 1))
    return found


def folder_sprints(folder: Path) -> set[int]:
    """Sprint numbers of the ``Sprint-NN-*`` directories directly under ``folder``."""
    out = set()
    for child in folder.iterdir():
        m = _FOLDER_RE.match(child.name)
        if child.is_dir() and m:
            out.add(int(m.group(1)))
    return out


def own_sprint(plan: Path) -> int | None:
    """The plan's own sprint number, read from its nearest ``Sprint-NN-*`` folder."""
    for parent in plan.resolve().parents:
        m = _FOLDER_RE.match(parent.name)
        if m:
            return int(m.group(1))
    return None


def derived_members(line: str, listing: set[int], own: int | None) -> set[int]:
    """The member set a quantified edge derives from the folder listing."""
    members = {n for n in listing if n != own}
    if own is not None and _PRIOR_RE.search(line):
        members = {n for n in members if n < own}
    return members


def _cmd_prereq(args: argparse.Namespace) -> int:
    try:
        text = args.sprint_plan.read_text(encoding="utf-8")
        listing = folder_sprints(args.sprint_folder)
    except OSError as exc:
        print(f"error: {exc}")
        return 2
    own = own_sprint(args.sprint_plan)
    lines = [ln for ln in unfenced(text.splitlines()) if _PREREQ_LINE_RE.search(ln)]
    print(f"sprint folders listed: {len(listing)}")
    print(f"prerequisite lines: {len(lines)}")
    if not listing or (own is not None and own not in listing):
        print("not run: --sprint-folder must be the plan folder that holds this plan's Sprint-NN folder")
        return 2
    checked = 0
    failed = False
    for line in lines:
        enumerated = enumerated_sprints(line)
        if not _QUANTIFIER_RE.search(line) or not enumerated:
            continue
        checked += 1
        derived = derived_members(line, listing, own)
        extra, absent = enumerated - derived, derived - enumerated
        if extra or absent:
            failed = True
            print(f"difference on: {line.strip()}")
            print(f"  enumerated, not derived: {sorted(extra)}")
            print(f"  derived, not enumerated: {sorted(absent)}")
    print(f"quantified lines with an enumeration: {checked}")
    if failed:
        return 1
    if checked == 0:
        print("not checked: no quantified prerequisite line enumerates sprints")
        return 0
    print("equal: every quantified enumeration matches its derived set")
    return 0


# --- siblings ---------------------------------------------------------------


def latest_date(text: str) -> date | None:
    """The latest ISO date written anywhere in ``text``."""
    dates = []
    for m in _DATE_RE.finditer(text):
        try:
            dates.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return max(dates) if dates else None


def files_modified(text: str) -> set[str]:
    """Paths under a Recovery's ``## Files Modified`` heading."""
    lines = section_lines(text, "Files Modified") or []
    paths = set()
    for line in lines:
        spans = _CODE_SPAN_RE.findall(line)
        if spans:
            paths.update(normalise_path(s) for s in spans if looks_like_path(s))
            continue
        bare = line.strip().lstrip("-*").strip()
        if looks_like_path(bare):
            paths.add(normalise_path(bare))
    return paths


def read_list(path: Path) -> set[str]:
    """One path per line; blank lines and ``#`` comments skipped."""
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(normalise_path(line))
    return out


def paths_meet(a: str, b: str) -> bool:
    """Equal, or one ends with the other on a path-component boundary."""
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return longer.endswith("/" + shorter)


def intersect(modified: set[str], edit_set: set[str]) -> set[str]:
    """Modified paths that meet some edit-set path."""
    return {m for m in modified if any(paths_meet(m, e) for e in edit_set)}


def _cmd_siblings(args: argparse.Namespace) -> int:
    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        print(f"error: --since is not YYYY-MM-DD: {args.since}")
        return 2
    recoveries, problem = empty_set_token(args.recoveries, "--recoveries")
    if problem:
        print(problem)
        return 2
    try:
        edit_set = read_list(args.edit_set)
        texts = {str(p): p.read_text(encoding="utf-8") for p in recoveries}
    except OSError as exc:
        print(f"error: {exc}")
        return 2
    print(f"edit-set paths: {len(edit_set)}")
    print(f"recoveries given: {len(texts)}")
    in_window = undated = 0
    hits: dict[str, set[str]] = {}
    for name, text in texts.items():
        latest = latest_date(text)
        if latest is None:
            undated += 1
            print(f"skipped, no date recorded: {name}")
            continue
        if latest < since:
            continue
        in_window += 1
        found = intersect(files_modified(text), edit_set)
        if found:
            hits[name] = found
    print(f"recoveries on or after {since.isoformat()}: {in_window}, undated: {undated}")
    if not hits:
        print("none: no sibling Files Modified path meets the edit set")
        return 0
    for name, found in hits.items():
        print(f"intersecting files in {name}: {len(found)}")
        for path in sorted(found):
            print(f"  {path}")
    return 1


# --- decomposition ----------------------------------------------------------


def section_name(text: str) -> str:
    """Normalised name with any leading section number dropped."""
    return normalise(_SECTION_NUMBER_RE.sub("", text.strip()))


def matrix_rows(text: str, column: int) -> set[str]:
    """Normalised cell ``column`` (1-based) of every table body row."""
    rows = table_rows(unfenced(text.splitlines()))
    return {section_name(r[column - 1]) for r in rows if len(r) >= column and r[column - 1].strip()}


def output_sections(text: str, level: int, prefix: str) -> set[str]:
    """Normalised headings of exactly ``level`` that start with ``prefix``."""
    out = set()
    for line in unfenced(text.splitlines()):
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) == level and m.group(2).replace("`", "").strip().startswith(prefix):
            out.add(section_name(m.group(2)))
    return out


def _cmd_decomposition(args: argparse.Namespace) -> int:
    try:
        rows = matrix_rows(args.matrix.read_text(encoding="utf-8"), args.column)
        sections = output_sections(args.output.read_text(encoding="utf-8"), args.heading_level, args.heading_prefix)
    except OSError as exc:
        print(f"error: {exc}")
        return 2
    print(f"decomposition rows: {len(rows)}")
    print(f"output sections: {len(sections)}")
    rows_only, sections_only = rows - sections, sections - rows
    if not rows_only and not sections_only:
        print("both differences empty")
        return 0
    print(f"rows with no section: {len(rows_only)}")
    for name in sorted(rows_only):
        print(f"  {name}")
    print(f"sections with no row: {len(sections_only)}")
    for name in sorted(sections_only):
        print(f"  {name}")
    return 1


# --- upstream ---------------------------------------------------------------


def required_context_outputs(text: str) -> list[str] | None:
    """``Outputs/`` file paths in the Required Context section, in order, once each.

    ``None`` when the text has no Required Context heading. A code span that holds a
    glob or a placeholder character is skipped, because it names no one file.
    """
    lines = section_lines(text, "required context")
    if lines is None:
        return None
    found: list[str] = []
    for line in lines:
        for token in _CODE_SPAN_RE.findall(line):
            path = normalise_path(token)
            if "Outputs" not in path.split("/") or not _EXTENSION_RE.search(path):
                continue
            if _PLACEHOLDER_CHARS & set(path) or path in found:
                continue
            found.append(path)
    return found


def outputs_index(plan_root: Path) -> dict[str, list[str]]:
    """Basename to the plan-root-relative paths of every file under an ``Outputs`` folder."""
    index: dict[str, list[str]] = {}
    for dirpath, _dirs, files in os.walk(plan_root):
        rel_dir = Path(dirpath).relative_to(plan_root).as_posix()
        if "Outputs" not in rel_dir.split("/"):
            continue
        for name in sorted(files):
            index.setdefault(name, []).append(f"{rel_dir}/{name}")
    return index


def classify_output(row: str, task_dir: Path, index: dict[str, list[str]]) -> tuple[str, str]:
    """Verdict and detail for one Required Context Output path.

    The verdict is ``resolved``, ``drift``, ``missing``, ``ambiguous`` or ``unresolved``.
    The detail is the live path (drift) or the comma-joined candidates (ambiguous).
    """
    if (task_dir / row).is_file():
        return "resolved", ""
    name = row.rsplit("/", 1)[-1]
    same = index.get(name, [])
    if len(same) == 1:
        return "resolved", ""
    if len(same) > 1:
        return "ambiguous", ", ".join(same)
    match = _TASK_ID_RE.match(name)
    if not match:
        return "unresolved", ""
    prefix = match.group(1) + "-"
    hits = sorted(path for live, paths in index.items() if live.startswith(prefix) for path in paths)
    if not hits:
        return "missing", ""
    if len(hits) == 1:
        return "drift", hits[0]
    return "ambiguous", ", ".join(hits)


def _cmd_upstream(args: argparse.Namespace) -> int:
    try:
        text = args.candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    if not args.plan_root.is_dir():
        print(f"error: --plan-root is not a folder: {args.plan_root}")
        return 2
    rows = required_context_outputs(text)
    if rows is None:
        print(f"error: no Required Context section in {args.candidate}")
        return 2
    print(f"required-context output paths: {len(rows)}")
    index = outputs_index(args.plan_root)
    failed = False
    for row in rows:
        verdict, detail = classify_output(row, args.candidate.parent, index)
        if verdict == "resolved":
            print(f"resolved: {row}")
            continue
        failed = True
        print(f"{verdict}: {row} -> {detail}" if detail else f"{verdict}: {row}")
    return 1 if failed else 0


# --- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("overlap", help="candidate Output paths against running tasks")
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--running", nargs="*", default=[], type=Path)
    p.set_defaults(func=_cmd_overlap)

    p = sub.add_parser("prereq", help="quantified prerequisite against the sprint folder list")
    p.add_argument("--sprint-plan", required=True, type=Path)
    p.add_argument("--sprint-folder", required=True, type=Path)
    p.set_defaults(func=_cmd_prereq)

    p = sub.add_parser("siblings", help="sibling Recovery Files Modified against the edit set")
    p.add_argument("--since", required=True)
    p.add_argument("--recoveries", required=True, nargs="+", type=Path)
    p.add_argument("--edit-set", required=True, type=Path)
    p.set_defaults(func=_cmd_siblings)

    p = sub.add_parser("decomposition", help="matrix rows against output sections, both ways")
    p.add_argument("--matrix", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--column", type=int, default=1)
    p.add_argument("--heading-level", type=int, default=2)
    p.add_argument("--heading-prefix", default="")
    p.set_defaults(func=_cmd_decomposition)

    p = sub.add_parser("upstream", help="Required Context Output paths against the live Outputs listing")
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--plan-root", required=True, type=Path)
    p.set_defaults(func=_cmd_upstream)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a console code page cannot crash the verdict
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
