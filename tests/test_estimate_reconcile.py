"""estimate_reconcile.py: every token-estimate level of a plan folder, read only."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import estimate_reconcile as er
import token_saver_writeback as tsw

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "estimate_reconcile.py"
SELF_NAME = "{SELF}"  # `_write` swaps in the task file's own name
SELF_KIB = "{SELFKIB}"  # `_write` swaps in the settled KiB figure
TASK_LIST_HEAD = (
    "| # | Task | Agent | Est. Tokens | Depends On |\n"
    "|---|------|-------|-------------|------------|\n"
)


def _task(task_id, header, subtotal_total, reads="~4K", row_file="`kit/tool.py`", rows=None,
          self_row=True, pad=0):
    """`rows` lists the ~Tokens cells, one row each. The default is one row equal to `reads`.

    `self_row` appends the row that names the task file itself, at zero tokens so the
    reads term stays put. `_write` fills its name and KiB. `pad` adds filler lines to
    the Execution Steps, so a test can work on a file large enough that the KiB cell's
    one-decimal rounding is far under 3%.
    """
    body = "".join(f"| {n} | {row_file} | 9.9 | {cell} | whole file |\n"
                   for n, cell in enumerate(rows or [reads], 1))
    if self_row:
        body += f"| {len(rows or [reads]) + 1} | `{SELF_NAME}` | {SELF_KIB} | ~0K | this task file |\n"
    return (
        "# Task: Probe\n\n"
        f"**Task ID:** {task_id}\n"
        "**Agent:** Sonnet\n"
        f"**Estimated Tokens:** {header}\n\n"
        "---\n\n"
        "## Required Context\n\n"
        "| Priority | File | KiB | ~Tokens | Purpose |\n"
        "|----------|------|----:|--------:|---------|\n"
        f"{body}\n"
        f"**Context subtotal:** {reads} (reads — the sum of the ~Tokens column)"
        f" + ~5K (output) + ~1K (working) = **{subtotal_total} total**\n\n"
        "---\n\n"
        "## Execution Steps\n\n1. Do the thing.\n" + "Filler line for size.\n" * pad
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


def _write(path, text):
    """Write a task file whose self row names the file and states its own size.

    The KiB figure is part of the bytes it measures, so the write repeats until the
    figure matches the size the file ends at.
    """
    text = text.replace(SELF_NAME, path.name)
    kib = "0.0"
    for _ in range(8):
        path.write_text(text.replace(SELF_KIB, kib), encoding="utf-8")
        measured = tsw._fmt_kib(path.stat().st_size)
        if measured == kib:
            return
        kib = measured
    raise AssertionError(f"the self row of {path.name} never settled")


def _tree(tmp_path, task1=None, task2=None, orch=None, sprint=None):
    """A reconciled Exec-DM tree; each argument replaces one file's text."""
    exec_dir = tmp_path / "Exec-DM"
    session = exec_dir / "Sprint-01-Alpha" / "Session-01-Beta"
    session.mkdir(parents=True)
    _write(session / "DM-S01-01-01-Sonnet-Probe.md",
           task1 or _task("DM-S01-01-01", "~10K", "~10K", reads="~4K"))
    _write(session / "DM-S01-01-02-Sonnet-Other.md",
           task2 or _task("DM-S01-01-02", "~20K", "~20K", reads="~14K"))
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


def _reads_tree(tmp_path, rows):
    """A tree whose task 1 reads ~100K, priced as 106K with output and working tokens.

    Every other level repeats the ~106K figure, so only the Required Context rows
    (`rows`, the ~Tokens cells) can disagree with the subtotal's reads term.
    """
    task1 = _task("DM-S01-01-01", "~106K", "~106K", reads="~100K", rows=rows)
    orch = _orchestration(cell1="~106K", total="~126K tokens (106 + 20)")
    sprint = _sprint_plan(row1="~126K", header="~141K", detail1="~106K",
                          detail_total="~126K tokens (106 + 20)")
    return _tree(tmp_path, task1=task1, orch=orch, sprint=sprint)


