"""Tests for the plan-level lint checks in ``lint_gate_checks_plan``.

Each check gets a known-bad plan tree that must produce a finding naming its
check number, and a positive plan tree that must produce none for it. Every
tree is built under ``tmp_path``, so no fixture under
``tests/fixtures/verification_gates`` changes. Sprint and session folder
names are generated from a number, the shape a plan scaffold writes.
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_plan as plan_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _sprint(number: int, name: str) -> str:
    return f"Sprint-{number:02d}-{name}"


def _session(number: int, name: str) -> str:
    return f"Session-{number:02d}-{name}"


def _found(plan_root: Path, check: int) -> list:
    return [
        (f["check"], f["severity"], f["file"], f["line"])
        for f in lint_plan(plan_root, execute=False)
        if f["check"] == check
    ]


def _task(title: str, output: str, after_lines=(), body: str = "") -> str:
    fence = "".join(f"> {line}\n" for line in after_lines)
    text = f"# Task: {title}\n\n**Output:** {output}\n\n{body}"
    if after_lines:
        text += (
            "## Verification Commands\n\n"
            "> [!verify] Before / After Commands\n"
            "> **After:** *(runner)*\n"
            "> ```bash\n" + fence + "> ```\n"
        )
    return text


# ---------------------------------------------------------------------------
# Check 26 -- anchor branch count
# ---------------------------------------------------------------------------

_ANCHOR_HEAD = (
    "# Sprint Signoff\n\n## Mechanical Anchor Checks\n\n"
    "| # | Exit Criterion | Mechanical Anchor | Branches | Result |\n"
    "|---|---|---|---|---|\n"
)


def test_check26_fires_when_listed_outcomes_carry_no_count(tmp_path):
    _write(tmp_path / "Sprint-Signoff.md", _ANCHOR_HEAD + (
        "| 6 | drift resolved | PASS when the report records `repoint`, `route`, or "
        "`CLOSED-NO-ACTION` | n/a | {PASS / FAIL} |\n"
    ))
    assert _found(tmp_path, 26) == [(26, "WARNING", "Sprint-Signoff.md", 7)]


def test_check26_fires_when_stated_count_differs(tmp_path):
    _write(tmp_path / "Sprint-Signoff.md", _ANCHOR_HEAD + (
        "| 6 | drift resolved | PASS when the report records `repoint` or `route` "
        "(3 branches) | n/a | {PASS / FAIL} |\n"
    ))
    assert _found(tmp_path, 26) == [(26, "WARNING", "Sprint-Signoff.md", 7)]


def test_check26_silent_when_count_matches_listed_outcomes(tmp_path):
    _write(tmp_path / "Sprint-Signoff.md", _ANCHOR_HEAD + (
        "| 6 | drift resolved | PASS when the report records `repoint`, `route`, or "
        "`CLOSED-NO-ACTION` (3 branches -- matches task step 4) | 3/3 | {PASS / FAIL} |\n"
        "| 7 | drift resolved | the report records `repoint` or `route` | 2/2 | {PASS / FAIL} |\n"
        "| 8 | headings | each section is named under `## A` or `## B` | 1/1 | {PASS / FAIL} |\n"
    ))
    assert _found(tmp_path, 26) == []


# ---------------------------------------------------------------------------
# Check 27 -- anchor path outside the declared cwd
# ---------------------------------------------------------------------------


def _cwd_tree(tmp_path: Path, anchor: str, declared: str = "repo/") -> Path:
    _write(tmp_path / "repo" / "scripts" / "tool.py", "")
    plan = tmp_path / "plan"
    _write(plan / "Sprint-Signoff.md", (
        "# Sprint Signoff\n\n## Mechanical Anchor Checks\n\n"
        f"Run all anchors from `{declared}`.\n\n"
        "| # | Criterion | Mechanical Anchor | Result |\n"
        "|---|---|---|---|\n"
        f"| 2 | report exists | {anchor} | PASS / FAIL |\n"
    ))
    return plan


def test_check27_fires_on_a_plan_relative_path_under_a_repo_cwd(tmp_path):
    plan = _cwd_tree(tmp_path, "`test -f Outputs/Report.md`")
    assert _found(plan, 27) == [(27, "WARNING", "Sprint-Signoff.md", 9)]


def test_check27_silent_when_paths_resolve_from_the_declared_cwd(tmp_path):
    plan = _cwd_tree(tmp_path, "`test -f scripts/tool.py`; `test -f scripts/new_tool.py`")
    assert _found(plan, 27) == []


def test_check27_uncertain_when_the_declared_cwd_does_not_resolve(tmp_path):
    plan = _cwd_tree(tmp_path, "`test -f Outputs/Report.md`", declared="{repo}/")
    assert _found(plan, 27) == [(27, "UNCERTAIN", "Sprint-Signoff.md", 5)]


# ---------------------------------------------------------------------------
# Check 28 -- a file count over a sibling task's Output
# ---------------------------------------------------------------------------

_COUNT_GATE = "git -C repo diff --name-only $ABC_S01_BASE -- src/a.py src/b.py | wc -l   # 2"


def test_check28_fires_when_a_sibling_writes_a_counted_file(tmp_path):
    session = tmp_path / _session(1, "Work")
    _write(session / "ABC-01-01-Task.md", _task("A", "`src/a.py`, `src/b.py`", [_COUNT_GATE]))
    _write(session / "ABC-01-02-Task.md", _task("B", "`repo/src/b.py` (the helper only)"))
    found = _found(tmp_path, 28)
    assert [(c, s) for c, s, _, _ in found] == [(28, "ERROR")]
    assert found[0][2].endswith("ABC-01-01-Task.md")


def test_check28_silent_for_other_sessions_inequalities_and_excludes(tmp_path):
    first = tmp_path / _session(1, "Work")
    second = tmp_path / _session(2, "Later")
    _write(first / "ABC-01-01-Task.md", _task("A", "`src/a.py`, `src/b.py`", [
        _COUNT_GATE,
        "git -C repo diff --name-only $ABC_S01_BASE -- src/a.py src/c.py | wc -l   # >= 1",
        "git -C repo diff --name-only $ABC_S01_BASE -- src ':(exclude)src/d.py' | wc -l   # 2",
    ]))
    _write(first / "ABC-01-02-Task.md", _task("D", "`src/d.py`"))
    _write(second / "ABC-02-01-Task.md", _task("B", "`src/b.py`, `src/c.py`"))
    assert _found(tmp_path, 28) == []


def _sibling_count_findings(tmp_path: Path, pathspec: str, sibling_output: str) -> list:
    """One session: task A counts ``pathspec`` (no ``-C``, so both sides are
    relative to the same root); task B's Output is ``sibling_output``."""
    session = tmp_path / _session(1, "Work")
    gate = f"git diff --name-only $ABC_S01_BASE -- {pathspec} | wc -l   # 1"
    _write(session / "ABC-01-01-Task.md", _task("A", "`Outputs/A.md`", [gate]))
    _write(session / "ABC-01-02-Task.md", _task("B", f"`{sibling_output}`"))
    return [(c, s) for c, s, _, _ in _found(tmp_path, 28)]


