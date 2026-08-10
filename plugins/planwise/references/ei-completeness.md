---
description: EI completeness — three-axis scope coverage (multi-sprint file-touch reconciliation, cluster enumeration, audit-grep-table coverage) so an EI's stated scope IS the executable work (ei-fidelity.md §9)
---

# EI Completeness (Three-Axis Scope Coverage)

**Segment C of a 4-way split of `ei-fidelity.md`** (934 lines, split 2026-08-10). Carries §9 (+9.1-9.3) verbatim; original §-numbers are preserved — a citation like "§9.2" names the section, not the file. See the anchor's segment index for the full 4-way map: [ei-fidelity.md](ei-fidelity.md) (§1-§4, this split's segment A), [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-source-promise-integrity.md](ei-source-promise-integrity.md) (§10-§11, segment D).

---

## 9. EI Completeness — Three-Axis Scope Coverage

> [!binding] EI Completeness — what the EI scopes IS the work
> When the Scaffolding agent extracts an EI from a multi-sprint plan or from an audit, the EI defines the entire scope the executor will be authorized to touch. Any in-scope work the EI does NOT enumerate becomes one of three failure modes at execution time:
>
> 1. **Wrong-baseline edits** — executor writes against a pre-plan baseline that has since shifted, duplicating or HALTing on anchor-quote mismatch.
> 2. **Mid-execution scope-expansion gates** — executor detects the gap, pauses for `AskUserQuestion`, blocks on user approval to extend scope.
> 3. **Exit-gate failure with no in-sprint remediation path** — final verification finds defects in files no upstream task was authorized to edit; the sprint cannot close.
>
> Three completeness axes prevent each mode. Apply all three when authoring an EI; flag any EI that omits one.

The three axes are independent — an EI may pass one and fail another. The §9.1/§9.2/§9.3 subsections below define each axis and its WRONG/CORRECT contract. The companion `/planwise review` checks (in `agents/plan-reviewer.md` under the EI Reviewer role) enforce them mechanically.

---

### 9.1 Multi-Sprint Cumulative File-Touch Reconciliation

