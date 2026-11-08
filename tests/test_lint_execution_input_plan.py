"""Tests for lint_execution_input_plan.py: the ten plan-file rules of the EI lint.

Every fixture is written under pytest's tmp_path. The base fixture is a plan
folder with two sprints, a Master Plan, an EI, a Sprint Plan, one session and a
Consolidated Context part under the plan root. It exits 0 with no finding. Each
rule then gets a known-bad copy that produces the rule's exit contract and the
repaired copy that exits 0 with no finding. The Cross-Sprint File Touches row
and the Spec cells copy the shape of real plan rows.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_execution_input as lint
import lint_execution_input_plan as plan_rules

SPRINT = "plan/Exec-XYZ/Sprint-02-Demo"
SESSION = f"{SPRINT}/Session-01-Alpha"

MASTER_PLAN = """# XYZ Master Plan

## Global Source Map

| # | Tier | Source File | ~Tokens |
|---|---|---|---|
| 1 | T2 | `XYZ-Consolidated-Context-Part-1-Alpha.md` | 100 |
| 2 | T1 | `XYZ-META-S01-01-Family.md` | 100 |

## Sprint Dependencies

Sprint-02 follows Sprint-01.
"""

EARLIER_PLAN = """# XYZ Sprint 01 Plan

## Write-Set

| Path | Task |
|---|---|
| `tests/test_shared.py` | XYZ-S01-02-04 |
"""

PART_1 = """# XYZ Sprint 02 Execution Input — Part 1: Header

**Sprint:** XYZ-S02
**Extracted from:** Spec #1 (XYZ-Consolidated-Context-Part-1-Alpha.md) [Tier 2], Spec #2 (XYZ-META-S01-01-Family.md) [Tier 1 raw]
**Retention: 100 %** (EI Parts 1 to 1, 5,000 tokens ÷ 5,000 source tokens).

---

## Section 1: Token Budget

| Session | Budget |
|---|---|
| XYZ-S02-01 | ~100K |

## Section 2: Rules

The cache rule applies to every reader.

**Note (cross-tier duplicate preserved):** This rule is cited in Spec #1 (XYZ-Consolidated-Context-Part-1-Alpha.md)
and in Spec #2 (XYZ-META-S01-01-Family.md). All citations retained.

## Section 3: Verbatim Block

Body Content runs from `First body line.` through `Last body line.`

First body line.
Second body line.
Third body line.
Last body line.

## Section 4: Repoint Map

| Line | Cluster | Target |
|---|---|---|
| line 10 | §4.2.1-4.2.3 | §4.2.1 |
| line 20 | §4.2.1-4.2.3 | §4.2.2 |
| line 30 | §4.2.1-4.2.3 | §4.2.3 |

## Section 5: Repair

Repoint the citations in `ref-a.md` and `ref-b.md`.

## Section 6: Verification Sweep

Confirm `ref-a.md` and `ref-b.md` hold no dangling citation.

## Cross-References

| Section | Source | Source Section(s) |
|---|---|---|
| §2 | Spec #1 (XYZ-Consolidated-Context-Part-1-Alpha.md) | § Rules |
| §2 | Spec #2 (XYZ-META-S01-01-Family.md) | § Rules |
"""

SPRINT_PLAN = """# XYZ Sprint 02 Plan

**Estimated Tokens:** ~100K total across all sessions

## Objective

Ship the demo cache tooling.

## Sessions

| Session | ID | Name | Objective | Est. Tokens |
|---|---|---|---|---|
| 1 | XYZ-S02-01 | Alpha | ship the cache tooling | ~100K |

The EI total is 5,000 tokens.

## Write-Set

| Path | Task |
|---|---|
| `tests/test_shared.py` | XYZ-S02-01-01 |

## Cross-Sprint File Touches

| File | Co-Writer Task | Co-Writer Delta Marker (content anchor) | Ordering | This Sprint Adds |
|---|---|---|---|---|
| `tests/test_shared.py` | XYZ-S01-02-04 | `SHARED = {` | prior | XYZ-S02-01-01 removes 1 entry |
"""

ORCHESTRATION = """# XYZ Session 01 Orchestration

**Total Estimated:** ~100K tokens (60 + 40)

## Success Criteria

- [ ] The cache tooling ships.
"""

TASK_ONE = """# Task: First

**Task ID:** XYZ-S02-01-01
**Estimated Tokens:** ~60K

## Execution Steps

