"""Tests for scripts/check_status_block.py: the status-block return contract check.

Each mutation input differs from the conforming block by one defect.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_status_block

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "check_status_block.py"

# Conforming eight-field block. The §1.28 field table sets the maxima
# 1, 1, 1, 1, 1, 5, 5, 3 (TASK_STATUS, TASK_ID, ROUTE/FLAGS, OUTPUT_FILES,
# LINES_PRODUCED, VERIFY_RESULTS, KEY_FINDINGS, ISSUES); total 18.
EIGHT = """TASK_STATUS:    COMPLETE
TASK_ID:        ABC-S01-02-03
ROUTE/FLAGS:    none
OUTPUT_FILES:   /abs/out.md
LINES_PRODUCED: 42
VERIFY_RESULTS:
- pytest: 12 passed
- ruff: clean
KEY_FINDINGS:
- finding one
- finding two
ISSUES:         none
"""

SIX = """TASK_STATUS:    COMPLETE
TASK_ID:        ABC-S01-02-03
OUTPUT_FILES:   /abs/out.md
LINES_PRODUCED: 42
KEY_FINDINGS:
- finding one
ISSUES:         none
"""


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=stdin,
        check=False,
    )


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def test_positive_eight_field_block_exits_0(tmp_path):
    result = _run(_write(tmp_path / "b.txt", EIGHT))
    assert result.returncode == 0, result.stdout
    assert "0 breach" in result.stdout


def test_mutation_dropped_field_exits_1(tmp_path):
    # Breaks §1.28 clause 3: every field in the table is present.
    text = EIGHT.replace("ROUTE/FLAGS:    none\n", "")
    result = _run(_write(tmp_path / "b.txt", text))
    assert result.returncode == 1
    assert "missing field ROUTE/FLAGS" in result.stdout


def test_mutation_field_over_its_maximum_exits_1(tmp_path):
    # Breaks §1.28 clause 3: KEY_FINDINGS at six lines, over its maximum of 5.
    text = EIGHT.replace("- finding two\n", "- finding two\n- 3\n- 4\n- 5\n- 6\n")
    result = _run(_write(tmp_path / "b.txt", text))
    assert result.returncode == 1
    assert "field KEY_FINDINGS has 6 lines, max 5" in result.stdout


def test_mutation_total_over_ceiling_exits_1():
    # Breaks §1.28 clause 3: every field at its maximum plus one ISSUES line over 18.
    text = EIGHT.replace("- ruff: clean\n", "- ruff: clean\n- a\n- b\n- c\n")
    text = text.replace("- finding two\n", "- finding two\n- 3\n- 4\n- 5\n")
    assert check_status_block.check_block(text) == []
    over = text.replace("ISSUES:         none\n", "ISSUES:\n- a\n- b\n- c\n- d\n")
    breaches = check_status_block.check_block(over)
    assert "block has 19 lines, max 18" in breaches


def test_mutation_fenced_block_exits_1(tmp_path):
    # Breaks §1.28 clause 1: no re-quoted file content.
    text = EIGHT.replace("- finding two\n", "```\n")
    result = _run(_write(tmp_path / "b.txt", text))
    assert result.returncode == 1
    assert "fenced block" in result.stdout


def test_mutation_blank_field_exits_1(tmp_path):
    # Breaks the §1.28 over-tight clause: ISSUES is written "none", never blanked.
    text = EIGHT.replace("ISSUES:         none\n", "ISSUES:\n")
    result = _run(_write(tmp_path / "b.txt", text))
    assert result.returncode == 1
    assert "field ISSUES is blank" in result.stdout


def test_six_mode_passes_six_field_block_and_eight_mode_fails_it(tmp_path):
    path = _write(tmp_path / "b.txt", SIX)
    assert _run(path, "--fields", "six").returncode == 0
    eight = _run(path)
    assert eight.returncode == 1
    assert "missing field ROUTE/FLAGS" in eight.stdout
    assert "missing field VERIFY_RESULTS" in eight.stdout


def test_stdin_input():
    assert _run("-", stdin=EIGHT).returncode == 0


def test_transcript_recovers_last_block(tmp_path):
    echo = {"message": "spawn template TASK_STATUS: {COMPLETE|BLOCKED}"}
    final = {"message": "Report follows.\n" + EIGHT}
    lines = [json.dumps(echo), json.dumps({"other": 1}), json.dumps(final)]
    path = _write(tmp_path / "agent-x.jsonl", "\n".join(lines) + "\n")
    result = _run("--transcript", path)
    assert result.returncode == 0, result.stdout


def test_transcript_without_block_exits_1(tmp_path):
    path = _write(tmp_path / "agent-x.jsonl", json.dumps({"m": "nothing"}) + "\n")
    assert _run("--transcript", path).returncode == 1


def test_usage_errors_exit_2(tmp_path):
    assert _run().returncode == 2
    assert _run(str(tmp_path / "absent.txt")).returncode == 2
    assert _run(str(tmp_path / "b.txt"), "--transcript", "x.jsonl").returncode == 2
