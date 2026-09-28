"""Lessons index legacy: the predicate that recognizes a hand-authored,
legacy-shaped lessons index, and the fence-aware listing of the sections a
`--replace-legacy` write would drop.

Imports `parse_lessons` only. Imported by `lessons_index_run`. Re-exported
unchanged by the `generate_lessons_index` facade.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_lessons import detect_index_shape

# --------------------------------------------------------------------------
# Legacy-shape predicate
# --------------------------------------------------------------------------


def is_legacy_index(content: str) -> bool:
    """True when `content` is a legacy-shaped lessons index (a
    `## Master Table` or `## Rule Promotion Log` heading present in the
    hub path) -- delegates entirely to `parse_lessons.detect_index_shape`,
    never re-derived. A write path refuses on this result unless a caller
    explicitly opts to replace a legacy-shaped index.
    """
    return detect_index_shape(content) == "legacy"


_LEGACY_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_LEGACY_HEADING_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _legacy_headings_to_drop(content: str) -> list:
    """Every `## ` heading in a legacy hub's raw content that
    `--replace-legacy` silently drops -- every H2 except `## Master
    Table`, whose row DATA migrates into the generated table (the heading
    structure around it does not, and neither does anything else). A real
    project's legacy hub typically accumulates hand-written prose sections
    here -- Naming Convention, Status Definitions, Quick Reference, Lesson
    File Template, Archive, the Rule Promotion Log pointer note -- that
    this generator has no migration path for (a later session relocates
    them); this function migrates nothing itself, it only names what is
    about to be lost so the operator sees it, on a legacy-hub refusal and
    on the `--replace-legacy` run that actually drops them.

    Fence-aware: a `## `-shaped line inside a fenced code block (opened and
    closed by a matching ``` or ~~~ line) is body text, not a heading -- a
    Lesson File Template section fences its own example `## Context` /
    `## Lesson` / `## Applies To` sub-headings inside one such block, and
    those must never be reported as sections this run drops.
    """
    headings = []
    in_fence = False
    for line in content.split("\n"):
        if _LEGACY_HEADING_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _LEGACY_HEADING_RE.match(line)
        if match and match.group(1).strip() != "Master Table":
            headings.append(match.group(1).strip())
    return headings
