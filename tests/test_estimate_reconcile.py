"""estimate_reconcile.py: every token-estimate level of a plan folder, read only."""
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import estimate_reconcile as er
import test_derived_surface as ds
import token_saver_scan as tss
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


# -- derived cells: the surface, Write-Set and Write-Sets figures of a rendered and priced plan -------
# Each fixture is the real renderer's output, priced by the real write-back.
NEW_LEVELS = ("surface-tokens", "surface-kib", "surface-rows", "surface-total", "surface-files",
              "writeset-tokens", "writeset-kib",
              "master-count", "master-sizes", "master-total", "master-files")
SURFACE, WRITE_SET, WRITE_SETS = "## Session Surface", "## Write-Set", "### Write-Sets"
EXTRA = "src/orchard/extra.py"  # a sprint row that no task cites


@pytest.fixture
def priced(tmp_path):
    """A clean new-shape plan of three sprints, each task file priced."""
    tree = ds.Tree(tmp_path, spec=ds._two_sprints())
    tree.write_back(*(p.relative_to(tree.plan).as_posix() for p in sorted(tree.plan.rglob("*.md"))
                      if er.sp.file_kind(p.name) == "task"))
    report = er.reconcile(tree.plan, tree.root)
    assert (report.mismatches, report.unread, report.exit_code) == ([], [], 0)
    return tree


def _section_line(tree, rel, heading, start):
    """(lines, index) of the one line under `heading` that starts with `start`."""
    lines = tree.text(rel).split("\n")
    at = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
    stop = next(i for i in range(at + 1, len(lines)) if lines[i].startswith("#"))
    hits = [i for i in range(at, stop) if lines[i].startswith(start)]
    assert len(hits) == 1, (rel, start, hits)
    return lines, hits[0]


def _set_row_cell(tree, rel, heading, first, column, change):
    """Pass one cell of the row whose first cell is `first` through `change`. Returns its line number."""
    lines, i = _section_line(tree, rel, heading, f"| {first} |")
    head = next(j for j in range(i, 0, -1) if not lines[j - 1].startswith("|"))
    names = tsw._table_header_at(lines, head)
    at = names.index(column)
    cells = tsw._cells(lines[i], len(names))
    lines[i] = tsw._rewrite_cell(lines[i], at, change(cells[at].strip()), len(names))
    tree.set(rel, "\n".join(lines))
    return i + 1


def _change_line(tree, rel, heading, start, change):
    lines, i = _section_line(tree, rel, heading, start)
    lines[i] = change(lines[i])
    tree.set(rel, "\n".join(lines))
    return i + 1


def _scaled(factor):
    def change(cell):
        value = tsw._parse_token_cell(cell) / 1000 if "K" in cell else Decimal(cell.replace(",", ""))
        assert value, "a zero figure cannot show a drift"
        new = (value * Decimal(str(factor))).quantize(Decimal("0.0001"))
        return f"~{new}K" if "K" in cell else str(new)
    return change


def _scaled_total(factor):
    return lambda line: re.sub(r"~[\d.]+K", lambda m: _scaled(factor)(m.group(0)), line, count=1)


def _other_count(line):
    return re.sub(r"over (\d+)", lambda m: f"over {int(m.group(1)) + 1}", line)


SIZED_CASES = {  # level: (file, heading, first cell, column)
    "surface-tokens": (ds.ORCH, SURFACE, f"`{ds.LEDGER}`", "~tokens"),
    "surface-kib": (ds.ORCH, SURFACE, f"`{ds.LEDGER}`", "kib"),
    "writeset-tokens": (ds.PLAN, WRITE_SET, f"`{ds.LEDGER}`", "~tokens"),
    "writeset-kib": (ds.PLAN, WRITE_SET, f"`{ds.LEDGER}`", "kib"),
}
LINE_CASES = {  # level: (file, heading, line start)
    "surface-total": (ds.ORCH, SURFACE, "**Session surface:**"),
    "master-total": (ds.MASTER, WRITE_SETS, "**Write-set total:**"),
}
COUNT_LINE_CASES = {
    "surface-files": (ds.ORCH, SURFACE, "**Session surface:**"),
    "master-files": (ds.MASTER, WRITE_SETS, "**Write-set total:**"),
}


def _levels(report):
    return [ln.split()[1] for ln in report.mismatches]


def _assert_drift(tree, level, rel, line, roll_ups=()):
    """One MISMATCH of `level` at the changed line, and no other line but the named roll-ups."""
    report = er.reconcile(tree.plan, tree.root)
    assert report.unread == []
    assert report.exit_code == 1
    assert [ln for ln in report.mismatches if ln.startswith(f"MISMATCH {level} {rel}:{line} declared ")], report
    assert _levels(report).count(level) == 1
    assert set(_levels(report)) <= {level, *roll_ups}, report


