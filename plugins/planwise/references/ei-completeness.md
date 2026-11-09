---
description: EI completeness — three-axis scope coverage (multi-sprint file-touch reconciliation, cluster enumeration, audit-grep-table coverage) so an EI's stated scope IS the executable work (ei-fidelity.md §9)
consult-when: Checking an Execution Input's stated scope actually covers the executable work (three axes)
---

# EI Completeness (Three-Axis Scope Coverage)

This file is segment C of the `ei-fidelity.md` split. The Segment Index in [ei-fidelity.md](ei-fidelity.md) holds the four-way map.

---

## 9. EI Completeness — Three-Axis Scope Coverage

> [!binding] EI Completeness — what the EI scopes IS the work
> When the Scaffolding agent extracts an EI from a multi-sprint plan or from an audit, the EI defines the entire scope the executor will be authorized to touch. Any in-scope work the EI does NOT enumerate becomes one of three failure modes at execution time:
>
> 1. **Wrong-baseline edits** — executor writes against a pre-plan baseline that has since shifted, duplicating or HALTing on anchor-quote mismatch.
> 2. **Mid-execution scope-expansion gates** — executor detects the gap, pauses for `AskUserQuestion`, blocks on user approval to extend scope.
> 3. **Exit-gate failure with no in-sprint remediation path** — final verification finds defects in files no upstream task was authorized to edit; the sprint cannot close.
>
> WRONG — an EI applies one or two of the axes below and omits the third, so the omitted work surfaces as one of the three failure modes.
>
> CORRECT — an EI applies all three axes, so its stated scope is the executable work. A review flags any EI that omits one.

The three axes are independent: an EI may pass one and fail another. The companion `/planwise review` checks (in `agents/plan-reviewer.md` under the EI Reviewer role) enforce them, and `scripts/lint_execution_input.py` tests each axis under the word id its section names.

---

### 9.1 Multi-Sprint Cumulative File-Touch Reconciliation

> [!constraint] Sprint-N's EI "Current state" anchor blocks MUST reflect POST-prior-sprint state, not pre-plan baseline
> When two or more sprints edit one file, Sprint-N's `Current state` block equals the pre-plan baseline plus the deltas of sprints 1..N-1, and its `Proposed change` block holds only the delta Sprint-N adds. The Scaffolding agent reconciles those deltas before it writes the blocks from any upstream source (Consolidated Context parts, Tier-2 binning outputs, audit documents).
>
> WRONG — Sprint-N's EI copies a 10-row "Current state" from a Consolidated Context part that predates the plan's first sprint. An earlier sprint already appended rows 11-15, so execution duplicates them or HALTs at the anchor-quote check.
>
> CORRECT — Sprint-N's EI declares the POST Sprint-{M} baseline of {N} rows behind a `[!gate] Cross-Sprint Precondition` callout, and appends only the remaining rows.

**Enforced by:** `scripts/lint_execution_input.py`, word id `cross-sprint-touch` (the rule lives in `scripts/lint_execution_input_plan.py`). It cannot see a file no Write-Set table lists, a later sprint's obligations, or whether the grep gate names the prior task's marker. Reviewer Check 055 covers the full detection.

The section also requires:

- The first task in Sprint-N that edits the file carries a Step-1 prerequisite grep gate for Sprint-M's marker. A missing marker means HALT, because Sprint-M is incomplete. See `templates/task-file.md` "Cross-Sprint Prerequisite Grep Gate" pattern.
- The later Sprint Plan declares the file and the prior sprint under `## Cross-Sprint File Touches` (see `templates/sprint-plan.md`).
- **When the two sprints have no declared ordering, there is no "later" sprint — and that case is strictly more dangerous, not exempt.** The scaffolder MUST either add an ordering edge between the two sprints or add a `MUST NOT run concurrently (shared file: {path})` row to the Sprint Dependencies table. Until one lands, both Sprint Plans carry the `## Cross-Sprint File Touches` row and both sprints' first writing tasks carry the Step-1 gate, each reading the live file and recording its observed state before editing. The emission rule and its pair live at `references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §16 (rule 16.6).
- **A path-scoped diff count is not the control for a shared file.** It shows this task's own edit and never another writer's loss. A task that shares a file also asserts a **content grep for a literal the other writer authored**, or that literal's documented absence when this task runs first.

