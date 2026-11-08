"""Tests for scripts/lint_execution_input.py.

Each rule has a fixture EI with the rule broken that produces the rule's exit
contract, and the same fixture repaired that exits 0 with no finding of that
rule. Fixtures are built under tmp_path. The base fixture is clean on all rules.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_execution_input as lint

SCRIPT = SCRIPTS / "lint_execution_input.py"

PART_1 = """# Demo Execution Input — Part 1: Header

**Sprint:** DEMO-S09
**Extracted from:** Spec #1 (Alpha-Source.md) [Tier 2], Spec #2 (Beta-Source.md) [Tier 1 raw]
**Tier 3: none produced.**
**Retention: 97 %** over the Tier 1 and Tier 2 source.

---

## Severity Vocabulary

| Tag | Meaning |
|---|---|
| `[WARNING]` | a warning the source raised |

## Section 1: Findings

The parser reads the `cache_key` input. [WARNING] applies to the cache.

**Note (cross-tier duplicate preserved):** This finding is cited in Spec #1 (Alpha-Source.md)
and in Spec #2 (Beta-Source.md). All citations retained.

## Data Quality Caveats

Nothing is caveated yet.

## Cross-References

| Section | Source | Source Section(s) |
|---|---|---|
| §1 | Spec #1 (Alpha-Source.md) | § Findings |
| §1 | Spec #2 (Beta-Source.md) | § Findings |
"""

PART_2 = """# Demo Execution Input — Part 2: More

## Section 2: More Findings

The second Part carries body text only.
"""

MASTER_PLAN = """# Demo Master Plan

## Global Source Map

The map lives in Part 2.
"""

MAP_PART_2 = """# Demo Master Plan — Part 2: Global Source Map

## Global Source Map

| # | Tier | Source File | ~Tokens |
|---|---|---|---|
| 1 | T2 | `Alpha-Source.md` | 100 |
| 2 | T1 | `…Beta-Source.md` | 100 |
| 3 | T1 | `Gamma-Source.md` | 100 |
"""

SPRINT_PLAN = """# Demo Sprint Plan

## Objective

Ship the demo cache tooling.

## Sessions

None yet.
"""

ORCHESTRATION = """# Demo Orchestration

## Success Criteria

- [ ] The cache tooling ships.
"""

TASK_FILE = """# Task: Demo

## Required Context

| Priority | File |
|---|---|
| 1 | the EI |

## Execution Steps

1. Docstring requirement: the cache helper cites Spec #1 and Spec #2 verbatim.
2. Grep the module for the Spec #1 and Spec #2 tokens.
3. The test fixture comment restates Spec #1 and Spec #2.

## Success Criteria

- [ ] The tool runs.
"""

SIGNOFF = """# Demo Sprint Signoff

- [ ] The cross-tier citations Spec #1 and Spec #2 pass the signoff grep.
"""

SOURCE_ALPHA = """# Alpha Source

