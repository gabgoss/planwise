---
description: DELEGATED dispatch discipline, Part 3 of 4. This file holds §1.23–§1.28, the cross-cutting dispatch-prompt and orchestrator discipline, including pinning foreground execution and a long timeout for a long suite (§1.27.1), polling a background command's independent progress signal and halting after two stalled polls (§1.27.2), and the status-block return contract (§1.28). Part 1 of 4 is agent-orchestration-delegated.md.
consult-when: Writing any DELEGATED spawn prompt or checking the orchestrator's own conduct — triple-scoping a single-task dispatch, giving a structure contract a literal template, adjudicating a runner-surfaced decision, keeping verification read-only inside a runner's ownership window, pinning the interpreter, foreground execution and a long timeout for a long suite, and the status-block return contract
---

# DELEGATED Dispatch Discipline — Part 3: Cross-Cutting Dispatch Discipline

**Purpose:** Part 3 of the DELEGATED dispatch discipline. It covers the constraints that bind every spawn prompt and the orchestrator's own conduct, whatever the task: triple-scoping a single-task dispatch, giving a structure contract a literal template, adjudicating a decision a runner surfaces, keeping verification read-only inside a runner's ownership window, naming the interpreter and pinning foreground execution for a long suite (§1.27.1), and the status-block return contract.

Section numbers are continuous across all four parts. A section keeps its `§1.N` identifier wherever it lands, so an existing `§`-anchor still names exactly one section — only the filename that holds it changes.

This file holds §1.23–§1.28. The part table in [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) names the file that holds every other section.

These sections apply to every DELEGATED spawn. Read this file whenever you construct a spawn prompt or adjudicate a runner's report — Part 1 alone does not carry them. What a spawn prompt must name in both directions, how to establish that a silent runner is dead, who resolves a shared precondition, and a remediation brief's write set are in [Part 4](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md).

## Table of Contents

