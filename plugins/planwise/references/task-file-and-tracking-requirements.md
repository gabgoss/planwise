---
description: Task file template and structure, completion tracking rules, and cross-sprint deferred-finding ownership
---

# Task Files and Completion Tracking

**Purpose:** Task file template and structure, completion tracking rules, and cross-sprint deferred-finding ownership.
**Extends session-plan-requirements.md §8; extracted to keep both under the 500-line limit.**

---

## 9. Task Files and Completion Tracking

### Task File Template

Every Task file MUST follow this structure:

```markdown
# Task: {Agent}-{TaskName}

**Task ID:** {Abbrev}-S{XX}-{YY}-{##}
**Agent:** {Haiku|Sonnet|Opus}
**Estimated Tokens:** ~{X}K
**Depends On:** {task numbers or "-"}
**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}

---

## Objective

{What this task must accomplish - clear, specific goal}

---

## Required Context

| Priority | File | Est. Lines | Est. Tokens | Purpose |
|----------|------|-----------|-------------|---------|
| 1 | {file path} | ~{N} | ~{X}K | {why needed} |

**Context subtotal:** ~{X}K tokens (reads) + ~{X}K (output) = ~{X}K total
<!-- Reconciliation: this total MUST match the Estimated Tokens in this task's header. -->
<!-- Use ~13 tokens/line for reads. See planwise plugin reference.md for per-operation costs. -->

**Section Reference Rule (scaffolded plans):** When referencing Execution Inputs, enumerate INDIVIDUAL section numbers with purpose — never ranges.

| Pattern | Acceptable? |
|---------|-------------|
| `EI.md (Sections 2-5)` | **NO** — agent doesn't know which section provides what |
| `EI.md — Section 2 (event types), Section 3 (patterns)` | **YES** — each section annotated with purpose |

---

## Execution Steps

1. {Step 1}
2. {Step 2}
3. {Step 3}

**Mapping Disambiguation:** When a task creates X→Y mapping logic (enum→domain, type→template, event→category), include either:
- A complete mapping table in the task file, OR
- Explicit decision rules with fallback (e.g., "if X matches pattern A → Y1; else → default")

Never leave many-to-many mappings for the agent to infer.

**Interface Consumption:** When a task's input is another module's data model (e.g., reads `ClassifiedChunk` or `HookDetectionResult`), include a field mapping showing which fields are consumed and how:

```
| Input Field | Used For |
|-------------|----------|
| hook_type | Template selection |
| event_name | Output filename |
```

---

## Expected Output

{What the subagent should produce - be specific}

---

## Success Criteria

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}

---

## Verification Commands

> [!verify] Pre- and Post-Task Verification
> Run these commands before and after this task to confirm no regression:
>
> | Command | Type | When |
> |---------|------|------|
> | `{precheck-cmd}` | Connectivity / pre-condition | Before task begins |
> | `{lint-cmd} {src/module/file.ext}` | Lint check | After each modified file |
> | `{format-cmd} {src/module/file.ext}` | Format check | After each modified file |
> | `{exec-cmd}` | Execute / smoke test | After all files modified |
>
> Consumer fills in commands from project config or convention.

---

## Notes for Agent

{Special instructions, edge cases, or context the agent needs}
```

> [!constraint] Verification Commands MUST Be Explicit Shell Invocations
> WRONG — verification commands are vague or absent:
> ```markdown
> ## Verification Commands
> Run your project's tests and lint.
> ```
> CORRECT — verification commands are explicit, parameterized shell invocations:
> ```markdown
> ## Verification Commands
>
> | Command | Type | When |
> |---------|------|------|
> | `{precheck-cmd}` | Connectivity / pre-condition | Before task begins |
> | `{lint-cmd} {src/module/file.ext}` | Lint | After each modified file |
> | `{exec-cmd}` | Execute / smoke test | After all files modified |
> ```
>
> Vague verification commands are treated as absent by `/planwise review`.

**Verification Commands Plan-Review Enforcement:**

