"""Classify the files of one `upgrade-backups/{pair}/` directory.

Both the upgrade scan (`artifact_upgrade._scan_recovery_artifacts`) and the
doctor sweep (`doctor_sweeps.sweep_upgrade_leftovers`) call
`classify_backup_pair`, and the prune writer (`doctor_cli`) calls it with
`pair_is_clearable`, so the three surfaces cannot disagree about a file.

An index-migration pre-image is the only restore point for the item files,
lesson files and Master Plans the migration rewrote. It is therefore never
offered as safe-to-discard: it reports as review-then-discard on its own
line, and the prune writer never deletes it. Every other file in the pair is
a refresh pre-image and stays safe-to-discard. `DISPOSITIONS.md` is
bookkeeping, not a recovery artifact: it is never counted while a refresh or
index file exists. A pair holding nothing else is residue and reports as
safe-to-discard, so the writer removes it. No walk here follows a symlink or
a junction, and the writer refuses a pair whose root is one.
"""

import os
import stat
import sys
from pathlib import Path

INDEX_SUBDIRS = ("backlog", "lessons", "plans")

# Surface-path suffix and banner text for the index pre-image surface.
INDEX_SURFACE_SUFFIX = "/{backlog,lessons,plans}/"
INDEX_BANNER_TEXT = (
    "index-migration pre-images: the only restore point for the files the "
    "migration rewrote; review against the migration ledger first"
)
# Doctor report text for the same surface (meaning and action lines).
INDEX_MEANING = (
    "index-migration pre-images: the only restore point for the files the "
    "migration rewrote"
)
INDEX_ACTION = (
    "review against the migration ledger (DISPOSITIONS.md) first; "
    "never pruned automatically"
)
# Action line for every other review-then-discard or action-required surface.
DEFAULT_ACTION = (
    "resolve per handlers/upgrade-Part-3-BannerAndConflictResolution.md "
    "Step 4 — never auto-pruned"
)
# Appended to the safe-to-discard surface path so it does not read as a glob
# over the three index subdirectories.
REFRESH_SURFACE_NOTE = " excluding the backlog/, lessons/ and plans/ subfolders"

LOG_NAME = "DISPOSITIONS.md"


def is_link(p) -> bool:
    """True when `p` is a symlink, a junction or any other reparse point.

    The reparse attribute is read on every Python, because `Path.is_junction`
    exists only on 3.12+. An OSError from lstat other than "absent" propagates:
    an entry that cannot be examined is not safely traversable.
    """
    p = Path(p)
    if os.path.islink(p):
        return True
    junction = getattr(p, "is_junction", None)
    if junction and junction():
        return True
    try:
        st = os.lstat(p)
    except (FileNotFoundError, NotADirectoryError):
        return False
    return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _walk(root: Path) -> tuple:
    """Return (files, dirs, links, bad) under `root`, never entering a linked dir.

    A linked directory is listed in `links` only. A linked file is a file
    entry: unlinking it removes the link and never its target. An entry or
    directory that cannot be examined or listed goes in `bad` and is never
    treated as empty. The walk itself never raises.
    """
    files, dirs, links, bad, todo = [], [], [], [], [root]
    while todo:
        d = todo.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            bad.append(d)
            continue
        for e in entries:
            try:
                linked, is_dir = is_link(e), e.is_dir()
            except OSError:
                bad.append(e)
                continue
            if linked and is_dir:
                links.append(e)
            elif is_dir and not linked:
                dirs.append(e)
                todo.append(e)
            else:
                files.append(e)
    return files, dirs, links, bad


def classify_backup_pair(pair_dir: Path) -> dict:
    """Split a pair directory's files into `index`, `refresh` and `logs`.

    `index` holds every file under `{backlog,lessons,plans}/`, `logs` holds
    every `DISPOSITIONS.md` outside them, and `refresh` holds the rest. `links`
    holds each linked directory skipped. A pair root that is a link yields
    itself in `refresh` and `links`, so the writer sees it and refuses it.
    `unreadable` holds each entry that could not be examined or listed. It may
    hide an index pre-image, so the pair is never cleared and a line names it.
    """
    groups: dict = {"index": [], "refresh": [], "logs": [], "links": [], "unreadable": []}
    try:
        root_linked = is_link(pair_dir)
    except OSError:
        root_linked = False
        groups["unreadable"] = [pair_dir]
    if root_linked:
        groups["refresh"] = groups["links"] = [pair_dir]
        return groups
    files, _dirs, groups["links"], bad = _walk(pair_dir)
    groups["unreadable"] += bad
    for p in groups["unreadable"]:
        print(f"UNREADABLE {p}: not scanned, its pair is never cleared", file=sys.stderr)
    for f in files:
        rel = f.relative_to(pair_dir)
        if rel.parts[0] in INDEX_SUBDIRS and len(rel.parts) > 1:
            groups["index"].append(f)
        elif f.name == LOG_NAME:
            groups["logs"].append(f)
        else:
            groups["refresh"].append(f)
    if not (groups["index"] or groups["refresh"] or groups["links"] or groups["unreadable"]):
        groups["refresh"], groups["logs"] = groups["logs"], []
    return groups


def pair_is_clearable(pair_dir: Path) -> bool:
    """True when no index pre-image remains and no link or unreadable entry is skipped."""
    g = classify_backup_pair(pair_dir)
    return not (g["index"] or g["links"] or g["unreadable"])


def _rmdir_quietly(dirs: list) -> None:
    """rmdir each directory in order, skipping one that is absent or not empty."""
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            pass


def copy_files(targets: list, src: Path, dst: Path, copy) -> None:
    """Copy each target to the same relative path under `dst` with `copy`.

    Refuses a `src` that is a link: it prints a REFUSED line and raises.
    """
    if is_link(src):
        print(f"REFUSED {src}: a symlink or junction is never followed")
        raise OSError(f"{src} is a symlink or junction")
    for t in targets:
        out = dst / t.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        copy(t, out)


def unlink_files(targets: list, src: Path) -> None:
    """Unlink each target, then rmdir the directories under `src` this emptied.

    A directory that still holds an index pre-image or its log is not empty,
    so it stays. A linked directory is never entered.
    """
    for t in targets:
        t.unlink()
    _rmdir_quietly(sorted(_walk(src)[1], reverse=True))


def clear_empty_parents(planwise_root: Path) -> None:
    """Remove empty directories inside each pair, the empty pair directories,
    then an empty `upgrade-backups/` and `upgrade-conflicts/` under
    `planwise_root`. A linked pair or parent is left alone. This never raises:
    a pair it cannot examine is printed as NOT CLEARED and skipped."""
    for parent in ("upgrade-backups", "upgrade-conflicts"):
        top = planwise_root / parent
        try:
            if not top.is_dir() or is_link(top):
                continue
            pairs = sorted(top.glob("*-to-*"))
        except OSError as exc:
            print(f"NOT CLEARED {top}: {exc}")
            continue
        for pair in pairs:
            try:
                if pair.is_dir() and not is_link(pair):
                    _rmdir_quietly(sorted(_walk(pair)[1], reverse=True))
                    _rmdir_quietly([pair])
            except OSError as exc:
                print(f"NOT CLEARED {pair}: {exc}")
        _rmdir_quietly([top])