@pytest.mark.parametrize("level", SIZED_CASES)
def test_a_sized_row_that_drifts_from_its_citing_row_fails(priced, level):
    case = SIZED_CASES[level]
    line = _set_row_cell(priced, *case, _scaled(1.5))
    _assert_drift(priced, level, case[0], line, {"surface-tokens": ("surface-total",),
                                                 "writeset-tokens": ("master-sizes", "master-total"),
                                                 "writeset-kib": ("master-sizes",)}.get(level, ()))


@pytest.mark.parametrize("level", SIZED_CASES)
def test_a_sized_row_within_ten_percent_is_clean(priced, level):
    case = SIZED_CASES[level]
    _set_row_cell(priced, *case, _scaled(1.05))
    assert er.reconcile(priced.plan, priced.root).lines == [
        "estimates: sessions=4 mismatches=0 unread=0"]


@pytest.mark.parametrize("level", LINE_CASES)
def test_a_total_line_that_drifts_from_its_rows_fails(priced, level):
    case = LINE_CASES[level]
    line = _change_line(priced, *case, _scaled_total(1.5))
    _assert_drift(priced, level, case[0], line)


@pytest.mark.parametrize("level", LINE_CASES)
def test_a_total_line_within_ten_percent_is_clean(priced, level):
    _change_line(priced, *LINE_CASES[level], _scaled_total(1.05))
    assert er.reconcile(priced.plan, priced.root).exit_code == 0


@pytest.mark.parametrize("level", COUNT_LINE_CASES)
def test_a_total_line_count_has_no_tolerance(priced, level):
    case = COUNT_LINE_CASES[level]
    line = _change_line(priced, *case, _other_count)
    _assert_drift(priced, level, case[0], line)
    report = er.reconcile(priced.plan, priced.root)
    assert re.search(r"declared (\d+) expected (\d+) \([\d.]+%\)$", report.mismatches[0])


@pytest.mark.parametrize("level", COUNT_LINE_CASES)
def test_a_total_line_count_that_matches_is_clean(priced, level):
    # The figure of the same line moves inside its limit, and the count stays.
    _change_line(priced, *COUNT_LINE_CASES[level], _scaled_total(0.95))
    assert er.reconcile(priced.plan, priced.root).mismatches == []


def test_a_master_count_has_no_tolerance(priced):
    line = _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-01", "count", lambda c: str(int(c) + 1))
    _assert_drift(priced, "master-count", ds.MASTER, line)


def test_a_master_count_that_counts_each_path_once_is_clean(priced):
    # Sprint one writes one file under two spellings, so its rows outnumber its paths.
    rows = ds._write_set(priced.text(ds.PLAN))
    cells, _total = ds._master(priced.text(ds.MASTER))
    assert int(cells["Sprint-01"][0]) < len(rows)
    assert er.reconcile(priced.plan, priced.root).mismatches == []


@pytest.mark.parametrize("column", ["kib", "~tokens"])
def test_a_master_row_that_drifts_from_its_sprint_fails(priced, column):
    line = _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-01", column, _scaled(1.5))
    _assert_drift(priced, "master-sizes", ds.MASTER, line)


@pytest.mark.parametrize("column", ["kib", "~tokens"])
def test_a_master_row_within_ten_percent_is_clean(priced, column):
    _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-01", column, _scaled(1.05))
    assert er.reconcile(priced.plan, priced.root).exit_code == 0


def test_a_renamed_surface_row_is_one_extra_and_one_missing_path(priced):
    line = _set_row_cell(priced, ds.ORCH, SURFACE, "`docs/guide.md`", "path", lambda _c: "`docs/other-guide.md`")
    report = er.reconcile(priced.plan, priced.root)
    head = _section_line(priced, ds.ORCH, SURFACE, "| Path |")[1] + 1
    assert report.mismatches == [
        f"MISMATCH surface-rows {ds.ORCH}:{line} declared 1 expected 0 (100.0%)",
        f"MISMATCH surface-rows {ds.ORCH}:{head} declared 0 expected 1 (100.0%)"]


def test_a_repeated_surface_row_fails(priced):
    _change_line(priced, ds.ORCH, SURFACE, "| `docs/guide.md` |", lambda ln: f"{ln}\n{ln}")
    report = er.reconcile(priced.plan, priced.root)
    assert [ln for ln in report.mismatches if "surface-rows" in ln and "declared 2 expected 1" in ln]
    assert set(_levels(report)) == {"surface-rows", "surface-files"}  # the total moves under 10%


def test_surface_rows_stay_clean_when_a_named_output_lands(priced):
    # The key of an output changes its spelling once the file is on disk. The path is the same.
    output = f"{ds.READ_PATH}/Outputs/QZX-parse.md"
    assert output in ds._rows(priced.text(ds.ORCH))
    path = priced.plan / output
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"# Result\n")
    tasks = [(priced.plan / r, priced.text(r)) for r in (ds.TASK_1, ds.TASK_2)]
    keys = [e["path"] for e in tsw.surface_entries(tasks, [], priced.plan, priced.root)]
    assert output not in keys  # the control: the producer's key moved
    assert er.reconcile(priced.plan, priced.root).mismatches == []


