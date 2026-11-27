"""Tests for scripts/dispatch_preflight.py: the six preflight set checks."""

import re
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import dispatch_preflight as dp
import scaffold_plan as sp
from test_scaffold_plan import make_spec


def _w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- overlap ----------------------------------------------------------------


def _task(tmp_path, name, output_line):
    return _w(tmp_path / name, f"# Task\n\n**Output:** {output_line}\n\n## Objective\n")


def test_overlap_known_bad_fires(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`, `tests/test_a.py` (new); `PIN_NAME` only")
    run = _task(tmp_path, "r.md", "`scripts\\a.py`; `docs/b.md`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", str(run)]) == 1
    out = capsys.readouterr().out
    assert "candidate output paths: 2" in out
    assert "  scripts/a.py" in out


def test_overlap_repaired_is_disjoint(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`, `tests/test_a.py`")
    run = _task(tmp_path, "r.md", "`scripts/c.py`; `docs/b.md`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", str(run)]) == 0
    assert "disjoint" in capsys.readouterr().out


def test_output_paths_is_importable_and_skips_non_paths():
    assert dp.output_paths("**Output:** `a/b.md`, `NAME_ONLY`, `c.py`") == {"a/b.md", "c.py"}
    assert dp.output_paths("no output line here") is None


def test_overlap_missing_output_line_is_input_error(tmp_path):
    cand = _w(tmp_path / "c.md", "# Task with no output line\n")
    run = _task(tmp_path, "r.md", "`x.md`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", str(run)]) == 2


