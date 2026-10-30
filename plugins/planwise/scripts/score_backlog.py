#!/usr/bin/env python3
"""Compute priority scores for backlog items and report them.

Reads the backlog index table and computes a numeric score per open item
using 8 weighted factors (configurable via config.yaml). Every mode is
read-only: the index is a generated artifact produced by
generate_backlog_index.py --write, so this script never writes a score back
into it. `--id N --explain` prints one item's per-factor derivation instead.
`--route` reports the mechanical half of the triage routing signals and the
provisional route the handler's Decision Logic derives from them (see
`compute_route_signals`); it is a report over the same single read.

Factors:
  1. Priority        — High/Medium/Low (configurable points)
  2. Bug/Fix class   — bonus if abbrev is BUG (controlled vocabulary; a
                        title-cap cannot truncate an enum the way it can
                        truncate free text)
  3. IN_PROGRESS     — bonus if status is IN_PROGRESS
  4. File count      — bonus per extra file beyond 1
  5. PLANNING penalty — penalty if status is PLANNING
  6. Blocks count    — bonus per item blocked (from YAML frontmatter)
  7. Abbrev momentum — bonus if same-abbrev item recently completed (Archive/)
  8. Age             — bonus per week since created (capped)
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from config_loader import get_scoring_weights, load_config
from constants import OPEN_STATUSES

# The frontmatter readers live in `item_frontmatter` and are re-exported here for existing importers.
from item_frontmatter import (
    _strip_inline_comment,  # noqa: F401 -- re-exported for callers of score_backlog
    _text_level_scoring_fields,  # noqa: F401 -- re-exported for callers of score_backlog
    read_item_frontmatter,
)

# The item-shape reading lives in `item_shape`, and this module re-exports
# its names, so `score_backlog.compute_item_shape` and the rest still
# resolve for callers and tests.
from item_shape import (
    _ANSWER_LINE_RE,  # noqa: F401 -- re-exported for callers of score_backlog
    _H2_RE,
    _QUESTION_HEADING_RE,  # noqa: F401 -- re-exported for callers of score_backlog
    REFINED_SECTION_HEADINGS,
    _blank_fenced_blocks,
    _longest_numbered_run,
    _section_spans,
    compute_item_shape,
    read_item_sections,  # noqa: F401 -- re-exported for callers of score_backlog
)
from markdown_parser import (
    normalize_id,
    parse_markdown_table,
    warn_on_unparsed_rows,
)
from scoped_rules import (
    LOOP_WRITTEN_HEADINGS,
    SIGNAL_EXCLUDED_HEADINGS,
    scoped_rules_block,
    section_line_count,
    strip_loop_sections,
    strip_sections,
)


def _score_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a backlog table row for scoring purposes.

    Score and Files are read position-relative to the row's own width
    (``cells[-2]`` / ``cells[-1]``), mirroring
    ``parse_backlog._backlog_row_processor`` and
    ``generate_backlog_index.py``'s own asserted contract
    (``COL_SCORE == COLUMN_COUNT - 2``, ``COL_FILE == COLUMN_COUNT - 1``) —
    a 7- or 9-column row resolves correctly with no per-width branch. A
    6-column row carries no Score column at all; ``cells[-2]`` on a 6-cell
    row would misread the Abbrev cell as Score, so that width keeps its own
    branch (Score absent, Files still the last cell).
    """
    if len(cells) < 6:
        return None

    if len(cells) >= 7:
        return {
            "id": cells[0],
            "feature": cells[1],
            "priority": cells[2],
            "status": cells[3],
            "abbrev": cells[4],
            "score": cells[-2],
            "files_raw": cells[-1],
            "file_count": len(re.findall(r"\[(\d+)\]\(", cells[-1])),
            "line_number": line_number,
        }
    return {
        "id": cells[0],
        "feature": cells[1],
        "priority": cells[2],
        "status": cells[3],
        "abbrev": cells[4],
        "score": None,
        "files_raw": cells[-1],
        "file_count": len(re.findall(r"\[(\d+)\]\(", cells[-1])),
        "line_number": line_number,
    }


def parse_index_table(content: str) -> list[dict]:
    """Parse the Backlog Items table from the index markdown.

    Returns list of dicts with keys: id, feature, priority, status, abbrev,
    score (str or None), files_raw, file_count, line_number.

    A ``generate_backlog_index.py``-produced hub, overflow leaf, or Archive
    shard carries no "## Backlog Items" heading — only the table itself.
    ``parse_backlog.with_section_heading`` is imported locally (not at module
    top) to avoid a real import cycle: ``generate_backlog_index`` imports
    ``compute_score``/``count_archived_by_abbrev`` from this module, and
    ``parse_backlog`` imports from ``generate_backlog_index`` — a module-level
    import here would close that loop. Splicing the same synthetic heading
    ``parse_backlog`` uses is a no-op on content that already carries one, so
    this changes nothing for the legacy index format.

    Warns loudly if any row present in the table failed to parse, so the
    "N open items" headline is never quietly derived from a short read.
    """
    from parse_backlog import with_section_heading

    stats: dict = {}
    items = parse_markdown_table(
        with_section_heading(content), "## Backlog Items", _score_row_processor, stats=stats
    )
    warn_on_unparsed_rows(stats, "Backlog Items")
    return items


def _enumerate_hub_family_files(index_path: Path, backlog_dir: Path) -> list[Path]:
    """Every on-disk hub-family file: the hub itself plus any overflow leaf
    `generate_backlog_index.py` split it into when the open-item set alone
    exceeded the per-file token budget.

    Deliberately scoped to `backlog_dir` only, never `archive_dir` -- an
    Archive shard holds only CLOSED items, which this scorer never computes
    a score for, so unioning it in would add cost with no reporting benefit.
    Imported locally (not at module top) to avoid a real `score_backlog`
    <-> `generate_backlog_index` import cycle -- see `parse_index_table`'s
    docstring. A legacy single-file corpus's only match is the hub itself,
    so this is a no-op there.
    """
    from generate_backlog_index import _index_naming, is_generated_index_file

    if not backlog_dir.is_dir():
        return [index_path] if index_path.exists() else []
    naming = _index_naming(index_path)
    return sorted(
        path for path in backlog_dir.iterdir()
        if path.is_file() and is_generated_index_file(path.name, naming)
    )


def _read_hub_family_items(index_path: Path, backlog_dir: Path) -> list[dict]:
    """Parse every hub-family file's Backlog Items table and union the
    result.

    An open item living in an overflow leaf must be scored and reported
    exactly like one in the hub, not silently skipped -- the defect this
    closes: a hub item's `blocks:` bonus naming a leaf item lost its bonus
    because the leaf's item never reached `open_item_ids` at all.
    """
    items: list[dict] = []
    for path in _enumerate_hub_family_files(index_path, backlog_dir):
        try:
            file_content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        items.extend(parse_index_table(file_content))
    return items


def count_archived_by_abbrev(archive_dir: Path) -> dict[str, int]:
    """Count items in Archive/ grouped by abbrev prefix."""
    if not archive_dir.exists():
        return {}
    counts: dict[str, int] = {}
    for f in archive_dir.glob("*.md"):
        parts = f.name.split("-")
        # New format: BB-{id}-{sb}-{domain}-{topic}.md → domain at index 3
        # Old format: {abbrev}-{id}-{seq}-{topic}.md → abbrev at index 0
        if len(parts) >= 4 and parts[0] == "BB" and parts[1].isdigit():
            abbrev = parts[3]
        else:
            abbrev = parts[0]  # old format
        counts[abbrev] = counts.get(abbrev, 0) + 1
    return counts