@pytest.mark.parametrize("name", [Path(ds.ORCH).name, Path(ds.RECOVERY).name])
def test_the_orchestration_and_recovery_sizes_are_not_compared(priced, name):
    for column in ("kib", "~tokens"):
        _set_row_cell(priced, ds.ORCH, SURFACE, f"`{name}`", column, _scaled(3))
    assert set(_levels(er.reconcile(priced.plan, priced.root))) <= {"surface-total"}


def test_a_write_set_row_no_task_cites_is_not_compared(priced):
    _set_row_cell(priced, ds.PLAN_2, WRITE_SET, f"`{EXTRA}`", "~tokens", lambda _c: "~900.0K")
    assert set(_levels(er.reconcile(priced.plan, priced.root))) == {"master-sizes", "master-total"}


def test_no_role_cell_is_compared(priced):
    _set_row_cell(priced, ds.ORCH, SURFACE, f"`{ds.LEDGER}`", "role", lambda _c: "READ")
    _set_row_cell(priced, ds.PLAN, WRITE_SET, f"`{ds.LEDGER}`", "role", lambda _c: "READ")
    assert er.reconcile(priced.plan, priced.root).exit_code == 0


@pytest.mark.parametrize("level,case", [
    *((level, case) for level, case in SIZED_CASES.items()),
    ("master-count", (ds.MASTER, WRITE_SETS, "Sprint-01", "count")),
    ("master-sizes", (ds.MASTER, WRITE_SETS, "Sprint-01", "kib")),
    ("master-sizes", (ds.MASTER, WRITE_SETS, "Sprint-01", "~tokens"))])
def test_a_derived_cell_without_a_figure_is_unread(priced, level, case):
    line = _set_row_cell(priced, *case, lambda _c: "~?")
    report = er.reconcile(priced.plan, priced.root)
    own, *rest = report.unread
    assert own == f"UNREAD {level} {case[0]}:{line} no figure in '~?'"
    # A Write-Set row without a figure also leaves its sprint's Master Plan cells uncompared.
    assert [ln.split()[1] for ln in rest] == (["master-sizes"] if case[0] == ds.PLAN else [])
    assert report.mismatches == []


@pytest.mark.parametrize("case,levels", [
    (LINE_CASES["surface-total"], ("surface-total", "surface-files")),
    (LINE_CASES["master-total"], ("master-total", "master-files"))])
def test_a_derived_total_line_without_figures_is_unread(priced, case, levels):
    _change_line(priced, *case, lambda ln: f"{case[2]} pending")
    report = er.reconcile(priced.plan, priced.root)
    assert [ln.split()[1] for ln in report.unread] == list(levels)
    assert report.exit_code == 0


def test_the_master_total_waits_for_every_sprint(priced):
    _change_line(priced, *LINE_CASES["master-total"], _scaled_total(2))
    assert _levels(er.reconcile(priced.plan, priced.root)) == ["master-total"]
    priced.set(ds.PLAN_2, priced.text(ds.PLAN_2).replace("| Path | Task | Role | KiB |", "| Path | Task | Role | Size |"))
    report = er.reconcile(priced.plan, priced.root)
    assert report.mismatches == []
    assert [ln.split()[1] for ln in report.unread] == ["master-sizes"]
    assert "Sprint-02" in report.unread[0]


def test_a_crlf_plan_is_clean(tmp_path):
    tree = ds.Tree(tmp_path, "\r\n", spec=ds._two_sprints())
    tree.write_back(ds.TASK_1, ds.TASK_2, ds.OTHER_TASK, ds.TASK_S2)
    assert not [ln for ln in er.reconcile(tree.plan, tree.root).lines
                if any(f" {level} " in ln for level in NEW_LEVELS)]


def test_a_whole_plan_in_the_old_shape_prints_no_new_level(tmp_path, capsys, monkeypatch):
    plan = tmp_path / "plans/QZX"
    old = {f"{ds.READ_PATH}/QZX-S01-01-01-Sonnet-Probe.md": ds.OLD_TASK, ds.ORCH: ds.OLD_ORCH,
           ds.PLAN: ds.OLD_SPRINT, ds.RECOVERY: "# Recovery\n", ds.MASTER: ds.OLD_MASTER}
    for rel, text in {ds.LEDGER: "ledger = {}\n" * 900, **{f"plans/QZX/{r}": t for r, t in old.items()}}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    tsw.write_estimates([plan / ds.READ_PATH / "QZX-S01-01-01-Sonnet-Probe.md"], plan, tmp_path)
    (plan / ds.MASTER).write_bytes(ds.OLD_MASTER.encode("utf-8") + b"\xff\n")  # no level reads this file
    (tmp_path / ".git").mkdir()  # the config search stops here, below other tests' folders
    monkeypatch.chdir(tmp_path)
    code, lines = _check(plan, capsys)
    assert (code, lines) == (0, ["estimates: sessions=1 mismatches=0 unread=0"])
    assert not [level for level in NEW_LEVELS if any(level in ln for ln in lines)]


