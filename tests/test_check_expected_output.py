"""Tests for scripts/check_expected_output.py: Output tokens against the declared budget.

The Output sizes are derived from measure_files' own ratio, so the 110 % and
130 % cases hold whatever the tokenizer table says.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_expected_output
from measure_files import measure_file

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "check_expected_output.py"

TASK = """# Task: Topic

**Context subtotal:** ~20.0K (reads) + ~10.0K (output) + ~5.0K (working) = **~35K total**
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


def _output_at(tmp_path: Path, tokens: int) -> str:
    """An Output file that measure_files estimates at about ``tokens`` tokens."""
    probe = Path(_write(tmp_path / "probe.md", "x" * 100000))
    ratio = measure_file(str(probe), "opus")["ratio"]
    return _write(tmp_path / "out.md", "x" * round(tokens * ratio))


def test_positive_output_at_110_percent_exits_0(tmp_path):
    task = _write(tmp_path / "task.md", TASK)
    result = _run("--task", task, "--output", _output_at(tmp_path, 11000), "--model", "opus")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "within tolerance" in result.stdout


def test_mutation_output_at_130_percent_exits_1(tmp_path):
    # Breaks §1.4: a deviation above 20 % of the declared budget.
    task = _write(tmp_path / "task.md", TASK)
    result = _run("--task", task, "--output", _output_at(tmp_path, 13000), "--model", "opus")
    assert result.returncode == 1
    assert "review before the next dispatch" in result.stdout


def test_task_without_output_figure_exits_2(tmp_path):
    task = _write(tmp_path / "task.md", TASK.replace(" + ~10.0K (output)", ""))
    result = _run("--task", task, "--output", _output_at(tmp_path, 11000))
    assert result.returncode == 2
    assert "(output)" in result.stderr


def test_usage_errors_exit_2(tmp_path):
    assert _run().returncode == 2
    task = _write(tmp_path / "task.md", TASK)
    assert _run("--task", task, "--output", str(tmp_path / "absent.md")).returncode == 2
    assert _run("--task", str(tmp_path / "absent.md"), "--output", task).returncode == 2


def test_bare_output_figure_is_read_and_checked(tmp_path):
    # templates/task-file.md writes `~33.3K reads + ~5.9K output = ~39.2K`, with no parentheses.
    bare = "**Context subtotal:** ~33.3K reads + ~10.0K output = ~43.3K\n"
    assert check_expected_output.declared_budget(bare) == 10000
    task = _write(tmp_path / "task.md", bare)
    result = _run("--task", task, "--output", _output_at(tmp_path, 11000), "--model", "opus")
    assert result.returncode == 0, result.stdout + result.stderr
    result = _run("--task", task, "--output", _output_at(tmp_path, 13000), "--model", "opus")
    assert result.returncode == 1


def test_mutation_bare_output_without_a_tilde_figure_is_not_read():
    assert check_expected_output.declared_budget("**Context subtotal:** ~33.3K reads + 10.0K output\n") is None
    assert check_expected_output.declared_budget("**Context subtotal:** ~33.3K reads + ~10.0K outputs\n") is None


def test_declared_budget_reads_the_subtotal_line():
    assert check_expected_output.declared_budget(TASK) == 10000
    assert check_expected_output.declared_budget("~10.0K (output)\n") is None