def _resolve_abbrev(item: dict, frontmatter: dict) -> str | None:
    """The controlled-vocabulary domain code that keys factor 2 (and any
    other abbrev-keyed decision).

    Prefers the item's own frontmatter `abbrev:` field, falling back to the
    index row's Domain cell (`item["abbrev"]`) when frontmatter carries
    none. Both are the same value for every item this scorer has ever
    seen -- a 9-column generated row's Domain cell is written from the
    same frontmatter field -- but the frontmatter copy is authoritative
    since it can never go stale relative to a regenerated index.
    """
    return frontmatter.get("abbrev") or item.get("abbrev")


def get_first_file_path(item: dict, backlog_dir: Path) -> Path | None:
    """Extract the first file path from the Files column raw string."""
    match = re.search(r"\]\(([^)]+)\)", item["files_raw"])
    if not match:
        return None
    filename = match.group(1)
    return backlog_dir / filename


class ScoreBreakdown(NamedTuple):
    """A `compute_score` result: the per-factor derivation plus the total.

    `factors` is an ordered mapping of factor name -> points contributed,
    in the same order as `backlog-schema.md`'s 8-factor table, with every
    factor present even when it contributed 0 — a factor omitted because it
    scored zero is indistinguishable from one that was never evaluated.
    `total` is the arithmetic sum, kept as its own field (not a derived
    property) so a conservation check ("does this equal the old bare int?")
    compares two plain values.
    """

    factors: dict[str, int]
    total: int


def compute_score(
    item: dict,
    frontmatter: dict,
    archive_counts: dict[str, int],
    weights: dict,
    open_item_ids: set[str] | None = None,
) -> ScoreBreakdown:
    """Compute the 8-factor score for a single item.

    Returns a `ScoreBreakdown` rather than a bare int — this is a
    representation change only; `total` is the same arithmetic the old bare
    `int` return computed.
    """
    factors: dict[str, int] = {}

    # Factor 1: Priority
    priority_map = {
        "High": weights["priority_high"],
        "Medium": weights["priority_medium"],
        "Low": weights["priority_low"],
    }
    factors["priority"] = priority_map.get(item["priority"], 0)

    # Factor 2: Bug/Fix classification
    factors["bug/fix"] = (
        weights["bug_fix_bonus"] if _resolve_abbrev(item, frontmatter) == "BUG" else 0
    )

    # Factor 3: IN_PROGRESS boost
    factors["in_progress"] = weights["in_progress_bonus"] if item["status"] == "IN_PROGRESS" else 0

    # Factor 4: File count bonus
    factors["file_count"] = (
        weights["file_count_bonus"] * (item["file_count"] - 1) if item["file_count"] > 1 else 0
    )

    # Factor 5: PLANNING penalty
    factors["planning_penalty"] = weights["planning_penalty"] if item["status"] == "PLANNING" else 0

    # Factor 6: Blocks count — only count blocks targeting open items
    blocks = frontmatter.get("blocks", [])
    blocks_points = 0
    if isinstance(blocks, list):
        if open_item_ids is not None:
            open_blocks = [b_str for b in blocks if (b_str := str(b).zfill(3)) in open_item_ids]
            blocks_points = weights["blocks_bonus"] * len(open_blocks)
        else:
            blocks_points = weights["blocks_bonus"] * len(blocks)
    factors["blocks"] = blocks_points

    # Factor 7: Abbrev momentum
    factors["momentum"] = weights["momentum_bonus"] if archive_counts.get(item["abbrev"], 0) > 0 else 0

    # Factor 8: Age (weeks since created, capped)
    age_points = 0
    created = frontmatter.get("created")
    if created:
        try:
            if isinstance(created, date) and not isinstance(created, datetime):
                created_date = created
            elif isinstance(created, datetime):
                created_date = created.date()
            else:
                created_date = date.fromisoformat(str(created))
            weeks = (datetime.now().astimezone().date() - created_date).days // 7
            age_points = min(weeks * weights["age_bonus_per_week"], weights["age_cap"])
        except (ValueError, TypeError):
            pass
    factors["age"] = age_points

    return ScoreBreakdown(factors=factors, total=sum(factors.values()))


def _blocks_detail(frontmatter: dict, open_item_ids: set[str] | None) -> str | None:
    """The `--explain` parenthetical for the blocks factor, or None when
    there is nothing to show (no blocks at all)."""
    blocks = frontmatter.get("blocks", [])
    if not isinstance(blocks, list) or not blocks:
        return None
    if open_item_ids is not None:
        count = sum(1 for b in blocks if str(b).zfill(3) in open_item_ids)
        return f"{count} open"
    return str(len(blocks))


def _age_detail(frontmatter: dict) -> str | None:
    """The `--explain` parenthetical for the age factor, or None when
    `created` is absent or unparseable."""
    created = frontmatter.get("created")
    if not created:
        return None
    try:
        if isinstance(created, date) and not isinstance(created, datetime):
            created_date = created
        elif isinstance(created, datetime):
            created_date = created.date()
        else:
            created_date = date.fromisoformat(str(created))
    except (ValueError, TypeError):
        return None
    weeks = (datetime.now().astimezone().date() - created_date).days // 7
    return f"{weeks} weeks"


def format_score_explanation(
    item_id: str,
    item: dict,
    breakdown: ScoreBreakdown,
    frontmatter: dict,
    open_item_ids: set[str] | None,
) -> str:
    """Render `breakdown`'s per-factor derivation, one line per factor —
    every factor shown, zero-contributing factors included, so a factor
    that scored 0 reads as "evaluated, no bonus" rather than "not run"."""
    details = {
        "priority": item.get("priority"),
        "bug/fix": _resolve_abbrev(item, frontmatter),
        "file_count": str(item.get("file_count", 0)),
        "blocks": _blocks_detail(frontmatter, open_item_ids),
        "age": _age_detail(frontmatter),
    }
    lines = [f"{item_id}  score {breakdown.total}"]
    for name, points in breakdown.factors.items():
        detail = details.get(name)
        label = f"{name}({detail})" if detail else name
        sign = "+" if points > 0 else ""
        lines.append(f"  {label:<20} {sign}{points}")
    return "\n".join(lines)


def _score_total(breakdown: ScoreBreakdown | None) -> int:
    """Extract the int total from a `ScoreBreakdown`, defaulting to 0 for an
    item with no computed score (e.g. absent from `scores` entirely)."""
    return breakdown.total if breakdown is not None else 0