def test_reconcile_returns_what_the_command_prints(priced, capsys, monkeypatch):
    _set_row_cell(priced, *SIZED_CASES["surface-kib"], _scaled(2))
    _set_row_cell(priced, *SIZED_CASES["surface-tokens"], lambda _c: "~?")
    (priced.root / ".git").mkdir()  # the config search stops here, below other tests' folders
    before = priced.snapshot()
    report = er.reconcile(priced.plan, priced.root)
    assert capsys.readouterr().out == ""
    assert (report.sessions, len(report.mismatches), len(report.unread)) == (4, 1, 1)
    assert report.summary == "estimates: sessions=4 mismatches=1 unread=1"
    monkeypatch.chdir(priced.root)
    assert _check(priced.plan, capsys) == (report.exit_code, report.lines)
    assert priced.snapshot() == before
    with pytest.raises(er.PlanReadError, match="^not a folder: "):
        er.reconcile(priced.plan / "absent", priced.root)


@pytest.fixture
def searched(priced, tmp_path, monkeypatch):
    """(tree, config file, folder outside the project), with each folder a root of the upward search."""
    output = priced.plan / ds.READ_PATH / "Outputs/QZX-parse.md"
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(b"# Result\n")
    priced.write_back(*ds.ALL_TASKS)  # the table now holds the landed key
    config = priced.root / "planwise/config.yaml"
    config.parent.mkdir()
    config.write_text("project:\n  name: Orchard\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    for root in (priced.root, elsewhere):
        (root / ".git").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["estimate_reconcile.py"])
    return priced, config, elsewhere


def test_the_root_comes_from_config_or_from_the_working_directory(searched, tmp_path, capsys, monkeypatch):
    # Two tasks name this output under two spellings. Only the right root makes them one path.
    tree, config, elsewhere = searched
    seen, real = [], er.reconcile
    monkeypatch.setattr(er, "reconcile", lambda path, root: seen.append(root) or real(path, root))
    clean = ["estimates: sessions=4 mismatches=0 unread=0"]
    monkeypatch.chdir(elsewhere)
    code, lines = _check(tree.plan, capsys)
    assert code == 1, lines  # no config is found, and the wrong root gives the paths another key
    assert er.main(["check", str(tree.plan), "--config", str(config)]) == 0
    assert capsys.readouterr().out.splitlines() == clean
    assert er.main(["check", str(tree.plan), "--config", str(tmp_path / "absent.yaml")]) == 2
    assert capsys.readouterr().out.startswith("ERROR: cannot read config file ")
    # Without --config, the search finds the project's config from any folder below the project.
    for folder in (tree.root, tree.root / "src/orchard", tree.plan / ds.READ_PATH):
        monkeypatch.chdir(folder)
        assert er.main(["check", str(tree.plan)]) == 0, folder
        captured = capsys.readouterr()
        assert captured.out.splitlines() == clean
        assert f"found config at {config.resolve()}" in captured.err
    assert seen == [None] + [tree.root.resolve()] * 4