- [1.23 Triple-Scope the Single-Task Dispatch](#123-triple-scope-the-single-task-dispatch)
- [1.24 Structure Contracts Need a Literal Template, Not Prose](#124-structure-contracts-need-a-literal-template-not-prose)
- [1.25 Adjudicating Runner-Surfaced Decisions](#125-adjudicating-runner-surfaced-decisions)
- [1.26 The Ownership Window — Orchestrator Verification Is Read-Only](#126-the-ownership-window--orchestrator-verification-is-read-only)
- [1.27 Interpreter Discipline in Every Spawn Prompt](#127-interpreter-discipline-in-every-spawn-prompt)
- [1.28 Status-Block Return Contract](#128-status-block-return-contract)

---

## 1.23 Triple-Scope the Single-Task Dispatch

A DELEGATED runner receives the Recovery file, whose Step Completion Status table lists every task in the session, and a capable runner can adopt *finishing the session* as its goal. One instruction stating otherwise is not enough: it was measured losing to a session-scoped opening line in the same prompt.

**Every DELEGATED spawn prompt MUST state the single-task scope in all three of these positions:**

| Position | Required content |
|---|---|
| **Opener** (first sentence — the frame that competes) | `You are dispatched to execute ONE task: {task-id}. The session has other tasks; you DO NOT execute them.` |
| **Hard-constraint block** | `Execute ONLY {task-id}. Do not start any other task in the session even if the Recovery file lists it as PENDING. Files you may write: {explicit list}.` |
| **Return instructions** | `Return after writing the single expected output file. Do NOT proceed to task {n+1}.` |

Never open with a session-scoped identity (*"You are a task-runner in session {session-id}"*) without the task-scoped clause in the same sentence. That framing is the specific signal measured to override a correctly-stated single-task constraint stated only once.

**Detection.** The over-run is visible before the next dispatch: Recovery shows more than one step flipped to COMPLETE, the session's `Outputs/` directory holds more files than the task declared, or the final message references a later task's content. Check all three, because the runner's own report describes the extra work as success.

**Recovery from a detected over-run — trust but verify.** Do NOT redo the extra work, which is usually genuine. Verify the landed state, then re-dispatch only the incomplete tail. For a large over-run, dispatch **verification-only** runners that read each output, check it against its source artifacts and report discrepancies. N re-executions become N cheaper reads.

**Hook.** `hooks/agent-guard.ts` reports, without blocking, a spawn prompt that lacks one of the three clauses (`You are dispatched to execute ONE task:`, `Execute ONLY`, `Do NOT proceed to task`).

> [!constraint] One Instruction Stating Scope Is Not Scoping
> WRONG — scope stated once, under a session-scoped opener that outranks it:
> ```
> "You are a DELEGATED task-runner subagent in planwise session {session-id}.
>  Execute exactly one task and return. …"
> # Measured: the runner executed all 11 remaining tasks, wrote a Summary, and
> # flipped the session status to COMPLETE — reporting it as success.
> ```
> CORRECT — scoped at the opener, in the hard constraints, and in the return instructions:
> ```
> "You are dispatched to execute ONE task: {task-id}. The session has other tasks;
>  you DO NOT execute them.
>  … HARD CONSTRAINTS: Execute ONLY {task-id}. Do not start any other task even if
>    Recovery lists it as PENDING. Files you may write: {explicit list}.
>  … RETURN: after writing {output-file}, return. Do NOT proceed to task {n+1}."
> ```

This is the over-run counterpart to §1.7's idle-mid-step wake-up. Both break the one-task-per-dispatch contract — one by doing too little, one by doing too much — and §1.17's diagnosis table covers only the first.

## 1.24 Structure Contracts Need a Literal Template, Not Prose

When a downstream task consumes a runner's output **by structure** — an aggregator reading a named section, a table cell read by column position, a script parsing headers — the phrase "with this EXACT structure" followed by an illustrative code block is not a sufficient contract. A 12-runner batch given exactly that instruction deviated in **4 of 12 (33%)**, each with content complete and structure reorganized. The same batch run with a template file, a checklist and a pre-acceptance `Grep` produced none.

Three requirements, in order of durability:

1. **Check in a literal template file; do not inline the example.** Replace *"Write `{output}` with this EXACT structure: {code block}"* with *"Write `{output}` from the template at `{template-path}`, substituting each `{placeholder}` and keeping every heading and table column verbatim."* A reviewer can diff against a checked-in template. An inline code block is read as illustration.
2. **Encode the required headings as a checklist in the task file**, not only as a code block: *"the output MUST contain these sections, in this order: `## A`, `## B`, …"*. A checklist is read as an obligation; a code block is read as an example. Where the consumer reads a table by column position, list the exact column headers in the same checklist.
3. **Grep the output before marking the task COMPLETE.** The post-dispatch gate greps the produced file for every required heading and every required table-column header. On a miss, re-dispatch the SAME runner with a **single corrective instruction** — *"normalize `{output}` to the structure in {section} of the task file"* — rather than accepting and reconciling downstream.

**Aggregator-side defence.** A task that consumes N such files locates content by **keyword, not by heading position**, and emits a canonical-shape **shadow file** before aggregating. One pass absorbs the residual drift that the three requirements leave.

> [!constraint] A Column-Position Contract Must Be Stated as Columns
> WRONG — the consumer reads a verdict by column position; the spec shows the table only inside an illustrative block:
> ```
> "Write the file with this EXACT structure:
>  ## Verdict Summary  (table: Artifact | Verdict | Severity)"
> # One of twelve runners emitted `Dimension | Status | Notes` — complete content,
> # wrong columns; the aggregator reads cell 2 and gets "Status", not a verdict.
> ```
> CORRECT — the columns are a named checklist item and the template is a real file:
> ```
> "Fill `templates/{name}-template.md`. The Verdict Summary table MUST have exactly
>  these column headers, in this order: `Artifact`, `Verdict`, `Severity`.
>  A downstream task reads the Verdict cell by column position."
> ```

## 1.25 Adjudicating Runner-Surfaced Decisions

A runner that returns a `BRIEF COLLISION` report — a breach, a better pattern, or a contradiction its brief did not anticipate — has done the right thing. The orchestrator, not the runner, owns the decision. Two classes, decided differently.

A collision at a write-set boundary is the cheapest to prevent. [Part 4](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md) §1.32 ("Derive a Remediation Brief's Write Set From Where Each Fix Lands") says how the author derives the write set before dispatch, so the runner never meets the boundary.

### 1.25.1 Binding-rule breach → Option A / Option B gate

Treat it exactly as a Phase-1 structural finding, except that it surfaced mid-execution: present the user an explicit **Option A (coherent — apply the prescribed remedy, naming the files and the structural impact)** vs **Option B (literal — ship the breach, naming the residual defect)**, call `AskUserQuestion`, and record the outcome as a `Scope-Expansion Decisions` row in Recovery plus its Summary mirror. Do not pick before the user answers.

### 1.25.2 Pattern-divergence proposal → decide by sibling existence AND correctness

When a runner proposes a pattern that differs from what siblings in the same batch already use, the discriminator is whether correct siblings exist — **not the proposal's merit**:

| Situation | Action |
|---|---|
| Proposed pattern diverges from siblings **already authored in this session or batch** | **Redirect** to the sibling pattern; file the proposal as a post-session backlog item scoped to the whole batch |
| The convention is **not yet established** (no siblings authored) | **Accept** — this pattern is now canonical; subsequent siblings follow it |
| A sibling pattern is **broken** (wrong field name, wrong constant, wrong signature) | **Fix in-session**; back-patch affected siblings |

If siblings exist **and** work correctly, mid-session divergence is net-negative regardless of the proposal's merit. Refactor at the batch level, never one artifact at a time. A partially applied refactor forces every later attempt to re-search and re-decide, and batch-wide consistency is never reached.

**Redirect protocol** — resume the SAME runner via `SendMessage` (its context holds the task) with the rationale stated, not just the verdict: the sibling-grep evidence, the downstream cross-artifact review contract the divergence would break, and the fact that the batch-wide refactor is its own item. Then verify the final output preserves the sibling pattern with a post-task grep.

> [!constraint] Do Not Accept a Mid-Batch Pattern Change Because It Is Correct
> WRONG — the proposal is technically valid, so the orchestrator accepts it:
> ```
> Task 04 → adopts the new pattern
> Tasks 01-03 + N pre-existing artifacts → still use the old one
> # 1-of-N divergence; cross-artifact grep gates weaken to "match A or match B";
> # the refactor is now partially applied and nobody owns finishing it.
> ```
> CORRECT — redirect to sibling parity; file the batch-wide refactor as its own item:
> ```
> Task 04 → sibling pattern preserved (post-task grep confirms)
> Recovery "Next Session" → candidate item: apply the new pattern across all N artifacts,
>                           one session, one batch edit, one consistency review
> ```

### 1.25.3 Smallest sufficient fix — rank the remedy, not just the dispatch

When a runner surfaces a constraint violation together with a proposed remedy, the orchestrator directs it to the **smallest fix that resolves the violation** — not the first fix that would.

| Rank | Remedy class | Try before escalating |
|---|---|---|
| 1 | In-place edit within the existing structure (compression, inlining, removing dead weight) | always first |
| 2 | Single-file change that alters structure locally | only if rank 1 cannot resolve it |
| 3 | Multi-file structural change (splits, moves, dependency rework) | only if rank 2 cannot, and only with an Option A/B gate per §1.25.1 |

Capability inverts here: a more capable runner reaches for a more elaborate remedy because it can see one. In the measured case, **docstring compression** (rank 1, a ~12% trim) brought a module slightly over its declared size budget under it, after the runner proposed a **parser split with lazy imports to break the resulting circular dependency** (rank 3). The rank-3 proposal was competent and unnecessary.

**This is distinct from §1.9**, which ranks how a follow-up fix is **dispatched** (inline message / targeted dispatch / new session). This section ranks **which remedy is applied**. A correctly-dispatched over-invasive fix is still an over-invasive fix.

## 1.26 The Ownership Window — Orchestrator Verification Is Read-Only

A file named in a task's `Output:` line is **owned by that runner** from the moment of dispatch until the runner reports and the orchestrator accepts. Inside that window the orchestrator's verification toolkit is `Read`, `Grep`, `git status`, `git diff`, and non-mutating measurement commands (`wc -l`, `wc -c`, checksum) — nothing that writes.

**Executing an artifact is a WRITE.** So are `{formatter}`, an in-place `{notebook-executor}`, an output-clear, and most build and lint commands. They *feel* like inspection because they answer a question; they answer it by rewriting the file. Running one against a file another agent is actively writing produces a two-writer measurement — and a two-writer measurement is indistinguishable from a settled one, because it yields a number, not an error.

| Rule | |
|---|---|
| **Establish ownership at dispatch** | Every file in the task's `Output:` line is the runner's until acceptance. State it explicitly in the Orchestration when several runners hold adjacent files. |
| **Verify by reading; delegate the re-run** | If a mutating check is genuinely required — a notebook must actually execute to prove it works — `SendMessage` the owner to re-run it and report the result. Do not run it yourself in parallel. |
| **Any measurement taken inside the window is void** | Re-take it after the runner reports and the file has settled. Do not average, reconcile, or reason about the intermediate readings; they are not data. |
| **Task briefs name the owner of every verification command** | An unattributed `{build-cmd}` or in-place executor in a brief is an invitation for the runner AND the orchestrator to run it. |
| **Paths outside `Output:` are not the runner's** | The §1.4 subtraction step in `agent-orchestration-delegated.md` classifies a dirty path outside the runner's `Output:` line. Never attribute it to the runner, and never revert it from the orchestrator. |

Highest-risk shapes: notebooks and any artifact where **execution is the verification**, and high-fanout batches where several runners hold adjacent files.

**A replay command runs only after the window closes.** An Orchestration re-verify item names a command the producing task ships (`scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §19). That command runs only after the runner reports and the orchestrator accepts. It creates files only in a temp directory and removes them. It does not write the runner's Output files.

> [!constraint] Do Not Run a Mutating Verification Against a File a Runner Still Owns
> WRONG — the orchestrator verifies by executing the runner's in-flight artifact:
> ```
> runner (mid-task) → writing {artifact}
> orchestrator      → {notebook-executor} --execute --inplace {artifact}   # a WRITE
> # Four different measurements of one logical file across the session; only the
> # post-settlement reading meant anything. No error was raised at any point.
> ```
> CORRECT — read the landed state, or delegate the mutating check to the owner:
> ```
> orchestrator → Read / Grep / git status / git diff / wc -l {artifact}   # read-only
> orchestrator → SendMessage(owner, "re-run {cmd} on {artifact}; report the result")
> orchestrator → re-measure only after the runner reports and the file has settled
> ```

**Near-neighbours, neither superseded.** This is the orchestrator-vs-runner form of the contention hazard §1.13 addresses between runners — same collision, different pair, and unlike §1.13's case no strategy matrix applies, because the orchestrator does not write here at all. §1.17.4's acceptance-gate checks stay in force and remain compatible: every check it names (`Grep` the target, `git status --short`, read Recovery) is already read-only, which is why it is a gate the orchestrator may run inside the window.

The line-level form, which deletions in a session-cumulative diff belong to which task, is also the orchestrator's to attribute: see [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) § "3. Diff Attribution Is the Orchestrator's Job, Not the Runner's".

## 1.27 Interpreter Discipline in Every Spawn Prompt

Spawned contexts inherit no shell state, so the interpreter on `PATH` is the platform default, never the project's. [`agent-orchestration.md`](agent-orchestration.md) §10 row 11 records that harness fact. This section states the dispatch-side consequence.

When the project declares an isolated environment, **every** DELEGATED spawn prompt whose task invokes a project tool MUST name the interpreter and tool paths explicitly. The orchestrator emits paths matching the project's OS — never one canonical shape.

```markdown
## ENVIRONMENT DISCIPLINE
Do not change directory — pass absolute paths for file arguments, or
`git -C {repo-path}` for git, so a bare tool name resolves against the
paths given, not a changed working directory. Use these paths — a bare
tool name resolves to the platform default, not this project's environment:
  interpreter:  {env-interpreter-path}
  linter:       {env-linter-path}
  test/notebook runner: {env-runner-path}
  (each project-relative, in a form an allow entry grants)
Confirm connectivity/setup with `{env-interpreter-path} {project-precheck}` BEFORE
doing dependent work.
Run every {suite} invocation in the FOREGROUND, with a timeout up to 600000 ms.
The full suite takes about {N} minutes. Never background it and wait.
A command over the ceiling: background it, poll {progress-probe} every 60-90 s,
and halt and report after two consecutive polls with no advance.
```

Emit the form for the project's platform, not both: POSIX `./.venv/bin/{tool}`, or Windows `.venv/Scripts/{tool}.exe` (Git Bash strips a backslash).

Each tool path MUST match a form a permission allow entry grants. A path no allow entry grants is denied silently when the runner cannot prompt ([Part 2 §1.21](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md)). If no entry grants a needed tool, tell the user before dispatch.

**Spawn prompts are not the only surface.** A task file's own **Verification Commands** carry the project-relative interpreter path too. A dispatched bare interpreter resolves against the subagent's ambient environment wherever it appears, and a command copied out of a brief inherits that defect. Long-lived repository scripts SHOULD also self-heal: a script that detects the wrong interpreter re-executes itself under the project's, rather than failing or, worse, succeeding against the wrong one.

**First-spawn diagnostic.** The first dispatch of a session probes one command per tool class the task invokes, so a silent gap becomes a loud one:

```
{env-interpreter-path} -c "import sys; print(sys.executable)"
{env-linter-path} --version
{env-runner-path} --version
```

An interpreter probe clears only the interpreter. HALT if a probe is denied or resolves outside the project environment. The shipped task-runner also detects `{Project root}/.venv/pyvenv.cfg` when the prompt names no interpreter, and runs the same `sys.executable` confirmation. That fallback does not replace the ENVIRONMENT DISCIPLINE block.

**Treat an "environment unavailable" report as UNVERIFIED, not as a completed check.** Before accepting one, confirm the runner received an interpreter path. A claim that a verification *could not* run deserves the scrutiny of a claim that it *failed*: the second is loud, the first is silent, and both leave the same gate unrun.

> [!constraint] A Bare Tool Name in a Spawn Prompt Is an Unrun Gate
> WRONG — the prompt inherits the orchestrator's environment implicitly:
> ```
> "…then run the connectivity precheck and the smoke test."
> # Runner executes the precheck with the platform default interpreter,
> # hits a module-resolution error, and reports: "smoke tests NOT RUN —
> # requires a live connection unavailable in this environment."
> # File-level work reported PASS. The gate never ran. No error surfaced.
> ```
> CORRECT — the prompt names the paths and the first dispatch proves them:
> ```
> "## ENVIRONMENT DISCIPLINE
>  interpreter: {env-interpreter-path} … Confirm one probe per tool class
>  (`{env-linter-path} --version`, `{env-runner-path} --version`) and HALT if
>  a probe is denied or resolves outside the project environment."
> # Cost: ~50 tokens per dispatch. Cost of omitting it: one lost verification
> # cycle per dispatch, plus a false PASS on every gate that silently did not run.
> ```

### 1.27.1 Pin foreground execution and a long timeout for any suite longer than about a minute

A backgrounded long command turns "waiting" into "stopped" for a dispatched runner. Polling costs turns, so it is reserved for a command over the foreground ceiling (§1.27.2). A background job's completion reaches the runner's own harness, not the orchestrator, and the idle notification ("waiting on it") is easy to mistake for a live task. §1.21 of Part 2 covers how the orchestrator launches the runner. This subsection covers a command the runner backgrounds itself.

> [!constraint] Pin the execution mode and the timeout in the spawn prompt
> - **State the foreground requirement in the ENVIRONMENT DISCIPLINE block of every spawn prompt whose task runs a suite longer than about one minute.** Give the expected duration too, so the runner sizes its timeout and does not reach for the background.
> - **Cap and pin the timeout.** Name the timeout in milliseconds, up to the harness maximum.
>
> WRONG — the spawn prompt says only which command to run:
> ```
> Tests: python -m pytest -q <path-to-suite>
> # runner: Bash(..., run_in_background=true) -> "waiting on it" -> idle, forever
> ```
> CORRECT — the spawn prompt pins the execution mode and the timeout, and names the failure:
> ```
> Run every pytest invocation in the FOREGROUND, with a timeout up to 600000 ms.
> The full suite takes about 3-4 minutes. Never background it and wait.
> ```

After the pinned lines entered every later spawn prompt in the measured case, five further runners and two fix rounds did not repeat the stall. `hooks/agent-guard.ts` reports, without blocking, a spawn prompt that lacks the `FOREGROUND` clause.

**Applies to** DELEGATED task-runner spawn prompts and to any task whose verification includes a multi-minute suite, build or migration run. The orchestrator-side classification and resume of a runner that stalled this way is Part 2 §1.17.1 and §1.17.3.

### 1.27.2 Long-running commands: foreground under the ceiling, poll above it

A backgrounded child does not outlive the session that launched it. A stall inside a backgrounded job also looks like progress, because a stalled process never sends the completion notification. The pattern "wait for the notification" has no timeout. §1.27.1 covers a command that fits the foreground ceiling. This subsection covers a command that cannot.

> [!constraint] Choose the pattern by run length, and make the work resumable in both
> | Run length | Pattern |
> |---|---|
> | Fits the foreground ceiling (600000 ms) | Run in the foreground. A stall surfaces as a timeout. |
> | Longer | Run in the background. Poll a progress signal that does not depend on the job every 60-90 s. Halt and report when it fails to advance across two consecutive polls. |
> | Either | Make the work resumable. Assert the landed delta, never the exit code. |
>
> - **The progress signal does not depend on the job.** A row count and a latest-timestamp query over a per-fetch audit table qualify. A line the job writes to its own log does not, because a stalled job writes nothing.
> - **Resumability has three parts.** Use a natural key with a UNIQUE constraint, an idempotent merge, and a resume filter that reads what is already stored.
> - **Assert the landed delta.** The exit code of a piped command is the status of its last stage, so a pipe into `tail` always exits 0.
> - **Write resume state before a session ends with a job in flight.** Record what landed, what remains, and the exact next command.
> - **Check for a live process id before ordering a restart.** A duplicate launch spends the budget twice.
> - **Verify the landed set is coherent before adopting it as a baseline.**
>
> WRONG — launch in the background and wait for a notification that a stalled job never sends:
> ```
> run ingestion in the background -> "waiting on the completion notification"
> # the job stalls, the session ends, the log holds one line: [killed]
> # no status block returns, and the Recovery file stays PENDING
> ```
> CORRECT — poll a signal the job does not own, and halt on a stall:
> ```
> run ingestion in the background
> poll: SELECT COUNT(*), MAX(ingestion_timestamp) FROM {audit-table}   # every 60-90 s
> stall: the pair is unchanged across two consecutive polls -> halt and report
> before the session ends: write what landed, what remains, and the exact next command
> ```

Measured case. A 1,393-item run forecast at about 13 minutes was launched in the background. After 976 items persisted, 50 minutes passed with no fetch, error or log line, and the session ended with `[killed]` in the job log. The next day the database held 39,159 rows against a recorded baseline of 120. Recovery took a forensic pass over two transcripts, the job log and a live re-measure. When the orchestrator briefly ordered a re-run during diagnosis, the runner refused and cited the live process id, which was right.

**Applies to** DELEGATED task-runner spawn prompts and to any task whose verification includes a command expected to exceed the 600000 ms foreground ceiling.

## 1.28 Status-Block Return Contract

When a dispatched task-runner completes, its final-message status block re-enters the orchestrator's own context window whole — in one measured instance this single re-entry cost **+27,008 tokens** in one turn (an upper bound on one event, never a per-dispatch rate; an earlier raw-content proxy overstated the same event ~4×). A session with N dispatches carries N such re-entries plus N dispatch prompts. **This section binds every parallel-mode runner return** (`agents/task-runner.md` §5.B); the status block is the token-cost lever the plugin's own contract controls, because the orchestrator cannot bound what a subagent thinks — only what it is contracted to return.

**This bound sits inside a directional finding, not a point fact.** Dispatching sessions measure heavier than direct-mode sessions (1.68× on median window size), but mode classification is a **lower bound** on delegated: a session that only continued an already-dispatched agent, issuing no fresh dispatch call, would classify as direct. Spot-checks found none such — not exhaustively ruled out. Any prose in this file or its siblings citing the ratio, or a "100% of delegated sessions" figure, carries this hedge.

This section bounds the block's **payload**. It does not specify how the block reaches the orchestrator — [Part 4](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md) §1.29.1 binds that, and a prompt that gives the shape without the channel produces a block nobody receives.

**Four binding clauses, in every parallel-mode return:**

1. **No re-quoted file content.** Cite a changed file by path and line count; never paste its body back into the orchestrator's window. The orchestrator already has the file on disk — quoting it a second time is the accumulation this section exists to stop.
2. **No restated task text.** The orchestrator dispatched the task and already holds the task file. A return references `TASK_ID` only — it never re-explains what the task was or re-summarizes the brief.
3. **An explicit line ceiling — 18 lines total**, derived by enumerating what central reconciliation actually consumes and capping each field at its worst case (not chosen for roundness — a supplied starting figure is the mechanism by which a derivation returns that figure, so none is supplied here):

   | Field | Max lines | Basis |
   |---|---|---|
   | `TASK_STATUS` | 1 | single enum value |
   | `TASK_ID` | 1 | single id string |
   | `ROUTE/FLAGS` | 1 | a coordination-flag pointer, or "none" — a flag needing more than a one-line pointer belongs in its own routed file, not the status block |
   | `OUTPUT_FILES` | 1 | comma-separated paths |
   | `LINES_PRODUCED` | 1 | single sum |
   | `VERIFY_RESULTS` | 5 | one summary line per gate category, capped at the same magnitude as `KEY_FINDINGS` below |
   | `KEY_FINDINGS` | 5 | existing "2-5 short bullets" cap (`agents/task-runner.md` §5.B), unchanged |
   | `ISSUES` | 3 | mirrors `agents/task-runner.md`'s own Error Handling cap — "do NOT exceed 3 attempts per operation" |
   | **Total** | **18** | sum of per-field worst case — a ceiling, not a typical-case average |

   This table is the one status-block schema for Agent-tool runners: where the orchestration template, the task-runner agent, the delegated §1.13 parallel-dispatch block or `handlers/run.md` restates a field list, this table wins, and each restatement is to be replaced by a pointer to this section by heading text. A Workflow script's `agent()` call returns the JSON its `schema` option names, and this section does not govern it.

4. **Bulk output routed to files.** Anything a field cannot carry within its allocation goes to the session `Outputs/` folder; the return names the path, and the orchestrator reads the file only if reconciliation needs it.

**Over-tight is a named failure mode.** The field enumeration above is the floor — the ceiling never cuts a field reconciliation needs. A runner that drops or blanks a required field (e.g., omits `ISSUES` instead of writing "none", or truncates `KEY_FINDINGS` mid-bullet) to fit under 18 lines converts a token saving into a correctness problem: reconciliation cannot act on information that was never returned. When a genuine return needs more than a field's allocation — six findings instead of five, a long coordination flag — the remedy is clause 4 (route the overflow to `Outputs/`), never silent truncation.

The plugin script `scripts/check_status_block.py` checks a returned status block against the eight-field schema of this section.

> [!constraint] Cite the id, route to the file — never re-quote or restate
> WRONG — the return pastes the edited section back into the orchestrator's window and re-explains the task it was given:
> ```
> TASK_STATUS: COMPLETE
> I finished the task of adding a new status-block return contract section.
> Here is the full section text I landed, for your review:
> ## 1.28 Status-Block Return Contract
> When a dispatched task-runner completes... [60 more lines]
> ```
> CORRECT — path + line count, task id only, bulk detail stays on disk:
> ```
> TASK_STATUS:    COMPLETE
> TASK_ID:        {task-id}
> OUTPUT_FILES:   references/agent-orchestration-delegated.md (+40L)
> KEY_FINDINGS:
> - New §1.28 landed at live-max+1; ceiling=18 derived from field enumeration
> ```

> [!note] Moved to Part 4
> - §1.29 A Subagent's World Is Its Definition Plus Its Prompt — held in [`agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md`](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md)
> - §1.30 Liveness — Establish Death Before Dispatching a Replacement — held in [`agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md`](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md)
> - §1.31 A Shared Precondition Belongs to the Orchestrator — held in [`agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md`](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md)
> - §1.32 Derive a Remediation Brief's Write Set From Where Each Fix Lands — held in [`agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md`](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md)

---

**Part of a four-file discipline:** [Part 1 — Foundations and Dispatch-Prompt Construction](agent-orchestration-delegated.md) (§1.1–§1.13) · [Part 2 — Dispatch Mechanics and Returns](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22) · [Part 4 — Delivery, Liveness and Remediation](agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md) (§1.29–§1.32)

*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*

