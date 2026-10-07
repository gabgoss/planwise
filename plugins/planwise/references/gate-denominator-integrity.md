---
description: A coverage or balance gate whose denominator, or whose aggregate observable, comes from the artifact it gates returns accurate numbers that answer a different question than the one asked. Covers the invariant-first substitution table, the false-FAIL and false-PASS directions of an aggregate count over a shared file, absence criteria that deletion satisfies, presence counts that cannot see an unscoped item, balance gates that become inapplicable when a second provenance appears, and the plan-review signatures that catch each before dispatch. Consult when writing or accepting a count, a coverage ratio, a "no X survives" criterion, or an "N in = N out" gate.
paths: {planwise_root}/{plans_dir}/**
---
# Gate Denominator Integrity — a Count Taken From the Artifact Being Gated Is a Tautology Wearing the Costume of a Check

**Purpose:** A gate prints a number, and the number is accurate. The gate still answers a different question than the one asked, because its denominator, or the aggregate it observes, was derived from the wrong side of the property it was meant to protect. Neither direction of the mistake shows in the gate's own output. Both look like a number matching or not matching an expectation.

**Read this when** you are writing or accepting a count, a coverage ratio, an absence criterion (`no X survives`), or a balance gate (`N in = N out`).

This file owns the **denominator and the aggregate**. [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) owns the **pattern**, [`gate-baseline-independence.md`](gate-baseline-independence.md) owns the **base a diff is taken against**, and [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the **input set**. A gate can pass all three of those and still fail here.

## Table of Contents

- [1. Ask What Invariant You Actually Wanted](#1-ask-what-invariant-you-actually-wanted)
- [2. Never Assert an Aggregate Count Over a Shared File](#2-never-assert-an-aggregate-count-over-a-shared-file)
- [3. Take the Denominator From Outside the Artifact](#3-take-the-denominator-from-outside-the-artifact)
- [4. A Balance Gate Is a Statement About Provenance, Not About Rows](#4-a-balance-gate-is-a-statement-about-provenance-not-about-rows)
- [5. Detection at Plan-Review Time](#5-detection-at-plan-review-time)

---

## 1. Ask What Invariant You Actually Wanted

The gate was derived from a convenient observable rather than from the invariant. Three recurring cases show it. In every one, the correct invariant was **not a count**.

| What the gate was trying to assert | Correct invariant |
|---|---|
| "I did not modify the existing text" | **Zero deletions in my own hunk.** Read `git diff --numstat` on my change, or inspect the `^-` lines |
| "my content landed in this file" | **A content grep for a literal I authored**, per file, reported separately |
| "the two copies of this sentence agree" | **Two counts of the same literal**, one per copy, both quoted |

All three are per-hunk or per-content assertions. None is an aggregate over a file that other people also write.

> [!practice] Name the invariant before choosing the instrument
> Write the property in one sentence ("nothing I did removed a line"), then ask which observable that sentence is actually about. A count is a statement about the whole file. A hunk, a literal, or a pair of literals is a statement about your change.

---

## 2. Never Assert an Aggregate Count Over a Shared File

> [!constraint] An aggregate count over a file with more than one writer is mis-specified in both directions
> WRONG — a count over a file that concurrent or additive work legitimately moves:
> ```
> Grep  pattern='plugin_root'  path='handlers/doctor.md'  output_mode='count'   # "MUST be unchanged"  → 10 becomes 11, correct work FAILS
> git diff --name-only -- fileA fileB fileC | wc -l                             # "MUST equal 3"       → siblings supply 2, missing work PASSES
> ```
> The first line is the **false-FAIL** direction. Correct additive work moved the count from 10 to 11, and the gate reported a failure while the protected text was provably byte-identical (`+47/−0`). The second line is the **false-PASS** direction. Under layered dispatch, sibling tasks had already modified two of the three files, so the count reached 3 the moment this task touched the third alone. The gate passed with two thirds of the work absent.
>
> CORRECT — the property itself, scoped to your own change:
> ```
> git diff --numstat -- handlers/doctor.md                                       # my hunk is +47/-0 → the existing gate text is byte-identical
> Grep  pattern='<literal I authored>'  path='fileA'  output_mode='count'        # 1
> Grep  pattern='<literal I authored>'  path='fileB'  output_mode='count'        # 1   ← each file proved separately
> Grep  pattern='<literal I authored>'  path='fileC'  output_mode='count'        # 1
> ```

[`verification-gates.md`](verification-gates.md) §11.1 states the false-FAIL direction for an enumeration (the expected value is derived from the enumeration under test). This section adds the false-PASS direction and the rules below. A rule that shows only the false-FAIL direction teaches runners to loosen gates, which is the opposite of the lesson.

- A "count must be unchanged" gate on a file the work may legitimately add prose to is **mis-specified**. Replace it with a zero-deletions assertion on the author's own hunk. Deletions are what "you modified the existing text" actually means.
- **Never let a file-presence count stand as proof that a task's content landed**, in any plan where more than one task writes the same file. Under layered dispatch on shared handler and reference docs that is the normal case. Prove content by content. [`verification-task-authoring.md`](verification-task-authoring.md) §2 and §10.6 carry the per-unit and input-set forms.
- **When a gate's expected value is stated as `≥ 1`, ask what a regression would look like.** At `≥ 1`, deleting two of three references still passes. `≥ 1` answers "does it exist at all", which is almost never the question after the first landing.
- **A false-failing gate is not the safe direction.** It is as corrosive as a skipped gate, because runners learn to route around it, and the routing-around is silent. Treat a gate that fires on correct work as a defect **in the gate**. Fix it at the point of discovery. Do not explain it away in a status block.

The failure is systematic rather than incidental. A well-written new stage that says "this is distinct from X" must mention X, so it always moves X's count. **The better the prose, the more reliably the gate false-fails.**

---

## 3. Take the Denominator From Outside the Artifact

> [!constraint] A denominator counted in your own output cannot detect what you never scoped
> Two failure shapes, stated precisely:
> - An **absence** criterion (`no X survives`) counts markers in your own output. A marker is a *record that work is outstanding*. Deleting the record and doing the work are byte-identical to a grep, and deletion is strictly cheaper.
> - A **presence** count (`N sections for N surfaces`) counts items in your own output against a number derived from the same decomposition that produced them. It is a tautology wearing the costume of a check. It can detect a *duplicate* or a *dropped* item. It structurally **cannot** detect an item nobody ever scoped.

The two fail together in practice. One consolidation criterion read *"No `[stability: map pending]` markers survive."* The same session's presence count read 10/10 ("every surface in the map appears exactly once") while the authoritative external matrix read 34/35. One surface was never scoped, so it appears in no output, and no sweep over the outputs can miss it.

The placeholder distribution across three upstream outputs shows why the absence criterion was unsafe:

| Upstream output | Surfaces | Placeholders emitted |
|---|---|---|
| Output 1 | 2 | 3 |
| Output 2 | 5 | 6 |
| Output 3 | **3** | **1** |

Every runner honoured its own task spec, and nothing in any single output was wrong. The consolidator could still satisfy `no X survives` **by deleting one line**, ship two surfaces with no note at all, and pass every other mechanical gate it had: line count, byte count, surface-coverage count, heading sweep. The 3 / 6 / 1 ratio is the evidence that per-runner correctness does not compose into whole-set correctness.

Five operational rules follow:

- **Never let an absence criterion stand alone.** Pair every `no X survives` with a positive criterion quantified over the full item set: *"all N items carry a filled Y."* Absence bounds the cleanup. Presence bounds the work. The absence half is the cheap mechanical check, and the presence half is the one that means something.
- **Reconcile coverage against the authoritative external reference** (the matrix, the schema, the map), never against the count your own decomposition produced. If the external set is outside every task's Required Context, that is a **scaffolding defect**. The reconciliation has no owner, and the gap surfaces at the join or not at all.
- **Require an explicit statement where data is absent.** "No source row exists for this item" is a filled note. A blank, or a silently dropped line, is indistinguishable from work not done. Make absence *say* absence.
- **Never emit a stub to satisfy a sweep.** A placeholder section makes a coverage grep read as covered and turns a visible gap into an invisible one. Record the gap as a gap, with its disposition, and route it downstream.
- **Sweep the marker distribution across the batch before dispatching the join.** Counting placeholders per output takes one count per file and exposes the ratio that shows a downstream criterion is unsafe. It is cheap at the batch gate and unrecoverable after the join. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) owns the batch-gate checks this one joins.

One small self-referential trap sits in the same family: **a prose claim about a grep result is itself grep-visible.** A governance sentence asserting that no `map pending` string survives will itself contain the string. Reword the claim to be true. Do not mutilate the artifact to fit a naive pattern. [`verification-task-authoring.md`](verification-task-authoring.md) §8.1 carries the scrub rule for the same token.

---

## 4. A Balance Gate Is a Statement About Provenance, Not About Rows

`N in = N out` is shorthand for *"every row in the output traces to exactly one row of this specific input set."* The moment a second provenance appears, meaning rows that belong in the output but were never in that input set, the equality is not *violated*. It is **inapplicable**. Folding the new class in guarantees a false failure, and no arithmetic rescues it.

> [!constraint] Scope the equality to the sourced class, and report the other class separately
> A balance gate was sound and had been dry-run to FAIL against doctored input. Then two claims minted at reconcile time (ids `CLM-{n}`, not `def:` rows) had to be dispositioned into the same Log. Adding them made `N out = N in + k` and failed correct work. The `^| DEF-` acceptance pattern could not see them at all, and the schema forbade renumbering their ids.
>
> WRONG — one class, one count, gate silently inapplicable to the new rows:
> ```
> N in (def: rows) = N out (all Log rows)   MUST be equal
> acceptance pattern: ^| DEF-
> ```
> CORRECT — two classes, equality scoped to the sourced one:
> ```
> ## Class 1 — Deferred (`def:`-sourced)        DEF- ids
>     N in (def: rows across the inputs) = N out (Class 1 rows)   MUST be equal
> ## Class 2 — Reconcile-time out-of-scope      original CLM- ids, never renumbered
>     count reported as k; NEVER folded into the equality above
> Closing table: N in = x · N out = x · Class 2 = k · Total = x + k
> patterns: ^| DEF-  (Class 1) · ^| CLM-  (Class 2) · ^| (DEF|CLM)-  (total)
> ```

Class 2 rows are *reported*, not *balanced*, because by construction they have no source row behind them. Three generalisations follow:

- **Emit the empty class's heading anyway.** A consumer must be able to tell "no Class 2 rows" from "the producer never ran this step". An absent heading conflates them.
- **Widen the acceptance patterns with the structure, in the same edit.** A structural change that leaves its verification pattern behind ships a gate that reads the old world. `^| DEF-` would have returned a perfectly balanced figure while two rows sat unexamined.
- **Tell the downstream consumer the shape changed.** The only task that later reads such a Log will otherwise write the obvious cross-count (`total == N in`) and false-fail correct work. That is a coordination flag, not a footnote.

[`verification-gates.md`](verification-gates.md) §11.3 states the set-comparison form of the same discipline: compare member sets, not counts. This section covers the case where the sets legitimately differ.

---

## 5. Detection at Plan-Review Time

Each defect above is catchable before dispatch. Flag any of these signatures in a plan under review:

- A gate of the form `count(rows sourced from X) == count(rows in Y)` where Y is a **standing** or **extended-later** artifact. If Y outlives the session that built it, such as a standing register or a log a later sprint extends, a second provenance is not hypothetical. It is scheduled. This is the highest-value signature because it is predictable in advance. Treat it as a blocker at plan-review time, not a note.
- A `no X survives` criterion with no paired positive criterion over the full item set.
- A count whose denominator is produced by the same decomposition that produced the items counted.
- An "unchanged count" check on a file whose new content must *reference* the old content to distinguish itself from it.
- An aggregate over a file with more than one writer in the plan.
- A reason or status enum that can gain a value mid-campaign. The new value ships with a legend recording the gap, rather than being normalised to an in-enum code, which would misfile it.

> [!verify] Check this file against its own signature list
> No gate specified in this file takes a denominator from the artifact it gates. The per-file literal count in §2 counts a literal the author wrote against an expected value of 1 per file, which is a per-content assertion and not an aggregate over a shared file.
