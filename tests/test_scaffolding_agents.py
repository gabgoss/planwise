#!/usr/bin/env python3
"""Contract pins for the three scaffolding agents.

The orchestrator hands a sprint to the extractor, the extractor's status block
feeds the scaffolder, and the harmonizer grades the whole pass. The agents are
prose, so the field names one party writes and the next reads can drift apart
with no error. These tests pin the model and effort values, the prohibitions
every agent states in words, the status-block fields, the handoff fields each
agent reads, the template headings the scaffolder carries, and the gate the
harmonizer names.

Test-only override: the environment variable PLANWISE_TEST_AGENTS_DIR
redirects ONLY the agents directory, so a mutation run reads a scratch copy.
It is unset in a normal run, and the default run reads the real agents folder.
The templates are always read from their real path. The status-block fields
and the handoff fields live in literal tables in this file, so no run skips them.

Run with:  python -m pytest tests/test_scaffolding_agents.py -q
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
AGENTS = Path(os.environ.get("PLANWISE_TEST_AGENTS_DIR") or PLUGIN / "agents")
TEMPLATES = PLUGIN / "templates"

EXTRACTOR = AGENTS / "ei-extractor.md"
SCAFFOLDER = AGENTS / "sprint-scaffolder.md"
HARMONIZER = AGENTS / "scaffold-harmonizer.md"
ALL_AGENTS = [EXTRACTOR, SCAFFOLDER, HARMONIZER]

# agent file -> (model, effort)
PINNED = {
    EXTRACTOR: ("opus", "high"),
    SCAFFOLDER: ("opus", "high"),
    HARMONIZER: ("sonnet", "medium"),
}

TEMPLATE_FILES = ("orchestration.md", "sprint-plan.md", "recovery.md", "task-file.md")

# These tables pin the scaffolding pipeline's handoff contract. A change to an
# agent's status block or inputs updates them in the same commit.
STATUS_FIELDS = {
    EXTRACTOR: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "EI_SECTION_MAP", "SOURCE_TOKENS",
        "EI_TOKENS", "DEFERRED_TOKENS", "RETENTION_PCT", "EMPTY_SECTIONS", "OPEN_QUESTIONS",
        "KEY_FINDINGS", "ISSUES",
    ),
    SCAFFOLDER: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "FILL_REMAINING", "STRAY_H2",
        "SPAN_ROWS_REPOINTED", "OPEN_QUESTIONS", "KEY_FINDINGS", "ISSUES",
    ),
    HARMONIZER: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "DEVIATIONS_BEFORE",
        "DEVIATIONS_AFTER", "EDITS_APPLIED", "STRAY_H2", "FILL_REMAINING", "KEY_FINDINGS", "ISSUES",
    ),
}

# (field, agent whose file must name it): one pair per field an agent reads.
AGENT_READS = (
    ("plugin_root", EXTRACTOR),
    ("plugin_root", SCAFFOLDER),
    ("plugin_root", HARMONIZER),
    ("planwise_root", SCAFFOLDER),
    ("abbrev", EXTRACTOR),
    ("abbrev", SCAFFOLDER),
    ("abbrev", HARMONIZER),
    ("sprint_id", EXTRACTOR),
    ("sprint_id", SCAFFOLDER),
    ("sprint_folder", EXTRACTOR),
    ("sprint_folder", SCAFFOLDER),
    ("meta_root", EXTRACTOR),
    ("plan_root", HARMONIZER),
    ("sprint_ids", HARMONIZER),
    ("spec_path", EXTRACTOR),
    ("spec_path", SCAFFOLDER),
    ("source_map", EXTRACTOR),
    ("ei_sections", EXTRACTOR),
    ("deferred_targets", EXTRACTOR),
    ("ei_paths", SCAFFOLDER),
    ("ei_section_map", SCAFFOLDER),
    ("write_set", SCAFFOLDER),
    ("cross_sprint_markers", SCAFFOLDER),
    ("naming_scheme", SCAFFOLDER),
    ("lessons_dir", SCAFFOLDER),
    ("EI_SECTION_MAP", SCAFFOLDER),
)


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
        if line.rstrip() == heading:
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


def _h2_set(text: str) -> set:
    """Return every `## ` heading line of `text`, with a trailing marker comment stripped."""
    found = set()
    for line in text.splitlines():
        if line.startswith("## "):
            found.add(re.sub(r"\s*<!--.*?-->\s*$", "", line).strip())
    return found


class ScaffoldingAgentContractTests(unittest.TestCase):
    def test_pinned_model_and_effort_per_agent(self):
        for path, (model, effort) in PINNED.items():
            keys = _frontmatter_keys(path)
            with self.subTest(agent=path.name):
                self.assertEqual(keys.get("model"), model)
                self.assertEqual(keys.get("effort"), effort)
                self.assertNotIn("background", keys)
                self.assertTrue(keys.get("description"), "folded description parsed empty")

    def test_no_agent_names_the_question_tool_or_plan_mode(self):
        for path in ALL_AGENTS:
            text = _read(path)
            for literal in ("AskUserQuestion", "EnterPlanMode"):
                with self.subTest(agent=path.name, literal=literal):
                    self.assertNotIn(literal, text)

    def test_status_block_fields(self):
        for path, fields in STATUS_FIELDS.items():
            status_block = _section(_read(path), "## Status Block")
            for field in fields:
                with self.subTest(agent=path.name, field=field):
                    self.assertRegex(status_block, rf"(?m)^{field}:")

    def test_handoff_fields_named_by_reader(self):
        for field, path in AGENT_READS:
            with self.subTest(agent=path.name, field=field):
                self.assertRegex(_read(path), re.compile(re.escape(field), re.IGNORECASE))

    def test_scaffolder_carries_template_headers(self):
        carried = _h2_set(_read(SCAFFOLDER))
        for name in TEMPLATE_FILES:
            wanted = _h2_set(_read(TEMPLATES / name))
            self.assertTrue(wanted, f"{name} yielded no headings")
            for heading in sorted(wanted):
                with self.subTest(template=name, heading=heading):
                    self.assertIn(heading, carried)

    def test_harmonizer_names_the_gate(self):
        text = _read(HARMONIZER)
        self.assertIn("scripts/scaffold_deviations.py", text)
        self.assertIn("deviations: A=", text)


if __name__ == "__main__":
    unittest.main()