def test_overlap_without_running_is_disjoint(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`")
    assert dp.main(["overlap", "--candidate", str(cand)]) == 0
    out = capsys.readouterr().out
    assert "running tasks: 0" in out
    assert "disjoint" in out


def test_overlap_without_running_still_checks_the_candidate(tmp_path, capsys):
    cand = _w(tmp_path / "c.md", "# Task with no output line\n")
    assert dp.main(["overlap", "--candidate", str(cand)]) == 2
    assert "no **Output:** line" in capsys.readouterr().out


def test_overlap_running_none_is_the_empty_set(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", "none"]) == 0
    out = capsys.readouterr().out
    assert "running tasks: 0" in out
    assert "disjoint" in out


def test_overlap_running_none_ignores_case(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", "NONE"]) == 0
    assert "running tasks: 0" in capsys.readouterr().out


def test_overlap_running_none_beside_a_path_is_input_error(tmp_path, capsys):
    cand = _task(tmp_path, "c.md", "`scripts/a.py`")
    run = _task(tmp_path, "r.md", "`docs/b.md`")
    assert dp.main(["overlap", "--candidate", str(cand), "--running", "none", str(run)]) == 2
    assert "cannot be combined" in capsys.readouterr().out


# --- prereq -----------------------------------------------------------------


def _plan_tree(tmp_path, prereq_line):
    root = tmp_path / "Exec"
    for n in (1, 2, 3, 5, 7, 8):
        (root / f"Sprint-{n:02d}-X").mkdir(parents=True)
    plan = _w(root / "Sprint-07-X" / "plan.md", f"# Plan\n\n## Prerequisites\n\n{prereq_line}\n")
    return plan, root


def test_prereq_known_bad_fires(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03 ALL COMPLETE")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 1
    out = capsys.readouterr().out
    assert "derived, not enumerated: [5, 8]" in out


def test_prereq_repaired_is_equal(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03, 05 and 08 ALL COMPLETE")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0
    out = capsys.readouterr().out
    assert "quantified lines with an enumeration: 1" in out
    assert "equal: every quantified enumeration matches its derived set" in out
    assert "not checked:" not in out


def test_prereq_own_sprint_folder_is_not_run(tmp_path, capsys):
    # The Orchestration once told the orchestrator to pass the sprint's own folder.
    # That folder holds session folders and no Sprint-NN folder, so nothing was compared.
    plan, _root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03, 05 and 08 ALL COMPLETE")
    (plan.parent / "Session-01-X").mkdir()
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(plan.parent)]) == 2
    out = capsys.readouterr().out
    assert "sprint folders listed: 0" in out
    assert "not run:" in out
    assert "equal:" not in out


def test_prereq_own_sprint_folder_without_quantified_line_is_not_run(tmp_path, capsys):
    # The reported run: zero folders listed and zero quantified lines. It printed equal and exited 0.
    plan, _root = _plan_tree(tmp_path, "**Prerequisite:** Sprint 03")
    (plan.parent / "Session-01-X").mkdir()
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(plan.parent)]) == 2
    out = capsys.readouterr().out
    assert "sprint folders listed: 0" in out
    assert "not run:" in out
    assert "equal:" not in out
    assert "not checked:" not in out


def test_prereq_folder_without_own_sprint_is_not_run(tmp_path, capsys):
    # A folder that lists sprints but not this plan's own sprint is the wrong folder.
    plan, _root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03, 05 and 08 ALL COMPLETE")
    other = tmp_path / "Other"
    (other / "Sprint-01-X").mkdir(parents=True)
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(other)]) == 2
    out = capsys.readouterr().out
    assert "sprint folders listed: 1" in out
    assert "not run:" in out
    assert "equal:" not in out


def test_prereq_prior_restricts_to_lower_numbers(tmp_path):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** all prior sprints: Sprints 01-03 and 05")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0


def test_prereq_unquantified_line_is_not_checked(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprint 03")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0
    out = capsys.readouterr().out
    assert "quantified lines with an enumeration: 0" in out
    assert "not checked: no quantified prerequisite line enumerates sprints" in out
    assert "equal:" not in out


def test_short_form_skips_task_id_segments():
    assert dp.enumerated_sprints("consumes RFH-S04-01 output") == set()
    assert dp.enumerated_sprints("consumes S04-01 output") == set()
    assert dp.enumerated_sprints("needs S04 and ES7") == {4, 7}


def test_short_form_range_expands():
    assert dp.enumerated_sprints("all of S01–S03") == {1, 2, 3}
    assert dp.enumerated_sprints("all of S01-S03") == {1, 2, 3}
    assert dp.enumerated_sprints("all of S01 to S03") == {1, 2, 3}
    assert dp.enumerated_sprints("Sprints 01 to 03") == {1, 2, 3}


def test_prereq_short_range_known_bad_and_repaired(tmp_path):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** all of S01-S03 and S05")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 1
    plan, root = _plan_tree(tmp_path / "b", "**Prerequisite:** all of S01-S03, S05 and S08")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0


def test_prereq_reads_only_the_prerequisites_section(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "- **Prerequisite:** all prior sprints: Sprints 01-03 and 05")
    outside = (
        "\n## Cross-Sprint File Touches\n\n"
        "Every pair is ordered, so no pair runs concurrently. The S05 writer of each row opens with a"
        " prerequisite grep gate.\n"
        "\n## Change Log\n\n"
        "| Date | Change |\n|---|---|\n"
        "| 2026-11-20 | Every session re-estimated; the prerequisite total for Sprints 700K is final |\n"
    )
    _w(plan, plan.read_text(encoding="utf-8") + outside)
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0
    out = capsys.readouterr().out
    assert "prerequisite lines: 1" in out
    assert "difference on:" not in out
    assert "equal: every quantified enumeration matches its derived set" in out


def test_prereq_without_prerequisites_section_is_not_run(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "unused")
    _w(plan, "# Plan\n\n**Prerequisite:** Sprints 01-03, 05 and 08 ALL COMPLETE\n")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 2
    out = capsys.readouterr().out
    assert "not run: no Prerequisites section" in out
    assert "equal:" not in out


def test_prereq_title_naming_prerequisites_is_not_the_section(tmp_path, capsys):
    # The title folds to a text that contains "prerequisites". A level-1 pick would read the whole plan.
    plan, root = _plan_tree(tmp_path, "unused")
    title = "# Sprint 07: PrerequisiteScope\n\n"
    section = "## Prerequisites <!-- REQUIRED -->\n\n- **Prerequisite:** all prior sprints: Sprints 01-03 and 05\n\n"
    log = "## Change Log\n\n| 2026-11-20 | the prerequisite total for all Sprints 700K is final |\n"
    args = ["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]
    _w(plan, title + section + log)
    assert dp.main(args) == 0
    assert "prerequisite lines: 1" in capsys.readouterr().out
    _w(plan, title + log)
    assert dp.main(args) == 2
    assert "not run: no Prerequisites section" in capsys.readouterr().out


def test_prereq_longer_heading_above_the_section_is_not_picked(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "unused")
    other = "## Cross-Sprint Prerequisites\n\n- No prerequisite lists a sprint here.\n\n"
    section = "## Prerequisites <!-- REQUIRED -->\n\n- **Prerequisite:** Sprints 01-03 ALL COMPLETE\n"
    _w(plan, "# Plan\n\n" + other + section)
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 1
    assert "derived, not enumerated: [5, 8]" in capsys.readouterr().out


# --- fences -----------------------------------------------------------------


def test_unfenced_follows_the_commonmark_close_rule():
    lines = ["```", "~~~", "in fence", "~~~", "```", "out"]
    assert dp.unfenced(lines) == ["out"]
    assert dp.unfenced(["````", "```", "still in", "````", "out"]) == ["out"]
    assert dp.unfenced(["~~~", "x", "~~~ info", "y", "~~~", "out"]) == ["out"]
    assert dp.unfenced(["```py `x`", "not a fence"]) == ["```py `x`", "not a fence"]


def test_heading_inside_fence_is_not_a_section():
    text = "# R\n\n```\n~~~\n## Files Modified\n- `a/fake.md`\n~~~\n```\n"
    assert dp.section_lines(text, "Files Modified") is None
    assert dp.files_modified(text) == set()


# --- siblings ---------------------------------------------------------------

RECOVERY = """# Recovery

## Change Log

| Date | Step | Status |
|---|---|---|
| {date} | 1 | COMPLETE |

## Files Modified

- `plugins/x/references/shared.md`
- tests/test_other.py
"""


def _siblings_args(tmp_path, date, edit_lines):
    rec = _w(tmp_path / "rec.md", RECOVERY.format(date=date))
    edit = _w(tmp_path / "edit.txt", "\n".join(edit_lines) + "\n")
    return ["siblings", "--since", "2026-01-10", "--recoveries", str(rec), "--edit-set", str(edit)]


def test_siblings_known_bad_fires(tmp_path, capsys):
    args = _siblings_args(tmp_path, "2026-01-12", ["# sweep set", "repo/plugins/x/references/shared.md"])
    assert dp.main(args) == 1
    assert "  plugins/x/references/shared.md" in capsys.readouterr().out


def test_siblings_repaired_is_none(tmp_path, capsys):
    args = _siblings_args(tmp_path, "2026-01-12", ["repo/plugins/x/references/other.md"])
    assert dp.main(args) == 0
    assert "recoveries on or after 2026-01-10: 1" in capsys.readouterr().out


def test_siblings_closed_before_since_is_out_of_window(tmp_path, capsys):
    args = _siblings_args(tmp_path, "2026-01-01", ["plugins/x/references/shared.md"])
    assert dp.main(args) == 0
    assert "recoveries on or after 2026-01-10: 0" in capsys.readouterr().out


def test_siblings_recoveries_none_is_the_empty_set(tmp_path, capsys):
    edit = _w(tmp_path / "edit.txt", "plugins/x/references/shared.md\n")
    args = ["siblings", "--since", "2026-01-10", "--recoveries", "none", "--edit-set", str(edit)]
    assert dp.main(args) == 0
    assert "recoveries given: 0" in capsys.readouterr().out


def test_paths_meet_needs_a_component_boundary():
    assert dp.paths_meet("a/b/shared.md", "b/shared.md")
    assert not dp.paths_meet("a/b/unshared.md", "shared.md")


@pytest.mark.parametrize(
    ("line", "met"),
    [
        ("- plugins/planwise/scripts/feedback_post.py, handlers/feedback.md", "handlers/feedback.md"),
        ("- `plugins/planwise/scripts/feedback_post.py`, handlers/feedback.md", "handlers/feedback.md"),
        ("- plugins/planwise/handlers/feedback.md -- added the route question", "plugins/planwise/handlers/feedback.md"),
        ("- `plugins/planwise/scripts/feedback_post.py`, `handlers/feedback.md`", "handlers/feedback.md"),
        ("| handlers/feedback.md | +12/-0 |", "handlers/feedback.md"),
        ("- [the handler](plugins/planwise/handlers/feedback.md): two rows.", "plugins/planwise/handlers/feedback.md"),
        ("- **handlers/feedback.md:** added the route question", "handlers/feedback.md"),
        ('- "handlers/feedback.md".', "handlers/feedback.md"),
        ("- [handlers/feedback.md]", "handlers/feedback.md"),
    ],
)
def test_every_path_token_on_a_files_modified_line_is_read(line, met):
    text = f"## Files Modified\n\n{line}\n"
    edit = {"plugins/planwise/handlers/feedback.md"}
    assert dp.intersect(dp.files_modified(text), edit) == {met}


def test_siblings_two_path_bullet_meets_the_second_path(tmp_path, capsys):
    rec = _w(
        tmp_path / "rec.md",
        "# Recovery\n\nDate: 2026-01-12\n\n## Files Modified\n\n"
        "- plugins/planwise/scripts/feedback_post.py, handlers/feedback.md\n",
    )
    edit = _w(tmp_path / "edit.txt", "plugins/planwise/handlers/feedback.md\n")
    args = ["siblings", "--since", "2026-01-10", "--recoveries", str(rec), "--edit-set", str(edit)]
    assert dp.main(args) == 1
    assert "  handlers/feedback.md" in capsys.readouterr().out


# --- decomposition ----------------------------------------------------------

MATRIX = """# Matrix

| Surface | Mode |
|---|---|
| S-run-sequential | one |
| S-run-delegated | two |
"""


def _decomp_args(tmp_path, output_text):
    m = _w(tmp_path / "matrix.md", MATRIX)
    o = _w(tmp_path / "out.md", output_text)
    return ["decomposition", "--matrix", str(m), "--output", str(o), "--heading-prefix", "S-"]


def test_decomposition_known_bad_lists_both_sides(tmp_path, capsys):
    out_text = "# Out\n\n## S-run-sequential\n\n## S-extra\n\n## Notes\n"
    assert dp.main(_decomp_args(tmp_path, out_text)) == 1
    out = capsys.readouterr().out
    assert "rows with no section: 1" in out and "  s-run-delegated" in out
    assert "sections with no row: 1" in out and "  s-extra" in out


def test_decomposition_repaired_is_empty_both_ways(tmp_path, capsys):
    out_text = "# Out\n\n## S-run-sequential\n\n## `S-run-delegated`\n\n## Notes\n"
    assert dp.main(_decomp_args(tmp_path, out_text)) == 0
    out = capsys.readouterr().out
    assert "decomposition rows: 2" in out and "output sections: 2" in out


# --- upstream ---------------------------------------------------------------

# One Required Context row of a real sprint sweep task, with its plan abbreviation replaced.
UPSTREAM_ROW = (
    "| 1 | the four session sweep Outputs (`Outputs/ABC-S04-01-10-CodeRowLedgerAndSessionSweep.md`, "
    "`Outputs/ABC-S04-02-09-DecisionRecordAndSweep.md`, `Outputs/ABC-S04-03-05-SessionSweep.md`, "
    "`Outputs/ABC-S04-04-05-SessionSweep.md`, each in its session folder) "
    "— their gate sections; the decision record is the second Output's first half "
    "| 20.4 (ceiling: the Outputs do not exist at authoring) | ~8.0K | the session readings |"
)
LIVE_FOUR = (
    "s1/Outputs/ABC-S04-01-10-CodeRowLedgerAndSessionSweep.md",
    "s2/Outputs/ABC-S04-02-09-DecisionRecord.md",
    "s3/Outputs/ABC-S04-03-05-SessionSweep.md",
    "s4/Outputs/ABC-S04-04-05-SessionSweep.md",
)


def _upstream_args(tmp_path, live_files, row=UPSTREAM_ROW, after=""):
    """Build a plan folder holding ``live_files`` and one task file; return the CLI argument list."""
    root = tmp_path / "plan"
    for rel in live_files:
        _w(root / rel, "# produced\n")
    task = _w(
        root / "s5" / "ABC-S04-05-06-Sonnet-Sweep.md",
        "# Task\n\n## Required Context\n\n| Priority | File | KiB | ~Tokens | Purpose |\n"
        f"|---|---|--:|--:|---|\n{row}\n\n## Objective\n\n{after}\n",
    )
    return ["upstream", "--candidate", str(task), "--plan-root", str(root)]


def test_upstream_drift_names_the_live_file(tmp_path, capsys):
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR)) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "required-context output paths: 4"
    assert out.count("resolved: ") == 3
    assert (
        "drift: Outputs/ABC-S04-02-09-DecisionRecordAndSweep.md -> s2/Outputs/ABC-S04-02-09-DecisionRecord.md" in out
    )


