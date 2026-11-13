#!/usr/bin/env python3
"""Lint a session Orchestration's Execution Strategy against its task files.

Usage: ``lint_plan_strategy.py <orchestration.md>...``

Two rules, each reported under its own name:

``[§1.1 strategy]`` -- the rule of ``agent-orchestration-delegated.md`` §1.1
(Mandatory Triggers). The predicate: when the session's task files hold two
or more ``**Agent:** Opus`` lines, or any ``**Estimated Tokens:**`` value above
50K, the Orchestration declares ``**Mode:** DELEGATED`` (or ``Execution
Strategy: DELEGATED``). A DELEGATED Orchestration also names its trigger: a
``**Reason:**`` or ``**Trigger:**`` line that names one (Opus tasks, a token
figure, META Discovery, output chaining), or a checked ``- [x]`` item in its
Execution Strategy section. "For consistency" names no trigger.

``[§1.3 context-boundary]`` -- the rule of ``agent-orchestration-delegated.md``
§1.3 (Orchestration Context Boundary). The predicate: a DELEGATED
Orchestration's Required Context table names only plan files, that is the
Orchestration, Recovery, Sprint Plan and Master Plan files and the session's
own task files. Each row's File cell is read for code-span paths and link
targets. A row with no path passes only when its text names a task file, the
Orchestration, the Recovery file or a Sprint Plan.

Input: one or more Orchestration files. The task files are the link targets
of the Orchestration's ``Task Files`` table, resolved from the Orchestration's
folder. With no such table, the sibling ``*-NN-<Agent>-*.md`` files that carry
a ``**Task ID:**`` line are read instead.

Exit 0 when every file is clean, 1 when any rule fires (each finding printed
as ``file:line: [rule] message``), 2 on a usage error, an unreadable file, a
task file the Task Files table names but the disk does not hold, or an
Orchestration for which no task file is found at all. An Orchestration with
no Execution Strategy or Required Context section is read, not refused: no
mode means no DELEGATED checks.

Cannot see: the META Discovery and output-chaining triggers, which no header
field states, so a DELEGATED session that fires only those passes the count
test and still needs its named trigger. A DELEGATED session whose counts fire
no trigger is not reported, because one of those two may hold. A Required
Context row that names a plan file by a path whose name hides its kind (a
renamed Recovery file) reads as heavy context. Token figures in units other
than K, M or a bare count are skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from dispatch_preflight import looks_like_path, normalise, normalise_path
from markdown_parser import extract_headings, split_row_cells

_MODE_RE = re.compile(r"^\s*(?:\*\*Mode:\*\*|Execution Strategy:)\s*(DIRECT|DELEGATED)\b")
_AGENT_RE = re.compile(r"^\s*\*\*Agent:\*\*\s*([A-Za-z]+)")
_TOKENS_RE = re.compile(r"^\s*\*\*Estimated Tokens:\*\*\s*~?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?")
_REASON_RE = re.compile(r"^\s*(?:\*\*)?(?:Reason|Trigger)s?:(?:\*\*)?\s*(\S[^\r\n]*)")
_TRIGGER_WORD_RE = re.compile(
    r"opus|\b[0-9]+(?:\.[0-9]+)?\s*K\b|token|\bmeta\b|discovery|chain|feeds?\b|output",
    re.IGNORECASE,
)
_CHECKED_RE = re.compile(r"^\s*>?\s*[-*]\s*\[[xX]\]")
_FENCE_RE = re.compile(r"^\s*```")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_TASK_NAME_RE = re.compile(r"-([0-9]{2,})-[A-Za-z]+-[^/\\]*\.md\Z")
_TASK_ID_RE = re.compile(r"^\s*\*\*Task ID:\*\*", re.MULTILINE)
_PLAN_FILE_RE = re.compile(r"orchestration|recovery|sprint-plan|master-plan", re.IGNORECASE)
_PLAN_PROSE_RE = re.compile(
    r"\btask files?\b|\borchestration\b|\brecovery\b|\bsprint plan\b", re.IGNORECASE
)
_OPUS_LIMIT = 2
_TOKEN_LIMIT = 50_000


class InputError(Exception):
    """An input file is missing or unreadable."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


def unfenced_numbered(text: str) -> list[tuple[int, str]]:
    """``(line number, line)`` for every line outside a backtick fence, 1-based."""
    out: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((number, line))
    return out


def section_span(text: str, title: str) -> tuple[int, int] | None:
    """1-based ``(first, last)`` body lines of the first heading whose text holds ``title``."""
    want = normalise(title)
    headings = extract_headings(text)
    last_line = len(text.splitlines())
    for i, heading in enumerate(headings):
        if want in normalise(heading.raw.lstrip("#")):
            end = last_line
            for later in headings[i + 1:]:
                if later.level <= heading.level:
                    end = later.line - 1
                    break
            return heading.line + 1, end
    return None


def section_numbered(text: str, title: str) -> list[tuple[int, str]] | None:
    span = section_span(text, title)
    if span is None:
        return None
    return [(n, line) for n, line in unfenced_numbered(text) if span[0] <= n <= span[1]]


def table_rows(numbered: list[tuple[int, str]]) -> list[tuple[int, list[str], list[str]]]:
    """``(line, header cells, row cells)`` for every body row of every table."""
    rows: list[tuple[int, list[str], list[str]]] = []
    block: list[tuple[int, str]] = []
    for number, line in numbered + [(0, "")]:
        if line.lstrip().startswith("|"):
            block.append((number, line))
            continue
        if len(block) >= 3:
            header = split_row_cells(block[0][1])
            for row_number, row in block[2:]:
                rows.append((row_number, header, split_row_cells(row)))
        block = []
    return rows


