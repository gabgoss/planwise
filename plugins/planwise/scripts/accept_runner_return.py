#!/usr/bin/env python3
"""Acceptance gate for a returned runner: check the deliverables on disk.

Rule enforced: references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md
§1.17.4 "Acceptance gate: a `completed` status is not a deliverable check",
with the over-run signs of §1.23 (Part-3 of the same reference). A harness
`completed` status and a clean final message are not evidence. Acceptance
rests on these checks:

    1. Every path in the task file's **Output:** line exists and is non-empty.
       A declared folder must hold at least one file and covers every dirty
       path under it in check 3.
    2. The task's row in the Recovery step table reads COMPLETE.
    3. The dirty set (`git status --porcelain`) equals the declared set, plus
       the Recovery file and any --peer-dirty paths.
    4. Over-run signs: a later step row already reads COMPLETE, or the task's
       Outputs/ folder holds a later task's output or an undeclared output of
       this task.

Usage:
    accept_runner_return.py --task FILE --recovery FILE --repo-root DIR
        [--nested DIR ...] [--peer-dirty FILE] [--base DIR ...] [--closed-session]

    --nested        a nested git repository under the repo root (repeatable).
                    Its dirty paths are read with its own `git status` and
                    prefixed with its path, because the outer repository may
                    ignore it.
    --peer-dirty    a file listing paths another session owns, one per line,
                    relative to the repo root. They are subtracted from the
                    dirty set.
    --base          an extra folder that a declared Output path may be
                    relative to (repeatable). The task file's folder and the
                    repo root are always tried first.
    --closed-session  skip checks 3 and 4, for a session already committed,
                    where later rows and later outputs are expected.

The **Output:** line is parsed with dispatch_preflight.output_paths, so this
script and the dispatch-time overlap check read one path set.

Exit: 0 when every check passes; 1 listing each miss; 2 on a usage error, an
unreadable file, a task file with no **Output:** line or no Task ID, a
Recovery file with no step table, or a failed git call.

What the sibling scripts check instead:
    outputs_coverage.py compares an Outputs/ listing with the Required Context
        rows of the consuming task files. It does not read the producer's
        **Output:** line, the Recovery row or git.
    batch_gate.py compares section labels and item counts across the outputs of
        one parallel batch. It does not check one task's deliverables.

What it cannot see: whether an output's content is right. A non-empty file
with the wrong body passes check 1. A declared path written as prose or as a
shorthand that resolves under no tried folder is reported missing, not
guessed. A peer's edit to a declared path is invisible to check 3.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
import subprocess
from pathlib import Path

from dispatch_preflight import output_paths
from markdown_parser import split_row_cells

_TASK_ID_RE = re.compile(r"^\s*\*\*Task ID:\*\*\s*`?([A-Za-z0-9-]+)-(\d+)`?\s*$")
_SEPARATOR_RE = re.compile(r"^:?-{3,}:?\Z")


class UsageError(Exception):
    """An input the checks cannot run on."""


def task_id(text: str) -> tuple[str, int]:
    """(prefix, ordinal) from the task file's ``**Task ID:**`` line."""
    for line in text.splitlines():
        m = _TASK_ID_RE.match(line)
        if m:
            return m.group(1), int(m.group(2))
    raise UsageError("task file has no **Task ID:** line")


def step_rows(text: str) -> list[tuple[int, str]]:
    """(step, status) for each body row of the first table with Step and Status columns."""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.lstrip().startswith("|"):
            continue
        header = [c.strip().lower() for c in split_row_cells(line)]
        separator = split_row_cells(lines[i + 1])
        if "step" not in header or "status" not in header:
            continue
        if not separator or not all(_SEPARATOR_RE.match(c.strip()) for c in separator if c.strip()):
            continue
        step_col, status_col = header.index("step"), header.index("status")
        rows: list[tuple[int, str]] = []
        for row in lines[i + 2:]:
            if not row.lstrip().startswith("|"):
                break
            cells = split_row_cells(row)
            if len(cells) > max(step_col, status_col) and cells[step_col].strip().isdigit():
                rows.append((int(cells[step_col].strip()), cells[status_col].strip()))
        return rows
    raise UsageError("Recovery file has no table with Step and Status columns")


def resolve(declared: str, bases: list[Path]) -> Path | None:
    """The first existing ``base / declared``, or ``None``."""
    for base in bases:
        candidate = base / declared
        if candidate.exists():
            return candidate.resolve()
    return None


def _is_empty(found: Path) -> bool:
    """A zero-byte file, or a folder holding no file."""
    if found.is_dir():
        return not any(f.is_file() for f in found.rglob("*"))
    return found.is_file() and found.stat().st_size == 0


