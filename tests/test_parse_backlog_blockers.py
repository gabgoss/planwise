#!/usr/bin/env python3
"""Unit tests for parse_backlog.py's blocked-item exclusion and blocker order.

`build_blocked_by_map`/`filter_items` used to key/probe the blocked-item map on
the raw ID string. On a prefixed-ID index every lookup missed, so a blocked
item silently fell through to the caller's selectable output -- the fail-open
failure mode a dependency gate exists to prevent. Both the write side
(status_map / blocked_by keys) and the read side (the filter_items probe) now
normalize through `normalize_id`, so a prefixed index and a bare index both
correctly exclude a blocked item.

The file also covers the Dependencies Blocks cell grammar, the row-level Blocks
cell, archived blockers, `open_blocker_map` and `order_with_blockers`.

Run with:  python -m pytest tests/test_parse_backlog_blockers.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ itself, for parse_backlog_fixture

import parse_backlog
from markdown_parser import normalize_id
from parse_backlog import (
    FilterCriteria,
    build_blocked_by_map,
    filter_items,
    format_blocked_summary,
    parse_backlog_table,
    parse_dependencies_table,
)
from parse_backlog_fixture import (
    CONFIG_YAML_FIXTURE,
    GENERATED_9COL_HEADER,
    HEADER,
    _ParseBacklogFixtureBase,
    _row,
    _row9,
)

DEPENDENCIES_HEADER = (
    "\n## Dependencies\n\n"
    "| ID  | Blocks |\n"
    "|-----|--------|\n"
)


class TestBlockedByMapFailOpenGuard(unittest.TestCase):
    """The load-bearing regression guard: a blocked item's exclusion from
    selectable output must survive whatever ID form the index and
    Dependencies table use. This is a fail-OPEN bug class -- a silent miss
    lets a blocked item straight through -- so every variant below asserts
    the dependency table actually parsed (a non-empty
    `parse_dependencies_table` result and a non-empty `blocked_by_map`)
    BEFORE asserting the exclusion. `markdown_parser.py`'s Dependencies-table
    header regex only recognizes a header row shaped `| ID | ... |`; any
    other header shape parses to an empty list, which would make the
    exclusion assertion below pass vacuously -- on an empty dependency set
    nothing is ever blocked, so "blocked item excluded" is trivially true for
    the wrong reason.

    This class covers the legacy, un-migrated shape: a hand-authored index
    whose only edges live in `## Dependencies` (no Blocks cell at all). The
    9-column generated-row Blocks-cell path is covered separately by
    `TestRowLevelBlocksCellUnionedIntoBlockedByMap` below, and the read-if-
    present union of the two sources is `build_blocked_by_map`'s own
    contract (Finding 2 of the closeout review).
    """

    def _content(self, blocker_cell: str, blocked_cell: str, index_rows: str) -> str:
        return (
            HEADER
            + index_rows
            + DEPENDENCIES_HEADER
            + f"| {blocker_cell} | {blocked_cell} |\n"
        )

    def _assert_fixture_actually_parsed(self, dependencies, blocked_by_map):
        self.assertTrue(
            dependencies,
            "fixture's Dependencies table failed to parse -- check the header "
            "shape is exactly '| ID | Blocks |'",
        )
        self.assertTrue(
            blocked_by_map,
            "blocked_by_map is empty -- build_blocked_by_map's normalization "
            "may be missing, or the dependency table above did not parse",
        )

    def test_blocked_item_excluded_on_a_prefixed_index_and_prefixed_dependency_ids(self):
        index_rows = _row("PFX-001") + _row("PFX-002")
        content = self._content("PFX-001", "PFX-002", index_rows)

        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)
        blocked_by_map = build_blocked_by_map(dependencies, items)
        self._assert_fixture_actually_parsed(dependencies, blocked_by_map)

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)

        self.assertNotIn("PFX-002", [i["id"] for i in filtered])
        self.assertIn("PFX-002", [i["id"] for i in blocked])

    def test_blocked_item_excluded_on_a_bare_index_and_bare_dependency_ids(self):
        # The historical (pre-prefix) case -- must keep working unchanged.
        index_rows = _row("001") + _row("002")
        content = self._content("001", "002", index_rows)

        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)
        blocked_by_map = build_blocked_by_map(dependencies, items)
        self._assert_fixture_actually_parsed(dependencies, blocked_by_map)

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)

        self.assertNotIn("002", [i["id"] for i in filtered])
        self.assertIn("002", [i["id"] for i in blocked])

    def test_blocked_item_excluded_when_index_is_prefixed_but_dependency_ids_are_bare(self):
        # The deepest cross-form case: nothing here matches by literal string
        # equality on EITHER map side -- this can only pass if normalize_id is
        # applied on both the write side (status_map / blocked_by keys in
        # build_blocked_by_map) and the read side (filter_items' probe). This
        # is the regression guard that must fail if Task 03's normalization is
        # reverted on either side of the map.
        index_rows = _row("PFX-001") + _row("PFX-002")
        content = self._content("001", "002", index_rows)  # bare dependency IDs

        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)
        blocked_by_map = build_blocked_by_map(dependencies, items)
        self._assert_fixture_actually_parsed(dependencies, blocked_by_map)

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)

        self.assertNotIn("PFX-002", [i["id"] for i in filtered])
        self.assertIn("PFX-002", [i["id"] for i in blocked])

    def test_blocker_closed_status_does_not_block(self):
        # Negative control: a CLOSED/COMPLETE blocker must NOT exclude the
        # dependent item -- proves the exclusion is status-gated, not a
        # blanket "any dependency row" match.
        index_rows = _row("PFX-001", status="COMPLETE") + _row("PFX-002")
        content = self._content("PFX-001", "PFX-002", index_rows)

        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)
        self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
        blocked_by_map = build_blocked_by_map(dependencies, items)

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)

        self.assertIn("PFX-002", [i["id"] for i in filtered])
        self.assertEqual(blocked, [])


class TestDependenciesBlocksCellGrammar(_ParseBacklogFixtureBase):
    """A legacy `## Dependencies` Blocks cell is read with the migrator's own
    grammar: ids, then at most one trailing parenthetical note. An annotated
    cell must still block (a fail-OPEN class: a silent miss routes a blocked
    item), and a cell outside the grammar must warn on stderr instead of going
    inert. Every test asserts the dependency table parsed before it asserts
    exclusion, so an empty parse cannot pass vacuously."""

    INDEX_ROWS = _row("097") + _row("098") + _row("100")

    def _content(self, blocker_cell: str, blocked_cell: str) -> str:
        return (
            HEADER
            + self.INDEX_ROWS
            + DEPENDENCIES_HEADER
            + f"| {blocker_cell} | {blocked_cell} |\n"
        )

    def _parse(self, blocker_cell: str, blocked_cell: str):
        """Return (dependencies, blocked_by_map, blocked_ids, stderr)."""
        content = self._content(blocker_cell, blocked_cell)
        items = parse_backlog_table(content)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            dependencies = parse_dependencies_table(content)
        blocked_by_map = build_blocked_by_map(dependencies, items)
        _, blocked = filter_items(items, FilterCriteria(), blocked_by_map)
        return dependencies, blocked_by_map, [i["id"] for i in blocked], err.getvalue()

    def test_annotated_cell_still_blocks_the_named_item(self):
        dependencies, blocked_by_map, blocked_ids, err = self._parse(
            "100", "BB-097 (some explanation here)"
        )
        self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
        self.assertTrue(blocked_by_map, "blocked_by_map is empty")
        self.assertIn("097", blocked_ids)
        self.assertEqual(blocked_by_map["97"], ["100"])
        self.assertEqual(err, "")

    def test_commas_inside_the_note_mint_no_ids(self):
        dependencies, blocked_by_map, blocked_ids, err = self._parse(
            "100", "BB-097 (10,000 of 133,252 rows)"
        )
        self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
        self.assertIn("097", blocked_ids)
        self.assertEqual(set(blocked_by_map), {"97"})
        self.assertEqual(err, "")

    def test_multi_id_annotated_cell_blocks_every_id(self):
        dependencies, blocked_by_map, blocked_ids, err = self._parse(
            "100", "097, 098 (note, with a comma)"
        )
        self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
        self.assertEqual(set(blocked_by_map), {"97", "98"})
        self.assertEqual(sorted(blocked_ids), ["097", "098"])
        self.assertEqual(err, "")

    def test_unparseable_cell_warns_with_line_and_cell_and_blocks_nothing(self):
        dependencies, blocked_by_map, blocked_ids, err = self._parse("100", "see the plan")
        self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
        self.assertEqual(blocked_by_map, {})
        self.assertEqual(blocked_ids, [])
        # The warning must name the dependency row's 1-based line number.
        row_line = self._content("100", "see the plan").splitlines().index("| 100 | see the plan |") + 1
        warnings = [line for line in err.splitlines() if line]
        self.assertEqual(len(warnings), 1, err)
        self.assertTrue(warnings[0].startswith("Warning:"), warnings[0])
        self.assertIn(f"line {row_line}", warnings[0])
        self.assertIn("'see the plan'", warnings[0])

    def test_dash_and_none_cells_are_deliberately_empty_and_silent(self):
        for blocked_cell in ("-", "none"):
            with self.subTest(blocked_cell=blocked_cell):
                dependencies, blocked_by_map, blocked_ids, err = self._parse("100", blocked_cell)
                self.assertTrue(dependencies, "fixture's Dependencies table failed to parse")
                self.assertEqual(dependencies[0]["blocked_ids"], [])
                self.assertEqual(blocked_by_map, {})
                self.assertEqual(blocked_ids, [])
                self.assertEqual(err, "")

    def test_blocker_cell_naming_no_single_id_warns_and_keeps_the_row(self):
        dependencies, _, _, err = self._parse("see 100 and 101", "097")
        self.assertEqual(len(dependencies), 1, "the row must not be dropped")
        self.assertEqual(dependencies[0]["blocker_id"], "see 100 and 101")
        self.assertEqual(dependencies[0]["blocked_ids"], ["097"])
        warnings = [line for line in err.splitlines() if line]
        self.assertEqual(len(warnings), 1, err)
        self.assertIn("'see 100 and 101'", warnings[0])

    def test_cli_reports_blocked_by_for_an_annotated_cell(self):
        self.backlog_dir.joinpath("00-Index-Backlog.md").write_text(
            self._content("100", "BB-097 (some explanation here)"), encoding="utf-8"
        )
        out, err = self.run_parse()
        self.assertIn("Blocked Items", out)
        self.assertIn("097", out)
        self.assertIn("blocked by: 100", out)
        self.assertEqual(err, "")

    def test_cli_unparseable_cell_warns_on_stderr_only(self):
        self.backlog_dir.joinpath("00-Index-Backlog.md").write_text(
            self._content("100", "see the plan"), encoding="utf-8"
        )
        out, err = self.run_parse()
        self.assertIn("Warning:", err)
        self.assertIn("'see the plan'", err)
        self.assertNotIn("Warning:", out)


class TestRowLevelBlocksCellUnionedIntoBlockedByMap(unittest.TestCase):
    """Code-review corrective, Finding 5: a 9-column row's own Blocks cell
    must feed `build_blocked_by_map` -- a generated hub carries no
    "## Dependencies" table at all, so without this the map is always
    empty on a generated corpus. `dependencies == []` below proves a
    generated index has no dependency on that section at all: blocking
    comes entirely from the Blocks column, and the read-if-present union
    (Finding 2 of the closeout review) contributes nothing here."""

    def test_generated_row_blocks_cell_blocks_the_named_item(self):
        content = (
            GENERATED_9COL_HEADER
            + _row9("001", feature="Item A", blocks="[002]")
            + _row9("002", feature="Item B")
        )

        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)
        self.assertEqual(dependencies, [])  # no "## Dependencies" table exists

        blocked_by_map = build_blocked_by_map(dependencies, items)
        self.assertEqual(blocked_by_map.get(normalize_id("002")), [normalize_id("001")])

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)
        self.assertNotIn("002", [i["id"] for i in filtered])
        self.assertIn("002", [i["id"] for i in blocked])

        id_to_title = {normalize_id(i["id"]): i["feature"] for i in items}
        summary = format_blocked_summary(blocked, blocked_by_map, id_to_title)
        # blocked_by_map/id_to_title are normalize_id-keyed, so the rendered
        # blocker id is the non-zero-padded form ("1"), not the row's own
        # zero-padded id ("001").
        self.assertIn(f"{normalize_id('001')} (Item A)", summary)

    def test_closed_blocker_row_cell_does_not_block(self):
        content = (
            GENERATED_9COL_HEADER
            + _row9("001", status="COMPLETE", feature="Item A", blocks="[002]", score="-")
            + _row9("002", feature="Item B")
        )

        items = parse_backlog_table(content)
        blocked_by_map = build_blocked_by_map(parse_dependencies_table(content), items)

        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map)
        self.assertIn("002", [i["id"] for i in filtered])
        self.assertEqual(blocked, [])


class TestArchivedBlockerInLegacyDependenciesTable(unittest.TestCase):
    """A legacy `## Dependencies` row whose blocker is COMPLETE and lives only
    in an Archive shard must not hold its blocked item back. The hub family
    carries no row for that blocker, so its status lookup used to return the
    empty string and the edge stayed open.

    Every test asserts the Dependencies table parsed before it asserts on
    blocking, because an empty table makes "nothing is blocked" vacuously true.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_archived_blocker_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        # Archive shard: blocker 100 is COMPLETE and absent from the hub.
        (self.archive_dir / "Index-Backlog-100-100.md").write_text(
            GENERATED_9COL_HEADER + _row9("100", status="COMPLETE", score="-"),
            encoding="utf-8",
        )

    def write_hub(self, blocker: str) -> str:
        """A legacy 6-column hub: item 002 is open, and the Dependencies row
        says `blocker` blocks it. Returns the hub text."""
        content = HEADER + _row("002") + DEPENDENCIES_HEADER + f"| {blocker} | 002 |\n"
        (self.backlog_dir / "00-Index-Backlog.md").write_text(content, encoding="utf-8")
        return content

    def run_parse(self) -> str:
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path)]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue()

    def test_archived_closed_blocker_does_not_block(self):
        content = self.write_hub("100")
        self.assertTrue(parse_dependencies_table(content), "fixture's Dependencies table failed to parse")

        out = self.run_parse()

        self.assertNotIn("Blocked Items", out)
        self.assertTrue(any(line.startswith("002") for line in out.splitlines()))

    def test_blocker_found_nowhere_still_blocks(self):
        # 999 is in neither the hub family nor an Archive shard. A typo in a
        # hand-authored row must keep its item blocked, not silently unblock it.
        content = self.write_hub("999")
        self.assertTrue(parse_dependencies_table(content), "fixture's Dependencies table failed to parse")

        out = self.run_parse()

        self.assertIn("Blocked Items", out)
        self.assertIn("blocked by: 999", out)

    def test_map_treats_only_a_closed_archived_id_as_resolved(self):
        content = HEADER + _row("002") + DEPENDENCIES_HEADER + "| 100 | 002 |\n"
        items = parse_backlog_table(content)
        dependencies = parse_dependencies_table(content)

        without_archive = build_blocked_by_map(dependencies, items)
        self.assertEqual(without_archive.get(normalize_id("002")), [normalize_id("100")])

        with_archive = build_blocked_by_map(
            dependencies, items, frozenset({normalize_id("100")})
        )
        self.assertEqual(with_archive, {})

    def test_hub_status_wins_over_an_archived_id(self):
        # An id present in the hub family keeps the hub row's status, so an
        # open hub row still blocks even when the same id sits in an archive.
        content = HEADER + _row("100") + _row("002") + DEPENDENCIES_HEADER + "| 100 | 002 |\n"
        items = parse_backlog_table(content)

        blocked_by_map = build_blocked_by_map(
            parse_dependencies_table(content), items, frozenset({normalize_id("100")})
        )

        self.assertEqual(blocked_by_map.get(normalize_id("002")), [normalize_id("100")])

    def test_collect_archived_closed_ids_skips_open_shard_rows(self):
        (self.archive_dir / "Index-Backlog-101-101.md").write_text(
            GENERATED_9COL_HEADER + _row9("101", status="NOT_STARTED"),
            encoding="utf-8",
        )
        self.write_hub("100")
        config = {
            "_archive_dir": self.archive_dir,
            "_index_path": self.backlog_dir / "00-Index-Backlog.md",
        }

        self.assertEqual(
            parse_backlog.collect_archived_closed_ids(config), frozenset({normalize_id("100")})
        )


