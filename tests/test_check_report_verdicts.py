"""Tests for scripts/check_report_verdicts.py.

Fixtures follow the ``| Check | Actual | Expected | Verdict |`` table of
references/gate-verdict-contract-and-adjudication.md §5. Every exit code of
both modes is shown here: 0, 1, 2 and 3 for the verdict mode, and 0, 1 and 2
for ``--input-set``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_report_verdicts as crv

SCRIPT = SCRIPTS / "check_report_verdicts.py"

HEADER = "| Check | Actual | Expected | Verdict |\n|-------|--------|----------|---------|\n"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


# --- verdicts mode: exit codes -------------------------------------------------


def test_clean_report_exits_0(tmp_path: Path) -> None:
    report = write(
        tmp_path,
        "clean.md",
        "# Report\n\n" + HEADER
        + "| rows added | 54 | ≥54 | PASS |\n"
        + "| untracked | 0 (none) | 0 | PASS |\n"
        + "| added lines | 1564 added lines | greater than 0 | PASS |\n",
    )
    result = run(str(report))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 numeric rows checked, 0 contradicted" in result.stdout


def test_contradicted_pass_exits_1_and_names_the_row(tmp_path: Path) -> None:
    # The WRONG example of §5: Actual 44 against Expected >=54, marked PASS.
    report = write(tmp_path, "fudged.md", HEADER + "| sites tagged | 44 | ≥54 | PASS (44 is ≥54) |\n")
    result = run(str(report))
    assert result.returncode == 1, result.stdout
    assert f"{report}:3: contradicted PASS" in result.stdout
    assert "'44'" in result.stdout


def test_no_numeric_row_exits_3(tmp_path: Path) -> None:
    report = write(
        tmp_path,
        "words.md",
        HEADER + "| tree clean | empty output | empty | PASS |\n| lint | 0 findings, 2 warnings | clean | PASS |\n",
    )
    result = run(str(report))
    assert result.returncode == 3, result.stdout
    assert "no numeric row checked" in result.stdout


def test_uncertain_row_is_not_a_pass_row(tmp_path: Path) -> None:
    # The CORRECT example of §5 carries no PASS, so nothing is checked.
    report = write(tmp_path, "uncertain.md", HEADER + "| sites tagged | 44 | ≥54 | [UNCERTAIN] escalating |\n")
    result = run(str(report))
    assert result.returncode == 3
    assert "0 PASS rows" in result.stdout


def test_result_column_is_not_an_alias(tmp_path: Path) -> None:
    # A signoff anchor table: no Actual or Expected column, Result not Verdict.
    report = write(
        tmp_path,
        "signoff.md",
        "| Exit Criterion | Mechanical Anchor | Pre-Change | Branches | Result |\n"
        "|---|---|---|---|---|\n"
        "| tests pass | 12 | 10 | 1 | PASS |\n",
    )
    result = run(str(report))
    assert result.returncode == 3
    assert "0 qualifying tables" in result.stdout


def test_fenced_table_is_skipped(tmp_path: Path) -> None:
    report = write(tmp_path, "fenced.md", "> ```markdown\n> " + HEADER.replace("\n|", "\n> |") + "> | x | 44 | ≥54 | PASS |\n> ```\n")
    result = run(str(report))
    assert result.returncode == 3, result.stdout


def test_column_order_and_escaped_pipe(tmp_path: Path) -> None:
    report = write(
        tmp_path,
        "order.md",
        "| Observation | Expected | Actual | Verdict |\n|---|---|---|---|\n"
        "| `git diff \\| grep -c '^+'` | = 0 | 2 | PASS |\n",
    )
    result = run(str(report))
    assert result.returncode == 1, result.stdout
    assert "Actual '2'" in result.stdout


def test_directory_input_aggregates_files(tmp_path: Path) -> None:
    write(tmp_path, "a.md", HEADER + "| n | 3 | at least 2 | PASS |\n")
    write(tmp_path, "b.md", "no table here\n")
    result = run(str(tmp_path))
    assert result.returncode == 0, result.stdout
    assert "total: 2 files, 1 qualifying tables, 1 PASS rows, 1 numeric rows checked" in result.stdout


# --- usage ------------------------------------------------------------------------


def test_no_arguments_exits_2() -> None:
    assert run().returncode == 2


def test_missing_path_exits_2(tmp_path: Path) -> None:
    result = run(str(tmp_path / "absent.md"))
    assert result.returncode == 2
    assert "path not found" in result.stderr


def test_missing_path_exits_2_in_input_set_mode(tmp_path: Path) -> None:
    assert run("--input-set", str(tmp_path / "absent.md")).returncode == 2


# --- --input-set mode ---------------------------------------------------------------


def test_input_set_clean_exits_0(tmp_path: Path) -> None:
    report = write(
        tmp_path,
        "set.md",
        "| `git diff --name-only $BASE -- scripts` | 3 files | 3 | PASS |\n"
        "| counts | spanned: 3, untracked: 0 | | |\n"
        "Sweep of the shipped tree: PASS, 0 hits (12 files spanned, 0 untracked)\n",
    )
    result = run("--input-set", str(report))
    assert result.returncode == 0, result.stdout
    assert "2 input-set criteria, 0 lacking a count" in result.stdout


def test_input_set_missing_counts_exits_1(tmp_path: Path) -> None:
    report = write(
        tmp_path,
        "set.md",
        "| `git diff --name-only $BASE -- scripts \\| wc -l` | 3 | 3 | PASS |\n\n"
        "The find ./plugins sweep printed nothing: PASS (spanned 40 files)\n",
    )
    result = run("--input-set", str(report))
    assert result.returncode == 1, result.stdout
    assert f"{report}:1: criterion lacks spanned-file count and untracked count" in result.stdout
    assert f"{report}:3: criterion lacks untracked count" in result.stdout


def test_input_set_ignores_lines_without_a_verdict(tmp_path: Path) -> None:
    report = write(tmp_path, "prose.md", "The sweep belongs to a later task.\nRun `git diff` first.\n")
    result = run("--input-set", str(report))
    assert result.returncode == 0
    assert "0 input-set criteria" in result.stdout


# --- the number parser --------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("44", ("=", 44.0)),
        (">= 3", (">=", 3.0)),
        ("≤ 3", ("<=", 3.0)),
        ("= 0", ("=", 0.0)),
        ("exactly 2", ("=", 2.0)),
        ("greater than 0", (">", 0.0)),
        ("at most 5 files", ("<=", 5.0)),
        ("1,564", ("=", 1564.0)),
        ("1564 added lines", ("=", 1564.0)),
        ("0 (3.1 printed nothing)", ("=", 0.0)),
        ("`12`", ("=", 12.0)),
        ("50%", ("=", 50.0)),
    ],
)
def test_parse_value_accepts(cell: str, expected: tuple[str, float]) -> None:
    assert crv.parse_value(cell) == expected


@pytest.mark.parametrize(
    "cell",
    ["empty", "6 files: a.md, b.md", "2535 vs 2535", "A equals B, A > 0", "3 of 5", "actual 21, expected 21"],
)
def test_parse_value_rejects(cell: str) -> None:
    assert crv.parse_value(cell) is None


def test_actual_with_its_own_comparator_is_not_checked() -> None:
    assert crv.compare("> 3", "5") is None
    assert crv.compare("3", "5") is False
    assert crv.compare("5", "≥ 5") is True


# --- read_lines: physical lines and fences -------------------------------------


def write_bytes(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("data", "count"),
    [
        (b"| a | b |\n|---|---|\n| 1 \x0c| 2 |\n", 3),
        ("line1\x85line2\n".encode(), 1),
        ("x y\n".encode(), 1),
        (b"a\x0bb\x1cc\x1dd\x1ee\n", 1),
        (b"one\r\ntwo\rthree\nfour", 4),
        (b"a\n\n", 2),
        (b"", 0),
    ],
)
def test_read_lines_splits_on_line_ends_only(tmp_path: Path, data: bytes, count: int) -> None:
    lines = crv.read_lines(write_bytes(tmp_path, "r.md", data))
    assert len(lines) == count
    assert [line.number for line in lines] == list(range(1, count + 1))


def test_form_feed_keeps_the_table_row_whole(tmp_path: Path) -> None:
    lines = crv.read_lines(write_bytes(tmp_path, "r.md", b"| a | b |\n|---|---|\n| 1 \x0c| 2 |\n"))
    assert lines[2].text == "| 1 \x0c| 2 |"


def test_info_string_line_inside_a_fence_does_not_close_it(tmp_path: Path) -> None:
    path = write_bytes(tmp_path, "r.md", b"```\n| Verdict |\n```python\n| PASS |\n```\nafter\n")
    fenced = [line.fenced for line in crv.read_lines(path)]
    assert fenced == [True, True, True, True, True, False]
