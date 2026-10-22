"""Tests for path_set_gate.py."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import path_set_gate as psg


def _lists(tmp_path, changed, allowed, expected):
    paths = []
    for name, rows in (("c", changed), ("a", allowed), ("e", expected)):
        p = tmp_path / f"{name}.txt"
        p.write_bytes(("\r\n".join(rows) + "\r\n").encode())  # CRLF on purpose
        paths.append(str(p))
    return paths


def test_empty_difference_exits_zero(tmp_path):
    args = _lists(tmp_path, ["x/a.md", "x/b.md"], ["x/a.md"], ["x/b.md"])
    assert psg.main(args) == 0


def test_unexpected_path_exits_one(tmp_path, capsys):
    args = _lists(tmp_path, ["x/a.md", "x/stray.md"], ["x/a.md"], [])
    assert psg.main(args) == 1
    assert "UNEXPECTED: x/stray.md" in capsys.readouterr().out


def test_stdin_changed_list(tmp_path, monkeypatch):
    _, a, e = _lists(tmp_path, [], ["x/a.md"], [])
    monkeypatch.setattr(sys, "stdin", io.StringIO("x/a.md\n"))
    assert psg.main(["-", a, e]) == 0


def test_utf16_list_exits_two(tmp_path, capsys):
    changed, allowed, expected = _lists(tmp_path, ["x/a.md"], ["x/a.md"], [])
    Path(changed).write_bytes("x/a.md\r\n".encode("utf-16"))  # PowerShell > output
    assert psg.main([changed, allowed, expected]) == 2
    assert capsys.readouterr().err.startswith("Error:")


def test_counts_of_every_input_are_printed(tmp_path, capsys):
    args = _lists(tmp_path, [], [], [])
    assert psg.main(args) == 0
    assert "changed=0 allowed=0 expected=0" in capsys.readouterr().out


def test_usage_exit_two(tmp_path):
    assert psg.main([]) == 2
    assert psg.main(["nope.txt", "nope2.txt", "nope3.txt"]) == 2
