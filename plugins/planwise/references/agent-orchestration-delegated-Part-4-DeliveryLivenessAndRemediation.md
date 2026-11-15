---
description: DELEGATED dispatch discipline, Part 4 of 4. This file holds §1.29–§1.32, delivery, liveness and remediation, including naming a status block's delivery channel (§1.29.1), establishing that a silent runner is dead before dispatching a replacement (§1.30), pinning a target over a stored corpus with a census, a fallback ceiling and a NONE sentinel (§1.31.1), and deriving a remediation brief's write set from where each fix lands (§1.32). Part 1 of 4 is agent-orchestration-delegated.md.
consult-when: Writing a DELEGATED spawn prompt's delivery channel or lead-resolved conditions, establishing that a silent runner is dead before dispatching a replacement, resolving a precondition a whole dispatch layer shares, pinning a paid or irreversible step's target over a stored corpus with a census, a fallback ceiling and a NONE sentinel, and deriving a remediation brief's write set from where each fix lands
---

# DELEGATED Dispatch Discipline — Part 4: Delivery, Liveness and Remediation

**Purpose:** Part 4 of the DELEGATED dispatch discipline. It covers what a spawn prompt must name in both directions, how to establish that a silent runner is dead before dispatching a replacement, who resolves a precondition a whole dispatch layer shares, and how to derive a remediation brief's write set from where each fix lands.

Section numbers are continuous across all four parts. Each `§1.N` anchor names exactly one section wherever it lands. Only the filename that holds it changes.

This file holds §1.29–§1.32. The part table in [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) names the file that holds every other section.

## Table of Contents

