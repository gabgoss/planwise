"""Controls for scripts/dispatch_model_override.py (delegated reference §1.19 and §1.20)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "dispatch_model_override.py"


def task_file(tmp_path: Path, agent: str = "Sonnet", subtotal: str | None = None,
              budget: str | None = None) -> Path:
    if subtotal is None:
        subtotal = "~25.1K (reads: 4.6 + 20.5) + ~12.0K (output) + ~14.9K (working) = **~52K total**"
    lines = ["# Task: Sample", "", "**Task ID:** ABC-T01", f"**Agent:** {agent}"]
    if budget is not None:
        lines.append(f"**Token Budget:** {budget}")
    lines += ["", f"**Context subtotal:** {subtotal}", ""]
    path = tmp_path / "task.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                          capture_output=True, text=True, encoding="utf-8", check=False)


def test_positive_small_total_and_surface_keep_declared_model(tmp_path):
    # Live figure: init_project.py --doctor flagged ~16202 tokens on 2026-11-12.
    result = run(str(task_file(tmp_path)), "--surface-tokens", "16202", "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "MODEL FLOOR: inert for ABC-T01 Sonnet" in result.stdout
    assert "inputs ~25.1K" in result.stdout and "output ~12K" in result.stdout
    assert "safe budget ~165K" in result.stdout


def test_mutation_total_above_165k_raises(tmp_path):
    # §1.19 trip point: the --doctor figure measured 2026-11-12 is ~16202 tokens.
    # Inputs 90.0K + 16.2K + 54K + 12.0K = 172.2K > 165K, so the floor fires.
    subtotal = "~90.0K (reads: 90.0) + ~12.0K (output) + ~14.9K (working) = **~117K total**"
    result = run(str(task_file(tmp_path, subtotal=subtotal)), "--surface-tokens", "16202",
                 "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Opus"
    assert "MODEL FLOOR: raised ABC-T01 Sonnet→1M" in result.stdout
    assert "= ~172.2K > Sonnet safe budget ~165K" in result.stdout


def test_mutation_surface_at_110k_alone_raises(tmp_path):
    # Breaks §1.19 step 3: a flagged surface of ~110K trips the floor by itself.
    subtotal = "~1.0K (reads: 1.0) + ~0.5K (output) + ~1.0K (working) = **~2K total**"
    result = run(str(task_file(tmp_path, subtotal=subtotal)), "--surface-tokens", "110000",
                 "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Opus"
    assert "MODEL FLOOR: raised" in result.stdout


def test_mutation_1m_exception_raises_to_opus(tmp_path):
    # Breaks §1.20: a 1M-exception flagged task under Token Saver on goes to Opus/1M.
    path = task_file(tmp_path, budget="~210K (1M-exception: cost)")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "on")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Opus"
    assert "1M EXCEPTION: raised ABC-T01 Sonnet→1M" in result.stdout


def test_template_cost_marker_raises_and_logs_the_1m_line(tmp_path):
    # templates/task-file.md writes the marker as `1M (cost)` inside `(exception: ...)`.
    path = task_file(tmp_path, budget="~240K (exception: 1M (cost))")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "on")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Opus"
    assert "1M EXCEPTION: raised ABC-T01 Sonnet→1M" in result.stdout


def test_mutation_template_cost_marker_inert_when_token_saver_off(tmp_path):
    path = task_file(tmp_path, budget="~240K (exception: 1M (cost))")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "off")
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "1M EXCEPTION" not in result.stdout


def test_mutation_template_none_marker_does_not_raise(tmp_path):
    path = task_file(tmp_path, budget="~40K (exception: none)")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "on")
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "1M EXCEPTION" not in result.stdout


def test_template_paged_read_marker_keeps_the_paged_read_branch(tmp_path):
    path = task_file(tmp_path, budget="~40K (exception: paged-read (read))")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "on")
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "paged-read required: ABC-T01 keeps Sonnet" in result.stdout
    assert "1M EXCEPTION" not in result.stdout


def test_bare_output_figure_parses_both_figures(tmp_path):
    # templates/task-file.md writes `~33.3K reads + ~5.9K output = ~39.2K`, with no parentheses.
    subtotal = "~33.3K reads + ~5.9K output = ~39.2K"
    result = run(str(task_file(tmp_path, subtotal=subtotal)), "--surface-tokens", "16202",
                 "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert "inputs ~33.3K" in result.stdout and "output ~5.9K" in result.stdout


def test_mutation_bare_output_word_without_a_figure_exits_2(tmp_path):
    subtotal = "~33.3K reads + 5.9K output = ~39.2K"
    result = run(str(task_file(tmp_path, subtotal=subtotal)), "--surface-tokens", "16202",
                 "--token-saver", "off")
    assert result.returncode == 2


def test_1m_exception_inert_when_token_saver_off(tmp_path):
    path = task_file(tmp_path, budget="~210K (1M-exception: cost)")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "1M EXCEPTION" not in result.stdout


def test_read_reason_critical_logs_paged_read_and_keeps_model(tmp_path):
    # §1.20 Window != Readability: a read-reason Critical never raises.
    path = task_file(tmp_path, budget="Critical (read-reason, 30K-token file)")
    result = run(str(path), "--surface-tokens", "16202", "--token-saver", "on")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Sonnet"
    assert "paged-read required: ABC-T01 keeps Sonnet" in result.stdout
    assert "1M EXCEPTION" not in result.stdout


def test_declared_opus_is_never_raised(tmp_path):
    subtotal = "~90.0K (reads: 90.0) + ~12.0K (output) + ~14.9K (working) = **~117K total**"
    result = run(str(task_file(tmp_path, agent="Opus", subtotal=subtotal)),
                 "--surface-tokens", "16202", "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "model: Opus"
    assert "MODEL FLOOR: inert" in result.stdout


def test_doctor_report_input(tmp_path):
    report = tmp_path / "doctor.txt"
    report.write_text("Total always-on injected budget from flagged rules: ~16202 tokens\n", encoding="utf-8")
    result = run(str(task_file(tmp_path)), "--doctor-report", str(report), "--token-saver", "off")
    assert result.returncode == 0, result.stderr
    assert "plan-path rules ~16.2K" in result.stdout
    report.write_text("No overscoped rules found.\n", encoding="utf-8")
    result = run(str(task_file(tmp_path)), "--doctor-report", str(report), "--token-saver", "off")
    assert result.returncode == 0 and "plan-path rules ~0K" in result.stdout


def test_usage_errors_exit_2(tmp_path):
    assert run(str(tmp_path / "missing.md"), "--surface-tokens", "0", "--token-saver", "off").returncode == 2
    assert run(str(task_file(tmp_path)), "--token-saver", "off").returncode == 2
    no_subtotal = tmp_path / "bare.md"
    no_subtotal.write_text("**Agent:** Sonnet\n", encoding="utf-8")
    assert run(str(no_subtotal), "--surface-tokens", "0", "--token-saver", "off").returncode == 2
    assert run(str(task_file(tmp_path, agent="Gpt")), "--surface-tokens", "0",
               "--token-saver", "off").returncode == 2
    bad_report = tmp_path / "bad.txt"
    bad_report.write_text("nothing here\n", encoding="utf-8")
    assert run(str(task_file(tmp_path)), "--doctor-report", str(bad_report),
               "--token-saver", "off").returncode == 2
