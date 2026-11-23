#!/usr/bin/env python3
"""Lint checks that compare one layer of a task file with another, registered into the linter.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check takes
the lint context duck-typed -- it reads only ``plan_root`` and
``markdown_files()`` -- and builds its finding with the same six keys the
linter's ``make_finding`` writes. The sibling modules ``lint_gate_checks_verify``,
``lint_gate_checks_dispatch`` and ``dispatch_preflight`` supply the task-file
reader, the section and table readers and the path helpers.

Every check here is advisory and reports at WARNING, except Check 57, which reports at
ERROR because three layers that state one dependency set and disagree cannot all be
right, the first branch of Check 59, which reports at ERROR because the overlap
check cannot see a write the Output line leaves out, and the first branch of Check 60,
which reports at ERROR because Reviewer Checks 037 and 038 are BLOCKER. Each docstring states the
predicate, the input and what the check cannot see.
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import lint_execution_input_plan
from dispatch_preflight import normalise_path, output_paths, paths_meet
from lint_gate_checks_dispatch import (
    _required_context_rows,
    _section_lines,
    _walk_section,
)
from lint_gate_checks_verify import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    _finding,
    _task_files,
)
from token_saver_writeback import (
    _cells,
    _col,
    _section_bounds,
    _split_eol,
    _token_tables,
)

# --- Check 54: an Execution Step reads a path with no Required Context row (task-content-fidelity.md §9.A.17) ---
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_PATH_ARG_RE = re.compile(r"\bpath\s*=\s*(['\"])(.*?)\1")
_PATH_SUFFIX_RE = re.compile(r"(?:#.*|:\d[\d,\-–]*)\Z")
_FILE_EXTENSION_RE = re.compile(
    r"\.(?:md|py|json|ya?ml|toml|txt|csv|ini|cfg|sh|ps1|js|ts|template|html)\Z", re.IGNORECASE
)
# A path with a placeholder, a glob, a regex operator or a URL scheme names no one file.
_UNRESOLVED_RE = re.compile(r"[{}<>$*?\[\]()|^\\]|://")
_NEGATION_RE = re.compile(r"\b(?:WRONG|never|do\s+not|does\s+not|must\s+not)\b", re.IGNORECASE)
# A step that reads a sprint base marker takes it from the spawn prompt's ``Base commit:`` line.
_BASE_NAME_RE = re.compile(r"_BASE\b")


def _clean_path(token: str) -> str:
    """Normalise a cited path and drop a trailing ``#heading`` or ``:line`` qualifier."""
    return _PATH_SUFFIX_RE.sub("", normalise_path(token))


def _is_file_path(token: str) -> bool:
    """A code span is a file path when it ends in a known file extension. A bare
    folder name such as ``Archive/`` is not read as a file."""
    if not token or " " in token or token.startswith("-"):
        return False
    return bool(_FILE_EXTENSION_RE.search(token))


def _is_scope_path(token: str) -> bool:
    """A ``path=`` argument names a file or a folder, so a slash is enough."""
    if not token or " " in token or token.startswith("-"):
        return False
    return "/" in token or bool(_FILE_EXTENSION_RE.search(token))


def _step_reads(line: str) -> list:
    """The resolved paths one Execution Step line names, in order and without repeats:
    each code span that is a file path, and each ``path=`` argument of a tool call."""
    found = []
    candidates = [(match.group(1), _is_file_path) for match in _CODE_SPAN_RE.finditer(line)]
    candidates += [(match.group(2), _is_scope_path) for match in _PATH_ARG_RE.finditer(line)]
    for token, accepts in candidates:
        path = _clean_path(token)
        if not accepts(path) or _UNRESOLVED_RE.search(path) or path in found:
            continue
        found.append(path)
    return found


def _row_paths(cells) -> list:
    """Every path a Required Context row names, across all its cells. A row that holds a
    command, such as a ``Grep`` over a folder, names its scope the same way."""
    paths = []
    for cell in cells:
        candidates = [match.group(1) for match in _CODE_SPAN_RE.finditer(cell)]
        candidates += [match.group(2) for match in _PATH_ARG_RE.finditer(cell)]
        for token in candidates:
            path = _clean_path(token)
            if path:
                paths.append(path)
    return paths


