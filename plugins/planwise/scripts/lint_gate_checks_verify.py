#!/usr/bin/env python3
"""Lint checks that read one task file's gate text, registered into the linter.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check takes
the lint context duck-typed -- it reads only ``commands``, ``plan_root`` and
``markdown_files()`` -- and builds its finding with the same six keys the
linter's ``make_finding`` writes. The severity strings equal the linter's
``SEVERITY_*`` constants. A test pins both agreements.

Every check here is static: none runs a command. Checks 30 and 31 are
heuristic, because what counts as a gate anchor or a status gate is a
judgment, so they report at WARNING and never decide a verdict alone.
"""

import re
from pathlib import Path

from lint_gate_checks_commands import (
    _grep_pattern_and_target,
    _is_task_file,
    _pipelines,
    _tokens,
)
from lint_gate_tool_calls import GREP_TOOL_CALL_RE

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_UNCERTAIN = "UNCERTAIN"

# A verified-on-date marker is an ISO date. The word ``unverified`` marks an
# anchor its author could not measure.
_VERIFIED_MARKER_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\bunverified\b", re.IGNORECASE)

# A heading anchor: a search pattern that starts at a markdown heading marker.
_HEADING_ANCHOR_RE = re.compile(r"^\^\s*#")
# The extracted-command blocks whose gate decides PASS or FAIL. The strings
# equal the linter's ``BLOCK_AFTER`` and ``BLOCK_EXIT_CRITERION``.
_ANCHOR_BLOCKS = frozenset({"After", "exit-criterion"})

# A status test: a status word that a gate reads as complete or pending.
_STATUS_TEST_RE = re.compile(
    r"\b(?:is|are|be|been|was|were|marked|reads?|shows?|status(?:\s+(?:is|of))?)\s+"
    r"[`*\"']{0,3}(?:COMPLETE|PENDING|NOT[ _]STARTED|complete|pending)\b"
)
# A line that gates on the status: a checkbox item or a stop word. The bare
# word "gate" is not a cue, because prose that describes a gate file or names
# ``gate-*.md`` carries it without gating on anything.
_GATE_CUE_RE = re.compile(
    r"^\s*(?:>\s*)?[-*]\s+\[[ xX]\]|\b(?:STOP|HALT|prerequisite|precondition)\b",
    re.IGNORECASE,
)
# The artifact a status gate must name: a file, or the table or field it reads.
_ARTIFACT_RE = re.compile(
    r"[\w./{}-]+\.(?:md|json|ya?ml|txt|csv|py)\b|\b(?:table|row|column|field|frontmatter)s?\b",
    re.IGNORECASE,
)

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s")
_SUCCESS_CRITERIA_RE = re.compile(r"^(#{1,6})\s+Success Criteria\b", re.IGNORECASE)
_OUTPUT_FIELD_RE = re.compile(r"^\*\*Output:\*\*\s*(.+)$")
_EXPECTED_OUTPUT_RE = re.compile(r"^#{1,6}\s+Expected Output\b", re.IGNORECASE)
_PLAN_ARTIFACT_RE = re.compile(r"[\w./{}-]+\.md\b")
# The size gate a file-producing task's Success Criteria carries.
_SIZE_GATE_RE = re.compile(r"measure_files|token.*(?:gate|budget|measure)", re.IGNORECASE)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Flags that make a command write: a fixer, an applier, an upgrade.
_WRITER_FLAGS = ("--write", "--fix", "--apply", "--upgrade")
# Flags that keep a writer from writing.
_NO_WRITE_FLAGS = frozenset({"--dry-run", "--check", "--diff", "-n"})
# A token that names a scratch target.
_SCRATCH_RE = re.compile(r"scratch|\btmp\b|\btemp\b|/tmp/|mktemp|\$TMP|\$TEMP", re.IGNORECASE)


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


