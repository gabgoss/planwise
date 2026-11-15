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


class SiblingEdgeLoopRun(_LoopFixtureBase):
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
        self.assertIn("warning: item 022 dropped: blocked or on hold", payload["warnings"])

    def test_an_inverted_edge_queues_the_dependent(self):
        payload = self.run_siblings(["020"], ["020", "021"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["022"])
        self.assertIn("warning: item 021 dropped: blocked or on hold", payload["warnings"])


if __name__ == "__main__":
    unittest.main()
