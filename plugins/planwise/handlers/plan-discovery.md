---
description: Discovery Workflow (Meta-Plan creation) for /planwise plan — reads source material, cross-references it, and produces Consolidated Context Parts
---

# Handler: /planwise plan — Discovery Workflow

**Loaded by:** [`handlers/plan.md`](plan.md) Step 0, when Discovery mode is detected.

**When:** Total context exceeds ~100K tokens, or the user explicitly requests a Meta-Plan. The Discovery phase reads source material, cross-references it, and produces Consolidated Context Parts — structured, full-detail specification documents organized by execution scope.

**Output:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` files

> [!constraint] Discovery ≠ Standard Planning
> WRONG: Create a standard execution plan inside `Meta-{Abbrev}/` with implementation tasks and a different abbreviation.
>
> CORRECT: Create a **discovery plan** inside `Meta-{Abbrev}/` with **reading and consolidation tasks** that produce Consolidated Context Parts. The abbreviation MUST match the parent project. The purpose is context discovery and consolidation — NOT implementation.

## Discovery Step 1: Gather Source Inventory

**CONFIRM block (per `references/scaffolding-hygiene.md` §1):**

Before gathering source inventory, output the Discovery context confirmation:

> [!template] Discovery Context Confirmation
> ```
> CONTEXT LOADED — DISCOVERY MODE
> Workflow: Discovery (Meta-Plan creation)
> Trigger: {indicator that triggered Discovery mode}
> Plugin references loaded: {list of loaded conditional refs}
> Next Action: Gather source inventory for {abbreviation}
> ```

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion`: "Confirm Discovery mode for this plan?"
(Auto-default: proceed; user can switch to Standard or Scaffolding.)

Then proceed with the source inventory questions below.

<!-- AUTO-MODE: critical -->
<!-- All Discovery Step 1 questions (Project name, Abbreviation, Vision, Source files, Domains, Expected output) are CRITICAL per S03-03 audit table — no safe inference. -->
Use `AskUserQuestion` to collect:

**Question 1: Project Details**
- What is the project name? (e.g., "DataMigration", "UserAuthentication") — pre-fill from `$1` if provided
- What is the 2-4 character abbreviation? (e.g., "DM", "UA") — this abbreviation will be used across ALL three phases (Meta, Scaffold, Exec)
- Briefly describe the project vision (1-2 sentences)

**Question 2: Source Material**
- What source files/documents need to be read and consolidated? (paths, URLs, or descriptions)
- Are there specific domains or topics to organize findings by?
- What should the consolidated output contain? (e.g., schema definitions, API contracts, design decisions)

## Discovery Step 2: Validate and Design