def test_rows_below_the_reads_term_fail_at_task_reads_only(tmp_path, capsys):
    # Rows sum to 90.0K, the reads term, header, total and every rollup say ~100K / ~106K.
    code, lines = _check(_reads_tree(tmp_path, ["~50K", "~40.0K"]), capsys)
    assert code == 1
    assert lines == [
        ("MISMATCH task-reads Sprint-01-Alpha/Session-01-Beta/DM-S01-01-01-Sonnet-Probe.md:17 "
         "declared ~100K expected ~90K (11.1%)"),
        "estimates: sessions=1 mismatches=1 unread=0",
    ]


def test_rows_matching_the_reads_term_are_clean(tmp_path, capsys):
    code, lines = _check(_reads_tree(tmp_path, ["~60K", "~40K"]), capsys)
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_rows_within_ten_percent_of_the_reads_term_pass(tmp_path, capsys):
    code, lines = _check(_reads_tree(tmp_path, ["~55K", "~40K"]), capsys)  # 95K against 100K
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_row_without_a_figure_is_unread_not_a_mismatch(tmp_path, capsys):
    code, lines = _check(_reads_tree(tmp_path, ["~50K", "~?K"]), capsys)
    assert code == 0
    assert ("UNREAD task-reads Sprint-01-Alpha/Session-01-Beta/DM-S01-01-01-Sonnet-Probe.md:14 "
            "a Required Context row has no figure in the ~Tokens cell") in lines
    assert lines[-1] == "estimates: sessions=1 mismatches=0 unread=1"


def test_task_without_a_required_context_table_is_unread(tmp_path, capsys):
    text = _task("DM-S01-01-01", "~10K", "~10K", reads="~4K")
    no_table = "".join(ln for ln in text.splitlines(keepends=True) if not ln.startswith("|"))
    code, lines = _check(_tree(tmp_path, task1=no_table), capsys)
    assert code == 0
    assert any(ln.startswith("UNREAD task-reads ") and ln.endswith("no Required Context table")
               for ln in lines)


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


# -- task-self: a task's own KiB row against the task file's bytes -----------------------------
TASK1 = "Sprint-01-Alpha/Session-01-Beta/DM-S01-01-01-Sonnet-Probe.md"


def _self_tree(tmp_path, grow_percent=0):
    """A tree whose task 1 is about 22 KiB with a settled self row, then grown by a share of its size."""
    exec_dir = _tree(tmp_path, task1=_task("DM-S01-01-01", "~10K", "~10K", reads="~4K", pad=1000))
    path = exec_dir / TASK1
    extra = path.stat().st_size * grow_percent // 100
    with path.open("ab") as handle:
        handle.write(b"x" * extra)  # trailing bytes outside every table, so only the file's size moves
    return exec_dir


def test_self_row_that_states_the_file_size_is_clean(tmp_path, capsys):
    code, lines = _check(_self_tree(tmp_path), capsys)
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_self_row_five_percent_under_the_file_fails(tmp_path, capsys):
    exec_dir = _self_tree(tmp_path, grow_percent=5)
    code, lines = _check(exec_dir, capsys)
    size = (exec_dir / TASK1).stat().st_size
    assert code == 1
    assert len(lines) == 2
    assert lines[0].startswith(f"MISMATCH task-self {TASK1}:")
    assert f"expected {tsw._fmt_kib(size)} KiB (" in lines[0]
    assert lines[-1] == "estimates: sessions=1 mismatches=1 unread=0"


def test_self_row_two_percent_under_the_file_passes(tmp_path, capsys):
    code, lines = _check(_self_tree(tmp_path, grow_percent=2), capsys)
    assert code == 0
    assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_self_row_over_the_file_fails_too(tmp_path, capsys):
    exec_dir = _self_tree(tmp_path)
    path = exec_dir / TASK1
    declared = tsw._fmt_kib(path.stat().st_size)
    inflated = f"{float(declared) * 1.05:.1f}"
    path.write_bytes(path.read_bytes().replace(f"| {declared} |".encode(), f"| {inflated} |".encode()))
    code, lines = _check(exec_dir, capsys)
    assert code == 1
    assert lines[0].startswith(f"MISMATCH task-self {TASK1}:")


