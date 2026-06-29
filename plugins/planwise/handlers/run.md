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

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue. Extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, `project.index_files.plans` (as `{plans_index}`), `project.lessons_dir`, and `project.index_files.lessons` (as `{lessons_index}`).
3. If NOT found: announce, resolve `{plugin_root}` from handler location, invoke `init_project.py` with `--auto-from "run"`, RE-RESOLVE, fail loud if still missing.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD and STOP.

All directory paths resolve as `{planwise_root}/{dir_name}`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Run-specific references (always load):**
1. Read `references/session-execution-protocol.md`

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`
- If a task involves DB writes or MERGE/upsert briefs: Read `references/task-content-fidelity.md`, `references/schema-pin-requirement.md`
- If a session is IPC/protocol/codec: Read `references/verification-gates.md`
- If executing in DELEGATED mode (orchestrator dispatches task-runner subagents): Read `references/agent-orchestration-delegated.md`

---

## AUTO-MODE Annotations

`<!-- AUTO-MODE: critical|convenience -->` HTML comments classify the `AskUserQuestion` call site that immediately follows them, per `references/skill-authoring.md` §4b (Auto Mode Policy):

- **`critical`** — the gate MUST always prompt the user; never auto-infer (e.g., scope decisions, destructive actions, a missing required argument).
- **`convenience`** — in Auto Mode the handler MAY skip the prompt and proceed with the documented default; in normal interactive use it still prompts as written.

The annotations are inert during ordinary interactive runs — they guide Auto Mode behavior only.

---

## Phase 0: Pre-Execution Setup

### Step 0.1: Parse Arguments

Parse `$ARGUMENTS` to identify the orchestration file:
- `$1` or `@file` syntax -- path to orchestration file or Master Plan

<!-- AUTO-MODE: critical -->
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
<!-- AUTO-MODE: critical -->
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

While reading, watch for structural findings beyond the literal task scope -- latent defects in adjacent sections, anchors, or enumerations that the directive did not name but that the minimum coherent fix requires touching. See [session-execution-protocol.md §1.2](../references/session-execution-protocol.md#12-structural-findings-beyond-literal-scope) for the full rule.

### Step 1.2: CONFIRM

Output the confirmation block:

> [!template] Context Confirmation
> ```
> CONTEXT LOADED
> File: {orchestration filename}, {recovery filename}
> Current State: {Session Status from Recovery -- NOT_STARTED | IN_PROGRESS | COMPLETE}
> Last Completed: {last COMPLETE task from Recovery, or "None" if NOT_STARTED}
> Next Action: {first PENDING task description, or "Resume from Task {N}" if resuming}
> Structural Finding: {none, or one-line summary — see §1.2}
> ```

#### Step 1.2a: Structural Finding (when READ reveals one)

If Step 1.1 surfaced a structural defect that makes the literal task scope produce a self-inconsistent artifact, the CONFIRM block MUST include a `Structural finding` paragraph AND an explicit Option A (Coherent) / Option B (Literal) block before proceeding. The executor MUST NOT pick a path before the user answers -- see [session-execution-protocol.md §1.2](../references/session-execution-protocol.md#12-structural-findings-beyond-literal-scope) for the template and rationale.

If the user approves Option A (or any expansion beyond the literal scope), the Phase-1 approval reference (the AskUserQuestion turn or timestamp) MUST be recorded in:
- Recovery's `Scope-Expansion Decisions` section (see [templates/recovery.md](../templates/recovery.md))
- Summary's `Scope-Expansion Decisions` block in Context Notes (see [templates/summary-template.md](../templates/summary-template.md))

### Step 1.3: ACT

<!-- AUTO-MODE: critical -->
Use `AskUserQuestion`: "Ready to proceed with {next action}?"

Only proceed after user approval. If Step 1.2a surfaced a structural finding, the AskUserQuestion options are the A (Coherent) / B (Literal) pair, not a generic "proceed?" -- the user's choice IS the Phase-1 approval reference recorded in Recovery and Summary.

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
  subagent_type: "planwise:task-runner",
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

**Model override:** The `model:` parameter in the Task tool call MUST match the Agent field declared in the task file (e.g., if task file says `Agent: Haiku`, use `model: "haiku"`) — except when the Model-Floor Bridge below raises it.

#### Model-Floor Bridge (DELEGATED) — Temporary

> [!constraint] Raise a 200K-window model to 1M when the plan-path rule surface is large
> This guard governs EVERY DELEGATED dispatch — both the Sequential and Parallel branches in the [Delegated Execution Protocol](#delegated-execution-protocol). It is a **temporary bridge**, not a permanent override (see self-deactivation below). It never changes the model for a healthy (small) rule surface.
>
> **Before dispatching a DELEGATED task whose `Agent:` maps to a 200K-window model (Sonnet or Haiku):**
> 1. **Measure the plan-path rule surface.** Reuse the engine's linter: run `python {plugin_root}/scripts/init_project.py --doctor --project-root {project_root}` and sum the `approx_tokens` of the flagged (over-scoped) rules — those `.claude/rules/**` whose `paths:` target `planwise/Plans/**` (or sibling plan/backlog/lessons paths). If `--doctor` is unavailable, fall back to summing those rule files' sizes at ~13 tokens/line.
> 2. **Project the subagent's worst-case load:** `flagged-rule tokens + ~54K fixed overhead`. If that **approaches the 200K window** — rule of thumb: flagged surface ≳ ~110K, leaving < ~35K of working headroom — the declared 200K-window model will overflow ("Prompt is too long") the instant it reads a plan brief that triggers those path rules.
> 3. **Raise and log.** In that case, raise the dispatch `model` to the **1M tier** (Opus, or a 1M-window Sonnet where available) for THIS dispatch only, and emit a one-line log — never silent:
>    ```
>    MODEL FLOOR: raised {task-id} {declared}→1M (plan-path rule surface ~{N}K exceeds safe {declared} budget)
>    ```
> 4. **Otherwise dispatch verbatim.** If the threshold is NOT tripped, pass the declared `Agent:` model through unchanged — the floor is inert for a small surface.

> [!practice] Self-Deactivating Bridge — Not Permanent
> This floor exists only to keep declared-Sonnet/Haiku runners alive while a project still carries a large author-time rule surface scoped to plan paths. Once the project is de-scoped — plugin author-time rules handler-loaded from `references/` (not installed), and any project-local domain rules re-scoped to code paths per `/planwise doctor` — the flagged surface shrinks toward ~0, step 2's threshold is never tripped, and declared-Sonnet tasks dispatch unchanged. When `--doctor` reports no over-scoped rules for a project, this bridge is already inert; it can be retired entirely once no supported project trips it.

#### 1M-Exception Dispatch (DELEGATED) — Token Saver

> [!constraint] Raise a `1M-exception`-flagged task to Opus/1M — a COST remedy ONLY
> This guard governs EVERY DELEGATED dispatch (both Sequential and Parallel branches), exactly like the Model-Floor Bridge above and using the **same override mechanism** — it raises the dispatch `model`, it does NOT rewrite the task file. It is triggered by the task's own flag, not by the plan-path rule surface.
>
> **Effective Token Saver gate.** The `1M-exception` flags were stamped at plan time under whatever Token Saver value was effective for THIS plan — the plan's Master-Plan `Token Saver:` field (`on`/`off`) over the project `context.token_saver` default, resolved via `config_loader.get_effective_token_saver_config(config, plan_override)`. At dispatch time, read that same effective value (the plan's Master-Plan field, falling back to `config.yaml`); when it resolves `false`, no task carries a Token-Saver `1M-exception` and this guard is inert. The runner does NOT re-resolve — it dispatches the flags the plan already baked in.
>
> **When a task is flagged `1M-exception`** (the warning engine sets this in the task header's `Token Budget:` exception field for a single oversized **indivisible** file whose `cost`-reason estimate exceeds a 200K-window runner's budget):
> 1. **Raise and log.** Raise the dispatch `model` to the **1M tier** (Opus) for THIS dispatch only — a Sonnet/Haiku runner's window is **200K**, so the 1M-exception is the ONLY way an oversized single-file task fits *the window*. Emit a one-line log, never silent:
>    ```
>    1M EXCEPTION: raised {task-id} {declared}→1M (oversized indivisible file — cost-reason Critical, cannot be split)
>    ```
> 2. **Non-flagged tasks dispatch verbatim** on their declared `Agent:` model. The exception is inert for every task the engine did not flag.

> [!constraint] Window ≠ Readability — 1M-Exception Does NOT Fix a `read`-reason Critical
> WRONG — a task's Required Context file is `read`-reason Critical (≥ 256 KiB byte gate, or above the per-Read 25K-token page cap) and the orchestrator routes the dispatch to Opus/1M assuming the larger window absorbs it:
> ```
> read-reason Critical context file  → raise dispatch to 1M  → "the bigger window reads it"  ← FALSE
> ```
> CORRECT — the Read tool's **25K-token page cap** and **256 KiB byte refusal** apply on EVERY model; Opus's tokenizer is ~1.44× heavier so it trips the page cap *sooner* (~1,340 lines vs ~1,920 for Sonnet/Haiku). The 1M-exception covers **only** a `cost`-reason Critical (a context-window/carrying-cost overflow). It does NOT cover a `read`-reason Critical — that file must be **paged** by the runner (`offset`/`limit`/Grep) even on Opus, or refactored:
> ```
> read-reason Critical context file  → log `paged-read required` (NOT 1M-exception)  → runner pages it (offset/limit/Grep) on its declared model
> ```
> The warning engine (Token Saver) does NOT set `1M-exception` for a `read`-reason Critical, and `run.md` MUST NOT infer it. Log such a task with a `paged-read required` note and dispatch it on its declared model — keep the two reasons distinct in the dispatch log: `1M-exception` for `cost`-Critical, `paged-read required` for `read`-Critical.

### Step 3.3: Post-Task Update

> [!binding] Recovery Update After EVERY Task
> Update the recovery file AFTER EACH TASK completes -- never batch updates.
>
> **Parallel-dispatch exception:** When dispatching 3+ task-runners in parallel within a DELEGATED session, the runners do NOT write Recovery — the orchestrator (you) reconciles Recovery centrally after the parallel batch returns. See [Parallel Dispatch Branch](#parallel-dispatch-branch-delegated) below and `references/agent-orchestration-delegated.md` §1.13 Recovery-file subsection. The "after EVERY task" rule still holds at batch granularity: reconcile Recovery once before dispatching the next dependency layer.

After each task completes (DIRECT or DELEGATED, sequential):

1. **Recovery file** -- update immediately:
   - Mark task COMPLETE with timestamp
   - Add key findings to "Key Findings" section
   - Add files modified to "Files Modified" section
   - Add Change Log entry: date, step number, status, notes
   - Update "Current Step" to next task number
2. **TaskList** -- update status: `TaskUpdate(taskId: "{id}", status: "completed")`
3. **Verify output** -- confirm expected output files were written (if applicable)
4. **THEN** proceed to next task

After a **parallel batch** of 3+ task-runners returns:

1. Parse the status block from each runner's final message (schema: `TASK_STATUS / TASK_ID / OUTPUT_FILES / LINES_PRODUCED / KEY_FINDINGS / ISSUES`)
2. Verify referenced OUTPUT_FILES exist on disk for every COMPLETE row
3. **Recovery file** -- write ONCE for the entire batch:
   - One Step Completion row per task in the batch, all with the reconciliation timestamp
   - Append every runner's KEY_FINDINGS to the "Key Findings" section
   - Append every runner's OUTPUT_FILES to the "Files Modified" section
   - One Change Log row per task (or one batch row noting the parallel group)
   - Update "Current Step" to the next dependency layer
4. **TaskList** -- mark every batch task `completed`
5. **THEN** dispatch the next dependency layer (sequential task, or next parallel batch)

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

<!-- AUTO-MODE: convenience -->
<!-- Default: No (proceed without confirmation; user can invoke /planwise lessons capture separately). -->
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
4. Update Master Plan Status field:
   - If all sprints COMPLETE AND no user-action gates pending → `Status: COMPLETE`
   - If all sprints COMPLETE BUT user-action gates pending (per Master Plan "Project Complete When" section) → `Status: IN_PROGRESS — awaiting {user action}` (per `references/session-execution-protocol.md` Discovery / Meta-Plan Status section)
   - If not all sprints COMPLETE → `Status: IN_PROGRESS`

   > [!practice] User-Action-Gate Check
   > When all sprints COMPLETE, check Master Plan's "Project Complete When" section for user-action gates. If user-action gates remain, set IN_PROGRESS with note — NOT COMPLETE.
5. Update plans index row for this plan in `{plans_dir}/{plans_index}`:
   - Set **Status** to match the Master Plan status (e.g., IN_PROGRESS or COMPLETE)
   - Set **Last Updated** to today's date

### Step 4.4: Propagate Cross-Task Coordination Flags

> [!binding] Downstream-Propagation Gate
> Every row in the Recovery file's `Cross-Task Coordination Flags` section MUST be propagated into the downstream consumer's plan file BEFORE the Git Commit step. A flag recorded only in upstream Recovery and never propagated is functionally a dropped constraint. See [references/session-execution-protocol.md §1.3](../references/session-execution-protocol.md#13-cross-task-coordination-flags) for the full lifecycle and destination matrix.

1. Read the Recovery file's `Cross-Task Coordination Flags` section. If the section is empty or absent, skip to Step 4.5.
2. For each flag row, route per the destination table in §1.3:

   | Downstream Consumer | Propagate To |
   |---------------------|--------------|
   | A specific named task in a later session | That task's file under `## Pre-Known Cross-Task Coordination Flags` |
   | A whole session (consumer task unclear) | That session's orchestration file under `## Pre-Known Cross-Task Coordination Flags` |
   | A future sprint (consumer task not yet authored) | That sprint plan's `## Carried-Forward Coordination Flags` section |
   | A follow-up plan not yet written | The current Master Plan's `## Carried-Forward Coordination Flags` section + the rollup/handoff task file |

3. Use the Propagated Flag Block format from §1.3 — group flags under `### From {source-session-id} ({source-session-name}) — recorded {YYYY-MM-DD}` and reserve a `### From {next-source-session-id} — to be appended when session completes` placeholder so later closeouts know where to append.
4. If the destination file does not yet have a `## Pre-Known Cross-Task Coordination Flags` (or `## Carried-Forward Coordination Flags`) section, create it; if it does, append under it.
5. Update the orchestration file at the destination (if propagating to a task file) with a one-line pointer to the new section, so the destination orchestrator surfaces the flags to its dispatcher.
6. Update the Summary file's `Cross-Task Coordination Flags` block (in Context Notes) to fill the `Propagated To` column with the destination path for every flag.
7. Verify: every Recovery flag row now has a non-empty `Propagated To` entry in the Summary. A flag with no destination is a closeout error — return to step 2 and route it.

### Step 4.5: Git Commit

If the session produced code changes and `/code-review` has not already been run on all changed files, run `/code-review` before staging. Per `references/session-execution-protocol.md` §7 Git Workflow.

```bash
git add {specific files changed during session}
git commit -m "{type}: {description}"
git push
```

**Rules:**
- Stage specific files -- never use `git add .` or `git add -A`
- Include: task output files, recovery file, orchestration file, summary file, lesson files (if created), plans index (if updated), **any downstream plan files that received propagated coordination flags in Step 4.4**
- Commit types: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`

### Step 4.6: Output Completion

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
| **Cross-task coordination flag surfaced** | **YES** | **Add row to `Cross-Task Coordination Flags` section IMMEDIATELY (not at closeout) — see [references/session-execution-protocol.md §1.3](../references/session-execution-protocol.md#13-cross-task-coordination-flags)** |
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

### Background vs Foreground Gate

> [!constraint] Write-Producing Agents MUST Run in Foreground
> Background subagents auto-deny any permission not explicitly pre-approved at launch — including Write, Edit, and Bash. The `bypassPermissions` mode does NOT override this gate. Tool calls fail silently: the agent continues executing but produces no output files.
>
> WRONG: Launch task-runner in background when it writes output files:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   run_in_background: true,
>   prompt: "Execute task 01..."
> )
> ```
> CORRECT: Launch task-runner in foreground (default) — background is only safe for read-only agents:
> ```
> Task(
>   subagent_type: "planwise:task-runner",
>   prompt: "Execute task 01..."
> )
> ```

| Task Produces | Launch Mode | Rationale |
|---------------|-------------|-----------|
| File output (Write, Edit) | **Foreground** | Permissions resolved interactively |
| Shell commands (Bash) | **Foreground** | Bash permission needs interactive approval |
| Read-only research (Explore) | Background OK | No write permissions needed |

### Context Boundary Rules

> [!binding] Context Boundaries
> These boundaries are MANDATORY. Violating them wastes the orchestrator's context budget.

| Actor | Reads | Never Reads |
|-------|-------|-------------|
| Orchestrator (you) | Orchestration, Recovery, task files | Consolidated Context parts, Execution Inputs, reference docs, source code |
| Task-runner agent (sequential dispatch) | Task Required Context files, task file | Other tasks' context, Recovery file (except for its own update) |
| Task-runner agent (parallel dispatch, 3+ runners) | Task Required Context files, task file | Other tasks' context, **the Recovery file (do NOT read or write — return a status block instead)** |

### Step-by-Step (DELEGATED)

1. Read plan files only: Orchestration + Recovery + all task files
2. Output CONTEXT LOADED confirmation block
3. Ask user to proceed (standard READ-CONFIRM-ACT)
4. Identify the next dependency layer (group of tasks whose `Depends On` are all COMPLETE)
5. Choose dispatch mode for that layer:
   - **Sequential** — 1 or 2 tasks in the layer, OR any layer task targets a file another layer task also targets (output-file collision)
   - **Parallel** — 3+ tasks in the layer with no inter-dependencies and disjoint output files (see [Parallel Dispatch Branch](#parallel-dispatch-branch-delegated))
6. Dispatch the layer per the chosen mode (see subsections below)
7. After the layer completes, return to step 4 for the next layer
8. Cleanup: generate summary, prompt for lessons, git commit (Phase 4)

#### Sequential Branch (DELEGATED)

For each task in the layer (respecting any intra-layer dependencies):

a. Build spawn prompt with all task parameters (see Phase 3, Step 3.2)
b. Launch `task-runner` agent:
   ```
   Task(
     subagent_type: "planwise:task-runner",
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

#### Parallel Dispatch Branch (DELEGATED)

Trigger: a dependency layer has 3+ tasks with no inter-dependencies and disjoint output files. (For 1-2 tasks, use the Sequential Branch — coordination overhead outweighs the gain.)

a. For each task in the layer, build a spawn prompt that includes the **PARALLEL DISPATCH addendum** below in addition to the standard parameters.
b. Launch all task-runners in the layer in a single message (multiple Task tool calls in one assistant turn — they run concurrently):
   ```
   Task(
     subagent_type: "planwise:task-runner",
     description: "Execute task {task-num} (parallel batch): {task-name}",
     model: "{agent-from-task-file}",
     prompt: |
       Execute the following task:

       Task file: {task-file-absolute-path}
       Session ID: {session-id}
       Abbreviation: {abbrev}
       Output directory: {output-dir-absolute-path}

       ## PARALLEL DISPATCH — Recovery Handling
       Do NOT read, edit, or write the Recovery file during this task.
       Return your completion as the structured status block below in your FINAL message.
       The orchestrator reconciles Recovery centrally after all parallel runners return.

       ## Status Block (required final-message format)
       TASK_STATUS:    COMPLETE | BLOCKED | PARTIAL
       TASK_ID:        {task-id}
       OUTPUT_FILES:   {comma-separated absolute paths actually written}
       LINES_PRODUCED: {sum of lines across output files}
       KEY_FINDINGS:   {2-5 short bullets — preserved across compaction}
       ISSUES:         {one line per issue, or "none"}
   )
   ```

   Note that the spawn prompt for parallel-mode runners OMITS the `Recovery file:` parameter — the runner must not touch it.
c. Wait for ALL parallel runners to return their status blocks.
d. Reconcile Recovery centrally per Step 3.3 "After a parallel batch" instructions: parse each status block, verify OUTPUT_FILES on disk, write Recovery ONCE for the whole batch.
e. If any task returned BLOCKED or PARTIAL: decide proceed or halt based on downstream dependencies. Mark BLOCKED tasks IN_PROGRESS in TaskList (do NOT mark `completed`).
f. Advance to the next dependency layer.

> [!pitfall] Mixed-Mode Layer
> **Problem:** A dependency layer with 4 tasks where two write the same output file. Dispatching all 4 in parallel races on the shared output file (separate from the Recovery-file question). Splitting into "3 parallel + 1 sequential" is awkward and error-prone.
> **Solution:** Apply `references/agent-orchestration-delegated.md` §1.13 to the *output files*: if any two tasks in the layer share an output target, the layer is NOT parallel-eligible — fall back to the Sequential Branch for the whole layer, or split the offending task pair into a separate sub-layer.

### Anti-Patterns

> [!antipattern] Delegated Mode Anti-Patterns
> - **Orchestrator reads Consolidated Context:** Blows context budget; task-runners duplicate the read
> - **Skip Recovery between tasks (sequential dispatch):** Context compaction loses progress
> - **Skip Recovery reconciliation after a parallel batch:** Context compaction loses the entire batch; status blocks were returned but never persisted
> - **Combine tasks in one task-runner:** Defeats fresh-context purpose
> - **Launch sequential Task N+1 before Recovery updated:** Compaction loses Task N completion
> - **Allow parallel task-runners to write Recovery:** Last-write-wins races silently drop completion rows
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