The cache evicts entries on a schedule the owner sets.
"""


def build(tmp_path: Path, **overrides: str) -> tuple[Path, Path]:
    """Write a sprint folder and a Master Plan; return (sprint, master plan)."""
    files = {
        "plan/DEMO-Master-Plan.md": MASTER_PLAN,
        "plan/DEMO-Master-Plan-Part-2-GlobalSourceMap.md": MAP_PART_2,
        "plan/sprint/DEMO-S09-Sprint-Plan.md": SPRINT_PLAN,
        "plan/sprint/DEMO-S09-Execution-Input-Part-1-Header.md": PART_1,
        "plan/sprint/DEMO-S09-Execution-Input-Part-2-More.md": PART_2,
        "plan/sprint/Session-01-Demo/DEMO-S09-01-Orchestration.md": ORCHESTRATION,
        "plan/sprint/Session-01-Demo/DEMO-S09-01-01-Sonnet-Demo.md": TASK_FILE,
        "plan/sprint/Sprint-Signoff.md": SIGNOFF,
        "plan/sources/Alpha-Source.md": SOURCE_ALPHA,
        "plan/sources/Beta-Source.md": "# Beta Source\n\nPlain text.\n",
    }
    files.update({key.replace("__", "/"): value for key, value in overrides.items()})
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return tmp_path / "plan" / "sprint", tmp_path / "plan" / "DEMO-Master-Plan.md"


PART_1_KEY = "plan__sprint__DEMO-S09-Execution-Input-Part-1-Header.md"
PART_2_KEY = "plan__sprint__DEMO-S09-Execution-Input-Part-2-More.md"
TASK_KEY = "plan__sprint__Session-01-Demo__DEMO-S09-01-01-Sonnet-Demo.md"
ORCH_KEY = "plan__sprint__Session-01-Demo__DEMO-S09-01-Orchestration.md"
PLAN_KEY = "plan__sprint__DEMO-S09-Sprint-Plan.md"


def run(tmp_path: Path, capsys: pytest.CaptureFixture[str], *extra: str, **overrides: str) -> tuple[int, str]:
    sprint, master = build(tmp_path, **overrides)
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master), *extra])
    return code, capsys.readouterr().out


def finding_lines(out: str, word: str) -> list[str]:
    return [line for line in out.splitlines() if f" {word} " in line and line.split(" ", 1)[0] in {"BLOCKER", "WARNING", "ADVISORY"}]


def all_findings(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.split(" ", 1)[0] in {"BLOCKER", "WARNING", "ADVISORY"}]


# --------------------------------------------------------------------------- base and counts


def test_base_fixture_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys)
    assert code == 0, out
    assert all_findings(out) == []


def test_first_line_names_the_part_count(tmp_path, capsys):
    _code, out = run(tmp_path, capsys)
    assert out.splitlines()[0] == f"2 EI Parts read, {len(lint.RULES)} rules run"
    for rule in lint.RULES:
        assert any(line.startswith(f"{rule.word}: ") and "subject(s)" in line for line in out.splitlines())


def test_rules_list_holds_the_eight_word_ids():
    assert [rule.word for rule in lint.RULES][:8] == [
        "severity-vocabulary",
        "retention-band-class",
        "four-site-caveat",
        "hedge-preservation",
        "cross-tier-note",
        "retention-threshold",
        "spec-citation-pair",
        "count-claim",
    ]


# --------------------------------------------------------------------------- Part-set reader


def test_parts_two_onward_need_no_header(tmp_path, capsys):
    """Part 2 has no Extracted from or Retention line, and its tag is covered by Part 1's heading."""
    part_2 = PART_2 + "\nA [WARNING] tag sits in Part 2.\n\n**Retention: 10 %** is not a header here.\n"
    code, out = run(tmp_path, capsys, **{PART_2_KEY: part_2})
    assert code == 0, out
    assert all_findings(out) == []


def test_part_order_is_numeric(tmp_path):
    sprint, _master = build(
        tmp_path,
        **{"plan__sprint__DEMO-S09-Execution-Input-Part-10-Late.md": "# Late\n\nText.\n"},
    )
    parts = lint.discover_parts(sprint)["DEMO-S09"]
    assert [num for num, _path in sorted(parts)] == [1, 2, 10]


def test_single_file_ei_is_part_one(tmp_path, capsys):
    sprint, master = build(tmp_path)
    (sprint / "DEMO-S09-Execution-Input-Part-2-More.md").unlink()
    (sprint / "DEMO-S09-Execution-Input-Part-1-Header.md").rename(sprint / "DEMO-S09-Execution-Input.md")
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master)])
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("1 EI Parts read")
    assert code == 0, out


# --------------------------------------------------------------------------- exit 3


def test_no_ei_part_found_exits_3(tmp_path, capsys):
    sprint, master = build(tmp_path)
    for path in sprint.glob("*-Execution-Input-*.md"):
        path.unlink()
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master)])
    captured = capsys.readouterr()
    assert code == 3
    assert captured.out.splitlines()[0] == f"0 EI Parts read, {len(lint.RULES)} rules run"
    assert "no *-Execution-Input" in captured.err


def test_unreadable_master_plan_exits_3(tmp_path, capsys):
    sprint, _master = build(tmp_path)
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(tmp_path / "missing.md")])
    assert code == 3
    assert "cannot read" in capsys.readouterr().err


def test_undecodable_part_exits_3(tmp_path, capsys):
    sprint, master = build(tmp_path)
    (sprint / "DEMO-S09-Execution-Input-Part-2-More.md").write_bytes(b"# Part 2\n\n\xff\xfe bad bytes\n")
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master)])
    assert code == 3
    assert "cannot read" in capsys.readouterr().err


def test_empty_source_map_exits_3(tmp_path, capsys):
    sprint, master = build(tmp_path, **{"plan__DEMO-Master-Plan-Part-2-GlobalSourceMap.md": "# Part 2\n"})
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master)])
    assert code == 3
    assert "no Global Source Map entries" in capsys.readouterr().err


