#!/usr/bin/env python3
"""Logic checks for workflows/plan-bodies.js, run through Node against stub agents.

The workflow script runs only inside the Workflow tool. The harness in
tests/workflow_harness/plan_bodies_harness.mjs parses the script as an
async-function body, hands it stub agents, and asserts which agents start in
each case. No agent runs and no API call is made.

The tests skip when `node` is not on PATH. A skip is not a pass: the static
checks in test_plan_bodies_workflow.py still run, and they cover less.

The path under test can be overridden with the environment variable
PLAN_BODIES_JS, as in test_plan_bodies_workflow.py.

Run from the project root:
    python -B -m pytest -q -rs -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_plan_bodies_harness.py
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_DIR / "plugins" / "planwise"
SCRIPT = Path(os.environ.get("PLAN_BODIES_JS") or PLUGIN_DIR / "workflows" / "plan-bodies.js")
HARNESS = Path(__file__).resolve().parent / "workflow_harness" / "plan_bodies_harness.mjs"
NODE = shutil.which("node")
EARLY_RETURN = "if (causes.length > 0) {"

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH, so the workflow logic harness cannot run")


def run_harness(script):
    return subprocess.run([str(NODE), str(HARNESS), str(script)], capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)


def test_harness_passes_on_the_script():
    result = run_harness(SCRIPT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan_bodies_harness: all checks pass" in result.stdout
    assert "PASS case: refused spec, from the REFUSED: line alone" in result.stdout


def test_harness_fails_when_the_early_return_is_removed(tmp_path):
    # Control: with the preflight early return disabled, authors start on a refused spec.
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count(EARLY_RETURN) == 1
    broken = tmp_path / "plan-bodies.js"
    broken.write_text(text.replace(EARLY_RETURN, "if (false) {"), encoding="utf-8")
    result = run_harness(broken)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL case: refused spec, from the REFUSED: line alone" in result.stdout


def test_harness_fails_on_a_syntax_error(tmp_path):
    broken = tmp_path / "plan-bodies.js"
    broken.write_text(SCRIPT.read_text(encoding="utf-8") + "\nconst = ;\n", encoding="utf-8")
    result = run_harness(broken)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL syntax" in result.stdout
