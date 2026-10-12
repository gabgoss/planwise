#!/usr/bin/env python3
"""Regression tests for the DELEGATED-mode detection pattern the review
handler greps for.

`handlers/review.md` Strategy Phase step 1 decides whether to bind the
DELEGATED reviewer block by grepping the Master Plan and every Orchestration
file for a DELEGATED mode line. The Orchestration template writes the mode as
a heading plus a separate `**Mode:** {DIRECT | DELEGATED}` line. A pattern
written for a one-line `Execution Strategy: DELEGATED` form never matches a
scaffolded plan, so the block stayed empty and reviews of DELEGATED plans
skipped the delegated catalog rows without any message.

The template also carries reminder text containing `Mode: DELEGATED` in the
middle of a line, and that text is copied into every DIRECT plan. A pattern
that is not anchored at the start of the line matches every DIRECT plan.

This suite reads the pattern out of the live handler, so it follows the
handler instead of a copy of it. It renders both modes from the live
template and checks the pattern against each.

Run with:  python -m pytest tests/test_review_delegated_detection.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# The detection pattern the handler's Strategy Phase step 1 names between
# backticks, directly after "every Orchestration file for".
_HANDLER_PATTERN_RE = re.compile(
    r"Grep the Master Plan and every Orchestration file for `([^`]+)`"
)
# The prefix every site must share, so the sites cannot drift apart.
_SHARED_PREFIX = r"^(\*\*Mode:\*\*|Execution Strategy:)\s*"
# The spelling that never matched a scaffolded Orchestration.
_OLD_PATTERN = r"Execution Strategy:\s*DELEGATED"
# The old pattern as a file spells it: a literal backslash-s after the colon.
# Prose such as "declares Execution Strategy: DELEGATED" has no backslash and
# must not count as an offender.
_OLD_PATTERN_SPELLING = "Execution Strategy:\\s"
# Files that spell the detection pattern out.
_SITES = (
    PLUGIN_ROOT / "handlers" / "review.md",
    PLUGIN_ROOT / "references" / "error-pattern-catalog.md",
    PLUGIN_ROOT / "references" / "agent-orchestration-delegated.md",
    PLUGIN_ROOT
    / "references"
    / "agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md",
)

_TEMPLATE_MODE_PLACEHOLDER = "{DIRECT | DELEGATED}"


def _handler_pattern() -> str:
    text = (PLUGIN_ROOT / "handlers" / "review.md").read_text(encoding="utf-8")
    match = _HANDLER_PATTERN_RE.search(text)
    if match is None:
        raise AssertionError(
            "no detection pattern found after 'every Orchestration file for' in "
            "handlers/review.md -- parser regression, not a missing pattern"
        )
    return match.group(1)


def _render_orchestration(mode: str) -> str:
    """Render the live Orchestration template with the given mode value."""
    template = (PLUGIN_ROOT / "templates" / "orchestration.md").read_text(
        encoding="utf-8"
    )
    if _TEMPLATE_MODE_PLACEHOLDER not in template:
        raise AssertionError(
            "templates/orchestration.md no longer carries the "
            f"'{_TEMPLATE_MODE_PLACEHOLDER}' placeholder -- update this test"
        )
    return template.replace(_TEMPLATE_MODE_PLACEHOLDER, mode)


class TestDelegatedDetectionPattern(unittest.TestCase):
    def test_handler_pattern_matches_a_delegated_orchestration(self):
        pattern = re.compile(_handler_pattern(), re.MULTILINE)
        rendered = _render_orchestration("DELEGATED")
        self.assertIsNotNone(
            pattern.search(rendered),
            "the handler's DELEGATED pattern does not match an Orchestration "
            "rendered from templates/orchestration.md with Mode: DELEGATED",
        )

    def test_handler_pattern_returns_zero_for_a_direct_orchestration(self):
        pattern = re.compile(_handler_pattern(), re.MULTILINE)
        rendered = _render_orchestration("DIRECT")
        # The reminder block must still be present, or this test would not
        # exercise the mid-line `Mode: DELEGATED` text it exists to cover.
        self.assertIn(
            "Mode: DELEGATED",
            rendered,
            "templates/orchestration.md lost its DELEGATED reminder text -- "
            "the DIRECT control no longer covers the mid-line false positive",
        )
        self.assertEqual(
            pattern.findall(rendered),
            [],
            "the handler's DELEGATED pattern matches a DIRECT Orchestration",
        )

    def test_old_pattern_does_not_match_a_delegated_orchestration(self):
        """Discrimination control: this is the defect the fix repairs."""
        rendered = _render_orchestration("DELEGATED")
        self.assertIsNone(
            re.search(_OLD_PATTERN, rendered, re.MULTILINE),
            "the old pattern now matches a scaffolded Orchestration, so this "
            "suite no longer proves the fix changed anything",
        )

    def test_legacy_one_line_form_still_matches(self):
        pattern = re.compile(_handler_pattern(), re.MULTILINE)
        self.assertIsNotNone(
            pattern.search("Execution Strategy: DELEGATED\n"),
            "the one-line form a hand-written plan may use no longer matches",
        )


class TestEverySiteSpellsTheSamePattern(unittest.TestCase):
    def test_every_site_carries_the_shared_prefix(self):
        missing = [
            str(path.relative_to(PLUGIN_ROOT))
            for path in _SITES
            if _SHARED_PREFIX not in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            missing,
            [],
            f"file(s) that no longer spell the detection pattern: {missing}",
        )

    def test_no_file_in_the_plugin_still_carries_the_old_pattern(self):
        offenders = []
        for path in sorted(PLUGIN_ROOT.rglob("*.md")):
            if _OLD_PATTERN_SPELLING in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(PLUGIN_ROOT)))
        self.assertEqual(
            offenders,
            [],
            f"file(s) that still name the pattern that never matched: {offenders}",
        )

    def test_handler_prints_the_detection_outcome(self):
        text = (PLUGIN_ROOT / "handlers" / "review.md").read_text(encoding="utf-8")
        self.assertIn("DELEGATED block: not bound (0 of", text)
        self.assertIn("DELEGATED block: bound (", text)


if __name__ == "__main__":
    unittest.main()
