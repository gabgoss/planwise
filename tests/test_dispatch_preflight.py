"""Tests for scripts/dispatch_preflight.py: the five preflight set checks."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import dispatch_preflight as dp


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
    plan = _w(root / "Sprint-07-X" / "plan.md", f"# Plan\n\n{prereq_line}\n")
    return plan, root


def test_prereq_known_bad_fires(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03 ALL COMPLETE")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 1
    out = capsys.readouterr().out
    assert "derived, not enumerated: [5, 8]" in out


def test_prereq_repaired_is_equal(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprints 01-03, 05 and 08 ALL COMPLETE")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0
    assert "quantified lines with an enumeration: 1" in capsys.readouterr().out


def test_prereq_prior_restricts_to_lower_numbers(tmp_path):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** all prior sprints: Sprints 01-03 and 05")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0


def test_prereq_unquantified_line_is_not_checked(tmp_path, capsys):
    plan, root = _plan_tree(tmp_path, "**Prerequisite:** Sprint 03")
    assert dp.main(["prereq", "--sprint-plan", str(plan), "--sprint-folder", str(root)]) == 0
    assert "quantified lines with an enumeration: 0" in capsys.readouterr().out


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
