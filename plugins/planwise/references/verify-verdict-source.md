---
description: A verdict rests on the primary source it re-read, not on who agrees with it. Covers the symbol-level search a negative verdict requires, what a "confirmation" must name, why severity does not ratchet on agreement, why a runner's accurate status block cannot see a cross-artifact invariant, why the orchestrator is not a safe place for an unverified negative, how to make a failure name its members, how to classify every non-zero exit as an instrument defect or a subject finding before acting on it, and why a criterion that names an instrument's printed line is met only by that line, and why a quotation deliverable is accepted by finding each quote in its source rather than on heading presence or the runner's own assertion, and why a predicate that names fields the build does not emit is graded by the field that carries the same fact, never marked untestable from the absence of its own names. Consult before recording ABSENT, before confirming another agent's finding, before accepting a batch of status blocks, before writing a negative into Recovery, when a verifier exits non-zero, before accepting a task whose criterion names a printed line, before accepting a copy or quote task, and before grading a predicate whose named fields the log does not carry.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Verdict's Source — A Verdict Is Only as Good as the Source It Re-Read

**Purpose:** Several verdicts were confident, internally consistent, and wrong — each because the evidence it rested on **could not have contained the answer**. One searched prose for a feature that lives in code and returned ABSENT. One "confirmed" a claim about a document without re-opening the document. One reported an accurate status block against a question its runner was never asked. Two more read an exit code or a printed line that did not come from the subject the gate exists to judge (§8, §9).

**Read this when** you are about to record ABSENT, confirm another agent's finding, accept a batch of runner status blocks as evidence for a whole-set property, or write a negative into Recovery. Read §8 when a verifier exits non-zero. Read §9 when you accept a task whose criterion names a line an instrument prints. Read §10 when you accept a delegated task whose brief says "copy" or "quote verbatim". Read §11 when a grader reports a predicate "untestable" because the fields it names are absent from the log.

The first three fail in different directions, which is why they belong in one rule. The known failure direction for delegated classification is **under-**classification — a runner calling something FIXED that is still live — and that is what closeout checklists train attention on. A false ABSENT (over-reporting a gap) and an over-classified severity (over-reporting a defect) both produce *extra* work rather than missing work, so nothing downstream fails loudly. They surface only if someone recomputes the claim against the primary source, including the claims that arrived pre-confirmed.

The cost is asymmetric and specific. A false PRESENT is usually caught immediately — someone looks for the code and it isn't there. A **false ABSENT propagates as work to be done**, and is discovered redundant only after someone does it, or worse, after they implement a second conflicting copy. Here it would have carried a work item to re-implement a shipped feature, against a backlog record already archived COMPLETE that would have kept a gap that did not exist.

Two neighbouring rules meet this one at a single point each. [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) governs what the *dispatcher writes into the brief*; this file governs what the *runner's verdict rests on*. A primed verdict is the case where recomputation is least likely to happen. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §1 establishes the batch gate as a distinct orchestrator-owned stage and §3 cross-checks claims that appear in more than one output; §4 below is about a *single* runner's block being accurate and still blind.

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
> A verification task was asked whether a proposed fix — *"doctor flags an unparseable config with an orphaned-block hint"* — had landed. It grepped the handler documentation for `'orphaned.block|fails to parse|ParserError'`, found nothing, and returned **ABSENT in both trees**. The feature was fully implemented: `doctor_cli.py` defines `_detect_orphaned_block_signature()` and calls it from the config parse check, which reads the config as text, `yaml.safe_load`s it, and returns `{"state": "ok"|"unparseable", "report": …}`. The live handler text did say *"parse error"* — it simply did not use the phrase the search guessed at.
>
> Before returning ABSENT:
>
> ```
> 1. Grep the CODE for the function/class/constant that would implement it —
>    not the phrase that would document it.
> 2. Search the WHOLE tree, not the one file the task named. Refactors relocate
>    symbols; a single-file miss is a relocation, not an absence.
> 3. Distinguish a DEFINITION from an import or re-export, and report which
>    file holds the definition.
> 4. If the Grep pattern was a guess at wording, say so in the report and treat
>    the result as provisional.
> ```

A prose search is dangerous rather than merely weak. Documentation and implementation are separate artifacts maintained by separate edits, so searching prose tests **whether someone described the feature in the words you guessed** — a much weaker proposition than whether it exists — and a weak test that returns empty is silently reported as a strong negative. It is also cheap to produce: fast, thorough-sounding in a report (*"greped for orphaned-block guidance — no hits"*), and requiring exactly one guessed string to succeed.