def review_items(
    items: list[dict],
    scores: dict[str, ScoreBreakdown],
    frontmatters: dict[str, dict],
) -> str:
    """Generate a priority review report."""
    lines = ["PRIORITY REVIEW", "=" * 50, ""]

    # 1. Items approaching age cap (>8 weeks)
    lines.append("Items approaching age cap (>8 weeks):")
    found = False
    for item in items:
        if item["status"] not in OPEN_STATUSES:
            continue
        fm = frontmatters.get(item["id"], {})
        created = fm.get("created")
        if created:
            try:
                if isinstance(created, date) and not isinstance(created, datetime):
                    created_date = created
                elif isinstance(created, datetime):
                    created_date = created.date()
                else:
                    created_date = date.fromisoformat(str(created))
                weeks = (datetime.now().astimezone().date() - created_date).days // 7
                if weeks > 8:
                    score = _score_total(scores.get(item["id"]))
                    lines.append(f"  ID {item['id']} — {item['feature'][:50]} (age: {weeks} weeks, score: {score})")
                    found = True
            except (ValueError, TypeError):
                pass
    if not found:
        lines.append("  (none)")
    lines.append("")

    # 2. Score/priority mismatch
    lines.append("Score/priority mismatch:")
    found = False
    for item in items:
        if item["status"] not in OPEN_STATUSES:
            continue
        score = _score_total(scores.get(item["id"]))
        if score >= 25 and item["priority"] == "Low":
            lines.append(f"  ID {item['id']} — {item['feature'][:50]} (Low priority, score: {score})")
            found = True
        elif score <= 20 and item["priority"] == "High":
            lines.append(f"  ID {item['id']} — {item['feature'][:50]} (High priority, score: {score})")
            found = True
    if not found:
        lines.append("  (none)")
    lines.append("")

    # 3. IN_PROGRESS items
    lines.append("IN_PROGRESS items (review for staleness):")
    found = False
    for item in items:
        if item["status"] == "IN_PROGRESS":
            score = _score_total(scores.get(item["id"]))
            lines.append(f"  ID {item['id']} — {item['feature'][:50]} (score: {score})")
            found = True
    if not found:
        lines.append("  (none)")
    lines.append("")

    # 4. High-impact blockers
    lines.append("High-impact blockers (blocks 2+ items):")
    found = False
    for item in items:
        if item["status"] not in OPEN_STATUSES:
            continue
        fm = frontmatters.get(item["id"], {})
        blocks = fm.get("blocks", [])
        if isinstance(blocks, list) and len(blocks) >= 2:
            lines.append(f"  ID {item['id']} — {item['feature'][:50]} (blocks: {blocks})")
            found = True
    if not found:
        lines.append("  (none)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# --route: the mechanical half of the triage routing signals
# ---------------------------------------------------------------------------
#
# The triage handler's Routing Decision Tree names nine scope signals. Eight
# are computable from the index row and the item body this script already
# holds. The pivot check, the existence premise, citation freshness and
# staleness are judgment and stay with the handler; the scoped-rule gate is
# computed here from the item's destinations and the project's rule
# frontmatter (see `scoped_rules_block`, called when `compute_route_signals`
# is given the config). What follows computes the eight and applies the handler's
# Decision Logic pseudocode without modification. The result is a report,
# recomputed from the live files on every call, so it cannot go stale
# silently -- unlike the optional `route_hint:` frontmatter, which is a dated
# claim the report compares itself against but never adopts.

# "multi-sprint" / "phased" -> HAS_MULTI_SPRINT (strong -> Session Planning)
MULTI_SPRINT_TERMS: tuple[str, ...] = ("multi-sprint", "phased")
# "refactor" / "redesign" / "architecture" / "migration" -> IS_ARCHITECTURAL.
# Matched as word stems so "refactoring", "architectural" and "migrations"
# count; a stem is the handler's keyword with its inflection removed.
ARCHITECTURAL_TERMS: tuple[str, ...] = ("refactor", "redesign", "architectur", "migration")
# A stem inside a name is vocabulary, not a statement about the work: a
# module called `rule_descope_migration`, a filename, or a path through a
# folder called `...Redesign/`. These three shapes are removed from a line
# before the stems are matched, and the hits they carried are reported as
# ignored so a reader still sees them.
# -- a path with two or more separators (`a/b/c`): one separator is too often
#    prose ("migration/refactor"), and a single-separator path ends in a
#    filename that `_FILE_PATH_RE` already removes
_PATH_NAME_RE = re.compile(r"[\w.~-]+(?:[/\\][\w.~-]+){2,}")
# -- a snake_case identifier (`backlog_migration`, `rule_descope_migration`)
_IDENTIFIER_NAME_RE = re.compile(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b")
# -- a line that is an `**Evidence:**` line quotes a log or a past reading,
#    and a table row quotes a cell. Neither describes the work the item asks for.
_EVIDENCE_LINE_RE = re.compile(r"^[\s>*+-]*(?:\*\*|__)?evidence(?:\*\*|__)?\s*:", re.IGNORECASE)
_TABLE_ROW_RE = re.compile(r"^\s*\|")
# -- the one `##` section whose prose describes the work the item asks for.
#    When an item carries this heading, only its lines feed IS_ARCHITECTURAL;
#    the title, Summary, Problem, Acceptance Criteria and Related name the
#    subject and its neighbours, so a stem there is vocabulary. An item
#    without the heading is read whole. The match is exact, like
#    TEMPLATE_SECTION_HEADINGS, and a test pins it to the template file.
COUNTED_SECTION_HEADING = "Proposed Solution"
# "Item file < 50 lines" -> IS_SHORT (a proxy for a small fix)
SHORT_ITEM_LINES = 50
# "6+ sub-items or ## headings" -> SUB_ITEMS >= 6
SUB_ITEMS_THRESHOLD = 6
# "2 <= STEP_COUNT <= 5" -> Route B. A refined item reaches Route B from one
# `## Resolution` step up to the same cap.
ROUTE_B_MIN_STEPS = 2
ROUTE_B_MAX_STEPS = 5

# The `##` section names of the backlog item template. Every filled-in item
# carries them, so they describe the item's layout and say nothing about its
# scope: they are excluded from the sub-item count. The match is exact and
# case-sensitive. A test pins this tuple to the template file.
TEMPLATE_SECTION_HEADINGS: tuple[str, ...] = (
    "Summary",
    "Problem",
    "Proposed Solution",
    "Acceptance Criteria",
    "Related",
    "Files Touched",
    "Notes",
    "Loop Decision Needed",  # loop-written; the loop's skip section (see LOOP_WRITTEN_HEADINGS in scoped_rules)
) + REFINED_SECTION_HEADINGS
_FILE_PATH_RE = re.compile(
    r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|cs|java|go|rs|rb|sh|ps1|sql|ya?ml|json|toml|ini|html|css|c|cpp|h|md)\b"
)
# The three evidence shapes behind HAS_CLEAR_FIX's mechanical half. Each
# pattern names the phrasings seen in this corpus; a miss here reports
# `clear_fix.*=no` with the sub-flag visible, so a reader sees which shape
# was not recognised rather than a bare verdict.
# -- a `file:line` anchor (`backlog.md:137-211`) or `line 80` / `lines 97-101`
_LINE_ANCHOR_RE = re.compile(r"\.[A-Za-z0-9]+:\d+(?:-\d+)?\b|\blines? \d+", re.IGNORECASE)
# -- an exact edit target: an old_string/new_string pair, a diff fence, or a
#    whole-file copy ("copy X over Y", "byte copy"). A verbatim string or a
#    whole file locates an edit as precisely as a line number, and survives
#    the line drift a number does not.
_EDIT_TARGET_RE = re.compile(
    r"old_string|```diff|\bcopy\b[^\n]{0,160}\bover\b|byte copy", re.IGNORECASE
)
# -- before/after content: the phrase, a WRONG/CORRECT pair, an old -> new
#    arrow, or "replace X with Y"
_BEFORE_AFTER_RE = re.compile(
    r"before/after|before-and-after|\bbefore\b[^\n]{0,80}\bafter\b|\bold\b\s*(?:→|->|to)\s*\bnew\b"
    r"|\breplace\b[^\n]{0,120}\bwith\b",
    re.IGNORECASE,
)
# -- a symbol named in prose: a backticked function call (`name()`), a snake_case
#    name, a CamelCase name or an UPPER_SNAKE constant. A file name carries a dot
#    and never matches. It reads the body with fenced blocks blanked, so the code
#    quoted in a fence does not name itself.
_NAMED_SYMBOL_RE = re.compile(
    r"`(?:_*[A-Za-z][A-Za-z0-9_]*\(\)"
    r"|_*[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
    r"|_*[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+"
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)`"
)
# -- an imperative amend verb opening a sentence or list item ("Amend the two
#    sentences ..."), followed within 240 characters, and not past a heading,
#    by the new text in double quotes (12+ characters). A line anchor does not
#    count: "change the string on line 3" says where the edit goes and not what
#    it becomes, and `_LINE_ANCHOR_RE` already reports the location. The verb
#    must open the sentence: "changed", "corrected" and a mid-sentence "change"
#    describe a past event or a noun, and matched 25 unrelated items when the
#    verb was free. It reads the body with fenced blocks blanked, because a
#    docstring or a log excerpt in a fence says "rewrite" too.
_AMEND_NEW_TEXT_RE = re.compile(
    r"(?:^|[.!?:][ \t]+)[ \t>*+\d.-]*(?:amend|reword|rewrite|rephrase|change|correct)\b"
    r"(?:(?!\n[ \t>]*#)[\s\S]){0,240}?\"[^\"\n]{12,}\"",
    re.IGNORECASE | re.MULTILINE,
)


def _label_then_fence(word: str) -> str:
    """Pattern text for a label line (`word` alone, optionally a heading, a
    list bullet, bold or italic markers, a trailing colon) followed, after
    any blank lines, by the opening line of a fenced block."""
    mark = r"(?:\*\*|__|\*|_)?"
    return (
        rf"^[ \t]*(?:#{{1,6}}[ \t]+|[-*+][ \t]+)?{mark}{word}{mark}[ \t]*:?{mark}[ \t]*\r?\n"
        r"(?:[ \t]*\r?\n)*[ \t]*(?:```|~~~)"
    )


