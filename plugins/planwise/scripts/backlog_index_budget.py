"""Backlog index partition and budget: splits items into the open hub set and
closed century shards, fills Score via `score_backlog.compute_score`, and
splits any table that would exceed its per-file token budget.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_render import render_table_body
from backlog_index_schema import GeneratorError
from config_loader import get_scoring_weights
from read_limits import READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN, estimate_tokens
from score_backlog import compute_score, count_archived_by_abbrev

# --------------------------------------------------------------------------
# Hub/shard partition and budget enforcement
#
# Sharding is the generator's whole size guarantee, not a readability setting:
# every file this module produces MUST measure under its own per-file budget
# before it is ever handed to a writer -- `HUB_TOKEN_BUDGET` for the hub and
# its overflow leaves, `READ_TOKEN_WARN` for an Archive shard. The
# measurement basis is `read_limits`'s own byte-ratio instrument -- the same
# one the Read-tool gate itself uses -- never TOKENS_PER_LINE, which
# under-estimates this dense-table corpus by roughly 28x -- a per-line band
# derived from prose, not from pipe-and-code-heavy single-line table rows.
# The bytes it is fed are the CRLF worst case (`_shipped_bytes`): a Windows
# checkout with `core.autocrlf=true` adds one byte per line to what the Read
# tool loads, so a budget that must hold on every checkout counts that byte
# whatever the line endings of the checkout running the generator.
# --------------------------------------------------------------------------

# Statuses this corpus's config.yaml declares CLOSED (`statuses:` list also
# carries NOT_STARTED, PLANNING, IN_PROGRESS, BLOCKED -- all open). Hub
# membership is decided by this field at run time, never by which directory
# a file happens to sit in and never by a hardcoded open-item count.
CLOSED_STATUSES = frozenset({"COMPLETE", "CLOSED"})

# The hub is the file most readers open first, and its target is a margin
# under the Read-tool page cap, not merely "under the warn threshold": every
# hub-family file (the hub and each overflow leaf) keeps at least
# HUB_HEADROOM_FACTOR x headroom under READ_PAGE_CAP_TOKENS. The budget is
# derived from that target rather than chosen beside it, so the two cannot
# drift apart. Archive shards keep `READ_TOKEN_WARN`, which is shared with
# other consumers and is deliberately not lowered here.
HUB_HEADROOM_FACTOR = 2
HUB_TOKEN_BUDGET = READ_PAGE_CAP_TOKENS // HUB_HEADROOM_FACTOR

# The instrument this measures against, by name, for every report this
# module emits: `read_limits.estimate_tokens` with no model/content override
# resolves to `DEFAULT_BYTES_PER_TOKEN` (2.6 bytes/token) -- the same
# gate-conservative default the Read-tool page-cap gate itself computes
# against, not a per-line band -- applied to the CRLF worst-case byte count.
MEASUREMENT_BASIS = (
    "read_limits.estimate_tokens(bytes) at its default ratio "
    "(model=None -> DEFAULT_BYTES_PER_TOKEN=2.6 bytes/token), where bytes is "
    "the CRLF worst case: UTF-8 bytes plus one per line"
)


def shard_for(item_id) -> int:
    """Return the ID-century shard number: (id - 1) // 100.

    A pure function of the id alone -- no lookup table, no registry has to
    stay in sync with which century a given id belongs to.
    """
    return (int(item_id) - 1) // 100


def is_open_item(item: dict) -> bool:
    """True unless `item["status"]` is one of the corpus's closed states."""
    return item["status"] not in CLOSED_STATUSES


def partition_items(items: list) -> tuple:
    """Split id-sorted `items` into the open (hub) list and closed items
    grouped by `shard_for` century.

    An item moves from hub to shard the moment its status closes; no item
    appears in both, and neither group is derived from which directory the
    item's file happens to live in.
    """
    open_items = []
    by_century: dict = {}
    for item in items:
        if is_open_item(item):
            open_items.append(item)
        else:
            by_century.setdefault(shard_for(item["id"]), []).append(item)
    return open_items, by_century


def compute_scores_for_items(items: list, archive_dir: Path, config: dict) -> None:
    """Fill each item's `score` field in place, via the one scoring
    implementation (`score_backlog.compute_score`) -- never a second copy.

    Feeds it a thin row/frontmatter-shaped adapter built from this module's own
    text-level scanned fields, never `score_backlog.read_item_frontmatter`'s
    YAML-typed load (which mis-types an unquoted all-octal-digit id like `061`
    to the int 49 -- see `backlog_index_scan`'s frontmatter scanner).
    `file_count` is always 1: this schema renders exactly one File link per
    row, unlike the legacy multi-file-per-row Files column `compute_score` was
    written against. `feature` is fed the item's raw, untruncated title -- the
    Bug/Fix keyword factor is a data question, not a rendering one, and
    truncation is display-only.

    A closed item's score is rendered `"-"`, matching score_backlog.py's own
    convention (`_score_row_processor`'s caller never computes one for a
    CLOSED/COMPLETE row): a closed item is not part of active priority
    triage, and computing a perpetually age-drifting number nobody reads
    would manufacture drift with no purpose.
    """
    weights = get_scoring_weights(config)
    archive_counts = count_archived_by_abbrev(archive_dir)
    open_item_ids = {item["id"] for item in items if is_open_item(item)}
    for item in items:
        if not is_open_item(item):
            item["score"] = "-"
            continue
        row_shaped = {
            "priority": item["priority"],
            "feature": item["title"],
            "status": item["status"],
            "file_count": 1,
            "abbrev": item["abbrev"],
        }
        frontmatter_shaped = {
            "blocks": item["blocks"],
            "created": item["created"],
        }
        item["score"] = str(
            compute_score(row_shaped, frontmatter_shaped, archive_counts, weights, open_item_ids).total
        )


