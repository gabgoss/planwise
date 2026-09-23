#!/usr/bin/env python3
"""Unit tests for parse_backlog.py's ID allocator and blocked-item exclusion.

parse_backlog.py underwent two related fixes:

  * `--next-id` used to derive the next ID from the row COUNT rather than
    from the numeric component of the ID column, so a prefixed or gappy index
    silently allocated a colliding or wrong-magnitude ID. It now derives
    max(numeric component) + 1 via `id_number`/`normalize_id`, and warns on
    stderr (exit code unaffected) when rows exist but none carry a numeric ID.

  * `build_blocked_by_map`/`filter_items` used to key/probe the blocked-item
    map on the raw ID string. On a prefixed-ID index every lookup missed, so a
    blocked item silently fell through to the caller's selectable output --
    the fail-open failure mode a dependency gate exists to prevent. Both the
    write side (status_map / blocked_by keys) and the read side (the
    filter_items probe) now normalize through `normalize_id`, so a prefixed
    index and a bare index both correctly exclude a blocked item.

Run with:  python -m pytest tests/test_parse_backlog.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import parse_backlog
from constants import ARCHIVE_STATUSES, CLOSED_STATUSES
from markdown_parser import normalize_id
from parse_backlog import (
    FilterCriteria,
    build_blocked_by_map,
    collect_all_known_ids,
    filter_items,
    format_blocked_summary,
    format_table,
    parse_backlog_table,
    parse_dependencies_table,
    resolve_closed_item_shard,
)

HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Files |\n"
    "|-----|---------|----------|--------|--------|-------|\n"
)

DEPENDENCIES_HEADER = (
    "\n## Dependencies\n\n"
    "| ID  | Blocks |\n"
    "|-----|--------|\n"
)

CONFIG_YAML_FIXTURE = """project:
  name: "ParseBacklogFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""


def _row(item_id: str, status: str = "NOT_STARTED", feature: str | None = None) -> str:
    feature = feature or f"Feature {item_id}"
    slug = item_id.replace("/", "-")
    return f"| {item_id} | {feature} | Low | {status} | DOC | [01](x-{slug}.md) |\n"


