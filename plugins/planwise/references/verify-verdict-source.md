---
description: A verdict rests on the primary source it re-read, not on who agrees with it. Covers the symbol-level search a negative verdict requires, what a "confirmation" must name, why severity does not ratchet on agreement, why a runner's accurate status block cannot see a cross-artifact invariant, why the orchestrator is not a safe place for an unverified negative, how to make a failure name its members, how to classify every non-zero exit as an instrument defect or a subject finding before acting on it, and why a criterion that names an instrument's printed line is met only by that line, and why a quotation deliverable is accepted by finding each quote in its source rather than on heading presence or the runner's own assertion, and why a predicate that names fields the build does not emit is graded by the field that carries the same fact, never marked untestable from the absence of its own names. Consult before recording ABSENT, before confirming another agent's finding, before accepting a batch of status blocks, before writing a negative into Recovery, when a verifier exits non-zero, before accepting a task whose criterion names a printed line, before accepting a copy or quote task, and before grading a predicate whose named fields the log does not carry.
consult-when: About to record ABSENT, confirm another agent's finding, accept a batch of status blocks as whole-set evidence, or write a negative into Recovery — search the code for the symbol not the prose, name the primary source re-opened, keep severity flat on agreement, recompute cross-artifact invariants on disk, make a failure name its members, classify a non-zero exit as instrument or subject, and treat a criterion that names a printed line as met only by that line, and accept a copy or quote deliverable by finding each quote in its source, not on heading presence, and grade a predicate whose named fields the log lacks by the field that carries the same fact, never "untestable" (§11)
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Verdict's Source — A Verdict Is Only as Good as the Source It Re-Read

**Purpose:** Several verdicts were confident, internally consistent, and wrong — each because the evidence it rested on **could not have contained the answer**. One searched prose for a feature that lives in code and returned ABSENT. One "confirmed" a claim about a document without re-opening the document. One reported an accurate status block against a question its runner was never asked. Two more read an exit code or a printed line that did not come from the subject the gate exists to judge (§8, §9).

**Read this when** you are about to record ABSENT, confirm another agent's finding, accept a batch of runner status blocks as evidence for a whole-set property, or write a negative into Recovery. Read §8 when a verifier exits non-zero. Read §9 when you accept a task whose criterion names a line an instrument prints. Read §10 when you accept a delegated task whose brief says "copy" or "quote verbatim". Read §11 when a grader reports a predicate "untestable" because the fields it names are absent from the log.

The known failure direction for delegated classification is **under-**classification: a runner calls something FIXED that is still live. A false ABSENT and an over-classified severity produce *extra* work instead, so nothing downstream fails loudly. A false PRESENT is usually caught immediately. A **false ABSENT propagates as work to be done**, and it surfaces only if someone recomputes the claim against the primary source.

Two neighbouring rules meet this one at a single point each. [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) governs what the *dispatcher writes into the brief*. This file governs what the *runner's verdict rests on*. A primed verdict is the case where recomputation is least likely to happen. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §1 establishes the batch gate as a distinct orchestrator-owned stage, and its §3 cross-checks claims that appear in more than one output. §4 below is about a *single* runner's block being accurate and still blind.

## Table of Contents