# -- a `Before` label with a fenced block under it and, on a LATER line, an
#    `After` label with a fenced block under it. No single line holds both
#    words, so the single-line clause above cannot see this shape.
_BEFORE_AFTER_BLOCKS_RE = re.compile(
    _label_then_fence("before") + r"[\s\S]*?" + _label_then_fence("after"),
    re.IGNORECASE | re.MULTILINE,
)
# -- a scope-confinement bound
_SCOPE_BOUND_RE = re.compile(
    r"out of scope|do not touch|must not touch|touch no other|edit only|scope[- ]confinement"
    r"|not solved by|intentionally not",
    re.IGNORECASE,
)
# -- a positive scope bound: a criterion that names what must keep its wording
#    ("returns 0 hits outside Recovery, Summary and Review records, which keep
#    the historical wording"). It needs both halves on ONE line: a Grep or count
#    check, and a keep / unchanged / leave-as-is / outside-records clause.
_POSITIVE_BOUND_CHECK_RE = re.compile(
    r"\bGrep\b|\bgrep -c\b|\b(?:returns?|finds?|prints?|shows?)\s+(?:\d+|zero|no)\s+(?:hits?|matches|lines)\b"
)
_POSITIVE_BOUND_CLAUSE_RE = re.compile(
    r"\bwhich keeps?\b|\bkeeps? (?:the|their|its)\b|\bleave\b[^\n]{0,60}\bas[- ]is\b"
    r"|\boutside\b[^\n]{0,80}\brecords?\b|\bunchanged\b",
    re.IGNORECASE,
)


def _has_positive_scope_bound(text: str) -> bool:
    """True when one line carries both a Grep/count check and a clause naming
    what keeps its wording (`_POSITIVE_BOUND_CLAUSE_RE`)."""
    return any(
        _POSITIVE_BOUND_CHECK_RE.search(line) and _POSITIVE_BOUND_CLAUSE_RE.search(line)
        for line in text.split("\n")
    )