class _ParseBacklogFixtureBase(unittest.TestCase):
    """CLI-path fixture: temp planwise tree + injected argv, mirroring
    test_update_backlog.py's `_UpdateBacklogFixtureBase` pattern."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

    def write_index(self, rows_markdown: str) -> Path:
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_text(HEADER + rows_markdown, encoding="utf-8")
        return path

    def run_next_id(self) -> tuple[str, str]:
        """Invoke parse_backlog.main() with --next-id; return (stdout, stderr)."""
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path), "--next-id"]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue().strip(), err.getvalue()

    def run_parse(self, extra_args: list[str] | None = None) -> tuple[str, str]:
        """Invoke parse_backlog.main() with the plain CLI path; return (stdout, stderr)."""
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path), *(extra_args or [])]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue()


class TestNextIdAllocatorMatrix(_ParseBacklogFixtureBase):
    """--next-id derives max(numeric component) + 1, regardless of ID form."""

    def test_all_prefixed_ids(self):
        rows = "".join(_row(f"PFX-{i:03d}") for i in range(1, 146))
        self.write_index(rows)
        out, err = self.run_next_id()
        self.assertEqual(out, "146")
        self.assertEqual(err, "")

    def test_mixed_prefixed_max_and_one_legacy_bare_id(self):
        rows = _row("PFX-001") + _row("PFX-050") + _row("PFX-145") + _row("117")
        self.write_index(rows)
        out, err = self.run_next_id()
        self.assertEqual(out, "146")
        self.assertEqual(err, "")

    def test_all_bare_ids(self):
        rows = "".join(_row(f"{i:03d}") for i in range(1, 146))
        self.write_index(rows)
        out, err = self.run_next_id()
        self.assertEqual(out, "146")
        self.assertEqual(err, "")

    def test_genuinely_empty_index_allocates_001_silently(self):
        self.write_index("")  # header + separator only, no data rows
        out, err = self.run_next_id()
        self.assertEqual(out, "001")
        self.assertEqual(err, "")

    def test_non_empty_with_no_numeric_ids_warns_and_allocates_001(self):
        rows = _row("ALPHA") + _row("BETA")
        self.write_index(rows)
        out, err = self.run_next_id()
        self.assertEqual(out, "001")
        self.assertEqual(
            err.strip(),
            "WARNING: 2 row(s) parsed but none carried a numeric ID; "
            "allocating 001. Check the index's ID column format.",
        )

    def test_trailing_digit_anchoring_ignores_digits_inside_the_prefix(self):
        # "V2-003" carries a digit ("2") inside its alpha prefix; the max must
        # anchor on the TRAILING numeric component (3, then 10) and never be
        # confused by a digit that is part of the prefix, not the ID number.
        rows = _row("V2-003") + _row("V9-010")
        self.write_index(rows)
        out, err = self.run_next_id()
        self.assertEqual(out, "011")
        self.assertEqual(err, "")


class TestFilterItemsIdEquivalence(unittest.TestCase):
    """`--id` (FilterCriteria.item_id) matches on the numeric component,
    regardless of which side of the comparison carries a prefix."""

    def _items(self):
        return [
            {
                "id": "PFX-002", "feature": "Prefixed row", "priority": "High",
                "status": "NOT_STARTED", "abbrev": "DOC", "score": 0, "files": [],
            },
            {
                "id": "003", "feature": "Bare row", "priority": "Low",
                "status": "NOT_STARTED", "abbrev": "DOC", "score": 0, "files": [],
            },
        ]

    def test_bare_criteria_matches_a_prefixed_row(self):
        filtered, _ = filter_items(self._items(), FilterCriteria(item_id="002"))
        self.assertEqual([i["id"] for i in filtered], ["PFX-002"])

    def test_prefixed_criteria_matches_a_bare_row(self):
        filtered, _ = filter_items(self._items(), FilterCriteria(item_id="PFX-003"))
        self.assertEqual([i["id"] for i in filtered], ["003"])


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


class TestArchiveStatusesNotAliasedToClosedStatuses(unittest.TestCase):
    """BB-077 AC1: setting a hold status must not risk archiving the item file.
    ARCHIVE_STATUSES used to be a bare alias (`ARCHIVE_STATUSES = CLOSED_STATUSES`),
    so the two names pointed at the identical frozenset object -- widening one
    concept silently widened the other. They must now be independent objects,
    even though their current membership (COMPLETE, CLOSED) still matches."""

    def test_archive_and_closed_statuses_are_independent_objects(self):
        self.assertIsNot(
            ARCHIVE_STATUSES, CLOSED_STATUSES,
            "ARCHIVE_STATUSES is aliased to CLOSED_STATUSES -- adding a hold "
            "status to one would silently change the other's archival behavior",
        )
        # Membership is unchanged by the split -- this is a decoupling, not a
        # behavior change to what already archives.
        self.assertEqual(ARCHIVE_STATUSES, CLOSED_STATUSES)


class TestHoldStatusSelectabilityFilter(_ParseBacklogFixtureBase):
    """BB-077 AC2/AC3: a BLOCKED item with no dependency edges is inert today --
    parse_backlog.py filters selectability only on closed-ness and the
    blocks: dependency graph, never on the item's own status. These pin the
    fix: BLOCKED excludes an item from the selectable table/JSON the same way
    a dependency block does, is distinguishable from a dependency block in the
    blocked summary, and is still resolvable by a direct --id lookup so the
    hold can be surfaced rather than silently bypassed."""

    def test_held_item_with_no_dependency_edges_is_excluded_from_filtered(self):
        items = [
            {"id": "067", "feature": "Held item", "priority": "Medium",
             "status": "BLOCKED", "abbrev": "DOC", "score": 25, "files": []},
            {"id": "068", "feature": "Ordinary item", "priority": "Medium",
             "status": "NOT_STARTED", "abbrev": "DOC", "score": 20, "files": []},
        ]
        filtered, blocked = filter_items(items, FilterCriteria(), blocked_by_map={})

        self.assertNotIn("067", [i["id"] for i in filtered])
        self.assertIn("068", [i["id"] for i in filtered])
        self.assertIn("067", [i["id"] for i in blocked])

    def test_show_blocked_still_reveals_a_held_item(self):
        items = [
            {"id": "067", "feature": "Held item", "priority": "Medium",
             "status": "BLOCKED", "abbrev": "DOC", "score": 25, "files": []},
        ]
        filtered, blocked = filter_items(
            items, FilterCriteria(show_blocked=True), blocked_by_map={}
        )
        self.assertIn("067", [i["id"] for i in filtered])
        self.assertEqual(blocked, [])

    def test_blocked_summary_distinguishes_hold_from_dependency_block(self):
        held = {"id": "067", "feature": "Held item", "priority": "Medium",
                "status": "BLOCKED", "abbrev": "DOC", "score": 25, "files": []}
        dep_blocked = {"id": "070", "feature": "Dependency-blocked item", "priority": "Medium",
                       "status": "NOT_STARTED", "abbrev": "DOC", "score": 20, "files": []}
        # blocked_by_map keys/values are normalize_id'd by build_blocked_by_map
        # (leading zeros stripped) -- mirror that here rather than the raw ID.
        summary = format_blocked_summary([held, dep_blocked], blocked_by_map={"70": ["69"]})

        held_line = next(line for line in summary.splitlines() if "067" in line)
        dep_line = next(line for line in summary.splitlines() if "070" in line)
        self.assertIn("held (status: BLOCKED)", held_line)
        self.assertIn("blocked by: 69", dep_line)

    def test_blocked_summary_names_blocker_with_its_title_when_available(self):
        # `id_to_title` is the optional, caller-supplied lookup (built from
        # already-parsed items -- no second read) that lets the summary name
        # the blocker's feature, not just its bare id. Assert the exact
        # rendered text, not merely that the line is non-empty -- a test
        # that only checked non-emptiness would pass against the wrong id.
        dep_blocked = {"id": "070", "feature": "Dependency-blocked item", "priority": "Medium",
                       "status": "NOT_STARTED", "abbrev": "DOC", "score": 20, "files": []}
        summary = format_blocked_summary(
            [dep_blocked],
            blocked_by_map={"70": ["69"]},
            id_to_title={"69": "Upstream blocker feature"},
        )
        dep_line = next(line for line in summary.splitlines() if "070" in line)
        self.assertIn("blocked by: 69 (Upstream blocker feature)", dep_line)

    def test_blocked_summary_falls_back_to_bare_id_when_title_unknown(self):
        # A blocker id absent from id_to_title (or a caller passing no map
        # at all) degrades to the bare id rather than raising or dropping
        # the blocker from the line -- ids alone are still strictly better
        # than an empty summary.
        dep_blocked = {"id": "070", "feature": "Dependency-blocked item", "priority": "Medium",
                       "status": "NOT_STARTED", "abbrev": "DOC", "score": 20, "files": []}
        summary = format_blocked_summary(
            [dep_blocked], blocked_by_map={"70": ["69"]}, id_to_title={},
        )
        dep_line = next(line for line in summary.splitlines() if "070" in line)
        self.assertIn("blocked by: 69", dep_line)
        self.assertNotIn("(", dep_line)

    def test_direct_id_lookup_on_a_held_item_still_resolves_via_json(self):
        # The direct-ID path (`/planwise backlog <id>`) skips the selectable
        # table entirely and reads the JSON temp file for item data. A held
        # item must still be resolvable there so the hold can be surfaced --
        # a filter that empties the JSON on a held item's only match makes
        # the direct-ID path fail silently instead of surfacing the hold.
        rows = _row("067", status="BLOCKED", feature="Held item")
        self.write_index(rows)

        out, err = self.run_parse(["--id", "067"])
        self.assertEqual(err, "")

        json_line = next(line for line in out.splitlines() if line.startswith("JSON: "))
        json_path = json_line.removeprefix("JSON: ")
        with open(json_path, encoding="utf-8") as f:
            items = json.load(f)

        self.assertEqual([i["id"] for i in items], ["067"])
        self.assertEqual(items[0]["status"], "BLOCKED")


GENERATED_9COL_HEADER = (
    "|" + "|".join(
        f" {c} " for c in
        ("ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File")
    ) + "|\n"
    + "|" + "|".join(["---"] * 9) + "|\n"
)

LEGACY_7COL_HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)


class TestWidthAgnosticRowReading(unittest.TestCase):
    """The `[!practice]` fixture proof: a 7-column legacy row and a
    9-column generated row (no "## Backlog Items" heading at all, matching
    generate_backlog_index.py's actual output) both yield the same record
    shape with Score and Files correctly populated -- Score at `cells[-2]`,
    Files at `cells[-1]`, no per-width special case beyond the 6-column
    (no-Score) legacy floor."""

    def test_seven_column_legacy_row_score_and_files_correct(self):
        # Recorded result: 1 item, score=42 (int), one file link ("01" -> "x.md").
        content = LEGACY_7COL_HEADER + "| 001 | Legacy feature | High | NOT_STARTED | DOC | 42 | [01](x.md) |\n"
        items = parse_backlog_table(content)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["score"], 42)
        self.assertEqual(item["files"], [{"label": "01", "path": "x.md"}])
        self.assertEqual(item["status"], "NOT_STARTED")
        self.assertEqual(item["feature"], "Legacy feature")

    def test_nine_column_generated_row_score_and_files_correct(self):
        # Recorded result: 1 item, score=77 (int), one file link ("042" -> "x.md") --
        # no "## Backlog Items" heading present anywhere in this content, matching
        # what generate_backlog_index.py actually emits for a hub/leaf/shard.
        content = (
            GENERATED_9COL_HEADER
            + "| 042 | Generated feature | Medium | IN_PROGRESS | DOC | 2024-01-01 |  | 77 | [042](x.md) |\n"
        )
        self.assertNotIn("## Backlog Items", content)
        items = parse_backlog_table(content)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["score"], 77)
        self.assertEqual(item["files"], [{"label": "042", "path": "x.md"}])
        self.assertEqual(item["feature"], "Generated feature")
        self.assertEqual(item["status"], "IN_PROGRESS")

    def test_escaped_pipe_cell_count_matches_header_not_dropped(self):
        # Recorded result: 1 item parses (not malformed); the escaped pipe
        # inside the Feature cell survives unescaped, and the row's cell
        # count still matches the 6-column header exactly.
        content = HEADER + "| 001 | Run `cmd \\| grep x` | Low | NOT_STARTED | DOC | [01](x.md) |\n"
        items = parse_backlog_table(content)
        self.assertEqual(len(items), 1)
        self.assertIn("cmd | grep x", items[0]["feature"])


class TestMalformedRowFailsLoudly(unittest.TestCase):
    """A row whose cell count differs from the header's now aborts the
    parse outright instead of being warned about and silently dropped."""

    def test_malformed_row_cell_count_mismatch_raises_system_exit(self):
        # Header wants 6 cells; this data row carries only 5 (Files is missing).
        content = HEADER + "| 001 | Feature | Low | NOT_STARTED | DOC |\n"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_backlog_table(content)


class TestHubShardResolution(unittest.TestCase):
    """`resolve_closed_item_shard` -- the pure `shard_for`-based guess, and
    the reported (never silent) fallback scan when that guess misses."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_shard_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backlog_dir = self.tmp / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "_index_path": self.backlog_dir / "00-Index-Backlog.md",
            "_backlog_dir": self.backlog_dir,
            "_archive_dir": self.archive_dir,
        }

    def _write_shard(self, filename: str, item_id: str) -> Path:
        path = self.archive_dir / filename
        row = (
            f"| {item_id} | Closed item | Low | CLOSED | DOC | 2024-01-01 |  | - | "
            f"[{item_id}](Archive/BB-{item_id}-x.md) |\n"
        )
        path.write_text(GENERATED_9COL_HEADER + row, encoding="utf-8")
        return path

    def test_computed_guess_hits_a_fully_dense_century_with_no_fallback(self):
        shard_path = self._write_shard("Index-Backlog-001-100.md", "042")
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            resolved, used_fallback = resolve_closed_item_shard("042", self.config)
        self.assertEqual(resolved, shard_path)
        self.assertFalse(used_fallback)
        self.assertEqual(out.getvalue(), "")

    def test_sparse_century_misses_the_guess_and_falls_back_reported(self):
        # The shard's real range (data-driven, per generate_backlog_index.py)
        # doesn't equal the guessed full-century "001-100" filename.
        shard_path = self._write_shard("Index-Backlog-003-097.md", "042")
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            resolved, used_fallback = resolve_closed_item_shard("042", self.config)
        self.assertEqual(resolved, shard_path)
        self.assertTrue(used_fallback)
        self.assertIn("falling back", out.getvalue())

    def test_missing_shard_entirely_reports_fallback_and_returns_none(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            resolved, used_fallback = resolve_closed_item_shard("999", self.config)
        self.assertIsNone(resolved)
        self.assertTrue(used_fallback)
        self.assertIn("falling back", out.getvalue())


class TestNextIdUnionsAcrossHubAndShards(_ParseBacklogFixtureBase):
    """The highest-severity regression this task guards: a hub-only max
    must never reissue an id a closed item already holds in a shard."""

    def test_next_id_considers_a_higher_id_already_closed_in_a_shard(self):
        # Hub: open items 001-050 (legacy 6-column, no Score).
        rows = "".join(_row(f"{i:03d}") for i in range(1, 51))
        self.write_index(rows)

        # Archive shard: closed items 051 and 145 -- a hub-only max would
        # allocate 051 next, colliding with the closed item that already
        # owns it, and would never even see 145.
        archive_dir = self.backlog_dir / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        shard_rows = "".join(
            f"| {i:03d} | Closed item {i} | Low | CLOSED | DOC | 2024-01-01 |  | - | "
            f"[{i:03d}](Archive/BB-{i:03d}-x.md) |\n"
            for i in (51, 145)
        )
        (archive_dir / "Index-Backlog-051-145.md").write_text(
            GENERATED_9COL_HEADER + shard_rows, encoding="utf-8"
        )

        out, err = self.run_next_id()
        self.assertEqual(out, "146")
        self.assertEqual(err, "")

    def test_collect_all_known_ids_unions_hub_and_shard(self):
        rows = "".join(_row(f"{i:03d}") for i in range(1, 4))
        self.write_index(rows)
        archive_dir = self.backlog_dir / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "Index-Backlog-001-100.md").write_text(
            GENERATED_9COL_HEADER
            + "| 099 | Closed item | Low | CLOSED | DOC | 2024-01-01 |  | - | [099](x.md) |\n",
            encoding="utf-8",
        )
        config = {
            "_index_path": self.backlog_dir / "00-Index-Backlog.md",
            "_backlog_dir": self.backlog_dir,
            "_archive_dir": archive_dir,
        }
        ids = collect_all_known_ids(config)
        self.assertEqual(sorted(ids), ["001", "002", "003", "099"])


