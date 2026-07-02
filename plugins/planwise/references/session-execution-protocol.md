---
description: Mandatory execution protocol - READ-CONFIRM-ACT, recovery, git workflow
---

# Session Execution Protocol

> [!binding] Enforcement
> These are not guidelines. Violations cause context loss and incomplete work.

## Table of Contents

- [1. READ-CONFIRM-ACT Pattern](#1-read-confirm-act-pattern)
  - [1.1 Confirmation Block](#11-confirmation-block)
  - [1.2 Structural Findings Beyond Literal Scope](#12-structural-findings-beyond-literal-scope)
  - [1.3 Cross-Task Coordination Flags](#13-cross-task-coordination-flags)
- [2. MUST READ References](#2-must-read-references)
- [3. Settings Modification Protocol](#3-settings-modification-protocol)
- [4. Session Rules](#4-session-rules)
- [4.5 Discovery / Meta-Plan Status with User-Action Gates](#45-discovery--meta-plan-status-with-user-action-gates)
- [5. Task Tracking](#5-task-tracking)
- [6. Refactoring Safety](#6-refactoring-safety)
- [7. Git Workflow](#7-git-workflow)

---

## 1. READ-CONFIRM-ACT Pattern

**Before ANY task:**
1. **READ** all referenced documents completely (not skim)
2. **CONFIRM** understanding with a confirmation block (see format below)
3. **ACT** only after user approval

### 1.1 Confirmation Block

> [!template] Context Confirmation
> ```
> CONTEXT LOADED
> File: {filename or "multiple files"}
> Current State: {status from document}
> Last Completed: {step/task from Recovery file}
> Next Action: {what the document says to do}
> Structural Finding: {none, or one-line summary — see §1.2}
> ```

After outputting, use `AskUserQuestion` tool: "Ready to proceed with [next action]?"

> [!constraint] Confirmation Block — All Fields Required
> WRONG — missing Current State and Last Completed fields; Next Action is vague:
> ```
> CONTEXT LOADED
> File: PRJ-S01-02-Orchestration.md
> Next Action: Continue with tasks
> ```
> CORRECT — all 4 fields present; Next Action is specific and actionable:
> ```
> CONTEXT LOADED
> File: PRJ-S01-02-Orchestration.md, PRJ-S01-02-Recovery.md
> Current State: IN_PROGRESS — Task 01 complete, Task 02 pending
> Last Completed: PRJ-S01-02-01 (Haiku-ValidateInputs) — inputs verified
> Next Action: Execute PRJ-S01-02-02-Sonnet-ImplementFeature.md
> ```

> [!binding] READ-CONFIRM-ACT Cannot Be Waived
> READ-CONFIRM-ACT applies in **every** operating configuration: Auto Mode, background mode, skill-forked contexts, plan mode, `claude --agent` sessions, and any other runtime configuration of Claude Code. There is no mode that exempts a session from CONFIRM. The Auto-Mode directive "prefer action over planning" applies to ad-hoc decisions inside a routine task — it does NOT waive the CONFIRM step for protocol-driven workflows.
>
> **For `/planwise plan --scaffold` specifically:** before writing any plan file (Master Plan, Execution Input, Sprint Plan, Orchestration, Recovery, task file, Outputs/), the scaffolding agent MUST emit a confirmation block enumerating expected outputs and wait for user approval. The block MUST list:
>
> ```
> CONTEXT LOADED
> Plan: {plan name + abbreviation}
> Expected outputs: 1 Master Plan + N Execution Inputs + M Sprint Plans
> Per-sprint session count: Sprint-01: K1 sessions, Sprint-02: K2 sessions, ...
> Total file count: F files (Σ session-folder × per-session file count + Master Plan + EIs + Sprint Plans)
> Next Action: Write {first file path}
> ```
>
> Skipping CONFIRM in any of these contexts is a known root-failure pattern: a scaffolder run in Auto Mode that wrote 20+ plan files with no CONFIRM, producing an incoherent plan tree. It is not a stylistic preference; it is the protocol's load-bearing gate.

### 1.2 Structural Findings Beyond Literal Scope

> [!binding] Phase-1 Scope-Expansion Gate
> When the READ step uncovers a structural defect that makes the literal scope produce a self-inconsistent artifact, the CONFIRM block MUST surface it BEFORE asking the user to proceed. Executing the literal scope silently — when the executor knows it publishes a defective artifact — is a protocol violation. Executing an expanded coherent scope silently — without an explicit user choice — is also a protocol violation.

Apply this rule whenever a single, narrowly-scoped task (typically from an audit punch-list, a backlog item, or a remediation directive) references a defect inside a larger artifact, AND the READ step reveals that the minimum *coherent* fix requires touching adjacent latent defects the task did not name. Typical patterns:

- Table-of-contents ↔ body ordering mismatches (literal "add §X to ToC" leaves §X anchoring into a mid-section H3, or leaves adjacent §Y/§Z still absent)
- Anchor ↔ heading-level mismatches (literal "add cross-reference to §X" requires promoting §X's heading first)
- Partial enumerations (literal "fix item 3 in the list" requires renumbering 4-7)
- Schema-pin ↔ deployed-schema drift discovered during a narrow column change

When the READ surfaces such a finding, the CONFIRM block MUST add a `Structural finding` paragraph and offer the user TWO explicit options:

> [!template] Structural Finding + Option Block
> ```
> Structural finding: {one-paragraph description of the latent adjacent defect
>                       and why the literal scope produces a self-inconsistent
>                       artifact}.
>
> Option A (Coherent): {describe the expanded scope, the structural rationale,
>                       and the expected line / heading-level / file-touch impact}.
> Option B (Literal):  {acknowledge that the literal scope produces a known-
>                       defective artifact and the original directive's intent
>                       is not satisfied; name the residual defect class}.
> ```

Then call `AskUserQuestion` with both options. The executor MUST NOT pick a path before the user answers; the option block is not a recommendation paragraph.

> [!constraint] Structural Finding Must Surface, Not Disappear
> WRONG — executor reads, notices the literal scope is incoherent, silently expands and writes:
> ```
> (reads target file)
> → notices §11 is H3 inside §9, and §12/§13 are absent from ToC
> → silently promotes §11→H2, relocates after §10, adds §11/§12/§13 to ToC
> → writes the file
> ```
> Result: ~270 lines moved and 15 heading levels changed during what the
> directive called a "ToC fix." User has no record of the expansion.
>
> WRONG — executor reads, notices the incoherence, executes the literal scope anyway:
> ```
> (reads target file)
> → notices §11 H3-inside-H2 misplacement and §12/§13 ToC absence
> → adds only the literal §11 ToC entry; leaves §11 anchoring into §9 mid-section,
>   leaves §12/§13 absent
> → writes the file
> ```
> Result: ToC lists §11 but skips §12/§13; §11 anchor points into §9; body order
> remains non-monotonic. The "fix" publishes an internally inconsistent document.
>
> CORRECT — executor surfaces the finding in CONFIRM with two options and gates on `AskUserQuestion`:
> ```
> CONTEXT LOADED
> File: {target file}
> Current State: directive scope = "add §11 to ToC"
> Last Completed: prior task complete
> Next Action: gated on user choice below
> Structural Finding: §11 is currently H3 inside §9, and §12/§13 are absent from
>                     the ToC. Adding only §11 produces a ToC that lists §11 but
>                     skips §12/§13 and anchors §11 into a mid-section H3.
>
> Option A (Coherent): promote §11→H2, relocate after §10, promote 15 H4
>                       children→H3, add §11/§12/§13 to ToC (~270 lines moved,
>                       15 heading-level changes).
> Option B (Literal):  add only the literal §11 ToC entry; leave §11 anchored
>                       inside §9 and §12/§13 absent from ToC. Residual defect:
>                       internally inconsistent ToC vs body ordering.
> → AskUserQuestion("Choose Option A (coherent expansion) or Option B (literal scope)")
> ```

#### Audit-Trail Requirement When Expansion Is Approved

When the user picks Option A (or any expansion beyond the literal directive), the session MUST record the decision in two places:

| File | What to Record | See |
|------|----------------|-----|
| Recovery file | A row in the `Scope-Expansion Decisions` section naming: directive scope (literal), expanded scope, structural rationale, line / heading / file-touch impact, Phase-1 approval reference (timestamp or AskUserQuestion turn) | [templates/recovery.md](../templates/recovery.md) |
| Summary file | A `Scope-Expansion Decisions` block in Context Notes linking back to the Phase-1 approval reference (so later reviewers can reconcile "why did you also touch X?") | [templates/summary-template.md](../templates/summary-template.md) |

The audit trail is NOT optional when the expansion is approved. A scope-expanded execution without a Recovery + Summary trail looks indistinguishable from a silent expansion to any later reviewer.

> [!practice] When in Doubt, Surface It
> If the executor is uncertain whether a finding is "structural" enough to warrant Option A/B, surface it anyway. The cost of asking is a single `AskUserQuestion` round-trip; the cost of NOT asking is either a defective artifact or an undocumented scope expansion. Bias toward surfacing.

> [!practice] Doctrinal Sweep Before Declaring a Claim Fixed
> When the session's scope involves correcting a factual claim (a rule, a parameter, a threshold, an assertion) that is stated in a source file and cited by consumers, do NOT declare it fixed after editing the source alone. First grep the entire plugin surface for every phrasing of the claim (the exact assertion text, common paraphrases, and any regex that catches the misconception). If instances fall outside the literal task scope, surface them as a structural finding and let the user decide (Option A / Option B above). Re-run the sweep at the end of the session and confirm only correct/negated phrasings remain. A citation chain is coherent only when the source and every consumer agree.

### 1.3 Cross-Task Coordination Flags

> [!binding] Downstream-Propagation Gate
> When a task surfaces an observation that constrains, sequences, or unlocks work in a DIFFERENT session, sprint, or plan, the orchestrator MUST (a) record the observation as a Cross-Task Coordination Flag in this session's Recovery file at the moment it is surfaced, AND (b) propagate every flag into the downstream consumer's task or orchestration file as part of session closeout. Closeout without propagation leaves the downstream agent to re-derive context the orchestrator already validated — wasting tokens at best, dropping a constraint on the floor at worst.

Apply this rule whenever an upstream task's output names a sequencing constraint, a content-routing dependency, a cluster-classification ambiguity, a release-quality tradeoff, or any other observation whose CONSUMER is a downstream task the upstream orchestrator can name. Typical patterns:

- **Sequencing constraints:** "Task X's SPLIT must land before Task Y's MOVE-IN, otherwise Y has nowhere correct to route its additions."
- **Content-routing dependencies:** "After the SPLIT, references to §A go to Part-1, references to §B go to Part-2 — downstream link updates must respect this routing."
- **Cluster-classification ambiguity:** "After the SPLIT, Part-2's topical cluster membership is unresolved; downstream themeing must pick a home."
- **Release-quality wins beyond scope:** "Doing this restructure also unlocks a base-context token reduction — flag as a candidate even though it wasn't the proximate goal."
- **Cross-plan flow-through:** an upstream plan's findings constrain the scope or sequencing of a follow-up plan that hasn't been written yet.

A flag is NOT a scope-expansion (§1.2 governs that — work done outside the literal scope) and is NOT a generic finding (those go in `Key Findings`). A flag specifically names a DOWNSTREAM consumer who needs to ACT on the observation.

#### Recording the Flag (At Surface Time)

When a task surfaces a coordination flag during execution, the orchestrator adds a row to the Recovery file's `Cross-Task Coordination Flags` section IMMEDIATELY — not at closeout. The same context-compaction risk that motivates per-task Recovery updates applies here: a flag held only in conversation context dies on the next compaction.

> [!template] Coordination Flag Row
> ```
> | Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
> |--------|-------------|---------------------|-------------|---------------------|
> | 1      | {abbrev}-S{XX}-{YY}-{##} | {abbrev}-S{XX}-{YY}-{##} or {sprint} or {plan} | {one-paragraph description of the constraint / dependency / opportunity} | {what the downstream agent should do — sequence, route, resolve, evaluate} |
> ```

#### Propagating the Flag (At Closeout)

At Phase 4 closeout, the orchestrator MUST add each flag to the downstream consumer's task file (preferred) or orchestration file. The destination depends on who the consumer is:

| Downstream Consumer | Propagate To |
|---------------------|--------------|
| A specific named task in a later session | That task's file under a `## Pre-Known Cross-Task Coordination Flags` section |
| A whole session (consumer task unclear) | That session's orchestration file under a `## Pre-Known Cross-Task Coordination Flags` section |
| A future sprint (consumer task not yet authored) | The sprint plan's `## Carried-Forward Coordination Flags` section, to be re-propagated when tasks are scaffolded |
| A follow-up plan not yet written | The current Master Plan's `## Carried-Forward Coordination Flags` section + the rollup/handoff task file |

Each propagated entry MUST be tagged with the source session ID and the surface date so the downstream agent recognizes it as orchestrator-validated context (do NOT re-derive) and can age it for staleness.

> [!template] Propagated Flag Block
> ```markdown
> ## Pre-Known Cross-Task Coordination Flags
>
> These flags were surfaced and reconciled by upstream session orchestrators. Treat them as orchestrator-validated context — do NOT re-derive.
>
> ### From {source-session-id} ({source-session-name}) — recorded {YYYY-MM-DD}
>
> 1. **{Short flag headline}.** {Paragraph describing the constraint / dependency / opportunity and the recommended action.}
> 2. **{Short flag headline}.** {...}
>
> ### From {next-source-session-id} — to be appended when session completes
>
> *(none yet)*
> ```

The reserved placeholder for later sources is intentional — it tells future closeout orchestrators where to append without re-deriving the section structure.

#### Audit-Trail Requirement

| File | What to Record | See |
|------|----------------|-----|
| Recovery file | A row in the `Cross-Task Coordination Flags` section per flag | [templates/recovery.md](../templates/recovery.md) |
| Summary file | A `Cross-Task Coordination Flags` block in Context Notes mirroring the Recovery rows (so later reviewers see what was handed off without opening Recovery) | [templates/summary-template.md](../templates/summary-template.md) |
| Downstream task / orchestration / sprint plan | A `Pre-Known Cross-Task Coordination Flags` section per the propagation table above | — |

Mirror requirement is the same as §1.2: a flag recorded only in Recovery and never propagated looks indistinguishable from a dropped constraint to any later reviewer.

> [!constraint] Flag Lifecycle Discipline
> WRONG — task surfaces a coordination flag in conversation, orchestrator notes it mentally, never writes it down:
> ```
> (task 03 completes, reports "by the way, this SPLIT has to precede task 04's MOVE-IN")
> → orchestrator: "noted, I'll remember"
> → continues to task 04
> → next session orchestrator never sees the flag
> ```
> Result: downstream agent either re-discovers the constraint (cost: tokens + risk of missing it) or executes in the wrong order and breaks the artifact.
>
> WRONG — orchestrator writes flag to Recovery but never propagates at closeout:
> ```
> (records flag in Recovery `Cross-Task Coordination Flags` section)
> → closeout runs through summary, lessons, git commit
> → flag stays buried in upstream Recovery; downstream task file never updated
> → downstream agent reads only its own task file → flag is invisible
> ```
> Result: a recorded-but-stranded flag is functionally identical to a dropped one.
>
> CORRECT — surface-time recording in Recovery, closeout-time propagation to downstream:
> ```
> (task surfaces flag)
> → orchestrator writes Recovery row immediately
> → Phase 4 closeout reads every Recovery flag row
> → for each row, propagates to the downstream consumer per the destination table
> → tagged with source session + date so the downstream agent treats as validated context
> ```

> [!practice] Default to Propagation
> If the consumer is ambiguous between a specific task and a whole session, propagate to BOTH — the task file for the agent that will act on it, the orchestration file for the orchestrator who will dispatch. Cost of duplication is two short paragraphs; cost of misrouting is a missed constraint.

---

## 2. Reference Documents

Detailed reference material for this project. Documents with a **Must Read** condition MUST be read before the corresponding task type.

| Category | Document | Purpose | Must Read | Last Verified |
|----------|----------|---------|-----------|---------------|
| | | Add your project's reference documents here. Use paths from config.yaml. | | |

**Staleness Thresholds:**

| Status | Age | Action |
|--------|-----|--------|
| Current | < 60 days | No action needed |
| Caution | 60-90 days | Review recommended |
| Stale | > 90 days | MUST review before use |

**Maintenance:** Update `Last Verified` when a document is modified (update its `Last Updated:` header) or reviewed without changes (update this table only).

---

## 3. Settings Modification Protocol

> [!protocol] Settings Modification
> **Before modifying ANY settings file:**
> 1. **READ** the Settings-Reference document for your project
> 2. **IDENTIFY** the correct file using the ownership matrix
> 3. **SCAN** code/docs for dependencies on the setting
> 4. **MODIFY** only what's necessary
> 5. **TEST** the change works
> 6. **DOCUMENT** if the setting is referenced elsewhere

**File Ownership Quick Reference:**

| Want To... | Modify This File |
|------------|------------------|
| Add application config | Your project's configuration files |
| Add Claude permission | `.claude/settings.json` |
| Add behavioral rule | `.claude/rules/{name}.md` |
| Add user-invocable skill | `.claude/skills/{name}/SKILL.md` |

### Claude Self-Modification Authorization

> [!binding] Self-Modification Scope
> Claude is AUTHORIZED to modify `.claude/settings.json` to add new Bash permissions when:
> - A command is needed for a project-related task
> - The command relates to technologies used in this project
> - The permission follows the existing pattern format
>
> **Process:** Add the permission, test it works, commit with the task. No pre-approval needed.

**Authorized Categories:**

| Category | Examples |
|----------|----------|
| Project build tools | Your project's build tools, CLI utilities |
| Git / GitHub | `git`, `gh` |
| Cloud services | Your cloud platform CLI tools |
| Package managers | Your project's package managers |
| File Operations | Standard Unix/Windows commands |
| Build/Test Tools | Project-relevant tooling |

---

## 4. Session Rules

> [!binding] Session Invariants
> - **Recovery file:** Update AFTER EVERY TASK (not batched)
> - **File structure:** ONE file per task per agent (e.g., `CI-S01-01-Haiku-TableCounts.md`)
> - **Output file:** REQUIRED at session end (`Outputs/{Abbrev}-Summary.md`)
> - **Agent delegation:** Haiku (lookups), Sonnet (code), Opus (decisions)

### After Each Step

> [!checklist] Post-Step Verification
> - [ ] Update Recovery file immediately
> - [ ] Save outputs to Outputs/ folder
> - [ ] Verify step success criteria
> - [ ] Check for blocking issues
> - [ ] Estimate remaining token budget

> [!constraint] Recovery File — Minimum Required Fields
> WRONG — missing timestamp, missing Current Step, Step Completion table absent, Key Findings empty:
> ```
> # Recovery: PRJ-S01-01
>
> Session started. Working on tasks.
>
> ## Files Modified
> - src/models/User.ts - updated
> ```
> CORRECT — all required fields present, step table populated, findings preserved across compaction:
> ```
> # Recovery: PRJ-S01-01
>
> **Last Updated:** 2026-02-17 14:32
> **Current Step:** 3 (Task 03 - Sonnet-ImplementFeature)
> **Session Status:** IN_PROGRESS
>
> ## Step Completion Status
> | Step | Task                        | Status   | Completed        |
> |------|-----------------------------|----------|------------------|
> | 1    | Haiku-ValidateInputs        | COMPLETE | 2026-02-17 13:45 |
> | 2    | Haiku-GatherContext         | COMPLETE | 2026-02-17 14:10 |
> | 3    | Sonnet-ImplementFeature     | PENDING  |                  |
>
> ## Key Findings
> - All input schemas validated; 2 missing fields identified and added
> - Authentication flow confirmed working across all endpoints
>
> ## Files Modified
> - src/models/User.ts - added missing fields
> ```

### Session-End Lesson Capture

> [!protocol] Lesson Capture
> At the end of each session, ask: **"Were any lessons learned during this session?"**
>
> If yes:
> 1. Read template from `LessonsLearned/00-Index-LessonsLearned.md` (Lesson File Template section)
> 2. Create lesson file: `LessonsLearned/LL-{NNN}-{Domain}-{Name}.md`
> 3. Add row to master table in `00-Index-LessonsLearned.md`
> 4. Commit lesson file and updated index

### Iteration Loop

> [!checklist] Iteration Safety
> - [ ] Completion criteria defined
> - [ ] Max iterations set (default: 50)
> - [ ] Fallback instructions documented
> - [ ] Self-correction pattern enabled
> - [ ] Build verification after changes

---

## 4.5 Discovery / Meta-Plan Status with User-Action Gates

> [!binding] Discovery Status with User-Action Gates
> When a Discovery or Meta-Plan has user-action gates outside `/planwise run` scope (e.g., "user reviews Consolidated Context before scaffolding begins"), Master Plan Status is `IN_PROGRESS` with an explicit `awaiting {user action}` note — NOT `COMPLETE`, even when all sprints have completed their tasks.

### State Table

| All Sprints Complete? | User-Action Gate Pending? | Master Plan Status |
|-----------------------|---------------------------|--------------------|
| Yes | No | COMPLETE |
| Yes | Yes | IN_PROGRESS — awaiting {user action} |
| No | — | IN_PROGRESS |

### WRONG/CORRECT

> [!constraint] Master Plan Status — All-Sprints-Complete + User-Gate-Pending
> WRONG — status set to COMPLETE even though user must act before scaffolding can begin:
> ```
> Status: COMPLETE
> # All 3 Discovery sprints landed, but user has not yet reviewed Consolidated Context
> # to confirm scaffolding scope — scaffolding cannot begin without that confirmation.
> ```
> CORRECT — status reflects pending user action:
> ```
> Status: IN_PROGRESS — awaiting user confirmation on scaffolding scope
> # (Consolidated Context Part {N} is ready for review; scaffolding starts after approval)
> ```

> [!practice] Sprint Overview Row vs Master Plan Status Distinction
> Even when Master Plan Status is `IN_PROGRESS` (awaiting user action), individual Sprint Overview rows SHOULD flip to ✅ COMPLETE if their sprints have finished. The Master Plan Status field encodes "all sprints landed but downstream scaffolding awaits user input" — Sprint Overview rows reflect per-sprint progress, not the overall gate status.

> [!practice] /planwise run Phase 4.3 Handler — User-Action-Gate Check
> When `/planwise run` Phase 4.3 detects all sprints COMPLETE, the handler MUST check the Master Plan's "Project Complete When" section for user-action gates. If user-action gates remain open, set Master Plan Status to `IN_PROGRESS — awaiting {user action}` rather than COMPLETE. See `handlers/run.md` Phase 4.3 for implementation.

---

## 5. Task Tracking

> [!hazard] Environment Constraint
> TaskList tools (`TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate`) are **CLI-only** — they do NOT work in VS Code Extension.

> [!decide] Track Selection
> | If... | Then... |
> |-------|---------|
> | Using VS Code Extension (or TaskList unavailable) | **Track A:** Use task table in Orchestration.md; update Recovery file AFTER EACH task; mark tasks PENDING → IN_PROGRESS → COMPLETE in Recovery; do NOT attempt TaskList tools |
> | Using Claude Code CLI | **Track B:** Use TaskList tools for visual tracking (`Ctrl+T`); update BOTH TaskList AND Recovery file after each task; Recovery file remains authoritative source |

**When to Create Task List (CLI only):**

| Condition | Create TaskList? |
|-----------|------------------|
| 3+ distinct steps | Yes |
| Multi-file changes | Yes |
| Session/sprint execution | Always |
| Single trivial fix | No |

> [!binding] Recovery Primacy
> Recovery file is ALWAYS mandatory — TaskList is a visual convenience layer (CLI only).

> [!constraint] Task List Isolation (Concurrent Sessions)
> The task list is **shared** across all CLI sessions. Multiple sessions may have active tasks simultaneously.
>
> **WRONG:** Delete or overwrite existing tasks to make room for yours
> ```
> ❌ TaskUpdate(taskId: "81", status: "deleted")  # Task belongs to another session!
> ❌ Clear all tasks, then create mine
> ```
>
> **CORRECT:** Add your tasks alongside existing ones
> ```
> ✅ TaskList → see existing tasks → TaskCreate (append yours)
> ✅ Use subject prefixes to distinguish sessions: [KMR-01], [MSQ-03]
> ```
>
> **Rules:**
> - **NEVER** delete, complete, or modify tasks you did not create
> - **ALWAYS** run `TaskList` before creating tasks to see what already exists
> - **USE** subject prefixes (e.g., `[ABBREV-##]`) to identify which session owns each task
> - **ONLY** update tasks whose prefix matches your current session

---

## 6. Refactoring Safety

> [!constraint] Refactoring Backup (Files 300+ lines)
> | Phase | Action |
> |-------|--------|
> | **BEFORE** refactoring | Create `{filename}.backup-{YYYY-MM-DD}.txt` in same folder |
> | **AFTER** refactoring | Run `/code-review` on refactored files to verify quality |
> | **AFTER** verified working | Move backup to `RefactoringArchive/` |

---

## 7. Git Workflow

> [!binding] Git Discipline
> - **Commit** at the end of each session
> - If session produced code changes and `/code-review` has not already been run on all changed files, run `/code-review` before committing
> - **Push** automatically (no confirmation needed)
> - **git add** specific files (never `git add .` or `git add -A`)

---

*Full details: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md), [session-plan-requirements.md](session-plan-requirements.md)*