def test_the_config_wins_over_the_one_the_search_finds(searched, capsys, monkeypatch):
    tree, config, elsewhere = searched
    other = elsewhere / "planwise/config.yaml"
    other.parent.mkdir()
    other.write_text("project:\n  name: Other\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    assert er.main(["check", str(tree.plan)]) == 1
    capsys.readouterr()
    assert er.main(["check", str(tree.plan), "--config", str(config)]) == 0


def test_a_searched_config_that_cannot_be_parsed_stops_the_check_as_it_stops_the_write_back(
        searched, capsys, monkeypatch):
    tree, config, _elsewhere = searched
    config.write_text("project:\n  name: [unterminated\n", encoding="utf-8")
    monkeypatch.chdir(tree.root)
    with pytest.raises(Exception, match="unterminated|expected|parsing"):
        tss.main(["--scan", "--plan", str(tree.plan), "--write-estimates", "--task", str(tree.plan / ds.TASK_1)])
    capsys.readouterr()
    assert er.main(["check", str(tree.plan)]) == 2
    captured = capsys.readouterr()
    (line,) = captured.out.splitlines()
    assert line.startswith(f"ERROR: cannot read config file {config.resolve()}: ")
    assert "while parsing a flow sequence" in line
    assert str(config.resolve()) in captured.err


def test_a_config_the_search_cannot_decode_is_passed_over(searched, capsys, monkeypatch):
    tree, config, _elsewhere = searched
    config.write_bytes(b"project:\n  name: \xff\xfe\n")
    monkeypatch.chdir(tree.root)
    assert er.main(["check", str(tree.plan)]) == 0  # the working directory is the root


# -- which surface entry a printed row belongs to -------------------------------------------------------
def _priced(tmp_path, spec):
    tree = ds.Tree(tmp_path, spec=spec)
    tree.write_back(*ds.ALL_TASKS)
    tree.write_back("Sprint-03-Empty/Session-01-Report/QZX-S03-01-01-Opus-Report.md")
    assert er.reconcile(tree.plan, tree.root).lines == ["estimates: sessions=4 mismatches=0 unread=0"]
    return tree


@pytest.mark.parametrize("spelling,landed", [
    (f"{ds.READ_PATH}/Outputs/QZX-parse.md", f"{ds.READ_PATH}/Outputs/QZX-parse.md"),
    ("../Session-01-ReadPath/Outputs/QZX-parse.md", f"{ds.READ_PATH}/Outputs/QZX-parse.md"),
    ("QZX-parse.md", f"{ds.READ_PATH}/Outputs/QZX-parse.md"),
    (f"plans/QZX/{ds.READ_PATH}/Outputs/QZX-parse.md", f"{ds.READ_PATH}/Outputs/QZX-parse.md"),
    ("Outputs/QZX-own.md", f"{ds.SPRINT}/Session-02-WritePath/Outputs/QZX-own.md"),
], ids=["sprint-folder", "sibling-folder", "bare-name", "full-control", "own-session-control"])
def test_a_row_of_an_output_that_lands_is_still_its_entry(tmp_path, spelling, landed):
    spec = ds._two_sprints()
    spec["sprints"][0]["sessions"][1]["tasks"][0]["required_context"].append(ds._row(spelling, 0.9))
    tree = _priced(tmp_path, spec)
    rows = ds._rows(tree.text(ds.OTHER_ORCH))
    path = tree.plan / landed
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"# Result\n")
    assert er.reconcile(tree.plan, tree.root).mismatches == []
    # The row still answers for its figure, and a removed row is still missing.
    row = next(r for r in rows if r.endswith(Path(landed).name))
    _set_row_cell(tree, ds.OTHER_ORCH, SURFACE, f"`{row}`", "~tokens", _scaled(1.5))
    assert "surface-tokens" in _levels(er.reconcile(tree.plan, tree.root))
    _change_line(tree, ds.OTHER_ORCH, SURFACE, f"| `{row}` |", lambda _ln: "REMOVED")
    tree.set(ds.OTHER_ORCH, tree.text(ds.OTHER_ORCH).replace("REMOVED\n", ""))
    assert "surface-rows" in _levels(er.reconcile(tree.plan, tree.root))


@pytest.mark.parametrize("qualified", ["src/orchard/new.py (the new module)", "src/orchard/new.py:10-20"])
def test_a_row_is_compared_with_the_entry_of_its_own_key(tmp_path, qualified):
    spec = ds._two_sprints()
    for task, (spelling, tokens) in zip(spec["sprints"][0]["sessions"][0]["tasks"],
                                        ((qualified, 1.0), ("src/orchard/new.py", 5.0))):
        task["required_context"].append(ds._row(spelling, tokens))
    tree = _priced(tmp_path, spec)
    built = tree.text(ds.ORCH)
    rows = ds._rows(built)
    assert (rows[qualified][2], rows["src/orchard/new.py"][2]) == ("~1.0K", "~5.0K")
    for row in (qualified, "src/orchard/new.py"):  # each row answers for its own entry
        line = _set_row_cell(tree, ds.ORCH, SURFACE, f"`{row}`", "~tokens", _scaled(1.5))
        _assert_drift(tree, "surface-tokens", ds.ORCH, line, ("surface-total",))
        tree.set(ds.ORCH, built)
        _change_line(tree, ds.ORCH, SURFACE, f"| `{row}` |", lambda _ln: "REMOVED")
        tree.set(ds.ORCH, tree.text(ds.ORCH).replace("REMOVED\n", ""))
        report = er.reconcile(tree.plan, tree.root)
        assert [ln for ln in report.mismatches if "surface-rows" in ln and "declared 0 expected 1" in ln], row
        tree.set(ds.ORCH, built)
    (tree.root / "src/orchard/new.py").write_bytes(b"new = 1\n")  # the producer now has one entry for both
    assert er.reconcile(tree.plan, tree.root).mismatches == []


