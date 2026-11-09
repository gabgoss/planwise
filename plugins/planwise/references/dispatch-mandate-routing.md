---
description: A promise with no gate step is a preference, and an artifact its consumer cannot reach was not delivered. Covers the numbered gate step every pre-action constraint requires, why the mandate-to-gate gap is invisible and emphasis is not the fix, gates that always or never fire, the three obligations that make a repair reachable by its consumer, why a repair is uniquely exposed, and the count-mismatch tell at closeout. Consult while writing a mandate into an orchestration's prose, flag block or Binding Constraints, while authoring a pre-dispatch gate, and whenever a session produces an artifact outside its planned task list.
consult-when: Writing a mandate into an orchestration's prose, flag block or Binding Constraints, authoring a pre-dispatch gate, or producing an artifact outside the planned task list — every mandate gets a numbered gate step stating the passing observation, a gate must be able to both fail and pass, and a repair reaches its consumer only by explicit path, a stated precedence rule, and updated counts
paths: {planwise_root}/{plans_dir}/**
---
# Dispatch Mandate Routing — A Promise With No Gate Is a Preference; An Unrouted Artifact Is Invisible

**Purpose:** Two failures share one shape: work that was correctly *identified* and never *wired into the thing that consumes it*. §1–§3 cover a *mandate* nobody wired into a gate. §4–§6 cover an *artifact* nobody wired into a consumer. Both are one authoring failure, so they are one rule.

**Read this when** you write a mandate into an orchestration's prose, flag block or Binding Constraints; when you author or review a pre-dispatch gate; and whenever a session produces an artifact outside its planned task list — a repair, a hotfix, a supplementary finding.

Both gaps are invisible from either side alone. The flag block reads as handled, and the gate reads as reasonable. Only the *join* exposes the gap: for each mandate, which step tests it? Nothing in the normal authoring or review flow performs that join. Likewise, a closeout checklist asks *"did the work get done?"*, and an artifact on disk with verified content passes it. The check misses that an artifact exists *for someone*, and that someone was addressed by a selector written before the artifact had a name.

Two neighbouring rules own adjacent machinery. [`../handlers/run.md`](../handlers/run.md) Step 1.1a owns the receiving orchestrator's flag preflight and its routing table, and §1's stamp is written there. [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 owns re-deriving the *documentation* surfaces a roster change invalidates. §4 below covers the *consumer's selector*, which no documentation sweep reaches.

## Table of Contents

- [1. Every Constraint That Must Hold Before an Action Requires a Numbered Step in the Gate That Performs That Action](#1-every-constraint-that-must-hold-before-an-action-requires-a-numbered-step-in-the-gate-that-performs-that-action)
- [2. Why the Gap Is Invisible, and Why Emphasis Is Not the Fix](#2-why-the-gap-is-invisible-and-why-emphasis-is-not-the-fix)
- [3. A Gate That Always Fires and a Gate That Never Fires Are the Same Defect](#3-a-gate-that-always-fires-and-a-gate-that-never-fires-are-the-same-defect)
- [4. A Repair Is Not Delivered Until Its Consumer Can Reach It](#4-a-repair-is-not-delivered-until-its-consumer-can-reach-it)
- [5. Why a Repair Is Uniquely Exposed, and What Hardens Against It](#5-why-a-repair-is-uniquely-exposed-and-what-hardens-against-it)
- [6. The Tell Is a Count Mismatch Between What Exists and What Is Claimed](#6-the-tell-is-a-count-mismatch-between-what-exists-and-what-is-claimed)

---

## 1. Every Constraint That Must Hold Before an Action Requires a Numbered Step in the Gate That Performs That Action

**A constraint nobody tests is documentation of an intention.** An emphatic, correct and precedented mandate with no gate step can be complied with zero times.

> [!constraint] The step must name the artifact it inspects and the observation that passes it
> WRONG — the gate step states the activity:
> ```
> Pre-dispatch gate, step 3: route the flags
> ```
> CORRECT — the gate step states the passing observation:
> ```
> Pre-dispatch gate, step 3: every flag row carries a `✅ ROUTED {date} into {file} {section}` stamp
> ```

1. For each mandate in an Orchestration's prose, flag block, or Binding Constraints, write the gate step or delete the mandate.
2. State the passing observation, not the activity.
3. Give the gate a recorded status line, so a resumed or handed-over session can tell whether it ran.
4. Check that the test can fail and can pass on realistic inputs (§3).

**The review rule is to perform the join in both directions.** For each prose mandate, name the enforcing step or report it. For each gate step, confirm its test could return a different answer than the one it always returns.

**Which hop writes the stamp.** The receiving orchestrator writes it at Phase-1 READ, when it routes each flag into task files and spawn prompts. It records the stamp in the routing table its flag preflight keeps in Recovery ([`../handlers/run.md`](../handlers/run.md) Step 1.1a — one row per flag, with a Disposition column). A sender never writes into a downstream task file. [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §2 gives the two-hop ownership, and §5 gives why a sender cannot verify its own delivery.

The flag-table template carries the `Routed` column and its stamp (`templates/orchestration.md`). `scripts/lint_gate_checks_dispatch.py` Check 47 reports a coordination-flag row with no routed stamp.

---

## 2. Why the Gap Is Invisible, and Why Emphasis Is Not the Fix

Prose and gates are authored in different passes and by different reflexes. Writing the constraint is the moment of insight, and articulating a risk *feels* like handling it. Writing the gate step is bookkeeping, done later against a mental model of "what could go wrong at dispatch" that no longer includes the thing already written down.

> [!practice] Answer an ignored mandate with a gate step, not stronger wording
> WRONG — strengthen the wording of a mandate that was already emphatic:
> ```
> "This is the most important thing in this block."  → add bold, add MUST, repeat it
> ```
> CORRECT — add the gate step and the stamp column, then perform the routing:
> ```
> gate step + `ROUTED` stamp column → route the flags now → the next session inherits done work, not a promise
> ```

**Emphasis was not the missing ingredient, and adding more would not have helped.** Three sentences of gate step plus a stamp column closed the gap.

This is not an accusation of carelessness. The two passes are separated by design. A careful author is exactly as exposed, because the instinct on discovering an ignored mandate is to strengthen its wording.

---

## 3. A Gate That Always Fires and a Gate That Never Fires Are the Same Defect

**Neither carries information.** A gate that drops a clause of its mandate never fires on what that clause covers. A gate whose shape does not match its subject fires on compliant output.

> [!constraint] Match the test's shape to the thing it measures
> WRONG — a two-sided deviation test against a one-sided cap:
> ```
> "compare against the ~600-line budget each task declares; a deviation >20% is a review signal"
> # the tasks declare a cap (≤ 600 lines); a compliant 420-line output is −30% and trips the gate
> ```
> CORRECT — a one-sided test for a cap, dry-run against known-bad and known-good input:
> ```
> output lines ≤ the declared 600-line cap → pass; above it → fail
> dry run: an output above the cap fails, and the compliant 420-line output passes
> ```

**Use a one-sided test for a cap and a two-sided test for a budget.** Dry-run it against known-bad and known-good input, and confirm the two results differ. A gate only ever exercised against clean input has never been shown to discriminate.

A two-sided test against a one-sided cap has the *form* of a check but fires on compliant output, so it trains its reader to wave it through. It arrives looking like a reasonable tolerance band, which is why the worked figure stays in the rule. This section belongs beside §1 because it is about the *join* between a mandate and a working step. A gate that cannot discriminate is the same absence wearing a check mark. The instrument-construction mismatches — a command whose mechanism differs from its claim — are [`gate-command-semantics.md`](gate-command-semantics.md) §10.8 and §10.9.

---

## 4. A Repair Is Not Delivered Until Its Consumer Can Reach It

**Producing the artifact is step 1 of 3.** A repair dispatch can run, verify clean, and hold a finding present in no other output, and still be unreachable. The consumer's Required Context selector was written before the repair had a name.

> [!constraint] Route a repair by explicit path, with a precedence rule and corrected counts
> WRONG — rely on the consumer's existing glob:
> ```
> | 1 | ../{upstream-session}/Outputs/…-0{1..9}-Hits*.md (nine sweep outputs) |
> # cannot match …-12-DeltaReSweep.md: the `0` prefix excludes a two-digit index, and `-Hits*` excludes the name
> ```
> CORRECT — add the repair by explicit path, state which row wins, and fix every count:
> ```
> | 2 | ../{upstream-session}/Outputs/…-12-DeltaReSweep.md (repair) |
> where a Task 12 row and a Task 1/3/10 row cover the same `file:line`, the Task 12 row wins — count the pair as ONE hit
> "the eleven outputs" → "the twelve outputs"; update `Depends On`, the prerequisite line, the merge step, the token subtotal
> ```

The three obligations:

1. **Add the repair to the consumer's Required Context by explicit path.** Never rely on an existing glob, which was written before the file had a name.
2. **State the precedence rule.** A repair usually overlaps the thing it repairs, so the consumer holds two rows for the same `file:line`. Say which wins and why. Otherwise the consumer treats the pair as a duplicate, or as two independent hits that inflate its own counts.
3. **Update every enumeration and count that now contradicts it** — "the eleven outputs", `Depends On`, the prerequisite line, per-task subtotals. A stale count reads as authoritative closure.

**Two reasons, not one, is the point.** One reason reads as a near-miss that better naming would have solved. Two show the selector could not have matched any repair. When the repair spans two consumer schemas, add an explicit row to *both* consuming task files.

`scripts/outputs_coverage.py named --side producer --outputs <Outputs dir> --tasks <consuming task files>` checks obligation 1: every file in the `Outputs/` listing must be named by a Required Context row.

The third obligation meets [`dispatch-edit-surface-sweep.md`](dispatch-edit-surface-sweep.md) on stale counts, and the two do not substitute for each other. Here the count is stale because a *new artifact* exists. There it is stale because the *locator* was too narrow.

---

## 5. Why a Repair Is Uniquely Exposed, and What Hardens Against It

**The consumer's selector is a snapshot of the moment it was authored.** A planned deliverable is named in the consumer's Required Context at scaffold time, covered by the counts in prose, and discoverable. A repair is, by definition, **unplanned**: it did not exist when the selector was written, the prose actively *excludes* it, and the consumer finds it only if someone routes it.

> [!constraint] Every artifact created after the selector was authored is routed by hand
> WRONG — trust a closure that was true when written:
> ```
> "the eleven outputs are the input"   # correct at scaffold time; a false closure once a twelfth exists
> ```
> CORRECT — the producer routes the late artifact and corrects the closure:
> ```
> twelfth file created → producer adds its Required Context row → "the twelve outputs are the input"
> ```

**A consumer obeying its brief faithfully is precisely the one that misses the repair.** That is why the obligation falls on the producer rather than on the reader. Any out-of-band artifact inherits this — a hotfix patch alongside a planned release set, an extra migration outside the numbered sequence, a supplementary finding appended after a report's index was written, an additional test file outside a runner's glob.

---

## 6. The Tell Is a Count Mismatch Between What Exists and What Is Claimed

**A count mismatch is greppable at closeout.** Check it whenever a session produced anything outside its planned task list. The unit is files on disk in the session's `Outputs/` folder. Count them, then `Grep` the consuming task files for the number they claim.

> [!constraint] Twelve files on disk and "eleven outputs" in three places is the tell
> WRONG — close out on the record of the expansion alone:
> ```
> scope expansion recorded in Recovery and the Summary → closeout passes
> # 12 files in Outputs/; "eleven outputs" in three separate places
> ```
> CORRECT — compare the file count with every count claim:
> ```
> python -B "{plugin_root}/scripts/outputs_coverage.py" count --outputs <session>/Outputs --tasks <consuming task files>
> # each count claim must equal the number of files in Outputs/
> ```

The closeout question has two parts. If a session performed a scope expansion, its closeout asks *"is the expansion recorded?"* (accountability to reviewers). It also asks *"is the expansion's **output** wired into whoever consumes this session?"* (the work actually functioning). Recording the expansion in Recovery and the Summary does not make the artifact reachable.

The documentation surfaces a roster change invalidates — counts, rosters, invocation lists — are derived by [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4. This tell is the closeout-time check that the derivation was run for the artifact the session did not plan.

---

*Cross-reference: [`../handlers/run.md`](../handlers/run.md) Step 1.1a (the flag preflight and its routing table) · [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §5 (a flag the sender says it delivered is a claim; only the destination file is evidence) · [`scaffolding-hygiene-Part-2-DerivationAndParallelism.md`](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §13.4 · [`gate-command-semantics.md`](gate-command-semantics.md) §10.8, §10.9 · [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §1 (the positive control — a gate must be shown to fire) · [`dispatch-edit-surface-sweep.md`](dispatch-edit-surface-sweep.md) (stale counts from a narrow locator)*