def test_upstream_live_name_is_resolved(tmp_path, capsys):
    row = UPSTREAM_ROW.replace("DecisionRecordAndSweep", "DecisionRecord")
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR, row=row)) == 0
    out = capsys.readouterr().out
    assert "required-context output paths: 4" in out and out.count("resolved: ") == 4
    assert "drift" not in out and "missing" not in out


def test_upstream_absent_producer_is_missing(tmp_path, capsys):
    live = [p for p in LIVE_FOUR if "02-09" not in p]
    assert dp.main(_upstream_args(tmp_path, live)) == 1
    out = capsys.readouterr().out
    assert "missing: Outputs/ABC-S04-02-09-DecisionRecordAndSweep.md" in out
    assert "drift" not in out


def test_upstream_two_hits_are_ambiguous_and_never_picked(tmp_path, capsys):
    live = [*LIVE_FOUR, "s6/Outputs/ABC-S04-02-09-DecisionRecordDraft.md"]
    assert dp.main(_upstream_args(tmp_path, live)) == 1
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("ambiguous: "))
    assert "s2/Outputs/ABC-S04-02-09-DecisionRecord.md" in line
    assert "s6/Outputs/ABC-S04-02-09-DecisionRecordDraft.md" in line
    assert "drift" not in out


def test_upstream_zero_paths_is_clean(tmp_path, capsys):
    row = "| 1 | `../Sprint-Signoff.md` | 24.9 | ~9.8K | the anchors to run |"
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR, row=row)) == 0
    assert "required-context output paths: 0" in capsys.readouterr().out


