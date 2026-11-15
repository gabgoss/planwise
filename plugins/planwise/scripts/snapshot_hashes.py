#!/usr/bin/env python3
"""Pin content hashes of a file set, and name each file that moved between pins.

Rule served: ``references/measure-artifact-identity.md`` section 2. When a read's
subject may be written concurrently, pin content hashes at both ends of the read
window (before dispatch, at runner start, at runner end, on return). All pins
agreeing proves the window was clean. Any disagreement names the file that moved.

Modes
-----
``take --label NAME --out FILE PATH [PATH ...]``
    Write one JSON snapshot: the label, a UTC timestamp, and per file its path,
    the SHA-256 of the raw bytes on disk, the byte count and a ``present`` flag.
    A directory argument expands to every file beneath it, sorted by path. A
    path that does not exist is recorded with ``present: false``.

``compare SNAPSHOT SNAPSHOT [SNAPSHOT ...]``
    Read two or more snapshots in the order given. Predicate: every file's
    state (present flag and hash) agrees across all snapshots.

Input
-----
Files on disk (``take``) or snapshot JSON files that ``take`` wrote (``compare``).

Exit contract
-------------
0  ``take`` wrote the snapshot; ``compare`` found every file in agreement.
1  ``compare`` found a disagreement. One line per file, naming the kind
   (``moved``, ``added`` or ``removed``), the path, and the first label at
   which the file's state differs from the snapshot before it.
2  Usage error, an unreadable input file, an unwritable output, or a
   malformed snapshot.

Raw bytes
---------
The hash is taken over the bytes on disk, never a decoded or normalized text.
A rewrite that only changes line endings (LF to CRLF) is a change, because a
reader sees different bytes. Version-control views that normalize line endings
cannot see that change, which is why this script reads the files itself.

What this check cannot see
--------------------------
- A change that is reverted between two snapshots. The bytes match at both pins,
  so the file reads as unchanged. Only a pin taken inside the window shows it.
- A file outside the set given to ``take``. Name every file the read depends on.
- Which writer moved a file. The report names the file and the window, not the
  cause.
- An earlier snapshot file left inside a named directory. ``take`` skips only
  its own ``--out`` path, so an older snapshot there is hashed like any other
  file and a later pin reports it as ``added``. Name the files explicitly, or
  keep snapshots outside the set.

A file that exists but cannot be read (locked by a writer, or deleted between
the listing and the open) makes ``take`` exit 2 naming the path and the error.
No partial snapshot is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_USAGE = 2

_CHUNK = 1 << 20


class SnapshotError(Exception):
    """A snapshot file that cannot be read or does not match the schema."""


class UnreadableFileError(Exception):
    """A file in the set exists but its bytes cannot be read."""


def _norm(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def expand_paths(paths: list[str], exclude: str | None = None) -> list[str]:
    """Expand directories to their files, sorted. Keep other paths as given.

    ``exclude`` names the current run's own output file, which is never hashed.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found = sorted(_norm(str(f)) for f in p.rglob("*") if f.is_file())
        else:
            found = [_norm(raw)]
        for item in found:
            if exclude is not None and _same_file(item, exclude):
                continue
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def hash_file(path: str) -> dict:
    """Return the snapshot entry for one path, hashing its raw bytes."""
    p = Path(path)
    if not p.is_file():
        return {"path": path, "present": False, "sha256": None, "bytes": None}
    digest = hashlib.sha256()
    size = 0
    try:
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise UnreadableFileError(f"{path}: cannot read ({exc.strerror or exc})") from exc
    return {"path": path, "present": True, "sha256": digest.hexdigest(), "bytes": size}


def take(label: str, paths: list[str], exclude: str | None = None) -> dict:
    files = [hash_file(p) for p in expand_paths(paths, exclude)]
    return {
        "label": label,
        "taken_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "files": files,
    }


