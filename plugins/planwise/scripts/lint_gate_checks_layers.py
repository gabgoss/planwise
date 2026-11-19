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

Every check here is advisory: it reports at WARNING, so none decides a verdict
alone. Each docstring states the predicate, the input and what the check cannot see.
"""

import re
import sys

sys.dont_write_bytecode = True

from dispatch_preflight import normalise_path, output_paths, paths_meet
from lint_gate_checks_dispatch import (
    _required_context_rows,
    _section_lines,
    _walk_section,
)
from lint_gate_checks_verify import SEVERITY_WARNING, _finding, _task_files

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


CHECKS = [
    _check54_step_reads_path_without_required_context_row,
]