1. **Validate abbreviation:** 2-4 characters, unique (check `{plans_dir}` for existing). Follow the [Abbreviation Validation Protocol](plan.md#abbreviation-length-validation) — never silently truncate or adjust
2. **Inventory source files:** List all source files with estimated line counts and token costs (~13 tokens/line)
3. **Confirm context exceeds 100K:** Sum total source tokens. If < 100K, recommend Standard plan instead
4. **Group sources by domain/topic:** Each group becomes a discovery sprint or session focus area
5. **Define expected Consolidated Context Parts:** One part per execution scope (each part ≤ 500 lines), with anticipated `Scope:` values

## Discovery Step 3: Create Folder Structure

Create the Meta-Plan structure under `{plans_dir}`:

```
{plans_dir}/{PlanName}/
└── Meta-{Abbrev}/
    ├── {Abbrev}-META-Master-Plan.md
    ├── Sprint-01-Discovery/
    │   ├── {Abbrev}-META-S01-Sprint-Plan.md
    │   └── Session-01-{SessionName}/
    │       ├── {Abbrev}-S01-01-Orchestration.md
    │       ├── {Abbrev}-S01-01-Recovery.md
    │       ├── {Abbrev}-S01-01-{##}-{Agent}-{Task}.md
    │       └── Outputs/
    └── Outputs/                                # Consolidated Context Parts go here
```

**Naming rules** (see [Meta-Plan File Naming](plan.md#meta-plan-file-naming) for full reference):
- Master Plan: `{Abbrev}-META-Master-Plan.md` (META infix distinguishes from Execution Plan)
- Sprint Plans: `{Abbrev}-META-S{XX}-Sprint-Plan.md` (META infix)
- Orchestration/Recovery: standard naming, no META infix (structural files)
- Task outputs: `{Abbrev}-META-S{XX}-{YY}-{TaskOutput}.md` (in session `Outputs/`)
- Consolidated outputs: `{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md` (in `Meta-{Abbrev}/Outputs/`)

## Discovery Step 4: Generate Meta-Plan Files

Use standard templates with the following overrides:

**Master Plan overrides:**
- Vision: "Context discovery and consolidation for {PlanName}" — NOT implementation
- Purpose: "Read source material, cross-reference findings, and produce Consolidated Context Parts"
- Success Criteria: Define what each Consolidated Context Part must contain
- List all source files/documents to be read (by reference, not loaded into the Master Plan)
- Expected output: Number and topics of Consolidated Context Parts

**Sprint Plan overrides:**
- Objective: "Gather and consolidate context for {domain/topic}" — NOT "implement"
- Sessions focused on reading and cross-referencing, not code generation

**Orchestration overrides:**
- Execution Strategy: **DELEGATED** (mandatory for META sessions — each agent needs fresh context to read sources)
- Context Boundary: Orchestrator reads plan files only; source material is read by task agents

**Task design rules:**
- Tasks are **reading and consolidation** tasks, not implementation tasks
- Each task reads a subset of source files and produces organized findings
- The **final task** in a session (or a dedicated consolidation session) combines findings into Consolidated Context Parts
- Agent assignments: Use **Opus** for cross-referencing and consolidation tasks (complex analysis); use **Sonnet** for straightforward reading tasks

## Discovery Step 5: Define Consolidation Tasks

The most critical part of the Discovery plan. The final task(s) must produce Consolidated Context Parts with this structure:

**Each Consolidated Context Part MUST have:**
- A header with `Scope:` field identifying which execution sprint it feeds
- A `What This Enables` section describing what downstream work this context supports
- Cross-references to other parts where topics overlap
- Full substantive detail — consolidation means organize and deduplicate, NOT summarize
- ≤ 500 lines per part; use multiple parts as needed

**Task file for a consolidation task should specify:**
- **Objective:** "Consolidate findings from {sources} into Consolidated Context Part(s) for {scope}"
- **Required Context:** The reading task outputs from earlier tasks in the session
- **Expected Output:** `Meta-{Abbrev}/Outputs/{Abbrev}-Consolidated-Context-Part-{N}-{Topic}.md`
- **Success Criteria:** All source material covered, no substantive content lost, organized by execution scope

## Discovery Step 6: Validation

Standard checklist applies, plus:

```
[ ] Plan is inside Meta-{Abbrev}/ folder
[ ] Master Plan and Sprint Plans include META infix (e.g., {Abbrev}-META-Master-Plan.md)
[ ] Orchestration and Recovery files use standard naming (no META infix)
[ ] Abbreviation matches the project abbreviation (not a new one)
[ ] Master Plan purpose is "discovery and consolidation" (NOT implementation)
[ ] Tasks are reading/consolidation tasks (NOT implementation tasks)
[ ] Execution Strategy is DELEGATED
[ ] Final task(s) produce Consolidated Context Parts in Meta-{Abbrev}/Outputs/
[ ] Expected Consolidated Context Parts are defined with Scope values
[ ] Source files are listed by reference in Master Plan
[ ] Each Consolidated Context Part target is ≤ 500 lines
[ ] Plans index updated with new row
```

## Discovery Step 7: Output Confirmation

```
META-PLAN CREATED: {PlanName} (Discovery Phase)

**Abbreviation:** {ABBREV}
**Location:** {plans_dir}/{PlanName}/Meta-{Abbrev}/
**Phase:** 1 of 3 (Discovery → Scaffolding → Execution)

**Source Files:** {N} files (~{X}K total tokens)
**Expected Output:** {N} Consolidated Context Parts in Meta-{Abbrev}/Outputs/

**Files Created:**
- {Abbrev}-META-Master-Plan.md
- Sprint-01-Discovery/{Abbrev}-META-S01-Sprint-Plan.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-Orchestration.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-Recovery.md
- Sprint-01-Discovery/Session-01-{Name}/{Abbrev}-S01-01-{##}-{Agent}-{Task}.md (x{N} task files)
- Sprint-01-Discovery/Session-01-{Name}/Outputs/ (folder)
- Outputs/ (folder for Consolidated Context Parts)

**Next Steps:**
1. Review the Meta-Plan files
2. Execute Discovery sessions with `/planwise run`
3. After Discovery completes, scaffold the Execution Plan with `/planwise plan --scaffold`
```

After the confirmation, proceed to [handlers/plan.md Step 10: Plan Review Gate](plan.md#step-10-plan-review-gate).

---

**Back to:** [handlers/plan.md](plan.md)