| Check | Severity | Reviewer Action |
|-------|----------|-----------------|
| Task file has `## Verification Commands` section | **BLOCKING** if absent for any task with Write steps that touch code, tests, or schemas (runnable-artifact tasks) | Block plan approval until populated, OR until a `<!-- VERIFICATION: not-applicable (reason) -->` HTML comment in the task's `## Notes for Agent` explicitly justifies the omission |
| Commands are explicit shell invocations (not vague prose) | **BLOCKING** if vague (e.g., "run lint and tests") on a runnable-artifact task | Block plan approval; require the planner to resolve `{lint-cmd}` / `{test-cmd}` / `{exec-cmd}` placeholders from `config.yaml.build_commands` or project convention |
| All command types present (connectivity / pre-condition + lint or format + exec or smoke test) | **BLOCKING** if only 1 type present on a runnable-artifact task | Block plan approval; require the planner to emit all three command types per `templates/task-file.md` §Per-File-Type Commands |
| Verification Commands omitted (pure-doc / decision-only / research task) | INFO if `<!-- VERIFICATION: not-applicable (reason) -->` comment present in Notes for Agent | Pass (intentional omission); flag as ERROR if comment absent but task produces no runnable artifact (planner forgot the escape hatch) |

**Scope of BLOCKING enforcement:** The BLOCKING severity applies ONLY to tasks that touch code, tests, or schemas (i.e., tasks whose Expected Output or Execution Steps create or modify files with extensions in the `templates/task-file.md` §Per-File-Type Commands table — `.py` / `.ipynb` / `.sql` / `.cs` / `.cshtml` / `.ts` / `.tsx` / `.{ext}` and equivalents). For purely documentary tasks (markdown edits, decision-only Opus tasks, research-and-report Sonnet tasks), Verification Commands MAY be omitted entirely — but the omission MUST be marked with a `<!-- VERIFICATION: not-applicable (reason) -->` HTML comment so the reviewer can confirm the choice was intentional rather than an oversight. The `handlers/plan.md` Step 8e (Populate Verification Commands) populates the section for runnable-artifact tasks; the `references/error-pattern-catalog.md` Error Pattern Catalog rows 34/35/36 enforce this at review time.