def test_check28_short_directory_pathspec_does_not_match_a_middle_segment(tmp_path):
    assert _sibling_count_findings(tmp_path, "tests", "plugins/x/tests/foo.py") == []


def test_check28_bare_file_pathspec_does_not_match_a_path_suffix(tmp_path):
    assert _sibling_count_findings(tmp_path, "a.py", "other/dir/a.py") == []


def test_check28_directory_pathspec_covers_a_file_under_it(tmp_path):
    assert _sibling_count_findings(tmp_path, "plugins/x/tests", "plugins/x/tests/foo.py") == [(28, "ERROR")]


def test_check28_identical_path_matches(tmp_path):
    assert _sibling_count_findings(tmp_path, "plugins/x/tests/foo.py", "plugins/x/tests/foo.py") == [(28, "ERROR")]


# ---------------------------------------------------------------------------
# Check 29 -- the sprint base is pinned
# ---------------------------------------------------------------------------

_SCOPED_GATE = "git -C repo diff --name-only <ABC_S01_SESSION_BASE> -- src/a.py | wc -l   # 1"


def _sprint_tree(tmp_path: Path, pin_in_orchestration: bool, recovery: str = "") -> Path:
    session = tmp_path / _sprint(1, "Demo") / _session(1, "Work")
    orchestration = "# Session Orchestration\n\n"
    if pin_in_orchestration:
        orchestration += (
            "```bash\n"
            "git -C repo status --porcelain -- src          # MUST be empty\n"
            "git -C repo rev-parse HEAD                     # -> ABC_S01_SESSION_BASE\n"
            "```\n"
        )
    _write(session / "ABC-S01-01-Orchestration.md", orchestration)
    _write(session / "ABC-S01-01-01-Preflight.md", _task(
        "Preflight", "`Outputs/ABC-S01-01-01-Preflight.md`",
        body=("Record `ABC_S01_BASE` behind the clean-scope check.\n\n```bash\n"
              "git -C repo status --porcelain -- src\n```\n\n") if pin_in_orchestration else "",
    ))
    _write(session / "ABC-S01-01-02-Edit.md", _task(
        "Edit", "`repo/src/a.py`, `Outputs/ABC-S01-01-02-Edit.md`", [_SCOPED_GATE],
        body="Sprint gate: `git -C repo diff $ABC_S01_BASE -- src`\n\n",
    ))
    if recovery:
        _write(session / "ABC-S01-01-Recovery.md", recovery)
    return tmp_path


