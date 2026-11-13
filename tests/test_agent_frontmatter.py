#!/usr/bin/env python3
"""Frontmatter pins for every shipped agent file.

Predicate. Each `agents/*.md` file has `name` equal to its filename stem in
lowercase-hyphen form (at most 64 characters) and a `description` of at most
1024 characters. The "Shipped Effort Levels" table of the agent-authoring
reference and the agent files agree in both directions: every agent file is
named in the table, every table row matches the file's `effort`, and an agent
the table lists as inherited sets no `effort`. Every `model`, `effort` and
`permissionMode` value comes from the set the reference's quick-reference table
lists, and a YAML boolean is lowercase.

Input. The real agents folder and `references/agent-authoring.md`. The table
and the value sets are parsed from the reference at run time, never copied
into this file.

Cannot see. The meaning of a pinned level (the table's Basis column), the
agent body, and any key the reference does not list.

Reference sections pinned. `agent-authoring.md §2` (Required Fields,
Shipped Effort Levels, Validation Notes).

Controls. The live tree passes (positive). A renamed `name`, a removed table
row, a drifted `effort`, a stray `effort` on an inherited agent, a bad
`model`, and an uppercase boolean each fail and name the item (mutation). A
file with no frontmatter, and a reference with no table, fail loudly (parse).

Run with:  python -m pytest tests/test_agent_frontmatter.py -q
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from frontmatter_parser import (
    parse_frontmatter_map,
    split_frontmatter_block,
)
from markdown_parser import split_row_cells

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
AGENTS = PLUGIN / "agents"
REFERENCE = PLUGIN / "references" / "agent-authoring.md"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")
BAD_BOOLEAN_RE = re.compile(r"^(True|TRUE|False|FALSE|Yes|YES|No|NO|On|ON|Off|OFF)$")
VALUE_FIELDS = ("model", "effort", "permissionMode")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_agents(agents_dir: Path) -> dict:
    """Return {stem: {key: value-text}} for every `*.md` in `agents_dir`.

    A file with no complete frontmatter block raises AssertionError, so a parse
    failure is loud and never an empty pass.
    """
    agents = {}
    for path in sorted(agents_dir.glob("*.md")):
        block = split_frontmatter_block(path.read_text(encoding="utf-8"))
        assert block is not None, f"{path.name} has no complete frontmatter block"
        fields = parse_frontmatter_map(block[0])
        assert fields is not None, f"{path.name} frontmatter cannot be attributed to keys"
        agents[path.stem] = fields
    assert agents, f"no agent files found under {agents_dir}"
    return agents


def description_text(value: str) -> str:
    """Return the logical description: a folded or literal block joined by spaces.

    The flat frontmatter map appends every line after the key to its value,
    including full-line YAML comments that follow the block, so those are dropped.
    """
    lines = [line for line in value.split("\n") if not line.lstrip().startswith("#")]
    if lines[0].strip() in (">", "|", ">-", "|-", ">+", "|+"):
        return " ".join(line.strip() for line in lines[1:] if line.strip())
    return _unquote(" ".join(line.strip() for line in lines))


def check_identity(agents: dict) -> list:
    """Return findings for name and description limits (one per defect)."""
    findings = []
    for stem, fields in agents.items():
        name = _unquote(fields.get("name", ""))
        if name != stem:
            findings.append(f"{stem}: name `{name}` differs from the filename stem")
        if not NAME_RE.match(name):
            findings.append(f"{stem}: name `{name}` is not lowercase-hyphen")
        if len(name) > NAME_MAX:
            findings.append(f"{stem}: name is {len(name)} characters, limit {NAME_MAX}")
        if "description" not in fields:
            findings.append(f"{stem}: description is missing")
        else:
            length = len(description_text(fields["description"]))
            if length > DESCRIPTION_MAX:
                findings.append(f"{stem}: description is {length} characters, limit {DESCRIPTION_MAX}")
    return findings


def _section_rows(reference_text: str, heading: str) -> list:
    """Return the cell lists of the data rows of the first table under `heading`."""
    lines = reference_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^#{2,4}\s+" + re.escape(heading) + r"\s*$", line):
            start = index + 1
            break
    assert start is not None, f"heading `{heading}` not found in the reference"
    rows = []
    in_table = False
    for line in lines[start:]:
        if line.startswith("|"):
            in_table = True
            rows.append(split_row_cells(line))
        elif in_table or re.match(r"^#{1,4}\s", line):
            break
    assert len(rows) >= 3, f"no table rows under `{heading}`"
    return rows[2:]  # drop the header and the separator


def parse_effort_table(reference_text: str) -> tuple:
    """Return ({agent: effort} for pinned rows, {agent} for inherited rows)."""
    pinned = {}
    inherited = set()
    for cells in _section_rows(reference_text, "Shipped Effort Levels"):
        names = BACKTICK_TOKEN_RE.findall(cells[0])
        assert names, f"table row has no agent name: {cells[0]!r}"
        level_tokens = BACKTICK_TOKEN_RE.findall(cells[1])
        if level_tokens:
            assert len(names) == 1, f"a pinned row names one agent: {cells[0]!r}"
            pinned[names[0]] = level_tokens[0]
        else:
            assert "inherited" in cells[1], f"row for {names} is neither pinned nor inherited"
            inherited.update(names)
    assert pinned, "Shipped Effort Levels table lists no pinned agent"
    return pinned, inherited


def parse_value_sets(reference_text: str) -> dict:
    """Return {field: set of allowed values} from the Quick Reference table."""
    sets = {}
    for cells in _section_rows(reference_text, "Quick Reference"):
        field = BACKTICK_TOKEN_RE.findall(cells[0])
        if field and field[0] in VALUE_FIELDS:
            sets[field[0]] = set(BACKTICK_TOKEN_RE.findall(cells[4]))
    for field in VALUE_FIELDS:
        assert sets.get(field), f"Quick Reference lists no values for `{field}`"
    return sets


def check_effort_table(agents: dict, pinned: dict, inherited: set) -> list:
    """Return findings where the table and the agent files disagree, both directions."""
    findings = []
    for stem, fields in agents.items():
        effort = _unquote(fields["effort"]) if "effort" in fields else None
        if stem not in pinned and stem not in inherited:
            findings.append(f"{stem}: not named in the Shipped Effort Levels table")
        elif stem in pinned and effort != pinned[stem]:
            findings.append(f"{stem}: table pins `{pinned[stem]}`, file has {effort!r}")
        elif stem in inherited and effort is not None:
            findings.append(f"{stem}: table lists it as inherited, file sets effort `{effort}`")
    for name in sorted(set(pinned) | inherited):
        if name not in agents:
            findings.append(f"{name}: the table names an agent with no file")
    return findings


def check_values(agents: dict, value_sets: dict) -> list:
    """Return findings for out-of-set values and non-lowercase booleans."""
    findings = []
    for stem, fields in agents.items():
        for field in VALUE_FIELDS:
            if field in fields and _unquote(fields[field]) not in value_sets[field]:
                findings.append(f"{stem}: {field} `{_unquote(fields[field])}` is not in {sorted(value_sets[field])}")
        for key, value in fields.items():
            if "\n" not in value and BAD_BOOLEAN_RE.match(_unquote(value)):
                findings.append(f"{stem}: {key} `{value}` is a boolean that is not lowercase")
    return findings


def _live_findings() -> list:
    agents = load_agents(AGENTS)
    text = REFERENCE.read_text(encoding="utf-8")
    pinned, inherited = parse_effort_table(text)
    return (
        check_identity(agents)
        + check_effort_table(agents, pinned, inherited)
        + check_values(agents, parse_value_sets(text))
    )


class LiveTreeTests(unittest.TestCase):
    """Positive control: the real tree passes, and the checks saw a real tree."""

    def test_live_tree_has_no_findings(self):
        self.assertEqual(_live_findings(), [])

    def test_checks_saw_agents_and_the_table(self):
        agents = load_agents(AGENTS)
        pinned, inherited = parse_effort_table(REFERENCE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(agents), 1)
        self.assertEqual(set(pinned) | inherited, set(agents))

    def test_plan_preflight_is_pinned_high(self):
        pinned, _ = parse_effort_table(REFERENCE.read_text(encoding="utf-8"))
        self.assertEqual(pinned.get("plan-preflight"), "high")


class MutationControlTests(unittest.TestCase):
    """Each fixture adds one defect to a copy of the live tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.agents_dir = Path(self._tmp.name) / "agents"
        shutil.copytree(AGENTS, self.agents_dir)
        self.text = REFERENCE.read_text(encoding="utf-8")

    def _edit(self, stem: str, old: str, new: str) -> None:
        path = self.agents_dir / f"{stem}.md"
        content = path.read_text(encoding="utf-8")
        self.assertIn(old, content, f"fixture precondition: {stem} holds {old!r}")
        path.write_text(content.replace(old, new, 1), encoding="utf-8")

    def _all(self) -> list:
        agents = load_agents(self.agents_dir)
        pinned, inherited = parse_effort_table(self.text)
        return (
            check_identity(agents)
            + check_effort_table(agents, pinned, inherited)
            + check_values(agents, parse_value_sets(self.text))
        )

    def test_renamed_name_fails(self):
        # Breaks agent-authoring.md §2 Required Fields: `name` must match the filename.
        self._edit("plan-reviewer", "name: plan-reviewer", "name: planReviewer")
        findings = self._all()
        self.assertTrue(any(f.startswith("plan-reviewer:") and "name" in f for f in findings), findings)

    def test_removed_table_row_fails(self):
        # Breaks agent-authoring.md §2 Shipped Effort Levels: every agent file is named in the table.
        kept = [line for line in self.text.splitlines() if not line.startswith("| `plan-preflight` |")]
        self.assertLess(len(kept), len(self.text.splitlines()), "fixture precondition: the row exists")
        self.text = "\n".join(kept)
        findings = self._all()
        self.assertTrue(any(f.startswith("plan-preflight:") and "not named" in f for f in findings), findings)

    def test_drifted_effort_fails(self):
        # Breaks agent-authoring.md §2 Shipped Effort Levels: the file's effort equals the table's.
        self._edit("task-runner", "effort: medium", "effort: high")
        findings = self._all()
        self.assertTrue(any(f.startswith("task-runner:") and "table pins" in f for f in findings), findings)

    def test_effort_on_an_inherited_agent_fails(self):
        # Breaks agent-authoring.md §2 Shipped Effort Levels: an inherited agent sets no effort.
        self._edit("fix-agent", "model: sonnet", "model: sonnet\neffort: low")
        findings = self._all()
        self.assertTrue(any(f.startswith("fix-agent:") and "inherited" in f for f in findings), findings)

    def test_out_of_set_model_fails(self):
        # Breaks agent-authoring.md §2 Validation Notes: values come from the listed sets.
        self._edit("fix-agent", "model: sonnet", "model: gpt")
        findings = self._all()
        self.assertTrue(any(f.startswith("fix-agent:") and "model" in f for f in findings), findings)

    def test_uppercase_boolean_fails(self):
        # Breaks agent-authoring.md §2 Validation Notes: YAML booleans are lowercase.
        self._edit("fix-agent", "model: sonnet", "model: sonnet\nbackground: True")
        findings = self._all()
        self.assertTrue(any(f.startswith("fix-agent:") and "background" in f for f in findings), findings)

    def test_overlong_description_fails(self):
        # Breaks agent-authoring.md §2 Required Fields: description is at most 1024 characters.
        self._edit("fix-agent", "model: sonnet", "model: sonnet\ndescription: " + "x" * 1030)
        # a second description key replaces the first in the flat map
        findings = self._all()
        self.assertTrue(any(f.startswith("fix-agent:") and "description" in f for f in findings), findings)


class ParseControlTests(unittest.TestCase):
    """A parse failure is loud, never an empty pass."""

    def test_agent_without_frontmatter_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken-agent.md").write_text("# no frontmatter here\n", encoding="utf-8")
            with self.assertRaises(AssertionError) as caught:
                load_agents(Path(tmp))
            self.assertIn("broken-agent.md", str(caught.exception))

    def test_empty_agents_folder_raises(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(AssertionError):
            load_agents(Path(tmp))

    def test_reference_without_the_table_raises(self):
        with self.assertRaises(AssertionError):
            parse_effort_table("# Title\n\nno table here\n")


if __name__ == "__main__":
    unittest.main()
