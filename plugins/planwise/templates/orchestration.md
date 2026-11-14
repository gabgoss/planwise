# Orchestration Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Orchestration.md`.

---

```markdown
# Session Orchestration - {ABBREV}-S{XX}-{YY}: {Session Name}

**Session ID:** {ABBREV}-S{XX}-{YY}
**Sprint:** {XX} - {SprintName}
**Status:** PLANNED
**Prerequisite:** {previous session or sprint that must be COMPLETE before this session can run, or "None" if first session of a plan}

<!-- Scaffolding CONFIRM block placeholder:
     When this orchestration is part of a scaffolded plan, ensure the handler emits the CONFIRM block
     before reading Consolidated Context parts. See handlers/plan-scaffolding.md Scaffolding Step 1
     and references/scaffolding-hygiene.md §1. -->

---

## Session Objective <!-- REQUIRED -->

{2-3 sentences describing what this session accomplishes}

---

## Required Context Files <!-- REQUIRED -->

<!-- DIRECT mode: list all context files needed for the session -->
<!-- DELEGATED mode: list ONLY plan files (Orchestration, Recovery, task files) -->
<!-- Heavy context files go in individual task file Required Context sections -->

| Priority | File | Purpose |
|----------|------|---------|
| 1 | `session-planning-protocol.md` | Planning hierarchy, delegation, checklists |
| 1 | `session-context-budget.md` | Token budget, context loading |
| 1 | `session-plan-requirements.md` | Required files, task templates |
| 2 | `{Abbrev}-Master-Plan.md` | Project overview |
| 3 | `{Abbrev}-S{XX}-{YY}-Recovery.md` | Resume point |

---

## Execution Strategy <!-- REQUIRED -->

**Mode:** {DIRECT | DELEGATED} <!-- REQUIRED -->
**Reason:** {Why this mode — e.g., "3 sequential Opus tasks each needing fresh context"}

### DELEGATED Mandatory Triggers Reminder

> [!checklist] When DELEGATED is Mandatory
> Set `Mode: DELEGATED` if ANY of these triggers apply:
> - [ ] Session has 2 or more Opus tasks
> - [ ] Session is part of a META Discovery phase
> - [ ] Any single task estimates > 50 K token context load
> - [ ] Sequential tasks where one task's output is the next task's input (output-chaining)
>
> See `references/session-plan-requirements.md` § Execution Strategy (Set by Planner) for the binding rule (canonical); `references/agent-orchestration-delegated.md` §1.1 Mandatory Triggers cites it.

### Context Boundary <!-- CONDITIONAL — DELEGATED mode only -->

> [!constraint] Mandatory Context Boundary
> In DELEGATED mode, the orchestrator reads ONLY plan files (Orchestration, Recovery, task files). Heavy context files (Consolidated Context parts, reference docs, source code) are read by subagents only.
>
> WRONG (orchestrator reads heavy context):
> ```
> Orchestrator reads:
> - Orchestration, Recovery, task files
> - Consolidated Context Part 4 (large file)   ← blows budget; defeats DELEGATED
> ```
> CORRECT (orchestrator reads only plan files):
> ```
> Orchestrator reads:
> - Orchestration, Recovery, task files
> Orchestrator NEVER reads:
> - Consolidated Context parts, reference docs, source code
> ```

**Orchestrator reads:** Orchestration, Recovery, task files (plan files only)
**Orchestrator NEVER reads:** {list the heavy files — Consolidated Context parts, reference docs, source code}
**Subagents read:** Per-task Required Context (each subagent gets a fresh window sized by the **dispatched model** — 200K for Haiku 4.5, 1M for every other current model — regardless of the parent tier; see `references/session-context-budget.md` § Subagent Context Window)

> **Subagent overhead:** Each subagent consumes ~54K (system ~26K + global rules/CLAUDE.md ~27K + skills ~1K) before any task work begins. Verify that each task's estimate + path-rule tokens (every rule whose `paths:` matches a file the runner reads or writes, including its own task brief under the plans directory: the flagged `approx_tokens` total from `python {plugin_root}/scripts/init_project.py --doctor --project-root {project_root}`, ~{R}K measured {YYYY-MM-DD}) + ~54K < the **dispatched model's** window (Haiku 4.5 200K, every other current model 1M — NOT the parent `context_window`; see `references/session-context-budget.md` § Subagent Context Window). See `references/session-context-budget.md` § Task-Level Estimation for the bottom-up estimation formula and conversion factor.

<!-- Uncomment when any task's declared Output is under `.claude/**` — declares the
     expected permission round-trip (see references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md §14):
> [!note] Task {NN} edits `.claude/**`
> The harness permission classifier gates these writes independently of planwise
> authorization. `/planwise run` invocation does not pre-clear it: expect a user
> permission prompt mid-task, expect per-call (not all-or-nothing) denials, and
> expect that some denials may not be clearable at all. Recovery records the
> applied-vs-denied list on first denial. -->

---

## Session Task List <!-- REQUIRED -->

| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | {Task 1} | Haiku | ~{X}K | - |
| 2 | {Task 2} | Sonnet | ~{X}K | 1 |
| 3 | {Task 3} | Opus | ~{X}K | 2 |

**Total Estimated:** ~{XX}K tokens <!-- REQUIRED -->
<!-- Reconciliation: this total MUST equal the sum of Est. Tokens above.
     This session's total MUST match the Est. Tokens in the Sprint Plan Sessions table. -->

---

## Dispatch Layers <!-- REQUIRED for DELEGATED mode -->

**Declared layers:** L1 = {1, 2} · L2 = {3} · L3 = {4, 5} · L4 = {6, 7}

<!-- A layer is the set of tasks whose `Depends On` are all satisfied at the same
     point. Multi-member layers dispatch in parallel, so each one needs its
     write-target intersection COMPUTED — never annotated "disjoint target files"
     and left unshown. See references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md §17. -->

### Computed Write-Target Intersection <!-- REQUIRED for DELEGATED mode -->

Collect every member task's `**Output:**` paths; intersect them pairwise. Also collect each member's Required Context and step text, and list every layer-mate `**Output:**` path it reads. Show the result for every layer, including the empty ones — an `∅` is as much a computation as a conflict, and leaving it implicit is what makes the claim unfalsifiable.

In `Allocates from`, name each shared next-free namespace a member takes a value from (a reviewer-check number, a catalog row, a section number), or write `∅`. Two members that name one namespace collide even when their write-targets are disjoint.

| Layer | Members | Member write-targets | Intersection | Reads from a layer-mate's Output | Allocates from | Verdict |
|-------|---------|----------------------|--------------|----------------------------------|----------------|---------|
| L1 | {1, 2} | `{path-a}` / `{path-b}` | ∅ | ∅ | ∅ | ✅ disjoint — parallel stands |
| L2 | {3} | `{path-c}` | ∅ | n/a | `{namespace}` | ✅ single member |
| L3 | {4, 5} | `{path-d}`, `{path-e}` / `{path-e}` | `{path-e}` | ∅ | ∅ | ❌ NOT disjoint — serialized: 5 after 4 on `{path-e}` |
| L4 | {6, 7} | `{path-f}` / `{path-g}` | ∅ | 7 reads `{path-f}` (Task 6's Output) | ∅ | ❌ NOT parallel — 7 moved to a later layer, Depends On: 6 |

<!-- A non-empty intersection has exactly four dispositions, per
     references/agent-orchestration-delegated.md §1.13: serialize the pair,
     shard the target, route deltas to a single writer, or cap parallelism with
     genuinely disjoint regions inside the file. Name the one chosen — a bare
     "disjoint" annotation is not a disposition.

     A shared next-free IDENTIFIER (reviewer-check number, catalog row, section
     number) is a write target too, even when the tasks write different files:
     both members read the same live maximum and allocate the same value. The
     `Allocates from` column above records it. Either resolve each member's number
     pre-dispatch and inject it as a literal (§1.6), or serialize the allocating
     tasks. -->

> [!constraint] Per-task gates are scoped to that task's own outputs
> The working tree accumulates every layer member's edits with no commit between dispatches. A count asserted repo-wide by a task that edited some of them false-fails — and inside a parallel layer the reading depends on completion order, so it false-fails non-deterministically, which reads as flakiness rather than as a defect.
>
> WRONG — repo-wide count, asserted by a task that edited one file:
> ```
> {vcs} diff --name-only {shared/dir}/ | wc -l   # MUST equal edited-file count
> ```
> CORRECT — scoped to this task's own declared Output paths:
> ```
> {vcs} diff --name-only -- {this task's declared output paths} | wc -l   # 1
> ```
> Keep the repo-wide form only in a **session-closing sweep task**, where the whole-session delta genuinely is the subject.

---

## Success Criteria <!-- REQUIRED -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}
- [ ] {Measurable criterion 3}

---

## Session Start Census <!-- REQUIRED when any task gate or step asserts a live-tree figure -->

Every figure a task gate or step asserts about the live tree (a file count, a split boundary, a scan-set size, a line-ending tally) is one row here, never a bare literal in the task file. The task file names the row as `{census:<name>}`.

| Name | Scaffold value | Artifact | Commit | Date | Re-measure command | On drift |
|------|----------------|----------|--------|------|--------------------|----------|
| `{ref_count}` | {104} | {references/*.md} | {short SHA} | {YYYY-MM-DD} | {runnable command that prints the count} | substitute |
| `{split_boundary}` | {last file of the first half} | {sorted file list} | {short SHA} | {YYYY-MM-DD} | {runnable command that prints the boundary name} | halt |
| `{crlf_tally}` | {CRLF files / LF-only files} | {references/*.md} | {short SHA} | {YYYY-MM-DD} | {runnable command that prints the tally} | substitute |

Before the first dispatch the orchestrator runs every row's command at the session base and writes `CENSUS {name} = {session-base value} (scaffold {value}; {artifact} at {commit}; {date})` to Recovery Key Findings. A `substitute` row takes the session-base value. A `halt` row whose value moved is a structural finding at CONFIRM, because the figure decides a task's Output paths or a layer's write-target intersection. Two tasks that split one list read the same row.

Before each dispatch the orchestrator runs the preflight set checks, each exiting 0 when clean and 1 with the difference listed: `python -B "{plugin_root}/scripts/dispatch_preflight.py" overlap --candidate {task file} --running {running task files}` (Output paths shared with a running task), `prereq --sprint-plan {Sprint Plan} --sprint-folder {sprint folder}` (enumerated prerequisites against the derived member set), `siblings --since {scaffold date} --recoveries {closed sibling Recovery files} --edit-set {file naming the edit and sweep paths}` (sibling Files Modified that meet the edit set), and `decomposition --matrix {surface matrix} --output {consolidated output}` (matrix rows against output sections, both ways).

---

## Recovery Protocol <!-- REQUIRED -->

Update `{Abbrev}-S{XX}-{YY}-Recovery.md` after EACH task completion.

---

## Spawn-Prompt Skeleton <!-- REQUIRED for DELEGATED mode -->

<!-- Fill this in. Do NOT replace it with a prose summary of what the spawn
     prompt will contain — a summary carries only the clauses its author
     happened to recall, and the procedural checks are the ones that vanish.
     Full rule: references/agent-orchestration-delegated.md §1.8. -->

```markdown
You are dispatched to execute ONE task: {task-id}. The session has other tasks;
you DO NOT execute them.

Execute the following task YOURSELF, directly, with your own tool calls. Do NOT
spawn, dispatch, or delegate to any other agent (no Agent tool calls) —
you ARE the task-runner.

Task file:        {task-file-absolute-path}
Session ID:       {Abbrev}-S{XX}-{YY}
Plugin root:      {value of config.yaml plugin_root, read at dispatch}
Project root:     {project root absolute path, resolved at dispatch}
Output directory: {output-dir-absolute-path}
Base commit:      {ABBREV}_S{NN}_BASE={resolved SHA literal}  (omit when no task gate runs git diff)
Census:           {name}={session-base value}, ...  (omit when no task gate names a census row)

## HARD CONSTRAINTS (non-negotiable)
Execute ONLY {task-id}. Do not start any other task in the session even if the
Recovery file lists it as PENDING. Files you may write: {explicit list from the
task file's Output}.

1. Modify ONLY the files named on this task's Output line. Every other Required Context file is read-only.
2. Do NOT read files not listed in Required Context. The `Base commit:` and `Census:`
   values above are authoritative as given: never read them from Recovery or any other file
3. Do NOT spawn sub-agents or create teams
4. If you encounter an ambiguity requiring a file not in Required Context, STOP
   and report it; do NOT expand scope
5. Permitted per Execution Step (no constraint above forbids these): Step {n}:
   launches {commands}, writes {paths}, fetches {URLs or "none"}; one entry per step
6. Deferral: a shared identifier you defer (a check number, a catalog row, a
   section number) is returned as draft text with no number assigned. Parallel
   runners read the same live maximum, so a self-assigned number collides

## SCOPE BOUNDARY
This task operates within:
- **In scope:** {files/modules this task modifies}
- **Out of scope:** {adjacent files/modules this task must NOT touch}
- **Decision branches:** {one entry per branch of the task's decision rule:
  "{condition} → {permitted write, or STOP and escalate}"}

## Status Block delivery (REQUIRED)
Deliver your status block by calling the SendMessage tool with to="main".
Plain-text output does NOT reach the orchestrator.
{status-block schema — see the Status Block Return Contract section below}

Return after writing the single expected output file. Do NOT proceed to task
{n+1}.

Resume clause (a resume message to a returned runner only, never a first dispatch):
Findings to fix: {finding id} at `{file}:{line}` — {what is wrong}; one line per
finding. An Output path alone is not a finding list.
```

Where a Verification Command in the task file holds the literal `{plugin_root}`, substitute the `Plugin root:` value above. Never copy a plugin path out of the task file. Where a gate holds `{census:<name>}`, substitute that name's value from the `Census:` line above.

<!-- Add when the project declares an isolated environment (§1.27): an
     ENVIRONMENT DISCIPLINE block naming interpreter/linter/runner paths in the
     platform-matched form, plus a first-spawn interpreter diagnostic on the
     session's first dispatch only. A runner given the `Project root:` line and no
     interpreter falls back to the project `.venv` when one exists.
     Add when the task needs path-scoped rules (§1.6): inject the rule content
     as a literal — a spawned context inherits no path triggers.
     Add when the layer dispatches 3+ runners in parallel (§1.13): the PARALLEL
     DISPATCH Recovery addendum — runners do not touch the Recovery file. -->

---

## Orchestrator Post-Dispatch Checklist <!-- REQUIRED for DELEGATED mode -->

Run this against **every** returned dispatch, before reconciling Recovery and before dispatching the next layer. A returned runner is not a completed task.

### Step 1 — Classify the return

Per `references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.17.1. Classify by the final-message voice and the working-tree state, and note that four of the five states are failures:

| Signal | Diagnosis | Action |
|--------|-----------|--------|
| Fast return, dispatch-voice reply ("I've dispatched the task-runner… I'll report back"), clean tree | Self-delegation — it spawned a nested duplicate instead of executing | Resume the SAME agent with the execute-yourself directive |
| Mid-work narration ending in a colon or next-step phrase, dirty tree with genuine partial edits | Message-boundary stall — it executed part-way, then ended its message at a narration checkpoint | Resume the SAME agent with a continuation message enumerating only the remaining work |
| `completed` return whose final message ends mid-action ("Now let me…", "Next I'll…") or omits required report fields | Mid-action stall masquerading as completion | Run Step 2's gate, then resume the SAME agent to finish |
| No completion report and no named permission denial, a near-clean tree, no dispatch voice, Bash-only deliverables absent on disk | Silently auto-denied tool permission — a spawn-prompt tool path matches no allow entry | Compare the prompt's tool paths against the project's allow entries BEFORE any resume, then resume the SAME agent with paths in a granted form |
| Structured completion report whose deliverables verify on disk | Real completion | Reconcile normally |
| No final message, deliverables verify on disk, Recovery row written where owned | Real completion, report lost | Reconcile normally, note the missing report, do NOT resume (§1.17.1) |

**On every failure state, resume the SAME agent — never dispatch a fresh one.** Its context already holds the task; a fresh runner re-reads everything and can race or duplicate the first one's partial work.

### Step 2 — Gate acceptance on on-disk evidence

A harness `completed` status means the agent stopped with no live children. It is **not** a check that the deliverables were produced (§1.17.4). Before marking any task done:

- [ ] Every path in `OUTPUT_FILES` exists on disk
- [ ] **The orchestrator** runs `python "{plugin_root}/scripts/measure_files.py" {output files}` (the orchestrator reads `plugin_root` from `config.yaml` at run time) and compares against the task's declared Expected Output **token** budget — a deviation over 20% is a signal to review before the next dispatch (§1.4). The runner's self-reported count is not this check
- [ ] Grep the edit target for the symbol that was supposed to change — confirm it is present, and that residual references meant to be swept are gone
- [ ] `git status --short` shows the expected file set dirty and nothing unexpected
- [ ] Every required status-block field is present and non-empty (a blanked field is not a short one)
- [ ] If the Orchestration promised to re-verify a runner's own verdict, run the replay command named in the producing task's Output (for example `<gate_script>.py --self-test`). Do not rebuild the fixtures yourself (`references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §19)
- [ ] If the Expected Output declared required headings or table-column headers, Grep the produced file for every one of them
- [ ] If a later task also edits a file this dispatch edited, run `{lint-cmd}` on that file before the next dispatch. On a failure, halt and record it in Recovery (`references/agent-orchestration-delegated.md` §1.4)
- [ ] Recompute the runner's verdict label from its reported counts with the producing task's rule. On a mismatch, log it in Recovery and act on the recomputed label (`references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.16.1)
- [ ] If a runner reported a defective gate: the defect is reproduced from the runner's verbatim output, and the same command shape is swept across the undispatched briefs before the next dispatch (§1.16.6)
- [ ] Once every member of a parallel layer has returned, run `python -B "{plugin_root}/scripts/batch_gate.py" labels {the layer's output files}`: exit 0 means one section-label set, exit 1 lists the labels per file. Where the outputs must cover a required id list, run `python -B "{plugin_root}/scripts/batch_gate.py" items --ids {file of one id per line} {output files}`: exit 1 prints the `MISSING` and `DUPLICATE` ids
- [ ] If a status block is lost or disputed, run `python -B "{plugin_root}/scripts/extract_status_block.py" --pattern '{field regex}' {agent-*.jsonl transcript}`: exit 0 prints the last status-block match, exit 1 means no line matched
- [ ] Run `python -B "{plugin_root}/scripts/outputs_coverage.py" named --side {producer|receiver} --outputs {Outputs folder} --tasks {task files}`: exit 0 means a Required Context row names every listed file, exit 1 lists the unnamed files (`producer` checks this session's Outputs against the consumer task files; `receiver` checks the upstream Outputs against this session's task files, advisory). `count` with the same `--outputs` and `--tasks` exits 1 when a count claim differs from the file count

### Step 3 — Scan the return for a stalled tail

Read the last paragraph of the returned message for forward-looking verbs — `will`, `next I will`, `the following step will`, `planned to` (§1.10). A hit means the runner intends to continue and has gone idle. Send a resume message quoting its own last line; do **not** mark the task COMPLETE.

**On any miss in Steps 1–3, resume the SAME agent, then re-run these checks before accepting.**

---

## Status Block Return Contract <!-- REQUIRED -->

> [!constraint] DELEGATED parallel-mode runners MUST bound their return
> Full contract, derivation, and the over-tight failure mode: `references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` §1.28. A dispatched runner's status block re-enters the orchestrator's own context window whole on return — bound it so that does not accumulate across N dispatches:
> - **No re-quoted file content** — cite `OUTPUT_FILES` by path + line count, never paste an edited file's body into the block.
> - **No restated task text** — `TASK_ID` is the reference; never re-explain the brief.
> - **18-line ceiling** on the whole block, derived from the field enumeration below — see §1.28 for the full per-field table and derivation. The ceiling never cuts a field reconciliation needs.
> - **Bulk output routed to files** — anything a field cannot carry within its allocation goes to the session `Outputs/` folder; name the path instead of inlining the content.

| Field | Max lines |
|---|---|
| `TASK_STATUS` | 1 |
| `TASK_ID` | 1 |
| `ROUTE/FLAGS` | 1 |
| `OUTPUT_FILES` | 1 |
| `LINES_PRODUCED` | 1 |
| `VERIFY_RESULTS` | 5 |
| `KEY_FINDINGS` | 5 |
| `ISSUES` | 3 |
| **Total** | **18** |

See `agents/task-runner.md` §5.B for the runnable schema.

---

## Task Files <!-- REQUIRED -->

| # | Task File | Agent |
|---|-----------|-------|
| 1 | [{Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md) | {Agent} |
| 2 | [{Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md) | {Agent} |
| 3 | [{Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md) | {Agent} |

---

## Pre-Known Cross-Task Coordination Flags <!-- OPTIONAL -->

<!-- Include when an upstream session's closeout routed coordination flags to this session.
     Omit the section when none arrived. Add one H3 block per source session, and append to
     an existing block rather than opening a second one. Before dispatch the receiving orchestrator
     routes each flag into its consuming task file. In the same edit it replaces `pending` in that
     row's Routed cell with `✅ ROUTED {YYYY-MM-DD} into {task file}` (trailing text is allowed).
     A row whose Routed cell still reads `pending` at dispatch was never routed. -->

### From {source-session-id} — recorded {date}

| Flag # | Source Task | Consuming Task | Observation | Recommended Action | Routed |
|--------|-------------|----------------|-------------|--------------------|--------|
| {n} | {source-task-id} | {task-id, or "session" when the consumer is unclear} | {observation} | {recommended action} | {pending, or ✅ ROUTED {YYYY-MM-DD} into {task file}} |

---

## Post-Session Checklist <!-- REQUIRED -->

> Corresponds to Phase 4 of the run handler. Complete these steps after all tasks finish.

- [ ] **Verify outputs** — confirm all expected output files were written to `Outputs/`
- [ ] **Finalize recovery** — mark Session Status: COMPLETE, update all task statuses, add final Key Findings
- [ ] **Generate session summary** — write `Outputs/{Abbrev}-S{XX}-{YY}-Summary.md` using `templates/summary-template.md`
- [ ] **Capture lessons** — ask "Were any lessons learned?" If yes, create lesson file and run the generator
- [ ] **Update plan status** — mark this orchestration COMPLETE; update sprint plan and master plan status fields
- [ ] **Git commit and push** — stage specific files (`git add` by name, never `git add .`), commit, push

---

## Plan-Specific Sections <!-- OPTIONAL -->

Write any section that no heading above covers here, as an `###` H3. Never add it as a new `##` H2 elsewhere in this file, and draft one `idea` feedback draft for each new H3 heading (see `references/feedback-drafting.md`).

### {Section Heading}

{content}

---

**Next Step:** Execute Task 1
```