def test_upstream_name_with_no_task_id_and_no_file_is_unresolved(tmp_path, capsys):
    row = "| 1 | `Outputs/notes.md` | 1 | ~1K | notes |"
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR, row=row)) == 1
    assert "unresolved: Outputs/notes.md" in capsys.readouterr().out


def test_upstream_path_beside_the_task_file_is_resolved(tmp_path, capsys):
    row = "| 1 | `Outputs/ABC-S04-05-01-Local.md` | 1 | ~1K | local |"
    live = [*LIVE_FOUR, "s5/Outputs/ABC-S04-05-01-Local.md", "s6/Outputs/ABC-S04-05-01-Local.md"]
    assert dp.main(_upstream_args(tmp_path, live, row=row)) == 0
    assert "resolved: Outputs/ABC-S04-05-01-Local.md" in capsys.readouterr().out


def test_upstream_same_basename_in_two_folders_is_ambiguous(tmp_path, capsys):
    row = "| 1 | `Outputs/notes.md` | 1 | ~1K | notes |"
    live = [*LIVE_FOUR, "s6/Outputs/notes.md", "s7/Outputs/notes.md"]
    assert dp.main(_upstream_args(tmp_path, live, row=row)) == 1
    assert "ambiguous: Outputs/notes.md -> s6/Outputs/notes.md, s7/Outputs/notes.md" in capsys.readouterr().out


