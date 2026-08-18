#!/usr/bin/env python3
"""Guard against silently mutating a COMPLETE prior sprint's Outputs/ artifact.

A re-executed producer -- a notebook, a generator script, an --inplace
formatter, a doc emitter -- can overwrite a file a previously completed
sprint already wrote into its Outputs/ folder and still exit 0. Those files
are the artifact of record that later sprints adjudicate against and that
signoffs quote; per-task verification never catches the mutation because
every task checks only its own outputs.

This script is non-mutating: it only inspects `git status` / `git diff` and
prints findings. It never writes, stages, or reverts anything, and it never
clears an override -- an acknowledged override is a human/orchestrator
decision recorded elsewhere (the Recovery file), not a state this script
can see or touch.

Usage (placeholder forms only):
    python check_prior_sprint_outputs.py --config {planwise_root}/config.yaml \\
        --current-session {plans_dir}/{Plan}/{Exec-Abbrev}/Sprint-{XX}-{Name}/Session-{YY}-{Name}

Recommended invocation: closeout-only (run handler Step 4.0), not per-task --
the artifact is not permanent until the session-end commit, and per-task
invocation costs one `git status` per task in long DELEGATED sessions.

Exit code: 1 when a BLOCKING finding is printed, 0 otherwise -- including
when git is unavailable or a Master Plan carries no parseable tracking
table. Coverage is always reported, never inferred: an uncovered plan is
named on the coverage line rather than silently treated as clean.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config

BLOCKING = {"M", "D", "R", "T"}  # modify / delete / rename / typechange

_HEADING_RE = re.compile(r"^##\s+Session Completion Tracking", re.MULTILINE)
_ABBREV_RE = re.compile(r"^([A-Za-z0-9]+)-(?:META-)?Master-Plan\.md$")
_LINK_HREF_RE = re.compile(r"\]\(([^)]+)\)")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _parse_tracking_table(text: str) -> list[list[str]] | None:
    """Return the Session Completion Tracking table's data rows as cell
    lists, or None when the heading or a parseable table is absent."""
    heading = _HEADING_RE.search(text)
    if heading is None:
        return None
    lines = text[heading.end():].split("\n")
    idx = 0
    while idx < len(lines) and not lines[idx].strip().startswith("|"):
        idx += 1
    if idx >= len(lines):
        return None
    idx += 1  # skip header row
    if idx >= len(lines) or not lines[idx].strip().startswith("|"):
        return None  # no separator row -- malformed table
    idx += 1  # skip separator row
    rows = []
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        cells = [c.strip() for c in lines[idx].strip().strip("|").split("|")]
        rows.append(cells)
        idx += 1
    return rows


def _summary_cell_path(cell: str) -> str | None:
    """Best-effort extraction of a relative path from a Summary File cell
    (markdown link, backtick-code, or bare text -- all three appear on live
    tracking tables)."""
    m = _LINK_HREF_RE.search(cell)
    if m:
        return m.group(1)
    m = _BACKTICK_RE.search(cell)
    if m:
        return m.group(1)
    cell = cell.strip()
    return cell if cell and cell != "-" else None


def _outputs_dir_from_path(rel_path: str) -> str | None:
    """Return the `.../Outputs` prefix of a relative path, or None if the
    path carries no Outputs component."""
    parts = Path(rel_path.replace("\\", "/")).parts
    if "Outputs" not in parts:
        return None
    return str(Path(*parts[: parts.index("Outputs") + 1]))


def resolve_complete_outputs_dirs(plans_dir: Path) -> tuple[dict, int]:
    """Scan every Master Plan under plans_dir for COMPLETE sessions.

    Returns (complete_dirs, uncovered) where complete_dirs maps an
    absolute, resolved Outputs/ directory to an owner label
    ("{Abbrev} {Sprint cell} {Session cell}"), and uncovered counts Master
    Plan files with no parseable Session Completion Tracking table.
    """
    complete_dirs: dict[Path, str] = {}
    uncovered = 0
    for master_plan in sorted(plans_dir.glob("**/*-Master-Plan.md")):
        text = master_plan.read_text(encoding="utf-8", errors="replace")
        rows = _parse_tracking_table(text)
        if rows is None:
            uncovered += 1
            continue
        abbrev_match = _ABBREV_RE.match(master_plan.name)
        abbrev = abbrev_match.group(1) if abbrev_match else master_plan.stem
        plan_dir = master_plan.parent
        for cells in rows:
            if len(cells) < 3 or "complete" not in cells[2].lower():
                continue
            summary_cell = cells[3] if len(cells) > 3 else ""
            rel_path = _summary_cell_path(summary_cell)
            outputs_rel = _outputs_dir_from_path(rel_path) if rel_path else None
            if outputs_rel is None:
                continue  # row carries no resolvable Outputs/ path -- skip silently
            outputs_dir = (plan_dir / outputs_rel).resolve()
            complete_dirs[outputs_dir] = f"{abbrev} {cells[0]} {cells[1]}"
    return complete_dirs, uncovered


def _git_context(plans_dir: Path) -> tuple[Path | None, bytes, bool]:
    """Return (repo_root, status_porcelain_z_stdout, is_git_repo).

    `git status --porcelain` always reports paths relative to the
    REPOSITORY ROOT, never relative to the subprocess cwd -- so the root
    must be resolved and carried alongside the status output; every
    consumer needs it to turn a reported path back into a real filesystem
    location. Fails open: any subprocess error (git absent, plans_dir
    outside any repo, etc.) yields (None, b"", False) rather than raising.
    """
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(plans_dir),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None, b"", False
    if root_result.returncode != 0:
        return None, b"", False
    repo_root = Path(root_result.stdout.decode("utf-8", "replace").strip()).resolve()

    try:
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--", "."],
            cwd=str(plans_dir),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None, b"", False
    if status_result.returncode != 0:
        return None, b"", False
    return repo_root, status_result.stdout, True


def _parse_porcelain_z(data: bytes):
    """Yield (code, path, orig_path) from `git status --porcelain -z`
    output. orig_path is None except for rename/copy entries, where -z
    emits the new path and the old path as two consecutive NUL fields."""
    tokens = data.split(b"\0")
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        i += 1
        if not tok:
            continue
        code = tok[:2].decode("utf-8", "replace")
        path = tok[3:].decode("utf-8", "replace")
        orig_path = None
        if ("R" in code or "C" in code) and i < n:
            orig_path = tokens[i].decode("utf-8", "replace")
            i += 1
        yield code, path, orig_path


def _enclosing_outputs_dir(rel_path: str, base: Path) -> Path | None:
    """Return the absolute, resolved Outputs/ dir enclosing rel_path
    (relative to `base`), or None if no ancestor is named Outputs."""
    outputs_rel = _outputs_dir_from_path(rel_path)
    return (base / outputs_rel).resolve() if outputs_rel else None


def _diffstat(repo_root: Path, rel_path: str) -> str:
    """Best-effort +ins/-del summary for rel_path (repo-root-relative,
    as reported by `git status`), relative to HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--numstat", "--", rel_path],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return "unknown"
    line = result.stdout.decode("utf-8", "replace").strip().splitlines()
    if not line:
        return "+0 -0"
    parts = line[0].split("\t")
    if len(parts) < 2 or parts[0] == "-" or parts[1] == "-":
        return "binary"
    return f"+{parts[0]} -{parts[1]}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Block session closeout when a COMPLETE prior sprint's "
        "Outputs/ artifact was modified, deleted, renamed, or typechanged."
    )
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument(
        "--current-session",
        default=None,
        help="Session folder being closed out; its own Outputs/ is excluded",
    )
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    args = parser.parse_args()

    config = load_config(Path(__file__))
    plans_dir: Path = config["_plans_dir"]

    current_session_outputs = None
    if args.current_session:
        current_session_outputs = (Path(args.current_session) / "Outputs").resolve()

    complete_dirs, uncovered = resolve_complete_outputs_dirs(plans_dir)
    repo_root, raw, is_git_repo = _git_context(plans_dir)

    findings = []
    if is_git_repo:
        for code, path, orig_path in _parse_porcelain_z(raw):
            stripped = code.strip()
            if code == "??" or stripped == "A":
                continue  # untracked / added -- not the hazard this guard covers
            if not (set(stripped) & BLOCKING):
                continue
            candidates = [path] if orig_path is None else [path, orig_path]
            reported = set()
            for cand in candidates:
                outputs_dir = _enclosing_outputs_dir(cand, repo_root)
                if outputs_dir is None or outputs_dir in reported:
                    continue
                if outputs_dir == current_session_outputs:
                    continue
                owner = complete_dirs.get(outputs_dir)
                if owner is None:
                    continue
                reported.add(outputs_dir)
                findings.append(
                    {
                        "path": str((repo_root / cand).resolve()),
                        "owner": owner,
                        "code": stripped,
                        "diffstat": _diffstat(repo_root, cand),
                    }
                )

    coverage_line = (
        f"Coverage: {len(complete_dirs)} COMPLETE session Outputs/ dirs checked; "
        f"{uncovered} plan(s) had no parseable tracking table."
    )
    if not is_git_repo:
        coverage_line += " Not a git repository -- guard inactive."

    if args.json:
        print(
            json.dumps(
                {
                    "findings": findings,
                    "coverage": {
                        "complete_dirs_checked": len(complete_dirs),
                        "uncovered_plans": uncovered,
                        "git_repo": is_git_repo,
                    },
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            print(
                "BLOCKING: modified file under a COMPLETE sprint's Outputs/\n"
                f"  path:          {f['path']}\n"
                f"  owning sprint: {f['owner']}  (Status: COMPLETE)\n"
                f"  change:        {f['code']}   ({f['diffstat']})"
            )
        print(coverage_line)

    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
