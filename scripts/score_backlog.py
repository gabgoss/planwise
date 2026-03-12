#!/usr/bin/env python3
"""Compute priority scores for backlog items and write to the index.

Reads the backlog index table, computes a numeric score per open item using
8 weighted factors (configurable via config.yaml), and writes the Score column
back to the index file.

Factors:
  1. Priority        — High/Medium/Low (configurable points)
  2. Bug/Fix keyword — bonus if Feature contains "Bug" or "Fix"
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

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config, get_scoring_weights
from constants import OPEN_STATUSES
from markdown_parser import parse_markdown_table

# Try yaml import; fall back to regex extraction if unavailable
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _score_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a backlog table row for scoring purposes."""
    has_score = header_info["has_score_column"]

    if has_score and len(cells) >= 7:
        return {
            "id": cells[0],
            "feature": cells[1],
            "priority": cells[2],
            "status": cells[3],
            "abbrev": cells[4],
            "score": cells[5],
            "files_raw": cells[6],
            "file_count": len(re.findall(r"\[(\d+)\]\(", cells[6])),
            "line_number": line_number,
        }
    elif len(cells) >= 6:
        return {
            "id": cells[0],
            "feature": cells[1],
            "priority": cells[2],
            "status": cells[3],
            "abbrev": cells[4],
            "score": None,
            "files_raw": cells[5],
            "file_count": len(re.findall(r"\[(\d+)\]\(", cells[5])),
            "line_number": line_number,
        }
    return None


def parse_index_table(content: str) -> list[dict]:
    """Parse the Backlog Items table from the index markdown.

    Returns list of dicts with keys: id, feature, priority, status, abbrev,
    score (str or None), files_raw, file_count, line_number.
    """
    return parse_markdown_table(content, "## Backlog Items", _score_row_processor)


def read_item_frontmatter(filepath: Path) -> dict:
    """Read YAML frontmatter from an item file. Returns dict or empty dict."""
    if not filepath.exists():
        return {}
    content = filepath.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}
    raw = content[3:end]

    if HAS_YAML:
        try:
            return yaml.safe_load(raw) or {}
        except Exception:
            return {}
    else:
        fm = {}
        created_match = re.search(r"^created:\s*(.+)$", raw, re.MULTILINE)
        if created_match:
            fm["created"] = created_match.group(1).strip().strip("'\"")
        blocks_match = re.search(r"^blocks:\s*\[(.+)\]", raw, re.MULTILINE)
        if blocks_match:
            fm["blocks"] = [b.strip().strip("'\"") for b in blocks_match.group(1).split(",")]
        blocks_list = re.findall(r"^  - (.+)$", raw, re.MULTILINE)
        if blocks_list and "blocks" not in fm:
            fm["blocks"] = [b.strip().strip("'\"") for b in blocks_list]
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


def get_first_file_path(item: dict, backlog_dir: Path) -> Path | None:
    """Extract the first file path from the Files column raw string."""
    match = re.search(r"\]\(([^)]+)\)", item["files_raw"])
    if not match:
        return None
    filename = match.group(1)
    return backlog_dir / filename


def compute_score(
    item: dict,
    frontmatter: dict,
    archive_counts: dict[str, int],
    weights: dict,
    open_item_ids: set[str] | None = None,
) -> int:
    """Compute the 8-factor score for a single item."""
    score = 0

    # Factor 1: Priority
    priority_map = {
        "High": weights["priority_high"],
        "Medium": weights["priority_medium"],
        "Low": weights["priority_low"],
    }
    score += priority_map.get(item["priority"], 0)

    # Factor 2: Bug/Fix keyword
    if re.search(r"\b(Bug|Fix)\b", item["feature"], re.IGNORECASE):
        score += weights["bug_fix_bonus"]

    # Factor 3: IN_PROGRESS boost
    if item["status"] == "IN_PROGRESS":
        score += weights["in_progress_bonus"]

    # Factor 4: File count bonus
    if item["file_count"] > 1:
        score += weights["file_count_bonus"] * (item["file_count"] - 1)

    # Factor 5: PLANNING penalty
    if item["status"] == "PLANNING":
        score += weights["planning_penalty"]

    # Factor 6: Blocks count — only count blocks targeting open items
    blocks = frontmatter.get("blocks", [])
    if isinstance(blocks, list):
        if open_item_ids is not None:
            open_blocks = [b_str for b in blocks if (b_str := str(b).zfill(3)) in open_item_ids]
            score += weights["blocks_bonus"] * len(open_blocks)
        else:
            score += weights["blocks_bonus"] * len(blocks)

    # Factor 7: Abbrev momentum
    if archive_counts.get(item["abbrev"], 0) > 0:
        score += weights["momentum_bonus"]

    # Factor 8: Age (weeks since created, capped)
    created = frontmatter.get("created")
    if created:
        try:
            if isinstance(created, date) and not isinstance(created, datetime):
                created_date = created
            elif isinstance(created, datetime):
                created_date = created.date()
            else:
                created_date = datetime.strptime(str(created), "%Y-%m-%d").date()
            weeks = (date.today() - created_date).days // 7
            score += min(weeks * weights["age_bonus_per_week"], weights["age_cap"])
        except (ValueError, TypeError):
            pass

    return score


