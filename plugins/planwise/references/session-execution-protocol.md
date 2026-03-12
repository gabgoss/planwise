---
description: Mandatory execution protocol - READ-CONFIRM-ACT, recovery, git workflow
---

# Session Execution Protocol

> [!binding] Enforcement
> These are not guidelines. Violations cause context loss and incomplete work.

## Table of Contents

- [1. READ-CONFIRM-ACT Pattern](#1-read-confirm-act-pattern)
- [2. MUST READ References](#2-must-read-references)
- [3. Settings Modification Protocol](#3-settings-modification-protocol)
- [4. Session Rules](#4-session-rules)
- [5. Task Tracking](#5-task-tracking)
- [6. Refactoring Safety](#6-refactoring-safety)
- [7. Git Workflow](#7-git-workflow)

---

## 1. READ-CONFIRM-ACT Pattern

**Before ANY task:**
1. **READ** all referenced documents completely (not skim)
2. **CONFIRM** understanding with a confirmation block (see format below)
3. **ACT** only after user approval

### Confirmation Block

> [!template] Context Confirmation
> ```
> CONTEXT LOADED
> File: {filename or "multiple files"}
> Current State: {status from document}
> Last Completed: {step/task from Recovery file}
> Next Action: {what the document says to do}
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
> | **AFTER** refactoring | Run `/simplify` on refactored files to verify quality |
> | **AFTER** verified working | Move backup to `RefactoringArchive/` |

---

## 7. Git Workflow

> [!binding] Git Discipline
> - **Commit** at the end of each session
> - If session produced code changes and `/simplify` has not already been run on all changed files, run `/simplify` before committing
> - **Push** automatically (no confirmation needed)
> - **git add** specific files (never `git add .` or `git add -A`)

---

*Full details: [session-planning-protocol.md](session-planning-protocol.md), [session-context-budget.md](session-context-budget.md), [session-plan-requirements.md](session-plan-requirements.md)*
