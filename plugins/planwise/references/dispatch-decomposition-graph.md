---
description: A scaffold-time declaration is a projection, not a constraint — a task's writable set must span the operation it owns, and the declared dispatch layer is a floor on what can run, never a ceiling. Covers the artifact that absorbs a merge belonging to the merging task's working set, the scaffold-time tell and its three fixes, a "may be absent" flag as a hypothesis to check, dispatching on the dependency graph rather than the layer label, and the two conditions plus three guardrails that gate a cross-layer dispatch. Consult while setting a task's Output set at scaffold time, and at run time whenever a task's dependencies have verified before its declared layer opens.
consult-when: Setting a task's `Output:` set at scaffold time, especially for a merge/dedupe/reconcile task, or deciding at run time whether a task is dispatchable ahead of its declared layer — the absorbing artifact belongs in the merging task's writable set, a "may be absent" flag is a hypothesis to check, and the declared layer is a floor, never a ceiling
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Decomposition Graph — A Scaffold-Time Declaration Is a Projection, Not a Constraint

**Purpose:** A plan's `Output:` sets and dispatch layers are both **computed before any runtime information exists**, and both are conservative by necessity. Read later as constraints rather than as projections, they cost in opposite directions.

**Read this when** you are setting a task's writable set at scaffold time — especially a task whose job is to merge, dedupe, reconcile or cross-reference across a boundary — and at run time when a task's declared dependencies have all verified while its declared layer has not yet opened.

Too narrow a writable set splits one atomic operation across two ownership domains. The runner then cannot finish the operation it was asked to perform. The shortfall surfaces as a *note* rather than an error, which is why it survives review.

Too rigid a reading of the declared layers idles work that is genuinely runnable. A layer label is a scaffold-time projection of when a dependency will likely be satisfied, not an additional constraint.

The common correction: at run time the orchestrator has strictly more information than the scaffold did — which tasks have actually verified, and what each remaining task actually needs. The two halves are one rule because they are the same error in opposite directions. §1–§3 is the projection drawn too tight, and §4–§5 the projection read too rigidly. A reader given only one half learns to distrust one projection and keep trusting the other.

One neighbouring rule points the opposite way on the same lever. [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) is about *run-time contention* — two runners allocating the same identifier, concurrent writers on one object — and its remedy is to forbid the collision. §1–§2 below are about a *scaffold-time decomposition* in which one writer's set is too small for the operation it owns. The remedy there is usually to widen the fence that rule exists to enforce. The boundary is "never two writers" versus "one writer, but give it the whole operation."

## Table of Contents

