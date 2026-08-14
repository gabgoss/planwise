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


def is_section_boundary(stripped: str, *, separator_seen: bool = True) -> bool:
    """True when a stripped line ends the current markdown table's section.

    A blank line is NOT a boundary -- it is whitespace inside the table body.
    """
    if stripped.startswith("## "):
        return True
    return stripped.startswith("---") and separator_seen


_ID_TRAILING_NUM = re.compile(r"(\d+)\s*$")


def normalize_id(raw: str | None) -> str:
    """Canonicalize a backlog ID for equality matching.

    The index ID column and a CLI --id argument may each be written bare
    ("NNN", "0NNN") or prefixed (e.g. "PFX-NNN"). Reduce both forms to the same
    bare, non-zero-padded numeric key so they compare equal. Falls back to the
    zero-stripped string when the value carries no trailing digits, so a
    non-numeric ID scheme still compares consistently with itself.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    m = _ID_TRAILING_NUM.search(s)
    return (m.group(1).lstrip("0") or "0") if m else s.lstrip("0")


def id_number(raw: str) -> int | None:
    """Numeric component of an index ID cell, or None when it carries no digits."""
    n = normalize_id(raw)
    return int(n) if n.isdigit() else None


def infer_predominant_id_form(content: str) -> tuple[str, str]:
    """Infer the Backlog Items index's predominant stored ID form.

    Walks the data rows with the same row filtering ``find_row_by_id`` uses
    (skip non-row lines, the header, and the separator) and counts prefixed
    vs bare ID cells. The majority wins; a tie -- including a genuinely
    empty or unparseable index -- falls back to ``"bare"``, the historical,
    regression-safe default.

    Returns ``(id_format, prefix)``: ``id_format`` is ``"bare"`` or
    ``"prefixed"``; ``prefix`` is the index's own most common alpha prefix
    among the prefixed cells (the text before the trailing numeric
    component that ``normalize_id`` also splits on, e.g. ``"PFX-"``), or
    ``""`` when ``id_format`` is ``"bare"``. A ``"prefixed"`` verdict always
    carries the index's own observed prefix, never an invented one, so a
    caller can hand it straight to ``render_id``.
    """
    bare = prefixed = 0
    prefix_counts: dict[str, int] = {}
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_row_cells(stripped)
        if len(cells) < 6:
            continue
        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue
        m = _ID_TRAILING_NUM.search(row_id)
        cell_prefix = row_id[: m.start()].strip() if m else ""
        if cell_prefix:
            prefixed += 1
            prefix_counts[cell_prefix] = prefix_counts.get(cell_prefix, 0) + 1
        else:
            bare += 1
    if prefixed > bare:
        return "prefixed", max(prefix_counts, key=prefix_counts.get)
    return "bare", ""


def render_id(raw_id: str, id_format: str, prefix: str = "") -> str:
    """Render raw_id in the given stored ID form.

    The numeric component -- via ``id_number``, the same trailing-digit span
    ``normalize_id`` matches -- is zero-padded to 3 digits either way
    (today's convention). When raw_id carries no trailing digits
    (``id_number`` returns None), it is zero-padded as a bare string instead,
    preserving the pre-existing ``args.id.zfill(3)`` behavior for a
    non-numeric ID so the bare-form default stays byte-identical to today's
    output. prefix is attached only when id_format == "prefixed", and only
    ever the caller-supplied, observed prefix -- render_id never invents one.
    """
    raw = str(raw_id).strip()
    n = id_number(raw)
    padded = f"{n:03d}" if n is not None else raw.zfill(3)
    if id_format == "prefixed" and prefix:
        return f"{prefix}{padded}"
    return padded


def find_row_by_id(lines: list[str], item_id: str) -> tuple[int, list[str]] | None:
    """Locate a table row by its ID column, matched on the numeric component.

    Walks an already-split line list (``content.split("\\n")``), skipping
    non-row lines, the header row, and the separator row, and returns the
    index and cell values (the ``split_row_cells`` view) of the first row
    whose ID column matches — or ``None`` if no row matches.

    A caller that needs to write the row back should re-split
    ``lines[index]`` with ``split_row_raw`` rather than mutate the cells
    returned here: the cell view has already unescaped the row for reading,
    which is not the round-trip-safe view a write-back needs.
    """
    target = normalize_id(item_id)
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = split_row_cells(line)
        if len(cells) < 6:
            continue
        row_id = cells[0].strip()
        if row_id in ("ID", "") or re.match(r"^[-]+$", row_id):
            continue
        if normalize_id(row_id) == target:
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
        if is_section_boundary(stripped, separator_seen=separator_seen):
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