def test_upstream_reads_only_the_required_context_section(tmp_path, capsys):
    row = "| 1 | `../Sprint-Signoff.md` | 24.9 | ~9.8K | the anchors to run |"
    after = "Write `Outputs/ABC-S04-09-09-Elsewhere.md` and see `Outputs/ABC-S04-*-Glob.md`."
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR, row=row, after=after)) == 0
    assert "required-context output paths: 0" in capsys.readouterr().out


def test_upstream_glob_and_placeholder_spans_name_no_one_file(tmp_path, capsys):
    row = "| 1 | `Outputs/ABC-S04-*-Sweep.md`, `Outputs/{ABBREV}-S01-01-01-X.md` | 1 | ~1K | globs |"
    assert dp.main(_upstream_args(tmp_path, LIVE_FOUR, row=row)) == 0
    assert "required-context output paths: 0" in capsys.readouterr().out


def test_upstream_unreadable_input_is_exit_two(tmp_path, capsys):
    args = _upstream_args(tmp_path, LIVE_FOUR)
    missing = ["upstream", "--candidate", str(tmp_path / "none.md"), "--plan-root", args[4]]
    assert dp.main(missing) == 2
    no_root = ["upstream", "--candidate", args[2], "--plan-root", str(tmp_path / "no-such-folder")]
    assert dp.main(no_root) == 2
    bare = _w(tmp_path / "bare.md", "# Task\n\n## Objective\n\n`Outputs/ABC-S04-02-09-X.md`\n")
    assert dp.main(["upstream", "--candidate", str(bare), "--plan-root", args[4]]) == 2
    assert "no Required Context section" in capsys.readouterr().out


# --- depends ----------------------------------------------------------------
# Every tree is the one the renderer writes for test_scaffold_plan's sample spec:
# session 1 task 02 depends on task 01, and each Recovery row starts PENDING.

