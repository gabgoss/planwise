"""Tests for scripts/flag_subject_diff.py: carried flags matched by subject."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import flag_subject_diff as fsd

PLAN = """# Plan

## Carried-Forward Coordination Flags

| Flag | Observation | Consuming session | Action |
|---|---|---|---|
| G-06 | The   Lint module is OVER the page cap | ABC-02 | split it |
| G-07 | Ledger keys move with inserted lines | abc-02 | re-key |
| G-08 | Unrelated flag for another session | ABC-05 | none |

## Next Section
"""

ORCH_ID_COLLISION = """# Orchestration

## Pre-Known Cross-Task Coordination Flags

| # | Source | Observation | Action in this task |
|---|---|---|---|
| G-06 | sender | the lint module is over the page cap | split it |
| G-07 | sender | An unrelated flag that reuses the id | none |
"""

ORCH_REPAIRED = ORCH_ID_COLLISION.replace(
    "| G-07 | sender | An unrelated flag that reuses the id | none |",
    "| G-07 | sender | An unrelated flag that reuses the id | none |\n"
    "| G-07b | sender | Ledger keys move with inserted lines | re-key |",
)


def _write(tmp_path, plan, orch):
    p = tmp_path / "plan.md"
    o = tmp_path / "orch.md"
    p.write_text(plan, encoding="utf-8")
    o.write_text(orch, encoding="utf-8")
    return ["--sprint-plan", str(p), "--orchestration", str(o), "--session", "ABC-02"]


def test_id_collision_hides_nothing_known_bad_fires(tmp_path, capsys):
    """The destination carries id G-07 for another subject: the subject match still fires."""
    assert fsd.main(_write(tmp_path, PLAN, ORCH_ID_COLLISION)) == 1
    out = capsys.readouterr().out
    assert "carried rows for session ABC-02: 2" in out
    assert "G-07: Ledger keys move with inserted lines" in out
    assert "G-06" not in out.split("unmatched carried rows")[1]


def test_repaired_destination_matches(tmp_path, capsys):
    assert fsd.main(_write(tmp_path, PLAN, ORCH_REPAIRED)) == 0
    assert "all carried rows matched by subject" in capsys.readouterr().out


def test_case_and_whitespace_are_normalised():
    assert fsd.normalise("The   Lint  module\tIS") == "the lint module is"


def test_missing_destination_section_is_an_empty_source(tmp_path, capsys):
    """An absent optional section is a note: carried rows then read as unmatched."""
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n")) == 1
    out = capsys.readouterr().out
    assert "note: no '## Pre-Known Cross-Task Coordination Flags' heading" in out
    assert "unmatched carried rows: 2" in out
    args = _write(tmp_path, PLAN, "# Orchestration\n")
    args[-1] = "XYZ-09"
    assert fsd.main(args) == 0


def test_missing_carried_section_is_an_empty_source(tmp_path, capsys):
    plan = "# Plan\n\n## Other\n"
    assert fsd.main(_write(tmp_path, plan, ORCH_REPAIRED)) == 0
    out = capsys.readouterr().out
    assert "note: no '## Carried-Forward Coordination Flags' heading" in out
    assert "carried rows for session ABC-02: 0" in out


def test_unreadable_file_still_exits_2(tmp_path, capsys):
    args = _write(tmp_path, PLAN, ORCH_REPAIRED)
    args[1] = str(tmp_path / "absent.md")
    assert fsd.main(args) == 2
    assert capsys.readouterr().out.startswith("error:")


def test_no_carried_rows_prints_zero_count(tmp_path, capsys):
    args = _write(tmp_path, PLAN, ORCH_REPAIRED)
    args[-1] = "XYZ-09"
    assert fsd.main(args) == 0
    assert "carried rows for session XYZ-09: 0" in capsys.readouterr().out


def test_session_matches_as_whole_token_only():
    assert not fsd.names_session("S04-10, S04-12", "S04-1")
    assert not fsd.names_session("S04-1-02", "S04-1")
    assert fsd.names_session("S04-1 and S04-10", "S04-1")
    assert fsd.names_session("ABC-S04-1", "s04-1")


def test_short_session_form_selects_the_full_id_and_nothing_longer():
    """Case a: S06-02 names RFH-S06-02, while a longer or foreign form does not."""
    assert fsd.names_session("S06-02", "RFH-S06-02")
    assert fsd.names_session("RFH-S06-02", "RFH-S06-02")
    assert not fsd.names_session("XYZ-S06-02", "RFH-S06-02")
    assert not fsd.names_session("S06-020", "RFH-S06-02")
    assert not fsd.names_session("S06-02-01", "RFH-S06-02")


def test_short_session_cells_are_selected_by_the_full_id(tmp_path, capsys):
    """Case b: a table that writes the short form is no longer read as empty."""
    plan = PLAN.replace("| ABC-02 |", "| S01-02 |").replace("| abc-02 |", "| s01-02 |")
    args = _write(tmp_path, plan, ORCH_ID_COLLISION)
    args[-1] = "ABC-S01-02"
    fsd.main(args)
    assert "carried rows for session ABC-S01-02: 2" in capsys.readouterr().out


def test_zero_selected_beside_a_non_empty_table_warns(tmp_path, capsys):
    """Case c: a blind zero prints a warning, not the all-matched line, and exits 0."""
    args = _write(tmp_path, PLAN, ORCH_REPAIRED)
    args[-1] = "XYZ-09"
    assert fsd.main(args) == 0
    out = capsys.readouterr().out
    assert "warning: 0 of 3 carried rows name session XYZ-09" in out
    assert "all carried rows matched by subject" not in out


def test_no_carried_section_prints_no_warning(tmp_path, capsys):
    """Case d: an absent section holds no rows, so there is nothing to warn about."""
    assert fsd.main(_write(tmp_path, "# Plan\n\n## Other\n", ORCH_REPAIRED)) == 0
    out = capsys.readouterr().out
    assert "warning:" not in out
    assert "all carried rows matched by subject" in out


def test_session_prefix_selects_no_longer_ids(tmp_path, capsys):
    plan = PLAN.replace("| ABC-02 |", "| ABC-020 |").replace("| abc-02 |", "| ABC-021 |")
    assert fsd.main(_write(tmp_path, plan, ORCH_ID_COLLISION)) == 0
    assert "carried rows for session ABC-02: 0" in capsys.readouterr().out


def test_heading_inside_a_fence_is_not_the_section(tmp_path, capsys):
    """A fenced example heading, with a tilde run inside a backtick fence, is skipped."""
    fenced = "```\n~~~\n## Pre-Known Cross-Task Coordination Flags\n~~~\n```\n\n"
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n\n" + fenced)) == 1
    assert "note: no '## Pre-Known" in capsys.readouterr().out
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n\n" + fenced + ORCH_REPAIRED)) == 0


def test_table_without_consumer_column_is_counted_as_skipped(tmp_path, capsys):
    plan = PLAN.replace("## Next Section", "| Flag | Note |\n|---|---|\n| X | y |\n\n## Next Section")
    fsd.main(_write(tmp_path, plan, ORCH_REPAIRED))
    assert "carried tables skipped (no consuming-session column): 1" in capsys.readouterr().out


# -- second hop: orchestration Pre-Known rows against each task file --------

NO_CARRIED_PLAN = "# Plan\n\n## Other\n"

ORCH_TASK_ROWS = """# Orchestration

