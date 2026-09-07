#!/usr/bin/env python3
"""Unit tests for frontmatter_parser.py, the shared frontmatter primitives.

Before consolidation the same frontmatter parse was implemented independently
in four scripts, and the copies did not agree: some returned a
(frontmatter, body) tuple and one a parsed dict; one signalled absence with
None and another with an empty dict; one stripped a leading BOM and the rest
did not. A caller could not be moved from one to another without reading
both, and a fix to one copy's malformed-input handling did not propagate.

Two split functions survive on purpose, because the tree needs two policies.
The class `TestTheTwoSplitsDiffer` pins the differences the module docstring
documents, so the variance stays deliberate and visible instead of drifting
back apart.

Run with:  python -m pytest tests/test_frontmatter_parser.py -q
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from frontmatter_parser import (  # noqa: E402
    BOM_CHAR,
    parse_frontmatter_map,
    split_frontmatter_block,
    split_frontmatter_without_paths,
)


WELLFORMED = "---\nid: 081\npaths: .claude/rules/*.md\n---\n\n# Body\n"


class TestSplitFrontmatterBlock(unittest.TestCase):
    """The faithful primitive: verbatim frontmatter, None on absence."""

    def test_wellformed_block_splits_verbatim(self):
        self.assertEqual(
            split_frontmatter_block(WELLFORMED),
            ("id: 081\npaths: .claude/rules/*.md", "\n# Body\n"),
        )

    def test_paths_key_is_kept(self):
        """Unlike the normalization split, this one removes nothing."""
        frontmatter, _ = split_frontmatter_block(WELLFORMED)
        self.assertIn("paths:", frontmatter)

    def test_leading_bom_is_tolerated(self):
        self.assertEqual(
            split_frontmatter_block(BOM_CHAR + WELLFORMED),
            ("id: 081\npaths: .claude/rules/*.md", "\n# Body\n"),
        )

    def test_missing_opening_delimiter_returns_none(self):
        self.assertIsNone(split_frontmatter_block("# Just a body\n"))

    def test_unterminated_block_returns_none(self):
        self.assertIsNone(split_frontmatter_block("---\nid: 081\nno closing fence\n"))

    def test_a_zero_length_block_is_not_recognized_as_a_block(self):
        """The closing-delimiter search starts at offset 4, past the opening
        `---\\n`, so `---\\n---\\n` leaves no room for one and reads as absence.
        The shortest recognized block therefore carries at least one
        character. Pinned because `score_backlog` relies on it: such a file
        must score as "no frontmatter", not as an empty-but-present block."""
        self.assertIsNone(split_frontmatter_block("---\n---\nbody\n"))

    def test_a_value_containing_three_dashes_does_not_truncate(self):
        """The delimiter search requires a full "\\n---\\n" line, so a value
        that merely contains "---" cannot end the block early."""
        content = '---\ntitle: "a---b"\nid: 081\n---\n\n# Body\n'
        frontmatter, body = split_frontmatter_block(content)
        self.assertEqual(frontmatter, 'title: "a---b"\nid: 081')
        self.assertEqual(body, "\n# Body\n")


class TestSplitFrontmatterWithoutPaths(unittest.TestCase):
    """The rule-normalization split: drops `paths:`, (None, content) on absence."""

    def test_paths_line_is_removed_and_trailing_space_stripped(self):
        self.assertEqual(
            split_frontmatter_without_paths(WELLFORMED), ("id: 081", "\n# Body\n")
        )

    def test_block_without_a_paths_key_is_returned_intact(self):
        self.assertEqual(
            split_frontmatter_without_paths("---\nid: 081\n---\nbody\n"),
            ("id: 081", "body\n"),
        )

    def test_a_paths_only_block_collapses_to_empty_string(self):
        self.assertEqual(
            split_frontmatter_without_paths("---\npaths: x\n---\nbody\n"),
            ("", "body\n"),
        )

    def test_absence_returns_none_and_the_original_content(self):
        content = "# Just a body\n"
        self.assertEqual(split_frontmatter_without_paths(content), (None, content))

    def test_unterminated_block_returns_none_and_the_original_content(self):
        content = "---\nid: 081\nno closing fence\n"
        self.assertEqual(split_frontmatter_without_paths(content), (None, content))

    def test_only_the_first_paths_line_is_removed(self):
        frontmatter, _ = split_frontmatter_without_paths(
            "---\npaths: one\npaths: two\n---\nbody\n"
        )
        self.assertEqual(frontmatter, "paths: two")


class TestTheTwoSplitsDiffer(unittest.TestCase):
    """Pin the three documented differences, so they stay deliberate.

    These are the contract variance the consolidation preserved rather than
    erased: collapsing the two would silently change a rule-divergence
    comparison verdict on one side and lose BOM tolerance on the other.
    """

    def test_absence_signals_differ(self):
        content = "# No frontmatter\n"
        self.assertIsNone(split_frontmatter_block(content))
        self.assertEqual(split_frontmatter_without_paths(content), (None, content))

    def test_paths_handling_differs(self):
        kept, _ = split_frontmatter_block(WELLFORMED)
        dropped, _ = split_frontmatter_without_paths(WELLFORMED)
        self.assertIn("paths:", kept)
        self.assertNotIn("paths:", dropped)

    def test_bom_handling_differs(self):
        bommed = BOM_CHAR + WELLFORMED
        self.assertIsNotNone(split_frontmatter_block(bommed))
        # The normalization split reads a BOM'd file as having no frontmatter.
        self.assertEqual(split_frontmatter_without_paths(bommed), (None, bommed))


class TestParseFrontmatterMap(unittest.TestCase):
    def test_scalar_keys_map_to_stripped_values(self):
        self.assertEqual(
            parse_frontmatter_map("id: 081\nstatus:   NOT_STARTED  "),
            {"id": "081", "status": "NOT_STARTED"},
        )

    def test_blank_lines_are_skipped(self):
        self.assertEqual(
            parse_frontmatter_map("id: 081\n\n\nstatus: OPEN\n"),
            {"id": "081", "status": "OPEN"},
        )

    def test_list_items_append_to_the_key_above_them(self):
        self.assertEqual(
            parse_frontmatter_map("blocks:\n  - 143\n  - 185\n"),
            {"blocks": "\n  - 143\n  - 185"},
        )

    def test_two_different_multiline_values_never_compare_equal(self):
        one = parse_frontmatter_map("blocks:\n  - 143\n")
        two = parse_frontmatter_map("blocks:\n  - 185\n")
        self.assertNotEqual(one, two)

    def test_a_leading_continuation_with_no_key_is_unparseable(self):
        self.assertIsNone(parse_frontmatter_map("  - orphaned\nid: 081\n"))

    def test_an_empty_block_parses_to_an_empty_map(self):
        self.assertEqual(parse_frontmatter_map(""), {})

    def test_a_value_containing_a_colon_keeps_its_whole_value(self):
        self.assertEqual(
            parse_frontmatter_map("title: a: b: c"), {"title": "a: b: c"}
        )


if __name__ == "__main__":
    unittest.main()
