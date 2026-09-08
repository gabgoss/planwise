---
description: A verdict rests on the primary source it re-read, not on who agrees with it. Covers the symbol-level search a negative verdict requires, what a "confirmation" must name, why severity does not ratchet on agreement, why a runner's accurate status block cannot see a cross-artifact invariant, why the orchestrator is not a safe place for an unverified negative, and how to make a failure name its members. Consult before recording ABSENT, before confirming another agent's finding, before accepting a batch of status blocks, and before writing a negative into Recovery.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Verdict's Source — A Verdict Is Only as Good as the Source It Re-Read

**Purpose:** Three verdicts in two sessions were confident, internally consistent, and wrong — each because the evidence it rested on **could not have contained the answer**. One searched prose for a feature that lives in code and returned ABSENT. One "confirmed" a claim about a document without re-opening the document. One reported an accurate status block against a question its runner was never asked.

**Read this when** you are about to record ABSENT, confirm another agent's finding, accept a batch of runner status blocks as evidence for a whole-set property, or write a negative into Recovery.

The three fail in different directions, which is why they belong in one rule. The known failure direction for delegated classification is **under-**classification — a runner calling something FIXED that is still live — and that is what closeout checklists train attention on. A false ABSENT (over-reporting a gap) and an over-classified severity (over-reporting a defect) both produce *extra* work rather than missing work, so nothing downstream fails loudly. They surface only if someone recomputes the claim against the primary source, including the claims that arrived pre-confirmed.

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

*Cross-reference: [`dispatch-brief-neutrality.md`](dispatch-brief-neutrality.md) (the dispatcher's side — link, never merge) · [`dispatch-batch-gate.md`](dispatch-batch-gate.md) §1, §3 · [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) (name the members inline) · [`verification-gate-evidence.md`](verification-gate-evidence.md) (a gate instrument versus the artifact it measures — a different "read the artifact")*