## Pre-Known Cross-Task Coordination Flags

### From ABC-S01-01 - recorded 2026-11-14

| Flag # | Source Task | Consuming Task | Observation | Recommended Action | Routed |
|--------|-------------|----------------|-------------|--------------------|--------|
| 1 | up-01 | Task 01 | The split part is OVER the page cap | read the parts | pending |
"""

TASK_NAME_01 = "ABC-S01-02-01-Sonnet-First.md"
TASK_NAME_03 = "ABC-S01-02-03-Sonnet-Third.md"
TASK_WITHOUT_FLAGS = "# Task\n\n## Execution Steps\n\nDo it.\n"
TASK_WITH_FLAG = (
    TASK_WITHOUT_FLAGS
    + "\n## Pre-Known Cross-Task Coordination Flags\n\n"
    "- **Flag 1 from up-01** (routed 2026-11-14): the   split part is OVER the page cap"
    " -> read the parts\n"
)


def _task_run(tmp_path, orch, tasks):
    """Write plan, orchestration and the named task files into ``tmp_path``."""
    (tmp_path / "plan.md").write_text(NO_CARRIED_PLAN, encoding="utf-8")
    (tmp_path / "ABC-S01-02-Orchestration.md").write_text(orch, encoding="utf-8")
    for name, text in tasks.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return [
        "--sprint-plan", str(tmp_path / "plan.md"),
        "--orchestration", str(tmp_path / "ABC-S01-02-Orchestration.md"),
        "--session", "ABC-S01-02",
    ]


def test_task_file_without_the_flag_is_listed_under_its_task_id(tmp_path, capsys):
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {TASK_NAME_01: TASK_WITHOUT_FLAGS})
    assert fsd.main(args) == 1
    out = capsys.readouterr().out
    assert "note: no '## Carried-Forward Coordination Flags' heading" in out
    assert "note: no '## Pre-Known Cross-Task Coordination Flags' heading" in out
    assert "task files: 1" in out
    assert "unrouted task flags: 1" in out
    assert "  ABC-S01-02-01: 1: The split part is OVER the page cap" in out


def test_task_file_carrying_the_flag_bullet_passes(tmp_path, capsys):
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {TASK_NAME_01: TASK_WITH_FLAG})
    assert fsd.main(args) == 0
    assert "unrouted task flags: 0" in capsys.readouterr().out


def test_full_task_id_consumer_selects_that_task_only(tmp_path, capsys):
    orch = ORCH_TASK_ROWS.replace("| Task 01 |", "| ABC-S01-02-03 |")
    args = _task_run(tmp_path, orch, {TASK_NAME_01: TASK_WITHOUT_FLAGS, TASK_NAME_03: TASK_WITHOUT_FLAGS})
    assert fsd.main(args) == 1
    out = capsys.readouterr().out
    assert "task files: 2" in out
    assert "unrouted task flags: 1" in out
    assert "  ABC-S01-02-03: 1:" in out
    assert "  ABC-S01-02-01: 1:" not in out


def test_session_consumer_row_is_listed_for_hand_routing_and_keeps_exit_0(tmp_path, capsys):
    orch = ORCH_TASK_ROWS.replace("| Task 01 |", "| session |")
    args = _task_run(tmp_path, orch, {TASK_NAME_01: TASK_WITHOUT_FLAGS})
    assert fsd.main(args) == 0
    out = capsys.readouterr().out
    assert "rows naming no task (route by hand): 1" in out
    assert "  1: The split part is OVER the page cap" in out
    assert "unrouted task flags: 0" in out


def test_task_ordinal_does_not_match_a_longer_number():
    assert fsd.names_task("Task 01", "ABC-S01-02-01", 1)
    assert fsd.names_task("tasks 1", "ABC-S01-02-01", 1)
    assert not fsd.names_task("Task 10", "ABC-S01-02-01", 1)
    assert not fsd.names_task("Task 01", "ABC-S01-02-03", 3)


def test_no_task_files_skips_the_second_hop(tmp_path, capsys):
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {})
    assert fsd.main(args) == 0
    out = capsys.readouterr().out
    assert "task files: 0" in out
    assert "unrouted task flags" not in out


# -- reworded hits: the sender is named, the subject text is not ----------------

REWORDED_TEXT = "the split segment exceeds its page limit -> read the parts"


def _reworded_task(lead):
    return TASK_WITHOUT_FLAGS + "\n## Pre-Known Cross-Task Coordination Flags\n\n- " + lead + REWORDED_TEXT + "\n"


def test_reworded_task_flag_with_the_reference_lead_counts_as_routed(tmp_path, capsys):
    task = _reworded_task("**Flag 1 from up-01** (routed 2026-11-14): ")
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {TASK_NAME_01: task})
    assert fsd.main(args) == 0
    out = capsys.readouterr().out
    assert "unrouted task flags: 0" in out
    assert "task flags routed by reference, subject reworded (confirm by hand): 1" in out
    assert "  ABC-S01-02-01: 1: The split part is OVER the page cap" in out


def test_reworded_task_flag_without_the_lead_is_no_hit(tmp_path, capsys):
    task = _reworded_task("Scaffold (Orchestration flag 1): ")
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {TASK_NAME_01: task})
    assert fsd.main(args) == 1
    out = capsys.readouterr().out
    assert "unrouted task flags: 1" in out
    assert "task flags routed by reference, subject reworded (confirm by hand): 0" in out


def test_reworded_task_flag_with_the_wrong_source_is_no_hit(tmp_path, capsys):
    task = _reworded_task("**Flag 1 from up-02** (routed 2026-11-14): ")
    args = _task_run(tmp_path, ORCH_TASK_ROWS, {TASK_NAME_01: task})
    assert fsd.main(args) == 1
    out = capsys.readouterr().out
    assert "unrouted task flags: 1" in out
    assert "task flags routed by reference, subject reworded (confirm by hand): 0" in out


def test_reference_matches_whole_tokens_only():
    text = fsd.normalise("- **Flag 11 from up-010** (routed): x")
    assert not fsd.names_reference(text, "1", "up-01")
    assert not fsd.names_reference(text, "11", "up-01")
    assert fsd.names_reference(text, "11", "up-010")


PLAN_WITH_SOURCE = """# Plan

