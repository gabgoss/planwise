#!/usr/bin/env python3
"""Lint checks that read the dispatch rules' text in task and orchestration files.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check takes
the lint context duck-typed -- it reads only ``plan_root`` and
``markdown_files()`` -- and builds its finding with the same six keys the
linter's ``make_finding`` writes. The sibling module ``lint_gate_checks_verify``
supplies the task-file reader and the finding builder.

Every check here is advisory: it prints the lines it found and reports at
WARNING, so none decides a verdict alone. Each is a text heuristic, and each
docstring states what its heuristic cannot see.

``subject_counts`` returns how many files and lines each check examined, so a
caller can tell an empty input from a clean one.
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from lint_gate_checks_verify import (
    _OUTPUT_FIELD_RE,
    SEVERITY_WARNING,
    _fence_marked,
    _finding,
    _task_files,
    _unfenced,
)
from markdown_parser import split_row_cells

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:<!--.*)?$")
_CODE_SPAN_RE = re.compile(r"`[^`]*`")

# --- Check 42: premise phrases (dispatch-brief-neutrality.md §1) ---
_PREMISE_RE = re.compile(
    r"\b(?:probably\s+find|be\s+willing\s+to\s+conclude|likely\s+headline\s+is)\b",
    re.IGNORECASE,
)
_BRIEF_SECTIONS = ("objective", "execution steps")

# --- Check 43: a write to a path outside the Output field (dispatch-decomposition-graph.md §2) ---
_WRITE_VERB_RE = re.compile(r"\b(?:amend|absorb|stamp)(?:s|ed|ing)?\b", re.IGNORECASE)
_PATH_TOKEN_RE = re.compile(r"[\w./{}-]+\.(?:md|py|json|ya?ml|txt|csv|template)\b")
_NEGATION_RE = re.compile(r"\b(?:WRONG|never|do\s+not|does\s+not|must\s+not|NOT)\b", re.IGNORECASE)

# --- Check 44: a measured figure without date and source (dispatch-preflight-claim-expiry.md §1) ---
_FIGURE_RE = re.compile(r"\d[\d,.]*\s*(?:KiB|KB|bytes?|lines?)\b", re.IGNORECASE)
_SIZE_HEADER_RE = re.compile(r"\b(?:KiB|KB|bytes|lines)\b", re.IGNORECASE)
_NUMBER_CELL_RE = re.compile(r"^~?\d[\d,.]*$")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SOURCE_CMD_RE = re.compile(
    r"measure_files|\bwc\s+-|\b(?:Grep|grep|Glob|git|python|pytest|suite\.py)\b", re.IGNORECASE
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")

# --- Check 45: a re-measure instruction without threshold and action (dispatch-preflight-claim-expiry.md §6) ---
_REMEASURE_RE = re.compile(r"\bre-?measure[sd]?\b", re.IGNORECASE)
_THRESHOLD_RE = re.compile(
    r"\bif\b|\bwhen\b|\bunless\b|\bdiffers?\b|\bdisagrees?\b|\bdiverg\w*|>\s*\d|<\s*\d|\d\s*%|\bmore\s+than\b|\bexceeds?\b|\boff\b",
    re.IGNORECASE,
)
_ACTION_RE = re.compile(
    r"\b(?:HALT|STOP|re-?roll|revise|correct|update|re-?derive|report|record|flag|stop|halt|replace|fix|abort|block(?:ed)?|raise|use\s+the\s+live)\b",
    re.IGNORECASE,
)


def _strip_spans(line: str) -> str:
    return _CODE_SPAN_RE.sub("", line)


def _section_lines(lines, names):
    """Yield ``(number, line)`` for each unfenced line under a heading whose text
    starts with one of ``names`` (lower case), down to the next heading of the same
    or a higher level."""
    level = None
    for number, line, fenced in _fence_marked(lines):
        if fenced:
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            depth = len(heading.group(1))
            if level is not None and depth <= level:
                level = None
            if level is None and heading.group(2).lower().lstrip("*0123456789. ").startswith(names):
                level = depth
            continue
        if level is not None:
            yield number, line


def _orchestration_files(context):
    """Yield ``(rel, lines)`` for each markdown file whose name holds ``Orchestration``."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        if "orchestration" not in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        yield rel, [raw.rstrip("\r") for raw in text.split("\n")]


