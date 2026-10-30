---
description: A coverage or balance gate whose denominator, or whose aggregate observable, comes from the artifact it gates returns accurate numbers that answer a different question than the one asked. Covers the invariant-first substitution table, the false-FAIL and false-PASS directions of an aggregate count over a shared file, absence criteria that deletion satisfies, presence counts that cannot see an unscoped item, balance gates that become inapplicable when a second provenance appears, the plan-review signatures that catch each before dispatch, and the containment check over a diff that walks only the added and changed hunks and so passes a deleted line (pair it with a per-file hunk census), and the completeness guard whose numerator and denominator both pass through the parser's region filter and so certify only what the filter saw (derive the denominator from the raw input by a simpler predicate, probe with a line the filter drops, and count every dropped line as unparsed). Consult when writing or accepting a count, a coverage ratio, a "no X survives" criterion, an "N in = N out" gate, or a "changes only inside markers" gate over a diff.
consult-when: Writing or accepting a count, a coverage ratio, a "no X survives" criterion, or an "N in = N out" balance gate — take the denominator from outside the artifact being gated, never assert an aggregate count over a file another task also writes, pair every absence criterion with a presence criterion over the full set, scope a balance gate's equality to the sourced class, pair a diff containment check with a per-file hunk census, and derive a completeness guard's denominator from the raw input, never through the filter it guards
paths: {planwise_root}/{plans_dir}/**
---
# Gate Denominator Integrity — a Count Taken From the Artifact Being Gated Is a Tautology Wearing the Costume of a Check

**Purpose:** A gate can print an accurate number and still answer the wrong question, because its denominator, or the aggregate it observes, came from the wrong side of the property it protects. Neither direction of the mistake shows in the gate's own output.

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

Derive the gate from the invariant, not from a convenient observable. In each of four recurring cases, the correct invariant was **not a count**:

| What the gate was trying to assert | Correct invariant |
|---|---|
| "I did not modify the existing text" | **Zero deletions in my own hunk.** Read `git diff --numstat` on my change, or inspect the `^-` lines |
| "my content landed in this file" | **A content grep for a literal I authored**, per file, reported separately |
| "the two copies of this sentence agree" | **Two counts of the same literal**, one per copy, both quoted |
| "no line changed outside the marked region" | **A hunk census with `d = 0`, plus a containment check over the added and changed lines** (§6) |

All four are per-hunk or per-content assertions. None is an aggregate over a file that other people also write.

> [!constraint] Name the invariant before choosing the instrument
> Write the property in one sentence ("nothing I did removed a line"), then ask which observable that sentence is about. A count is a statement about the whole file. A hunk, a literal, or a pair of literals is a statement about your change.
>
> WRONG — one aggregate count stands in for "the two copies agree":
> ```
> Grep  pattern='<sentence literal>'  path='<folder holding both copies>'  output_mode='count'   # "MUST be 2": also 2 when one copy holds it twice and the other lost it
> ```
> CORRECT — two counts of the same literal, one per copy, both quoted:
> ```
> Grep  pattern='<sentence literal>'  path='<copy A>'  output_mode='count'   # 1
> Grep  pattern='<sentence literal>'  path='<copy B>'  output_mode='count'   # 1
> ```

---

## 2. Never Assert an Aggregate Count Over a Shared File

> [!constraint] An aggregate count over a file with more than one writer is mis-specified in both directions
> WRONG — a count over a file that concurrent or additive work legitimately moves:
> ```
> Grep  pattern='plugin_root'  path='handlers/doctor.md'  output_mode='count'   # "MUST be unchanged"  → 10 becomes 11, correct work FAILS
> git diff --name-only -- fileA fileB fileC | wc -l                             # "MUST equal 3"       → siblings supply 2, missing work PASSES
> ```
> The first line is the **false-FAIL** direction. Correct additive work moved the count from 10 to 11 while the protected text was provably byte-identical (`+47/−0`). The second line is the **false-PASS** direction. Sibling tasks had already modified two of the three files, so the count reached 3 when this task touched the third alone.
>
> CORRECT — the property itself, scoped to your own change:
> ```
> git diff --numstat -- handlers/doctor.md                                       # my hunk is +47/-0 → the existing gate text is byte-identical
> Grep  pattern='<literal I authored>'  path='fileA'  output_mode='count'        # 1
> Grep  pattern='<literal I authored>'  path='fileB'  output_mode='count'        # 1   ← each file proved separately
> Grep  pattern='<literal I authored>'  path='fileC'  output_mode='count'        # 1
> ```

[`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.1 states the false-FAIL direction for an enumeration. This section adds the false-PASS direction. A rule that shows only the false-FAIL direction teaches runners to loosen gates.

- A "count must be unchanged" gate on a file the work may legitimately add prose to is **mis-specified**. Replace it with a zero-deletions assertion on the author's own hunk.
- **Never let a file-presence count stand as proof that a task's content landed** where more than one task writes the same file. Prove content by content. [`gate-heuristic-verifier-patterns.md`](gate-heuristic-verifier-patterns.md) §2 and [`gate-input-set-and-compared-window.md`](gate-input-set-and-compared-window.md) §10.6 carry the per-unit and input-set forms.
- **When a gate's expected value is stated as `≥ 1`, ask what a regression would look like.** At `≥ 1`, deleting two of three references still passes.
- **A false-failing gate is not the safe direction.** Runners learn to route around it, silently. Treat a gate that fires on correct work as a defect **in the gate**, and fix it at the point of discovery.

A new stage that says "this is distinct from X" must mention X, so it always moves X's count. **The better the prose, the more reliably the gate false-fails.**

Check 28 of `scripts/lint_gate_checks_plan.py` lints a plan's gates against this section.

---

## 3. Take the Denominator From Outside the Artifact

> [!constraint] A denominator counted in your own output cannot detect what you never scoped
> Two failure shapes, stated precisely:
> - An **absence** criterion (`no X survives`) counts markers in your own output. A marker is a *record that work is outstanding*. Deleting the record and doing the work are byte-identical to a grep, and deletion is strictly cheaper.
> - A **presence** count (`N sections for N surfaces`) counts items in your own output against a number derived from the same decomposition that produced them. It is a tautology wearing the costume of a check. It can detect a *duplicate* or a *dropped* item. It structurally **cannot** detect an item nobody ever scoped.
>
> WRONG — an absence criterion standing alone, satisfied by deleting the marker:
> ```
> No `[stability: map pending]` markers survive.     # passes once the one marker line is deleted
> ```
> CORRECT — the absence half paired with a presence half over the external set:
> ```
> No `[stability: map pending]` markers survive, and all 35 surfaces in the external matrix carry a filled note.
> ```

The two fail together in practice. One session's presence count read 10/10 while the authoritative external matrix read 34/35, because one surface was never scoped and so appeared in no output. Three upstream outputs emitted 3, 6 and 1 placeholders for 2, 5 and 3 surfaces. Every runner honoured its own spec, and the consolidator could still pass `no X survives` by deleting one line. Per-runner correctness does not compose into whole-set correctness.

Five operational rules follow:

- **Never let an absence criterion stand alone.** Pair every `no X survives` with a positive criterion quantified over the full item set: *"all N items carry a filled Y."* Absence bounds the cleanup. Presence bounds the work.
- **Reconcile coverage against the authoritative external reference** (the matrix, the schema, the map), never against the count your own decomposition produced. If the external set is outside every task's Required Context, that is a **scaffolding defect**: the reconciliation has no owner.
- **Require an explicit statement where data is absent.** "No source row exists for this item" is a filled note. A blank, or a silently dropped line, is indistinguishable from work not done.
- **Never emit a stub to satisfy a sweep.** A placeholder section turns a visible gap into an invisible one. Record the gap as a gap, with its disposition, and route it downstream.
- **Sweep the marker distribution across the batch before dispatching the join.** One count per output exposes the ratio that shows a downstream criterion is unsafe. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) owns the batch-gate checks this one joins.

A denominator can also fail by sharing the numerator's filter rather than its output. § "7. A Guard's Denominator Must Not Pass Through the Filter It Guards" covers that form.

A prose claim about a grep result is itself grep-visible, so reword the claim to be true rather than mutilate the artifact to fit a naive pattern. [`gate-absence-and-consistency.md`](gate-absence-and-consistency.md) §8.1 carries the scrub rule.

---

## 4. A Balance Gate Is a Statement About Provenance, Not About Rows

`N in = N out` means *"every row in the output traces to exactly one row of this specific input set."* When a second provenance appears, the equality is not *violated*. It is **inapplicable**, and folding the new class in guarantees a false failure.

> [!constraint] Scope the equality to the sourced class, and report the other class separately
> Two claims minted at reconcile time (ids `CLM-{n}`, not `def:` rows) had to be dispositioned into the same Log. Adding them made `N out = N in + k` and failed correct work. The `^| DEF-` acceptance pattern could not see them, and the schema forbade renumbering their ids.
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

Class 2 rows are *reported*, not *balanced*, because they have no source row behind them. Three generalisations follow:

- **Emit the empty class's heading anyway.** A consumer must be able to tell "no Class 2 rows" from "the producer never ran this step".
- **Widen the acceptance patterns with the structure, in the same edit.** A structural change that leaves its verification pattern behind ships a gate that reads the old world.
- **Tell the downstream consumer the shape changed.** Otherwise it writes the obvious cross-count (`total == N in`) and false-fails correct work. That is a coordination flag, not a footnote.

[`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.3 states the set-comparison form: compare member sets, not counts. This section covers the case where the sets legitimately differ.

---

## 5. Detection at Plan-Review Time

Flag any of these signatures in a plan under review, because each defect above is catchable before dispatch:

- A gate of the form `count(rows sourced from X) == count(rows in Y)` where Y is a **standing** or **extended-later** artifact. If Y outlives the session that built it, a second provenance is scheduled, not hypothetical. Treat it as a blocker at plan-review time, not a note.
- A `no X survives` criterion with no paired positive criterion over the full item set.
- A count whose denominator is produced by the same decomposition that produced the items counted.
- A completeness guard (`N of N compared`, `all rows resolved`) whose denominator is `len()` of the same list the parser's region rule produced. See § "7. A Guard's Denominator Must Not Pass Through the Filter It Guards".
- A guard tested only with zero-row, partial-parse, and in-region fixtures, and never with a line the parser's region rule drops.
- An "unchanged count" check on a file whose new content must *reference* the old content to distinguish itself from it.
- An aggregate over a file with more than one writer in the plan.
- A reason or status enum that can gain a value mid-campaign. The new value ships with a legend recording the gap, rather than being normalised to an in-enum code.

> [!constraint] A standing-artifact balance gate is a blocker, not a note
> WRONG — the reviewer notes the signature and the plan dispatches:
> ```
> count(rows sourced from X) == count(rows in Y)    # Y is a standing register; review says "noted"
> ```
> CORRECT — the reviewer blocks, and the plan rescopes the gate before dispatch:
> ```
> count(rows sourced from X) == count(Class 1 rows in Y)    # other classes reported as k (§4)
> ```

> [!verify] Check this file against its own signature list
> No gate specified in this file takes a denominator from the artifact it gates. The per-file literal count in §2 counts a literal the author wrote against an expected value of 1 per file, which is a per-content assertion and not an aggregate over a shared file.

---

## 6. A Containment Check Proves Only What It Iterates Over

> [!constraint] A containment check over a diff must iterate every hunk kind, or a census must prove the missing kind is absent
> A check that walks the new side of each hunk cannot see a hunk that has no new side. A deleted line passes it. A task's gate said every differing line in `diff -r control/ copy/` sits inside a fence pair. The runner's check walked the new-file range of each `a` and `c` hunk and printed PASS. A `d` hunk (`NNdM` followed by only `<` lines) has no new-file range, so the loop never ran for it.
>
> WRONG — the check walks `a` and `c` ranges on the new file and prints PASS:
> ```
> for hunk in diff_hunks:
>     if hunk.kind in ("a", "c"):
>         for ln in hunk.new_range:
>             if not fenced[ln]: fail()
> # a `d` hunk never enters the loop; a deleted control line passes
> ```
> CORRECT — the same check, plus a per-file census that makes deletions visible:
> ```
> diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+d[0-9,]+$'   # MUST be 0 per file
> diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+c[0-9,]+$'   # each one read by hand and recorded
> diff <control>/<file> <copy>/<file> | grep -cE '^[0-9,]+a[0-9,]+$'
> ```

`scripts/diff_hunk_census.py` runs the per-file hunk census. The rules it does not replace:

- **Pair the containment check with a hunk census.** `d = 0` is the signal the containment check cannot produce. If `d > 0`, treat every deletion as a finding.
- **Read each `c` hunk by hand once.** Its `>` side may be fenced while its `<` side is a control line that no longer exists as written. That is acceptable only when the design required the modification and the fenced block re-emits the line. Say so in the proof.
- **Read the printed count, not the exit status.** `grep -c` prints `0` and exits 1 when nothing matches.
- **Record the census** as per-file counts of `a`, `c`, `d`. A downstream re-run expects the recorded census, and a changed `d` count is a finding.
- **Dry-run both directions.** On a scratch pair, a copy with one control line deleted must report `d` = 1, and a clean copy that only adds a fenced block must report `d` = 0.

**Applies to** any "changes only inside markers" gate over a diff of a copied-and-extended file, and to review of a runner-written verification script: ask which hunk kinds it iterates over. [`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11 states the state-detecting form.

---

## 7. A Guard's Denominator Must Not Pass Through the Filter It Guards

> [!constraint] When the numerator and the denominator are both computed after one filter, the guard proves the filter is self-consistent
> A guard of the form "everything counted was compared" is only as good as its count. An index drift audit exited 3 unless `compared == total`. The parser's region ended at the first heading, so a row after a `## Notes` heading was neither compared nor counted. The audit printed "3 of 3 rows compared" over a fourth row it never read.
>
> WRONG — both sides of the guard come from the region the parser chose:
> ```python
> table = parse_table(content)              # region ends at the first heading
> compared = diff.compared                  # rows inside the region only
> total = len(table.table_lines)            # ALSO rows inside the region only
> if total and compared == total:
>     print("No drift detected.")           # a row after a heading is invisible to both
> ```
> CORRECT — the denominator counts every candidate in the whole input, and whatever the filter drops becomes a named, counted line:
> ```python
> # every six-cell line outside the region (not a header or separator) is
> # recorded as unparsed "outside-table-region" and appended to table_lines
> table = parse_table(content)
> total = len(table.table_lines)            # now includes outside-region lines
> if table.unparsed:
>     status = "incomplete"                 # exit 3, names each line
> ```

Three operative rules:

- **Derive the guard's denominator from the raw input, by a predicate simpler than the parser's.** Here the predicate is "splits into six cells", not "is a row inside the recognized table".
- **Probe the guard with an input the filter drops.** Zero-row and partial-parse fixtures exercise the guard inside the filter. Only an excluded input, such as a row after a heading or a renamed header, shows that the denominator was filtered too.
- **Fail loud on what the filter excludes.** Counting an excluded line as `unparsed` also makes the audit exit non-zero on a commented or fenced example row. That false alarm is the right error direction for a guard that must never certify unread input.

This section owns the guard form. [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) § "2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions" owns the reporting form.

**Applies to** any "N of N compared" or "all rows resolved" all-clear: index drift audits, `--check` modes, reconcilers, and parsers with a region rule that feed a completeness gate.
