---
description: A figure is not verified until its derivation is. Covers why recomputing a total proves only that the author can add, why a filtered denominator is wrong only where it bites, why a bare count in prose has to be re-derived at every hop that depends on it, and why a measurement written into its own subject needs a convergence argument. Consult when about to report, verify or repair a figure that is a sum, a labelled aggregate, or a count stated in prose.
paths: {planwise_root}/{plans_dir}/**
---
# Aggregate Provenance — A Figure Is Not Verified Until Its Derivation Is

**Purpose:** Three defect shapes in which a reported figure was correct, or correctable, while the derivation behind it was unreproducible — and in every case the check that was actually run could not have discovered that. These are not arithmetic errors. An arithmetic error is wrong everywhere and the next consumer catches it. These defects are **right everywhere the flaw is inert**, which is why they survive review, spot-checks, and an honest re-derivation of the wrong quantity.

**Read this when** you are about to report a total, label an aggregate, state a count in prose, repair a figure a reviewer questioned, or record a measurement inside the artifact it measures.

The three share one structure: a number was verified at a grain **coarser than the grain at which it can fail**. A grand total cannot expose two offsetting component errors. A label naming a population cannot expose a filter applied two steps upstream. A numeral in prose cannot expose which of two same-sized sets it was counting. In each case the verification was performed diligently and reported clean.

Three neighbouring rules own adjacent machinery. [`measurement-discipline.md`](measurement-discipline.md) §8.9 hardens the **recorded figure a gate compares against** — its drift, its derivation, its expiry. [`verification-task-authoring.md`](verification-task-authoring.md) §4 and [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.2 bind the denominator of a coverage or ratio **gate**. This file is about a figure **reported in an artifact** — a total, a labelled aggregate, a count in prose — whose derivation nobody re-ran. The remedies differ: a gate is re-bound to an external item set; a reported figure has its addends re-derived and its population stated.

## Table of Contents

- [1. When a Verified Figure Is a Sum, Verify the Addends](#1-when-a-verified-figure-is-a-sum-verify-the-addends)
- [2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions](#2-state-the-denominator-with-the-number-and-never-re-use-a-row-set-across-questions)
- [3. A Bare Count in Prose Is a Claim, Not a Measurement — Name the Members Inline](#3-a-bare-count-in-prose-is-a-claim-not-a-measurement--name-the-members-inline)
- [4. A Measurement Stored Inside Its Own Subject Needs a Convergence Argument](#4-a-measurement-stored-inside-its-own-subject-needs-a-convergence-argument)

---

## 1. When a Verified Figure Is a Sum, Verify the Addends

> [!constraint] A sum is a lossy function — recomputing it recovers one number and destroys the information needed to check that number's provenance
> When the sum is the only thing verified, **any even number of offsetting errors is indistinguishable from zero errors** — and offsetting errors are not rare in hand-maintained tables, because the same edit that drops a row often adds one elsewhere.
>
> A 252-row disposition table reconciled per-source subtotals into a grand total. The coverage gate recomputed the grand total from the artifact — the correct discipline, applied correctly — and got **252**, matching the file. Inside it: one source's roll-up claimed **51** rows where the section held **52** (a repair row omitted from the breakdown, −1), and a cross-cutting item counted **twice**, once inside a source's subtotal and again as its own standalone line (+1). Net zero. Every column summed, and a reader following the table's own arithmetic could not reproduce 252.
>
> The gate caught it only because the check was specified at **deliverable grain** rather than as "verify the total". The difference between the two phrasings is the whole rule:
>
> ```
> PASSES on this defect:  "confirm the totals reconcile"
> CATCHES it:             "re-extract each ledger and confirm every entry appears
>                          as exactly one row, and vice versa"
> ```
>
> **Treat an exact match on a derived aggregate as weak evidence, not strong.** A total that lands precisely on its expected value *after a defect was suspected* deserves more scrutiny, not less — it is the signature of cancellation.
>
> **Print the arithmetic in the artifact**, so a reader can falsify it rather than only agree with it:
>
> ```
> 15+11+21+52+29+24+18+31 = 201
> 201+32+18+1 = 252
> ```
>
> **Re-check the explanations, not just the numbers.** A third defect of the same shape survived the repair pass: a footnote explained a secondary figure ("a prefix-keyed recount returns 198") with a single cause when three effects produced it — a dual-keyed row matching no single prefix at −1, a declared-metadata row matching the prefix anyway at +1, and three genuine cluster-level rows at −3 — two of which cancelled. Correct figure, wrong explanation, second time in the same document. It survived precisely because the repair targeted figures and that figure was already right.

Specify checks at the grain the artifact claims, not the grain that is convenient to measure. A table that claims "every ledger entry appears as exactly one row" is checked by re-extracting the ledgers and matching entries to rows in both directions; a table that claims only "the total is 252" has made a weaker claim, and a reader who needs the stronger one has no way to recover it from the total.

---

## 2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions

> [!constraint] A wrong number is wrong everywhere and you notice it; a filtered denominator is right everywhere the filter is inert and wrong only where it bites
> — which is, by construction, the part of the data that differs from the rest. The failure is silent, correlated with the interesting cases, and survives spot-checks, because any cell you happen to verify is likely one of the ones that agrees.
>
> A verification script built a row set filtered to reviewer-or-shell-bearing transcripts, correctly used it for the reviewer aggregate it was written for, and then printed a version histogram from the same filtered rows under the label **"all team-path transcripts by version."** One bucket read **63** where the truth was **69**. The other five were right — not because the method was sound, but because in those buckets nearly every transcript happened to carry a `Bash` call, so the filter removed nothing. The defect was invisible in **5 of 6 cells** and shipped into a published artifact. The reviewer who caught the wrong figure diagnosed it as a duplicated cell — a transcription slip. That diagnosis was plausible, wrong, and would have left the lesson "check your numbers" instead of "check your denominator."
>
> Two sub-rules:
>
> - **A row set built for one purpose must not be reused for a second aggregate without re-checking the filter against the new question.** The filter that makes a reviewer aggregate correct makes a corpus histogram wrong. Same rows, different question, different validity.
> - **A detector keyed on *content* rather than *structure* is blind wherever the content varies** — and content varies most in exactly the cases worth measuring. A deny-detector matching `blocked|denied|permission|hook…block` was pointed at an experiment whose entire purpose was testing *redirect-worded* deny messages ("use Read with offset/limit instead of piping through cat") and found **0 of 4** genuine denials, all four confirmed against the rig's own capture ground truth. **A keyword detector systematically undercounts exactly the wording a remediation is trying to promote** — it is most blind precisely where the measurement matters most. Pair on a structural signal (`is_error`, a hook-fire record, a spawn record) and use text only as corroboration.
>
> **Report the population with the figure — "218 of 281 subagent transcripts," not "218."** A figure whose population is unstated cannot be audited, and writing the population down is usually enough to catch the mismatch yourself.
>
> **When a re-measurement disagrees with a published figure, find the cause before recording the correction.** "Wrong digit" and "wrong population" demand different fixes, and only one of them tells you the rest of the numbers need re-checking.
>
> **Independent verification protects against inheriting *their* defect and does nothing about introducing your own.** Verifying someone else's claim with your own instrument is worth doing for the first reason. It is not a guarantee, and the confidence of "I checked this myself" makes an unverified check **more** dangerous than a relayed one — a relayed figure still reads as somebody else's claim; a self-checked one reads as settled.

---

## 3. A Bare Count in Prose Is a Claim, Not a Measurement — Name the Members Inline

> [!constraint] Re-derive a count from the artifact at every hop that depends on it, and name the members inline where the count is load-bearing
> A config template held **six** keys of one family; the calibration function that wrote that family wrote **four**. Two handler docs said the function *"overwrites the six keys in place"* — borrowing the template's cardinality and attaching it to the write set. It was wrong before the sprint began, and nobody noticed, because six is plausible and the two sets sit two files apart. Then a sprint added two keys to the write set, and the wrong numeral travelled four hops:
>
> ```
> runner:         reads "six", sprint adds 2         →  writes "eight"
>                 (correct arithmetic on a wrong operand)
> orchestrator:   enumerates the actual write sites  →  4 before, 6 after
>                 (the correct value is the same word already there, right for a different reason)
> second runner:  on a file carrying the identical sentence, reports it as
>                 "goes stale this sprint"            →  the exact inverse
> Recovery file:  records a test count of "22 → 35" taken from a runner's narrative;
>                 the closing sweep measured 16 → 35
> ```
>
> Every hop was reasonable. The number was stated confidently in a shipped doc, adjacent to the code it described, and re-deriving it means enumerating three write sites across two branches of a function — which is real work when a sentence right there already claims the answer. The root cause was that during the sprint both sets were briefly size six: **a shared cardinality between two nearby sets is a coincidence that reads as a cross-check.**
>
> **Review cannot catch this, and that is the sharpest part.** A diff showing `six → eight` looks like diligent maintenance; a diff showing `six → six` looks like nothing happened at all. The correct fix produced no change to the numeral, so a reviewer reading only the diff could not tell the count had been re-derived rather than skipped.
>
> ```
> WRONG — trust the stated baseline and do arithmetic on it:
> doc says "six keys"  →  sprint adds 2  →  write "eight"
>
> CORRECT — enumerate the artifact, then compare against the doc:
> enumerate calibrate()'s actual write sites  →  4 before, 6 after
>   →  the doc's "six" was ALWAYS wrong; it is now right by coincidence
>   →  land the count self-verifying (name the six keys inline)
> ```
>
> Two mechanical consequences:
>
> - **Name the members inline when a count is load-bearing.** A sentence of the form `"overwrites its six written keys — {key-1}, {key-2}, {key-3}, {key-4}, {key-5}, {key-6} — in place"` cannot silently drift, and a reviewer can audit it without opening the module. A bare "six" can drift and cannot be audited from the sentence.
> - **Treat a shared cardinality between two nearby sets as a hazard, and say which set you mean.** After the sprint the collision broke — 11 template keys against 6 written — and a runner "reconciling" those numbers to match would have reintroduced the original defect.
>
> This applies with equal force to the orchestrator's own Recovery and summary files. **An acceptance gate that verifies nine claims does not vouch for a tenth that arrived in the same message.**

§1 and §3 both end at "re-derive rather than inherit", but the artifact differs and so does the tell. §1's subject is a computed aggregate inside one table, caught by diffing components against their own sources. §3's subject is a numeral that travelled through prose across files, caught by enumerating the members. A merged rule collapses into "check counts", which is true of neither and actionable in neither.

---

## 4. A Measurement Stored Inside Its Own Subject Needs a Convergence Argument

> [!practice] Writing the number changes the number
> A generated artifact is gated on `wc -l` **and** `wc -c` **and** a token estimate, and is asked to record its own final measurement in its header — and that header is inside the file it measures. One Part's header read 389 → 412 → 415 → 420 lines as content landed after each measurement. A byte count measured at 47,510 was written as "47,510", thereby making the file 47,571.
>
> Two fixes:
>
> - **Measure after the last edit, not before it.** Treat the header as part of the content being measured, not as metadata outside it.
> - **Make the correction a same-length substitution.** `47,510` → `47,571` is digit-for-digit identical in length, so the file size does not move and the note converges in one pass. A correction that alters the string's length re-invalidates itself, and you loop.

This is a mechanical trap rather than an epistemic one, which is why it is a practice and not a constraint. The three sections above are about what a figure *means*; this one is about the order in which two edits have to happen.

---

*Cross-reference: [`measurement-discipline.md`](measurement-discipline.md) §8.9 (the recorded figure a gate compares against) · [`verification-task-authoring.md`](verification-task-authoring.md) §4 (denominator scoping for a coverage gate) · [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.2 (a gate on a derived ratio names its column, grain and denominator) · [`session-context-budget.md`](session-context-budget.md) § File Size Limits (the three Read-tool gates a self-measuring header reports against)*
