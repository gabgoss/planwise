#!/usr/bin/env python3
"""Backlog-index generator tests: rendering, sharding and the token budget.

These tests pin: the column-position contracts that existing scripts key off;
an escaped-pipe title round-tripping through rendering; `shard_for` as a pure
function with no lookup table; the three budget-enforcer paths (fits,
must-split, refuses rather than ships an over-budget row); the hub-family
budget (half the Read-tool page cap); the CRLF worst-case byte basis; leaf
0's directory listing exactly the overflow leaves shipped; the `budget` /
`page_cap_ratio` fields in both the JSON and the printed report; and the
Score factor that ranks a `BUG` item above a non-bug item.

Split from `test_generate_backlog_index.py`, whose docstring maps every moved
class to its file.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index_budget.py
"""

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import read_limits
from generate_backlog_index_fixtures import (
    _PURE_BACKLOG_DIR,
    _GeneratorFixtureBase,
    _make_item,
)
from markdown_parser import split_row_cells, split_row_raw


def _one_shard_shards_section():
    """The `## Shards` directory a single closed item (id 990, its own
    century) produces -- a one-row directory, matching Finding F1's probe
    J shape and this session's live-corpus overhead order of magnitude."""
    return gbi.render_shards_section([
        {"min_id": 990, "max_id": 990, "path": "Archive/Index-Backlog-990-990.md"},
    ])


def _hub_wrapper_tokens(shards_section):
    """Call build_hub_files' own wrapper-reserve computation, so the
    boundary window this module's tests target is the SAME window the
    production function computes. An earlier local replica omitted the
    changelog footer line that production includes; calling production
    removes that drift instead of re-deriving an approximation."""
    return gbi.hub_wrapper_tokens(shards_section, gbi._DEFAULT_INDEX_NAMING)


def _boundary_open_items(variable_blocks_len):
    """79 minimal open items (ids 001-079) plus one (id 080) carrying a
    `blocks` list long enough to push the body toward the split boundary.
    Every entry names item 990 -- a KNOWN but CLOSED id, so it resolves
    (no dangling-blocks abort) and contributes nothing to the blocks-count
    scoring factor (that factor only counts entries targeting an OPEN
    item), keeping the row's size the only thing this list inflates."""
    items = [_make_item(i, status="NOT_STARTED") for i in range(1, 80)]
    items.append(
        _make_item(80, status="NOT_STARTED", blocks=["990"] * variable_blocks_len)
    )
    return items


def _body_tokens_for(variable_blocks_len):
    items = _boundary_open_items(variable_blocks_len)
    body, _truncated = gbi.render_table_body(items, _PURE_BACKLOG_DIR)
    _num_bytes, tokens = gbi._measure(body)
    return tokens


def _find_boundary_blocks_len(target_low, target_high):
    """Binary-search the smallest `variable_blocks_len` whose body tokens
    reach the WINDOW's midpoint -- not its bare minimum -- so the fixture
    keeps buffer against small overhead differences (e.g. a computed
    Score's digit width) between this pure in-memory measurement and the
    real CLI reproduction built from the same recipe."""
    target = target_low + (target_high - target_low) // 2
    lo, hi = 0, 400000
    assert _body_tokens_for(lo) < target_low
    assert _body_tokens_for(hi) >= target_high
    while lo < hi:
        mid = (lo + hi) // 2
        if _body_tokens_for(mid) < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _hub_splitting_items(row_count=200, blocks_per_row=500):
    """200 open items, each with a 500-entry `blocks` list (every entry
    naming item 990 -- a known CLOSED id, so each entry resolves and
    contributes nothing to the blocks-count scoring factor, which only
    counts entries targeting an OPEN item) -- dense enough in aggregate to
    force a multi-leaf hub split (case (b)'s density), while no SINGLE row
    is anywhere close to budget alone, so no unsplittable-row refusal is
    at risk of firing instead of the split this is meant to force.
    """
    blocks = ["990"] * blocks_per_row
    return [_make_item(i, status="NOT_STARTED", blocks=blocks) for i in range(1, row_count + 1)]