def _row_covers(row_path: str, read_path: str) -> bool:
    """A row covers a read when the paths meet, or when the row names a folder
    (a trailing slash) that holds the read."""
    if paths_meet(row_path, read_path):
        return True
    return row_path.endswith("/") and read_path.startswith(row_path)


def _check54_step_reads_path_without_required_context_row(context) -> list:
    """Check 54 -- an Execution Step names a path that no Required Context row covers
    and that the task's ``**Output:**`` line does not name (task-content-fidelity.md
    §9.A.17, Reviewer Check 123). The token budget trusts Required Context, so a file
    a step reads with no row is unpriced and the estimate runs low by its size. Input:
    the unfenced lines of the Execution Steps section, reading each code span that is
    a path and each ``path=`` argument of a tool call. A row covers a read when any
    path the row names, in any cell, equals the read or meets it on a path-component
    boundary, or when the row names a folder that holds it. A task file with a
    Required Context heading and no table is read as having no rows. A task file
    with no Required Context heading is skipped, because it has nothing to compare
    with. A path with a placeholder, a
    glob, a regex operator or a URL, a line that negates (never, do not, WRONG), and a
    line that names a ``_BASE`` marker (read from the spawn prompt's ``Base commit:``
    line) are skipped. Advisory, so WARNING, as Check 123 states; Check 123's ERROR
    tier needs a measured cost and is not applied here. It cannot see a read written
    without a code span, a read inside a fenced block, a placeholder path, a row that
    names a file the step does not read (a row is never reported), or whether a row
    that covers the path prices it at the right size.
    """
    findings = []
    for rel, lines in _task_files(context):
        if not any(True for _hit in _walk_section(lines, ("required context",), first_only=True)):
            continue
        output = output_paths("\n".join(lines)) or set()
        covered = [
            path for _number, _line, cells, _header in _required_context_rows(lines)
            for path in _row_paths(cells)
        ]
        seen = set()
        for number, line in _section_lines(lines, ("execution steps",)):
            if _NEGATION_RE.search(line) or _BASE_NAME_RE.search(line):
                continue
            for path in _step_reads(line):
                if path in seen:
                    continue
                if any(paths_meet(path, declared) for declared in output):
                    continue
                if any(_row_covers(row, path) for row in covered):
                    continue
                seen.add(path)
                findings.append(_finding(
                    check=54, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
                    message=(
                        f"This Execution Step names {path!r}, and no Required Context row covers it "
                        "or the Output field names it. The token budget trusts Required Context, so "
                        "the file is unpriced and the estimate runs low by its size. Add a measured "
                        "row and re-derive the subtotal and Estimated Tokens "
                        "(task-content-fidelity.md, Reviewer Check 123)"
                    ),
                ))
    return findings


# --- Check 57: one task's Depends On differs across the three layers that state it ---
# --- Check 58: a cross-sprint Required Context row with no Cross-Sprint Refs field ---
_DEPENDS_HEADER_RE = re.compile(r"^\*\*Depends On:\*\*(.*)$")
_TASK_ID_HEADER_RE = re.compile(r"^\*\*Task ID:\*\*(.*)$")
_CROSS_SPRINT_REFS_RE = re.compile(r"^\*\*Cross-Sprint Refs:\*\*")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
_NO_DEPENDENCY = frozenset({"", "-", "–", "—", "∅", "none", "n/a"})
_PREFIXED_RE = re.compile(r"(cross-sprint|cross-session)\s*:\s*(.+)", re.IGNORECASE)
_SPRINT_FOLDER_RE = re.compile(r"(?:^|/)Sprint-(\d{2})(?=[-/])")
_TASK_NUMBER_RE = re.compile(r"-(\d+)\s*$")
_ORCHESTRATION_SUFFIX = "-Orchestration.md"


def _header_fields(lines):
    """The task file's header lines, down to its first ``## `` heading, as ``(number, line)``."""
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            return
        yield number, line