1. Grep `tests/test_shared.py` for `SHARED = {` before the first edit.
2. Copy verbatim from EI §3 into the new file.
3. Docstring requirement: the helper cites Spec #1 and Spec #2 verbatim.
4. Grep the module for the Spec #1 and Spec #2 tokens.
5. The test fixture comment restates Spec #1 and Spec #2.

## Success Criteria

- [ ] The new file holds ~4-5 lines (5 total - 1 trailing blank line).
  The band is a signal, not a target.
"""

TASK_TWO = """# Task: Second

**Task ID:** XYZ-S02-01-02
**Estimated Tokens:** ~40K

## Expected Output

The anchor lands at ~338-340 lines (472 total - 134 extracted: lines 99-147 = 49, 186-270 = 85).
The band is a signal, not a target.
"""

SIGNOFF = """# XYZ Sprint 02 Signoff

- [ ] The cross-tier citations Spec #1 and Spec #2 pass the signoff grep.
"""

AUDIT = """# XYZ Sprint 02 Audit Record

## Audit Range Table

| Cluster | Cited lines |
|---|---|
| §4.2.1-4.2.3 | `ref.md:10`, `ref.md:20`, `ref.md:30` |

## Audit Grep Table

| File | Hits |
|---|---|
| `ref-a.md` | 2 |
| `ref-b.md` | 1 |
"""

CONSOLIDATED = """# XYZ Consolidated Context Part 1: Alpha

**Driving Findings:** Alpha-Finding, Beta-Finding

---

## Rules

Alpha-Finding: every reader checks the cache first.

Beta-Finding: a stale entry is dropped on read.

## Cross-References

| Section | Source |
|---|---|
| Rules | Alpha-Finding §1; Gamma-Finding §2 [source-doc-only — see src/gamma.md] |
"""

KEYS = {
    "master": "plan/Exec-XYZ/XYZ-Master-Plan.md",
    "earlier": "plan/Exec-XYZ/Sprint-01-Base/XYZ-S01-Sprint-Plan.md",
    "part1": f"{SPRINT}/XYZ-S02-Execution-Input-Part-1-Header.md",
    "plan": f"{SPRINT}/XYZ-S02-Sprint-Plan.md",
    "signoff": f"{SPRINT}/Sprint-Signoff.md",
    "audit": f"{SPRINT}/XYZ-S02-Audit.md",
    "orch": f"{SESSION}/XYZ-S02-01-Orchestration.md",
    "task1": f"{SESSION}/XYZ-S02-01-01-Opus-First.md",
    "task2": f"{SESSION}/XYZ-S02-01-02-Sonnet-Second.md",
    "consolidated": "plan/Meta-XYZ/Outputs/XYZ-Consolidated-Context-Part-1-Alpha.md",
}

BASE = {
    "master": MASTER_PLAN,
    "earlier": EARLIER_PLAN,
    "part1": PART_1,
    "plan": SPRINT_PLAN,
    "signoff": SIGNOFF,
    "audit": AUDIT,
    "orch": ORCHESTRATION,
    "task1": TASK_ONE,
    "task2": TASK_TWO,
    "consolidated": CONSOLIDATED,
}


def build(tmp_path: Path, files: dict[str, str | None]) -> None:
    for key, text in files.items():
        if text is None:
            continue
        path = tmp_path / KEYS[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def edited(**changes: tuple[str, str] | None) -> dict[str, str | None]:
    """The base files with each named file's (old, new) replacement applied, or the file dropped."""
    files: dict[str, str | None] = dict(BASE)
    for key, change in changes.items():
        if change is None:
            files[key] = None
            continue
        old, new = change
        assert old in files[key], f"{old!r} not in {key}"
        files[key] = files[key].replace(old, new)
    return files


def run(tmp_path: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str | None], root: bool = True) -> tuple[int, str]:
    build(tmp_path, files)
    args = ["--sprint", str(tmp_path / SPRINT), "--master-plan", str(tmp_path / KEYS["master"])]
    if root:
        args += ["--plan-root", str(tmp_path / "plan")]
    code = lint.main(args)
    return code, capsys.readouterr().out


def findings(out: str, word: str | None = None) -> list[str]:
    lines = [line for line in out.splitlines() if line.split(" ", 1)[0] in {"BLOCKER", "WARNING"}]
    return [line for line in lines if word is None or line.split(" ")[1] == word]


def subject_line(out: str, word: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(f"{word}: ") and "subject(s)" in line)


# --------------------------------------------------------------------------- registration and base