# -- a figure that is missing or unreadable -------------------------------------------------------------
@pytest.mark.parametrize("column,level", [("~tokens", "writeset-tokens"), ("kib", "writeset-kib")])
def test_an_uncited_write_set_row_without_a_figure_is_unread(priced, column, level):
    line = _set_row_cell(priced, ds.PLAN_2, WRITE_SET, f"`{EXTRA}`", column, lambda _c: "~?")
    report = er.reconcile(priced.plan, priced.root)
    assert report.mismatches == []
    assert report.unread[0] == f"UNREAD {level} {ds.PLAN_2}:{line} no figure in '~?'"
    assert [ln.split()[1] for ln in report.unread[1:]] == ["master-sizes"]


def _drop_master_rows(tree, *starts):
    text = tree.text(ds.MASTER)
    at = text.index(WRITE_SETS)
    stop = text.index("**Write-set total:**", at)
    kept = [ln for ln in text[at:stop].split("\n") if not ln.startswith(starts)]
    tree.set(ds.MASTER, text[:at] + "\n".join(kept) + text[stop:])


def _figureless_sprint(tree):
    _set_row_cell(tree, ds.PLAN_2, WRITE_SET, f"`{EXTRA}`", "~tokens", lambda _c: "~?")


def test_no_master_cell_is_compared_that_the_write_back_cannot_repair(priced):
    _figureless_sprint(priced)
    for column, value in (("count", "77"), ("kib", "900.0"), ("~tokens", "~900.0K")):
        _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-02", column, lambda _c, v=value: v)
    row = _section_line(priced, ds.MASTER, WRITE_SETS, "| Sprint-02")[1] + 1
    _change_line(priced, ds.MASTER, WRITE_SETS, "**Write-set total:**", _other_count)
    _change_line(priced, ds.MASTER, WRITE_SETS, "**Write-set total:**", _scaled_total(3))
    report = er.reconcile(priced.plan, priced.root)
    assert report.mismatches == []
    (unread,) = [ln for ln in report.unread if ds.MASTER in ln]
    assert unread.startswith(f"UNREAD master-sizes {ds.MASTER}:{row} ") and "Sprint-02" in unread
    # The rows of the other sprints are still compared.
    _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-01", "count", lambda _c: "77")
    assert _levels(er.reconcile(priced.plan, priced.root)) == ["master-count"]


@pytest.mark.parametrize("dropped", ["| Sprint-02", "|"], ids=["no-row", "total-line-only"])
def test_a_sprint_without_figures_is_unread_when_no_master_row_names_it(priced, dropped):
    _drop_master_rows(priced, dropped)
    _figureless_sprint(priced)
    line = _change_line(priced, ds.MASTER, WRITE_SETS, "**Write-set total:**", _scaled_total(3))
    report = er.reconcile(priced.plan, priced.root)
    assert report.mismatches == []
    assert [ln for ln in report.unread if ln.startswith(f"UNREAD master-sizes {ds.MASTER}:{line} ")
            and "Sprint-02" in ln], report


def test_a_master_row_of_a_sprint_that_has_no_folder_is_unread(priced):
    _change_line(priced, ds.MASTER, WRITE_SETS, "| Sprint-02",
                 lambda ln: ln + "\n" + ln.replace("Sprint-02", "Sprint-09"))
    report = er.reconcile(priced.plan, priced.root)
    assert report.mismatches == []
    assert [ln for ln in report.unread if " master-sizes " in ln and "Sprint-09" in ln], report


def test_a_master_row_that_names_no_sprint_is_unread(priced):
    _set_row_cell(priced, ds.MASTER, WRITE_SETS, "Sprint-02", "sprint", lambda _c: "Second")
    report = er.reconcile(priced.plan, priced.root)
    assert [ln for ln in report.unread if " master-sizes " in ln and "'Second'" in ln], report


def test_two_master_plans_are_unread(priced):
    priced.set("QZX-Second-Master-Plan.md", priced.text(ds.MASTER))
    report = er.reconcile(priced.plan, priced.root)
    assert len([ln for ln in report.unread if " master-sizes " in ln]) == 2, report


def test_a_master_total_with_no_sprint_folder_is_unread(priced):
    master = priced.text(ds.MASTER)
    alone = priced.plan / "Alone"
    alone.mkdir()
    (alone / Path(ds.MASTER).name).write_bytes(master.encode("utf-8"))
    path = alone / Path(ds.MASTER).name
    text = path.read_text(encoding="utf-8")
    path.write_text("\n".join(ln for ln in text.split("\n") if not ln.startswith("| Sprint-0")), encoding="utf-8")
    report = er.reconcile(alone, priced.root)
    assert [ln for ln in report.unread if " master-total " in ln], report


def test_a_surface_total_line_without_its_table_is_unread(priced):
    priced.set(ds.ORCH, priced.text(ds.ORCH).replace("| Path | Role | KiB | ~Tokens | Cited By |",
                                                     "| Path | Role | Size | ~Tokens | Cited By |"))
    report = er.reconcile(priced.plan, priced.root)
    assert [ln for ln in report.unread if " surface-total " in ln], report


