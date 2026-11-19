"""Cross-language round trip: a TypeScript writer and the Python reader agree on one draft.

`hooks/feedback/render.ts` writes a feedback draft. `scripts/feedback_drafts.py` reads it.
Each side's own tests pass alone, because the TypeScript test round-trips through the
writer's own inverse and the Python tests feed hand-written frontmatter. Neither run
proves the pair. This test renders a draft through the real `renderDraft` under node, then
runs the real reader's `admit` and `list --json` over the file, and compares every
hostile value with a hand-written literal. A literal is never computed by re-implementing
`yamlQuote`, because that would repeat the writer's own logic as the expectation.

The reader strips one quote pair and decodes no escape. The writer therefore emits no
escape: a line break becomes a space, `"` becomes `'` and `\\` becomes `/`.

Mutation control: set FEEDBACK_RENDER_TS to the path of an altered copy of render.ts (with
names.ts beside it) and the writer is loaded from that copy. A `JSON.stringify` writer
makes the title come back as `He said \\"stop\\": C:\\\\x` and the test fails. The shipped
test ignores the variable when it is unset.

Node must be able to run TypeScript. Under CI a missing node, or one without type
stripping, fails the module. Elsewhere it skips with the reason.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "planwise"
FEEDBACK_PY = PLUGIN / "scripts" / "feedback_drafts.py"
OVERRIDE_ENV = "FEEDBACK_RENDER_TS"
NODE = shutil.which("node")

DRAFT_NAME = "2026-10-14-draft-bug-fix-quoted.md"

# The writer's input values, one hostile character class per key.
TITLE_IN = 'He said "stop": C:\\x\nthen left'
SUBCOMMAND_IN = 'a "b"\r\nc'
SESSION_IN = '"quoted"'

# What the reader must return, written by hand from the reader's contract.
TITLE_OUT = "He said 'stop': C:/x then left"
SUBCOMMAND_OUT = "a 'b' c"
SESSION_OUT = "'quoted'"

NODE_SCRIPT = """
import { readFileSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
const [renderPath, payloadPath, outPath] = process.argv.slice(1)
const { renderDraft } = await import(pathToFileURL(renderPath).href)
const payload = JSON.parse(readFileSync(payloadPath, 'utf8'))
writeFileSync(outPath, renderDraft(payload.meta, payload.input), 'utf8')
"""


def _render_path() -> Path:
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        return Path(override)
    return PLUGIN / "hooks" / "feedback" / "render.ts"


def _unusable(reason: str) -> NoReturn:
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="module")
def node_exe() -> str:
    """The node executable, after a probe shows it can run TypeScript."""
    if NODE is None:
        _unusable("node is not on PATH")
    probe = subprocess.run([NODE, "-p", "process.features.typescript"], capture_output=True, text=True, encoding="utf-8", check=False)
    kind = probe.stdout.strip()
    if probe.returncode != 0 or kind not in ("strip", "transform"):
        _unusable(f"node cannot run TypeScript (process.features.typescript = {kind or probe.stderr.strip()!r})")
    return NODE


def _run_reader(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(FEEDBACK_PY), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_writer_output_reads_back_through_the_real_reader(node_exe: str, tmp_path: Path) -> None:
    feedback = tmp_path / "feedback"
    work = tmp_path / "work"
    feedback.mkdir()
    work.mkdir()
    payload = {
        "meta": {
            "draftId": "pending",
            "createdAt": "pending",
            "producer": "planwise-test",
            "sourceSessionId": SESSION_IN,
            "pluginVersion": "1.0.0",
            "cliVersion": "2.1.0",
            "model": "test-model",
            "os": "test-os",
            "status": "pending",
        },
        "input": {
            "kind": "bug",
            "title": TITLE_IN,
            "subcommand": SUBCOMMAND_IN,
            "fields": {"what_happened": "x", "what_expected": "y", "steps": "z"},
        },
    }
    payload_file = work / "payload.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    draft = feedback / DRAFT_NAME

    written = subprocess.run(
        [node_exe, "--input-type=module", "-e", NODE_SCRIPT, str(_render_path()), str(payload_file), str(draft)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert written.returncode == 0, written.stderr
    assert draft.is_file(), "the TypeScript writer wrote no draft"

    admitted = _run_reader("admit", str(draft), "--feedback-dir", str(feedback))
    assert admitted.returncode == 0, admitted.stderr

    listed = _run_reader("list", "--json", "--feedback-dir", str(feedback))
    assert listed.returncode == 0, listed.stderr
    records = json.loads(listed.stdout)
    assert len(records) == 1, records
    record = records[0]

    assert record["title"] == TITLE_OUT
    assert record["subcommand"] == SUBCOMMAND_OUT
    assert record["source_session_id"] == SESSION_OUT
    assert record["kind"] == "bug"
    assert record["drafted_by"] == "model"
    assert record["status"] == "queued"
