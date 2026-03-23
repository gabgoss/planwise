#!/usr/bin/env python3
"""Parse the backlog index markdown and output filtered items."""

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Fix Windows cp1252 stdout encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from constants import CLOSED_STATUSES
from markdown_parser import parse_markdown_table


def _backlog_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a backlog table row into an item dict."""
    if len(cells) < 6:
        return None

    if len(cells) >= 7:
        try:
            score = int(cells[5]) if cells[5] else 0
        except ValueError:
            score = 0
        files_raw = cells[6]
    else:
        score = 0
        files_raw = cells[5]

    file_links = re.findall(r"\[(\d+)\]\(([^)]+)\)", files_raw)
    files = [{"label": label, "path": path} for label, path in file_links]

    return {
        "id": cells[0],
        "feature": cells[1],
        "priority": cells[2],
        "status": cells[3],
        "abbrev": cells[4],
        "score": score,
        "files": files,
    }


def parse_backlog_table(content: str) -> list[dict]:
    """Parse the Backlog Items markdown table into a list of dicts."""
    return parse_markdown_table(content, "## Backlog Items", _backlog_row_processor)


def _dependency_row_processor(cells: list[str], line_number: int, header_info: dict) -> dict | None:
    """Process a dependency table row into a dep dict."""
    if len(cells) < 2:
        return None
    blocker_id = cells[0].zfill(3)
    blocked_raw = cells[1]
    blocked_ids = [b.strip().zfill(3) for b in blocked_raw.split(",")]
    return {
        "blocker_id": blocker_id,
        "blocked_ids": blocked_ids,
    }


def parse_dependencies_table(content: str) -> list[dict]:
    """Parse the Dependencies table from the index.

    Returns list of dicts with keys: blocker_id, blocked_ids (list of str).
    Only parses hard blockers — stops at "Soft dependencies" or next section.
    """
    return parse_markdown_table(
        content, "## Dependencies", _dependency_row_processor,
        stop_before="**Soft dependencies", require_section=False,
    )


def build_blocked_by_map(
    dependencies: list[dict], items: list[dict]
) -> dict[str, list[str]]:
    """Build reverse dependency map: blocked_item_id -> [open blocker IDs]."""
    status_map = {item["id"]: item["status"] for item in items}
    blocked_by: dict[str, list[str]] = {}

    for dep in dependencies:
        blocker = dep["blocker_id"]
        if status_map.get(blocker, "") not in CLOSED_STATUSES:
            for blocked_id in dep["blocked_ids"]:
                blocked_by.setdefault(blocked_id, []).append(blocker)

    return blocked_by


@dataclass
class FilterCriteria:
    """Bundle of filter parameters for backlog item selection."""
    status: str | None = None
    priority: str | None = None
    abbrev: str | None = None
    item_id: str | None = None
    include_closed: bool = False
    show_blocked: bool = False


def filter_items(
    items: list[dict],
    criteria: FilterCriteria,
    blocked_by_map: dict[str, list[str]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Filter items by provided criteria. Returns (selectable_items, blocked_items)."""
    filtered = []
    blocked = []
    for item in items:
        if not criteria.include_closed and item["status"] in CLOSED_STATUSES:
            continue
        if criteria.status and item["status"].upper() != criteria.status.upper():
            continue
        if criteria.priority and item["priority"].lower() != criteria.priority.lower():
            continue
        if criteria.abbrev and item["abbrev"].upper() != criteria.abbrev.upper():
            continue
        if criteria.item_id and item["id"].lstrip("0") != criteria.item_id.lstrip("0"):
            continue

        if blocked_by_map and not criteria.show_blocked:
            if blocked_by_map.get(item["id"]):
                blocked.append(item)
                continue

        filtered.append(item)

    return filtered, blocked


