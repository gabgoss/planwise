---
description: A scaffold-time declaration is a projection, not a constraint — a task's writable set must span the operation it owns, and the declared dispatch layer is a floor on what can run, never a ceiling. Covers the artifact that absorbs a merge belonging to the merging task's working set, the scaffold-time tell and its three fixes, a "may be absent" flag as a hypothesis to check, dispatching on the dependency graph rather than the layer label, and the two conditions plus three guardrails that gate a cross-layer dispatch. Consult while setting a task's Output set at scaffold time, and at run time whenever a task's dependencies have verified before its declared layer opens.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Decomposition Graph — A Scaffold-Time Declaration Is a Projection, Not a Constraint

**Purpose:** A plan's `Output:` sets and dispatch layers are both **computed before any runtime information exists**, and both are conservative by necessity. Read later as constraints rather than as projections, they cost in opposite directions.

**Read this when** you are setting a task's writable set at scaffold time — especially a task whose job is to merge, dedupe, reconcile or cross-reference across a boundary — and at run time when a task's declared dependencies have all verified while its declared layer has not yet opened.

Too narrow a writable set splits one atomic operation across two ownership domains. The runner is then structurally unable to finish the operation it was asked to perform — and the shortfall surfaces as a *note* rather than an error, which is why it survives review. One such split cost three follow-on dispatches, two of which existed only to sweep the now-false "open action item" assertions the first report had correctly written into two other artifacts. The substantive check then found the condition was **already present**: the entire cost bought a stamp and three status rewrites.

Too rigid a reading of the declared layers idles work that is genuinely runnable. A layer label is a scaffold-time projection of when a dependency will likely be satisfied, not an additional constraint — and the delegated protocol's own dispatch test is stated over `Depends On`, not over the label. Treating the projection as a barrier costs a little on every delegated session, and it is a habit rather than an incident.

The common correction: at run time the orchestrator has strictly more information than the scaffold did — which tasks have actually verified, and what each remaining task actually needs. The two halves are one rule because they are the same error in opposite directions: §1–§3 is the projection drawn too tight, §4–§5 the projection read too rigidly. A reader given only one half learns to distrust one projection and keep trusting the other.

One neighbouring rule points the opposite way on the same lever. [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) is about *run-time contention* — two runners allocating the same identifier, concurrent writers on one object — and its remedy is to forbid the collision. §1–§2 below are about a *scaffold-time decomposition* in which one writer's set is too small for the operation it owns, and the remedy is usually to widen the fence that rule exists to enforce. The boundary is "never two writers" versus "one writer, but give it the whole operation."

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
> A discovery sprint split claim reconciliation across two sequential runners along part-of-origin lines: Reconcile A merged binder Parts 1+2 into register Parts 1a/1b; Reconcile B merged Part 3 into Parts 1c/1d and ran cross-part dedupe against A's one-line claim index. Each task's `Output:` named only its own Parts, and the spawn prompts enforced that — correctly, since two runners writing the same register file is the contention hazard the shared-edit-target rules exist to prevent. Cross-part dedupe then did exactly what it was designed to do: it found a Part-3 claim restating a Part-2 claim, and the earliest-binder-position rule made the Part-2 id canonical. An upstream flag had anticipated this specific merge and attached a condition:
>
> > *"Do NOT drop the Part-3 instance outright — its subscription-tier conditionality may be absent from the Part-2 claims, in which case the canonical entry must absorb that condition rather than lose it."*
>
> The canonical entry lived in Part 1b — Reconcile A's output, **outside Reconcile B's writable set.** The runner did the best available thing: stamped the merge, preserved the condition verbatim in an "Absorption note" in its own Part 1d, named the required edit precisely, and reported that it could not make it. **That is model behaviour under the constraint. It is also a register whose canonical entry was incomplete unless a downstream designer happened to read a note in a different Part.**

The narrow `Output:` sets were correct contention protection, and the runner's conduct was correct under them. The defect is in the decomposition: the fix is to widen the writable set at scaffold time, not to instruct runners to escalate, and not to loosen fences generally.

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

The scaffold-time review question: *check that every task whose steps can **identify** an amendment can also **apply** it, or names who will.* Two fixes leave a reader without the common case; dropping option (a)'s sequential caveat turns it into blanket advice to widen writable sets.

---

## 3. A Flag Phrased as a Possibility Triggers a Check, Not a Plan

> [!constraint] "May be absent" is an unverified hypothesis, not a finding
> When an inherited flag says a condition *"may be absent"* from some target, verify it before scheduling remediation around it. Here the condition was present all along, stated from the opposite side — the target described the fallback from the usage-credits direction while the source described the automatic case from the included-usage direction, the same rule from opposite vantages.
>
> The cost: closing the item took three follow-on dispatches — one to the owner of the absorbing Part to make the substantive check, then two more to sweep the now-false "open action item" assertions the first report had correctly written into two other artifacts — and the substantive check found nothing was owed.