- [1. The Artifact That ABSORBS a Merge Is Part of the Merging Task's Working Set](#1-the-artifact-that-absorbs-a-merge-is-part-of-the-merging-tasks-working-set)
- [2. The Tell at Scaffold Time, and the Three Fixes](#2-the-tell-at-scaffold-time-and-the-three-fixes)
- [3. A Flag Phrased as a Possibility Triggers a Check, Not a Plan](#3-a-flag-phrased-as-a-possibility-triggers-a-check-not-a-plan)
- [4. Dispatch on the Dependency Graph, Not the Declared Layer](#4-dispatch-on-the-dependency-graph-not-the-declared-layer)
- [5. The Two Conditions That Gate a Cross-Layer Dispatch, and the Three Guardrails](#5-the-two-conditions-that-gate-a-cross-layer-dispatch-and-the-three-guardrails)

---

## 1. The Artifact That ABSORBS a Merge Is Part of the Merging Task's Working Set

> [!constraint] A decomposition that grants write access where the duplicate is discovered but not where it lands has split one atomic operation across two ownership domains
> When a task's job is to merge, dedupe, reconcile, or cross-reference across a boundary, the absorbing artifact is not an incidental neighbour.
>
> WRONG — the dedupe task finds the duplicate, and the canonical entry sits in a sibling's file:
> ```
> Reconcile B  Output: Parts 1c/1d          # Reconcile A owns Parts 1a/1b
>   dedupe → a Part-3 claim restates a Part-2 claim, whose canonical entry is in Part 1b
>   result → a stamp, an "Absorption note" in Part 1d, and an incomplete canonical entry
> ```
> CORRECT — the scaffold widens the writable set to the absorbing artifact:
> ```
> Reconcile B  Output: Parts 1c/1d plus the absorbing Part 1b   (A completes before B dispatches)
>   cross-part dedupe → the canonical entry in Part 1b absorbs the condition in the same pass
> ```

The narrow `Output:` sets were correct contention protection, because two runners writing one register file is the hazard the shared-edit-target rules prevent. The runner's conduct was also correct: it preserved the condition, named the required edit and reported that it could not make it. The register was still incomplete unless a later reader happened to find a note in a different Part. The defect is in the decomposition. Widen the writable set at scaffold time. Do not instruct runners to escalate, and do not loosen fences generally.

---

## 2. The Tell at Scaffold Time, and the Three Fixes

> [!constraint] If the canonical-selection rule can point outside the writable set, it WILL, on some input
> The tell: *a task whose Execution Steps say "the earliest-position id becomes canonical" or "the absorbing entry must take on X", where the absorbing entry can live in a file the task does not list under `Output:`.*
>
> ```
> WRONG — dedupe authority and amend authority split, so the merge cannot complete:
>   Task B  Output: Parts 1c/1d
>           Step:   "for each P3 claim, scan the P1/P2 index — a coinciding
>                    prediction makes the P3 id a dup-of stamp toward the
>                    P1/P2 canonical"
>           Step:   "the canonical entry must absorb any condition it lacks"
>   # The canonical entry is in Part 1a/1b. Task B cannot write there.
>   # Result: a stamp, a note, and an incomplete canonical entry.
>
> CORRECT — one of three, chosen at scaffold time:
>   (a) Widen the writable set: Task B's Output includes the absorbing Parts,
>       and Task A is complete before B dispatches (sequential already, so no race).
>   (b) Declare a handoff block: Task B writes an "amendments owed" table with
>       id, target file, and exact text; a named follow-up task applies it.
>   (c) Invert the split: dedupe as its own task, after BOTH reconcilers, owning
>       every register Part — merges land where they belong in one pass.
> ```
>
> **Option (a) is usually right when the tasks are already sequential** — the ownership fence was protecting against a race that the dependency order had already eliminated.

The scaffold-time review question: *check that every task whose steps can **identify** an amendment can also **apply** it, or names who will.* Keep all three fixes. Two fixes leave a reader without the common case. Dropping option (a)'s sequential caveat turns it into blanket advice to widen writable sets. Check 43 in `scripts/lint_gate_checks_dispatch.py` flags the tell in a task file: an Execution Step that names a write (amend, absorb, stamp) to a path the task's `Output:` field does not name.

---

## 3. A Flag Phrased as a Possibility Triggers a Check, Not a Plan

> [!constraint] "May be absent" is an unverified hypothesis, not a finding
> When an inherited flag says a condition *"may be absent"* from some target, verify it before scheduling remediation around it.
>
> WRONG — schedule the remediation on the flag's word:
> ```
> flag: the condition "may be absent" from the canonical entry
>   → dispatch the absorbing Part's owner → dispatch two sweeps of the "open action item" notes
>   → the substantive check finds the condition already present: nothing was owed
> ```
> CORRECT — read the target first:
> ```
> flag: the condition "may be absent" → read the canonical entry
>   → the condition is present, stated from the opposite side → nothing is scheduled
> ```

This is a claim-freshness rule inside a decomposition rule, and it stays here deliberately. The flag it concerns is the one that *created* the cross-boundary amendment in §1, so a reader who verified the flag first would never have reached the ownership problem. It is the cheaper of the two checks, and it belongs where the expensive one is described. Acting on a hypothesis is expensive, and the three follow-on dispatches are the evidence.

---

## 4. Dispatch on the Dependency Graph, Not the Declared Layer

> [!constraint] The declared layer is the floor on what CAN run, never the ceiling
> A scaffold-time layering is a **conservative topological sort computed before any runtime information exists.** It must assume every task in a layer might be the one another task waits on, because at scaffold time nobody knows which will finish first. At run time the orchestrator has strictly more information.
>
> WRONG — treat the declared layer as a barrier and idle a runnable task:
> ```
> Declared:  L1 = {1, 2, 3} (parallel — disjoint files), L2 = {4} (needs Task 2's landed section number)
> L1 = {1,2,3} → wait for ALL of L1 → dispatch L2={4}
> (Task 4 idles behind Task 1, which it does not depend on)
> ```
> CORRECT — after each verified completion, ask which tasks are now dispatchable:
> ```
> Task 2 verifies → Task 4's Depends On = {2} is satisfied
>                 → Task 4's outputs are disjoint from every running task
>                 → dispatch Task 4 now, concurrent with Task 1
> ```
>
> In the measured case Task 4's actual `Depends On` was Task 2 ALONE, and its three edit targets were disjoint from Task 1's two. Task 4 went out when Task 2 verified, while Task 1 was still executing, and recovered ~1 task's wall-clock at zero risk.

This is protocol-conformant rather than a shortcut. [`../handlers/run.md`](../handlers/run.md) § Step 3.2: Dispatch by Execution Mode chooses a dispatch mode for *"the current dependency layer (tasks whose `Depends On` are all COMPLETE)"*. A reader without that quotation will treat this section as permission to skip layers. With it, the section is the same test applied after every verified completion instead of once per label.

---

## 5. The Two Conditions That Gate a Cross-Layer Dispatch, and the Three Guardrails

> [!constraint] Both conditions, then all three guardrails
> 1. **Every declared dependency is COMPLETE and VERIFIED ON DISK** — not merely "returned COMPLETE". The value Task 4 needed to cite was re-measured from the artifact before Task 4 was briefed with it.
> 2. **No output-file collision with anything still RUNNING** — checked against every running task, not just against the declared layer. The collision test itself is the one [`../handlers/run.md`](../handlers/run.md) § Step 3.2: Dispatch by Execution Mode applies to a layer. `scripts/dispatch_preflight.py overlap` runs it for a candidate task's `Output:` paths against the running tasks.
>
> WRONG — brief the dependent from the status block:
> ```
> Task 2 returns COMPLETE → brief Task 4 with the value Task 2's status block reports → dispatch Task 4
> ```
> CORRECT — verify on disk, test every running task, reconcile, then dispatch:
> ```
> Task 2 returns COMPLETE → re-measure the value from Task 2's artifact
>   → Task 4's outputs are disjoint from every RUNNING task → reconcile Recovery → dispatch Task 4
> ```
>
> - **Never on an unverified return.** The whole gain rests on the dependency being *verified*, and a `COMPLETE` status is not acceptance. Dispatching a dependent on a status block alone converts a wall-clock saving into a corrupted output chain.
> - **Never past a file collision.** Where a declared layer exists to serialize a *file collision* rather than a data dependency, this does not apply — the collision is the constraint and the label is load-bearing.
> - **Recovery is still reconciled before the new dispatch.** [`../handlers/run.md`](../handlers/run.md) § Step 3.3: Post-Task Update holds the reconcile-before-dispatch order. That rule protects against compaction, and it applies to a frontier-based dispatch exactly as to a layer-based one.

The gain is **modest and real** — one task's wall-clock on a six-task session, with no change to any artifact, gate, or verification. Overstating it invites a reader to trade the guardrails for it. The declared layering *looks* authoritative, because the orchestration prints it as a plan. Treating a scaffold-time projection as a runtime constraint is a habit that costs a little on every delegated session. The first guardrail is the principle [`verify-verdict-source.md`](verify-verdict-source.md) §4 states about batch acceptance. It is restated here because *when to dispatch* is the moment the orchestrator is deciding. [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17.4 states the per-task acceptance gate it rests on.

---

*Cross-reference: [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) (never two writers — the opposite direction on the same lever) · [`../handlers/run.md`](../handlers/run.md) Step 3.2, Step 3.3 · [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) (the DELEGATED dispatch loop) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17 (parallel-layer derivation at scaffold time) · [`verify-verdict-source.md`](verify-verdict-source.md) §4 · [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §5 (an inherited flag is a claim until the destination is read)*
