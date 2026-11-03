#!/usr/bin/env python3
"""Pin a git tree's state at both ends of a read window, and compare the pins.

A verification task records which tree it read. It takes the stamps as its
first action and again as its last. When the two stamp sets differ, the tree
moved during the read, so the read is redone rather than adjudicated
(`references/verify-backlog-citation-freshness.md` section 12.2 and 12.3).

Usage:
    tree_pin.py stamp --repo <path> [--subtree <path>]... --out <file>
    tree_pin.py compare <file> --repo <path>

`stamp` records the HEAD sha, the current branch, and the
`git status --porcelain -- <subtree>` output of each subtree (the whole tree
when no `--subtree` is given). It writes the stamps as JSON to `--out`.
It refuses an `--out` path inside the stamped repository, so the stamp file
can never change the status it records.

`compare` re-takes the same stamps and prints each differing field.

Exit codes: 0 stamps written, or stamps equal; 1 the stamps differ;
2 usage error, git error, or an `--out` path inside the repository.
Stdout is LF-only text.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

WHOLE_TREE = "."
DETACHED = "(detached)"


class PinError(Exception):
    """A stamp could not be taken or read."""


def _emit(lines: list[str]) -> None:
    """Write lines to stdout with LF endings on every platform."""
    if not lines:
        return
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    sys.stdout.flush()


def _git(repo: Path, *args: str) -> str:
    """Run one git command in `repo` and return its stdout with LF endings."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise PinError(f"git could not start: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise PinError(f"git {' '.join(args)} failed: {err}")
    return proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def repo_toplevel(repo: Path) -> Path:
    """Return the resolved top-level directory of the repository at `repo`."""
    return Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()


def take_stamps(repo: Path, subtrees: list[str]) -> dict:
    """Take the HEAD, branch and per-subtree status stamps of `repo`."""
    subtrees = list(subtrees) or [WHOLE_TREE]
    head = _git(repo, "rev-parse", "HEAD").strip()
    branch = _git(repo, "branch", "--show-current").strip() or DETACHED
    status = {}
    for sub in subtrees:
        status[sub] = _git(repo, "status", "--porcelain", "--", sub)
    return {"head": head, "branch": branch, "subtrees": subtrees, "status": status}


def is_inside(path: Path, root: Path) -> bool:
    """True when `path` resolves to `root` or to a location below it."""
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def diff_stamps(before: dict, after: dict) -> list[str]:
    """Return one line per differing field; an empty list means the stamps are equal."""
    out: list[str] = []
    for key in ("head", "branch"):
        if before.get(key) != after.get(key):
            out.append(f"differs: {key}: {before.get(key)} -> {after.get(key)}")
    for sub in before.get("subtrees", []):
        old = set(before.get("status", {}).get(sub, "").splitlines())
        new = set(after.get("status", {}).get(sub, "").splitlines())
        for line in sorted(new - old):
            out.append(f"differs: status {sub}: + {line}")
        for line in sorted(old - new):
            out.append(f"differs: status {sub}: - {line}")
    return out


def cmd_stamp(args: argparse.Namespace) -> int:
    """Write the stamps of `--repo` to `--out`."""
    repo = Path(args.repo)
    out = Path(args.out)
    top = repo_toplevel(repo)
    if is_inside(out, top):
        _emit([f"error: --out {out.as_posix()} is inside the stamped repository {top.as_posix()}"])
        return 2
    stamps = take_stamps(repo, args.subtree or [])
    stamps["repo"] = top.as_posix()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(stamps, handle, indent=2, sort_keys=True)
        handle.write("\n")
    dirty = sum(len(v.splitlines()) for v in stamps["status"].values())
    _emit([
        f"stamped: head {stamps['head']}",
        f"stamped: branch {stamps['branch']}",
        f"stamped: subtrees {', '.join(stamps['subtrees'])} ({dirty} status lines)",
        f"stamp file: {out.as_posix()}",
    ])
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Re-take the stamps recorded in the stamp file and print every difference."""
    path = Path(args.stamp_file)
    try:
        before = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PinError(f"cannot read stamp file {path.as_posix()}: {exc}") from exc
    if not isinstance(before, dict) or "subtrees" not in before:
        raise PinError(f"stamp file {path.as_posix()} holds no stamps")
    after = take_stamps(Path(args.repo), before["subtrees"])
    lines = diff_stamps(before, after)
    if lines:
        _emit(lines + [f"stamps differ: {len(lines)} field(s); redo the read"])
        return 1
    _emit([f"stamps equal: head {after['head']}, branch {after['branch']}"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the two-mode argument parser."""
    parser = argparse.ArgumentParser(description="Pin and compare a git tree's state.")
    modes = parser.add_subparsers(dest="mode", required=True)
    stamp = modes.add_parser("stamp", help="write the stamps to a file outside the repository")
    stamp.add_argument("--repo", required=True, help="the repository to stamp")
    stamp.add_argument("--subtree", action="append", help="a subtree path; repeatable")
    stamp.add_argument("--out", required=True, help="the stamp file, outside the repository")
    stamp.set_defaults(func=cmd_stamp)
    compare = modes.add_parser("compare", help="re-take the stamps and compare")
    compare.add_argument("stamp_file", help="a file written by `stamp`")
    compare.add_argument("--repo", required=True, help="the repository to re-stamp")
    compare.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run one mode."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PinError as exc:
        _emit([f"error: {exc}"])
        return 2


if __name__ == "__main__":
    sys.exit(main())