This is a claim-freshness rule sitting inside a decomposition rule, and it stays here deliberately: the flag it concerns is the one that *created* the cross-boundary amendment in §1, so a reader who verified the flag first would never have reached the ownership problem at all. It is the cheaper of the two checks and belongs where the expensive one is described. The section's claim is that acting on a hypothesis is expensive, and the price is the evidence.

---

## 4. Dispatch on the Dependency Graph, Not the Declared Layer

> [!constraint] The declared layer is the floor on what CAN run, never the ceiling
> A scaffold-time layering is a **conservative topological sort computed before any runtime information exists.** It must assume every task in a layer might be the one another task waits on, because at scaffold time nobody knows which will finish first. At run time the orchestrator has strictly more information.
>
> ```
> Declared:  L1 = {1, 2, 3}   (parallel — disjoint files)
>            L2 = {4}         (needs Task 2's landed section number)
>            L3 = {5}
>            L4 = {6}
>
> Task 4's actual `Depends On` is Task 2 ALONE, and its three edit targets are
> disjoint from Task 1's two. Task 2 returned and verified while Task 1 was
> still executing; Task 4 was dispatched at that moment rather than at the
> layer boundary, recovering ~1 task's wall-clock at zero risk.
> ```
>
> ```
> WRONG — treat the declared layer as a barrier and idle a runnable task:
>   L1 = {1,2,3} → wait for ALL of L1 → dispatch L2={4}
>   (Task 4 idles behind Task 1, which it does not depend on)
>
> CORRECT — after each verified completion, ask which tasks are now dispatchable:
>   Task 2 verifies → Task 4's Depends On = {2} is satisfied
>                   → Task 4's outputs are disjoint from every running task
>                   → dispatch Task 4 now, concurrent with Task 1
> ```

This is protocol-conformant rather than a shortcut. The delegated dispatch loop's own test — [`../handlers/run.md`](../handlers/run.md) Step 3.2 — chooses a dispatch mode for *"the current dependency layer (tasks whose `Depends On` are all COMPLETE)"*: it is stated over **`Depends On`**, not over the layer label. A reader without that quotation will treat this section as permission to skip layers; with it, the section is the test applied after every verified completion instead of once per label.

---

## 5. The Two Conditions That Gate a Cross-Layer Dispatch, and the Three Guardrails

> [!constraint] Both conditions, then all three guardrails
> ```
> 1. Every declared dependency is COMPLETE and VERIFIED ON DISK — not merely
>    "returned COMPLETE". The value Task 4 needed to cite was re-measured from
>    the artifact before Task 4 was briefed with it.
> 2. No output-file collision with anything still RUNNING — checked against
>    every running task, not just against the declared layer. This is the same
>    test that decides whether a layer is parallel-eligible at all.
> ```
>
> - **Never on an unverified return.** The whole gain rests on the dependency being *verified*, and a `COMPLETE` status is not acceptance. Dispatching a dependent on a status block alone converts a wall-clock saving into a corrupted output chain.
> - **Never past a file collision.** Where a declared layer exists to serialize a *file collision* rather than a data dependency, this does not apply — the collision is the constraint and the label is load-bearing.
> - **Recovery is still reconciled before the new dispatch.** The reconcile-before-dispatching-the-next-layer rule — [`../handlers/run.md`](../handlers/run.md) Step 3.3 updates Recovery and Current Step and only *then* dispatches the next layer — protects against compaction and applies to a frontier-based dispatch exactly as to a layer-based one.

The gain is **modest and real** — one task's wall-clock on a six-task session, with no change to any artifact, gate, or verification. Overstating it invites a reader to trade the guardrails for it. The reason to record it is that the declared layering *looks* authoritative — it is printed in the orchestration as a plan — and treating a scaffold-time projection as a runtime constraint is a habit that costs a little on every delegated session. The first guardrail is the same principle [`verify-verdict-source.md`](verify-verdict-source.md) §4 states about batch acceptance; it is restated here because *when to dispatch* is the moment the orchestrator is deciding.

---

*Cross-reference: [`parallel-layer-shared-objects.md`](parallel-layer-shared-objects.md) (never two writers — the opposite direction on the same lever) · [`../handlers/run.md`](../handlers/run.md) Step 3.2, Step 3.3 · [`agent-orchestration-delegated.md`](agent-orchestration-delegated.md) (the DELEGATED dispatch loop) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §17 (parallel-layer derivation at scaffold time) · [`verify-verdict-source.md`](verify-verdict-source.md) §4 · [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §5 (an inherited flag is a claim until the destination is read)*
