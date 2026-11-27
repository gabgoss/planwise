#!/usr/bin/env python3
"""Backlog-index generator tests: the item scan and the `blocks:` graph.

These tests pin: an unresolvable `blocks:` entry aborting generation; a
reciprocal edge, a longer cycle and an inverted edge being reported; the
scanner skipping the generator's own artifacts and refusing a duplicate item
id; inline comments stripped at the read sites; and the scan overrides that
stand in for an invalid on-disk block.

Split from `test_generate_backlog_index.py`, whose docstring maps every moved
class to its file.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index_scan.py
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
from generate_backlog_index_fixtures import (
    _GeneratorFixtureBase,
)


class TestUnresolvableBlocksAborts(_GeneratorFixtureBase):
    """A `blocks:` entry naming no scanned item is a data error, never a
    silent drop -- generation must abort naming both the file and the id,
    in every mode, with no index file written."""

    def test_write_mode_refuses_naming_file_and_id(self):
        path = self.write_item("001", title="Dangling blocker", blocks=["999"])

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn(str(path), err)
        self.assertIn("999", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_report_mode_also_refuses(self):
        self.write_item("001", title="Dangling blocker", blocks=["999"])

        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 2)
        self.assertIn("999", err)


class TestReciprocalBlocksEdge(_GeneratorFixtureBase):
    """A reciprocal blocks: edge (A blocks B and B blocks A) is reported,
    never silently accepted or reversed. Report modes still reach
    measurement; only --write treats it as refused."""

    def setUp(self):
        super().setUp()
        self.write_item("007", title="A", blocks=["009"])
        self.write_item("009", title="B", blocks=["007"])

    def test_report_mode_exits_one_and_still_measures(self):
        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("reciprocal blocks edge", err)
        # Measurement still ran -- the report-mode disposition never
        # short-circuits before build_index_files.
        self.assertIn("00-Index-Backlog.md", out)

    def test_write_mode_refuses_and_writes_nothing(self):
        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("reciprocal blocks edge", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())


class TestBlocksCycles(_GeneratorFixtureBase):
    """A cycle of three or more ids is reported with its full path. A reciprocal pair is still reported as a pair."""

    def test_three_item_cycle_is_reported_with_its_full_path(self):
        self.write_item("001", title="A", blocks=["002"])
        self.write_item("002", title="B", blocks=["003"])
        self.write_item("003", title="C", blocks=["001"])

        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("blocks cycle -- 001 -> 002 -> 003 -> 001", err)
        self.assertNotIn("reciprocal blocks edge", err)
        self.assertIn("00-Index-Backlog.md", out)  # measurement still ran

    def test_three_item_cycle_refuses_write_and_writes_nothing(self):
        self.write_item("001", title="A", blocks=["002"])
        self.write_item("002", title="B", blocks=["003"])
        self.write_item("003", title="C", blocks=["001"])

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("blocks cycle -- 001 -> 002 -> 003 -> 001", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_pair_and_cycle_in_one_graph_are_each_reported_once(self):
        graph = {
            "001": {"002"}, "002": {"003"}, "003": {"001"},
            "010": {"011"}, "011": {"010"},
            "020": {"021", "022"}, "021": {"022"}, "022": {"023"}, "023": {"020"},
            "030": set(),
        }

        self.assertEqual(gbi.detect_reciprocal_edges(graph), [("010", "011")])
        # The chord 020 -> 022 makes a second, shorter cycle through the same four ids.
        self.assertEqual(
            gbi.detect_blocks_cycles(graph),
            [["001", "002", "003"], ["020", "021", "022", "023"], ["020", "022", "023"]],
        )

    def test_acyclic_graph_reports_no_cycle(self):
        graph = {"001": {"002", "003"}, "002": {"003"}, "003": set()}

        self.assertEqual(gbi.detect_blocks_cycles(graph), [])

    def test_a_long_chain_does_not_reach_the_recursion_limit(self):
        ids = [f"{n:04d}" for n in range(3000)]
        graph = {ids[n]: {ids[n + 1]} for n in range(2999)}
        graph[ids[-1]] = {ids[0]}

        cycles = gbi.detect_blocks_cycles(graph)

        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]), 3000)


class TestInvertedBlocksEdge(_GeneratorFixtureBase):
    """An item whose prose waits on N, while its own `blocks:` lists N, has the edge written backwards."""

    def test_the_three_items_as_filed_each_report_the_inverted_id(self):
        self.write_item("703", title="Prerequisite estimate checker")
        self.write_item("727", title="Prerequisite install check")
        self.write_item(
            "704", title="Review layer", blocks=["703"],
            body="\n## Summary\n\nSub-item 2 of a parent. It is blocked by BB-703, which creates a script.\n",
        )
        self.write_item(
            "728", title="Doctor advisory", blocks=["727"],
            body="\n## Summary\n\nThis item adds a line. It depends on the `install_check` module from BB-727.\n",
        )
        self.write_item(
            "729", title="Upgrade warning", blocks=["727"],
            body="\n## Related\n\n- Blocked by BB-727 (provides `scripts/install_check.py`)\n",
        )

        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("inverted blocks edge -- 704", err)
        self.assertIn("waits on 703", err)
        self.assertIn("inverted blocks edge -- 728", err)
        self.assertIn("inverted blocks edge -- 729", err)
        self.assertIn("Move 703 out of 704's blocks:", err)
        self.assertIn("Direction check: scanned 5 items, 3 inverted edge(s)", out)

    def test_a_correct_direction_reports_nothing_and_prints_the_scan_count(self):
        self.write_item(
            "010", title="Prerequisite", blocks=["011"],
            body="\n## Summary\n\nThis is the prerequisite for the next item.\n",
        )
        self.write_item(
            "011", title="Dependent",
            body="\n## Summary\n\nThis item is blocked by BB-010.\n",
        )

        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 0)
        self.assertNotIn("inverted blocks edge", err)
        self.assertIn("Direction check: scanned 2 items, 0 inverted edge(s)", out)

    def test_quoted_evidence_fenced_and_other_section_phrases_do_not_raise_it(self):
        self.write_item("020", title="Target")
        body = (
            "\n## Summary\n\n"
            "> The user wrote: this is blocked by BB-020.\n\n"
            "**Evidence:** an older copy said it depends on BB-020.\n"
            "- the same copy was blocked by BB-020 in a continued line\n\n"
            "```\nblocked by BB-020\n```\n\n"
            "## Proposed Solution\n\nThis step waits for BB-020 in the new design.\n"
        )
        self.write_item("021", title="Holder", blocks=["020"], body=body)

        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 0)
        self.assertNotIn("inverted blocks edge", err)
        self.assertIn("scanned 2 items, 0 inverted edge(s)", out)

    def test_a_phrase_in_the_next_sentence_does_not_lend_its_id(self):
        ids = gbi.extract_waiting_ids("## Summary\n\nIt depends on the loader. The follow-up is BB-020.\n")

        self.assertEqual(ids, [])

    def test_a_list_of_ids_after_one_phrase_is_read_whole(self):
        ids = gbi.extract_waiting_ids("## Summary\n\nIt is blocked by BB-020, BB-21 and BB-022.\n")

        self.assertEqual(ids, ["020", "021", "022"])

    def test_write_reports_an_inverted_edge_and_still_writes(self):
        self.write_item("703", title="Prerequisite")
        self.write_item(
            "704", title="Dependent", blocks=["703"],
            body="\n## Summary\n\nIt is blocked by BB-703.\n",
        )

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertIn("inverted blocks edge -- 704", err)
        self.assertTrue((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_check_exits_one_on_an_inverted_edge_after_a_clean_write(self):
        self.write_item("703", title="Prerequisite")
        self.write_item("704", title="Dependent", blocks=["703"], body="\n## Summary\n\nIt waits for BB-703.\n")
        self.run_main("--write")

        code, out, err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("inverted blocks edge -- 704", err)
        self.assertIn("inverted blocks edge -- 704", out)

    def test_a_related_line_whose_object_is_this_item_is_not_flagged(self):
        self.write_item(
            "101", title="Parent", blocks=["102", "103"],
            body=(
                "\n## Related\n\n"
                "- [BB-102-01-X.md](BB-102-01-X.md) - sub-item 2; waits for this item (same file edit as BB-103)\n"
            ),
        )
        self.write_item("102", title="Sub-item two")
        self.write_item("103", title="Sub-item three")
        self.run_main("--write")

        code, out, err = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertNotIn("inverted blocks edge", err)
        self.assertIn("0 inverted edge(s)", out)

    def test_waits_on_is_a_waiting_phrase(self):
        self.write_item("703", title="Prerequisite")
        self.write_item("704", title="Dependent", blocks=["703"], body="\n## Summary\n\nIt waits on BB-703.\n")

        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("inverted blocks edge -- 704", err)

    def test_a_phrase_whose_object_is_this_item_lends_no_id(self):
        ids = gbi.extract_waiting_ids("## Summary\n\nBB-051 is blocked by this item; BB-052 also reads it.\n")

        self.assertEqual(ids, [])


class TestScannerSkipsOwnGeneratedArtifacts(_GeneratorFixtureBase):
    """`is_generated_index_file` must be invisible to the scanner (so a
    second run never re-ingests its own shard as an item), while an
    ordinary frontmatter-less item-like file still aborts the scan by
    name -- the filter is scoped to this module's own naming shape, not
    "any file lacking frontmatter"."""

    def test_predicate_matches_only_this_modules_own_shapes(self):
        self.assertTrue(gbi.is_generated_index_file("Index-Backlog-001-100.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog-101-200.md"))
        self.assertFalse(gbi.is_generated_index_file("BB-500-01-BUG-NoFrontmatter.md"))

    def test_shard_named_file_skipped_ordinary_file_aborts(self):
        self.write_item("999", title="Real archived item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-999-01-PROC-Fixture.md")
        (self.archive_dir / "Index-Backlog-001-100.md").write_text(
            "not a real item\n", encoding="utf-8"
        )

        index_path = self.backlog_dir / "00-Index-Backlog.md"
        items = gbi.scan_backlog(self.backlog_dir, self.archive_dir, index_path)
        self.assertEqual([i["id"] for i in items], ["999"])

        (self.archive_dir / "BB-500-01-BUG-NoFrontmatter.md").write_text(
            "also not a real item\n", encoding="utf-8"
        )
        with self.assertRaises(gbi.GeneratorError) as ctx:
            gbi.scan_backlog(self.backlog_dir, self.archive_dir, index_path)
        self.assertIn("BB-500-01-BUG-NoFrontmatter.md", str(ctx.exception))


class TestDuplicateItemIdRefusedAtScan(_GeneratorFixtureBase):
    """CR1 (pre-commit review, Finding 1): two item files sharing one id
    must refuse at scan time, before any row renders, naming both paths
    and the id -- never silently emitting two rows for it (the old
    `--write` behavior) or surfacing as a raw `KeyError` (the old
    `--check` behavior)."""

    def setUp(self):
        super().setUp()
        self.path_a = self.write_item("003", title="A copy", filename="BB-003-01-BUG-A.md")
        self.path_b = self.write_item(
            "003", title="B copy", priority="Low", status="COMPLETE", abbrev="PROC",
            created="2025-01-01", archived=True, filename="BB-003-02-PROC-B.md",
        )

    def test_check_refuses_naming_both_paths_and_id(self):
        code, _out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("003", err)
        self.assertIn(str(self.path_a), err)
        self.assertIn(str(self.path_b), err)
        # The report names the renumber fix and its --file option.
        self.assertIn('reconcile_backlog.py" --renumber 003 <next free id> --file ', err)

    def test_write_refuses_and_writes_no_hub(self):
        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_dry_run_refuses(self):
        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


class TestGeneratedFilePatternCoversFourDigitIds(_GeneratorFixtureBase):
    """CR2 (Finding 2): the generated-file pattern must recognize a
    4+-digit id range (`\\d{3,}`), not just the 3-digit `:03d` shape a
    too-narrow `\\d{3}` pattern produced -- a closed item with id >= 1000
    used to have its own shard re-ingested as a frontmatter-less item on
    the very next run, aborting `--check` forever after."""

    def test_pattern_matches_four_digit_ranges(self):
        self.assertTrue(gbi.is_generated_index_file("Index-Backlog-1000-1000.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog-1000-1042.md"))

    def test_write_then_check_stays_clean_for_a_four_digit_id(self):
        self.write_item("001", title="Open item")
        self.write_item("1000", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-1000-01-PROC-Fixture.md")

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertTrue((self.archive_dir / "Index-Backlog-1000-1000.md").exists())

        code, _out, _err = self.run_main("--check")
        self.assertEqual(code, 0)


class TestInlineCommentStrippedAtReadSites(_GeneratorFixtureBase):
    """Pre-write repair, Execution Step 3: a YAML inline comment on
    `blocks:`/`created:`/`id:` must not survive into the generator's own
    frontmatter read, ported from `score_backlog._strip_inline_comment`.
    Mirrors that module's own two tests -- the generator's edge set and age
    inputs must equal the scorer's on every item."""

    def test_inline_comment_after_blocks_flow_form_keeps_every_edge(self):
        path = self.backlog_dir / "BB-081-01-BUG-Fixture.md"
        path.write_text(
            "---\nid: 081\ntitle: Fixture item\npriority: Medium\n"
            "status: NOT_STARTED\nabbrev: BUG\ncreated: 2026-01-01\n"
            "blocks: [007, 009]  # two\n---\n\n# Body\n",
            encoding="utf-8",
        )
        fields = gbi._scan_one_file(path)
        self.assertEqual(fields["blocks"], ["007", "009"])

    def test_inline_comment_after_created_keeps_the_age_input(self):
        path = self.backlog_dir / "BB-082-01-BUG-Fixture.md"
        path.write_text(
            "---\nid: 082\ntitle: Fixture item\npriority: Medium\n"
            "status: NOT_STARTED\nabbrev: BUG\ncreated: 2026-01-15  # filed\n"
            "blocks: []\n---\n\n# Body\n",
            encoding="utf-8",
        )
        fields = gbi._scan_one_file(path)
        self.assertEqual(fields["created"], "2026-01-15")


