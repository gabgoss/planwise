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


def test_check27_resolves_a_git_C_pathspec_from_the_C_directory(tmp_path):
    _write(tmp_path / "repo" / "sub" / "lib" / "b.py", "")
    plan = _cwd_tree(tmp_path, "`git -C sub diff -- lib/b.py`")
    assert _found(plan, 27) == []


def test_check27_fires_on_a_git_C_pathspec_missing_under_the_C_directory(tmp_path):
    # scripts/ exists at the cwd and not under sub/, so only the -C base can flag it.
    _write(tmp_path / "repo" / "sub" / "lib" / "b.py", "")
    plan = _cwd_tree(tmp_path, "`git -C sub diff -- scripts/tool.py`")
    assert _found(plan, 27) == [(27, "WARNING", "Sprint-Signoff.md", 9)]


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


_UNION_PATHS = "src/a.py src/b.py src/c.py src/d.py"


def _union_gate(note: str) -> str:
    return (
        "{ git diff --name-only $ABC_S01_BASE -- " + _UNION_PATHS + "; "
        "git ls-files --others --exclude-standard -- " + _UNION_PATHS + "; } | sort -u | wc -l   # " + note
    )


def test_check28_reads_the_union_form_and_fires_on_a_sibling_owned_path(tmp_path):
    session = tmp_path / _session(1, "Work")
    _write(session / "ABC-01-01-Task.md", _task("A", "`src/a.py`", [_union_gate("4")]))
    _write(session / "ABC-01-02-Task.md", _task("B", "`src/b.py`"))
    found = _found(tmp_path, 28)
    assert [(c, s) for c, s, _, _ in found] == [(28, "ERROR")]
    assert found[0][2].endswith("ABC-01-01-Task.md")


# ---------------------------------------------------------------------------
# Check 55 -- a count expectation above the pathspecs it counts
# ---------------------------------------------------------------------------


def _count_expect_findings(tmp_path: Path, gate: str) -> list:
    session = tmp_path / _session(1, "Work")
    _write(session / "ABC-01-01-Task.md", _task("A", "`src/a.py`", [gate]))
    return [(c, s) for c, s, _, _ in _found(tmp_path, 55)]


def test_check55_fires_on_the_union_gate_that_expects_more_than_its_four_paths(tmp_path):
    assert _count_expect_findings(tmp_path, _union_gate("expect 5")) == [(55, "ERROR")]


def test_check55_fires_on_the_plain_name_only_form(tmp_path):
    gate = "git diff --name-only $ABC_S01_BASE -- src/a.py src/b.py | wc -l   # MUST equal 3"
    assert _count_expect_findings(tmp_path, gate) == [(55, "ERROR")]


def test_check55_silent_when_the_expectation_equals_the_path_count(tmp_path):
    assert _count_expect_findings(tmp_path, _union_gate("expect 4")) == []


def test_check55_silent_when_a_pathspec_has_no_computable_bound(tmp_path):
    for spec in ("src", "src/", "'src/*.py' src/a.py", "<ABC_FILES> src/a.py", ".", "src/a.py ':(exclude)src/b.py' src"):
        gate = f"git diff --name-only $ABC_S01_BASE -- {spec} | wc -l   # expect 9"
        assert _count_expect_findings(tmp_path, gate) == [], spec


def test_check55_silent_for_an_inequality_and_a_note_with_no_count(tmp_path):
    for note in (">= 9", "at least 9", "all changed files"):
        gate = f"git diff --name-only $ABC_S01_BASE -- src/a.py | wc -l   # {note}"
        assert _count_expect_findings(tmp_path, gate) == [], note


def test_check55_counts_a_repeated_path_once(tmp_path):
    gate = "git diff --name-only $ABC_S01_BASE -- src/a.py src/a.py | wc -l   # expect 2"
    assert _count_expect_findings(tmp_path, gate) == [(55, "ERROR")]


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
# Check 34 -- a Verification Commands path outside the working directory
# ---------------------------------------------------------------------------

