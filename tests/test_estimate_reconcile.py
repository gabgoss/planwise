"""estimate_reconcile.py: every token-estimate level of a plan folder, read only."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import estimate_reconcile as er
import token_saver_writeback as tsw

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "estimate_reconcile.py"
TASK_LIST_HEAD = (
    "| # | Task | Agent | Est. Tokens | Depends On |\n"
    "|---|------|-------|-------------|------------|\n"
)


def _task(task_id, header, subtotal_total, reads="~4K", row_file="`kit/tool.py`"):
    return (
        "# Task: Probe\n\n"
        f"**Task ID:** {task_id}\n"
        "**Agent:** Sonnet\n"
        f"**Estimated Tokens:** {header}\n\n"
        "---\n\n"
        "## Required Context\n\n"
        "| Priority | File | KiB | ~Tokens | Purpose |\n"
        "|----------|------|----:|--------:|---------|\n"
        f"| 1 | {row_file} | 9.9 | {reads} | whole file |\n\n"
        f"**Context subtotal:** {reads} (reads — the sum of the ~Tokens column)"
        f" + ~5K (output) + ~1K (working) = **{subtotal_total} total**\n\n"
        "---\n\n"
        "## Execution Steps\n\n1. Do the thing.\n"
    )


def _orchestration(cell1="~10K", cell2="~20K", total="~30K tokens (10 + 20)"):
    return (
        "# Orchestration\n\n"
        "## Session Task List\n\n"
        + TASK_LIST_HEAD
        + f"| 1 | Probe: price the kit | Sonnet | {cell1} | - |\n"
        f"| 2 | Other: use the prices | Sonnet | {cell2} | 1 |\n\n"
        f"**Total Estimated:** {total}\n\n"
        "## Task Files\n\n"
        "| # | Task File | Agent |\n"
        "|---|-----------|-------|\n"
        "| 1 | [DM-S01-01-01-Sonnet-Probe.md](DM-S01-01-01-Sonnet-Probe.md) | Sonnet |\n"
    )


def _sprint_plan(row1="~30K", header="~45K", detail1="~10K", detail2="~20K",
                 detail_total="~30K tokens (10 + 20)"):
    return (
        "# Sprint Plan\n\n"
        f"**Estimated Tokens:** {header} total across all sessions\n\n"
        "## Sessions\n\n"
        "| Session | ID | Name | Objective | Est. Tokens |\n"
        "|---------|----|------|-----------|-------------|\n"
        f"| 1 | DM-S01-01 | Beta | Price the kit | {row1} |\n"
        "| 2 | DM-S01-02 | Gamma | Use the prices | ~15K |\n\n"
        "## Session Details\n\n"
        "### Session 01: Beta (DM-S01-01)\n\n"
        + TASK_LIST_HEAD
        + f"| 1 | Probe: price the kit | Sonnet | {detail1} | - |\n"
        f"| 2 | Other: use the prices | Sonnet | {detail2} | 1 |\n\n"
        f"**Total Estimated:** {detail_total}\n\n"
        "### Session 02: Gamma (DM-S01-02)\n\n"
        + TASK_LIST_HEAD
        + "| 1 | Use: apply the prices | Sonnet | ~15K | cross-session: DM-S01-01-01 |\n\n"
        "**Total Estimated:** ~15K tokens\n"
    )


def _tree(tmp_path, task1=None, task2=None, orch=None, sprint=None):
    """A reconciled Exec-DM tree; each argument replaces one file's text."""
    exec_dir = tmp_path / "Exec-DM"
    session = exec_dir / "Sprint-01-Alpha" / "Session-01-Beta"
    session.mkdir(parents=True)
    (session / "DM-S01-01-01-Sonnet-Probe.md").write_text(
        task1 or _task("DM-S01-01-01", "~10K", "~10K", reads="~4K"), encoding="utf-8")
    (session / "DM-S01-01-02-Sonnet-Other.md").write_text(
        task2 or _task("DM-S01-01-02", "~20K", "~20K", reads="~14K"), encoding="utf-8")
    (session / "DM-S01-01-Orchestration.md").write_text(orch or _orchestration(), encoding="utf-8")
    (exec_dir / "Sprint-01-Alpha" / "DM-S01-Sprint-Plan.md").write_text(
        sprint or _sprint_plan(), encoding="utf-8")
    return exec_dir


def _check(exec_dir, capsys):
    code = er.main(["check", str(exec_dir)])
    out = capsys.readouterr().out
    return code, out.splitlines()


def test_known_good_tree_is_clean(tmp_path, capsys):
    code, lines = _check(_tree(tmp_path), capsys)
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_identical_headers_fail(tmp_path, capsys):
    # Both tasks copy one header, so task 2's header no longer equals its subtotal.
    task2 = _task("DM-S01-01-02", "~10K", "~20K", reads="~14K")
    code, lines = _check(_tree(tmp_path, task2=task2), capsys)
    assert code == 1
    assert ("MISMATCH task Sprint-01-Alpha/Session-01-Beta/DM-S01-01-02-Sonnet-Other.md:5 "
            "declared ~10K expected ~20K (50.0%)") in lines
    assert any(ln.startswith("MISMATCH orchestration-cell ") for ln in lines)
    assert any(ln.startswith("MISMATCH sprint-details-cell ") for ln in lines)
    assert lines[-1].startswith("estimates: sessions=1 mismatches=")


