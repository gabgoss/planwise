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


ORCHESTRATION_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "templates" / "orchestration.md"
)


def test_orchestration_template_names_task_files_per_side():
    """The post-dispatch checklist line gives each side its own `--tasks` slot."""
    text = ORCHESTRATION_TEMPLATE.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "outputs_coverage.py" in ln and " named " in ln)
    spans = line.split("`")[1::2]
    invocations = [s for s in spans if "outputs_coverage.py" in s]
    producer = [s for s in invocations if "--side producer" in s]
    receiver = [s for s in invocations if "--side receiver" in s]
    assert producer, "no --side producer invocation on the checklist line"
    assert receiver, "no --side receiver invocation on the checklist line"
    # (a) producer: this session's Outputs against the downstream consumer task files
    assert all("--tasks {downstream consumer task files}" in s for s in producer)
    # (b) receiver: the upstream Outputs against this session's task files
    assert all("--tasks {this session's task files}" in s for s in receiver)
    # (c) no producer form takes this session's own task files or the bare placeholder
    for s in producer:
        assert "{this session's task files}" not in s
        assert "{task files}" not in s
    # (d) the no-consumer-yet skip rule is present
    assert "no consumer task file exists yet" in line.lower()
    assert "not applicable" in line.lower()


def test_terminal_only_unnamed_file_exits_zero_and_prints_terminal_line(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer", "--terminal", "b.md")
    assert r.returncode == 0, r.stdout
    assert "terminal: b.md" in r.stdout
    assert "unnamed:" not in r.stdout
    # the same run without the exemption is the known-bad reading: exit 1 on b.md
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer")
    assert r.returncode == 1
    assert "unnamed: b.md" in r.stdout


def test_terminal_exempts_only_the_listed_file(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md", "c.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer", "--terminal", "b.md")
    assert r.returncode == 1
    assert "terminal: b.md" in r.stdout
    assert "unnamed: c.md" in r.stdout
    assert "unnamed: b.md" not in r.stdout


def test_terminal_name_missing_from_listing_exits_two(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    for side in ("producer", "receiver"):
        r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", side, "--terminal", "gone.md")
        assert r.returncode == 2, r.stdout
        assert "error: --terminal name not in the listing: gone.md" in r.stdout
        assert "Traceback" not in r.stderr


def test_terminal_accepts_several_names_and_the_receiver_still_exits_zero(tmp_path):
    out = _outputs(tmp_path, ["a.md", "b.md", "c.md"])
    t = _task(tmp_path / "t.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer", "--terminal", "b.md", "c.md")
    assert r.returncode == 0, r.stdout
    assert "terminal: b.md" in r.stdout and "terminal: c.md" in r.stdout
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "receiver", "--terminal", "b.md")
    assert r.returncode == 0
    assert "unnamed: c.md" in r.stdout


def test_orchestration_template_states_exit_semantics_and_terminal_slot():
    """The checklist line restates the exit codes per side and names the terminal slot."""
    text = ORCHESTRATION_TEMPLATE.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "outputs_coverage.py" in ln and " named " in ln)
    spans = line.split("`")[1::2]
    producer = [s for s in spans if "outputs_coverage.py" in s and "--side producer" in s]
    receiver = [s for s in spans if "outputs_coverage.py" in s and "--side receiver" in s]
    assert producer and receiver
    for s in producer:
        # the terminal slot follows the tasks slot, so the per-side tasks wording is untouched
        assert s.index("--terminal {Outputs no later session consumes}") > s.index(
            "--tasks {downstream consumer task files}"
        )
    for s in receiver:
        assert "--terminal" not in s
    low = line.lower()
    assert "producer run exits 0" in low and "exits 1" in low
    assert "receiver run always exits 0" in low
    assert "exit 2 means the gate did not run" in low


def test_comma_glued_tasks_exit_two_and_name_the_separator(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    a = _task(tmp_path / "t1.md", ["a.md"])
    b = _task(tmp_path / "t2.md", ["a.md"])
    # an unquoted "a, b" keeps the comma on the first token, a quoted one is a single token
    for tasks in ([f"{a},", str(b)], [f"{a}, {b}"]):
        for argv in (
            ["named", "--outputs", str(out), "--side", "producer", "--tasks", *tasks],
            ["count", "--outputs", str(out), "--tasks", *tasks],
        ):
            r = _run(*argv)
            assert r.returncode == 2, r.stdout
            assert "not commas" in r.stdout
            assert "[Errno" not in r.stdout
            assert "Traceback" not in r.stderr


def test_space_separated_tasks_are_accepted(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    a = _task(tmp_path / "t1.md", ["a.md"])
    b = _task(tmp_path / "t2.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(a), str(b), "--side", "producer")
    assert r.returncode == 0, r.stdout
    assert "task files: 2" in r.stdout.splitlines()[0]


def test_existing_task_path_with_comma_is_not_refused(tmp_path):
    out = _outputs(tmp_path, ["a.md"])
    t = _task(tmp_path / "a,b.md", ["a.md"])
    r = _run("named", "--outputs", str(out), "--tasks", str(t), "--side", "producer")
    assert r.returncode == 0, r.stdout


def test_orchestration_template_states_the_tasks_separator():
    text = ORCHESTRATION_TEMPLATE.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "outputs_coverage.py" in ln and " named " in ln)
    assert "with spaces, never commas" in line
