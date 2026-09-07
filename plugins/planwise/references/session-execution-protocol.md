---
description: Mandatory execution protocol - READ-CONFIRM-ACT, recovery, git workflow
---

# Session Execution Protocol

> [!binding] Enforcement
> These are not guidelines. Violations cause context loss and incomplete work.

## Table of Contents

- [1. READ-CONFIRM-ACT Pattern](read-confirm-act-protocol.md) (§1.1 Confirmation Block, §1.2 Structural Findings Beyond Literal Scope, §1.3 Cross-Task Coordination Flags) — extracted to [read-confirm-act-protocol.md](read-confirm-act-protocol.md)
- [2. MUST READ References](#2-must-read-references)
- [3. Settings Modification Protocol](#3-settings-modification-protocol)
- [4. Session Rules](#4-session-rules)
- [4.5 Discovery / Meta-Plan Status with User-Action Gates](#45-discovery--meta-plan-status-with-user-action-gates)
- [5. Task Tracking](#5-task-tracking)
- [6. Refactoring Safety](#6-refactoring-safety)
- [7. Git Workflow](#7-git-workflow)

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

### Session-Length Checkpoint

> [!binding] Resume State Must Be Complete Before a Boundary Is Offered
> A session-length boundary is a net win only when the next session can resume without re-deriving anything. An incomplete handoff costs more than the tokens the split saved. The checkpoint therefore **recommends and records** — it never force-terminates a session, and the only writes it mandates are the resume-state writes required above. `handlers/run.md` Step 3.5 evaluates it at each task boundary.

The thresholds are read from config, never hardcoded: `context.token_saver_session_checkpoint.window` (shipped default 400,000 projected window) and `context.token_saver_session_checkpoint.turns` (shipped default 194 turns), both through `scripts/config_loader.py::get_token_saver_extension_config()`. Whichever is reached first trips the checkpoint, and `context.token_saver_orchestrator_advisory: off` disables the evaluation entirely.

Those two defaults are chosen operating points derived from measured accumulation bands, not statistical boundaries. 194 is the measured minimum turn count of the above-500,000 band (22 of the 99 measured sessions). 400,000 is a level the heaviest sessions *cross* rather than their onset — the measured 90th percentile is 565,189 across all sessions — and it is chosen because the delegated median of roughly 455,000 is already too late to act on.

> [!checklist] Resume-State Completeness — every box before a boundary is offered
> - [ ] The in-flight task is COMPLETE — a boundary never interrupts a dispatch
> - [ ] Recovery is current through that last completed task: status, timestamp, Key Findings, Files Modified, Change Log row
> - [ ] `Current Step` names the NEXT task, not the one just finished
> - [ ] Every coordination flag surfaced so far is recorded and routed to its destination
> - [ ] A session-boundary note names the **exact next dispatch** — task id, its agent, and the dependency layer it belongs to
> - [ ] Every output Recovery claims exists on disk at the path claimed for it
> - [ ] The carrying-cost arithmetic is logged — projected window, the threshold that tripped, the break-even — on both branches, since a declined split is evidence too
>
> An unchecked box means the resume state is not yet complete: finish it, then offer the boundary. If a box cannot be checked at all, do not offer the boundary — continue the session and record why.

### Session-End Lesson Capture

> [!protocol] Lesson Capture
> At the end of each session, ask: **"Were any lessons learned during this session?"**
>
> If yes:
> 1. Read template from `LessonsLearned/00-Index-LessonsLearned.md` (Lesson File Template section)
> 2. Create lesson file: `LessonsLearned/LL-{NNN}-{Domain}-{Name}.md`
> 3. Add row to master table in `00-Index-LessonsLearned.md`
> 4. Commit lesson file and updated index

### Post-Session Artifact Completeness

> [!checklist] Post-Session Artifact Completeness
> - [ ] The session Summary's Consumption Record is filled with the `measured|estimated` tag on every measured field
> - [ ] `orchestrator_window_total` and `summed_dispatch_budgets` are recorded as distinct values, never summed into one figure
>
> See [templates/summary-template.md § Consumption Record](../templates/summary-template.md#consumption-record) for field semantics — this checklist verifies completeness, it does not restate the field list.

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

Backup discipline first, then §6.1 — the four ways a refactor's change surface reaches past its edit set while every declared gate stays green.

> [!constraint] Refactoring Backup (Files 300+ lines)
> | Phase | Action |
> |-------|--------|
> | **BEFORE** refactoring | Create `{filename}.backup-{YYYY-MM-DD}.txt` in same folder |
> | **AFTER** refactoring | Run `/code-review` on refactored files to verify quality |
> | **AFTER** verified working | Move backup to `RefactoringArchive/` |

### 6.1 A Refactor's Blast Radius Exceeds Its Edit Set

The four sub-rules below share one property: in every originating case **the edit set was correct and complete on its own terms, and every declared gate passed.** What was wrong was the change *surface* — wider than the edit set, and invisible to anything mechanical the task had declared. They are ordered by edit type — collapse, consolidate, move, gate the move — so a reader doing one of those operations finds theirs first.

> [!constraint] Sub-rule A — deduplication is a merge with an explicit set difference
> Deduplication is framed as *removing redundancy*, which presumes the copy being deleted is a **subset** of the one being kept. That presumption is almost never checked and routinely false: two descriptions of one behaviour drift *apart*, each accreting details the other lacks.
>
> ```
> for each claim in B (the copy being deleted):
>     is it present in A (the survivor)?  -> yes: safe to drop
>                                         -> no:  MERGE INTO A FIRST, then delete
> ```
>
> In the originating case the "duplicate" table described one write documented **only** there. Deleting it outright would have left that behaviour documented in exactly zero places, with every gate reporting success.
>
> Three consequences:
>
> 1. **Audit the promotion target, not just the deleted copy.** The moment A becomes the single source, A's omissions stop being harmless and become defects — they were masked by B's existence, not absent.
> 2. **Expect the audit to expand the edit set, and let it.** A collapse that touches only the file you set out to shrink has not been audited.
> 3. **Do not accept a pattern search as the verification.** When two documents disagree *without sharing vocabulary* — which is exactly why they were allowed to disagree in the first place — no pattern matches both, and an empty result means nothing. The gate is an **end-to-end read of both documents**, and it is stated as such in the acceptance criteria so it cannot be quietly downgraded to a mechanical check.
>
> The shape generalises past prose: merging rules, deduping references, collapsing config layers, replacing inline docs with a link.

> [!constraint] Sub-rule B — measure copy count before and after an extraction
> An extraction has done its job only if the number of implementations goes **DOWN**. One dedup task extracted duplicated config-block surgery into a shared home, reported COMPLETE with every declared gate green — both pin suites byte-unmodified, full suite green, a real discrimination proof — and filled both consumers' import-guard fallbacks with full-fidelity duplicates of the logic just extracted:
>
> | | Implementations | Lines |
> |---|---|---|
> | Before | 2 | baseline |
> | After | **3** | **+124** |
>
> The task's own "zero duplicated logic remains" criterion was unmet on disk. **Green gates cannot establish this, because none of them measures copy count.**
>
> The probe: pick a distinctive token from the logic being consolidated — a local variable name, not a function name, which the extraction legitimately keeps — and count the files carrying it at both ends.
>
> ```
> Grep  pattern='{distinctive local token}'  path='{target tree}'  output_mode='files_with_matches'
> # BEFORE: N files.  AFTER: must be fewer. Equal or greater = the extraction added a copy.
> ```
>
> **When a fallback must exist, prefer failing loudly to degrading silently — above all for code that writes user data.** A trivial no-op-safe fallback is fine. A duplicated *algorithm* behind an import guard is a divergence bomb with no detonator: nothing tests it, nothing compares it to the original, and it activates precisely when the system is already in an unexpected state. In the originating case the copies were marked no-coverage (so drift was structurally invisible) and they mutate user config (so drift means silently writing differently-shaped data, not crashing).
>
> **Precedent caveat:** an existing precedent in the codebase is evidence about what was done before, not about what is correct now. Weigh it by whether its **consequences** transfer, never by whether its shape matches.

> [!constraint] Sub-rule C — a move invalidates every patch that steers the moved symbol
> A moved function resolves its globals in its **new** module, and a re-export binds a NAME rather than a live indirection. So a patch installed against the old home compares the real code path against itself, passes, and pins nothing. A 9-module decomposition kept the suite green at 376 throughout and kept every old import path resolving; neither protects a test that reaches *in* to steer behaviour. Twelve of the affected sites steered the destructive-path invariant arbiters.
>
> The timing is the trap: the old binding identity was true right up until the function moved, so every patch worked and every green suite was honest.
>
> ```
> WRONG — patch target follows the import the test file uses:
>   patch('old_home.helper')        # old_home now re-exports; the patch binds a
>                                   # name nothing calls. Test passes, pins nothing.
> CORRECT — patch target follows the DEFINING module:
>   patch('new_module.helper')      # where the function's globals now resolve
> ```
>
> Three rules make the repair safe:
>
> 1. **Repoint targets and imports only.** Zero assertions, expected values, call counts or fixture data may change. Prove it with a **normalization diff**: rewrite the new module tokens back to the old name and diff against the pre-change file. A correct repoint collapses to pure additions.
> 2. **Prove each repoint discriminates.** A repointed patch that still fails to steer *looks* fixed and pins nothing — the same failure one address later.
> 3. **Watch for one fixture feeding two modules** after a seam splits. Independent bindings need independent patches; collapsing them to one silently unpins whichever consumer lost its patch.
>
> Corollary: a symbol the moved code needs may itself have to follow it, because a function's free-variable lookup resolves in its **defining** module, not its calling one.

> [!constraint] Sub-rule D — name the lifecycle stage your gate observes
> **A gate and the failure it should catch can live at different lifecycle stages, and green is the default answer for anything a gate structurally cannot reach.** Splitting a 3,685-line test monolith was gated on collected-count conservation. Two real bugs raise errors **when a test runs**, not when it is collected; the count stayed exactly 376 → 376 and the gate read fully green while tests errored.
>
> ```
> WRONG — conservation alone:
>   <collect-only> | tail -1        # 376 -> 376, EQUAL -> "conserved" -> PASS
>   # says nothing about whether any of the 376 actually executed successfully
> CORRECT — all three, in this order:
>   <compile-check each output file>  # parse errors (a slicing script's newline bug lands here)
>   <collect-only> | tail -1          # nothing dropped or duplicated
>   <run the suite> | tail -1         # nothing broken at execution
> ```
>
> Two corollaries:
>
> - **Run a per-module undefined-name lint on each newly created file, before the suite.** It is the cheap *complete* cross-reference check; a careful manual read still missed 15 undefined names across four modules.
> - **During an extract-module refactor, "remove unused imports" is not a safe cleanup.** A module import may be a patch target that appears nowhere else in the file. Compute each file's import set from what its body references, and treat over-importing as the cheap failure.
>
> Generalise in one line: for any gate, state the stage it observes — parse, collect, execute, integrate — and confirm something else covers the stages after it. This is about the **stage** a gate reaches, not the **shape** a pattern can see; the two fail independently.

#### Reviewer Check 089 — Refactor Deliverable With No Blast-Radius Sweep

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** When a plan's deliverables include a **move, extraction, consolidation, or collapse**, its criteria MUST carry at least one blast-radius gate — because the edit set can be correct and complete on its own terms while the change surface is wider, and nothing the task already declares will object. The four gates that reach past the edit set are: a **copy-count probe measured at both ends**; a **set-difference audit** of the deleted copy against the survivor; a **sweep of the test surface** for patches steering the moved symbols; and an **execution-stage gate** beyond collection or compilation. A plan carrying none of them has gated the edit, not the change.
- **Detection:**
  1. Identify deliverables whose objective contains a move, extraction, consolidation, collapse, dedup, or merge verb.
  2. For each, read the criteria and classify every gate by the question it answers. Count how many of the four blast-radius gates are present. Zero → WARNING.
  3. For a collapse or dedup specifically: check for a stated end-to-end read of both documents or bodies. A pattern-search gate offered as the conservation check → WARNING (two descriptions that disagree share no vocabulary, so no pattern matches both).
  4. For an extraction: check for a copy-count probe with a BEFORE value recorded. A criterion phrased "zero duplicated logic remains" with no measurement behind it → WARNING.
  5. For a module move: check for a sweep of the test surface for patch targets naming the old home, and for a normalization diff proving the repoint changed only targets and imports.
  6. For any gate policing a move: name the lifecycle stage it observes. Collection- or compile-stage only, with no execution-stage gate after it → WARNING.
- **Finding template:**
```
[WARNING] Refactor deliverable gated on its edit set, not its change surface
File: {plan or task file path} | Location: {Deliverables | Success Criteria}
Issue: Deliverable {id} is a {move|extraction|consolidation|collapse} and its criteria carry none of: a copy-count probe measured at both ends, a set-difference audit of the deleted copy against the survivor, a test-surface sweep for patches steering the moved symbols, an execution-stage gate beyond {collection|compilation}
Fix: Add the blast-radius gate matching the edit type per references/session-execution-protocol.md §6.1 — for a collapse, an end-to-end read of both bodies stated in the criteria; for an extraction, a BEFORE/AFTER copy count on a distinctive local token; for a move, a patch-target sweep plus a normalization diff; and name the lifecycle stage every gate observes | Confidence: MEDIUM
```

---

## 7. Git Workflow

> [!binding] Git Discipline
> - **Commit** at the end of each session
> - If session produced code changes and `/code-review` has not already been run on all changed files, run `/code-review` before committing
> - **Push** automatically (no confirmation needed)
> - **git add** specific files (never `git add .` or `git add -A`)
> - **Prior-sprint Outputs guard** (run handler Step 4.0) must have passed before the session-end commit, or carry a recorded Recovery override

---

*Full details: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md), [session-plan-requirements.md](session-plan-requirements.md), [read-confirm-act-protocol.md](read-confirm-act-protocol.md) (§1 READ-CONFIRM-ACT Pattern)*
