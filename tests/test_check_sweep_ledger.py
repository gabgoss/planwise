"""Tests for check_sweep_ledger.py."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_sweep_ledger as csl
import pytest

HEADER = "| Deliverable | Class | Invoked from |\n|---|---|---|\n"
GOOD = "| hint | adds a parameter | `scripts/x.py:12` `x(arg)` |\n"
BAD = "| deep | adds a flag | definition exists |\n"


def _run(tmp_path, text):
    path = tmp_path / "ledger.md"
    path.write_text(text, encoding="utf-8")
    return csl.main([str(path)])


def test_row_with_call_site_is_clean(tmp_path, capsys):
    assert _run(tmp_path, HEADER + GOOD) == 0
    assert capsys.readouterr().out.splitlines()[0] == "1 behaviour-adding rows checked in 1 ledger tables"


def test_row_without_file_line_fires(tmp_path, capsys):
    assert _run(tmp_path, HEADER + GOOD + BAD) == 1
    out = capsys.readouterr().out
    assert "NO CALL SITE line 4 (missing file:line and calling expression)" in out
    assert "hint" not in out.split("NO CALL SITE", 1)[1]


def test_row_with_file_line_but_no_expression_fires(tmp_path, capsys):
    assert _run(tmp_path, HEADER + "| k | adds a key | scripts/c.py:4 |\n") == 1
    assert "missing calling expression" in capsys.readouterr().out


@pytest.mark.parametrize("quoted", ["`def x(arg):`", "`class X(Base):`", "`async def x(a)`"])
def test_row_quoting_only_the_definition_fires(tmp_path, capsys, quoted):
    assert _run(tmp_path, HEADER + f"| d | adds a function | scripts/x.py:12 {quoted} |\n") == 1
    assert "missing calling expression" in capsys.readouterr().out


def test_parenthesis_between_two_spans_is_not_an_expression(tmp_path):
    assert _run(tmp_path, HEADER + "| d | adds a flag | `scripts/x.py:3` see (note) `x` |\n") == 1


def test_non_behaviour_row_is_skipped(tmp_path, capsys):
    assert _run(tmp_path, HEADER + "| doc | reword only | none |\n") == 0
    assert capsys.readouterr().out.startswith("0 behaviour-adding rows checked in 1 ledger tables")


def test_behaviour_class_cell_counts(tmp_path):
    assert _run(tmp_path, HEADER + "| g | behaviour | none |\n") == 1


def test_table_without_ledger_columns_is_ignored(tmp_path, capsys):
    assert _run(tmp_path, "| Name | Count |\n|---|---|\n| adds a flag | 3 |\n") == 0
    assert capsys.readouterr().out.startswith("0 behaviour-adding rows checked in 0 ledger tables")


def test_escaped_pipe_stays_in_its_cell(tmp_path):
    text = HEADER + "| p | adds a branch \\| guard | `scripts/x.py:3` `x(a)` |\n"
    assert _run(tmp_path, text) == 0


def test_stdin_dash(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(HEADER + BAD))
    assert csl.main(["-"]) == 1


@pytest.mark.parametrize("argv", [[], ["a", "b"], ["/nonexistent/none.md"]])
def test_usage_exit_two(argv):
    assert csl.main(argv) == 2


def test_help_exits_zero(capsys):
    assert csl.main(["--help"]) == 0
    assert "<ledger.md|->" in capsys.readouterr().out
