# Handler: /planwise run

**Purpose:** Execute a planned session using READ-CONFIRM-ACT protocol. Orchestrates task execution (DIRECT or DELEGATED), manages recovery state, generates session summary, captures lessons, and commits results.

**Invocation examples:**
```
/planwise run @APM-S01-01-Orchestration.md
/planwise run @Plans/MyPlan/Sprint-01/APM-S01-01-Orchestration.md
```

---

## Table of Contents

- [Config Gate](#config-gate-auto-init-fallback)
- [Phase 0: Pre-Execution Setup](#phase-0-pre-execution-setup)
- [Phase 1: Execution Gate (READ-CONFIRM-ACT)](#phase-1-execution-gate-read-confirm-act)
- [Phase 2: Always-TaskList Setup](#phase-2-always-tasklist-setup)
- [Phase 3: Task Execution Loop](#phase-3-task-execution-loop)
- [Phase 4: Post-Session Integration](#phase-4-post-session-integration)
- [Recovery Protocol](#recovery-protocol)
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

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Run-specific references (always load):**
1. Read `references/session-execution-protocol.md`
2. Read `references/read-confirm-act-protocol.md` — source for READ-CONFIRM-ACT, structural findings, and Cross-Task Coordination Flags (cited throughout this handler)

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

While reading, watch for structural findings beyond the literal task scope -- latent defects in adjacent sections, anchors, or enumerations that the directive did not name but that the minimum coherent fix requires touching. See [read-confirm-act-protocol.md §1.2](../references/read-confirm-act-protocol.md#12-structural-findings-beyond-literal-scope) for the full rule.

### Step 1.1a: RECONCILE (Flag-Reconciliation Preflight)

> [!binding] Route binding cross-sprint flags into task files BEFORE confirming
> A binding coordination flag recorded in a sprint plan's `Carried-Forward Coordination Flags` section only reaches sessions scaffolded AFTER it lands. When THIS session was already scaffolded when the flag was recorded, the "re-propagate at scaffold time" step never fired — the session orchestrator reads only the orchestration / Recovery / task files, the flag is invisible, and tasks execute their stale EI-verbatim specs. In the incident this rule exists to prevent, a destructive prune operation shipped able to delete user content the contract existed to protect, and only a closeout cross-check caught it. Reconcile flags into the task files at session start, before the CONFIRM block.

> [!checklist] Flag-Reconciliation Preflight (Phase 1, between READ and CONFIRM)
> - [ ] Read the sprint plan's `Carried-Forward Coordination Flags` section (if present)
> - [ ] For each flag recorded ON OR AFTER this session's scaffold date: check it appears in the orchestration's `Pre-Known Cross-Task Coordination Flags` AND in every affected task file
> - [ ] Route each missing flag: write it into the affected task file(s) under `## Pre-Known Cross-Task Coordination Flags`, and carry it into that task's spawn prompt at dispatch
> - [ ] Record the routing in Recovery (one Change Log row: "flag preflight — N flags routed to tasks X, Y")
> - [ ] If a routed flag CONTRADICTS an **Execution Step**, **Success Criterion**, or **Schema Pin** stated in a task file → structural finding: surface it in the CONFIRM block via the Step 1.2a Option A / Option B gate; do not dispatch first
> - [ ] A flag whose text is an unresolved fork must be pinned before dispatch — leaving a "pick one and say so" open means each runner resolves it ad hoc, with no recorded decision for downstream sessions to inherit

**The two-hop propagation model (why the receiver routes the last hop):**

A coordination flag reaches an executing task in two hops, and each hop has exactly one owner:

- **Hop 1 — upstream closeout (sender).** The closing session delivers every flag to the downstream session's FRONT DOOR: the orchestration file's `Pre-Known Cross-Task Coordination Flags` section when that session is already scaffolded, else the sprint plan's `Carried-Forward Coordination Flags` section. The sender NEVER reaches into another session's task files — it does not own that decomposition and would race a concurrent session editing the same files.
- **Hop 2 — downstream session start (receiver, THIS preflight).** This session routes each flag the final hop into its own task files, because it already reads every task file, knows its own decomposition, and is the single writer of its own files.

Corollary — when an upstream contract SUPERSEDES an EI-verbatim block, the flag MUST say so explicitly (e.g. "the LIVE implementation supersedes EI §N"). A runner copying a "verbatim" spec has no reason to doubt it otherwise. Spawn-prompt injection alone (without the task-file write) is acceptable ONLY for informational flags; a binding contract belongs in the task file so it survives session resumption and is visible to reviewers.

### Step 1.2: CONFIRM

Output the confirmation block. See [examples/confirmation-block.md](../examples/confirmation-block.md) for correctly formatted examples (standard, multiple files, fresh session, recovery, and structural-finding variants).

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

If Step 1.1 surfaced a structural defect that makes the literal task scope produce a self-inconsistent artifact, the CONFIRM block MUST include a `Structural finding` paragraph AND an explicit Option A (Coherent) / Option B (Literal) block before proceeding. The executor MUST NOT pick a path before the user answers -- see [read-confirm-act-protocol.md §1.2](../references/read-confirm-act-protocol.md#12-structural-findings-beyond-literal-scope) for the template and rationale.

If the user approves Option A (or any expansion beyond the literal scope), the Phase-1 approval reference (the AskUserQuestion turn or timestamp) MUST be recorded in:
- Recovery's `Scope-Expansion Decisions` section (see [templates/recovery.md](../templates/recovery.md))
- Summary's `Scope-Expansion Decisions` block in Context Notes (see [templates/summary-template.md](../templates/summary-template.md))

> [!practice] Recommend the Coherent Option — Effort Is Not a Tiebreaker
> When surfacing Option A (Coherent) / Option B (Literal) — or any fix-versus-patch choice that arises during execution — the "(Recommended)" label goes to the coherent, complete treatment by default. Diff size, renumbering churn, or ripple through dependent files is never by itself a reason to recommend the partial path: dependent references are exactly what closeout reconciliation exists to update. Recommend the partial path only when a real constraint forces it (an interface external consumers already depend on, an irreversible-migration boundary, an explicit user deadline) and name that constraint in the recommendation. The user still chooses — this rule governs which option the executor endorses. Project quality compounds; deferred coherence rarely gets cheaper than it is today. Full principle, exception clause, and stage table: [do-the-hard-things.md](../references/do-the-hard-things.md).

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

You are the ORCHESTRATOR. Choose dispatch mode for the current dependency layer (tasks whose `Depends On` are all COMPLETE): **Sequential** for 1-2 tasks, or when any task in the layer targets a file another layer task also targets (output-file collision); **Parallel** for 3+ tasks with no inter-dependencies and disjoint output files.

Before dispatching, read `references/agent-orchestration-delegated.md`: §1.3 (context boundary), §1.6 (path-rule injection), §1.8 (HARD CONSTRAINTS skeleton), §1.13 (shared-edit-target strategy; parallel-dispatch Recovery contract), §1.17 (classify every return before consuming it — a `completed` status alone is not a deliverable check), §1.19 (Model-Floor Bridge), §1.20 (1M-Exception Dispatch), §1.21 (Background vs Foreground Gate), §1.22 (Anti-Patterns checklist).

The spawn prompt states the single-task scope in three positions — the opener, a hard-constraint line, and the return instruction — so the scope is stated even against a session-scoped identity that would otherwise outrank a single mention. When the project declares an isolated environment (Config Gate), it also adds an environment-discipline block naming interpreter/linter/runner paths in the platform-matched form (POSIX `./.venv/bin/{tool}` or Windows `.\.venv\Scripts\{tool}.exe` — emit the one matching the project's platform, never both), and on the session's FIRST dispatch only, a one-line interpreter diagnostic:

```
Task(
  subagent_type: "planwise:task-runner",
  description: "Execute task {task-num}: {task-name}",
  model: "{model-override-from-task-file-Agent-field}",
  prompt: |
    You are dispatched to execute ONE task: {task-id}. The session has other
    tasks; you DO NOT execute them.

    Execute the following task YOURSELF, directly, with your own tool calls.
    Do NOT spawn, dispatch, or delegate to any other agent (no Agent/Task
    tool calls) — you ARE the task-runner.

    Task file: {task-file-absolute-path}
    Session ID: {session-id}
    Abbreviation: {abbrev}
    Recovery file: {recovery-file-absolute-path}
    Output directory: {output-dir-absolute-path}

    HARD CONSTRAINTS: Execute ONLY {task-id}. Do not start any other task in
    the session even if the Recovery file lists it as PENDING. Files you may
    write: {explicit list from the task file's Output}.

    (If the project declares an isolated environment, add:)
    ## ENVIRONMENT DISCIPLINE
    Change to the project root first. Use these paths — a bare tool name
    resolves to the platform default, not this project's environment:
      interpreter:  {env-interpreter-path}
      linter:       {env-linter-path}
      test/notebook runner: {env-runner-path}
    Confirm connectivity/setup with `{env-interpreter-path} {project-precheck}`
    BEFORE doing dependent work.

    (On this session's first dispatch only, add:)
    First-spawn diagnostic — run `{env-interpreter-path} -c "import sys;
    print(sys.executable)"` and HALT if the output does not resolve inside
    the project environment.

    Return after writing the single expected output file. Do NOT proceed to
    task {n+1}.
)
```

**Model override:** The `model:` parameter in the Task tool call MUST match the Agent field declared in the task file (e.g., if task file says `Agent: Haiku`, use `model: "haiku"`) — except when `references/agent-orchestration-delegated.md` §1.19 (Model-Floor Bridge) or §1.20 (1M-Exception Dispatch) raises it for this dispatch only; log the raise per those sections, never silent.

**Parallel dispatch (3+ tasks):** launch all task-runners in the layer in a single message (multiple Task tool calls in one assistant turn — they run concurrently). Include the PARALLEL DISPATCH addendum and Status Block format from `references/agent-orchestration-delegated.md` §1.13 in each spawn prompt, and omit the `Recovery file:` parameter — parallel runners must not touch Recovery. After all runners return, classify each per §1.17, then reconcile Recovery centrally per §1.13's orchestrator contract and Step 3.3's "After a parallel batch" instructions below.

> [!pitfall] Mixed-Mode Layer
> **Problem:** A dependency layer where two tasks share an output file. Dispatching the whole layer in parallel races on that shared file (separate from the Recovery-file question).
> **Solution:** Apply `references/agent-orchestration-delegated.md` §1.13 to the *output files*: if any two tasks in the layer share an output target, the layer is NOT parallel-eligible — fall back to Sequential dispatch for the whole layer, or split the offending pair into a separate sub-layer.

### Step 3.2a: Handle Permission Denial

If a tool-permission prompt denies a write during dispatch or execution (DIRECT or DELEGATED) -- most commonly a `.claude/**` target, which the harness permission classifier gates independently of planwise authorization -- follow this protocol, in order:

1. Write the applied-vs-denied edit list to Recovery BEFORE anything else.
2. STOP and surface the precise file plus the remaining edits to the user.
3. Never re-issue the identical batch in the same mode.
4. On resumption, apply only the remainder, recording any unclearable edit as a non-blocking residual in the Summary.

### Step 3.3: Post-Task Update

> [!binding] Recovery Update After EVERY Task
> Update the recovery file AFTER EACH TASK completes -- never batch updates.
>
> **Parallel-dispatch exception:** When dispatching 3+ task-runners in parallel within a DELEGATED session, the runners do NOT write Recovery — the orchestrator (you) reconciles Recovery centrally after the parallel batch returns. See Phase 3 Step 3.2's DELEGATED Mode (Parallel dispatch) above and `references/agent-orchestration-delegated.md` §1.13 Recovery-file subsection. The "after EVERY task" rule still holds at batch granularity: reconcile Recovery once before dispatching the next dependency layer.

After each task completes (DIRECT or DELEGATED, sequential):

1. **Recovery file** -- update immediately:
   - Mark task COMPLETE with timestamp
   - Add key findings to "Key Findings" section
   - Add files modified to "Files Modified" section
   - Add Change Log entry: date, step number, status, notes
   - Update "Current Step" to next task number
2. **TaskList** -- update status: `TaskUpdate(taskId: "{id}", status: "completed")`
3. **Verify output** -- confirm expected output files were written (if applicable)
4. **Verify structure** -- if the task's Expected Output declared required headings or table-column headers, grep the produced file for every one of them; on a miss, re-dispatch the same runner with a single corrective instruction rather than accepting and reconciling downstream (keep this step list cleanly extensible -- a later sprint adds a resolve-and-route step here)
5. **THEN** proceed to next task

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

### Step 4.0: Prior-Sprint Outputs Guard

A session must not leave a **completed prior sprint's** `Outputs/` artifact modified or deleted. Those files are the artifact of record that later sprints adjudicate against and that signoffs quote; mutating one rewrites the evidence a past decision was made on, after the fact. Any re-executed producer — a notebook, a generator script, an `--inplace` formatter, a doc emitter — can do this and still exit 0, and per-task verification never catches it because every task checks only its own outputs.

Run the guard BEFORE generating the summary, so a violation halts closeout while the session state is still intact:

```bash
python {plugin_root}/scripts/check_prior_sprint_outputs.py \
  --config {planwise_root}/config.yaml \
  --current-session {session-folder-path}
```

The script exits 0 when clean and 1 when it finds a BLOCKING violation, printing one block per finding:

```
BLOCKING: modified file under a COMPLETE sprint's Outputs/
  path:          {plans_dir}/{Plan}/{Exec-Abbrev}/Sprint-{XX}-{Name}/Session-{YY}-{Name}/Outputs/{file}
  owning sprint: {Abbrev} Sprint-{XX} Session-{YY}  (Status: COMPLETE)
  change:        M   (+{ins} -{del})
```

**On a clean result** — continue to Step 4.1.

**On a BLOCKING result** — do NOT proceed to Step 4.1. Present the findings to the user and resolve one of two ways:

| Resolution | Action |
|---|---|
| The mutation was unintended | Restore the file (`git checkout -- {path}`), fix the producer so it no longer writes to that path, and re-run the guard. Closeout resumes only after a clean run. |
| The mutation is a genuine correction to a past artifact | Record the override in the Recovery file (format below), then proceed. The override is never silent and never inferred — it requires explicit user acknowledgement. |

Recovery file override entry:

```markdown
### Prior-Sprint Outputs Override

| Path | Owning sprint | Change | Acknowledged by | Reason |
|------|---------------|--------|-----------------|--------|
| {path} | {Abbrev} S{XX}-{YY} | M (+{ins} -{del}) | user | {why this correction is intended} |
```

> [!verify] Prior-sprint Outputs are unmodified at closeout
> ```bash
> python {plugin_root}/scripts/check_prior_sprint_outputs.py --config {planwise_root}/config.yaml
> # MUST exit 0, OR every reported path MUST have a corresponding
> # "Prior-Sprint Outputs Override" row in this session's Recovery file.
> ```

**Untracked new files are not findings.** Adding a new file to a completed sprint's `Outputs/` is not the hazard this guard exists for; only mutation or deletion of an existing tracked artifact is.

**Not a git repo / no Master Plan tracking table** — the guard reports what it could not cover and exits 0. It never fails closed on an absent input, but it never stays silent about reduced coverage either (see the script's coverage line).

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

> [!constraint] Twin-BB reconciliation — if a backlog route already shipped this plan's deliverables, reconcile instead of duplicating
> A plan and a backlog item that name the same deliverables are twins. If this session found its deliverables **already satisfied** at the first dispatch layer — you grepped each deliverable against the live target and it already existed — the work was shipped through a backlog route (`/planwise backlog` Route A/B, a direct commit) and this twin plan was never retired at that route's closeout. Do NOT re-author or re-run idempotency-unsafe steps ("append N rows", "insert at max+1") against already-satisfied state. Reconcile instead: set this plan's Master Plan / sprint / orchestration `Status: COMPLETE (superseded — shipped via BB-{NNN} {route} {date})`, update its plans-index row, and record the linkage in the Summary. A plan that is entirely already-satisfied at its first dispatch layer is the signal that its twin was never retired.

### Step 4.4: Propagate Cross-Task Coordination Flags

> [!binding] Downstream-Propagation Gate
> Every row in the Recovery file's `Cross-Task Coordination Flags` section MUST be propagated into the downstream consumer's plan file BEFORE the Git Commit step. A flag recorded only in upstream Recovery and never propagated is functionally a dropped constraint. See [references/read-confirm-act-protocol.md §1.3](../references/read-confirm-act-protocol.md#13-cross-task-coordination-flags) for the full lifecycle and destination matrix.

1. Read the Recovery file's `Cross-Task Coordination Flags` section. If the section is empty or absent, skip to Step 4.5.
2. For each flag row, route per the destination table in §1.3:

   | Downstream Consumer | Propagate To |
   |---------------------|--------------|
   | A specific named task in a later session | That task's file under `## Pre-Known Cross-Task Coordination Flags` |
   | A whole session (consumer task unclear) | That session's orchestration file under `## Pre-Known Cross-Task Coordination Flags` |
   | A future sprint, downstream sessions NOT yet scaffolded on disk | That sprint plan's `## Carried-Forward Coordination Flags` section |
   | A future sprint whose downstream session is ALREADY scaffolded on disk | That session's orchestration file under `## Pre-Known Cross-Task Coordination Flags` (the sprint-plan `Carried-Forward` entry remains as the record) |
   | A follow-up plan not yet written | The current Master Plan's `## Carried-Forward Coordination Flags` section + the rollup/handoff task file |

   > [!constraint] "Future sprint" → `Carried-Forward` applies ONLY while the downstream session is unscaffolded
   > The sprint-plan `Carried-Forward Coordination Flags` destination reaches a downstream session ONLY at that session's scaffold time. Once the downstream session already exists on disk, it never re-reads the sprint plan's `Carried-Forward` section at its own start — so a flag dropped there after scaffolding is invisible to it. When the downstream session is already scaffolded, deliver the flag to that session's orchestration file front door instead (keep the sprint-plan entry as the record). The sending side NEVER edits another session's task files: it does not own that decomposition and risks racing a concurrent session. The receiving session routes the flag the last hop into its own task files at its Phase-1 Flag-Reconciliation Preflight (Step 1.1a).

3. Use the Propagated Flag Block format from §1.3 — group flags under `### From {source-session-id} ({source-session-name}) — recorded {YYYY-MM-DD}` and reserve a `### From {next-source-session-id} — to be appended when session completes` placeholder so later closeouts know where to append.
4. If the destination file does not yet have a `## Pre-Known Cross-Task Coordination Flags` (or `## Carried-Forward Coordination Flags`) section, create it; if it does, append under it.
5. Update the orchestration file at the destination (if propagating to a task file) with a one-line pointer to the new section, so the destination orchestrator surfaces the flags to its dispatcher.
6. Update the Summary file's `Cross-Task Coordination Flags` block (in Context Notes) to fill the `Propagated To` column with the destination path for every flag.
7. Verify: every Recovery flag row now has a non-empty `Propagated To` entry in the Summary. A flag with no destination is a closeout error — return to step 2 and route it.

### Step 4.5: Git Commit

If the session produced code changes and `/code-review` has not already been run on all changed files, run `/code-review` before staging. Per `references/session-execution-protocol.md` §7 Git Workflow.

> [!binding] Destructive-Diff Pre-Commit Review Gate
> - [ ] If this session's diff adds or widens a destructive disposition (delete / overwrite / migrate / prune / sweep): a pre-commit adversarial multi-agent code review was run as a gate DISTINCT from script verification, its findings fixed, and regression tests added in the same session. (A green suite + clean lint + passing smoke does NOT satisfy this gate.)
>
> "Run script verification" and "run code review" are DIFFERENT gates; the second is mandatory when the diff touches destructive dispositions, even when the first is fully green — a fresh feature's tests are written by the same mind that wrote its bugs, so a green suite says nothing about the inputs nobody imagined (BOMs, block-style YAML, non-dict JSON cache entries, retry-after-crash staleness, filename collisions).

```bash
git add {specific files changed during session}
git commit -m "{type}: {description}"
git push
```

**Rules:**
- Stage specific files -- never use `git add .` or `git add -A`
- Include: task output files, recovery file, orchestration file, summary file, lesson files (if created), plans index (if updated), **any downstream plan files that received propagated coordination flags in Step 4.4**
- Commit types: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Step 4.0's prior-sprint Outputs guard MUST have passed (or carry a recorded Recovery override) before staging — a commit is what makes a silent overwrite of a completed sprint's artifact of record permanent

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
| **Cross-task coordination flag surfaced** | **YES** | **Add row to `Cross-Task Coordination Flags` section IMMEDIATELY (not at closeout) — see [references/read-confirm-act-protocol.md §1.3](../references/read-confirm-act-protocol.md#13-cross-task-coordination-flags)** |
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
