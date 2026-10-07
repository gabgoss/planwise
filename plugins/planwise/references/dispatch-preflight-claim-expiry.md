---
description: What expires between authoring a plan and dispatching it — the six surfaces a stale premise hides on, quantifier-to-enumeration drift in prerequisites, why a prerequisite-COMPLETE gate re-validates nothing, the Depends On / Required Context split, the sibling-sprint sweep, and why a re-measure instruction needs a threshold and an action. Consult at Phase 1, before dispatching any session authored earlier or held behind a gate.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Preflight — Claim Expiry (What Aged Between Authoring and Dispatch)

**Purpose:** A gate validates a session against its *stated* premise, and the premise is upstream of every gate. Deferral accrues expiry, and **the waiting is invisible, because nothing re-runs when the gate finally clears.** This file governs what a session re-takes at Phase 1, before it dispatches anything.

**Read this when** a plan was authored before today's dispatch — held BLOCKED behind an external event, scaffolded many sprints in one pass, or waiting on an upstream that has since closed.

Two neighbouring rules own machinery this file builds on and does not restate. [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.5 governs re-measuring **gate-bound figures** at preflight — the figures a gate's predicate compares against. §12.3 governs re-deriving a **state-asserting row** at scaffold close. This file covers what neither reaches: the premises that live on surfaces no gate reads, and the reconciliations a resolving dependency graph cannot perform. [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) §1.4 governs the inherited *flag* specifically.

## Table of Contents

- [1. A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears](#1-a-held-plan-re-takes-every-measurement-it-asserts-at-the-moment-the-gate-clears)
- [2. Quote the Edge, Then Enumerate — Never Enumerate Instead of Quoting](#2-quote-the-edge-then-enumerate--never-enumerate-instead-of-quoting)
- [3. A Prerequisite-COMPLETE Gate Is a Completion Gate, Not a Re-Validation Gate](#3-a-prerequisite-complete-gate-is-a-completion-gate-not-a-re-validation-gate)
- [4. `Depends On` and `Required Context` Are Two Different Assertions](#4-depends-on-and-required-context-are-two-different-assertions)
- [5. Sweep Sibling Sprints That Closed On or After Your Scaffold Date](#5-sweep-sibling-sprints-that-closed-on-or-after-your-scaffold-date)
- [6. A "Re-Measure at Dispatch" Instruction Without a Divergence Action Is a No-Op](#6-a-re-measure-at-dispatch-instruction-without-a-divergence-action-is-a-no-op)

---

## 1. A Held Plan Re-Takes Every Measurement It Asserts, at the Moment the Gate Clears

> [!constraint] This is a numbered step of the pre-dispatch gate, never a note
> A plan authored for immediate execution has near-zero expiry. One held behind an external event accrues expiry proportional to how long it waits. Nothing re-runs when the gate clears, so the re-take must be a step that executes.

One sprint held BLOCKED for two days guarded this thoroughly and still shipped six expired facts. Every task brief carried a re-derive instruction. A sweep for pre-committing phrasing returned zero hits across all seven files. All six expired facts sat **outside** task execution steps:

| Expired fact | Surface it lived on |
|---|---|
| a binding "quoted from the live handler" — the binding had moved to a reference section | **two success criteria** |
| a Required Context row describing a section as "the binding definition" — it had become a summary deferring elsewhere | **a Required Context row** |
| a corpus count ("2 active lessons… 18 active items") — actually 8 and 36, with one named defect already repaired | **a Prerequisites block + a Dependencies row** |
| four named coordination-flag consumers — all four sessions had completed | **a task step's "expect at least" list + a Recovery flag table** |
| "Sprints 02–06 are NOT STARTED" + a quoted standing do-not-run note — both false | **a Prerequisites gate callout** |
| eleven line counts, one contradicting a corrected figure in the same file | **Required Context tables + a Context Boundary note** |

**A task file is not the only thing that expires.** A success criterion naming a file is a premise. A gate specification naming a source is a premise. A Required Context row describing what a section contains is a premise. A downstream-consumer list asserting a session is still in the future is a premise. None of them reads like a "brief", and each fails differently:

- A stale criterion is unsatisfiable at closeout.
- A stale Required Context row silently mis-scopes a read.
- A stale consumer list spends real effort drafting for sessions that already finished.

### Four obligations

Each carries its threshold and its action, per §6.

1. **Stamp every measured figure with its measurement date, inline.** The refresh pass then finds them by `Grep` rather than by reading. No threshold applies — this is an authoring rule, not a measurement.
2. **Enumerate the expiring surfaces explicitly**, using the table above as the checklist. **Threshold:** any surface whose re-take disagrees with the recorded value. **Action:** correct it in every copy together, record the cause rather than only the new value, and where the disagreement touches a success criterion or a gate specification, revise that criterion **before dispatch** — not at closeout, where it is unsatisfiable.
3. **Re-derive conclusions, not just counts.** One headline conclusion here survived only by coincidence, resting on eight entirely different lessons, while a sibling claim was outright refuted because the defect it named had been fixed and its owner archived COMPLETE. **Threshold:** the re-derived conclusion differs from the recorded one, in any direction. **Action:** revise the plan before dispatch. Do not annotate the old conclusion and proceed.
4. **A downstream consumer's existence is a measurement too.** Before drafting a coordination flag, check its target is still a future session. **Threshold:** the named consumer has already completed. **Action:** do not draft the flag. Route the observation to the genuine consumer, or record it as discharged with the date the target closed.

**Adding another "re-derive this" sentence to the briefs would have changed nothing.** The briefs already said it, repeatedly and well. What was missing was a step that *runs*.

---

## 2. Quote the Edge, Then Enumerate — Never Enumerate Instead of Quoting

> [!constraint] A prerequisite is a derived artifact, and restating a quantifier as an enumeration is a lossy derivation
> ```
> WRONG — the quantifier restated as the sprint set that existed at authoring time:
>   **Sprints 01–06 ALL COMPLETE** (E6 edge) — verify each Sprint Signoff verdict PASS.
>      ← the edge said "all". Sprints 08, 10 and 11 were dropped silently.
>      ← the citation certifies a narrowing the source does not contain.
>
> CORRECT — the derivation stays visible and re-checkable on the line itself:
>   E6 = all→ES7  ⇒  {ES1…ES6, ES8, ES10, ES11}
>      ← a reader can falsify the enumeration against the edge without leaving the line.
> ```

The citation is what made it dangerous. Written as a bare list, `Sprints 01–06` invites the question *"why those?"*. Written with the edge name attached it reads as already reconciled, and a reader's natural verification — *does the plan say that edge exists?* — returns yes. A 27-finding review fixed 5 BLOCKERs and 9 ERRORs and never flagged it.

Three rules follow.

- **The two forms agree only at the instant of authoring.** A quantifier keeps tracking the set. An enumeration freezes it.
- **When an edge names a quantifier (`all`, `every`, `any`), treat the enumeration as expiring.** Re-derive the member set at Phase 1 whenever new members have been scaffolded since.
- **Add the reconciliation to plan review explicitly.** For every prerequisite citing a graph edge, re-derive the edge's member set and diff it against the stated list. This is mechanical and cheap, and no existing check covers it — prerequisites are treated as premises rather than as derived claims.

### The same expiry lands on what the session publishes

- **A sprint that publishes "final" anything owes a freshness predicate, not a prerequisite.** "Runs last" is meaningful only relative to a set. State the validity condition — *"these counts are final iff no sprint lands after this session"* — so that reordering makes the staleness self-announcing.
- **When such a sprint is suspended mid-flight, re-label its outputs at suspension time, with the void scope enumerated** (which files, which counts). A delta report authored as *the gate* for the next session, and left labelled that way, hands that session an expired claim wearing a gate's name.

---

## 3. A Prerequisite-COMPLETE Gate Is a Completion Gate, Not a Re-Validation Gate

> [!constraint] "Prerequisite COMPLETE" answers a question nobody was worried about
> It establishes that the upstream finished and its outputs exist. The actual risk — that what the upstream *found* invalidates the downstream plan — is untouched by it, and the green checkmark feels like clearance.

In one measured case both upstream sprints were COMPLETE and all six discovery documents existed. The mandated re-read found a routing table in which **14 of 21 hypotheses had no owning task** — ten of them unanswerable by the probe apparatus every authored task had built. The session as written could not have answered two thirds of what it existed to answer.

**Diligence alone will not fix this, for a structural reason.** The context boundary that keeps an orchestrator's budget intact forbids it from reading upstream outputs. So the orchestrator is the one actor guaranteed not to see the evidence that its own plan has gone stale. Everything visible from inside the session — statuses, dependency graph, file existence — reads clean. Staleness is visible only from outside the boundary, which is precisely where nobody is looking.

### Five application rules

1. **Put the re-validation gate in the file the executor is required to read.** Under delegated execution that is the orchestration file, with an explicit statement that the context boundary is suspended for this one read. The same warning existed in four places here. Only the one positioned in the execution path fired.
2. **Make "confirmed unchanged" an artifact.** Require the outcome written down either way. An empty record is indistinguishable from a re-read that never happened, and a resuming session cannot tell the difference.
3. **State the gate as an action with a named input.** *"Re-read X against Y and revise before dispatch"* is executable. *"This decomposition is provisional"* will be read as context.
4. **Author upstream findings in checkable form.** A routing table with an owner column per hypothesis makes staleness countable. The same information as narrative advice is a judgement call under time pressure.
5. **Expect the revision to change the task count, not just the task contents.** Where an upstream finding says an entire class of question is unanswerable by the authored apparatus, widening existing tasks cannot fix it. A gate phrased as "expect scope to change" under-prepares for that.

**Preserve identifiers across the revision** wherever anything downstream cites them.

---

## 4. `Depends On` and `Required Context` Are Two Different Assertions

> [!constraint] Only the first survives a preserved-numbering revision
> ```
> Depends On      says "this task cannot start until that one finishes."
>                 → preserving task numbers keeps it TRUE.
> Required Context says "these specific files contain the evidence I need."
>                 → a new sibling task producing new evidence FALSIFIES it,
>                   and no amount of careful numbering repairs that.
> ```

An upstream added two tasks and deliberately preserved numbering 1–4 so downstream `Depends On` stayed valid. Between them the two new tasks owned **15 of 21 hypotheses**. The downstream's Required Context listed the outputs of Tasks 3 and 4. Dispatched as authored, it would have marked fifteen questions UNRESOLVED and produced a verdict table that looked complete and carried a plausible tally.

**An upstream that revised itself correctly is exactly why nobody caught it.** Numbering was preserved precisely so downstream declarations stayed valid — which is correct for `Depends On`, and is what made the staleness invisible, because the dependency graph still resolved so nothing looked broken. Every safeguard worked as designed and none covered this: the prerequisite gate passed 6/6, seven coordination flags were routed, the upstream's own record was accurate and detailed, and both sessions were internally consistent. The gap lived *between* the two records.

**For the sender.** Recording the revision in your own Recovery is necessary and not sufficient. Your closeout owes every downstream session a flag naming which **output files are new, by path**, and which downstream **deliverables or questions now depend on them**. "We went from 4 tasks to 6" is not that flag. If you preserved numbering to protect the dependency graph, say so *and* say that Required Context is the thing you did not protect.

**For the receiver.** At the step-zero gate, do not check only that `Depends On` still resolves. Enumerate the upstream's output directory and reconcile it against your own Required Context tables, file by file, asking the question the dependency graph cannot answer: *is there evidence on disk that no task of mine has been told to read?*

**A gate that validates relationships between tasks will not catch a change in the artifacts those tasks produce. When an upstream moves, re-derive both.**

---

## 5. Sweep Sibling Sprints That Closed On or After Your Scaffold Date

This is a third Phase-1 preflight source, alongside the sprint plan's Carried-Forward section and the orchestration's own flag block.

> Sweep sibling sprints whose session closed ON OR AFTER this session's scaffold date. Read their Recovery `Files Modified` and `Key Findings`. For each file they touched that intersects this session's edit set OR any sweep surface a task declares, derive the fact and route it into the affected task files as an orchestrator-measured preflight entry — labelled as such, distinct from an upstream-routed flag.

**Threshold and action, per §6.** The threshold is any intersecting file. The action is to route the derived fact into every affected task file before dispatch, and — where the fact changes a gate's expected value — to restate that expected value in the task file itself, not merely to note the change.

**The two-hop flag model cannot cover this.** It routes flags to their consumer. It does not route situational awareness to a concurrent sibling, and a sprint that closes between your scaffold and your dispatch has changed your inputs without owing you a flag. One sibling closed the same day this session ran and routed all three of its flags correctly, to their genuine consumer, a different sprint. Four material side effects reached no file this session's orchestrator reads:

- a brand-new 186-line reference entering a task's file sweep by design, naming forbidden shell verbs;
- a shipped decision resting on two anchors another task was about to edit, one of which it then deleted;
- a landed edit changing a cross-sprint content grep gate's expected value from 1 to 0;
- a reciprocal control that pre-answered part of this session's own gate.

**The intersection test is not just "files we both edit".** That is what a Cross-Sprint File Touches table already covers. It must include **files a task will only read or sweep** — which is how a brand-new file enters a sweep surface with no shared-edit declaration anywhere. A file nobody declared as shared is exactly the file no existing table lists, so an edit-set-only test is blind to the whole class.

Two supporting practices:

- **State the expected value, not just the command, for a cross-sprint gate.** "1 = not yet landed; 0 = landed" merely records a value. "Expect 0, the sibling landed it" converts it into a gate that can *fail*.
- **Label orchestrator measurements distinctly from routed flags.** A runner treats an upstream flag as validated context not to re-derive, and a sweep that echoes the orchestrator's numbers is not independent.

---

## 6. A "Re-Measure at Dispatch" Instruction Without a Divergence Action Is a No-Op

> [!constraint] It reliably produces a measurement and reliably changes nothing
> ```
> Task 1: <!-- Register rows (projected) — re-measure at dispatch, re-roll if >10% off. -->
> Task 2: <!-- Register rows (projected) — re-measure at dispatch. -->
> Task 3: <!-- Register rows (projected) — re-measure at dispatch. -->
> ```
> The `re-roll if >10% off` clause — the only part naming an **action** — was present on the one task whose projection was accurate, and absent from the two that needed it.

Task 2 duly re-measured, reported `85` against a projected `~45` in its verification block, and proceeded on the wrong budget. It surfaced the gap in `ISSUES` at completion: correct behaviour, far too late to change any decision.

Every re-measure instruction needs all three parts:

| Part | Example |
|---|---|
| The measurement | `re-measure the pull count at dispatch` |
| The **threshold** | `if >10% off the projection` |
| The **action** | `re-roll the token estimate AND the output-file budget derived from it, and report the new figures in your status block before authoring` |

Without the third part the runner has no licence to act, so it does the only thing it can: absorbs the divergence and mentions it at the end.

**When a divergence-action clause exists on some siblings and not others, that is a defect, not a style difference.** Sibling task files are usually written by one pass over one template, so a clause present on one and missing on two is an authoring slip that a reviewer reads as intentional variation. `Grep` the sibling set for the clause and normalize it.

This section binds §1 and §5 of this file, and both carry their threshold and their action inline. A rule that prescribes re-measurement without them would ship the exact defect it records.

---

*Cross-references: [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.3 (re-derive a state-asserting row at scaffold close) and §12.5 (re-measure every gate-bound figure at preflight) — this file covers the surfaces neither reaches; [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4 (reconciling an inherited flag, receiver side); [scaffolding-hygiene-Part-2-DerivationAndParallelism.md](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §16 (the computed write-set intersection §5's sweep extends to read-or-sweep surfaces).*
