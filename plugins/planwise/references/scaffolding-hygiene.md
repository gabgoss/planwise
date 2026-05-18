---
description: Seven binding hygiene rules for multi-sprint plan scaffolding — Meta-Plan source detection, Exec folder naming, abbreviation validation, Sprint Plan status defaults, Outputs/ folder creation, sequential-sprint prerequisite declarations, and no-improvisation of artifact types
---
# Scaffolding Hygiene

**Purpose:** Enforce seven mechanical hygiene rules when scaffolding any multi-sprint plan (`/planwise plan --scaffold`, `/planwise plan` against Meta-Plan outputs, or hand-authored multi-sprint folders). Each rule has been re-derived in independent planning sessions; review-cycle tokens are wasted relitigating the same seven issues.

This file is the §14 expansion of [session-planning-protocol.md](session-planning-protocol.md). Read it before generating any `Sprint-{XX}-{Name}/` folders.

## Table of Contents

- [1. Meta-Plan Source Detection — Workflow Trigger](#1-meta-plan-source-detection--workflow-trigger)
- [2. Execution-Plan Folder Naming Inherits Parent Abbreviation](#2-execution-plan-folder-naming-inherits-parent-abbreviation)
- [3. Abbreviation Length Validation — ASK, Do Not Silently Truncate](#3-abbreviation-length-validation--ask-do-not-silently-truncate)
- [4. Sprint Plan Status Defaults — Only the Master Plan Is READY_TO_EXECUTE](#4-sprint-plan-status-defaults--only-the-master-plan-is-ready_to_execute)
- [5. Outputs/ Folder Per Session — Created at Scaffold Time](#5-outputs-folder-per-session--created-at-scaffold-time)
- [6. Sequential-Sprint Prerequisite — Declared in Each Orchestration](#6-sequential-sprint-prerequisite--declared-in-each-orchestration)
- [7. No Improvisation of Artifact Types During Scaffolding](#7-no-improvisation-of-artifact-types-during-scaffolding)

---

## 1. Meta-Plan Source Detection — Workflow Trigger

> [!constraint] Scaffolding workflow is triggered by INPUT FORMAT, not by the user's plan-type label
> When source material references `Meta-{Abbrev}/Outputs/` or lists files from a
> completed Discovery phase, USE the Scaffolding workflow even if the user says
> "standard execution plan." The trigger is the input shape (Meta-Plan outputs),
> not the output-type label.
>
> WRONG — user says "standard execution plan", source material is multiple
> thousand lines of `Meta-{Abbrev}/Outputs/` research; planner uses the
> Standard `/planwise plan` workflow. Task files reference deep paths into
> `Meta-{Abbrev}/`, subagents read entire research docs to extract per-sprint
> slivers, and no self-contained per-sprint document exists.
>
> CORRECT — recognise the Meta-Plan source signal and switch to the Scaffolding
> workflow. Produce per-sprint Execution Inputs that filter and reorganise raw
> research into focused per-sprint content. Subagents read the EI for the
> sprint they are executing, not the raw Meta-Plan outputs.

---

## 2. Execution-Plan Folder Naming Inherits Parent Abbreviation

> [!constraint] Exec plans go in `Exec-{Abbrev}/`; reuse the parent abbreviation
> When a Meta-Plan produced Discovery outputs for project `{Abbrev}`, the
> execution plan goes in `Exec-{Abbrev}/` and uses the SAME abbreviation. Do
> not invent a new abbreviation for the execution phase.
>
> ```
> Plans/{PlanName}/
> ├── Meta-{Abbrev}/      ← Phase 1: Discovery
> ├── Scaffold-{Abbrev}/  ← Phase 2: Plan writing
> └── Exec-{Abbrev}/      ← Phase 3: Execution
> ```
>
> WRONG — `Plans/{PlanName}/{NewAbbrev}/` with abbreviation `{NewAbbrev}` for
> the execution phase of a `Meta-{Abbrev}`-derived plan. Severs the visual link
> between Discovery and Execution; users ask "what is `{NewAbbrev}`?" and
> "why is `{NewAbbrev}` inside `{PlanName}`?"
>
> CORRECT — `Plans/{PlanName}/Exec-{Abbrev}/` with abbreviation `{Abbrev}`. The
> folder name and abbreviation make the Discovery → Execution lineage visible
> at a glance.

---

## 3. Abbreviation Length Validation — ASK, Do Not Silently Truncate

> [!constraint] User-provided abbreviations exceeding 2-4 chars require an ASK, not a silent rewrite
> When a user-provided abbreviation violates the 2-4 character constraint, STOP
> and ask the user how to resolve it. Present the constraint, what they
> provided, and at least two suggested alternatives — including reusing the
> parent project's abbreviation if a `Meta-{Abbrev}/` folder exists.
>
> WRONG — user supplies a 6-character compound abbreviation
> `{ParentAbbrev}-{PhaseAbbrev}`; planner silently shortens to `{PhaseAbbrev}`
> only. The user's mental model breaks — they chose the compound form to express
> "the {PhaseAbbrev} phase OF {ParentAbbrev}"; the silent truncation discards
> the parent-project signal and produces user-visible confusion.
>
> CORRECT — surface the constraint and ask:
>
> > Planwise abbreviations must be 2-4 characters. You provided
> > `{ParentAbbrev}-{PhaseAbbrev}` (6 chars). Options:
> > 1. Keep `{ParentAbbrev}` — same project, execution phase. Recommended if
> >    `Meta-{ParentAbbrev}/` already exists.
> > 2. Use `{PhaseAbbrev}` — standalone abbreviation; loses the parent-project
> >    link.
> > 3. Other (your call).
>
> The general principle: when a user-provided value violates a constraint, ask
> rather than silently adjusting. Silent decisions that change user-visible
> naming always cause confusion.

---

## 4. Sprint Plan Status Defaults — Only the Master Plan Is READY_TO_EXECUTE

> [!constraint] Scaffolded Sprint Plans use `Status: PLANNED` regardless of generation order
> When scaffolding multi-sprint plans, ALL Sprint Plans MUST start at
> `**Status:** PLANNED`. Only the Master Plan sets `**Status:**
> READY_TO_EXECUTE`. Sprint status transitions during execution: `PLANNED →
> IN_PROGRESS → COMPLETE`.
>
> WRONG — a Sprint Plan's header says `**Status:** READY_TO_EXECUTE` while its
> prerequisite sprint is still `NOT_STARTED`. Caused by the generating agent
> copying the Master Plan's status field instead of the Sprint Plan template's.
>
> CORRECT — every Sprint Plan starts at `**Status:** PLANNED`, regardless of
> which sprint was generated first. Agent prompts for scaffolding tasks must
> include the explicit instruction: "Set Sprint Plan status to PLANNED (not
> READY_TO_EXECUTE)."

---

## 5. Outputs/ Folder Per Session — Created at Scaffold Time

> [!constraint] Every session's `Outputs/` folder MUST exist at scaffold time
> When scaffolding a multi-session plan, create the `Outputs/` directory for
> every session, not just Session 01. Each post-session checklist references
> writing summaries to `Outputs/`; if the directory does not exist when the
> session starts, the executor either skips the artifact or wastes a turn
> creating the folder.
>
> WRONG — plan has multiple sessions; only Session 01's `Outputs/` folder
> exists. Later sessions reference their `Outputs/` folder in post-session
> checklists, but the directories are missing.
>
> CORRECT — every `S{NN}-{NN}/` session directory contains an `Outputs/`
> subdirectory at scaffold time. Use `.gitkeep` files to commit empty folders
> since git does not track empty directories.

---

## 6. Sequential-Sprint Prerequisite — Declared in Each Orchestration

> [!constraint] Each sequential sprint's Orchestration MUST declare its prerequisite
> When sprints are sequential (each depends on the prior sprint's output),
> every Orchestration file MUST include an explicit prerequisite statement
> referencing the prior sprint's Recovery file. Master Plan dependency tables
> are not sufficient — the Orchestration is what the executor reads, and it
> must be self-contained for its own prerequisites.
>
> WRONG — Master Plan's Dependencies section says "Sprint N-1 complete →
> Sprint N → Sequential", but `S{NN}-01-Orchestration.md` contains no
> reference to Sprint N-1's completion. An executor opening Sprint N directly
> has no local indication that Sprint N-1 must be complete.
>
> CORRECT — each sequential sprint's Orchestration includes a Prerequisite
> line at the top:
>
> > **Prerequisite:** Sprint {N-1} session COMPLETE — {what must exist}.
> > Verify `{Abbrev}-S{N-1}-01-Recovery.md` shows Session Status: COMPLETE.
>
> Applies in both DIRECT and DELEGATED execution modes.

---

## 7. No Improvisation of Artifact Types During Scaffolding

> [!constraint] Scaffolding agents MUST NOT invent new artifact types or fabricate authoritative-sounding framing for ad-hoc additions
> The spec for `/planwise plan --scaffold` enumerates every artifact type the
> agent may produce: Master Plan, Execution Input, Sprint Plan, Orchestration,
> Recovery, task file, `Outputs/` folder. When the scaffolding agent perceives
> a gap that none of those artifacts cover, the answer is NEVER "invent a new
> artifact type with confident framing." That pattern produces files that look
> spec-defined but are not — readers and downstream agents treat the invented
> artifact as authoritative, institutionalising the drift.
>
> Three legal options when an agent perceives a scaffolding gap:
>
> 1. **HALT and escalate.** Stop scaffolding, describe the perceived gap to the
>    user, and let the user decide whether the gap is real or illusory. Halting
>    costs one round-trip; inventing costs an indefinite cleanup.
> 2. **File a backlog item, proceed with spec-defined artifacts.** Open a
>    `BLI-` describing the perceived gap. Continue the current scaffold using
>    only artifacts the spec defines. The backlog item carries the gap forward
>    without contaminating the current plan.
> 3. **Use the closest existing template verbatim, mark deviation explicitly.**
>    When the perceived gap is small enough to fit inside an existing artifact
>    (e.g., a Master-Plan paragraph, an Orchestration callout, a task-file
>    Notes section), use that artifact's existing template verbatim AND mark the
>    addition with an explicit "non-spec, ad hoc" annotation in the Step 9
>    confirmation block.
>
> WRONG — a prior scaffolder run invented `Scaffold-{Abbrev}/README.md`
> mid-scaffold with retrofitted "just-in-time incremental scaffolding" framing.
> The README declared an authoritative-sounding workflow that contradicted the
> spec's two-phase scaffold/execute model. A prior backlog item explicitly
> REJECTED templating this invented file — institutionalising it would have
> made the drift permanent.
>
> CORRECT — when a similar gap is perceived (e.g., "the user might want
> progress visibility during a long scaffold"), pick one of the three legal
> options:
>
> - HALT: "I notice the spec doesn't define a per-phase progress artifact.
>   Should I add one now, defer to a backlog item, or proceed with spec-only
>   artifacts?"
> - BACKLOG: file `BLI-{NNN}-Progress-Visibility-During-Scaffold.md`, proceed
>   with spec-defined artifacts only.
> - INLINE: add a Master-Plan paragraph titled "Scaffolding Progress" (existing
>   artifact, existing prose), and mark it `**non-spec, ad hoc:**` in the
>   Step 9 confirmation block.
>
> Inventing `Scaffold-{Abbrev}/README.md` (or any peer-level new artifact type)
> is NEVER one of the three options.

---

*Seven binding rules for multi-sprint plan scaffolding. Cross-referenced from [session-planning-protocol.md](session-planning-protocol.md) §14.*
