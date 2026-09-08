---
description: Anchoring a check to the artifact rather than to the text that describes it — why an anchor derived from a criterion inherits the criterion's false premises, re-deriving the section citations that lifted text carries, naming the artifact and field a cross-plan status gate reads, and counting a set whose members are already on disk. Consult before writing a gate anchor, a landing-zone reference, a lifted citation, or a projected set size.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Anchor Against the Artifact (Not Against Its Description)

**Purpose:** Conformance to a specification and correspondence to the world are different properties, and only one of them is what a gate is usually wanted for. A hand-maintained status cell, a criterion's restatement, a source document's numbering and a scaffold-time projection are all **descriptions**. Each can be checked perfectly while the artifact says something else.

**Read this when** you are about to write a check, criterion, citation or figure whose subject lives in another artifact — and in three of the four failures below, that artifact was sitting on disk, one command away, the entire time.

**Numbering.** This file carries its own §1–§4. It does not extend the shared `§3x` / `§9.B` series that [`verify-against-shipped-artifact.md`](verify-against-shipped-artifact.md) and [`verify-before-cite.md`](verify-before-cite.md) split between them. Those two govern the **identifier** being cited — a third-party symbol there, an internal project artifact here. This file governs the **anchor**: the thing a check points at to decide PASS or FAIL.

## Table of Contents