def _dependency_set(cell) -> frozenset:
    """One ``Depends On`` cell as a set of comparable entries. Backticks, bold markers and
    HTML comments are dropped, and the cell is split on commas. ``-``, ``None`` and an
    empty cell are the empty set. A bare number compares as an integer, so ``01`` equals
    ``1``. A ``cross-sprint:`` or ``cross-session:`` entry compares as the pair of its
    prefix and its full Task ID."""
    text = _HTML_COMMENT_RE.sub("", cell).replace("`", "").replace("**", "").strip()
    entries = set()
    for part in text.split(","):
        part = part.strip()
        if part.lower() in _NO_DEPENDENCY:
            continue
        prefixed = _PREFIXED_RE.fullmatch(part)
        if prefixed:
            entries.add((prefixed.group(1).lower(), prefixed.group(2).strip()))
        elif part.isdigit():
            entries.add(("", int(part)))
        else:
            entries.add(("", part))
    return frozenset(entries)


def _describe(entries) -> str:
    """A dependency set as the text a reader would write in the cell."""
    texts = sorted(f"{prefix}: {body}" if prefix else str(body) for prefix, body in entries)
    return ", ".join(texts) or "-"


def _read_lines(path):
    """A file's lines with carriage returns removed, or None when it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return [raw.rstrip("\r") for raw in text.split("\n")]


def _depends_by_task(lines, start, stop):
    """``{task number: Depends On cell}`` for the one task table in ``lines[start:stop]`` that
    has ``#``, ``Task`` and ``Depends On`` columns, or None when there is not exactly one."""
    tables = []
    for _header_index, _token_col, rows, header in _token_tables(lines, start, stop):
        columns = (_col(header, ("#",)), _col(header, ("task",)), _col(header, ("depends on",)))
        if None not in columns:
            tables.append((rows, header, columns[0], columns[2]))
    if len(tables) != 1:
        return None
    rows, header, number_col, depends_col = tables[0]
    found = {}
    for row in rows:
        cells = _cells(_split_eol(lines[row])[0], len(header))
        if len(cells) == len(header) and cells[number_col].strip().isdigit():
            found.setdefault(int(cells[number_col].strip()), cells[depends_col])
    return found


def _orchestration_layer(folder):
    """The Orchestration's ``Session Task List`` map in ``folder``, or None."""
    files = sorted(folder.glob(f"*{_ORCHESTRATION_SUFFIX}"))
    lines = _read_lines(files[0]) if len(files) == 1 else None
    bounds = _section_bounds(lines, "Session Task List") if lines is not None else None
    if lines is None or bounds is None:
        return None
    return _depends_by_task(lines, *bounds)


def _sprint_layer(folder, session_id):
    """The Sprint Plan's ``Session Details`` map for ``session_id``, or None. The Sprint Plan
    sits one folder above the session folder."""
    files = sorted(folder.parent.glob("*-Sprint-Plan.md"))
    lines = _read_lines(files[0]) if len(files) == 1 else None
    details = _section_bounds(lines, "Session Details") if lines is not None else None
    if lines is None or details is None:
        return None
    id_re = rf"(?<![\w-]){re.escape(session_id)}(?![\w-])"
    start = next((i for i in range(*details)
                  if lines[i].startswith("### ") and re.search(id_re, lines[i])), None)
    if start is None:
        return None
    stop = next((j for j in range(start + 1, details[1]) if re.match(r"^#{1,3}\s", lines[j])), details[1])
    return _depends_by_task(lines, start, stop)


def _session_layers(folder, session_id, cache):
    """``(orchestration, sprint plan)`` maps of task number to ``Depends On`` cell for the session
    in ``folder``. A layer that is missing, ambiguous or has no such table is None. The result is
    cached per folder, so each file is read once however many tasks the session holds."""
    if folder not in cache:
        cache[folder] = _orchestration_layer(folder), _sprint_layer(folder, session_id)
    return cache[folder]


