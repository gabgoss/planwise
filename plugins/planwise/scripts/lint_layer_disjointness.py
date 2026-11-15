#!/usr/bin/env python3
"""Lint a session Orchestration's dispatch layers for shared writes and in-layer edges.

Usage: ``lint_layer_disjointness.py <orchestration.md>...``

Four rules, each reported under its own name. Only a layer with two or more
members is checked: a single-member layer has no layer-mate.

``[§1.13 intersection]`` -- the rule of ``agent-orchestration-delegated.md``
§1.13 (Shared-Edit-Target Strategy Matrix). The predicate: per layer, the
pairwise intersection of the members' ``**Output:**`` path sets is empty, or
the layer's row in the Orchestration names Option A, B or C. Output paths come
from ``dispatch_preflight.output_paths``; this script parses no Output line of
its own. Two paths meet when equal or when one ends with the other on a
path-component boundary (``dispatch_preflight.intersect``).

The other three rules enforce the section "A Shared Precondition Belongs to
the Orchestrator" (§1.31), held in the part of the delegated discipline that
the part table of ``agent-orchestration-delegated.md`` lists for that number:

``[§1.31 consumes-mate-output]`` -- a member's Required Context names a path
that a layer-mate's ``**Output:**`` line declares (by a whole path token that
meets it on a path-component boundary with at least one folder, never by the
bare file name, or by the fixed prefix of a ``*`` pattern).

``[§1.31 recovery-read]`` -- a member's Required Context names a Recovery file,
or a line of its Execution Steps tells it to read or take a value from the
Recovery file.

``[§1.31 whole-tree-gate]`` -- a member's text holds a gate over the whole
working tree: a ``git`` line with a ``diff ... --name-only`` or a ``status
--porcelain`` and no ``--`` path scope. A ``git show --name-only`` lists one
commit, not the working tree, and does not fire.

Input: one or more Orchestration files. The layers come from the
``**Declared layers:**`` line (``L4 = {4, 5}``); the member files from the
Orchestration's Task Files table (``lint_plan_strategy.task_files``).

Exit 0 when every layer is clean, 1 when any rule fires (each finding printed
as ``file:line: [rule] message``), 2 on a usage error, an unreadable file, an
Orchestration with no ``**Declared layers:**`` line, a layer member with no
task file, or a member with no ``**Output:**`` line.

Cannot see: two spellings of one path that differ other than by a leading
prefix (``../y/x.md`` against ``z/x.md``) compare unequal, and two ``*`` patterns
are never intersected with each other. A shared allocation (a
next-free number) leaves no path to intersect. A layer that serializes under a
word other than Option A, B or C is reported. A Recovery read phrased without
"read", "take" or "from" passes, and a whole-tree gate written as prose
rather than as a command passes.
"""

from __future__ import annotations

import argparse
import re
import sys
from itertools import combinations
from pathlib import Path

sys.dont_write_bytecode = True

from dispatch_preflight import intersect, normalise_path, output_paths, paths_meet
from lint_plan_strategy import (
    InputError,
    read_text,
    section_numbered,
    task_files,
    unfenced_numbered,
)
from markdown_parser import split_row_cells

_DECLARED_RE = re.compile(r"^\s*\*\*Declared layers:\*\*")
_LAYER_RE = re.compile(r"\b(L[0-9]+)\s*=\s*\{([^}]*)\}")
_STRATEGY_RE = re.compile(r"\bOption [ABC]\b")
_RECOVERY_NAME_RE = re.compile(r"recovery", re.IGNORECASE)
_RECOVERY_READ_RE = re.compile(
    r"\b(?:read|reads|take|takes|from)\b[^.\r\n]*\bRecovery\b", re.IGNORECASE
)
_NEGATION_RE = re.compile(r"\b(?:not|never|no)\b", re.IGNORECASE)
_WHOLE_TREE_RE = re.compile(r"\bgit\b[^\r\n]*\b(?:diff\b[^\r\n]*--name-only|status\s+--porcelain\b)")
_PATHSPEC_RE = re.compile(r"\s--\s")
_MIN_PREFIX = 8
_TOKEN_RE = re.compile(r"[^\s`|,;()<>\[\]\"'*]+")


def declared_layers(orch: Path, text: str) -> tuple[int, dict[str, list[int]]]:
    """The declaration line number and each layer's member numbers."""
    for number, line in unfenced_numbered(text):
        if _DECLARED_RE.match(line):
            layers = {}
            for name, members in _LAYER_RE.findall(line):
                layers[name] = [int(m) for m in re.findall(r"[0-9]+", members)]
            return number, layers
    raise InputError(f"{orch}: no **Declared layers:** line")