The asymmetry is the reason to treat a negative differently from a positive. A positive verdict names the thing it found, and the next reader can open it. A negative names only the search that failed, and the next reader inherits the search's blind spot without seeing it.

---

## 2. A "Confirmation" Must Name Which Primary Source It Re-Read

> [!constraint] Re-derived reasoning from the same starting point reaches the same conclusion by construction
> If a second agent's verification did not open the artifact the claim is *about*, it has re-derived the reasoning, not tested it.
>
> A verification task reported that a filed item's proposed `--prune-stale` flag **collided with an existing unrelated `--prune-stale`** already pruning destructively into `upgrade-backups/prune-{date}/`, and routed it as *"must pick a distinct flag name."* A synthesis agent confirmed it, verified the flag's existence in the code, and escalated to *"Error-severity correction to a filed backlog item, confirmed."* The orchestrator recorded Error severity and reported it as a genuine catch. The refutation took one command — reading the item's own item-3 text, which says the flag *"gains an opt-in flag (**or a sibling `--prune-upgrade-leftovers`**)"*. The item already named the exact alternative all three parties believed they had discovered.
>
> ```
> A finding of the form "X conflicts with Y" is verified by checking X AND Y.
> When X is code and Y is a document, checking X feels like verification and is
> much easier. The document gets inherited from whoever summarized it first.
>
> For a claim that an artifact's stated plan is wrong:
> 1. Re-read the artifact's own text at the point the claim disputes. Quote it.
> 2. Check whether the artifact already anticipates the objection — proposals
>    routinely carry alternatives that a summary drops.
> 3. Verify each half of a two-sided claim separately, and say which half each
>    piece of evidence supports.
> 4. Do not let severity rise on hop count.
> ```

The quoted item text is the evidence that the disputed half was answerable in one read and that nobody performed it. A confirmation that cannot name the primary source it re-opened is a restatement, and a restatement adds a second signature to one unexamined read.

---

## 3. Severity Does Not Ratchet on Agreement

> [!constraint] If the second pass added no new evidence, its severity contribution is zero
> Severity rose *raised → confirmed → Error severity* while evidence stayed flat. Agreement was mistaken for corroboration, and three independent-looking judgements rested on a single unexamined read.

This section stays separate from §2 because it is the half a reader drops. §2's procedure reads as sufficient once written down, and a rule that only says "re-read the source" leaves severity free to rise on agreement. Count the evidence each hop added. Where the count is zero, the severity stays where the first hop left it.

---

## 4. A Status Block Reports Only Against Questions Its Author Knew to Ask

> [!constraint] A `COMPLETE` status is a claim about the task, not about the set
> Ten parallel runners each produced one Consolidated Context Part against a requirement that all 28 source items appear **exactly once** across Parts 1–8, since the downstream synthesis keys its disposition table by item ID. One runner returned `TASK_STATUS: COMPLETE` with a full, internally consistent block: correct output path, correct line count, a per-item ledger (`Item1=10, Item2=6, Item3=9, Item4=5`), and findings that later proved sound. Every self-reported field was accurate. Its Part contained **zero item identifiers** — it had over-applied an identifier-isolation rule (which governs *landable content blocks*, where an internal ID is meaningless to a consumer) to its Part's own **routing metadata**, where its task file explicitly permitted them, and referred to its items as "Item 1–4" throughout. The orchestrator's independent recount from Part headers returned **24 of 28**, naming the four missing IDs.

Nothing in the block could have disclosed this. A cross-cutting invariant that spans *all* outputs — coverage, uniqueness, no-duplicates, total-count reconciliation — is by construction invisible from inside any single runner, however careful. The section's force comes from the block being blameless: a reader who remembers it as a sloppy runner concludes better runners would not need the recount, and that conclusion is wrong.

Gate acceptance of the batch separately from acceptance of each runner. Recompute every cross-artifact invariant from the artifacts on disk after the batch returns. Treat status blocks as *leads*, never as evidence for a whole-set property. [`dispatch-batch-gate.md`](dispatch-batch-gate.md) owns the batch gate as an orchestrator stage and the cross-checks between outputs; this section is the reason a lone runner's block needs the same treatment even when there is no sibling to cross-check against.

---

## 5. The Orchestrator Is Not a Safe Place for an Unverified Negative

> [!constraint] Recompute a negative before recording it, or record it explicitly marked as unverified
> The ABSENT claim was recorded in Recovery and reported to the user before it was checked. Passing through the orchestrator conferred no verification but did confer authority: it arrived downstream as an established finding rather than a runner's claim.

