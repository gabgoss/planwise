#!/usr/bin/env python3
"""Text-pin tests for the /planwise backlog loop-mode hooks.

`handlers/backlog.md` carries short hooks that point at
`handlers/backlog-Part-2-LoopMode.md`. These tests pin the hook literals, the
Part-2 question and marker text, and the two reference edits, so a later edit
cannot silently drop one.

Run with:  python -m pytest tests/test_backlog_loop_handler.py -q
"""

import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
BACKLOG_HANDLER = PLUGIN / "handlers" / "backlog.md"
LOOP_PART2 = PLUGIN / "handlers" / "backlog-Part-2-LoopMode.md"
AUTO_MODE_POLICY = PLUGIN / "references" / "auto-mode-policy.md"
BACKLOG_SCHEMA = PLUGIN / "references" / "backlog-schema.md"

# Each hook leaves one literal in the handler: (literal, minimum count).
HOOK_LITERALS = [
    ("--mark --phase acting", 1),
    ("LOOP: re-assessed to Route C", 1),
    ("--mark --phase verifying", 2),
    ("--mark --outcome", 1),
    ("continue to Phase 9", 1),
    ("(one, in loop mode)", 2),
    ("where C is not selectable", 1),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _span_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    return text[start:text.index(end_marker, start)]


class BacklogLoopHandlerTests(unittest.TestCase):
    def test_phase_9_heading_appears_once(self):
        text = _read(BACKLOG_HANDLER)
        self.assertEqual(text.count("## Phase 9: LOOP BOUNDARY"), 1)

    def test_hook_literals_and_loop_resume_present(self):
        text = _read(BACKLOG_HANDLER)
        self.assertGreaterEqual(text.count("--loop-resume"), 3)
        for literal, minimum in HOOK_LITERALS:
            with self.subTest(literal=literal):
                self.assertGreaterEqual(
                    text.count(literal), minimum,
                    f"hook literal {literal!r} is missing from backlog.md",
                )

    def test_phase_1_to_2_slice_unchanged_claims(self):
        text = _read(BACKLOG_HANDLER)
        span = _span_between(text, "## Phase 1: FETCH", "## Phase 2: SELECT")
        for needle in ("hand-authored index", "/planwise upgrade", "STOP"):
            with self.subTest(needle=needle):
                self.assertIn(needle, span)

    def test_part_2_carries_questions_and_marker_shape(self):
        text = _read(LOOP_PART2)
        for needle in (
            "Loop through the backlog this run?",
            "Which items should the loop cover?",
            "Which items would you like to triage?",
            "BACKLOG LOOP: run=<run-id> done=<item-id> remaining=<N> state=<abs path>",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_auto_mode_policy_has_loop_rows(self):
        text = _read(AUTO_MODE_POLICY)
        self.assertIn("Loop opt-in (backlog.md Phase 2 Q1)", text)
        self.assertIn("Loop mode / count (backlog.md Phase 2 Q2)", text)

    def test_backlog_schema_documents_backlog_loop(self):
        self.assertIn("### backlog_loop.py", _read(BACKLOG_SCHEMA))


if __name__ == "__main__":
    unittest.main()