def _check57_depends_on_layers_disagree(context) -> list:
    """Check 57 -- a task's ``Depends On`` differs across the task-file header, the Orchestration
    ``## Session Task List`` cell and the Sprint Plan ``## Session Details`` cell for the same
    task (Reviewer Check 137). The task file is the layer written with the task's Required
    Context in front of the author, and the other two restate it, so any difference is drift
    in a restated layer. Input: each task file's ``**Depends On:**`` header line, and the row
    numbered like the task in the Orchestration in the same folder and in the Sprint Plan one
    folder up. The task number comes from the ``**Task ID:**`` suffix. A task-file header
    outside the first block above its first ``## `` heading is not read. Cells compare as
    sets after the normalisation in ``_dependency_set``: backticks, bold and comments are
    dropped, ``-``, ``None`` and an empty cell are the empty set, a bare number compares as
    an integer, and a prefixed entry compares as the pair of its prefix and full Task ID.
    ERROR, because each layer states the same dependency and the layers cannot all be right.
    A layer that is missing, whose file is not unique in its folder, that has no table with
    ``#``, ``Task`` and ``Depends On`` columns, or that has no row for the task is skipped,
    and a task with no other layer to compare is silent. It cannot see the Orchestration
    ``**Prerequisite:**`` header, which is free text with no parseable set, or a task listed
    in a table outside the two sections named above.
    """
    findings = []
    root = Path(context.plan_root)
    cache: dict = {}
    for rel, lines in _task_files(context):
        header = list(_header_fields(lines))
        depends = next(((n, m.group(1)) for n, ln in header if (m := _DEPENDS_HEADER_RE.match(ln))), None)
        task_id = next((m.group(1) for _n, ln in header if (m := _TASK_ID_HEADER_RE.match(ln))), "")
        task_id = task_id.replace("`", "").replace("*", "").strip()
        number = _TASK_NUMBER_RE.search(task_id)
        if depends is None or number is None:
            continue
        orchestration, sprint = _session_layers((root / rel).parent, task_id.rsplit("-", 1)[0], cache)
        values = {"the task header": _dependency_set(depends[1])}
        for name, layer in (("the Orchestration Session Task List", orchestration),
                            ("the Sprint Plan Session Details", sprint)):
            if layer is not None and int(number.group(1)) in layer:
                values[name] = _dependency_set(layer[int(number.group(1))])
        if len(set(values.values())) < 2:
            continue
        shown = "; ".join(f"{name}: {_describe(entries)}" for name, entries in values.items())
        findings.append(_finding(
            check=57, severity=SEVERITY_ERROR, file=rel, line=depends[0],
            command=f"**Depends On:**{depends[1]}".strip(),
            message=(
                f"Task {task_id} states different Depends On sets in its layers ({shown}). "
                "Copy the task header's value into the other layers, or correct the header "
                "(task-file-and-tracking-requirements.md, Reviewer Check 137)"
            ),
        ))
    return findings


def _check58_cross_sprint_read_without_refs_field(context) -> list:
    """Check 58 -- a Required Context row names a path under another sprint's folder, and the
    task header has no ``**Cross-Sprint Refs:**`` field (Reviewer Check 138). The task-file
    template makes that field conditional on exactly this trigger. Input: each task file's
    header block, and the paths named in every cell of its ``## Required Context`` rows. The
    task's own sprint is the ``Sprint-NN`` folder in its path under the plan root, and a row
    path is cross-sprint when its own ``Sprint-NN`` folder carries another number. A path with
    a placeholder, a glob, a regex operator or a URL is skipped. One finding per distinct
    path. WARNING, because the field is a navigation aid and the dependency itself is Check
    57's and the ``Depends On`` prefix checks' concern. A task whose path holds no
    ``Sprint-NN`` folder is skipped, because its own sprint is unknown. It cannot see a field
    that is present but does not list the file, a cross-sprint read cited without a
    ``Sprint-NN`` folder in the path, or a path that names a sprint by something other than
    that folder.
    """
    findings = []
    for rel, lines in _task_files(context):
        own = _SPRINT_FOLDER_RE.search(rel)
        if own is None or any(_CROSS_SPRINT_REFS_RE.match(ln) for _n, ln in _header_fields(lines)):
            continue
        seen = set()
        for number, line, cells, _header in _required_context_rows(lines):
            for path in _row_paths(cells):
                other = _SPRINT_FOLDER_RE.search(path)
                if other is None or other.group(1) == own.group(1) or _UNRESOLVED_RE.search(path) or path in seen:
                    continue
                seen.add(path)
                findings.append(_finding(
                    check=58, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
                    message=(
                        f"This Required Context row names {path!r} under Sprint-{other.group(1)}, "
                        f"and the task header has no **Cross-Sprint Refs:** field. The template "
                        "requires the field whenever Required Context cites a cross-sprint file. "
                        "Add it, and keep the producer's Task ID in Depends On "
                        "(task-file-and-tracking-requirements.md, Reviewer Check 138)"
                    ),
                ))
    return findings


