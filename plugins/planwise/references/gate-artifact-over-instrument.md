---
description: The artifact is authoritative and the instrument is the defect when the two disagree (§10); a gate annotation predicts the shape of correct work and never constrains it (§11); a runner's disclosure that a gate influenced the artifact is a re-derivation trigger for the orchestrator (§12); and a dispatcher pre-adjudicates a doctrine artifact's collision with a live gate at dispatch (§13).
consult-when: A correct edit and a gate's annotated value disagree, a runner says it shaped content to satisfy a gate, or an authoring task is a live gate's subject — the artifact is authoritative (§10), an annotation predicts and never constrains (§11), a disclosure is a re-derivation trigger (§12), pre-adjudicate the collision at dispatch (§13)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Artifact Over Instrument (When a Live Gate Disagrees With Correct Work)

**Purpose:** The sibling files prove an instrument before it is cited (`gate-positive-and-mutation-controls.md` §1-§4, `gate-fixture-provenance.md` §5-§9). This file governs the other direction: the instrument is already in play, and it disagrees with correct work anyway. §10 fixes which side yields. §11 binds the runner reading a gate's annotation. §12 binds the orchestrator reading a runner's report. §13 binds the dispatcher whose authoring task is a live gate's subject. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** your correct edit and a gate's annotated value disagree, a runner reports that it shaped content to satisfy a gate, or you dispatch an authoring task whose content is a live gate's subject.

## Table of Contents

