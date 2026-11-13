"""Tests for scripts/recompute_verdict.py: verdict recomputed from finding counts.

Each mutation input differs from the matching positive input by one defect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import recompute_verdict

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "recompute_verdict.py"

GREEN = """# Findings

- broken: 0
- contradiction: 0
- drift: 0
- missing: 0

**Verdict:** GREEN
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def test_positive_green_file_exits_0(tmp_path):
    result = _run(_write(tmp_path / "f.md", GREEN))
    assert result.returncode == 0, result.stdout + result.stderr


def test_mutation_green_label_on_red_counts_exits_1(tmp_path):
    # Breaks §1.16.1: broken=2 recomputes to RED, the file still says GREEN.
    result = _run(_write(tmp_path / "f.md", GREEN.replace("broken: 0", "broken: 2")))
    assert result.returncode == 1
    assert "reported=GREEN, recomputed=RED" in result.stdout


def test_mutation_green_label_on_yellow_counts_exits_1(tmp_path):
    # Breaks §1.16.1: drift=1 recomputes to YELLOW.
    result = _run(_write(tmp_path / "f.md", GREEN.replace("drift: 0", "drift: 1")))
    assert result.returncode == 1
    assert "recomputed=YELLOW" in result.stdout


def test_table_and_equals_forms():
    text = "| broken | 0 |\n| contradiction | 1 |\nDRIFT=0\nMISSING=0\nverdict = RED\n"
    counts, reported, problems = recompute_verdict.read_findings(text)
    assert problems == []
    assert reported == "RED"
    assert recompute_verdict.recompute(counts) == "RED"


def test_usage_and_unreadable_exit_2(tmp_path):
    assert _run().returncode == 2
    assert _run(str(tmp_path / "absent.md")).returncode == 2


def test_missing_count_and_missing_verdict_exit_2(tmp_path):
    assert _run(_write(tmp_path / "a.md", GREEN.replace("- missing: 0\n", ""))).returncode == 2
    assert _run(_write(tmp_path / "b.md", GREEN.replace("**Verdict:** GREEN\n", ""))).returncode == 2


def test_conflicting_count_exits_2(tmp_path):
    assert _run(_write(tmp_path / "c.md", GREEN + "- broken: 3\n")).returncode == 2
