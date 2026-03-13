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
| < 100K | Standard (Execution Plan only) | Single plan with standard hierarchy |
| > 100K | Meta-Plan + Execution Plan | Two-phase: Discovery → Execution |

---

### Meta-Plan Requirements (Discovery Phase)

*Only needed when total context > 100K*

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

## Notes for Agent

{Special instructions, edge cases, or context the agent needs}
```

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

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md)*