# --- Check 59: the Sprint Plan Write-Set, a task's Output line and its Expected Output paths agree ---
_OUTPUT_LINE_RE = re.compile(r"^\s*\*\*Output:\*\*")
_OUTPUTS_FOLDER_RE = re.compile(r"(?:^|/)Outputs/")
_SPRINT_PLAN_SUFFIX = "-Sprint-Plan.md"


def _path_covers(declared: str, path: str) -> bool:
    """Two paths cover each other when they meet on a path-component boundary, or when one
    is a folder (a trailing slash) that holds the other at a component boundary."""
    if paths_meet(declared, path):
        return True
    return any(
        folder.endswith("/") and f"/{folder}" in f"/{other}"
        for folder, other in ((declared, path), (path, declared))
    )


def _write_set_rows(lines) -> list:
    """The first Write-Set table of a Sprint Plan as ``(row index, path, task ids)``, alias
    legend expanded and paths normalised. The reader is ``lint_execution_input_plan``'s
    ``_write_set``, which needs the core module bound. Importing ``lint_execution_input``
    binds it, so the import sits here and the module is read only when a plan is."""
    import lint_execution_input as core

    doc = core.Doc(Path("Sprint-Plan.md"), list(lines))
    return [
        (index, normalise_path(path), tasks)
        for index, path, tasks in lint_execution_input_plan._write_set(doc)
    ]


def _sprint_write_set(task_path, cache):
    """The Write-Set rows of the one Sprint Plan one folder above the task's session folder,
    or None when that file is missing, not unique, unreadable or states no Write-Set rows.
    Cached per Sprint Plan, so each plan is read once however many tasks it holds."""
    plans = sorted(task_path.parent.parent.glob(f"*{_SPRINT_PLAN_SUFFIX}"))
    if len(plans) != 1:
        return None
    if plans[0] not in cache:
        lines = _read_lines(plans[0])
        rows = _write_set_rows(lines) if lines is not None else []
        cache[plans[0]] = rows or None
    return cache[plans[0]]


def _expected_output_lines(lines):
    """Yield ``(number, line)`` for each unfenced line directly under the Expected Output
    heading, down to its first sub-heading. The task-file template puts a conditional
    sub-section of its own prose under that heading, and that prose is not the task's claim."""
    opened = False
    for number, line, is_heading in _walk_section(lines, ("expected output",)):
        if not is_heading:
            yield number, line
        elif opened:
            return
        else:
            opened = True


def _outside_comments(numbered):
    """Yield ``(number, text)`` for each ``(number, line)`` with HTML comment text removed, a
    comment that spans several lines included. A line that is wholly inside a comment is
    dropped. The task-file template leaves long guidance comments under its headings, and
    their code spans name reference files the task does not touch."""
    inside = False
    for number, line in numbered:
        kept = []
        rest = line
        while rest:
            if inside:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                    break
                rest = rest[end + 3:]
                inside = False
                continue
            start = rest.find("<!--")
            if start < 0:
                kept.append(rest)
                break
            kept.append(rest[:start])
            rest = rest[start + 4:]
            inside = True
        text = "".join(kept)
        if text.strip():
            yield number, text


def _is_comparable(path: str) -> bool:
    """A path names one file or folder: no placeholder, glob, regex operator or URL."""
    return bool(path) and not _UNRESOLVED_RE.search(path)


