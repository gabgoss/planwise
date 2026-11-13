"""Controls for scripts/lint_plan_strategy.py.

Each mutation fixture differs from the positive fixture by one defect, and a
comment names the reference section whose rule the defect breaks.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_plan_strategy as lps

PLAN_ROWS = [
    "| 1 | `ABC-S01-01-Orchestration.md` (this file) | task list |",
    "| 1 | `ABC-S01-01-Recovery.md` | resume point |",
    "| 1 | the task files (Task Files table) | dispatch content |",
    "| 2 | `../ABC-S01-Sprint-Plan.md` | write-set |",
]
REASON = "**Reason:** two Opus tasks (01, 02) and task 02 above 50K."


def task_text(number, agent, tokens):
    return (
        f"# Task: {agent}-Thing{number}\n\n"
        f"**Task ID:** ABC-S01-01-{number:02d}\n"
        f"**Agent:** {agent}\n"
        f"**Estimated Tokens:** ~{tokens}K\n"
        f"**Output:** `Outputs/ABC-S01-01-{number:02d}-Thing.md`\n"
    )


def build(tmp_path, *, mode="DELEGATED", reason=REASON, rows=PLAN_ROWS,
          tasks=(("Opus", 40), ("Opus", 62)), task_table=True):
    for number, (agent, tokens) in enumerate(tasks, start=1):
        name = f"ABC-S01-01-{number:02d}-{agent}-Thing{number}.md"
        (tmp_path / name).write_text(task_text(number, agent, tokens), encoding="utf-8")
    table = "\n".join(
        f"| {n} | [ABC-S01-01-{n:02d}-{a}-Thing{n}.md](ABC-S01-01-{n:02d}-{a}-Thing{n}.md) | {a} |"
        for n, (a, _) in enumerate(tasks, start=1)
    )
    text = "\n".join([
        "# Session Orchestration - ABC-S01-01",
        "",
        "## Required Context Files",
        "",
        "| Priority | File | Purpose |",
        "|----------|------|---------|",
        *rows,
        "",
        "## Execution Strategy",
        "",
        f"**Mode:** {mode}",
        reason,
        "",
        "## Task Files",
        "",
        "| # | Task File | Agent |",
        "|---|-----------|-------|",
        table if task_table else "",
        "",
    ])
    orch = tmp_path / "ABC-S01-01-Orchestration.md"
    orch.write_text(text, encoding="utf-8")
    return orch


def run(capsys, *paths):
    code = lps.main([str(p) for p in paths])
    return code, capsys.readouterr().out


def test_positive_delegated_session_with_named_trigger_and_plan_only_context(tmp_path, capsys):
    code, out = run(capsys, build(tmp_path))
    assert code == 0, out
    assert "task files read: 2" in out


def test_mutation_direct_mode_with_two_opus_tasks(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.1: two Opus tasks require DELEGATED
    code, out = run(capsys, build(tmp_path, mode="DIRECT", tasks=(("Opus", 40), ("Opus", 30))))
    assert code == 1, out
    assert "[§1.1 strategy] 2 Opus tasks (1, 2)" in out
    assert "the mode is DIRECT" in out


def test_mutation_direct_mode_with_one_task_over_50k(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.1: a task over 50K requires DELEGATED
    code, out = run(capsys, build(tmp_path, mode="DIRECT", tasks=(("Sonnet", 40), ("Opus", 62))))
    assert code == 1, out
    assert "tasks over 50K (2: 62K)" in out


def test_mutation_delegated_without_a_named_trigger(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.1: "for consistency" names no trigger
    code, out = run(capsys, build(tmp_path, reason="**Reason:** for consistency."))
    assert code == 1, out
    assert "DELEGATED names no trigger" in out


def test_a_checked_trigger_item_names_the_trigger(tmp_path, capsys):
    reason = "- [x] Session has 2 or more Opus tasks"
    code, out = run(capsys, build(tmp_path, reason=reason))
    assert code == 0, out


def test_mutation_execution_input_row_in_delegated_required_context(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.3: a DELEGATED Required Context lists plan files only
    rows = PLAN_ROWS + ["| 1 | `../ABC-S01-Execution-Input-Part-1-Tree.md` | conventions |"]
    code, out = run(capsys, build(tmp_path, rows=rows))
    assert code == 1, out
    assert "[§1.3 context-boundary]" in out
    assert "../ABC-S01-Execution-Input-Part-1-Tree.md" in out
    assert "ABC-S01-01-Orchestration.md:11:" in out


def test_boundary_applies_only_to_delegated(tmp_path, capsys):
    rows = PLAN_ROWS + ["| 1 | `references/some-rule.md` | rules |"]
    tasks = (("Sonnet", 30), ("Sonnet", 20))
    code, out = run(capsys, build(tmp_path, mode="DIRECT", rows=rows, tasks=tasks))
    assert code == 0, out


def test_sibling_task_files_are_read_without_a_task_files_table(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.1: two Opus tasks under DIRECT
    orch = build(tmp_path, mode="DIRECT", task_table=False)
    code, out = run(capsys, orch)
    assert code == 1, out
    assert "task files read: 2" in out


def test_usage_missing_orchestration_exits_2(tmp_path, capsys):
    code, out = run(capsys, tmp_path / "absent-Orchestration.md")
    assert code == 2
    assert "error: cannot read" in out


def test_usage_no_task_files_at_all_exits_2(tmp_path, capsys):
    orch = tmp_path / "ABC-S01-01-Orchestration.md"
    orch.write_text("# Session Orchestration\n\nNo sections, no tables.\n", encoding="utf-8")
    code, out = run(capsys, orch)
    assert code == 2
    assert "no task files found" in out


def test_no_strategy_or_context_section_is_read_not_crashed(tmp_path, capsys):
    orch = build(tmp_path, tasks=(("Sonnet", 30),))
    text = orch.read_text(encoding="utf-8")
    text = text.replace("## Execution Strategy", "## Notes").replace("## Required Context Files", "## Other")
    orch.write_text(text.replace("**Mode:** DELEGATED", ""), encoding="utf-8")
    code, out = run(capsys, orch)
    assert code == 0, out


def test_usage_task_files_link_to_a_missing_file_exits_2(tmp_path, capsys):
    orch = build(tmp_path)
    next(tmp_path.glob("*-01-Opus-*.md")).unlink()
    code, out = run(capsys, orch)
    assert code == 2
    assert "names a missing file" in out
