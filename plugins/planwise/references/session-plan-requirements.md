---
description: Required file specifications per plan level, task file templates, and completion tracking
---

# Session Plan Requirements

**Purpose:** Required files per plan level, task file template, and completion tracking rules.
**Companion files:** [session-planning-protocol.md](session-planning-protocol.md) (protocol, hierarchy, delegation), [session-context-budget.md](session-context-budget.md) (token budget, context loading)

---

## 8. Required Files Per Level

### Plan Type Decision

| Context Needed | Plan Type | Structure |
|----------------|-----------|-----------|
| < `meta_plan_threshold` | Standard (Execution Plan only) | Single plan with standard hierarchy |
| > `meta_plan_threshold` | Meta-Plan + Execution Plan | Two-phase: Discovery → Execution |

`meta_plan_threshold` is tier-aware: 100K on Pro, 500K on Max. Read `context.context_window` from `config.yaml` and resolve per `references/session-context-budget.md` §5 Threshold Formulas.

---

### Meta-Plan Requirements (Discovery Phase)

*Only needed when total context > `meta_plan_threshold` (100K on Pro, 500K on Max)*

**Meta-Plan Master Plan MUST Have:**
- Purpose: Context discovery and consolidation (not implementation)
- List of source files/documents to be read (by reference, not loaded)
- Expected consolidated output description
- Success Criteria: What the consolidated artifact must contain

**Meta-Plan Sprint MUST Have:**
- Objective: Gather and consolidate specific context
- Sessions focused on reading and cross-referencing
- Clear output artifact defined

**Meta-Plan Session MUST Have:**
- Orchestration with agent assignments (agents read source files)
- Recovery file
- Outputs/ folder containing: **Consolidated Context Document**

**Consolidated Context Documents (KEY ARTIFACTS):**
- Contain findings from all source files read by agents — FULL DETAIL, not summarized
- Cross-references resolved, duplicates removed, trivial information pruned
- Decisions/constraints identified
- Organized by domain or execution unit (one part per sprint scope)
- Become the PRIMARY INPUT for the Scaffolding Phase
- Live at: `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md`
- Each part ≤ 500 lines; use as many parts as needed for full coverage

**Consolidation ≠ Summarization.** Consolidation means: organize, deduplicate, and structure. If source material is unique and substantive, it MUST appear in the consolidated output. Only remove true duplicates and trivial/redundant information.

---

### Scaffolding Phase Requirements (Plan Writing)

*Only needed when Meta-Plan was used. Bridges Discovery → Execution.*

**Purpose:** Read Consolidated Context parts and produce two things: (1) sprint-scoped **Execution Inputs** and (2) all Execution Plan files (sprint plans, sessions, task files).

**How It Works:**
- Read Consolidated Context parts and map each to sprint scope
- For each sprint, **extract** relevant content into an Execution Input file (sprint-scoped, self-contained)
- Create sprint's folder, Execution Input, sprint plan, session folders, orchestration, recovery, and task files
- Task files reference their sprint's Execution Input — NOT the original Consolidated Context parts

**Execution Inputs (KEY ARTIFACT):**
- One per sprint: `{Abbrev}-S{XX}-Execution-Input.md` in the sprint folder
- Contains content **extracted** from Consolidated Context parts, reorganized by sprint scope
- Each section maps to specific tasks (noted in section header)
- Agents executing tasks read ONLY their sprint's Execution Input — self-contained
- Cross-sprint reference parts: extract only the portions relevant to that sprint
- 500-line limit per file; split into parts if needed: `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md`
- MUST include Cross-References table tracing each section back to its source part
- Cross-References use `Spec #{N} ({filename.md})` format — global number + exact filename
- Every file cited in Cross-References MUST appear in the `Extracted from:` header
- Cross-sprint sources (used by multiple sprints) are listed in each EI's header like any other source

**Global Source Map:** When using global numbering for spec outputs (recommended for multi-sprint plans), the Master Plan MUST include a Global Source Map table assigning each spec output a number, its primary sprint, and any additional sprints that use it.

**Multi-Tier Discovery Extraction (PLG-008):**

When the source material is a Meta-Plan Discovery output, EI extraction MUST consume THREE tiers:

- **Tier 1:** Raw task outputs (per-task Outputs/ files in `Meta-{Abbrev}/Sprint-{XX}-Discovery/Session-{YY}-*/Outputs/`)
- **Tier 2:** Per-sprint consolidated context parts (`Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md`)
- **Tier 3:** Final consolidated layer (if produced — typically a Triage or Cross-Reference part)

Extraction MUST cite all three tiers in the EI's `Extracted from:` header when applicable. Skipping Tier 1 is BLOCKER — raw outputs carry detail that consolidated parts shed during compression passes.

> [!constraint] Multi-Tier EI Extraction
> WRONG — EI cites only the final consolidated layer (Tier 2/3); Tier 1 raw outputs ignored:
> ```
> **Extracted from:** Spec #1 (PPU-Consolidated-Context-Part-1.md), Spec #2 (PPU-Consolidated-Context-Part-2.md)
> ```
> CORRECT — EI cites all tiers with Tier 1 raw outputs explicitly:
> ```
> **Extracted from:** Spec #1 (PPU-META-S01-01-PlanwiseRulesInventory.md) [Tier 1 raw],
>   Spec #2 (PPU-META-S01-02-PLGPromotionsInventory.md) [Tier 1 raw],
>   Spec #3 (PPU-Consolidated-Context-Part-1.md) [Tier 2 consolidated],
>   Spec #4 (PPU-Consolidated-Context-Part-3-EnforcementLayer.md) [Tier 2 consolidated]
> ```

**Deferred/Out-of-Scope Log Requirement:**

Every scaffolded sprint MUST include a `{Abbrev}-S{XX}-Deferred-OutOfScope-Log.md` in the sprint folder enumerating:
- Content from Tier 1/2/3 NOT extracted into this sprint's EI
- Rationale for deferral (out of sprint scope, belongs to a different sprint, truly out of scope)
- Target sprint or "Out of scope" designation

**EI Bidirectional Consistency (BB-031 P4):**

Every Spec listed in the EI's `Extracted from:` header MUST appear in at least one Cross-References row. And conversely: every Cross-References row's source citation MUST appear in the `Extracted from:` header. Bidirectional inconsistency is WARNING with HIGH confidence at `/planwise review` Phase 2.

