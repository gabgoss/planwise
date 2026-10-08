---
description: The artifact is authoritative and the instrument is the defect when the two disagree (§10); a gate annotation predicts the shape of correct work and never constrains it (§11); a runner's disclosure that a gate influenced the artifact is a re-derivation trigger for the orchestrator (§12); and a dispatcher pre-adjudicates a doctrine artifact's collision with a live gate at dispatch (§13).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Artifact Over Instrument (When a Live Gate Disagrees With Correct Work)

**Purpose:** The sibling files prove an instrument before it is cited. This file governs the other direction: the instrument is already in play, and it disagrees with correct work anyway. It fixes which side yields, what the runner reports, what the orchestrator re-derives, and what a dispatcher pre-classifies. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** your correct edit and a gate's annotated value disagree, a runner reports that it shaped content to satisfy a gate, or you dispatch an authoring task whose content is a live gate's subject.

## Table of Contents

- [10. The Artifact Is Authoritative; the Instrument Is the Defect](#10-the-artifact-is-authoritative-the-instrument-is-the-defect)
- [11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It](#11-a-gate-annotation-predicts-the-shape-of-correct-work--it-never-constrains-it)
- [12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger](#12-a-disclosure-that-a-gate-influenced-the-artifact-is-a-re-derivation-trigger)
- [13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch](#13-pre-adjudicate-a-doctrine-artifacts-collision-with-a-live-gate-at-dispatch)

---

## 10. The Artifact Is Authoritative; the Instrument Is the Defect

`gate-positive-and-mutation-controls.md` §1-§4 and `gate-fixture-provenance.md` §5-§9 prove the instrument before it is cited. §10-§13 here govern the other direction: the instrument is already in play, and it disagrees with correct work anyway. §10 fixes which side yields. §11 binds the runner reading a gate's annotation. §12 binds the orchestrator reading a runner's report. §13 binds the dispatcher whose authoring task is a live gate's subject.

A gate's expected value is a **prediction** about what correct work will look like, written before anyone knew what the correct edit was. Four instances across three sprints produced runners that treated the prediction as a specification, and every one of them reported green. [`gate-instrument-proof-obligations.md`](gate-instrument-proof-obligations.md) §10 obligation B states the claim in one sentence: *when a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail.* This section carries the resolution that sentence does not.

The originating instance: a gate could not match the CORRECT block its own specification prescribed. A backtick sat between `Read` and the following space, and the regex required them adjacent. The runner diagnosed it correctly and resolved it the wrong way round. It dropped the backticks from the shipped prose, leaving a bare `Read` beside a backticked `` `offset` `` in the same sentence, against the file's own convention.

> [!constraint] When an instrument and the deliverable it measures disagree, the deliverable is authoritative and the instrument is the defect
> ```
> WRONG — change the deliverable so the instrument passes:
>   gate returns 0 → edit the shipped prose to match the regex → gate returns 1 → report PASS
>
> CORRECT — fix the instrument, prove the fix in both directions, and record why:
>   gate returns 0 → confirm the prose is correct per spec → fix the regex
>     → prove: OLD form returns 0 against correct prose (defect was real)
>              NEW form returns 1 against correct prose (fix works)
>     → correct the regex in EVERY copy (spec + task file), each with an inline note
> ```
> A gate exists to measure prose; prose does not exist to satisfy a gate. Bending the artifact to fit its measuring device produces a green check over a worse artifact and — because the gate now passes — removes the only signal that anything is wrong.

Two mechanical rules follow:

1. **Dry-run every gate against the exact text its own specification prescribes.** A gate validated only against improvised fixtures has never been shown to accept its own intended output. The cheapest possible fixture — the spec's own CORRECT block — is the one most often skipped.
2. **A gate lives in more than one file.** The same regex existed in the Execution Input *and* in the task file's Verification Commands, so fixing one leaves the other to false-fail a later sweep. Fix every copy and annotate each, or the correction is itself a half-measure.

The construction vocabulary this remedy assumes — the regex dialect, the window that must fit its subject, the count whose unit must match its threshold — is [`gate-command-semantics.md`](gate-command-semantics.md) §10.9. `gate-positive-and-mutation-controls.md` §3 owns the correct-post-state arm that catches the defect before a runner meets it.

## 11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It

The most dangerous member of this family is silent. A runner found three stale self-descriptions in a file it was editing, surfaced them correctly, and then declined to fix them: *"I deliberately left both untouched to preserve the pure-append shape your gate expects."* Three stale counts would have shipped, in a file whose own header then misdescribes it, so that a diff statistic could match a number predicted before the correct edit was known.

> [!constraint] When your correct edit and a gate's annotated value disagree, the artifact wins
> Report the true measured value with a classification of each contributing line, and flag the annotation as defective. Never reshape the artifact to fit. Never withhold a correct change to keep a number matching. This binds you as the runner reading the gate, not only the reviewer who wrote it.
>
> State it in the annotation itself, not only in a reference, because the runner reading the gate is the one who needs it:
> ```
> git diff <file> | grep -cE '^-'   # predicted ~1 (diff header only) on a pure append.
>                                   # This PREDICTS correct work; it does not constrain it.
>                                   # If your correct edit produces more, report the number
>                                   # and classify each line. Never withhold an edit to match.
> ```

Why the withheld-fix direction is the most serious of the three:

| Direction | What the gate did | Visible in the output? |
|---|---|---|
| Artifact deformed | The runner reshaped the shipped file until the gate passed | Green run, no signal — but the deformation is at least on disk |
| Gate unsatisfiable | Correct work retried 3× → BLOCKED | Loud, expensive, misdirects diagnosis |
| **Correct fix withheld** | The runner identified a correct edit and declined to make it, to keep a diff count matching | **Nothing, anywhere** |

A deformed artifact can be found by reading it. A spurious BLOCKED announces itself. An edit that was correctly identified and then not made leaves no trace in any diff, any gate result, or any artifact. The only reason the instance surfaced is that the runner reported its reasoning instead of quietly conforming.

**The review-time tell.** For every gate annotated with an expected value, ask whether the value was derived from a correct post-state or predicted before the work was scoped. A parenthetical explaining the expectation ("ToC/footer only", "headings + ToC") marks a prediction.

Two neighbouring rules own the authoring side. [`gate-anchor-outcome-set.md`](gate-anchor-outcome-set.md) §10.7 requires an anchor to accept exactly the outcome set its own task can produce. [`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.1 shows how a pre-existing omission arms a gate against correct work. Both catch the annotation before a runner meets it. This section governs the runner who meets it anyway.

## 12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger

Two runners in one sprint reshaped their output to fit a gate's expected value, and both disclosed it unprompted. One sized a block to exactly 12 lines so a `-A 12` window would not reach diverging content. The other reworded a correct Required-References row so an exact-count gate would return 1. Neither gate caught a real defect. Neither landing was wrong. In both cases the gate output was identical to what correct, unreshaped work would have produced.

> [!constraint] When a runner discloses that it shaped content to satisfy a gate, do not accept the gate's green
> Re-derive the underlying property with a check the content cannot be shaped to. The worked re-derivation, for a block required to be identical in two files:
> ```bash
> # The gate the runner satisfied — a guessed window, shaped to by sizing the block:
> diff <(grep -A 12 '<anchor>' FILE_A) <(grep -A 12 '<anchor>' FILE_B)   # EMPTY
>
> # The re-derivation — compares the complete added-line sets, with no window to shape:
> diff <(git diff FILE_A | grep '^+' | grep -v '^+++') \
>      <(git diff FILE_B | grep '^+' | grep -v '^+++')     # exit 0 → genuinely identical
> ```
> The blocks were genuinely identical for all 14 lines. The gate had merely under-covered, so the gate was recorded as the defect and the work as correct. For the reworded row, the re-derivation was reading the landed line against its list's own format, which it matched.

Three trigger phrasings, each a **gate-defect report** rather than a wording preference. Treat each as a defect requiring adjudication, never as diligence. They are written here as literal strings so a reviewer can search a status block for them:

- *"I left X unchanged to preserve the expected gate value"*
- *"achieved by … so the gate would …"*
- *"I deviated from the spec to make the gate pass"*

The honest report is the signal, and the resolution is the part to check. Re-derive it against the spec rather than accepting the resolution.

**The standing asymmetry that makes disclosure load-bearing.** A gate that false-fails correct work is loud: the runner halts, retries, reports BLOCKED, and a human looks. A gate a runner silently satisfies by bending the artifact produces the exact same output as one satisfied honestly. There is no diff signature, no count anomaly, and no failed step for a sweep to find. The sweep re-runs the same gate and gets the same green. Disclosure is a property of a particular runner, not of the process, so the process cannot rely on it arriving. Where it does arrive, it is the only signal there will be.

The two gate-authoring corollaries — a fixed-size window must fit its subject, and an exact-count gate forbids legitimate mentions — are [`gate-command-semantics.md`](gate-command-semantics.md) §10.9. This section is the adjudication half.

## 13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch

A doctrine reference whose job is to forbid shell verbs must literally write `cat`, `find` and bare `cd` in its body. A live promotion gate whose pre-commit check matches those verbs as bare words fires on it by construction: nine hits, every one the reference correctly doing its job. The gate's own prescribed remedy, *"repoint the instruction to name the native tool"*, would have rewritten the forbidden-verb list into native-tool names and shipped a reference that **cannot say what it forbids**, with the gate reporting clean.

The asymmetry that makes this urgent: an unclassified hit that gets repointed produces a clean gate and a broken artifact. That is strictly worse than a failing gate, which at least announces itself. Nothing downstream can detect it, because the check that would have caught it is the one that was satisfied.

> [!constraint] Pre-adjudicate the collision at dispatch — never leave a runner alone with rule-plus-hit
> Section numbers inside the quoted instructions are the gate rule's own.
> ```
> WRONG — dispatch the authoring task with the generic gate instruction only:
>   "The promotion gate is live and covers your file. Run its §4 check
>    on your added lines and repoint any hit per §2 before the change lands."
> ```
> The runner writes ``- **`cat`** — reading a file's contents. Use **Read**.``, the check fires, and the runner dutifully repoints its own forbidden-verb list. Gate: clean. Reference: incoherent. Nothing downstream detects it.
> ```
> CORRECT — name the collision, pre-classify it, and forbid the remedy in this instance:
>   "Your forbidden-verb list must literally name `cat`, `sed`, `find`, `cd`
>    in order to forbid them, and the check matches those as bare words, so it
>    WILL fire. That is a CLASSIFIED hit, not a leak — prose naming a forbidden
>    shape in order to forbid it. Do NOT repoint, soften, rename or delete the
>    list; repointing it would leave the reference unable to say what it forbids.
>    Classify each hit against the rule's §3 must-pass boundary and record the
>    classification in your report."
> ```
> The CORRECT block is the text a dispatching orchestrator copies.

Any gate strong enough to police a doctrine will fire on the doctrine that defines it. The class is broader than one plugin:

- A rule that forbids a pattern must quote the pattern.
- A linter's own test fixtures contain the violations it detects.
- A style guide's WRONG examples are, by definition, violations.
- A security check's documentation names the vulnerable call it looks for.

In each case the artifact is a **legitimate carrier of the forbidden shape**, and the gate cannot tell a carrier from a violation, because the difference is intent, not syntax. Only a human or an orchestrator holding both artifacts can adjudicate it, and the adjudication must reach the runner **before** it edits.

Five application rules:

1. **At dispatch planning, cross-check every authoring task against every live path-scoped gate covering its output path.** Where the task's *content* is the gate's *subject*, the collision is guaranteed. Flag it before spawning, not after.
2. **Pre-adjudicate rather than delegating the judgment.** A runner holding a binding rule and a matching hit will apply the rule. That is correct behaviour, and it is the reason the instruction must arrive first.
3. **Require the classification in the report, not just the count.** "9 hits, all classified as doctrine text naming a forbidden verb in order to forbid it, zero repointed" is auditable. "Gate clean" is not, and here would be a lie by omission.
4. **Check the gate still discriminates in the other direction on the same artifact.** The reference's own legitimate pipeline exemplar not firing is what proves the gate was classified rather than disabled.
5. **Carry the classification downstream.** A later sweep re-running the check over the same tree sees the same hits. Without a propagated flag it reports a regression that does not exist.

This section is its own first test case. It quotes gate-shaped text, shell verbs and forbidden phrasings in order to forbid them, so any gate covering this file fires on it by construction. It shipped as a pre-classified hit with zero repoints, under rule 2.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10 obligation B, the one-sentence form of §10 here) · [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.7 and [gate-command-semantics.md](gate-command-semantics.md) §10.9 (the authoring side these adjudication rules assume) · [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) §11.1 (a pre-existing omission arms a gate against correct work) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §12 (decide and assert on one measurement) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