_SESSION_REL = "Sprint-01-Demo/Session-01-Work"


def _vc_plan(repo: Path, commands, field=None) -> Path:
    """A repo (``.git``, ``src/a.py``, ``plans/Master-Plan.md``) holding a plan
    whose one task carries ``commands`` in its Verification Commands block.
    Returns the plan root. ``field`` is the declared working directory."""
    (repo / ".git").mkdir(parents=True)
    _write(repo / "src" / "a.py", "")
    _write(repo / "plans" / "Master-Plan.md", "# Plan\n")
    plan = repo / "plans" / "Demo"
    session = plan / _sprint(1, "Demo") / _session(1, "Work")
    (session / "Outputs").mkdir(parents=True)
    head = f"**Working directory:** `{field}`\n\n" if field else ""
    body = "".join(f"> {command}\n" for command in commands)
    _write(session / "DEM-01-01-Task.md", (
        "# Task: Gate\n\n**Output:** `Outputs/Report.md`\n\n## Verification Commands\n\n" + head
        + "> [!verify] Before / After Commands\n> **After:** *(runner)*\n> ```bash\n" + body + "> ```\n"
    ))
    return plan


_TASK_REL = f"{_SESSION_REL}/DEM-01-01-Task.md"


def test_check34_fires_on_a_block_mixing_repo_root_and_session_paths(tmp_path):
    plan = _vc_plan(tmp_path, ["python src/a.py   # lint", "test -f Outputs/Report.md   # exists"])
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 11)]


def test_check34_silent_when_a_block_keeps_to_one_base(tmp_path):
    repo_only = _vc_plan(tmp_path / "a", ["python src/a.py", "test -f src/a.py"])
    session_only = _vc_plan(tmp_path / "b", ["test -f Outputs/Report.md", "test -f ../x.md"])
    declared = _vc_plan(tmp_path / "c", ["python src/a.py"], field=".")
    assert _found(repo_only, 34) == []
    assert _found(session_only, 34) == []
    assert _found(declared, 34) == []


def test_check34_fires_when_the_repo_root_base_meets_a_session_relative_path(tmp_path):
    plan = _vc_plan(tmp_path, ["test -f Outputs/Report.md"], field=".")
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 12)]


def test_check34_fires_on_a_path_one_level_short_of_the_declared_base(tmp_path):
    plan = _vc_plan(tmp_path, ["test -f ../../Master-Plan.md"], field=f"plans/Demo/{_SESSION_REL}")
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 12)]


def test_check34_silent_on_the_correct_depth_from_the_declared_base(tmp_path):
    plan = _vc_plan(tmp_path, ["test -f ../../../Master-Plan.md"], field=f"plans/Demo/{_SESSION_REL}")
    assert _found(plan, 34) == []


def test_check34_uncertain_when_the_declared_base_is_a_placeholder(tmp_path):
    plan = _vc_plan(tmp_path, ["test -f Outputs/Report.md"], field="{repo}")
    assert _found(plan, 34) == [(34, "UNCERTAIN", _TASK_REL, 7)]


def _git_c_plan(repo: Path, commands, field: "str | None" = ".") -> Path:
    """``_vc_plan`` plus a ``sub/lib/b.py`` under the repo root. The repo root holds
    ``src/`` and the ``sub`` folder holds ``lib/``, so a pathspec read from the wrong
    base resolves for one and not the other."""
    plan = _vc_plan(repo, commands, field=field)
    _write(repo / "sub" / "lib" / "b.py", "")
    _write(repo / "sub" / "lib" / "deep" / "c.py", "")
    return plan


def test_check34_resolves_a_git_C_pathspec_from_the_C_directory(tmp_path):
    plan = _git_c_plan(tmp_path, [
        "git -C sub diff -- lib/b.py",
        "git -C sub diff --name-only -- lib/b.py | wc -l   # 1",
    ])
    assert _found(plan, 34) == []