def _brief_lines(context):
    """Yield ``(rel, number, line)`` for brief prose: Objective and Execution Steps of
    task files, and every line of an orchestration file (spawn prompts sit in fences there)."""
    for rel, lines in _task_files(context):
        for number, line in _section_lines(lines, _BRIEF_SECTIONS):
            yield rel, number, line
    for rel, lines in _orchestration_files(context):
        for number, line in enumerate(lines, start=1):
            yield rel, number, line


def _check42_premise_phrase_in_brief(context) -> list:
    """Check 42 -- a brief sentence holds a premise phrase such as ``probably find``
    or ``be willing to conclude`` (dispatch-brief-neutrality.md §1). Such a sentence
    names where the runner will end up, so the runner's finding returns the brief's
    own answer. Input: Objective and Execution Steps of task files, and
    orchestration files whole. A phrase inside a code span or on a line labelled
    WRONG is skipped. Advisory, so WARNING. It cannot see a premise worded
    without one of these phrases, nor one split across two lines.
    """
    findings = []
    for rel, number, line in _brief_lines(context):
        if "WRONG" in line:
            continue
        match = _PREMISE_RE.search(_strip_spans(line))
        if match is None:
            continue
        findings.append(_finding(
            check=42, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
            message=(
                f"This brief sentence holds the premise phrase {match.group(0)!r}. A premise "
                "names where the runner will probably end up, and the runner then returns it. "
                "State the measurement, correction or scope limit as context, or give the "
                "premise a reason and mark it as a premise "
                "(dispatch-brief-neutrality.md, \"Context and Premise Are Indistinguishable\")"
            ),
        ))
    return findings


def _output_text(lines) -> str | None:
    for _number, line in _unfenced(lines):
        match = _OUTPUT_FIELD_RE.match(line.strip())
        if match:
            return match.group(1)
    return None


def _declared_paths(output: str) -> list:
    """The whole path tokens the Output field names, as posix path parts."""
    return [Path(token).parts for token in _PATH_TOKEN_RE.findall(output)]


def _declared(token: str, declared) -> bool:
    """True when ``token`` equals a declared path by its file name, or is the tail of one
    (a step may name ``b/Core.md`` for a declared ``a/b/Core.md``). A file name that is
    only a substring of a declared name does not match."""
    parts = Path(token.rstrip(".")).parts
    return any(
        len(parts) <= len(path) and path[len(path) - len(parts):] == parts for path in declared
    )


def _check43_step_writes_outside_output(context) -> list:
    """Check 43 -- an Execution Step names a write (amend, absorb, stamp) to a path that
    the task's ``**Output:**`` field does not name (dispatch-decomposition-graph.md §2).
    The task can then identify an amendment and cannot apply it. A step path matches
    a whole path token of the Output field, equal or as its trailing parts, never as
    a substring of a longer name. Lines that negate (never, do not, WRONG) are skipped,
    and so is a task file with no Output field. Advisory,
    so WARNING. It cannot see a write phrased with another verb, a path without a file
    extension, a path held in a variable, or a declared directory that covers the file (a step
    path under an Output directory is reported). A bare file name matches a declared
    path with the same trailing name, so a same-named file in another directory passes.
    """
    findings = []
    for rel, lines in _task_files(context):
        output = _output_text(lines)
        if output is None:
            continue
        declared = _declared_paths(output)
        for number, line in _section_lines(lines, ("execution steps",)):
            if _NEGATION_RE.search(line):
                continue
            verb = _WRITE_VERB_RE.search(line)
            if verb is None:
                continue
            missing = [
                token for token in _PATH_TOKEN_RE.findall(line)
                if not _declared(token, declared)
            ]
            if not missing:
                continue
            findings.append(_finding(
                check=43, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
                message=(
                    f"This step names a write ({verb.group(0)}) to {missing[0]!r}, which the Output "
                    "field does not name. The runner can identify the amendment and cannot apply "
                    "it. Widen the writable set, declare a handoff table, or give the write to "
                    "its own task (dispatch-decomposition-graph.md, \"The Tell at Scaffold Time\")"
                ),
            ))
    return findings


def _required_context_rows(lines):
    """Yield ``(number, line, cells, header_cells)`` for each data row of a table that
    sits under a ``Required Context`` heading."""
    header = None
    for number, line in _section_lines(lines, ("required context",)):
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None if not stripped else header
            continue
        cells = split_row_cells(stripped)
        if cells and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells if cell):
            continue
        if header is None:
            header = cells
            continue
        yield number, line, cells, header