def write_scores_to_index(content: str, scores: dict[str, int]) -> str:
    """Insert or update Score column in the index table."""
    lines = content.split("\n")
    section_match = re.search(r"## Backlog Items\s*\n", content)
    if not section_match:
        return content

    section_start = content[:section_match.end()].count("\n")
    has_score_column = False
    header_idx = None
    separator_idx = None

    for i in range(section_start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and i > section_start:
            break
        if header_idx is None and re.match(r"\|\s*ID\s*\|", stripped):
            header_idx = i
            has_score_column = "Score" in stripped
        elif header_idx is not None and separator_idx is None and re.match(r"\|[-\s|]+\|", stripped):
            separator_idx = i

    if header_idx is None or separator_idx is None:
        return content

    if not has_score_column:
        hparts = lines[header_idx].split("|")
        hparts.insert(-2, " Score ")
        lines[header_idx] = "|".join(hparts)

        sparts = lines[separator_idx].split("|")
        sparts.insert(-2, "------")
        lines[separator_idx] = "|".join(sparts)

    for i in range(separator_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped.startswith("|"):
            break
        if stripped.startswith("## ") or stripped.startswith("---"):
            break

        parts = lines[i].split("|")
        if len(parts) < 3:
            continue

        row_id = parts[1].strip() if len(parts) > 1 else ""
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue

        status_cell = parts[4].strip() if len(parts) > 4 else ""
        if status_cell in ("COMPLETE", "CLOSED"):
            score_val = "-"
        else:
            score_val = str(scores.get(row_id, 0))

        if has_score_column:
            if len(parts) >= 8:
                parts[6] = f" {score_val} "
                lines[i] = "|".join(parts)
        else:
            if len(parts) >= 7:
                parts.insert(-2, f" {score_val} ")
                lines[i] = "|".join(parts)

    return "\n".join(lines)


def review_items(
    items: list[dict],
    scores: dict[str, int],
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
                    created_date = datetime.strptime(str(created), "%Y-%m-%d").date()
                weeks = (date.today() - created_date).days // 7
                if weeks > 8:
                    score = scores.get(item["id"], 0)
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
        score = scores.get(item["id"], 0)
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
            score = scores.get(item["id"], 0)
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
    parser.add_argument("--dry-run", action="store_true", help="Compute and print scores without writing to the index.")
    parser.add_argument("--review", action="store_true", help="Output a priority review report (no index writes).")

    args = parser.parse_args()

    # Load config
    config = load_config(Path(__file__))
    weights = get_scoring_weights(config)
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")
    items = parse_index_table(content)

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
    scores: dict[str, int] = {}
    for item in items:
        if item["status"] in OPEN_STATUSES:
            fm = frontmatters.get(item["id"], {})
            scores[item["id"]] = compute_score(item, fm, archive_counts, weights, open_item_ids)

    if args.review:
        print(review_items(items, scores, frontmatters))
        return

    print(f"Backlog Priority Scores ({len(scores)} open items)")
    print("=" * 60)

    sorted_items = sorted(
        [i for i in items if i["status"] in OPEN_STATUSES],
        key=lambda x: scores.get(x["id"], 0),
        reverse=True,
    )

    for item in sorted_items:
        score = scores.get(item["id"], 0)
        print(f"  ID {item['id']:>3} | {score:>3} pts | {item['priority']:<6} | {item['feature'][:45]}")

    if scores:
        print(f"\nScore range: {min(scores.values())} — {max(scores.values())}")

    if not args.dry_run:
        updated_content = write_scores_to_index(content, scores)
        index_path.write_text(updated_content, encoding="utf-8")
        print(f"\nScores written to {index_path.name}")
    else:
        print("\n(dry-run mode — no changes written)")


if __name__ == "__main__":
    main()
