"""Lessons index generator — hub and shard partition and the per-file token budget."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import MEASUREMENT_BASIS, _measure
from lessons_index_render import _render_lessons_table_body
from lessons_index_schema import HUB_STATUSES, LessonsGeneratorError
from parse_lessons import format_id
from read_limits import READ_TOKEN_WARN

# --------------------------------------------------------------------------
# Membership and partition
# --------------------------------------------------------------------------


def is_hub_lesson(item: dict) -> bool:
    return item["status"] in HUB_STATUSES


def shard_for(lesson_id) -> int:
    """The ID-century shard number: (id - 1) // 100. A pure function of
    the id alone, mirrored from generate_backlog_index's own `shard_for`
    rather than imported (the backlog and lessons partitions key off
    different fields).
    """
    return (int(lesson_id) - 1) // 100


def partition_lessons(items: list) -> tuple:
    """Split id-sorted `items` into the hub list and the non-hub items
    grouped by `shard_for` century. A lesson's directory is never read as
    a routing input; only `status:` decides.
    """
    hub_items = []
    by_century: dict = {}
    for item in items:
        if is_hub_lesson(item):
            hub_items.append(item)
        else:
            by_century.setdefault(shard_for(item["id"]), []).append(item)
    return hub_items, by_century


def detect_location_anomalies(items: list) -> list:
    """A lesson whose directory disagrees with its status: a hub-status
    lesson filed under `Archive/`, or a non-hub-status lesson left at top
    level. Routed by status regardless (see `partition_lessons`); this
    only records the disagreement for a later check to report.
    """
    anomalies = []
    for item in items:
        if is_hub_lesson(item) == item["_in_archive"]:
            anomalies.append({
                "path": item["_path"],
                "status": item["status"],
                "in_archive": item["_in_archive"],
            })
    return anomalies


# --------------------------------------------------------------------------
# Per-file token budget: the splitter with the wrapper reserve
# --------------------------------------------------------------------------


def split_lessons_to_budget(
    items: list, from_dir: Path, wrapper_tokens: int = 0, budget: int = READ_TOKEN_WARN
) -> list:
    """Mirrors generate_backlog_index.split_items_to_budget, re-written to
    render through this module's own `_render_lessons_table_body` (which
    calls `render_row`) instead of the backlog renderer.

    Recursively splits `items` until the rendered table body, PLUS the
    caller's `wrapper_tokens` reserve, is under `budget`: the split
    decision measures body-plus-wrapper, the same quantity the
    shipped file will actually carry, never the bare body alone. A single
    item that alone (plus the wrapper reserve) cannot fit under budget
    raises `LessonsGeneratorError` naming its id -- no file is ever shipped
    over budget. Returns a list of leaves, each `(subset, body, num_bytes,
    tokens, truncated_ids)`; `tokens` is the BARE body's token count, not
    body+wrapper, matching `split_items_to_budget`'s own contract.
    """
    body, truncated = _render_lessons_table_body(items, from_dir)
    num_bytes, tokens = _measure(body)
    if tokens + wrapper_tokens < budget:
        return [(items, body, num_bytes, tokens, truncated)]
    if len(items) == 1:
        item = items[0]
        raise LessonsGeneratorError(
            f"{item['_path']}: lesson {format_id(item['id'])} alone renders "
            f"to {tokens} tokens ({num_bytes} bytes; basis: "
            f"{MEASUREMENT_BASIS}) plus a {wrapper_tokens}-token wrapper "
            f"reserve -- exceeds the {budget}-token budget and cannot be "
            f"reduced by sharding further"
        )
    mid = len(items) // 2
    return (
        split_lessons_to_budget(items[:mid], from_dir, wrapper_tokens, budget)
        + split_lessons_to_budget(items[mid:], from_dir, wrapper_tokens, budget)
    )