SESSION_1 = "Sprint-01-LedgerCore/Session-01-ReadPath"
SESSION_2 = "Sprint-01-LedgerCore/Session-02-WritePath"
RECOVERY_1 = f"{SESSION_1}/QZX-S01-01-Recovery.md"
TASK_1_1 = f"{SESSION_1}/QZX-S01-01-01-Sonnet-ParseRows.md"
TASK_1_2 = f"{SESSION_1}/QZX-S01-01-02-Opus-IndexRows.md"
TASK_2_1 = f"{SESSION_2}/QZX-S01-02-01-Sonnet-WriteRows.md"


@pytest.fixture
def plan(tmp_path):
    files, _rec = sp.render_all(make_spec(), sp.DEFAULT_TEMPLATES)
    root = tmp_path / "plan"
    sp.write_tree(files, root)
    return root


def _rewrite(path: Path, pattern: str, replacement: str) -> None:
    """Replace one match, byte for byte, so the file keeps its line endings."""
    text, count = re.subn(pattern, lambda _m: replacement, path.read_bytes().decode("utf-8"), count=1)
    assert count == 1, pattern
    path.write_bytes(text.encode("utf-8"))


def _set_depends(root, task, value):
    _rewrite(root / task, r"\*\*Depends On:\*\*[^\r\n]*", f"**Depends On:** {value}")


def _set_status(root, step, status, recovery=RECOVERY_1):
    path = root / recovery
    row = re.search(rf"(?m)^(\| {step} \|[^|]*\|[^|]*\|) PENDING \|", path.read_bytes().decode("utf-8"))
    assert row, step
    _rewrite(path, re.escape(row.group(0)), f"{row.group(1)} {status} |")


def _depends(capsys, root, task):
    code = dp.main(["depends", "--candidate", str(root / task), "--plan-root", str(root)])
    return code, capsys.readouterr().out.splitlines()


def test_depends_pending_producer_stops(plan, capsys):
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out) == (1, ["depends-on entries: 1", "not-complete: 01 (PENDING)"])


def test_depends_complete_producer_passes(plan, capsys):
    _set_status(plan, 1, "COMPLETE")
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out) == (0, ["depends-on entries: 1", "complete: 01"])


def test_depends_no_producer(plan, capsys):
    assert _depends(capsys, plan, TASK_1_1) == (0, ["depends-on entries: 0"])


@pytest.mark.parametrize("value", ["", "None", "n/a", "- (parallel group; cross-sprint gate in Step 1)"])
def test_depends_empty_spellings_name_no_producer(plan, capsys, value):
    _set_depends(plan, TASK_1_2, value)
    assert _depends(capsys, plan, TASK_1_2) == (0, ["depends-on entries: 0"])


def test_depends_missing_line_names_no_producer(plan, capsys):
    _rewrite(plan / TASK_1_2, r"\*\*Depends On:\*\*[^\r\n]*\r?\n", "")
    assert _depends(capsys, plan, TASK_1_2) == (0, ["depends-on entries: 0"])


@pytest.mark.parametrize("value", ["1", "Task 01", "`01`", "01 (`RUN_BASE`; the row ledger)",
                                   "01 <!-- the parser -->", "**01**", "01, 01"])
def test_depends_same_session_spellings(plan, capsys, value):
    _set_depends(plan, TASK_1_2, value)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out[0]) == (1, "depends-on entries: 1")
    assert out[1].startswith("not-complete: ")
    _set_status(plan, 1, "COMPLETE")
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 0, out


@pytest.mark.parametrize("value", ["1-2", "1 to 2", "01–02", "Tasks 1 - 2"])
def test_depends_range_names_every_task_in_it(plan, capsys, value):
    _set_depends(plan, TASK_1_1, value)
    _set_status(plan, 1, "COMPLETE")
    code, out = _depends(capsys, plan, TASK_1_1)
    assert code == 1, out
    assert out[0] == "depends-on entries: 2"
    assert any(ln.startswith("not-complete: ") and ln.endswith("(PENDING)") for ln in out), out
    _set_status(plan, 2, "COMPLETE")
    assert _depends(capsys, plan, TASK_1_1)[0] == 0


@pytest.mark.parametrize("status", ["COMPLETE", "✅ COMPLETE", "**COMPLETE**", "COMPLETE (verified)", "Complete"])
def test_depends_completion_cells_that_pass(plan, capsys, status):
    _set_status(plan, 1, status)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 0, out