def test_registration_adds_the_ten_word_ids_after_the_core_eight():
    words = [rule.word for rule in lint.RULES]
    assert len(words) == 18
    assert words[8:] == plan_rules.WORDS
    assert words[8:] == [
        "threshold-alignment",
        "cross-tier-propagation",
        "token-reconciliation",
        "verbatim-line-range",
        "size-band-derivation",
        "cross-sprint-touch",
        "repoint-cluster",
        "repair-covers-verify",
        "body-citation-presence",
        "pre-extraction-step",
    ]


def test_base_fixture_is_clean_and_every_rule_sees_a_subject(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited())
    assert code == 0, out
    assert findings(out) == []
    assert out.splitlines()[0] == "1 EI Parts read, 18 rules run"
    for word in plan_rules.WORDS:
        assert "0 subject(s)" not in subject_line(out, word), out


def test_fresh_interpreter_run_prints_eighteen_rules_first(tmp_path):
    build(tmp_path, edited())
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPTS / "lint_execution_input.py"),
            "--sprint",
            str(tmp_path / SPRINT),
            "--master-plan",
            str(tmp_path / KEYS["master"]),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.stdout.splitlines()[0] == "1 EI Parts read, 18 rules run", proc.stderr
    assert proc.stderr == ""
    assert proc.returncode == 0, proc.stdout


def test_missing_plan_module_exits_3_at_run_time(tmp_path):
    """The core and its reader copied without the plan module: the import succeeds, the run exits 3."""
    build(tmp_path, edited())
    alone = tmp_path / "scripts-alone"
    alone.mkdir()
    for name in ("lint_execution_input.py", "markdown_parser.py"):
        (alone / name).write_bytes((SCRIPTS / name).read_bytes())
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            str(alone / "lint_execution_input.py"),
            "--sprint",
            str(tmp_path / SPRINT),
            "--master-plan",
            str(tmp_path / KEYS["master"]),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert proc.stdout.splitlines()[0] == "1 EI Parts read, 9 rules run"
    assert "cannot import a sibling module" in proc.stderr
    assert "Traceback" not in proc.stderr


# --------------------------------------------------------------------------- threshold-alignment


def test_threshold_alignment_fires_above_ten_percent(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(part1=("| XYZ-S02-01 | ~100K |", "| XYZ-S02-01 | ~150K |")))
    assert code == 1
    assert len(findings(out, "threshold-alignment")) == 2  # the Sessions row and the Orchestration total


def test_threshold_alignment_within_ten_percent_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(part1=("| XYZ-S02-01 | ~100K |", "| XYZ-S02-01 | ~108K |")))
    assert code == 0, out
    assert findings(out, "threshold-alignment") == []
    assert "threshold-alignment: 1 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- cross-tier-propagation


@pytest.mark.parametrize(
    ("key", "old", "new", "surface"),
    [
        ("task1", "3. Docstring requirement:", "3. Requirement:", "docstring requirement"),
        ("task1", "4. Grep the module", "4. Search the module", "citation-token grep"),
        ("task1", "test fixture comment", "test comment", "fixture comment"),
        ("signoff", "Spec #1 and Spec #2 pass", "pass", "signoff line"),
    ],
)
def test_cross_tier_propagation_fires_on_each_missing_surface(tmp_path, capsys, key, old, new, surface):
    code, out = run(tmp_path, capsys, edited(**{key: (old, new)}))
    assert code == 1
    lines = findings(out, "cross-tier-propagation")
    assert len(lines) == 1 and surface in lines[0], out


def test_cross_tier_propagation_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "cross-tier-propagation: 1 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- token-reconciliation


def test_token_reconciliation_fires_on_ei_total_deviation(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=("The EI total is 5,000 tokens.", "The EI total is 8,000 tokens.")))
    assert code == 1
    lines = findings(out, "token-reconciliation")
    assert len(lines) == 1 and "EI total 5K" in lines[0], out


def test_token_reconciliation_fires_on_task_sums_that_disagree(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(task1=("~60K", "~70K")))
    assert code == 1
    lines = findings(out, "token-reconciliation")
    assert len(lines) == 1 and "sum to 110K" in lines[0], out


def test_token_reconciliation_fires_on_sprint_total(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=("~100K total across", "~120K total across")))
    assert code == 1
    assert len(findings(out, "token-reconciliation")) == 1


def test_token_reconciliation_repaired_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=("The EI total is 5,000 tokens.", "The EI total is 5,400 tokens.")))
    assert code == 0, out
    assert "token-reconciliation: 3 subject(s), 0 finding(s)" in out


