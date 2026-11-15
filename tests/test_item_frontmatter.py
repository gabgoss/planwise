#!/usr/bin/env python3
"""Unit tests for item_frontmatter.py, the frontmatter readers score_backlog re-exports.

Each moved name must be the same object through both modules, so every
`from score_backlog import X` keeps working. One round trip reads the same
fixture through both modules and expects the same dict.

Run with:  python -m pytest tests/test_item_frontmatter.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import item_frontmatter
import score_backlog

MOVED_NAMES = ("read_item_frontmatter", "_text_level_scoring_fields", "_strip_inline_comment")


class TestReExportIdentity(unittest.TestCase):
    def test_each_moved_name_is_the_same_object_in_both_modules(self):
        for name in MOVED_NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(item_frontmatter, name), getattr(score_backlog, name))


class TestRoundTrip(unittest.TestCase):
    def test_same_fixture_reads_the_same_dict_through_both_modules(self):
        tmp = Path(tempfile.mkdtemp(prefix="item_frontmatter_test_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "item.md"
        path.write_text(
            "---\nid: 081\ncreated: 2026-08-12  # filed\nblocks: [007, 009]  # two\n"
            "refined: true\n---\n\n# Body\n",
            encoding="utf-8",
        )

        via_module = item_frontmatter.read_item_frontmatter(path)
        via_router = score_backlog.read_item_frontmatter(path)

        self.assertEqual(via_module, via_router)
        self.assertEqual(via_module["blocks"], ["007", "009"])
        self.assertIn("# Body", via_module["_body"])


if __name__ == "__main__":
    unittest.main()
