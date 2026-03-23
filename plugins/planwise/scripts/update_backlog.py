#!/usr/bin/env python3
"""Update a backlog item's status in the backlog index markdown.

When status is set to COMPLETE or CLOSED, item files are automatically
moved to the Archive/ directory and index links are updated.
"""

import argparse
import re
import shutil
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
from constants import VALID_STATUSES, ARCHIVE_STATUSES


def update_item_status(content: str, item_id: str, new_status: str) -> tuple[str, str]:
    """Find the row matching item_id and update its status.

    Returns (updated_content, old_status).
    Raises ValueError if item not found.
    """
    lines = content.split("\n")
    target_id_num = item_id.lstrip("0")

    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue

        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue

        if row_id.lstrip("0") == target_id_num:
            old_status = cells[3].strip()

            parts = line.split("|")
            if len(parts) >= 5:
                old_cell = parts[4]
                leading = len(old_cell) - len(old_cell.lstrip())
                trailing = len(old_cell) - len(old_cell.rstrip())
                if trailing == 0:
                    parts[4] = " " * leading + new_status
                else:
                    parts[4] = " " * leading + new_status + " " * trailing

                lines[i] = "|".join(parts)

            return "\n".join(lines), old_status

    raise ValueError(f"Item ID '{item_id}' not found in backlog index.")


def extract_file_links(content: str, item_id: str) -> list[str]:
    """Extract file paths from the Files column of a backlog index row."""
    lines = content.split("\n")
    target_id_num = item_id.lstrip("0")

    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue
        if row_id.lstrip("0") == target_id_num:
            files_cell = cells[6] if len(cells) >= 7 else cells[5]
            return re.findall(r'\]\(([^)]+)\)', files_cell)

    return []


def archive_item_files(
    backlog_dir: Path, archive_dir: Path, filenames: list[str]
) -> list[tuple[str, bool, str]]:
    """Move item files from backlog_dir to archive_dir.

    Returns list of (filename, success, message) tuples.
    """
    archive_dir.mkdir(exist_ok=True, parents=True)

    results = []
    for filename in filenames:
        src = backlog_dir / filename
        dst = archive_dir / filename
        if not src.exists():
            if dst.exists():
                results.append((filename, True, "already in Archive"))
            else:
                results.append((filename, False, "file not found"))
            continue
        try:
            shutil.move(str(src), str(dst))
            results.append((filename, True, "moved to Archive"))
        except Exception as e:
            results.append((filename, False, str(e)))

    return results


def update_index_links_to_archive(content: str, item_id: str) -> str:
    """Update file links in the index row to point to Archive/ subfolder."""
    lines = content.split("\n")
    target_id_num = item_id.lstrip("0")

    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue
        if row_id.lstrip("0") == target_id_num:
            parts = line.split("|")
            files_idx = 7 if len(parts) >= 9 else 6
            if len(parts) > files_idx:
                files_cell = parts[files_idx]
                updated_cell = re.sub(
                    r'\]\((?!Archive/)([^)]+)\)',
                    r'](Archive/\1)',
                    files_cell,
                )
                parts[files_idx] = updated_cell
                lines[i] = "|".join(parts)
            break

    return "\n".join(lines)


def sync_yaml_status(item_file_path: Path, new_status: str) -> bool:
    """Update the status field in the item file's YAML frontmatter."""
    if not item_file_path.exists():
        return False

    content = item_file_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False

    end_idx = content.find("---", 3)
    if end_idx == -1:
        return False

    frontmatter = content[3:end_idx]
    if not re.search(r"^status:\s", frontmatter, re.MULTILINE):
        return False

    updated_fm = re.sub(
        r"^status:\s*.*$",
        f"status: {new_status}",
        frontmatter,
        flags=re.MULTILINE,
    )
    item_file_path.write_text(
        "---" + updated_fm + "---" + content[end_idx + 3 :], encoding="utf-8"
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Update a backlog item's status in the index markdown."
    )
    parser.add_argument("--id", required=True, help="Item ID (e.g., 003)")
    parser.add_argument(
        "--status",
        required=True,
        help=f"New status. Valid: {', '.join(sorted(VALID_STATUSES))}",
    )

    args, _ = parser.parse_known_args()

    if args.status.upper() not in VALID_STATUSES:
        print(
            f"Error: Invalid status '{args.status}'. "
            f"Valid values: {', '.join(sorted(VALID_STATUSES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    new_status = args.status.upper()

    # Load config
    config = load_config(Path(__file__))
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")

    try:
        updated_content, old_status = update_item_status(content, args.id, new_status)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if old_status == new_status:
        print(f"Item {args.id} already has status {new_status}. No change.")
        return

    index_path.write_text(updated_content, encoding="utf-8")
    print(f"Updated item {args.id} status: {old_status} → {new_status}")

    # Sync YAML frontmatter status in item files
    filenames = extract_file_links(updated_content, args.id)
    for filename in filenames:
        item_path = backlog_dir / filename
        if not item_path.exists():
            item_path = archive_dir / filename
        if sync_yaml_status(item_path, new_status):
            print(f"  YAML status synced: {filename}")

    # Archive item files when status is COMPLETE or CLOSED
    if new_status in ARCHIVE_STATUSES:
        filenames = extract_file_links(content, args.id)
        if filenames:
            results = archive_item_files(backlog_dir, archive_dir, filenames)
            for filename, success, message in results:
                prefix = "  +" if success else "  !"
                print(f"{prefix} {filename}: {message}")

            archived_content = index_path.read_text(encoding="utf-8")
            archived_content = update_index_links_to_archive(archived_content, args.id)
            index_path.write_text(archived_content, encoding="utf-8")
            print("  Index links updated to Archive/")


if __name__ == "__main__":
    main()