## Carried-Forward Coordination Flags

| Flag # | Source | Observation | Consuming session | Action |
|---|---|---|---|---|
| 4 | up-01 | The Lint module is OVER the page cap | ABC-02 | split it |
"""

ORCH_REWORDED_SUBJECT = """# Orchestration

## Pre-Known Cross-Task Coordination Flags

| Flag # | Source | Observation | Action |
|---|---|---|---|
| 4 | up-01 | Lint module exceeds the page limit | split it |
"""


def test_reworded_carried_row_with_the_same_id_and_source_counts_as_routed(tmp_path, capsys):
    assert fsd.main(_write(tmp_path, PLAN_WITH_SOURCE, ORCH_REWORDED_SUBJECT)) == 0
    out = capsys.readouterr().out
    assert "unmatched carried rows" not in out
    assert "all carried rows matched\n" in out
    assert "carried rows matched by reference, subject reworded (confirm by hand): 1" in out
    assert "  4: The Lint module is OVER the page cap" in out


def test_reworded_carried_row_with_a_different_source_is_no_hit(tmp_path, capsys):
    orch = ORCH_REWORDED_SUBJECT.replace("| 4 | up-01 |", "| 4 | up-09 |")
    assert fsd.main(_write(tmp_path, PLAN_WITH_SOURCE, orch)) == 1
    out = capsys.readouterr().out
    assert "unmatched carried rows: 1" in out
    assert "carried rows matched by reference, subject reworded (confirm by hand): 0" in out


def test_subject_hit_stays_a_plain_match_beside_a_source_column(tmp_path, capsys):
    orch = ORCH_REWORDED_SUBJECT.replace("Lint module exceeds the page limit", "the lint module is over the page cap")
    assert fsd.main(_write(tmp_path, PLAN_WITH_SOURCE, orch)) == 0
    out = capsys.readouterr().out
    assert "all carried rows matched by subject" in out
    assert "subject reworded (confirm by hand): 0" in out
