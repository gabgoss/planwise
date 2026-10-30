#!/usr/bin/env python3
"""Drift test for the single-task scope line of a DELEGATED spawn prompt.

`handlers/run.md` spawns each DELEGATED runner with a HARD CONSTRAINTS block
that opens `Execute ONLY {task-id}. ...`. A plan copies its spawn prompt from
the Spawn-Prompt Skeleton in `templates/orchestration.md`. When the skeleton
lacked the sentence, every DELEGATED plan scaffolded from it named the task
scope in two positions instead of three, and `/planwise review` graded each
Orchestration a BLOCKER.

This suite reads the sentence out of the live handler and checks that the
skeleton's HARD CONSTRAINTS block carries the same words, so the two cannot
drift apart again.

Run with:  python -m pytest tests/test_orchestration_scope_line.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# The handler's sentence, from its first word to the end of the Output list.
_SENTENCE_RE = re.compile(r"Execute ONLY \{task-id\}\..*?Output\}\.")
# The skeleton is the first fenced block after its heading.
_SKELETON_RE = re.compile(
    r"^## Spawn-Prompt Skeleton[^\n]*\n.*?^```markdown\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


def _flat(text: str) -> str:
    """Collapse every whitespace run, so line wraps and indents do not count."""
    return re.sub(r"\s+", " ", text)


def _handler_sentence() -> str:
    text = _flat((PLUGIN_ROOT / "handlers" / "run.md").read_text(encoding="utf-8"))
    match = _SENTENCE_RE.search(text)
    if match is None:
        raise AssertionError(
            "handlers/run.md no longer carries 'Execute ONLY {task-id}. ... "
            "Output}.' -- parser regression or the handler changed its wording"
        )
    return match.group(0)


def _skeleton_hard_constraints() -> str:
    text = (PLUGIN_ROOT / "templates" / "orchestration.md").read_text(
        encoding="utf-8"
    )
    match = _SKELETON_RE.search(text)
    if match is None:
        raise AssertionError(
            "templates/orchestration.md has no fenced block under "
            "'## Spawn-Prompt Skeleton' -- parser regression, not a missing line"
        )
    skeleton = match.group(1)
    start = skeleton.find("## HARD CONSTRAINTS")
    if start < 0:
        raise AssertionError("the skeleton has no '## HARD CONSTRAINTS' block")
    end = skeleton.find("\n## ", start + 1)
    return _flat(skeleton[start : end if end > 0 else len(skeleton)])


class TestSkeletonCarriesTheScopeLine(unittest.TestCase):
    def test_hard_constraints_block_carries_the_handler_sentence(self):
        sentence = _handler_sentence()
        self.assertIn(
            sentence,
            _skeleton_hard_constraints(),
            "the HARD CONSTRAINTS block of the Spawn-Prompt Skeleton in "
            "templates/orchestration.md does not carry the scope sentence "
            f"handlers/run.md spawns with: {sentence!r}",
        )

    def test_the_sentence_is_not_matched_outside_its_block(self):
        """Discrimination control: the block parser must not see the opener."""
        block = _skeleton_hard_constraints()
        self.assertNotIn("You are dispatched to execute ONE task", block)
        self.assertNotIn("Do NOT proceed to task", block)


if __name__ == "__main__":
    unittest.main()