class TestColumnPositionContract(unittest.TestCase):
    """Three existing scripts read this table by cell position: Status at
    a literal index 3, Score second-to-last, File last. Pinned both as
    module constants and as the actual runtime placement render_row
    produces -- a regression in the constant and a regression in the
    assignment are two different failure modes, and only the second is
    invisible to the module's own import-time asserts."""

    def test_module_level_constants(self):
        self.assertEqual(gbi.COL_STATUS, 3)
        self.assertEqual(gbi.COL_SCORE, gbi.COLUMN_COUNT - 2)
        self.assertEqual(gbi.COL_FILE, gbi.COLUMN_COUNT - 1)

    def test_render_row_places_status_priority_score_file_at_contract_positions(self):
        item = _make_item(1, title="Sample", priority="High", status="IN_PROGRESS", score="42")
        row, _was_truncated = gbi.render_row(item, _PURE_BACKLOG_DIR)
        cells = split_row_cells(row)

        self.assertEqual(len(cells), gbi.COLUMN_COUNT)
        self.assertEqual(cells[3], "IN_PROGRESS")
        self.assertEqual(cells[-2], "42")
        self.assertIn("BB-001-01-BUG-Fixture.md", cells[-1])


class TestEscapedPipeRoundTrip(unittest.TestCase):
    """A `|` inside a title (e.g. quoting a shell pipeline in a code span)
    must round-trip through rendering without shifting every later column
    -- the BB-070 defect class this generator exists to end."""

    RAW_TITLE = r"Run `git diff --name-only | grep dir` first"

    def test_pipe_is_escaped_and_cell_count_matches_header(self):
        item = _make_item(2, title=self.RAW_TITLE, abbrev="INFRA", status="NOT_STARTED")
        row, _was_truncated = gbi.render_row(item, _PURE_BACKLOG_DIR)

        # The raw pipe survives rendering only via escaping -- an
        # unescaped cell would silently shift Status/Score/File left by one.
        self.assertIn(r"\|", row)
        self.assertEqual("|".join(split_row_raw(row)), row)

        cells = split_row_cells(row)
        self.assertEqual(len(cells), gbi.COLUMN_COUNT)
        self.assertEqual(cells[gbi.COL_TITLE], self.RAW_TITLE)
        self.assertEqual(cells[gbi.COL_STATUS], "NOT_STARTED")


