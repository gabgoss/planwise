"""Lessons index build: assembly of the hub file with its overflow leaves and of
the Archive shard files, including the wrapper-token reserve and the fixed-point
loop that sizes the `## Shards` directory against the split.

Imports `lessons_index_budget`, `lessons_index_render`, and `lessons_index_schema`
from this generator, plus `generate_backlog_index` and `read_limits`. Imported by
`lessons_index_run`. Re-exported unchanged by the `generate_lessons_index`
facade.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import (
    HUB_TOKEN_BUDGET,
    MEASUREMENT_BASIS,
    _budget_fields,
    _hub_filename,
    _hub_leaf_entries,
    _id_range,
    _measure,
    _relative_link,
    _shard_filename,
    _shipped_bytes,
    render_shards_section,
)
from lessons_index_budget import partition_lessons, split_lessons_to_budget
from lessons_index_render import _footer_line, render_header_block
from lessons_index_schema import LessonsGeneratorError
from read_limits import READ_TOKEN_WARN, estimate_tokens

# --------------------------------------------------------------------------
# Hub and shard file assembly
# --------------------------------------------------------------------------


def _hub_continuation_wrapper(naming) -> str:
    """The backlink line every hub overflow leaf opens with."""
    return f"[Back to Lessons Index]({naming.hub_name})\n\n"


def hub_wrapper_tokens(
    shards_section: str, naming, next_id: int, header_block: str | None = None
) -> int:
    """Mirrors generate_backlog_index.hub_wrapper_tokens -- re-written
    because its signature does not fit the lessons wrapper: the lessons
    header block carries a computed counter line (`render_header_block`)
    that backlog's bare `Generated:` line does not, and the footer
    is two fixed pointers (Changelog, Promotion Log) rather than backlog's
    one. Same shape otherwise: the LARGER of leaf 0's full wrapper (header
    block + the '## Shards' directory + the footer) and a continuation
    leaf's backlink line, on the CRLF worst-case basis -- one definition,
    so the reserve the splitter is given and the wrapper leaf 0 actually
    ships cannot drift apart.
    """
    if header_block is None:
        header_block = render_header_block(next_id)
    leaf0_wrapper = header_block + "\n" + shards_section + "\n" + _footer_line(naming)
    wrapper_bytes = max(
        _shipped_bytes(leaf0_wrapper),
        _shipped_bytes(_hub_continuation_wrapper(naming)),
    )
    return estimate_tokens(wrapper_bytes)


def build_lessons_hub_files(
    hub_items: list, lessons_dir: Path, shard_entries: list, naming, next_id: int,
    budget: int = HUB_TOKEN_BUDGET,
) -> list:
    """Mirrors generate_backlog_index.build_hub_files, re-written to render
    through `lessons_index_budget.split_lessons_to_budget` and the
    `lessons_index_render` renderer, and to carry the lessons
    header block and two-pointer footer instead of backlog's.

    Leaf 0 carries the header block (`render_header_block`), the
    table, the '## Shards' directory (Archive shards plus every hub
    overflow leaf this split produces), and the two footer pointers. The
    directory's size depends on the split's own leaf boundaries, and the
    split depends on the directory's size (via the wrapper reserve), so the
    two are iterated to a fixed point exactly as `build_hub_files` does --
    see its docstring for why this converges and why a stable leaf count is
    enough to trust it. After convergence: the completeness assertion
    (every hub item appears in exactly one leaf, no item lost or
    duplicated) is a raise, not a warning, and the post-assembly
    `_measure(assembled_leaf) < budget` check on every leaf is a can't-fire
    assertion when the reserve above was computed correctly -- kept as a
    raise all the same.

    `next_id` is threaded through explicitly (not in the pinned signature
    below) because the header block's counter line needs it and nothing
    else in this call graph computes it.
    """
    header_block = render_header_block(next_id)
    continuation_wrapper = _hub_continuation_wrapper(naming)
    footer_line = _footer_line(naming)

    def _split(section: str) -> list:
        reserve = hub_wrapper_tokens(section, naming, next_id, header_block)
        return split_lessons_to_budget(hub_items, lessons_dir, reserve, budget)

    leaves = _split(render_shards_section(shard_entries))
    max_rounds = len(hub_items) + 1
    for _round in range(max_rounds):
        leaf_entries = _hub_leaf_entries(leaves, naming)
        shards_section = render_shards_section(shard_entries + leaf_entries)
        next_leaves = _split(shards_section)
        converged = len(next_leaves) == len(leaves)
        leaves = next_leaves
        if converged:
            break
    else:
        raise LessonsGeneratorError(
            f"{naming.hub_name}: the hub directory and its overflow split "
            f"did not reach a stable leaf count within {max_rounds} rounds "
            f"-- report it as a bug in the directory fixed point"
        )
    if leaf_entries != _hub_leaf_entries(leaves, naming):
        raise LessonsGeneratorError(
            f"{naming.hub_name}: the '## Shards' directory lists overflow "
            f"leaves that differ from the leaves being shipped -- this "
            f"should be unreachable; report it as a bug in the directory "
            f"fixed point"
        )

    # Completeness: every hub item appears in exactly one leaf.
    covered_ids = []
    for subset, *_rest in leaves:
        covered_ids.extend(item["id"] for item in subset)
    expected_ids = [item["id"] for item in hub_items]
    if sorted(covered_ids) != sorted(expected_ids):
        raise LessonsGeneratorError(
            f"{naming.hub_name}: hub split lost or duplicated items -- "
            f"expected {sorted(expected_ids)}, covered {sorted(covered_ids)}"
        )

    split = len(leaves) > 1
    files = []
    for index, (subset, body, _num_bytes, _tokens, truncated) in enumerate(leaves):
        min_id, max_id = _id_range(subset) if subset else (0, 0)
        filename = _hub_filename(naming, min_id, max_id, index)
        if index == 0:
            content = header_block + body + "\n" + shards_section + "\n" + footer_line
        else:
            content = continuation_wrapper + body
        num_bytes_final, tokens_final = _measure(content)
        if tokens_final >= budget:
            # Can't-fire assertion: unreachable on any input the
            # splitter above accepted, because the reserve given to it was
            # this exact wrapper's token cost.
            raise LessonsGeneratorError(
                f"{filename}: adding the directory/footer section pushed "
                f"the file to {tokens_final} tokens (basis: "
                f"{MEASUREMENT_BASIS}), >= the {budget}-token budget "
                f"despite a wrapper reserve computed at split time -- this "
                f"should be unreachable; report it as a bug in the reserve "
                f"calculation, not as an unshardable row"
            )
        files.append({
            "path": filename,
            "content": content,
            "rows": len(subset),
            "kind": "hub" if index == 0 else "hub-leaf",
            **_budget_fields(num_bytes_final, tokens_final, budget),
            "split": split,
            "min_id": min_id,
            "max_id": max_id,
            "truncated_ids": truncated,
        })
    return files


def build_lessons_shard_files(
    by_century: dict, lessons_dir: Path, archive_dir: Path, naming,
    budget: int = READ_TOKEN_WARN,
) -> list:
    """Mirrors generate_backlog_index.build_shard_files: one Archive-century
    file per group, split further only if a single century's table itself
    exceeds `budget`. Each shard opens with a backlink to the hub, derived
    from `naming` (never hardcoded), and rows render with `archive_dir` as
    their `emit_dir` -- see the `generate_lessons_index` module docstring's
    File-cell section: a shard row's File link differs from the same lesson's hub-row link.
    """
    files = []
    hub_path = lessons_dir / naming.hub_name
    backlink_target = _relative_link(archive_dir, hub_path)
    backlink_line = f"[Back to Lessons Index]({backlink_target})\n\n"
    wrapper_tokens = estimate_tokens(_shipped_bytes(backlink_line))
    for century in sorted(by_century):
        items = by_century[century]
        leaves = split_lessons_to_budget(items, archive_dir, wrapper_tokens, budget)
        split = len(leaves) > 1
        for subset, body, _num_bytes, _tokens, truncated in leaves:
            min_id, max_id = _id_range(subset)
            filename = _shard_filename(naming, min_id, max_id)
            shard_path = _relative_link(lessons_dir, archive_dir / filename)
            content = backlink_line + body
            num_bytes_final, tokens_final = _measure(content)
            if tokens_final >= budget:
                raise LessonsGeneratorError(
                    f"{shard_path}: adding the backlink line pushed the "
                    f"file to {tokens_final} tokens (basis: "
                    f"{MEASUREMENT_BASIS}), >= the {budget}-token budget "
                    f"despite a {wrapper_tokens}-token reserve at split "
                    f"time -- this should be unreachable; report it as a "
                    f"bug in the reserve calculation, not as an "
                    f"unshardable row"
                )
            files.append({
                "path": shard_path,
                "content": content,
                "rows": len(subset),
                "kind": "shard",
                **_budget_fields(num_bytes_final, tokens_final, budget),
                "split": split,
                "min_id": min_id,
                "max_id": max_id,
                "truncated_ids": truncated,
            })
    return files


def build_lessons_index_files(
    items: list, lessons_dir: Path, archive_dir: Path, naming, next_id: int
) -> dict:
    """Mirrors generate_backlog_index.build_index_files: partition, shard,
    and budget-enforce the full lessons set into a hub(+overflow) plus
    Archive-shard file set, entirely in memory. Each family is split
    against its own budget: READ_TOKEN_WARN for Archive shards,
    HUB_TOKEN_BUDGET for the hub and its overflow leaves.
    """
    hub_items, by_century = partition_lessons(items)
    shard_files = build_lessons_shard_files(
        by_century, lessons_dir, archive_dir, naming, budget=READ_TOKEN_WARN
    )
    hub_files = build_lessons_hub_files(
        hub_items, lessons_dir, shard_files, naming, next_id, budget=HUB_TOKEN_BUDGET
    )
    all_files = hub_files + shard_files
    truncated_ids = []
    for entry in all_files:
        truncated_ids.extend(entry.get("truncated_ids", []))
    return {"files": all_files, "truncated_ids": truncated_ids}
