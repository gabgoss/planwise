"""Pins the doctor estimate drift stage: its output lines and its exit-status contract.

Each tree is a one-session plan built in tmp_path. Its expected MISMATCH lines come
from `estimate_reconcile.reconcile` on the same tree, so the stage is compared with
the check it wraps.
"""

import contextlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import doctor_cli
import doctor_estimate_drift_stage as stage
import init_project as ip
from estimate_reconcile import reconcile

BANNER = "planwise doctor — estimate drift"
INDEX_HEAD = (
    "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|---|---|---|---|---|---|\n"
)
SESSION = "Sprint-01-One/Session-01-First"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _doctor_cfg(root: Path):
    return ip.InitConfig(project_name="Fixture", project_root=root, plugin_root=PLUGIN_ROOT)


def _project(root: Path, *plans: str, status: str = "IN_PROGRESS") -> Path:
    """A project whose plans index lists each abbreviation in `plans`."""
    _write(
        root / "planwise" / "config.yaml",
        f'plugin_version: "{_doctor_cfg(root).plugin_version}"\nproject:\n  name: fixture\n',
    )
    (root / "planwise" / "Backlog").mkdir()
    rows = "".join(f"| {a} | {a} plan | {status} | 2026-01-01 | 2026-01-01 | {a}/ |\n" for a in plans)
    if plans:
        _write(root / "planwise" / "Plans" / "00-Index-Plans.md", INDEX_HEAD + rows)
    return root


def _plan(root: Path, abbrev: str, *, header: str = "~20K", cell: str = "~20K", write_set: str = "") -> Path:
    """A one-session plan whose figures agree unless `header` or `cell` is changed."""
    plan = root / "planwise" / "Plans" / abbrev
    session = plan / SESSION
    name = f"{abbrev}-S01-01-01-Opus-Build.md"
    body = (
        "# Task: Opus-Build\n\n"
        f"**Task ID:** {abbrev}-S01-01-01\n**Agent:** Opus\n**Estimated Tokens:** {header}\n\n"
        "## Required Context <!-- REQUIRED -->\n\n"
        "| Priority | File | KiB | ~Tokens | Purpose |\n"
        "|----------|------|----:|--------:|---------|\n"
        "| 1 | `src/app.py` | 19.4 | ~7.4K | The module |\n"
        f"| 2 | `{name}` | 2.0 | ~2.6K | this task file |\n\n"
        "**Context subtotal:** ~10K (reads) + ~5K (output) + ~5K (working) = **~20K total**\n\n"
    )
    body += "x" * (2048 - len(body.encode("utf-8")))
    _write(session / name, body)
    _write(
        session / f"{abbrev}-S01-01-Orchestration.md",
        "# Orchestration\n\n## Session Task List\n\n"
        "| # | Task | Agent | ~Tokens |\n|---|------|-------|--------:|\n"
        f"| 1 | Build | Opus | {cell} |\n\n**Total Estimated:** ~20K\n",
    )
    _write(
        plan / "Sprint-01-One" / f"{abbrev}-S01-Sprint-Plan.md",
        "# Sprint Plan\n\n**Estimated Tokens:** ~20K\n\n## Sessions\n\n"
        "| # | Session ID | Name | ~Tokens |\n|---|------------|------|--------:|\n"
        f"| 1 | {abbrev}-S01-01 | First | ~20K |\n" + write_set,
    )
    return plan


def _stage_lines(root: Path, capsys) -> list[str]:
    stage.run_estimate_drift_stage(
        SimpleNamespace(project_root=root, planwise_root="planwise", plugin_root=PLUGIN_ROOT)
    )
    return capsys.readouterr().out.splitlines()


def _doctor(root: Path) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        status = doctor_cli._run_doctor(_doctor_cfg(root))
    return status, buf.getvalue()


def test_a_drifted_plan_prints_its_mismatch_under_the_plan_name(tmp_path, capsys):
    root = _project(tmp_path, "FIX")
    report = reconcile(_plan(root, "FIX", header="~30K"), root)
    assert any(ln.startswith("MISMATCH task ") for ln in report.mismatches)
    assert _stage_lines(root, capsys) == [
        "  FIX:",
        *(f"      {ln}" for ln in (*report.mismatches, report.summary)),
    ]


def test_a_clean_plan_prints_the_no_drift_line(tmp_path, capsys):
    root = _project(tmp_path, "FIX")
    _plan(root, "FIX")
    assert _stage_lines(root, capsys) == ["  FIX: no drift (1 session(s) checked)"]


def test_an_unread_figure_prints_only_the_summary_line(tmp_path, capsys):
    root = _project(tmp_path, "FIX")
    _plan(root, "FIX", cell="~?K")
    assert _stage_lines(root, capsys) == ["  FIX:", "      estimates: sessions=1 mismatches=0 unread=1"]


