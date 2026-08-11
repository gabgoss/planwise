#!/usr/bin/env python3
"""Update a backlog item's status in the backlog index markdown.

When status is set to COMPLETE or CLOSED, item files are automatically
moved to the Archive/ directory and index links are updated.

With --create, append a brand-new backlog item: write its BLI file from the
backlog-item template (unless the file already exists) and add an index row.
"""

import argparse
import re
import shutil
import sys
from datetime import date
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
from markdown_parser import find_row_by_id, pad_cell, split_row_raw

# A row's raw segments carry one extra leading element — the text before the
# row's opening pipe, normally empty. So the raw index of cell N is N + 1.
# Deriving write positions this way (rather than from a `len(parts) >= K`
# threshold) is what keeps a write aimed at the column it names, whatever the
# row's width.
_RAW_OFFSET = 1
_CELL_STATUS = 3


def _files_cell_index(cells: list[str]) -> int:
    """Return the index of the Files cell — always the row's last cell.

    The index table ships in two widths: 6 columns without a Score, 7 with one.
    Files is the trailing column in both, so the last cell is the answer for
    either width. This is only safe because the row was split on unescaped
    pipes: under a naive split an escaped pipe added a phantom cell and every
    width-based guess landed one column short.
    """
    return len(cells) - 1


def update_item_status(content: str, item_id: str, new_status: str) -> tuple[str, str]:
    """Find the row matching item_id and update its status.

    Returns (updated_content, old_status).
    Raises ValueError if item not found.
    """
    lines = content.split("\n")

    match = find_row_by_id(lines, item_id)
    if match is None:
        raise ValueError(f"Item ID '{item_id}' not found in backlog index.")
    i, cells = match
    old_status = cells[_CELL_STATUS].strip()

    parts = split_row_raw(lines[i])
    status_idx = _CELL_STATUS + _RAW_OFFSET
    if len(parts) > status_idx:
        parts[status_idx] = pad_cell(parts[status_idx], new_status)
        lines[i] = "|".join(parts)

    return "\n".join(lines), old_status


def extract_file_links(content: str, item_id: str) -> list[str]:
    """Extract file paths from the Files column of a backlog index row."""
    lines = content.split("\n")

    match = find_row_by_id(lines, item_id)
    if match is None:
        return []
    _, cells = match
    files_cell = cells[_files_cell_index(cells)]
    return re.findall(r'\]\(([^)]+)\)', files_cell)


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

    match = find_row_by_id(lines, item_id)
    if match is not None:
        i, cells = match
        parts = split_row_raw(lines[i])
        files_idx = _files_cell_index(cells) + _RAW_OFFSET
        if len(parts) > files_idx:
            files_cell = parts[files_idx]
            updated_cell = re.sub(
                r'\]\((?!Archive/)([^)]+)\)',
                r'](Archive/\1)',
                files_cell,
            )
            parts[files_idx] = updated_cell
            lines[i] = "|".join(parts)

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


def reconcile_archival(
    index_path: Path, backlog_dir: Path, archive_dir: Path, item_id: str
) -> bool:
    """Ensure a COMPLETE/CLOSED item's file(s) live in Archive/ and its links point there.

    State-coupled and idempotent: the correct invariant is a property of the
    item's *state* ("a closed item's file lives in Archive/ and its index link
    points there"), not of the *transition* that produced it. This reconcile
    holds that invariant regardless of how the row reached COMPLETE/CLOSED — a
    real transition, a closeout hand-edit, or a no-op re-run — so calling it is
    always safe.

    Reads the index fresh, extracts the row's linked files, moves any still
    outside Archive/ (archive_item_files reports "already in Archive" for ones
    already moved), then repoints any index link not already prefixed Archive/.
    A linked file present in neither location is reported "file not found" — a
    deleted/renamed anomaly is surfaced, never fabricated. Prints only what it
    actually reconciled and writes the index only when a link changed, so a
    second call on an already-archived item changes nothing and stays quiet.

    Returns True when it moved a file or rewrote a link, False otherwise.
    """
    content = index_path.read_text(encoding="utf-8")
    filenames = extract_file_links(content, item_id)
    if not filenames:
        return False

    # Normalize to bare filenames — a link may already read "Archive/BB-...md".
    basenames = [f.rsplit("/", 1)[-1] for f in filenames]

    changed = False
    results = archive_item_files(backlog_dir, archive_dir, basenames)
    for filename, success, message in results:
        if success and message == "moved to Archive":
            changed = True
        prefix = "  +" if success else "  !"
        print(f"{prefix} {filename}: {message}")

    relinked = update_index_links_to_archive(content, item_id)
    if relinked != content:
        index_path.write_text(relinked, encoding="utf-8")
        print("  Index links updated to Archive/")
        changed = True

    return changed


