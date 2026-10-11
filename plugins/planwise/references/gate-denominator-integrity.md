---
description: A coverage or balance gate whose denominator, or whose aggregate observable, comes from the artifact it gates returns accurate numbers that answer a different question than the one asked. Covers the invariant-first substitution table, the false-FAIL and false-PASS directions of an aggregate count over a shared file, absence criteria that deletion satisfies, presence counts that cannot see an unscoped item, balance gates that become inapplicable when a second provenance appears, the plan-review signatures that catch each before dispatch, and the containment check over a diff that walks only the added and changed hunks and so passes a deleted line (pair it with a per-file hunk census), and the completeness guard whose numerator and denominator both pass through the parser's region filter and so certify only what the filter saw (derive the denominator from the raw input by a simpler predicate, probe with a line the filter drops, and count every dropped line as unparsed). Consult when writing or accepting a count, a coverage ratio, a "no X survives" criterion, an "N in = N out" gate, or a "changes only inside markers" gate over a diff.
paths: {planwise_root}/{plans_dir}/**
---
# Gate Denominator Integrity — a Count Taken From the Artifact Being Gated Is a Tautology Wearing the Costume of a Check

**Purpose:** A gate prints a number, and the number is accurate. The gate still answers a different question than the one asked, because its denominator, or the aggregate it observes, was derived from the wrong side of the property it was meant to protect. Neither direction of the mistake shows in the gate's own output. Both look like a number matching or not matching an expectation.

**Read this when** you are writing or accepting a count, a coverage ratio, an absence criterion (`no X survives`), a balance gate (`N in = N out`), or a "changes only inside the markers" gate over a diff of a copied-and-extended file.

This file owns the **denominator and the aggregate**. [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) owns the **pattern**, [`gate-baseline-independence.md`](gate-baseline-independence.md) owns the **base a diff is taken against**, and [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the **input set**. A gate can pass all three of those and still fail here.

## Table of Contents

- [1. Ask What Invariant You Actually Wanted](#1-ask-what-invariant-you-actually-wanted)
- [2. Never Assert an Aggregate Count Over a Shared File](#2-never-assert-an-aggregate-count-over-a-shared-file)
- [3. Take the Denominator From Outside the Artifact](#3-take-the-denominator-from-outside-the-artifact)
- [4. A Balance Gate Is a Statement About Provenance, Not About Rows](#4-a-balance-gate-is-a-statement-about-provenance-not-about-rows)
- [5. Detection at Plan-Review Time](#5-detection-at-plan-review-time)
- [6. A Containment Check Proves Only What It Iterates Over](#6-a-containment-check-proves-only-what-it-iterates-over)
- [7. A Guard's Denominator Must Not Pass Through the Filter It Guards](#7-a-guards-denominator-must-not-pass-through-the-filter-it-guards)

---

## 1. Ask What Invariant You Actually Wanted

The gate was derived from a convenient observable rather than from the invariant. Four recurring cases show it. In every one, the correct invariant was **not a count**.

| What the gate was trying to assert | Correct invariant |
|---|---|
| "I did not modify the existing text" | **Zero deletions in my own hunk.** Read `git diff --numstat` on my change, or inspect the `^-` lines |
| "my content landed in this file" | **A content grep for a literal I authored**, per file, reported separately |
| "the two copies of this sentence agree" | **Two counts of the same literal**, one per copy, both quoted |
| "no line changed outside the marked region" | **A hunk census with `d = 0`, plus a containment check over the added and changed lines** (§6) |

All four are per-hunk or per-content assertions. None is an aggregate over a file that other people also write.

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

[`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.1 states the false-FAIL direction for an enumeration (the expected value is derived from the enumeration under test). This section adds the false-PASS direction and the rules below. A rule that shows only the false-FAIL direction teaches runners to loosen gates, which is the opposite of the lesson.

- A "count must be unchanged" gate on a file the work may legitimately add prose to is **mis-specified**. Replace it with a zero-deletions assertion on the author's own hunk. Deletions are what "you modified the existing text" actually means.
- **Never let a file-presence count stand as proof that a task's content landed**, in any plan where more than one task writes the same file. Under layered dispatch on shared handler and reference docs that is the normal case. Prove content by content. [`gate-heuristic-verifier-patterns.md`](gate-heuristic-verifier-patterns.md) §2 and [`gate-input-set-and-compared-window.md`](gate-input-set-and-compared-window.md) §10.6 carry the per-unit and input-set forms.
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

A denominator can also fail by sharing the numerator's filter rather than its output. § "7. A Guard's Denominator Must Not Pass Through the Filter It Guards" covers that form.

One small self-referential trap sits in the same family: **a prose claim about a grep result is itself grep-visible.** A governance sentence asserting that no `map pending` string survives will itself contain the string. Reword the claim to be true. Do not mutilate the artifact to fit a naive pattern. [`gate-absence-and-consistency.md`](gate-absence-and-consistency.md) §8.1 carries the scrub rule for the same token.

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

[`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.3 states the set-comparison form of the same discipline: compare member sets, not counts. This section covers the case where the sets legitimately differ.

---

## 5. Detection at Plan-Review Time

Each defect above is catchable before dispatch. Flag any of these signatures in a plan under review:

- A gate of the form `count(rows sourced from X) == count(rows in Y)` where Y is a **standing** or **extended-later** artifact. If Y outlives the session that built it, such as a standing register or a log a later sprint extends, a second provenance is not hypothetical. It is scheduled. This is the highest-value signature because it is predictable in advance. Treat it as a blocker at plan-review time, not a note.
- A `no X survives` criterion with no paired positive criterion over the full item set.
- A count whose denominator is produced by the same decomposition that produced the items counted.
- A completeness guard (`N of N compared`, `all rows resolved`) whose denominator is `len()` of the same list the parser's region rule produced. See § "7. A Guard's Denominator Must Not Pass Through the Filter It Guards".
- A guard tested only with zero-row, partial-parse, and in-region fixtures, and never with a line the parser's region rule drops.
- An "unchanged count" check on a file whose new content must *reference* the old content to distinguish itself from it.
- An aggregate over a file with more than one writer in the plan.
- A reason or status enum that can gain a value mid-campaign. The new value ships with a legend recording the gap, rather than being normalised to an in-enum code, which would misfile it.

> [!verify] Check this file against its own signature list
> No gate specified in this file takes a denominator from the artifact it gates. The per-file literal count in §2 counts a literal the author wrote against an expected value of 1 per file, which is a per-content assertion and not an aggregate over a shared file.

---

## 6. A Containment Check Proves Only What It Iterates Over

> [!constraint] A containment check over a diff must iterate every hunk kind, or a census must prove the missing kind is absent
> A check that walks the new side of each hunk cannot see a hunk that has no new side. A deleted line passes it.

A task copied scripts from a control kit and added module code inside `# --- module additions ---` and `# --- end module additions ---` fence pairs. The gate said every differing line in `diff -r control/ copy/` sits inside a fence pair. The runner's check parsed each hunk header. For `a` (add) and `c` (change) hunks it walked the new-file range and confirmed every line was fenced. It printed PASS.

**The gap.** A `d` (delete) hunk has no new-file range. A control line removed outright produces a header `NNdM` followed by only `<` lines. The loop body never runs for it, so PASS prints. A deleted control line is a change outside every fence by definition.

Two rules close the gap.

- **Pair the containment check with a hunk census.** Count the `a`, `c` and `d` hunks per file and record the counts. `d = 0` is the signal the containment check cannot produce. If `d > 0`, treat every deletion as a finding, because no fence can contain a line that is not there.
- **Read each `c` hunk by hand once.** Its `>` side may be fenced while its `<` side is a control line that no longer exists as written. That is acceptable only when the design required the modification and the fenced block re-emits the line. Say so in the proof.

```
# WRONG — the check walks `a` and `c` ranges on the new file and prints PASS:
for hunk in diff_hunks:
    if hunk.kind in ("a", "c"):
        for ln in hunk.new_range:
            if not fenced[ln]: fail()
# a `d` hunk never enters the loop; a deleted control line passes

# CORRECT — the same check, plus a per-file census that makes deletions visible:
diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+d[0-9,]+$'   # MUST be 0 per file
diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+c[0-9,]+$'   # each one read by hand and recorded
diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+a[0-9,]+$'
```

`grep -c` prints `0` and exits 1 when nothing matches. Read the printed count, not the exit status.

**Record the census.** Use the shape "per-file counts of `a`, `c`, `d`". The worked example's census was 8 `a`, then 5 `a` plus 1 `c`, then 4 `a` plus 2 `c`, with 0 `d` across all three files. A downstream re-run of the gate expects the recorded census. A changed `d` count is a finding.

**Dry-run both directions.** On a scratch pair, a copy with one control line deleted must report `d` = 1. A clean copy that only adds a fenced block must report `d` = 0. The two runs must differ, or the census cannot see deletions.

**Applies to** any "changes only inside markers" gate over a diff of a copied-and-extended file: fence comments, region markers and generated-code blocks. Also use it when you review a runner-written verification script before you accept its PASS. Ask which hunk kinds it iterates over.

[`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11 states the state-detecting form. The wider principle is the same: a gate that could not have seen its subject prints the same as a gate that saw it and found it clean.

---

## 7. A Guard's Denominator Must Not Pass Through the Filter It Guards

> [!constraint] When the numerator and the denominator are both computed after one filter, the guard proves the filter is self-consistent
> A guard of the form "everything counted was compared" is only as good as its count. Computed after one filter, both sides agree by construction. The guard then says nothing about input the filter never saw.

**Scenario.** An index drift audit exited 3 unless `compared == total`. It shipped with tests for zero comparisons, a partial parse and comments between rows. All passed. A row after a `## Notes` heading, and a row after a legend table, were neither compared nor counted. The parser's region ended at the first heading, so both the compared count and the total skipped them. The audit printed "3 of 3 rows compared" over a fourth row it never read. A renamed header over an empty tree printed "0 of 0" and exited 0.

```python
# WRONG — both sides of the guard come from the region the parser chose:
table = parse_table(content)              # region ends at the first heading
compared = diff.compared                  # rows inside the region only
total = len(table.table_lines)            # ALSO rows inside the region only
if total and compared == total:
    print("No drift detected.")           # a row after a heading is invisible to both

# CORRECT — the denominator counts every candidate in the whole input,
# and whatever the filter drops becomes a named, counted line:
# every six-cell line outside the region (not a header or separator) is
# recorded as unparsed "outside-table-region" and appended to table_lines
table = parse_table(content)
total = len(table.table_lines)            # now includes outside-region lines
if table.unparsed:
    status = "incomplete"                 # exit 3, names each line
```

Three operative rules:

- **Derive the guard's denominator from the raw input, by a predicate simpler than the parser's.** Here the predicate is "splits into six cells", not "is a row inside the recognized table". A denominator that shares the parser's region rule inherits the parser's blind spot.
- **Probe the guard with an input the filter drops.** Zero-row and partial-parse fixtures exercise the guard inside the filter. Only an input the filter excludes can show that the denominator was filtered too. Examples: a row after a heading, a renamed header, a row after a trailing table.
- **Fail loud on what the filter excludes.** Counting an excluded line as `unparsed` makes the audit exit non-zero on a commented or fenced example row too. That false alarm is the right error direction for a guard whose purpose is to never certify unread input.

This section owns the guard form. [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) § "2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions" owns the reporting form.

**Applies to** any "N of N compared" or "all rows resolved" all-clear: index drift audits, `--check` modes, reconcilers, and parsers with a region rule that feed a completeness gate.