def column(header: list[str], name: str, default: int) -> int:
    for i, cell in enumerate(header):
        if name in normalise(cell):
            return i
    return default


def task_files(orchestration: Path, text: str) -> dict[int, Path]:
    """Task number to task file, from the Task Files table or the sibling files."""
    found: dict[int, Path] = {}
    rows = section_numbered(text, "Task Files")
    if rows is not None:
        for _, header, cells in table_rows(rows):
            joined = " ".join(cells)
            link = _LINK_RE.search(joined)
            number = re.match(r"\s*([0-9]+)", cells[0]) if cells else None
            if link and number:
                found[int(number.group(1))] = orchestration.parent / link.group(1)
        missing = [p for p in found.values() if not p.is_file()]
        if missing:
            raise InputError(f"{orchestration}: Task Files names a missing file: {missing[0]}")
        if found:
            return found
    for path in sorted(orchestration.parent.glob("*.md")):
        m = _TASK_NAME_RE.search(path.name)
        if m and _TASK_ID_RE.search(read_text(path)):
            found[int(m.group(1))] = path
    if not found:
        raise InputError(f"{orchestration}: no task files found (no Task Files links, no sibling task file)")
    return found


def header_value(text: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            return m
    return None


def token_estimate(text: str) -> float | None:
    m = header_value(text, _TOKENS_RE)
    if m is None:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").upper()
    return value * {"K": 1_000, "M": 1_000_000}.get(unit, 1)


def mode_of(text: str) -> tuple[str | None, int]:
    for number, line in unfenced_numbered(text):
        m = _MODE_RE.match(line)
        if m:
            return m.group(1), number
    span = section_span(text, "Execution Strategy")
    return None, (span[0] - 1 if span else 1)


def names_a_trigger(text: str) -> bool:
    rows = section_numbered(text, "Execution Strategy") or unfenced_numbered(text)
    for _, line in rows:
        reason = _REASON_RE.match(line)
        if reason and _TRIGGER_WORD_RE.search(reason.group(1)):
            return True
        if _CHECKED_RE.match(line) and _TRIGGER_WORD_RE.search(line):
            return True
    return False


def check_strategy(orch: Path, text: str, tasks: dict[int, Path]) -> list[str]:
    """The §1.1 findings for one Orchestration."""
    opus: list[int] = []
    heavy: list[tuple[int, float]] = []
    for number, path in sorted(tasks.items()):
        body = read_text(path)
        agent = header_value(body, _AGENT_RE)
        if agent and agent.group(1).casefold() == "opus":
            opus.append(number)
        tokens = token_estimate(body)
        if tokens is not None and tokens > _TOKEN_LIMIT:
            heavy.append((number, tokens))
    mode, line = mode_of(text)
    fired = []
    if len(opus) >= _OPUS_LIMIT:
        fired.append(f"{len(opus)} Opus tasks ({', '.join(map(str, opus))})")
    if heavy:
        fired.append("tasks over 50K (" + ", ".join(f"{n}: {t / 1000:g}K" for n, t in heavy) + ")")
    findings = []
    if fired and mode != "DELEGATED":
        findings.append(
            f"{orch}:{line}: [§1.1 strategy] {' and '.join(fired)} require DELEGATED, "
            f"but the mode is {mode or 'not declared'}"
        )
    if mode == "DELEGATED" and not names_a_trigger(text):
        findings.append(
            f"{orch}:{line}: [§1.1 strategy] DELEGATED names no trigger "
            "(add a Reason or Trigger line naming one of the four triggers)"
        )
    return findings


def plan_file_cell(cell: str, task_names: set[str]) -> tuple[bool, str]:
    """Whether a Required Context File cell names only plan files, and the first offender."""
    paths = [t for t in _CODE_SPAN_RE.findall(cell) if looks_like_path(t)]
    paths += _LINK_RE.findall(cell)
    if not paths:
        return bool(_PLAN_PROSE_RE.search(cell)), cell
    for raw in paths:
        name = normalise_path(raw).rsplit("/", 1)[-1]
        if name not in task_names and not _PLAN_FILE_RE.search(name):
            return False, raw
    return True, ""


def check_boundary(orch: Path, text: str, tasks: dict[int, Path]) -> list[str]:
    """The §1.3 findings for one DELEGATED Orchestration."""
    rows = section_numbered(text, "Required Context")
    if rows is None:
        return []
    names = {p.name for p in tasks.values()}
    findings = []
    for line, header, cells in table_rows(rows):
        index = column(header, "file", 1)
        cell = cells[index] if index < len(cells) else " ".join(cells)
        ok, offender = plan_file_cell(cell, names)
        if not ok:
            findings.append(
                f"{orch}:{line}: [§1.3 context-boundary] DELEGATED Required Context "
                f"names a non-plan file: {offender}"
            )
    return findings


def lint(orch: Path) -> tuple[list[str], int]:
    text = read_text(orch)
    tasks = task_files(orch, text)
    findings = check_strategy(orch, text, tasks)
    if mode_of(text)[0] == "DELEGATED":
        findings += check_boundary(orch, text, tasks)
    return findings, len(tasks)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Lint an Orchestration's Execution Strategy (§1.1, §1.3).")
    p.add_argument("orchestrations", nargs="+", type=Path, help="session Orchestration files")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings: list[str] = []
    task_count = 0
    try:
        for orch in args.orchestrations:
            found, count = lint(orch)
            findings += found
            task_count += count
    except InputError as exc:
        print(f"error: {exc}")
        return 2
    print(f"orchestrations: {len(args.orchestrations)}, task files read: {task_count}")
    for finding in findings:
        print(finding)
    if findings:
        print(f"findings: {len(findings)}")
        return 1
    print("clean: every strategy declaration and context boundary holds")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
