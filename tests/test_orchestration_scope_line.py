#!/usr/bin/env python3
"""Drift test for the single-task scope line of a DELEGATED spawn prompt.

`handlers/run.md` dispatches each DELEGATED runner from the Orchestration's
`## Spawn-Prompt Skeleton`, filled per task, and falls back to the skeleton in
`templates/orchestration.md` when the Orchestration has none. It no longer
carries a prompt of its own. The skeleton's HARD CONSTRAINTS block opens
`Execute ONLY {task-id}. ...`. When the skeleton lacked the sentence, every
DELEGATED plan scaffolded from it named the task scope in two positions
instead of three, and `/planwise review` graded each Orchestration a BLOCKER.

This suite checks that the handler names the skeleton as its prompt source and
holds no second prompt, and that the template skeleton's HARD CONSTRAINTS block
carries the scope sentence, so the prompt the runner receives and the prompt
review grades cannot drift apart again.

It also pins the skeleton's return line (every Output-line file, not one file)
and the one exception HARD CONSTRAINT 1 makes for the sequential-mode Recovery
writes that `agents/task-runner.md` §5.A asks for.

Run with:  python -m pytest tests/test_orchestration_scope_line.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# The scope sentence, from its first word to the end of the Output list.
_SENTENCE = (
    "Execute ONLY {task-id}. Do not start any other task in the session even if "
    "the Recovery file lists it as PENDING. Files you may write: {explicit list "
    "from the task file's Output}."
)
# The skeleton is the first fenced block after its heading.
_SKELETON_RE = re.compile(
    r"^## Spawn-Prompt Skeleton[^\n]*\n.*?^```markdown\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


def _flat(text: str) -> str:
    """Collapse every whitespace run, so line wraps and indents do not count."""
    return re.sub(r"\s+", " ", text)


def _handler_text() -> str:
    return _flat((PLUGIN_ROOT / "handlers" / "run.md").read_text(encoding="utf-8"))


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
    def test_hard_constraints_block_carries_the_scope_sentence(self):
        self.assertIn(
            _flat(_SENTENCE),
            _skeleton_hard_constraints(),
            "the HARD CONSTRAINTS block of the Spawn-Prompt Skeleton in "
            "templates/orchestration.md does not carry the scope sentence "
            f"{_SENTENCE!r}",
        )

    def test_handler_names_the_skeleton_as_its_prompt_source(self):
        handler = _handler_text()
        self.assertIn(
            "## Spawn-Prompt Skeleton",
            handler,
            "handlers/run.md does not name '## Spawn-Prompt Skeleton' as the "
            "source of its spawn prompt",
        )
        self.assertIn("templates/orchestration.md", handler)

    def test_handler_carries_no_second_prompt(self):
        """Discrimination control: the inline prompt must not return to run.md."""
        handler = _handler_text()
        self.assertNotIn("dispatched to execute ONE task", handler)
        self.assertNotIn("Execute ONLY {task-id}", handler)

    def test_the_sentence_is_not_matched_outside_its_block(self):
        """Discrimination control: the block parser must not see the opener."""
        block = _skeleton_hard_constraints()
        self.assertNotIn("You are dispatched to execute ONE task", block)
        self.assertNotIn("Do NOT proceed to task", block)


def _constraint_one(text: str, fence_pattern: re.Pattern) -> str:
    """The `1. Modify ONLY` line of the first fenced block the pattern finds."""
    match = fence_pattern.search(text)
    if match is None:
        raise AssertionError("no fenced block found -- parser regression")
    for line in match.group(1).splitlines():
        if line.strip().startswith("1. Modify ONLY"):
            return line.strip()
    raise AssertionError("the fenced block has no '1. Modify ONLY' line")


def _read(relative: str) -> str:
    return (PLUGIN_ROOT / relative).read_text(encoding="utf-8")


# The reference copy is the first fenced block after its section 1.8 heading.
_REFERENCE_SKELETON_RE = re.compile(
    r"^## 1\.8 [^\n]*\n.*?^```markdown\n(.*?)^```", re.MULTILINE | re.DOTALL
)
# What a sequential runner writes in Recovery, as task-runner section 5.A names it.
_RECOVERY_ENTRIES = ("Key Findings", "Files Modified", "Change Log", "Current Step")


class TestSkeletonReturnAndCheckpoint(unittest.TestCase):
    def test_return_line_names_every_output_file(self):
        match = _SKELETON_RE.search(_read("templates/orchestration.md"))
        self.assertIsNotNone(match)
        skeleton = _flat(match.group(1))
        self.assertIn("Return after writing every file on this task's Output line.", skeleton)
        self.assertNotIn("single expected output file", skeleton)

    def test_constraint_one_names_the_checkpoint_exception(self):
        self.assertIn(
            "Exception: in sequential mode you may also write this task's own Recovery row",
            _skeleton_hard_constraints(),
        )

    def test_exception_covers_every_entry_the_runner_protocol_writes(self):
        agent = _read("agents/task-runner.md")
        start = agent.index("### 5.A ")
        protocol = agent[start : agent.index("### 5.B ", start)]
        line = _constraint_one(_read("templates/orchestration.md"), _SKELETON_RE)
        for entry in _RECOVERY_ENTRIES:
            with self.subTest(entry=entry):
                self.assertIn(entry, protocol, "task-runner 5.A no longer names it")
                self.assertIn(entry, line)
        self.assertIn("Read that Recovery file", line)

    def test_exception_names_its_mode_signal_and_beats_the_file_list(self):
        """The runner must see which mode it is in, and that the list yields."""
        self.assertIn("Recovery file: {", _read("handlers/run.md"))
        line = _constraint_one(_read("templates/orchestration.md"), _SKELETON_RE)
        self.assertIn("Sequential mode means this prompt has a `Recovery file:` line.", line)
        self.assertIn("even though the Output line and the file list leave it out", line)

    def test_reference_constraint_one_matches_the_template(self):
        self.assertEqual(
            _constraint_one(
                _read("references/agent-orchestration-delegated.md"),
                _REFERENCE_SKELETON_RE,
            ),
            _constraint_one(_read("templates/orchestration.md"), _SKELETON_RE),
        )


if __name__ == "__main__":
    unittest.main()
