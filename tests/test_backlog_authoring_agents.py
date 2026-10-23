#!/usr/bin/env python3
"""Contract pins for the three backlog authoring agents.

The preflight writes a fact sheet, the planner reads it and writes a design
file, and the author reads both. The agents are prose, so the field names one
agent writes and the next agent reads can drift apart with no error. These
tests pin the field names each consumer must name, the prohibitions every agent
states in words, the shared process reference, and the model and effort pins.

Run with:  python -m pytest tests/test_backlog_authoring_agents.py -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
AGENTS = PLUGIN / "agents"
PREFLIGHT = AGENTS / "backlog-preflight.md"
PLANNER = AGENTS / "backlog-planner.md"
AUTHOR = AGENTS / "backlog-author.md"
ALL_AGENTS = [PREFLIGHT, PLANNER, AUTHOR]

PROCESS_REFERENCE = "references/backlog-creation-process.md"

# agent file -> (model, effort)
PINNED = {
    PREFLIGHT: ("sonnet", "medium"),
    PLANNER: ("opus", "high"),
    AUTHOR: ("sonnet", "medium"),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter_keys(path: Path) -> dict:
    """Return the top-level `key: value` pairs of the YAML frontmatter block."""
    lines = _read(path).splitlines()
    assert lines[0] == "---", f"{path.name} has no frontmatter"
    keys = {}
    for line in lines[1:]:
        if line == "---":
            return keys
        if line and not line[0].isspace() and not line.startswith("#") and ":" in line:
            key, _, value = line.partition(":")
            keys[key.strip()] = value.strip()
    raise AssertionError(f"{path.name} frontmatter is not closed")


class BacklogAuthoringAgentContractTests(unittest.TestCase):
    def test_planner_consumes_preflight_fields(self):
        text = _read(PLANNER)
        for literal in ("DISPOSITION", "ANCHORS", "CRITERIA", "HOLDS"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text)

    def test_author_consumes_planner_fields(self):
        text = _read(AUTHOR)
        for literal in ("DESIGN", "STEPS", "VERIFICATION", "QUESTIONS", "SUB_ITEMS", "ITEMS_ALREADY_MET"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text)

    def test_no_agent_names_the_question_tool_or_plan_mode(self):
        for path in ALL_AGENTS:
            text = _read(path)
            for literal in ("AskUserQuestion", "EnterPlanMode"):
                with self.subTest(agent=path.name, literal=literal):
                    self.assertNotIn(literal, text)

    def test_planner_never_authors_a_session_plan(self):
        self.assertIn("never authors a session plan", _read(PLANNER))

    def test_every_agent_cites_the_creation_process_reference(self):
        for path in ALL_AGENTS:
            with self.subTest(agent=path.name):
                self.assertIn(PROCESS_REFERENCE, _read(path))

    def test_pinned_model_and_effort_per_agent(self):
        for path, (model, effort) in PINNED.items():
            keys = _frontmatter_keys(path)
            with self.subTest(agent=path.name):
                self.assertEqual(keys.get("model"), model)
                self.assertEqual(keys.get("effort"), effort)
                self.assertNotIn("background", keys)


if __name__ == "__main__":
    unittest.main()
