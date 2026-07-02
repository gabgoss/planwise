#!/usr/bin/env python3
"""Unit tests for the structural comparison primitive.

`structural_compare.classify_blocks(installed_raw, shipped_raw)` segments two
markdown documents into structural blocks (frontmatter, headings, top-level
callouts, preamble), normalizes each block into an order-/whitespace-
insensitive token multiset, and classifies the installed document against the
shipped one as a strict SUBSET (safe to silently refresh/remove, subject to
confidence) or as HAS_UNIQUE (carries installed-only content that must be
preserved).

These tests pin the verdict posture for every documented case: identical
content, reordered sections, reflowed whitespace, additive upstream growth
(shipped block grew around the installed content), an added section, an
in-block reword, fenced example text that must not be mistaken for real
structure, a renamed/renumbered heading with an identical body, and a lossless
StructuralVerdict round trip.

Run with:  python -m unittest scripts/test_structural_compare.py
"""

import sys
import unittest
from pathlib import Path

# Allow `import structural_compare` whether unittest is launched from the repo
# root (python -m unittest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import structural_compare as sc  # noqa: E402


class TestClassifyBlocks(unittest.TestCase):
    def test_identical_is_exact_subset(self):
        content = """## Introduction
This section explains the setup process for new projects clearly.

## Configuration
Set the required options before running the tool for the first time.
"""
        v = sc.classify_blocks(content, content)
        self.assertEqual(v.classification, "SUBSET")
        self.assertEqual(v.confidence, "exact")

    def test_reordered_sections_exact(self):
        shipped = """## Introduction
This section explains the setup process for new projects clearly.

## Configuration
Set the required options before running the tool for the first time.
"""
        installed = """## Configuration
Set the required options before running the tool for the first time.

## Introduction
This section explains the setup process for new projects clearly.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertEqual(v.classification, "SUBSET")
        self.assertEqual(v.confidence, "exact")

    def test_reflowed_body_is_subset(self):
        shipped = """## Introduction
This section explains the setup process for new projects clearly.
"""
        installed = """## Introduction
This section explains
the setup process
for new projects clearly.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertTrue(sc.is_subset(v))

    def test_shipped_grew_block_is_contained(self):
        installed = """## Introduction
This section explains the setup process
"""
        shipped = """## Introduction
This section explains the setup process for new projects and teams alike.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertEqual(v.classification, "SUBSET")
        self.assertEqual(v.confidence, "contained")
        self.assertTrue(sc.is_safe_to_remove(v))

    def test_added_section_has_unique(self):
        shipped = """## Introduction
This section explains the setup process for new projects clearly.
"""
        installed = """## Introduction
This section explains the setup process for new projects clearly.

## Custom Notes
This project also requires an extra manual approval step before deployment.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertEqual(v.classification, "HAS_UNIQUE")
        self.assertIn("Custom Notes", v.unique_blocks)

    def test_in_block_reword_not_safe_to_remove(self):
        shipped = """## Introduction
This section explains the setup process for new projects clearly.
"""
        installed = """## Introduction
This section explains the configuration workflow for new projects clearly.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertFalse(sc.is_safe_to_remove(v))

    def test_fenced_callout_examples_not_split(self):
        content = """### Real Heading One

Some real prose content that is definitely not fenced at all here.

> [!binding] Real Policy
> This is a real top-level callout describing an enforcement mechanism clearly.

```markdown
> [!note] Example Note
> This is fenced example content that must not become a real block at all.

### Example Heading Inside Fence

> > [!template]
> > nested fenced template example line goes here
```

### Real Heading Two

More real prose after the fence closes for good measure right here.
"""
        blocks = sc.segment_blocks(content)
        labels = [b.label for b in blocks]

        # The fenced example lines must never surface as their own blocks.
        self.assertNotIn("Example Heading Inside Fence", labels)
        self.assertNotIn("[!note] Example Note", labels)
        self.assertNotIn("[!template]", labels)

        # Only the two real headings and the one real top-level callout are
        # actual structural blocks; the fenced content stays merged into
        # "Real Heading One".
        heading_labels = [b.label for b in blocks if b.kind == "heading"]
        self.assertEqual(heading_labels, ["Real Heading One", "Real Heading Two"])
        callout_labels = [b.label for b in blocks if b.kind == "callout"]
        self.assertEqual(callout_labels, ["[!binding] Real Policy"])

    def test_renamed_renumbered_heading_identical_body(self):
        # "Overview" -> "Summary" is a renamed *lone* heading (no body
        # beneath it) on both sides, so both normalize to a single token
        # below MIN_BLOCK_TOKENS and are excluded as noise regardless of the
        # rename. "Setup {#setup-2}" -> "Setup {#setup-3}" is a renumbered
        # anchor: the `{#...}` anchor is stripped by normalize_tokens
        # (unanchored, so it applies inside a heading line too), leaving the
        # heading + body tokens identical on both sides.
        shipped = """## Overview

## Setup {#setup-2}
Follow these steps to install and configure the tool correctly for use.
"""
        installed = """## Summary

## Setup {#setup-3}
Follow these steps to install and configure the tool correctly for use.
"""
        v = sc.classify_blocks(installed, shipped)
        self.assertTrue(sc.is_subset(v))

    def test_verdict_round_trip(self):
        content = """## A
Some real body content that has enough tokens to not be noise.
"""
        v = sc.classify_blocks(content, content)
        d = v.as_dict()

        self.assertEqual(sc.StructuralVerdict.from_dict(d), v)

        # from_dict tolerates an extra key an agent-produced verdict might add.
        d["extra_context_field"] = "agent added this"
        self.assertEqual(sc.StructuralVerdict.from_dict(d), v)


if __name__ == "__main__":
    unittest.main()