# `**Evidence:** ... verified 2026-08-26 by ...` and the coordination-flag
# form `recorded 2026-09-23`: the dates a stored route hint is judged against.
_EVIDENCE_DATE_RE = re.compile(r"\b(?:verified|recorded|measured)\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


def _keyword_hits(text: str, terms: tuple[str, ...]) -> list[dict]:
    """Every case-insensitive occurrence of any term, with the line it sits
    on. The line is reported because a hit is a candidate, not a verdict: an
    item that *quotes* the handler's signal table matches every keyword in
    it without being multi-sprint or architectural itself, and only the
    surrounding text lets a reader tell the two apart."""
    hits: list[dict] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        lowered = line.lower()
        for term in terms:
            if term in lowered:
                hits.append({"term": term, "line": line_no, "text": line.strip()[:120]})
    return hits


def _architectural_hits(text: str) -> tuple[list[dict], list[dict]]:
    """(hits, ignored) for the IS_ARCHITECTURAL stems.

    `hits` are the occurrences that count. `ignored` are occurrences the
    reader can still see but the signal does not read: the line sits
    outside the `## Proposed Solution` section, the whole line is an
    `**Evidence:**` line or a table row, or the stem sits inside a file name,
    a multi-segment path or a snake_case identifier. Each ignored entry
    carries a `why`. A hit is a candidate, not a verdict (see
    `_keyword_hits`); this narrows the candidates to prose that describes
    the work, and leaves the reading of what remains to the reader.

    The section rule applies only when the item has a `## Proposed Solution`
    heading. That section is where an item describes the work it asks for;
    the title names the subject, the Summary restates the problem, and
    Related names siblings, so a stem in any of them is vocabulary. An item
    without the heading is read whole, as before. A hit outside the section
    is ignored with the section's heading as its `why` (`Summary section`),
    or `title block` for the lines before the first `##` heading.
    """
    hits: list[dict] = []
    ignored: list[dict] = []
    lines = text.split("\n")
    sectioned = any(
        _H2_RE.match(line) and line[3:].rstrip() == COUNTED_SECTION_HEADING for line in lines
    )
    section: str | None = None  # the current `##` heading; None before the first one
    for line_no, line in enumerate(lines, start=1):
        if _H2_RE.match(line):
            section = line[3:].rstrip()
        lowered = line.lower()
        present = [term for term in ARCHITECTURAL_TERMS if term in lowered]
        if not present:
            continue
        shown = line.strip()[:120]
        if sectioned and section != COUNTED_SECTION_HEADING:
            where = "title block" if section is None else f"{section} section"
            ignored.extend({"term": t, "line": line_no, "text": shown, "why": where} for t in present)
            continue
        if _EVIDENCE_LINE_RE.match(line):
            ignored.extend({"term": t, "line": line_no, "text": shown, "why": "evidence line"} for t in present)
            continue
        if _TABLE_ROW_RE.match(line):
            ignored.extend({"term": t, "line": line_no, "text": shown, "why": "table row"} for t in present)
            continue
        bare = _PATH_NAME_RE.sub(" ", _FILE_PATH_RE.sub(" ", line))
        bare = _IDENTIFIER_NAME_RE.sub(" ", bare).lower()
        for term in present:
            if term in bare:
                hits.append({"term": term, "line": line_no, "text": shown})
            else:
                ignored.append({"term": term, "line": line_no, "text": shown, "why": "file, path or identifier name"})
    return hits, ignored


def _coerce_date(value) -> date | None:
    """A frontmatter date as `date`, whether YAML typed it or left it a
    string; None when absent or unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _latest_evidence_date(body: str) -> date | None:
    """The newest dated evidence line in the body, or None when it carries
    none. This is the date a `route_dated:` hint is judged stale against."""
    dates = [_coerce_date(m) for m in _EVIDENCE_DATE_RE.findall(body)]
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def decide_route(
    has_clear_fix: bool,
    is_architectural: bool,
    has_multi_sprint: bool,
    sub_items: int,
    step_count: int,
    *,
    refined: bool = False,
    shape_ok: bool = False,
    needs_plan: bool = False,
) -> tuple[str, bool, str]:
    """The handler's Decision Logic, reproduced without modification.

    Returns (route, large_scope, branch). `large_scope` is only meaningful
    when the route is C: True means a marked-for-planning item or the
    strong-signal branch, False means C was reached through a failed shape
    gate or the conservative default. Any divergence between this function
    and the handler's pseudocode is a defect here, never a design choice.

    The seven branches run in order: `needs_plan`; today's Route A; the
    strong signals; a refined item whose shape gate passed with 1 to
    `ROUTE_B_MAX_STEPS` steps; any other refined item; 2 to
    `ROUTE_B_MAX_STEPS` steps; the default. A refined item with six or
    more steps meets the strong-signal branch first (`SUB_ITEMS >= 6`). A
    short refined item routes A, because a short file sets HAS_CLEAR_FIX.
    """
    if needs_plan:
        return "C", True, "NEEDS_PLAN: true (marked for a planning session)"
    if has_clear_fix and not (is_architectural or has_multi_sprint or sub_items >= SUB_ITEMS_THRESHOLD):
        return "A", False, "HAS_CLEAR_FIX AND NOT (IS_ARCHITECTURAL OR HAS_MULTI_SPRINT OR SUB_ITEMS >= 6)"
    if has_multi_sprint or is_architectural or sub_items >= SUB_ITEMS_THRESHOLD:
        return "C", True, "HAS_MULTI_SPRINT OR IS_ARCHITECTURAL OR (SUB_ITEMS >= 6)"
    if refined and shape_ok and 1 <= step_count <= ROUTE_B_MAX_STEPS:
        return "B", False, f"REFINED: 1 <= STEP_COUNT <= {ROUTE_B_MAX_STEPS} from ## Resolution"
    if refined:
        return "C", False, "REFINED but shape gate failed (see shape block)"
    if ROUTE_B_MIN_STEPS <= step_count <= ROUTE_B_MAX_STEPS:
        return "B", False, f"{ROUTE_B_MIN_STEPS} <= STEP_COUNT <= {ROUTE_B_MAX_STEPS}"
    return "C", False, "ELSE (conservative default)"


def judgment_routes(
    has_clear_fix: bool,
    is_architectural: bool,
    has_multi_sprint: bool,
    sub_items: int,
    step_count: int,
    is_short: bool,
    clear_fix_evidence: bool,
    *,
    clear_fix_candidate: bool = False,
    refined: bool = False,
    shape_ok: bool = False,
    needs_plan: bool = False,
) -> tuple[set[str], list[str]]:
    """(routes a reader's judgment could reach, the signals that judgment turns on).

    Three signals are candidates the script reports and a reader classifies:
    `IS_ARCHITECTURAL` and `HAS_MULTI_SPRINT` (each a keyword hit that may
    quote a name or a table), and `HAS_CLEAR_FIX`. The first two can be
    judged absent only when the script found them present.

    `HAS_CLEAR_FIX` is judged in either direction. When the script found
    its evidence shapes present, the reader decides whether they are enough
    and may judge the signal absent. When the script found them absent
    (`clear_fix_candidate`: the item quotes the current code in a fence and
    names a symbol, so the fix may be exact in prose the patterns do not
    read), the reader may judge the signal present, and the set can reach
    route A. That second class is reported as `HAS_CLEAR_FIX (judged
    present)`. A short file's `HAS_CLEAR_FIX` is a line count, so it is
    mechanical. The returned set holds the route of every combination of
    those judgments, the script's own route included. The signals that no
    reader judgment can move (abbrev, line count, file count, sub-item
    count, step count) are held fixed, and so are `refined`, `shape_ok`
    and `needs_plan`, which every combination passes to `decide_route`.
    """
    judged_absent = has_clear_fix and clear_fix_evidence and not is_short
    judged_present = clear_fix_candidate and not has_clear_fix
    adjustable = [
        name
        for name, present in (
            ("IS_ARCHITECTURAL", is_architectural),
            ("HAS_MULTI_SPRINT", has_multi_sprint),
            ("HAS_CLEAR_FIX", judged_absent),
            ("HAS_CLEAR_FIX (judged present)", judged_present),
        )
        if present
    ]
    routes: set[str] = set()
    for mask in range(1 << len(adjustable)):
        flipped = {name for i, name in enumerate(adjustable) if mask & (1 << i)}
        route, _large, _branch = decide_route(
            has_clear_fix != bool(flipped & {"HAS_CLEAR_FIX", "HAS_CLEAR_FIX (judged present)"}),
            is_architectural and "IS_ARCHITECTURAL" not in flipped,
            has_multi_sprint and "HAS_MULTI_SPRINT" not in flipped,
            sub_items,
            step_count,
            refined=refined,
            shape_ok=shape_ok,
            needs_plan=needs_plan,
        )
        routes.add(route)
    return routes, adjustable


def reconcile_route_hint(
    frontmatter: dict,
    route: str,
    latest_evidence: date | None,
    judgment: tuple[set[str], list[str]] | None = None,
) -> dict | None:
    """Compare the item's optional `route_hint:` frontmatter with the
    computed route. None when the item carries no hint.

    The hint is never adopted here or anywhere: this reports agreement and
    staleness so the handler can state the divergence in its Reason line.
    `stale` is None when the item carries no dated evidence line to judge
    against, or the hint carries no `route_dated:`.

    `judgment` is `judgment_routes`' result. When the hint is valid, not
    stale and differs from `route`, and it names a route a reader's judgment
    of the candidate signals could reach, the verdict is `undecided`: the
    script cannot overrule a hint with a signal it calls a candidate. A stale
    hint, an invalid hint, and a hint no judgment reaches keep `script wins`.
    """
    raw_hint = frontmatter.get("route_hint")
    if raw_hint is None or str(raw_hint).strip() == "":
        return None
    hint = str(raw_hint).strip().upper()
    valid = hint in ("A", "B", "C")
    dated = _coerce_date(frontmatter.get("route_dated"))
    stale: bool | None = None
    if dated is not None and latest_evidence is not None:
        stale = dated < latest_evidence
    agrees = valid and hint == route
    reachable, judged = judgment if judgment is not None else (set(), [])
    undecided = valid and not agrees and not stale and hint in reachable
    if not valid:
        verdict = "script wins — hint is not one of A/B/C"
    elif undecided:
        verdict = "undecided — the divergence rests on reader-judgment signals; see the hit lines"
    elif not agrees:
        verdict = "script wins — hint disagrees with the live signals"
    elif stale:
        verdict = "agree — but the hint predates the item's newest evidence"
    else:
        verdict = "agree"
    return {
        "route": hint,
        "valid": valid,
        "evidence": frontmatter.get("route_evidence"),
        "dated": dated.isoformat() if dated else None,
        "latest_evidence_date": latest_evidence.isoformat() if latest_evidence else None,
        "agrees": agrees,
        "undecided": undecided,
        "judgment_signals": judged if undecided else [],
        "stale": stale,
        "verdict": verdict,
    }


def compute_route_signals(item: dict, frontmatter: dict, config: dict | None = None) -> dict:
    """The mechanical signal vector for one open item, plus the provisional
    route `decide_route` derives from it.

    Reads only the index row (`item`) and what `read_item_frontmatter`
    already returned (`frontmatter`, including `_body` and `_line_count`);
    without `config` it opens no file. HAS_CLEAR_FIX is reported as its
    mechanical half only -- whether the evidence shapes are *present* (an
    edit location: a line anchor, an exact edit string, or a whole-file
    copy; a before/after; a scope-confinement bound). Whether they are
    *sufficient* is a judgment this function does not make and the report
    says so.

    Loop-written sections (`## Loop Decision Needed`) and `## Open Questions`
    (`SIGNAL_EXCLUDED_HEADINGS`) are removed from the body before any signal
    is read, so a skip the backlog loop records or a question the item still
    asks never moves the item's route, headings, steps or effective line
    count. `line_count` stays the whole file's count; `is_short` reads
    `line_count_effective`, which excludes the `excluded_lines` removed.
    Those include the blank-line separators a removed run takes with it.
    `loop_lines` counts only the lines inside the loop-written sections,
    heading to end (`scoped_rules.section_line_count`). A blank line outside
    them is never a loop line, even when the strip removes it.

    Keyword and structure signals read the body with fenced blocks blanked
    (see `_blank_fenced_blocks`); the clear-fix patterns read it whole.

    The result carries the `shape` block (`compute_item_shape`), read from
    the body with only the loop sections removed. A refined item takes
    `step_count` from its `## Resolution` steps only, and `step_count_source`
    names which text the count came from. When its shape gate also passes
    (`shape_ok`), its multi-sprint and architectural hits, H2 count and
    sub-items read `## Resolution` only, too. A refined item whose shape
    gate fails reads them from the whole body, as an unrefined item does,
    so a large-scope signal anywhere in it still blocks Route A.

    With `config`, the result carries the `scoped_rules` block
    (`scoped_rules_block` over the raw body, which strips the
    `SIGNAL_EXCLUDED_HEADINGS` sections itself, `## Open Questions`
    included); without it, `scoped_rules` is None and no file is read.
    """
    raw_body = frontmatter.get("_body") or ""
    loop_body, _ = strip_loop_sections(raw_body)
    loop_lines = section_line_count(raw_body, LOOP_WRITTEN_HEADINGS)
    body, excluded_lines = strip_sections(raw_body, SIGNAL_EXCLUDED_HEADINGS)
    body_available = "_body" in frontmatter
    structural = _blank_fenced_blocks(body)
    line_count = frontmatter.get("_line_count")
    line_count_effective = None if line_count is None else line_count - excluded_lines

    abbrev = _resolve_abbrev(item, frontmatter)
    is_bug = abbrev == "BUG"
    is_short = line_count_effective is not None and line_count_effective < SHORT_ITEM_LINES
    file_paths = sorted(set(_FILE_PATH_RE.findall(body)))

    # The shape gate reads `## Open Questions`, so it gets the body with only
    # the loop sections removed.
    shape = compute_item_shape(frontmatter, body=loop_body, blanked=_blank_fenced_blocks(loop_body))
    # A refined item whose shape gate passes reads its large-scope signals
    # from its `## Resolution` section only. The other lines are blanked, so
    # a hit's line number counts lines of the body with the
    # `SIGNAL_EXCLUDED_HEADINGS` sections removed, as for any other item.
    # A refined item whose gate fails reads the whole body.
    signal_text = structural
    if shape["refined"] and shape["shape_ok"]:
        resolution = _section_spans(structural).get("Resolution", (0, 0))
        signal_text = "\n".join(
            line if resolution[0] <= index < resolution[1] else ""
            for index, line in enumerate(structural.split("\n"))
        )

    multi_sprint_hits = _keyword_hits(signal_text, MULTI_SPRINT_TERMS)
    architectural_hits, architectural_ignored = _architectural_hits(signal_text)
    has_multi_sprint = bool(multi_sprint_hits)
    is_architectural = bool(architectural_hits)

    h2_count = sum(
        1
        for line in signal_text.split("\n")
        if _H2_RE.match(line) and line[3:].rstrip() not in TEMPLATE_SECTION_HEADINGS
    )
    numbered_items, body_step_count = _longest_numbered_run(signal_text)
    sub_items = max(h2_count, body_step_count)
    # A refined item's steps are its `## Resolution` steps; any other item
    # reads the body's longest run, as before.
    if shape["refined"]:
        step_count, step_count_source = shape["resolution_steps"], "## Resolution"
    else:
        step_count, step_count_source = body_step_count, "body"
    route_flags = {
        "refined": shape["refined"],
        "shape_ok": shape["shape_ok"],
        "needs_plan": shape["needs_plan"],
    }

    file_count = int(item.get("file_count", 0) or 0)

    clear_fix = {
        "line_anchor": bool(_LINE_ANCHOR_RE.search(body)),
        "edit_target": bool(_EDIT_TARGET_RE.search(body)),
        "before_after": (
            bool(_BEFORE_AFTER_RE.search(body))
            or bool(_BEFORE_AFTER_BLOCKS_RE.search(body))
            or bool(_AMEND_NEW_TEXT_RE.search(structural))
            or ("WRONG" in body and "CORRECT" in body)
        ),
        "scope_bound": bool(_SCOPE_BOUND_RE.search(body)) or _has_positive_scope_bound(body),
    }
    clear_fix["evidence_present"] = (
        (clear_fix["line_anchor"] or clear_fix["edit_target"])
        and clear_fix["before_after"]
        and clear_fix["scope_bound"]
    )
    has_clear_fix = is_short or clear_fix["evidence_present"]
    # The fix may be exact in prose the patterns do not read: the item quotes
    # the current code in a fence and names a symbol. The script reports it as
    # a candidate and leaves the call to the reader. It never moves the route.
    clear_fix_candidate = (
        not has_clear_fix and structural != body and bool(_NAMED_SYMBOL_RE.search(structural))
    )

    route, large_scope, branch = decide_route(
        has_clear_fix, is_architectural, has_multi_sprint, sub_items, step_count, **route_flags
    )
    hint = reconcile_route_hint(
        frontmatter,
        route,
        _latest_evidence_date(body),
        judgment_routes(
            has_clear_fix, is_architectural, has_multi_sprint, sub_items, step_count,
            is_short, clear_fix["evidence_present"],
            clear_fix_candidate=clear_fix_candidate, **route_flags,
        ),
    )

    return {
        "id": item["id"],
        "body_available": body_available,
        "abbrev": abbrev,
        "is_bug": is_bug,
        "line_count": line_count,
        "loop_lines": loop_lines,
        "excluded_lines": excluded_lines,
        "line_count_effective": line_count_effective,
        "is_short": is_short,
        "file_paths": file_paths,
        "multi_sprint_hits": multi_sprint_hits,
        "has_multi_sprint": has_multi_sprint,
        "architectural_hits": architectural_hits,
        "architectural_ignored": architectural_ignored,
        "is_architectural": is_architectural,
        "h2_count": h2_count,
        "numbered_items": numbered_items,
        "sub_items": sub_items,
        "step_count": step_count,
        "step_count_source": step_count_source,
        "shape": shape,
        "file_count": file_count,
        "has_multiple_files": file_count >= 2,
        "clear_fix": clear_fix,
        "has_clear_fix": has_clear_fix,
        "clear_fix_candidate": clear_fix_candidate,
        "has_clear_fix_note": (
            "mechanical half only: a short file, or an edit location (line anchor, "
            "exact edit string, or whole-file copy) + a before/after + a scope bound "
            "all present. "
            "Sufficiency is a judgment the reader makes."
        ),
        "route": route,
        "large_scope": large_scope,
        "branch": branch,
        "hint": hint,
        "scoped_rules": None if config is None else scoped_rules_block(item["id"], raw_body, config),
    }


ROUTE_LEGEND = (
    "Legend: route A = Direct Fix, B = Task List, C = Session Planning; "
    "large = LARGE_SCOPE (meaningful for C only).\n"
    "  clear = HAS_CLEAR_FIX, mechanical half only (short file, or edit location + "
    "before/after + scope bound present); sufficiency is a judgment.\n"
    "  ms/arch = keyword hit counts for HAS_MULTI_SPRINT / IS_ARCHITECTURAL -- "
    "candidates, not verdicts; an item quoting the signal table matches them all. "
    "Use --id N for the hit lines.\n"
    "  ign = IS_ARCHITECTURAL hits dropped as lines outside ## Proposed Solution (when the item has one), "
    "evidence lines, table rows, or names (files, paths, identifiers).\n"
    "  h2/steps = non-template ## headings outside code fences / longest consecutive numbered list.\n"
    "  hint = the item's route_hint frontmatter, compared but never adopted; undecided = the hint names a route "
    "a reader's judgment of the candidate signals could reach.\n"
    "  rules = scoped_rules verdict: i = inject the matched rules, p = placement decision needed, - = none.\n"
    "  ref = the item's refined frontmatter (y/n); a refined item's steps come from ## Resolution, and "
    "--id N prints its shape gate.\n"
    "The scoped-rule gate is computed here (rules column); the pivot check and the other pre-routing gates "
    "are judgment, and this report does not run them."
)


def format_route_line(signals: dict, score: int) -> str:
    """One report row per item for the all-items `--route` listing."""
    hint = signals["hint"]
    if hint is None:
        hint_text = "-"
    elif hint["undecided"]:
        hint_text = f"{hint['route']} undecided"
    elif hint["agrees"] and not hint["stale"]:
        hint_text = f"{hint['route']} agree"
    elif hint["agrees"]:
        hint_text = f"{hint['route']} agree/stale"
    else:
        hint_text = f"{hint['route']} DISAGREE"
    large = "large" if signals["route"] == "C" and signals["large_scope"] else "-"
    block = signals.get("scoped_rules")
    verdict = block["verdict"] if block else None
    rules = {"inject": "i", "placement": "p"}.get(verdict, "-")
    return (
        f"  ID {signals['id']:>3} | {signals['route']} | {large:<5} | {score:>3} pts | "
        f"clear={'y' if signals['has_clear_fix'] else 'n'} "
        f"ms={len(signals['multi_sprint_hits'])} arch={len(signals['architectural_hits'])} "
        f"ign={len(signals['architectural_ignored'])} "
        f"h2={signals['h2_count']} steps={signals['step_count']} "
        f"ref={'y' if signals['shape']['refined'] else 'n'} files={signals['file_count']} "
        f"rules={rules} "
        f"| hint {hint_text}"
    )


def _format_scoped_rules(block: dict | None) -> list[str]:
    """The `scoped_rules:` lines of the `--route --id N` detail."""
    if block is None:
        return ["  scoped_rules:      (not computed)"]
    lessons = ", ".join(block["owning_lessons"]) or "none"
    lines = [
        (f"  scoped_rules:      {block['verdict']}  (source: {block['source']}; "
         f"{block['rules_scanned']} path-scoped rules scanned; owning lessons: {lessons}; "
         f"inject form: {block['inject_form']} ({block['rules_bytes']} bytes))"),
    ]
    for dest in block["destinations"]:
        matched = ", ".join(dest["rules"]) or "none"
        lines.append(f"    {dest['path']}  {dest['role']}  rules: {matched}  -> {dest['verdict']}")
    lines.append(f"  rules_to_inject:   {', '.join(block['rules_to_inject']) or 'none'}")
    return lines


def _format_shape(shape: dict) -> list[str]:
    """The three shape-block lines of the `--route --id N` detail."""
    yes_no = lambda flag: "yes" if flag else "no"
    if not shape["refined"]:
        gate = "n/a"
    elif shape["shape_ok"]:
        gate = "PASS"
    else:
        gate = f"FAIL -- missing: {'; '.join(shape['missing'])}"
    return [
        f"  refined/needs_plan: {yes_no(shape['refined'])} / {yes_no(shape['needs_plan'])}",
        f"  shape gate: {gate}",
        (f"  resolution_steps/verification/open_questions: {shape['resolution_steps']} / "
         f"{yes_no(shape['has_verification'])} / {shape['open_questions']}"),
    ]


CLEAR_FIX_CANDIDATE_NOTE = (
    "    candidate: the item quotes the current code in a fence and names a symbol; "
    "a reader may judge the fix present"
)


def format_route_detail(signals: dict, score: int) -> str:
    """The full signal vector for one item (`--route --id N`)."""
    yes_no = lambda flag: "yes" if flag else "no"
    lines = [
        (f"{signals['id']}  route {signals['route']}  LARGE_SCOPE {yes_no(signals['large_scope'])}"
         f"  (score {score})"),
        f"  branch:            {signals['branch']}",
        f"  abbrev/is_bug:     {signals['abbrev']} / {yes_no(signals['is_bug'])}",
        (f"  line_count/short:  {signals['line_count']} / {yes_no(signals['is_short'])}"
         f"  (< {SHORT_ITEM_LINES}; {signals['excluded_lines']} loop-written and open-question lines excluded)"),
        f"  file_paths:        {len(signals['file_paths'])}",
        (f"  h2 / numbered:     {signals['h2_count']} / {signals['numbered_items']}"
         f"  -> SUB_ITEMS {signals['sub_items']} (>= {SUB_ITEMS_THRESHOLD}: "
         f"{yes_no(signals['sub_items'] >= SUB_ITEMS_THRESHOLD)})"),
        (f"  step_count:        {signals['step_count']}  (longest consecutive numbered list; "
         f"source: {signals['step_count_source']})"),
        *_format_shape(signals["shape"]),
        f"  file_count:        {signals['file_count']}  (multiple: {yes_no(signals['has_multiple_files'])})",
        f"  HAS_CLEAR_FIX:     {yes_no(signals['has_clear_fix'])}  -- {signals['has_clear_fix_note']}",
        (f"    line_anchor={yes_no(signals['clear_fix']['line_anchor'])} "
         f"edit_target={yes_no(signals['clear_fix']['edit_target'])} "
         f"before_after={yes_no(signals['clear_fix']['before_after'])} "
         f"scope_bound={yes_no(signals['clear_fix']['scope_bound'])}"),
        *([CLEAR_FIX_CANDIDATE_NOTE] if signals.get("clear_fix_candidate") else []),
        f"  HAS_MULTI_SPRINT:  {yes_no(signals['has_multi_sprint'])}  ({len(signals['multi_sprint_hits'])} hit(s))",
    ]
    lines.extend(f"    L{h['line']} [{h['term']}] {h['text']}" for h in signals["multi_sprint_hits"])
    ignored = signals["architectural_ignored"]
    lines.append(
        f"  IS_ARCHITECTURAL:  {yes_no(signals['is_architectural'])}  ({len(signals['architectural_hits'])} hit(s); "
        f"ignored ({len(ignored)}))"
    )
    lines.extend(f"    L{h['line']} [{h['term']}] {h['text']}" for h in signals["architectural_hits"])
    lines.extend(f"    ignored L{h['line']} [{h['term']}] ({h['why']}) {h['text']}" for h in ignored)
    hint = signals["hint"]
    if hint is None:
        lines.append("  route_hint:        (none) -- derive from the live signals alone")
    else:
        lines.append(f"  route_hint:        {hint['route']}  dated {hint['dated'] or '?'}  -> {hint['verdict']}")
        if hint["undecided"]:
            lines.append(f"    judgment turns on: {', '.join(hint['judgment_signals'])}")
        if hint["evidence"]:
            lines.append(f"    evidence: {hint['evidence']}")
        lines.append(
            f"    newest dated evidence in body: {hint['latest_evidence_date'] or 'none'}; "
            f"stale: {'unknown' if hint['stale'] is None else yes_no(hint['stale'])}"
        )
    lines.extend(_format_scoped_rules(signals.get("scoped_rules")))
    if not signals["body_available"]:
        lines.append("  (item body unavailable -- frontmatter did not parse; body signals are empty)")
    return "\n".join(lines)


def write_route_json(payload) -> str:
    """Write the `--route --json` payload to a temp file and return its path,
    matching `parse_backlog.write_json`'s convention."""
    tmp_dir = tempfile.mkdtemp(prefix="backlog-route-")
    json_path = os.path.join(tmp_dir, "route.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return json_path


def load_scored_items(
    config: dict,
) -> tuple[list[dict], dict[str, dict], dict[str, ScoreBreakdown], set[str]]:
    """Load and score every open item; `main()` and `backlog_loop.py --init` are the two callers.

    Returns `(items, frontmatters, scores, open_item_ids)`. Never exits: an
    empty backlog returns an empty list and the caller decides what to do.
    """
    weights = get_scoring_weights(config)
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    # Report modes (--dry-run, --review, --id/--explain, and the no-flag
    # report) all read the UNION of the hub and every hub overflow leaf -- an
    # open item living in a leaf must be scored and reported like any hub
    # item.
    items = _read_hub_family_items(index_path, backlog_dir)

    # Read frontmatter for each open item
    frontmatters: dict[str, dict] = {}
    for item in items:
        if item["status"] in OPEN_STATUSES:
            filepath = get_first_file_path(item, backlog_dir)
            if filepath:
                frontmatters[item["id"]] = read_item_frontmatter(filepath)
            else:
                frontmatters[item["id"]] = {}

    # Count archived items for momentum
    archive_counts = count_archived_by_abbrev(archive_dir)

    # Compute scores
    open_item_ids = {item["id"] for item in items if item["status"] in OPEN_STATUSES}
    scores: dict[str, ScoreBreakdown] = {}
    for item in items:
        if item["status"] in OPEN_STATUSES:
            fm = frontmatters.get(item["id"], {})
            scores[item["id"]] = compute_score(item, fm, archive_counts, weights, open_item_ids)

    return items, frontmatters, scores, open_item_ids


def main():
    parser = argparse.ArgumentParser(
        description="Compute priority scores for backlog items."
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute and print scores; every mode is report-only and never writes to the index.")
    parser.add_argument("--review", action="store_true", help="Output a priority review report; every mode is report-only and never writes to the index.")
    parser.add_argument("--id", type=str, default=None,
                        help="Look up one item's score by ID (bare or prefixed, matched on the numeric component).")
    parser.add_argument("--explain", action="store_true",
                        help="With --id, print the per-factor score derivation instead of just the total.")
    parser.add_argument("--route", action="store_true",
                        help="Report the mechanical triage-routing signal vector and provisional route "
                             "per open item (with --id, one item in full). Report-only; writes nothing.")
    parser.add_argument("--json", action="store_true",
                        help="With --route, also write the report as a JSON temp file and print its path.")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.yaml; overrides default config search and scoring thresholds.")

    args = parser.parse_args()

    if args.json and not args.route:
        print("Error: --json is only meaningful with --route.", file=sys.stderr)
        sys.exit(1)

    # Load config
    config = load_config(Path(__file__))
    index_path = config["_index_path"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    items, frontmatters, scores, open_item_ids = load_scored_items(config)

    if not items:
        print("No items found in backlog index.", file=sys.stderr)
        sys.exit(1)

    if args.id:
        target = normalize_id(args.id)
        matched_item = next((i for i in items if normalize_id(i["id"]) == target), None)
        if matched_item is None:
            print(f"Error: item {args.id} not found in backlog index.", file=sys.stderr)
            sys.exit(1)
        breakdown = scores.get(matched_item["id"])
        if breakdown is None:
            print(f"Item {matched_item['id']} is not open; no score computed.", file=sys.stderr)
            sys.exit(1)
        if args.route:
            fm = frontmatters.get(matched_item["id"], {})
            signals = compute_route_signals(matched_item, fm, config=config)
            print(format_route_detail(signals, breakdown.total))
            if args.json:
                print(f"JSON: {write_route_json({**signals, 'score': breakdown.total})}")
            return
        if args.explain:
            fm = frontmatters.get(matched_item["id"], {})
            print(format_score_explanation(matched_item["id"], matched_item, breakdown, fm, open_item_ids))
        else:
            print(f"{matched_item['id']}  score {breakdown.total}")
        return

    if args.review:
        print(review_items(items, scores, frontmatters))
        return

    if args.route:
        open_items = sorted(
            [i for i in items if i["status"] in OPEN_STATUSES],
            key=lambda x: (-_score_total(scores.get(x["id"])), x["id"]),
        )
        rows = []
        print(f"Backlog Route Signals ({len(open_items)} open items)")
        print("=" * 60)
        for item in open_items:
            signals = compute_route_signals(item, frontmatters.get(item["id"], {}), config=config)
            score = _score_total(scores.get(item["id"]))
            rows.append({**signals, "score": score})
            print(format_route_line(signals, score))
        print()
        print(ROUTE_LEGEND)
        print("\n(report only — nothing is written)")
        if args.json:
            print(f"JSON: {write_route_json(rows)}")
        return

    print(f"Backlog Priority Scores ({len(scores)} open items)")
    print("=" * 60)

    sorted_items = sorted(
        [i for i in items if i["status"] in OPEN_STATUSES],
        key=lambda x: _score_total(scores.get(x["id"])),
        reverse=True,
    )

    for item in sorted_items:
        score = _score_total(scores.get(item["id"]))
        print(f"  ID {item['id']:>3} | {score:>3} pts | {item['priority']:<6} | {item['feature'][:45]}")

    if scores:
        totals = [b.total for b in scores.values()]
        print(f"\nScore range: {min(totals)} — {max(totals)}")

    if args.dry_run:
        print("\n(dry-run mode — no changes written)")
    else:
        # The index is a generated artifact -- generate_backlog_index.py
        # --write produces it, and nothing here writes a score back into it.
        # Every mode is report-only; this branch is the same report the
        # --dry-run branch prints, worded for the flag that names no writes
        # ever happened in the first place.
        print(
            "\n(report only — scores are not written to the index; "
            "regenerate it with generate_backlog_index.py --write)"
        )


if __name__ == "__main__":
    main()
