#!/usr/bin/env python3
"""Doctor's Lesson Resolution Keys stage — read-only, advisory, always-on.

`scan_lesson_keys(lessons_dir, kinds)` walks the `LL-*.md` files of the lessons
folder and its `Archive/` folder and grades each lesson whose `status:` is in
`HUB_STATUSES` (an open lesson). It returns how many it graded and, per gap
class, the ids of the lessons that show the gap. `run_lesson_keys_stage(cfg)`
resolves the lessons folder and the check kinds from the project's
`config.yaml`, calls the scan and prints the report.

The gap classes cover a missing or unknown `origin:`, a missing or unknown
`promotion-target:` token, a missing or malformed `enforced-by:`, a check kind
the project does not declare, a `none:` answer with no reason, a code origin
whose targets name no `code` target, and one `none:` reason shared by three or
more lessons. A lesson is read with the shared frontmatter parser, not strict
YAML, so a quoted and an unquoted `enforced-by:` value both read. A file that
cannot be read or parsed is skipped and counted in one line. Nothing here asks
a question or writes a file. The caller wraps the stage, so an exception never
changes doctor's exit status.
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import DEFAULT_LESSON_CHECK_KINDS
from doctor_audits import _load_project_config, _resolve_config_path
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from lessons_index_schema import (
    CODE_ORIGINS,
    HUB_STATUSES,
    LESSON_ORIGINS,
    NO_CHECK,
    PROMOTION_TARGETS,
    parse_enforced_by,
    split_targets,
)

# Each gap class: its key, then the label the report prints.
GAP_CLASSES = (
    ("origin-missing", "no origin: key"),
    ("origin-unknown", "origin: outside the known origins"),
    ("target-missing", "no promotion-target: key"),
    ("target-unknown", "promotion-target: token outside the known targets"),
    ("check-missing", "no enforced-by: answer"),
    ("check-invalid", "enforced-by: answer that does not read as kind: text"),
    ("kind-unknown", "enforced-by: kind that config does not declare"),
    ("none-no-reason", "enforced-by: none: with no reason"),
    ("origin-target-mismatch", "code origin with no code target"),
    ("none-reason-shared", "one none: reason shared by three or more lessons"),
)

_MAX_IDS = 10
_SHARED_REASON_MIN = 3
_ACTION = "  action: set the keys with /planwise lessons curate or /planwise lessons promote-batch"
_DECLARES_KINDS_RE = re.compile(r"^lesson_check_kinds[ \t]*:", re.MULTILINE)


class ScanResult(NamedTuple):
    """Lessons graded, the ids per gap class, and the count of unreadable files."""

    scanned: int
    classes: dict
    unreadable: int


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def _lesson_files(lessons_dir: Path) -> list:
    files = list(lessons_dir.glob("LL-*.md"))
    archive = lessons_dir / "Archive"
    if archive.is_dir():
        files += list(archive.rglob("LL-*.md"))
    return sorted(files)


def _lesson_id(path: Path, fm: dict) -> str:
    ident = _unquote(fm.get("id") or "")
    if ident:
        return ident
    return "-".join(path.stem.split("-")[:2])


def _read_map(path: Path):
    """The frontmatter map of a lesson file, or None when it cannot be read or parsed."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    block = split_frontmatter_block(text)
    if block is None:
        return None
    return parse_frontmatter_map(block[0])


def scan_lesson_keys(lessons_dir, kinds) -> ScanResult:
    """Grade the open lessons under `lessons_dir` against the resolution keys. Pure and read-only."""
    known_kinds = {str(k).strip().lower() for k in kinds}
    classes = {key: [] for key, _ in GAP_CLASSES}
    reasons: dict = {}
    scanned = 0
    unreadable = 0
    for path in _lesson_files(Path(lessons_dir)):
        fm = _read_map(path)
        if fm is None:
            unreadable += 1
            continue
        if _unquote(fm.get("status") or "").lower() not in HUB_STATUSES:
            continue
        scanned += 1
        ident = _lesson_id(path, fm)

        origin = _unquote(fm.get("origin") or "").lower()
        if not origin:
            classes["origin-missing"].append(ident)
        elif origin not in LESSON_ORIGINS:
            classes["origin-unknown"].append(ident)

        targets = split_targets(fm.get("promotion-target"))
        if not targets:
            classes["target-missing"].append(ident)
        else:
            if any(t not in PROMOTION_TARGETS for t in targets):
                classes["target-unknown"].append(ident)
            if origin in CODE_ORIGINS and "code" not in targets:
                classes["origin-target-mismatch"].append(ident)

        raw = fm.get("enforced-by")
        if raw is None or not raw.strip():
            classes["check-missing"].append(ident)
            continue
        parsed = parse_enforced_by(raw)
        if parsed is None:
            classes["check-invalid"].append(ident)
            continue
        kind, text = parsed
        if kind == NO_CHECK:
            if not text:
                classes["none-no-reason"].append(ident)
            else:
                reasons.setdefault(text.lower(), []).append(ident)
        elif kind not in known_kinds:
            classes["kind-unknown"].append(ident)

    for ids in reasons.values():
        if len(ids) >= _SHARED_REASON_MIN:
            classes["none-reason-shared"].extend(ids)
    return ScanResult(scanned, {k: sorted(v) for k, v in classes.items()}, unreadable)


def _id_list(ids: list) -> str:
    shown = ", ".join(ids[:_MAX_IDS])
    extra = len(ids) - _MAX_IDS
    return f"{shown}, +{extra} more" if extra > 0 else shown


def _declares_kinds(cfg) -> bool:
    path = _resolve_config_path(cfg)
    if path is None:
        return False
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _DECLARES_KINDS_RE.search(text) is not None


def run_lesson_keys_stage(cfg) -> None:
    """Print the open lessons that lack a valid origin or check answer. Read-only, advisory."""
    config, reason = _load_project_config(cfg)
    if config is None:
        raise RuntimeError(f"config.yaml could not be loaded ({reason})")
    lessons_dir = config.get("_lessons_dir")
    if lessons_dir is None:
        print("Lesson resolution keys: no lessons folder is configured, nothing scanned.")
        return
    kinds = config.get("lesson_check_kinds") or list(DEFAULT_LESSON_CHECK_KINDS)
    lessons_dir = Path(lessons_dir)
    if not lessons_dir.is_dir():
        print("Lesson resolution keys: no lessons folder is configured, nothing scanned.")
        return
    result = scan_lesson_keys(lessons_dir, kinds)
    gaps = [(label, result.classes[key]) for key, label in GAP_CLASSES if result.classes[key]]

    if not gaps and not result.unreadable:
        print(
            f"Lesson resolution keys: {result.scanned} open lessons scanned, "
            "each carries a valid origin and check answer."
        )
    else:
        print("Lesson resolution keys (advisory):")
        print(f"  open lessons scanned: {result.scanned}")
        for label, ids in gaps:
            print(f"  ~ {label}: {len(ids)} — {_id_list(ids)}")
        if result.unreadable:
            print(f"  ~ unreadable lesson files: {result.unreadable}")
        if gaps:
            print(_ACTION)
    if not _declares_kinds(cfg):
        print(
            "  ~ config.yaml declares no lesson_check_kinds, so the default kinds apply "
            f"({', '.join(DEFAULT_LESSON_CHECK_KINDS)}). action: run /planwise upgrade"
        )
