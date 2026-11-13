#!/usr/bin/env python3
"""Namespacing pin for every agent spawn in the plugin handlers.

Predicate. Every `subagent_type` value in `handlers/*.md` is either a built-in
subagent type or carries the plugin's own `{plugin-name}:` prefix. A bare agent
name resolves in the consumer project's scope chain, where the plugin's agent
file does not exist, so the spawn fails with "agent not found".

Input. The real handlers folder. The plugin name is read from
`.claude-plugin/plugin.json` and the built-in type names are parsed from the
"Built-in Subagent Types" table of `references/agent-authoring.md`. The test
pins no spawn-site count.

Cannot see. A spawn written without the literal key `subagent_type`, and
whether a prefixed agent name has a file under `agents/`.

Reference section pinned. `agent-orchestration.md §5` (Plugin Handler Spawns
Resolve in the Consumer's Scope Chain).

Controls. The live handlers pass and the scan saw spawn sites (positive). A
bare agent name in a scratch handler fails and names the file and line
(mutation). An empty handlers folder and a missing built-in table fail loudly
(parse).

Run with:  python -m pytest tests/test_handler_spawn_namespacing.py -q
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from markdown_parser import split_row_cells

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
HANDLERS = PLUGIN / "handlers"
AUTHORING = PLUGIN / "references" / "agent-authoring.md"
PLUGIN_JSON = PLUGIN / ".claude-plugin" / "plugin.json"

SPAWN_RE = re.compile(r"""subagent_type\s*[:=]\s*["']?([^"',\s)]+)""")
BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")


def plugin_name() -> str:
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["name"]


def builtin_types(reference_text: str) -> set:
    """Return the first-column names of the Built-in Subagent Types table."""
    lines = reference_text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^###\s+Built-in Subagent Types\s*$", line)), None)
    assert start is not None, "heading `Built-in Subagent Types` not found in the reference"
    names = set()
    in_table = False
    for line in lines[start + 1:]:
        if line.startswith("|"):
            in_table = True
            found = BACKTICK_TOKEN_RE.findall(split_row_cells(line)[0])
            names.update(found)
        elif in_table:
            break
    assert names, "Built-in Subagent Types table lists no type"
    return names


def spawn_sites(handlers_dir: Path) -> list:
    """Return (file name, line number, value) for every `subagent_type` in the handlers."""
    files = sorted(handlers_dir.glob("*.md"))
    assert files, f"no handler files found under {handlers_dir}"
    sites = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in SPAWN_RE.finditer(line):
                sites.append((path.name, number, match.group(1)))
    return sites


def check_spawns(sites: list, prefix: str, builtins: set) -> list:
    """Return one finding per site that is neither built-in nor prefixed."""
    return [
        f"{name}:{number}: subagent_type `{value}` is neither built-in nor `{prefix}`-prefixed"
        for name, number, value in sites
        if value not in builtins and not value.startswith(prefix)
    ]


class LiveTreeTests(unittest.TestCase):
    """Positive control: the live handlers pass and the scan saw real sites."""

    def test_live_handlers_have_no_unprefixed_spawn(self):
        builtins = builtin_types(AUTHORING.read_text(encoding="utf-8"))
        sites = spawn_sites(HANDLERS)
        self.assertEqual(check_spawns(sites, plugin_name() + ":", builtins), [])

    def test_scan_saw_prefixed_sites(self):
        sites = spawn_sites(HANDLERS)
        prefixed = [s for s in sites if s[2].startswith(plugin_name() + ":")]
        self.assertGreaterEqual(len(prefixed), 1)

    def test_builtin_table_names_general_purpose(self):
        self.assertIn("general-purpose", builtin_types(AUTHORING.read_text(encoding="utf-8")))


class MutationControlTests(unittest.TestCase):
    def test_bare_agent_name_fails_and_names_the_line(self):
        # Breaks agent-orchestration.md §5: a handler spawn must use the plugin-namespaced form.
        with tempfile.TemporaryDirectory() as tmp:
            handler = Path(tmp) / "fixture.md"
            handler.write_text(
                'Agent(\n  subagent_type: "planwise:plan-reviewer",\n)\n'
                'Agent(\n  subagent_type: "plan-reviewer",\n)\n',
                encoding="utf-8",
            )
            builtins = builtin_types(AUTHORING.read_text(encoding="utf-8"))
            findings = check_spawns(spawn_sites(Path(tmp)), plugin_name() + ":", builtins)
        self.assertEqual(len(findings), 1, findings)
        self.assertTrue(findings[0].startswith("fixture.md:5:"), findings)
        self.assertIn("plan-reviewer", findings[0])


class ParseControlTests(unittest.TestCase):
    def test_empty_handlers_folder_raises(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(AssertionError):
            spawn_sites(Path(tmp))

    def test_reference_without_the_builtin_table_raises(self):
        with self.assertRaises(AssertionError):
            builtin_types("# Title\n\nno table here\n")


if __name__ == "__main__":
    unittest.main()
