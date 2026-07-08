---
description: Plan hierarchy, naming conventions, agent delegation, recovery protocol, checklists, and session workflow
---

# Session Planning Protocol

**Purpose:** Enforce development best practices when creating or executing plans.

## Table of Contents

- [Status Field](#status-field)
- [1. Plan Hierarchy](#1-plan-hierarchy-binding)
- [2. Naming Conventions](#2-naming-conventions-binding)
- [3. Agent Delegation](#3-agent-delegation-binding)
- [4. Recovery Protocol](#4-recovery-protocol-binding)
- [5. Token Budget](session-context-budget.md#5-token-budget)
- [6. Context Loading Strategy](session-context-budget.md#6-context-loading-strategy)
- [7. Context Conservation](session-context-budget.md#7-context-conservation)
- [8. Required Files Per Level](session-plan-requirements.md#8-required-files-per-level)
- [9. Task Files and Completion Tracking](session-plan-requirements.md#9-task-files-and-completion-tracking)
- [10. Pre-Session Validation Checklist](#10-pre-session-validation-checklist)
- [11. Post-Session Checklist](#11-post-session-checklist)
- [12. Git Workflow](#12-git-workflow)
- [13. READ-CONFIRM-ACT Protocol](#13-read-confirm-act-protocol)
- [Quick Reference](#quick-reference)
- [Templates](#templates)

**Companion files:**
- [session-context-budget.md](session-context-budget.md) — Token budget, context loading strategy, conservation (Sections 5-7)
- [session-plan-requirements.md](session-plan-requirements.md) — Required files per level, task file template, completion tracking (Sections 8-9)
- [scaffolding-hygiene.md](scaffolding-hygiene.md) — Scaffolding hygiene rules: Meta-Plan source detection, folder naming, abbreviation validation, sprint status defaults, Outputs/ creation, sequential-sprint prerequisites, parallel-scaffold deviation classes, plan-sizing expansion ratio, cohort token-uplift
- [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md) — Discovery scope rigor and cross-layer enforcement: count by execution, persist IDs, binding-refinement echo, enforceable-surface checks, verbatim-quote exit criteria, design-extension traceability, cross-tier audit triage
- [ei-fidelity.md](ei-fidelity.md) — Execution Input fidelity: EI-as-archival transform, severity vocabulary, threshold alignment, UNCONFIRMED caveat enforcement, cross-tier preservation, citation propagation, token reconciliation gate
- [task-content-fidelity.md](task-content-fidelity.md) — Task file content fidelity: Required Context freshness, no `~?` placeholders, token rate bands, verify-before-cite discipline (14 rules including Schema Pin, env vars, Field Mapping)
- [schema-pin-requirement.md](schema-pin-requirement.md) — Schema Pin requirement: pin construction recipe, pin format template, plan-review enforcement

---

## Status Field

The `/planwise plan` command sets `Status: READY_TO_EXECUTE` in the Master Plan when complete.

This status is the **execution gate** checked by `/execute` before any work begins.

**Recommended:** Run `/plan-review` between planning and execution. The review validates structure, references, and content — catching errors before they cost execution tokens. Optional but recommended for all plans with 2+ sprints or Execution Inputs.

---

## When These Rules Apply

These rules apply when:
- Creating a new Master Plan, Sprint, or Session
- Executing an existing session
- Working with Orchestration or Recovery files
- Any task involving plan structure or session management

---

## 1. Plan Hierarchy (BINDING)

Every plan MUST follow this 4-level hierarchy:

```
Master Plan ({Abbrev}-Master-Plan.md)
└── Sprint ({Abbrev}-S{XX}-Sprint-Plan.md)
    └── Session (Session-{YY}-{Name}/)
        ├── {Abbrev}-S{XX}-{YY}-Orchestration.md
        ├── {Abbrev}-S{XX}-{YY}-Recovery.md
        ├── {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{Task}.md   # One file per task
        └── Outputs/
            └── {Abbrev}-S{XX}-{YY}-Summary.md
```

> [!constraint] Plan Hierarchy — No Level Skipping
> WRONG — task files created directly inside plan root, sprint level skipped, session folder absent:
> ```
> RVR/
> ├── RVR-Master-Plan.md
> ├── RVR-01-Haiku-ScanViews.md          ← task at plan root (no sprint, no session)
> └── Outputs/
>     └── RVR-Summary.md
> ```
> CORRECT — all 4 levels present: Master Plan → Sprint → Session → Task files:
> ```
> RVR/
> ├── RVR-Master-Plan.md
> └── Sprint-01-ScanAndMap/
>     ├── RVR-S01-Sprint-Plan.md
>     └── Session-01-Scan/
>         ├── RVR-S01-01-Orchestration.md
>         ├── RVR-S01-01-Recovery.md
>         ├── RVR-S01-01-01-Haiku-ScanViews.md
>         ├── RVR-S01-01-02-Sonnet-MapControllers.md
>         └── Outputs/
>             └── RVR-S01-01-Summary.md
> ```

---

## 2. Naming Conventions (BINDING)

### Plan Abbreviation
- **2-4 characters**, unique across project
- Examples: `DVD`, `CI`, `CNSA`, `PI`

### File Naming

| Type | Pattern | Example |
|------|---------|---------|
| Master Plan | `{Abbrev}-Master-Plan.md` | `PI-Master-Plan.md` |
| Sprint Plan | `{Abbrev}-S{XX}-Sprint-Plan.md` | `PI-S01-Sprint-Plan.md` |
| Orchestration | `{Abbrev}-S{XX}-{YY}-Orchestration.md` | `PI-S01-01-Orchestration.md` |
| Recovery | `{Abbrev}-S{XX}-{YY}-Recovery.md` | `PI-S01-01-Recovery.md` |
| Task (Haiku) | `{Abbrev}-S{XX}-{YY}-{##}-Haiku-{Task}.md` | `PI-S01-01-01-Haiku-Verify.md` |
| Task (Sonnet) | `{Abbrev}-S{XX}-{YY}-{##}-Sonnet-{Task}.md` | `PI-S01-01-02-Sonnet-Generate.md` |
| Task (Opus) | `{Abbrev}-S{XX}-{YY}-{##}-Opus-{Task}.md` | `PI-S01-01-03-Opus-Design.md` |
| Summary | `{Abbrev}-S{XX}-{YY}-Summary.md` | `PI-S01-01-Summary.md` |
| Execution Input | `{Abbrev}-S{XX}-Execution-Input.md` | `PI-S01-Execution-Input.md` |
| Execution Input (multi-part) | `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` | `PI-S01-Execution-Input-Part-1-Schema.md` |

**Task Number Convention:**
- `{##}` = Two-digit task number (01, 02, 03...)
- Task numbers match the `#` column in the Orchestration task list
- One file per task - NEVER combine multiple tasks into one file

> [!constraint] File Naming Convention
> WRONG — lowercase, no plan abbreviation, missing agent type, missing task number:
> ```
> Sprint1-Session1.md
> planwise-task1.md
> task-validate-schema.md
> Orchestration.md
> ```
> CORRECT — plan abbreviation prefix, sprint/session numbers, agent type, sequential task number:
> ```
> MSQ-Master-Plan.md
> MSQ-S01-Sprint-Plan.md
> MSQ-S01-02-Orchestration.md
> MSQ-S01-02-Recovery.md
> MSQ-S01-02-01-Haiku-ValidateSchema.md
> MSQ-S01-02-02-Sonnet-GenerateEntities.md
> CI-S03-01-03-Opus-DesignModel.md
> ```

### Folder Structure

#### Standard Plan (< 100K context)

```
Plans/{PlanName}/
├── {Abbrev}-Master-Plan.md
├── Sprint-{XX}-{Name}/
│   ├── {Abbrev}-S{XX}-Sprint-Plan.md
│   └── Session-{YY}-{Name}/
│       ├── {Abbrev}-S{XX}-{YY}-Orchestration.md
│       ├── {Abbrev}-S{XX}-{YY}-Recovery.md
│       └── Outputs/
```

#### With Meta-Plan (> 100K context needed)

Three-phase approach: **Discovery → Scaffolding → Execution**

```
Plans/{PlanName}/
├── Meta-{Abbrev}/                              # Phase 1: Discovery
│   ├── {Abbrev}-META-Master-Plan.md
│   ├── Sprint-01-Discovery/
│   │   ├── {Abbrev}-META-S01-Sprint-Plan.md
│   │   └── Session-{YY}-{Name}/
│   │       ├── Orchestration, Recovery, Task files...
│   │       └── Outputs/                        # Task outputs (multi-part OK)
│   │           ├── {Abbrev}-META-S01-{YY}-{TaskOutput}.md
│   │           └── {Abbrev}-META-S01-{YY}-{TaskOutput}-Part-2.md
│   └── Outputs/                                # Consolidated Context (multi-part)
│       ├── {Abbrev}-Consolidated-Context-Part-1-{Topic}.md
│       ├── {Abbrev}-Consolidated-Context-Part-2-{Topic}.md
│       └── {Abbrev}-Consolidated-Context-Part-N-{Topic}.md
│
├── Scaffold-{Abbrev}/                          # Phase 2: Plan Scaffolding
│   └── (agents read spec parts → create Exec folders/files)
│
└── Exec-{Abbrev}/                              # Phase 3: Execution (standard structure)
    ├── {Abbrev}-Master-Plan.md
    ├── Sprint-{XX}-{Name}/
    │   ├── {Abbrev}-S{XX}-Execution-Input.md   # Sprint-scoped spec (extracted from parts)
    │   ├── {Abbrev}-S{XX}-Sprint-Plan.md
    │   └── Session-{YY}-{Name}/
    │       └── ... (standard structure from above)
```

**Phase naming:** `META` = Discovery, `Scaffold` = Plan writing, `Exec` = Execution.

**Fan-out principle:** More specification detail = more sprints, sessions, and tasks. That is correct behavior — do NOT compress to reduce plan size.

---

## 3. Agent Delegation (BINDING)

> [!delegate] Agent Assignment
> | Task Type | Agent | Examples |
> |-----------|-------|----------|
> | Lookups, validation, counts | **Haiku** | File search, FK validation, list columns |
> | Code generation, implementation | **Sonnet** | Entities, controllers, views, migrations |
> | Architecture, complex decisions | **Opus** | Data model design, trade-offs, analysis |

> [!escalation] Agent Escalation
> - **Haiku → Sonnet:** If Haiku produces poor results or task needs code
> - **Sonnet → Opus:** If architectural decision needed or requirements ambiguous
> - **Opus → Sonnet:** After decision made, delegate implementation

> [!antipattern] Agent Misuse
> - Using Opus for file searches (wastes tokens)
> - Using Haiku for code generation (poor quality)
> - Keeping Opus for implementation after decision made

### Parallel vs Sequential Execution

```
Parallel execution when:
- Tasks have NO dependencies on each other
- Tasks query different data sources
- Tasks produce independent outputs

Sequential execution when:
- Task B needs output from Task A
- Tasks modify the same files
- Order matters for correctness
```

#### Parallel Execution Diagram

```
        ┌──────────────────────┐
        │ Orchestrator (Opus)  │
        │ Reads session prompt │
        └──────────┬───────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌───────┐    ┌───────┐    ┌───────┐
│Haiku 1│    │Haiku 2│    │Haiku 3│
│Task A │    │Task B │    │Task C │
└───┬───┘    └───┬───┘    └───┬───┘
    │              │              │
    └──────────────┼──────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ Sonnet               │
        │ Combines results     │
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ Opus                 │
        │ Final decision       │
        └──────────────────────┘
```

#### Dependency Declaration

Always declare dependencies explicitly:

```markdown
## Task Dependencies

| Task | Depends On | Blocks |
|------|------------|--------|
| Task 1 | None | Task 3 |
| Task 2 | None | Task 3 |
| Task 3 | Task 1, Task 2 | Task 4 |
| Task 4 | Task 3 | None |

Parallel groups:
- Group 1: Task 1, Task 2 (parallel)
- Group 2: Task 3 (sequential, after Group 1)
- Group 3: Task 4 (sequential, after Group 2)
```

---

## 4. Recovery Protocol (BINDING)

Recovery Protocol — full specification and binding update discipline live in [session-execution-protocol.md §4](session-execution-protocol.md#4-session-rules). Read that section for the WRONG/CORRECT minimum-content example and the update-after-every-task gate.

---

## 10. Pre-Session Validation Checklist

Before starting ANY session, verify:

> [!checklist] Pre-Session Validation
> - [ ] Orchestration file exists with task list
> - [ ] Recovery file exists and initialized
> - [ ] Outputs/ folder exists
> - [ ] All tasks have agent assignments
> - [ ] Task files exist (one per task, numbered 01, 02, 03...)
> - [ ] Task files are linked in Orchestration (Task Files table)
> - [ ] Context accumulation pattern identified (Discovery / Planned / Front-loaded)
> - [ ] Domain rules estimated (see [Domain Rule Costs](session-context-budget.md#domain-rule-costs))
> - [ ] Total context estimate: Files + Growth < 100K
> - [ ] If > 100K needed, Meta-Plan pattern documented
> - [ ] All required files will be read in full (no partial reads)
> - [ ] Dependencies between tasks documented
> - [ ] Cross-sprint task references use full Task ID format ({Abbrev}-S{XX}-{YY}-{##})
> - [ ] Task file EI section references are individual with purpose (no ranges)
> - [ ] Plan review completed (`/plan-review`) or consciously skipped
> - [ ] Reviewed relevant past lessons (/lessons {domain} or /lessons {language})
> - [ ] Execution Strategy declared in Orchestration (DIRECT or DELEGATED)
> - [ ] If 2+ Opus tasks → Mode is DELEGATED
> - [ ] If META Discovery session → Mode is DELEGATED
> - [ ] If DELEGATED: Orchestration Required Context lists ONLY plan files
> - [ ] If DELEGATED: Heavy context files appear ONLY in task file Required Context
> - [ ] If DELEGATED: Context Boundary subsection present in Execution Strategy
> - [ ] If plan uses Meta-Plan: `Exec-{Abbrev}/` folder exists (not writing into Meta parent)
> - [ ] If plan uses Meta-Plan: `Scaffold-{Abbrev}/` folder exists (scaffolding phase was run)
> - [ ] If the plan is a Discovery / Meta-Plan workflow, verify user-action gates per `session-execution-protocol.md §4.5` BEFORE setting Master Plan status to COMPLETE (gates may legitimately hold status at IN_PROGRESS even when all sprints are done)
> - [ ] All prerequisite sprints marked COMPLETE before starting this sprint
> - [ ] Outputs/ folder for this session exists (with `.gitkeep` if empty)
> - [ ] If any task reads cross-sprint files: `Depends On` field uses `cross-sprint:` prefix

---

## 11. Post-Session Checklist

After completing a session:

> [!checklist] Post-Session Validation
> - [ ] All tasks marked COMPLETE in Recovery
> - [ ] If session produced code changes and `/code-review` has not already been run on all changed files, run `/code-review` to review for reuse, quality, and efficiency
> - [ ] Summary file created in Outputs/
> - [ ] Orchestration status updated to COMPLETE
> - [ ] Sprint Plan tracking table updated
> - [ ] Master Plan tracking table updated
> - [ ] Lessons learned documented in LessonsLearned/LL-{NNN}-{Domain}-{Name}.md (YAML frontmatter + 3 sections)
> - [ ] 00-Index-LessonsLearned.md master table updated with new entries
> - [ ] If any session lesson is HIGH-severity or recurs (2+ instances across sessions), evaluate promotion to `.claude/rules/` per `session-plan-requirements.md §9` step 6. Record the promotion decision in the lesson frontmatter (`applied-as:` path) and the Rule Promotion Log.
> - [ ] Git commit with changes (lessons included before final commit)

---

## 12. Git Workflow

Git Workflow — full binding rules live in [session-execution-protocol.md §7](session-execution-protocol.md#7-git-workflow). Commit at session end; run `/code-review` before commit when the session produced code; stage specific files (never `git add .`).

---

## 13. READ-CONFIRM-ACT Protocol

The full READ-CONFIRM-ACT specification — including the 5-field Confirmation Block template (File, Current State, Last Completed, Next Action, Structural Finding) and the binding "Cannot Be Waived" callout — lives in [session-execution-protocol.md §1](session-execution-protocol.md#1-read-confirm-act-pattern). Read that section before every planning task.

---

## 14. Scaffolding Hygiene

See [scaffolding-hygiene.md](scaffolding-hygiene.md) for the complete set of binding rules governing multi-sprint scaffolded plans:
- §1-§7: Six foundational hygiene rules (Meta-Plan source detection, folder naming, abbreviation validation, sprint status defaults, Outputs/ creation, sequential-sprint prerequisites)
- §8: Parallel-Scaffold Deviation Classes
- §9: Multi-Shape Integration Plan-Sizing Expansion Ratio
- §10: Pre-Allocate Tokens for Known High-Divergence Cohorts

---

## 15. Discovery Scope Rigor

See [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md) §15 for binding rules governing Discovery and Meta-Plan scope:
- §15.1: Count by execution (not estimation)
- §15.2: Persist IDs, not just counts

---

## 16. Cross-Layer Enforcement & Exit-Criteria Fidelity

See [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md) §16 for cross-layer enforcement rules:
- §16.1: Binding refinements echo across all plan layers
- §16.2: "Surfaces" claims require enforceable checks
- §16.3: Verbatim-quote EI exit criteria with mechanical anchors

---

## Quick Reference

> [!consequences] Rule Violations
> | Rule | Consequence of Violation |
> |------|--------------------------|
> | Recovery updated after EVERY task | Context compaction loses all progress |
> | Total context (files + growth) < 100K | Session hits ceiling, loses ability to iterate |
> | Files read in full | Partial reads cause confusion and failures |
> | Agent assignment per task | Poor quality, token waste |
> | One task file per task (numbered) | Subagents lack clear instructions |
> | Task files linked in Orchestration | Cannot delegate to subagents properly |
> | Orchestration + Recovery exist | Cannot resume if compacts |
> | Lessons learned after each session | Insights lost to context compaction |
> | Commit after session | Lost work history |

---

## Templates

For full templates, see the [planwise plugin templates](templates/):
- [master-plan.md](templates/master-plan.md) — Master Plan Template
- [sprint-plan.md](templates/sprint-plan.md) — Sprint Plan Template
- [orchestration.md](templates/orchestration.md) — Orchestration Template
- [recovery.md](templates/recovery.md) — Recovery Template
- Pre/Post-Session Checklists: Sections 10-11 above

---

*These rules are binding. Violations cause context loss and incomplete work.*
*Companion files: [session-context-budget.md](session-context-budget.md), [session-plan-requirements.md](session-plan-requirements.md)*