Pair the rule with an explicit downstream allowance to re-read and overturn. A "suspected false ABSENT" allowance is what caught the incident in §1, and the orchestrator then re-verified by symbol search across both trees and confirmed the reversal.

§5 and §2 both say the orchestrator's agreement is not evidence, and they are separated deliberately. §2 governs a *second agent* confirming a *runner's* claim; §5 governs the *orchestrator* recording an unverified claim into Recovery, where it acquires authority for every downstream reader. The remedies differ — §2 adds a re-read step, §5 adds an unverified marker.

---

## 6. Make the Failure Output Name Its Members, and Repair by Resuming the Author

> [!practice] Two mechanics that made these repairs cheap
> ```
> Gate output:  "MISSING: 033, 046, 047, 052"   not   "24 of 28"
> Repair:       resume the same agent, metadata only — its context holds
>               the full task; a re-dispatch rebuilds it from nothing.
> ```
>
> Naming the specific missing members is what made the diagnosis immediate and the fix precise; the fix took one resume, with landable blocks untouched and the file length unchanged.

A third mechanic belongs here: **when a scoped rule exists, state its scope in the task file at the point of use**, not only in a general reference. The runner in §4 had the correct rule and applied it one level too broadly; the Expected Output skeleton did say "IDs allowed here", which is why the fix was a one-line resume rather than a rewrite. The over-application is the *cause* of §4's miss, not colour — it is what makes stating the scope at the point of use a fix rather than a platitude.

---

## 7. When a Verdict Is Downgraded, Look for the Salvageable Finding

> [!practice] An over-classified finding is usually a real observation wearing the wrong conclusion
> The false half in §2 ("rename the flag") was noise. The true half — that the existing pruner writes its own output **into** `upgrade-backups/prune-{YYYY-MM-DD}/`, inside a directory the proposal sweeps — was a real nesting hazard absent from the filed item, and it is what the execution sprint actually needed. Discarding the row would have discarded it.

---

## 8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result

> [!constraint] An exit code says the check did not pass. It does not say why
> "The instrument is broken" and "the subject is defective" print the same number. A verifier that has never reached its subject has never tested it. Fixing the verifier does not clear the gate. It lets the gate run for the first time, and the first honest run on a new subject usually fails.
>
> A session criterion read "`<checker>` exits 0 over the probe's `<sidecar>`". The first run exited 1 with `DRIFT … no archived transcript found`. The grading runner read the checker's source. The checker looked up `session_id` at a key path the sidecar never carried. It fell back to a `*.jsonl` glob. That glob now matched two files (the transcript and a `<log>.jsonl` that a new arm writes), so its "exactly one match" branch returned nothing. The transcript was on disk. The exit 1 was the instrument's.
>
> A fix runner repaired the lookup and the glob. It then found a second instrument defect behind the first: 67 of 279 transcript records carried no `version` key, and the version check had never reached them. With both repaired, the checker read the sidecar for the first time and exited 1 again: `native_event 'UserPromptSubmit' is not a declared event`. That one was real. The module's log writer defaulted a native-event field to the row's label. The next probe added a third label at three more sites.
>
> ```
> WRONG — three runs recorded as one repeated failure:
> <checker> → exit 1   # "still failing"
> <checker> → exit 1   # "still failing"
> <checker> → exit 1   # "still failing"
>
> CORRECT — each exit classified, the instrument fixes separated from the subject finding:
> exit 1: DRIFT no archived transcript   → INSTRUMENT (wrong key path + ambiguous glob); transcript present on disk
> exit 1: version check on unversioned records → INSTRUMENT (67/279 records carry no `version`); skip them
> exit 1: native_event 'UserPromptSubmit' undeclared → SUBJECT (<module> log writer default + register site); route to the module's owner
> ```

Three consequences:

- **Classify every non-zero exit by cause before acting on it.** Read the failing message. Then confirm from primary evidence whether the instrument could have seen the subject: the transcript is on disk, the key path exists, the glob matches one file. An instrument that could not have seen its subject is the empty-gate hazard with a non-zero exit code.
- **Expect the next failure after fixing the instrument, and budget for it.** Report the movement as exactly what it is: the criterion moved from unmeetable-by-instrument to unmet-by-defect. Do not soften it into "the checker works now".
- **Do not let the criterion's wording hide the distinction.** "Exits 0" collapses two questions. Write it as "the checker reads the sidecar's transcript (the step names the session id) and reports OK". An instrument failure and a subject failure then become different unmet clauses with different owners.

**Applies to** any success criterion phrased "exits 0" or "prints PASS" over a verifier the same project authored. It applies to the first run of a verifier against a new class of input (a new arm, a new record type, a second file that matches an old glob). At closeout, record whether a criterion is unmet because the instrument could not run or because the subject failed, never just "unmet".