- [1. An Anchor Is Measured Against the Artifact, Never Derived From the Criterion It Verifies](#1-an-anchor-is-measured-against-the-artifact-never-derived-from-the-criterion-it-verifies)
- [2. Re-Derive Every Section Citation in Lifted Text Before Accepting the Lift](#2-re-derive-every-section-citation-in-lifted-text-before-accepting-the-lift)
- [3. A Status Gate Names the Artifact and the Specific Table or Field It Reads](#3-a-status-gate-names-the-artifact-and-the-specific-table-or-field-it-reads)
- [4. A Set Selected by a Greppable Key Over an Existing Artifact Has a COUNT, Not an Estimate](#4-a-set-selected-by-a-greppable-key-over-an-existing-artifact-has-a-count-not-an-estimate)

---

## 1. An Anchor Is Measured Against the Artifact, Never Derived From the Criterion It Verifies

> [!constraint] Conformance is not correspondence
> **An anchor derived from a spec tests conformance to the spec. It cannot test whether the spec was true of the world.** Only a measurement against the artifact does that.

Three independent-looking artifacts — a task file's execution step, a sprint exit criterion, and the mechanical Signoff anchor that would verify it — all named a "Reviewer Checklists" zone in a handler that has no such heading and never did. A tree-wide search finds exactly one hit, in a different file. The anchor was written by reading the criterion and restating it as a search, so the two then **corroborated each other**.

Four rules follow.

- **Before briefing work into a named landing zone, verify the zone exists.** One heading search against the live artifact, at authoring time. This is cheaper than every downstream consequence of getting it wrong.
- **Write anchors from a live read. Where that is impossible, mark the anchor unverified** so a runner knows to re-derive rather than trust. An anchor whose author never opened the target file tests only internal consistency.
- **Two artifacts agreeing is not corroboration when one was copied from the other.** Ask what each was derived *from*. Independent confirmation requires independent derivation, ideally with one of the two taken from the artifact itself.
- **"Present and greppable" is not "operative."** When a rule must be *executed* by something, verify it landed on the surface that executes it.

### The near-miss that makes rule 4 load-bearing

A sibling reference file *does* carry a matching `## Reviewer Checklists` heading with a `### Task Reviewer` subsection, and a runner under retry pressure could reasonably have landed there and satisfied a reworded anchor. It would have been wrong. That file's own header says *"The following is a summary for the lead's reference during synthesis"*, while the handler instructs the reviewing agent to execute its checklist **from its own protocol**. A check landed only in the synthesis summary sits where no reviewer ever executes it: present, greppable, gate-passing, and inert.

**The authoring tell: precision about the wrong thing reads as diligence.** The brief that named the nonexistent zone had just demonstrated rigour by measuring a *different* wrong locate and warning the runner off it. Being sharpened at review time is not evidence an anchor was measured.

---

## 2. Re-Derive Every Section Citation in Lifted Text Before Accepting the Lift

> [!constraint] A lifted `§N` stays syntactically valid while its meaning drifts
> ```
> WRONG — lift the fix-shape verbatim because the lift boundary was respected:
>   read source `## Fix shape` → paste into target → run identifier gates → empty → accept
>
> CORRECT — enumerate the citations the lift carried, and resolve each against the live target:
>   git diff <target> | grep '^+' | grep -oE '§1?[0-9]+(\.[0-9]+)*' | sort -u
>   → for EACH: grep -n '^#\+ <that number> ' <target>   # must resolve, AND mean what the text claims
>   → report the full citation list and its resolutions
> ```
> Both commands are required. The enumeration alone proves nothing about meaning, and a per-citation check alone never learns which citations exist.

Rule bodies lifted verbatim from five upstream documents carried `§1.18`–`§1.22` and `§11.2`. Every one of the first five **is a live heading in the target file today**, denoting entirely different rules than the source authors meant.

**A wrong-but-live citation is worse than a dead one**, for four reasons that compound:

- No link-checker flags it — the target exists.
- No search flags it — the syntax is valid.
- The reader is not confused — they arrive somewhere plausible and read a real rule.
- It survives review — reviewing a citation means checking that it resolves, and it does.

**Silent, durable and actively misleading is the worst combination available.** A file appended to over time makes this *more* likely, not less: age converts dead links into wrong-but-live ones.

**The gate that guards the lift does not guard what the lift says.** Lift discipline is normally framed as a *boundary* problem — lift only from the sanctioned span, never from sections carrying bookkeeping identifiers. That framing catches identifier leaks and has nothing to say about the *content* inside the sanctioned span, which is exactly where the stale numbers live.

Three obligations:

- **Treat a source document's section numbers exactly as line numbers are already treated — a cost hint, never an anchor.** The line-number rule is [`measurement-discipline.md`](measurement-discipline.md) §8.1 and [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.1. Section numbers earn the same treatment for the same reason.
- **Require the enumerated list in the report.** "Citations checked" is unauditable. A list of seven citations with seven resolved headings is not.
- **A lift-based task frequently needs to cite section numbers it created itself**, which by definition cannot come from the source document — a further reason the source's numbering cannot serve as an anchor.

**The significant half of a clean enumeration is what is absent.** None of the six source-proposed numbers survived here, and that absence is informative only because someone enumerated what should have been there and checked it was not. An unenumerated "looks fine" would read identically while shipping five wrong-but-live citations.

---

## 3. A Status Gate Names the Artifact and the Specific Table or Field It Reads

> [!constraint] A gate asking "is X complete?" that names no artifact is a coin flip
> One plan of record answered that question three ways in one file:
>
> | Surface | Answer |
> |---|---|
> | Status line | *"✅ COMPLETE — all six sprints signed off PASS; release battery 8/8"* |
> | Sprint Overview table | all six ✅ COMPLETE, with per-sprint PASS counts |
> | **Session Completion Tracking table** | **five of ten sessions ⏳ NOT STARTED** |
>
> All five of those sessions had demonstrably shipped, their commits reachable from HEAD. A gate with `STOP` attached could return a false FAIL against a prerequisite genuinely met, decided by which of three tables the orchestrator happened to open.

A plan of record accumulates representations of the same fact because each serves a different reader — a headline for humans, a per-sprint roll-up for scheduling, a per-session table for tracking. They are written at different moments by different steps, and **the hand-maintained, most granular one lags hardest**, because it is updated last, at closeout, when the work already feels finished.

### The asymmetry that makes this dangerous rather than untidy

Machine-checkable evidence — a manifest version, a commit reachable from HEAD, a file that does or does not exist — cannot drift from the thing it describes. A hand-maintained status cell can, and it drifts **stale-negative** far more often than stale-positive, because the update marking completion is the one most likely to be skipped. **A gate preferring the hand-maintained source therefore fails in the halting direction**: it blocks work against a prerequisite that was genuinely met.

Five rules follow.

1. **Name the source in the gate text** — and name the ones that are *not* authoritative, when you know they disagree.
2. **Prefer machine-checkable evidence** over any hand-maintained status cell. Where a narrative status line and a table disagree, reach for the third kind of evidence, because both of those are hand-maintained.
3. **Record inter-artifact disagreement as a gate finding, never silently resolve it.** The observation is real information about the upstream plan, and it is the only thing that will ever get the stale table fixed.
4. **Do not repair another plan's artifact from inside a gated session.** Route it project-side. The gate's job is to read correctly, not to correct its input.
5. On the producing side, symmetrically: **fill the tracking row at closeout.** To a downstream mechanical gate, "pending" and "failed" are the same string.

**The worked resolution:** name the authority, declare the tracking table non-authoritative with its five stale rows enumerated, and add a gate row recording the contradiction as observed-and-overridden. That is what let the session run the next day and log *"contradiction confirmed, exactly the 5 predicted rows … Recorded, not resolved"* without stalling.

This section keeps its producing-side clause inside a rule otherwise addressed to consumers, deliberately. The two halves of the failure are only legible together, and the mirror-image case is real: an unfilled Signoff once halted a plan's final session against a sprint that had passed 8/8.

---

## 4. A Set Selected by a Greppable Key Over an Existing Artifact Has a COUNT, Not an Estimate

> [!constraint] Record the number with the command that produced it
> ```markdown
> WRONG:   | ~610 pulled | ~9.5K | The claims to design (largest probe family, ~45 claims expected) |
> CORRECT: | 85 claims   | ~18K  | `Grep pattern='\*\*Modality:\*\* headless' output_mode='count'` over
>                                   Parts 1a–1d of the register = 85 (34/6/14/31), measured 2026-08-19 |
> ```
> Where the artifact does not exist at scaffold time the figure is legitimately a projection — and then the divergence-action requirement binds instead, per [`dispatch-preflight-claim-expiry.md`](dispatch-preflight-claim-expiry.md) §6.

The WRONG row is kept whole rather than reduced to the offending phrase. Its other cells — a plausible pull count and a plausible token figure — are what made the estimate survive review.

Two of three sibling projections were accurate, which is what makes this a counting rule rather than a sloppiness complaint:

| Task | Projected | Actual | Error |
|---|---|---|---|
| static | (implicit, consistent) | 26 | accurate |
| **headless** | **"~45 claims expected"** | **85** | **~1.9×** |
| matrix | "~30 expected" | 34 | accurate |

The register was already on disk and frozen when all three tasks were scaffolded. A 1.9× error from one uncounted partition is exactly the kind of error an estimate produces and a count cannot.

### Corollary 1 — a count feeds more budgets than the token estimate

Trace every figure derived from it — output-file count, per-file size gates, rep counts, cost forecasts — and check whether each actually **binds**. Re-rolling only the token number leaves the others silently wrong. Assuming any of them binds is its own error.

### Corollary 2 — when checking whether a derived budget binds, measure the budget, not a proxy

One orchestrator reached for `lines per design`, compared it against a sibling task, and inferred a fidelity squeeze that was not real — because 24.6% of the sibling's lines were full-factorial cell tables its modality mandates and this one's does not. The direct measurements refuted it:

| | The task under suspicion | The sibling it was compared to |
|---|---|---|
| Lines used | 1,094 of 1,500 — **406 spare** | 761 |
| Lines per design | 12.9 | 20.0 raw / **16.9 excluding cell tables** |
| Bytes per design | ~2,320 | ~2,600 |
| Field completeness | **602 = 7 × 86 entries**, zero missing | — |

Lines used against the gate, and field completeness against the schema, answer *"is fidelity being traded away?"* in one measurement each, and answer it correctly. **A cross-partition density comparison answers a different question and reads like an answer to this one.**

---

*Cross-references: [verify-before-cite.md](verify-before-cite.md) §9.B (verifying the internal artifact a brief cites), [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §2 (verifying a third-party identifier before pinning it), [verification-task-authoring.md](verification-task-authoring.md) §2 (per-unit existence assertions over aggregate count thresholds — the gate-construction counterpart to §1), [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.4 (sweeping every restatement of a refreshed count in the same document), [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4 (reconciling an inherited flag, receiver side).*
