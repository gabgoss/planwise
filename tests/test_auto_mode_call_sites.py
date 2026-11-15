#!/usr/bin/env python3
"""Pins the inline tagging convention of `references/auto-mode-policy.md` (section "Inline Tagging Convention").

Predicate: every line in `handlers/*.md` that names `AskUserQuestion` carries an
`AUTO-MODE:` marker on its own line or within the two lines above it, or it
appears in the closed list below. The list classifies each unmarked line as a
non-call mention or as a known untagged call site. A new unmarked line fails
until a reviewer classifies it. A list entry that no live line matches also
fails, so the list cannot go stale.

Input: the markdown files under `plugins/planwise/handlers/`. Entries key on a
text fragment of the line, never on a line number, so an inserted line does not
break them. Under pytest, a failed assertion names each unmarked line with its
handler and line number.

Cannot see: a call written without the literal word `AskUserQuestion`, a marker
placed three or more lines above its question, and whether a tag says critical or
convenience correctly. A marker moved three lines up reads as untagged here, which
is the intended result: an inserted paragraph between a marker and its question
hides the marker from the two-line check.

Run with:  python -m pytest tests/test_auto_mode_call_sites.py -q
"""

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

HANDLERS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "handlers"
CALL = "AskUserQuestion"
MARKER = "AUTO-MODE:"
WINDOW = 2

NON_CALL = "non-call"
UNTAGGED_CALL = "untagged-call"

# Closed list: (handler file, fragment unique to the line, class).
# non-call: the line mentions the tool without asking, such as a description, a
#   field table, a WRONG/CORRECT example, an Auto Mode pointer, or "issues no ...".
# untagged-call: the line tells the agent to ask, and no marker sits within two
#   lines above it. These are known gaps in the convention, listed so the set
#   cannot grow unnoticed. Tag one and delete its entry.
CLASSIFIED = [
    ("backlog-Part-2-LoopMode.md", "No question, no sentence", NON_CALL),
    ("backlog-Part-3-Answers.md", "Ask one `AskUserQuestion` per unanswered block", UNTAGGED_CALL),
    ("backlog-Part-3-Answers.md", "| `AskUserQuestion` field | Value |", NON_CALL),
    ("backlog-Part-4-Refine.md", "ask one `AskUserQuestion` per question", UNTAGGED_CALL),
    ("backlog.md", "Use `AskUserQuestion` to collect project info", UNTAGGED_CALL),
    ("backlog.md", "For Auto Mode behavior (how a step behaves when `AskUserQuestion`", NON_CALL),
    ("backlog.md", "use `AskUserQuestion` to confirm", UNTAGGED_CALL),
    ("backlog.md", "It issues no `AskUserQuestion`", NON_CALL),
    ("backlog.md", "`AskUserQuestion` Approve/Revert", UNTAGGED_CALL),
    ("backlog.md", "via AskUserQuestion (include LARGE_SCOPE", UNTAGGED_CALL),
    ("doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md", "ask one `AskUserQuestion` per PRESENT prunable class", UNTAGGED_CALL),
    ("init.md", "Use `AskUserQuestion`: \"This planwise copy", UNTAGGED_CALL),
    ("init.md", "Use `AskUserQuestion` to collect:", UNTAGGED_CALL),
    ("init.md", "`AskUserQuestion` takes at most four questions", NON_CALL),
    ("init.md", "**If it does not resolve,** use `AskUserQuestion`:", UNTAGGED_CALL),
    ("init.md", "no `AskUserQuestion` is issued", NON_CALL),
    ("plan-Part-2-GatherAndGenerate.md", "use `AskUserQuestion` to collect it", UNTAGGED_CALL),
    ("plan-Part-2-GatherAndGenerate.md", "handler prompts with `AskUserQuestion` showing", NON_CALL),
    ("plan-Part-2-GatherAndGenerate.md", "use `AskUserQuestion` with the following", UNTAGGED_CALL),
    ("plan-Part-2-GatherAndGenerate.md", "ask the user once with `AskUserQuestion` whether", UNTAGGED_CALL),
    ("plan-scaffolding.md", "goes to the user through `AskUserQuestion`", UNTAGGED_CALL),
    ("plan.md", "Use `AskUserQuestion` to collect project info", UNTAGGED_CALL),
    ("plan.md", "For Auto Mode behavior (how a step behaves when `AskUserQuestion`", NON_CALL),
    ("plan.md", "recommend Discovery via `AskUserQuestion`", UNTAGGED_CALL),
    ("plan.md", "recommend Scaffolding via `AskUserQuestion`", UNTAGGED_CALL),
    ("review.md", "For Auto Mode behavior (how a step behaves when `AskUserQuestion`", NON_CALL),
    ("run.md", "(the AskUserQuestion turn or timestamp)", NON_CALL),
    ("run.md", "the AskUserQuestion options are the A", NON_CALL),
    ("run.md", "skip the `AskUserQuestion` above ONLY", NON_CALL),
    ("upgrade-Part-2-RecoveryAndReference.md", "Offer to run `/planwise init` via `AskUserQuestion`", UNTAGGED_CALL),
    ("upgrade-Part-3-BannerAndConflictResolution.md", "Then `AskUserQuestion` per file", UNTAGGED_CALL),
    ("upgrade.md", "the card's single `AskUserQuestion` offers it", NON_CALL),
    ("upgrade.md", "merged `AskUserQuestion` the card names", NON_CALL),
    ("upgrade.md", "ask the user with `AskUserQuestion` whether to proceed", UNTAGGED_CALL),
    ("upgrade.md", "is `false` or absent", UNTAGGED_CALL),
    ("upgrade.md", "in its single `AskUserQuestion`, so never ask", NON_CALL),
    ("upgrade.md", "do not call `AskUserQuestion`", NON_CALL),
]