def _check59_write_set_output_expected_output_agree(context) -> list:
    """Check 59 -- a task's Sprint Plan Write-Set rows, its ``**Output:**`` line and the paths
    its Expected Output section names disagree. ``dispatch_preflight overlap`` reads the
    Output line as the task's write set (the task-file template's Output comment), so a write
    the Output line leaves out is invisible to it. Input: each task file's ``**Output:**``
    line and the code-span paths in the unfenced lines directly under its Expected Output
    heading, down to the first sub-heading, and the first
    Write-Set table of the one Sprint Plan one folder above the session folder, read with
    ``lint_execution_input_plan._write_set`` (alias legend expanded). The task is matched by
    the full Task ID in the row's task cell. Two paths cover each other when they meet on a
    path-component boundary or one is a folder, shown by a trailing slash, that holds the
    other. Three branches. ERROR: a Write-Set path given to the task that no Output path
    covers, because ``overlap`` cannot see that write. WARNING: an Output path outside an
    ``Outputs/`` folder that no Write-Set row of the task covers, when the Sprint Plan states
    Write-Set rows. WARNING: a path in the Expected Output section that is neither covered by
    the Output line nor by a Required Context row, as Check 54 reads a step's paths, with HTML
    comment text left out because the task-file template carries guidance comments there; a task
    with no Required Context heading is not read for this branch. A task with no ``**Output:**``
    line is skipped, because there is no write set to compare. A path with a placeholder, a
    glob, a regex operator or a URL is skipped. It cannot see a Write-Set row whose task
    cell names no full Task ID, a second Write-Set table, a Sprint Plan that is missing or not
    unique, a write the plan states nowhere, or an Expected Output path written without a
    code span.
    """
    findings = []
    root = Path(context.plan_root)
    cache: dict = {}
    for rel, lines in _task_files(context):
        output_line = next(((n, ln) for n, ln in enumerate(lines, start=1) if _OUTPUT_LINE_RE.match(ln)), None)
        output = output_paths("\n".join(lines))
        if output_line is None or output is None:
            continue
        header = list(_header_fields(lines))
        task_id = next((m.group(1) for _n, ln in header if (m := _TASK_ID_HEADER_RE.match(ln))), "")
        task_id = task_id.replace("`", "").replace("*", "").strip()
        rows = _sprint_write_set(root / rel, cache) if task_id else None
        number, text = output_line
        if rows is not None:
            owned = []
            for _index, path, tasks in rows:
                if task_id in tasks and _is_comparable(path) and path not in owned:
                    owned.append(path)
            for path in owned:
                if not any(_path_covers(declared, path) for declared in output):
                    findings.append(_finding(
                        check=59, severity=SEVERITY_ERROR, file=rel, line=number, command=text.strip(),
                        message=(
                            f"The Sprint Plan Write-Set gives {path!r} to {task_id}, and no path on this "
                            "task's **Output:** line covers it. The overlap check reads the Output line as "
                            "the task's write set, so it cannot see this write. Add the path to the Output "
                            "line, or correct the Write-Set row (templates/task-file.md, the Output comment)"
                        ),
                    ))
            for path in sorted(output):
                if _OUTPUTS_FOLDER_RE.search(path) or not _is_comparable(path):
                    continue
                if not any(_path_covers(declared, path) for declared in owned):
                    findings.append(_finding(
                        check=59, severity=SEVERITY_WARNING, file=rel, line=number, command=text.strip(),
                        message=(
                            f"This task's **Output:** line names {path!r} outside an Outputs/ folder, and no "
                            f"Sprint Plan Write-Set row gives it to {task_id}. The Write-Set is what the "
                            "Master Plan intersects across parallel sprints, so the file is invisible there. "
                            "Add a Write-Set row, or drop the path from the Output line "
                            "(templates/sprint-plan.md, the Write-Set section)"
                        ),
                    ))
        if not any(True for _hit in _walk_section(lines, ("required context",), first_only=True)):
            continue
        covered = [
            path for _n, _ln, cells, _header_cells in _required_context_rows(lines)
            for path in _row_paths(cells)
        ]
        seen = set()
        for line_number, line in _outside_comments(_expected_output_lines(lines)):
            if _NEGATION_RE.search(line):
                continue
            for path in _step_reads(line):
                if path in seen or any(_path_covers(declared, path) for declared in output):
                    continue
                if any(_row_covers(row, path) for row in covered):
                    continue
                seen.add(path)
                findings.append(_finding(
                    check=59, severity=SEVERITY_WARNING, file=rel, line=line_number, command=line.strip(),
                    message=(
                        f"This Expected Output line names {path!r}, and neither the **Output:** line nor a "
                        "Required Context row covers it. Add the path to the Output line if the task writes "
                        "it, or to Required Context if the task reads it"
                    ),
                ))
    return findings


