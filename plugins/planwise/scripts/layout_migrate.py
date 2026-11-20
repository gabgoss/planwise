"""Move the two working folders of an older install into the current layout.

Older installs keep `plan-build/` and `feedback-drafts/` at the top of the planwise
folder. The current layout keeps them one level down:

    {planwise_root}/plan-build/                         -> {planwise_root}/{plans_dir}/Plan-Build/
    {planwise_root}/feedback-drafts/ and the loose
    files in {planwise_root}/Feedback/                  -> {planwise_root}/Feedback/Feedback-Drafts/

Both `/planwise init` and `/planwise upgrade` call this module, so the two entry
points cannot drift. Every function here follows four rules:

  * It reads the folders on disk. It never reads the version pin, so it runs correctly
    from any starting version and on an install that is already current.
  * It never overwrites a file and never deletes one. A name clash, a locked file or a
    failed move leaves the file where it was and lists it in the report.
  * It is idempotent. A second run reports `already present` and changes nothing.
  * It never raises for a problem with one file or one config edit. It reports it.

`feedback-intake/` is not part of this move.
"""

from __future__ import annotations

import dataclasses
import os
import re
import shutil
from pathlib import Path

import config_loader

# The old and the new names. The old names are the only place they still appear.
LEGACY_PLAN_BUILD = "plan-build"
LEGACY_FEEDBACK_DRAFTS = "feedback-drafts"
FEEDBACK_PARENT = "Feedback"
FEEDBACK_DRAFTS_DIRNAME = "Feedback-Drafts"
NEW_FEEDBACK_DIR = f"{FEEDBACK_PARENT}/{FEEDBACK_DRAFTS_DIRNAME}"

# A `project.feedback_dir` value that names an old location. Any other value is the
# user's own choice, and this module leaves it alone.
_LEGACY_FEEDBACK_VALUES = frozenset({LEGACY_FEEDBACK_DRAFTS, FEEDBACK_PARENT.lower()})

_KEY_LINE = re.compile(r"^([ \t]+)feedback_dir:[ \t]*(\"[^\"]*\"|'[^']*'|[^#\s]*)", re.MULTILINE)


@dataclasses.dataclass
class LayoutReport:
    """What one migration did. `lines()` renders it for the upgrade or init output."""

    label: str
    state: str  # created, moved, merged, already present, kept
    path: Path
    moved: int = 0
    left: list[str] = dataclasses.field(default_factory=list)
    note: str = ""

    def lines(self) -> list[str]:
        out = [f"{self.label}: {self.state} ({self.path})"]
        if self.moved:
            out.append(f"  moved {self.moved} file(s)")
        if self.note:
            out.append(f"  {self.note}")
        out.extend(f"  left in place: {item}" for item in self.left)
        return out


def _count_files(folder: Path) -> int:
    """Number of files under `folder`, or 0 when it is not a folder."""
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.rglob("*") if p.is_file())


def _move_file(src: Path, dst: Path) -> str | None:
    """Move one file without overwriting. Return None on success, else the reason it stayed."""
    if dst.exists():
        return "a file with this name is already at the destination"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as exc:
        return f"move failed: {' '.join(str(exc).split())}"
    return None


def _prune_empty(folder: Path) -> None:
    """Remove `folder` and its empty subfolders. A folder that still holds a file stays."""
    if not folder.is_dir():
        return
    for sub in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            sub.rmdir()
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        pass


def _merge_tree(src: Path, dst: Path, report: LayoutReport) -> None:
    """Move every file under `src` into `dst`, keeping the relative layout. Never overwrite."""
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        reason = _move_file(path, dst / rel)
        if reason is None:
            report.moved += 1
        else:
            report.left.append(f"{src.name}/{rel.as_posix()} ({reason})")
    _prune_empty(src)


def migrate_plan_build(planwise_dir: Path, plans_dir: Path, create_missing: bool = True) -> LayoutReport:
    """Create `{plans_dir}/Plan-Build/`, or move the old `plan-build/` folder into it.

    `planwise_dir` and `plans_dir` are absolute folders. With `create_missing` false, a
    missing source leaves the destination alone, for a caller that creates it itself.
    """
    src = Path(planwise_dir) / LEGACY_PLAN_BUILD
    dst = Path(plans_dir) / config_loader.PLAN_BUILD_DIRNAME
    report = LayoutReport("Plan-Build directory", "already present", dst)

    if not src.is_dir():
        existed = dst.is_dir()
        if create_missing:
            dst.mkdir(parents=True, exist_ok=True)
            report.state = "already present" if existed else "created"
        return report

    if not dst.exists():
        count = _count_files(src)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
        except OSError:
            pass  # a lock on the folder: fall through to the file-by-file merge
        else:
            report.state, report.moved = "moved", count
            return report

    dst.mkdir(parents=True, exist_ok=True)
    _merge_tree(src, dst, report)
    report.state = "merged" if (report.moved or report.left) else "already present"
    return report


