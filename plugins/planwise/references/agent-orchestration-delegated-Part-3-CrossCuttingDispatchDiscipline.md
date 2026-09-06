---
description: DELEGATED dispatch discipline, Part 3 of 3. This file holds §1.23–§1.31, the cross-cutting dispatch-prompt and orchestrator discipline. Part 1 of 3 is agent-orchestration-delegated.md.
---

# DELEGATED Dispatch Discipline — Part 3: Cross-Cutting Dispatch Discipline

**Purpose:** Part 3 of the DELEGATED dispatch discipline. It covers the constraints that bind every spawn prompt and the orchestrator's own conduct, whatever the task: triple-scoping a single-task dispatch, giving a structure contract a literal template, adjudicating a decision a runner surfaces, keeping verification read-only inside a runner's ownership window, naming the interpreter, the status-block return contract, what a spawn prompt must name in both directions, how to establish that a silent runner is dead before dispatching a replacement, and who resolves a precondition a whole dispatch layer shares.

Section numbers are continuous across all three parts. A section keeps its `§1.N` identifier wherever it lands, so an existing `§`-anchor still names exactly one section — only the filename that holds it changes.

| Part | File | Sections | Topic |
|---|---|---|---|
| 1 | [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) | §1.1–§1.13 | Declaration, foundations, and dispatch-prompt construction |
| 2 | [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) | §1.14–§1.22 | Dispatch mechanics and post-return handling |
| 3 (this file) | `agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` | §1.23–§1.31 | Cross-cutting dispatch-prompt and orchestrator discipline |

These sections apply to every DELEGATED spawn. Read this file whenever you construct a spawn prompt, adjudicate a runner's report, or decide what to do about a runner that has gone quiet — Part 1 alone does not carry them.

## Table of Contents