def unmarked_lines(text: str) -> list[tuple[int, str]]:
    """Return (line number, line) for each call line with no marker on it or the two lines above."""
    lines = text.replace("\r\n", "\n").split("\n")
    found = []
    for i, line in enumerate(lines):
        if CALL in line and not any(MARKER in x for x in lines[max(0, i - WINDOW) : i + 1]):
            found.append((i + 1, line))
    return found


def problems(texts: dict[str, str], classified=CLASSIFIED) -> list[str]:
    """Return one line per unmarked line outside the list and per list entry with no live match."""
    found: list[str] = []
    used: set[int] = set()
    for handler, text in sorted(texts.items()):
        for number, line in unmarked_lines(text):
            hits = [k for k, (h, frag, _) in enumerate(classified) if h == handler and frag in line]
            if not hits:
                found.append(f"{handler}:{number}: untagged and unclassified: {line.strip()[:80]}")
            elif len(hits) > 1:
                found.append(f"{handler}:{number}: matches {len(hits)} list entries")
            used.update(hits)
    for k, (handler, frag, _) in enumerate(classified):
        if k not in used:
            found.append(f"stale list entry, no live line matches: {handler}: {frag}")
    return found


def _live() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(HANDLERS.glob("*.md"))}


# Fixtures: the two differ only in where the marker sits.
TAGGED = "<!-- AUTO-MODE: convenience -->\n<!-- Default: yes -->\nUse `AskUserQuestion` to ask.\n"
# Marker three lines above the question (an inserted paragraph pushed it out of the window).
UNTAGGED = "<!-- AUTO-MODE: convenience -->\n<!-- Default: yes -->\nA note that was inserted.\nUse `AskUserQuestion` to ask.\n"


class TestAutoModeCallSites(unittest.TestCase):
    def test_live_tree_is_tagged_or_classified(self):
        self.assertEqual(problems(_live()), [])

    def test_the_walk_saw_the_handlers(self):
        texts = _live()
        self.assertGreater(len(texts), 10)
        total = sum(text.count(CALL) for text in texts.values())
        self.assertGreater(total, 0)
        self.assertTrue(any(MARKER in text for text in texts.values()))

    def test_tagged_and_untagged_fixtures_differ(self):
        self.assertEqual(unmarked_lines(TAGGED), [])
        self.assertEqual(len(unmarked_lines(UNTAGGED)), 1)

    def test_a_marker_moved_three_lines_up_fails(self):
        live = _live()
        found = problems({**live, "init.md": live["init.md"] + "\n" + UNTAGGED})
        self.assertEqual(len(found), 1)
        self.assertIn("init.md", found[0])
        self.assertIn("untagged and unclassified", found[0])

    def test_a_tagged_addition_passes(self):
        live = _live()
        self.assertEqual(problems({**live, "init.md": live["init.md"] + "\n" + TAGGED}), [])

    def test_a_stale_list_entry_fails(self):
        extra = CLASSIFIED + [("init.md", "a fragment no line holds", NON_CALL)]
        found = problems(_live(), extra)
        self.assertEqual(len(found), 1)
        self.assertIn("stale list entry", found[0])

    def test_every_entry_has_a_known_class(self):
        for _, _, kind in CLASSIFIED:
            self.assertIn(kind, (NON_CALL, UNTAGGED_CALL))


if __name__ == "__main__":
    unittest.main()