def test_check34_fires_on_a_git_C_pathspec_missing_under_the_C_directory(tmp_path):
    # src/ exists at the repo root and not under sub/, so only the -C base can flag it.
    plan = _git_c_plan(tmp_path, ["git -C sub diff -- src/b.py"])
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 12)]


def test_check34_still_checks_a_path_beside_a_git_C_stage(tmp_path):
    plan = _git_c_plan(tmp_path, ["git -C sub diff -- lib/b.py", "test -f Outputs/Report.md"])
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 13)]


def test_check34_skips_a_placeholder_git_C_directory(tmp_path):
    plan = _git_c_plan(tmp_path, ["git -C $REPO diff -- nope/b.py"])
    assert _found(plan, 34) == []


def test_check34_mixed_base_test_ignores_a_git_C_pathspec(tmp_path):
    # With no declared directory, src/b.py would read as a repo-root path beside Outputs/.
    plan = _git_c_plan(tmp_path, ["git -C sub diff -- src/b.py", "test -f Outputs/Report.md"], field=None)
    assert _found(plan, 34) == []


def test_check34_joins_repeated_git_C_directories_in_order(tmp_path):
    # git reads -C sub -C lib as sub/lib, so deep/c.py resolves. The last -C alone would not.
    plan = _git_c_plan(tmp_path, ["git -C sub -C lib diff -- deep/c.py"])
    assert _found(plan, 34) == []


def test_check34_reads_a_git_C_pathspec_inside_a_brace_group(tmp_path):
    ok = _git_c_plan(tmp_path / "ok", ["{ git -C sub diff -- lib/b.py; } | wc -l   # 1"])
    bad = _git_c_plan(tmp_path / "bad", ["{ git -C sub diff -- src/b.py; } | wc -l   # 1"])
    assert _found(ok, 34) == []
    assert _found(bad, 34) == [(34, "WARNING", _TASK_REL, 12)]


def test_check34_still_checks_a_git_C_operand_written_as_a_path(tmp_path):
    # An operand that ends in a slash was a checked path before pathspecs took the -C base.
    plan = _git_c_plan(tmp_path, ["git -C nodir/ diff --stat"])
    assert _found(plan, 34) == [(34, "WARNING", _TASK_REL, 12)]


def test_check34_skips_a_git_C_directory_it_cannot_resolve(tmp_path):
    for operand in ("~/repos/x", "/abs/repo"):
        plan = _git_c_plan(tmp_path / operand.strip("/~").replace("/", "_"), [f"git -C {operand} diff -- nope/b.py"])
        assert _found(plan, 34) == [], operand


def test_check34_hint_joins_the_git_C_directory_to_the_other_base(tmp_path):
    plan = _git_c_plan(tmp_path, ["git -C sub diff -- src/b.py"])
    messages = [f["message"] for f in lint_plan(plan, execute=False) if f["check"] == 34]
    assert len(messages) == 1 and "resolves from" not in messages[0], messages
    _write(plan / "sub" / "src" / "b.py", "")   # now the plan root holds sub/src/b.py
    messages = [f["message"] for f in lint_plan(plan, execute=False) if f["check"] == 34]
    assert len(messages) == 1 and "It resolves from '.' instead" in messages[0], messages


# ---------------------------------------------------------------------------
# Check 56 -- a plan-level id a task names with no definition it can read
# ---------------------------------------------------------------------------