def _feedback_key_value(config_path: Path) -> str | None:
    """The `project.feedback_dir` text in the config file, or None when the key or file is absent."""
    try:
        text = Path(config_path).read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.split("\n")
    block = config_loader.find_top_level_block(lines, "project")
    if block is None:
        return None
    header_idx, block_end, _indent = block
    match = _KEY_LINE.search("\n".join(lines[header_idx + 1:block_end]))
    if match is None:
        return None
    return match.group(2).strip("\"'").strip() or None


def _rewrite_feedback_key(config_path: Path) -> tuple[bool, str]:
    """Point `project.feedback_dir` at the new folder. Return (changed, note) for the report."""
    path = Path(config_path)
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        return False, f"feedback_dir not rewritten ({' '.join(str(exc).split())})"
    block = config_loader.find_top_level_block(lines, "project")
    if block is None:
        return False, "feedback_dir not rewritten (the config has no project block)"
    header_idx, block_end, _indent = block
    for i in range(header_idx + 1, block_end):
        match = _KEY_LINE.match(lines[i])
        if match is not None:
            lines[i] = f'{match.group(1)}feedback_dir: "{NEW_FEEDBACK_DIR}"' + lines[i][match.end():]
            try:
                config_loader.write_config_checked(path, "\n".join(lines))
            except (config_loader.ConfigWriteError, OSError) as exc:
                return False, f"feedback_dir not rewritten ({' '.join(str(exc).split())})"
            return True, f"project.feedback_dir now {NEW_FEEDBACK_DIR}"
    return False, ""


def migrate_feedback_drafts(planwise_dir: Path, config_path: Path) -> LayoutReport | None:
    """Move old drafts into `Feedback/Feedback-Drafts/` and point `feedback_dir` there.

    Sources are `feedback-drafts/` and the loose files in `Feedback/`. Returns None when
    there is nothing to move, so a current install stays silent. A custom
    `project.feedback_dir` is kept, and the report says so.
    """
    root = Path(planwise_dir)
    dst = root / FEEDBACK_PARENT / FEEDBACK_DRAFTS_DIRNAME
    value = _feedback_key_value(Path(config_path))
    normalized = None if value is None else value.replace("\\", "/").strip("/")
    # Folder names compare without case, as the Windows and macOS file systems do.
    is_legacy = normalized is not None and normalized.lower() in _LEGACY_FEEDBACK_VALUES

    if normalized is not None and not is_legacy and normalized.lower() != NEW_FEEDBACK_DIR.lower():
        return LayoutReport("Feedback drafts", "kept", root / normalized,
                            note=f"custom project.feedback_dir kept ({normalized}); nothing moved")

    legacy = root / LEGACY_FEEDBACK_DRAFTS
    parent = root / FEEDBACK_PARENT
    loose = sorted(p for p in parent.iterdir() if p.is_file()) if parent.is_dir() else []
    has_legacy = legacy.is_dir() and _count_files(legacy) > 0
    if not has_legacy and not loose:
        if is_legacy and Path(config_path).is_file():
            _changed, note = _rewrite_feedback_key(Path(config_path))
            if note:
                return LayoutReport("Feedback drafts", "already present", dst, note=note)
        return None

    dst.mkdir(parents=True, exist_ok=True)
    report = LayoutReport("Feedback drafts", "moved", dst)
    if legacy.is_dir():
        _merge_tree(legacy, dst, report)
    for path in loose:
        reason = _move_file(path, dst / path.name)
        if reason is None:
            report.moved += 1
        else:
            report.left.append(f"{FEEDBACK_PARENT}/{path.name} ({reason})")
    if report.left:
        report.state = "merged"
    if is_legacy and Path(config_path).is_file():
        _changed, report.note = _rewrite_feedback_key(Path(config_path))
    return report
