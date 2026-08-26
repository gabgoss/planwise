---
description: Discovery scope rigor (deterministic-bug counts, ID persistence, upstream-normalization scoping) and the shared 13-row plan-review BLOCKING-findings table for the discovery/exit-criteria rule family; cross-layer exit-criteria fidelity lives in exit-criteria-fidelity.md and execution-time binding rules (design-extension traceability, audit-finding triage, bounded-temp-fix, spike-instrument verdict discipline) live in execution-time-binding-rules.md
---

# Discovery Scope Rigor & Exit-Criteria Fidelity

**Purpose:** Binding rules covering related plan-fidelity concerns, split across three files. This file (the anchor) covers Discovery scope rigor (§15) and carries the shared 13-row `/planwise review` BLOCKING-findings table for the whole family — kept whole here rather than split, so review tooling scans one table for all 13 checks. Cross-layer enforcement of exit-criteria fidelity (§16) lives in [exit-criteria-fidelity.md](exit-criteria-fidelity.md); design-extension traceability (§17), cross-tier audit-finding triage (§18), the bounded-temp-fix that seeds a deferred Discovery (§19), and spike-instrument verdict discipline (§20) live in [execution-time-binding-rules.md](execution-time-binding-rules.md). Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same issues.

This file is the §15 segment of a 3-way split of what was originally referenced as the "§15 + §16 expansion" from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols); §16 and §17-§20 were subsequently split into the two sibling files named above to keep all three files comfortably within a single Read call. Read this file before authoring Discovery-phase Consolidated Context or Execution Inputs that name affected records. Read the siblings before authoring multi-layer binding refinements, BLOCKING-coverage task files, or sprint signoff checklists (`exit-criteria-fidelity.md`); or design-extension documentation, cross-tier audit triage, bug-fix sessions that surface a recurring defect class, or de-risk spikes that run on synthetic fixtures (`execution-time-binding-rules.md`).

## Table of Contents