class TestDisplayTruncationUnchanged(unittest.TestCase):
    """The 55-character display truncation is unrelated to the 120-char
    storage cap and must stay unchanged by this task's other reads."""

    def test_feature_truncated_at_fifty_five_characters_for_display(self):
        long_feature = "x" * 100
        items = [{
            "id": "001", "feature": long_feature, "priority": "Low",
            "status": "NOT_STARTED", "abbrev": "DOC", "score": 0, "files": [],
        }]
        table = format_table(items)
        line = next(line for line in table.splitlines() if line.startswith("001"))
        self.assertIn("x" * 52 + "...", line)
        self.assertNotIn("x" * 53, line)


def _row9(
    item_id: str,
    status: str = "NOT_STARTED",
    feature: str | None = None,
    abbrev: str = "DOC",
    blocks: str = "",
    score: str = "0",
) -> str:
    """One 9-column generated-shape row, matching
    `generate_backlog_index.render_row`'s cell order (ID, Title, Priority,
    Status, Domain, Created, Blocks, Score, File)."""
    feature = feature or f"Feature {item_id}"
    return (
        f"| {item_id} | {feature} | Low | {status} | {abbrev} | 2024-01-01 | "
        f"{blocks} | {score} | [{item_id}](BB-{item_id}-x.md) |\n"
    )