class TestOpenBlockerMap(unittest.TestCase):
    """`open_blocker_map` is the one home of the open-blocker join: hub-family rows
    that carry `blocks`, the legacy `## Dependencies` table and the archived-closed
    ids. Each case reads the files from a real temp tree, so `rows=None` and
    `index_text=None` take their default readers."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_open_blocker_map_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backlog_dir = self.tmp / "planwise" / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.backlog_dir / "00-Index-Backlog.md"
        self.config = {
            "_index_path": self.index_path,
            "_backlog_dir": self.backlog_dir,
            "_archive_dir": self.archive_dir,
        }

    def write_hub(self, text: str) -> str:
        self.index_path.write_text(text, encoding="utf-8")
        return text

    def write_archive_shard(self, text: str) -> None:
        (self.archive_dir / "Index-Backlog-100-100.md").write_text(text, encoding="utf-8")

    def test_row_level_blocks_edge_blocks_the_named_item(self):
        self.write_hub(
            GENERATED_9COL_HEADER
            + _row9("001", blocks="[002]")
            + _row9("002")
        )

        self.assertEqual(
            parse_backlog.open_blocker_map(self.config),
            {normalize_id("002"): [normalize_id("001")]},
        )

    def test_closed_hub_blocker_does_not_block(self):
        self.write_hub(
            GENERATED_9COL_HEADER
            + _row9("001", status="COMPLETE", blocks="[002]", score="-")
            + _row9("002")
        )

        self.assertEqual(parse_backlog.open_blocker_map(self.config), {})

    def test_dependencies_edge_from_an_archived_closed_blocker_is_resolved(self):
        content = self.write_hub(
            HEADER + _row("002") + DEPENDENCIES_HEADER + "| 100 | 002 |\n"
        )
        self.assertTrue(parse_dependencies_table(content), "fixture's Dependencies table failed to parse")
        self.write_archive_shard(
            GENERATED_9COL_HEADER + _row9("100", status="COMPLETE", score="-")
        )

        self.assertEqual(parse_backlog.open_blocker_map(self.config), {})

    def test_unknown_blocker_stays_open(self):
        content = self.write_hub(
            HEADER + _row("002") + DEPENDENCIES_HEADER + "| 999 | 002 |\n"
        )
        self.assertTrue(parse_dependencies_table(content), "fixture's Dependencies table failed to parse")
        self.write_archive_shard(
            GENERATED_9COL_HEADER + _row9("100", status="COMPLETE", score="-")
        )

        self.assertEqual(
            parse_backlog.open_blocker_map(self.config),
            {normalize_id("002"): [normalize_id("999")]},
        )

    def test_passed_rows_and_index_text_replace_the_default_readers(self):
        # The hub on disk says nothing is blocked. The arguments say 002 waits on 001.
        self.write_hub(GENERATED_9COL_HEADER + _row9("001") + _row9("002"))
        rows = parse_backlog_table(
            GENERATED_9COL_HEADER + _row9("001", blocks="[002]") + _row9("002")
        )

        self.assertEqual(parse_backlog.open_blocker_map(self.config), {})
        self.assertEqual(
            parse_backlog.open_blocker_map(self.config, rows=rows, index_text=""),
            {normalize_id("002"): [normalize_id("001")]},
        )

    def test_unreadable_index_counts_as_empty(self):
        rows = parse_backlog_table(
            GENERATED_9COL_HEADER + _row9("001", blocks="[002]") + _row9("002")
        )
        self.assertFalse(self.index_path.exists())

        self.assertEqual(
            parse_backlog.open_blocker_map(self.config, rows=rows),
            {normalize_id("002"): [normalize_id("001")]},
        )

    def test_archive_shards_are_not_read_without_a_dependencies_table(self):
        self.write_hub(GENERATED_9COL_HEADER + _row9("001", blocks="[002]") + _row9("002"))

        with mock.patch.object(
            parse_backlog, "collect_archived_closed_ids", side_effect=AssertionError("archive read")
        ):
            parse_backlog.open_blocker_map(self.config)


# waiting id -> its blockers, the shape of a decomposed backlog: two chains, two
# parents that wait for their sub-items, and one item (088) that stands alone.
FOURTEEN = {
    "082": ["095"],
    "083": ["082"],
    "084": ["085", "086", "087"],
    "086": ["085"],
    "089": ["090", "091", "092", "093"],
    "094": ["082", "083", "095"],
}
FOURTEEN_BASE = [f"{n:03d}" for n in range(82, 96)]


class TestOrderWithBlockers(unittest.TestCase):
    """`order_with_blockers` admits a blocked id only behind its blockers.

    `blocked_by` maps a waiting id to its open blockers, the shape
    `build_blocked_by_map` returns.
    """

    def order(self, base, blocked_by, **kwargs):
        return parse_backlog.order_with_blockers(base, blocked_by, **kwargs)

    def assert_blockers_first(self, order, blocked_by):
        for position, item_id in enumerate(order):
            for blocker in blocked_by.get(item_id, []):
                with self.subTest(item=item_id, blocker=blocker):
                    self.assertIn(blocker, order[:position])

    def test_unblocked_ids_keep_the_base_order(self):
        self.assertEqual(self.order(["c", "a", "b"], {}), (["c", "a", "b"], []))

    def test_a_chain_named_backwards_runs_blocker_first(self):
        order, left_out = self.order(["c", "b", "a"], {"c": ["b"], "b": ["a"]})
        self.assertEqual((order, left_out), (["a", "b", "c"], []))

    def test_a_blocker_outside_the_base_order_leaves_the_item_out(self):
        self.assertEqual(self.order(["a", "b"], {"b": ["q"]}), (["a"], ["b"]))

    def test_an_item_behind_a_left_out_item_is_left_out_too(self):
        order, left_out = self.order(["a", "b", "c"], {"b": ["q"], "c": ["b"]})
        self.assertEqual((order, left_out), (["a"], ["b", "c"]))

    def test_a_cycle_is_never_admitted(self):
        order, left_out = self.order(["a", "b", "c", "d"], {"a": ["c"], "b": ["a"], "c": ["b"]})
        self.assertEqual((order, left_out), (["d"], ["a", "b", "c"]))

    def test_a_reciprocal_pair_is_never_admitted(self):
        self.assertEqual(self.order(["a", "b"], {"a": ["b"], "b": ["a"]}), ([], ["a", "b"]))

    def test_accept_is_asked_only_once_every_blocker_is_in(self):
        asked = []

        def accept(item_id):
            asked.append(item_id)
            return item_id != "b"

        order, left_out = self.order(["a", "b", "c"], {"b": ["a"], "c": ["b"]}, accept=accept)

        self.assertEqual((order, left_out), (["a"], ["b", "c"]))
        # `c` waits for `b`, and `b` was refused, so `c` is never examined.
        self.assertEqual(asked, ["b"])

    def test_no_blocker_moves_ahead_for_an_item_that_is_left_out(self):
        # `x` waits for `b1` (in the run) and `b2` (not in the run).
        order, left_out = self.order(["x", "y", "b1"], {"x": ["b1", "b2"]})
        self.assertEqual((order, left_out), (["y", "b1"], ["x"]))

    def test_the_fourteen_item_shape(self):
        order, left_out = self.order(FOURTEEN_BASE, FOURTEEN)

        self.assertEqual(
            order,
            ["095", "082", "083", "085", "086", "087", "084", "088", "090", "091", "092", "093", "089", "094"],
        )
        self.assertEqual(left_out, [])
        self.assert_blockers_first(order, FOURTEEN)

    def test_a_limit_takes_an_item_with_its_blockers_or_passes_it_over(self):
        blocked_by = {"d": ["z"]}
        base = ["a", "d", "b", "z"]

        # `d` needs two places (`z` and itself) and one is left, so `b` takes it.
        self.assertEqual(self.order(base, blocked_by, limit=2)[0], ["a", "b"])
        self.assertEqual(self.order(base, blocked_by, limit=3)[0], ["a", "z", "d"])

    def test_every_limited_prefix_holds_its_own_blockers(self):
        for limit in range(1, 15):
            with self.subTest(limit=limit):
                order, _left_out = self.order(FOURTEEN_BASE, FOURTEEN, limit=limit)
                self.assertLessEqual(len(order), limit)
                self.assert_blockers_first(order, FOURTEEN)


if __name__ == "__main__":
    unittest.main()
