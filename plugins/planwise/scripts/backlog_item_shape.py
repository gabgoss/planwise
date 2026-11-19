#!/usr/bin/env python3
"""Doctor's Backlog Item Shape stage: read-only, advisory, always-on.

`scan_item_shapes(backlog_dir)` walks the `BB-*.md` files directly under the backlog
folder (never `Archive/`). It grades each open item against the item template and
returns how many it graded and, per drift class, the ids of the items that show it.
`run_item_shape_stage(cfg)` resolves the backlog folder from the project's
`config.yaml`, calls the scan and prints the report.

The drift classes cover a status outside `VALID_STATUSES`, a legacy
`## Loop Decision Needed` section, a title over `TITLE_MAX_LEN`, an H2 heading outside the
template, a missing core section, a `**Priority:**` or `**Domain:**` line that is missing
or differs from the frontmatter, a footer that is missing or differs from `created:`, and a
frontmatter key outside the template. A heading inside a fenced code block is not a heading.
An item whose frontmatter cannot be read is skipped and counted in one line. A closed item
still sitting outside `Archive/` belongs to the archive check, so the scan skips it.

Nothing here asks a question or writes a file. The caller wraps the stage, so an exception
never changes doctor's exit status.
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import TITLE_MAX_LEN
from backlog_loop import DECISION_HEADING
from constants import CLOSED_STATUSES, VALID_STATUSES
from doctor_audits import _load_project_config
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from score_backlog import TEMPLATE_SECTION_HEADINGS

# The 12 keys of the Field Definitions table in `templates/backlog-item.md`.
TEMPLATE_FRONTMATTER_KEYS = frozenset(
    {
        "id",
        "title",
        "priority",
        "status",
        "abbrev",
        "created",
        "blocks",
        "route_hint",
        "route_evidence",
        "route_dated",
        "refined",
        "needs_plan",
    }
)

# The template names these three as optional sections beside the scored headings.
_EXTRA_OPTIONAL_HEADINGS = ("Dependencies", "Implementation Notes", "Constraints")
_ALLOWED_HEADINGS = frozenset(TEMPLATE_SECTION_HEADINGS) | frozenset(_EXTRA_OPTIONAL_HEADINGS)
_LEGACY_HEADING = DECISION_HEADING.removeprefix("## ").strip()
CORE_HEADINGS = ("Summary", "Problem", "Proposed Solution", "Acceptance Criteria")

# Each drift class: its key, then the label the report prints.
GAP_CLASSES = (
    ("status-invalid", "status outside the valid statuses"),
    ("legacy-decision", "legacy ## Loop Decision Needed section"),
    ("title-over-cap", f"title over {TITLE_MAX_LEN} characters"),
    ("section-nontemplate", "H2 heading outside the item template"),
    ("section-missing", "missing core section"),
    ("priority-line", "Priority: line missing or differing from the frontmatter"),
    ("domain-line", "Domain: line missing or differing from the frontmatter"),
    ("footer", "footer missing or differing from the created date"),
    ("key-nontemplate", "frontmatter key outside the template"),
)

_MAX_IDS = 10
_ACTION = "  action: repair the listed items with /planwise upgrade"
_H2_RE = re.compile(r"^##[ \t]+(\S.*?)[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_PRIORITY_RE = re.compile(r"^\*\*Priority:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_DOMAIN_RE = re.compile(r"^\*\*Domain:\*\*[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_FOOTER_RE = re.compile(r"^\*Created:[ \t]*(.*?)[ \t]*\*$")


class ScanResult(NamedTuple):
    """Items graded, the ids per drift class and the unreadable count."""

    scanned: int
    classes: dict
    unreadable: int


def _unquote(text: str) -> str:
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def _headings(body: str) -> list:
    """The H2 headings of `body`, skipping every line inside a fenced code block."""
    found = []
    fence = None
    for line in body.split("\n"):
        opened = _FENCE_RE.match(line)
        if fence is not None:
            if opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group(1)
            continue
        match = _H2_RE.match(line)
        if match:
            found.append(match.group(1))
    return found


def _item_id(path: Path, fm: dict) -> str:
    ident = _unquote(fm.get("id") or "")
    if ident:
        return ident
    return path.stem.split("-")[1] if path.stem.count("-") >= 1 else path.stem


def _last_line(body: str) -> str:
    lines = [line for line in body.split("\n") if line.strip()]
    return lines[-1].strip() if lines else ""


def _read(path: Path):
    """The (frontmatter map, body) of an item file, or None when it cannot be read or parsed."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    block = split_frontmatter_block(text)
    if block is None:
        return None
    fm = parse_frontmatter_map(block[0])
    return None if fm is None else (fm, block[1])


