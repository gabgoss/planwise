---
description: Nine binding hygiene rules plus three advisory practices for multi-sprint plan scaffolding — Meta-Plan source detection, Exec folder naming, abbreviation validation, Sprint Plan status defaults, Outputs/ folder creation, sequential-sprint prerequisite declarations, no-improvisation of artifact types, mega-scaffold review-gate, parallel-scaffold deviation classes, multi-shape plan-sizing, high-divergence cohort token uplift, and run-time-sound verification commands and context pointers
---
# Scaffolding Hygiene

**Purpose:** Enforce seven mechanical hygiene rules — and apply three advisory scaffolding practices (§8–§10) — when scaffolding any multi-sprint plan (`/planwise plan --scaffold`, `/planwise plan` against Meta-Plan outputs, or hand-authored multi-sprint folders). Each rule has been re-derived in independent planning sessions; review-cycle tokens are wasted relitigating the same recurring issues.

This file is the §14 expansion referenced from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols). Read it before generating any `Sprint-{XX}-{Name}/` folders.

## Table of Contents

- [1. Meta-Plan Source Detection — Workflow Trigger](#1-meta-plan-source-detection--workflow-trigger)
- [2. Execution-Plan Folder Naming Inherits Parent Abbreviation](#2-execution-plan-folder-naming-inherits-parent-abbreviation)
- [3. Abbreviation Length Validation — ASK, Do Not Silently Truncate](#3-abbreviation-length-validation--ask-do-not-silently-truncate)
- [4. Sprint Plan Status Defaults — Only the Master Plan Is READY_TO_EXECUTE](#4-sprint-plan-status-defaults--only-the-master-plan-is-ready_to_execute)
- [5. Outputs/ Folder Per Session — Created at Scaffold Time](#5-outputs-folder-per-session--created-at-scaffold-time)
- [6. Sequential-Sprint Prerequisite — Declared in Each Orchestration](#6-sequential-sprint-prerequisite--declared-in-each-orchestration)
- [7. No Improvisation of Artifact Types During Scaffolding](#7-no-improvisation-of-artifact-types-during-scaffolding)
- [8. Parallel-Scaffold Deviation Classes](#8-parallel-scaffold-deviation-classes)
- [9. Multi-Shape Integration Plan-Sizing Expansion Ratio](#9-multi-shape-integration-plan-sizing-expansion-ratio)
- [10. Pre-Allocate Tokens for Known High-Divergence Cohorts](#10-pre-allocate-tokens-for-known-high-divergence-cohorts)
- [11. Mega-Scaffold Review-Gate — Non-Skippable for 2+ Sprints In One Pass](#11-mega-scaffold-review-gate--non-skippable-for-2-sprints-in-one-pass)
- [12. Verification Commands and Context Pointers Must Be Run-Time Sound](#12-verification-commands-and-context-pointers-must-be-run-time-sound)

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

## 8. Parallel-Scaffold Deviation Classes

> [!practice] When 2+ scaffold subagents author plan files in parallel from the same templates, three deviation classes accumulate that `/planwise review` should catch
>
> None of the three breaks execution; all three reduce consistency and weaken
> reviewer signal. They recur in any project that scaffolds with parallel
> subagents.
>
> 1. **Class A — Section-header text drift.** Semantically equivalent but
>    textually different headers (e.g., `## Execution Plan` vs `## Task List`).
> 2. **Class B — Optional formatting lines omitted.** Bold totals, divider
>    rules, and other lines present in the templates but not structurally
>    required (e.g., `**Total Estimated:** ~50K`).
> 3. **Class C — Scaffold folder absent when scaffolding is done inline.**
>    `Scaffold-{Abbrev}/` folder missing because scaffolding ran inline rather
>    than in a dedicated session.
>
> Mitigation hooks:
> - `/planwise review` Phase 1 structural check runs three greps — one per
>   class — against the plan tree.
> - The reviewer flags each deviation by class severity (A = WARNING,
>   B = ERROR, C = BLOCKER) and prompts the orchestrator to harmonize.
>
> WRONG — parallel scaffolders silently produce inconsistent files; the
> reviewer trusts the variance is intentional.
>
> CORRECT — the reviewer flags the three deviation classes; the orchestrator
> harmonizes section headers, restores the optional formatting lines, and
> creates the Scaffold folder if appropriate.

---

## 9. Multi-Shape Integration Plan-Sizing Expansion Ratio

> [!practice] Size a multi-shape external-integration plan from the expanded artifact count, not the endpoint-family count
>
> When sizing a plan that ingests data from an external system with multi-shape
> endpoints — one base path with sub-resources whose response containers differ,
> or query-flag-driven shape variants — artifact count expands to roughly
> `1.5–2.0 × endpoint_family_count`. Sizing the plan from the bare family count
> under-budgets the work by 50–100%.
>
> | Pattern | Ratio | Rationale |
> |---------|-------|-----------|
> | Shape-uniform integration (single response container, no sub-paths, no aggregate flags) | ~1.0× | Most internal CRUD APIs |
> | Light multi-shape (entity-type variants, optional aggregate flags) | ~1.3–1.5× | Each variant gets its own table or artifact |
> | Heavy sub-path multiplexing (one base path → sub-resources with fundamentally different response containers; or query-flag-driven shape variants) | ~1.6–2.0× | Each leaf shape gets its own artifact |
>
> **CONDITIONALLY-EXTENDED ≠ MULTI-SHAPE — do not over-split.** An endpoint with
> an optional sub-object (a field that only appears under specific conditions)
> gets a *single* artifact with nullable columns / fields, not multiple
> artifacts. The expansion ratio applies only to genuinely distinct response
> shapes.
>
> Sprint-planning implication: when a plan estimates token cost per artifact
> (DDL + adapter + notebook + facade re-export + index entry, or the equivalent
> stack for the project), multiply by the *expanded* count, not the family
> count.

---

## 10. Pre-Allocate Tokens for Known High-Divergence Cohorts

> [!practice] Pre-Allocate Tokens for Known High-Divergence Cohorts
>
> When a sprint authors multiple deliverables across a cohort that empirically
> exhibits MAX cross-tier divergence (e.g., adapter row vs deployed schema,
> source-spec vs implementation, EI prose vs downstream code), scaffold-time
> token estimates MUST include a cohort-specific uplift — not just the
> per-deliverable baseline. The uplift covers the extra reconciliation-discipline
> overhead: explicit field mappings, named-parameter binding, additional
> verification gates.
>
> Three-step protocol:
> 1. **Identify cohort divergence at scaffold time** — grep the upstream
>    artifact (adapter dataclass, source schema, etc.) and the downstream
>    artifact (DDL, consumer code, etc.) for the cohort's members. Compute the
>    average rename count + dispatched-field count + field-count delta across
>    the cohort.
> 2. **If average divergence exceeds the project's field/rename threshold per
>    deliverable** → declare the cohort "high-divergence" and apply the
>    token-uplift heuristic.
> 3. **Encode the uplift in the Master Plan token-budget summary AND in each
>    per-task estimate.**
>
> Cohort-divergence signal table:
>
> | Cohort divergence | Reconciliation effort | Token impact |
> |---|---|---|
> | None / matching shapes | Standard positional binding — ~200 tokens | Standard estimate |
> | Minor (≤5 renames, no dispatch) | Aliased positional binding — ~500 tokens | +500 over standard |
> | Major (>5 renames OR dispatched fields) | Explicit named-param binding — ~2000 tokens | +2000 over standard |
> | **High-divergence cohort (structural)** | **Explicit named-param binding + Field Mapping subsection (`task-content-fidelity.md` §9.B.8)** — **~3000–4000 tokens** | **+3000–4000 over standard** |
>
> Mechanical signal: when a cohort's task briefs all share a paste-templated
> Field Mapping subsection (per `task-content-fidelity.md` §9.B.8), the cohort
> is divergence-aware by construction; the token-uplift is the budget mechanism
> that makes the Field Mapping actionable.
>
> Project-specific applications of this pattern — a particular API family known
> to exhibit MAX divergence, for instance — belong in project-local rule files,
> not in this plugin reference. This reference defines the *principle* and the
> *signal*; a project's own rules name the *cohorts*.

---

## 11. Mega-Scaffold Review-Gate — Non-Skippable for 2+ Sprints In One Pass

> [!gate] When a `/planwise plan --scaffold` (or equivalent inline-scaffolding session) authors 2+ sprints / Execution Inputs in a single pass, `/planwise review` is MANDATORY before the plan can advance to `/planwise run`
> The two scaffolding strategies (per-sprint cadence vs inline mega-scaffold) have different self-review economics. Per-sprint scaffolding allows the author to run the bidirectional-consistency self-check (every Cross-References file appears in `Extracted from:`, and vice versa; every cited identifier is a full, resolvable filename) after each sprint, while the scaffolding context is still fresh. Inline mega-scaffold trades that per-sprint self-review for speed — and EI header/cross-reference hygiene is the first thing to slip.
>
> The defect is silent: every file is individually well-formed; only the *consistency between* a header and its Cross-References table is wrong. The downstream cost is mechanical — typically a handful of mis-cited spec numbers, missing header entries, or unresolvable short-form filenames — but every one of those defects rides into execution if the review gate is also skipped. An agent reading a Cross-References row that points at a source the header never declared will either burn tokens reconciling or fall back to an invented framing.
>
> **The gate, stated mechanically:**
>
> 1. The scaffolder counts `n_sprints_scaffolded_this_pass` — the number of distinct Sprint Plan files authored during the current `/planwise plan` invocation.
> 2. If `n_sprints_scaffolded_this_pass ≥ 2`, the plan's Step-10 plan-review gate (in `handlers/plan.md`) MUST present a non-skippable branch — "Skip to /planwise run" is removed from the available options. Only "Auto-review with /planwise review" or "Review manually first" remain.
> 3. The scaffold session may legitimately defer the *content* review for cause (e.g., a follow-up session is already scheduled), but the *gate itself* — the explicit decision to defer — MUST be recorded in the Master Plan's status note rather than silently skipped.
>
> WRONG — scaffold N sprints inline, declare the scaffold "done", proceed toward `/planwise run` without a review:
>
> ```
> /planwise plan --scaffold (4 sprints, one pass)
>   → Step-10 prompt: "Auto-review / Manual review / Skip to /planwise run"
>   → User picks "Skip to /planwise run"
>   → Header⇄Cross-References inconsistencies ride into execution
>   → Agent reads a Cross-References row pointing at a source the header never declared
> ```
>
> CORRECT — scaffold N sprints inline, gate forces a review decision:
>
> ```
> /planwise plan --scaffold (4 sprints, one pass)
>   → Step-10 detects n_sprints_scaffolded_this_pass = 4
>   → Prompt: "Auto-review with /planwise review (Recommended) / Review manually first"
>     (no "Skip" option; review is mandatory)
>   → User picks Auto-review
>   → /planwise review runs, finds 2 ERROR + 5 WARNING (header⇄Cross-References hygiene)
>   → User addresses findings before /planwise run
> ```
>
> Equivalently: scaffold per-sprint and run the bidirectional-consistency self-check after each sprint. Skipping both the per-sprint cadence AND the post-scaffold review gate is the trap this rule closes.

The cost asymmetry justifies the gate: roughly half a dozen mechanical fixes after the fact, vs a one-pass self-check at authoring time. The point is not "never scaffold inline" — it is that the inline path is only safe when paired with the review gate.

How the gate is enforced at the planner layer:

- `handlers/plan.md` Step 10 counts `n_sprints_scaffolded_this_pass` (1 for standard plans; N for `/planwise plan --scaffold` sessions).
- When `n_sprints_scaffolded_this_pass ≥ 2`, the `AskUserQuestion` "Plan Review Approach" prompt omits the "Skip to /planwise run" option.
- The handler's Question 2 ("Review Context") still applies — auto-review can run in this session or a new one — but Question 1's "Skip" option is gated off.

Applies to:

- Any `/planwise plan` invocation that produces 2+ Sprint Plan files in a single pass.
- Any hand-authored multi-sprint scaffolding session where the same pattern applies (2+ sprints authored in one work-session before any review runs).
- Reinforces the existing EI bidirectional-consistency rule (`ei-fidelity.md` §9) and the new body⇄citation source-promise rule (`ei-fidelity.md` §10) — both rules exist; this gate ensures the most likely failure pattern (inline mega-scaffold skips both per-sprint self-review and the post-scaffold review) is closed.

Red flags during reviewer audit:

- Master Plan Status is `READY_TO_EXECUTE` AND `n_sprints_scaffolded_this_pass ≥ 2` AND no `/planwise review` report is referenced — gate skipped.
- The Step-10 confirmation block in the planner's transcript shows a "Skip to /planwise run" choice was offered for a multi-sprint scaffold — gate not enforced by the handler.

See also: `handlers/plan.md` Step 10 (the gate's mechanical enforcement point), `ei-fidelity.md` §9 (EI bidirectional consistency — the rule the inline mega-scaffold most often violates), `ei-fidelity.md` §10 (Source-Promise Integrity — the rule the scaffolder's body⇄citation promises depend on).

---

## 12. Verification Commands and Context Pointers Must Be Run-Time Sound

Content written into a task file at **scaffold** time can encode an assumption about the on-disk world that is no longer true — or was never true — at **run** time, while every per-task gate still passes because the scaffolded artifact is internally well-formed. Two surfaces are especially prone to this: Required-Context line pointers and verification-command paths. Both must be treated as run-time-derived facts, not scaffold-time constants.

### 12.1 Required-Context Line Pointers Are Cost Hints — Locate by Symbol Before Reading/Editing

> [!constraint] Treat a scaffolded `file — Lxxx-yyy` pointer as a hint for cost estimation, never as a read/edit anchor
> Before any `offset/limit` read or edit of a cited region, re-locate the target by symbol grep and re-derive the offsets.

A scaffolded pointer like `some_script.py — L860-930 (offset/limit read)` is authored when the file is in one state. By run time, concurrent sessions editing the same shared source — or an earlier task in the *same* session adding lines above the cited region — will have shifted the target. Observed drift: ~100+ lines into a shared script, so a verbatim `offset/limit` read lands on unrelated code.

WRONG — trust the scaffolded pointer:

```
Read(some_script.py, offset=860, limit=70)   # reads unrelated code after concurrent sessions shifted the target ~100 lines
```

CORRECT — locate by content, then read:

```
grep -n "def normalize_rule_for_diff" some_script.py   # → :976
Read(some_script.py, offset=970, limit=70)
```

Drift driver: concurrent sessions editing shared source (shared scripts, handlers, references) between scaffold time and run time — and a task adding lines earlier in the same file shifting a later task's offsets.

Corollaries:

- Task Step-1 gates and dispatch prompts gate on **symbols** (`grep -c 'def _classify_diverged' …`), never on line numbers.
- An orchestrator forwarding context to a runner passes the **symbol names** and flags the line numbers as possibly stale.

### 12.2 Scaffolded Verification Commands Derive the Repo Root — Never Assume Directory Depth

> [!constraint] A relative `git -C ../../..` depth is a guess about the on-disk tree; the repo root is a derivable fact
> Derive it, or anchor to a stable known path — never bake a directory-depth assumption into a verification command.

A verification command that hard-codes a relative depth (`git -C ../../..`) assumes how many levels up the repo root sits. If the assumption is wrong, the command targets a different directory — and a BINDING gate whose pass condition is "empty output" then passes **vacuously**: a "clean" result from the wrong repo is indistinguishable from a genuinely clean target.

WRONG — assumed depth baked in at scaffold time:

```
git -C ../../.. diff plugins/planwise/ | grep -E '^\+' | grep -E '(LL-[0-9]|BB-[0-9])'
```

CORRECT — derive the root, or anchor project-root-relative to a stable known path:

```
git -C "$(git rev-parse --show-toplevel)" diff plugins/planwise/ | grep -E '^\+' | grep -E '(LL-[0-9]|BB-[0-9])'
# or, from the project root (stable known path):
git -C cloned-repos/planwise diff plugins/planwise/ | grep -E '^\+' | grep -E '(LL-[0-9]|BB-[0-9])'
```

Additional guidance:

- When an auto-commit hook may fire mid-session, a working-tree diff alone under-covers the gate — also sweep the session's committed delta (`git diff HEAD~1 -- plugins/planwise/`) so already-committed edits are leak-checked too.
- Any BINDING gate whose pass condition is "empty output" has path-correctness as part of its soundness: a wrong-repo invocation passes vacuously.
- Reviewers should spot-check one `git -C` depth per scaffolded sprint against the live tree.

Applies to:

- Any scaffolded task file citing `file — Lxxx-yyy (offset/limit read)` in Required Context, especially into files that multiple concurrent sessions edit (shared scripts, handlers, references).
- Scaffolding authoring Verification Commands into task files, wherever the target lives in a nested or cloned sub-repo.
- Plan review: reviewers spot-check both surfaces — one symbol-vs-line pointer and one `git -C` depth per scaffolded sprint — against the live tree.

---

*Nine binding hygiene rules plus three advisory practices for multi-sprint plan scaffolding. Cross-referenced from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols).*
