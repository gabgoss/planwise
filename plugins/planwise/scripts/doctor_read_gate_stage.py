#!/usr/bin/env python3
"""Doctor's Consumer Read-Gate Scan stage — read-only, always-on.

`run_read_gate_stage(cfg)` walks the consumer project's `.claude/rules/`,
`.claude/agents/` and `.claude/skills/` trees and the files of each active
plan, and classifies every file with `read_limits.classify_file` at the
conservative ratio. It prints each Warn and Critical file with its level,
reason, path and token estimate. For each printed file it then says whether an
open backlog item names the file in its title. With no such item it prints one
filing line that names the command to run and the procedure to follow. Green
and Notice files print nothing.

The scan skips `.claude/rules/planwise/`, which holds machine-managed copies
that `/planwise upgrade` owns, and any `Outputs/` or `Reviews/` directory of a
plan. A backlog item counts only when it sits outside `Archive/`, its status is
not closed, and its frontmatter `title:` names the file as a whole token. When
two scanned files share a basename, the match and the filing line use the
project-relative path instead.

An active plan is each plan whose plans-index status is `IN_PROGRESS`, read
through `parse_plans`. When no active plan resolves, or the plans index cannot
be read, the stage says so and scans the three `.claude` trees only. Nothing
here asks a question or writes a file. The caller wraps the stage, so an
exception never changes doctor's exit status.
"""

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parse_plans
import read_limits
from constants import CLOSED_STATUSES
from doctor_audits import _load_project_config
from doctor_probes import _display

_CLAUDE_TREES = (("rules", "*.md"), ("agents", "*.md"), ("skills", "*"))
_MANAGED_RULES = ("rules", "planwise")
_SKIPPED_PLAN_DIRS = frozenset({"Outputs", "Reviews"})
_PRINTED_LEVELS = ("Warn", "Critical")
_PROCEDURE = 'references/session-context-budget.md, "Page-Cap Procedure"'
_FRONTMATTER_RE = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _claude_files(project_root: Path) -> list[Path]:
    """Every file under the three `.claude` trees the stage scans, managed copies excluded."""
    claude = project_root / ".claude"
    managed = claude.joinpath(*_MANAGED_RULES)
    files = []
    for tree, pattern in _CLAUDE_TREES:
        base = claude / tree
        if base.is_dir():
            files.extend(
                p for p in sorted(base.rglob(pattern)) if p.is_file() and managed not in p.parents
            )
    return files


def _plan_files(plan_dir: Path) -> list[Path]:
    """Every `.md` file of one plan, outside any `Outputs/` or `Reviews/` directory."""
    return [
        p
        for p in sorted(plan_dir.rglob("*.md"))
        if p.is_file() and not _SKIPPED_PLAN_DIRS.intersection(p.relative_to(plan_dir).parts[:-1])
    ]


def _active_plan_dirs(config: dict | None) -> tuple[list[tuple[str, Path]], str]:
    """`([(abbrev, plan directory)], reason)`. The reason is empty when a plan resolved."""
    if config is None:
        return [], "config.yaml could not be loaded"
    index_path = Path(config["_plans_index"])
    if not index_path.is_file():
        return [], f"no plans index at {index_path.name}"
    table = parse_plans.parse_index_table(index_path.read_text(encoding="utf-8"))
    plans_dir = Path(config["_plans_dir"])
    found = []
    for row in table.rows:
        if row.status_token != "IN_PROGRESS":
            continue
        plan_dir = plans_dir / row.path
        if plan_dir.is_dir():
            found.append((row.abbrev, plan_dir))
    if not found:
        return [], "no IN_PROGRESS plan in the plans index resolves to a directory"
    return found, ""


def _frontmatter_value(block: str, key: str) -> str:
    m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*$", block, re.MULTILINE)
    return m.group(1).strip("\"'") if m else ""


def _open_item_titles(config: dict | None) -> dict[str, str] | None:
    """Name -> title of each open, non-archived `BB-*.md` item, or None when the backlog is unknown."""
    if config is None or not config.get("_backlog_dir"):
        return None
    backlog_dir = Path(config["_backlog_dir"])
    if not backlog_dir.is_dir():
        return None
    titles = {}
    # A top-level pattern only, so items under Archive/ never count.
    for p in sorted(backlog_dir.glob("BB-*.md")):
        m = _FRONTMATTER_RE.match(p.read_text(encoding="utf-8", errors="replace"))
        if not m:
            continue
        if _frontmatter_value(m.group(1), "status").upper() in CLOSED_STATUSES:
            continue
        title = _frontmatter_value(m.group(1), "title")
        if title:
            titles[p.name] = title
    return titles


def _names(title: str, name: str) -> bool:
    """Whether `title` holds `name` as a whole token, so `padded.md` never matches `my-padded.md`."""
    return re.search(rf"(?<![\w.\-]){re.escape(name)}(?![\w\-]|\.\w)", title) is not None


def run_read_gate_stage(cfg) -> None:
    """Print the Warn and Critical files of the consumer scan set. Read-only."""
    project_root = Path(cfg.project_root).resolve()
    config, reason = _load_project_config(cfg)
    try:
        plans, plan_reason = _active_plan_dirs(config)
        unresolved = False
    except Exception as exc:  # noqa: BLE001 -- a bad plans index must not stop the .claude scan
        plans, plan_reason = [], f"{exc.__class__.__name__}: {exc}"
        unresolved = True

    seen: dict[Path, None] = {}
    for path in _claude_files(project_root):
        seen.setdefault(path.resolve(), None)
    for _abbrev, plan_dir in plans:
        for path in _plan_files(plan_dir):
            seen.setdefault(path.resolve(), None)

    if plans:
        print(f"Active plan(s): {', '.join(abbrev for abbrev, _ in plans)}")
    elif unresolved:
        print(f"Active plan: could not be resolved ({plan_reason}); scanned the three .claude trees only")
    else:
        print(f"Active plan: none ({plan_reason}); scanned the three .claude trees only")

    flagged = []
    for path in seen:
        result = read_limits.classify_file(str(path), None)
        if result["level"] in _PRINTED_LEVELS:
            flagged.append((_display(path, project_root), path, result))
    flagged.sort(key=lambda item: item[0])

    if not flagged:
        print(f"No file at Warn or Critical ({len(seen)} file(s) scanned).")
        return

    shared = {name for name, count in Counter(p.name for p in seen).items() if count > 1}
    items = _open_item_titles(config)
    print(f"{len(flagged)} file(s) at Warn or Critical ({len(seen)} file(s) scanned):")
    for shown, path, result in flagged:
        print(f"  {result['level']}  reason={result['reason']}  {shown}  (~{result['tokens']} tokens)")
        if items is None:
            print(f"      backlog: not checked ({reason or 'no backlog directory'})")
            continue
        name = shown if path.name in shared else path.name
        naming = [item for item, title in items.items() if _names(title, name)]
        if naming:
            print(f"      backlog: named by {', '.join(naming)}")
        else:
            print(
                f"      File an item with /planwise backlog: Refactor `{name}` below the read warn "
                f"(procedure: {_PROCEDURE})"
            )
