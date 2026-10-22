#!/usr/bin/env python3
"""Lint checks that read more than one plan file, registered into the linter.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. Like ``lint_gate_checks_commands``, this module
imports nothing from the linter (the linter runs as ``__main__`` when invoked
as a script, so an import back would load a second copy). Each check takes
the lint context duck-typed -- it reads only ``commands``, ``plan_root`` and
``markdown_files()`` -- and builds findings with the six keys the linter's
``make_finding`` writes. The severity strings equal the linter's
``SEVERITY_*`` constants, and a test pins both agreements.

The command-text parsers (``_tokens``, ``_pipelines``, ``_diff_parts``,
``_norm``, ``_is_task_file``) come from ``lint_gate_checks_commands``, which
imports nothing from the linter either, so the import adds no cycle.

These checks read files the command extractor never opens: a Signoff's anchor
tables, a sibling task's ``**Output:**`` line, and a sprint's Recovery files.
Each reads them itself from ``markdown_files()``. Nothing here runs a command.

A sprint folder is a directory named ``Sprint-NN-{Name}``; a task file is a
markdown file whose first heading starts ``# Task:``.
"""

import re
from pathlib import Path

from lint_gate_checks_commands import (
    _diff_parts,
    _is_task_file,
    _norm,
    _pipelines,
    _tokens,
)

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_UNCERTAIN = "UNCERTAIN"

_HEADING_RE = re.compile(r"^(#{1,6})\s")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LIST_BULLET_RE = re.compile(r"^[-*+]\s+")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SIGNOFF_NAME_RE = re.compile(r"signoff\.md$", re.IGNORECASE)

# Two or more inline-code outcomes joined into one "or" list after a verb or
# arrow that states what the anchor accepts:
# "records `repoint`, `route`, or `CLOSED-NO-ACTION`". A list after any other
# word ("under `## A` or `## B`") names places, not outcomes.
_OUTCOME_LIST_RE = re.compile(
    r"(?:\b(?:records?|accepts?|reports?|reads?|prints?|returns?|shows?|equals?|is|are)\b|→|->)"
    r"\s+(?:either\s+|one of\s+)?"
    r"(`[^`\n]+`(?:\s*,\s*`[^`\n]+`)*\s*,?\s*\bor\s+`[^`\n]+`)",
    re.IGNORECASE,
)
_BRANCH_PARENTHETICAL_RE = re.compile(r"\((\d+)\s+branch(?:es)?\b", re.IGNORECASE)
_BRANCH_CELL_RE = re.compile(r"^\s*(\d+)\s*/\s*\d+")

# A sentence or header cell that declares where the anchors run:
# "Run all anchors from `<dir>/`." or "cwd: `<dir>`".
_CWD_DECLARATION_RE = re.compile(
    r"\b(?:run|execute)\b[^`|]*?\bfrom\s+`([^`]+)`|\bcwd\b\s*(?:is|:|=)?\s*`([^`]+)`",
    re.IGNORECASE,
)
_PLACEHOLDER_CHARS = frozenset("<>{}$*?")
_PATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_./-]*$")

_INEQUALITY_RE = re.compile(r">=|<=|≥|≤|\bat (?:least|most)\b|\bor (?:more|fewer)\b|\s[<>]\s", re.IGNORECASE)

_SPRINT_DIR_RE = re.compile(r"^Sprint-\d+")
_BASE_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_BASE)\b")
_DIFF_LINE_RE = re.compile(r"\bgit\b.*\bdiff\b")
_PIN_WORD_RE = re.compile(r"rev-parse|\brecords?\b|\bpin(?:s|ned)?\b", re.IGNORECASE)
_STATUS_PRECONDITION_RE = re.compile(r"\bstatus\s+--porcelain\b")
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def _finding(*, check, severity, file, line, command, message) -> dict:
    """Build a finding with the six keys the linter's ``make_finding`` writes."""
    return {
        "check": check,
        "severity": severity,
        "file": file,
        "line": line,
        "command": command,
        "message": message,
    }