def _row_id_exists(content: str, item_id: str) -> bool:
    """Return True if a Backlog Items row already uses this item ID."""
    return find_row_by_id(content.split("\n"), item_id) is not None


def append_backlog_row(
    content: str,
    item_id: str,
    feature: str,
    priority: str,
    status: str,
    abbrev: str,
    files_cell: str,
    score: str = "-",
) -> str:
    """Append a new row to the '## Backlog Items' table and return updated content."""
    lines = content.split("\n")

    section_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Backlog Items":
            section_idx = i
            break
    if section_idx is None:
        raise ValueError("Could not find '## Backlog Items' section in the index.")

    header_idx = None
    for i in range(section_idx + 1, len(lines)):
        if re.match(r"\|\s*ID\s*\|", lines[i].strip()):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not find the Backlog Items table header.")

    # Header + separator + data rows are a contiguous run of lines starting with '|'.
    last_table_idx = header_idx
    i = header_idx + 1
    while i < len(lines) and lines[i].strip().startswith("|"):
        last_table_idx = i
        i += 1

    new_row = (
        f"| {item_id} | {feature} | {priority} | {status} | "
        f"{abbrev} | {score} | {files_cell} |"
    )
    lines.insert(last_table_idx + 1, new_row)
    return "\n".join(lines)


def _render_bli_file(
    item_id: str,
    feature: str,
    priority: str,
    status: str,
    abbrev: str,
    files_list: list[str],
) -> str:
    """Render a new BLI file body from the backlog-item template structure."""
    stem = files_list[0][:-3] if files_list[0].endswith(".md") else files_list[0]
    today = date.today().isoformat()
    title = feature.replace("\\", "\\\\").replace('"', '\\"')
    related = "\n".join(f"- `{f}`" for f in files_list)
    return (
        "---\n"
        f"id: {item_id}\n"
        f'title: "{title}"\n'
        f"priority: {priority}\n"
        f"status: {status}\n"
        f"abbrev: {abbrev}\n"
        f"created: {today}\n"
        "blocks: []\n"
        "---\n"
        "\n"
        f"# {stem}: {feature}\n"
        "\n"
        f"**Priority:** {priority}\n"
        f"**Status:** {status}\n"
        f"**Domain:** {abbrev}\n"
        "\n"
        "---\n"
        "\n"
        "## Summary\n"
        "\n"
        f"{feature}\n"
        "\n"
        "## Problem\n"
        "\n"
        f"{feature}\n"
        "\n"
        "## Proposed Solution\n"
        "\n"
        "{Describe the approach.}\n"
        "\n"
        "## Acceptance Criteria\n"
        "\n"
        f"- [ ] {feature}\n"
        "\n"
        "## Related\n"
        "\n"
        f"{related}\n"
        "\n"
        "---\n"
        "\n"
        f"*Created: {today}*\n"
    )