def test_missing_master_plan_argument_exits_3(tmp_path, capsys):
    sprint, _master = build(tmp_path)
    assert lint.main(["--sprint", str(sprint)]) == 3


# --------------------------------------------------------------------------- severity-vocabulary (exit 1)


def test_severity_vocabulary_fires_without_the_heading(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **{PART_1_KEY: PART_1.replace("## Severity Vocabulary", "## Tags")})
    assert code == 1
    assert len(finding_lines(out, "severity-vocabulary")) == 1
    assert all_findings(out) == finding_lines(out, "severity-vocabulary")


def test_severity_vocabulary_repaired_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys)
    assert code == 0
    assert finding_lines(out, "severity-vocabulary") == []


# --------------------------------------------------------------------------- retention-band-class (exit 1)

GENERIC_HEADER = PART_1.replace(
    "**Tier 3: none produced.**", "**Tier 3: none produced.**\n**Band:** the generic 80–120 % retention band."
)
ALGORITHM_HEADER = PART_1.replace(
    "**Tier 3: none produced.**", "**Tier 3: none produced.**\n**Band:** the 95–120 % algorithm band."
)
ALGORITHM_PLAN = SPRINT_PLAN.replace("Ship the demo cache tooling.", "Design the ranking algorithm.")


def test_retention_band_class_fires_on_generic_band(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **{PART_1_KEY: GENERIC_HEADER, PLAN_KEY: ALGORITHM_PLAN})
    assert code == 1
    assert len(finding_lines(out, "retention-band-class")) == 1
    assert all_findings(out) == finding_lines(out, "retention-band-class")


def test_retention_band_class_repaired_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **{PART_1_KEY: ALGORITHM_HEADER, PLAN_KEY: ALGORITHM_PLAN})
    assert code == 0, out
    assert all_findings(out) == []


def test_retention_band_class_ignores_generic_band_without_keyword(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **{PART_1_KEY: GENERIC_HEADER})
    assert code == 0, out


# --------------------------------------------------------------------------- four-site-caveat (exit 1)

CLAIM = "\nThe `api_flag` field is UNCONFIRMED — not in the response.\n"
PART_1_CLAIM = PART_1.replace("## Data Quality Caveats", CLAIM + "\n## Data Quality Caveats")
PART_1_CLAIM_REPAIRED = PART_1_CLAIM.replace(
    "Nothing is caveated yet.", "`api_flag` is UNCONFIRMED: do not ship it."
)
ORCH_SITE = ORCHESTRATION + "- [ ] The schema omits `api_flag`.\n"
TASK_SITE = TASK_FILE + "- [ ] `api_flag` stays out of the schema.\n"
FOUR_SITES = {PART_1_KEY: PART_1_CLAIM_REPAIRED, ORCH_KEY: ORCH_SITE, TASK_KEY: TASK_SITE}


@pytest.mark.parametrize(
    ("broken", "missing"),
    [
        ({PART_1_KEY: PART_1_CLAIM}, "EI Data Quality Caveats"),
        ({ORCH_KEY: ORCHESTRATION}, "Orchestration success criterion"),
        ({TASK_KEY: TASK_FILE}, "task file Required Context or Success Criteria"),
    ],
)
def test_four_site_caveat_fires_on_each_missing_site(tmp_path, capsys, broken, missing):
    code, out = run(tmp_path, capsys, **{**FOUR_SITES, **broken})
    assert code == 1
    lines = finding_lines(out, "four-site-caveat")
    assert len(lines) == 1 and missing in lines[0] and "api_flag" in lines[0]
    assert all_findings(out) == lines


def test_four_site_caveat_repaired_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **FOUR_SITES)
    assert code == 0, out
    assert all_findings(out) == []
    assert "four-site-caveat: 2 subject(s), 0 finding(s)" in out


def test_four_site_caveat_fires_on_practice_callout(tmp_path, capsys):
    callout = "\n> [!practice] Caveat\n> The `api_flag` field is UNCONFIRMED.\n"
    part = PART_1_CLAIM_REPAIRED.replace("## Data Quality Caveats", callout + "\n## Data Quality Caveats")
    code, out = run(tmp_path, capsys, **{**FOUR_SITES, PART_1_KEY: part})
    assert code == 1
    lines = finding_lines(out, "four-site-caveat")
    assert len(lines) == 1 and "[!practice]" in lines[0]