class TestHubFamilyUnionAndShardIdLookup(unittest.TestCase):
    """Code-review corrective, Finding 1: `main()`'s item set is the union
    of every hub-family file, and a `--id` miss against that union resolves
    against an Archive shard rather than reporting the id as nonexistent."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_hubfamily_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        # Hub: one open item.
        (self.backlog_dir / "00-Index-Backlog.md").write_text(
            GENERATED_9COL_HEADER + _row9("001"), encoding="utf-8",
        )
        # Overflow leaf: a second open item, invisible to a hub-only read.
        (self.backlog_dir / "00-Index-Backlog-002-002.md").write_text(
            "[Back to Backlog Index](00-Index-Backlog.md)\n\n"
            + GENERATED_9COL_HEADER + _row9("002"),
            encoding="utf-8",
        )
        # Archive shard: a closed item, at a range that misses the pure
        # century guess -- forces the fallback scan, still a live path.
        (self.archive_dir / "Index-Backlog-100-100.md").write_text(
            GENERATED_9COL_HEADER + _row9("100", status="CLOSED", score="-"),
            encoding="utf-8",
        )

    def run_parse(self, extra_args: list[str]) -> tuple[str, str]:
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path), *extra_args]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue()

    def _json_from(self, stdout: str) -> list[dict]:
        json_line = next(line for line in stdout.splitlines() if line.startswith("JSON: "))
        json_path = json_line[len("JSON: "):].strip()
        return json.loads(Path(json_path).read_text(encoding="utf-8"))

    def test_leaf_item_is_visible_to_a_direct_id_lookup(self):
        out, _err = self.run_parse(["--id", "002"])
        records = self._json_from(out)
        self.assertEqual([r["id"] for r in records], ["002"])

    def test_leaf_item_is_visible_to_an_ordinary_filter(self):
        out, _err = self.run_parse(["--abbrev", "DOC"])
        records = self._json_from(out)
        self.assertEqual(sorted(r["id"] for r in records), ["001", "002"])

    def test_shard_item_resolves_the_same_record_shape_as_a_hub_item(self):
        hub_out, _ = self.run_parse(["--id", "001"])
        shard_out, shard_err = self.run_parse(["--id", "100", "--include-closed"])

        hub_records = self._json_from(hub_out)
        shard_records = self._json_from(shard_out)

        self.assertEqual([r["id"] for r in shard_records], ["100"])
        self.assertEqual(sorted(hub_records[0].keys()), sorted(shard_records[0].keys()))
        self.assertIn("falling back", shard_err)


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


if __name__ == "__main__":
    unittest.main()