def _task_files(context):
    """Yield ``(rel, lines)`` for each task file, with carriage returns removed.

    A task file is a markdown file whose first heading starts ``# Task:``."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        if not _is_task_file(path):
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


def _fence_marked(lines):
    """Yield ``(number, line, fenced)``; a fence marker line counts as fenced."""
    fence = None
    for number, line in enumerate(lines, start=1):
        stripped = line.lstrip("> ").strip()
        marker = _FENCE_RE.match(stripped)
        if fence is not None:
            if marker and stripped[0] == fence[0] and len(stripped) >= len(fence):
                fence = None
            yield number, line, True
            continue
        if marker:
            fence = marker.group(1)
            yield number, line, True
            continue
        yield number, line, False


def _unfenced(lines):
    """Yield ``(number, line)`` for each line outside a fenced block."""
    for number, line, fenced in _fence_marked(lines):
        if not fenced:
            yield number, line


def _heading_anchor_commands(context):
    """Yield ``(file, line, text, notes)`` for every non-placeholder gate
    command with a grep stage whose pattern starts at a heading marker. Only
    an After-block gate or an exit criterion decides PASS or FAIL, so a
    Before-block reading is a measurement, not an anchor, and is skipped."""
    for command in context.commands:
        if command.is_placeholder or not command.is_gate or "WRONG" in command.command:
            continue
        if command.block not in _ANCHOR_BLOCKS:
            continue
        tokens = _tokens(command.command)
        if not tokens:
            continue
        for stages in _pipelines(tokens):
            if any(
                stage[0] == "grep" and _HEADING_ANCHOR_RE.match(_grep_pattern_and_target(stage)[0] or "")
                for stage in stages
            ):
                notes = f"{command.command} {command.comment} {command.annotation}"
                yield command.file, command.line, command.command, notes
                break


def _heading_anchor_tool_calls(context):
    """Yield ``(file, line, text, notes)`` for every native ``Grep`` call in a
    task file whose pattern starts at a heading marker. The line after the
    call is part of its notes, because a pre-edit comment sits there."""
    for rel, lines in _task_files(context):
        for index, line in enumerate(lines):
            if "WRONG" in line:
                continue
            for call in GREP_TOOL_CALL_RE.finditer(line):
                if _HEADING_ANCHOR_RE.match(call.group(2)):
                    following = lines[index + 1] if index + 1 < len(lines) else ""
                    yield rel, index + 1, call.group(0), f"{line} {following}"
                    break


def _check30_gate_anchor_without_verified_marker(context) -> list:
    """Check 30 -- a gate anchor carries neither a verified-on-date marker nor
    the word ``unverified`` (verify-anchor-against-artifact.md §1, the rule to
    write anchors from a live read or mark them unverified). A gate anchor here
    is a heading search: a grep gate command, or a native ``Grep`` call in a
    task file, whose pattern starts at a markdown heading marker. The command,
    its comment and its annotation line are read for an ISO date or the word
    ``unverified``. Heuristic, so WARNING: it reports and never gates alone.
    """
    findings = []
    seen = set()
    for source in (_heading_anchor_commands(context), _heading_anchor_tool_calls(context)):
        for file, line, text, notes in source:
            if (file, line) in seen or _VERIFIED_MARKER_RE.search(notes):
                continue
            seen.add((file, line))
            findings.append(_finding(
                check=30, severity=SEVERITY_WARNING, file=file, line=line, command=text,
                message=(
                    "This heading anchor carries no verified-on date and is not marked "
                    "unverified, so a runner cannot tell a measured anchor from one "
                    "restated from the criterion. Record the date of the live read, "
                    "or mark the anchor unverified"
                ),
            ))
    return findings


def _check31_status_gate_names_no_artifact(context) -> list:
    """Check 31 -- a status gate that tests complete or pending names no file
    and no table or field (verify-anchor-against-artifact.md §3). A plan states
    one status in several hand-maintained places, so a gate that names none
    reads whichever the runner opens. A status gate here is a line in a task
    file, outside a fenced block, that is a checkbox item or carries a stop
    word (STOP, HALT, prerequisite, precondition), and tests a status word. Heuristic, so WARNING: it reports and
    never gates alone.
    """
    findings = []
    for rel, lines in _task_files(context):
        for number, line in _unfenced(lines):
            if "WRONG" in line or _HEADING_LINE_RE.match(line.lstrip("> ")):
                continue
            match = _STATUS_TEST_RE.search(line)
            if match is None or not _GATE_CUE_RE.search(line) or _ARTIFACT_RE.search(line):
                continue
            findings.append(_finding(
                check=31, severity=SEVERITY_WARNING, file=rel, line=number,
                command=line.strip(),
                message=(
                    f"This status gate tests {match.group(0)!r} and names no file and no "
                    "table or field. A plan holds the same status in several places, "
                    "so the answer depends on which one the runner opens. Name the "
                    "artifact and the table or field the gate reads"
                ),
            ))
    return findings


def _success_criteria_text(lines) -> str | None:
    """The text of the Success Criteria section, or None when there is none.

    A heading is read only outside a fenced block, so a ``# comment`` line in
    a fenced command does not end the section. Fenced lines stay in the text,
    because the size gate is usually a fenced command."""
    level = None
    body: list = []
    for _number, line, fenced in _fence_marked(lines):
        heading = None if fenced else _HEADING_LINE_RE.match(line)
        if level is not None and heading and len(heading.group(1)) <= level:
            break
        if level is not None:
            body.append(line)
            continue
        criteria = None if fenced else _SUCCESS_CRITERIA_RE.match(line)
        if criteria:
            level = len(criteria.group(1))
    return None if level is None else "\n".join(body)


def _check32_file_producing_task_without_size_gate(context) -> list:
    """Check 32 -- a file-producing task has no measured size gate in its
    Success Criteria (verify-before-cite.md §9.B.8, Reviewer Check 029). Each
    produced file must land under the Read gates, and only a ``measure_files``
    run shows that. A file-producing task here has an ``Expected Output``
    section and an ``**Output:**`` field naming a markdown file. The detection
    is the source check's: Success Criteria matching ``measure_files`` or a
    token gate, budget or measure. ERROR, the source check's BLOCKER.
    """
    findings = []
    for rel, lines in _task_files(context):
        # A fenced sample of a task file is not this task's own field or section.
        if not any(_EXPECTED_OUTPUT_RE.match(line) for _number, line in _unfenced(lines)):
            continue
        output = next(
            ((number, m.group(1)) for number, line in _unfenced(lines)
             if (m := _OUTPUT_FIELD_RE.match(line.strip()))),
            None,
        )
        if output is None or not _PLAN_ARTIFACT_RE.search(output[1]):
            continue
        criteria = _success_criteria_text(lines)
        if criteria is not None and _SIZE_GATE_RE.search(criteria):
            continue
        findings.append(_finding(
            check=32, severity=SEVERITY_ERROR, file=rel, line=output[0],
            command=output[1].strip(),
            message=(
                "This task produces a markdown file, and its Success Criteria carry no "
                "measured size gate. Add a measure_files.py gate on each produced file "
                "so it lands under the Read gates before COMPLETE"
            ),
        ))
    return findings


def _writer_flag(stage):
    """The first writer flag in a stage, or None when the stage does not write."""
    if any(token in _NO_WRITE_FLAGS for token in stage[1:]):
        return None
    for token in stage[1:]:
        if token == "--":
            break
        if token in _WRITER_FLAGS or token.startswith(tuple(f"{flag}=" for flag in _WRITER_FLAGS)):
            return token
    return None


def _check33_writer_command_without_scratch_target(context) -> list:
    """Check 33 -- a verification command runs a writer (``--write``,
    ``--fix``, ``--apply`` or ``--upgrade``) and names no scratch target
    (verification-task-authoring.md §7, the checklist item on an anchor or
    verification command that runs a writer). Run against the live tree, a
    writer changes the files the next gate reads. A stage that also passes
    ``--dry-run``, ``--check`` or ``--diff`` does not write. A scratch target
    is a token naming a scratch, tmp or temp location. ERROR.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or "WRONG" in command.command:
            continue
        tokens = _tokens(command.command)
        if not tokens:
            continue
        flags = [
            flag for stages in _pipelines(tokens) for stage in stages
            if (flag := _writer_flag(stage)) is not None
        ]
        if not flags or any(_SCRATCH_RE.search(token) for token in tokens):
            continue
        findings.append(_finding(
            check=33, severity=SEVERITY_ERROR, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This verification command runs a writer ({flags[0]}) and names no "
                "scratch target, so it rewrites the live files the next gate reads. "
                "Copy the subject to a scratch directory and point the writer there"
            ),
        ))
    return findings


CHECKS = [
    _check30_gate_anchor_without_verified_marker,
    _check31_status_gate_names_no_artifact,
    _check32_file_producing_task_without_size_gate,
    _check33_writer_command_without_scratch_target,
]