def test_self_row_rounding_alone_never_fails_a_small_file(tmp_path, capsys):
    # A file under 2 KiB can sit up to 0.05 KiB, over 2.5%, from the one-decimal figure it prints.
    # `_write` settles each fixture on exactly that figure, and the check must stay silent.
    for task in (_task("DM-S01-01-01", "~10K", "~10K", reads="~4K", pad=n) for n in range(0, 40, 7)):
        sub = tmp_path / f"t{len(task)}"
        sub.mkdir()
        code, lines = _check(_tree(sub, task1=task), capsys)
        assert code == 0, lines
        assert lines == ["estimates: sessions=1 mismatches=0 unread=0"]


def test_task_without_a_self_row_is_unread_and_exits_zero(tmp_path, capsys):
    task = _task("DM-S01-01-01", "~10K", "~10K", reads="~4K", self_row=False)
    code, lines = _check(_tree(tmp_path, task1=task), capsys)
    assert code == 0
    assert f"UNREAD task-self {TASK1}:11 no Required Context row names this task file" in lines
    assert lines[-1] == "estimates: sessions=1 mismatches=0 unread=1"


def test_self_row_without_a_figure_is_unread(tmp_path, capsys):
    exec_dir = _self_tree(tmp_path)
    path = exec_dir / TASK1
    declared = tsw._fmt_kib(path.stat().st_size)
    path.write_bytes(path.read_bytes().replace(f"| {declared} |".encode(), b"| {K} |"))
    code, lines = _check(exec_dir, capsys)
    assert code == 0
    assert any(ln.startswith(f"UNREAD task-self {TASK1}:")
               and ln.endswith("no figure in the KiB cell of the row that names this task file")
               for ln in lines)


def test_only_a_whole_file_row_for_the_task_file_counts_as_the_self_row(tmp_path, capsys):
    # A row that cites the task file with a span, or names another file, is not the self row.
    exec_dir = _self_tree(tmp_path, grow_percent=5)
    path = exec_dir / TASK1
    text = path.read_text(encoding="utf-8").replace(f"`{path.name}`", f"`{path.name}` §Execution Steps")
    path.write_text(text, encoding="utf-8")
    code, lines = _check(exec_dir, capsys)
    assert code == 0
    assert not any("MISMATCH task-self" in ln for ln in lines)
    assert any(ln.startswith("UNREAD task-self ") for ln in lines)


def _settle_bytes(path, body, newline):
    """Write `body` with `newline` endings and a self-row KiB figure that matches the result."""
    kib = "0.0"
    for _ in range(8):
        path.write_bytes(body.replace(SELF_KIB, kib).replace("\n", newline).encode("utf-8"))
        measured = tsw._fmt_kib(path.stat().st_size)
        if measured == kib:
            return
        kib = measured
    raise AssertionError("the self row never settled")


def test_self_row_in_a_crlf_file_is_measured_in_bytes(tmp_path, capsys):
    body = _task("DM-S01-01-01", "~10K", "~10K", reads="~4K", pad=1000)
    body = body.replace(SELF_NAME, "DM-S01-01-01-Sonnet-Probe.md")
    exec_dir = _tree(tmp_path)
    path = exec_dir / TASK1
    # The same text at CRLF is one byte longer per line, about 4% here, so a figure that
    # counted the LF copy would drift past 3%. A figure settled on the CRLF bytes is clean.
    _settle_bytes(path, body, "\r\n")
    assert _check(exec_dir, capsys) == (0, ["estimates: sessions=1 mismatches=0 unread=0"])
    lf_kib = tsw._fmt_kib(len(body.replace(SELF_KIB, "0.0").encode("utf-8")))
    crlf_kib = tsw._fmt_kib(path.stat().st_size)
    assert float(crlf_kib) > float(lf_kib) * 1.03
    text = path.read_bytes().decode("utf-8").replace(f"| {crlf_kib} |", f"| {lf_kib} |")
    path.write_bytes(text.encode("utf-8"))
    code, lines = _check(exec_dir, capsys)
    assert code == 1
    assert lines[0].startswith(f"MISMATCH task-self {TASK1}:")
