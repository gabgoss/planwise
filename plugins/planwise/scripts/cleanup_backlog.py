#!/usr/bin/env python3
"""Clean up backlog index and/or archive directory.

Removes COMPLETE/CLOSED rows from the index table and/or deletes
archived .md files from the Archive/ directory.
"""

import argparse
import re
import sys
from pathlib import Path

# Fix Windows cp1252 stdout/stderr encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from constants import ARCHIVE_STATUSES
from markdown_parser import split_row_cells


def cleanup_index(index_path: Path) -> int:
    """Remove COMPLETE/CLOSED rows from ## Backlog Items table.

    Returns count of removed rows.
    """
    if not index_path.exists():
        print(f"Error: Index file not found: {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")

    section_match = re.search(r"## Backlog Items\s*\n", content)
    if not section_match:
        print("Error: Could not find '## Backlog Items' section.", file=sys.stderr)
        sys.exit(1)

    before = content[:section_match.end()]
    section_content = content[section_match.end():]
    lines = section_content.split("\n")

    kept_lines = []
    removed = 0
    header_seen = False
    separator_seen = False

    for line_idx, line in enumerate(lines):
        stripped = line.strip()

        # Past the table — keep everything after
        if stripped.startswith("## ") or (stripped.startswith("---") and separator_seen):
            kept_lines.append(line)
            kept_lines.extend(lines[line_idx + 1:])
            break

        # Header row
        if not header_seen and re.match(r"\|\s*ID\s*\|", stripped):
            header_seen = True
            kept_lines.append(line)
            continue

        # Separator row
        if header_seen and not separator_seen and re.match(r"\|[-\s|]+\|", stripped):
            separator_seen = True
            kept_lines.append(line)
            continue

        # Data row — check status
        if separator_seen and stripped.startswith("|"):
            cells = split_row_cells(stripped)
            # Status is at index 3 in both 6-col and 7-col formats
            if len(cells) >= 4 and cells[3] in ARCHIVE_STATUSES:
                removed += 1
                continue

        kept_lines.append(line)

    if removed > 0:
        new_content = before + "\n".join(kept_lines)
        index_path.write_text(new_content, encoding="utf-8")

    return removed


def cleanup_archive(archive_dir: Path) -> int:
    """Delete .md files from Archive/ directory.

    Returns count of deleted files.
    """
    if not archive_dir.exists():
        print(f"Archive directory does not exist: {archive_dir}")
        return 0

    deleted = 0
    for f in sorted(archive_dir.glob("*.md")):
        f.unlink()
        deleted += 1

    return deleted


def main():
    parser = argparse.ArgumentParser(
        description="Clean up backlog index and/or archive directory"
    )
    parser.add_argument(
        "--target",
        choices=["index", "archive", "both"],
        required=True,
        help="What to clean up: index (remove COMPLETE/CLOSED rows), "
             "archive (delete files), both (do both)",
    )
    args, _ = parser.parse_known_args()

    config = load_config(Path(__file__))

    if args.target in ("index", "both"):
        count = cleanup_index(config["_index_path"])
        print(f"Removed {count} COMPLETE/CLOSED rows from index")

    if args.target in ("archive", "both"):
        count = cleanup_archive(config["_archive_dir"])
        print(f"Deleted {count} files from Archive/")


if __name__ == "__main__":
    main()