def _shipped_bytes(text: str) -> int:
    """The byte count `text` occupies on a CRLF checkout: its UTF-8 bytes
    plus one per `\\n`, because a Windows checkout with `core.autocrlf=true`
    adds one byte per line to what the Read tool actually loads.

    Every render in this module is `\\n`-only internally, so this is exact
    for a CRLF checkout and over-counts an LF checkout by one byte per line
    -- the safe direction. It is deliberately independent of the line
    endings of the checkout running the generator: a `--check` on the other
    convention must compute the same split boundaries, or it would report
    drift that no item caused. Additive over concatenation, like the plain
    UTF-8 length it extends.
    """
    return len(text.encode("utf-8")) + text.count("\n")


def _measure(body: str) -> tuple:
    """Return (num_bytes, tokens) for `body` via MEASUREMENT_BASIS."""
    num_bytes = _shipped_bytes(body)
    tokens = estimate_tokens(num_bytes)
    return num_bytes, tokens


def _id_range(items: list) -> tuple:
    ids = [int(item["id"]) for item in items]
    return min(ids), max(ids)


def split_items_to_budget(
    items: list, backlog_dir: Path, wrapper_tokens: int = 0, budget: int = READ_TOKEN_WARN
) -> list:
    """Recursively split `items` until every rendered table, PLUS the
    wrapper text its caller will assemble around it, is under `budget`
    tokens -- the enforced per-file budget. It defaults to READ_TOKEN_WARN
    (deliberately the warn level, not the 25,000 hard cap, so a produced
    file never even warns); `build_hub_files` passes the tighter
    HUB_TOKEN_BUDGET for the hub family.

    `wrapper_tokens` is a conservative reserve for the bytes/tokens the
    caller adds around this table body before shipping it: leaf 0's
    `Generated:` line plus the full `## Shards` directory (`build_hub_files`),
    a continuation leaf's backlink line, or a shard's backlink line
    (`build_shard_files`). The split decision below measures `body tokens +
    wrapper_tokens` against budget, not the bare body -- matching what will
    actually be assembled and shipped. Defaults to 0 for a caller with no
    wrapper (this module's own tests call this directly as a pure function
    over a bare table). Because `estimate_tokens` rounds up and
    `_shipped_bytes` adds exactly across concatenation (both the UTF-8
    length and the per-line CRLF byte are additive, so the CRLF worst-case
    basis leaves this proof unchanged), `estimate_tokens(body_bytes) +
    estimate_tokens(wrapper_bytes) >= estimate_tokens(body_bytes +
    wrapper_bytes)` always -- so accepting a leaf here on the token SUM is
    never less conservative than measuring the assembled bytes directly,
    which is exactly what makes the post-assembly check in each caller an
    assertion rather than a live branch (see their docstrings).

    Returns a list of leaves, each `(subset, body, num_bytes, tokens,
    truncated_ids)`, all under budget -- `tokens` is the BARE body's count,
    not body+wrapper, matching every existing caller (including this
    module's own tests, which assert `tokens < budget` on the bare body).
    This is the enforcement mechanism: a file that would exceed budget is
    split and re-measured, not shipped with a violation reported.
    Splitting a leaf that is already a single row raises GeneratorError
    naming that row -- the pathological case no split can fix (body alone,
    plus the wrapper reserve, still at or over budget), refused rather than
    shipped over budget.
    """
    body, truncated = render_table_body(items, backlog_dir)
    num_bytes, tokens = _measure(body)
    if tokens + wrapper_tokens < budget:
        return [(items, body, num_bytes, tokens, truncated)]
    if len(items) == 1:
        item = items[0]
        raise GeneratorError(
            f"{item['_path']}: item {item['id']} alone renders to {tokens} "
            f"tokens ({num_bytes} bytes; basis: {MEASUREMENT_BASIS}) plus a "
            f"{wrapper_tokens}-token wrapper reserve -- exceeds the "
            f"{budget}-token budget and cannot be reduced by "
            f"sharding further"
        )
    mid = len(items) // 2
    return (
        split_items_to_budget(items[:mid], backlog_dir, wrapper_tokens, budget)
        + split_items_to_budget(items[mid:], backlog_dir, wrapper_tokens, budget)
    )


