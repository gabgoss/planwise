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