- [1. A Negative Verdict About a Feature Rests on a Symbol-Level Search of the Implementation, Never on Prose](#1-a-negative-verdict-about-a-feature-rests-on-a-symbol-level-search-of-the-implementation-never-on-prose)
- [2. A "Confirmation" Must Name Which Primary Source It Re-Read](#2-a-confirmation-must-name-which-primary-source-it-re-read)
- [3. Severity Does Not Ratchet on Agreement](#3-severity-does-not-ratchet-on-agreement)
- [4. A Status Block Reports Only Against Questions Its Author Knew to Ask](#4-a-status-block-reports-only-against-questions-its-author-knew-to-ask)
- [5. The Orchestrator Is Not a Safe Place for an Unverified Negative](#5-the-orchestrator-is-not-a-safe-place-for-an-unverified-negative)
- [6. Make the Failure Output Name Its Members, and Repair by Resuming the Author](#6-make-the-failure-output-name-its-members-and-repair-by-resuming-the-author)
- [7. When a Verdict Is Downgraded, Look for the Salvageable Finding](#7-when-a-verdict-is-downgraded-look-for-the-salvageable-finding)
- [8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result](#8-classify-every-non-zero-exit-by-cause-before-treating-it-as-a-bug-or-a-result)
- [9. A Criterion That Names an Instrument's Line Is Met Only by That Line](#9-a-criterion-that-names-an-instruments-line-is-met-only-by-that-line)
- [10. A Quotation Deliverable Is Accepted by Finding Each Quote in Its Source](#10-a-quotation-deliverable-is-accepted-by-finding-each-quote-in-its-source)
- [11. A Predicate That Names Fields the Build Does Not Emit Is Graded by the Field That Carries the Same Fact](#11-a-predicate-that-names-fields-the-build-does-not-emit-is-graded-by-the-field-that-carries-the-same-fact)

---

## 1. A Negative Verdict About a Feature Rests on a Symbol-Level Search of the Implementation, Never on Prose

> [!constraint] The near-miss is the argument
> A negative verdict about a feature rests on a search of the code for the symbol that would implement it, never on a search of the prose that would describe it.

A prose search tests only **whether someone described the feature in the words you guessed**, and its empty result is silently reported as a strong negative. Before returning ABSENT:

1. Grep the code for the function, class or constant that would implement it, not the phrase that would document it.
2. Search the whole tree, not the one file the task named. Refactors relocate symbols, so a single-file miss is a relocation, not an absence.
3. Distinguish a definition from an import or re-export, and report which file holds the definition.
4. If the Grep pattern was a guess at wording, say so in the report and treat the result as provisional.

A positive verdict names the thing it found, and the next reader can open it. A negative names only the search that failed, and the next reader inherits the search's blind spot without seeing it.

WRONG — search the handler prose with a guessed phrase, then report a strong negative:
```
Grep 'orphaned.block|fails to parse|ParserError' over the handler docs -> no hits
verdict: ABSENT in both trees
```
CORRECT — search the code for the implementing symbol, and report the file that defines it:
```
Grep '_detect_orphaned_block_signature' over the whole tree -> defined in doctor_cli.py
verdict: PRESENT; the handler says "parse error", which the guessed phrase missed
```

---

## 2. A "Confirmation" Must Name Which Primary Source It Re-Read

> [!constraint] Re-derived reasoning from the same starting point reaches the same conclusion by construction
> If a second agent's verification did not open the artifact the claim is *about*, it has re-derived the reasoning, not tested it.

A confirmation that cannot name the primary source it re-opened is a restatement, and a restatement adds a second signature to one unexamined read. A finding of the form "X conflicts with Y" is verified by checking X and Y. When X is code and Y is a document, checking X feels like verification and is much easier. The document gets inherited from whoever summarized it first.

For a claim that an artifact's stated plan is wrong:

1. Re-read the artifact's own text at the point the claim disputes. Quote it.
2. Check whether the artifact already anticipates the objection. Proposals routinely carry alternatives that a summary drops.
3. Verify each half of a two-sided claim separately, and say which half each piece of evidence supports.
4. Do not let severity rise on hop count.

WRONG — verify the code half, and inherit the document half from a summary:
```
claim:    the item's proposed --prune-stale collides with an existing --prune-stale
verified: the flag exists in the code
verdict:  "must pick a distinct flag name", Error severity, confirmed
```
CORRECT — re-read the disputed text at the point the claim disputes, and quote it:
```
item-3 text: gains an opt-in flag (or a sibling --prune-upgrade-leftovers)
verdict:     the item already names the alternative, so the collision finding falls
```

---

## 3. Severity Does Not Ratchet on Agreement

> [!constraint] If the second pass added no new evidence, its severity contribution is zero
> Count the evidence each hop added. Where the count is zero, the severity stays where the first hop left it.

Agreement is not corroboration. This section stays separate from §2 because it is the half a reader drops: a rule that only says "re-read the source" leaves severity free to rise on agreement.

WRONG — severity rises on agreement while the evidence stays flat:
```
raised -> confirmed -> Error severity        # three judgements, one unexamined read
```
CORRECT — each hop states the evidence it added:
```
hop 1: raised, one read       hop 2: agreed, new evidence 0       severity: unchanged
```

---

## 4. A Status Block Reports Only Against Questions Its Author Knew to Ask

> [!constraint] A `COMPLETE` status is a claim about the task, not about the set
> A cross-cutting invariant that spans *all* outputs — coverage, uniqueness, no-duplicates, total-count reconciliation — is by construction invisible from inside any single runner, however careful.

Gate acceptance of the batch separately from acceptance of each runner. Recompute every cross-artifact invariant from the artifacts on disk after the batch returns. Treat status blocks as *leads*, never as evidence for a whole-set property. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) owns the batch gate as an orchestrator stage and the cross-checks between outputs. This section is the reason a lone runner's block needs the same treatment even when there is no sibling to cross-check against.

The block below was blameless. Its runner over-applied an identifier-isolation rule to its Part's own **routing metadata**, so the Part held zero item identifiers while every self-reported field stayed accurate. Better runners would still need the recount.

WRONG — accept the set because every field of every block is accurate:
```
TASK_STATUS: COMPLETE, correct path, correct line count, ledger Item1=10, Item2=6, Item3=9, Item4=5
orchestrator: all 28 source items appear exactly once
```
CORRECT — recount the set from the artifacts on disk, and name the gap:
```
recount from Part headers: 24 of 28; the four missing IDs named
```

---

## 5. The Orchestrator Is Not a Safe Place for an Unverified Negative

> [!constraint] Recompute a negative before recording it, or record it explicitly marked as unverified
> Passing through the orchestrator confers no verification but does confer authority: the claim arrives downstream as an established finding rather than a runner's claim.

Pair the rule with an explicit downstream allowance to re-read and overturn. A "suspected false ABSENT" allowance is what caught the incident in §1.

§5 and §2 both say the orchestrator's agreement is not evidence, and they are separated deliberately. §2 governs a *second agent* confirming a *runner's* claim. §5 governs the *orchestrator* recording an unverified claim into Recovery, where it acquires authority for every downstream reader. The remedies differ: §2 adds a re-read step, and §5 adds an unverified marker.

WRONG — record the runner's ABSENT in Recovery and report it to the user before it is checked:
```
Recovery: feature ABSENT in both trees
```
CORRECT — re-verify by symbol search across both trees, or carry the marker and the allowance:
```
Recovery: feature ABSENT (runner claim, unverified; a suspected false ABSENT may be re-read and overturned)
```

---

## 6. Make the Failure Output Name Its Members, and Repair by Resuming the Author

> [!practice] Two mechanics that made these repairs cheap
> A gate names the specific missing members, which makes the diagnosis immediate and the fix precise. The repair resumes the same agent, because its context holds the full task.

A third mechanic belongs here: **when a scoped rule exists, state its scope in the task file at the point of use**, not only in a general reference. The runner in §4 had the correct rule and applied it one level too broadly. The Expected Output skeleton did say "IDs allowed here", which is why the fix was a one-line resume rather than a rewrite.

WRONG — a bare count, and a re-dispatch that rebuilds the task:
```
Gate output:  "24 of 28"
Repair:       re-dispatch; the new runner rebuilds the context from nothing
```
CORRECT — the output names its members, and the repair resumes the author:
```
Gate output:  "MISSING: 033, 046, 047, 052"   (a uniqueness gate prints "DUPLICATE: <ids>" the same way)
Repair:       resume the same agent, metadata only; landable blocks stay untouched
```

---

## 7. When a Verdict Is Downgraded, Look for the Salvageable Finding

> [!practice] An over-classified finding is usually a real observation wearing the wrong conclusion
> Split a downgraded finding into its false half and its true half, and keep the true half. Discarding the row discards it.

WRONG — the verdict falls, so the whole row goes:
```
"rename the flag" is false -> delete the finding
```
CORRECT — the false half goes, and the true half stays as a finding:
```
"rename the flag"  -> noise, dropped
the existing pruner writes its own output into upgrade-backups/prune-{YYYY-MM-DD}/,
inside a directory the proposal sweeps -> a real nesting hazard absent from the filed item, kept
```

---

## 8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result

Decide which side is wrong, the instrument or the subject, from primary evidence before you route a fix.

> [!constraint] An exit code says the check did not pass. It does not say why
> "The instrument is broken" and "the subject is defective" print the same number. A verifier that has never reached its subject has never tested it. Fixing the verifier does not clear the gate. It lets the gate run for the first time, and the first honest run on a new subject usually fails.

A session criterion read "`<checker>` exits 0 over the probe's `<sidecar>`". The first run exited 1 with the transcript on disk, so that exit was the instrument's. Two repairs later the checker read the sidecar for the first time and exited 1 again, and that one was real.

WRONG — three runs recorded as one repeated failure:
```
<checker> → exit 1   # "still failing"
<checker> → exit 1   # "still failing"
<checker> → exit 1   # "still failing"
```
CORRECT — each exit classified, the instrument fixes separated from the subject finding:
```
exit 1: DRIFT no archived transcript   → INSTRUMENT (wrong key path + ambiguous glob); transcript present on disk
exit 1: version check on unversioned records → INSTRUMENT (67/279 records carry no `version`); skip them
exit 1: native_event 'UserPromptSubmit' undeclared → SUBJECT (<module> log writer default + register site); route to the module's owner
```

Three consequences:

- **Classify every non-zero exit by cause before acting on it.** Read the failing message. Then confirm from primary evidence whether the instrument could have seen the subject: the transcript is on disk, the key path exists, the glob matches one file. An instrument that could not have seen its subject is the empty-gate hazard with a non-zero exit code.
- **Expect the next failure after fixing the instrument, and budget for it.** Report the movement as exactly what it is: the criterion moved from unmeetable-by-instrument to unmet-by-defect. Do not soften it into "the checker works now".
- **Do not let the criterion's wording hide the distinction.** "Exits 0" collapses two questions. Write it as "the checker reads the sidecar's transcript (the step names the session id) and reports OK". An instrument failure and a subject failure then become different unmet clauses with different owners.

**Applies to** any success criterion phrased "exits 0" or "prints PASS" over a verifier the same project authored. It applies to the first run of a verifier against a new class of input (a new arm, a new record type, a second file that matches an old glob). At closeout, record whether a criterion is unmet because the instrument could not run or because the subject failed, never just "unmet".

---

## 9. A Criterion That Names an Instrument's Line Is Met Only by That Line

> [!constraint] A criterion that names an instrument's output line is a claim about that line
> The number that satisfies it must appear where the criterion says it appears. A correct number stored elsewhere, plus a paragraph in a proof document that explains the gap, satisfies the author's intent and fails the criterion. Every later reader of the instrument sees the wrong number and never sees the paragraph.

WRONG — the dump prints a false positive on the negative control, and the proof file explains why it is not one:
```
(3) marker records: 21        # on an archive where no module ran
<proof>.md: "the strict count is 0; the broad dump (21) is recorded here so the two are never conflated"
```
CORRECT — the dump carries both readings under distinct labels, and the criterion's line reads zero:
```
(3) marker records (<MARKER> only): 0
(3b) candidate records (<NAME> or "<shared phrase>"): 21
```

Three consequences:

- **The instrument is the artifact of record, not the proof file.** A proof file is read once, at acceptance. An instrument's output is read on every later run. When the two disagree, the instrument wins in practice, so fix the instrument. [`gate-artifact-over-instrument.md`](gate-artifact-over-instrument.md) §10 states the artifact-over-instrument rule.
- **"The criterion is satisfied by a different search" is the tell.** When a runner argues the criterion holds via a structure the criterion did not name, the argument is the finding. Recompute from the instrument's own output before accepting.
- **The fix is a relabel, not a redesign.** The defect was one label carrying two meanings, and two lines made the criterion's line true.

**Applies to** accepting a delegated task whose criterion names a specific printed line, count or field. When you author a criterion for an instrument, name the label the reader will see, and make that label mean one thing.

---

## 10. A Quotation Deliverable Is Accepted by Finding Each Quote in Its Source

> [!constraint] "Quote verbatim" is a property of each quoted line, and acceptance tests it per line
> Heading presence, file size, a clean file-measure gate and the runner's own "all quotes match" sentence test something else. A model asked to copy fills a gap with a fluent approximation when the source is thin. Every gate that does not open the source sees the approximation as a quote.

One search for the message prefix `CLI build changed` across the Output directory exposed both an invented line and the wrong source file in under a minute.

WRONG — accept on structure and on the runner's assertion:
```
Grep '^## ' <target-file>          # 11 headings present
measure_files.py <target-file>     # OK
status block: "Every output quoted beneath each command matches its source"
→ COMPLETE
```
CORRECT — for each block that claims to be a quote, find the line in the recorded source:
```
python -B scripts/check_quote_sources.py <target-file> --source <output-file>
    UNMATCHED <target-file>:<line> → the quote is invented, or its source is a file the brief did not allow
for each quote the script cannot see:
    take one distinctive substring (a number, a hash, a message prefix)
    Grep the declared source Output file(s) for it
```

`scripts/check_quote_sources.py` checks three labelled shapes: a fenced block, a `>` blockquote run, and a table cell in a column whose header is the label word or ends in it in parentheses. A run that reports `0 quote block(s)` proves nothing, because an unlabelled quote is not checked. Fall back to the per-quote search for any such quote.

Two operative rules:

- **The brief names a per-quote check, and the orchestrator runs it.** The criterion reads "every quote traces to a line in `<task>`'s Output". The acceptance step searches one distinctive substring per quote. A miss means the quote is invented or its source was not allowed. [task-content-fidelity.md](task-content-fidelity.md) §9.A.16 covers the brief side: every quote source must sit in Required Context.
- **A "quoted" table enumerates the full pinned set, with a gap column.** The brief's list is the denominator. Each row says `recorded in <source>` or `none (gap)`. A table with fewer rows than the brief's list is itself a finding.

**Applies to** any README, runbook, report or doc task whose brief says "copy", "quote verbatim", "do not run" or "every number traces to". It applies most to the cheapest model tier, but the failure is not tier-specific, because the gate is what failed. Heading presence is necessary and never sufficient.

§2 covers a second agent's confirmation, which must name the primary source it re-read. This section covers the orchestrator's acceptance of a copy deliverable.

---

## 11. A Predicate That Names Fields the Build Does Not Emit Is Graded by the Field That Carries the Same Fact

> [!constraint] A predicate's field names are a claim about the build at design time, and they expire independently of the fact they capture
> When the names miss, the fact may still be on the row under another name. "Untestable" is a claim about the evidence. It is false whenever the evidence exists under a different key.

WRONG — grade by the design's names, conclude from their absence:
```
Grep <field-a>   -> 0 matches
Grep <field-b>   -> 0 matches
verdict: store round-trip untestable; record as unproven
```
CORRECT — grade by the field the build writes for the same transition:
```
<module>.ts: restored = typeof mine?.lastStep === 'number' ? ... : null
line 3 (first bind):  <carrier-field>: null   -> wrote {sid: {lastStep: 0}}
line 8 (reload bind): <carrier-field>: 0      -> read back the entry written before the reload
verdict: survival held by presence; field names <field-a>/<field-b> absent (naming drift, flagged)
```

Three consequences follow.

1. **On a missing field, read the writer before grading.** Open the code that emits the row. Find the field that encodes the same state transition and grade against it. Say which field stood in and why it carries the same fact.
2. **Distinguish "not held as worded" from "untestable".** The first is a naming drift between design and build. It is real and worth a flag. The second says the run cannot answer the question, and it needs a reason that survives a look at the code.
3. **Recompute a "cannot be determined" verdict from primary evidence, as you would a PASS.** A "cannot be determined" label is a verdict. It softens a held clause into an open one, which is the under-classification direction. Treat it with the same suspicion as a PASS read off a summary line.

**The recording rule.** A design document that names fields records the drift and the stand-in field in the write-up. It does not record a lost result. The orchestrator recomputes a delegated grader's "cannot be determined" verdict from the row and the code that wrote it, as it would a PASS or FAIL. §5 ("The Orchestrator Is Not a Safe Place for an Unverified Negative") covers why an unverified negative must not travel on.

**Applies to** any grading of a design predicate, probe sheet or acceptance criterion that names log fields, event keys or column names. §1 requires a symbol-level search before a negative verdict about a feature. This section covers the same search applied to the field a predicate names.

---

*Cross-reference: [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) (the dispatcher's side — link, never merge) · [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §1, §3 · [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) (name the members inline) · [`verification-gate-evidence.md`](verification-gate-evidence.md) (a gate instrument versus the artifact it measures — a different "read the artifact")*
