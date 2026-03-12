# Handler: /planwise run

**Purpose:** Execute a planned session using READ-CONFIRM-ACT protocol. Orchestrates task execution (DIRECT or DELEGATED), manages recovery state, generates session summary, captures lessons, and commits results.

**Invocation examples:**
```
/planwise run @APM-S01-01-Orchestration.md
/planwise run @Plans/MyPlan/Sprint-01/APM-S01-01-Orchestration.md
```

---

## Table of Contents

- [Config Gate](#config-gate)
- [Phase 0: Pre-Execution Setup](#phase-0-pre-execution-setup)
- [Phase 1: Execution Gate (READ-CONFIRM-ACT)](#phase-1-execution-gate-read-confirm-act)
- [Phase 2: Always-TaskList Setup](#phase-2-always-tasklist-setup)
- [Phase 3: Task Execution Loop](#phase-3-task-execution-loop)
- [Phase 4: Post-Session Integration](#phase-4-post-session-integration)
- [Recovery Protocol](#recovery-protocol)
- [Delegated Execution Protocol](#delegated-execution-protocol)
- [Error Handling](#error-handling)
- [Context Recovery](#context-recovery)

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `project.planwise_root` -- the planwise root folder (default: `planwise`)
- `project.plans_dir` -- the Plans directory name (relative to planwise_root)
- `project.lessons_dir` -- the Lessons directory name (relative to planwise_root)
- `project.index_files.lessons` -- the lessons index filename

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Plans`).

---

## Required References

Before proceeding, read these reference files from `${CLAUDE_PLUGIN_ROOT}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Run-specific references (always load):**
1. Read `references/session-execution-protocol.md`

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

---

## Phase 0: Pre-Execution Setup

### Step 0.1: Parse Arguments

Parse `$ARGUMENTS` to identify the orchestration file:
- `$1` or `@file` syntax -- path to orchestration file or Master Plan

If no argument provided, ask the user:
```
Which session should I execute? Provide the orchestration file path.
Example: /planwise run @Plans/MyPlan/Sprint-01/APM-S01-01-Orchestration.md
```

### Step 0.2: Locate Session Files

1. Read the orchestration file
2. Extract from orchestration:
   - **Session ID** (e.g., `APM-S01-01`)
   - **Abbreviation** (e.g., `APM`)
   - **Sprint** folder path
   - **Execution Strategy mode** (DIRECT or DELEGATED)
   - **Session Task List** (all tasks with agents and dependencies)
   - **Task Files** table (paths to individual task files)
3. Locate the recovery file in the same directory: `{Abbrev}-S{XX}-{YY}-Recovery.md`
4. If recovery file does not exist, create it from [templates/recovery.md](../templates/recovery.md) using the orchestration's task list
5. Locate or create `Outputs/` directory in the sprint folder

### Step 0.3: Check Master Plan Status

Read the Master Plan. Check the `Status:` field.
- If `READY_TO_EXECUTE` or `REVIEWED` or `APPROVED` -- proceed
- Otherwise -- warn the user: "Master Plan status is `{status}`. Run `/planwise plan` or `/planwise review` first. Proceed anyway?" Use `AskUserQuestion`.

---

## Phase 1: Execution Gate (READ-CONFIRM-ACT)

> [!binding] READ-CONFIRM-ACT is MANDATORY
> No task execution begins until the user explicitly approves.

### Step 1.1: READ

Read these files completely (not skim):
1. Orchestration file (already read in Phase 0)
2. Recovery file -- check for resumption state
3. All task files listed in the Task Files table (read file headers, objectives, agents)

### Step 1.2: CONFIRM

Output the confirmation block:

> [!template] Context Confirmation
> ```
> CONTEXT LOADED
> File: {orchestration filename}, {recovery filename}
> Current State: {Session Status from Recovery -- NOT_STARTED | IN_PROGRESS | COMPLETE}
> Last Completed: {last COMPLETE task from Recovery, or "None" if NOT_STARTED}
> Next Action: {first PENDING task description, or "Resume from Task {N}" if resuming}
> ```

### Step 1.3: ACT

Use `AskUserQuestion`: "Ready to proceed with {next action}?"

Only proceed after user approval.

---

## Phase 2: Always-TaskList Setup

> [!binding] TaskList Creation is MANDATORY
> Create TaskList entries for ALL tasks at session start, BEFORE executing any task. This provides visual progress tracking via `Ctrl+T`.

### Step 2.1: Check Existing Tasks

Run `TaskList` to check for existing tasks from other sessions.

> [!constraint] Task List Isolation
> WRONG: Delete or overwrite existing tasks from other sessions.
> CORRECT: Add your tasks alongside existing ones using `[{ABBREV}-##]` subject prefixes.

### Step 2.2: Create Task Entries

For EACH task in the orchestration's Session Task List:

```
TaskCreate(
  subject: "[{ABBREV}-{task-num}] {task-name}",
  description: "{task objective from task file}",
  activeForm: "Executing {task-name}"
)
```

If resuming a session (some tasks already COMPLETE in recovery):
- Create entries for ALL tasks
- Immediately mark completed tasks via `TaskUpdate(status: "completed")`
- Mark the current in-progress task via `TaskUpdate(status: "in_progress")`

### Step 2.3: Set Dependencies

For tasks with declared dependencies in the orchestration:

```
TaskUpdate(
  taskId: "{task-id}",
  blockedBy: ["{dependency-task-id}"]
)
```

---

## Phase 3: Task Execution Loop

For each task in the orchestration's Session Task List (respecting dependency order):

### Step 3.1: Pre-Task Setup

1. Read the task file completely
2. Mark task IN_PROGRESS in recovery file
3. Update TaskList: `TaskUpdate(taskId: "{id}", status: "in_progress")`

### Step 3.2: Dispatch by Execution Mode

Read the orchestration's `## Execution Strategy` section.

> [!decide] Execution Mode Dispatch
> | Declared Mode | Behavior |
> |---------------|----------|
> | **DIRECT** | Execute the task yourself. Read all Required Context listed in the task file. Follow the task's Execution Steps. |
> | **DELEGATED** | You are the ORCHESTRATOR. Launch `task-runner` agent. Do NOT read task Required Context yourself. |
> | **Missing** | Treat as DIRECT. Warn user: "Execution Strategy not declared -- defaulting to DIRECT mode." |

#### DIRECT Mode

1. Read all files listed in the task's Required Context table
2. Follow the task's Execution Steps in order
3. Write output files as specified in Expected Output
4. Verify Success Criteria are met

#### DELEGATED Mode

Launch the `task-runner` agent via Task tool. See [Delegated Execution Protocol](#delegated-execution-protocol) for full details.

```
Task(
  subagent_type: "task-runner",
  description: "Execute task {task-num}: {task-name}",
  model: "{model-override-from-task-file-Agent-field}",
  prompt: |
    Execute the following task:

    Task file: {task-file-absolute-path}
    Session ID: {session-id}
    Abbreviation: {abbrev}
    Recovery file: {recovery-file-absolute-path}
    Output directory: {output-dir-absolute-path}
)
```

**Model override:** The `model:` parameter in the Task tool call MUST match the Agent field declared in the task file (e.g., if task file says `Agent: Haiku`, use `model: "haiku"`).

### Step 3.3: Post-Task Update

> [!binding] Recovery Update After EVERY Task
> Update the recovery file AFTER EACH TASK completes -- never batch updates.

After each task completes (DIRECT or DELEGATED):

1. **Recovery file** -- update immediately:
   - Mark task COMPLETE with timestamp
   - Add key findings to "Key Findings" section
   - Add files modified to "Files Modified" section
   - Add Change Log entry: date, step number, status, notes
   - Update "Current Step" to next task number
2. **TaskList** -- update status: `TaskUpdate(taskId: "{id}", status: "completed")`
3. **Verify output** -- confirm expected output files were written (if applicable)
4. **THEN** proceed to next task

### Step 3.4: Handle Task Failure

If a task fails or returns BLOCKED:

1. Update recovery: mark task BLOCKED with description
2. Update TaskList: leave as in_progress (do not mark completed)
3. Decide: if remaining tasks depend on the blocked task, halt execution. If independent tasks remain, continue with those.
4. Report to user: "Task {N} is BLOCKED: {reason}. Continue with remaining tasks?"

---

## Phase 4: Post-Session Integration

After all tasks complete (or all non-blocked tasks complete):

### Step 4.1: Generate Session Summary

Read recovery file and orchestration file. Generate the summary document using [templates/summary-template.md](../templates/summary-template.md).

**Content sources for the 8-section summary:**

| # | Section | Content Source |
|---|---------|----------------|
| 1 | Tasks Completed | Recovery file step table |
| 2 | Key Deliverables | Files Modified in Recovery |
| 3 | Issues Encountered | Issues table in Recovery |
| 4 | Verification Results | Build/test results from execution |
| 5 | Success Criteria Status | Orchestration success criteria |
| 6 | Context Notes | Key Findings in Recovery |
| 7 | Next Session | Sprint plan dependencies |
| 8 | Lessons Learned | Lesson files created this session (populated after Step 4.2) |

Write to: `Outputs/{Abbrev}-S{XX}-{YY}-Summary.md` in the sprint folder.

### Step 4.2: Lesson Capture

Ask the user: "Were any lessons learned during this session?"

**If yes, for each lesson:**

1. Read the lessons index at `{lessons_dir}/{lessons_index_file}` for next available ID and template
2. Determine from session context:
   - What was learned
   - Domain (infer from files worked on, or ask user)
   - Technology and language involved
   - Severity (high / medium / low)
3. Draft the lesson with pre-filled YAML frontmatter:
   ```yaml
   ---
   id: LL-{next-available}
   title: {auto-generated from context}
   date: {today}
   source: {session-id}
   category: {inferred: anti-pattern | pattern | process}
   severity: {inferred: low | medium | high}
   language: [{inferred}]
   technology: [{inferred}]
   domain: [{inferred domain abbreviation}]
   status: documented
   applied-as: null
   ---
   ```
4. Present draft to user: "Capture this lesson? (approve / edit / skip)"
5. If approved:
   - Write file: `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md`
   - Add row to master table in the lessons index
   - Update summary Section 8 with lesson reference

**If no lessons:** Write "No lessons captured this session." in the summary's Section 8.

### Step 4.3: Update Plan Status

1. Mark recovery file Session Status: COMPLETE
2. Update orchestration: Status -> COMPLETE
3. Update Sprint Plan session status (if sprint plan exists)
4. Update Master Plan Status field (e.g., COMPLETE if all sprints done, or IN_PROGRESS with notes on completed sprint)

### Step 4.4: Git Commit

```bash
git add {specific files changed during session}
git commit -m "{type}: {description}"
git push
```

**Rules:**
- Stage specific files -- never use `git add .` or `git add -A`
- Include: task output files, recovery file, orchestration file, summary file, lesson files (if created)
- Commit types: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`

### Step 4.5: Output Completion

Output a summary to the user:

```
/planwise run -- Complete

Session: {session-id}
Status: COMPLETE
Tasks: {completed}/{total} completed

Summary: Outputs/{Abbrev}-S{XX}-{YY}-Summary.md
Lessons: {N} captured (or "None")

Next: {next session from summary, or "Sprint complete"}
```

---

## Recovery Protocol

### Update Frequency

| Event | Must Update? | What to Update |
|-------|--------------|----------------|
| Task started | YES | Mark IN_PROGRESS, update Current Step |
| Task completed | YES | Mark COMPLETE, add timestamp, add findings |
| Error encountered | YES | Add to Issues section with severity |
| Partial progress | YES | Add to Key Findings what was done |
| Session complete | YES | Final status, completion timestamp |
| Before any break | YES | Ensure current state is saved |

### Recovery File Minimum Content

The recovery file follows [templates/recovery.md](../templates/recovery.md). Required fields:

- `Last Updated:` -- timestamp
- `Current Step:` -- task number or COMPLETE
- `Session Status:` -- NOT_STARTED / IN_PROGRESS / COMPLETE
- Step Completion Status table with all tasks
- Key Findings section
- Files Modified section
- Change Log

---

## Delegated Execution Protocol

When the orchestration's Execution Strategy section declares DELEGATED mode, you are the orchestrator -- not the executor.

### Context Boundary Rules

> [!binding] Context Boundaries
> These boundaries are MANDATORY. Violating them wastes the orchestrator's context budget.

| Actor | Reads | Never Reads |
|-------|-------|-------------|
| Orchestrator (you) | Orchestration, Recovery, task files | Consolidated Context parts, Execution Inputs, reference docs, source code |
| Task-runner agent | Task Required Context files, task file | Other tasks' context, Recovery file (except for its own update) |

### Step-by-Step (DELEGATED)

1. Read plan files only: Orchestration + Recovery + all task files
2. Output CONTEXT LOADED confirmation block
3. Ask user to proceed (standard READ-CONFIRM-ACT)
4. For each task (sequential, respecting dependencies):
   a. Build spawn prompt with all task parameters (see Phase 3, Step 3.2)
   b. Launch `task-runner` agent:
      ```
      Task(
        subagent_type: "task-runner",
        description: "Execute task {task-num}: {task-name}",
        model: "{agent-from-task-file}",
        prompt: |
          Execute the following task:

          Task file: {task-file-absolute-path}
          Session ID: {session-id}
          Abbreviation: {abbrev}
          Recovery file: {recovery-file-absolute-path}
          Output directory: {output-dir-absolute-path}
      )
      ```
   c. Wait for task-runner to return
   d. Read updated recovery file -- check task status
   e. If BLOCKED: decide proceed or halt based on dependencies
   f. If COMPLETE: update TaskList, proceed to next task
5. Cleanup: generate summary, prompt for lessons, git commit (Phase 4)

### Anti-Patterns

> [!antipattern] Delegated Mode Anti-Patterns
> - **Orchestrator reads Consolidated Context:** Blows context budget; task-runners duplicate the read
> - **Skip Recovery between tasks:** Context compaction loses progress
> - **Combine tasks in one task-runner:** Defeats fresh-context purpose
> - **Launch Task N+1 before Recovery updated:** Compaction loses Task N completion
> - **Orchestrator produces task outputs:** Context accumulates; no fresh budget benefit
> - **Infer DELEGATED at runtime:** Planning should have set this; warn user and re-plan if needed

---

## Error Handling

### Severity Levels

| Category | Severity | Description | Action |
|----------|----------|-------------|--------|
| **A** | Blocker | Cannot proceed, integrity at risk | Must fix before continuing |
| **B** | Error | Incorrect behavior, workaround exists | Fix in current session |
| **C** | Warning | Suboptimal but functional | Document, fix in future |
| **D** | Info | Observation, no action needed | Document for reference |

### Self-Correction Pattern

When errors occur:
1. Capture full error output
2. Analyze error type (compilation, test failure, runtime)
3. Make targeted fix
4. Retry operation
5. If same error 3x -- escalate to user for manual review

---

## Context Recovery

### When Context Compacts Mid-Session

If you lose context mid-session:

1. **READ** recovery file FIRST -- find "Current Step" and last COMPLETE task
2. **READ** Outputs/ folder contents -- load completed task results and Key Findings
3. **RESUME** from next incomplete task -- mark it IN_PROGRESS immediately
4. **UPDATE** recovery after completing resumed task

### Agent Escalation

| From | To | When |
|------|-----|------|
| Haiku | Sonnet | Haiku produces poor results or task needs code generation |
| Sonnet | Opus | Architectural decision needed or requirements ambiguous |
| Opus | Sonnet | After decision made, delegate implementation |

> [!antipattern] Agent Misuse
> - Using Opus for file searches (wastes tokens)
> - Using Haiku for code generation (poor quality)
> - Keeping Opus active after decision is made
> - Never escalating stuck Haiku (infinite retry loops)