def test_four_site_caveat_constraint_callout_is_clean(tmp_path, capsys):
    callout = "\n> [!constraint] Caveat\n> The `api_flag` field is UNCONFIRMED.\n"
    part = PART_1_CLAIM_REPAIRED.replace("## Data Quality Caveats", callout + "\n## Data Quality Caveats")
    code, out = run(tmp_path, capsys, **{**FOUR_SITES, PART_1_KEY: part})
    assert code == 0, out


def test_four_site_caveat_skips_mentions(tmp_path, capsys):
    mention = "\nPlace each UNCONFIRMED caveat at four sites, and never cite `UNCONFIRMED` as a claim.\n"
    part = PART_1.replace("## Data Quality Caveats", mention + "\n## Data Quality Caveats")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 0, out
    assert "four-site-caveat: 0 subject(s)" in out


# --------------------------------------------------------------------------- hedge-preservation (advisory, exit 0)

HEDGED_SOURCE = "# Alpha Source\n\nThe cache most likely evicts stale entries after ninety seconds of idle time.\n"
FLAT_EI = PART_1.replace(
    "## Data Quality Caveats",
    "The cache evicts stale entries after ninety seconds of idle time.\n\n## Data Quality Caveats",
)
HEDGED_EI = PART_1.replace(
    "## Data Quality Caveats",
    "The cache most likely evicts stale entries after ninety seconds of idle time.\n\n## Data Quality Caveats",
)


def _plan_root(tmp_path: Path) -> str:
    return str(tmp_path / "plan" / "sources")


