---
id: 617
title: "ZCU Task 03 criterion says three --report calls; the plans source its Step 1 allows runs two plus three other calls"
priority: Low
status: COMPLETE
abbrev: SCAF
created: 2026-10-14
blocks: []
route_hint: A
route_evidence: "Two sentences in one completed task file; the test already asserts the correct five calls"
route_dated: 2026-10-14
---

# BB-617-01-SCAF-ZcuTask03ReportCallCountCriterion: ZCU Task 03 criterion says three --report calls; the plans source its Step 1 allows runs two plus three other calls

**Priority:** Low
**Domain:** SCAF

---

## Summary

ZeroCallUpgrade task ZCU-S01-01-03 (BuildPreflight) contradicts itself about the plans call in the no-op proof. Step 1 lets the runner take the plans anomaly condition from either of two scripts:

- `migrate_plans_index.py --report`, which is a `--report` call;
- `generate_plans_index.py --check --json`, which is not.

Success Criterion 2 and one note still assume the first: they say the card's `debug:` line lists "the three `--report` calls". The runner chose the second script, because `migrate_plans_index.py --help` shows no anomaly line and its `--report` JSON has no anomalies key.

So the correct run lists two `--report` calls plus three other calls, five argv lists in all. Test 8 asserts exactly that and passes. The criterion as worded is unmet by correct work. A reviewer re-reading the completed task would read it as a miss.

## Problem

The task file's two sentences, quoted verbatim from `planwise/Plans/ZeroCallUpgrade/Sprint-01-BuildAndSandbox/Session-01-ScriptsAndSkill/ZCU-S01-01-03-Sonnet-BuildPreflight.md`:

- line 160 (Success Criteria): `- [ ] On the up-to-date fixture the card's `debug:` line lists the three `--report` calls, the `--questions` call and the lessons `--check` call`
- line 183 (Notes for Agent): `- The read-only proof on the pre-upgrade fixture stops at the first failing no-op condition, so none of the three `--report` subprocesses run there. Test 8 exists to cover that gap: only the up-to-date fixture reaches them. ...`

Step 1 of the same file (line 59) permits the alternative: "The plans anomaly condition comes from the `anomalies` key of `generate_plans_index.py --check --json`, or from an anomaly line of `migrate_plans_index.py --report` if `--help` shows that line exists (record which one you used in the status block)."

What test 8 asserts, verbatim from `skills_wip/zero-call-upgrade/tests/test_upgrade_preflight.py` lines 170-173:

```python
assert len(calls) == 5
assert flags == {("migrate_backlog_index.py", "--report"), ("migrate_lessons_index.py", "--report"),
                 ("generate_plans_index.py", "--json"), ("index_shape_preflight.py", "--questions"),
                 ("generate_lessons_index.py", "--json")}
```

**Evidence:** both task-file sentences are present. Verified 2026-10-14 by ``Grep pattern="three `--report`" path=planwise/Plans/ZeroCallUpgrade output_mode=content`` (hits at lines 160 and 183 of the Task 03 file).

**Evidence:** test 8 asserts five calls with two `--report` calls. Verified 2026-10-14 by `Grep pattern="def test_read_only_proof_up_to_date_runs_every_report" path=skills_wip/zero-call-upgrade/tests/test_upgrade_preflight.py -A 16`. The full suite passed with it (`38 passed in 581.75s`, ZCU-S01-01 closeout).

The ZCU-S01-01 Recovery Issues table and the session Summary record the defect as severity D and leave the plan unedited.

## Proposed Solution

Amend the two sentences so they cover both permitted sources. Keep each original sentence and mark the amendment, because the task is COMPLETE and its text is the record:

- line 160: "the card's `debug:` line lists the backlog and lessons `--report` calls, the plans call chosen in Step 1 (`migrate_plans_index.py --report` or `generate_plans_index.py --check --json`), the `--questions` call and the lessons `--check` call: five argv lists"
- line 183: "none of the `--report`, `--check` or `--questions` subprocesses run there"

Add a dated note naming the run's choice (`generate_plans_index.py --check --json`, ZCU-S01-01, 2026-10-14). Check the Design's card section and the Sprint-01 Orchestration for the same wording with a Grep, and amend any hit the same way.

## Acceptance Criteria

- [ ] ``Grep pattern="three `--report`" path=planwise/Plans/ZeroCallUpgrade`` returns 0 hits outside Recovery, Summary and Review records, which keep the historical wording
- [ ] The amended criterion is met by the recorded run: five argv lists, with the plans source named
- [ ] The amendment is dated and cites the ZCU-S01-01 run

## Related

- `planwise/Plans/ZeroCallUpgrade/Sprint-01-BuildAndSandbox/Session-01-ScriptsAndSkill/ZCU-S01-01-Recovery.md`: Issues row recording the defect.
- `skills_wip/zero-call-upgrade/tests/test_upgrade_preflight.py`: test 8, the executable form of the correct criterion.

---

*Created: 2026-10-14*