_MASTER = (
    "# ABC Master Plan\n\n"
    "### Hypotheses\n\n"
    "| # | Hypothesis | Confirmed By | Status |\n"
    "|---|------------|--------------|--------|\n"
    "| H4 | the cache is stale | task 01 | OPEN |\n\n"
    "## Decisions (Locked)\n\n"
    "| ID | Decision | Rationale |\n"
    "|----|----------|-----------|\n"
    "| D2 | keep the old index | cheaper |\n\n"
    "## Gates\n\n"
    "| Gate | Trigger |\n"
    "|------|---------|\n"
    "| G1 | on merge |\n"
)
_ID_STEP = "1. Confirm hypothesis H4 and apply decision D2 to the new index.\n"
_RC_NO_MASTER = (
    "## Required Context\n\n| # | File | Purpose |\n|---|------|---------|\n"
    "| 1 | `src/a.py` | the module |\n\n"
)
_RC_WITH_MASTER = _RC_NO_MASTER + "| 2 | `ABC-Master-Plan.md` | Decisions and Hypotheses |\n\n"


def _id_findings(tmp_path: Path, task_body: str, master: str = _MASTER) -> list:
    if master:
        _write(tmp_path / "ABC-Master-Plan.md", master)
    task = _write(
        tmp_path / _sprint(1, "Demo") / _session(1, "Work") / "ABC-01-01-Task.md",
        "# Task: A\n\n**Output:** `src/a.py`\n\n" + task_body,
    )
    assert task.exists()
    return [f for f in lint_plan(tmp_path, execute=False) if f["check"] == 56]


def test_check56_fires_on_each_id_defined_only_in_the_master_plan(tmp_path):
    findings = _id_findings(tmp_path, _RC_NO_MASTER + "## Execution Steps\n\n" + _ID_STEP)
    assert [(f["severity"], f["line"]) for f in findings] == [("WARNING", 13), ("WARNING", 13)]
    assert [f["message"].split()[6].rstrip(",") for f in findings] == ["H4", "D2"]


def test_check56_reports_one_finding_per_id_at_the_first_mention(tmp_path):
    body = _RC_NO_MASTER + "## Execution Steps\n\n" + _ID_STEP + "2. Re-check H4 once more.\n"
    assert len(_id_findings(tmp_path, body)) == 2


def test_check56_silent_when_the_definitions_are_inlined_in_the_task(tmp_path):
    inlined = (
        "| H4 | the cache is stale | task 01 | OPEN |\n"
        "D2: keep the old index\n\n"
    )
    assert _id_findings(tmp_path, _RC_NO_MASTER + "## Execution Steps\n\n" + inlined + _ID_STEP) == []


def test_check56_silent_when_required_context_lists_the_master_plan(tmp_path):
    assert _id_findings(tmp_path, _RC_WITH_MASTER + "## Execution Steps\n\n" + _ID_STEP) == []


def test_check56_silent_when_the_id_is_in_no_master_plan_table(tmp_path):
    body = _RC_NO_MASTER + "## Execution Steps\n\n1. Apply G1 and H9 to the index.\n"
    assert _id_findings(tmp_path, body) == []


def test_check56_silent_when_no_master_plan_exists(tmp_path):
    assert _id_findings(tmp_path, _RC_NO_MASTER + "## Execution Steps\n\n" + _ID_STEP, master="") == []


def test_check56_ignores_a_mention_inside_a_fenced_block(tmp_path):
    body = _RC_NO_MASTER + "## Execution Steps\n\n```text\n" + _ID_STEP + "```\n"
    assert _id_findings(tmp_path, body) == []


def test_check56_ignores_a_path_that_embeds_the_id(tmp_path):
    body = _RC_NO_MASTER + "## Execution Steps\n\n1. Read `docs/H4.md` and the D2-notes file.\n"
    assert _id_findings(tmp_path, body) == []


# ---------------------------------------------------------------------------
# Registration and contract
# ---------------------------------------------------------------------------


def test_each_plan_check_is_registered_once():
    for check in plan_module.CHECKS:
        assert lint_module.CHECK_REGISTRY.count(check) == 1, check.__name__
    numbers = [int(c.__name__.split("_")[1].removeprefix("check")) for c in plan_module.CHECKS]
    assert numbers == [26, 27, 28, 29, 34, 55, 56]


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
