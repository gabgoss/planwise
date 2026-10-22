"""Tests for scripts/byte_tally.py: exit contract 0 / 1 / 2."""

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "planwise"
    / "scripts"
    / "byte_tally.py"
)


def run(*args):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_lf_file_exits_zero(tmp_path):
    f = write(tmp_path / "a.md", b"a\nb\n")
    result = run(f)
    assert result.returncode == 0
    assert result.stdout.startswith("lf ")
    assert result.stdout.strip().splitlines()[-1] == "files=1 mixed=0"


def test_crlf_file_exits_zero(tmp_path):
    f = write(tmp_path / "a.md", b"a\r\nb\r\n")
    result = run(f)
    assert result.returncode == 0
    assert result.stdout.startswith("crlf ")
    assert result.stdout.strip().splitlines()[-1] == "files=1 mixed=0"


def test_mixed_file_exits_one(tmp_path):
    f = write(tmp_path / "a.md", b"a\r\nb\n")
    result = run(f)
    assert result.returncode == 1
    assert result.stdout.startswith("mixed ")
    assert result.stdout.strip().splitlines()[-1] == "files=1 mixed=1"


def test_crlf_to_lf_snapshot_counts_changed(tmp_path):
    write(tmp_path / "before" / "a.md", b"a\r\nb\r\n")
    write(tmp_path / "after" / "a.md", b"a\nb\n")
    result = run("--before", tmp_path / "before", "--after", tmp_path / "after")
    assert result.returncode == 1
    assert result.stdout.strip().splitlines()[-1] == "files=1 mixed=0 changed=1"


def test_unchanged_snapshot_exits_zero(tmp_path):
    write(tmp_path / "before" / "a.md", b"a\r\nb\r\n")
    write(tmp_path / "after" / "a.md", b"a\r\nb\r\nc\r\n")
    result = run("--before", tmp_path / "before", "--after", tmp_path / "after")
    assert result.returncode == 0
    assert result.stdout.strip().splitlines()[-1] == "files=1 mixed=0 changed=0"


def test_usage_exits_two(tmp_path):
    assert run().returncode == 2
    assert run("--before", tmp_path).returncode == 2
    assert run(tmp_path / "absent.md").returncode == 2