@pytest.mark.parametrize("status", ["NOT COMPLETE", "PARTIALLY COMPLETE", "INCOMPLETE", "PARTIAL",
                                    "IN_PROGRESS", "-"])
def test_depends_completion_cells_that_stop(plan, capsys, status):
    _set_status(plan, 1, status)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out[1]) == (1, f"not-complete: 01 ({status})")


def test_depends_latest_attempt_row_wins(plan, capsys):
    _set_status(plan, 1, "PARTIAL")
    _rewrite(plan / RECOVERY_1, r"(?m)^\| 2 \|", "| 1 (attempt 2) | ParseRows | Sonnet | COMPLETE | - |\n| 2 |")
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 0, out


def test_depends_missing_step_row(plan, capsys):
    _set_depends(plan, TASK_1_2, "07")
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out[1]) == (1, "not-complete: 07 (no step row)")


def test_depends_missing_recovery(plan, capsys):
    (plan / RECOVERY_1).unlink()
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out[1]) == (1, "not-complete: 01 (no Recovery)")


@pytest.mark.parametrize("value", ["cross-session: QZX-S01-01-02", "QZX-S01-01-02",
                                   "cross-sprint: `QZX-S01-01-02`"])
def test_depends_remote_producer(plan, capsys, value):
    _set_depends(plan, TASK_2_1, value)
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out[1]) == (1, "not-complete: QZX-S01-01-02 (PENDING)")
    _set_status(plan, 2, "COMPLETE")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out[1]) == (0, "complete: QZX-S01-01-02")


def test_depends_meta_plan_id(plan, capsys):
    _set_status(plan, 2, "COMPLETE")
    meta = plan / "Sprint-01-Discovery" / "QZX-META-S01-01-Recovery.md"
    _w(meta, (plan / RECOVERY_1).read_text(encoding="utf-8"))
    _set_depends(plan, TASK_2_1, "cross-sprint: QZX-META-S01-01-02")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out[1]) == (0, "complete: QZX-META-S01-01-02")


def test_depends_remote_producer_with_no_recovery_is_unresolved(plan, capsys):
    _set_depends(plan, TASK_2_1, "cross-session: QZX-S01-09-02")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert code == 1
    assert out[1].startswith("unresolved: QZX-S01-09-02"), out


def test_depends_two_recoveries_of_one_name_are_ambiguous(plan, capsys):
    _set_status(plan, 2, "COMPLETE")
    _w(plan / "Archive" / "QZX-S01-01-Recovery.md", (plan / RECOVERY_1).read_text(encoding="utf-8"))
    _set_depends(plan, TASK_2_1, "cross-session: QZX-S01-01-02")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert code == 1
    assert out[1].startswith("ambiguous: QZX-S01-01-02"), out


@pytest.mark.parametrize("value", ["01 and 02", "1 & 2", "QZX-S01-01-01 and QZX-S01-01-02"])
def test_depends_joined_entries_are_two_producers(plan, capsys, value):
    _set_depends(plan, TASK_2_1 if "QZX" in value else TASK_1_1, value)
    task = TASK_2_1 if "QZX" in value else TASK_1_1
    _set_status(plan, 1, "COMPLETE")
    code, out = _depends(capsys, plan, task)
    assert (code, out[0]) == (1, "depends-on entries: 2"), out
    _set_status(plan, 2, "COMPLETE")
    assert _depends(capsys, plan, task)[0] == 0


def test_depends_an_id_whose_abbreviation_is_a_word_is_not_split(plan, capsys):
    _set_depends(plan, TASK_2_1, "cross-session: AND-S01-09-02")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out[1]) == (1, "unresolved: AND-S01-09-02 (no Recovery under the plan root)")


@pytest.mark.parametrize("value", ["the ledger audit", "cross-session: QZX-S01-01", "3-1", "{task numbers}"])
def test_depends_never_guesses(plan, capsys, value):
    _set_status(plan, 1, "COMPLETE")
    _set_depends(plan, TASK_1_2, value)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 1, out
    assert out[1].startswith("unresolved: "), out


@pytest.mark.parametrize("value", ["- (cross-sprint: QZX-S01-01-02 -- the index)",
                                   "- (see (also QZX-S01-01-02))",
                                   "- (reads QZX-S01-01-02-Index.md)"])
