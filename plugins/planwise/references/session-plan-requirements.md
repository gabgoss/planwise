---
description: Required file specifications per plan level and the DELEGATED-trigger canonical (Execution Strategy)
---

# Session Plan Requirements

**Purpose:** Required files per plan level and the DELEGATED-trigger canonical (Execution Strategy — the four mandatory triggers).
**Companion files:** [session-planning-protocol.md](session-planning-protocol.md) (protocol, hierarchy, delegation), [session-context-budget.md](session-context-budget.md) (token budget, context loading), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (task file template, completion tracking), [destructive-change-requirements.md](destructive-change-requirements.md) (destructive-path & config-gated change requirements)

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

**Multi-Tier Discovery Extraction:**

When the source material is a Meta-Plan Discovery output, EI extraction MUST consume THREE tiers:

- **Tier 1:** Raw task outputs (per-task Outputs/ files in `Meta-{Abbrev}/Sprint-{XX}-Discovery/Session-{YY}-*/Outputs/`)
- **Tier 2:** Per-sprint consolidated context parts (`Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md`)
- **Tier 3:** Final consolidated layer (if produced — typically a Triage or Cross-Reference part)

Extraction MUST cite all three tiers in the EI's `Extracted from:` header when applicable. Skipping Tier 1 is BLOCKER — raw outputs carry detail that consolidated parts shed during compression passes.

> [!constraint] Multi-Tier EI Extraction
> WRONG — EI cites only the final consolidated layer (Tier 2/3); Tier 1 raw outputs ignored:
> ```
> **Extracted from:** Spec #1 (PI-Consolidated-Context-Part-1.md), Spec #2 (PI-Consolidated-Context-Part-2.md)
> ```
> CORRECT — EI cites all tiers with Tier 1 raw outputs explicitly:
> ```
> **Extracted from:** Spec #1 (PI-META-S01-01-SourceInventory.md) [Tier 1 raw],
>   Spec #2 (PI-META-S01-02-DependencyInventory.md) [Tier 1 raw],
>   Spec #3 (PI-Consolidated-Context-Part-1.md) [Tier 2 consolidated],
>   Spec #4 (PI-Consolidated-Context-Part-3-EnforcementLayer.md) [Tier 2 consolidated]
> ```

**Deferred/Out-of-Scope Log Requirement:**

Every scaffolded sprint MUST include a `{Abbrev}-S{XX}-Deferred-OutOfScope-Log.md` in the sprint folder enumerating:
- Content from Tier 1/2/3 NOT extracted into this sprint's EI
- Rationale for deferral (out of sprint scope, belongs to a different sprint, truly out of scope)
- Target sprint or "Out of scope" designation

**EI Bidirectional Consistency:**

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

**Three-Step Scaffolding Procedure for EI Consistency:**

1. Author EI sections with full content
2. Build Cross-References table mapping each section to its source citation
3. Reconcile `Extracted from:` header: list every source cited in the table (exact filename); annotate informational-only rows where applicable

**Reviewer note:** `/planwise review` Phase 2 reports EI header ↔ Cross-References inconsistency as WARNING with HIGH confidence.

#### Reviewer Check 009 — EI Bidirectional Source/Cross-Reference Consistency

- **Severity / Role / Type:** WARNING (HIGH confidence) | EI Reviewer | NEW
- **What:** Every Spec in EI header `Extracted from:` MUST appear in ≥1 Cross-References row AND vice versa.
- **Detection:** Open EI; extract header source list; extract Cross-References rows; set-diff bidirectionally. Header → row missing = WARNING. Row → header missing = WARNING.
- **Finding template:**
```
[WARNING] EI bidirectional consistency violation
File: {EI file path} | Location: EI header Extracted from vs Cross-References
Issue: {direction_description} (e.g., "Spec #N in header but absent from Cross-References")
Fix: Reconcile per references/session-plan-requirements.md §8 | Confidence: HIGH
```

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

> [!constraint] Canonical: the four mandatory DELEGATED triggers below are normatively defined HERE; other files (e.g. `agent-orchestration-delegated.md` §1.1) cite this section rather than restating the list.

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

*Companion files: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (§9 Task Files and Completion Tracking), [destructive-change-requirements.md](destructive-change-requirements.md) (§10 Destructive-Path & Config-Gated Change Requirements)*
