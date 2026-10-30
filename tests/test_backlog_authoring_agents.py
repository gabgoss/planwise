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
    """Return the top-level `key: value` pairs of the YAML frontmatter block.

    Comment lines are skipped. A folded or literal block (`key: >` or `key: |`)
    takes its indented continuation lines, joined by single spaces.
    """
    lines = _read(path).splitlines()
    assert lines and lines[0].strip() == "---", f"{path.name} has no frontmatter"
    keys = {}
    block_key = None
    for line in lines[1:]:
        if line.strip() == "---":
            return keys
        if line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            if block_key is not None and line.strip():
                keys[block_key] = f"{keys[block_key]} {line.strip()}".strip()
            continue
        block_key = None
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if value[:1] in (">", "|"):
                block_key, value = key, ""
            keys[key] = value
    raise AssertionError(f"{path.name} frontmatter is not closed")


def _tool_list(value: str) -> list:
    """Split a frontmatter tool line such as `Read, Write, Glob` into names."""
    return [name.strip() for name in value.split(",") if name.strip()]


def _section(text: str, heading: str) -> str:
    """Return the body under `heading` up to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.startswith(heading):
            break
    else:
        raise AssertionError(f"heading {heading!r} not found")
    body = []
    for line in lines[start + 1:]:
        stripped = line.lstrip("#")
        line_level = len(line) - len(stripped)
        if 0 < line_level <= level and stripped.startswith(" "):
            break
        body.append(line)
    return "\n".join(body)


DISPOSITIONS = ("HOLDS", "RESOLVED", "DUPLICATE", "ALREADY_MET", "PREMISE_FAILS")


class BacklogAuthoringAgentContractTests(unittest.TestCase):
    def test_planner_consumes_preflight_fields(self):
        text = _read(PLANNER)
        for literal in ("DISPOSITION", "ANCHORS", "CRITERIA", "HOLDS"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text)
        read_section = _section(text, "## 1. READ")
        for field in ("DISPOSITION", "ANCHORS", "CRITERIA", "SOURCE_PINS"):
            with self.subTest(read_field=field):
                self.assertIn(f"`{field}`", read_section)

    def test_author_consumes_planner_fields(self):
        text = _read(AUTHOR)
        for literal in ("DESIGN", "STEPS", "VERIFICATION", "QUESTIONS", "SUB_ITEMS", "ITEMS_ALREADY_MET"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text)
        # HOLDS reaches the author only through a design file, so the mapping
        # table maps it by its DESIGN rows. The READ section names all five.
        mapping = _section(text, "### Mapping From Inputs to the Item")
        for value in DISPOSITIONS:
            with self.subTest(read_disposition=value):
                self.assertIn(f"`{value}`", _section(text, "## 1. READ"))
            if value != "HOLDS":
                with self.subTest(mapping_disposition=value):
                    self.assertIn(value, mapping)
        status_block = _section(text, "## Status Block")
        for field in ("ITEMS_FILED", "ITEMS_REWRITTEN", "ITEMS_ALREADY_MET", "ITEMS_RETIRED"):
            with self.subTest(status_field=field):
                self.assertRegex(status_block, rf"(?m)^{field}:")

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
                self.assertTrue(keys.get("description"), "folded description parsed empty")
        preflight = _frontmatter_keys(PREFLIGHT)
        self.assertNotIn("Edit", _tool_list(preflight["tools"]))
        self.assertIn("Edit", _tool_list(preflight["disallowedTools"]))
        planner_denied = _tool_list(_frontmatter_keys(PLANNER)["disallowedTools"])
        for name in ("SendMessage", "ToolSearch"):
            with self.subTest(planner_denied=name):
                self.assertIn(name, planner_denied)


if __name__ == "__main__":
    unittest.main()
