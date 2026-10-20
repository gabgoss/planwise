---
id: 516
title: "Audit five plugin references for per-task whole-suite baseline guidance that the new §10.1.1 scope rule supersedes"
priority: Low
status: NOT_STARTED
abbrev: DOC
created: 2026-10-11
blocks: []
route_hint: A
route_evidence: "Read-and-classify over 5 files (~2,071 lines). A first pass at filing found no hit that teaches a per-task whole-suite baseline, so the likely outcome is zero or one small wording edit"
route_dated: 2026-10-11
---

# BB-516-DOC-AuditFiveReferencesForWholeSuiteBaselines: Audit five plugin references for per-task whole-suite baseline guidance that the new §10.1.1 scope rule supersedes

**Priority:** Low
**Domain:** DOC

---

## Summary

The ScopedGateBaselines plan (SGB, COMPLETE 2026-10-11, plugin commit `b5c199c`) wrote a scope rule for pre-edit measurement into the plugin. Its Master Plan scoped five other plugin references out and asked for this follow-up. This item reads all five and decides, per hit, whether any of them teaches a **per-task whole-suite baseline**. Any hit that does is brought in line with the new rule. Every other hit is recorded as unrelated.

Master Plan § Vision, verbatim:

> Out of scope, not reviewed: five other plugin files mention a whole-suite run (`discovery-and-exit-criteria.md`, `exit-criteria-fidelity.md`, `task-file-and-tracking-requirements.md`, `verification-gates.md`, `session-execution-protocol.md`). The plan review read one of them and found it unrelated. If a later read shows another teaches a per-task whole-suite baseline, file a backlog item for it. This plan does not widen its write-set.

The plan did not record which of the five the review read.

## Problem

### The rule the five files must agree with

`cloned-repos/planwise/plugins/planwise/references/gate-pre-edit-baseline.md`, `#### 10.1.1 Scope the measurement to the gate's population`, as shipped in `b5c199c`:

```markdown
A gate's population is the set of files its command reads. Measure the pre-edit value against that population and no wider one. A per-task gate names the task's own test module and lint paths. A whole-suite command costs minutes and moves for reasons outside the task.

Measure a whole-population baseline once per plan, before the first task file. Record it with its tree identity: the repo's `HEAD` sha and an empty `git status --porcelain` over the population's paths. A recorded value with a checked identity is a measurement, so it satisfies §10.1. Reuse it only in gates that run before any edit to that population. Re-check the identity at each dispatch and re-measure when it fails.

> [!constraint] One whole-population baseline per plan, one scoped measurement per task
> WRONG — every task runs the whole suite for its own baseline:
> ```bash
> {test-cmd}                           # minutes, repeated per task
> # pre-edit: 2590 passed → expect >= 2591 passed
> ```
> CORRECT — the task gate is scoped, and the whole-suite value is recorded once per plan:
> ```bash
> {test-cmd} tests/test_{module}.py
> # pre-edit: 41 passed → expect 43 passed
> ```
```

The same file (line 70) also states that `scripts/lint_verification_gates.py` Check 16 fires on a task file's Before or After `pytest` gate that names no path. `handlers/plan.md` Step 8e item 5 and `templates/task-file.md` now teach the same scope.

### What a first pass at filing found

Measured 2026-10-11 on the development tree at plugin `HEAD` `7a862c7`. Each search was a `Grep` with `-i` over `cloned-repos/planwise/plugins/planwise/references/`, with these two patterns:

```
whole[- ]suite|full[- ]suite|entire (test )?suite|whole[- ]repo
\bsuite\b|full test|all tests|\{test-cmd\}\s*($|[`#|])
```

| File | Lines | Hits | First-pass reading (not a verdict) |
|---|---:|---|---|
| `discovery-and-exit-criteria.md` | 212 | :77 "Discovery outputs citing counts MUST also cite the underlying execution (e.g., `{lint-cmd}` / `{test-cmd}` / SQL query / Glob pattern)." | Cites the command behind a count. Says nothing about scope |
| `exit-criteria-fidelity.md` (+ `-Part-2-DecisionLeavesCriteriaStale.md`, 119 lines, 0 hits) | 777 | :246 "**Mechanical anchor per row** — `{test-cmd}` + expected count …" and :252 the matching checklist row | A sprint-signoff anchor at sprint close, not a per-task baseline. Decide whether "`{test-cmd}` + expected count" should say which population |
| `task-file-and-tracking-requirements.md` | 463 | :135 a BLOCKING row: commands must be explicit, resolving `{lint-cmd}` / `{test-cmd}` / `{exec-cmd}` placeholders from `config.yaml.build_commands` | **Highest-risk hit.** `build_commands` usually holds the whole-suite command, so "resolve the placeholder from config" may push a planner to an unscoped per-task gate. Read the surrounding section |
| `verification-gates.md` | 70 | none | Now a 70-line family index. It was split into `gate-*` topic files on 2026-10-08, after the plan's 2026-10-06 survey. The whole-suite text it held, if any, moved. See the next table |
| `session-execution-protocol.md` | 430 | :334 anecdote ("full suite green"). :355 and :357 anecdotes. :385 `<run the suite> \| tail -1  # nothing broken at execution`. :390 "lint … before the suite" | :385 is the refactor-safety gate (§6.1 sub-rule D, execution stage after a move). A whole-suite run there is a once-per-refactor execution check, so it is likely legitimate. Confirm, and decide whether the recipe should say "once, after the move" |

