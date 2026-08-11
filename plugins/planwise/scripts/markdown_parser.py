#!/usr/bin/env python3
"""Generic markdown table parser for backlog index files.

Extracts rows from a markdown table under a given section header,
delegating column interpretation to a caller-supplied processor.
"""

import re
import sys
from typing import Callable

# Matches a pipe that is NOT preceded by a backslash. A cell may legitimately
# contain an escaped pipe — `` `git diff --name-only \| grep dir` `` is the
# correct way to write a shell pipeline inside a markdown table cell — and a
# naive split on that pipe shifts every subsequent column right by one.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def split_row_raw(line: str) -> list[str]:
    """Split a table row on unescaped pipes, preserving each segment verbatim.

    Escapes and surrounding whitespace are left untouched, so
    ``"|".join(split_row_raw(line)) == line`` for every line. This is the view
    write-back loops need: they mutate one segment and rebuild the row, and any
    unescaping here would silently rewrite the author's markdown.

    Includes the empty leading/trailing segments produced by the row's edge
    pipes, matching the shape of a plain ``line.split("|")``.
    """
    return _UNESCAPED_PIPE_RE.split(line)


def split_row_cells(line: str) -> list[str]:
    """Split a table row into its logical cell values.

    Drops the edge pipes, unescapes ``\\|`` back to ``|``, and strips
    surrounding whitespace. This is the view readers need: the cell value as the
    author meant it, with escaping an artifact of the table format rather than
    part of the data.
    """
    stripped = line.strip()
    segments = _UNESCAPED_PIPE_RE.split(stripped)
    # Drop the empty segments contributed by leading/trailing pipes only —
    # mirroring str.strip("|") without eating a genuinely empty first/last cell
    # in an unfenced row.
    if segments and stripped.startswith("|"):
        segments = segments[1:]
    if segments and stripped.endswith("|") and not stripped.endswith("\\|"):
        segments = segments[:-1]
    return [seg.replace("\\|", "|").strip() for seg in segments]


def count_cells(line: str) -> int:
    """Return the number of logical cells in a table row."""
    return len(split_row_cells(line))


def find_row_by_id(lines: list[str], item_id: str) -> tuple[int, list[str]] | None:
    """Locate a table row by its ID column, matched with leading zeros stripped.

    Walks an already-split line list (``content.split("\\n")``), skipping
    non-row lines, the header row, and the separator row, and returns the
    index and cell values (the ``split_row_cells`` view) of the first row
    whose ID column matches — or ``None`` if no row matches.

    A caller that needs to write the row back should re-split
    ``lines[index]`` with ``split_row_raw`` rather than mutate the cells
    returned here: the cell view has already unescaped the row for reading,
    which is not the round-trip-safe view a write-back needs.
    """
    target = item_id.lstrip("0")
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = split_row_cells(line)
        if len(cells) < 6:
            continue
        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue
        if row_id.lstrip("0") == target:
            return i, cells
    return None


def pad_cell(old_cell: str, new_value: str) -> str:
    """Replace a table cell's value while preserving its surrounding whitespace padding."""
    leading = len(old_cell) - len(old_cell.lstrip())
    trailing = len(old_cell) - len(old_cell.rstrip())
    if trailing == 0:
        return " " * leading + new_value
    return " " * leading + new_value + " " * trailing


def warn_on_unparsed_rows(stats: dict, table_name: str) -> int:
    """Report rows that were present in the table but did not survive parsing.

    Returns the number of malformed rows. Callers that print a count of items
    ("N open items") should treat a non-zero return as meaning their headline is
    a floor, not a total — the whole point of the check is that a short answer
    must not look like a complete one.
    """
    malformed = stats.get("rows_malformed", 0)
    if not malformed:
        return 0

    present = stats.get("rows_present", 0)
    parsed = stats.get("rows_parsed", 0)
    print(
        f"Warning: {malformed} of {present} row(s) in '{table_name}' could not be "
        f"parsed and are NOT included in the {parsed} row(s) reported below. "
        f"Counts derived from this table are incomplete until the row(s) above "
        f"are corrected.",
        file=sys.stderr,
    )
    return malformed


def parse_markdown_table(
    content: str,
    section_header: str,
    row_processor: Callable[[list[str], int, dict], dict | None],
    *,
    stop_before: str | None = None,
    require_section: bool = True,
    stats: dict | None = None,
    strict: bool = False,
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
        stats: Optional dict, populated in place so the caller can compare the
            rows it received against the rows actually present in the table:
            {"rows_present", "rows_parsed", "rows_skipped", "rows_malformed",
             "malformed"}. A caller that reports "N items" MUST derive N from a
            table whose rows_malformed is 0 — otherwise a short answer is
            indistinguishable from a complete one.
        strict: If True, a row whose cell count differs from the header's exits
            with an error instead of warning and skipping it.

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
    header_info: dict = {"has_score_column": False, "header_text": "", "cell_count": 0}
    rows_present = 0
    rows_skipped = 0
    malformed: list[dict] = []

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
            header_info["cell_count"] = count_cells(stripped)
            continue

        # Separator row
        if header_seen and not separator_seen and re.match(r"\|[-\s|]+\|", stripped):
            separator_seen = True
            continue

        # Data row
        if separator_seen and stripped.startswith("|"):
            rows_present += 1
            cells = split_row_cells(stripped)
            line_number = lines_before + idx

            # A row whose cell count differs from the header's is misaligned:
            # every cell past the divergence means something other than what the
            # row processor will read it as. Never hand shifted cells onward.
            expected = header_info["cell_count"]
            if expected and len(cells) != expected:
                detail = {
                    "line_number": line_number,
                    "expected": expected,
                    "found": len(cells),
                    "text": stripped,
                }
                malformed.append(detail)
                message = (
                    f"Error: malformed table row at line {line_number + 1}: "
                    f"expected {expected} cells, found {len(cells)}.\n"
                    f"  {stripped}"
                )
                if strict:
                    print(message, file=sys.stderr)
                    sys.exit(1)
                print(f"Warning: {message[len('Error: '):]}", file=sys.stderr)
                continue

            result = row_processor(cells, line_number, header_info)
            if result is not None:
                items.append(result)
            else:
                rows_skipped += 1

    if stats is not None:
        stats.update(
            {
                "rows_present": rows_present,
                "rows_parsed": len(items),
                "rows_skipped": rows_skipped,
                "rows_malformed": len(malformed),
                "malformed": malformed,
            }
        )

    return items
