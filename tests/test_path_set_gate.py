"""Tests for path_set_gate.py."""
import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import path_set_gate as psg

TEMPLATE = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "templates" / "orchestration.md"


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


# --- Real-git arms: the scaffolded "wrote nothing under X" listing with a commit leg ---

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def _git(repo, *args):
    done = subprocess.run(
        [*_GIT, *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout


def _commit_file(repo, rel, text="x\n"):
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode())
    _git(repo, "add", "--", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


def _listing(repo, sha, commit_leg=True):
    """Run the listing legs as argv lists and return their sorted union."""
    out = _git(repo, "diff", "--name-only", "HEAD", "--", "x")
    out += _git(repo, "ls-files", "--others", "--exclude-standard", "--", "x")
    if commit_leg:
        out += _git(repo, "log", "--name-only", "--format=", f"{sha}..HEAD", "--", "x")
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def _write_list(path, rows):
    path.write_bytes(("".join(f"{r}\n" for r in rows)).encode())  # LF-only
    return str(path)


def _gate(tmp_path, after, before, peer):
    args = [
        _write_list(tmp_path / "after.txt", after),
        _write_list(tmp_path / "before.txt", before),
        _write_list(tmp_path / "peer.txt", peer),
    ]
    return psg.main(args)


def _correct_listing_line(text):
    """Return the CORRECT-block line that writes the before list, or None."""
    for line in text.splitlines():
        if "git diff --name-only HEAD -- {X}" in line and "{before list}" in line:
            return line
    return None


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
class TestCommitLegWithRealGit:
    @pytest.fixture
    def repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _commit_file(repo, "x/seed.md")
        sha = _git(repo, "rev-parse", "HEAD").strip()
        work = tmp_path / "lists"
        work.mkdir()
        return repo, sha, work

    def test_a_no_change_exits_zero(self, repo):
        root, sha, work = repo
        before = _listing(root, sha)
        assert before == []
        assert _gate(work, _listing(root, sha), before, []) == 0

    def test_b_own_commit_exits_one(self, repo, capsys):
        root, sha, work = repo
        before = _listing(root, sha)
        _commit_file(root, "x/own.md")
        after = _listing(root, sha)
        assert after == ["x/own.md"]
        assert _gate(work, after, before, []) == 1
        assert "UNEXPECTED: x/own.md" in capsys.readouterr().out

    def test_c_classed_peer_commit_exits_zero(self, repo):
        root, sha, work = repo
        before = _listing(root, sha)
        _commit_file(root, "x/peer.md")
        peer_sha = _git(root, "rev-parse", "HEAD").strip()
        peer_paths = [p for p in _git(root, "show", "--name-only", "--format=", peer_sha).splitlines() if p]
        assert peer_paths == ["x/peer.md"]
        assert _gate(work, _listing(root, sha), before, peer_paths) == 0

    def test_d_old_two_leg_listing_is_blind_to_own_commit(self, repo):
        root, sha, work = repo
        before = _listing(root, sha, commit_leg=False)
        _commit_file(root, "x/own.md")
        after = _listing(root, sha, commit_leg=False)
        assert after == []  # the commit removed its path from the dirty set
        assert _gate(work, after, before, []) == 0  # known-bad: the old form passes an own commit


def test_e_template_carries_the_commit_leg():
    line = _correct_listing_line(TEMPLATE.read_text(encoding="utf-8"))
    assert line is not None, "CORRECT-block listing line not found"
    assert "{dispatch sha}..HEAD -- {X}" in line


def test_e_control_listing_without_the_third_leg_fails():
    text = (
        "> { git diff --name-only HEAD -- {X}; git ls-files --others --exclude-standard -- {X}; }"
        " | sort -u > {before list}\n"
    )
    line = _correct_listing_line(text)
    assert line is not None
    assert "{dispatch sha}..HEAD -- {X}" not in line