> [!constraint] BLOCKING Severity Discipline
> WRONG — Verification Commands enforcement left at WARNING, allowing plans to ship with blank `{cmd_before_1}` / `{cmd_after_1}` placeholders:
> ```
> | Severity | Reviewer Action       |
> | WARNING  | Flag as missing       |
> ```
> CORRECT — BLOCKING for runnable-artifact tasks, with explicit `<!-- VERIFICATION: not-applicable -->` escape hatch for documentation/decision-only tasks:
> ```
> | Severity   | Reviewer Action                                           |
> | BLOCKING   | Block plan approval until populated or explicitly exempted |
> ```
> The escape hatch keeps the rule humane (pure-doc tasks aren't penalized) without weakening enforcement on tasks that actually produce runnable artifacts. This check is BLOCKING rather than a warning: BLOCKING enforcement is warranted here, the task-file template has per-file-type infrastructure, the plan-handler Step 8e populates it, and the escape hatch covers legitimate exemptions.

> [!constraint] One Task File Per Task — Never Combined
> WRONG — multiple tasks combined into one file, tasks numbered inline rather than as separate files:
> ```
> CNSA-S02-01-Sonnet-AllTasks.md          ← one file for tasks 01, 02, and 03
>
> Contents of AllTasks.md:
>   ## Task 1: Scan Controllers
>   ## Task 2: Map Routes
>   ## Task 3: Generate Report
> ```
> CORRECT — one file per task, task number in filename matches Orchestration table:
> ```
> CNSA-S02-01-01-Haiku-ScanControllers.md
> CNSA-S02-01-02-Haiku-MapRoutes.md
> CNSA-S02-01-03-Sonnet-GenerateReport.md
>
> Orchestration Task Files table:
>   | # | Task File                              | Agent  |
>   |---|----------------------------------------|--------|
>   | 1 | CNSA-S02-01-01-Haiku-ScanControllers.md | Haiku  |
>   | 2 | CNSA-S02-01-02-Haiku-MapRoutes.md       | Haiku  |
>   | 3 | CNSA-S02-01-03-Sonnet-GenerateReport.md | Sonnet |
> ```

### Orchestration Must Link Task Files

The Orchestration file MUST include a Task Files table:

```markdown
## Task Files

| # | Task File | Agent |
|---|-----------|-------|
| 1 | [{Abbrev}-S{XX}-{YY}-01-Haiku-{Task}.md]({filename}) | Haiku |
| 2 | [{Abbrev}-S{XX}-{YY}-02-Sonnet-{Task}.md]({filename}) | Sonnet |
```

### Task Content Fidelity (cross-reference)

Task file Required Context sections and Execution Steps are subject to the rules in [`task-content-fidelity.md`](task-content-fidelity.md). The critical fidelity rules for task file authoring are:

**§9.A Required Context Fidelity (summary — see full rules in task-content-fidelity.md):**
- §9.A.1: Update Required Context when project file structure changes
- §9.A.2: No `~?` placeholders — token estimates MUST be concrete integers
- §9.A.3: Use per-file-type token rate bands (markdown ~10-14 tok/line; code ~11-16 tok/line; use `~13 tokens/line` as universal fallback; denser file types may run higher — measure if uncertain)
- §9.A.4: Re-glob live file counts before authoring (counts >1 hour old are stale)
- §9.A.5: Budget 1.5-2× for multi-source consolidation tasks (dedup overhead)
- §9.A.6: Use generator-script pattern for tasks walking ≥100 files
- §9.A.7: Declare per-artifact shape (line budget, topic) for multi-artifact outputs

**§9.B Verify-Before-Cite (summary — see full rules in task-content-fidelity.md):**
- §9.B.2: Reconcile field/column/parameter names against live source (DDL, function signatures) — use `{long_form_identifier}` vs `{abbreviated_identifier}` pair to illustrate drift
- §9.B.5: SQL column names MUST be verified against pinned schema before encoding in task brief
- §9.B.7: USED-helper enumeration: when copying helpers, enumerate USED and NOT-USED explicitly
- Schema Pin: at planning time MUST be reconciled against deployed-tier schema at execution time (see `schema-pin-requirement.md` §3)
- §9.B.2 (extended): Env vars, function signatures, and config keys verified against live source (extends `verify-before-cite.md` §9.B.2 identifier reconciliation)
- §9.B.8: MERGE/upsert task briefs MUST include Field Mapping subsection (Source Field | DDL Column | Type Cast | Default)

**Cross-sprint dependency mirroring:**

When a task's Required Context cites files from another sprint or session, the task's `Depends On` field MUST mirror those reads with `cross-sprint:` or `cross-session:` prefixes:

| Required Context references... | Depends On entry |
|--------------------------------|------------------|
| File in same session | Task number only (e.g., `01`) |
| File from earlier session in same sprint | `cross-session: {Abbrev}-S{XX}-{YY}-{##}` |
| File from earlier sprint | `cross-sprint: {Abbrev}-S{XX}-{YY}-{##}` |

> [!constraint] Cross-Sprint Dependency Mirroring
> WRONG — `Depends On` shows `-` but Required Context cites a cross-sprint file:
> ```markdown
> **Depends On:** -
> ## Required Context
> | 2 | Plans/{PlanName}/Sprint-{XX}/Session-{YY}/Outputs/{Abbrev}-S{XX}-{YY}-ResearchOutput.md | ... |
> ```
> CORRECT — `Depends On` mirrors the cross-sprint read:
> ```markdown
> **Depends On:** cross-sprint: {Abbrev}-S{XX}-{YY}-{##}
> ## Required Context
> | 2 | Plans/{PlanName}/Sprint-{XX}/Session-{YY}/Outputs/{Abbrev}-S{XX}-{YY}-ResearchOutput.md | ... |
> ```

#### Reviewer Check 037 — Cross-Sprint Required Context Mirrored in Depends On

- **Severity / Role / Type:** BLOCKER | Dependency Reviewer | NEW
- **What:** Required Context citations to files in OTHER sprints MUST be mirrored in `Depends On` with `cross-sprint:` prefix.
- **Detection:** Classify Required Context by sprint; grep `Depends On` for `cross-sprint:\s*\{Abbrev\}-S\d+`. Cross-sprint cited without prefix → BLOCKER.
- **Finding template:**
```
[BLOCKER] Cross-sprint dependency not mirrored
File: {task file path} | Location: Depends On field
Issue: Required Context cites {cross_sprint_file} but Depends On lacks cross-sprint: prefix
Fix: Add "cross-sprint: {Abbrev}-S{XX}" per references/task-file-and-tracking-requirements.md §9 | Confidence: HIGH
```

#### Reviewer Check 038 — Cross-Session Required Context Mirrored in Depends On

- **Severity / Role / Type:** BLOCKER | Dependency Reviewer | NEW
- **What:** Required Context citations to other sessions (same sprint) MUST use `cross-session:` prefix in `Depends On`.
- **Detection:** Cross-session cited without `cross-session:` prefix → BLOCKER.
- **Finding template:**
```
[BLOCKER] Cross-session dependency not mirrored
File: {task file path} | Location: Depends On field
Issue: Required Context cites {cross_session_file} but Depends On lacks cross-session: prefix
Fix: Add "cross-session: {Abbrev}-S{XX}-{YY}" per references/task-file-and-tracking-requirements.md §9 | Confidence: HIGH
```

**Post-scaffold back-propagation rule:**

When a task file is edited AFTER scaffolding (adding a Required Context entry, extending Execution Steps, or changing Expected Output), the corresponding EI section MUST be back-propagated:

1. Update task file
2. Update the EI section that maps to this task
3. Update the EI's Cross-References table if a new source is added
4. Update the EI's `Extracted from:` header if a new file is cited

Skipping any of these 4 sites is ERROR with HIGH confidence at `/planwise review` Phase 2.

**Declarative follow-up block convention:**

Task files MAY include a Declarative Follow-Up block enumerating actionable recommendations that auto-surface during backlog Phase 7 (FOLLOW-UP BLI CAPTURE):

```markdown
## Follow-Up Recommendations

> [!followup] Actionable Recommendations (auto-surfaced during backlog Phase 7)
> - Recommendation A: {description} (target: {file_path}; severity: {high|medium|low})
> - Recommendation B: {description} (target: {file_path}; severity: {high|medium|low})
```

The `> [!followup]` callout type signals to `handlers/backlog.md` Phase 7 that these recommendations should be surfaced for auto-creation as backlog items.

### Selective Helper Enumeration in Spawn Prompts

When a task brief instructs a subagent to copy helpers from a reference or template module, "verbatim from reference" is ambiguous — the subagent typically copies ALL helpers, triggering unused-symbol diagnostics and pushing borderline files past the line limit. The fix is in the spawn prompt, not the lint rule. This subsection is the canonical anchor for reviewer Check 030 (USED-helper enumeration); it elaborates the spawn-prompt discipline summarized as `verify-before-cite.md §9.B.7`.

> [!constraint] Spawn prompts MUST enumerate USED helpers explicitly rather than instruct "verbatim from reference"
> WRONG — "Helpers — copy verbatim from {reference module}." The subagent copies
> ALL helpers; unused ones trigger LSP `unused-function`-class diagnostics and
> inflate file size past project limits.
>
> CORRECT — enumerate the USED and NOT-used sets explicitly:
>
> ```
> Helpers — copy ONLY what your module uses, not all N. For Task X:
>   USED     = _to_int, _to_decimal, _to_date, _split_localized
>   NOT used = _to_bigint, _to_str, _to_str_64, _to_datetime, _to_raw_text
> Do NOT embed unused helpers.
> ```

> [!practice] Indirect-dependency audit
> Some helpers call other helpers internally (e.g., `_split_localized` may call
> `_to_str` or `_to_raw_text`). When trimming, grep for each candidate-deletion
> helper inside the file body. Indirectly-called helpers MUST be retained even
> when not used directly. Verification:
>
> ```bash
> # For each helper considered for removal:
> grep -nE "<helper>\(" <file>
> # If matches > 0 inside another retained helper's body → keep.
> ```

A related code-generation discipline applies when the LSP reports a diagnostic the agent suspects is stale:

> [!practice] Do not silence a stale linter diagnostic with an inline suppression
> Suppressing a diagnostic instead of resolving it is an anti-pattern: a stale
> diagnostic clears on the next LSP refresh, and the suppression then becomes
> permanent dead weight that also hides any future real defect on the same line.
> When a diagnostic is stale, wait for the refresh; when it is real, fix the
> underlying cause. Inline suppression directives — illustratively, an
> ignore-comment or an allow-attribute in whatever language is in use — are not a
> substitute for either. (Verify stale-vs-real per the verify-before-acting LSP
> discipline in `agent-orchestration-delegated.md` §1.18.)

### Completion Tracking (BINDING)

**After each Session completes:**
1. Update Session status to COMPLETE in Orchestration
2. Update Sprint Plan's Sessions table to mark session COMPLETE
3. Create Summary file in Outputs/
4. Document lessons learned in `LessonsLearned/LL-{NNN}-{Domain}-{Name}.md` (use template from 00-Index-LessonsLearned.md, update master table)
5. Update `LessonsLearned/00-Index-LessonsLearned.md` master table with new entries
6. If lesson severity is HIGH or lesson recurs 2+ times, consider promoting to `.claude/rules/` (update lesson status to `rule` and set `applied-as` path)

**After each Sprint completes:**
1. Update Sprint Plan status to COMPLETE
2. Update Master Plan's Sprint Overview table to mark sprint COMPLETE
3. Update Master Plan's Session Completion Tracking table

**After entire Plan completes:**
1. Update Master Plan status to COMPLETE
2. Final git commit with "Complete {PlanName} project"
3. *If Meta-Plan was used:* Meta, Scaffold, and Exec Master Plans marked COMPLETE

### Module Split Threshold

> [!practice] Module Split for Wide Dataclasses
> Adapter/client modules whose row dataclass exceeds 75-80 fields SHOULD be split into:
> - **Public module:** thin facade exposing only the fields downstream tasks consume
> - **Private companion module (`_{module}_full.{ext}`):** complete dataclass with all 75-80+ fields

When task briefs reference adapter modules, verify the field count before authoring. Modules exceeding the threshold that have NOT been split yet should be noted as candidates for splitting before the task encodes field-access patterns.

> [!hazard] Format-Restore Overhead Warning
> When splitting a wide dataclass module, verify the consumer count is >1 before splitting. Format-restore overhead (reconstituting the full dataclass for serialization from the companion module) can exceed the token savings from the split in single-consumer cases.

**Cross-reference:** [Large-File Read Tactics](session-context-budget.md#large-file-read-tactics) in `references/session-context-budget.md` — apply large-file tactics when reading the wide companion module at task execution time.

### Cross-Sprint Deferred-Finding Ownership

> [!constraint] A deferred finding MUST have a forward owning action in the gate-opening sprint, not a backward cross-reference to a CLOSED task
>
> When a sprint defers a finding because its gate (a prerequisite task in another sprint) has not yet opened, the deferring sprint's closeout MUST create a **forward owning action** in the gate-opening sprint — a success-criterion checkbox or a backlog item — so the finding has a live owner regardless of execution order.
>
> WRONG — backward-only cross-reference; the deferred finding has no live owner after the deferring sprint closes:
> ```
> Sprint-B Task 1 note: "land this BEFORE Sprint-A Task 2's finding update."
> Master Plan dependency: Sprint-B Task 1 → Sprint-A Task 2 (finding) | ⏳ Pending
> # Sprint-A ran first, deferred the finding, and CLOSED. Nothing now applies it.
> ```
>
> CORRECT — the deferring sprint records the deferral AND assigns a forward owning action in the gate-opening sprint's closeout (a success-criterion checkbox or a backlog item), so the finding has a live owner regardless of execution order:
> ```
> Sprint-A Summary: "Finding DEFERRED — gate is Sprint-B Task 1. Owner: Sprint-B closeout."
> Sprint-B Sprint-Plan Success Criteria: "[ ] After Task 1 lands, apply the deferred finding."
> Master Plan dependency row: Sprint-B Task 1 → deferred finding follow-up (owned by Sprint-B closeout).
> ```
>
> Two reinforcing safeguards: (1) a deferral note that names a CLOSED task as the future owner is a red flag — reassign to a live, not-yet-run sprint/session; (2) verify the artifact's live state before trusting "deferred" bookkeeping (a grep that returns 0 confirms the finding is genuinely unapplied, not just mis-tracked).

#### Reviewer Check 068 — Deferred Finding Owner Is a CLOSED Task

- **Severity / Role / Type:** BLOCKER | Dependency Reviewer | NEW
- **What:** A dependency or sequencing row that names a COMPLETE/CLOSED task as the owner of still-pending deferred work is stale and MUST be flagged.
- **Detection:** In the Master Plan and Sprint Plans, find rows whose status is ⏳ Pending and whose owner task is marked COMPLETE/CLOSED. Any such row → BLOCKER.
- **Finding template:**
```
[BLOCKER] Deferred-finding owner is CLOSED
File: {plan file path} | Location: {dependency/sequencing row}
Issue: Dependency row names {closed_task_id} (CLOSED) as owner of still-pending work
Fix: Reassign ownership to a live not-yet-run sprint/session per references/task-file-and-tracking-requirements.md §9 | Confidence: HIGH
```

---

*Anchor: [session-plan-requirements.md](session-plan-requirements.md) §8 Required Files Per Level, Execution Strategy (the DELEGATED-trigger canonical). Companion: [destructive-change-requirements.md](destructive-change-requirements.md).*
