"""Static gate on the /planwise skill's shell-injection lines.

The skill body carries one column-one ``!`` line that runs before the model
sees the prompt, and frontmatter that grants exactly that command. A defect
here aborts every subcommand, so the checks below read the real SKILL.md:

- the ``!`` line starts at column one and ends with ``|| true``, so a failing
  script cannot abort the skill;
- ``allowed-tools`` and the ``!`` line name the identical script token, and
  the grant carries no ``Bash(true)`` (``|| true`` needs none);
- ``arguments:`` declares only ``sub``, and the ``!`` line passes only
  single-quoted named placeholders. An unsupplied positional such as ``$1``
  stays literal and the permission check refuses the whole skill, and a
  second free-text word can carry an apostrophe that ends the quote;
- the skill stays model-invocable, because a handler spawns a subagent that
  runs ``/planwise review``;
- the ``## List`` section names the one-call fallback and ``/planwise init``;
- the routing table and the Help block still list ``list``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
SKILL_MD = PLUGIN / "skills" / "planwise" / "SKILL.md"
SCRIPTS = PLUGIN / "scripts"

EXPECTED_ARGUMENTS = "sub"
SCRIPT_TOKEN_RE = re.compile(r'"\$\{CLAUDE_PLUGIN_ROOT\}/[^"]+"')
PLACEHOLDER_RE = re.compile(r"'\$([A-Za-z_][A-Za-z0-9_]*)'")


def _frontmatter(lines: list[str]) -> dict[str, str] | None:
    if not lines or lines[0] != "---":
        return None
    front: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            return front
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            front[key.strip()] = value.strip()
    return None


def _section(lines: list[str], heading: str) -> list[str]:
    try:
        start = lines.index(heading)
    except ValueError:
        return []
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start + 1 : end]


def skill_line_failures(text: str) -> list[str]:
    """Return one message per failed check; an empty list means the skill passes."""
    failures: list[str] = []
    lines = text.splitlines()
    front = _frontmatter(lines)
    if front is None:
        return ["SKILL.md has no closed frontmatter block"]

    allowed = front.get("allowed-tools", "")
    if not allowed:
        failures.append("frontmatter has no allowed-tools line")
    if "Bash(true)" in allowed:
        failures.append("allowed-tools grants Bash(true); `|| true` needs no grant")
    if front.get("arguments") != EXPECTED_ARGUMENTS:
        failures.append(f"arguments: is {front.get('arguments')!r}, expected {EXPECTED_ARGUMENTS!r}")
    if front.get("disable-model-invocation") != "false":
        failures.append("disable-model-invocation must stay false")

    indented = [ln for ln in lines if ln.lstrip().startswith("!`") and not ln.startswith("!`")]
    if indented:
        failures.append(f"{len(indented)} injection line(s) do not start at column one")
    bang = [ln for ln in lines if ln.startswith("!`")]
    if len(bang) != 1:
        failures.append(f"expected exactly one column-one `!` line, found {len(bang)}")
        return failures
    line = bang[0]
    if not line.endswith(" || true`"):
        failures.append("the `!` line does not end with `|| true`")

    grant_tokens = SCRIPT_TOKEN_RE.findall(allowed)
    line_tokens = SCRIPT_TOKEN_RE.findall(line)
    if len(grant_tokens) != 1 or grant_tokens != line_tokens:
        failures.append(f"script token differs: allowed-tools {grant_tokens} vs `!` line {line_tokens}")

    names = PLACEHOLDER_RE.findall(line)
    if names != (front.get("arguments") or "").split() or names != EXPECTED_ARGUMENTS.split():
        failures.append(f"`!` line placeholders {names} do not match arguments: {EXPECTED_ARGUMENTS!r}")
    rest = PLACEHOLDER_RE.sub("", SCRIPT_TOKEN_RE.sub("", line))
    if "$" in rest:
        failures.append("the `!` line holds a `$` outside the script token and the quoted placeholders")

    list_section = "\n".join(_section(lines, "## List"))
    if 'skill_preflight.py" list' not in list_section:
        failures.append('## List does not name the one-call command `skill_preflight.py" list`')
    if "/planwise init" not in list_section:
        failures.append("## List does not name `/planwise init`")

    if not any(ln.startswith("| `list` |") for ln in lines):
        failures.append("the routing table has no `list` row")
    if not any(ln.startswith("  list") for ln in _section(lines, "## Help")):
        failures.append("the Help block has no line starting `  list`")
    return failures


class TestPlanwiseSkillLines(unittest.TestCase):
    def test_real_skill_passes_every_check(self):
        self.assertEqual(skill_line_failures(SKILL_MD.read_text(encoding="utf-8")), [])

    def test_granted_scripts_exist_beside_the_skill(self):
        for name in ("skill_preflight.py", "list_plans.py"):
            self.assertTrue((SCRIPTS / name).is_file(), name)

    def test_gate_rejects_positional_placeholders(self):
        text = SKILL_MD.read_text(encoding="utf-8").replace("'$sub' || true", '"$0" "$1" || true')
        self.assertTrue(skill_line_failures(text))


if __name__ == "__main__":
    unittest.main()