> [!constraint] EI Header ↔ Cross-References Table Consistency
> WRONG — `Extracted from:` cites Spec #2 but Cross-References table has no row citing Spec #2:
> ```markdown
> **Extracted from:** Spec #1, Spec #2 ({filename.md}), Spec #5
>
> | Section | Source | ... |
> | §1 Auth design | Spec #1 §3 | ... |
> | §2 API routes  | Spec #5 §1 | ... |
> ```
> (Spec #2 is listed in header but never appears in the table — where was it used?)
>
> CORRECT — every header entry appears in at least one table row, and vice versa:
> ```markdown
> **Extracted from:** Spec #1, Spec #2 ({filename.md}), Spec #5
>
> | Section | Source | ... |
> | §1 Auth design | Spec #1 §3 | ... |
> | §2 API routes  | Spec #2 §4 ({filename.md}) | ... |
> | §3 Data model  | Spec #5 §1 | ... |
> ```

> WRONG — Cross-References table cites Spec #7 but `Extracted from:` header does not list Spec #7:
> ```markdown
> **Extracted from:** Spec #1, Spec #2, Spec #5
> | §4 Legacy compat | Spec #7 §2 | ... |   ← Spec #7 not in header
> ```
> CORRECT — add Spec #7 to header OR remove from table:
> ```markdown
> **Extracted from:** Spec #1, Spec #2, Spec #5, Spec #7 ({filename.md})
> | §4 Legacy compat | Spec #7 §2 | ... |
> ```

> When a Spec is referenced ONLY for background context (not as the source of any extracted section), it MAY be omitted from `Extracted from:` IF the table row carries an `(informational-only)` annotation:
> ```markdown
> | §4 Legacy compat | Spec #7 §2 (informational-only) | Background reference, not extracted |
> ```

**Three-Step Scaffolding Procedure for EI Consistency (BB-031 P6):**

1. Author EI sections with full content
2. Build Cross-References table mapping each section to its source citation
3. Reconcile `Extracted from:` header: list every source cited in the table (exact filename); annotate informational-only rows where applicable

**Reviewer note (BB-031 P7):** `/planwise review` Phase 2 reports EI header ↔ Cross-References inconsistency as WARNING with HIGH confidence.

**Execution Input ≠ Summary.** Extraction means: select, reorganize, and scope. If source content is needed by the sprint, it MUST appear in the Execution Input verbatim. Only omit content irrelevant to that sprint's tasks.

**Scaffolding Session MUST Have:**
- Orchestration listing which spec parts map to which sprints
- One task per sprint to scaffold (agent creates Execution Input + all plan files for that sprint)
- Recovery file tracking which sprints have been scaffolded

**Output:** A fully populated `Exec-{Abbrev}/` folder with Execution Inputs, sprint plans, sessions, and task files ready to run.

---

### Execution Plan Requirements (Standard Structure)

*Used for all plans, or as Phase 3 after Meta-Plan + Scaffolding*

**Master Plan MUST Have:**
- Vision (WHY this plan exists)
- Sprint Overview table
- Session Completion Tracking table
- Success Criteria (measurable)
- Dependencies
- *If Meta-Plan was used:* Reference to Consolidated Context Parts as input (created during Scaffolding Phase)

**Sprint Plan MUST Have:**
- Sprint Objective
- Sessions table with token estimates
- Prerequisites
- Success Criteria
- *If scaffolded:* Execution Input file in sprint folder (extracted from Consolidated Context parts)

**Session MUST Have:**
- Orchestration file (task list, agent plan, success criteria)
- Recovery file (initialized)
- Outputs/ folder

**Each Task MUST Have:**
- **Individual Task file** (one file per task, NEVER combined)
- Task number in filename (01, 02, 03...)
- Agent assignment
- Token estimate
- Dependencies documented
- Expected output
- **Link in Orchestration file** (Task Files table)

### Execution Strategy (Set by Planner)

The planner (`/planwise plan`) MUST evaluate Execution Strategy triggers and declare the mode in the Orchestration file. This is a **planning decision**, not an execution-time decision.

| Mode | When | Orchestrator Reads | Tasks Run By |
|------|------|-------------------|--------------|
| DIRECT | All Haiku/Sonnet tasks, total context <80K | All Required Context | Orchestrator directly |
| DELEGATED | Any DELEGATED trigger present (see below) | Plan files only | Subagents (fresh context each) |

**Mandatory DELEGATED triggers (any ONE = DELEGATED required):**
- Session has 2 or more Opus tasks
- Session is part of a META Discovery phase
- Any single task estimates >50K token context load
- Sequential tasks where one task's output is the next task's input (output-chaining)

**Planning responsibility:** When the planner declares DELEGATED:
1. Orchestration Required Context lists ONLY plan files
2. Heavy context files appear ONLY in task file Required Context sections
3. Execution Strategy section includes Context Boundary subsection
4. The executor follows the declared strategy — no runtime inference

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

**Scope of BLOCKING enforcement:** The BLOCKING severity applies ONLY to tasks that touch code, tests, or schemas (i.e., tasks whose Expected Output or Execution Steps create or modify files with extensions in the `templates/task-file.md` §Per-File-Type Commands table — `.py` / `.ipynb` / `.sql` / `.cs` / `.cshtml` / `.ts` / `.tsx` / `.{ext}` and equivalents). For purely documentary tasks (markdown edits, decision-only Opus tasks, research-and-report Sonnet tasks), Verification Commands MAY be omitted entirely — but the omission MUST be marked with a `<!-- VERIFICATION: not-applicable (reason) -->` HTML comment so the reviewer can confirm the choice was intentional rather than an oversight. The `handlers/plan.md` Step 8e (Populate Verification Commands) populates the section for runnable-artifact tasks; the `handlers/review.md` Error Pattern Catalog rows 34/35/36 enforce this at review time.

> [!constraint] BLOCKING Severity — Source PLG-003 Discipline
> WRONG — Verification Commands enforcement left at WARNING, allowing plans to ship with blank `{cmd_before_1}` / `{cmd_after_1}` placeholders:
> ```
> | Severity | Reviewer Action       |
> | WARNING  | Flag as missing       |
> ```
> CORRECT — BLOCKING for runnable-artifact tasks (source PLG-003 §3C), with explicit `<!-- VERIFICATION: not-applicable -->` escape hatch for documentation/decision-only tasks:
> ```
> | Severity   | Reviewer Action                                           |
> | BLOCKING   | Block plan approval until populated or explicitly exempted |
> ```
> The escape hatch keeps the rule humane (pure-doc tasks aren't penalized) without weakening enforcement on tasks that actually produce runnable artifacts. This check is BLOCKING rather than a warning: the source PLG-003 spec called for BLOCKING enforcement, the task-file template has per-file-type infrastructure, the plan-handler Step 8e populates it, and the escape hatch covers legitimate exemptions.

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
- §9.B.2 (extended): Env vars, function signatures, and config keys verified against live source (extends `task-content-fidelity.md` §9.B.2 identifier reconciliation)
- §9.B.8: MERGE/upsert task briefs MUST include Field Mapping subsection (Source Field | DDL Column | Type Cast | Default)

**Cross-sprint dependency mirroring (PLG-007 S2):**

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
> | 2 | Plans/{PlanName}/Sprint-01/Session-02/Outputs/{Abbrev}-S01-02-ResearchOutput.md | ... |
> ```
> CORRECT — `Depends On` mirrors the cross-sprint read:
> ```markdown
> **Depends On:** cross-sprint: {Abbrev}-S01-02-03
> ## Required Context
> | 2 | Plans/{PlanName}/Sprint-01/Session-02/Outputs/{Abbrev}-S01-02-ResearchOutput.md | ... |
> ```

**Post-scaffold back-propagation rule (PLG-007 S5):**

When a task file is edited AFTER scaffolding (adding a Required Context entry, extending Execution Steps, or changing Expected Output), the corresponding EI section MUST be back-propagated:

1. Update task file
2. Update the EI section that maps to this task
3. Update the EI's Cross-References table if a new source is added
4. Update the EI's `Extracted from:` header if a new file is cited

Skipping any of these 4 sites is ERROR with HIGH confidence at `/planwise review` Phase 2.

**Declarative follow-up block convention (PLG-018):**

Task files MAY include a Declarative Follow-Up block enumerating actionable recommendations that auto-surface during backlog Phase 7 (FOLLOW-UP BLI CAPTURE):

```markdown
## Follow-Up Recommendations

> [!followup] Actionable Recommendations (auto-surfaced during backlog Phase 7)
> - Recommendation A: {description} (target: {file_path}; severity: {high|medium|low})
> - Recommendation B: {description} (target: {file_path}; severity: {high|medium|low})
```

The `> [!followup]` callout type signals to `handlers/backlog.md` Phase 7 that these recommendations should be surfaced for auto-creation as backlog items.

### Selective Helper Enumeration in Spawn Prompts

When a task brief instructs a subagent to copy helpers from a reference or template module, "verbatim from reference" is ambiguous — the subagent typically copies ALL helpers, triggering unused-symbol diagnostics and pushing borderline files past the line limit. The fix is in the spawn prompt, not the lint rule. This subsection is the canonical anchor for reviewer Check 030 (USED-helper enumeration); it elaborates the spawn-prompt discipline summarized as `task-content-fidelity.md §9.B.7`.

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
> discipline in `agent-orchestration.md`.)

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

### Module Split Threshold (PLG-016 Fragment B)

> [!practice] Module Split for Wide Dataclasses
> Adapter/client modules whose row dataclass exceeds 75-80 fields SHOULD be split into:
> - **Public module:** thin facade exposing only the fields downstream tasks consume
> - **Private companion module (`_{module}_full.{ext}`):** complete dataclass with all 75-80+ fields

When task briefs reference adapter modules, verify the field count before authoring. Modules exceeding the threshold that have NOT been split yet should be noted as candidates for splitting before the task encodes field-access patterns.

> [!hazard] Format-Restore Overhead Warning
> When splitting a wide dataclass module, verify the consumer count is >1 before splitting. Format-restore overhead (reconstituting the full dataclass for serialization from the companion module) can exceed the token savings from the split in single-consumer cases.

**Cross-reference:** `references/agent-orchestration.md §13 Large-File Read Tactics` — apply large-file tactics when reading the wide companion module at task execution time.

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md)*