- [1.23 Triple-Scope the Single-Task Dispatch](#123-triple-scope-the-single-task-dispatch)
- [1.24 Structure Contracts Need a Literal Template, Not Prose](#124-structure-contracts-need-a-literal-template-not-prose)
- [1.25 Adjudicating Runner-Surfaced Decisions](#125-adjudicating-runner-surfaced-decisions)
- [1.26 The Ownership Window — Orchestrator Verification Is Read-Only](#126-the-ownership-window--orchestrator-verification-is-read-only)
- [1.27 Interpreter Discipline in Every Spawn Prompt](#127-interpreter-discipline-in-every-spawn-prompt)
- [1.28 Status-Block Return Contract](#128-status-block-return-contract)
- [1.29 A Subagent's World Is Its Definition Plus Its Prompt](#129-a-subagents-world-is-its-definition-plus-its-prompt)
- [1.30 Liveness — Establish Death Before Dispatching a Replacement](#130-liveness--establish-death-before-dispatching-a-replacement)
- [1.31 A Shared Precondition Belongs to the Orchestrator](#131-a-shared-precondition-belongs-to-the-orchestrator)

---

## 1.23 Triple-Scope the Single-Task Dispatch

A DELEGATED runner is handed the Recovery file, whose Step Completion Status table enumerates every task in the session. A capable runner reads that list and can adopt *finishing the session* as its goal. A single instruction stating otherwise is not enough — it has been measured losing to a session-scoped opening line in the same prompt.

**Every DELEGATED spawn prompt MUST state the single-task scope in all three of these positions:**

| Position | Required content |
|---|---|
| **Opener** (first sentence — the frame that competes) | `You are dispatched to execute ONE task: {task-id}. The session has other tasks; you DO NOT execute them.` |
| **Hard-constraint block** | `Execute ONLY {task-id}. Do not start any other task in the session even if the Recovery file lists it as PENDING. Files you may write: {explicit list}.` |
| **Return instructions** | `Return after writing the single expected output file. Do NOT proceed to task {n+1}.` |

Never open with a session-scoped identity (*"You are a task-runner in session {session-id}"*) without the task-scoped clause in the same sentence. That framing is the specific signal measured to override a correctly-stated single-task constraint stated only once.

**Detection.** The over-run is visible before the next dispatch: the returned Recovery shows more than one step flipped to COMPLETE, the session's `Outputs/` directory holds more files than the task declared, or the final message references content belonging to a later task. Check all three; the runner's own report will describe the extra work as success.

**Recovery from a detected over-run — trust but verify.** Do NOT redo the extra work; it is usually genuine. Verify the landed state, then re-dispatch only the genuinely incomplete tail. For a large over-run, dispatch **verification-only** runners (read the existing output, fact-check it against its source artifacts, report discrepancies) rather than re-executing the tasks; this converts N re-executions into N cheaper reads.

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

When a downstream task consumes a runner's output **by structure** — an aggregator reading a named section, a table cell read by column position, a script parsing headers — the phrase "with this EXACT structure" followed by an illustrative code block is not a sufficient contract. Measured deviation rate on a 12-runner batch given exactly that instruction: **4 of 12 (33%)**, with content complete and structure reorganized in every failing case. The same batch run with a template file, a checklist, and a pre-acceptance grep produced none.

Three requirements, in order of durability:

1. **Check in a literal template file; do not inline the example.** Replace *"Write `{output}` with this EXACT structure: {code block}"* with *"Write `{output}` by reading the template at `{template-path}` and substituting each `{placeholder}` — preserve every heading and every table column verbatim."* A checked-in template is an artifact the reviewer can diff against; an inline code block is read as illustration.
2. **Encode the required headings as a checklist in the task file**, not only as a code block: *"the output MUST contain these sections, in this order: `## A`, `## B`, …"*. A checklist is read as an obligation; a code block is read as an example. Where the consumer reads a table by column position, list the exact column headers in the same checklist.
3. **Grep the output before marking the task COMPLETE.** The post-dispatch gate greps the produced file for every required heading and every required table-column header. On a miss, re-dispatch the SAME runner with a **single corrective instruction** — *"normalize `{output}` to the structure in {section} of the task file"* — rather than accepting and reconciling downstream.

**Aggregator-side defence.** A task that consumes N such files locates content by **keyword, not by heading position**, and emits a canonical-shape **shadow file** before aggregating. This costs one pass and makes the aggregation robust to the residual drift the three requirements above do not eliminate.

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

### 1.25.1 Binding-rule breach → Option A / Option B gate

Treat it exactly as a Phase-1 structural finding, except that it surfaced mid-execution: present the user an explicit **Option A (coherent — apply the prescribed remedy, naming the files and the structural impact)** vs **Option B (literal — ship the breach, naming the residual defect)**, call `AskUserQuestion`, and record the outcome as a `Scope-Expansion Decisions` row in Recovery plus its Summary mirror. Do not pick before the user answers.

### 1.25.2 Pattern-divergence proposal → decide by sibling existence AND correctness

When a runner proposes a pattern that differs from what siblings in the same batch already use, the discriminator is whether correct siblings exist — **not the proposal's merit**:

| Situation | Action |
|---|---|
| Proposed pattern diverges from siblings **already authored in this session or batch** | **Redirect** to the sibling pattern; file the proposal as a post-session backlog item scoped to the whole batch |
| The convention is **not yet established** (no siblings authored) | **Accept** — this pattern is now canonical; subsequent siblings follow it |
| A sibling pattern is **broken** (wrong field name, wrong constant, wrong signature) | **Fix in-session**; back-patch affected siblings |

If siblings exist **and** work correctly, mid-session divergence is net-negative regardless of the proposal's merit. Refactor at the batch level, never one artifact at a time — a partially applied refactor forces every later attempt to re-grep and re-decide, and the natural endpoint of batch-wide consistency is never reached.

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

Capability inverts here: a more capable runner reaches for a more elaborate remedy, because it can see one. In the measured case a module slightly over its declared size budget was brought under it by **docstring compression** (rank 1, a ~12% trim) after the runner had proposed a **parser split with lazy imports to break the resulting circular dependency** (rank 3). The rank-3 proposal was competent and unnecessary.

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

Highest-risk shapes: notebooks and any artifact where **execution is the verification**, and high-fanout batches where several runners hold adjacent files.

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

**Near-neighbours, neither superseded.** This is the orchestrator-vs-runner form of the contention hazard §1.13 addresses between runners — same collision, different pair, and unlike §1.13's case no strategy matrix applies, because the orchestrator does not write here at all. §1.17.4's acceptance-gate checks stay in force and remain compatible: every check it names (`grep` the target, `git status --short`, read Recovery) is already read-only, which is why it is a gate the orchestrator may run inside the window.

## 1.27 Interpreter Discipline in Every Spawn Prompt

Spawned contexts inherit no shell state — the interpreter on `PATH` is the platform default, never the project's. That harness fact is recorded at [`agent-orchestration.md`](agent-orchestration.md) §10 row 11 and is not restated here; what follows is the dispatch-side consequence.

When the project declares an isolated environment, **every** DELEGATED spawn prompt whose task invokes a project tool MUST name the interpreter and tool paths explicitly. The orchestrator emits paths matching the project's OS — never one canonical shape.

```markdown
## ENVIRONMENT DISCIPLINE
Do not change directory — pass absolute paths, or `git -C {repo-path}` for
git, so a bare tool name resolves against the paths given, not a changed
working directory. Use these paths — a bare tool name resolves to the
platform default, not this project's environment:
  interpreter:  {env-interpreter-path}
  linter:       {env-linter-path}
  test/notebook runner: {env-runner-path}
Confirm connectivity/setup with `{env-interpreter-path} {project-precheck}` BEFORE
doing dependent work.
```

Emit the POSIX (`./.venv/bin/{tool}`) or the Windows (`.\.venv\Scripts\{tool}.exe`) form per the project's platform; do not emit both and leave the runner to choose.

**Spawn prompts are not the only surface.** A task file's own **Verification Commands** carry the project-relative interpreter path too — a dispatched bare interpreter resolves against the subagent's ambient environment wherever it appears, and a command copied out of a brief inherits that defect verbatim. Long-lived repository scripts SHOULD additionally self-heal: when a script detects it is running under the wrong interpreter, it re-executes itself under the project's rather than failing or, worse, succeeding against the wrong one.

**First-spawn diagnostic.** The first dispatch of a session confirms its interpreter before doing other work — one line, once per session, that converts a silent gap into a loud one:

```
{env-interpreter-path} -c "import sys; print(sys.executable)"
```

HALT if the output does not resolve inside the project environment.

**Treat an "environment unavailable" report as UNVERIFIED, not as a completed check.** Before accepting one, confirm the runner was given an interpreter path at all. A runner claiming a verification *could not* run deserves the scrutiny of one claiming it *failed* — the second is loud, the first is silent, and both leave the same gate unrun.

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
>  interpreter: {env-interpreter-path} … Confirm with
>  `{env-interpreter-path} -c \"import sys; print(sys.executable)\"` and HALT
>  if it does not resolve inside the project environment."
> # Cost: ~50 tokens per dispatch. Cost of omitting it: one lost verification
> # cycle per dispatch, plus a false PASS on every gate that silently did not run.
> ```

## 1.28 Status-Block Return Contract

When a dispatched task-runner completes, its final-message status block re-enters the orchestrator's own context window whole — in one measured instance this single re-entry cost **+27,008 tokens** in one turn (an upper bound on one event, never a per-dispatch rate; an earlier raw-content proxy overstated the same event ~4×). A session with N dispatches carries N such re-entries plus N dispatch prompts. **This section binds every parallel-mode runner return** (`agents/task-runner.md` §5.B); the status block is the token-cost lever the plugin's own contract controls, because the orchestrator cannot bound what a subagent thinks — only what it is contracted to return.

**This bound sits inside a directional finding, not a point fact.** Dispatching sessions measure heavier than direct-mode sessions (1.68× on median window size), but mode classification is a **lower bound** on delegated: a session that only continued an already-dispatched agent, issuing no fresh dispatch call, would classify as direct. Spot-checks found none such — not exhaustively ruled out. Any prose in this file or its siblings citing the ratio, or a "100% of delegated sessions" figure, carries this hedge.

This section bounds the block's **payload**. It does not specify how the block reaches the orchestrator — §1.29.1 binds that, and a prompt that gives the shape without the channel produces a block nobody receives.

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

4. **Bulk output routed to files.** Anything a field cannot carry within its allocation goes to the session `Outputs/` folder; the return names the path, and the orchestrator reads the file only if reconciliation needs it.

**Over-tight is a named failure mode.** The field enumeration above is the floor — the ceiling never cuts a field reconciliation needs. A runner that drops or blanks a required field (e.g., omits `ISSUES` instead of writing "none", or truncates `KEY_FINDINGS` mid-bullet) to fit under 18 lines converts a token saving into a correctness problem: reconciliation cannot act on information that was never returned. When a genuine return needs more than a field's allocation — six findings instead of five, a long coordination flag — the remedy is clause 4 (route the overflow to `Outputs/`), never silent truncation.

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

## 1.29 A Subagent's World Is Its Definition Plus Its Prompt

A spawned agent knows two things: what its own agent definition carries, and what its spawn prompt literally names. It inherits nothing else. It does not inherit the conditional reads the orchestrator performed, and it does not inherit a convention the protocol merely assumes.

The failure is silent in both directions. An instruction the prompt omits never arrives. Telemetry the prompt never routed never returns. Neither omission raises an error. §1.29.1 binds the inbound direction, §1.29.2 the outbound one, and §1.29.3 states the shared rule.

### 1.29.1 Name the delivery channel, not just the payload format

A spawn prompt that specifies a status block's *format* has not specified how the block reaches the orchestrator. §1.28 bounds what the block carries; this section binds how it arrives. When runners are spawned as named or teammate-style agents, a plain-text final message does not route to the orchestrator — only an idle notification arrives. A protocol that says "RETURN a status block" then means "write a status block nobody receives."

> [!constraint] Specify the mechanism, not only the shape
> WRONG — the prompt gives the format and no channel:
> ```markdown
> ## Status Block (required final-message format)
> TASK_STATUS:   COMPLETE | BLOCKED | PARTIAL
> TASK_ID:       {task-id}
> ...
> ```
> CORRECT — the prompt names the tool and the recipient:
> ```markdown
> ## Status Block delivery (REQUIRED)
> Deliver your status block by calling the SendMessage tool with to="team-lead".
> Plain-text output does NOT reach the orchestrator.
> TASK_STATUS:   COMPLETE | BLOCKED | PARTIAL
> TASK_ID:       {task-id}
> ...
> ```

Two practices follow.

**Acceptance may proceed on disk evidence while telemetry is recovered.** The on-disk deliverable gate confirms COMPLETE independently of the status block; §1.17.4 specifies that gate and this section does not restate it. The recovered block then supplies `KEY_FINDINGS` for Recovery reconciliation.

**Name the tool and the recipient when re-requesting a missing block.** A generic re-request — "reply with your status block" — reproduces the original failure, because it leaves the channel unnamed a second time. In one measured 7-runner parallel dispatch every runner had executed correctly and written its deliverables, yet the orchestrator received only idle notifications. All 7 blocks arrived only after an explicit instruction to call the SendMessage tool with `to="team-lead"`. The generic re-request cost one wasted round-trip per runner.

### 1.29.2 Push a lead-resolved condition into the spawn prompt

A handler that enumerates conditional references for the orchestrator, then delegates the actual checking to spawned agents, has split the condition from the check. The orchestrator resolves the condition and never runs the check. The spawned agent runs the check and never sees the condition. The checklist row is then present, indexed, and never evaluated.

> [!constraint] Resolve the condition in the lead, then name it in the prompt
> WRONG — the prompt names the role, the plan type and the paths, but never the execution strategy or the conditional reference:
> ```markdown
> "You are reviewing plan {Abbrev} for task quality.
>  Your assigned role: Task Reviewer
>  Plan path: {PlanPath}
>  Task files: {list}
>  Orchestration files: {list}"
> # The reviewer starts with a fresh context window. Nothing tells it the plan is
> # DELEGATED, and nothing points it at the reference whose §§ its checklist cites.
> ```
> CORRECT — the lead appends a block naming the reference, the sections to verify, and the rows to report against:
> ```markdown
> "…Orchestration files: {list}
>
>  This plan declares Execution Strategy: DELEGATED. The dispatch discipline
>  ships in three parts. Read each one and verify every Orchestration file
>  against the sections that part holds:
>    - references/agent-orchestration-delegated.md
>        -> §1.1-§1.4, §1.8-§1.13
>    - references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md
>        -> §1.16
>    - references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md
>        -> §1.23-§1.27
>  Report each miss against its Error Pattern Catalog row."
> ```

Two practices follow.

**The lead already knows the trigger.** One Grep for `Execution Strategy:\s*DELEGATED` over the Master Plan and every Orchestration file decides whether to append the block. A handler that already runs that Grep for another check reuses the same result here, at no extra cost.

**A checklist row with no loader is a false assurance.** When auditing a checklist-driven handler, verify for each row that *some* spawn prompt causes it to be evaluated. Counting how often the handler names the reference does not answer that question. A mention in a synthesis step, or in a lead-side conditional-reference list, loads nothing into the agent that runs the check. Read each prompt.

Hand-extending one prompt for one pass does not fix this. The next run reverts to the shipped prompt and the blind spot returns. The extension has to land in the handler.

### 1.29.3 The shared rule

Both directions are one rule with the arrow reversed. The table below names what the orchestrator holds and what the prompt must therefore carry.

| Direction | The orchestrator holds | The prompt MUST carry |
|---|---|---|
| Outbound — instruction to the runner | A condition it resolved, or a convention the protocol assumes | The resolved instruction, named literally |
| Inbound — telemetry from the runner | An expectation of structured return | The delivery channel, not only the payload shape |

Applied: any handler that both enumerates conditional references for the lead and delegates the checking to spawned agents MUST resolve the condition in the lead and push the resulting instruction into the prompt. Symmetrically, any orchestration expecting structured telemetry back MUST specify the delivery channel, not only the payload shape.

## 1.30 Liveness — Establish Death Before Dispatching a Replacement

A task-runner produces **no observable output between dispatch and its final status block**. For a short task that gap is seconds. For a fixture build or a probe loop it can be hours. Across that whole window the orchestrator cannot tell apart three states that demand opposite responses:

| State | Correct response |
|---|---|
| Working normally | Wait. Touch nothing it owns (§1.26). |
| Dead or killed | Re-dispatch. |
| Stalled or looping | Intervene, then re-dispatch. |

§1.17 classifies a runner that **returned**. This section covers the case where nothing arrives at all, which is exactly the case the orchestrator must resolve by inference rather than by reading a report.

> [!constraint] Silence is not evidence of death — prove it before replacing the runner
> The recovery action for a presumed-dead runner is re-dispatch, and re-dispatching onto a **live** runner puts two writers on one task's declared output set. Where the task writes only its own output file, that corrupts a deliverable. Where it writes machine-global state under inventory-and-restore, two concurrent restore sequences can leave a global config file holding fixture content, with no clean rollback and no error raised.
>
> So the ordering is binding: **establish death, then dispatch a replacement. Never the reverse.**

**Two things that look like liveness signals are not.**

1. **An agent listing may not show in-process subagents at all.** Measured with a dispatched task-runner actively writing files, the listing returned only peer interactive sessions and no subagent rows whatsoever — and a *completed* runner from earlier in the same session was equally absent. A listing that cannot tell running from finished from never-existed cannot support an inference either way. Reading absence there as death is unsound.
2. **An idle notification means "available", not "finished".** It is a signal about the runner's turn, not about its work, and it says nothing at all about the case at issue here: sustained silence.

**The check that settles it is the runner's own transcript.** It is cheap, it is available throughout the window, and it discriminates directly:

```bash
F={agent-transcript-path}          # the dispatched subagent's own JSONL transcript
wc -l < "$F"                       # sample twice, a minute apart — growing => alive
python -c "import json,sys;print(json.loads(open(sys.argv[1],encoding='utf-8').readlines()[-1])['timestamp'])" "$F"
date -u -Iseconds                  # compare against the line above
```

A last-entry timestamp seconds old settles the question: alive. Minutes old **with no line growth across two samples** is a genuine stall. One sample proves nothing — a single reading is consistent with both hypotheses, which is the whole failure mode.

> [!pitfall] A half-built output tree is not evidence of a dead process
> **Problem:** the orchestrator inventories disk, finds a partial artifact tree, and reads it as the residue of a mid-write kill. In the measured incident that tree was a snapshot of a **live** agent mid-write; the runner wrote again minutes after being declared dead, having never stopped. Every input the orchestrator used was consistent with both hypotheses. It picked one and acted.
> **Solution:** a disk inventory measures *what exists*, never *whether a writer is still attached to it*. Only the transcript check answers the second question. Run it before concluding anything from disk state.

**The replacement runner self-checks before its first write.** When a re-dispatch does happen, the detection that catches a wrong death call belongs in the protocol rather than in luck. Tell the replacement, in its spawn prompt, that its inventory is a **frozen snapshot** taken at dispatch:

```markdown
The file inventory above was captured when you were dispatched and is a frozen
snapshot. BEFORE your first write, compare it against live modification times.
Anything created or modified between that snapshot and your first tool call
means another writer is active on this task: HOLD and report it. Do NOT
proceed to any irreversible step.
```

In the measured incident this is what held the line — the duplicate compared its snapshot against live mtimes, saw fixture files created minutes *before its own first tool call*, and stopped short of the irreversible swap. Blast radius was zero because the duplicate caught the error, not because the orchestrator's reasoning was sound.

**A replacement's brief marks the dead runner's leftovers UNVERIFIED.** A partial artifact reads as a complete one to whatever consumes it next. When a re-dispatch is genuinely warranted, enumerate what the previous runner left on disk and label the inventory UNVERIFIED, so the replacement re-derives rather than trusting it.

> [!practice] A toolchain that updates mid-run splits a measurement set silently
> An auto-updating CLI can upgrade itself between dispatches, or during one. For a campaign treating measurements as per-build facts, an update landing between repetitions splits a rep set across two builds with nothing surfacing an error. The same event also produces a long quiet window that is easy to misread as a dead runner. Pin or record the build at session start, and re-record it at close; a measurement set that spans two builds is reported as two sets.

## 1.31 A Shared Precondition Belongs to the Orchestrator

A precondition that every task in a dispatch layer depends on — a baseline SHA, a resolved schema version, a next-free identifier — is the **orchestrator's** to establish. It is not the first task's. Resolve it once, before the layer goes out, and hand every runner the resolved value.

```
# WRONG — task 01 produces it, tasks 02-06 consume it, all dispatched together
Task 01: BASE=$({pin command}); write BASE to {shared bookkeeping file}
Task 0N: BASE=$(read back from {shared bookkeeping file}); test -n "$BASE" || exit 1

# CORRECT — orchestrator resolves once, pre-dispatch
orchestrator:          assert preconditions; BASE=$({pin command}); record centrally
spawn prompt (all N):  "BASE={resolved literal value}"
```

The WRONG shape fails twice over, and the two failures compound. All N tasks dispatch **concurrently**, so task 01 has produced nothing at the moment its siblings need the value. And the parallel-dispatch contract forbids a runner to touch the shared bookkeeping file at all — runners return status blocks and the orchestrator reconciles centrally — so task 01 could never write it and the others could never read it. Executed literally, N-1 runners HALT at the guard. Executed loosely, a runner improvises, and an unset variable degrades the gate **silently** rather than failing it, restoring the very unscoped behaviour the guard existed to prevent. **The failure is worse when the guard is skipped than when it fires.**

The same defect reaches the producing task's own first step whenever that step asserts a clean write-set. Run concurrently, it observes its siblings' in-flight edits and HALTs on correct work.

**The delivery mechanism is already specified — this section does not restate it.** [Part 1](agent-orchestration-delegated.md) §1.6 states that a shared pin is injected as a **literal** into every task file and every spawn prompt, and carries the WRONG/CORRECT spawn-prompt pair for it. What this section adds is **who resolves the value**: the orchestrator, before dispatch. §1.6 assumes that assignment rather than making it.

> [!checklist] Diagnostic questions for a declared-parallel layer
> Apply these by reading the layer's task files. The dependency field cannot answer them.
> - [ ] Does any task in this layer **produce** something another task in the same layer **consumes**? If yes they are not parallel — serialise them, or lift the shared step to the orchestrator.
> - [ ] Does the consumer read that value from a file the dispatch contract **forbids it to touch**? That is a guaranteed deadlock, not a race.
> - [ ] Does any task assert a property of the **whole working tree** — clean status, changed-file counts, "exactly N files changed"? Concurrent siblings violate such an assertion by construction, so it belongs pre-dispatch or post-batch, never inside a batch member. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17.3 carries the path-scoped form a per-task gate must use instead.

**Why the eligibility check missed it.** Every task in the measured batch honestly declared no dependency, because the *file write-sets* really were disjoint — and disjoint write-sets are the criterion the parallel-eligibility check applies. The dependency was on a **shared variable**, and no field in the task schema represents one. Disjoint outputs are **necessary but not sufficient** for parallel dispatch: a shared input that one member generates serialises the layer exactly as hard as a shared output file does. So apply the check by reading the layer, not by trusting the field.

[`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17 computes a layer's write-target intersection at scaffold time, and §17.2 covers the sibling case where the shared object is an **allocation** — a next-free number — rather than a path. Those are the plan-time gates. This section is the dispatch-time obligation, and it stands whether or not the plan carried one.

---

**Part of a three-file discipline:** [Part 1 — Foundations and Dispatch-Prompt Construction](agent-orchestration-delegated.md) (§1.1–§1.13) · [Part 2 — Dispatch Mechanics and Returns](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22)

*Originally extracted from [`agent-orchestration.md`](agent-orchestration.md) §11-§12 (DELEGATED Dispatch Discipline + Verify-Before-Acting on LSP Diagnostics); §1.19–§1.22 folded from `handlers/run.md`'s Delegated Execution Protocol (2026-08-10). That file now carries only a short §11 pointer stub back to Part 1. Split into three topical parts (2026-09-06) because the combined text exceeded the Read-tool page cap; section numbers were frozen across the split.*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