def test_hedge_preservation_prints_candidate_and_exits_0(tmp_path, capsys):
    sprint, master = build(tmp_path, **{"plan__sources__Alpha-Source.md": HEDGED_SOURCE, PART_1_KEY: FLAT_EI})
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master), "--plan-root", _plan_root(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    lines = finding_lines(out, "hedge-preservation")
    assert len(lines) == 1 and lines[0].startswith("ADVISORY") and "most likely" in lines[0]


def test_hedge_preservation_repaired_has_no_candidate(tmp_path, capsys):
    sprint, master = build(tmp_path, **{"plan__sources__Alpha-Source.md": HEDGED_SOURCE, PART_1_KEY: HEDGED_EI})
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master), "--plan-root", _plan_root(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert all_findings(out) == []
    assert "hedge-preservation: 1 subject(s), 0 finding(s)" in out


def test_hedge_preservation_dated_measurement_resolves(tmp_path, capsys):
    resolved = FLAT_EI.replace("idle time.", "idle time (measured 2026-01-05).")
    sprint, master = build(tmp_path, **{"plan__sources__Alpha-Source.md": HEDGED_SOURCE, PART_1_KEY: resolved})
    code = lint.main(["--sprint", str(sprint), "--master-plan", str(master), "--plan-root", _plan_root(tmp_path)])
    assert code == 0
    assert all_findings(capsys.readouterr().out) == []


def test_hedge_preservation_skips_without_root(tmp_path, capsys):
    code, out = run(tmp_path, capsys, **{"plan__sources__Alpha-Source.md": HEDGED_SOURCE, PART_1_KEY: FLAT_EI})
    assert code == 0
    assert "hedge-preservation: skipped: no source root" in out


# --------------------------------------------------------------------------- cross-tier-note (exit 1)


def test_cross_tier_note_fires_without_the_note(tmp_path, capsys):
    part = PART_1.replace("**Note (cross-tier duplicate preserved):**", "**Note:**")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 1
    lines = finding_lines(out, "cross-tier-note")
    assert len(lines) == 1 and "Spec #1, Spec #2" in lines[0]
    assert all_findings(out) == lines


def test_cross_tier_note_fires_when_note_omits_a_source(tmp_path, capsys):
    part = PART_1.replace("\nand in Spec #2 (Beta-Source.md).", ".")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 1
    assert len(finding_lines(out, "cross-tier-note")) == 1


def test_cross_tier_note_repaired_is_clean(tmp_path, capsys):
    code, out = run(tmp_path, capsys)
    assert code == 0
    assert "cross-tier-note: 1 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- retention-threshold (0, 2, 1)


@pytest.mark.parametrize(
    ("figure", "code", "severity"),
    [("90 %", 2, "WARNING"), ("80 %", 2, "WARNING"), ("79 %", 1, "BLOCKER"), ("70 %", 1, "BLOCKER")],
)
def test_retention_threshold_bands(tmp_path, capsys, figure, code, severity):
    part = PART_1.replace("**Retention: 97 %**", f"**Retention: {figure}**")
    got, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert got == code
    lines = finding_lines(out, "retention-threshold")
    assert len(lines) == 1 and lines[0].startswith(severity)
    assert all_findings(out) == lines


@pytest.mark.parametrize("figure", ["95 %", "97 %", "120 %"])
def test_retention_threshold_repaired_is_clean(tmp_path, capsys, figure):
    part = PART_1.replace("**Retention: 97 %**", f"**Retention: {figure}**")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 0
    assert finding_lines(out, "retention-threshold") == []


def test_retention_threshold_above_band_is_advisory(tmp_path, capsys):
    part = PART_1.replace("**Retention: 97 %**", "**Retention: 147 %**")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 0
    lines = finding_lines(out, "retention-threshold")
    assert len(lines) == 1 and lines[0].startswith("ADVISORY")


def test_retention_threshold_missing_line_warns(tmp_path, capsys):
    part = PART_1.replace("**Retention: 97 %** over the Tier 1 and Tier 2 source.\n", "")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 2
    assert "no 'Retention:' line" in out


# --------------------------------------------------------------------------- spec-citation-pair (exit 1)


@pytest.mark.parametrize(
    "broken",
    [
        "| §1 | Spec #2 (Alpha-Source.md) | § Findings |",  # number paired with the wrong file
        "| §1 | Spec #9 (Alpha-Source.md) | § Findings |",  # number absent from the map
        "| §1 | Spec #2 | § Findings |",  # bare token
    ],
)
def test_spec_citation_pair_fires(tmp_path, capsys, broken):
    part = PART_1.replace("| §1 | Spec #2 (Beta-Source.md) | § Findings |", broken)
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 1
    assert len(finding_lines(out, "spec-citation-pair")) == 1


def test_spec_citation_pair_fires_on_extracted_from_line(tmp_path, capsys):
    part = PART_1.replace("Spec #2 (Beta-Source.md) [Tier 1 raw]", "Spec #3 (Beta-Source.md) [Tier 1 raw]")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 1
    lines = finding_lines(out, "spec-citation-pair")
    assert len(lines) == 1 and ":4 " in lines[0]


def test_spec_citation_pair_repaired_is_clean(tmp_path, capsys):
    """The base resolves Spec #2 through the elided map name, read from the Part 2 sibling."""
    code, out = run(tmp_path, capsys)
    assert code == 0
    assert "spec-citation-pair: 4 subject(s), 0 finding(s)" in out


# --------------------------------------------------------------------------- count-claim (advisory, exit 0)


def test_count_claim_prints_candidate_and_exits_0(tmp_path, capsys):
    task = TASK_FILE + "\nRead columns 5 to 9 of the table.\n"
    code, out = run(tmp_path, capsys, **{TASK_KEY: task})
    assert code == 0
    lines = finding_lines(out, "count-claim")
    assert len(lines) == 1 and lines[0].startswith("ADVISORY") and "columns 5" in lines[0]


def test_count_claim_repaired_has_no_candidate(tmp_path, capsys):
    task = TASK_FILE + "\nRead columns 5 to 9 of the table (EI §2).\n"
    code, out = run(tmp_path, capsys, **{TASK_KEY: task})
    assert code == 0
    assert all_findings(out) == []
    assert "count-claim: 1 subject(s), 0 finding(s)" in out


def test_count_claim_inside_the_ei_is_not_a_candidate(tmp_path, capsys):
    part = PART_2 + "\nThe table has columns 5 to 9.\n"
    code, out = run(tmp_path, capsys, **{PART_2_KEY: part})
    assert code == 0
    assert finding_lines(out, "count-claim") == []


# --------------------------------------------------------------------------- aggregation and process


def test_blocker_outranks_warning(tmp_path, capsys):
    part = PART_1.replace("**Retention: 97 %**", "**Retention: 90 %**").replace("## Severity Vocabulary", "## Tags")
    code, out = run(tmp_path, capsys, **{PART_1_KEY: part})
    assert code == 1
    assert finding_lines(out, "retention-threshold") and finding_lines(out, "severity-vocabulary")


def test_fresh_interpreter_run_prints_count_first(tmp_path):
    sprint, master = build(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--sprint", str(sprint), "--master-plan", str(master)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.splitlines()[0] == f"2 EI Parts read, {len(lint.RULES)} rules run"
    assert proc.stderr == ""