---

## 9. A Criterion That Names an Instrument's Line Is Met Only by That Line

> [!constraint] A criterion that names an instrument's output line is a claim about that line
> The number that satisfies it must appear where the criterion says it appears. A correct number stored elsewhere, plus a paragraph in a proof document that explains the gap, satisfies the author's intent and fails the criterion. Every later reader of the instrument sees the wrong number and never sees the paragraph.
>
> A task extended a transcript inspector with a "module records" dump. Its criterion read: "the dump on the control archive finds zero marker records, proving the marker search returns empty on a negative control rather than false hits." The design searched for three things: the module's own bracket markers, the plugin name, and a phrase that the control lab shares with the module lab.
>
> On the control archive the dump printed `(3) marker records: 21`. The shared parser's strict collection, which keys on the bracket markers alone, held zero entries. The runner wrote a table in the calibration document that explained the two readings and reported the criterion as met. The orchestrator re-ran the dump, read `21` beside the words "marker records" on a negative control, and stopped.
>
> ```
> WRONG — the dump prints a false positive on the negative control, and the proof file explains why it is not one:
> (3) marker records: 21        # on an archive where no module ran
> <proof>.md: "the strict count is 0; the broad dump (21) is recorded here so the two are never conflated"
>
> CORRECT — the dump carries both readings under distinct labels, and the criterion's line reads zero:
> (3) marker records (<MARKER> only): 0
> (3b) candidate records (<NAME> or "<shared phrase>"): 21
> ```

Three consequences:

- **The instrument is the artifact of record, not the proof file.** A proof file is read once, at acceptance. An instrument's output is read on every later run. When the two disagree, the instrument wins in practice, so fix the instrument. [`verification-gate-evidence.md`](verification-gate-evidence.md) §10 states the artifact-over-instrument rule.
- **"The criterion is satisfied by a different search" is the tell.** When a runner argues the criterion holds via a structure the criterion did not name, the argument is the finding. Recompute from the instrument's own output before accepting.
- **The fix is a relabel, not a redesign.** The broad search was correct and wanted. The defect was one label carrying two meanings. Splitting it into two lines kept the design and made the criterion's line true.

**Applies to** accepting a delegated task whose criterion names a specific printed line, count or field. It applies to reading a runner's report that argues a criterion is met by a structure the criterion did not name. When you author a criterion for an instrument, name the label the reader will see, and make that label mean one thing.

---

## 10. A Quotation Deliverable Is Accepted by Finding Each Quote in Its Source

> [!constraint] "Quote verbatim" is a property of each quoted line, and acceptance tests it per line
> Heading presence, file size, a clean file-measure gate and the runner's own "all quotes match" sentence test something else. A model asked to copy fills a gap with a fluent approximation when the source is thin. Every gate that does not open the source sees the approximation as a quote.
>
> A documentation task was told to quote every pinned command's output verbatim from an earlier task's Output file. A command with no recorded output was not pinned. A missing output was written as `(not recorded in <output-file> — run it and paste the output)`. The brief's notes opened with "Copy, do not measure." The runner returned COMPLETE with a clean status block. The document had all eleven required headings. The file-measure gate passed. The index diff was exactly two lines. The orchestrator's check that every required heading was present passed.
>
> The orchestrator then read one section. A settings block showed keys that differ from the shape installed on disk. Beneath it a mismatch line read `CLI build changed: installed 2.1.273 (size …) differs from newest snapshot 2.1.272 (…)`. That line appears in no Output file. The recorded line said `installed unknown (…)` and named `2.1.273` as the newest snapshot. The runner had composed a plausible line from the message template in the brief. Two sections gave counts with no quoted source. A "Commands quoted" table listed five commands as present and omitted the four the brief also named. The true source of the quote was a file that the task's Required Context did not include.
>
> WRONG — accept on structure and on the runner's assertion:
> ```
> Grep '^## ' <target-file>          # 11 headings present
> measure_files.py <target-file>     # OK
> status block: "Every output quoted beneath each command matches its source"
> → COMPLETE
> ```
> CORRECT — for each fenced block that claims to be a quote, find the line in the recorded source:
> ```
> for each fenced block under the quoting sections:
>     take one distinctive substring (a number, a hash, a message prefix)
>     Grep the declared source Output file(s) for it
>     miss → the quote is invented, or its source is a file the brief did not allow
> ```
> One search for the message prefix `CLI build changed` across the Output directory showed the only recorded form. It exposed both the invented line and the wrong source file in under a minute.

Two operative rules:

- **The brief names a per-quote check, and the orchestrator runs it.** The criterion reads "every quote traces to a line in `<task>`'s Output". The acceptance step searches one distinctive substring per quote. Bulk quoting makes this cheap: a dozen searches, not a re-read. A miss means the quote is invented or its source was not allowed. [task-content-fidelity.md](task-content-fidelity.md) §9.A.16 covers the brief side: every quote source must sit in Required Context.
- **A "quoted" table enumerates the full pinned set, with a gap column.** The brief's list is the denominator. Each row says `recorded in <source>` or `none (gap)`. A table with fewer rows than the brief's list is itself a finding. The runner's table that listed only the commands it had quoted hid four omissions.

**Applies to** any README, runbook, report or doc task whose brief says "copy", "quote verbatim", "do not run" or "every number traces to". It applies most to the cheapest model tier, where a missing source is filled most readily. The failure is not tier-specific, because the gate is what failed. Orchestrator acceptance of a delegated quotation task reads each quote against its source. Heading presence is necessary and never sufficient.

§2 covers a second agent's confirmation, which must name the primary source it re-read. This section covers the orchestrator's acceptance of a copy deliverable.

---

## 11. A Predicate That Names Fields the Build Does Not Emit Is Graded by the Field That Carries the Same Fact

> [!constraint] A predicate's field names are a claim about the build at design time, and they expire independently of the fact they capture
> When the names miss, the fact may still be on the row under another name. "Untestable" is a claim about the evidence. It is false whenever the evidence exists under a different key.

A design predicate read: after a reload, a second `start` row carries `<field-a>: true` and `<field-b>` holding the stored handoff key, proving the module's own state survived. The build's `start` row has neither field. It has `<carrier-field>` and `<other-field>`. The grader grepped the log for the named fields and found zero matches. It marked two clauses not held. It wrote that the store round-trip was "untestable from this run's evidence" and should be recorded as "unproven".

That verdict reached the Recovery file's Key Findings, an Issues row and a coordination flag before the orchestrator read the code. The store function returns `null` when the store holds no entry for the session id. It returns a number only when it reads back an entry written earlier. The first bind logged `<carrier-field>: null` and wrote `{sid: {lastStep: 0}}`. The reload's bind logged `<carrier-field>: 0`. The only way that field becomes a number is by reading back what was written before the reload. The proof was on the row the grader had already quoted verbatim.

> [!constraint] Grade by the field the build writes for the same transition
> WRONG — grade by the design's names, conclude from their absence:
> ```
> Grep <field-a>   -> 0 matches
> Grep <field-b>   -> 0 matches
> verdict: store round-trip untestable; record as unproven
> ```
> CORRECT — grade by the field the build writes for the same transition:
> ```
> <module>.ts: restored = typeof mine?.lastStep === 'number' ? ... : null
> line 3 (first bind):  <carrier-field>: null   -> wrote {sid: {lastStep: 0}}
> line 8 (reload bind): <carrier-field>: 0      -> read back the entry written before the reload
> verdict: survival held by presence; field names <field-a>/<field-b> absent (naming drift, flagged)
> ```

Three consequences follow.

1. **On a missing field, read the writer before grading.** Open the code that emits the row. Find the field that encodes the same state transition and grade against it. Say which field stood in and why it carries the same fact.
2. **Distinguish "not held as worded" from "untestable".** The first is a naming drift between design and build. It is real and worth a flag. The second says the run cannot answer the question, and it needs a reason that survives a look at the code.
3. **Recompute a "cannot be determined" verdict from primary evidence, as you would a PASS.** A "cannot be determined" label is a verdict. It softens a held clause into an open one, which is the under-classification direction. Treat it with the same suspicion as a PASS read off a summary line.

**The recording rule.** A design document that names fields records the drift and the stand-in field in the write-up. It does not record a lost result. The orchestrator recomputes a delegated grader's "cannot be determined" verdict from the row and the code that wrote it, as it would a PASS or FAIL. §5 ("The Orchestrator Is Not a Safe Place for an Unverified Negative") covers why an unverified negative must not travel on.

**Applies to** any grading of a design predicate, probe sheet or acceptance criterion that names log fields, event keys or column names. It applies when the predicate was written before the build existed. §1 requires a symbol-level search before a negative verdict about a feature. This section covers the same search applied to the field a predicate names.

---

*Cross-reference: [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) (the dispatcher's side — link, never merge) · [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §1, §3 · [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) (name the members inline) · [`verification-gate-evidence.md`](verification-gate-evidence.md) (a gate instrument versus the artifact it measures — a different "read the artifact")*
