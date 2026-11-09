"""Tests for scripts/record_checks.py: one positive and one mutation control per subcommand."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import record_checks


def _write(path: Path, text: str, newline: str = "\n") -> Path:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def test_parser_builds_when_docstring_is_stripped(monkeypatch):
    # python -OO sets __doc__ to None; the parser must still build
    monkeypatch.setattr(record_checks, "__doc__", None)
    assert record_checks.build_parser().description == "record checks"


# ---- sums ----


def test_sums_positive_form_i(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "total 15+11+21 = 47 here\n")
    assert record_checks.main(["sums", str(f)]) == 0
    assert capsys.readouterr().out.startswith("evaluated 1")


def test_sums_mutation_form_i(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "intro\ntotal 15+11+21 = 48 here\n")
    assert record_checks.main(["sums", str(f)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("evaluated 1")
    assert "a.md:2: 15+11+21 = 48 (computed 47)" in out


def test_sums_thousands_separator(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "1,000 + 2,500 = 3,500\n")
    assert record_checks.main(["sums", str(f)]) == 0
    f2 = _write(tmp_path / "b.md", "1,000 + 2,500 = 3,400\n")
    assert record_checks.main(["sums", str(f2)]) == 1
    assert "computed 3500" in capsys.readouterr().out


def test_sums_form_ii_positive_and_mutation(tmp_path, capsys):
    good = _write(tmp_path / "g.md", "Tier 1 sources 997 lines (271 + 187 + 147 + 124 + 268, tool, 2026)\n")
    assert record_checks.main(["sums", str(good)]) == 0
    bad = _write(tmp_path / "b.md", "Tier 1 sources 998 lines (271 + 187 + 147 + 124 + 268, tool, 2026)\n")
    capsys.readouterr()
    assert record_checks.main(["sums", str(bad)]) == 1
    assert "computed 997" in capsys.readouterr().out


def test_sums_form_ii_total_not_adjacent(tmp_path):
    f = _write(tmp_path / "a.md", "| Headings | 64 over 8 files (column: 7+7+10+6+8+19+3+4) | x |\n")
    assert record_checks.main(["sums", str(f)]) == 0


def test_sums_zero_found_exits_two(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "no arithmetic here\n")
    assert record_checks.main(["sums", str(f)]) == 2
    assert capsys.readouterr().out.startswith("evaluated 0")


# ---- self-count ----


def test_self_count_lines_positive(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "Lines: 3\nbody\nend\n")
    assert record_checks.main(["self-count", "--field", "lines", str(f)]) == 0
    assert capsys.readouterr().out.startswith("examined 1 recorded figure")


def test_self_count_lines_mutation(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "Lines: 9\nbody\nend\n")
    assert record_checks.main(["self-count", "--field", "lines", str(f)]) == 1
    assert "recorded lines 9, actual 3" in capsys.readouterr().out


def test_self_count_bytes_crlf(tmp_path, capsys):
    # CRLF file: "Bytes: 16\r\n" is 11 bytes and "abc\r\n" is 5, so the raw total is 16
    good = _write(tmp_path / "g.md", "Bytes: 16\nabc\n", newline="\r\n")
    assert len(good.read_bytes()) == 16
    assert record_checks.main(["self-count", "--field", "bytes", str(good)]) == 0
    bad = _write(tmp_path / "b.md", "Bytes: 14\nabc\n", newline="\r\n")  # the LF-form count
    capsys.readouterr()
    assert record_checks.main(["self-count", "--field", "bytes", str(bad)]) == 1
    assert "recorded bytes 14, actual 16" in capsys.readouterr().out


def test_self_count_no_figure_exits_two(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "nothing recorded\n")
    assert record_checks.main(["self-count", "--field", "bytes", str(f)]) == 2
    assert capsys.readouterr().out.startswith("examined 0")


# ---- commit-scope ----


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("a\n")
    (r / "b.txt").write_text("b\n")
    _git(r, "add", "a.txt", "b.txt")
    _git(r, "commit", "-q", "-m", "c")
    return r


def test_commit_scope_positive(repo, tmp_path, capsys):
    decl = tmp_path / "decl.txt"
    decl.write_bytes(b"a.txt\nb.txt\n")
    assert record_checks.main(["commit-scope", "--repo", str(repo), "--declared", str(decl)]) == 0
    assert capsys.readouterr().out.startswith("declared 2 paths")


def test_commit_scope_mutation_lists_foreign(repo, tmp_path, capsys):
    decl = tmp_path / "decl.txt"
    decl.write_bytes(b"a.txt\n")
    assert record_checks.main(["commit-scope", "--repo", str(repo), "--declared", str(decl)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("declared 1 paths")
    assert "foreign path: b.txt" in out


def test_commit_scope_empty_declared_exits_two(repo, tmp_path, capsys):
    decl = tmp_path / "decl.txt"
    decl.write_bytes(b"\n")
    assert record_checks.main(["commit-scope", "--repo", str(repo), "--declared", str(decl)]) == 2
    assert capsys.readouterr().out.startswith("declared 0 paths")


def test_commit_scope_bad_rev_exits_two(repo, tmp_path, capsys):
    decl = tmp_path / "decl.txt"
    decl.write_bytes(b"a.txt\n")
    code = record_checks.main(["commit-scope", "--repo", str(repo), "--rev", "no-such-rev", "--declared", str(decl)])
    assert code == 2
    assert "cannot resolve" in capsys.readouterr().out


# ---- review fixes ----


def test_self_count_comma_only_capture_exits_two(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "Lines: , 5\nbody\n")
    assert record_checks.main(["self-count", "--field", "lines", str(f)]) == 2
    assert "not a number" in capsys.readouterr().out


def test_self_count_custom_pattern_non_numeric_exits_two(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "count=abc\n")
    assert record_checks.main(["self-count", "--pattern", r"count=(\w+)", str(f)]) == 2
    assert "not a number" in capsys.readouterr().out


def test_self_count_capture_does_not_cross_a_line_break(tmp_path, capsys):
    f = _write(tmp_path / "a.md", "Lines:\n2\n")
    assert record_checks.main(["self-count", "--field", "lines", str(f)]) == 2
    assert capsys.readouterr().out.startswith("examined 0")


def test_commit_scope_zero_listed_paths_exits_two(repo, tmp_path, capsys):
    _git(repo, "commit", "-q", "--allow-empty", "-m", "empty")
    decl = tmp_path / "decl.txt"
    decl.write_bytes(b"a.txt\n")
    assert record_checks.main(["commit-scope", "--repo", str(repo), "--declared", str(decl)]) == 2
    assert "commit lists 0 paths" in capsys.readouterr().out


def test_sums_paren_sum_with_wide_whitespace(tmp_path, capsys):
    good = _write(tmp_path / "g.md", "(100 + 20  = 120)\n(100 + 20\t= 120)\n")
    assert record_checks.main(["sums", str(good)]) == 0
    assert capsys.readouterr().out.startswith("evaluated 2")
    bad = _write(tmp_path / "b.md", "(100 + 20  = 130)\n")
    assert record_checks.main(["sums", str(bad)]) == 1
    assert "computed 120" in capsys.readouterr().out