def test_token_reconciliation_without_a_plan_ei_total_is_no_subject(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=("The EI total is 5,000 tokens.", "")))
    assert code == 0, out
    assert "token-reconciliation: no subject for the EI total: the Sprint Plan states no EI token total" in out
    assert findings(out, "token-reconciliation") == []


def test_token_reconciliation_ignores_a_sprint_figure_of_another_kind(tmp_path, capsys):
    """A line naming the EI and a plan total is not an EI total (the real-run false match)."""
    other_kind = "EI Part 3 sections were measured, so the plan total reads ~100K."
    code, out = run(tmp_path, capsys, edited(plan=("The EI total is 5,000 tokens.", other_kind)))
    assert code == 0, out
    assert "the Sprint Plan states no EI token total" in out


# --------------------------------------------------------------------------- verbatim-line-range


def test_verbatim_line_range_fires_without_body_delimiters(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(part1=("Body Content runs from `First body line.` through `Last body line.`\n", "")))
    assert code == 1
    lines = findings(out, "verbatim-line-range")
    assert len(lines) == 1 and "no body delimiters" in lines[0], out


def test_verbatim_line_range_fires_on_a_section_length_range(tmp_path, capsys):
    section = next(
        (start, end) for _l, title, start, end in lint.sections(PART_1.splitlines()) if title.startswith("Section 3")
    )
    length = section[1] - section[0]
    code, out = run(tmp_path, capsys, edited(task1=("~4-5 lines", f"~{length}-{length} lines")))
    assert code == 1
    lines = findings(out, "verbatim-line-range")
    assert len(lines) == 1 and "not its 4-line body block" in lines[0], out


def test_verbatim_line_range_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "verbatim-line-range: 1 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- size-band-derivation


@pytest.mark.parametrize(
    ("old", "new", "problem"),
    [
        ("The band is a signal, not a target.", "Hit the band.", "no signal-not-target clause"),
        ("(472 total - 134 extracted: lines 99-147 = 49, 186-270 = 85)", "(measured)", "no inline derivation"),
        ("99-147 = 49", "99-147 = 50", "states 50, measures 49"),
        ("472 total - 134", "472 total - 140", "the spans sum to 134"),
    ],
)
def test_size_band_derivation_warns(tmp_path, capsys, old, new, problem):
    code, out = run(tmp_path, capsys, edited(task2=(old, new)))
    assert code == 2, out
    lines = findings(out, "size-band-derivation")
    assert len(lines) == 1 and lines[0].startswith("WARNING ") and problem in lines[0], out


def test_size_band_derivation_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "size-band-derivation: 2 subject(s), 0 finding(s)" in out  # task 2's band and task 1's range


# --------------------------------------------------------------------------- cross-sprint-touch

TOUCH_ROW = "| `tests/test_shared.py` | XYZ-S01-02-04 | `SHARED = {` | prior | XYZ-S02-01-01 removes 1 entry |\n"


def test_cross_sprint_touch_fires_without_the_touch_row(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=(TOUCH_ROW, "")))
    assert code == 1
    lines = findings(out, "cross-sprint-touch")
    assert len(lines) == 1 and "no Cross-Sprint File Touches row" in lines[0], out


def test_cross_sprint_touch_fires_without_a_step_one_gate(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(task1=("1. Grep `tests/test_shared.py`", "1. Open `tests/test_shared.py`")))
    assert code == 1
    lines = findings(out, "cross-sprint-touch")
    assert len(lines) == 1 and "no Step-1 grep gate" in lines[0], out


def test_cross_sprint_touch_fires_on_an_unordered_pair_without_the_row(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(plan=("| prior |", "| unordered |")))
    assert code == 1
    lines = findings(out, "cross-sprint-touch")
    assert len(lines) == 1 and "MUST NOT run concurrently" in lines[0], out


def test_cross_sprint_touch_unordered_pair_with_the_row_is_clean(tmp_path, capsys):
    files = edited(
        plan=("| prior |", "| unordered |"),
        master=("Sprint-02 follows Sprint-01.", "| Sprint-01 | Sprint-02 | MUST NOT run concurrently (shared file: `tests/test_shared.py`) |"),
    )
    code, out = run(tmp_path, capsys, files)
    assert code == 0, out
    assert "cross-sprint-touch: 1 subject(s), 0 finding(s)" in out


def test_cross_sprint_touch_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "cross-sprint-touch: 1 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- repoint-cluster


