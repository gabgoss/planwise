#!/usr/bin/env python3
"""Generic markdown table parser for backlog index files.

Extracts rows from a markdown table under a given section header,
delegating column interpretation to a caller-supplied processor.
"""

import re
import sys
from typing import Callable


def parse_markdown_table(
    content: str,
    section_header: str,
    row_processor: Callable[[list[str], int, dict], dict | None],
    *,
    stop_before: str | None = None,
    require_section: bool = True,
) -> list:
    """Parse a markdown table under a section header.

    Args:
        content: Full markdown file content.
        section_header: Section to find (e.g., "## Backlog Items").
        row_processor: Called for each data row with (cells, line_number, header_info).
            header_info contains: {"has_score_column": bool, "header_text": str}.
            Return a dict to include the row, or None to skip it.
        stop_before: Stop parsing if this text appears (e.g., "**Soft dependencies").
        require_section: If True, exit with error when section is missing.

    Returns:
        List of dicts returned by row_processor.
    """
    pattern = re.escape(section_header.rstrip()) + r"\s*\n"
    section_match = re.search(pattern, content)
    if not section_match:
        if require_section:
            print(
                f"Error: Could not find '{section_header}' section.",
                file=sys.stderr,
            )
            sys.exit(1)
        return []

    section_content = content[section_match.end():]
    lines = section_content.split("\n")
    lines_before = content[:section_match.end()].count("\n")

    items = []
    header_seen = False
    separator_seen = False
    header_info: dict = {"has_score_column": False, "header_text": ""}

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Stop conditions
        if stop_before and stripped.startswith(stop_before):
            break
        if stripped.startswith("## ") or (stripped.startswith("---") and separator_seen):
            break

        # Header row
        if not header_seen and re.match(r"\|\s*ID\s*\|", stripped):
            header_seen = True
            header_info["has_score_column"] = "Score" in stripped
            header_info["header_text"] = stripped
            continue

        # Separator row
        if header_seen and not separator_seen and re.match(r"\|[-\s|]+\|", stripped):
            separator_seen = True
            continue

        # Data row
        if separator_seen and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            line_number = lines_before + idx

            result = row_processor(cells, line_number, header_info)
            if result is not None:
                items.append(result)

    return items