#### Reviewer Check 055 — EI Multi-Sprint Cumulative File-Touch Reconciliation

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** When the same file is edited across two or more sprints, the later sprint's EI "Current state" anchor block MUST reflect the cumulative POST-prior-sprint state, not the pre-plan baseline. The later sprint's `Proposed change` MUST cover ONLY the delta this sprint adds. The Sprint Plan SHOULD declare the file under `## Cross-Sprint File Touches`, and the first task that edits the file MUST include a Step-1 prerequisite grep gate.
- **Detection:**
  1. Build a file-touch matrix across all sprint EIs in the plan: for each file edited, list every (sprint, EI section).
  2. For each file edited by ≥2 sprints: extract the later sprint's `Current state` anchor quote and grep the earlier sprint's `Proposed change` block for the same content. If the later sprint's "Current state" matches the pre-plan baseline (i.e., does NOT include the earlier sprint's appended rows/lines) → BLOCKER.
  3. For each file edited by ≥2 sprints: open the later sprint's Sprint Plan; grep `## Cross-Sprint File Touches`. Absent → BLOCKER (the prerequisite-gate authoring rule cannot fire without the declaration).
  4. For each file edited by ≥2 sprints: open the first task file in the later sprint that edits it; grep Step 1 for a prerequisite grep gate naming the prior task ID. Absent → BLOCKER.
  5. **Steps 2-4 select "the later sprint", so an unordered pair falls through them entirely — check it separately.** For each file edited by ≥2 sprints, read the Master Plan's Sprint Dependencies table for an ordering edge between those sprints. If none exists: assert a `MUST NOT run concurrently (shared file: …)` row for the pair, a `## Cross-Sprint File Touches` row in **both** Sprint Plans, and a Step-1 gate in **both** sprints' first writing task. Any one absent → BLOCKER.
  6. For each file edited by ≥2 sprints: read the writing tasks' Verification Commands. A task whose only shared-file assertion is a path-scoped diff count → BLOCKER; it must also assert a content grep for a literal the co-writer authored, or that literal's documented absence.
- **Finding template:**
```
[BLOCKER] EI multi-sprint cumulative state not reconciled
File: {later sprint EI file path} | Location: §{section_name} Current state block
Issue: Current state anchor matches pre-plan baseline; prior sprint {prior_sprint_id} already extended this file
Fix: Reconcile per references/ei-completeness.md §9.1 (post-prior-sprint baseline + delta-only Proposed change + Sprint Plan Cross-Sprint File Touches + task-file Step-1 prerequisite grep gate) | Confidence: HIGH
```

---

### 9.2 Cluster Enumeration in EI Repoint Maps

> [!constraint] EI repoint maps MUST enumerate every row of an audit-identified cluster — listing only the canonical example forces a mid-execution scope-expansion gate
> When an audit identifies a range cluster (dangling anchors of one canonical range, one misnumbered series, or one defect-class set), the EI repoint map holds one row per audit-cited `file:line`, naming the check and anchor that line uses, with an explicit source anchor and target anchor. Implicit scope expansion via parenthetical hints ("canonical §X.Y.{first}-{last}") is forbidden.
>
> WRONG — the map lists only line {L_canonical} with the hint "→ canonical §X.Y.{first}-{last}". The executor meets dangling anchors at lines `{L_2}`, `{L_3}`, `{L_4}` that the map does not cover, pauses for `AskUserQuestion`, and the repoint is no longer mechanical.
>
> CORRECT — the map lists lines {L_1} to {L_4}, each with its own `§X.Y.{misnumbered_N}` source and `§X.Y.{target_N}` target.

**Enforced by:** `scripts/lint_execution_input.py`, word id `repoint-cluster`. It cannot see a cluster written differently in the map, or cited lines not written as `file:line`, and it reports no subject when the audit has no range table. Reviewer Check 056 covers the full detection.

The section also requires:

- A cluster with a sequential canonical mapping states the mapping rule explicitly in EI prose ABOVE the table. The prose makes the mapping auditable, and the per-row enumeration makes it mechanical.
- A repoint task must not require inference. Either the EI is complete, or it carries an explicit out-of-scope marker for each row it deliberately omits.
- An executor that finds a dangling anchor the map does not cover MUST surface the gap before applying any silent extrapolation. Mid-execution `AskUserQuestion` is the correct fallback, but the better outcome is a complete map.