def create_backlog_item(args) -> None:
    """Create a new backlog item: write its BLI file (if absent) and append an index row.

    In create mode --status is optional and defaults to NOT_STARTED (the open/not-started
    state) — "Open" is not a member of VALID_STATUSES, and the backlog-item template and
    backlog handler both stamp new items NOT_STARTED, so the file and the index row agree.
    """
    missing = [
        name
        for name, val in (
            ("--id", args.id),
            ("--feature", args.feature),
            ("--priority", args.priority),
            ("--abbrev", args.abbrev),
            ("--files", args.files),
        )
        if not val
    ]
    if missing:
        print(
            f"Error: --create requires {', '.join(missing)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    status = (args.status or "NOT_STARTED").upper()
    if status not in VALID_STATUSES:
        print(
            f"Error: Invalid status '{args.status}'. "
            f"Valid values: {', '.join(sorted(VALID_STATUSES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    item_id = args.id.zfill(3)
    feature = args.feature.strip()
    priority = args.priority
    abbrev = args.abbrev.strip()
    files_list = [f.strip() for f in args.files.split(";") if f.strip()]
    if not files_list:
        print("Error: --files must name at least one file.", file=sys.stderr)
        sys.exit(1)

    config = load_config(Path(__file__))
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    content = index_path.read_text(encoding="utf-8")

    if _row_id_exists(content, item_id):
        print(
            f"Error: Item ID '{item_id}' already exists in the backlog index.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Write the BLI file from the template — never clobber a richer file the
    # handler may have already created in its Phase 7.3 flow.
    bli_path = backlog_dir / files_list[0]
    if bli_path.exists():
        print(f"  BLI file already exists, not overwriting: {bli_path.name}")
    else:
        bli_path.parent.mkdir(parents=True, exist_ok=True)
        bli_path.write_text(
            _render_bli_file(item_id, feature, priority, status, abbrev, files_list),
            encoding="utf-8",
        )
        print(f"  Created BLI file: {bli_path.name}")

    files_cell = " ".join(f"[{i + 1:02d}]({f})" for i, f in enumerate(files_list))
    updated_content = append_backlog_row(
        content, item_id, feature, priority, status, abbrev, files_cell
    )
    index_path.write_text(updated_content, encoding="utf-8")
    print(f"Created backlog item {item_id}: {feature} [{priority}/{status}/{abbrev}]")


def main():
    parser = argparse.ArgumentParser(
        description="Update a backlog item's status in the index markdown."
    )
    parser.add_argument("--id", required=True, help="Item ID (e.g., 003)")
    parser.add_argument(
        "--status",
        required=False,
        help=(
            f"New status. Valid: {', '.join(sorted(VALID_STATUSES))}. "
            "Required for a status update; in --create mode it is optional "
            "and defaults to NOT_STARTED."
        ),
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new backlog item (write its BLI file + append an index row) instead of updating an existing item's status.",
    )
    parser.add_argument("--feature", help="Feature / recommendation summary (required when --create).")
    parser.add_argument(
        "--priority",
        choices=["High", "Medium", "Low"],
        help="Priority (required when --create).",
    )
    parser.add_argument("--abbrev", help="Domain abbreviation (required when --create).")
    parser.add_argument(
        "--files",
        help="Affected files, semicolon-separated; the first is the new BLI file written from the template (required when --create).",
    )

    args, _ = parser.parse_known_args()

    # --create takes a fully separate path: build a new item rather than update one.
    if args.create:
        create_backlog_item(args)
        return

    if not args.status:
        print(
            "Error: --status is required (unless --create is used).",
            file=sys.stderr,
        )
        sys.exit(1)

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
        # The status write is a true no-op, but archival is state-coupled, not
        # transition-coupled: an item whose row is ALREADY COMPLETE/CLOSED may
        # still have its file stranded outside Archive/ (e.g. a closeout that
        # hand-edited the row without going through this script). Reconcile the
        # archival location/link even on a no-op status change so the invariant
        # holds by state — this is precisely the reconciliation call an operator
        # reaches for, and it used to hit the early-return and no-op. The status
        # cell and frontmatter are left untouched; only the file location + link
        # are healed.
        if new_status in ARCHIVE_STATUSES:
            reconcile_archival(index_path, backlog_dir, archive_dir, args.id)
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

    # Archive item files when status is COMPLETE or CLOSED — same idempotent
    # state-coupled reconcile used on the no-op path above.
    if new_status in ARCHIVE_STATUSES:
        reconcile_archival(index_path, backlog_dir, archive_dir, args.id)


if __name__ == "__main__":
    main()
