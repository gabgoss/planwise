"""Tests for scripts/dispatch_preflight.py: the four preflight set checks."""

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
