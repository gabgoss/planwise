"""Backlog index rendering: escapes and renders each 9-cell item row and
assembles one table body (header, separator, rows).

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import (
    COL_BLOCKS,
    COL_CREATED,
    COL_DOMAIN,
    COL_FILE,
    COL_ID,
    COL_PRIORITY,
    COL_SCORE,
    COL_STATUS,
    COL_TITLE,
    COLUMN_COUNT,
    HEADER_CELLS,
    TITLE_MAX_LEN,
)

_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _escape_cell(text: str) -> str:
    """Escape an unescaped pipe so the cell survives table round-tripping.

    A cell containing a literal `|` -- including one inside a code span,
    e.g. a shell pipeline quoted in a title -- must come back out through
    `split_row_raw` as the same number of cells it went in as. Only the
    presence of a raw pipe triggers the substitution; a pipe-free cell
    returns untouched.
    """
    if "|" not in text:
        return text
    return _UNESCAPED_PIPE_RE.sub(r"\\|", text)


def truncate_title(title: str, max_len: int = TITLE_MAX_LEN):
    """Truncate `title` to `max_len` chars at a word boundary.

    Returns (rendered_title, was_truncated). Truncation happens on the raw
    title, before escaping, so a cut can never land inside an escape
    sequence.
    """
    if len(title) <= max_len:
        return title, False
    cut = title.rfind(" ", 0, max_len + 1)
    if cut <= 0:
        cut = max_len
    return title[:cut].rstrip(), True


def _relative_file_path(path: Path, backlog_dir: Path) -> str:
    try:
        rel = path.relative_to(backlog_dir)
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


def _render_blocks_cell(blocks: list) -> str:
    if not blocks:
        return ""
    return "[" + ", ".join(blocks) + "]"


def _render_file_cell(item_id: str, path: Path, backlog_dir: Path) -> str:
    return f"[{item_id}]({_relative_file_path(path, backlog_dir)})"


def render_row(item: dict, backlog_dir: Path):
    """Render one item's fields into a 9-cell table row.

    Returns (row_text, title_was_truncated). The Score cell reads
    `item["score"]`, which `compute_scores_for_items` must have populated
    before this is called -- a numeric string for an open item, `"-"` for a
    closed one (the score_backlog.py convention this mirrors: a closed item
    is not part of active priority triage). A missing key here means the
    caller forgot that step, so it is read with no default -- a KeyError is
    the correct failure, not a silently blank cell.
    """
    rendered_title, was_truncated = truncate_title(item["title"])
    cells = [""] * COLUMN_COUNT
    cells[COL_ID] = item["id"]
    cells[COL_TITLE] = _escape_cell(rendered_title)
    cells[COL_PRIORITY] = item["priority"]
    cells[COL_STATUS] = item["status"]
    cells[COL_DOMAIN] = item["abbrev"]
    cells[COL_CREATED] = item["created"]
    cells[COL_BLOCKS] = _render_blocks_cell(item["blocks"])
    cells[COL_SCORE] = item["score"]
    cells[COL_FILE] = _render_file_cell(item["id"], item["_path"], backlog_dir)
    assert len(cells) == COLUMN_COUNT
    row = "|" + "|".join(f" {cell} " for cell in cells) + "|"
    return row, was_truncated


def render_header() -> str:
    return "|" + "|".join(f" {cell} " for cell in HEADER_CELLS) + "|"


def render_separator() -> str:
    return "|" + "|".join(["---"] * COLUMN_COUNT) + "|"

def render_table_body(items: list, backlog_dir: Path) -> tuple:
    """Render one table (header + separator + one row per item).

    Returns (body_text, truncated_ids). Reuses `render_header`/`render_row`
    exactly, so a sharded/budgeted table renders byte-identical rows to an
    unsharded run.
    """
    lines = [render_header(), render_separator()]
    truncated_ids = []
    for item in items:
        row, was_truncated = render_row(item, backlog_dir)
        lines.append(row)
        if was_truncated:
            truncated_ids.append(item["id"])
    return "\n".join(lines) + "\n", truncated_ids

