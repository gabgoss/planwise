"""Tests for scripts/extract_status_block.py: the bounded transcript extractor.

A synthetic transcript carries two status blocks. The extractor must print the
last one, exit 1 when nothing matches, and exit 2 on an unreadable file.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import extract_status_block

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "scripts" / "extract_status_block.py"
)

PATTERN = r"(TASK_STATUS:|TASK_ID:|OUTPUT_FILES:)[^\\]{0,40}"


def _block(status: str, task: str, out: str) -> str:
    return f"TASK_STATUS: {status}\nTASK_ID: {task}\nOUTPUT_FILES: {out}\n"


def _transcript(path: Path, messages: list[str]) -> str:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for i, text in enumerate(messages):
            fh.write(json.dumps({"seq": i, "message": {"content": text}}) + "\n")
    return str(path)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_two_blocks_prints_the_last(tmp_path):
    jsonl = _transcript(
        tmp_path / "agent-ademo-1.jsonl",
        [
            "spawn prompt template: " + _block("{COMPLETE|BLOCKED}", "{id}", "{paths}"),
            "working on it, no fields here",
            "first report: " + _block("PARTIAL", "T-1", "/a.md"),
            "final report: " + _block("COMPLETE", "T-1", "/a.md,/b.md"),
            "trailing idle line",
        ],
    )
    res = _run(jsonl, "--pattern", PATTERN)
    assert res.returncode == 0, res.stdout + res.stderr
    lines = res.stdout.splitlines()
    assert lines[0] == "scanned 5 lines, 3 matching"
    assert lines[1:] == [
        "TASK_STATUS: COMPLETE",
        "TASK_ID: T-1",
        "OUTPUT_FILES: /a.md,/b.md",
    ]
    assert "PARTIAL" not in res.stdout
    assert "{COMPLETE|BLOCKED}" not in res.stdout


def test_no_match_exits_1(tmp_path):
    jsonl = _transcript(tmp_path / "agent-ademo-2.jsonl", ["nothing", "still nothing"])
    res = _run(jsonl, "--pattern", PATTERN)
    assert res.returncode == 1
    assert res.stdout.splitlines()[0] == "scanned 2 lines, 0 matching"


def test_empty_file_reads_differently_from_clean(tmp_path):
    empty = tmp_path / "agent-ademo-3.jsonl"
    empty.write_text("", encoding="utf-8")
    res = _run(str(empty), "--pattern", PATTERN)
    assert res.returncode == 1
    assert "scanned 0 lines" in res.stdout


def test_unreadable_file_exits_2(tmp_path):
    res = _run(str(tmp_path / "agent-absent.jsonl"), "--pattern", PATTERN)
    assert res.returncode == 2
    assert "cannot read" in res.stderr


def test_bad_pattern_exits_2(tmp_path):
    jsonl = _transcript(tmp_path / "agent-ademo-4.jsonl", ["x"])
    res = _run(jsonl, "--pattern", "(unclosed")
    assert res.returncode == 2


def test_pattern_is_required(tmp_path):
    jsonl = _transcript(tmp_path / "agent-ademo-5.jsonl", ["x"])
    res = _run(jsonl)
    assert res.returncode == 2


def test_last_block_function_keeps_only_the_last_line(tmp_path):
    jsonl = _transcript(
        tmp_path / "agent-ademo-6.jsonl",
        [_block("BLOCKED", "T-2", "none"), _block("COMPLETE", "T-2", "/c.md")],
    )
    scanned, matching, block = extract_status_block.last_block(Path(jsonl), re.compile(PATTERN))
    assert (scanned, matching) == (2, 2)
    assert block[0] == "TASK_STATUS: COMPLETE"