def rel(path: Path, root: Path) -> str:
    """``path`` relative to ``root`` in forward-slash form, or absolute when outside it."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def porcelain_paths(repo: Path) -> set[str]:
    """Dirty paths of one repository, relative to that repository."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise UsageError(f"git status failed in {repo}: {proc.stderr.strip()}")
    paths: set[str] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ")[-1]
        paths.add(entry.strip().strip('"'))
    return paths


def dirty_set(root: Path, nested: list[str]) -> set[str]:
    """Dirty paths of the root repository and every nested one, relative to the root."""
    prefixes = [n.replace("\\", "/").rstrip("/") + "/" for n in nested]
    out = {p for p in porcelain_paths(root) if not any(p.startswith(x) or p + "/" == x for x in prefixes)}
    for prefix in prefixes:
        out |= {prefix + p for p in porcelain_paths(root / prefix)}
    return out


def check(args: argparse.Namespace) -> list[str]:
    """Run the checks and return one message per miss."""
    task = Path(args.task)
    recovery = Path(args.recovery)
    root = Path(args.repo_root)
    try:
        task_text = task.read_text(encoding="utf-8")
        recovery_text = recovery.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read input: {exc}") from exc
    if not root.is_dir():
        raise UsageError(f"repo root is not a folder: {root}")
    declared = output_paths(task_text)
    if declared is None:
        raise UsageError(f"{task}: no **Output:** line")
    prefix, ordinal = task_id(task_text)
    misses: list[str] = []

    bases = [task.parent, root, *(Path(b) for b in args.base)]
    resolved: dict[str, Path] = {}
    for item in sorted(declared):
        found = resolve(item, bases)
        if found is None:
            misses.append(f"{task}: declared Output missing: {item}")
        elif _is_empty(found):
            misses.append(f"{task}: declared Output is empty: {item}")
        else:
            resolved[item] = found

    rows = step_rows(recovery_text)
    own = [status for step, status in rows if step == ordinal]
    if not own:
        misses.append(f"{recovery}: no step row {ordinal}")
    elif own[0].upper() != "COMPLETE":
        misses.append(f"{recovery}: step {ordinal} reads {own[0]}, not COMPLETE")

    if args.closed_session:
        return misses

    later = [step for step, status in rows if step > ordinal and status.upper() == "COMPLETE"]
    for step in later:
        misses.append(f"{recovery}: over-run: later step {step} already reads COMPLETE")

    outputs_dir = task.parent / "Outputs"
    declared_names = {p.name for p in resolved.values()}
    if outputs_dir.is_dir():
        name_re = re.compile(re.escape(prefix) + r"-(\d+)-")
        for entry in sorted(outputs_dir.iterdir()):
            m = name_re.match(entry.name)
            if not m:
                continue
            number = int(m.group(1))
            if number > ordinal:
                misses.append(f"{entry}: over-run: a later task's output exists")
            elif number == ordinal and entry.name not in declared_names:
                misses.append(f"{entry}: over-run: output not declared on the **Output:** line")

    peer: set[str] = set()
    if args.peer_dirty:
        try:
            peer_text = Path(args.peer_dirty).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UsageError(f"cannot read --peer-dirty list: {exc}") from exc
        peer = {ln.strip().replace("\\", "/") for ln in peer_text.splitlines() if ln.strip()}
    dirty = dirty_set(root, list(args.nested))
    expected = {rel(p, root) for p in resolved.values() if p.is_file()} | {rel(recovery, root)}
    folders = {rel(p, root) for p in resolved.values() if p.is_dir()}
    for path in sorted(dirty - expected - peer):
        if not any(path.startswith(f + "/") for f in folders):
            misses.append(f"dirty but not declared: {path}")
    for path in sorted(expected - dirty - {rel(recovery, root)}):
        misses.append(f"declared but not dirty: {path}")
    for folder in sorted(folders):
        if not any(path.startswith(folder + "/") for path in dirty):
            misses.append(f"declared but not dirty: {folder}/")
    return misses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Accept a runner return on disk evidence (§1.17.4, §1.23 over-run signs)."
    )
    parser.add_argument("--task", required=True, help="the task file")
    parser.add_argument("--recovery", required=True, help="the session Recovery file")
    parser.add_argument("--repo-root", required=True, help="root of the repository the task edits")
    parser.add_argument("--nested", action="append", default=[], help="nested repository under the root")
    parser.add_argument("--peer-dirty", help="file listing paths another session owns")
    parser.add_argument("--base", action="append", default=[], help="extra folder for Output paths")
    parser.add_argument("--closed-session", action="store_true", help="skip the dirty-set and over-run checks")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        misses = check(args)
    except UsageError as exc:
        print(f"accept_runner_return: {exc}", file=sys.stderr)
        return 2
    print(f"{len(misses)} miss(es)")
    for item in misses:
        print(item)
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
