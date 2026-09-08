---
description: Every statement crossing the orchestrator/runner boundary is a hypothesis authored inside one window about a world visible only from the other. Covers withholding the figures a dispatched task exists to re-derive, resolving an inbound flag's named consumer against the partition key, why diff attribution belongs to the orchestrator and not the runner, and what a silent resume actually means. Consult while composing a spawn prompt, while routing an inherited artifact into task files, and while reading what comes back.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Boundary — What Crosses It Is a Hypothesis, Not Evidence

**Purpose:** An orchestrator and a runner cannot see each other's context. Every statement that crosses between them — a figure in a spawn prompt, a routing assignment in a coordination flag, a causal claim in a status block, the absence of a status block entirely — is authored inside one window about a world visible only from the other. The failures are symmetric, and every one of them is silent.

**Read this when** you are composing a spawn prompt, routing an inherited artifact into task files, or reading a runner's return.

Outbound, what the orchestrator writes into a prompt determines what comes back. Injecting the answer converts an independent instrument into a dependent one. Injecting an upstream routing guess sends work to a task that does not own it. Inbound, a runner's report is scoped to a window that often cannot answer the question the report is answering, and the report's non-arrival carries no information at all.

Three neighbouring rules own machinery this file builds on. [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.6 and [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.31 own the **inject** side — a shared precondition is resolved once by the orchestrator and handed to every runner as a literal. §1 below is the deliberate exception to that economy, not a contradiction of it. [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) §1.4 owns receiver-side reconciliation of an inherited flag's *claim* — its values, its judgements, its referent. §2 below covers a different field of the same flag: its named **consumer**.

## Table of Contents

- [1. Withhold Any Figure the Dispatched Task Exists to Re-Derive](#1-withhold-any-figure-the-dispatched-task-exists-to-re-derive)
- [2. A Flag's Named Consumer Is a Hypothesis — Resolve It Against the Partition Key](#2-a-flags-named-consumer-is-a-hypothesis--resolve-it-against-the-partition-key)
- [3. Diff Attribution Is the Orchestrator's Job, Not the Runner's](#3-diff-attribution-is-the-orchestrators-job-not-the-runners)
- [4. A Silent Resume Means the Reply Exists and Did Not Route](#4-a-silent-resume-means-the-reply-exists-and-did-not-route)
- [5. A Flag the Sender Says It Delivered Is a Claim; Only the Destination File Is Evidence](#5-a-flag-the-sender-says-it-delivered-is-a-claim-only-the-destination-file-is-evidence)

---

## 1. Withhold Any Figure the Dispatched Task Exists to Re-Derive

> [!constraint] Injected context is not free — it converts an independent instrument into a dependent one
> | Inject | Withhold |
> |---|---|
> | How to invoke (flags, path form, shell fix) | What the previous run cost |
> | What the envelope looks like and where fields live | What the previous run's write set was |
> | Environment constraints (`cd` denied, encoding traps) | Any figure this task exists to re-derive |
> | Known traps that waste budget | Any sibling's verdict on the same question |
>
> The discriminator is one question: **could knowing this change the number the agent reports?** If yes, withhold it — even when injecting would be cheaper, and even when you are confident the agent would resist anchoring.
>
> ```
> WRONG — the orchestrator injects everything it knows, including the answer:
> spawn: "…pinned form is X. For reference, Wave 1 measured list at $0.71/98s/17 turns
>         and a 10-file write set. Re-measure and report."
> → runner measures $0.89/151s/19 turns, 0 files
> → reconciles toward the injected anchor, or reports it as an anomaly needing explanation
> → the 2-to-1 split is never visible; the non-determinism ships as "deterministic"
>
> CORRECT — procedural facts injected, figures withheld, and the reason stated so the runner
> does not experience the gap as an oversight and go looking:
> spawn: "…pinned form is X [+ 8 other procedural facts].
>         I am deliberately NOT giving you sibling cost figures — your value here is
>         independence. Compare against the ORIGINAL anchor only. Report what you
>         measure even if it looks surprising; a surprising honest number is worth
>         more than a plausible one."
> → runner measures independently → orchestrator cross-checks → agreement on one surface
>   is evidence; divergence on another is a finding
> ```

The qualitative twin of this rule — a stated *expectation* or a named cause rather than a figure, why hedging it does not help, and what to do once such a premise has already shipped — is [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) §1, §2 and §7. The two meet on the same discriminator question.

**Say why you are withholding.** An agent that notices a conspicuous gap in an otherwise thorough briefing may go and find the data itself — reading a sibling's output file, or asking. Naming the withholding as deliberate closes that path. Telling the runner that a surprising honest number outranks a plausible one licenses it to report the outlier.

**The withholding paid twice in the measured session.** On the surface that agreed, a warm-run cache-read token count came in at **30,705 against 30,691**, across separate operating-system processes that never saw each other's data. That is corroboration anyone can trust. On the surface that disagreed, the divergence *was* the finding: one run wrote **zero** files and enumerated a different project, where two same-day runs had written the expected 10-file tree. The 2-to-1 split proved the surface non-deterministic and invalidated an inherited baseline finding the whole plan rested on.

**The sample-size corollary — plan for three or more observations on any surface you intend to call deterministic.** Two blind measurements that agree are corroboration. Two that disagree are only a puzzle. It was the *third* observation that made the split legible as non-determinism rather than as one runner's error. When a plan's binding constraints rest on a surface being deterministic, the sample size is a design decision, not an accident of how many tasks happened to touch it.

---

## 2. A Flag's Named Consumer Is a Hypothesis — Resolve It Against the Partition Key

> **A fork announces itself. A confidently-wrong consumer does not.**

> [!constraint] Check every flag that names an item, not only the ones that look undecided
> The graded example is what shows an existing "pin unresolved forks before dispatch" rule to be necessary and insufficient:
>
> | Flag text | How it reads | What trips on it |
> |---|---|---|
> | `"Task 1 or Task 3 — assign at Phase 1"` | visibly a fork | the pin-the-forks rule |
> | `"Task 3, or whichever task takes {claim-id}"` | mostly decided | nothing reliably — it slips past |
> | `"Task 3"`, in a confident tone | settled | nothing at all |
>
> The third is exactly as capable of being wrong as the first.

**The four-step receiving preflight.**

1. **Resolve the id against the partition key.** One bounded `Grep` per claim returns the authoritative stamp. Four such searches cost roughly a dozen lines of context.
2. **Record one of three rulings, with its evidence** (the stamp plus `file:line`): **confirmed** (the flag's consumer is right), **re-pinned** (a different task owns it), or **no-op for this session** (nobody here owns it — re-route to the session that does).
3. **Tell the non-owning tasks explicitly.** Write "this flag is NOT yours, and its absence from your pull is expected, not a coverage gap" into their task files. Otherwise a runner that correctly finds nothing cannot distinguish that from a broken pull.
4. **State that the key outranks prose wherever prose appears** — including an assignment written inside the authoritative artifact itself.

**Why nothing errors, in either direction.** Route a flag to the task it names, and that runner finds the claim absent from its own pull. It either designs a claim it does not own — double-design, discovered later at cross-count if at all — or drops it as "not mine", which is silent. Route in a flag no task owns, and a runner spends effort on a passage no claim in its set references. The runner's report describes either outcome as success.

**Why this lands on the receiver and can land nowhere else.** Hop 1, upstream delivering into the downstream orchestration file, is owned by a session that knows its own findings but not the receiver's decomposition. Hop 2, orchestration into task files, is owned by the receiver, which knows both. **The preflight is the only point where the flag and the partition key are visible at the same time.** An upstream author cannot do this check. A dispatched runner sees only its own slice. If the receiver does not do it, nobody does.

**The measured case.** A session dispatched three parallel designers over one frozen register of 200 claims, each selecting its work by a mechanical key — a `Modality` stamp on disk. Ten inbound flags each named a downstream consumer in prose, and **two of the ten were wrong**. One named a fork between two tasks for a claim stamped `headless`, which belonged to a third task the flag never mentioned. Another named two claims stamped `observational` that **no task in the session owned** — they belonged to the next session. The upstream authors were not careless. They had read the source closely enough to find a genuine contradiction. What they had not read was the final reconciled partition, which did not exist when the flags were written. A third variant appeared in the authoritative register itself, which named a resolver task on a line predating an enum change that had moved the boundary.

> [!hazard] Two conditions raise the rate
> The risk rises when the partition was reconciled *after* the upstream flags were authored, and when the partition key changed mid-plan. An enum gaining a value moves boundaries under flags already in flight.

---

## 3. Diff Attribution Is the Orchestrator's Job, Not the Runner's

> [!constraint] A runner reports what it wrote; it never says what the diff means
> When a repo is committed once per session, a runner's own `git diff` is a **session-cumulative** view, not a per-task one. A runner may legitimately report *what it wrote*. It must not claim what the diff's deletions or file list *mean*.
>
> ```
> WRONG — a runner explaining a diff stat it cannot see the origin of:
> LINES_PRODUCED: 202 insertions, 3 deletions
>                 (the 3 deletions are my anchored Edit re-inserting heading lines)
>
> CORRECT — the runner reports its own writes and scopes its gate to its own path;
>           the orchestrator attributes:
> LINES_PRODUCED: 658 → 734 (my four sections appended after §9.B.15)
> ISSUES: 3 deletions present in the file's cumulative diff — not mine; origin unknown from my view
> ```
>
> The attribution command the orchestrator runs at reconciliation:
>
> ```bash
> git diff -- <file> | grep -E '^-' | grep -v '^---'   # inspect EVERY deleted line, match to the task that made it
> ```

**The count-side corollary, and how the two relate.** A per-task isolation gate must be **path-scoped** (`git diff --name-only -- <this task's paths>`), because a repo-wide file count is cumulative for exactly this reason and false-fails by the third task. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17.3 owns that rule and protects the *count*. This section extends it to the *content*, because a runner cannot interpret deletion lines either.

**Do not solve this by committing per task.** The single-commit-per-session convention exists for good reasons. The fix is to stop asking runners a question their view cannot answer.

**The damage, even where no artifact was harmed.** A runner appending four sections reported that three deletions were its own anchored Edit re-inserting heading lines. Inspecting every deleted line showed the three were the **previous task's** sanctioned repair lines. It had deleted nothing. The runner was not careless — it saw three deletions in "its" diff, knew it had performed anchored Edits, and constructed a plausible story, because nothing in its view distinguished its own changes from its predecessor's. An incorrect account of the diff still enters the record and propagates to any downstream reader, reviewer or sweep that trusts the status block. In this case it also **understated** the runner's own result: correctly attributed, those three lines were the file's entire session-wide deletion set, which proves about fifteen pre-existing sections were byte-unchanged apart from two intended repairs.

---

## 4. A Silent Resume Means the Reply Exists and Did Not Route

> [!constraint] Delivery failure and non-completion are different states, and only on-disk evidence separates them
> | Signal | State | Action |
> |---|---|---|
> | Idle, no status block, **Output absent or partial** | Genuinely unfinished | Resume the SAME agent to finish the work |
> | Idle, no status block, **Output complete on disk** | Finished; report did not route | Resume the SAME agent for **the report only** |
> | **Resume also returns silent**, Output still complete | The reply exists and is not routing | **Recover from the transcript** — do not ask a third time |
>
> An idle notification carries no information about either state. It means "available", not "finished".

The first two rows are existing practice, owned in detail by [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 (classify the return before consuming it) and [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.7.1 (the read-only resolution ladder on an idle notification). They are restated as rows here because the discriminator that selects the third row is only legible beside them. The third row is this section's own content.

```
WRONG — treat the second silence as another non-answer:
idle, no block → disk shows complete → resume for report → idle again
→ ask a third time (same failure path), or re-dispatch a fresh runner
# Re-dispatch is the expensive error: it re-reads everything, may race a live agent,
# and can duplicate writes to the same declared Output path.

CORRECT — the second silence reclassifies the problem from "no answer" to "no delivery":
resume → idle again
→ glob ~/.claude/projects/**/subagents/agent-a<name>-*.jsonl
→ bounded `-o` extraction of the field names, take the LAST match
→ cross-check every recovered field against the orchestrator's own measurements
```

**The bounded-recovery mechanics, because the unbounded form fails.** The `.jsonl` is the full subagent conversation and will overflow the orchestrator's context if read whole. What works is a targeted `-o` extraction of the status-block field names with a small capture window, taking the **last** matching line. Earlier hits are the spawn prompt's own template echoed back, so a recovery that takes the first match recovers the prompt rather than the report.

```
Grep pattern='(TASK_STATUS:|TASK_ID:|OUTPUT_FILES:|LINES_PRODUCED:|KEY_FINDINGS:)[^\\]{0,120}'
     path='…/subagents/agent-aNAME-*.jsonl'  output_mode=content  -o=true
```

A whole-line match on the same file returns `[Omitted long matching line]` and yields nothing. The small capture window is what makes it work. Keep the field list aligned with the status-block contract in [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.28, since a pattern naming a field the contract does not define can never match.

**The recovered block is corroboration, not the source of truth.** Every load-bearing field a status block reports — output paths, line counts, byte counts, repo invariants — the orchestrator can and should measure itself, and the acceptance gate already requires it. Treat recovery as filling in the narrative fields (key findings, issues, budget spent) around measurements you already own. That is also why a delivery failure never blocks acceptance: **you were never supposed to be accepting on the strength of the final message anyway.**

> [!hazard] Do not turn this into "always skip the message layer"
> Three of six blocks arrived fine in the measured session, and an earlier one recorded four of five. The failure is intermittent, so blanket transcript-scraping burns calls on the majority that work. The trigger is specific: **a resume that also comes back silent while the deliverable is verifiably complete.** In the measured case the reply was recoverable from the subagent transcript and matched the orchestrator's own independent measurements field for field.

> [!practice] §3 and §4 are adjacent and must not be merged
> §3 is about a status block that **arrived and said something its window could not support**. §4 is about a status block that **never arrived at all**. The correctives run in opposite directions — §3 discounts the report and re-derives from the artifact, §4 goes and fetches the report. A merged section collapses into "don't trust status blocks", which is true of neither.

Sustained silence with **no** idle signal at all is a different question again. [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.30 answers that one: establish death before dispatching a replacement.

---

## 5. A Flag the Sender Says It Delivered Is a Claim; Only the Destination File Is Evidence

**Run this check before §2's.** Both act at the same preflight moment — routing an inherited artifact into task files. There is nothing to adjudicate about a flag that is not there.

> [!constraint] Diff the sender's manifest against the destination, and match on subject
> WRONG — read the front door and assume it is complete:
> ```
> Read orchestration's `## Pre-Known Cross-Task Coordination Flags`
> → 30 flags present → route all 30 → dispatch
> # A flag the sprint plan says was delivered here, but was not, is never noticed.
> ```
>
> CORRECT — diff the sender's manifest against the destination:
> ```
> Read the sprint plan's Carried-Forward table; select rows whose Consuming Session is THIS one
> For each: confirm a row with that flag's SUBJECT (not merely its id) exists at the front door
> Zero hits → recover it from the sprint plan, route it, and record the gap
> ```

**Three sub-rules, each with its reason.** A bare instruction to "check arrivals" loses what makes every one of them non-obvious.

- **Match on subject, never on id alone.** Flag ids are assigned per-sender and collide freely across senders. Two upstream sessions both numbering a flag `G-06` is normal, not a bug. An id match is therefore not an arrival check. Search the destination for the flag's distinguishing content — a claim id, an anchor, a file name.
- **When you recover a flag whose id is already taken at the destination, renumber it rather than overwrite** (`G-06b`), and state in the routed text that the id was reused upstream. Silently replacing the occupant destroys a live flag in order to deliver another.
- **Record the propagation gap as a finding, not a fix.** The sender's record stays wrong until someone corrects it. A receiver who quietly patches the hole leaves the next session inheriting the same false assurance.

**Why this lands on the receiver, and can land nowhere else.** The sender cannot verify its own delivery. It writes the `Delivered To` cell in the same pass that performs — or fails to perform — the write, so the claim and the act come from one intent. An intermediate session reading the sender's column propagates the claim without testing it. That is how a false assurance gains a second, more credible-looking source: the second record comes from a different party and is therefore read as independent corroboration, while in fact it is a copy. **The destination file is only ever readable from the destination.** Without this, the section reads as optional diligence that a careful sender could make unnecessary, and a reader will reasonably conclude the sender should simply be more careful.

**The measured incident, and how the flag was recovered.** A sprint plan's Carried-Forward table recorded a flag whose `Delivered To` column named the downstream session's orchestration file. An intermediate session's preflight then recorded, in its own Recovery file, that the flag was "a no-op for this session — it belongs to that session and was already delivered there." Both records were half right. The flag genuinely belonged to the downstream session, and it had never been written into that session's orchestration file. Two mechanisms kept the absence invisible and they compound: **the id was occupied** — the receiving orchestration already carried a row with that number from an unrelated flag by the same upstream session, so a reader scanning for the id finds it and stops — and **two independent records asserted delivery, neither of which was the destination file.** It was recovered only because the receiving orchestrator searched the *destination folder* for the flag's subject matter rather than for its id, and got zero hits across the entire session directory. Had it stayed lost, both claims the flag governs were in that session's pull, and their protocols would have been authored against a field that disagreed with the ledger.

**This is not planwise-specific.** The shape appears in any hand-off protocol where a producer records what it delivered and a consumer reads a separate front-door location: cross-session and cross-sprint carried-forward sections, ticket hand-offs with a "notified" field, migration checklists with a "propagated" column. The risk is highest when flag ids are sender-scoped, so collisions are expected, and when an intermediate party restates the sender's claim.

> [!practice] §5 is a distinct section, not part of §2
> §2's subject is a flag that **arrived and named the wrong consumer**. §5's is a flag that **never arrived**. The correctives run in opposite directions: one re-adjudicates a row that is in front of you, the other goes looking for a row that is not. This is the same arrived-but-wrong versus never-arrived distinction that keeps §3 and §4 apart. Merged, the pair collapses into "check your flags", which is true of neither.

[`../handlers/run.md`](../handlers/run.md) Step 1.1a owns the four-source enumeration and the union-diff against task files. This section is the half that check does not specify: **how to match.** A union-diff run on ids alone returns a false negative exactly when the destination already carries that id, which is the condition the measured incident was in.

---

*Cross-reference: [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) §1.6, §1.7.1 · [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 · [`agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`](agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md) §1.28, §1.30, §1.31 · [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) §1.4 · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17.3*
