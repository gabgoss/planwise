---
description: A figure is not verified until its derivation is. Covers why recomputing a total proves only that the author can add, why a filtered denominator is wrong only where it bites, why a bare count in prose has to be re-derived at every hop that depends on it, and why a measurement written into its own subject needs a convergence argument. Consult when about to report, verify or repair a figure that is a sum, a labelled aggregate, or a count stated in prose. Also covers why every operand of a byte-equality gate must come from one byte instrument, because a character count in a byte identity reads as lost content. Also covers four more shapes. An occurrence count comes from a findall over the bare pattern. Both readings of a before/after level gate come from one instrument. Two recounts that disagree are reconciled by their unmatched lists, not their totals. A fan-out pins the selection grain as a literal beside the instrument.
consult-when: About to report, verify or repair a total, a labelled aggregate, or a count stated in prose — verify the addends, state the population beside the figure, name the members inline, and take every operand of a byte-equality gate from one byte instrument (a character count in a byte identity reads as lost content), pin an occurrence count from a findall over the bare pattern, read both sides of a before/after level gate from one instrument, reconcile two recounts by their unmatched lists, and pin a fan-out's selection grain as a literal
paths: {planwise_root}/{plans_dir}/**
---
# Aggregate Provenance — A Figure Is Not Verified Until Its Derivation Is

**Purpose:** Three defect shapes in which a reported figure was correct, or correctable, while the derivation behind it was unreproducible — and in every case the check that was actually run could not have discovered that. These are not arithmetic errors. An arithmetic error is wrong everywhere and the next consumer catches it. These defects are **right everywhere the flaw is inert**, which is why they survive review, spot-checks, and an honest re-derivation of the wrong quantity.

**Read this when** you are about to report a total, label an aggregate, state a count in prose, repair a figure a reviewer questioned, or record a measurement inside the artifact it measures.

The three share one structure: a number was verified at a grain **coarser than the grain at which it can fail**. A grand total cannot expose two offsetting component errors. A label naming a population cannot expose a filter applied two steps upstream. A numeral in prose cannot expose which of two same-sized sets it was counting. In each case the verification was performed diligently and reported clean.

Three neighbouring rules own adjacent machinery. [`measurement-discipline.md`](measurement-discipline.md) §8.9 hardens the **recorded figure a gate compares against** — its drift, its derivation, its expiry. [`gate-heuristic-verifier-patterns.md`](gate-heuristic-verifier-patterns.md) §4 and [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.2 bind the denominator of a coverage or ratio **gate**. This file is about a figure **reported in an artifact** — a total, a labelled aggregate, a count in prose — whose derivation nobody re-ran. The remedies differ: a gate is re-bound to an external item set; a reported figure has its addends re-derived and its population stated.

## Table of Contents

- [1. When a Verified Figure Is a Sum, Verify the Addends](#1-when-a-verified-figure-is-a-sum-verify-the-addends)
- [2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions](#2-state-the-denominator-with-the-number-and-never-re-use-a-row-set-across-questions)
- [3. A Bare Count in Prose Is a Claim, Not a Measurement — Name the Members Inline](#3-a-bare-count-in-prose-is-a-claim-not-a-measurement--name-the-members-inline)
- [4. A Measurement Stored Inside Its Own Subject Needs a Convergence Argument](#4-a-measurement-stored-inside-its-own-subject-needs-a-convergence-argument)
- [5. Every Operand of a Byte Identity Comes From One Byte Instrument](#5-every-operand-of-a-byte-identity-comes-from-one-byte-instrument)
- [6. A Pinned Occurrence Count Comes From a Findall Over the Bare Pattern](#6-a-pinned-occurrence-count-comes-from-a-findall-over-the-bare-pattern)
- [7. Both Readings of a Before/After Level Gate Come From One Instrument](#7-both-readings-of-a-beforeafter-level-gate-come-from-one-instrument)
- [8. Two Recounts Disagree by Tokenizer: Reconcile the Unmatched Lists, Never the Totals](#8-two-recounts-disagree-by-tokenizer-reconcile-the-unmatched-lists-never-the-totals)
- [9. A Fan-Out Pins the Selection Grain as a Literal, Not Only the Instrument](#9-a-fan-out-pins-the-selection-grain-as-a-literal-not-only-the-instrument)

---

## 1. When a Verified Figure Is a Sum, Verify the Addends

> [!constraint] A sum is a lossy function — recomputing it recovers one number and destroys the information needed to check that number's provenance
> When the sum is the only thing verified, **any even number of offsetting errors is indistinguishable from zero errors**. Offsetting errors are common in hand-maintained tables, because the edit that drops a row often adds one elsewhere. A table can match its grand total while one subtotal is short by a row and one item is counted twice.
>
> WRONG — the check verifies the total, and passes on two offsetting errors:
> ```
> "confirm the totals reconcile"
> ```
> CORRECT — the check runs at the grain the artifact claims:
> ```
> "re-extract each ledger and confirm every entry appears as exactly one row, and vice versa"
> ```
>
> **Treat an exact match on a derived aggregate as weak evidence, not strong.** A total that lands precisely on its expected value *after a defect was suspected* deserves more scrutiny, not less — it is the signature of cancellation.
>
> **Print the arithmetic in the artifact**, so a reader can falsify it rather than only agree with it: `15+11+21+52+29+24+18+31 = 201`, then `201+32+18+1 = 252`. Run `scripts/record_checks.py sums <file>` over the artifact to evaluate every such line. It prints `evaluated N`, exits 1 naming each false line, and exits 2 when it found no sum. It cannot see offsetting errors in the addends, so it does not replace the per-entry check.
>
> **Re-check the explanations, not just the numbers.** A footnote can explain a correct figure with one cause while two other effects cancel inside it. A repair pass that targets only wrong figures never reaches that footnote.

Specify checks at the grain the artifact claims, not the grain that is convenient to measure. A table that claims only "the total is 252" has made a weaker claim, and a reader who needs the stronger one cannot recover it from the total.

---

## 2. State the Denominator With the Number, and Never Re-Use a Row Set Across Questions

> [!constraint] A wrong number is wrong everywhere and you notice it; a filtered denominator is right everywhere the filter is inert and wrong only where it bites
> — which is, by construction, the part of the data that differs from the rest. The failure is silent, correlated with the interesting cases, and survives spot-checks, because any cell you happen to verify is likely one of the ones that agrees.
>
> WRONG — a bare figure, and a label naming a population the row set was not built for:
> ```
> 218
> all team-path transcripts by version: 63    # rows filtered for a reviewer aggregate; the true figure is 69
> ```
> CORRECT — the population beside the figure, from a row set built for this question:
> ```
> 218 of 281 subagent transcripts
> ```
>
> Two sub-rules:
>
> - **A row set built for one purpose must not be reused for a second aggregate without re-checking the filter against the new question.** The filter that makes a reviewer aggregate correct makes a corpus histogram wrong. Same rows, different question, different validity.
> - **A detector keyed on *content* rather than *structure* is blind wherever the content varies** — and content varies most in exactly the cases worth measuring. **A keyword detector systematically undercounts exactly the wording a remediation is trying to promote.** Pair on a structural signal (`is_error`, a hook-fire record, a spawn record) and use text only as corroboration.
>
> **State the population beside the figure.** A figure whose population is unstated cannot be audited, and writing the population down is usually enough to catch the mismatch yourself.
>
> **A completeness guard's denominator must not share its numerator's filter.** The guard form of this rule, where `compared == total` passes over a row the parser's region rule dropped, is in `gate-denominator-integrity.md` § "7. A Guard's Denominator Must Not Pass Through the Filter It Guards". This section owns the reporting form.

**When a re-measurement disagrees with a published figure, find the cause before recording the correction.** "Wrong digit" and "wrong population" demand different fixes, and only one of them tells you the rest of the numbers need re-checking.

**Independent verification protects against inheriting *their* defect and does nothing about introducing your own.** A relayed figure still reads as somebody else's claim. A self-checked one reads as settled, so an unverified self-check is **more** dangerous than a relayed figure.

---

## 3. A Bare Count in Prose Is a Claim, Not a Measurement — Name the Members Inline

> [!constraint] Re-derive a count from the artifact at every hop that depends on it, and name the members inline where the count is load-bearing
> A config template held **six** keys of one family, and the function that wrote that family wrote **four**. Two handler docs said the function *"overwrites the six keys in place"*, borrowing the template's cardinality. When a sprint added two keys to the write set, the wrong numeral travelled on: one runner wrote "eight". **A shared cardinality between two nearby sets is a coincidence that reads as a cross-check.**
>
> **Review cannot catch this.** A diff showing `six → eight` looks like diligent maintenance, and a diff showing `six → six` looks like nothing happened. A reviewer reading only the diff cannot tell a re-derived count from a skipped one.
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
> - **Treat a shared cardinality between two nearby sets as a hazard, and say which set you mean.** A runner who "reconciles" two such counts to match reintroduces the original defect.
>
> This applies with equal force to the orchestrator's own Recovery and summary files. **An acceptance gate that verifies nine claims does not vouch for a tenth that arrived in the same message.**

§1 and §3 both end at "re-derive rather than inherit", but the artifact differs and so does the tell. §1's subject is a computed aggregate inside one table, caught by diffing components against their own sources. §3's subject is a numeral that travelled through prose across files, caught by enumerating the members. A merged rule collapses into "check counts", which is true of neither and actionable in neither.

---

## 4. A Measurement Stored Inside Its Own Subject Needs a Convergence Argument

> [!practice] Writing the number changes the number
> A file that records its own final line count, byte count or token estimate in its header changes that figure by writing it. A byte count measured at 47,510 and written as "47,510" made the file 47,571.
>
> - **Measure after the last edit, not before it.** Treat the header as part of the content being measured, not as metadata outside it.
> - **Make the correction a same-length substitution.** A correction that alters the string's length re-invalidates itself, and you loop.
>
> WRONG — measure before the last edit, and treat the header as outside the content:
> ```
> measure 47,510 bytes  →  write "47,510" into the header  →  the file is now 47,571, and the header is stale
> ```
> CORRECT — measure after the last edit, and correct with a same-length substitution:
> ```
> write "47,510"  →  re-measure 47,571  →  replace "47,510" with "47,571"  →  converged in one pass
> ```
>
> Run `scripts/record_checks.py self-count <file> --field lines` or `--field bytes` after the last edit. It compares the figure the file records about itself with the final file, exits 1 printing both numbers, and exits 2 when the file records no figure. Bytes are raw bytes on disk, so a CRLF checkout differs from its committed blob by the line count.

This is a mechanical trap rather than an epistemic one, which is why it is a practice and not a constraint. §1 to §3 are about what a figure *means*. This section is about the order in which two edits have to happen.

---

## 5. Every Operand of a Byte Identity Comes From One Byte Instrument

> [!constraint] A character-counted operand in a byte identity produces a deficit that reads as content loss
> `length($0)` is a character count in any locale-aware `awk`. It equals the byte count only while the input is pure ASCII. A markdown corpus with typographic punctuation is not pure ASCII. A gate that asserts byte equality takes every operand from the same byte-level instrument: `len(open(path, 'rb').read())`, `wc -c`, or a byte regex. One character-counted operand produces a deficit equal to the count of multi-byte characters.

A 58,562-byte line holding 723 non-ASCII bytes read 58,091 by `awk`. Compared against byte figures, that operand reports 471 bytes of "lost content" on work that lost nothing.

> ```
> WRONG — one operand from awk, the rest from bytes:
> PRE   = awk length($0)          # 58091 characters
> POST  = len(changelog_bytes) + len(pointer_bytes)   # bytes
> assert PRE == POST              # fails by the non-ASCII byte count
>
> CORRECT — every operand from the same byte instrument:
> PRE   = len(re.search(rb'(?m)^\*Last Updated:[^\r\n]*', data).group(0))   # 58562
> POST  = entry_content_bytes + marker_bytes + prefix_bytes                  # 58476 + 72 + 14
> assert PRE == POST
> ```

Two points follow.

- **Measure conservation in bytes end to end.** The baseline, the per-destination accounting and the live re-measure all come from `rb` reads or `wc -c`. Never from `awk`, `${#var}` or `len(str)`.
- **A brief's pinned measurement command is a claim to run once and cross-check, not an instrument to trust.** Only two instruments side by side expose a mechanism the brief did not predict.

Check 51 in `scripts/lint_gate_checks_measure.py` enforces the first point on task files. `scripts/lint_verification_gates.py` runs it and reports an ERROR for a byte-equality gate that takes an operand from `awk length(`, `${#var}` or `len(` over a decoded string. The check reports a `len(` only when its operand traces to decoded text in the same command. It does not report a raw-bytes subprocess read, an item count, or an operand it cannot trace.

Name the instrument beside each byte figure, and treat blob bytes against checkout bytes as the same trap: [`measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md`](measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md) § "8.12 A byte pin names its instrument: blob bytes and checkout bytes differ under autocrlf".

[`measurement-discipline.md`](measurement-discipline.md) § "8.1 Line-count measurements MUST use `wc -l`, not Read-output line numbers" governs line counts. This section is the byte-and-character counterpart.

---

## 6. A Pinned Occurrence Count Comes From a Findall Over the Bare Pattern

> [!constraint] Take an occurrence count from the instrument the executor will assert with, and run that instrument once before pinning the number
> Context added to a shell search pattern becomes part of the match. A search that prints each match (`-o`) with trailing context can absorb the next occurrence on the same line. A line count (`Grep` count mode, or a shell `-c`) counts lines, not occurrences. A brief pinned "5 replacements" on a file that held 6, because one line held the pattern twice.
>
> ```
> WRONG — count occurrences from a context-padded match, or from a line count:
> re.findall(rb'.{0,60}PATTERN.{0,40}', data)      # 6 matches, but 7 occurrences
> Grep  pattern='PATTERN'  output_mode='count'     # 6 lines, not occurrences
>
> CORRECT — count with a findall over the bare pattern; use context only for display:
> python -c "import re,sys; print(len(re.findall(rb'PATTERN', open(sys.argv[1],'rb').read())))" file   # 7
> ```

A brief that pins a replacement count or an occurrence count takes it from the same kind of instrument the executor will assert with. That instrument is `re.findall` or `re.subn`. Run it once before pinning the number.

The trigger is a file where one line can hold the pattern twice. Doc comments, examples and tables are the usual places.

---

## 7. Both Readings of a Before/After Level Gate Come From One Instrument

> [!constraint] Read the base and the current figure with the same instrument, then attribute the delta by commit
> Under `core.autocrlf=true` a blob holds LF and the checkout holds CRLF, one byte more per line. A read-gate level boundary sits close to the sizes of these files, so that difference can cross it. A handler read 24,681 tokens (WARN) as a base blob and about 25,000 tokens (OVER) as a checkout. The report said the series had moved it to OVER.
>
> The HEAD blob, measured with the same instrument, read 24,699 tokens. That is still WARN. The series had added 18 tokens through a one-line edit.
>
> ```
> WRONG — base from the blob, current from the checkout:
> base   git show <base>:run.md → measure → 24,681 WARN
> now    measure run.md (CRLF)  → 25,000 OVER   # "the series pushed it over"
>
> CORRECT — one instrument on both sides, then attribute the delta by commit:
> base   git show <base>:run.md → measure → 24,681 WARN
> now    git show HEAD:run.md   → measure → 24,699 WARN   # +18, no level change
> git log --numstat <base>..HEAD -- <path>    # whose commit moved it
> ```

A second file in the same row did cross from OK to WARN on the blob instrument. `git log` showed that two peer commits caused it. The plan's one-line edit did not.

Section 5 carries the same trap for byte pins. A level gate is the token form of it.

---

## 8. Two Recounts Disagree by Tokenizer: Reconcile the Unmatched Lists, Never the Totals

> [!constraint] List each unmatched item and classify it before comparing two totals
> A runner reported 15 inline-code spans with 0 unmatched, and 55 digit-bearing figures with 11 unmatched. The orchestrator recounted the same blob. It split on whitespace and kept punctuation. It read 15 spans with 1 unmatched, and 60 figures with 14 unmatched.
>
> Listing the orchestrator's unmatched items settled it. The one span belonged to a cut paragraph that the set-difference section recorded. The extra figures were punctuation variants of terms still present, such as `(see 10.2` and `(see 10.2)`. The rest was the tail of a cut guard that the set-difference record also named.
>
> ```
> WRONG — compare two totals from two instruments:
> runner:       figures 55, unmatched 11
> orchestrator: figures 60, unmatched 14   -> "mismatch" or "close enough"
>
> CORRECT — list each unmatched item and classify it:
> for each item in orchestrator_unmatched:
>     present in the edited file under another punctuation?   -> instrument artifact
>     recorded in ## Set Difference with a survivor?          -> covered
>     neither?                                                 -> a lost term: the finding
> ```

The gate passes when every unmatched item is an artifact or covered. The record names which instrument produced which count. A gate that demands equal totals fails correct work. A gate that accepts "close enough" passes a real loss.

---

## 9. A Fan-Out Pins the Selection Grain as a Literal, Not Only the Instrument

> [!constraint] Pin what is put on the scale as well as how it is weighed
> A measurement has two parts that drift independently. The instrument is how the number is taken, here bytes divided by 2.6. The selection is which text counts as kept. A method gate checks how a number was taken. It does not check what was put on the scale.
>
> Four outputs of one fan-out gave five readings, and all passed the method gate. Each used the same instrument and read a different grain:
>
> | Output | Grain read | Example target | Share of source kept |
> |---|---|---|---|
> | Output 1 | per file | `callout-conventions.md` 6,985 → 2,106 | 30% |
> | Output 1 | per file | `rule-authoring.md` 7,625 → 3,879 | 51% |
> | Output 2 | mixed | four files | 59% to 81% |
> | Output 3 | per rule section | `read-confirm-act-protocol.md` 22,430 → 17,362 | 77% |
> | Output 4 | per rule section, every heading and Reviewer Check kept | `scaffolding-hygiene.md` 23,919 → 19,086 | 80% |

Four rules follow.

1. Pin the selection grain as a literal. Write "one WRONG/CORRECT pair per file" or "one pair per `##` rule section". Never write "the operative rule plus one pair".
2. Make each output state its grain beside its method line.
3. At the batch gate, compare the kept share across outputs. A spread of 30% to 87% for one disposition is the signal, and only the set shows it.
4. When the spread has already happened, never average or sum across grains. Route it to the consolidator. The consolidator pins one grain and re-derives the other class, or reports the two classes separately.

```
WRONG — the brief pins the instrument and leaves the selection to each runner:
Step 5: for compress, sum the bytes of the operative rule sentences plus one
        WRONG/CORRECT pair and divide by 2.6.
# runner A: one pair per file        -> 30-51% kept
# runner B: one pair per rule section -> 77-87% kept   (both pass the method gate)

CORRECT — the brief pins both, and the output declares its grain:
Step 5: for compress, keep every heading, each section's operative rule sentences,
        and ONE WRONG/CORRECT pair per FILE. Sum the kept bytes, divide by 2.6.
Output header: **Target-token method:** bytes / 2.6. **Grain:** one pair per file.
```

The trigger is any fan-out where several runners each produce a figure that a later step sums or compares. Compress targets, kept-line counts, "core" token budgets and coverage percentages all qualify. The vocabulary half of the same discipline is [`dispatch-batch-gate.md`](dispatch-batch-gate.md) § "4. Pin the Output Vocabulary Before Fan-Out; Diff the Emitted Shapes After".

---

*Cross-reference: [`measurement-discipline.md`](measurement-discipline.md) §8.9 (the recorded figure a gate compares against) · [`gate-heuristic-verifier-patterns.md`](gate-heuristic-verifier-patterns.md) §4 (denominator scoping for a coverage gate) · [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.2 (a gate on a derived ratio names its column, grain and denominator) · [`session-context-budget.md`](session-context-budget.md) § File Size Limits (the three Read-tool gates a self-measuring header reports against)*
