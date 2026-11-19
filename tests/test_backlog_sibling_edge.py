#!/usr/bin/env python3
"""Pins for the sibling-dependency edge direction in the backlog planner and author.

A sub-item that waits on a sibling is filed with the edge on the prerequisite:
the prerequisite's `blocks:` lists the dependent, never the other way round.
Two groups of tests pin that:

  SiblingEdgeTextPins   the new wording on six shipped plugin files
  SiblingEdgeLoopRun    the backlog loop on a two-sibling result, in two shapes

Fixture items (the parent is 020, the siblings are A = 021 and B = 022, B waits for A):

  correct   021 blocks [020, 022], 022 blocks [020]   -> queue 021, 022 dropped as blocked
  inverted  021 blocks [020], 022 blocks [020, 021]   -> queue 022, 021 dropped as blocked

The inverted shape is the one the incident items had. The two runs differ, so the
loop test can fail.

Run with:  python -m pytest tests/test_backlog_sibling_edge.py -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_backlog_loop import _LoopFixtureBase, item_filename

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# file under the plugin root -> (literals it holds, literals it must not hold)
PINS = {
    "agents/backlog-planner.md": (
        (
            "| {criteria} | {after}",
            "earlier `SUB_ITEMS` line only",
            "for every sub-item that waits on a sibling",
        ),
        ("The parts are independent",),
    ),
    "agents/backlog-author.md": (
        (
            "File every sub-item first",
            "prerequisite's `blocks:`",
            "Never add the prerequisite to the dependent's own `blocks:`",
        ),
        (),
    ),
    "templates/backlog-item.md": (("B waits for A", "in A's file"), ()),
    "references/backlog-schema.md": (("B waits for A", "in A's file"), ()),
    "references/backlog-creation-process.md": (("prerequisite sibling",), ()),
    "handlers/backlog-Part-2-LoopMode.md": (("prerequisite sibling",), ()),
}


class SiblingEdgeTextPins(unittest.TestCase):
    def test_each_file_holds_its_literals(self):
        for rel, (present, absent) in PINS.items():
            text = (PLUGIN / rel).read_text(encoding="utf-8")
            for literal in present:
                with self.subTest(file=rel, holds=literal):
                    self.assertIn(literal, text)
            for literal in absent:
                with self.subTest(file=rel, lacks=literal):
                    self.assertNotIn(literal, text)


class _SiblingFixture(_LoopFixtureBase):
    def add_item(self, item_id: str, blocks: list[str]) -> Path:
        """Write one open item with a `blocks:` line and append its hub row."""
        cell = "[" + ", ".join(blocks) + "]" if blocks else ""
        lines = [
            "---",
            f"id: {item_id}",
            "status: NOT_STARTED",
            f"blocks: {cell or '[]'}",
            "---",
            "",
            f"# Item {item_id}",
            "",
            "A small, well-bounded change to one helper.",
        ]
        path = self.backlog_dir / item_filename(item_id)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        index = self.backlog_dir / "00-Index-Backlog.md"
        row = (
            f"| {item_id} | Fixture {item_id} | Low | NOT_STARTED | INFRA | 2026-10-01 | "
            f"{cell} | 0 | [01]({item_filename(item_id)}) |\n"
        )
        index.write_text(index.read_text(encoding="utf-8") + row, encoding="utf-8")
        return path


class SiblingEdgeLoopRun(_SiblingFixture):
    def run_siblings(self, a_blocks: list[str], b_blocks: list[str]) -> dict:
        self.add_item("020", [])
        self.add_item("021", a_blocks)
        self.add_item("022", b_blocks)
        code, _text, payload = self.loop(
            "--init", "--mode", "specific", "--items", "021,022", "--dry-run"
        )
        self.assertEqual(code, 0, payload)
        return payload

    def test_the_prerequisite_is_queued_and_the_dependent_waits(self):
        payload = self.run_siblings(["020", "022"], ["020"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["021"])
        self.assertIn("warning: item 022 dropped: blocked by 021 (open)", payload["warnings"])

    def test_an_inverted_edge_queues_the_dependent(self):
        payload = self.run_siblings(["020"], ["020", "021"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["022"])
        self.assertIn("warning: item 021 dropped: blocked by 022 (open)", payload["warnings"])


class DropWarningNamesBlockers(_SiblingFixture):
    """The `--init` drop warning names the open blockers, or says the item is on hold."""

    def run_named(self, items: str) -> dict:
        code, _text, payload = self.loop("--init", "--mode", "specific", "--items", items, "--dry-run")
        self.assertEqual(code, 0, payload)
        return payload

    def test_the_three_items_as_filed_name_both_blockers_and_the_direction(self):
        # BB-728 and BB-729 each list 727, and 727 lists nothing: the inverted shape.
        self.add_item("727", [])
        self.add_item("728", ["727"])
        self.add_item("729", ["727"])
        payload = self.run_named("727,728,729")
        self.assertIn("warning: item 727 dropped: blocked by 728, 729 (open)", payload["warnings"])
        self.assertIn(
            "note: 727 is blocked by 728, 729, which you also named. "
            "If 727 must land first, check the blocks: direction.",
            payload["warnings"],
        )
        self.assertEqual([q["id"] for q in payload["queue"]], ["728", "729"])

    def test_a_blocker_that_is_not_named_gets_no_direction_note(self):
        self.add_item("020", [])
        self.add_item("021", ["022"])
        self.add_item("022", [])
        payload = self.run_named("020,022")
        self.assertEqual(payload["warnings"], ["warning: item 022 dropped: blocked by 021 (open)"])

    def test_a_held_item_says_on_hold_with_its_status(self):
        path = self.add_item("030", [])
        path.write_text(path.read_text(encoding="utf-8").replace("NOT_STARTED", "BLOCKED"), encoding="utf-8", newline="\n")
        index = self.backlog_dir / "00-Index-Backlog.md"
        text = index.read_text(encoding="utf-8")
        index.write_text(text.replace("| 030 | Fixture 030 | Low | NOT_STARTED", "| 030 | Fixture 030 | Low | BLOCKED"), encoding="utf-8")
        self.add_item("031", [])
        payload = self.run_named("030,031")
        self.assertEqual(payload["warnings"], ["warning: item 030 dropped: on hold (status BLOCKED)"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["031"])


if __name__ == "__main__":
    unittest.main()