def load_snapshot(path: str) -> dict:
    """Read and validate one snapshot. Raise SnapshotError on any defect."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise SnapshotError(f"{path}: cannot read ({exc.strerror})") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise SnapshotError(f"{path}: top level is not an object")
    label = data.get("label")
    if not isinstance(label, str) or not label:
        raise SnapshotError(f"{path}: missing or empty 'label'")
    files = data.get("files")
    if not isinstance(files, list):
        raise SnapshotError(f"{path}: 'files' is not a list")
    seen: set[str] = set()
    for i, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise SnapshotError(f"{path}: files[{i}] is not an object")
        fpath = entry.get("path")
        present = entry.get("present")
        sha = entry.get("sha256")
        if not isinstance(fpath, str) or not fpath:
            raise SnapshotError(f"{path}: files[{i}] has no 'path'")
        if not isinstance(present, bool):
            raise SnapshotError(f"{path}: files[{i}] 'present' is not a boolean")
        if present and not (isinstance(sha, str) and len(sha) == 64):
            raise SnapshotError(f"{path}: files[{i}] present but 'sha256' is not a hex digest")
        if fpath in seen:
            raise SnapshotError(f"{path}: duplicate entry for {fpath}")
        seen.add(fpath)
    return data


def compare(snapshots: list[dict]) -> list[str]:
    """Return one finding line per file whose state changes across snapshots."""
    states: list[dict[str, str | None]] = []
    order: list[str] = []
    known: set[str] = set()
    for snap in snapshots:
        state: dict[str, str | None] = {}
        for entry in snap["files"]:
            state[entry["path"]] = entry["sha256"] if entry["present"] else None
            if entry["path"] not in known:
                known.add(entry["path"])
                order.append(entry["path"])
        states.append(state)

    findings: list[str] = []
    for fpath in sorted(order):
        for i in range(1, len(snapshots)):
            before = states[i - 1].get(fpath)
            after = states[i].get(fpath)
            if before == after:
                continue
            if before is None:
                kind = "added"
            elif after is None:
                kind = "removed"
            else:
                kind = "moved"
            findings.append(
                f"{kind}: {fpath} changed at label '{snapshots[i]['label']}'"
                f" (after '{snapshots[i - 1]['label']}')"
            )
            break
    return findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pin content hashes of a file set and compare the pins "
        "(references/measure-artifact-identity.md section 2).",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_take = sub.add_parser("take", help="write one snapshot of the named files")
    p_take.add_argument("--label", required=True, help="name of this pin, e.g. runner-start")
    p_take.add_argument("--out", required=True, help="path of the JSON snapshot to write")
    p_take.add_argument("paths", nargs="+", help="files or directories to hash")

    p_cmp = sub.add_parser("compare", help="compare two or more snapshots in order")
    p_cmp.add_argument("snapshots", nargs="+", help="snapshot JSON files, oldest first")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code not in (0, None) else EXIT_OK

    if args.mode == "take":
        if not args.label.strip():
            print("error: --label must not be empty", file=sys.stderr)
            return EXIT_USAGE
        try:
            snap = take(args.label, args.paths, exclude=args.out)
        except UnreadableFileError as exc:
            print(f"error: unreadable file, no snapshot written: {exc}", file=sys.stderr)
            return EXIT_USAGE
        try:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(snap, fh, indent=2)
                fh.write("\n")
        except OSError as exc:
            print(f"error: cannot write {args.out} ({exc.strerror})", file=sys.stderr)
            return EXIT_USAGE
        present = sum(1 for f in snap["files"] if f["present"])
        print(f"took '{args.label}': {len(snap['files'])} files ({present} present) -> {args.out}")
        return EXIT_OK

    if len(args.snapshots) < 2:
        print("error: compare needs two or more snapshots", file=sys.stderr)
        return EXIT_USAGE
    try:
        snaps = [load_snapshot(p) for p in args.snapshots]
    except SnapshotError as exc:
        print(f"error: malformed snapshot: {exc}", file=sys.stderr)
        return EXIT_USAGE
    findings = compare(snaps)
    total = len({e["path"] for s in snaps for e in s["files"]})
    if findings:
        for line in findings:
            print(line)
        print(f"summary: {len(findings)} of {total} files changed across {len(snaps)} snapshots")
        return EXIT_FINDING
    print(f"ok: {total} files agree across {len(snaps)} snapshots")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
