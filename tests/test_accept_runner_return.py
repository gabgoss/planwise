"""Tests for scripts/accept_runner_return.py: the on-disk acceptance gate.

Each test builds a scratch git repository under tmp_path. Each mutation differs
from the accepted state by one defect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import accept_runner_return

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "accept_runner_return.py"

TASK = """# Task: Topic

**Task ID:** ABC-S01-02-01
**Output:** `src/a.txt`; `Outputs/ABC-S01-02-01-Topic.md`
"""

RECOVERY = """# Recovery

| Step | Task | Agent | Status | Completed |
|------|------|-------|--------|-----------|
| 1 | Topic | Opus | {one} | - |
| 2 | Next | Opus | {two} | - |
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        capture_output=True,
        check=True,
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _accepted(tmp_path: Path, task_text: str = TASK) -> tuple[Path, Path, Path]:
    """A repository where task 1 returned with every deliverable in place."""
    repo = tmp_path / "repo"
    session = repo / "plan" / "S"
    task = _write(session / "ABC-S01-02-01-Opus-Topic.md", task_text)
    recovery = _write(session / "ABC-S01-02-Recovery.md", RECOVERY.format(one="PENDING", two="PENDING"))
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _write(recovery, RECOVERY.format(one="COMPLETE", two="PENDING"))
    _write(repo / "src" / "a.txt", "content\n")
    _write(session / "Outputs" / "ABC-S01-02-01-Topic.md", "# Output\n")
    return repo, task, recovery


def _run(repo: Path, task: Path, recovery: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--task", str(task), "--recovery", str(recovery),
         "--repo-root", str(repo), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_positive_accepted_return_exits_0(tmp_path):
    repo, task, recovery = _accepted(tmp_path)
    result = _run(repo, task, recovery)
    assert result.returncode == 0, result.stdout + result.stderr


def test_mutation_deleted_output_exits_1(tmp_path):
    # Breaks §1.17.4: a declared Output file must exist.
    repo, task, recovery = _accepted(tmp_path)
    (task.parent / "Outputs" / "ABC-S01-02-01-Topic.md").unlink()
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "declared Output missing: Outputs/ABC-S01-02-01-Topic.md" in result.stdout


def test_mutation_empty_output_exits_1(tmp_path):
    # Breaks §1.17.4: a declared Output file must be non-empty.
    repo, task, recovery = _accepted(tmp_path)
    _write(repo / "src" / "a.txt", "")
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "declared Output is empty: src/a.txt" in result.stdout


def test_mutation_extra_dirty_path_exits_1(tmp_path):
    # Breaks §1.17.4: the dirty set must equal the declared set.
    repo, task, recovery = _accepted(tmp_path)
    _write(repo / "src" / "b.txt", "stray\n")
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "dirty but not declared: src/b.txt" in result.stdout


TASK_FOLDER = TASK.replace("`Outputs/ABC-S01-02-01-Topic.md`", "`Outputs/rows/`")


def _folder_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo, task, recovery = _accepted(tmp_path, TASK_FOLDER)
    (task.parent / "Outputs" / "ABC-S01-02-01-Topic.md").unlink()
    return repo, task, recovery


def test_declared_folder_with_two_written_files_passes(tmp_path):
    repo, task, recovery = _folder_case(tmp_path)
    _write(task.parent / "Outputs" / "rows" / "r1.md", "one\n")
    _write(task.parent / "Outputs" / "rows" / "r2.md", "two\n")
    result = _run(repo, task, recovery)
    assert result.returncode == 0, result.stdout + result.stderr


def test_mutation_empty_declared_folder_exits_1(tmp_path):
    repo, task, recovery = _folder_case(tmp_path)
    (task.parent / "Outputs" / "rows").mkdir(parents=True)
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "declared Output is empty: Outputs/rows/" in result.stdout


def test_mutation_file_outside_the_declared_folder_is_still_dirty(tmp_path):
    repo, task, recovery = _folder_case(tmp_path)
    _write(task.parent / "Outputs" / "rows" / "r1.md", "one\n")
    _write(task.parent / "Outputs" / "other" / "x.md", "stray\n")
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "dirty but not declared: plan/S/Outputs/other/x.md" in result.stdout
    assert "plan/S/Outputs/rows/r1.md" not in result.stdout


def test_peer_dirty_list_subtracts_a_peer_path(tmp_path):
    repo, task, recovery = _accepted(tmp_path)
    _write(repo / "src" / "b.txt", "peer\n")
    peer = _write(tmp_path / "peer.txt", "src/b.txt\n")
    assert _run(repo, task, recovery, "--peer-dirty", str(peer)).returncode == 0


def test_mutation_recovery_row_not_complete_exits_1(tmp_path):
    # Breaks §1.17.4: the Recovery row must read COMPLETE.
    repo, task, recovery = _accepted(tmp_path)
    _write(recovery, RECOVERY.format(one="IN_PROGRESS", two="PENDING"))
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "step 1 reads IN_PROGRESS, not COMPLETE" in result.stdout


def test_mutation_later_row_complete_is_an_over_run(tmp_path):
    # Breaks the §1.23 over-run sign: a later step already reads COMPLETE.
    repo, task, recovery = _accepted(tmp_path)
    _write(recovery, RECOVERY.format(one="COMPLETE", two="COMPLETE"))
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "later step 2 already reads COMPLETE" in result.stdout
    assert _run(repo, task, recovery, "--closed-session").returncode == 0


def test_mutation_later_output_is_an_over_run(tmp_path):
    # Breaks the §1.23 over-run sign: a later task's output exists.
    repo, task, recovery = _accepted(tmp_path)
    _write(task.parent / "Outputs" / "ABC-S01-02-02-Next.md", "# Next\n")
    result = _run(repo, task, recovery)
    assert result.returncode == 1
    assert "a later task's output exists" in result.stdout


def test_output_paths_reused_from_dispatch_preflight():
    assert accept_runner_return.output_paths(TASK) == {"src/a.txt", "Outputs/ABC-S01-02-01-Topic.md"}


def test_usage_errors_exit_2(tmp_path):
    repo, task, recovery = _accepted(tmp_path)
    no_output = _write(tmp_path / "t.md", "**Task ID:** ABC-S01-02-01\n")
    assert _run(repo, no_output, recovery).returncode == 2
    assert _run(repo, tmp_path / "absent.md", recovery).returncode == 2
    missing_arg = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--task", str(task)],
        capture_output=True, text=True, check=False,
    )
    assert missing_arg.returncode == 2