def _lines(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [line.rstrip("\r") for line in text.split("\n")]


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _unquote(line: str) -> str:
    """Drop blockquote markers, so a table inside a callout still reads."""
    stripped = line.lstrip()
    while stripped.startswith(">"):
        stripped = stripped[1:].lstrip()
    return stripped


def _has_placeholder(text: str) -> bool:
    return any(char in _PLACEHOLDER_CHARS for char in text)


# ---------------------------------------------------------------------------
# Signoff anchor tables (Checks 26 and 27)
# ---------------------------------------------------------------------------


def _cells(row: str) -> list:
    cells = [cell.strip() for cell in _CELL_SPLIT_RE.split(row.strip())]
    if cells and not cells[0]:
        cells = cells[1:]
    if cells and not cells[-1]:
        cells = cells[:-1]
    return cells


def _cwd_declaration(text: str):
    match = _CWD_DECLARATION_RE.search(text)
    if not match:
        return None
    return (match.group(1) or match.group(2)).strip()


def _anchor_tables(lines: list) -> list:
    """Tables under a heading that names anchors, each with its header cells,
    data rows ``(line, cells, text)`` and the cwd declared above it or in its
    header row (``(dir, line)`` or None). A deeper heading inside an anchor
    section keeps the section open."""
    tables: list = []
    anchor_level = 0
    cwd = None
    current = None
    in_fence = False
    for number, raw in enumerate(lines, start=1):
        stripped = _unquote(raw).strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            current = None
            continue
        if in_fence:
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            if "anchor" in stripped.lower():
                anchor_level, cwd = level, None
            elif anchor_level and level <= anchor_level:
                anchor_level, cwd = 0, None
            current = None
            continue
        if not anchor_level:
            continue
        if stripped.startswith("|"):
            if current is None:
                header = _cells(stripped)
                declared = _cwd_declaration(stripped)
                current = {
                    "header": header,
                    "cwd": (declared, number) if declared else cwd,
                    "rows": [],
                }
                tables.append(current)
            elif not _TABLE_SEPARATOR_RE.match(stripped):
                current["rows"].append((number, _cells(stripped), stripped))
            continue
        current = None
        declared = _cwd_declaration(stripped)
        if declared:
            cwd = (declared, number)
    return tables


def _column(header: list, word: str):
    for index, cell in enumerate(header):
        if word in cell.lower():
            return index
    return None


def _anchor_text(table: dict, cells: list, row: str) -> str:
    index = _column(table["header"], "anchor")
    if index is not None and index < len(cells):
        return cells[index]
    return row


def _signoff_tables(context):
    """Yield ``(rel, table)`` for every anchor table in a Signoff file."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        if not _SIGNOFF_NAME_RE.search(path.name) or _is_task_file(path):
            continue
        rel = _rel(path, root)
        for table in _anchor_tables(_lines(path)):
            yield path, rel, table


def _listed_outcomes(text: str) -> int:
    return max((len(_INLINE_CODE_RE.findall(m.group(1))) for m in _OUTCOME_LIST_RE.finditer(text)), default=0)


def _stated_branches(table: dict, cells: list, row: str):
    match = _BRANCH_PARENTHETICAL_RE.search(row)
    if match:
        return int(match.group(1))
    index = _column(table["header"], "branch")
    if index is not None and index < len(cells):
        cell = _BRANCH_CELL_RE.match(cells[index])
        if cell:
            return int(cell.group(1))
    return None


def _check26_anchor_branch_count(context) -> list:
    """Check 26 -- a Signoff anchor row lists two or more outcomes and carries
    no branch count equal to them (gate-anchor-outcome-set.md §10.7). The
    outcomes are inline-code values joined into one "or" list in the anchor
    cell. The count is a parenthetical ``(N branches`` or the accepted figure
    of a ``Branches`` cell written ``accepted/task``. Without the count, parity
    with the owning task's terminal branches is not checkable without
    re-reading both files. Deriving the task's branches from its prose stays
    Reviewer Check 095. WARNING, the severity that check states.
    """
    findings = []
    for _, rel, table in _signoff_tables(context):
        for number, cells, row in table["rows"]:
            listed = _listed_outcomes(_anchor_text(table, cells, row))
            if listed < 2:
                continue
            stated = _stated_branches(table, cells, row)
            if stated == listed:
                continue
            if stated is None:
                detail = "carries no branch count"
            else:
                detail = f"states {stated} branches"
            findings.append(_finding(
                check=26, severity=SEVERITY_WARNING, file=rel, line=number, command=row,
                message=(
                    f"This anchor lists {listed} accepted outcomes and {detail}. Carry the "
                    f"count inline, as ({listed} branches -- matches the task's terminal "
                    "outcomes), so set parity with the owning task is checkable"
                ),
            ))
    return findings


def _resolve_dir(declared: str, plan_root: Path):
    if _has_placeholder(declared):
        return None
    candidate = Path(declared)
    if candidate.is_absolute():
        return candidate if candidate.is_dir() else None
    for base in (plan_root, *plan_root.parents):
        if (base / candidate).is_dir():
            return base / candidate
    return None


def _anchor_paths(text: str):
    """Relative path tokens inside the inline code of an anchor cell. A token
    qualifies when every segment holds a letter and it ends in a file
    extension or a slash; placeholders, flags and absolute paths are skipped."""
    for span in _INLINE_CODE_RE.findall(text):
        for token in _tokens(span) or []:
            if token.startswith(("-", "/", "~")) or "://" in token or _has_placeholder(token):
                continue
            if "/" not in token or not _PATH_TOKEN_RE.match(token):
                continue
            segments = [s for s in token.split("/") if s]
            if not all(s in (".", "..") or re.search(r"[A-Za-z]", s) for s in segments):
                continue
            if token.endswith("/") or "." in segments[-1].lstrip("."):
                yield _norm(token)


def _resolves(cwd: Path, token: str) -> bool:
    target = cwd / token
    if target.exists():
        return True
    first = Path(token).parts[0]
    if first == "..":
        return target.parent.exists()
    return (cwd / first).exists()


def _check27_anchor_path_outside_declared_cwd(context) -> list:
    """Check 27 -- a path in a Signoff anchor row does not resolve from the
    cwd its table declares (gate-command-semantics.md §10.8 trap 4). The cwd
    is read from a "Run all anchors from `<dir>`" or "cwd: `<dir>`" sentence
    above the table, or from its header row. A path whose first segment is
    absent under that cwd cannot resolve whatever the task produces, so the
    anchor fails correct work. A path that may be created later is accepted
    when its first segment exists. WARNING; UNCERTAIN when the declared cwd
    itself does not resolve from the plan root or any parent.
    """
    root = Path(context.plan_root)
    findings = []
    for path, rel, table in _signoff_tables(context):
        if not table["cwd"]:
            continue
        declared, declared_line = table["cwd"]
        cwd = _resolve_dir(declared, root)
        if cwd is None:
            findings.append(_finding(
                check=27, severity=SEVERITY_UNCERTAIN, file=rel, line=declared_line,
                command=declared,
                message=(
                    f"The anchor table declares the cwd {declared!r}, which does not resolve "
                    "from the plan root or any parent, so its paths were not checked"
                ),
            ))
            continue
        for number, cells, row in table["rows"]:
            for token in _anchor_paths(_anchor_text(table, cells, row)):
                if _resolves(cwd, token):
                    continue
                elsewhere = [
                    _rel(base, root) or "."
                    for base in (path.parent, root)
                    if (base / token).exists() or (base / Path(token).parts[0]).is_dir()
                ]
                hint = f" It resolves from {elsewhere[0]!r} instead." if elsewhere else ""
                findings.append(_finding(
                    check=27, severity=SEVERITY_WARNING, file=rel, line=number, command=token,
                    message=(
                        f"The path {token!r} does not resolve from the declared cwd "
                        f"{declared!r}, so this anchor fails on every run.{hint} Write the "
                        "path from the declared cwd, or state the exception in the header"
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# Cross-task count (Check 28)
# ---------------------------------------------------------------------------


def _output_paths(lines: list) -> list:
    """Paths in the first ``**Output:**`` line: the first word of each inline
    code span, placeholders skipped."""
    for raw in lines:
        stripped = _LIST_BULLET_RE.sub("", _unquote(raw).strip())
        if not stripped.startswith(("**Output:**", "**Outputs:**")):
            continue
        paths = []
        for span in _INLINE_CODE_RE.findall(stripped):
            words = span.split()
            if words and not _has_placeholder(words[0]):
                paths.append(_norm(words[0]))
        return paths
    return []


def _covers(gate_forms, output: str) -> bool:
    """True when any anchored form of a gate pathspec covers an Output path,
    compared by whole path components from the same root: the two are equal,
    the pathspec is a directory holding the Output, or the Output is a
    directory holding the pathspec. A pathspec that is only a suffix or a
    middle segment of the Output (``tests`` against ``a/tests/b.py``) does
    not match."""
    out = _norm(output).rstrip("/")
    if not out:
        return False
    for form in gate_forms:
        gate = _norm(form).rstrip("/")
        if gate and (gate == out or out.startswith(gate + "/") or gate.startswith(out + "/")):
            return True
    return False


def _anchored_forms(spec: str, repo_dir) -> tuple:
    """The pathspec as written, and joined to the gate's relative ``-C``
    directory, so an Output written from the outer root compares with the
    pathspec from the same root."""
    spec = _norm(spec)
    if repo_dir is None or Path(repo_dir).is_absolute() or Path(spec).is_absolute():
        return (spec,)
    return (spec, _norm(repo_dir.rstrip("/\\") + "/" + spec))


_EXCLUDE_PATHSPEC_RE = re.compile(r"^:(?:\(exclude\)|!|\^)(.+)$")


def _name_only_count_paths(command):
    """Return ``(paths, excludes)`` of every ``git diff --name-only -- <paths>
    | wc -l`` pipeline in the command, each entry a tuple of anchored forms
    (see ``_anchored_forms``). An exclude pathspec (``:(exclude)X``, ``:!X``,
    ``:^X``) removes files from the count; other magic is skipped."""
    paths, excludes = [], []
    for stages in _pipelines(_tokens(command.command) or []):
        for index, stage in enumerate(stages):
            parts = _diff_parts(stage)
            if parts is None or "--name-only" not in stage:
                continue
            counted = any(
                later[0] == "wc" and ("-l" in later or "--lines" in later)
                for later in stages[index + 1:]
            )
            if not counted:
                continue
            for spec in parts[2]:
                if _has_placeholder(spec):
                    continue
                exclude = _EXCLUDE_PATHSPEC_RE.match(spec)
                if exclude:
                    excludes.append(_anchored_forms(exclude.group(1), parts[0]))
                elif not spec.startswith(":"):
                    paths.append(_anchored_forms(spec, parts[0]))
    return paths, excludes


def _check28_count_over_sibling_output(context) -> list:
    """Check 28 -- a gate asserts ``git diff --name-only -- <files> | wc -l``
    equals N while a sibling task's ``**Output:**`` names one of those files
    (gate-denominator-integrity.md §2). The sibling's edit supplies part of
    the count, so the gate passes with this task's work missing and fails
    correct additive work. A sibling is another task file in the same folder
    as the gate, the tasks one session dispatches into one working tree. An
    Output an exclude pathspec removes is not counted. A gate whose note
    states an inequality (``>=``, "at least") is skipped. Placeholder lines
    are read, because the pathspec is usually literal beside a base slot.
    ERROR.
    """
    root = Path(context.plan_root)
    outputs = {}
    for path in context.markdown_files():
        if _is_task_file(path):
            outputs[path] = _output_paths(_lines(path))
    findings = []
    for command in context.commands:
        if not command.is_gate:
            continue
        if _INEQUALITY_RE.search(f"{command.comment} {command.annotation}"):
            continue
        paths, excludes = _name_only_count_paths(command)
        if not paths:
            continue
        hits = sorted({
            (_rel(path, root), gate[0])
            for path, owned in outputs.items()
            if path != command.path and path.parent == command.path.parent
            for gate in paths for output in owned
            if _covers(gate, output) and not any(_covers(ex, output) for ex in excludes)
        })
        if not hits:
            continue
        named = "; ".join(f"{gate} (Output of {task})" for task, gate in hits[:3])
        more = f"; and {len(hits) - 3} more" if len(hits) > 3 else ""
        findings.append(_finding(
            check=28, severity=SEVERITY_ERROR, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This gate counts changed files over pathspecs a sibling task also writes: "
                f"{named}{more}. The sibling's edit supplies part of the count, so the gate "
                "passes with this task's work missing. Prove each file's content separately"
            ),
        ))
    return findings


# ---------------------------------------------------------------------------
# Sprint base pin (Check 29)
# ---------------------------------------------------------------------------


def _sprint_dirs(root: Path) -> list:
    dirs = [root] if _SPRINT_DIR_RE.match(root.name) else []
    dirs.extend(sorted(p for p in root.rglob("*") if p.is_dir() and _SPRINT_DIR_RE.match(p.name)))
    return dirs


def _order_key(rel: Path, is_task: bool) -> tuple:
    """Session-level files sort before the session's task files."""
    return (rel.parent.parts, 1 if is_task else 0, rel.name)


def _is_repo_touching(path: Path, outputs: list) -> bool:
    """True when an Output path lies outside the plan: not under ``Outputs/``,
    not reached through ``../``, and not an existing plan-relative file."""
    return any(
        "/" in out and not out.startswith(("Outputs/", "../")) and not (path.parent / out).exists()
        for out in outputs
    )


def _sprint_files(sprint: Path):
    """Return ``(plan_files, recovery_files)`` for one sprint, each a list of
    ``(path, rel, lines, is_task)``. ``Outputs`` folders are skipped."""
    plan, recovery = [], []
    for path in sorted(sprint.rglob("*.md")):
        rel = path.relative_to(sprint)
        if not path.is_file() or "Outputs" in rel.parts:
            continue
        entry = (path, rel, _lines(path), _is_task_file(path))
        (recovery if "recovery" in path.name.lower() else plan).append(entry)
    return plan, recovery


def _first_diff_uses(plan_files) -> dict:
    """Map each ``*_BASE`` name to the ``(key, path, line, text)`` of the first
    line that runs a git diff against it. Series bases are adopted, not
    pinned, per sprint, so they are left out."""
    uses: dict = {}
    for path, rel, lines, is_task in plan_files:
        key = _order_key(rel, is_task)
        for number, line in enumerate(lines, start=1):
            if not _DIFF_LINE_RE.search(line):
                continue
            for name in _BASE_NAME_RE.findall(line):
                if "SERIES" in name:
                    continue
                if name not in uses or key < uses[name][0]:
                    uses[name] = (key, path, number, line.strip())
    return uses


def _pins(lines: list, name: str) -> bool:
    if not any(_STATUS_PRECONDITION_RE.search(line) for line in lines):
        return False
    return any(name in line and _PIN_WORD_RE.search(line) for line in lines)


def _check29_sprint_base_not_pinned(context) -> list:
    """Check 29 -- a sprint runs ``git diff`` against a ``*_BASE`` name that no
    task or Orchestration file pins behind an empty-status precondition by
    the sprint's first repo-touching task, and no Recovery file records with a
    commit id (gate-diff-baseline-pinning.md §8.1 and §8.4; Reviewer Check 077
    steps c and d). A pin is a line naming the base beside ``rev-parse``,
    "record" or "pin", in a file that also runs ``git status --porcelain``.
    The pin may sit no later than the first repo-touching task (a task whose
    Output names a path outside the plan) or the base's first diff use,
    whichever comes later. A gate scoped to a base nobody pinned reads the
    whole working tree. Ordering inside one file stays Reviewer Check 077.
    Series bases are skipped. ERROR.
    """
    root = Path(context.plan_root)
    findings = []
    for sprint in _sprint_dirs(root):
        plan_files, recovery_files = _sprint_files(sprint)
        uses = _first_diff_uses(plan_files)
        if not uses:
            continue
        repo_keys = [
            _order_key(rel, True) for path, rel, lines, is_task in plan_files
            if is_task and _is_repo_touching(path, _output_paths(lines))
        ]
        first_repo = min(repo_keys) if repo_keys else None
        for name, (use_key, use_path, use_line, use_text) in sorted(uses.items()):
            cutoff = max(use_key, first_repo) if first_repo else use_key
            pinned = any(
                _order_key(rel, is_task) <= cutoff and _pins(lines, name)
                for path, rel, lines, is_task in plan_files
                if is_task or "orchestration" in path.name.lower()
            )
            recorded = any(
                name in line and _SHA_RE.search(line)
                for _, _, lines, _ in recovery_files for line in lines
            )
            if pinned or recorded:
                continue
            findings.append(_finding(
                check=29, severity=SEVERITY_ERROR, file=_rel(use_path, root), line=use_line,
                command=use_text,
                message=(
                    f"This sprint diffs against {name}, but no task or Orchestration file "
                    "pins it behind an empty git status --porcelain precondition by the "
                    "first repo-touching task, and no Recovery file records its value. "
                    f"Pin {name}=$(git -C <repo> rev-parse HEAD) before the first edit and "
                    "record it in Recovery Key Findings"
                ),
            ))
    return findings


CHECKS = [
    _check26_anchor_branch_count,
    _check27_anchor_path_outside_declared_cwd,
    _check28_count_over_sibling_output,
    _check29_sprint_base_not_pinned,
]
