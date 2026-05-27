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
> The READ-CONFIRM-ACT pattern applies before ANY task execution, including plan scaffolding. When `/planwise plan --scaffold` produces a CONFIRM block, the user MUST approve it before any Write or Edit tool calls are made. Skipping the CONFIRM step and proceeding directly to writes is a protocol violation.
>
> WRONG — agent reads orchestration and immediately begins writing task files without CONFIRM:
> ```
> (reads Orchestration.md) → (writes Sprint-01/Session-01/Orchestration.md directly)
> ```
> CORRECT — agent reads orchestration, produces CONFIRM block, waits for approval, then writes:
> ```
> (reads Orchestration.md)
> → CONTEXT LOADED / File: Orchestration.md / Current State: ... / Next Action: scaffold Sprint-01
> → AskUserQuestion("Ready to proceed with scaffolding Sprint-01?")
> → (user approves) → (writes Sprint-01/Session-01/Orchestration.md)
> ```

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