def test_run_doctor_returns_the_same_value_for_a_drifted_and_a_clean_tree(tmp_path):
    drifted, clean = _project(tmp_path / "bad", "FIX"), _project(tmp_path / "good", "FIX")
    _plan(drifted, "FIX", header="~30K")
    _plan(clean, "FIX")
    bad_status, bad_out = _doctor(drifted)
    good_status, good_out = _doctor(clean)
    assert bad_out.index("planwise doctor — backlog item shape") < bad_out.index(BANNER)
    assert "MISMATCH task " in bad_out.split(BANNER)[1]
    assert "FIX: no drift" in good_out.split(BANNER)[1]
    assert bad_status == good_status == 0


def test_a_raising_stage_prints_one_line_and_keeps_the_return_value(tmp_path, monkeypatch):
    root = _project(tmp_path, "FIX")
    _plan(root, "FIX")
    clean_status, _ = _doctor(root)

    def boom(_cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(stage, "run_estimate_drift_stage", boom)
    status, out = _doctor(root)
    assert status == clean_status
    assert "Estimate drift: the check failed: boom" in out


def test_no_plans_folder_prints_one_line(tmp_path, capsys):
    root = _project(tmp_path)
    assert _stage_lines(root, capsys) == ["No plans folder at Plans/; no estimate to check."]


def test_no_active_plan_prints_one_line(tmp_path, capsys):
    root = _project(tmp_path, "FIX", status="COMPLETE")
    _plan(root, "FIX", header="~30K")
    (line,) = _stage_lines(root, capsys)
    assert line.startswith("Active plan: none (")


@pytest.mark.parametrize("sized", [False, True], ids=["old-shape", "sized-control"])
def test_an_old_shape_plan_prints_nothing_for_a_missing_column(tmp_path, capsys, sized):
    root = _project(tmp_path, "FIX")
    head, rule, cells = (" KiB | ~Tokens |", "----:|----:|", " 19.4 | ~99K |") if sized else ("", "", "")
    write_set = f"\n## Write-Set\n\n| Path | Task |{head}\n|------|------|{rule}\n| `src/app.py` | 01 |{cells}\n"
    plan = _plan(root, "FIX", write_set=write_set)
    _write(
        plan / "FIX-Master-Plan.md",
        "# Plan\n\n### Write-Sets\n\n| Sprint | Count |\n|---|---|\n| Sprint-01-One | 1 |\n",
    )
    lines = _stage_lines(root, capsys)
    if sized:
        # The control: the same tree with the new columns is read, and its wrong cell prints.
        assert any(ln.startswith("      MISMATCH writeset-tokens ") for ln in lines)
    else:
        assert lines == ["  FIX: no drift (1 session(s) checked)"]


def test_an_unreadable_plan_prints_one_line_and_the_next_plan_still_reports(tmp_path, capsys):
    root = _project(tmp_path, "BAD", "FIX")
    bad = _plan(root, "BAD")
    (bad / SESSION / "BAD-S01-01-Orchestration.md").write_bytes(b"# Orchestration\n\xff\xfe\n")
    _plan(root, "FIX")
    first, second = _stage_lines(root, capsys)
    assert first.startswith("  BAD: not checked (cannot read plan file ")
    assert second == "  FIX: no drift (1 session(s) checked)"


def test_an_arithmetic_error_in_one_plan_hides_no_later_plan(tmp_path, capsys):
    root = _project(tmp_path, "BAD", "FIX")
    _plan(root, "BAD", header=f"~{'9' * 40}K")
    _plan(root, "FIX")
    first, second = _stage_lines(root, capsys)
    assert first.startswith("  BAD: not checked (InvalidOperation: ")
    assert second == "  FIX: no drift (1 session(s) checked)"


def test_a_file_error_in_one_plan_hides_no_later_plan(tmp_path, capsys, monkeypatch):
    root = _project(tmp_path, "BAD", "FIX")
    _plan(root, "BAD")
    _plan(root, "FIX")

    def locked(path, project_root):
        if Path(path).name == "BAD":
            raise PermissionError("locked folder\nsecond line")
        return reconcile(path, project_root)

    monkeypatch.setattr(stage, "reconcile", locked)
    assert _stage_lines(root, capsys) == [
        "  BAD: not checked (PermissionError: locked folder)", "  FIX: no drift (1 session(s) checked)"]


def test_the_stage_uses_the_root_that_the_config_names(tmp_path, capsys, monkeypatch):
    root = _project(tmp_path / "project", "FIX")
    _plan(root, "FIX")
    other = tmp_path / "other"
    config = root / "planwise" / "config.yaml"
    _write(config, config.read_text(encoding="utf-8") + f'project_root: "{other.as_posix()}"\n')
    seen = []
    monkeypatch.setattr(stage, "reconcile", lambda path, at: seen.append(at) or reconcile(path, at))
    _stage_lines(root, capsys)
    assert seen == [other.resolve()]


def test_the_stage_writes_no_file(tmp_path, capsys):
    root = _project(tmp_path, "FIX")
    _plan(root, "FIX", header="~30K")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    _stage_lines(root, capsys)
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
