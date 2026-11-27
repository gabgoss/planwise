#!/usr/bin/env python3
"""Tests for `scripts/check_session_fill.py`, the unfilled-session refusal.

Every fixture is a session the real renderer wrote (`scaffold_plan.render_all`
over the spec in `test_scaffold_plan.py`), so a template change that moves or
respells a marker reaches these arms. A filled session is that same render with
each marker replaced.

Run with:  python -m pytest tests/test_check_session_fill.py -q
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_session_fill as csf
import scaffold_plan as sp
from test_scaffold_plan import make_spec

SESSION = "Sprint-01-LedgerCore/Session-01-ReadPath"
MARKER_RE = re.compile(r"<!-- FILL: \{.+?\} -->")
OPEN_MARKER = sp.FILL % "state the step"


@pytest.fixture
def plan(tmp_path):
    files, _rec = sp.render_all(make_spec(), sp.DEFAULT_TEMPLATES)
    root = tmp_path / "plan"
    sp.write_tree(files, root)
    return root


@pytest.fixture
def filled(plan):
    """The rendered plan with every marker replaced by body text."""
    for path in plan.rglob("*.md"):
        path.write_bytes(MARKER_RE.sub("done", path.read_bytes().decode("utf-8")).encode("utf-8"))
    return plan


def run(capsys, *paths):
    code = csf.main([str(p) for p in paths])
    return code, capsys.readouterr().out


def task_file(root):
    return next(iter(sorted((root / SESSION).glob("*-ParseRows.md"))))


def add_under(path, heading, *lines):
    """Insert lines at the top of one H2 section."""
    body = path.read_bytes().decode("utf-8").split("\n")
    at = next(i for i, ln in enumerate(body) if sp.norm_heading(ln) == f"## {heading}")
    body[at + 1:at + 1] = ["", *lines]
    path.write_bytes("\n".join(body).encode("utf-8"))


def test_rendered_session_is_refused(plan, capsys):
    code, out = run(capsys, plan / SESSION)
    assert code == 1, out
    unfilled = [ln for ln in out.splitlines() if ln.startswith("UNFILLED: ")]
    expected = {p.name for p in (plan / SESSION).glob("*.md") if sp.file_kind(p.name) in ("task", "orchestration")}
    assert len(expected) == 3
    for name in expected:
        assert any(name in ln for ln in unfilled), name
    assert len(unfilled) == len(expected)
    assert "fill_check files=3 unfilled=3" in out
    refused = next(ln for ln in out.splitlines() if ln.startswith("REFUSED: "))
    assert "/planwise plan --scaffold" in refused
    assert "Sprint-01-LedgerCore" in refused


def test_unfilled_line_names_each_gated_section(plan, capsys):
    _code, out = run(capsys, task_file(plan))
    for section in ("Objective", "Execution Steps", "Success Criteria"):
        assert re.search(rf"{section}=[1-9]\d*", out), section


def test_filled_session_passes_and_ungated_markers_are_ignored(filled, capsys):
    add_under(task_file(filled), "Notes for Agent", OPEN_MARKER)
    recovery = next(iter((filled / SESSION).glob("*-Recovery.md")))
    recovery.write_bytes(recovery.read_bytes() + f"\n{OPEN_MARKER}\n".encode())
    code, out = run(capsys, filled / SESSION)
    assert code == 0, out
    assert "fill_check files=3 unfilled=0" in out
    assert "REFUSED" not in out


@pytest.mark.parametrize("line, code", [
    (f"1. The renderer writes `{OPEN_MARKER}` for a gap.", 0),
    (f"1. The renderer writes ``{OPEN_MARKER}`` for a gap.", 0),
    (f"1. {OPEN_MARKER}", 1),
    # A marker whose own name holds a backtick is still a bare marker.
    ("1. " + sp.FILL % "`the command`", 1),
    # An unmatched backtick opens no code span.
    (f"1. a lone ` then {OPEN_MARKER}", 1),
])
def test_code_spans_are_not_counted(filled, capsys, line, code):
    add_under(task_file(filled), "Execution Steps", line)
    got, out = run(capsys, filled / SESSION)
    assert got == code, out


def test_fence_and_blockquote_lines_are_not_counted(filled, capsys):
    add_under(task_file(filled), "Success Criteria",
              "```markdown", OPEN_MARKER, "## Objective", OPEN_MARKER, "```", f"> {OPEN_MARKER}")
    code, out = run(capsys, filled / SESSION)
    assert code == 0, out


@pytest.mark.parametrize("lines", [
    ("````", "x", "````"),
    ("```code``` is the shape",),
    ("```",),
    ("```text", "```bash", "```"),
], ids=["four-backtick", "inline-run", "unclosed", "unbalanced"])
def test_a_fence_never_hides_a_later_section(filled, capsys, lines):
    path = task_file(filled)
    add_under(path, "Execution Steps", *lines)
    add_under(path, "Success Criteria", OPEN_MARKER)
    code, out = run(capsys, filled / SESSION)
    assert code == 1, out
    assert "Success Criteria=1" in out


def test_a_closed_four_backtick_fence_leaves_no_depth_behind():
    text = f"## Objective\n````\nx\n````\n{OPEN_MARKER}"
    assert csf.count_markers(text, ("Objective",)) == {"Objective": 1}


@pytest.mark.parametrize("lines", [
    ("1. Paste:","   ```markdown", f"   {OPEN_MARKER}", "   ```"),
    ("~~~", OPEN_MARKER, "~~~"),
    ("```markdown", "```bash", "x", "```", OPEN_MARKER, "```"),
    ("````markdown", "```", OPEN_MARKER, "```", "````"),
    ("The renderer writes `a", f"gap as {OPEN_MARKER} c` here."),
], ids=["indented", "tilde", "nested", "longer-outer", "wrapped-span"])
def test_quoted_marker_is_not_counted(filled, capsys, lines):
    add_under(task_file(filled), "Execution Steps", *lines)
    code, out = run(capsys, filled / SESSION)
    assert code == 0, out


@pytest.mark.parametrize("lines", [
    ("1. a stray ` here", f"2. {OPEN_MARKER} and ` there"),
    (f"1. \\` {OPEN_MARKER} \\`",),
], ids=["span-across-items", "escaped-backticks"])
def test_stray_backticks_do_not_hide_a_marker(filled, capsys, lines):
    add_under(task_file(filled), "Execution Steps", *lines)
    code, out = run(capsys, filled / SESSION)
    assert code == 1, out


def test_refusal_names_the_repair_for_a_plan_built_from_bodies(plan, capsys):
    _code, out = run(capsys, plan / SESSION)
    refused = next(ln for ln in out.splitlines() if ln.startswith("REFUSED: "))
    assert "bodies" in refused


def test_crlf_file_is_still_refused(plan, capsys):
    path = task_file(plan)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    code, out = run(capsys, path)
    assert code == 1, out
    assert "fill_check files=1 unfilled=1" in out


def test_folder_with_no_session_file_is_not_checked(plan, tmp_path, capsys):
    only_master = tmp_path / "only-master"
    only_master.mkdir()
    master = next(iter(plan.glob("*-Master-Plan.md")))
    (only_master / master.name).write_bytes(master.read_bytes())
    code, out = run(capsys, only_master)
    assert code == 2, out
    assert out.startswith("NOT CHECKED: ")


def test_missing_path_is_an_error(tmp_path, capsys):
    code, out = run(capsys, tmp_path / "absent")
    assert code == 2, out
    assert out.startswith("ERROR: no such path: ")


def test_unreadable_file_is_an_error_not_a_refusal(filled, capsys):
    task_file(filled).write_bytes(b"## Objective\n\xff\xfe\n")
    code, out = run(capsys, filled / SESSION)
    assert code == 2, out
    assert out.startswith("ERROR: cannot read ")


def test_relative_path_still_names_the_sprint(plan, monkeypatch, capsys):
    monkeypatch.chdir(plan / SESSION)
    code, out = run(capsys, ".")
    assert code == 1, out
    assert "Sprint-01-LedgerCore" in out