def layer_row(text: str, layer: str) -> str:
    """The text of the first table row whose first cell is the layer name."""
    for _, line in unfenced_numbered(text):
        if line.lstrip().startswith("|"):
            cells = split_row_cells(line)
            if cells and cells[0] == layer:
                return line
    return ""


def names_path(text: str, path: str) -> bool:
    """Whether ``text`` names ``path`` by full path, file name or fixed prefix."""
    if "*" in path:
        prefix = path.rsplit("/", 1)[-1].split("*", 1)[0]
        return len(prefix) >= _MIN_PREFIX and prefix in text
    for raw in _TOKEN_RE.findall(text):
        token = normalise_path(raw).rstrip(".:")
        # a bare file name never matches a longer output path: the token needs a folder
        if token and ("/" in token or token == path) and paths_meet(token, path):
            return True
    return False


def check_intersection(orch, line, layer, members, outputs, row) -> list[str]:
    shared: set[str] = set()
    for a, b in combinations(members, 2):
        shared |= intersect(outputs[a], outputs[b])
    if not shared or _STRATEGY_RE.search(row):
        return []
    return [(
        f"{orch}:{line}: [§1.13 intersection] {layer} members share "
        f"{', '.join(sorted(shared))} and the layer names no Option A, B or C"
    )]


def check_member(number, path, body, mates, outputs) -> list[str]:
    """The three §1.31 findings for one member of a multi-member layer."""
    findings = []
    context = section_numbered(body, "Required Context") or []
    context_text = "\n".join(line for _, line in context)
    for mate in mates:
        hits = sorted(p for p in outputs[mate] if names_path(context_text, p))
        if hits:
            first = next(n for n, line in context if any(names_path(line, p) for p in hits))
            findings.append(
                f"{path}:{first}: [§1.31 consumes-mate-output] task {number} reads "
                f"layer-mate {mate}'s Output: {', '.join(hits)}"
            )
    recovery = [n for n, line in context if line.lstrip().startswith("|") and _RECOVERY_NAME_RE.search(line)]
    for n, line in section_numbered(body, "Execution Steps") or []:
        if _RECOVERY_READ_RE.search(line) and not _NEGATION_RE.search(line):
            recovery.append(n)
    if recovery:
        findings.append(
            f"{path}:{min(recovery)}: [§1.31 recovery-read] task {number} reads a value "
            "from the Recovery file inside a parallel layer"
        )
    for n, line in enumerate(body.splitlines(), start=1):
        if _WHOLE_TREE_RE.search(line) and not _PATHSPEC_RE.search(line):
            findings.append(
                f"{path}:{n}: [§1.31 whole-tree-gate] task {number} asserts a "
                "whole-tree property with no path scope"
            )
    return findings


def lint(orch: Path) -> tuple[list[str], int, int]:
    text = read_text(orch)
    line, layers = declared_layers(orch, text)
    tasks = task_files(orch, text)
    findings: list[str] = []
    multi = 0
    for layer, members in layers.items():
        if len(members) < 2:
            continue
        multi += 1
        bodies, outputs = {}, {}
        for member in members:
            if member not in tasks:
                raise InputError(f"{orch}: layer {layer} member {member} has no task file")
            bodies[member] = read_text(tasks[member])
            paths = output_paths(bodies[member])
            if paths is None:
                raise InputError(f"{tasks[member]}: no **Output:** line")
            outputs[member] = paths
        findings += check_intersection(orch, line, layer, members, outputs, layer_row(text, layer))
        for member in members:
            mates = [m for m in members if m != member]
            findings += check_member(member, tasks[member], bodies[member], mates, outputs)
    return findings, len(layers), multi


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Lint an Orchestration's dispatch layers (§1.13, §1.31).")
    p.add_argument("orchestrations", nargs="+", type=Path, help="session Orchestration files")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings: list[str] = []
    layer_count = multi_count = 0
    try:
        for orch in args.orchestrations:
            found, layers, multi = lint(orch)
            findings += found
            layer_count += layers
            multi_count += multi
    except InputError as exc:
        print(f"error: {exc}")
        return 2
    print(f"orchestrations: {len(args.orchestrations)}, layers: {layer_count}, multi-member: {multi_count}")
    for finding in findings:
        print(finding)
    if findings:
        print(f"findings: {len(findings)}")
        return 1
    print("clean: every multi-member layer is disjoint and has no in-layer edge")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