class TestShardForIsPure(unittest.TestCase):
    """`shard_for` is a pure function of the id alone -- no registry has to
    stay in sync with which century a given id belongs to."""

    def test_boundary_and_formula(self):
        self.assertEqual(gbi.shard_for(1), gbi.shard_for(100))
        self.assertNotEqual(gbi.shard_for(100), gbi.shard_for(101))
        for item_id in (1, 50, 100, 101, 200, 201, 999):
            self.assertEqual(gbi.shard_for(item_id), (item_id - 1) // 100)

    def test_no_lookup_table_backs_it(self):
        # A pure function has no state to grow: computing the same id
        # repeatedly, and out of numeric order, must be idempotent -- a
        # lookup/registry populated on first use is the failure mode this
        # guards against.
        first_pass = [gbi.shard_for(i) for i in (300, 1, 250, 999, 1)]
        second_pass = [gbi.shard_for(i) for i in (1, 999, 250, 1, 300)]
        self.assertEqual(first_pass[0], second_pass[4])  # 300, computed once each way
        self.assertEqual(first_pass[1], first_pass[4])   # 1, computed twice in one pass


class TestBudgetEnforcerThreePaths(unittest.TestCase):
    """The budget enforcer's three paths, as a pure function over in-memory
    items -- no filesystem, no CLI, so the recursion itself is exercised
    directly."""

    def test_fits_in_one_file_no_split(self):
        items = [_make_item(i) for i in range(1, 21)]
        leaves = gbi.split_items_to_budget(items, _PURE_BACKLOG_DIR)

        self.assertEqual(len(leaves), 1)
        _subset, _body, _num_bytes, tokens, _truncated = leaves[0]
        self.assertLess(tokens, gbi.READ_TOKEN_WARN)

    def test_must_split_and_every_leaf_under_budget(self):
        # Title truncation caps every Title cell at 120 chars regardless of
        # the frontmatter value, so a long title cannot force this density
        # -- inflate the uncapped `blocks` column instead, matching how the
        # real corpus's own dense rows reach it.
        bulky_blocks = [f"{i % 1000:03d}" for i in range(500)]
        items = [_make_item(i, blocks=bulky_blocks) for i in range(1, 201)]

        leaves = gbi.split_items_to_budget(items, _PURE_BACKLOG_DIR)

        self.assertGreater(len(leaves), 1)
        total_rows = 0
        for _subset, _body, _num_bytes, tokens, _truncated in leaves:
            self.assertLess(tokens, gbi.READ_TOKEN_WARN)
            total_rows += len(_subset)
        self.assertEqual(total_rows, 200)

    def test_unsplittable_single_row_refuses_naming_the_row(self):
        huge_blocks = [f"{i % 1000:03d}" for i in range(15000)]
        item = _make_item(1, blocks=huge_blocks)

        with self.assertRaises(gbi.GeneratorError) as ctx:
            gbi.split_items_to_budget([item], _PURE_BACKLOG_DIR)

        message = str(ctx.exception)
        self.assertIn("item 001", message)
        self.assertIn(str(item["_path"]), message)
        self.assertIn("cannot be reduced by sharding further", message)


class TestWriteRefusesOnPathologicalRow(_GeneratorFixtureBase):
    """The budget enforcer's refusal, proven end to end through --write:
    a single row that cannot fit under budget must produce a non-zero exit
    and leave no index file on disk -- never ship a violation."""

    def test_write_refuses_and_writes_no_file(self):
        huge_blocks = [f"{i % 1000:03d}" for i in range(15000)]
        self.write_item("001", blocks=huge_blocks)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("001", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())


class TestSplitMeasuresShippedFileNotBody(_GeneratorFixtureBase):
    """Finding F1: the split decision now measures body + wrapper, not the
    bare body. A body that used to be accepted as one leaf -- and then
    made the ASSEMBLED file overflow, refusing in every mode with a
    message that blamed an unshardable row -- must now split instead.
    The window is the hub's own budget (`HUB_TOKEN_BUDGET`), the budget
    the hub split is actually decided against."""

    def test_body_in_boundary_window_splits_instead_of_refusing(self):
        shards_section = _one_shard_shards_section()
        wrapper_tokens = _hub_wrapper_tokens(shards_section)
        target_low = gbi.HUB_TOKEN_BUDGET - wrapper_tokens
        target_high = gbi.HUB_TOKEN_BUDGET

        blocks_len = _find_boundary_blocks_len(target_low, target_high)
        body_tokens = _body_tokens_for(blocks_len)

        # Guard against a vacuous pass: the pre-fix condition must actually
        # hold here -- the bare body alone is under budget (the OLD code
        # would have accepted it as one leaf), yet body + wrapper is not
        # (the OLD code's post-assembly check would then have raised).
        self.assertTrue(target_low <= body_tokens < target_high)
        self.assertLess(body_tokens, gbi.HUB_TOKEN_BUDGET)
        self.assertGreaterEqual(body_tokens + wrapper_tokens, gbi.HUB_TOKEN_BUDGET)

        items = _boundary_open_items(blocks_len) + [_make_item(990, status="COMPLETE", priority="Low")]
        result = gbi.build_index_files(items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive")

        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        shard_leaves = [entry for entry in result["files"] if not entry["path"].startswith("00-")]

        self.assertEqual(len(hub_leaves), 2)
        self.assertEqual(len(shard_leaves), 1)
        for entry in hub_leaves:
            self.assertLess(entry["tokens"], gbi.HUB_TOKEN_BUDGET)
            self.assertEqual(entry["tokens"], gbi.estimate_tokens(entry["bytes"]))

    def test_write_on_boundary_fixture_exits_zero(self):
        shards_section = _one_shard_shards_section()
        wrapper_tokens = _hub_wrapper_tokens(shards_section)
        target_low = gbi.HUB_TOKEN_BUDGET - wrapper_tokens
        target_high = gbi.HUB_TOKEN_BUDGET
        blocks_len = _find_boundary_blocks_len(target_low, target_high)

        # Same guard as the pure-function test above, over the identical
        # in-memory recipe this on-disk fixture is built from.
        body_tokens = _body_tokens_for(blocks_len)
        self.assertTrue(target_low <= body_tokens < target_high)

        for item_id in range(1, 80):
            self.write_item(f"{item_id:03d}", status="NOT_STARTED")
        self.write_item("080", status="NOT_STARTED", blocks=["990"] * blocks_len)
        self.write_item("990", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-990-01-PROC-Fixture.md")

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0, err)
        self.assertTrue((self.backlog_dir / "00-Index-Backlog.md").exists())
        overflow_leaves = list(self.backlog_dir.glob("00-Index-Backlog-*.md"))
        self.assertEqual(len(overflow_leaves), 1)


class TestHubDirectoryListsOverflowLeaves(unittest.TestCase):
    """CR4 (Finding 4): the hub's '## Shards' directory must list every
    hub OVERFLOW leaf a split produces, not just Archive shards -- a
    split-off leaf that exists on disk but is not listed in leaf 0 is
    unreachable to any reader who never thinks to look for a same-
    directory sibling file."""

    def test_hub_split_leaves_are_listed_backlinked_and_under_budget(self):
        items = _hub_splitting_items() + [_make_item(990, status="COMPLETE", priority="Low")]

        result = gbi.build_index_files(items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive")
        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        self.assertGreater(len(hub_leaves), 1)

        leaf0 = next(entry for entry in hub_leaves if entry["path"] == "00-Index-Backlog.md")
        overflow_leaves = [entry for entry in hub_leaves if entry is not leaf0]
        self.assertGreater(len(overflow_leaves), 0)

        for entry in hub_leaves:
            self.assertLess(entry["tokens"], gbi.HUB_TOKEN_BUDGET)
        for entry in overflow_leaves:
            self.assertIn(f"]({entry['path']})", leaf0["content"])
            self.assertIn("[Back to Backlog Index](00-Index-Backlog.md)", entry["content"])


class TestFactor2RekeyReachesGenerator(unittest.TestCase):
    """`compute_scores_for_items`'s frontmatter-shaped adapter carries no
    `abbrev` key of its own -- confirming the factor-2 re-key (`abbrev ==
    "BUG"`, not a Bug/Fix keyword regex over the title; BIR-S02-02-04)
    reaches this module's UNMODIFIED `compute_scores_for_items`
    automatically, with no edit to this file's production code."""

    def test_bug_item_without_keyword_beats_non_bug_item_by_the_bonus(self):
        tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_rekey_test_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        archive_dir = tmp / "Archive"  # never created -- count_archived_by_abbrev
        # treats an absent dir as zero counts, so momentum contributes
        # nothing to either item and cannot mask the bug/fix difference.

        config = {}
        weights = gbi.get_scoring_weights(config)

        bug_item = _make_item(901, title="Plain title, no keyword", abbrev="BUG")
        other_item = _make_item(902, title="Plain title, no keyword", abbrev="INFRA")
        items = [bug_item, other_item]

        gbi.compute_scores_for_items(items, archive_dir, config)

        # Otherwise identical inputs -- the only difference is `abbrev`, so
        # the score gap must equal exactly the configured bug/fix bonus,
        # read from config rather than assumed as a literal 15.
        self.assertEqual(
            int(bug_item["score"]) - int(other_item["score"]), weights["bug_fix_bonus"]
        )


# Every class below uses only API that predates the hub budget
# (`build_index_files`, `render_table_body`, `main()`, and `read_limits`'
# own constants), so each one fails BY ASSERTION -- never by an
# AttributeError on a new symbol -- when run against an older generator.
_HUB_LIMIT = read_limits.READ_PAGE_CAP_TOKENS // 2


def _mid_size_fixture():
    """17 open rows and 17 closed rows (one century), each row ~1,000
    tokens: both tables land between the hub limit (12,500) and the
    shard budget (22,000)."""
    open_items = _hub_splitting_items(row_count=17)
    closed_items = [
        _make_item(i, status="COMPLETE", score="-", blocks=["990"] * 500)
        for i in range(101, 118)
    ]
    return open_items, closed_items


def _lf_body_tokens(items):
    body, _truncated = gbi.render_table_body(items, _PURE_BACKLOG_DIR)
    return read_limits.estimate_tokens(len(body.encode("utf-8")))


class TestHubBudgetIsHalfThePageCap(unittest.TestCase):
    """P1: the hub family splits against half the Read-tool page cap, not
    the 22,000-token warn level, while an Archive shard of similar size
    stays one file under its own, larger budget."""

    def test_mid_size_hub_splits_and_same_size_shard_does_not(self):
        open_items, closed_items = _mid_size_fixture()

        # Guard against a vacuous pass: both tables lie between the hub
        # limit and the shard budget, with room left for any wrapper, so
        # an older generator ships the open set as ONE hub file.
        for items in (open_items, closed_items):
            tokens = _lf_body_tokens(items)
            self.assertGreaterEqual(tokens, _HUB_LIMIT)
            self.assertLess(tokens + 1000, read_limits.READ_TOKEN_WARN)

        result = gbi.build_index_files(
            open_items + closed_items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive"
        )
        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        shard_files = [entry for entry in result["files"] if entry["path"].startswith("Archive/")]

        self.assertGreater(len(hub_leaves), 1)
        for entry in hub_leaves:
            self.assertLess(entry["tokens"], _HUB_LIMIT)
        self.assertEqual(sum(entry["rows"] for entry in hub_leaves), len(open_items))

        # Distinct budgets: the closed century is just as large, and stays whole.
        self.assertEqual(len(shard_files), 1)
        self.assertGreaterEqual(shard_files[0]["tokens"], _HUB_LIMIT)
        self.assertLess(shard_files[0]["tokens"], read_limits.READ_TOKEN_WARN)

    def test_every_entry_reports_its_budget_and_page_cap_ratio(self):
        open_items, closed_items = _mid_size_fixture()
        result = gbi.build_index_files(
            open_items + closed_items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive"
        )

        for entry in result["files"]:
            is_hub = entry["path"].startswith("00-")
            expected_budget = _HUB_LIMIT if is_hub else read_limits.READ_TOKEN_WARN
            self.assertEqual(entry.get("budget"), expected_budget, entry["path"])
            self.assertEqual(entry.get("headroom"), expected_budget - entry["tokens"])
            self.assertEqual(
                entry.get("page_cap_ratio"),
                round(read_limits.READ_PAGE_CAP_TOKENS / entry["tokens"], 2),
            )
            if is_hub:
                self.assertGreaterEqual(entry["page_cap_ratio"], 2.0)


class TestCrlfCheckoutBytesAreBudgeted(_GeneratorFixtureBase):
    """P2 (end to end): the reported `bytes` is what a CRLF checkout holds
    on disk, not the LF render. The on-disk files are rewritten as CRLF
    from explicit bytes -- never `Path.write_text`, which normalizes to
    `os.linesep` and would make the fixture depend on the platform."""

    def test_dry_run_bytes_equal_the_crlf_files_on_disk(self):
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        self.write_item("150", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-150-01-PROC-Fixture.md")
        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 0, err)

        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        shard_path = self.archive_dir / "Index-Backlog-150-150.md"
        for path in (hub_path, shard_path):
            crlf_bytes = path.read_bytes().replace(b"\n", b"\r\n")
            path.write_bytes(crlf_bytes)
            self.assertGreater(crlf_bytes.count(b"\r\n"), 0)
            self.assertEqual(crlf_bytes.count(b"\r\n"), crlf_bytes.count(b"\n"))

        code, out, err = self.run_main("--dry-run", "--json")
        self.assertEqual(code, 0, err)
        entries = {entry["path"]: entry for entry in json.loads(out)}

        self.assertEqual(entries["00-Index-Backlog.md"]["bytes"], len(hub_path.read_bytes()))
        self.assertEqual(
            entries["Archive/Index-Backlog-150-150.md"]["bytes"], len(shard_path.read_bytes())
        )
        for entry in entries.values():
            self.assertEqual(entry["tokens"], read_limits.estimate_tokens(entry["bytes"]))


class TestShardSplitCountsCrlfBytes(unittest.TestCase):
    """P2 (pure function): a closed century that fits the shard budget on
    LF bytes but not on CRLF bytes must split into two shard files. The
    window is one byte per line, so the fixture binary-searches into it."""

    BACKLINK = "[Back to Backlog Index](../00-Index-Backlog.md)\n\n"

    def _century(self, blocks_len):
        items = [_make_item(i, status="COMPLETE", score="-") for i in range(101, 150)]
        items.append(_make_item(150, status="COMPLETE", score="-", blocks=["990"] * blocks_len))
        return items

    def _measure_both(self, blocks_len):
        """Return (the LF split sum an older generator decides on, the
        token count of the assembled shard as a CRLF checkout holds it)."""
        body, _truncated = gbi.render_table_body(self._century(blocks_len), _PURE_BACKLOG_DIR)
        lf_split_sum = read_limits.estimate_tokens(
            len(body.encode("utf-8"))
        ) + read_limits.estimate_tokens(len(self.BACKLINK.encode("utf-8")))
        crlf_file = (self.BACKLINK + body).replace("\n", "\r\n").encode("utf-8")
        return lf_split_sum, read_limits.estimate_tokens(len(crlf_file))

    def test_century_inside_the_crlf_window_splits_into_two_shards(self):
        budget = read_limits.READ_TOKEN_WARN
        lo, hi = 0, 20000
        self.assertLess(self._measure_both(lo)[1], budget)
        self.assertGreaterEqual(self._measure_both(hi)[1], budget)
        while lo < hi:  # smallest blocks_len whose CRLF file reaches the budget
            mid = (lo + hi) // 2
            if self._measure_both(mid)[1] < budget:
                lo = mid + 1
            else:
                hi = mid

        # Guard against a vacuous pass: LF bytes fit, CRLF bytes do not.
        lf_split_sum, crlf_tokens = self._measure_both(lo)
        self.assertLess(lf_split_sum, budget)
        self.assertGreaterEqual(crlf_tokens, budget)

        result = gbi.build_index_files(
            self._century(lo), _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive"
        )
        shards = [entry for entry in result["files"] if entry["path"].startswith("Archive/")]

        self.assertEqual(len(shards), 2)
        self.assertEqual(sum(entry["rows"] for entry in shards), 50)
        for entry in shards:
            self.assertTrue(entry["content"].startswith(self.BACKLINK))
            self.assertLess(entry["tokens"], budget)


class TestHubDirectoryIsComplete(unittest.TestCase):
    """P3: leaf 0's `## Shards` directory links exactly the hub overflow
    leaves that ship -- no stale id range pointing at a file that does not
    exist, and no shipped leaf left unlisted. Many Archive shards make the
    directory itself a large part of the reserve, so its own growth feeds
    back into the split."""

    def test_leaf0_links_exactly_the_overflow_files_produced(self):
        closed = [
            _make_item(century * 100 + 1, status="COMPLETE", score="-")
            for century in range(3, 43)
        ]
        items = _hub_splitting_items() + closed

        result = gbi.build_index_files(items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive")
        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        leaf0 = next(entry for entry in hub_leaves if entry["path"] == "00-Index-Backlog.md")
        produced = {entry["path"] for entry in hub_leaves if entry is not leaf0}
        linked = set(re.findall(r"\]\((00-Index-Backlog-[^)]+)\)", leaf0["content"]))

        self.assertGreater(len(produced), 1)
        self.assertEqual(linked, produced)
        self.assertEqual(sum(entry["rows"] for entry in hub_leaves), 200)


class TestPrintedReportShowsBudgetAndRatio(_GeneratorFixtureBase):
    """The printed (non-JSON) report names each file's budget and its
    page-cap ratio, so a later headroom miss shows up in every run."""

    def test_each_file_line_names_budget_and_page_cap_ratio(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("150", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-150-01-PROC-Fixture.md")

        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 0, err)
        file_lines = [line for line in out.splitlines() if " rows, " in line]
        self.assertEqual(len(file_lines), 2)
        for line in file_lines:
            self.assertIn("page_cap_ratio ", line)
        hub_line = next(line for line in file_lines if line.startswith("00-Index-Backlog.md:"))
        shard_line = next(line for line in file_lines if line.startswith("Archive/"))
        self.assertIn(f"budget {_HUB_LIMIT}", hub_line)
        self.assertIn(f"budget {read_limits.READ_TOKEN_WARN}", shard_line)


if __name__ == "__main__":
    unittest.main()