def _grade(fm: dict, body: str) -> dict:
    """The drift classes one item shows, as {class key: True}."""
    hits = {}
    status = _unquote(fm.get("status") or "")
    if status not in VALID_STATUSES:
        hits["status-invalid"] = True
    if len(_unquote(fm.get("title") or "")) > TITLE_MAX_LEN:
        hits["title-over-cap"] = True
    if any(key not in TEMPLATE_FRONTMATTER_KEYS for key in fm):
        hits["key-nontemplate"] = True

    headings = _headings(body)
    if _LEGACY_HEADING in headings:
        hits["legacy-decision"] = True
    if any(h not in _ALLOWED_HEADINGS for h in headings):
        hits["section-nontemplate"] = True
    if any(core not in headings for core in CORE_HEADINGS):
        hits["section-missing"] = True

    priority = _PRIORITY_RE.search(body)
    if priority is None or priority.group(1) != _unquote(fm.get("priority") or ""):
        hits["priority-line"] = True
    domain = _DOMAIN_RE.search(body)
    if domain is None or domain.group(1) != _unquote(fm.get("abbrev") or ""):
        hits["domain-line"] = True
    footer = _FOOTER_RE.match(_last_line(body))
    if footer is None or footer.group(1) != _unquote(fm.get("created") or ""):
        hits["footer"] = True
    return hits


def scan_item_shapes(backlog_dir) -> ScanResult:
    """Grade the open items directly under `backlog_dir` against the item template. Pure and read-only."""
    classes = {key: [] for key, _ in GAP_CLASSES}
    scanned = 0
    unreadable = 0
    for path in sorted(Path(backlog_dir).glob("BB-*.md")):
        parsed = _read(path)
        if parsed is None:
            unreadable += 1
            continue
        fm, body = parsed
        if _unquote(fm.get("status") or "") in CLOSED_STATUSES:
            continue
        scanned += 1
        ident = _item_id(path, fm)
        for key in _grade(fm, body):
            classes[key].append(ident)
    return ScanResult(scanned, {k: sorted(v) for k, v in classes.items()}, unreadable)


def _id_list(ids: list) -> str:
    shown = ", ".join(ids[:_MAX_IDS])
    extra = len(ids) - _MAX_IDS
    return f"{shown}, +{extra} more" if extra > 0 else shown


def run_item_shape_stage(cfg) -> None:
    """Print the open items whose shape drifts from the item template. Read-only, advisory."""
    config, reason = _load_project_config(cfg)
    if config is None:
        raise RuntimeError(f"config.yaml could not be loaded ({reason})")
    backlog_dir = config.get("_backlog_dir")
    if backlog_dir is None or not Path(backlog_dir).is_dir():
        print("Backlog item shape: no backlog folder is configured, nothing scanned.")
        return
    result = scan_item_shapes(backlog_dir)
    gaps = [(label, result.classes[key]) for key, label in GAP_CLASSES if result.classes[key]]

    if not gaps and not result.unreadable:
        print(f"Backlog item shape: {result.scanned} open items scanned, each follows the item template.")
        return
    print("Backlog item shape (advisory):")
    print(f"  open items scanned: {result.scanned}")
    for label, ids in gaps:
        print(f"  ~ {label}: {len(ids)} — {_id_list(ids)}")
    if result.unreadable:
        print(f"  ~ unreadable item files: {result.unreadable}")
    if gaps:
        print(_ACTION)
