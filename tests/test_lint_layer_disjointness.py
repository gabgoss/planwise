"""Controls for scripts/lint_layer_disjointness.py.

Each mutation fixture differs from the positive fixture by one defect, and a
comment names the reference section whose rule the defect breaks.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import dispatch_preflight
import lint_layer_disjointness as lld

OUTPUTS = {
    1: "`Outputs/ABC-S01-01-01-Base.md`",
    2: "`scripts/alpha.py`, `tests/test_alpha.py`, `Outputs/ABC-S01-01-02-*`",
    3: "`scripts/beta.py`, `tests/test_beta.py`, `Outputs/ABC-S01-01-03-*`",
}
CONTEXT = "| 1 | `references/some-rule.md` | the rule |"
STEPS = "1. Write the module.\n2. Run its tests."
VERIFY = "git -C repo diff --name-only -- scripts/beta.py tests/test_beta.py | wc -l"


def task_text(number, output, context=CONTEXT, steps=STEPS, verify=VERIFY):
    return "\n".join([
        f"# Task: Thing{number}",
        "",
        f"**Task ID:** ABC-S01-01-{number:02d}",
        f"**Output:** {output}",
        "",
        "## Required Context",
        "",
        "| Priority | File | Purpose |",
        "|----------|------|---------|",
        context,
        "",
        "## Execution Steps",
        "",
        steps,
        "",
        "## Verification Commands",
        "",
        "```",
        verify,
        "```",
        "",
    ])


def build(tmp_path, *, outputs=None, layer_row="| L2 | {2, 3} | ... | ∅ | none | n/a | ✅ parallel |",
          task3=None, declared="**Declared layers:** L1 = {1} · L2 = {2, 3}"):
    outputs = {**OUTPUTS, **(outputs or {})}
    for number, output in outputs.items():
        text = task3 if (number == 3 and task3) else task_text(number, output)
        (tmp_path / f"ABC-S01-01-{number:02d}-Opus-Thing{number}.md").write_text(text, encoding="utf-8")
    table = "\n".join(
        f"| {n} | [ABC-S01-01-{n:02d}-Opus-Thing{n}.md](ABC-S01-01-{n:02d}-Opus-Thing{n}.md) | Opus |"
        for n in outputs
    )
    text = (
        "# Session Orchestration - ABC-S01-01\n\n"
        "## Dispatch Layers\n\n"
        f"{declared}\n\n"
        "| Layer | Members | Member write-targets | Intersection | Reads | Allocates | Verdict |\n"
        "|-------|---------|----------------------|--------------|-------|-----------|---------|\n"
        f"{layer_row}\n\n"
        "## Task Files\n\n"
        "| # | Task File | Agent |\n"
        "|---|-----------|-------|\n"
        f"{table}\n"
    )
    orch = tmp_path / "ABC-S01-01-Orchestration.md"
    orch.write_text(text, encoding="utf-8")
    return orch


def run(capsys, *paths):
    code = lld.main([str(p) for p in paths])
    return code, capsys.readouterr().out


def test_the_output_parser_is_imported_not_rewritten():
    assert lld.output_paths is dispatch_preflight.output_paths


def test_positive_disjoint_parallel_layer(tmp_path, capsys):
    code, out = run(capsys, build(tmp_path))
    assert code == 0, out
    assert "layers: 2, multi-member: 1" in out


def test_mutation_two_members_share_an_output_path(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.13: a shared Output path with no strategy
    shared = {3: "`scripts/alpha.py`, `tests/test_beta.py`, `Outputs/ABC-S01-01-03-*`"}
    code, out = run(capsys, build(tmp_path, outputs=shared))
    assert code == 1, out
    assert "[§1.13 intersection] L2 members share scripts/alpha.py" in out
    assert "ABC-S01-01-Orchestration.md:5:" in out


def test_mutation_a_shared_path_written_with_a_longer_prefix(tmp_path, capsys):
    # breaks agent-orchestration-delegated.md §1.13: one file under two spellings, no strategy
    shared = {3: "`repo/scripts/alpha.py`, `tests/test_beta.py`, `Outputs/ABC-S01-01-03-*`"}
    code, out = run(capsys, build(tmp_path, outputs=shared))
    assert code == 1, out
    assert "[§1.13 intersection]" in out


def test_a_shared_path_passes_when_the_layer_names_a_strategy(tmp_path, capsys):
    shared = {3: "`scripts/alpha.py`, `tests/test_beta.py`, `Outputs/ABC-S01-01-03-*`"}
    row = "| L2 | {2, 3} | ... | `scripts/alpha.py` | none | n/a | Option C: deltas to the orchestrator |"
    code, out = run(capsys, build(tmp_path, outputs=shared, layer_row=row))
    assert code == 0, out


def test_a_shared_path_across_single_member_layers_passes(tmp_path, capsys):
    shared = {3: "`scripts/alpha.py`, `tests/test_beta.py`, `Outputs/ABC-S01-01-03-*`"}
    declared = "**Declared layers:** L1 = {1} · L2 = {2} · L3 = {3}"
    code, out = run(capsys, build(tmp_path, outputs=shared, declared=declared))
    assert code == 0, out
    assert "multi-member: 0" in out


def test_mutation_a_layer_mate_reads_another_members_output(tmp_path, capsys):
    # breaks §1.31 "A Shared Precondition Belongs to the Orchestrator": a mate consumes a mate's product
    context = "| 1 | `scripts/alpha.py` | the module task 2 writes |"
    task3 = task_text(3, OUTPUTS[3], context=context)
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 1, out
    assert "[§1.31 consumes-mate-output] task 3 reads layer-mate 2's Output: scripts/alpha.py" in out


def test_a_same_named_file_in_another_folder_is_not_a_mate_output(tmp_path, capsys):
    mate = {2: "`plugins/x/README.md`, `tests/test_alpha.py`, `Outputs/ABC-S01-01-02-*`"}
    context = "| 1 | `docs/README.md` | the project readme |"
    task3 = task_text(3, OUTPUTS[3], context=context)
    code, out = run(capsys, build(tmp_path, outputs=mate, task3=task3))
    assert code == 0, out


def test_mutation_a_mate_output_read_by_its_true_path_still_fails(tmp_path, capsys):
    mate = {2: "`plugins/x/README.md`, `tests/test_alpha.py`, `Outputs/ABC-S01-01-02-*`"}
    for context in ("| 1 | `plugins/x/README.md` | the readme |",
                    "| 1 | `repo/plugins/x/README.md` | the readme |"):
        sub = tmp_path / str(abs(hash(context)))
        sub.mkdir()
        task3 = task_text(3, OUTPUTS[3], context=context)
        code, out = run(capsys, build(sub, outputs=mate, task3=task3))
        assert code == 1, out
        assert "[§1.31 consumes-mate-output] task 3 reads layer-mate 2's Output: plugins/x/README.md" in out


def test_mutation_a_bare_file_name_alone_is_not_a_match(tmp_path, capsys):
    mate = {2: "`plugins/x/README.md`, `tests/test_alpha.py`, `Outputs/ABC-S01-01-02-*`"}
    context = "| 1 | `README.md` | some readme |"
    task3 = task_text(3, OUTPUTS[3], context=context)
    code, out = run(capsys, build(tmp_path, outputs=mate, task3=task3))
    assert code == 0, out


def test_mutation_a_layer_mate_reads_a_mates_output_by_pattern_prefix(tmp_path, capsys):
    # breaks §1.31 "A Shared Precondition Belongs to the Orchestrator": the base comes from a mate's Output file
    context = "| 1 | `Outputs/ABC-S01-01-02-Base.md` | base commit |"
    task3 = task_text(3, OUTPUTS[3], context=context)
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 1, out
    assert "Outputs/ABC-S01-01-02-*" in out


def test_mutation_a_member_reads_a_recovery_value(tmp_path, capsys):
    # breaks §1.31 "A Shared Precondition Belongs to the Orchestrator": a runner reads the Recovery file
    steps = "1. Read the base commit from the Recovery file.\n2. Run its tests."
    task3 = task_text(3, OUTPUTS[3], steps=steps)
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 1, out
    assert "[§1.31 recovery-read] task 3" in out


def test_a_negated_recovery_mention_passes(tmp_path, capsys):
    steps = "1. Do not read or write the Recovery file.\n2. Run its tests."
    task3 = task_text(3, OUTPUTS[3], steps=steps)
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 0, out


def test_mutation_a_member_asserts_a_whole_tree_count(tmp_path, capsys):
    # breaks §1.31 "A Shared Precondition Belongs to the Orchestrator": a whole-tree gate inside a batch
    task3 = task_text(3, OUTPUTS[3], verify="git -C repo diff --name-only | wc -l   # MUST equal 2")
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 1, out
    assert "[§1.31 whole-tree-gate] task 3" in out


def test_a_one_commit_file_list_is_not_a_whole_tree_gate(tmp_path, capsys):
    task3 = task_text(3, OUTPUTS[3], verify="git -C repo show --stat --name-only --format= HEAD")
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 0, out


def test_mutation_a_member_asserts_a_clean_whole_tree_status(tmp_path, capsys):
    # breaks §1.31 "A Shared Precondition Belongs to the Orchestrator": an unscoped clean-status gate
    task3 = task_text(3, OUTPUTS[3], verify="git -C repo status --porcelain   # MUST print nothing")
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 1, out
    assert "[§1.31 whole-tree-gate]" in out


def test_usage_missing_orchestration_exits_2(tmp_path, capsys):
    code, out = run(capsys, tmp_path / "absent-Orchestration.md")
    assert code == 2
    assert "error: cannot read" in out


def test_usage_no_declared_layers_exits_2(tmp_path, capsys):
    code, out = run(capsys, build(tmp_path, declared="No layers here."))
    assert code == 2
    assert "no **Declared layers:** line" in out


def test_a_member_with_no_required_context_or_steps_section_is_read_not_crashed(tmp_path, capsys):
    task3 = f"# Task: Thing3\n\n**Task ID:** ABC-S01-01-03\n**Output:** {OUTPUTS[3]}\n"
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 0, out


def test_usage_a_layer_member_with_no_task_file_exits_2(tmp_path, capsys):
    declared = "**Declared layers:** L1 = {1} · L2 = {2, 3, 9}"
    code, out = run(capsys, build(tmp_path, declared=declared))
    assert code == 2
    assert "member 9 has no task file" in out


def test_usage_member_with_no_output_line_exits_2(tmp_path, capsys):
    task3 = task_text(3, OUTPUTS[3]).replace("**Output:**", "**Writes:**")
    code, out = run(capsys, build(tmp_path, task3=task3))
    assert code == 2
    assert "no **Output:** line" in out