- [15. Discovery Scope Rigor](#15-discovery-scope-rigor-binding)
  - [15.1 Deterministic-bug scope MUST be counted by execution, not estimated](#151-deterministic-bug-scope-must-be-counted-by-execution-not-estimated)
  - [15.2 Persist specific IDs, not just counts](#152-persist-specific-ids-not-just-counts)
  - [15.3 Scope an Upstream Normalization Task by Failure Mode, Not by Audit Tier](#153-scope-an-upstream-normalization-task-by-failure-mode-not-by-audit-tier)
- [16. Cross-Layer Enforcement & Exit-Criteria Fidelity](exit-criteria-fidelity.md#16-cross-layer-enforcement--exit-criteria-fidelity-binding) — `exit-criteria-fidelity.md`
  - [16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers](exit-criteria-fidelity.md#161-binding-refinements-must-be-echoed-as--binding-callouts-across-plan-layers)
  - [16.2 "Surfaces" is an enforcement claim, not a mention](exit-criteria-fidelity.md#162-surfaces-is-an-enforcement-claim-not-a-mention)
  - [16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row](exit-criteria-fidelity.md#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row)
  - [16.4 Verify the Metric Definition Before Reproduction](exit-criteria-fidelity.md#164-verify-the-metric-definition-before-reproduction)
- [17. Design Extensions Introduced During Execution](execution-time-binding-rules.md#17-design-extensions-introduced-during-execution-binding) — `execution-time-binding-rules.md`
- [18. Cross-Tier Audit-Finding Triage](execution-time-binding-rules.md#18-cross-tier-audit-finding-triage-binding)
- [19. Narrow Fix Reveals a Systemic Gap — Bounded Temp Fix That Seeds the Deferred Discovery](execution-time-binding-rules.md#19-narrow-fix-reveals-a-systemic-gap--bounded-temp-fix-that-seeds-the-deferred-discovery-binding)
- [20. Spike Instrument Verdict Discipline](execution-time-binding-rules.md#20-spike-instrument-verdict-discipline-binding)
  - [20.1 Synthetic-Fixture Verdict Partitioning](execution-time-binding-rules.md#201-synthetic-fixture-verdict-partitioning)

---

## 15. Discovery Scope Rigor (BINDING)

Discovery is the only phase where scope is cheap to measure correctly. After Discovery, every downstream artifact (Execution Input, task files, token estimates, success criteria) inherits the Discovery scope — and a wrong scope cascades through the entire plan.

### 15.1 Deterministic-bug scope MUST be counted by execution, not estimated

> [!constraint] Bugs with deterministic trigger conditions MUST be counted by running the identification query during Discovery
> When a bug has a deterministic trigger condition (alphabetical ordering, date
> range, specific column value, foreign-key state, or any evaluable predicate),
> the Discovery phase MUST run the identification query against the actual data
> store and persist the exact count and IDs. Estimating from a sample, a
> user-reported subset, or "looks like ~{N}" fails this rule.
>
> WRONG — Discovery declares "{N} confirmed-affected records" based on a
> user-reported sample. Plan documents and query templates use {N} throughout.
> Execution discovers the actual count is {M} (where M is materially larger
> than N). The scope increase requires user confirmation mid-session and
> invalidates row-count estimates in all downstream task files.
>
> CORRECT — Discovery writes and executes the identification query, persists the
> exact count and IDs in the Consolidated Context, and propagates the real count
> to every downstream estimate:
>
> ```sql
> SELECT f.{id_col}, f.{date_col}, d.{name_col} AS {dim_label}
> FROM {fact_table} f
> JOIN {dim_table} d ON d.{id_col} = f.{fk_col}
> WHERE f.{date_col} > '{date_value}'
>   AND f.{snapshot_col} != '{snapshot_value}';
> -- Returns: {row_count} rows (verified {YYYY-MM-DD})
> ```

> [!checklist] Discovery Scope Counting (Deterministic-Bug Plans)
> - [ ] Wrote the identification query (selection criteria explicit, not paraphrased)
> - [ ] Executed the identification query against the live data store during Discovery
> - [ ] Persisted the result count in the Consolidated Context
> - [ ] Persisted the actual IDs (or the exact query) in the Execution Input
> - [ ] Used the real count for all downstream estimates (row counts, token budgets, runtime estimates)

Applies to:
- Any plan where a bug has deterministic affected-row criteria
- Meta-Plan Discovery phases that analyze data corruption scope
- Execution Input extraction where row counts drive token estimates

#### Reviewer Check 040 — §15.1 Discovery Count-by-Execution

- **Severity / Role / Type:** BLOCKER | Coverage Reviewer | NEW
- **What:** Discovery outputs citing counts MUST also cite the underlying execution (e.g., `{lint-cmd}` / `{test-cmd}` / SQL query / Glob pattern).
- **Detection:** Grep Discovery for `\b(\d+)\s+(rows|files|matches|tasks)`. For each count, check for adjacent execution citation. Absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Discovery count missing execution citation
File: {Discovery output path} | Location: {section}
Issue: Count "{N}" cited without underlying execution
Fix: Cite per references/discovery-and-exit-criteria.md §15.1 | Confidence: HIGH
```

### 15.2 Persist specific IDs, not just counts

> [!constraint] Discovery MUST persist specific IDs (or the deterministic identification query), not count-only placeholders
> When Discovery identifies a specific set of affected records, the Execution
> Input and downstream query templates MUST contain either the actual IDs or the
> exact identification query (with parameters). Count-only placeholders like
> `{N_record_ids}` force re-derivation at execution time and lose information
> about which records are in scope.
>
> WRONG — count-only placeholder; no one knows which records:
> ```sql
> WHERE record_id IN ({N_record_ids})
> ```
> Cost: every downstream task either re-runs the identification query (extra
> data-store round-trip per task) or guesses, risking off-by-one drift between
> Discovery and execution.
>
> CORRECT — list the IDs OR document the deterministic query that produces them:
> ```sql
> -- Option A: inline IDs (when ≤100 records)
> WHERE record_id IN (
>   '{id1}', '{id2}', ...
> )
>
> -- Option B: deterministic query (when >100 records or list would dominate the file)
> WHERE {deterministic_criterion}
>   AND {date_criterion};
> ```

When the ID list is too long for inline inclusion (>100 IDs), persist the identification query with exact parameters so execution can reproduce the list deterministically. The query itself becomes the canonical artifact — citing it removes ambiguity about scope.

Applies to:
- Any data-repair plan targeting specific records
- Meta-Plan Discovery phases that identify corruption scope
- Execution Inputs referencing record subsets by count

#### Reviewer Check 041 — §15.2 Persist IDs Not Just Counts

- **Severity / Role / Type:** BLOCKER | Coverage Reviewer | NEW
- **What:** Discovery outputs MUST persist actual IDs/keys (not just counts) for downstream tasks to dereference.
- **Detection:** "N matches" without enumerated ID list → BLOCKER.
- **Finding template:**
```
[BLOCKER] Discovery output persists count without IDs
File: {Discovery output path} | Location: {section}
Issue: "{N} matches" stated without ID enumeration
Fix: Persist IDs per references/discovery-and-exit-criteria.md §15.2 | Confidence: HIGH
```

### 15.3 Scope an Upstream Normalization Task by Failure Mode, Not by Audit Tier

When one task is scaffolded to normalize a set of items *before* a mechanical batch processes the rest, the scoping criterion MUST be the **failure mode the mechanical batch cannot handle** — not a severity tier, priority band, or triage bucket inherited from an earlier audit.

A triage tier answers "how much attention does this need?" The mechanical batch asks a different question: "does this item have the property that makes the mechanical transform unsafe?" Those two questions have different answers, and where they diverge the upstream task ships incomplete while reporting success.

> [!constraint] The Upstream Scope Criterion Must Name the Blocking Property
> WRONG — scope inherited from an audit's severity tier:
> ```
> Upstream task: "normalize the SEVERE-tier {N} items"
> # SEVERE = "needs manual attention". But the property that blocks the mechanical
> # transform — a non-canonical calling site — occurs at COSMETIC tier too.
> # Result: 7 normalized, 9 missed, all 9 surfacing later as batch HALTs.
> ```
> CORRECT — scope derived by executing the discriminating check against the full population:
> ```
> Upstream task: "normalize every item whose caller does not match the canonical
>                 signature" — enumerated by running that check over all {M} items
>                 at Discovery time, independent of any audit tier.
> ```

The general form: when an upstream task's scope is a *subset* named by an inherited classification, verify at scaffold time that the classification and the blocking property select the same set. If they do not, scope by the property.

---

## Scaffolding Templates (canonical paste-ready blocks)

> [!practice] Canonical Scaffolding Template Lives Inline in This Rule
> When scaffolding a Discovery phase, paste the block below verbatim — it is
> the canonical template for §15.1 (Discovery identification-query block).
> Maintaining it inline (rather than as a sibling template file) keeps the
> template, the rationale, and the WRONG/CORRECT contrast in a single source.
> Template 2 (§16.3 verbatim sprint-signoff checklist block) lives in
> [exit-criteria-fidelity.md](exit-criteria-fidelity.md#scaffolding-template-2--sprint-signoff-checklist-block-163).
>
> **Template 1 — Discovery identification-query block (§15.1).** Paste into the
> Consolidated Context Part covering scope counting; adapt SELECT/WHERE to the
> deterministic trigger:
>
> ```sql
> -- Discovery identification query (executed against live data store at Discovery time)
> SELECT f.{id_col}, f.{date_col}, d.{name_col} AS {dim_label}
> FROM {fact_table} f
> JOIN {dim_table} d ON d.{id_col} = f.{fk_col}
> WHERE {deterministic_trigger_condition};
> -- Returns: {row_count} rows (verified {YYYY-MM-DD})
> ```
>
> Persist the row count + verification date inline. Then propagate the count +
> ID list (or the query + parameters when >100 IDs) into every Execution Input
> and downstream task file (§15.2).

---

## Plan-Review Enforcement Summary

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following violations. Kept whole on this anchor file (rather than split across the three segments), so review tooling scans one table for all 13 checks; each row's Source rule column names the file that now carries the cited rule.

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Discovery scope estimated, not counted | Discovery output cites a deterministic-bug count without an inline identification query that was executed against the live data store | §15.1 |
| 2 | Count-only placeholder in Execution Input | A `{N_ids}` or `{N_records}` style placeholder appears in any task file's Required Context or query template without an accompanying ID list or deterministic query | §15.2 |
| 3 | Single-layer binding refinement | A binding refinement is mentioned in the Sprint Plan but not echoed as `> [!binding]` callouts in at least the Orchestration and the gated task file | exit-criteria-fidelity.md §16.1 |
| 4 | "Surfaces" without enforceable check | A task body claims to "surface" a BLOCKING item but contains no numeric assertion, grep, source-introspection check, documentation-content check, or parametrized test mechanism | exit-criteria-fidelity.md §16.2 |
| 5 | Signoff row count mismatch or vague row | A sprint signoff checklist's row count differs from the EI exit-criteria item count, or any row lacks a mechanical anchor, or any rename/substitution lacks a deviation annotation | exit-criteria-fidelity.md §16.3 |
| 6 | BLI-cited audit anchor without re-verification or with bare-column grep | A Sprint Plan / Orchestration encodes BLI-cited bugs as mechanical-grep success criteria AND does NOT include a pre-flight re-verification step at session start, OR uses bare-column grep anchors when ≥2 tables in the audit scope share the column name | exit-criteria-fidelity.md §16.3 |
| 7 | Undocumented design extension | A sprint signoff cites a parameter / threshold that does not appear in the original design spec AND has no inline What/Why/Source comment AND is not in the project's config catalog | execution-time-binding-rules.md §17 |
| 8 | Audit Findings doc lacks a pre-emptive flags table | A cross-tier audit's Findings doc enumerates HIGH/MEDIUM findings on items whose downstream artifacts are NOT all in deployed code AND lacks a pre-emptive flags table sectioning those findings into the Sprint-M Authoring bucket | execution-time-binding-rules.md §18 |
| 9 | Systemic gap resolved inline or under-fixed | A bug-fix session whose fix surfaces a recurring defect class either builds the whole framework inline (scope explosion) OR pins only the observed instances (no severity-class handling, no seeding catalog, no separate Discovery/Meta-Plan) | execution-time-binding-rules.md §19 |
| 10 | Metric HALT on labelling difference | A signoff or consolidation agent declares FAIL / HALT because a probe column does not match the baseline, without first doing the cheap arithmetic check to confirm whether a different probe column (or combination) reproduces the baseline exactly | exit-criteria-fidelity.md §16.4 |
| 11 | Synthetic-fixture magnitude claim | A spike reports tolerance or threshold magnitudes as "confirmed" based on synthetic-fixture sweep results alone, without deferring the magnitude verdict to real-input data | execution-time-binding-rules.md §20.1 |
| 12 | Unsatisfiable absence criterion (enactor or ownership) | A removal/absence Success Criterion asserts a zero-match grep AND either the removal artifact is not excluded from the search scope (enactor cause) OR the searched token is a bare symbol/identifier with no pasted occurrence count (ownership cause) | exit-criteria-fidelity.md §16.9 |
| 13 | Upstream normalization task scoped by tier, not property | A task scaffolded to normalize a set of items before a mechanical batch processes the rest names its scope via an inherited severity/triage tier rather than the specific property that blocks the mechanical transform | §15.3 |

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols) (parent rule, §15 + §16 cross-references from its Companion Files table), [exit-criteria-fidelity.md](exit-criteria-fidelity.md) (§16, cross-layer enforcement & exit-criteria fidelity), [execution-time-binding-rules.md](execution-time-binding-rules.md) (§17-§20, design extensions, audit-finding triage, bounded-temp-fix, spike-instrument verdict discipline), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Task File Template), [session-plan-requirements.md](session-plan-requirements.md) (signoff sections), [task-content-fidelity.md](task-content-fidelity.md) (Required Context fidelity, verify-before-cite).*