def _states_measured_figure(cells, header) -> bool:
    for index, cell in enumerate(cells):
        if _FIGURE_RE.search(cell):
            return True
        head = header[index] if index < len(header) else ""
        if _SIZE_HEADER_RE.search(head) and _NUMBER_CELL_RE.match(cell.strip()):
            return True
    return False


def _check44_figure_without_date_and_source(context) -> list:
    """Check 44 -- a Required Context row states a measured figure (a KiB, byte or line
    count, or a number in a column headed by one of those units) and the row holds no
    ISO date or no source command (dispatch-preflight-claim-expiry.md §1). A figure
    with neither cannot be re-taken when the gate clears. A source command is a
    measure_files run, a wc, or a named tool such as Grep or git. Advisory, so
    WARNING. It cannot see a figure stated outside a table, a date that is not the
    measurement date, or a command that is not the figure's source.
    """
    findings = []
    for rel, lines in _task_files(context):
        for number, line, cells, header in _required_context_rows(lines):
            if not _states_measured_figure(cells, header):
                continue
            row = " ".join(cells)
            has_date = _DATE_RE.search(row) is not None
            has_source = _SOURCE_CMD_RE.search(row) is not None
            if has_date and has_source:
                continue
            lacking = " and ".join(
                part for part, ok in (("a date", has_date), ("a source command", has_source)) if not ok
            )
            findings.append(_finding(
                check=44, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
                message=(
                    f"This Required Context row states a measured figure and carries no {lacking} "
                    "beside it. A refresh pass cannot find the figure by search or re-take it "
                    "at dispatch. Stamp it with the measurement date and name the command "
                    "that produced it (dispatch-preflight-claim-expiry.md, \"A Held Plan Re-Takes "
                    "Every Measurement\")"
                ),
            ))
    return findings


def _check45_remeasure_without_threshold_and_action(context) -> list:
    """Check 45 -- a re-measure instruction in a task file's comments or steps has no
    threshold clause and no action clause (dispatch-preflight-claim-expiry.md §6).
    Such an instruction produces a measurement and changes nothing. A threshold
    clause is a condition word or a comparison, and an action clause is a verb such as
    HALT, re-roll, revise, report or record. Unfenced lines only, with code spans
    removed, and lines labelled WRONG skipped. Advisory, so WARNING. It reads one line,
    so a threshold or action on the next line is not seen, and it cannot judge
    whether the clause names a real action.
    """
    findings = []
    for rel, lines in _task_files(context):
        for number, line in _unfenced(lines):
            text = _strip_spans(line)
            if "WRONG" in line or _HEADING_RE.match(line.lstrip("> ")) or not _REMEASURE_RE.search(text):
                continue
            has_threshold = _THRESHOLD_RE.search(text) is not None
            has_action = _ACTION_RE.search(text) is not None
            if has_threshold and has_action:
                continue
            lacking = " and ".join(
                part for part, ok in (("threshold", has_threshold), ("action", has_action)) if not ok
            )
            findings.append(_finding(
                check=45, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
                message=(
                    f"This re-measure instruction has no {lacking} clause. The runner measures, "
                    "finds a divergence, and has no licence to act on it. Name the threshold "
                    "that counts as a divergence and the action to take "
                    "(dispatch-preflight-claim-expiry.md, \"A Re-Measure at Dispatch Instruction "
                    "Without a Divergence Action\")"
                ),
            ))
    return findings


def subject_counts(context) -> dict:
    """Return how many subjects each check examined: files and lines read.

    Keys: ``task_files``, ``orchestration_files``, ``brief_lines`` (checks 42, 43),
    ``context_rows`` (check 44) and ``unfenced_lines`` (check 45). A caller prints
    these before the verdict, so an empty input reads differently from a clean one."""
    tasks = list(_task_files(context))
    return {
        "task_files": len(tasks),
        "orchestration_files": sum(1 for _ in _orchestration_files(context)),
        "brief_lines": sum(1 for _ in _brief_lines(context)),
        "context_rows": sum(1 for _rel, lines in tasks for _row in _required_context_rows(lines)),
        "unfenced_lines": sum(1 for _rel, lines in tasks for _row in _unfenced(lines)),
    }


CHECKS = [
    _check42_premise_phrase_in_brief,
    _check43_step_writes_outside_output,
    _check44_figure_without_date_and_source,
    _check45_remeasure_without_threshold_and_action,
]