def test_stale_orchestration_total_fails(tmp_path, capsys):
    orch = _orchestration(total="~45K tokens (10 + 20)")
    code, lines = _check(_tree(tmp_path, orch=orch), capsys)
    assert code == 1
    assert ("MISMATCH orchestration-total Sprint-01-Alpha/Session-01-Beta/"
            "DM-S01-01-Orchestration.md:10 declared ~45K expected ~30K (50.0%)") in lines
    # The Sprint Plan row is compared with the declared total, so it reports too.
    assert any(ln.startswith("MISMATCH sprint-row ") for ln in lines)


def test_unsynced_sprint_plan_row_fails(tmp_path, capsys):
    code, lines = _check(_tree(tmp_path, sprint=_sprint_plan(row1="~20K", header="~35K")), capsys)
    assert code == 1
    assert ("MISMATCH sprint-row Sprint-01-Alpha/DM-S01-Sprint-Plan.md:9 "
            "declared ~20K expected ~30K (33.3%)") in lines
    assert not any(ln.startswith("MISMATCH sprint-header ") for ln in lines)


def test_sprint_header_against_its_rows(tmp_path, capsys):
    code, lines = _check(_tree(tmp_path, sprint=_sprint_plan(header="~60K")), capsys)
    assert code == 1
    assert ("MISMATCH sprint-header Sprint-01-Alpha/DM-S01-Sprint-Plan.md:3 "
            "declared ~60K expected ~45K (33.3%)") in lines


def test_stale_session_details_total_fails(tmp_path, capsys):
    sprint = _sprint_plan(detail_total="~40K tokens (10 + 30)")
    code, lines = _check(_tree(tmp_path, sprint=sprint), capsys)
    assert code == 1
    assert any(ln.startswith("MISMATCH sprint-details-total Sprint-01-Alpha/DM-S01-Sprint-Plan.md:")
               for ln in lines)


def test_drift_under_ten_percent_passes(tmp_path, capsys):
    task1 = _task("DM-S01-01-01", "~10.5K", "~10K", reads="~4K")
    code, lines = _check(_tree(tmp_path, task1=task1), capsys)
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_placeholder_header_is_unread_not_a_mismatch(tmp_path, capsys):
    task1 = _task("DM-S01-01-01", "~?K", "~10K", reads="~4K")
    code, lines = _check(_tree(tmp_path, task1=task1), capsys)
    assert code == 0
    assert ("UNREAD task Sprint-01-Alpha/Session-01-Beta/DM-S01-01-01-Sonnet-Probe.md:5 "
            "no figure on the **Estimated Tokens:** line") in lines
    assert lines[-1] == "estimates: sessions=1 mismatches=0 unread=1"


def test_tree_rerolled_by_write_estimates_passes(tmp_path, capsys):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "tool.py").write_bytes(b"def f():\n    return 1\n" * 300)
    # Stale on every level: the reads cells and headers do not match the priced file.
    task1 = _task("DM-S01-01-01", "~10K", "~10K", reads="~4K")
    task2 = _task("DM-S01-01-02", "~10K", "~10K", reads="~4K")
    exec_dir = _tree(tmp_path, task1=task1, task2=task2,
                     orch=_orchestration(cell2="~10K", total="~20K tokens (10 + 10)"),
                     sprint=_sprint_plan(row1="~70K", detail2="~10K",
                                         detail_total="~20K tokens (10 + 10)"))
    code, lines = _check(exec_dir, capsys)
    assert code == 1  # the stale tree fails before the re-roll
    session = exec_dir / "Sprint-01-Alpha" / "Session-01-Beta"
    tasks = sorted(session.glob("DM-S01-01-0*-Sonnet-*.md"))
    report = tsw.write_estimates(tasks, exec_dir, tmp_path)
    assert report["errors"] == [] and report["written"], report
    code, lines = _check(exec_dir, capsys)
    assert code == 0, lines
    assert lines[-1] == "estimates: sessions=1 mismatches=0 unread=0"


def test_missing_folder_exits_2(tmp_path, capsys):
    code = er.main(["check", str(tmp_path / "absent")])
    assert code == 2
    assert capsys.readouterr().out.startswith("ERROR: not a folder: ")


def test_non_utf8_plan_file_exits_2(tmp_path, capsys):
    exec_dir = _tree(tmp_path)
    task = exec_dir / "Sprint-01-Alpha" / "Session-01-Beta" / "DM-S01-01-01-Sonnet-Probe.md"
    task.write_bytes(b"**Estimated Tokens:** \xff\xfe\n")
    code = er.main(["check", str(exec_dir)])
    assert code == 2
    assert capsys.readouterr().out.startswith("ERROR: cannot read plan file ")


def test_cli_rejects_unknown_flag_and_prints_the_total_line(tmp_path):
    exec_dir = _tree(tmp_path)
    bad = subprocess.run([sys.executable, "-B", str(SCRIPT), "check", str(exec_dir), "--bogus"],
                         capture_output=True, text=True, encoding="utf-8", check=False)
    assert bad.returncode == 2
    assert "unrecognized arguments: --bogus" in bad.stderr
    ok = subprocess.run([sys.executable, "-B", str(SCRIPT), "check", str(exec_dir)],
                        capture_output=True, text=True, encoding="utf-8", check=False)
    assert ok.returncode == 0
    assert ok.stdout.splitlines()[-1] == "estimates: sessions=1 mismatches=0 unread=0"
