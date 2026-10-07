---
description: A promise with no gate step is a preference, and an artifact its consumer cannot reach was not delivered. Covers the numbered gate step every pre-action constraint requires, why the mandate-to-gate gap is invisible and emphasis is not the fix, gates that always or never fire, the three obligations that make a repair reachable by its consumer, why a repair is uniquely exposed, and the count-mismatch tell at closeout. Consult while writing a mandate into an orchestration's prose, flag block or Binding Constraints, while authoring a pre-dispatch gate, and whenever a session produces an artifact outside its planned task list.
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Mandate Routing — A Promise With No Gate Is a Preference; An Unrouted Artifact Is Invisible

**Purpose:** Two failures with one shape: work that was correctly *identified* and never *wired into the thing that consumes it*. In one, a sprint diagnosed its own largest risk with unusual precision, named the remedy, marked it *"the most important thing in this block"* — and the pre-dispatch gate that would enforce it had two steps, neither of which was the routing pass. Measured: **0 of 4** task files carried the section the flag block demanded. In the other, an approved repair dispatch ran, verified clean, and recovered the session's single most on-point hit — into a filename that the consuming task's Required Context glob **structurally excludes**.

**Read this when** you write a mandate into an orchestration's prose, flag block or Binding Constraints; when you author or review a pre-dispatch gate; and whenever a session produces an artifact outside its planned task list — a repair, a hotfix, a supplementary finding.

Both are invisible from either side taken alone. Read the flag block and the risk is handled; read the gate and it looks reasonable. Only the *join* — for each mandate, which step tests it? — exposes the gap, and nothing in the normal authoring or review flow performs that join. Likewise, a closeout checklist asks *"did the work get done?"* and is satisfied by an artifact existing on disk with verified content. That check passes. What it misses is that an artifact only exists *for someone*, and the someone was addressed by a selector written before the artifact had a name.

The two halves are one rule on purpose. §1–§3 are a *mandate* nobody wired into a gate; §4–§6 are an *artifact* nobody wired into a consumer. Both are the same authoring failure — the thing was produced and never connected — and the incident behind §1 is itself an unrouted-flag failure. Two neighbouring rules own adjacent machinery. [`../handlers/run.md`](../handlers/run.md) Step 1.1a owns the receiving orchestrator's flag preflight and its routing table; §1's stamp is written there. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 owns re-deriving the *documentation* surfaces a roster change invalidates; §4 below is about the *consumer's selector*, which no documentation sweep reaches.

## Table of Contents