def test_a_cited_path_with_no_figure_is_compared_with_the_zero_the_producer_writes(priced):
    text = priced.text(ds.TASK_2)
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and "`docs/guide.md`" in ln)
    priced.set(ds.TASK_2, text.replace(row, tsw._rewrite_cell(row, 3, "n/a", len(tsw._cells(row, 6)))))
    levels = _levels(er.reconcile(priced.plan, priced.root))
    assert "surface-tokens" in levels and "surface-kib" in levels


def test_a_cited_kib_cell_the_sum_cannot_read_is_unread(priced):
    line = _set_row_cell(priced, ds.PLAN, WRITE_SET, f"`{ds.LEDGER}`", "kib", lambda c: f"~{c}")
    report = er.reconcile(priced.plan, priced.root)
    own, at_master = report.unread
    assert own.startswith(f"UNREAD writeset-kib {ds.PLAN}:{line} no figure in '~")
    assert at_master.startswith(f"UNREAD master-sizes {ds.MASTER}:") and "KiB not compared" in at_master


def test_a_citing_row_without_a_kib_figure_is_unread(priced):
    text = priced.text(ds.TASK_2)
    row = next(ln for ln in text.split("\n") if ln.startswith("|") and "`docs/guide.md`" in ln)
    priced.set(ds.TASK_2, text.replace(row, tsw._rewrite_cell(row, 2, "n/a", len(tsw._cells(row, 6)))))
    report = er.reconcile(priced.plan, priced.root)
    assert [ln for ln in report.unread if " surface-kib " in ln and "its citing row" in ln], report


def test_a_write_set_outside_every_checked_session_is_unread_at_the_master(priced):
    _set_row_cell(priced, ds.PLAN_2, WRITE_SET, f"`{EXTRA}`", "~tokens", lambda _c: "~?")
    next((priced.plan / ds.TASK_S2).parent.glob("*-Orchestration.md")).unlink()
    report = er.reconcile(priced.plan, priced.root)
    assert [ln for ln in report.unread if ln.startswith(f"UNREAD master-sizes {ds.MASTER}:")], report


# -- the rows that a table may hold for one file --------------------------------------------------------
def _agree(tree):
    """Make the total line agree with the rows, so that no other level names a wrong row."""
    rows = [ln for ln in ds._block(tree.text(ds.ORCH)).split("\n") if ln.startswith("| `")]
    total = sum(tsw._parse_token_cell(tsw._cells(ln, 5)[3]) for ln in rows)
    _change_line(tree, ds.ORCH, SURFACE, "**Session surface:**",
                 lambda _ln: f"**Session surface:** {tsw._fmt_k(total)} tokens over {len(rows)} files")


def _add_rows(tree, *names):
    block = "".join(f"| `{n}` | READ | 900.0 | ~500.0K | 01 |\n" for n in names)
    _change_line(tree, ds.ORCH, SURFACE, "| `docs/guide.md` |", lambda ln: f"{ln}\n{block}".rstrip("\n"))
    _agree(tree)


def _drop_row(tree, name):
    _change_line(tree, ds.ORCH, SURFACE, f"| `{name}` |", lambda _ln: "REMOVED")
    tree.set(ds.ORCH, tree.text(ds.ORCH).replace("REMOVED\n", ""))


def _row_lines(tree):
    return [ln.split(" declared ")[1] for ln in er.reconcile(tree.plan, tree.root).mismatches
            if " surface-rows " in ln]


EXTRA_ROW, MISSING_ROW = "1 expected 0 (100.0%)", "0 expected 1 (100.0%)"


def test_two_rows_under_spellings_no_task_uses_are_extra(priced):
    _drop_row(priced, ds.LEDGER)
    _add_rows(priced, f"./{ds.LEDGER}", f"././{ds.LEDGER}")
    assert _row_lines(priced) == [EXTRA_ROW, EXTRA_ROW, MISSING_ROW]


def test_a_stale_row_beside_the_correct_row_is_extra(priced):
    _add_rows(priced, f"./{ds.LEDGER}")
    assert _row_lines(priced) == [EXTRA_ROW]


NEW = "src/orchard/new.py"
SPELLED = ((f"{NEW} (the new module)", 1.0), (f"{NEW}:10-20", 5.0), (NEW, 2.0))


def _three_keys(tmp_path):
    spec = ds._two_sprints()
    first, second = spec["sprints"][0]["sessions"][0]["tasks"]
    for task, (spelling, tokens) in zip((first, second, second), SPELLED):
        task["required_context"].append(ds._row(spelling, tokens))
    return _priced(tmp_path, spec)


def test_each_deleted_row_of_one_file_is_missing(tmp_path):
    tree = _three_keys(tmp_path)
    for spelling, _tokens in SPELLED[:2]:
        _drop_row(tree, spelling)
    _set_row_cell(tree, ds.ORCH, SURFACE, f"`{NEW}`", "path", lambda _c: f"`./{NEW}`")
    _agree(tree)
    assert _row_lines(tree) == [EXTRA_ROW] + [MISSING_ROW] * 3


