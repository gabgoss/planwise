#!/usr/bin/env python3
"""`score_backlog.py --route` reports each item's open blockers.

The route letter says how an item would be worked. The open-blocker gate says
whether it may be worked at all, so the report carries both and the route
stays unchanged. Every fixture index here is rendered by the real producer,
`generate_backlog_index.py --write`, including an Archive shard.

Run with:  python -m pytest tests/test_route_open_blockers.py
"""

import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import score_backlog
from generate_backlog_index_fixtures import _GeneratorFixtureBase

PARENT = "100"
FIRST_SUB = "101"
SECOND_SUB = "102"
FREE = "103"

# Two numbered steps and enough lines to keep the item out of the short branch.
BODY = "\n## Steps\n\n1. First step.\n2. Second step.\n" + ("\nfiller\n" * 30)


class _RouteBlockerBase(_GeneratorFixtureBase):
    def build(self, first_status: str, second_status: str, *, first_archived: bool = False) -> None:
        """The parent, its two sub-items and one unrelated item, then the index."""
        self.write_item(PARENT, title="Parent", body=BODY)
        self.write_item(
            FIRST_SUB, title="First sub", status=first_status, blocks=[PARENT],
            archived=first_archived, body=BODY,
        )
        self.write_item(
            SECOND_SUB, title="Second sub", status=second_status, blocks=[PARENT],
            archived=True, body=BODY,
        )
        self.write_item(FREE, title="Free", body=BODY)
        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 0, err)
        shards = list(self.archive_dir.glob("*Index*.md"))
        self.assertTrue(shards, "the producer wrote no Archive shard")

    def run_score(self, *args: str) -> str:
        sys.argv = ["score_backlog", "--config", str(self.config_path), *args]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                score_backlog.main()
            except SystemExit as exc:
                self.fail(f"score_backlog exited {exc.code}: {err.getvalue()}")
        return out.getvalue()

    def detail(self, item_id: str) -> list[str]:
        return self.run_score("--route", "--id", item_id).splitlines()

    def route_line(self, item_id: str) -> str:
        rows = [line for line in self.run_score("--route").splitlines() if line.startswith(f"  ID {item_id} ")]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def json_payload(self, *args: str):
        out = self.run_score("--route", "--json", *args)
        printed = next(line for line in out.splitlines() if line.startswith("JSON: "))
        path = Path(printed[len("JSON: "):])
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        return json.loads(path.read_text(encoding="utf-8"))


class TestRouteWithAnOpenBlocker(_RouteBlockerBase):
    def setUp(self):
        super().setUp()
        self.build("NOT_STARTED", "COMPLETE")

    def test_detail_names_the_blocker_after_the_branch_line(self):
        lines = self.detail(PARENT)
        expected = f"  open_blockers:     {FIRST_SUB} -> NOT ROUTABLE until each blocker closes"
        self.assertIn(expected, lines)
        branch = next(i for i, line in enumerate(lines) if line.startswith("  branch:"))
        self.assertEqual(lines[branch + 1], expected)

    def test_json_reads_not_routable_for_one_item_and_for_the_listing(self):
        one = self.json_payload("--id", PARENT)
        self.assertEqual(one["open_blockers"], [FIRST_SUB])
        self.assertIs(one["routable"], False)
        listed = {row["id"]: row for row in self.json_payload()}
        self.assertEqual(listed[PARENT]["open_blockers"], [FIRST_SUB])
        self.assertIs(listed[PARENT]["routable"], False)
        self.assertIs(listed[FREE]["routable"], True)

    def test_route_line_counts_the_blocker(self):
        self.assertRegex(self.route_line(PARENT), r" ref=n blk=1 files=\d+ ")

    def test_the_route_letter_does_not_change(self):
        blocked = self.json_payload("--id", PARENT)
        free = self.json_payload("--id", FREE)
        self.assertEqual(blocked["route"], free["route"])
        self.assertEqual(blocked["branch"], free["branch"])

    def test_item_with_no_blocker_reads_none(self):
        self.assertIn("  open_blockers:     none", self.detail(FREE))
        self.assertIn(" blk=- ", self.route_line(FREE))

    def test_legend_names_the_column_and_the_computed_gate(self):
        out = self.run_score("--route")
        self.assertIn("blk = ", out)
        self.assertIn("open-blocker gate", out)


class TestRouteAfterTheBlockersClose(_RouteBlockerBase):
    def test_closed_sub_items_unblock_the_parent_with_one_archived(self):
        self.build("COMPLETE", "COMPLETE")
        self.assertIn("  open_blockers:     none", self.detail(PARENT))
        self.assertIs(self.json_payload("--id", PARENT)["routable"], True)
        self.assertIn(" blk=- ", self.route_line(PARENT))


class TestRouteSpellsABlockerAsItsRowDoes(_RouteBlockerBase):
    def test_a_zero_padded_blocker_keeps_its_padding(self):
        self.write_item("012", title="Waits", body=BODY)
        self.write_item("007", title="Blocks", blocks=["012"], body=BODY)
        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 0, err)
        self.assertIn("  open_blockers:     007 -> NOT ROUTABLE until each blocker closes", self.detail("012"))
        self.assertEqual(self.json_payload("--id", "012")["open_blockers"], ["007"])


class TestRouteSignalsWithoutTheMap(unittest.TestCase):
    def test_a_direct_call_without_the_keyword_reads_not_computed(self):
        item = {"id": PARENT, "abbrev": "DOC"}
        signals = score_backlog.compute_route_signals(item, {"_body": BODY, "_line_count": 70})
        self.assertIsNone(signals["open_blockers"])
        self.assertIsNone(signals["routable"])
        self.assertIn("  open_blockers:     (not computed)", score_backlog.format_route_detail(signals, 0))
        self.assertIn(" blk=- ", score_backlog.format_route_line(signals, 0))


if __name__ == "__main__":
    unittest.main()
