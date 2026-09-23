#!/usr/bin/env python3
"""Compute priority scores for backlog items and report them.

Reads the backlog index table and computes a numeric score per open item
using 8 weighted factors (configurable via config.yaml). Every mode is
read-only: the index is a generated artifact produced by
generate_backlog_index.py --write, so this script never writes a score back
into it. `--id N --explain` prints one item's per-factor derivation instead.

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
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import get_scoring_weights, load_config
from constants import OPEN_STATUSES
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from markdown_parser import (
    normalize_id,
    parse_markdown_table,
    warn_on_unparsed_rows,
)

# Try yaml import; fall back to regex extraction if unavailable
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


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


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")

# A trailing ` #...`/`\t#...` YAML inline comment, matched per line. Applied
# only to `id`, `created`, and `blocks` (`_strip_inline_comment`'s callers) --
# these three never legitimately contain a `#`, so stripping it unconditionally
# before any further parsing is safe and needs no quoting-aware lookahead.
_TRAILING_COMMENT_RE = re.compile(r"[ \t]+#.*$")


def _strip_inline_comment(raw: str) -> str:
    """Strip a trailing YAML inline comment from each line of `raw`.

    `parse_frontmatter_map` hands back the key's raw value text verbatim,
    comment included -- unlike `yaml.safe_load`, which strips a YAML comment
    at the tokenizer level regardless of position. Without this, a value
    like ``blocks: [007, 009]  # two`` overlays the octal-safe text-level
    read with ``['007', '009]  # two']`` (the comment swallowed into the
    last list entry), and ``created: 2026-01-15  # filed`` overlays a
    correctly-YAML-parsed date with a string `date.fromisoformat` cannot
    parse, silently zeroing the age factor. Applied line-by-line so a
    block-form multi-line value (each ``- id`` on its own line) strips a
    per-line comment without disturbing sibling lines.
    """
    return "\n".join(_TRAILING_COMMENT_RE.sub("", line) for line in raw.split("\n"))


def _parse_blocks_field(raw: str) -> list:
    """Parse a `blocks:`-shaped value into a list of id strings, as written.

    Handles the flow form (`blocks: [007, 009]`) and the block form spread
    over indented `- ` lines — `parse_frontmatter_map` hands back either
    shape as the key's raw, un-typed value text. Entries are kept exactly as
    authored (no re-padding); scoring and routing already normalize on
    comparison.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [_strip_quotes(part.strip()) for part in inner.split(",") if part.strip()]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_strip_quotes(match.group(1).strip()))
    return items


def _text_level_scoring_fields(raw: str) -> dict:
    """Extract `id`, `created`, and `blocks` from frontmatter text directly,
    bypassing YAML's implicit type resolvers.

    `yaml.safe_load` turns an unquoted zero-padded, all-octal-digit `id:`
    like "061" into the int 49 (YAML 1.1 reads a leading-zero digit string as
    octal), and turns a numeric `blocks:` entry the same way. Reading these
    three fields at the text level via the shared `parse_frontmatter_map` —
    the same primitive `generate_backlog_index.py` already uses for exactly
    this reason — keeps them exactly as the author wrote them. Returns {}
    when `parse_frontmatter_map` cannot attribute the text to any key at all
    (structurally unparseable); a key simply absent from the frontmatter is
    just absent from the result, not an error.
    """
    fm_map = parse_frontmatter_map(raw)
    if fm_map is None:
        return {}
    fields: dict = {}
    if "id" in fm_map:
        candidate = _strip_quotes(_strip_inline_comment(fm_map["id"]).strip())
        if candidate:
            fields["id"] = candidate
    if "created" in fm_map:
        candidate = _strip_quotes(_strip_inline_comment(fm_map["created"]).strip())
        if candidate:
            fields["created"] = candidate
    if "blocks" in fm_map:
        fields["blocks"] = _parse_blocks_field(_strip_inline_comment(fm_map["blocks"]))
    return fields


def read_item_frontmatter(filepath: Path) -> dict:
    """Read YAML frontmatter from an item file. Returns dict or empty dict.

    The split is the shared `frontmatter_parser` primitive; only the file I/O
    and the typed-value parse are this function's own. Absence of any kind —
    a missing file, no frontmatter block, an unterminated one, or a block YAML
    cannot parse — is reported the same way, as an empty dict, because every
    caller here reads scoring inputs off the result and must not have to
    distinguish "no data" from "bad data" mid-scoring.

    `id`, `created`, and `blocks` are overlaid from `_text_level_scoring_fields`
    after the YAML load (or read directly from it when no YAML is available),
    since `yaml.safe_load` mistypes exactly those three — see
    `_text_level_scoring_fields`'s docstring. The overlay costs no second file
    read: `raw` is the same frontmatter text already split out below.

    The item body is retained from this same read and returned under `_body`
    — the whole file is already loaded here and the body was previously
    thrown away; nothing downstream consumes it yet.
    """
    if not filepath.exists():
        return {}
    content = filepath.read_text(encoding="utf-8")
    parts = split_frontmatter_block(content)
    if parts is None:
        return {}
    raw, body = parts

    if HAS_YAML:
        try:
            fm = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            return {}
        if not isinstance(fm, dict):
            # A frontmatter block that is a bare scalar or a list (e.g. a
            # stray "- one\n- two") parses without error but isn't a
            # mapping -- `.update()` on it would raise AttributeError and
            # abort the whole scoring run for one malformed file, against
            # this function's own "reported the same way, as an empty
            # dict" contract.
            return {}
        fm.update(_text_level_scoring_fields(raw))
    else:
        # The fallback reads only the scoring keys `created`/`blocks` — never
        # `id`, which nothing in this no-YAML path has ever read.
        fm = {
            key: value
            for key, value in _text_level_scoring_fields(raw).items()
            if key != "id"
        }

    fm["_body"] = body
    return fm


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
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.yaml; overrides default config search and scoring thresholds.")

    args, _ = parser.parse_known_args()

    # Load config
    config = load_config(Path(__file__))
    weights = get_scoring_weights(config)
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    # Report modes (--dry-run, --review, --id/--explain, and the no-flag
    # report) all read the UNION of the hub and every hub overflow leaf -- an
    # open item living in a leaf must be scored and reported like any hub
    # item.
    items = _read_hub_family_items(index_path, backlog_dir)

    if not items:
        print("No items found in backlog index.", file=sys.stderr)
        sys.exit(1)

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
        if args.explain:
            fm = frontmatters.get(matched_item["id"], {})
            print(format_score_explanation(matched_item["id"], matched_item, breakdown, fm, open_item_ids))
        else:
            print(f"{matched_item['id']}  score {breakdown.total}")
        return

    if args.review:
        print(review_items(items, scores, frontmatters))
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