def test_a_table_from_before_the_file_landed_answers_for_each_row(tmp_path):
    tree = _three_keys(tmp_path)
    (tree.root / NEW).write_bytes(b"new = 1\n")  # three keys become one
    assert er.reconcile(tree.plan, tree.root).mismatches == []
    built = tree.text(ds.ORCH)
    for spelling, _tokens in SPELLED:
        line = _set_row_cell(tree, ds.ORCH, SURFACE, f"`{spelling}`", "~tokens", _scaled(1.5))
        _assert_drift(tree, "surface-tokens", ds.ORCH, line, ("surface-total",))
        tree.set(ds.ORCH, built)
        _drop_row(tree, spelling)
        _agree(tree)
        assert _row_lines(tree) == [MISSING_ROW], spelling
        tree.set(ds.ORCH, built)


def test_a_table_of_one_state_holds_no_row_of_the_other(tmp_path):
    tree = _three_keys(tmp_path)
    for spelling, _tokens in SPELLED[:2]:
        _drop_row(tree, spelling)
    _set_row_cell(tree, ds.ORCH, SURFACE, f"`{NEW}`", "~tokens", lambda _c: "~5.0K")
    _set_row_cell(tree, ds.ORCH, SURFACE, f"`{NEW}`", "kib", lambda _c: "10.0")
    _agree(tree)
    (tree.root / NEW).write_bytes(b"new = 1\n")
    assert er.reconcile(tree.plan, tree.root).mismatches == []
    _add_rows(tree, f"{NEW}:1-2")
    assert _row_lines(tree) == [EXTRA_ROW]


@pytest.mark.parametrize("spelling", [
    f"{ds.READ_PATH}/Outputs/QZX-parse.md", "../Session-01-ReadPath/Outputs/QZX-parse.md",
    f"plans/QZX/{ds.READ_PATH}/Outputs/QZX-parse.md"], ids=["sprint-folder", "sibling-folder", "full"])
def test_a_row_of_a_landed_output_that_is_removed_is_still_its_entry(tmp_path, spelling):
    spec = ds._two_sprints()
    spec["sprints"][0]["sessions"][1]["tasks"][0]["required_context"].append(ds._row(spelling, 0.9))
    tree = ds.Tree(tmp_path, spec=spec)
    path = tree.plan / ds.READ_PATH / "Outputs/QZX-parse.md"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"# Result\n" * 200)
    tree.write_back(*ds.ALL_TASKS)
    path.unlink()
    row = f"plans/QZX/{ds.READ_PATH}/Outputs/QZX-parse.md"
    assert row in ds._rows(tree.text(ds.OTHER_ORCH))  # the control: the landed key
    levels = _levels(er.reconcile(tree.plan, tree.root))
    assert "surface-rows" not in levels and "surface-tokens" not in levels
    # The landed row still answers for its figure.
    _set_row_cell(tree, ds.OTHER_ORCH, SURFACE, f"`{row}`", "~tokens", lambda _c: "~900.0K")
    assert "surface-tokens" in _levels(er.reconcile(tree.plan, tree.root))


# -- a crash is one line and exit 2 ---------------------------------------------------------------------
def test_an_error_inside_the_check_is_one_error_line_and_exit_2(tmp_path, capsys, monkeypatch):
    exec_dir = _tree(tmp_path, task1=_task("DM-S01-01-01", f"~{'9' * 40}K", "~10K", reads="~4K"))
    code, lines = _check(exec_dir, capsys)
    assert code == 2
    assert lines == ["ERROR: InvalidOperation: [<class 'decimal.InvalidOperation'>]"]

    def locked(*_args):
        raise PermissionError("locked\nsecond line")

    monkeypatch.setattr(er, "reconcile", locked)
    assert _check(exec_dir, capsys) == (2, ["ERROR: PermissionError: locked"])


def test_an_underived_level_is_one_line(priced, monkeypatch):
    def odd(*_args):
        raise RuntimeError("odd\nsecond line")

    monkeypatch.setattr(er, "writeset_figures", odd)
    report = er.reconcile(priced.plan, priced.root)
    assert {ln.split(" not derived ")[1] for ln in report.unread} == {"(RuntimeError: odd)"}


def test_the_search_notes_print_when_the_search_succeeds(searched, capsys, monkeypatch):
    tree, config, _elsewhere = searched
    config.write_text("project:\n  plans_dir: Plans\n", encoding="utf-8")
    monkeypatch.chdir(tree.root)
    assert er.main(["check", str(tree.plan)]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["estimates: sessions=4 mismatches=0 unread=0"]
    assert "may not be the intended config" in captured.err
    assert "walks up from the folder of its own script" in " ".join(er.__doc__.split())
