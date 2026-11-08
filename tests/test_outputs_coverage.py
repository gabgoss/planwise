"""Tests for scripts/outputs_coverage.py (Outputs/ listing coverage and count claims)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import outputs_coverage as oc

SCRIPT = (
    Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "outputs_coverage.py"
)


def _task(path: Path, named: list[str], extra: str = "") -> Path:
    rows = "\n".join(f"| 1 | `Outputs/{n}` | 1.0 | ~0.4K | input |" for n in named)
    path.write_text(
        "# Task\n\n## Required Context\n\n"
        "| Priority | File | KiB | ~Tokens | Purpose |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n\n## Execution Steps\n\n{extra}\n",
        encoding="utf-8",
    )
    return path


def _outputs(root: Path, names: list[str]) -> Path:
    d = root / "Outputs"
    d.mkdir()
    (d / ".gitkeep").write_text("", encoding="utf-8")
    for n in names:
        (d / n).write_text("x\n", encoding="utf-8")
    return d


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_named_producer_fails_on_unnamed_and_passes_repaired(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md"])
    bad = _task(tmp_path / "t1.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(bad), "--side", "producer")
    assert r.returncode == 1
    assert r.stdout.splitlines()[0].startswith("listing: 2 files")
    assert "unnamed: b.md" in r.stdout
    good = _task(tmp_path / "t2.md", ["a.md", "b.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(good), "--side", "producer")
    assert r.returncode == 0
    assert "unnamed:" not in r.stdout


def test_named_receiver_prints_but_exits_zero(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md"])
    bad = _task(tmp_path / "t1.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(bad), "--side", "receiver")
    assert r.returncode == 0
    assert "unnamed: b.md" in r.stdout


def test_gitkeep_is_ignored_by_listing(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    assert oc.list_outputs(str(out)) == ["a.md"]


def test_empty_listing_prints_zero_count(tmp_path):
    out = _outputs(tmp_path, [])
    t = _task(tmp_path / "t.md", [])
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer")
    assert r.returncode == 0
    assert r.stdout.splitlines()[0].startswith("listing: 0 files")


def test_mention_outside_required_context_does_not_name(tmp_path):
    _outputs(tmp_path, ["a.md"])
    t = _task(tmp_path / "t.md", [], extra="See a.md in prose.")
    assert oc.find_unnamed(["a.md"], [str(t)]) == ["a.md"]


def test_count_catches_spelled_out_claim_and_passes_repaired(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md", "c.md"])
    bad = _task(tmp_path / "t1.md", ["a.md"], extra="Read the eleven outputs first.")
    r = _run("count", "--outputs", str(out), "--tasks", str(bad))
    assert r.returncode == 1
    assert r.stdout.splitlines()[0].startswith("listing: 3 files")
    assert "says 11" in r.stdout and "listing has 3" in r.stdout
    good = _task(tmp_path / "t2.md", ["a.md"], extra="Read the three outputs first.")
    r = _run("count", "--outputs", str(out), "--tasks", str(good))
    assert r.returncode == 0
    assert "claims seen: 1" in r.stdout


def test_count_catches_digit_claim(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    bad = _task(tmp_path / "t.md", ["a.md"], extra="All 4 output files are inputs.")
    r = _run("count", "--outputs", str(out), "--tasks", str(bad))
    assert r.returncode == 1
    assert "says 4" in r.stdout


def test_count_with_no_claims_reports_zero_seen(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    r = _run("count", "--outputs", str(out), "--tasks", str(t))
    assert r.returncode == 0
    assert "claims seen: 0" in r.stdout


def test_suffix_of_longer_name_does_not_name_the_file(tmp_path):
    t = _task(tmp_path / "t.md", ["RFH-S04-01-01-Audit.md"])
    assert oc.find_unnamed(["01-Audit.md"], [str(t)]) == ["01-Audit.md"]
    assert oc.find_unnamed(["RFH-S04-01-01-Audit.md"], [str(t)]) == []


def test_name_with_longer_extension_does_not_name_the_file(tmp_path):
    t = _task(tmp_path / "t.md", ["a.md.bak"])
    assert oc.find_unnamed(["a.md"], [str(t)]) == ["a.md"]


def test_missing_outputs_dir_exits_two_with_error_line(tmp_path):
    t = _task(tmp_path / "t.md", ["a.md"])
    for side in ("producer", "receiver"):
        r = _run("named", "--outputs", str(tmp_path / "nope"), "--tasks", str(t), "--side", side)
        assert r.returncode == 2
        assert r.stdout.startswith("error:")
        assert "Traceback" not in r.stderr


def test_unreadable_task_file_exits_two(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    r = _run("count", "--outputs", str(out), "--tasks", str(tmp_path / "missing.md"))
    assert r.returncode == 2
    assert r.stdout.splitlines()[-1].startswith("error:")


def test_runs_under_optimize_two(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    r = subprocess.run(
        [sys.executable, "-B", "-OO", str(SCRIPT), "count", "--outputs", str(out), "--tasks", str(t)],
        capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