- [1. Every Constraint That Must Hold Before an Action Requires a Numbered Step in the Gate That Performs That Action](#1-every-constraint-that-must-hold-before-an-action-requires-a-numbered-step-in-the-gate-that-performs-that-action)
- [2. Why the Gap Is Invisible, and Why Emphasis Is Not the Fix](#2-why-the-gap-is-invisible-and-why-emphasis-is-not-the-fix)
- [3. A Gate That Always Fires and a Gate That Never Fires Are the Same Defect](#3-a-gate-that-always-fires-and-a-gate-that-never-fires-are-the-same-defect)
- [4. A Repair Is Not Delivered Until Its Consumer Can Reach It](#4-a-repair-is-not-delivered-until-its-consumer-can-reach-it)
- [5. Why a Repair Is Uniquely Exposed, and What Hardens Against It](#5-why-a-repair-is-uniquely-exposed-and-what-hardens-against-it)
- [6. The Tell Is a Count Mismatch Between What Exists and What Is Claimed](#6-the-tell-is-a-count-mismatch-between-what-exists-and-what-is-claimed)

---

## 1. Every Constraint That Must Hold Before an Action Requires a Numbered Step in the Gate That Performs That Action

> [!constraint] The step must name the artifact it inspects and the observation that passes it
> A sprint's Orchestration said, of task files authored against a plugin tree that had since been refactored and shipped:
>
> > *"Your task files were authored against the pre-refactor tree and carry the same staleness the first session had to repair before it could dispatch. **This is the most important thing in this block.** … Read it at Phase-1 and re-measure your Required Context before dispatching."*
>
> The block's own header carried the routing instruction — *"route each into the named task's file or spawn prompt at Phase-1 READ."* The diagnosis was right, the remedy was right, and the plan had a worked precedent: a sibling sprint had performed exactly that pass at dispatch and recorded *"Status of the dispatch-time repair pass: COMPLETE."* The pre-dispatch gate had **two steps** — confirm the external release gate, and `wc -l` some files. The routing pass was in neither: no per-flag routing checklist, no `ROUTED` stamp column, no closeout check that routing had happened. Measured: **0 of 4** task files carried a `## Pre-Known Cross-Task Coordination Flags` section.
>
> ```
> 1. For each mandate in an Orchestration's prose, flag block, or Binding
>    Constraints — write the gate step, or delete the mandate. A constraint
>    nobody tests is documentation of an intention.
> 2. State the passing OBSERVATION, not the activity.
>    "Every flag row carries a `✅ ROUTED {date} into {file} {section}` stamp"
>      is checkable;
>    "route the flags" is not.
> 3. Give the gate a recorded status line so a resumed or handed-over session
>    can tell whether it ran.
> 4. Check that the test CAN FAIL and CAN PASS on realistic inputs.
> ```

**A constraint nobody tests is documentation of an intention**, and the `0 of 4` figure is what makes that a measurement rather than a worry: the mandate was emphatic, correct, precedented, and complied with zero times.

**The review rule is to perform the join in both directions.** For each prose mandate, name the enforcing step or report it. For each gate step, confirm its test could return a different answer than the one it always returns.

**Which hop writes the stamp.** Coordination flags travel two hops: the sender delivers a flag to the downstream orchestration file only, and the receiving orchestrator routes it into task files and spawn prompts at Phase-1 READ. The stamp is written at the *second* hop, by the receiving orchestrator, in the routing table its flag preflight records in Recovery ([`../handlers/run.md`](../handlers/run.md) Step 1.1a — one row per flag, with a Disposition column). A sender never writes into a downstream task file, and a `ROUTED` stamp on the sender's side would assert a delivery the sender cannot verify.

---

## 2. Why the Gap Is Invisible, and Why Emphasis Is Not the Fix

> [!practice] Prose and gates are authored in different passes and by different reflexes
> Writing the constraint is the moment of insight — you have just understood the risk, and articulating it *feels* like handling it. Writing the gate step is bookkeeping, done later against a mental model of "what could go wrong at dispatch" that no longer includes the thing you already wrote down.
>
> Hence the corollary. The flag block here was already emphatic (*"the most important thing in this block"*); **emphasis was not the missing ingredient and adding more would not have helped.** What closed it was three sentences of gate step plus a stamp column — and, separately, actually performing the routing so the next session inherits done work rather than a promise.

This is not an accusation of carelessness. The two passes are separated by design, and a careful author is exactly as exposed, because the instinct on discovering an ignored mandate is to strengthen its wording.

---

## 3. A Gate That Always Fires and a Gate That Never Fires Are the Same Defect

> [!constraint] Neither carries information
> Both instances are from the same sprint as §1:
>
> ```
> Dropped clause — a Binding Constraint required "BOTH project Grep gates must
> return empty" for identifier isolation. The implementing task shipped ONE
> merged Grep, silently dropping the hyphen-less clause that exists precisely
> because the citation-spelling pattern misses identifiers glued into filenames.
>
> Unsatisfiable shape — the inter-dispatch size gate said "compare against the
> ~600-line budget each task declares; a deviation >20% is a review signal."
> The tasks declare a CAP (≤ 600 lines), not a budget. A fully compliant
> 420-line output is −30% and trips the gate — a test that fires on the
> expected case.
> ```
>
> **Match the test's shape to the thing it measures: one-sided for a cap, two-sided for a budget.** Dry-run it against known-bad and known-good input and confirm the two differ — a gate only ever exercised against clean input has never been shown to discriminate.

A two-sided deviation test against a one-sided cap has the *form* of a check but fires on compliant output, so it trains its reader to wave it through. The case arrives looking like a reasonable tolerance band, which is why the worked figure stays in the rule. This section belongs beside §1 rather than in a rule about how a gate's instrument is built: it is about the *join* between a stated mandate and the existence of any step at all, and a gate that cannot discriminate is the same absence wearing a check mark. The instrument-construction mismatches — a command whose mechanism differs from its claim — are [`verification-task-authoring.md`](verification-task-authoring.md) §10.8 and §10.9.

---

## 4. A Repair Is Not Delivered Until Its Consumer Can Reach It

> [!constraint] Producing the artifact is step 1 of 3
> A concurrent session edited four files mid-sweep, so parts of an eleven-task inventory described a tree state that no longer existed. The approved fix was a twelfth dispatch — a bounded delta re-sweep of just those four files against a hash-pinned window. It ran, verified clean, and recovered the session's single most on-point hit, present in **no other output**. The consuming session's task file declared its inputs as:
>
> ```
> | 1 | ../{upstream-session}/Outputs/…-0{1..9}-Hits*.md (nine sweep outputs) |
> ```
>
> The repair's filename ends `-12-DeltaReSweep.md` and cannot match `0{1..9}-Hits*` for two independent reasons: the `0` prefix excludes a two-digit index, and `-Hits*` excludes the `-DeltaReSweep` name. The task's notes reinforced the closure — *"the eleven outputs are the input"* and *"Do NOT re-read the plugin trees."* So the consumer would have read eleven files, correctly believed it had everything, and been *unable* to discover the twelfth: forbidden from re-reading the trees, and given a glob that structurally excludes the repair.
>
> ```
> 1. Add it to the consumer's Required Context BY EXPLICIT PATH — never rely
>    on an existing glob, which was written before the file had a name.
> 2. State the precedence rule. A repair usually OVERLAPS the thing it repairs,
>    so the consumer will hold two rows for the same file:line. Say which wins
>    and why, or the consumer treats the pair as a duplicate — or worse, as two
>    independent hits, inflating its own counts.
> 3. Update every enumeration and count that now contradicts it — "the eleven
>    outputs", `Depends On`, the prerequisite line, per-task subtotals.
>    A stale count reads as authoritative closure.
> ```

Two reasons, not one, is the point: one reason reads as a near-miss that better naming would have solved; two show the selector could not have matched any repair.

**What applying it looked like.** An explicit Required Context row in *both* consuming task files (forward-mandate rows to one, counter-inventory rows to the other, since the repair spanned both schemas), a `[!constraint]` block stating *"where a Task 12 row and a Task 1/3/10 row cover the same `file:line`, the Task 12 row wins — and count the pair as ONE hit, not a duplicate"*, and edits to the `Depends On` field, the session prerequisite line, the merge step, and the token subtotal.

The third obligation meets [`dispatch-edit-surface-sweep.md`](dispatch-edit-surface-sweep.md) on stale counts, and the two do not substitute for each other: here the count is stale because a *new artifact* exists; there because the *locator* was too narrow.

---

## 5. Why a Repair Is Uniquely Exposed, and What Hardens Against It

> [!constraint] The consumer's selector is a snapshot of the moment it was authored
> | | Planned deliverable | Repair artifact |
> |---|---|---|
> | Named in consumer's Required Context | yes, at scaffold time | **no — it did not exist then** |
> | Covered by an index/count in prose | yes ("the eleven outputs") | no — and the prose actively *excludes* it |
> | Discoverable by the consumer | yes | only if someone routes it |
>
> A repair is, by definition, **unplanned**, and the surrounding language hardens against it: *"the eleven outputs are the input"* was **correct when written** and becomes a false closure the moment a twelfth exists. **A consumer obeying its brief faithfully is precisely the one that misses the repair.** Every artifact created after the selector was authored must be routed by hand.

Together, those two sentences are the reason the obligation falls on the producer rather than on the reader. Any out-of-band artifact inherits this — a hotfix patch alongside a planned release set, an extra migration outside the numbered sequence, a supplementary finding appended after a report's index was written, an additional test file outside a runner's glob.

---

## 6. The Tell Is a Count Mismatch Between What Exists and What Is Claimed

> [!constraint] Twelve files on disk, "eleven outputs" in three separate places
> That mismatch **is greppable at closeout** and is worth checking explicitly whenever a session produced anything outside its planned task list: count the files in the session's `Outputs/` folder, then `Grep` the consuming task files for the number they claim.
>
> The closeout question has two parts. If a session performed a scope expansion, its closeout must ask not only *"is the expansion recorded?"* (accountability to reviewers) but *"is the expansion's **output** wired into whoever consumes this session?"* (the work actually functioning). Recording the expansion in Recovery and the Summary — which was done — would not have made the artifact reachable.

The documentation surfaces a roster change invalidates — counts, rosters, invocation lists — are derived by [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4. This tell is the closeout-time check that the derivation was run for the artifact the session did not plan.

---

*Cross-reference: [`../handlers/run.md`](../handlers/run.md) Step 1.1a (the flag preflight and its routing table) · [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §5 (a flag the sender says it delivered is a claim; only the destination file is evidence) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 · [`verification-task-authoring.md`](verification-task-authoring.md) §10.8, §10.9 · [`verification-gate-evidence.md`](verification-gate-evidence.md) §1 (the positive control — a gate must be shown to fire) · [`dispatch-edit-surface-sweep.md`](dispatch-edit-surface-sweep.md) (stale counts from a narrow locator)*