class TestScanBacklogOverridesSkipInvalidDisk(_GeneratorFixtureBase):
    """`overrides` lets a caller plan a frontmatter backfill in memory and
    scan the planned result -- proven here by an on-disk block that is
    itself invalid (missing `created`, so a plain disk read would raise):
    the override's fields are what `scan_backlog` yields, so the disk was
    never actually read for this file."""

    def test_override_used_instead_of_invalid_disk_block(self):
        path = self.write_item("001", title="On-disk broken", priority="High",
                                status="NOT_STARTED", abbrev="BUG")
        text = path.read_text(encoding="utf-8")
        broken_text = "\n".join(
            line for line in text.split("\n") if not line.startswith("created:")
        )
        path.write_text(broken_text, encoding="utf-8")
        index_path = self.backlog_dir / "00-Index-Backlog.md"

        with self.assertRaises(gbi.GeneratorError):
            gbi.scan_backlog(self.backlog_dir, self.archive_dir, index_path)

        override_text = (
            "---\nid: 001\ntitle: Override title\npriority: High\n"
            "status: NOT_STARTED\nabbrev: BUG\ncreated: 2026-02-02\n"
            "blocks: []\n---\n\n# Override title\n"
        )
        items = gbi.scan_backlog(
            self.backlog_dir, self.archive_dir, index_path,
            overrides={path.resolve(): override_text},
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Override title")
        self.assertEqual(items[0]["created"], "2026-02-02")


if __name__ == "__main__":
    unittest.main()
