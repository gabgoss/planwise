"""Backlog index file assembly: builds the Archive shard files and the hub,
with its `## Shards` directory and overflow leaves, all in memory.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_budget import (
    HUB_TOKEN_BUDGET,
    MEASUREMENT_BASIS,
    _id_range,
    _shipped_bytes,
    partition_items,
    split_items_to_budget,
)
from backlog_index_schema import (
    _DEFAULT_INDEX_NAMING,
    GeneratorError,
    IndexNaming,
    _footer_line,
    _hub_filename,
    _shard_filename,
)
from read_limits import READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN, estimate_tokens

def _relative_link(from_dir: Path, to_path: Path) -> str:
    rel = os.path.relpath(to_path, start=from_dir)
    return str(rel).replace("\\", "/")


def render_shards_section(shard_files: list) -> str:
    """Render the hub's '## Shards' directory: one row per Archive shard
    file, each linking to it and naming its id range.

    The caller places this AFTER the Backlog Items table (Execution Step
    7): `## ` starts a new section, and `markdown_parser.is_section_boundary`
    ends any table walk on sight of one, so this text must never sit above
    the table or every existing hub reader breaks.
    """
    lines = ["## Shards", "", "| Range | File |", "|---|---|"]
    for entry in shard_files:
        label = f"{entry['min_id']:03d}-{entry['max_id']:03d}"
        lines.append(f"| {label} | [{entry['path']}]({entry['path']}) |")
    return "\n".join(lines) + "\n"


def _budget_fields(num_bytes: int, tokens: int, budget: int) -> dict:
    """The per-file measurement fields every generated-file entry carries:
    the CRLF worst-case byte count, its token estimate, the basis, the
    budget this file was split against, the headroom under that budget,
    and the headline ratio -- how many times over the Read-tool page cap
    covers this file (two decimals). `tokens` is never 0 here: every
    generated file carries at least a wrapper line.
    """
    return {
        "bytes": num_bytes,
        "tokens": tokens,
        "basis": MEASUREMENT_BASIS,
        "budget": budget,
        "headroom": budget - tokens,
        "page_cap_ratio": round(READ_PAGE_CAP_TOKENS / tokens, 2),
    }


def build_shard_files(
    by_century: dict,
    backlog_dir: Path,
    archive_dir: Path,
    naming: IndexNaming,
    budget: int = READ_TOKEN_WARN,
) -> list:
    """Render every closed-item century group as one or more shard files
    under `Archive/`, splitting further only if a single century's table
    itself exceeds `budget` (bounded at 100 rows by construction, so this is
    rare, but not assumed impossible).

    Each shard file backlinks to the hub (bidirectional links, Execution
    Step 6). The backlink line is the wrapper `split_items_to_budget` is
    given a reserve for (Finding F1): without it, the split decision
    measured the bare table body while this function measured body +
    backlink, so a body just under budget could still push the assembled
    file over it, in every mode, with no split ever offered. `naming`
    (Finding F5) names the hub itself and every shard's own filename stem
    from the project's actual configured index path, never a hardcoded
    constant. Returns one dict per file: path (relative to backlog_dir,
    "Archive/..."), content, rows, bytes, tokens, basis, budget, headroom,
    page_cap_ratio, split, min_id, max_id, truncated_ids.
    """
    files = []
    hub_path = backlog_dir / naming.hub_name
    backlink_target = _relative_link(archive_dir, hub_path)
    backlink_line = f"[Back to Backlog Index]({backlink_target})\n\n"
    wrapper_tokens = estimate_tokens(_shipped_bytes(backlink_line))
    for century in sorted(by_century):
        items = by_century[century]
        leaves = split_items_to_budget(items, backlog_dir, wrapper_tokens, budget)
        split = len(leaves) > 1
        for subset, body, _num_bytes, _tokens, truncated in leaves:
            min_id, max_id = _id_range(subset)
            filename = _shard_filename(naming, min_id, max_id)
            # Derived from the SAME `archive_dir` the backlink above already
            # uses, relative to `backlog_dir` -- never a hardcoded "Archive/"
            # prefix (the CR5 residual this closes): with a non-default
            # `archive_dir`, that hardcoded prefix wrote the shard somewhere
            # `_list_disk_generated_files`/`--check` never looks, even though
            # every OTHER path in this module was already config-derived.
            shard_path = _relative_link(backlog_dir, archive_dir / filename)
            content = backlink_line + body
            num_bytes_final = _shipped_bytes(content)
            tokens_final = estimate_tokens(num_bytes_final)
            if tokens_final >= budget:
                # Unreachable on any input the splitter above accepted: the
                # reserve above IS this exact backlink line's token cost, so
                # `split_items_to_budget` already refused (or split further)
                # any body for which body_tokens + wrapper_tokens >= budget
                # -- see its docstring for the ceiling-superadditivity
                # proof. Kept as a defensive assertion, not a live branch:
                # it would only fire if this line's own computation diverged
                # from the reserve computed above.
                raise GeneratorError(
                    f"{shard_path}: adding the backlink line pushed "
                    f"the file to {tokens_final} tokens (basis: "
                    f"{MEASUREMENT_BASIS}), >= the {budget}-token "
                    f"budget despite a {wrapper_tokens}-token reserve at "
                    f"split time -- this should be unreachable; report it "
                    f"as a bug in the reserve calculation, not as an "
                    f"unshardable row"
                )
            files.append({
                "path": shard_path,
                "content": content,
                "rows": len(subset),
                **_budget_fields(num_bytes_final, tokens_final, budget),
                "split": split,
                "min_id": min_id,
                "max_id": max_id,
                "truncated_ids": truncated,
            })
    return files


def _hub_leaf_entries(leaves: list, naming: IndexNaming) -> list:
    """The `## Shards`-directory entries for every hub OVERFLOW leaf
    (index > 0) a split produced -- min_id/max_id/path, the same shape
    `build_shard_files` already produces for an Archive shard, so
    `render_shards_section` needs no special-casing to list both kinds in
    one directory (Finding F4).
    """
    entries = []
    for index, (subset, _body, _num_bytes, _tokens, _truncated) in enumerate(leaves):
        if index == 0 or not subset:
            continue
        min_id, max_id = _id_range(subset)
        entries.append({
            "min_id": min_id,
            "max_id": max_id,
            "path": _hub_filename(naming, min_id, max_id, index),
        })
    return entries


def _generated_line() -> str:
    """Leaf 0's first line. The ISO date is fixed-width, so its byte count
    never depends on which day it renders."""
    today = datetime.now().astimezone().date()
    return f"Generated: {today.isoformat()}\n\n"


def _continuation_wrapper(naming: IndexNaming) -> str:
    """The backlink line every hub overflow leaf opens with."""
    return f"[Back to Backlog Index]({naming.hub_name})\n\n"


def hub_wrapper_tokens(
    shards_section: str, naming: IndexNaming, generated_line: str | None = None
) -> int:
    """The wrapper-token reserve `build_hub_files` gives the splitter: the
    LARGER of leaf 0's wrapper (`Generated:` line + the `## Shards`
    directory + the changelog footer, exactly as leaf 0 is assembled) and
    a continuation leaf's backlink line, measured on the CRLF worst-case
    basis. One definition, so the reserve the splitter is given and the
    wrapper leaf 0 actually ships cannot drift apart.
    """
    if generated_line is None:
        generated_line = _generated_line()
    leaf0_wrapper = generated_line + "\n" + shards_section + "\n" + _footer_line(naming)
    wrapper_bytes = max(
        _shipped_bytes(leaf0_wrapper),
        _shipped_bytes(_continuation_wrapper(naming)),
    )
    return estimate_tokens(wrapper_bytes)


def build_hub_files(
    open_items: list,
    backlog_dir: Path,
    shard_files: list,
    naming: IndexNaming,
    budget: int = HUB_TOKEN_BUDGET,
) -> list:
    """Render the hub as one or more files, splitting by `budget` (the
    hub-family budget, HUB_TOKEN_BUDGET, by default) if the open set alone
    exceeds it -- the open-item count is not bounded by construction.

    Leaf 0 carries the '## Shards' directory (after its table), listing
    BOTH the Archive shards (`shard_files`) AND any hub overflow leaf this
    very split produces (Finding F4) -- without the second half, a
    split-off hub leaf is unreachable from leaf 0, the only file most
    readers ever open, and its rows are silently invisible to anyone who
    never thinks to look for a same-directory sibling file. Any later
    overflow leaf backlinks to leaf 0. Returns entries in the same shape as
    `build_shard_files` (without min_id/max_id, since the hub is one
    logical unit; overflow leaves are still named by id range). `naming`
    (Finding F5) supplies every filename this function produces or links
    to, from the project's actual configured index path.

    The split decision (`split_items_to_budget`) is given a wrapper-token
    reserve (Finding F1, `hub_wrapper_tokens`) sized from the LARGER of
    leaf 0's wrapper (`Generated:` line + the full `## Shards` directory +
    the changelog footer) and a continuation leaf's short backlink line.
    Because the directory also depends on the split's OWN leaf boundaries
    (Finding F4), the directory and the split are iterated to a fixed
    point: the first split runs against the Archive-only directory (a leaf
    cannot list its own overflow siblings before the split that creates
    them exists); each later round rebuilds the directory from the current
    leaves and re-splits against that directory's reserve, until the leaf
    count stops changing.

    Why this converges, and why a stable count is enough: the splitter
    halves at a fixed midpoint, so every possible split lies on one halving
    tree over `open_items`, and a run is fully described by the set of tree
    nodes it splits (leaf count = split nodes + 1). A larger reserve splits
    a superset of the nodes a smaller one split. Each round's leaves refine
    the previous round's. Splitting leaf 0 adds new directory rows.
    Splitting an overflow leaf replaces its one directory row with two or
    more rows over narrower id ranges. The first replacement row keeps the
    old minimum id and the last keeps the old maximum id, and every row
    carries its own framing, so the replacement rows are longer in total
    than the row they replace. The directory therefore never shrinks, and
    neither does the reserve, from round to round. The leaf count is
    therefore non-decreasing and bounded by `len(open_items)`, and two
    rounds with equal counts split the same node set -- identical
    boundaries, so the directory built from the earlier round lists
    exactly the leaves the later round ships. The loop is still bounded
    at `len(open_items) + 1` rounds and raises GeneratorError past that
    bound, and leaf 0's directory is asserted equal to the shipped
    overflow leaves before assembly, so a violated argument refuses
    instead of shipping links to files that do not exist.
    """
    generated_line = _generated_line()
    continuation_wrapper = _continuation_wrapper(naming)
    footer_line = _footer_line(naming)

    def _split(section: str) -> list:
        reserve = hub_wrapper_tokens(section, naming, generated_line)
        return split_items_to_budget(open_items, backlog_dir, reserve, budget)

    leaves = _split(render_shards_section(shard_files))
    max_rounds = len(open_items) + 1
    for _round in range(max_rounds):
        hub_entries = _hub_leaf_entries(leaves, naming)
        shards_section = render_shards_section(shard_files + hub_entries)
        next_leaves = _split(shards_section)
        converged = len(next_leaves) == len(leaves)
        leaves = next_leaves
        if converged:
            break
    else:
        raise GeneratorError(
            f"{naming.hub_name}: the hub directory and its overflow split did "
            f"not reach a stable leaf count within {max_rounds} rounds -- "
            f"report it as a bug in the directory fixed point"
        )
    if hub_entries != _hub_leaf_entries(leaves, naming):
        raise GeneratorError(
            f"{naming.hub_name}: the '## Shards' directory lists overflow "
            f"leaves that differ from the leaves being shipped -- this should "
            f"be unreachable; report it as a bug in the directory fixed point"
        )
    wrapper_tokens = hub_wrapper_tokens(shards_section, naming, generated_line)

    split = len(leaves) > 1
    files = []
    for index, (subset, body, _num_bytes, _tokens, truncated) in enumerate(leaves):
        min_id, max_id = _id_range(subset) if subset else (0, 0)
        filename = _hub_filename(naming, min_id, max_id, index)
        if index == 0:
            # Excluded from every `--check` comparison below (see
            # `generate_backlog_index`'s module docstring carve-outs): it
            # changes every day by construction, never because an item changed,
            # so comparing it would report drift on every single run regardless
            # of the corpus.
            # Footer after `## Shards` (Execution Step 4): never between a
            # table heading and its rows, and only on leaf 0 -- the canonical
            # hub, the changelog's one intended pointer. An overflow leaf
            # carries no `## Shards` directory of its own and needs none.
            content = generated_line + body + "\n" + shards_section + "\n" + footer_line
        else:
            content = continuation_wrapper + body
        num_bytes_final = _shipped_bytes(content)
        tokens_final = estimate_tokens(num_bytes_final)
        if tokens_final >= budget:
            # Unreachable on any input the splitter above accepted, for the
            # same ceiling-superadditivity reason `build_shard_files` states
            # at its own mirror of this raise -- kept as a defensive
            # assertion, never a live branch.
            raise GeneratorError(
                f"{filename}: adding the directory/backlink section pushed "
                f"the file to {tokens_final} tokens (basis: "
                f"{MEASUREMENT_BASIS}), >= the {budget}-token "
                f"budget despite a {wrapper_tokens}-token reserve at split "
                f"time -- this should be unreachable; report it as a bug "
                f"in the reserve calculation, not as an unshardable row"
            )
        files.append({
            "path": filename,
            "content": content,
            "rows": len(subset),
            **_budget_fields(num_bytes_final, tokens_final, budget),
            "split": split,
            "truncated_ids": truncated,
        })
    return files


def build_index_files(
    items: list, backlog_dir: Path, archive_dir: Path, naming: IndexNaming | None = None
) -> dict:
    """Partition, shard, and budget-enforce the full backlog into a hub +
    Archive shard file set, entirely in memory.

    `naming` (Finding F5) is the project's real config-derived naming; it
    defaults to the fallback stem (`_DEFAULT_INDEX_NAMING`) for a bare
    pure-function call with no project config in play (this module's own
    tests call it this way).

    Returns {"files": [...], "truncated_ids": [...]}. Every file entry
    carries the (relative_path, content) pair a later atomic-write stage
    (this task does not write anything to disk) needs, plus the per-file
    measurement report: rows, bytes, tokens, basis, budget, headroom,
    page_cap_ratio, split. Each family is split against its own budget,
    passed explicitly here: READ_TOKEN_WARN for Archive shards and
    HUB_TOKEN_BUDGET for the hub and its overflow leaves.
    """
    naming = naming or _DEFAULT_INDEX_NAMING
    open_items, by_century = partition_items(items)
    shard_files = build_shard_files(
        by_century, backlog_dir, archive_dir, naming, budget=READ_TOKEN_WARN
    )
    hub_files = build_hub_files(
        open_items, backlog_dir, shard_files, naming, budget=HUB_TOKEN_BUDGET
    )

    all_files = hub_files + shard_files
    truncated_ids = []
    for entry in all_files:
        truncated_ids.extend(entry.get("truncated_ids", []))

    return {"files": all_files, "truncated_ids": truncated_ids}