# --- Check 60: Depends On mirrors the producers of the files a task's Required Context reads ---
_TASK_ID_RE = re.compile(r"^(?P<prefix>.+)-S(?P<sprint>\d+)-(?P<session>\d+)-(?P<number>\d+)$")
_CROSS_PREFIXES = ("cross-session", "cross-sprint")


def _parse_task_id(task_id: str):
    """``(plan prefix, sprint, session, task number)`` of a full Task ID such as
    ``QZX-S01-01-02``, or None when the text is not one."""
    match = _TASK_ID_RE.match(task_id)
    if match is None:
        return None
    return (
        match.group("prefix"),
        int(match.group("sprint")),
        int(match.group("session")),
        int(match.group("number")),
    )


def _has_folder(path: str) -> bool:
    """A whole path holds at least one folder. A bare file name never names one file, so it is
    never matched, as ``lint_layer_disjointness`` §1.31 reads a mate's Output."""
    return "/" in path.strip("/")


def _anchored_outputs(rel: str, output) -> list:
    """The paths a producer's ``**Output:**`` line declares, as paths a reader can cite. A path
    that starts with ``Outputs/`` is relative to the producer's own session folder, so that
    folder is put in front of it. A bare file name, a placeholder, a glob and a URL are left out."""
    folder = Path(rel).parent.as_posix()
    found = []
    for path in sorted(output):
        if _UNRESOLVED_RE.search(path):
            continue
        if path.startswith("Outputs/") and folder not in ("", "."):
            path = f"{folder}/{path}"
        if _has_folder(path):
            found.append(path)
    return found


def _required_context_reads(lines) -> list:
    """The whole paths a task's Required Context rows name, in order and without repeats. A
    folder, a bare file name, a placeholder, a glob and a URL name no one file and are left out."""
    reads = []
    for _number, _line, cells, _header in _required_context_rows(lines):
        for path in _row_paths(cells):
            if path.endswith("/") or not _is_scope_path(path) or _UNRESOLVED_RE.search(path):
                continue
            if _has_folder(path) and path not in reads:
                reads.append(path)
    return reads


def _dependency_class(reader, producer):
    """How ``reader``'s ``Depends On`` must name ``producer``: ``same-session`` for an earlier
    task of the same session, ``cross-session`` for an earlier session of the same sprint, and
    ``cross-sprint`` for an earlier sprint. None when ``producer`` does not come first."""
    if reader[0] != producer[0]:
        return None
    if producer[1] != reader[1]:
        return "cross-sprint" if producer[1] < reader[1] else None
    if producer[2] != reader[2]:
        return "cross-session" if producer[2] < reader[2] else None
    return "same-session" if producer[3] < reader[3] else None


def _reads_a_product(reader_reads, producer_outputs):
    """The first path ``reader_reads`` names that a declared output of the producer covers."""
    return next(
        (read for read in reader_reads if any(_path_covers(out, read) for out in producer_outputs)),
        None,
    )


def _mirror_tasks(context) -> list:
    """One record per task file that carries a parseable ``**Task ID:**``, with its Output
    paths, Required Context reads and ``Depends On`` header."""
    tasks = []
    for rel, lines in _task_files(context):
        header = list(_header_fields(lines))
        task_id = next((m.group(1) for _n, ln in header if (m := _TASK_ID_HEADER_RE.match(ln))), "")
        task_id = task_id.replace("`", "").replace("*", "").strip()
        key = _parse_task_id(task_id)
        if key is None:
            continue
        depends = next(((n, m.group(1)) for n, ln in header if (m := _DEPENDS_HEADER_RE.match(ln))), None)
        output = output_paths("\n".join(lines)) or set()
        tasks.append({
            "rel": rel, "id": task_id, "key": key, "depends": depends,
            "outputs": _anchored_outputs(rel, output), "reads": _required_context_reads(lines),
        })
    return tasks


