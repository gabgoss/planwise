---
description: DELEGATED dispatch discipline, Part 2 of 3. This file holds §1.14–§1.22, dispatch mechanics and post-return handling, including gating a runner's sweep table on its control rows (§1.16.5) and the idle-while-waiting-on-a-background-command stall (§1.17.1, §1.17.3). Part 1 of 3 is agent-orchestration-delegated.md.
---

# DELEGATED Dispatch Discipline — Part 2: Dispatch Mechanics and Returns

**Purpose:** Part 2 of the DELEGATED dispatch discipline. It covers what the orchestrator does around a dispatch and after a task-runner returns: which review commands only the orchestrator may invoke, build ordering, recomputing a delegated verdict from primary evidence, classifying dispatch failure modes, verifying LSP diagnostics, model-tier and launch-mode gating, and the anti-patterns checklist.

Section numbers are continuous across all three parts. A section keeps its `§1.N` identifier wherever it lands, so an existing `§`-anchor still names exactly one section — only the filename that holds it changes.

| Part | File | Sections | Topic |
|---|---|---|---|
| 1 | [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) | §1.1–§1.13 | Declaration, foundations, and dispatch-prompt construction |
| 2 (this file) | `agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` | §1.14–§1.22 | Dispatch mechanics and post-return handling |
| 3 | [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) | §1.23–§1.32 | Cross-cutting dispatch-prompt and orchestrator discipline |

Read Part 1 first when declaring a DELEGATED session — it holds the mandatory triggers and the context boundary this file assumes. Read Part 3 alongside this one when constructing a spawn prompt.

## Table of Contents