def format_table(items: list[dict], sort_by: str = "score") -> str:
    """Format items as a readable table."""
    if not items:
        return "No items match filters."

    if sort_by == "score":
        items = sorted(items, key=lambda x: (-x.get("score", 0), x["id"]))
    else:
        items = sorted(items, key=lambda x: x["id"])

    id_w = max(len(item["id"]) for item in items)
    id_w = max(id_w, 2)
    feat_w = max(len(item["feature"]) for item in items)
    feat_w = min(max(feat_w, 7), 55)
    pri_w = max(len(item["priority"]) for item in items)
    pri_w = max(pri_w, 8)
    stat_w = max(len(item["status"]) for item in items)
    stat_w = max(stat_w, 6)
    abbr_w = max(len(item["abbrev"]) for item in items)
    abbr_w = max(abbr_w, 6)
    score_w = 5
    files_w = 5

    header = (
        f"{'ID':<{id_w}} | {'Feature':<{feat_w}} | {'Priority':<{pri_w}} | "
        f"{'Status':<{stat_w}} | {'Abbrev':<{abbr_w}} | {'Score':>{score_w}} | {'Files':<{files_w}}"
    )
    separator = (
        f"{'-' * id_w}-+-{'-' * feat_w}-+-{'-' * pri_w}-+-"
        f"{'-' * stat_w}-+-{'-' * abbr_w}-+-{'-' * score_w}-+-{'-' * files_w}"
    )

    lines = [header, separator]

    for item in items:
        feature = item["feature"]
        if len(feature) > 55:
            feature = feature[:52] + "..."
        file_count = str(len(item["files"]))
        score_str = str(item.get("score", 0))

        lines.append(
            f"{item['id']:<{id_w}} | {feature:<{feat_w}} | {item['priority']:<{pri_w}} | "
            f"{item['status']:<{stat_w}} | {item['abbrev']:<{abbr_w}} | {score_str:>{score_w}} | {file_count:<{files_w}}"
        )

    lines.append(f"\n{len(items)} item(s) found.")
    return "\n".join(lines)


def format_blocked_summary(
    blocked_items: list[dict], blocked_by_map: dict[str, list[str]]
) -> str:
    """Format a summary of blocked items with their blockers."""
    if not blocked_items:
        return ""

    lines = ["", "--- Blocked Items (resolve blockers first) ---"]

    for item in sorted(blocked_items, key=lambda x: (-x.get("score", 0), x["id"])):
        blockers = blocked_by_map.get(item["id"], [])
        blocker_str = ", ".join(blockers)
        feature = item["feature"]
        if len(feature) > 45:
            feature = feature[:42] + "..."
        score_str = str(item.get("score", 0))
        lines.append(
            f"  {item['id']} | {feature:<45} | {score_str:>3} pts | blocked by: {blocker_str}"
        )

    lines.append(f"\n{len(blocked_items)} item(s) blocked.")
    return "\n".join(lines)


def write_json(items: list[dict]) -> str:
    """Write items to a JSON temp file and return the path."""
    tmp_dir = tempfile.mkdtemp(prefix="backlog-")
    json_path = os.path.join(tmp_dir, "items.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return json_path


def main():
    parser = argparse.ArgumentParser(
        description="Parse the backlog index and output filtered items."
    )
    parser.add_argument("--status", help="Filter by status (e.g., NOT_STARTED, IN_PROGRESS)")
    parser.add_argument("--priority", help="Filter by priority (e.g., High, Medium, Low)")
    parser.add_argument("--abbrev", help="Filter by abbreviation")
    parser.add_argument("--id", help="Filter by specific item ID (e.g., 003)")
    parser.add_argument("--include-closed", action="store_true", help="Include COMPLETE and CLOSED items")
    parser.add_argument("--show-blocked", action="store_true", help="Include items blocked by open dependencies")
    parser.add_argument("--sort", choices=["score", "id"], default="score", help="Sort order (default: score descending)")

    args, _ = parser.parse_known_args()

    # Load config
    config = load_config(Path(__file__))
    index_path = config["_index_path"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")
    all_items = parse_backlog_table(content)
    dependencies = parse_dependencies_table(content)
    blocked_by_map = build_blocked_by_map(dependencies, all_items)

    criteria = FilterCriteria(
        status=args.status,
        priority=args.priority,
        abbrev=args.abbrev,
        item_id=args.id,
        include_closed=args.include_closed,
        show_blocked=args.show_blocked,
    )
    filtered, blocked = filter_items(all_items, criteria, blocked_by_map)

    print(format_table(filtered, sort_by=args.sort))

    if blocked:
        print(format_blocked_summary(blocked, blocked_by_map))

    if filtered:
        json_path = write_json(filtered)
        print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
