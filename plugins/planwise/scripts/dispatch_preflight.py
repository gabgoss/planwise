#!/usr/bin/env python3
"""Dispatch preflight set checks: overlap, prerequisites, siblings, decomposition, upstream Outputs, Depends On.

Six subcommands, each a set comparison that prints the number of subjects
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
    Reads only the lines under the plan's ``## Prerequisites`` heading that
    name a prerequisite or depends on. A plan with no such heading prints
    ``not run`` and exits 2. Such a line that names a quantifier (all, every,
    any) and also enumerates sprints is compared with the member set the
    quantifier derives from the folder listing: every ``Sprint-NN-*`` folder
    except the plan's own, restricted to lower numbers when the line says prior,
    earlier, preceding or before. Sets are compared, never counts. A listing
    that is empty, or that lacks the plan's own Sprint-NN folder, is the wrong
    folder: the check prints ``not run`` and exits 2. A valid listing with no
    quantified line prints ``not checked`` and exits 0, never ``equal``. Cannot
    see: a quantifier scoped by other words ("all dispatch sprints") derives the
    whole listing, so its difference is a candidate for a human to read. Also a
    quantified edge outside that section, and a Prerequisites bullet that never
    says prerequisite or depends on.

``siblings --since <YYYY-MM-DD> --recoveries <file>... --edit-set <list file>``
    A sibling Recovery whose latest recorded date is on or after ``--since``
    lists, under ``## Files Modified``, a path that the edit or sweep set also
    names. ``--recoveries none`` is the empty set, for a session with no closed
    sibling yet. The list file holds one path per line. Paths match when equal or
    when one ends with the other on a path-component boundary. A Files Modified
    line yields each code span, and each word outside the spans that holds a
    slash or ends in an extension (words split at spaces, commas, semicolons and
    parentheses). Cannot see: a Recovery that records no date is skipped and
    counted, never read as clean, and a file named in prose with no slash and no
    extension.

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

``depends --candidate <task file> --plan-root <dir>``
    Each producer on the candidate's ``**Depends On:**`` header line is looked up
    in the ``## Step Completion Status`` table of its session's Recovery. A task
    number, or a range such as ``1-5``, names a task of the candidate's own
    session, whose Recovery sits beside it. A full task id names a task whose
    Recovery is found by file name under the plan root. Entries are separated by
    commas, semicolons, ``&`` or the word "and". Text in parentheses is an
    annotation, but a task id or a cross-session target in it still counts. A
    value that runs onto the next line is ``unresolved:``. Prints ``depends-on entries: N``, then one line per
    producer: ``complete:``, ``not-complete:``, ``unresolved:`` (the entry names
    no task id, or no Recovery of that name exists) or ``ambiguous:`` (two or
    more Recovery files share the name). A producer is complete when its Status
    cell starts with the word COMPLETE. The later of two rows for one step
    counts. Exit 0 when every producer is complete (also when N is 0), 1 on any
    other line, 2 on an unreadable input, a candidate with no task id, or a plan
    root that is not a folder. Cannot see: a bare task number or a session id
    inside parentheses, and a COMPLETE row whose output was later deleted.
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
from parse_plans import normalize_status

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?\Z")
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)")
_SPACE_RE = re.compile(r"\s+")
_COMMENT_RE = re.compile(r"<!--.*?-->")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
# The separators between two paths written outside code spans.
_TOKEN_SPLIT_RE = re.compile(r"[\s,;()]+")
# Bold, italic-star and quote marks around such a path. Underscores stay: ``__init__.py``.
_TOKEN_WRAPPERS = "*\"'"
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
# A Depends On value: the spellings that name no producer, and the shapes that name one.
_NO_PRODUCER = frozenset({"", "-", "–", "—", "∅", "none", "n/a"})
_PARENTHETICAL_RE = re.compile(r"\([^()]*\)")
_ENTRY_SPLIT_RE = re.compile(r"[,;&]|\s+and\s+", re.IGNORECASE)
_REMOTE_PREFIX_RE = re.compile(r"^cross-(?:session|sprint)\s*:\s*", re.IGNORECASE)
# A session id such as ABC-S01-02, or ABC-META-S01-02 in a Meta-plan.
_SESSION_ID = r"[A-Za-z0-9]+(?:-META)?-S\d+-\d+"
_FULL_ID_RE = re.compile(rf"^({_SESSION_ID})-(\d+[A-Za-z]?)\Z")
_LEADING_ID_RE = re.compile(rf"^({_SESSION_ID})-\d+[A-Za-z]?\b")
_LOCAL_ENTRY_RE = re.compile(r"^(?:tasks?\s+)?(\d+[A-Za-z]?)\Z", re.IGNORECASE)
_RANGE_ENTRY_RE = re.compile(r"^(?:tasks?\s+)?(\d{1,2})\s*(?:[–—-]|\bto\b)\s*(\d{1,2})\Z", re.IGNORECASE)
_STEP_RE = re.compile(r"^(\d+)([A-Za-z]?)\Z")
# What an annotation in parentheses can still name: a task id, or a cross-session target.
_NOTED_ID_RE = re.compile(rf"(?<![\w-]){_SESSION_ID}-\d+[A-Za-z]?(?!\w)")
_NOTED_TARGET_RE = re.compile(
    r"cross-(?:session|sprint)\s*:\s*(?:Sprint-\d+|[A-Za-z0-9]+(?:-META)?-S\d+(?:-\d+)*[A-Za-z]?)", re.IGNORECASE
)
# The openings of a line that starts something new after a header value.
_NOT_A_CONTINUATION = ("**", "#", "---", "<!--", "|", ">")


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


def section_lines(text: str, heading: str, level: int | None = None) -> list[str] | None:
    """Lines under the first heading whose text contains ``heading``; ``None`` if absent.

    With ``level``, the heading has that depth and reads exactly ``heading``, its
    section number and HTML comments aside. A title or a longer heading that holds
    the same word then claims nothing.
    """
    lines = unfenced(text.splitlines())
    want = normalise(heading)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        depth = len(m.group(1))
        if level is None:
            found = want in normalise(m.group(2))
        else:
            found = depth == level and section_name(_COMMENT_RE.sub("", m.group(2))) == want
        if found:
            out = []
            for rest in lines[i + 1:]:
                n = _HEADING_RE.match(rest)
                if n and len(n.group(1)) <= depth:
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
    section = section_lines(text, "Prerequisites", level=2)
    print(f"sprint folders listed: {len(listing)}")
    if section is None:
        print(f"not run: no Prerequisites section in {args.sprint_plan}")
        return 2
    lines = [ln for ln in section if _PREREQ_LINE_RE.search(ln)]
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
        paths.update(normalise_path(s) for s in _CODE_SPAN_RE.findall(line) if looks_like_path(s))
        outside = _CODE_SPAN_RE.sub(" ", line).strip().lstrip("-*")
        for token in _TOKEN_SPLIT_RE.split(outside):
            token = token.rstrip(".:").strip(_TOKEN_WRAPPERS).rstrip(".:")
            if token.startswith("[") and token.endswith("]"):
                token = token[1:-1]  # a pair only: ``[id]/page.tsx`` keeps its bracket
            if looks_like_path(token):
                paths.add(normalise_path(token))
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


# --- depends ----------------------------------------------------------------


def header_field(text: str, name: str) -> tuple[str, str]:
    """A ``**Name:**`` header value and the line after it; both empty when absent.

    Reads above the first ``## `` heading. The field starts a line or follows a
    ``|``. For an empty value, the line returned is the next non-blank one.
    """
    pattern = re.compile(rf"(?:^|\|)\s*\*\*{re.escape(name)}(?::\*\*|\*\*:)", re.IGNORECASE)
    lines = unfenced(text.splitlines())
    for i, line in enumerate(lines):
        if line.startswith("## "):
            break
        m = pattern.search(line)
        if not m:
            continue
        value = _COMMENT_RE.sub("", line[m.end() :]).split("| **")[0].strip()
        rest = lines[i + 1 :]
        after = rest[:1] if value else [ln for ln in rest if ln.strip()][:1]
        return value, after[0] if after else ""
    return "", ""


def runs_on(following: str) -> bool:
    """True when the line after a header value continues it: a list item or loose text."""
    following = following.strip()
    return bool(following) and not following.startswith(_NOT_A_CONTINUATION)


def depends_entries(cell: str) -> list[str]:
    """The entries of one Depends On value, empty spellings dropped.

    Text in parentheses is an annotation. A task id or a ``cross-session:`` or
    ``cross-sprint:`` target inside it still counts as an entry.
    """
    text = cell.replace("`", "").replace("**", "")
    annotations: list[str] = []
    found = 1
    while found:  # inner brackets first, so a nested annotation goes too
        annotations += _PARENTHETICAL_RE.findall(text)
        text, found = _PARENTHETICAL_RE.subn("", text)
    parts = [part.strip() for part in _ENTRY_SPLIT_RE.split(text)]
    for note in annotations:
        parts += _NOTED_ID_RE.findall(note)
        parts += [hit for hit in _NOTED_TARGET_RE.findall(note) if not _NOTED_ID_RE.search(hit)]
    return [part for part in parts if part.casefold() not in _NO_PRODUCER]


def step_key(cell: str) -> tuple[int, str] | None:
    """``(number, letter)`` of a task number or a Step cell, ``None`` when it holds neither."""
    text = _PARENTHETICAL_RE.sub("", cell.replace("*", "").replace("`", "")).strip()
    m = _STEP_RE.match(text)
    return (int(m.group(1)), m.group(2).lower()) if m else None


def named_producers(entry: str, own_steps=()) -> list[tuple[str, str | None, tuple[int, str]]]:
    """``(label, session id or None, step key)`` per task the entry names; empty when it names none.

    ``None`` as the session id means the candidate's own session. ``own_steps``
    holds that session's step keys, so a range also covers its lettered steps.
    """
    bare = _REMOTE_PREFIX_RE.sub("", entry)
    m = _FULL_ID_RE.match(bare)
    if m:
        return [(bare, m.group(1), step_key(m.group(2)))]
    m = _LOCAL_ENTRY_RE.match(entry)
    if m:
        number, letter = step_key(m.group(1))
        return [(f"{number:02d}{letter}", None, (number, letter))]
    m = _RANGE_ENTRY_RE.match(entry)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        keys = {key for key in own_steps if low <= key[0] <= high}
        numbered = {number for number, _letter in keys}
        keys |= {(n, "") for n in range(low, high + 1) if n not in numbered}
        return [(f"{n:02d}{letter}", None, (n, letter)) for n, letter in sorted(keys)]
    return []


def step_statuses(text: str) -> dict[tuple[int, str], str]:
    """Step key to Status cell from a Recovery's first Step Completion Status table.

    A later row for one step replaces an earlier one, as a second attempt does.
    """
    block: list[str] = []
    for line in section_lines(text, "Step Completion Status") or []:
        if line.lstrip().startswith("|"):
            block.append(line)
        elif block:
            break
    if not block:
        return {}
    header = [normalise(cell.replace("*", "")) for cell in split_row_cells(block[0])]
    step = next((header.index(name) for name in ("step", "#") if name in header), None)
    if step is None or "status" not in header:
        return {}
    status = header.index("status")
    out = {}
    for row in table_rows(block):
        if len(row) > max(step, status) and (key := step_key(row[step])):
            out[key] = row[status].strip()
    return out


def recovery_index(plan_root: Path) -> dict[str, list[Path]]:
    """Recovery file name to every file of that name under the plan root."""
    index: dict[str, list[Path]] = {}
    for dirpath, _dirs, files in os.walk(plan_root):
        for name in files:
            if name.endswith("-Recovery.md"):
                index.setdefault(name, []).append(Path(dirpath) / name)
    return index


def producer_verdict(label: str, recovery: Path, key: tuple[int, str]) -> str:
    """The report line for one producer whose Recovery path is known."""
    if not recovery.is_file():
        return f"not-complete: {label} (no Recovery)"
    status = step_statuses(recovery.read_text(encoding="utf-8")).get(key)
    if status is None:
        return f"not-complete: {label} (no step row)"
    if normalize_status(status.upper()) == "COMPLETE":
        return f"complete: {label}"
    return f"not-complete: {label} ({status})"


def depends_report(cell: str, own_session: str, task_dir: Path, plan_root: Path) -> list[str]:
    """One line per producer the Depends On value names, each producer once."""
    index = recovery_index(plan_root)
    own = task_dir / f"{own_session}-Recovery.md"
    own_steps = step_statuses(own.read_text(encoding="utf-8")) if own.is_file() else {}
    lines: list[str] = []
    for entry in depends_entries(cell):
        producers = named_producers(entry, own_steps)
        if not producers:
            lines.append(f"unresolved: {entry}")
        for label, session, key in producers:
            if session is None:
                lines.append(producer_verdict(label, own, key))
                continue
            hits = index.get(f"{session}-Recovery.md", [])
            if not hits:
                lines.append(f"unresolved: {label} (no Recovery under the plan root)")
            elif len(hits) > 1:
                found = ", ".join(sorted(p.relative_to(plan_root).as_posix() for p in hits))
                lines.append(f"ambiguous: {label} -> {found}")
            else:
                lines.append(producer_verdict(label, hits[0], key))
    return list(dict.fromkeys(lines))


def _cmd_depends(args: argparse.Namespace) -> int:
    try:
        text = args.candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    if not args.plan_root.is_dir():
        print(f"error: --plan-root is not a folder: {args.plan_root}")
        return 2
    own = _LEADING_ID_RE.match(header_field(text, "Task ID")[0].lstrip("`* "))
    if not own:
        print(f"error: no **Task ID:** line with a task id in {args.candidate}")
        return 2
    cell, following = header_field(text, "Depends On")
    try:
        lines = depends_report(cell, own.group(1), args.candidate.parent, args.plan_root)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}")
        return 2
    if runs_on(following):
        lines.append("unresolved: the Depends On value runs onto the next line")
    print(f"depends-on entries: {len(lines)}")
    for line in lines:
        print(line)
    return 1 if any(not line.startswith("complete: ") for line in lines) else 0


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

    p = sub.add_parser("depends", help="Depends On producers against their Recovery step rows")
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--plan-root", required=True, type=Path)
    p.set_defaults(func=_cmd_depends)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a console code page cannot crash the verdict
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