Hits in the `gate-*` files that replaced `verification-gates.md`, from the same `Grep` with the `{gate-*,verification-gate*}.md` glob:

| File | Hit | First-pass reading |
|---|---|---|
| `gate-environment-inputs.md` | :53 "The full suite passed throughout, because some test always imported the hub first." | Anecdote |
| `gate-fixture-provenance.md` | :129 "A green suite over invented fixtures says nothing …" | Prose |
| `gate-positive-and-mutation-controls.md` | :60 mutation-control step 3: "delete the scratch copy; re-run the suite green" | Once per control, not a per-task baseline. Decide whether "the suite" should read "the test" |
| `gate-pre-edit-baseline.md` | :54-:70 | The rule itself, so excluded |

The first pass may be wrong because both patterns are vocabulary-shaped. A file can teach an unscoped per-task gate with no matching word, for example a Before/After exemplar that shows a bare `{test-cmd}` with nothing after it. So this item requires a full read of each file, not only the hit lines.

## Proposed Solution

1. Read each of the five files end to end: `discovery-and-exit-criteria.md`, `exit-criteria-fidelity.md` with its Part-2 file, `task-file-and-tracking-requirements.md`, `session-execution-protocol.md`, and the `verification-gates.md` index plus the `gate-*` topic files it maps. Also read any Before/After exemplar, recipe or checklist that names `{test-cmd}`, `pytest`, `{lint-cmd}` or a build command.
2. Classify every hit as one of:
   - **teaches a per-task whole-suite baseline**: rewrite it to the scoped form and cite `references/gate-pre-edit-baseline.md` §10.1.1 by heading text
   - **legitimate whole-population run**: once per plan, sprint signoff, or refactor execution stage. Leave it, or add a few words naming the population
   - **unrelated**: anecdote or prose. Leave it
3. Record the classification table in the closing note, with one row per hit, including the ones left alone.
4. Edits stay inside the shipped plugin's identifier-isolation rules. Never cite `BB-516`, `SGB` or `LL-` ids in the plugin. State the content.

Out of scope: any change to `gate-pre-edit-baseline.md` §10.1.1, `handlers/plan.md` Step 8e, `templates/task-file.md`, or the linter's Check 16. Those carry the rule this item checks against.

## Acceptance Criteria

- [ ] All five files (and the `gate-*` topic files mapped from `verification-gates.md`) were read in full. The closing note lists every one with its line count at read time.
- [ ] The closing note has a classification table with one row per hit from both searches in Problem, plus any extra hit found by the full read. Each row's disposition is one of the three classes in Proposed Solution.
- [ ] Every row classed "teaches a per-task whole-suite baseline" is rewritten to the scoped form and cites §10.1.1 by heading text. If no row is so classed, the closing note says so, and the item closes with no plugin edit.
- [ ] If any plugin file is edited: the identifier-isolation battery from `.claude/rules/plugin-identifier-isolation.md` §3 is empty on the added lines. The native-tool verb check from `.claude/rules/native-tool-promotion-gate.md` §4 is empty. `python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_reviewer_reference_reachability.py cloned-repos/planwise/tests/test_lint_verification_gates.py` passes (58 passed at `cf61b54`. Re-take the count before trusting it).
- [ ] If any plugin file is edited, `python -m ruff check cloned-repos/planwise` passes.

## Related

- [BB-516-DOC-AuditFiveReferencesForWholeSuiteBaselines.md](BB-516-DOC-AuditFiveReferencesForWholeSuiteBaselines.md) - file for this item
- `planwise/Plans/ScopedGateBaselines/SGB-Master-Plan.md` § Vision - the out-of-scope note this item discharges
- `planwise/Plans/ScopedGateBaselines/Sprint-01-HandlerAndTemplate/Session-01-ScopeTheMeasurement/Outputs/SGB-S01-01-Summary.md` - the session that shipped the rule (plugin commit `b5c199c`)

---

*Created: 2026-10-11*