- [1.14 Orchestrator-Only Review Commands](#114-orchestrator-only-review-commands)
- [1.15 Delegated Code Task-Runners Build LAST](#115-delegated-code-task-runners-build-last)
- [1.16 Recompute Delegated Verdicts from Primary Evidence — Both Directions](#116-recompute-delegated-verdicts-from-primary-evidence--both-directions)
- [1.17 Task-Runner Dispatch Failure Modes and Resume Protocol](#117-task-runner-dispatch-failure-modes-and-resume-protocol)
- [1.18 Verify-Before-Acting on LSP Diagnostics](#118-verify-before-acting-on-lsp-diagnostics)
- [1.19 Model-Floor Bridge (DELEGATED) — Temporary](#119-model-floor-bridge-delegated--temporary)
- [1.20 1M-Exception Dispatch (DELEGATED) — Token Saver](#120-1m-exception-dispatch-delegated--token-saver)
- [1.21 Background vs Foreground Gate](#121-background-vs-foreground-gate)
- [1.22 Delegated Mode Anti-Patterns Checklist](#122-delegated-mode-anti-patterns-checklist)

---

## 1.14 Orchestrator-Only Review Commands

Slash-commands that themselves spawn review agents (`/simplify`, `/code-review`, and similar multi-agent review skills) CANNOT run inside a task-runner subagent. Per Constraint 1 (`agent-orchestration.md` §10), the Agent tool is stripped from all non-main contexts at spawn time, so a subagent has no way to spawn the review agents the command depends on; the call resolves to "Unknown subcommand" or fails silently.

A DELEGATED task-runner does an INLINE self-review — it applies the review lenses itself, with no agent spawn. The orchestrator (running in the main session) invokes the real review command on the diff after the task-runner returns, before commit.

> [!constraint] Do Not Instruct a Task-Runner to Invoke Orchestrator-Only Commands
> WRONG — spawn prompt instructs the task-runner to run a slash-command that itself spawns review agents:
> ```
> Agent(
>   subagent_type: "planwise:task-runner",
>   prompt: "...implement X; build; then run /simplify"
> )
> # task-runner: "Unknown subcommand: simplify" — it cannot spawn the review agents.
> ```
> CORRECT — task-runner applies the review lenses inline; orchestrator runs the real review command on the diff after:
> ```
> Agent(
>   subagent_type: "planwise:task-runner",
>   prompt: "...implement X; apply the review lenses INLINE yourself — do NOT invoke /simplify or /code-review, you cannot spawn the review agents"
> )
> # orchestrator, after task-runner returns: Skill(code-review) (or /simplify) on the diff.
> ```

## 1.15 Delegated Code Task-Runners Build LAST

In a DELEGATED code task, the build/verification command is the FINAL step — after any inline self-review edits. This guarantees the reported build result reflects what is actually on disk. A task-runner that builds, then edits, then reports "build clean" has published a stale verification: the build predates the final code, and any post-build edit could silently invalidate the gate.

If the task-runner edits after building (whether by accident or because the spawn prompt allowed it), the orchestrator MUST re-run `{build-cmd}` on the final on-disk code before trusting the gate and before commit.

> [!constraint] Build/Verification Is the Final Step in a Delegated Code Task
> WRONG — build, then refactor, then report (verified build no longer matches on-disk code):
> ```
> 1. write code  2. run {build-cmd} (CLEAN)  3. apply self-review edits  4. report "CLEAN"
> # The reported result is from step 2; step 3's edits are unverified.
> ```
> CORRECT — refactor first, build last, so the reported result matches what is on disk:
> ```
> 1. write code  2. apply self-review edits (inline review lenses)  3. run {build-cmd} LAST  4. report
> # If the agent edits after building despite the prompt, the orchestrator re-runs {build-cmd} on the
> # final on-disk code before trusting the gate.
> ```

## 1.16 Recompute Delegated Verdicts from Primary Evidence — Both Directions

Any session that delegates structured classification — a verdict label, a severity tag, a readiness state — to a sub-agent MUST recompute that classification from the agent's reported raw evidence before consuming the label. Two failure modes bound the gap symmetrically: **under-classification** (the sub-agent softens the verdict against its own enumerated counts) and **over-classification** (the sub-agent manufactures a finding on incomplete cross-file evidence). Capability does not prevent either — a smaller-tier agent (e.g. Sonnet) systematically under-classifies, and a frontier-tier agent (e.g. Opus) can over-classify on cross-file control-flow claims; the rule applies to ALL agent tiers and must not be scoped to one model. The orchestrator, holding the full evidence set, is the only reliable recompute site.

### 1.16.1 Under-classification — recompute verdict from finding counts

In one observed 13-way parallel dispatch, 8 of 13 sub-agents wrote a final verdict line that did not match the classification rule applied to their own enumerated counts; every error softened severity (e.g. BROKEN=2 reported as `YELLOW` instead of `RED`). The aggregate as-reported severity mix understated the canonical mix enough to mis-classify release-blocking findings as negotiable. The orchestrator must recompute the label from the counts, never read it off the agent's summary line.

> [!constraint] Recompute the Verdict from the Reported Counts
> WRONG — orchestrator trusts the verdict line:
> ```
> verdict = read_verdict_line(findings_file)  # may be wrong
> roll_up_to_release_blocker_table(verdict)
> ```
> CORRECT — orchestrator recomputes from counts:
> ```
> counts = read_finding_counts(findings_file)
> verdict = "RED" if counts.broken + counts.contradiction > 0 \
>      else "YELLOW" if counts.drift + counts.missing > 0 \
>      else "GREEN"
> roll_up_to_release_blocker_table(verdict)
> reported = read_verdict_line(findings_file)
> if reported != verdict:
>     log_meta_finding(f"sub-agent verdict mis-classification: reported={reported}, canonical={verdict}")
> ```

Scope note: this applies to any structured-classification dispatch — GREEN/YELLOW/RED verdicts, MUST_FIX/SHOULD_FIX/DEFER labels, BLOCKER/ERROR tags, or readiness states.

### 1.16.2 Over-classification — cross-file control-flow claims require full call-path trace

The mirror failure: a capable task-runner reviewing a cumulative diff returned READY-WITH-NOTES on the strength of a new finding — "`args.config` is never referenced in the script, therefore `--config` is a no-op." The orchestrator read the code and found the claim false: the script calls a loader, which calls a helper in a sibling module that runs its own `argparse.parse_known_args()` over `sys.argv` and returns the `--config` value. The flag is consumed end-to-end through a second file. Capability did not prevent the error — the agent over-classified.

> [!constraint] Trace the Full Call Path Before Accepting a Cross-File Non-Use Claim
> WRONG — accept the agent's new-issue finding because local evidence looks conclusive:
> ```
> # Agent: "args.config never referenced in {script}.py → --{flag} is a no-op → READY-WITH-NOTES"
> # Orchestrator: records READY-WITH-NOTES, files the seed.   # propagates a false positive
> ```
> CORRECT — trace the full call path before accepting a cross-file non-use claim:
> ```
> # Agent: "args.config never referenced → --{flag} inert"
> # Orchestrator: reads {load_fn}() → finds {helper}() re-parses {argv-source}
> #               → confirms --{flag} IS consumed end-to-end → withdraws finding → verdict READY
> ```

The per-arm form of this failure is §1.16.4.

A claim of the form "symbol X is declared but never used in this file, therefore feature Y is broken" is only safe to accept after tracing every consumer of X — including consumers in other files that may read the same input independently (e.g. a second argparse over `sys.argv`). Single-file grep proves local non-use, not global inertness.

Highest false-positive risk patterns — any of these warrants an independent code-read before accepting the verdict: "declared-but-unused," "never called," "dead code," "flag has no effect," "interface mismatch," "unreferenced in this file."

Cost note: a false positive in a release-signoff verdict either blocks a shippable tag or spawns phantom backlog work; the verification is a few targeted reads of the disputed call path — NOT a full re-review.

#### Reviewer Check 067 — Orchestration Delegated Verdict Recompute Gate

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** When a DELEGATED session's Orchestration file synthesizes sub-agent verdicts (GREEN/YELLOW/RED, MUST_FIX/SHOULD_FIX/DEFER, READY/READY-WITH-NOTES, or equivalent), the synthesis step or rollup table MUST declare a recompute-from-counts gate — i.e. explicitly state that the orchestrator will recompute each verdict from the agent's reported finding counts rather than consuming the verdict label verbatim. The gate covers both directions: under-classification (the agent softens the verdict against its own counts) and over-classification (a cross-file control-flow claim accepted without tracing the full consumer call path).
- **Detection:** In DELEGATED Orchestration files, grep the synthesis steps for `recompute|canonical.*verdict|verdict.*count|count.*verdict`. If absent AND the session dispatches sub-agents that produce verdict labels → ERROR.
- **Finding template:**
```
[ERROR] Orchestration delegated verdict recompute gate missing
File: {Orchestration file path} | Location: Synthesis / rollup section
Issue: DELEGATED session synthesizes sub-agent verdicts but lacks recompute-from-counts gate
Fix: Add recompute gate per references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md §1.16 | Confidence: MEDIUM
```

### 1.16.3 A runner's "dormant until a follow-up wires it" note is a BLOCKING classification

A third recompute, in the same spirit as §1.16.1: read the runner's evidence for a **production call site**, not its status label. A deliverable that adds a function, an optional parameter, a CLI flag, a config key or a guarded branch is terminal only when the runner quotes where production invokes it with the activating argument. A return that says the behaviour is complete but *"dormant until a follow-up task passes the argument / registers the flag"* is recomputed to **PARTIAL or BLOCKED — never COMPLETE** — and the wiring is routed inside the session, because the site and the value it needs are usually already in scope and the fix is one to four lines. Once the session closes, a deferred activation is indistinguishable from a dropped one: the handoff has no owner and no gate. The gate, its call-site search and the closing-sweep ledger requirement: [verify-caller-before-complete.md](verify-caller-before-complete.md).

### 1.16.4 A runner's comparative claim about arms it did not grade is recomputed

A per-arm runner's evidence ends at its own arm's archive. A sentence in its status block that compares its arm to others is a claim about evidence it did not read, offered in the voice of evidence it did. §1.16.2 names over-classification for cross-file control-flow claims. The same shape appears whenever a per-arm runner explains its result by reference to sibling arms.

> [!constraint] Recompute every comparative clause from evidence the orchestrator holds
> - **A sentence that names another arm, task, or session is a comparative claim.** The orchestrator recomputes it before it propagates. The runner's own arm is its evidence. Everything else is inference.
> - **Softening words are the trigger.** "Fixture-wide", "pre-existing", "same as `<arm>`", and "not caused by" each move a finding from the arm's column to nobody's. Use `Grep` for them in a grade return before accepting it.
> - **The orchestrator's own stdout is evidence.** It ran the sibling grade, and the verdict lines sit in its window. Recomputing a comparative claim usually costs one `Grep` or one re-read of a line it already holds. That is cheaper than the downstream correction across three files.
>
> WRONG — accept the comparative clause because the local finding is correct:
> ```
> runner: "P3 FAIL (3 outputs checksum=missing) — identical on <arm-a>/<arm-b>, fixture-wide"
> orchestrator: P3 FAIL is real -> accept the sentence -> write-up Notes: "fixture-wide"
> ```
> CORRECT — split the sentence into the graded claim and the comparative claim, and recompute the second from evidence the orchestrator holds:
> ```
> graded claim:      P3 FAIL, 3 outputs without checksum   <- the runner's archive; accept
> comparative claim: "identical on <arm-b>"                <- not the runner's archive
> orchestrator: Grep checksum <arm-b>/grade.json -> 0 hits; its P3 read "problems=none"
> -> the comparative claim is false -> corrective resume of the same agent
> ```

Worked figures: three of ten outputs lacked a checksum line on the graded arm. The sibling arm's grade read `10 task(s) checked; problems=none` and held no checksum text. The other failures the runner may have seen on a third arm were "file missing" after a fixture reset, a different cause. The softening clause would have reached three downstream files.

**Applies to** multi-arm measurement sessions where each runner grades one arm and the write-up compares them (a lab, a census, an A/B sweep). It also applies to DELEGATED acceptance generally.

### 1.16.5 A sweep table is gated on its control rows and its own summary before a downstream task consumes it

A task that sweeps patterns and classes each hit as `update` or `leave` returns a judgment table, and a clean status block is not evidence that the table is right. Mechanical steps (prerequisite searches, git bases, collect counts) and judgment steps (classifying each hit) fail differently. The mechanical steps can be fully correct while the judgment table is wrong in several plausible ways. This holds for any runner tier that sweeps and classifies.

> [!constraint] Gate the table on disk before the next task reads it
> - **Gate any sweep table on its control rows before a downstream task consumes it.** Pick at least two rows whose answer the task file already states. Run `Grep` on the file behind each control and compare it with the claimed value. A clean status block is not evidence.
> - **Reject a table whose summary disagrees with its rows.** A count that does not match the rows means at least one of them is wrong.
> - **Keep the verified mechanical steps when you reject the judgment steps.** Re-run only the rejected steps, and record the rejection in Recovery.
> - **Check a classification against the next task's own text.** A note marked `leave` that the next task's step names for editing is a contradiction. Fix the table before dispatching the next task.
>
> WRONG — accept a sweep table because the status block is clean:
> ```
> runner -> COMPLETE, "<SET> already includes both style rules"
> orchestrator -> dispatch the next task from that table
> ```
> CORRECT — gate the table on disk first:
> ```
> runner -> COMPLETE, control rows: <manifest>:572 update, <fixtures>:56 update
> orchestrator -> Grep <fixtures> 'rules/<dir>/' -> 4 members -> the claim "6" is false -> reject the table
>              -> re-run only the judgment steps, keep the verified mechanical steps
>              -> then dispatch the next task
> ```

Measured case. A sweep reported a write-set constant at six paths. On disk it held four, and the task file named that constant as the known `update` case. The same table marked a manifest note `leave` although the next task's own step named the note for editing. It marked a README line `leave` and then counted seven README update rows in its summary. It reported a table at six rules where a locked decision keeps it at four. It closed an out-of-repo enumerator as "no action" although the orchestration routed that decision to the user. A re-run of the judgment steps on a stronger tier produced a table that matched the files. The same session's cheap-tier cost-measurement task returned correct numbers, but its reuse sentences named a second project and backlog ids that a shipped README must not carry.

**Applies to** surface sweeps, enumeration sweeps, and any task that classes each hit as stale or current.

## 1.17 Task-Runner Dispatch Failure Modes and Resume Protocol

A dispatched task-runner has four post-return states — three failure modes and one real completion. Before dispatching the next task — or before treating a "completed" notification as done — classify the return by the final-message voice and the working-tree state; and when the return *reads* as complete, gate acceptance on **on-disk deliverable evidence** before believing it — a stall can masquerade as completion (§1.17.4). For every failure state of the unit of work in hand the corrective is the same: **resume the SAME agent** (its context already holds the full task), never dispatch a fresh runner for that same unit of work. A fresh runner re-reads everything and can race or duplicate the first one's partial work. A new round of work is a different case and gets a fresh runner (§1.17.7).

### 1.17.1 Diagnosis table

Classify every returned runner against this table before acting on its result:

| Signal | Diagnosis | Action |
|--------|-----------|--------|
| Fast return (seconds, a handful of tool calls), dispatch-voice reply ("I've dispatched the task-runner… I'll report back"), clean tree (zero diff in the edit target, Recovery untouched) | Self-delegation — the runner spawned a nested duplicate instead of executing | Resume the same agent with the execute-yourself directive (§1.17.2) |
| Mid-work narration ending in a colon or next-step phrase ("Now let's rewrite each. First, `test_conflict…`:"), dirty tree with genuine partial edits on disk | Message-boundary stall — the runner executed part-way, then ended its message at a narration checkpoint | Resume the SAME agent with a continuation message (§1.17.3); its context holds the full task state |
| Idle, final message says the runner is "waiting on" a background job or command, dirty tree | Message-boundary stall — the job's completion reached the runner's harness and never woke the runner | Resume the SAME agent (§1.17.3), instruct a foreground re-run with a long timeout |
| `completed` return whose final message ends mid-action ("Now let me…", "Next I'll…") or omits required report fields — reads as done, but deliverables are not yet on disk | Mid-action stall masquerading as completion — the `completed` status is not a deliverable check | Run the on-disk acceptance gate, then resume the SAME agent to finish (§1.17.4) |
| Structured completion report (status + verification results) whose deliverables verify on disk | Real completion | Reconcile normally |

The three failure modes are genuinely distinct: self-delegation is a **clean** tree + **dispatch** voice (the runner never executed); a message-boundary stall is a **dirty** tree + **executor** voice that ends visibly mid-work (the runner executed part-way); a mid-action stall masquerading as completion **reads** as done — a structured-looking report or a clean final line — yet its deliverables are not on disk (§1.17.4). The shared corrective is "resume the same agent," but the resume *message* — and, for the masquerade case, the on-disk check that exposes it — differs; see below.

### 1.17.2 Self-delegation resume

A task-runner whose spawn prompt merely says "Execute the following task:" can pattern-match itself into the ORCHESTRATOR role (the task file and handler prose it reads are full of dispatch language) and delegate the work onward instead of executing. On the self-delegation signature, do NOT re-dispatch a fresh runner — the first may have left a live nested duplicate that will race it. Resume the same agent with this directive (identical to the spawn-prompt role pin the dispatch loop opens with):

> Execute the following task YOURSELF, directly, with your own tool calls. Do NOT spawn, dispatch, or delegate to any other agent (no Agent tool calls) — you ARE the task-runner.

Then verify single-application afterward (`git status` / diff on the edit target; Recovery advanced).

**Secondary consequence to reconcile:** an orphaned nested duplicate can finish AFTER the corrected primary, so "file modified since read" Edit rejections or unexplained concurrent-editor observations in Recovery may be the duplicate — reconcile by verifying the working tree holds a single spec-exact application, rather than assuming an external session raced.

### 1.17.3 Message-boundary-stall resume

On a message-boundary stall the runner's partial edits are real and on disk. Do NOT treat the stall notification as completion (that silently loses the unfinished tail), and do NOT dispatch a fresh runner for the same unit of work (it re-reads everything and may re-edit or conflict with the partial work). Send the SAME agent a continuation message that:

1. quotes the runner's own last line so it anchors where it stopped;
2. forbids starting over or re-editing completed work;
3. enumerates ONLY the remaining work items; and
4. restates the required final-report format.

An idle notice that says the runner is "waiting on a background job" is a message-boundary stall, not progress. The job's completion reached the runner's harness and never woke the runner. Resume the SAME agent with a continuation that tells it to re-run the command in the foreground with a long timeout and lists only the remaining steps. Do not wait for the job yourself and do not dispatch a fresh runner. Add "idle while waiting on a background command" to the stall signals you check on every return.

> [!constraint] Classify "waiting on a background command" as a stall
> WRONG — read the idle notice as live work and wait:
> ```
> runner: "The full suite is still running, so I'm waiting on it. The sweep and the
>          summary numbers depend on its result."   -> orchestrator waits -> nothing wakes the runner
> ```
> CORRECT — classify as a stall and resume the same runner:
> ```
> dirty tree + executor voice + "waiting on a background command" -> message-boundary stall
> resume: "Re-run <suite> in the FOREGROUND with a timeout up to 600000 ms (about 4 minutes).
>          Remaining steps: the sweep, the final summary numbers, the Recovery row."
> ```
> Prevent it in the spawn prompt: [Part 3](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.27.1 pins foreground execution for any long suite.

For long remediation prompts, instruct up front: "work through to the end without pausing for narration checkpoints."

**Residual risk to reconcile:** a stalled runner may have half-updated Recovery (e.g. the header + step table but not Files Modified / Change Log). The orchestrator owns reconciling that gap from verified facts — check Recovery section-by-section after any stalled-then-resumed task. Runs approaching the ~50-tool-use regime are the stall-prone range; budget 1–2 resume round-trips into session-time estimates.

### 1.17.4 Acceptance gate: a `completed` status is not a deliverable check

A runner can return with harness `status: completed` and a final message that reads clean, yet have stopped **mid-action** — before writing Recovery and before emitting its completion report. The harness `completed` status only means the agent stopped with no live children; it is NOT a check that the task's deliverables were produced. Accepting such a return at face value ships whatever the runner had not yet done — an unwritten Recovery step a later compaction would lose, or residual defects it had not yet addressed. Before marking a delegated task done, gate acceptance on **on-disk evidence**, not the agent's final message — especially when that message ends mid-action ("Now let me…", "Next I'll…") or omits the required report fields.

This is distinct from the two voice+tree failure modes above: those announce themselves (dispatch voice, or narration ending mid-work). A mid-action stall *reads* as completion, so only an on-disk check exposes it. The corrective is still to resume the SAME agent — but acceptance is gated on the check first.

> [!constraint] Gate acceptance on on-disk evidence, not the final message
> WRONG — the runner returns `status=completed` with the last line "Now let me update the Recovery file"; the orchestrator marks the task COMPLETE and dispatches the next. The Recovery step is never written, and the stale references the runner had not yet cleaned ship:
> ```
> runner → status=completed, final line: "Now let me update the Recovery file"
> orchestrator → mark COMPLETE, dispatch next task
> [Recovery step unwritten; residual stale references remain in the edit target.]
> ```
> CORRECT — the final line ends mid-action / report fields are missing, so the orchestrator does NOT accept on the status alone. It greps the edit target for the symbol that was supposed to change and reads Recovery, detects the unwritten step + residual references, and resumes the SAME agent (context intact) to finish — then re-verifies on disk before accepting:
> ```
> runner → status=completed, final line ends mid-action / report fields missing
> orchestrator → grep edit target for the changed symbol + read Recovery
>              → unwritten step + residual refs detected
>              → resume SAME agent: "you stopped before finishing — do X, write
>                 Recovery, return the full report"
> agent (context intact) → completes
> orchestrator → re-verify on disk, THEN accept
> ```

**Cheap, high-signal acceptance checks for a code-edit task** (run before accepting a `completed` return; each is sub-second):

- `grep` the target for the symbol that was supposed to change (added, removed, or renamed) — confirm the edit is actually present, and that residual references that were supposed to be swept are gone.
- `git status --short` — confirm the expected file set is dirty and nothing unexpected changed.
- A collection / parse check where applicable (the produced file parses; the test file collects).
- Confirm the Recovery step row for the task flipped to its completed state.

On any miss, resume the SAME agent to finish (never re-dispatch a fresh one), then re-run the checks before accepting.

### 1.17.5 Name a write-by turn in the spawn prompt, and size the brief by its proof count

The harness caps a runner by turns, not by tokens. The cap is invisible to the runner until it fires. Writing is the last step in every brief, so a runner that reads until it is cut off leaves nothing on disk. The stall is a limit-and-brief problem, not a model-tier problem.

> [!constraint] Give the runner the shape of the run, and count the proofs the brief demands
> - **Every transcript-reading dispatch names a write-by turn.** The number is the harness limit minus the cost of the write phase (for example 50 minus about 15). It goes in the spawn prompt, not the task file, because the limit belongs to the harness the orchestrator chose.
> - **`unmeasured (reason)` is a licensed value.** A brief that only lists what must be measured leaves the runner no honest way to stop. Naming the fallback turns a stall into a gap the orchestrator can see and route.
> - **Count the required per-unit proofs at scaffold time.** A brief that demands N per-unit proofs spends at least N x (mutate + run + restore + verify) turns before any authoring. Above about 5 proofs, either split the proofs into their own task or require one script that runs every mutation in a single call. Have the runner write that script itself.
> - **Order the spawn prompt for the cap.** Write the output file and the Recovery row as soon as the verification data exists, before any polish. Batch independent calls. Write pre-step evidence to disk before any run-once step.
> - **Record the measured cost against the estimate.** A figure of 189K against 46.7K is evidence for the next estimate, not noise.

WRONG — a brief with steps and headings but no turn shape:

```
spawn prompt: task file + archive + 7 headings + status block
runner: Grep, Read(offset), Grep, Read ... x63 -> turn limit -> nothing on disk
```

CORRECT — the spawn prompt states the shape of the run:

```
TURN BUDGET: <= 25 turns of evidence (Grep first, paged Read second),
WRITE the output row in one Write call by turn 30, then the sheet, then Recovery.
A figure not found in budget is written `unmeasured (reason)` — never leave
the file unwritten to keep hunting.
```

**Worked figures.** A stalled runner used 63 tool uses and about 130K tokens. It left only an empty placeholder in `Outputs/`. The orchestrator resumed it with "write the row now, in one call, from the figures you hold; a figure you cannot find is `unmeasured (reason)`; do not re-read". The runner then wrote a 96-line file in five tool uses. A proof-heavy runner used 89 tool uses and 189,468 tokens against a 46.7K estimate. It repeated the edit-run-mutate-run-restore-verify loop 9 times.

**Applies to** grade, audit, census, and review dispatches whose Required Context is a transcript, a log, or any file read by paging. It also applies to any DELEGATED brief that pairs authoring with an iterative verify loop, such as test authoring with per-class mutation proofs.

### 1.17.6 Measure the landed state before resuming a capped runner, or accept it from disk

When a dispatched runner stops mid-task, establish the landed state before the next move. The orchestrator reads the tree read-only: which files changed, whether the changed set equals the intended set, and whether the write's invariants hold. Then it either resumes the same runner with that state or accepts the task on it.

> [!constraint] Two continuations are forbidden
> - **Resume blind.** The runner re-derives its position from its transcript and may re-enter a run-once step. A guard may refuse the second run, but only if one exists.
> - **Revert and restart.** A task file's recovery path that discards a directory throws away correct work and any concurrent session's uncommitted file.

The resume message states the measured facts, says "the write ran; do NOT run it again", and lists only the remaining steps.

WRONG — resume on the notification alone:

```text
Runner stopped at turn limit -> SendMessage "continue the task"
# The runner re-derives its position from its transcript and may re-enter the write step.
```

CORRECT — measure the landed state, then resume with it:

```text
git status --porcelain -- <write-set>           -> 46 files modified
changed set == files with the missing rulings   -> 46 == 46
one heading per file; numstat deletions         -> all 1; 0
SendMessage "the write ran; do NOT run it again; continue from POST measurements"
```

**Accept without a resume.** When every deliverable is on disk and only the status block is missing, do not resume. Check the edit target, the output headings, the Recovery row, and one re-run of the deliverable's own test. Resume only if something is missing. A window near 200K has no headroom for a resume, and a resume would spend a round trip only to produce a report.

**Budget a run-once step at authoring time.** A task with an irreversible or run-once step writes its PRE evidence to disk before the step. It also keeps tool calls per phase low (one measurement script instead of ten shell probes), so the cap falls on either side of the write and not across it.

The same rule gave a different action in three real recurrences:

| Landed state | Action |
|---|---|
| Edits on disk, net growth over the limit (97 lines against a limit under 80), evidence note and Recovery update missing | Resume the same runner with the measured facts and only the remaining steps: trim, dry-run pair, verify, note, Recovery |
| Every deliverable on disk, Recovery row COMPLETE, only the status block missing | Do not resume. Recompute the gates and accept (22 passed, lint clean, 9 of 9 functions present, 252 lines under a 260 limit) |
| A non-turn stop (an API DNS failure, or a 600-second stream watchdog before anything was written) | Check the landed state, then resume the same agent from its last line |

**Applies to** any delegated task with a run-once side effect (an append, a migration, a cutover, a commit, a publish), and any runner whose notification reports a harness stop instead of a status block.

### 1.17.7 A new round of work gets a fresh runner; resume only for the same unit of work

"Resume the same agent" is right for one task that stalled or needs one corrective. It is wrong for a new round of work. A resumed runner pays for every earlier round's context on every later turn. The cost grows with each round, and the old context adds no value to the new round.

> [!constraint] Fresh runner per round, resume per unit of work
> - **A new round gets a fresh runner with a short brief.** The brief names the findings file, the ledgers of earlier rounds, the pinned hashes of the files in scope, and a frozen-snapshot self-check. The on-disk artifacts carry what the new runner needs. The old transcript does not.
> - **Resume only for the same unit of work.** That means a stall, a missing status block, or a single corrective instruction on the deliverable the runner just produced.
> - **Stop an over-grown runner.** If a runner is mid-edit and over-grown, stop it. Take an inventory of the tree: what is edited, what is untouched, and the current lint errors. Then dispatch a fresh runner with the partial work marked UNVERIFIED and a frozen-snapshot self-check.

WRONG — one runner carried across rounds:

```
<task> runner -> resume for fix loop -> resume for caveats -> resume for review round
# ~750K tokens by round 4; stopped mid-edit
```

CORRECT — one runner per round, with the ledger as the handoff:

```
<task> runner (ledger) -> fresh fix-loop runner (reads ledger) -> fresh review-round runner (reads ledgers)
# a single corrective on a round's own deliverable -> resume that round's runner
```

**Applies to** DELEGATED sessions where review findings, dry-run failures, or gate caveats reopen work after a task was accepted. It also applies at any moment the orchestrator chooses between resuming a runner and dispatching a new one.

## 1.18 Verify-Before-Acting on LSP Diagnostics

> [!practice] LSP Diagnostic Verification
> LSP diagnostics ({type-checker}/`{linter}`/rust-analyzer/gopls) may go stale when the underlying source file is edited mid-session. Before acting on a diagnostic (e.g., adding an import, fixing a type), verify the diagnostic is still live.

### Stale vs Live Diagnostic Decision Matrix

| Signal | Likely Stale | Likely Live |
|--------|--------------|-------------|
| Diagnostic line number > file's actual line count | Yes | — |
| Diagnostic mentions identifier not present in file | Yes | — |
| Diagnostic timestamp predates last edit | Yes | — |
| Diagnostic re-fired after LSP refresh | — | Yes |
| Same diagnostic appears across multiple unrelated files | Yes (index drift) | — |
| Diagnostic references a type that was recently renamed | Yes | — |

**When a diagnostic is likely stale:**
1. Trigger an LSP refresh (close and reopen the file, or run `{lint-cmd}` from CLI)
2. If diagnostic is gone after refresh → it was stale; do NOT act on it
3. If diagnostic persists after refresh → it is live; act on it

**When to act without refreshing:**
- Diagnostic is confirmed live (matches current file content at the reported line)
- Diagnostic was emitted by a CLI tool run this session (not cached from prior session)

## 1.19 Model-Floor Bridge (DELEGATED) — Temporary

Applies to every DELEGATED task-runner launch, sequential or parallel.

> [!constraint] Raise a 200K-window model to 1M when the plan-path rule surface is large
> This guard governs EVERY DELEGATED dispatch — both sequential and parallel task-runner launches (see `handlers/run.md` § DELEGATED Mode; §1.13 and §1.17 above for dispatch-return handling). It is a **temporary bridge**, not a permanent override (see self-deactivation below). It never changes the model for a healthy (small) rule surface.
>
> **Before dispatching a DELEGATED task whose `Agent:` maps to a 200K-window model (Sonnet or Haiku):**
> 1. **Measure the plan-path rule surface.** Reuse the engine's linter: run `python {plugin_root}/scripts/init_project.py --doctor --project-root {project_root}` and sum the `approx_tokens` of the flagged (over-scoped) rules — those `.claude/rules/**` whose `paths:` target `planwise/Plans/**` (or sibling plan/backlog/lessons paths). If `--doctor` is unavailable, fall back to summing those rule files' byte sizes ÷ the conservative bytes-per-token ratio (2.6) — `measure_files.py` does this per file.
> 2. **Project the subagent's worst-case load:** `flagged-rule tokens + ~54K fixed overhead`. If that **approaches the 200K window** — rule of thumb: flagged surface ≳ ~110K, leaving < ~35K of working headroom — the declared 200K-window model will overflow ("Prompt is too long") the instant it reads a plan brief that triggers those path rules.
> 3. **Raise and log.** In that case, raise the dispatch `model` to the **1M tier** (Opus, or a 1M-window Sonnet where available) for THIS dispatch only, and emit a one-line log — never silent:
>    ```
>    MODEL FLOOR: raised {task-id} {declared}→1M (plan-path rule surface ~{N}K exceeds safe {declared} budget)
>    ```
> 4. **Otherwise dispatch verbatim.** If the threshold is NOT tripped, pass the declared `Agent:` model through unchanged — the floor is inert for a small surface.

> [!practice] Self-Deactivating Bridge — Not Permanent
> This floor exists only to keep declared-Sonnet/Haiku runners alive while a project still carries a large author-time rule surface scoped to plan paths. Once the project is de-scoped — plugin author-time rules handler-loaded from `references/` (not installed), and any project-local domain rules re-scoped to code paths per `/planwise doctor` — the flagged surface shrinks toward ~0, step 2's threshold is never tripped, and declared-Sonnet tasks dispatch unchanged. When `--doctor` reports no over-scoped rules for a project, this bridge is already inert; it can be retired entirely once no supported project trips it.

## 1.20 1M-Exception Dispatch (DELEGATED) — Token Saver

Applies to every DELEGATED task-runner launch, sequential or parallel; uses the same override mechanism as §1.19 above.

> [!constraint] Raise a `1M-exception`-flagged task to Opus/1M — a COST remedy ONLY
> This guard governs EVERY DELEGATED dispatch — both sequential and parallel task-runner launches (see `handlers/run.md` § DELEGATED Mode) — exactly like the Model-Floor Bridge (§1.19 above) and using the **same override mechanism** — it raises the dispatch `model`, it does NOT rewrite the task file. It is triggered by the task's own flag, not by the plan-path rule surface.
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
> CORRECT — the Read tool's **25K-token page cap** and **256 KiB byte refusal** apply on EVERY model; the Claude 5 tokenizer (Opus, Sonnet and Fable alike) is ~1.31–1.38× heavier than Haiku 4.5's, so it trips the page cap on *fewer bytes* (~65 KB of dense markdown vs ~87 KB for Haiku). The 1M-exception covers **only** a `cost`-reason Critical (a context-window/carrying-cost overflow). It does NOT cover a `read`-reason Critical — that file must be **paged** by the runner (`offset`/`limit`/Grep) even on Opus, or refactored:
> ```
> read-reason Critical context file  → log `paged-read required` (NOT 1M-exception)  → runner pages it (offset/limit/Grep) on its declared model
> ```
> The warning engine (Token Saver) does NOT set `1M-exception` for a `read`-reason Critical, and `run.md` MUST NOT infer it. Log such a task with a `paged-read required` note and dispatch it on its declared model — keep the two reasons distinct in the dispatch log: `1M-exception` for `cost`-Critical, `paged-read required` for `read`-Critical.

## 1.21 Background vs Foreground Gate

Governs whether a DELEGATED task-runner launches in foreground or background.

> [!constraint] Write-Producing Agents MUST Run in Foreground
> Background subagents auto-deny any permission not explicitly pre-approved at launch — including Write, Edit, and Bash. The `bypassPermissions` mode does NOT override this gate. Tool calls fail silently: the agent continues executing but produces no output files.
>
> WRONG: Launch task-runner in background when it writes output files:
> ```
> Agent(
>   subagent_type: "planwise:task-runner",
>   run_in_background: true,
>   prompt: "Execute task 01..."
> )
> ```
> CORRECT: Launch task-runner in foreground (default) — background is only safe for read-only agents:
> ```
> Agent(
>   subagent_type: "planwise:task-runner",
>   prompt: "Execute task 01..."
> )
> ```

| Task Produces | Launch Mode | Rationale |
|---------------|-------------|-----------|
| File output (Write, Edit) | **Foreground** | Permissions resolved interactively |
| Shell commands (Bash) | **Foreground** | Bash permission needs interactive approval |
| Read-only research (Explore) | Background OK | No write permissions needed |

A runner that backgrounds its own long command stalls too; see the foreground-suite subsection in Part 3 (§1.27.1).

## 1.22 Delegated Mode Anti-Patterns Checklist

Quick-reference checklist for common DELEGATED-mode mistakes; several map to fuller rules elsewhere in this file.

> [!antipattern] Delegated Mode Anti-Patterns
> - **Orchestrator reads Consolidated Context:** Blows context budget; task-runners duplicate the read (full rule: §1.3)
> - **Skip Recovery between tasks (sequential dispatch):** Context compaction loses progress
> - **Skip Recovery reconciliation after a parallel batch:** Context compaction loses the entire batch; status blocks were returned but never persisted (full rule: §1.13)
> - **Combine tasks in one task-runner:** Defeats fresh-context purpose
> - **Launch sequential Task N+1 before Recovery updated:** Compaction loses Task N completion
> - **Allow parallel task-runners to write Recovery:** Last-write-wins races silently drop completion rows (full rule: §1.13)
> - **Orchestrator produces task outputs:** Context accumulates; no fresh budget benefit
> - **Infer DELEGATED at runtime:** Planning should have set this; warn user and re-plan if needed (full rule: §1.1)

---

**Part of a three-file discipline:** [Part 1 — Foundations and Dispatch-Prompt Construction](agent-orchestration-delegated.md) (§1.1–§1.13) · [Part 3 — Cross-Cutting Dispatch Discipline](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) (§1.23–§1.32)

*Originally extracted from [`agent-orchestration.md`](agent-orchestration.md) §11-§12; §1.19–§1.22 folded from `handlers/run.md`'s Delegated Execution Protocol (2026-08-10). Split into three topical parts (2026-09-06) because the combined text exceeded the Read-tool page cap; section numbers were frozen across the split.*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