def _check60_depends_on_mirrors_required_context_producers(context) -> list:
    """Check 60 -- a task's ``Depends On`` does not mirror the producers of the files its Required
    Context reads (Reviewer Checks 037 and 038, and the same-session row of the mirroring table in
    task-file-and-tracking-requirements.md). Input: every task file's ``**Task ID:**``,
    ``**Depends On:**`` header and ``**Output:**`` line, and the whole paths named in every cell
    of its Required Context rows. A task is a producer of a read when an earlier task's Output
    path covers the path, as Check 59 reads a cover: the paths meet on a path-component
    boundary, or one is a folder that holds the other. A path needs at least one folder, so a
    bare file name is never matched, and an ``Outputs/`` path is read under its producer's own
    session folder. Earlier means the Task ID's order: a lower task number in the same session,
    an earlier session of the same sprint, or an earlier sprint. ERROR: a producer the reader
    needs whose entry is missing, or is present under the wrong form. The form is the task
    number for the same session, ``cross-session:`` and the full Task ID for an earlier
    session of the same sprint, and ``cross-sprint:`` and the full Task ID for an earlier
    sprint. A ``Cross-Sprint Refs`` listing does not replace the entry (templates/task-file.md).
    WARNING: a ``Depends On`` entry that names a task whose Output covers no file this task's
    Required Context reads, because an ordering gate can be legitimate. A task with no
    ``**Task ID:**`` or ``**Depends On:**`` header, or whose Required Context names no whole
    path, is skipped. It cannot see a read written outside Required Context, a read of a file
    the producer writes without declaring it on its Output line, a path with a placeholder, a
    glob or a URL, a task that appears twice under one Task ID, or a producer in a plan
    with another abbreviation.
    """
    findings = []
    tasks = _mirror_tasks(context)
    by_key = {}
    for task in tasks:
        by_key.setdefault(task["key"], task)
    for reader in tasks:
        if reader["depends"] is None or not reader["reads"]:
            continue
        line, cell = reader["depends"]
        entries = _dependency_set(cell)
        command = f"**Depends On:**{cell}".strip()
        for producer in tasks:
            if producer is reader:
                continue
            kind = _dependency_class(reader["key"], producer["key"])
            if kind is None:
                continue
            read = _reads_a_product(reader["reads"], producer["outputs"])
            if read is None:
                continue
            number = producer["id"].rsplit("-", 1)[-1]
            needed = ("", producer["key"][3]) if kind == "same-session" else (kind, producer["id"])
            if needed in entries:
                continue
            wanted = number if kind == "same-session" else f"{kind}: {producer['id']}"
            wrong = sorted(f"{prefix}: {body}" if prefix else str(body)
                           for prefix, body in entries if body == producer["id"])
            how = (f"names it as {wrong[0]!r}, and the {kind} form is {wanted!r}" if wrong
                   else f"has no {wanted!r} entry")
            findings.append(_finding(
                check=60, severity=SEVERITY_ERROR, file=reader["rel"], line=line, command=command,
                message=(
                    f"Task {reader['id']} reads {read!r} in Required Context, and task {producer['id']} "
                    f"declares that file on its Output line, but this Depends On {how}. A producer in "
                    f"{kind.replace('-', ' ')} is mirrored in that form, and Cross-Sprint Refs does not "
                    "replace it (task-file-and-tracking-requirements.md, Reviewer Checks 037 and 038)"
                ),
            ))
        for prefix, body in sorted(entries, key=str):
            if prefix == "" and isinstance(body, int):
                key = (reader["key"][0], reader["key"][1], reader["key"][2], body)
            elif prefix in _CROSS_PREFIXES and isinstance(body, str):
                key = _parse_task_id(body)
            else:
                continue
            target = by_key.get(key)
            if target is None or target is reader or _reads_a_product(reader["reads"], target["outputs"]):
                continue
            shown = f"{prefix}: {body}" if prefix else f"{body:02d}"
            findings.append(_finding(
                check=60, severity=SEVERITY_WARNING, file=reader["rel"], line=line, command=command,
                message=(
                    f"Task {reader['id']} lists {shown!r} in Depends On, and task {target['id']} declares "
                    "no file on its Output line that this task's Required Context reads. An ordering "
                    "gate can be legitimate. Remove the entry, or add the file it produces to Required "
                    "Context (task-file-and-tracking-requirements.md, Reviewer Checks 037 and 038)"
                ),
            ))
    return findings


CHECKS = [
    _check54_step_reads_path_without_required_context_row,
    _check57_depends_on_layers_disagree,
    _check58_cross_sprint_read_without_refs_field,
    _check59_write_set_output_expected_output_agree,
    _check60_depends_on_mirrors_required_context_producers,
]