- [10. The Artifact Is Authoritative; the Instrument Is the Defect](#10-the-artifact-is-authoritative-the-instrument-is-the-defect)
- [11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It](#11-a-gate-annotation-predicts-the-shape-of-correct-work--it-never-constrains-it)
- [12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger](#12-a-disclosure-that-a-gate-influenced-the-artifact-is-a-re-derivation-trigger)
- [13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch](#13-pre-adjudicate-a-doctrine-artifacts-collision-with-a-live-gate-at-dispatch)

---

## 10. The Artifact Is Authoritative; the Instrument Is the Defect

A gate's expected value is a **prediction** about what correct work will look like, written before anyone knew what the correct edit was. A runner that treats the prediction as a specification reports green over a worse artifact. [`gate-instrument-proof-obligations.md`](gate-instrument-proof-obligations.md) §10 obligation B states the claim in one sentence: *when a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail.* This section carries the resolution that sentence does not.

> [!constraint] When an instrument and the deliverable it measures disagree, the deliverable is authoritative and the instrument is the defect
> WRONG — change the deliverable so the instrument passes:
> ```
> gate returns 0 → edit the shipped prose to match the regex → gate returns 1 → report PASS
> ```
> CORRECT — fix the instrument, prove the fix in both directions, and record why:
> ```
> gate returns 0 → confirm the prose is correct per spec → fix the regex
>   → prove: OLD form returns 0 against correct prose (defect was real)
>            NEW form returns 1 against correct prose (fix works)
>   → correct the regex in EVERY copy (spec + task file), each with an inline note
> ```
> A gate exists to measure prose; prose does not exist to satisfy a gate. Bending the artifact to fit its measuring device produces a green check over a worse artifact and — because the gate now passes — removes the only signal that anything is wrong.

Two mechanical rules follow:

1. **Dry-run every gate against the exact text its own specification prescribes.** The cheapest possible fixture — the spec's own CORRECT block — is the one most often skipped.
2. **A gate lives in more than one file.** A regex in the Execution Input is often copied into the task file's Verification Commands. Fix every copy and annotate each, or the correction is itself a half-measure.

The construction vocabulary this remedy assumes — the regex dialect, the window that must fit its subject, the count whose unit must match its threshold — is [`gate-command-semantics.md`](gate-command-semantics.md) §10.9. `gate-positive-and-mutation-controls.md` §3 owns the correct-post-state arm that catches the defect before a runner meets it.

## 11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It

When your correct edit and a gate's annotated value disagree, the artifact wins: an annotation never constrains correct work. Report the true measured value with a classification of each contributing line, and flag the annotation as defective. Never reshape the artifact to fit. Never withhold a correct change to keep a number matching. This binds you as the runner reading the gate, not only the reviewer who wrote it.

> [!constraint] When your correct edit and a gate's annotated value disagree, the artifact wins
> WRONG — withhold a correct fix so a diff statistic matches its prediction:
> ```
> runner: "I deliberately left both untouched to preserve the pure-append shape your gate expects."
> → three stale counts ship, and the file's own header misdescribes it
> ```
> CORRECT — make the edit, report the number, and state the rule in the annotation itself, where the runner reads it:
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

A withheld edit leaves no trace in any diff, any gate result, or any artifact. It surfaces only when the runner reports its reasoning instead of quietly conforming.

**The review-time tell.** For every gate annotated with an expected value, ask whether the value was derived from a correct post-state or predicted before the work was scoped. A parenthetical explaining the expectation ("ToC/footer only", "headings + ToC") marks a prediction.

Two neighbouring rules own the authoring side: [`gate-anchor-outcome-set.md`](gate-anchor-outcome-set.md) §10.7 (an anchor accepts exactly the outcome set its own task can produce) and [`gate-change-vs-state-detecting.md`](gate-change-vs-state-detecting.md) §11.1 (a pre-existing omission arms a gate against correct work). This section governs the runner who meets the annotation anyway.

## 12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger

When a runner discloses that it shaped content to satisfy a gate, do not accept the gate's green. Re-derive the underlying property with a check the content cannot be shaped to. When the re-derivation shows the work correct, record the gate as the defect and the work as correct.

> [!constraint] When a runner discloses that it shaped content to satisfy a gate, do not accept the gate's green
> WRONG — accept the green the runner disclosed shaping toward:
> ```
> runner:       "sized the block to exactly 12 lines so the -A 12 window would not reach diverging content"
> orchestrator: window gate EMPTY → accept → dispatch the next task
> ```
> CORRECT — re-derive with a check the content cannot be shaped to, then record the verdict:
> ```
> orchestrator: compare the complete added-line sets of both files (no window to shape;
>               the command is gate-command-semantics.md §10.9, fixed-size window block)
>   → exit 0, identical for all 14 lines → gate under-covered (defect), work correct
> runner reworded a row so an exact-count gate returns 1
>   → read the landed line against its list's own format → matched → same verdict
> ```

Three trigger phrasings, each a **gate-defect report** rather than a wording preference. Treat each as a defect requiring adjudication, never as diligence. They are written here as literal strings so a reviewer can search a status block for them:

- *"I left X unchanged to preserve the expected gate value"*
- *"achieved by … so the gate would …"*
- *"I deviated from the spec to make the gate pass"*

`scripts/scan_runner_disclosures.py` scans a runner's status block for these three phrases.

The honest report is the signal, and the resolution is the part to check. Re-derive it against the spec rather than accepting the resolution.

**The standing asymmetry that makes disclosure load-bearing.** A gate that false-fails correct work is loud. A gate a runner silently satisfies by bending the artifact produces the exact same output as one satisfied honestly, so a sweep that re-runs the gate gets the same green. Disclosure is a property of a particular runner, not of the process, so the process cannot rely on it arriving. Where it does arrive, it is the only signal there will be.

The two gate-authoring corollaries — a fixed-size window must fit its subject, and an exact-count gate forbids legitimate mentions — are [`gate-command-semantics.md`](gate-command-semantics.md) §10.9, which also holds the window example. This section is the adjudication half.

## 13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch

A doctrine reference whose job is to forbid shell verbs must literally write `cat`, `find` and bare `cd` in its body, so a live gate that matches those verbs as bare words fires on it by construction. The gate's own remedy, *"repoint the instruction to name the native tool"*, would ship a reference that **cannot say what it forbids**, with the gate reporting clean. That is strictly worse than a failing gate, which at least announces itself.

> [!constraint] Pre-adjudicate the collision at dispatch — never leave a runner alone with rule-plus-hit
> Section numbers inside the quoted instructions are the gate rule's own.
>
> WRONG — dispatch the authoring task with the generic gate instruction only:
> ```
> "The promotion gate is live and covers your file. Run its §4 check
>  on your added lines and repoint any hit per §2 before the change lands."
> ```
> The runner writes ``- **`cat`** — reading a file's contents. Use **Read**.``, the check fires, and the runner dutifully repoints its own forbidden-verb list. Gate: clean. Reference: incoherent. Nothing downstream detects it.
>
> CORRECT — name the collision, pre-classify it, and forbid the remedy in this instance:
> ```
> "Your forbidden-verb list must literally name `cat`, `sed`, `find`, `cd`
>  in order to forbid them, and the check matches those as bare words, so it
>  WILL fire. That is a CLASSIFIED hit, not a leak — prose naming a forbidden
>  shape in order to forbid it. Do NOT repoint, soften, rename or delete the
>  list; repointing it would leave the reference unable to say what it forbids.
>  Classify each hit against the rule's §3 must-pass boundary and record the
>  classification in your report."
> ```
> The CORRECT block is the text a dispatching orchestrator copies.

Any gate strong enough to police a doctrine will fire on the doctrine that defines it: a rule quotes the pattern it forbids, a linter's fixtures contain its violations, a style guide's WRONG examples are violations, and a security check's documentation names the vulnerable call. In each case the artifact is a **legitimate carrier of the forbidden shape**, and the gate cannot tell a carrier from a violation, because the difference is intent, not syntax. Only a human or an orchestrator holding both artifacts can adjudicate it, and the adjudication must reach the runner **before** it edits.

Five application rules:

1. **At dispatch planning, cross-check every authoring task against every live path-scoped gate covering its output path.** Where the task's *content* is the gate's *subject*, the collision is guaranteed. Flag it before spawning, not after.
2. **Pre-adjudicate rather than delegating the judgment.** A runner holding a binding rule and a matching hit will apply the rule. That is correct behaviour, and it is the reason the instruction must arrive first.
3. **Require the classification in the report, not just the count.** "9 hits, all classified as doctrine text naming a forbidden verb in order to forbid it, zero repointed" is auditable. "Gate clean" is not, and here would be a lie by omission.
4. **Check the gate still discriminates in the other direction on the same artifact.** The reference's own legitimate pipeline exemplar not firing is what proves the gate was classified rather than disabled.
5. **Carry the classification downstream.** A later sweep re-running the check over the same tree sees the same hits. Without a propagated flag it reports a regression that does not exist.

This section is its own first test case. It quotes gate-shaped text, shell verbs and forbidden phrasings in order to forbid them, so any gate covering this file fires on it by construction. It shipped as a pre-classified hit with zero repoints, under rule 2.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10 obligation B, the one-sentence form of §10 here) · [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.7 and [gate-command-semantics.md](gate-command-semantics.md) §10.9 (the authoring side these adjudication rules assume) · [gate-change-vs-state-detecting.md](gate-change-vs-state-detecting.md) §11.1 (a pre-existing omission arms a gate against correct work) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §12 (decide and assert on one measurement) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