#### Reviewer Check 056 — EI Repoint Map Cluster Completeness

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** When an EI repoint map addresses an audit-identified range cluster (multiple dangling anchors belonging to the same canonical range or misnumbered series), the EI repoint map MUST enumerate every row of the cluster with explicit source anchor + target anchor per row. Implicit scope expansion via parenthetical hints ("canonical §X.Y.{first}-{last}") is forbidden.
- **Detection:**
  1. Open the upstream audit document(s) cited by the EI; locate every range table or cluster enumeration (a row that names a range like `§X.Y.{first}-{last}` with multiple `file:line` citations).
  2. For each cluster: count the cited lines in the audit (cluster_lines).
  3. Open the EI repoint map(s); count the rows referencing the cluster's canonical range or any of its misnumbered anchors (mapped_rows).
  4. If `mapped_rows < cluster_lines` → BLOCKER.
  5. If the EI map contains a parenthetical "canonical §X.Y.{first}-{last}" hint but enumerates fewer rows than the cluster → BLOCKER.
- **Finding template:**
```
[BLOCKER] EI repoint map cluster incomplete
File: {EI file path} | Location: §{section_name} repoint map
Issue: Audit cites {cluster_lines} lines in cluster "{cluster_name}" but map enumerates only {mapped_rows} rows
Fix: Enumerate every cluster row with explicit source+target per references/ei-completeness.md §9.2 | Confidence: HIGH
```

---

### 9.3 Audit-Grep-Table Coverage — Repair Scope ⊇ Verification Scope

> [!constraint] When an audit lists a multi-file defect-class grep table, the EI MUST scope explicit repair tasks for EVERY file in the table — not the high-visibility subset
> Repair scope ⊇ Verification scope. If a file is in the verification scope, it MUST be in at least one upstream repair task's Required Context, with the EI authorizing that task to edit it. Verification scope = ∪ (Repair scope_i) is the only configuration that closes an exit gate, because the verification task's mandate is "do not edit" and it has no remediation hook.
>
> WRONG — the EI scopes repair to `{primary_file_1}` and `{primary_file_2}` and verification to all four files. `{secondary_file_1}` and `{secondary_file_2}` keep their dangling citations, the final sweep FAILS, and no task is authorized to edit them.
>
> CORRECT — every file in the audit's defect-class grep table gets an explicit repair task, so the final sweep is a true verification of scoped work.

**Enforced by:** `scripts/lint_execution_input.py`, word id `repair-covers-verify`. It cannot see a repair authorized in a task file rather than the EI, or a file named without backticks, and it reports no subject when the audit has no grep table. Reviewer Check 057 covers the full detection.

The section also requires:

- Each file in the audit's grep table gets an explicit repair task in the EI, even when its defect count is small (1-3 lines).
- The final verification task is scheduled AFTER all repair tasks complete, with cross-session or cross-sprint dependencies if needed.
- An executor whose final verification finds defect instances in files no upstream task touched MUST report a BLOCKER on the exit gate, not fix them silently. A silent fix masks the EI scoping defect, and the same gap recurs in the next plan.

#### Reviewer Check 057 — EI Audit-Grep-Table Coverage (Repair Scope ⊇ Verification Scope)

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** When an audit lists a multi-file defect-class grep table and the EI scopes a final verification sweep across that file set, every file in the grep table MUST appear in at least one upstream repair task's Required Context (with the EI authorizing that task to edit it). Repair scope MUST be a superset of verification scope.
- **Detection:**
  1. Open the upstream audit document(s); extract every defect-class grep table (file enumeration) the audit produces. Call this set `audit_files`.
  2. Open the EI; identify the final verification task (or sweep) — typically the last task in the sprint, with Objective containing "verify" / "sweep" / "0 dangling" / equivalent exit-gate language. Extract the files named in its scope. Call this set `verify_files`.
  3. Open every other EI section that authorizes a repair task; extract the files named in each repair task's Required Context (with edit authority). Call the union `repair_files`.
  4. Compute `verify_files − repair_files`. If non-empty → BLOCKER (the missing files are in the verification scope but no upstream repair task is authorized to edit them).
  5. Also flag: if `audit_files − repair_files` is non-empty AND any of those files are cited in the EI (even outside the verification task) → BLOCKER (the EI scoped verification beyond repair).
- **Finding template:**
```
[BLOCKER] EI audit-grep-table coverage gap (verification > repair)
File: {EI file path} | Location: §{verification_section} vs §{repair_sections}
Issue: Files in verification scope but not in any repair task scope: {missing_files}
Fix: Add explicit repair task(s) authorizing edits to {missing_files}, OR remove them from the verification scope — per references/ei-completeness.md §9.3 | Confidence: HIGH
```