- [1.29 A Subagent's World Is Its Definition Plus Its Prompt](#129-a-subagents-world-is-its-definition-plus-its-prompt)
- [1.30 Liveness — Establish Death Before Dispatching a Replacement](#130-liveness--establish-death-before-dispatching-a-replacement)
- [1.31 A Shared Precondition Belongs to the Orchestrator](#131-a-shared-precondition-belongs-to-the-orchestrator)
- [1.32 Derive a Remediation Brief's Write Set From Where Each Fix Lands](#132-derive-a-remediation-briefs-write-set-from-where-each-fix-lands)

---

## 1.29 A Subagent's World Is Its Definition Plus Its Prompt

A spawned agent knows two things: its own agent definition, and what its spawn prompt literally names. It inherits nothing else, neither the conditional reads the orchestrator performed nor a convention the protocol merely assumes.

Both omissions are silent. An instruction the prompt omits never arrives, and telemetry the prompt never routed never returns. §1.29.1 binds the inbound direction, §1.29.2 the outbound one, and §1.29.3 states the shared rule.

### 1.29.1 Name the delivery channel, not just the payload format

A spawn prompt that specifies a status block's *format* has not specified how the block reaches the orchestrator. §1.28 bounds what the block carries; this section binds how it arrives. When runners are spawned with a name, a plain-text final message does not reach the orchestrator inside its turn. It arrives only after the turn ends, in the result field of an idle notification (measured 2026-10-12 on Claude Code 2.1.296, one sample). A protocol that says "RETURN a status block" then means "write a status block nobody receives."

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
> Deliver your status block by calling the SendMessage tool with to="main".
> Plain-text output does NOT reach the orchestrator.
> TASK_STATUS:   COMPLETE | BLOCKED | PARTIAL
> TASK_ID:       {task-id}
> ...
> ```

The spawn-prompt hook in `hooks/agent-guard.ts` checks a composed task-runner prompt for this delivery clause and reports a prompt that lacks it.

Two practices follow.

**Acceptance may proceed on disk evidence while telemetry is recovered.** The on-disk deliverable gate confirms COMPLETE independently of the status block; §1.17.4 specifies that gate and this section does not restate it. A silent runner whose deliverables verify on disk is accepted from disk and not resumed, and its narrative fields are recovered read-only from its transcript (Part-2 § "1.17.1 Diagnosis table"). The recovered block then supplies `KEY_FINDINGS` for Recovery reconciliation.

**Name the tool and the recipient when re-requesting a missing block.** A generic re-request — "reply with your status block" — reproduces the original failure, because it leaves the channel unnamed a second time. In one measured 7-runner parallel dispatch every runner had executed correctly and written its deliverables, yet the orchestrator received only idle notifications. All 7 blocks arrived only after an explicit instruction to call the SendMessage tool with `to="team-lead"`. The generic re-request cost one wasted round-trip per runner.

The same rule applies when you resume a runner with a review's result: the findings travel in the message, and an output-file path is only a supplement. See "A Findings Relay Carries the Findings, Not Only the Path of the File That Holds Them" in [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md).

### 1.29.2 Push a lead-resolved condition into the spawn prompt

A handler that enumerates conditional references for the orchestrator, then delegates the checking to spawned agents, has split the condition from the check. The orchestrator resolves the condition and never runs the check. The spawned agent runs the check and never sees the condition. The checklist row is then present, indexed, and never evaluated.

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
>  ships in four parts. Read each one and verify every Orchestration file
>  against the sections that part holds:
>    - references/agent-orchestration-delegated.md
>        -> §1.1-§1.4, §1.8-§1.13
>    - references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md
>        -> §1.16
>    - references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md
>        -> §1.23-§1.27
>    - references/agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md
>        -> §1.29-§1.31
>  Report each miss against its Error Pattern Catalog row."
> ```

Two practices follow.

**The lead already knows the trigger.** One Grep for `^(\*\*Mode:\*\*|Execution Strategy:)\s*DELEGATED\b` over the Master Plan and every Orchestration file decides whether to append the block. The pattern matches the `**Mode:**` line the Orchestration template writes, and it anchors at the line start so the template's reminder text in a DIRECT plan does not match. The lead prints the outcome with the matched and total file counts, so a miss reads as a defect and not as a DIRECT plan. A handler that already runs that Grep for another check reuses the same result here, at no extra cost.

**A checklist row with no loader is a false assurance.** When auditing a checklist-driven handler, verify for each row that *some* spawn prompt causes it to be evaluated. A count of the handler's mentions of the reference does not answer that. A mention in a synthesis step, or in a lead-side conditional-reference list, loads nothing into the agent that runs the check. Read each prompt. `tests/test_reviewer_reference_reachability.py` asserts that the shipped reviewer block names every delegated part file.

Hand-extending one prompt for one pass does not fix this. The next run reverts to the shipped prompt, so the extension has to land in the handler.

### 1.29.3 The shared rule

Both directions are one rule with the arrow reversed. The table names what the orchestrator holds and what the prompt must therefore carry.

| Direction | The orchestrator holds | The prompt MUST carry |
|---|---|---|
| Outbound — instruction to the runner | A condition it resolved, or a convention the protocol assumes | The resolved instruction, named literally |
| Inbound — telemetry from the runner | An expectation of structured return | The delivery channel, not only the payload shape |

Applied: any handler that both enumerates conditional references for the lead and delegates the checking to spawned agents MUST resolve the condition in the lead and push the resulting instruction into the prompt. Symmetrically, any orchestration expecting structured telemetry back MUST specify the delivery channel, not only the payload shape.

### 1.29.4 A session-scope gate names its corpus, and why a narrower one fails

A runner holds a slice of the inputs. A property such as "no deliverable shares 12 words with the source" quantifies over the whole source and every deliverable. A runner that sweeps only its own slice cannot see a collision with material it was never given.

> [!constraint] State the required gate corpus and the one-line reason a narrower one is insufficient
> When a session asserts a property over a corpus larger than any single runner's inputs, the spawn prompt MUST state two things. It names the corpus the session gate runs over. It also gives a one-line reason a narrower corpus is insufficient.
>
> WRONG — the prompt asks for a clean sweep and leaves the corpus implicit:
> ```
> "Before returning, sweep your section files for verbatim overlap with the source. Report any hits."
> # A capable runner reads this as "sweep my own inputs". It cannot have copied text it never read,
> # so it reasons that its own slice is the whole corpus, and it reports clean.
> ```
> CORRECT — the prompt names the gate corpus, labels the runner sweep as a drafting aid, and carries the mechanism:
> ```
> "Sweep your own section files against the source as fast feedback while you draft. This sweep is NOT
>  the gate. The session gate sweeps the FULL source against ALL deliverables from every runner.
>  Reason a narrower corpus fails: a collision with material outside your slice is undetectable from
>  inside your slice, even when your own sweep reports zero hits."
> ```
>
> The reason travels in the prompt, not only the instruction. A runner told only to run the wider sweep may optimise it back down to its own inputs, reasoning soundly about copying and unsoundly about collision. The one-line mechanism blocks that step.

## 1.30 Liveness — Establish Death Before Dispatching a Replacement

A task-runner produces **no observable output between dispatch and its final status block**: seconds for a short task, hours for a fixture build or a probe loop. Across that window the orchestrator cannot tell apart three states that demand opposite responses:

| State | Correct response |
|---|---|
| Working normally | Wait. Touch nothing it owns (§1.26). |
| Dead or killed | Re-dispatch. |
| Stalled or looping | Intervene, then re-dispatch. |

§1.17 classifies a runner that **returned**. This section covers the case where nothing arrives at all, which the orchestrator must resolve by inference rather than by reading a report.

> [!constraint] Silence is not evidence of death — prove it before replacing the runner
> The recovery action for a presumed-dead runner is re-dispatch, and re-dispatching onto a **live** runner puts two writers on one task's declared output set. Where the task writes only its own output file, that corrupts a deliverable. Where it writes machine-global state under inventory-and-restore, two concurrent restore sequences can leave a global config file holding fixture content, with no clean rollback and no error raised.
>
> So the ordering is binding: **establish death, then dispatch a replacement. Never the reverse.**

**Two things that look like liveness signals are not.**

1. **An agent listing may not show in-process subagents at all.** Measured with a dispatched task-runner actively writing files, the listing returned only peer interactive sessions and no subagent rows — and a *completed* runner from earlier in the same session was equally absent. A listing that cannot tell running from finished from never-existed supports no inference either way, so reading absence there as death is unsound.
2. **An idle notification means "available", not "finished".** It is a signal about the runner's turn, not about its work, and it says nothing about sustained silence.

**The check that settles it is the runner's own transcript.** It is cheap, available throughout the window, and discriminates directly. `scripts/runner_liveness.py` runs it:

```bash
python -B {plugin_root}/scripts/runner_liveness.py {agent-transcript-path}   # two samples, 60 s apart by default
```

A last-entry timestamp seconds old settles the question: alive. Minutes old **with no line growth across two samples** is a genuine stall. One sample proves nothing — a single reading is consistent with both hypotheses, which is the whole failure mode.

> [!pitfall] A half-built output tree is not evidence of a dead process
> **Problem:** the orchestrator inventories disk, finds a partial artifact tree, and reads it as the residue of a mid-write kill. In the measured incident it was a **live** agent's tree mid-write: the runner wrote again minutes after being declared dead. Every input the orchestrator used fit both hypotheses, and it picked one.
> **Solution:** a disk inventory measures *what exists*, never *whether a writer is still attached to it*. Only the transcript check answers the second question. Run it before concluding anything from disk state.

**The replacement runner self-checks before its first write.** When a re-dispatch does happen, the detection that catches a wrong death call belongs in the protocol rather than in luck. Tell the replacement, in its spawn prompt, that its inventory is a **frozen snapshot** taken at dispatch:

```markdown
The file inventory above was captured when you were dispatched and is a frozen
snapshot. BEFORE your first write, compare it against live modification times.
Anything created or modified between that snapshot and your first tool call
means another writer is active on this task: HOLD and report it. Do NOT
proceed to any irreversible step.
```

In the measured incident the duplicate compared its snapshot against live mtimes, saw fixture files created minutes *before its own first tool call*, and stopped short of the irreversible swap. Blast radius was zero because the duplicate caught the error, not because the orchestrator reasoned soundly.

**A replacement's brief marks the dead runner's leftovers UNVERIFIED.** A partial artifact reads as a complete one to whatever consumes it next. When a re-dispatch is warranted, enumerate what the previous runner left on disk and label the inventory UNVERIFIED, so the replacement re-derives rather than trusting it.

> [!practice] A toolchain that updates mid-run splits a measurement set silently
> An auto-updating CLI can upgrade itself between dispatches, or during one. Where measurements are per-build facts, an update between repetitions splits a rep set across two builds with no error, and the update's quiet window is easy to misread as a dead runner. Record the build at session start and at close, and report a set that spans two builds as two sets.

### 1.30.1 A run journal with `started` and no `result` is in progress

A background workflow journal records a `result` line as each agent settles. A batch spawned together logs all its `started` lines up front. A started-only journal therefore reads the same for a live run and a dead one. An agent transcript that ends on an unanswered `user` message is a turn in flight, not a death.

Wait for the completion notification, or check the run's live task status. To prove a stall, run the two-sample transcript-growth check above. Relaunch only after death is established. Stop the prior run first, then resume it by its run id with `resumeFromRunId`. Never start a fresh duplicate. If the harness refuses the resume, start a new run only after the prior one is stopped.

> [!constraint] A started-only journal after a context compaction is not a dead run
> WRONG — the journal is read as a death certificate, and a duplicate starts:
> ```
> compaction -> journal shows N `started` lines, no `result` -> "run is dead" -> launch a duplicate
> -> the original finishes later: two writers on one target, double spend
> ```
> CORRECT — the run stays in progress until death is proven, and the relaunch is a resume:
> ```
> compaction -> journal shows `started` lines, no `result` -> in progress
> -> wait for the notification, or check live task status
> -> two-sample transcript-growth check shows no growth -> stop the prior run -> resume it by run id
> ```

## 1.31 A Shared Precondition Belongs to the Orchestrator

A precondition that every task in a dispatch layer depends on — a baseline SHA, a resolved schema version, a next-free identifier — is the **orchestrator's** to establish, not the first task's. Resolve it once, before the layer goes out, and hand every runner the resolved value.

```
# WRONG — task 01 produces it, tasks 02-06 consume it, all dispatched together
Task 01: BASE=$({pin command}); write BASE to {shared bookkeeping file}
Task 0N: BASE=$(read back from {shared bookkeeping file}); test -n "$BASE" || exit 1

# CORRECT — orchestrator resolves once, pre-dispatch
orchestrator:          assert preconditions; BASE=$({pin command}); record centrally
spawn prompt (all N):  "BASE={resolved literal value}"
```

The WRONG shape fails twice over, and the two failures compound. All N tasks dispatch **concurrently**, so task 01 has produced nothing when its siblings need the value. And the parallel-dispatch contract forbids a runner to touch the shared bookkeeping file at all — runners return status blocks and the orchestrator reconciles centrally — so task 01 could never write it and the others could never read it. Executed literally, N-1 runners HALT at the guard. Executed loosely, a runner improvises, and an unset variable degrades the gate **silently** rather than failing it, restoring the unscoped behaviour the guard existed to prevent. **The failure is worse when the guard is skipped than when it fires.**

The same defect reaches the producing task's own first step whenever that step asserts a clean write-set. Run concurrently, it observes its siblings' in-flight edits and HALTs on correct work.

**The delivery mechanism is already specified — this section does not restate it.** [Part 1](agent-orchestration-delegated.md) §1.6 states that a shared pin is injected as a **literal** into every task file and every spawn prompt, and carries the WRONG/CORRECT spawn-prompt pair for it. This section adds **who resolves the value**: the orchestrator, before dispatch. §1.6 assumes that assignment rather than making it.

> [!checklist] Diagnostic questions for a declared-parallel layer
> Apply these by reading the layer's task files. The dependency field cannot answer them.
> - [ ] Does any task in this layer **produce** something another task in the same layer **consumes**? If yes they are not parallel — serialise them, or lift the shared step to the orchestrator.
> - [ ] Does the consumer read that value from a file the dispatch contract **forbids it to touch**? That is a guaranteed deadlock, not a race.
> - [ ] Does any task assert a property of the **whole working tree** — clean status, changed-file counts, "exactly N files changed"? Concurrent siblings violate such an assertion by construction, so it belongs pre-dispatch or post-batch, never inside a batch member. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17.3 carries the path-scoped form a per-task gate must use instead.

`scripts/lint_layer_disjointness.py` reports each of these three questions against a session Orchestration's dispatch layers.

**Why the eligibility check missed it.** Every task in the measured batch honestly declared no dependency, because the *file write-sets* really were disjoint, and disjoint write-sets are the criterion the parallel-eligibility check applies. The dependency was on a **shared variable**, and no field in the task schema represents one. Disjoint outputs are **necessary but not sufficient** for parallel dispatch: a shared input that one member generates serialises the layer exactly as hard as a shared output file does. So apply the check by reading the layer, not by trusting the field.

[`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17 computes a layer's write-target intersection at scaffold time, and §17.2 covers the sibling case where the shared object is an **allocation** — a next-free number — rather than a path. Those are the plan-time gates. This section is the dispatch-time obligation, and it stands whether or not the plan carried one.

### 1.31.1 A target pin over a stored corpus carries a census, a fallback ceiling and a NONE sentinel

A target pin is a precondition the orchestrator resolves before dispatch. Some pins name a record that a runner reads from a stored data corpus, such as a database, an archive or a backfilled table. A recency-ordered query assumes the corpus is dense up to its newest timestamp. Real corpora are not: a backfill stops where its budget stopped, a list endpoint may write future-dated rows, and some periods hold one record per day.

In one reported run, a paid smoke test needed one past record that resolves in a stored corpus. The orchestrator pinned the target with a recency-ordered query and a bounded fallback of "step back one date, at most 3 tries". The corpus stopped well before its newest timestamp. All three tries fell into the same gap, and the first resolvable candidate was the query's 13th. The runner wrote the sentinel `NONE` with the reason, measured two alternatives with read-only queries and returned, having spent no paid credits. The orchestrator then re-pinned the target.

> [!constraint] A pin over a stored corpus is checked against the corpus before dispatch
> A recency order and a short fallback together assume a dense corpus. Nothing in the pin tests that assumption.
>
> WRONG — recency order, a fallback shorter than the gap, and no existence assertion:
> ```text
> Target: the newest {record} in {corpus}, ordered by {timestamp} descending.
> Fallback: if the candidate is unresolved, step back one date, at most 3 tries.
> ```
> CORRECT — a census in the delta, a ceiling above the gap, an existence assertion and the sentinel:
> ```text
> Census ({corpus}, {date}): {GROUP BY month result, with the empty months named}.
> Target: the newest {record} in {corpus} at or before {date before the gap}, and the query asserts
>         the record exists in the corpus the runner reads.
> Fallback: step back one date, at most {N above the largest known gap} tries.
> If no candidate resolves, write NONE with the reason, measure alternatives with read-only
> queries, and substitute no other target.
> ```

1. **Run a census first.** Run one `GROUP BY` over the corpus, by month or another coarse bucket. It takes seconds and shows the gap that the recency order falls into. Cite the census in the delta as a dated row, per [verify-before-cite.md](verify-before-cite.md) §9.B.24.
2. **Set the fallback ceiling above the largest known gap, or make the query skip the gap.** A limit of three tries suits a name mismatch. It cannot cross a two-month coverage hole.
3. **Keep the `NONE` sentinel and the "measure, don't substitute" instruction.** The runner records `NONE` with the reason and measures alternatives with read-only queries. It has no permission to pick another target. This turns a miss into a free finding instead of a mis-targeted paid call.
4. **Assert the target exists in the corpus the runner reads.** Ordering by recency does not assert that. Add the existence condition to the pin query.

#### Reviewer Check 120 — Corpus Target Pin With No Census, Fallback Ceiling or NONE Sentinel

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** A paid or irreversible step whose target is pinned by a recency-ordered query over a stored corpus MUST cite a census of the corpus, set a fallback ceiling above the largest known gap, and keep the `NONE` sentinel with the "measure, don't substitute" instruction.
- **Detection:**
  1. List each Execution Input, delta or task step that pins a target for a paid or irreversible step by querying a stored corpus.
  2. Flag a pin ordered by recency whose delta cites no census of the corpus.
  3. Flag a bounded fallback ("step back one date, at most N tries") whose limit the plan never compares with the largest known gap.
  4. Flag a pin that carries no `NONE` sentinel or no "measure, don't substitute" instruction, and a pin query that does not assert the target exists in the corpus the runner reads.
  5. A pin that cites a census, sets the ceiling above the gap or skips it, keeps the sentinel and asserts existence is not a finding. A free and reversible step is not a finding.
- **Finding template:**
```
[ERROR] Corpus target pin with no census, fallback ceiling or NONE sentinel
File: {task or Execution Input file path} | Location: {the pin or delta line}
Issue: The pin "{quoted pin}" orders {corpus} by recency for a paid or irreversible step and {cites no census | bounds the fallback at N tries with no comparison to the largest gap | gives the runner no NONE sentinel}
Fix: Add the census to the delta, set the ceiling above the largest known gap, and keep the NONE sentinel with the measure-don't-substitute instruction, per references/agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md §1.31.1 | Confidence: HIGH
```

## 1.32 Derive a Remediation Brief's Write Set From Where Each Fix Lands

A remediation task written at a review gate carries two lists. The Fixes table lists intents. The `Output:` line (the runner's write set) lists locations. An author who writes the second from memory of the first drops every fix whose location the author did not picture. The runner then finds the fix, reproduces the defect with a failing test, and correctly refuses to edit a file or line outside its write set.

> [!constraint] Derive the write set row by row from the Fixes table
> WRONG — the write set written from what each file is "for":
> ```
> Output: <style module>, <upgrade module> (try/except wrap only), <io module> (one function), tests
> Fix 3: "the style render callable keeps an installed paths: value"   # lives in <upgrade module>:373
> ```
> CORRECT — the write set derived row by row from the Fixes table:
> ```
> | # | Fix | Lands at |
> | 3 | keep installed paths: on adoption | <upgrade module>:373 (render lambda) |
> | 9 | wrap main-path reconcile          | <upgrade module>:1032 |
> Output: union of the "Lands at" column, plus tests and the Output file
> ```
> In the measured case the file was allowed only for "the try/except wrap" and one condition. Fix 3 lived in a render lambda at a third site. The runner returned PARTIAL with a `BRIEF COLLISION` and parked the test as an expected failure.

[`dispatch-decomposition-graph.md`](dispatch-decomposition-graph.md) §1-§2 holds the scaffold-time form of the same rule: a task that can identify an amendment must be able to apply it, or name who will.

**Step 1 — Add a "Lands at" column.** Give the Fixes table a "Lands at" column (`file:symbol` or `file:line`). Make the `Output:` line the union of that column. Where the location is unknown, `Grep` for the symbol before writing the brief. A `Grep` costs one call. A halted runner costs a resume.

**Step 2 — Add a row for each reader of a changed scope, key or predicate.** For each fix that changes a scope, a key or a predicate, add a row for each existing call site that depends on the old meaning. Example: a fix narrows a sync to two managed paths. A skip condition elsewhere was keyed on "any other copy" and is now inconsistent with the new scope. Nothing owned that row. `Grep` for every reader of the changed scope, key or predicate before writing the table.

**Step 3 — Adjudicate the halt.** Fix the brief, authorize the line, and record the adjudication.

**The cost to inline.** The measured halt cost a full resume round trip into a nearly full window: the runner had used about 200K tokens. §1.17.5 of [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) ("Name a write-by turn in the spawn prompt, and size the brief by its proof count") covers the neighbouring rule on brief size. The two rules compound: a large brief with an incomplete write set halts late.

**Applies to** remediation tasks written at a review gate, where the orchestrator authors a brief under time pressure from a findings list. It also applies to any brief that lists permitted edits per file by purpose ("only the X block") rather than by location. For how to rank the fixes themselves, see [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.9 and §1.25.3.

---

**Part of a four-file discipline:** [Part 1 — Foundations and Dispatch-Prompt Construction](agent-orchestration-delegated.md) (§1.1–§1.13) · [Part 2 — Dispatch Mechanics and Returns](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) (§1.14–§1.22) · [Part 3 — Cross-Cutting Dispatch Discipline](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) (§1.23–§1.28)

*Originally extracted from [`agent-orchestration.md`](agent-orchestration.md) §11-§12 (DELEGATED Dispatch Discipline + Verify-Before-Acting on LSP Diagnostics); §1.19–§1.22 folded from `handlers/run.md`'s Delegated Execution Protocol (2026-08-10). `agent-orchestration.md` now carries only a short §11 pointer stub back to Part 1. Split into three topical parts (2026-09-06) because the combined text exceeded the Read-tool page cap; section numbers were frozen across the split.*
*Cross-reference: [agent-orchestration.md](agent-orchestration.md), [agent-authoring.md](agent-authoring.md), [skill-authoring.md](skill-authoring.md)*
