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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import parse_backlog  # noqa: E402
from parse_backlog import (  # noqa: E402
    FilterCriteria,
    build_blocked_by_map,
    filter_items,
    parse_backlog_table,
    parse_dependencies_table,
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


if __name__ == "__main__":
    unittest.main()
