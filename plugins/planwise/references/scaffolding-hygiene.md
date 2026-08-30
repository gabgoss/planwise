---
description: Thirteen binding hygiene rules plus three advisory practices for multi-sprint plan scaffolding — Meta-Plan source detection, Exec folder naming, abbreviation validation, Sprint Plan status defaults, Outputs/ folder creation, sequential-sprint prerequisite declarations, no-improvisation of artifact types, mega-scaffold review-gate, parallel-scaffold deviation classes, multi-shape plan-sizing, high-divergence cohort token uplift, run-time-sound verification commands and context pointers, retirement-deliverables deletion-set derivation, config-editing permission-round-trip scaffolding, first-task sprint diff-baseline recording, and computed write-set intersection for declared-parallel sprints
---
# Scaffolding Hygiene

**Purpose:** Enforce thirteen mechanical hygiene rules — and apply three advisory scaffolding practices (§8–§10) — when scaffolding any multi-sprint plan (`/planwise plan --scaffold`, `/planwise plan` against Meta-Plan outputs, or hand-authored multi-sprint folders). Each rule has been re-derived in independent planning sessions; review-cycle tokens are wasted relitigating the same recurring issues.

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
- [13. Retirement Deliverables Must Derive the Deletion Set](#13-retirement-deliverables-must-derive-the-deletion-set)
- [14. Scaffold a Config-Editing Plan for a Permission Round-Trip](#14-scaffold-a-config-editing-plan-for-a-permission-round-trip)
- [15. First Task of Each Sprint Records the Diff Baseline](#15-first-task-of-each-sprint-records-the-diff-baseline)
- [16. Declared Parallelism Requires a Computed Write-Set Intersection](#16-declared-parallelism-requires-a-computed-write-set-intersection)

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

#### Reviewer Check 046 — Meta-Plan Source Detection

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **Detection:** Glob `**/Consolidated-Context-Part-*.md` under `Meta-{Abbrev}/Outputs/`. Absent for Meta-Plan → BLOCKER.
- **Finding template:** `[BLOCKER] Meta-Plan Consolidated Context parts missing | File: {Meta folder} | Fix: Generate per references/scaffolding-hygiene.md §1`

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

#### Reviewer Check 047 — Execution-Folder Naming Discipline

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **Detection:** Glob `Plans/{PlanName}/Exec-{Abbrev}/`. Folder name not matching `Exec-{Abbrev}` → BLOCKER.
- **Finding template:** `[BLOCKER] Execution folder naming non-conformant | Fix: Rename to Exec-{Abbrev}/ per references/scaffolding-hygiene.md §2`

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

#### Reviewer Check 048 — Abbreviation Validation

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **Detection:** Extract `{Abbrev}` from Master Plan filename; validate 2-4 chars uppercase; check uniqueness across `Plans/` siblings. Invalid/non-unique → BLOCKER.
- **Finding template:** `[BLOCKER] Abbreviation invalid or non-unique | Fix: Choose 2-4 char unique abbrev per references/scaffolding-hygiene.md §3`

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
> Recovery, task file, `Outputs/` folder, Sprint Signoff, Deferred/Out-of-Scope
> Log. The last two are defined elsewhere and are easy to mistake for
> improvisations when read against this list alone —
> [templates/sprint-signoff.md](../templates/sprint-signoff.md) is a full
> template and [exit-criteria-fidelity.md](exit-criteria-fidelity.md) §16.3
> makes the Signoff REQUIRED for every multi-sprint scaffolded plan, while
> [session-plan-requirements.md](session-plan-requirements.md) mandates a
> per-sprint Deferred/Out-of-Scope Log with an inline template. A reviewer
> applying this list literally must not flag either as invented. When the
> scaffolding agent perceives
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

#### Reviewer Check 049 — Parallel-Scaffold Deviation Classes

- **Severity / Role:** ERROR/WARNING/BLOCKER (by class) | Scaffolding Hygiene Reviewer | NEW
- **Detection:** Compare scaffolded sprint outputs against template; classify deviations: A (section-header drift = WARNING), B (optional-formatting omission = ERROR), C (Scaffold-folder absence = BLOCKER).
- **Finding template:** `[{SEVERITY}] Parallel-scaffold deviation class {A|B|C} | Fix per references/scaffolding-hygiene.md §8`

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
> | **High-divergence cohort (structural)** | **Explicit named-param binding + Field Mapping subsection (`verify-before-cite.md` §9.B.8)** — **~3000–4000 tokens** | **+3000–4000 over standard** |
>
> Mechanical signal: when a cohort's task briefs all share a paste-templated
> Field Mapping subsection (per `verify-before-cite.md` §9.B.8), the cohort
> is divergence-aware by construction; the token-uplift is the budget mechanism
> that makes the Field Mapping actionable.
>
> Project-specific applications of this pattern — a particular API family known
> to exhibit MAX divergence, for instance — belong in project-local rule files,
> not in this plugin reference. This reference defines the *principle* and the
> *signal*; a project's own rules name the *cohorts*.

#### Reviewer Check 050 — Cohort Token-Uplift Practice

- **Severity / Role:** WARNING | Scaffolding Hygiene Reviewer | NEW
- **Detection:** Open Master Plan Sprint Overview Notes column; for high-divergence cohorts, verify cohort token-uplift entry present. Absent → WARNING.
- **Finding template:** `[WARNING] High-divergence cohort missing token-uplift entry | Fix per references/scaffolding-hygiene.md §10`

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
- Reinforces the existing EI bidirectional-consistency rule (`ei-completeness.md` §9) and the new body⇄citation source-promise rule (`ei-source-promise-integrity.md` §10) — both rules exist; this gate ensures the most likely failure pattern (inline mega-scaffold skips both per-sprint self-review and the post-scaffold review) is closed.

Red flags during reviewer audit:

- Master Plan Status is `READY_TO_EXECUTE` AND `n_sprints_scaffolded_this_pass ≥ 2` AND no `/planwise review` report is referenced — gate skipped.
- The Step-10 confirmation block in the planner's transcript shows a "Skip to /planwise run" choice was offered for a multi-sprint scaffold — gate not enforced by the handler.

See also: `handlers/plan.md` Step 10 (the gate's mechanical enforcement point), `ei-completeness.md` §9 (EI bidirectional consistency — the rule the inline mega-scaffold most often violates), `ei-source-promise-integrity.md` §10 (Source-Promise Integrity — the rule the scaffolder's body⇄citation promises depend on).

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

### 12.3 State-Asserting Rows Are Cost Hints Too — Re-Derive the Conclusion at Scaffold Close

> [!constraint] A row that asserts a STATE about an artifact is a scaffold-time snapshot, exactly like a line-number pointer — re-derive it at scaffold close, not just its file path
> §12's opening principle is: content written into a task file at scaffold time can encode an assumption about the on-disk world that is no longer true — or was never true — at run time, while every per-task gate still passes because the artifact is internally well-formed. §12.1 applies this to path pointers (`file — Lxxx-yyy`); §12.2 applies it to directory-depth assumptions in verification commands. This subsection applies the SAME principle to a third surface: a row whose content asserts a STATE — "X is an orphan", "X is cited by nothing", "X has N members", "X is Y lines long", "X is unreferenced" — rather than merely citing a path.
>
> A state assertion differs from a path pointer in one important way: nothing in the existing gates re-derives it automatically. A stale line-number pointer fails loudly (the read lands on the wrong content, and a symbol-grep gate catches it). A stale state assertion fails silently — the assertion reads as a settled fact, gets folded into a priority order, an exit criterion, or a Signoff anchor, and nothing downstream re-checks whether it is still true.
>
> Mandatory step: for every row whose content asserts a STATE (not just cites a path), scaffolding MUST re-run the assertion against the LIVE artifact at scaffold close and record the measured value inline with a date — the same treatment §12.1 already gives path pointers. "Re-derive at scaffold close" means literally running the grep/count/check the row claims — NOT re-reading the same source document that produced the original claim (re-reading the source re-confirms what the source said, not what is currently true).
>
> WRONG — a state assertion is compressed and carried forward without re-derivation:
> ```
> Source (Discovery-era): "{file} is cited by nothing."
> EI row (scaffold time, unchanged): "{file} is a true orphan, cited by nothing."
> (no grep run against the live tree before this row is written)
> ```
> The EI row hardens into a priority order. If the live tree has since gained a citation, the row is false and nothing catches it until execution — or later.
>
> CORRECT — the assertion is re-run against the live artifact, and the measured value + date is recorded inline:
> ```
> Source (Discovery-era): "{file} is cited by nothing."
> Scaffold-close re-derivation: `grep -rn "{file}"` → 1 hit (`{citing-file}:{line}`), measured {date}.
> EI row: "{file} is cited once, by {citing-file}:{line} (measured {date}) — NOT a true orphan; the
>          Discovery-era 'cited by nothing' claim is superseded."
> ```

Applies to:

- Any EI row, Deliverable, exit criterion, or Signoff anchor asserting a count ("N members"), a reachability claim ("orphan" / "cited by nothing" / "unreferenced"), a size claim ("X lines"), or any other fact about an artifact's CURRENT state.
- Scaffolding Step 4 (Create Execution Inputs) of the scaffolding workflow — see `handlers/plan-scaffolding.md`.
- Companion to §10.4 in `references/ei-source-promise-integrity.md` (cited-authority currency): that subsection covers a claim whose support comes from ANOTHER artifact's conclusion; this subsection covers a claim whose support is a directly-measurable fact about the artifact itself. A row can fail either, both, or neither independently.

#### Reviewer Check 081 — State-Asserting Row Re-Derivation at Scaffold Close

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Every EI row, Deliverable, exit criterion, or Signoff anchor asserting a STATE about an artifact (count, reachability, size, existence) MUST carry a measured value + date recorded inline, re-derived against the live artifact at scaffold close — not merely inherited from the Discovery-era source that first made the claim.
- **Detection:**
  1. Grep the EI/Sprint Plan/Orchestration for state-asserting phrasing: "is an orphan", "cited by nothing", "unreferenced", "has {N} members", "is {N} lines", or equivalent count/reachability/size claims.
  2. For each match, check whether the row carries an inline measured value + date (e.g., "measured {date}: {value}").
  3. If absent, re-run the assertion against the live artifact yourself and compare to the row's claim.
  4. If the row lacks a measured value + date, OR the live re-derivation contradicts the row's claim → BLOCKER.
- **Finding template:**
```
[BLOCKER] State-asserting row not re-derived at scaffold close
File: {EI/plan file path} | Location: {row/section}
Issue: row asserts "{claim}" with no measured value + date; live re-derivation shows {measured value}
Fix: Re-run the assertion against the live artifact and record the measured value + date inline, per references/scaffolding-hygiene.md §12.3 | Confidence: HIGH
```

---

## 13. Retirement Deliverables Must Derive the Deletion Set

A Deliverables list that removes a persistent artifact is produced by a sweep, not written from memory: run the sweep first, paste its output into the plan, and let that output be the list. Two sweep passes are needed because they catch different misses, and the hits must then be classified by ROLE — not file type — because exactly one role can silently undo the retirement.

### 13.1 Derive the Deletion Set Before Authoring Deliverables

> [!constraint] Run the sweep first, paste its output into the plan, and let that output be the list
> A Deliverables list that **removes** a persistent artifact is produced by a sweep, not written from memory.

```bash
# Run BEFORE writing the Deliverables section. Two passes, because they miss different things.
grep -rln --exclude-dir={vcs,cache dirs} "{qualified_artifact_name}" {source_roots} {docs}
find {source_roots} -name "*{artifact_name}*"   # catches members that never mention the name in prose
```

WRONG — the Deliverables section names the files the author remembers touching:

```markdown
6. **Deletions:** `{path}/refresh_helper.{ext}`, `{path}/driving_notebook.{ext}`
```

Both entries correct; the creator artifact absent; nothing in the plan detects the absence, because every gate the plan wrote checks the work that *was* scheduled.

CORRECT — the Deliverables section cites the command and pastes what it returned:

```markdown
6. **Deletions** — derived by `grep -rln "{qualified_name}" {roots}` + `find {roots} -name "*{name}*"`
   (run {date}; full output in `Outputs/{...}-DeletionSweep.md`):
   - `{path}/schema_definition.{ext}`   ← CREATOR (see §13.2 — omission undoes the retirement)
   - `{path}/refresh_helper.{ext}`      ← REFRESHER
   - `{path}/driving_notebook.{ext}`    ← DRIVER
   - 5 citer-only references listed in §13.3 (edit, do not delete)
```

### 13.2 Classify Sweep Hits by ROLE, Not by File Type

The sweep returns paths. What matters is what each path *does* to the artifact, because exactly one role can undo the retirement:

| Role | What it does | Typical members | Cost of omitting it |
|---|---|---|---|
| **Creator** | Re-creates the artifact from nothing | schema DDL, migration, generator script, seed/fixture loader, packaging or re-export declaration | **UNDOES the retirement** — the next routine run resurrects the artifact as an orphan nothing refreshes and nothing drives |
| Refresher | Populates or updates it | helper module, transform, ETL step | Inert dead code — fails or no-ops |
| Driver | Invokes the refresher | notebook, CLI entry point, scheduled job | Inert dead code |
| Citer | Names it in prose | docstrings, comments, docs, index rows, cross-references | Misleads the next reader toward a file that is gone (§13.3) |

The Deliverables list MUST either contain a Creator-role member, or state explicitly which creator is being **kept** and why (a shared file that also defines artifacts staying alive is a legitimate keep — but it must be named as a decision, not omitted as an oversight).

> A deletion list holding a Refresher and a Driver but no Creator is the failure signature. It reads complete — the two things a human remembers touching — and it schedules the artifact's return.

### 13.3 Citers Are Edited, Not Deleted

The same grep that derives the deletion set also finds every Citer. Citers are **edited, not deleted** — a docstring naming a deleted module as a precedent needs the precedent restated or the sentence dropped, not the docstring removed. Enumerate citers in the Deliverables list as a separate group with an explicit count, so the executor can verify the count rather than judge completeness by eye.

---

## 14. Scaffold a Config-Editing Plan for a Permission Round-Trip

When a plan's deliverable includes editing `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, or `.claude/settings*.json`, the harness permission classifier gates those writes **independently of planwise authorization**. A task brief, Sprint Plan, and Master Plan that all name the file as the deliverable do **not** pre-clear it, and the classifier's decisions within a single batch are **not deterministic**.

This is a scaffolding obligation, not an execution surprise. Such a plan is predictably going to pause; scaffold it so pausing is cheap rather than destructive.

| # | Obligation | Why |
|---|---|---|
| 1 | **Declare the round-trip in the Orchestration.** Treat it the way a DB-touching task treats a connectivity precheck — a known, planned interruption. | A pause the plan predicted is an interrupt; a pause it did not is a BLOCKED cycle. |
| 2 | **Keep each edit batch to the smallest coherent set.** Do not dispatch many edits to one config file expecting all-or-nothing. | Denials are per-call, so a large batch half-applies and leaves the file internally inconsistent. |
| 3 | **Record applied-vs-denied state in Recovery immediately on any denial.** | The file can then be completed or reverted deterministically instead of re-derived from a half-remembered batch. |
| 4 | **On denial, STOP and ask — never retry verbatim.** Surface the precise file and the exact remaining edit list. | A verbatim retry in the same mode re-denies, burning a round-trip and adding nothing. |
| 5 | **Scope the brief to the minimum required sections.** | Out-of-brief "consistency nicety" edits inflate the edit count against the classifier, and can be the one edit that hits an unclearable block — losing nothing essential while adding interrupts. |

Some denials cannot be cleared by user authorization at all. The plan must be able to record such an edit as a known, non-blocking residual and continue, rather than treating the session as failed.

> [!constraint] Do Not Scaffold a Rule-Editing Task as an Ordinary File Edit
> WRONG:
> ```
> Task 03: edit {rule-file-A} + {rule-file-B}   (no round-trip declared)
> → 16 Edit calls dispatched; the classifier denies 3 of them
> → both files half-flipped and internally inconsistent; session blocked;
>   no recorded partial state, so the next attempt cannot tell applied from pending
> ```
> CORRECT:
> ```
> Orchestration declares the expected permission prompt for Task 03
> → dispatch brief-scoped edits only, smallest coherent batch
> → on first denial: write the applied-vs-denied list to Recovery, STOP, ask the user
> → after the grant: apply the remainder; record any unclearable residual as a
>   known, non-blocking follow-up
> ```

Note that this applies **in every operating configuration** — the classifier is the gate regardless of mode, so Auto Mode does not bypass it.

Planwise-level self-modification authorization does not pre-clear this harness-level gate: [session-execution-protocol.md](session-execution-protocol.md#claude-self-modification-authorization) §3 (Claude Self-Modification Authorization) authorizes Claude to add Bash permissions to `.claude/settings.json` at the planwise/workflow level, but that authorization is independent of the permission classifier described above (`agent-orchestration.md` constraints table row 12, self-modification writes) — satisfying one does not satisfy the other, and a reader who knows only §3 needs this pointer.

---

## 15. First Task of Each Sprint Records the Diff Baseline

A sprint's verification gates are only as trustworthy as the tree state they name, and a gate written as `git diff $..._BASE -- <paths>` is unfalsifiable if no task in the sprint was ever given the job of recording that base. The unset name expands to nothing, the command degrades into a bare whole-tree `diff`, and it still runs, still prints, and still reads as green or red — so the failure is invisible at exactly the moment the report is written. Scaffolding is where that gap is closed: the obligation to pin a baseline is assigned to a task at scaffold time or it does not exist at all.

> [!constraint] Every sprint carries a baseline-recording obligation, assigned to a task at scaffold time
> **Who.** The first task in the sprint that **touches the target repo** records the baseline — identified by **write-set, not by task number**. The first *numbered* task is routinely a read-only survey, inventory, or discovery pass; the first *touching* task is the one whose Output names a file in that repo. Assign the obligation to that task and state in its brief why it holds it, so a later re-ordering of the task list does not silently move the pin off the front.
>
> **Precondition.** Before pinning, the sprint's own write scope MUST be clean:
> ```bash
> git -C <repo> status --porcelain -- <this sprint's write paths>
> # MUST be empty. Non-empty → HALT. Not a warning — a halt.
> ```
> Uncommitted work inside the sprint's own write-set makes every later gate unfalsifiable in both directions: the base already contains changes this sprint did not make, so a scope gate fails the sprint for someone else's edits, while a self-containment sweep either blames it for a token it never wrote or credits its own leak elsewhere. Scope the precondition with `--` to the sprint's write paths rather than the whole repo — unrelated dirt outside the sprint's area is not this sprint's to stash, and a whole-repo cleanliness demand is the kind of gate sessions learn to override.
>
> **What.**
> ```bash
> {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> ```
>
> **Where.** The session Recovery file's Key Findings, as that task's **first** Recovery write — before any file edit, so a compaction or a crash mid-task does not lose the pin. Record the name, the value, and which task recorded it. Every later task in the sprint then **reads the value from Recovery** instead of re-deriving it: a `rev-parse HEAD` taken after the first edit is not the baseline, and a gate scoped to it is blind to every change made before it ran.
>
> **Series base.** A multi-sprint plan additionally records `{ABBREV}_SERIES_BASE` at the first task of the first sprint, for the release / whole-series battery that needs one base predating every sprint. **First-to-touch contingency:** a sprint that may not run first — any sprint the plan's ordering declares INDEPENDENT — MUST check the plan's Recovery files for an already-recorded series base before minting one, and **adopt that value verbatim** if it finds one. Only when none exists does its own HEAD become the series base.

> [!constraint] Scaffold the pin onto a task, or the sprint's gates measure the wrong tree
> WRONG — the sprint's gates all name a base, but the scaffold assigned the pin to nobody; and where a task does pin, it pins after it has already started editing:
> ```
> {Abbrev}-S{XX}-01   Output: <file A>
>   Step 1: edit <file A>   …   Step 5: {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
> {Abbrev}-S{XX}-02   Verification: git -C <repo> diff $..._BASE -- <paths> | …   # nothing ever recorded this name
> ```
> Task 02's gate expands to a whole-tree `diff` and reports every uncommitted file in the repo as this sprint's. Task 01's late pin does not rescue it either: a base taken after its own edit already contains that edit, so a gate scoped to it is blind to the one change it was written to check and reports empty for the reason that makes empty worthless.
>
> CORRECT — the pin is step 1 of the first task whose write-set touches the repo, behind the clean-scope HALT, written to Recovery before any edit:
> ```
> {Abbrev}-S{XX}-01   Output: <file A>
>   Step 1: git -C <repo> status --porcelain -- <this sprint's write paths>   # MUST be empty, else HALT
>           {ABBREV}_S{NN}_BASE=$(git -C <repo> rev-parse HEAD)
>           → Recovery Key Findings, as the session's FIRST Recovery write
>           (first sprint of a series: also check the plan's Recovery files for
>            {ABBREV}_SERIES_BASE and adopt it verbatim, else record it here too)
>   Step 2: edit <file A>
> {Abbrev}-S{XX}-02   Step 1: read {ABBREV}_S{NN}_BASE from Recovery — do not re-derive
> ```

This section owns **who** records a baseline, **when**, and **where** it lives; what a gate must then look like once a base exists — the `--` path scoping, the positive allow-list form of a scope test, and the five sub-rules governing each gate shape — belongs to [verification-gates.md](verification-gates.md#8-diff-scoped-gates-pin-a-recorded-baseline) §8, the definition site for `$..._BASE`. Its §8.1 and §8.4 state the pin mechanics and the series-base contingency from the *gate's* side; the scaffolding obligation above is what makes them satisfiable, and neither restates the other. Read §8 before authoring any diff-scoped gate.

---

## 16. Declared Parallelism Requires a Computed Write-Set Intersection

A `∥` in a Master Plan's ordering is not a scheduling preference — it is a claim that two sprints never write the same file. The claim is about file sets, so only a file-set operation can support it, and a sprint's *name* is not evidence of one. "Agents vs handlers, disjoint files" describes two clusters; a cluster is not a write-set, and the distance between the two is exactly where concurrent sessions overwrite each other. This section makes the intersection an artifact the plan has to **show**, so that a parallel declaration is either computed or absent — never inferred, and never asserted behind a marker that cannot fail.

> [!constraint] A declared-parallel pair is unsupported until its write-sets are intersected and the result is shown
> **16.1 — Every sprint declares a write-set.** Each Sprint Plan carries a `## Write-Set` section listing every directory or file the sprint **EDITS** — not the ones it merely reads — as a `| Path | Task |` table naming the task that writes each path. The read/edit distinction is the whole point: nearly every sprint reads broadly while only a handful of paths are ever written to, so an intersection computed over read-sets is meaningless. The `## Write-Set` declaration is distinct from a sequential Cross-Sprint File-Touch declaration, which compares this sprint against a *prior* sprint's already-landed delta; the write-set is the declaration an intersection is computed **from**, independent of landing order.
>
> **16.2 — Every declared-parallel pair states its computed intersection, with the result shown.** The Master Plan's `## Execution Ordering` section carries the declared-ordering line, a `### Write-Sets` table (`| Sprint | Write-set |`) collected from each Sprint Plan's own declaration, and a `### Computed Write-Set Intersection` table (`| Declared pair | Intersection | Verdict |`) with one row per `∥` pair. `∅` means the parallelism stands as declared. A non-empty intersection permits exactly two dispositions: (1) **serialize the pair, dropping `∥`**; or (2) **qualify the parallelism per-file, naming an explicit task-level ordering edge for each shared file (`S0A-01-0x → S0B-01-0y`)**. "We looked and it seemed fine" is neither disposition: an unshown result is an assertion wearing a computation's clothes, which is the precise shape that survives review. **Recompute the matrix whenever any sprint's write-set changes** — a mid-plan coordination flag that admits one new file into a sprint's scope can turn a `∅` row false, and the row does not re-derive itself.
>
> **16.3 — A file appearing under two sprints declared `∥` is a BLOCKER-grade contradiction.** When a plan's own file-touch or write-set tables list the same path under two sprints the ordering line joins with `∥`, the plan contradicts itself in writing. That is caught **mechanically**, by the structural reviewer, not by a reviewer happening to notice — the two statements typically sit sections apart, and the whole failure mode is that nobody reads them against each other.
>
> **16.4 — A gate marker may not be an assumption.** A marker reading `n/a — single-writer per sprint` is not a gate; it is an assertion with no check behind it, and it reports the same result whether or not the property it names holds. A gate marker must be a **runnable command whose failure is possible** against the pre-edit tree — for a write-set concern, typically a baseline-pinned, path-scoped diff whose output must never name the parallel sprint's files (`git -C <repo> diff --name-only $..._BASE -- {dir}/`). Before trusting any marker, confirm it can return the failing result at all: a check that cannot fail is not evidence, it is decoration.
>
> **16.5 — Cross-sprint coordination flags must be reciprocal.** If sprint A raises a flag about a file sprint B also writes, B's flag chain names A and vice versa. Without the return edge each sprint measures a **shared** threshold — a file-size gate, a line budget — against its own contribution alone, and against a baseline the other sprint has already moved. Both sprints then pass a limit their combined delta breaks, and each one's arithmetic is locally correct.

> [!constraint] Compute the intersection, or the `∥` is an unbacked claim
> WRONG — the parallelism inferred from cluster names, while the plan's own tables say otherwise:
> ```
> **Declared ordering:** `{ S0A ∥ S0B }`   ← marked *binding*
>   rationale: "agents vs handlers — disjoint files"
>
> Cross-Sprint File-Touch Matrix (same plan, further down):
>   `{path/to/shared-a.ext}`   touched by S0A, S0B
>   `{path/to/shared-b.ext}`   touched by S0A, S0B
> ```
> Nothing reconciles the two, because nothing ever intersected the write-sets. Run concurrently, two sessions append to the same two files with no lock. The sharpest detail is where the inference came from: the very document whose own resolution invalidated it — an upstream refactor map decided on a **per-source fold into a shared directory**, then a few sections later called the two sprints disjoint. The fold is what created the overlap; the disjointness claim was authored downstream of the decision that broke it and never re-derived.
>
> WRONG — the assumption-shaped gate marker:
> ```
> | `{shared/dir}/` | S0A → S0B → S0C | n/a (single-writer per sprint) |
> ```
> The directory is written by three sprints, two of them declared `∥`. The marker asserts the property the table itself disproves, and it was benign only by accident: the file lists happened not to overlap. A marker that would have read identically had they overlapped is not a gate.
>
> CORRECT — declared per sprint, intersected, the result shown per pair, and the non-empty pair disposed of explicitly:
> ```
> ### Write-Sets
> | Sprint | Write-set |
> | {Sprint-N} (A) | `{dir-one}/`, `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` |
> | {Sprint-N} (B) | `{dir-two}/`, `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` |
>
> ### Computed Write-Set Intersection
> | Declared pair | Intersection | Verdict |
> | S0A ∥ S0B | `{path/to/shared-a.ext}`, `{path/to/shared-b.ext}` | ❌ NOT disjoint — qualified per-file: `S0A-01-0x → S0B-01-0y`, `S0A-01-0z → S0B-01-0y` |
> | S0A ∥ S0C | ∅ | ✅ disjoint — parallel stands |
>
> gate marker: `git -C <repo> diff --name-only $..._BASE -- {shared/dir}/`
>                must never name the other sprint's files (pre-edit: empty)
> ```
> The `∅` row is as much a computation as the `❌` row — it is shown, dated, and recomputed when a write-set changes, not left implicit because the answer was expected.

§8 (Parallel-Scaffold Deviation Classes) and this section address different failures of the same scaffolding shape and neither substitutes for the other: §8 governs the **consistency** of the files parallel scaffolders produce — whether they look alike — while §16 governs the **correctness** of the parallel declaration itself, whether the sprints may run at once at all. A plan can pass §8 with perfectly uniform files and still be wrong here.

The mechanical enforcement of 16.3 is Check S05 in `agents/structural-reviewer.md`, which detects the file-under-two-parallel-sprints contradiction during the structural pass. This section owns **what** must be declared, computed, and shown; that check owns the detection procedure, and neither restates the other.

#### Reviewer Check 078 — Declared Parallelism Without a Computed Intersection

- **Severity / Role:** BLOCKER | Scaffolding Hygiene Reviewer | NEW
- **What:** A Master Plan declaring any sprint pair parallel without a computed write-set intersection shown for that pair; or a sprint named on the ordering line with no declared write-set; or a gate marker that is an assertion rather than a runnable command.
- **Detection:** Read the Master Plan's `## Execution Ordering` section. For each `∥` pair on the declared-ordering line, assert a matching row exists in the `### Computed Write-Set Intersection` table carrying a shown result (`∅` or the named paths) and a Verdict; assert every sprint named on that line has a `## Write-Set` section in its own Sprint Plan; then Grep the Verdict and gate-marker cells for assertion-shaped text (`n/a`, `single-writer`, `assumed`, `should be`) with no command behind it. Any one → BLOCKER.
- **Finding template:** `[BLOCKER] Declared-parallel pair {S0A ∥ S0B} has no computed write-set intersection | File: {Master Plan} | Fix per references/scaffolding-hygiene.md §16 | Confidence: HIGH`

---

*Thirteen binding hygiene rules plus three advisory practices for multi-sprint plan scaffolding. Cross-referenced from the Companion Files and Extracted Protocols table in [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols).*
