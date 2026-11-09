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


def test_missing_destination_section_is_an_input_error(tmp_path, capsys):
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n")) == 2
    assert "Pre-Known Cross-Task Coordination Flags" in capsys.readouterr().out


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


def test_session_prefix_selects_no_longer_ids(tmp_path, capsys):
    plan = PLAN.replace("| ABC-02 |", "| ABC-020 |").replace("| abc-02 |", "| ABC-021 |")
    assert fsd.main(_write(tmp_path, plan, ORCH_ID_COLLISION)) == 0
    assert "carried rows for session ABC-02: 0" in capsys.readouterr().out


def test_heading_inside_a_fence_is_not_the_section(tmp_path, capsys):
    """A fenced example heading, with a tilde run inside a backtick fence, is skipped."""
    fenced = "```\n~~~\n## Pre-Known Cross-Task Coordination Flags\n~~~\n```\n\n"
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n\n" + fenced)) == 2
    capsys.readouterr()
    assert fsd.main(_write(tmp_path, PLAN, "# Orchestration\n\n" + fenced + ORCH_REPAIRED)) == 0


def test_table_without_consumer_column_is_counted_as_skipped(tmp_path, capsys):
    plan = PLAN.replace("## Next Section", "| Flag | Note |\n|---|---|\n| X | y |\n\n## Next Section")
    fsd.main(_write(tmp_path, plan, ORCH_REPAIRED))
    assert "carried tables skipped (no consuming-session column): 1" in capsys.readouterr().out