def test_check29_fires_when_no_task_pins_and_no_recovery_records(tmp_path):
    plan = _sprint_tree(tmp_path, pin_in_orchestration=False, recovery="# Recovery\n\nnothing yet\n")
    found = _found(plan, 29)
    assert sorted((c, s) for c, s, _, _ in found) == [(29, "ERROR"), (29, "ERROR")]
    assert all(f[2].endswith("ABC-S01-01-02-Edit.md") for f in found)


def test_check29_silent_when_pinned_behind_a_status_gate(tmp_path):
    plan = _sprint_tree(tmp_path, pin_in_orchestration=True)
    assert _found(plan, 29) == []


def test_check29_silent_when_recovery_records_the_values(tmp_path):
    plan = _sprint_tree(tmp_path, pin_in_orchestration=False, recovery=(
        "# Recovery\n\n- `ABC_S01_BASE` = `0123456789abcdef0123456789abcdef01234567`\n"
        "- `ABC_S01_SESSION_BASE` = `89abcde`\n"
    ))
    assert _found(plan, 29) == []


# ---------------------------------------------------------------------------
# Registration and contract
# ---------------------------------------------------------------------------


def test_each_plan_check_is_registered_once():
    for check in plan_module.CHECKS:
        assert lint_module.CHECK_REGISTRY.count(check) == 1, check.__name__
    numbers = [int(c.__name__.split("_")[1].removeprefix("check")) for c in plan_module.CHECKS]
    assert numbers == [26, 27, 28, 29]


def test_local_constants_and_finding_keys_match_the_linter():
    assert plan_module.SEVERITY_ERROR == lint_module.SEVERITY_ERROR
    assert plan_module.SEVERITY_WARNING == lint_module.SEVERITY_WARNING
    assert plan_module.SEVERITY_UNCERTAIN == lint_module.SEVERITY_UNCERTAIN
    fields = {"check": 26, "severity": "WARNING", "file": "f.md", "line": 3,
              "command": "cmd", "message": "msg"}
    assert plan_module._finding(**fields) == lint_module.make_finding(**fields)


def test_cli_run_as_script_reports_a_plan_check(tmp_path):
    _write(tmp_path / "Sprint-Signoff.md", _ANCHOR_HEAD + (
        "| 6 | drift resolved | PASS when the report records `repoint` or `route` | n/a | x |\n"
    ))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), str(tmp_path), "--no-execute"],
        capture_output=True, text=True, encoding="utf-8", check=False, env=env,
    )
    assert completed.returncode == 1, completed.stderr
    assert "[WARNING] Check 26:" in completed.stdout
