"""Tests for scripts/diff_hunk_census.py: exit contract 0 / 1 / 2."""

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "planwise"
    / "scripts"
    / "diff_hunk_census.py"
)


def run(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def write(path, data):
    path.write_bytes(data)
    return path


def test_extended_copy_exits_zero(tmp_path):
    control = write(tmp_path / "c.txt", b"one\ntwo\nthree\n")
    cand = write(tmp_path / "x.txt", b"one\ntwo\nthree\nfour\n")
    result = run(control, cand)
    assert result.returncode == 0
    assert result.stdout.strip().splitlines()[-1] == "d=0 c=0 a=1"


def test_deleted_line_exits_one(tmp_path):
    control = write(tmp_path / "c.txt", b"one\ntwo\nthree\n")
    cand = write(tmp_path / "x.txt", b"one\nthree\n")
    result = run(control, cand)
    assert result.returncode == 1
    lines = result.stdout.strip().splitlines()
    assert lines[0].startswith("d ")
    assert lines[-1] == "d=1 c=0 a=0"


def test_crlf_control_against_lf_candidate_is_one_changed_hunk(tmp_path):
    control = write(tmp_path / "c.txt", b"one\r\ntwo\r\nthree\r\n")
    cand = write(tmp_path / "x.txt", b"one\ntwo\nthree\n")
    result = run(control, cand)
    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0].startswith("c ")
    assert lines[-1] == "d=0 c=1 a=0"


def test_usage_and_missing_path_exit_two(tmp_path):
    assert run().returncode == 2
    present = write(tmp_path / "c.txt", b"x\n")
    assert run(present, tmp_path / "absent.txt").returncode == 2