def test_repoint_cluster_fires_on_a_short_map(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(part1=("| line 30 | §4.2.1-4.2.3 | §4.2.3 |\n", "")))
    assert code == 1
    lines = findings(out, "repoint-cluster")
    assert len(lines) == 1 and "cites 3 line(s), the EI repoint map holds 2 row(s)" in lines[0], out


def test_repoint_cluster_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "repoint-cluster: 1 subject(s), 0 finding(s)" in out


def test_repoint_cluster_without_an_audit_table_is_no_subject(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(audit=None, part1=("| line 30 | §4.2.1-4.2.3 | §4.2.3 |\n", "")))
    assert code == 0, out
    assert "repoint-cluster: no subject: no audit range table in the sprint" in out
    assert "repoint-cluster: 0 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- repair-covers-verify


def test_repair_covers_verify_fires_on_a_verified_unrepaired_file(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(part1=("Repoint the citations in `ref-a.md` and `ref-b.md`.", "Repoint the citations in `ref-a.md`.")))
    assert code == 1
    lines = findings(out, "repair-covers-verify")
    assert len(lines) == 1 and "ref-b.md is in a verification section" in lines[0], out


def test_repair_covers_verify_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "repair-covers-verify: 4 subject(s), 0 finding(s)" in out


def test_repair_covers_verify_without_an_audit_table_is_no_subject(tmp_path, capsys):
    files = edited(audit=None, part1=("Repoint the citations in `ref-a.md` and `ref-b.md`.", "Repoint the citations in `ref-a.md`."))
    code, out = run(tmp_path, capsys, files)
    assert "repair-covers-verify: no subject: no audit grep table in the sprint" in out
    assert findings(out, "repair-covers-verify") == []
    assert code == 0, out


# --------------------------------------------------------------------------- body-citation-presence


def test_body_citation_presence_fires_on_an_unmarked_absence(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(consolidated=(" [source-doc-only — see src/gamma.md]", "")))
    assert code == 1
    lines = findings(out, "body-citation-presence")
    assert len(lines) == 1 and "'Gamma-Finding'" in lines[0], out


def test_body_citation_presence_fires_on_a_driving_finding_without_prose(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(consolidated=("Alpha-Finding, Beta-Finding", "Alpha-Finding, Delta-Finding")))
    assert code == 1
    lines = findings(out, "body-citation-presence")
    assert len(lines) == 1 and "'Delta-Finding'" in lines[0], out


def test_body_citation_presence_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "body-citation-presence: 4 subject(s), 0 finding(s)" in out


def test_body_citation_presence_without_a_root_is_skipped(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(consolidated=(" [source-doc-only — see src/gamma.md]", "")), root=False)
    assert code == 0, out
    assert "body-citation-presence: skipped: no source root" in out
    assert "body-citation-presence: 0 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- pre-extraction-step

ABSENT_STEP = ("2. Copy verbatim from EI §3 into the new file.", "2. Extract verbatim the rule text of §9 into the new file.")


def test_pre_extraction_step_fires_on_an_absent_section(tmp_path, capsys):
    code, out = run(tmp_path, capsys, edited(task1=ABSENT_STEP))
    assert code == 1
    lines = findings(out, "pre-extraction-step")
    assert len(lines) == 1 and lines[0].startswith("BLOCKER ") and "§9 is absent" in lines[0], out


def test_pre_extraction_step_warns_when_the_task_is_verification_aware(tmp_path, capsys):
    aware = (ABSENT_STEP[0], ABSENT_STEP[1] + " Run the pre-extraction check first.")
    code, out = run(tmp_path, capsys, edited(task1=aware))
    assert code == 2, out
    lines = findings(out, "pre-extraction-step")
    assert len(lines) == 1 and lines[0].startswith("WARNING ") and "verification-aware" in lines[0], out


def test_pre_extraction_step_repaired_is_clean(tmp_path, capsys):
    _code, out = run(tmp_path, capsys, edited())
    assert "pre-extraction-step: 1 subject(s), 0 finding(s)" in out


def test_pre_extraction_step_tests_existence_only(tmp_path, capsys):
    """A present section passes even when it carries none of the cited prose."""
    files = edited(task1=("2. Copy verbatim from EI §3 into", "2. Extract verbatim the eviction table of §2 into"))
    code, out = run(tmp_path, capsys, files)
    assert code == 0, out
    assert findings(out, "pre-extraction-step") == []
    assert "pre-extraction-step: 1 subject(s), 0 finding(s)" in out
