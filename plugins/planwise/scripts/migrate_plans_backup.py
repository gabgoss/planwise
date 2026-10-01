#!/usr/bin/env python3
"""Byte-exact backups, DISPOSITIONS rows and restore for the plans-index migration.

`migrate_plans_index.py` (the standalone migrator) and `plans_migration.py`
(the `/planwise upgrade` and `/planwise init` routine) both back up before
they write, so the mechanics live here once. They mirror the lessons
routine's backup for the plans directory and a `plans` backup folder: the
lessons helpers resolve paths under the lessons directory, so they cannot be
imported for plans.

The first pre-image wins. A backup an earlier run left in the same version
pair is kept, and a target that has changed since gets a numbered sibling
(`{name}.{n}.bak`), so a later run's own restore point is not lost.
"""
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import upgrade_io


class BackupFailed(Exception):
    def __init__(self, src, exc):
        super().__init__(f"could not back up {src}: {exc}")


@dataclass
class Backups:
    pre: dict = field(default_factory=dict)  # path -> pre-image bytes (None when the file does not exist)
    backed_up: list = field(default_factory=list)
    kept: list = field(default_factory=list)  # backups an earlier run made; left as they were
    diverged: dict = field(default_factory=dict)  # backup dst (str) -> sibling pre-image (str)


def rel_path(path: Path, plans_dir: Path) -> Path:
    """`path` relative to the plans directory. A path outside it goes under `_outside/{digest}/`, so two
    same-named files never share one backup."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(plans_dir).resolve())
    except ValueError:
        digest = hashlib.sha256(str(resolved.parent).encode("utf-8")).hexdigest()[:12]
        return Path("_outside") / digest / resolved.name


def _sibling(dst: Path, current: bytes | None = None) -> Path | None:
    """The numbered sibling of `dst` holding `current`, or (current None) the next free numbered name."""
    n = 1
    while True:
        candidate = dst.with_name(f"{dst.name}.{n}.bak")
        if not candidate.exists():
            return candidate if current is None else None
        if current is not None and candidate.read_bytes() == current:
            return candidate
        n += 1


def backup_targets(targets: list, plans_dir: Path, backup_dir: Path) -> Backups:
    """Copy every existing target byte-exact, then return this run's pre-images. Raises `BackupFailed`
    before any caller writes."""
    result = Backups()
    for src in targets:
        dst = backup_dir / rel_path(src, plans_dir)
        if str(dst) in result.backed_up or str(dst) in result.kept:
            continue
        try:
            if dst.exists():
                result.kept.append(str(dst))
                current = Path(src).read_bytes() if Path(src).is_file() else None
                if current is not None and current != dst.read_bytes():
                    sibling = _sibling(dst, current)
                    if sibling is None:
                        sibling = _sibling(dst)
                        upgrade_io._copy_bytes_exact(Path(src), sibling)
                        result.backed_up.append(str(sibling))
                    result.diverged[str(dst)] = str(sibling)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                upgrade_io._copy_bytes_exact(Path(src), dst)
                result.backed_up.append(str(dst))
        except OSError as exc:
            raise BackupFailed(src, exc) from exc
    try:
        result.pre = {Path(p): Path(p).read_bytes() if Path(p).exists() else None for p in targets}
    except OSError as exc:
        raise BackupFailed("a pre-image", exc) from exc
    return result


def log_backups(cfg, from_version: str, to_version: str, backups: Backups, plans_dir: Path, backup_dir: Path) -> list:
    """One DISPOSITIONS row per backed-up file, written once the backups have landed and before any write.
    Returns the paths logged."""
    pair = backup_dir.parent.name
    logged = []
    for path, data in backups.pre.items():
        if data is None:
            continue
        rel = rel_path(path, plans_dir)
        dst = backup_dir / rel
        reason = f"pre-image at upgrade-backups/{pair}/plans/{rel.as_posix()}"
        if str(dst) in backups.kept:
            reason += " (made by an earlier run in this version pair; kept, not overwritten)"
        if backups.diverged.get(str(dst)):
            sibling = Path(backups.diverged[str(dst)]).relative_to(backup_dir).as_posix()
            reason += f"; current bytes differed, also backed up to upgrade-backups/{pair}/plans/{sibling}"
        upgrade_io._append_disposition_log(cfg, from_version, to_version, Path(path), "plans-backed-up", reason)
        logged.append(str(path))
    return logged


def restore(pre: dict, created: list) -> str:
    """Put every pre-existing file back to its pre-image and remove each file the write created. Returns ''
    or the error text of a restore that failed part-way."""
    try:
        for path, data in pre.items():
            if data is None:
                path.unlink(missing_ok=True)
            elif not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
        for path in created:
            path.unlink(missing_ok=True)
    except OSError as exc:
        return str(exc)
    return ""
