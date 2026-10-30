"""Tests for dry_run_pair.py."""
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import dry_run_pair as drp

# A gate that prints the first line of its input file.
_GATE = f"{shlex.quote(Path(sys.executable).as_posix())} -c \"import sys; print(open(sys.argv[1]).readline().strip())\" {{input}}"


def _files(tmp_path, good_text, bad_text):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.txt"
    good.write_text(good_text)
    bad.write_text(bad_text)
    return good.as_posix(), bad.as_posix()


def test_outputs_differ_exits_zero(tmp_path):
    good, bad = _files(tmp_path, "ok\n", "FAIL\n")
    assert drp.main(["--outputs", _GATE, good, bad]) == 0


def test_outputs_identical_exits_one(tmp_path, capsys):
    good, bad = _files(tmp_path, "same\n", "same\n")
    assert drp.main(["--outputs", _GATE, good, bad]) == 1
    assert "IDENTICAL" in capsys.readouterr().out


def test_missing_gate_executable_exits_two(tmp_path, capsys):
    good, bad = _files(tmp_path, "a\n", "b\n")
    assert drp.main(["--outputs", "no-such-gate-binary-xyz {input}", good, bad]) == 2
    assert capsys.readouterr().err.startswith("Error:")


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True,
    )


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "f.md").write_bytes(b"## One\nbody\n## Two\n")
    _git(repo, "add", "f.md")
    _git(repo, "commit", "-q", "-m", "init")
    # Working copy: CRLF endings and one more heading.
    (repo / "f.md").write_bytes(b"## One\r\nbody\r\n## Two\r\n## Three\r\n")
    return repo


def test_at_head_differing_count_exits_zero(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert drp.main(["--at-head", str(repo), "f.md", "^## "]) == 0
    assert "HEAD=2 working=3" in capsys.readouterr().out


def test_at_head_equal_count_exits_one_despite_crlf(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert drp.main(["--at-head", str(repo), "f.md", "^body$"]) == 1
    assert "HEAD=1 working=1" in capsys.readouterr().out


def test_usage_exit_two(tmp_path):
    assert drp.main([]) == 2
    assert drp.main(["--outputs", "x"]) == 2
    assert drp.main(["--at-head", "a", "b"]) == 2
    assert drp.main(["--at-head", str(_repo(tmp_path)), "missing.md", "x"]) == 2