def test_depends_a_producer_inside_parentheses_is_checked(plan, capsys, value):
    _set_depends(plan, TASK_2_1, value)
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out) == (1, ["depends-on entries: 1", "not-complete: QZX-S01-01-02 (PENDING)"])
    _set_status(plan, 2, "COMPLETE")
    assert _depends(capsys, plan, TASK_2_1)[0] == 0


def test_depends_a_listed_task_does_not_hide_a_parenthesised_one(plan, capsys):
    _set_status(plan, 1, "COMPLETE")
    _set_depends(plan, TASK_1_2, "01 (+ cross-session: QZX-S01-09-02)")
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 1, out
    assert out[2].startswith("unresolved: QZX-S01-09-02"), out


def test_depends_a_session_id_inside_parentheses_is_unresolved(plan, capsys):
    _set_depends(plan, TASK_2_1, "- (cross-session: QZX-S01-01 first)")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out) == (1, ["depends-on entries: 1", "unresolved: cross-session: QZX-S01-01"])


def test_depends_a_note_after_the_label_is_not_a_target(plan, capsys):
    _set_depends(plan, TASK_2_1, "- (cross-sprint: consumes `parse()` from QZX-S01-01-02)")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out) == (1, ["depends-on entries: 1", "not-complete: QZX-S01-01-02 (PENDING)"])
    _set_depends(plan, TASK_2_1, "- (cross-sprint: session-entry gate only)")
    assert _depends(capsys, plan, TASK_2_1) == (0, ["depends-on entries: 0"])


def test_depends_a_sprint_folder_target_inside_parentheses_is_unresolved(plan, capsys):
    _set_depends(plan, TASK_2_1, "- (cross-sprint: Sprint-01 COMPLETE)")
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out) == (1, ["depends-on entries: 1", "unresolved: cross-sprint: Sprint-01"])


@pytest.mark.parametrize("header", ["**Agent:** Opus | **Depends On:** 01", "**Depends on:** 01",
                                    "**Depends On**: 01"])
def test_depends_header_shapes_are_read(plan, capsys, header):
    _rewrite(plan / TASK_1_2, r"\*\*Depends On:\*\*[^\r\n]*", header)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out) == (1, ["depends-on entries: 1", "not-complete: 01 (PENDING)"])


@pytest.mark.parametrize("header", ["**Depends On:**\n- 01\n- 02", "**Depends On:** 01,\n02"])
def test_depends_a_value_on_a_second_line_stops(plan, capsys, header):
    _set_status(plan, 1, "COMPLETE")
    _rewrite(plan / TASK_1_2, r"\*\*Depends On:\*\*[^\r\n]*", header)
    code, out = _depends(capsys, plan, TASK_1_2)
    assert code == 1, out
    assert "unresolved: the Depends On value runs onto the next line" in out


def test_depends_a_range_covers_lettered_steps(plan, capsys):
    _set_status(plan, 1, "COMPLETE")
    _set_status(plan, 2, "COMPLETE")
    _rewrite(plan / RECOVERY_1, r"(?m)^\| 2 \|", "| 1b | Extra | Opus | PENDING | - |\n| 2 |")
    _set_depends(plan, TASK_2_1, "1-2")
    _w(plan / SESSION_2 / "QZX-S01-02-Recovery.md", (plan / RECOVERY_1).read_text(encoding="utf-8"))
    code, out = _depends(capsys, plan, TASK_2_1)
    assert (code, out) == (1, ["depends-on entries: 3", "complete: 01", "not-complete: 01b (PENDING)",
                               "complete: 02"])


def test_depends_reads_only_the_header(plan, capsys):
    _set_depends(plan, TASK_1_2, "-")
    _rewrite(plan / TASK_1_2, r"(?m)^## Objective[^\r\n]*", "## Objective\n\n**Depends On:** 07")
    assert _depends(capsys, plan, TASK_1_2) == (0, ["depends-on entries: 0"])


def test_depends_crlf_files(plan, capsys):
    for rel in (TASK_1_2, RECOVERY_1):
        path = plan / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    code, out = _depends(capsys, plan, TASK_1_2)
    assert (code, out[1]) == (1, "not-complete: 01 (PENDING)")


def test_depends_unreadable_input_is_exit_two(plan, capsys):
    assert _depends(capsys, plan, f"{SESSION_1}/none.md")[0] == 2
    code, out = _depends(capsys, plan, RECOVERY_1)
    assert code == 2
    assert "no **Task ID:** line" in out[0]
    assert dp.main(["depends", "--candidate", str(plan / TASK_1_2), "--plan-root", str(plan / "absent")]) == 2