> [!constraint] Sprint-N's EI "Current state" anchor blocks MUST reflect POST-prior-sprint state, not pre-plan baseline
> When a multi-sprint plan touches the same file across two or more sprints, the Scaffolding agent that extracts Sprint-N's EI from upstream sources (Consolidated Context parts, Tier-2 binning outputs, audit documents) MUST reconcile the cumulative deltas from sprints 1..N-1 before writing the per-sprint EI "Current state" blocks.
>
> **Identity:**
>
> - Sprint-N `Current state` block = pre-plan baseline + Σ deltas from sprints 1..N-1
> - Sprint-N `Proposed change` block = ONLY the delta this sprint adds
>
> WRONG — Sprint-N EI extracts "Current state" verbatim from a Consolidated Context part that predates the plan's own Sprint-1, declaring a pre-plan baseline:
>
> ```markdown
> **Current state** (existing rows 1-10, last row quoted for anchoring):
> | 10 | ...row-10 anchor... |
>
> **Proposed change** — APPEND 8 new rows after row 10:
> | 11 | ...new row... |
> | 12 | ...new row... |
> ...
> ```
>
> If Sprint-1 already appended rows 11-15 to this file, naive Sprint-N execution either (a) duplicates rows 11-15 (writing them twice), or (b) HALTs at the anchor-quote check because the file now has 15 rows, not 10.
>
> CORRECT — Sprint-N EI declares the post-prior-sprint baseline and a Cross-Sprint Precondition gate:
>
> ```markdown
> > [!gate] Cross-Sprint Precondition
> > This {N}-row baseline assumes Sprint-{M} Task {prior_task_id} has completed.
>
> **Current state — POST Sprint-{M} Task {prior_task_id} ({N} rows; rows {M+1}-{N} already present)**:
> | {row-N} | ...current anchor... |
>
> **Proposed change** — APPEND ONLY {remaining_count} rows ({N+1}-{N+remaining}):
> | {row-N+1} | ...new row... |
> ```
>
> And the matching task file (Sprint-N's first task that edits this file) MUST include a Step-1 prerequisite grep gate verifying Sprint-M's marker is present in the file. If the marker is missing, HALT — Sprint-M is incomplete and Sprint-N cannot run against an outdated baseline. See `templates/task-file.md` "Cross-Sprint Prerequisite Grep Gate" pattern.

How to apply during scaffolding:

1. Build a Cross-Sprint File-Touch matrix: for each file edited by the plan, list every (sprint, session, task) that touches it.
2. For each file edited by ≥2 sprints, walk the sprints in order. For each later sprint, the EI "Current state" anchor block MUST reflect the post-prior-sprint state, not the source's pre-plan snapshot.
3. The Sprint Plan for the later sprint SHOULD include a `## Cross-Sprint File Touches` section listing the file and the prior sprint that already edited it (see `templates/sprint-plan.md`).
4. The task file for the first session that touches a previously-touched file MUST include a Step-1 prerequisite grep gate.

Red flags during review:

- Sprint-N EI "Current state" anchor quotes content from a Consolidated Context part dated before Sprint-1.
- Sprint-N "Proposed change" overlaps numerically with a delta already applied by Sprint-M < N.
- Sprint-N task file edits a cross-sprint-touched file with no Step-1 prerequisite grep.

---

### 9.2 Cluster Enumeration in EI Repoint Maps

> [!constraint] EI repoint maps MUST enumerate every row of an audit-identified cluster — listing only the canonical example forces a mid-execution scope-expansion gate
> When an audit identifies a range cluster (multiple dangling anchors all belonging to the same canonical range, the same misnumbered series, or the same defect-class set), the EI repoint map MUST enumerate every row of the cluster — with explicit source anchor and target anchor per row. Implicit scope expansion via parenthetical hints ("canonical §X.Y.{first}-{last}") is forbidden.
>
> WRONG — list only the canonical mis-number; assume executor will infer the cluster:
>
> ```markdown
> | line {L_canonical} (Check {N_canonical}) | `§X.Y.{misnumbered_canonical}` | `§X.Y.{canonical_target}` (the §X.Y.{misnumbered_canonical} mis-number → canonical §X.Y.{first}-{last}) |
> ```
>
> Cost: the executor running the mechanical repoint task hits dangling anchors at lines `{L_2}`, `{L_3}`, `{L_4}` that the EI map does NOT cover, pauses for `AskUserQuestion`, and waits for user approval to scope-expand. The repoint is no longer mechanical.
>
> CORRECT — enumerate every row of the audit-identified cluster, with explicit per-row target:
>
> ```markdown
> | line {L_1} (Check {N_1}) | `§X.Y.{misnumbered_1}` | `§X.Y.{target_1}` |
> | line {L_2} (Check {N_2}) | `§X.Y.{misnumbered_2}` | `§X.Y.{target_2}` |
> | line {L_3} (Check {N_3}) | `§X.Y.{misnumbered_3}` | `§X.Y.{target_3}` |
> | line {L_4} (Check {N_4}) | `§X.Y.{misnumbered_4}` | `§X.Y.{target_4}` |
> ```
>
> If the cluster has a sequential canonical mapping (`§X.Y.{m_1}→§X.Y.{t_1}`, `§X.Y.{m_2}→§X.Y.{t_2}`, ...), state the mapping rule explicitly in EI prose ABOVE the table. The prose makes the mapping auditable; the per-row enumeration makes it mechanical.

Why mechanical tasks must not require inference:

The repoint task is mechanical — open file, find anchor, change anchor, move on. Mechanical tasks must not require the executor to interpret which other rows of an audit's range table are also in scope. Either the EI is complete (executor proceeds mechanically) or the EI carries an explicit out-of-scope marker for the rows it deliberately omits. Implicit scope expansion based on parenthetical hints ("canonical §X.Y.{first}-{last}") is ambiguous and one mid-execution-pause away from incorrect scope.

How to apply during scaffolding:

1. Open the audit's range row and enumerate every file:line cited.
2. For each line, identify the specific check and the specific anchor used (Source field, Fix-pointer).
3. Emit one repoint-map row per cited line, with the explicit source anchor + target anchor.
4. If the cluster has a sequential canonical mapping, state it explicitly in EI prose above the table.

How to apply during execution:

If the executor finds a dangling anchor that the EI map does NOT cover, the executor MUST surface the gap before applying any silent extrapolation. Mid-execution `AskUserQuestion` is the correct fallback — but the better outcome is that the EI map is complete to begin with.

Red flags during review:

- EI repoint map has fewer rows than the audit's cited-line count for the same cluster.
- EI prose references a "canonical range" without enumerating every line in that range.
- Downstream verification task references anchors no upstream repoint task enumerated.

---

### 9.3 Audit-Grep-Table Coverage — Repair Scope ⊇ Verification Scope

> [!constraint] When an audit lists a multi-file defect-class grep table, the EI MUST scope explicit repair tasks for EVERY file in the table — not the high-visibility subset
> An exit-gate verification task ("0 defects across N files") is only achievable if every one of those N files was scoped for repair somewhere upstream. If the EI scopes repair in M < N files and verification across N, the exit gate is structurally guaranteed to fail at the verification task. The verification task has no remediation hook — its mandate is "do not edit."
>
> WRONG — EI scopes repair only to the "primary" or "most-visible" files in the audit's defect-class table; other files appear only in the final-sweep "verification only" task:
>
> ```markdown
> # EI §1: repoint citations in {primary_file_1}                       ← repair
> # EI §2: repoint citations in {primary_file_2}                       ← repair
> # EI §5: verify ALL FOUR files have 0 dangling (verification only)   ← verify scope wider than repair scope
> ```
>
> Cost: `{secondary_file_1}` and `{secondary_file_2}` were in §5's verification scope but never in §1-§2's repair scope. They retain their dangling citations. The §5 sweep FAILS. Exit gate FAILS. No in-sprint path to remediate because no task was authorized to edit them. The sprint can complete its task work and still fail its exit gate.
>
> CORRECT — every file in the audit's defect-class grep table gets an explicit repair task; the final sweep is then a true verification:
>
> ```markdown
> # EI §1: repoint citations in {primary_file_1}                       ← repair
> # EI §2: repoint citations in {primary_file_2}                       ← repair
> # EI §3: repoint citations in {secondary_file_1}                     ← repair (was missing)
> # EI §4: repoint citations in {secondary_file_2}                     ← repair (was missing)
> # EI §5: verify all four files have 0 dangling (verification only)   ← verify scope = repair scope
> ```
>
> Result: §5 sweep finds 0 dangling because §1-§4 covered every file. Exit gate is achievable; the verification task confirms the work.

The invariant:

> Repair scope ⊇ Verification scope.
>
> If a file is in the verification scope, it MUST be in at least one upstream repair task's Required Context (with the EI authorizing that task to edit it). Verification scope = ∪ (Repair scope_i) is the only configuration that closes an exit gate.

How to apply during scaffolding:

1. Find every grep table or file enumeration in the audit that lists files where defect instances live.
2. For each file in that table, emit an explicit repair task in the EI — even if the per-file defect count is small (1-3 lines).
3. Schedule the final verification task AFTER all repair tasks complete (cross-session or cross-sprint dependencies if needed).
4. Pre-flight check: for each file in the audit table, ask "which EI section authorizes editing this file?" If the answer is none, add it.

How to apply during execution:

If the executor running the final verification finds defect instances in files no upstream task touched, the executor MUST report it as a BLOCKER on the exit gate — not silently fix it. Silent fix masks the EI scoping defect and the same gap recurs in the next plan.

Red flags during review:

- Audit `## Dangling Anchors` (or equivalent) grep table lists N files; EI repair sections cover M < N of them.
- Final-sweep verification task names files no upstream repair task was authorized to edit.
- The phrase "verification only — do not edit" appears in a sweep that covers files the EI's earlier sections did not scope for repair.

---

*Anchor: [ei-fidelity.md](ei-fidelity.md) (§1-§4 EI-as-archival, severity vocabulary preservation, threshold alignment, UNCONFIRMED four-site enforcement — segment A of this file's 4-way split, 2026-08-10). Sibling segments: [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-source-promise-integrity.md](ei-source-promise-integrity.md) (§10-§11, segment D).*
