#!/usr/bin/env python3
"""Static checks for workflows/plan-bodies.js, the plan-bodies workflow script.

The script runs only inside the Workflow tool, so these tests read it as text.
They also hold its hand-copied bodies grammar to the module docstring of
scripts/plan_build.py, which is read as text and never imported.

The path under test can be overridden with the environment variable
PLAN_BODIES_JS, so a corrupted scratch copy can prove the checks fail.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_plan_bodies_workflow.py
"""

import ast
import os
import re
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_DIR / "plugins" / "planwise"
SCRIPT = Path(os.environ.get("PLAN_BODIES_JS") or PLUGIN_DIR / "workflows" / "plan-bodies.js")
PLAN_BUILD = PLUGIN_DIR / "scripts" / "plan_build.py"
PREFLIGHT_AGENT = PLUGIN_DIR / "agents" / "plan-preflight.md"
HANDLER = PLUGIN_DIR / "handlers" / "plan-Part-2-GatherAndGenerate.md"

PHASES_RE = re.compile(r"phases:\s*\[(.*?)\]\s*,?\s*\n\}", re.DOTALL)
PHASE_TITLE_RE = re.compile(r"\{\s*title:\s*'([^']+)'")
REQUIRED_ARGS_RE = re.compile(r"const REQUIRED_ARGS = \[(.*?)\]")
AGENT_OPTIONS_RE = re.compile(r"\{ label: [^\n]*\}")  # the options object of one agent() call
OPTIONS_PHASE_RE = re.compile(r"phase: '([^']+)'")

GRAMMAR_RE = re.compile(r"const BODIES_GRAMMAR = \[(.*?)\]\.join\(", re.DOTALL)
DIRECTIVE_RE = re.compile(r"<!-- (?:doc|fill|section): [^>]*?-->")
FORBIDDEN = ("import(", "Date.now(", "Math.random(", "new Date()", "AskUserQuestion")


def script_text():
    return SCRIPT.read_text(encoding="utf-8")


def plan_build_docstring():
    return ast.get_docstring(ast.parse(PLAN_BUILD.read_text(encoding="utf-8")), clean=False)


def grammar_directives():
    match = GRAMMAR_RE.search(script_text())
    assert match, "BODIES_GRAMMAR array not found in " + str(SCRIPT)
    return DIRECTIVE_RE.findall(match.group(1))


def test_meta_block_names_the_workflow():
    text = script_text()
    assert text.startswith("export const meta = {")
    assert "export const meta" in text
    assert "name: 'plan-bodies'" in text


def test_script_runs_only_the_session_lint():
    assert "plan_build.py lint --session" in script_text()


def test_script_holds_no_forbidden_call():
    text = script_text()
    found = [token for token in FORBIDDEN if token in text]
    assert found == []


def test_grammar_directives_match_the_plan_build_docstring():
    directives = grammar_directives()
    assert len(directives) == 4, directives  # doc, fill, indexed fill, section
    doc = plan_build_docstring()
    missing = [d for d in directives if d not in doc]
    assert missing == []


def phase_titles():
    match = PHASES_RE.search(script_text())
    assert match, "meta.phases array not found in " + str(SCRIPT)
    return PHASE_TITLE_RE.findall(match.group(1))


def test_meta_phases_are_title_objects():
    # The Workflow tool reads each phase as an object. A bare string entry is malformed,
    # and no plugin validator reports it.
    match = PHASES_RE.search(script_text())
    assert match, "meta.phases array not found in " + str(SCRIPT)
    entries = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    assert len(entries) >= 4, entries
    not_objects = [entry for entry in entries if not entry.startswith("{ title: '")]
    assert not_objects == []


def test_every_agent_call_names_a_declared_phase():
    options = AGENT_OPTIONS_RE.findall(script_text())
    assert len(options) >= 5, options  # preflight, read, author, review, apply
    titles = set(phase_titles())
    undeclared = []
    for option in options:
        phase = OPTIONS_PHASE_RE.search(option)
        if not phase or phase.group(1) not in titles:
            undeclared.append(option)
    assert undeclared == []


def test_caller_passes_no_plugin_root():
    text = script_text()
    match = REQUIRED_ARGS_RE.search(text)
    assert match, "REQUIRED_ARGS not found in " + str(SCRIPT)
    assert "'planwise_root'" in match.group(1)  # control: the capture holds the list
    assert "'plugin_root'" not in match.group(1)
    assert "args.plugin_root" not in text and "input.plugin_root" not in text


def test_plugin_root_comes_from_the_preflight_agent_definition():
    # The placeholder resolves in an agent definition body, and stays literal in a
    # workflow script. So the script names the agent type and never holds the placeholder.
    text = script_text()
    assert "agentType: 'planwise:plan-preflight'" in text
    assert "${CLAUDE_PLUGIN_ROOT}" not in text
    agent = PREFLIGHT_AGENT.read_text(encoding="utf-8")
    assert "\nname: plan-preflight\n" in agent
    assert "\nPlugin root: ${CLAUDE_PLUGIN_ROOT}\n" in agent
    tools = [line for line in agent.splitlines() if line.startswith("tools:")]
    assert tools == ["tools: Read, Glob, Grep, Bash"]  # read-only: no Write, no Edit


def test_handler_launch_step_matches_the_script_contract():
    text = HANDLER.read_text(encoding="utf-8")
    start = text.index("**Workflow opt-in, before item 2.**")
    step = text[start:text.index("  2. For each session in order", start)]
    assert 'Workflow({ name: "planwise:plan-bodies"' in step
    assert "`REFUSED:` line, STOP" in step
    assert "as one command, with nothing chained after it" in step
    assert "Do not call `ScheduleWakeup`" in step
    assert "/planwise:plan-bodies" not in step  # the slash form sends a caller to the Skill tool
    assert "`plugin_root`" not in step  # the caller passes no plugin path
