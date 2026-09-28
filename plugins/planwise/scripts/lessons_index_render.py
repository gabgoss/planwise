"""Lessons index render: the 10-cell lesson row, the header and separator, the
counter line and header block, the footer pointers, and the table body. Each
row takes the directory of the generated file it lands in as an explicit
`emit_dir`, so the File cell is a relative link from that file.

Imports `lessons_index_schema` from this generator, plus `generate_backlog_index`
and `parse_lessons`. Imported by `lessons_index_budget` and `lessons_index_build`.
Re-exported unchanged by the `generate_lessons_index` facade.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import (
    _changelog_filename,
    _escape_cell,
    _generated_line,
    _relative_link,
    truncate_title,
)
from lessons_index_schema import (
    COL_CATEGORY,
    COL_DOMAIN,
    COL_FILE,
    COL_ID,
    COL_LANGUAGE,
    COL_SEVERITY,
    COL_SOURCE,
    COL_STATUS,
    COL_TECHNOLOGY,
    COL_TITLE,
    COLUMN_COUNT,
    HEADER_CELLS,
)
from parse_lessons import format_id

# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_file_cell(item_id: int, path: Path, emit_dir: Path) -> str:
    padded = f"{item_id:03d}"
    return f"[{padded}]({_relative_link(emit_dir, path)})"


def render_row(item: dict, emit_dir: Path):
    """Render one lesson's fields into a 10-cell table row.

    Returns (row_text, title_was_truncated). `emit_dir` is the directory
    of the generated file this row is rendered into -- see the
    `generate_lessons_index` module docstring's File-cell section.
    """
    rendered_title, was_truncated = truncate_title(item["title"])
    cells = [""] * COLUMN_COUNT
    cells[COL_ID] = format_id(item["id"])
    cells[COL_TITLE] = _escape_cell(rendered_title)
    cells[COL_CATEGORY] = _escape_cell(item["category"])
    cells[COL_SEVERITY] = _escape_cell(item["severity"])
    cells[COL_LANGUAGE] = _escape_cell(", ".join(item["language"]))
    cells[COL_TECHNOLOGY] = _escape_cell(", ".join(item["technology"]))
    cells[COL_DOMAIN] = _escape_cell(", ".join(item["domain"]))
    cells[COL_SOURCE] = _escape_cell(item["source"])
    cells[COL_STATUS] = _escape_cell(item["status"])
    cells[COL_FILE] = _render_file_cell(item["id"], item["_path"], emit_dir)
    assert len(cells) == COLUMN_COUNT
    row = "|" + "|".join(f" {cell} " for cell in cells) + "|"
    return row, was_truncated


def render_header() -> str:
    return "|" + "|".join(f" {cell} " for cell in HEADER_CELLS) + "|"


def render_separator() -> str:
    return "|" + "|".join(["---"] * COLUMN_COUNT) + "|"


# --------------------------------------------------------------------------
# Header, counter, footer
# --------------------------------------------------------------------------

_PROMOTION_LOG_HUB_RE = re.compile(r"^00-Index-(.+)$")


def _promotion_log_filename(naming) -> str:
    """The one namer for the promotion-log file, the same shape as
    `_changelog_filename`: `00-Index-{X}{suffix}` -> `00-PromotionLog-{X}
    {suffix}`; a hub that does not follow that shape falls back to
    `00-{hub_stem}-PromotionLog{suffix}`.
    """
    match = _PROMOTION_LOG_HUB_RE.match(naming.hub_stem)
    if match:
        return f"00-PromotionLog-{match.group(1)}{naming.suffix}"
    return f"00-{naming.hub_stem}-PromotionLog{naming.suffix}"


def render_counter_line(next_id: int) -> str:
    return f"**Next available ID:** {format_id(next_id)}\n"


def render_header_block(next_id: int) -> str:
    """`_generated_line()`, then the counter line, then a blank line. The
    generated hub carries no `## Master Table` heading -- the table sits
    directly under this block. `next_id` is the derived value from
    `parse_lessons.compute_next_id`, floored (never lowered) against
    whatever counter is already on disk by `_counter_floor` -- the caller
    passes the floored value in, this function never reads a line itself.
    """
    return _generated_line() + render_counter_line(next_id) + "\n"


def _footer_line(naming) -> str:
    """The two fixed footer pointers: a changelog link, then a promotion-
    log link. Neither file is ever written by this generator.
    """
    return (
        f"[Changelog]({_changelog_filename(naming)})\n"
        f"[Promotion Log]({_promotion_log_filename(naming)})\n"
    )


# --------------------------------------------------------------------------
# Table-body rendering (mirrors generate_backlog_index's render_table_body,
# re-written to call this module's own render_row/render_header/
# render_separator instead of the backlog renderer)
# --------------------------------------------------------------------------


def _render_lessons_table_body(items: list, emit_dir: Path) -> tuple:
    """Render `items` into one table body: header, separator, one row per
    item, each through `render_row` (see the `generate_lessons_index` module
    docstring's File-cell section for what `emit_dir` controls). Returns (body_text,
    truncated_ids) -- `truncated_ids` is every id whose Title cell was
    truncated, in canonical `LL-NNN` form, matching what a report entry's
    `truncated_ids` field carries.
    """
    lines = [render_header(), render_separator()]
    truncated_ids = []
    for item in items:
        row, was_truncated = render_row(item, emit_dir)
        lines.append(row)
        if was_truncated:
            truncated_ids.append(format_id(item["id"]))
    return "\n".join(lines) + "\n", truncated_ids
