#!/usr/bin/env python3
"""List the same folder in every other linked git worktree of a repository.

A linked worktree has its own copy of the backlog and lessons folders, so an id
allocated in one worktree can repeat an id that another worktree already holds.
`sibling_dirs` maps a folder into each other worktree, so a caller can read the
ids those worktrees hold too.

The helper runs two local git reads, `rev-parse --show-toplevel` and
`worktree list --porcelain`. It never fetches and never reads a remote branch.
It returns an empty list when git is absent, the folder sits outside a
repository, a git call fails or times out, or the repository has one worktree.
"""

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

GIT_TIMEOUT_SECONDS = 10


def _git(folder: Path, *args: str) -> str | None:
    """Run one git command in `folder`. Return stdout with LF endings, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(folder), *args],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def _worktree_paths(listing: str) -> list[Path]:
    """Return the path of each non-bare record in `git worktree list --porcelain` output."""
    paths: list[Path] = []
    for record in listing.split("\n\n"):
        lines = record.strip().split("\n")
        if "bare" in lines:
            continue
        for line in lines:
            if line.startswith("worktree "):
                paths.append(Path(line[len("worktree "):]))
                break
    return paths


def sibling_dirs(folder: Path) -> list[Path]:
    """Map `folder` into every other linked worktree of its repository.

    Returns the mapped folders that exist as directories. Returns [] on any
    failure and for a repository with a single worktree. `folder` itself need
    not exist: git tracks no empty folder, so a fresh worktree can lack one
    that another worktree holds. git then runs in the nearest folder that exists.
    """
    folder = Path(folder)
    anchor = next((path for path in (folder, *folder.parents) if path.is_dir()), folder)
    top_out = _git(anchor, "rev-parse", "--show-toplevel")
    if top_out is None or not top_out.strip():
        return []
    try:
        toplevel = Path(top_out.strip()).resolve()
        relative = folder.resolve().relative_to(toplevel)
    except (OSError, ValueError):
        return []
    listing = _git(anchor, "worktree", "list", "--porcelain")
    if listing is None:
        return []
    found: list[Path] = []
    for root in _worktree_paths(listing):
        try:
            if root.resolve() == toplevel:
                continue
        except OSError:
            continue
        candidate = root / relative
        if candidate.is_dir():
            found.append(candidate)
    return found
