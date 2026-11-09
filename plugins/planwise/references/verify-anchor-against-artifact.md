---
description: Anchoring a check to the artifact rather than to the text that describes it — why an anchor derived from a criterion inherits the criterion's false premises, re-deriving the section citations that lifted text carries, naming the artifact and field a cross-plan status gate reads, counting a set whose members are already on disk, and keeping a marked fallback for every version in the committed snapshot set when an extractor's anchor is replaced. Consult before writing a gate anchor, a landing-zone reference, a lifted citation, a projected set size, or a re-anchor commit.
consult-when: Writing a gate anchor, landing zone, lifted `§N` citation, cross-plan status assertion, or projected set size — measure it against the artifact, never restate the description, and keep a marked fallback for every committed snapshot version when an extractor's anchor is replaced
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Anchor Against the Artifact (Not Against Its Description)

**Purpose:** Conformance to a specification and correspondence to the world are different properties, and only one of them is what a gate is usually wanted for. A hand-maintained status cell, a criterion's restatement, a source document's numbering and a scaffold-time projection are all **descriptions**. Each can be checked perfectly while the artifact says something else.

**Read this when** you are about to write a check, criterion, citation or figure whose subject lives in another artifact — and in three of the four failures below, that artifact was sitting on disk, one command away, the entire time.

**Numbering.** This file carries its own §1–§5. It does not extend the shared `§3x` / `§9.B` series that [`verify-against-shipped-artifact.md`](verify-against-shipped-artifact.md) and [`verify-before-cite.md`](verify-before-cite.md) split between them. Those two govern the **identifier** being cited — a third-party symbol there, an internal project artifact here. This file governs the **anchor**: the thing a check points at to decide PASS or FAIL.

## Table of Contents

- [1. An Anchor Is Measured Against the Artifact, Never Derived From the Criterion It Verifies](#1-an-anchor-is-measured-against-the-artifact-never-derived-from-the-criterion-it-verifies)
- [2. Re-Derive Every Section Citation in Lifted Text Before Accepting the Lift](#2-re-derive-every-section-citation-in-lifted-text-before-accepting-the-lift)
- [3. A Status Gate Names the Artifact and the Specific Table or Field It Reads](#3-a-status-gate-names-the-artifact-and-the-specific-table-or-field-it-reads)
- [4. A Set Selected by a Greppable Key Over an Existing Artifact Has a COUNT, Not an Estimate](#4-a-set-selected-by-a-greppable-key-over-an-existing-artifact-has-a-count-not-an-estimate)
- [5. A Re-Anchor Keeps a Fallback for Every Version the Snapshot Set Covers](#5-a-re-anchor-keeps-a-fallback-for-every-version-the-snapshot-set-covers)

---

## 1. An Anchor Is Measured Against the Artifact, Never Derived From the Criterion It Verifies

> [!constraint] Conformance is not correspondence
> **An anchor derived from a spec tests conformance to the spec. It cannot test whether the spec was true of the world.** Only a measurement against the artifact does that.
>
> WRONG — write the anchor by reading the criterion and restating it as a search. A task file's execution step, a sprint exit criterion and the Signoff anchor all named a "Reviewer Checklists" zone in a handler that has no such heading and never did, and the copies **corroborated each other**.
>
> CORRECT — run one heading search against the live handler at authoring time. A tree-wide search finds exactly one hit, in a different file, so no brief rests on that zone.

**A target's structure is proven in the named file before a brief rests on it.** Four rules follow.

- **Before briefing work into a named landing zone, verify the zone exists.** One heading search against the live artifact, at authoring time. `scripts/check_section_citations.py` zone mode (`--brief <file> --zone <target>`) prints `DEAD-ZONE` at a count of 0. Its extraction is heuristic, so a zone it misses still needs the search.
- **Write anchors from a live read. Where that is impossible, mark the anchor unverified** so a runner knows to re-derive rather than trust. Check 30 of `scripts/lint_verification_gates.py` warns on a heading-search anchor with neither a date nor that word.
- **Two artifacts agreeing is not corroboration when one was copied from the other.** Independent confirmation requires independent derivation, ideally with one of the two taken from the artifact itself.
- **"Present and greppable" is not "operative."** When a rule must be *executed* by something, verify it landed on the surface that executes it.

### The near-miss that makes rule 4 load-bearing

A sibling reference file *does* carry a matching `## Reviewer Checklists` heading with a `### Task Reviewer` subsection. That file's own header says *"The following is a summary for the lead's reference during synthesis"*, while the handler instructs the reviewing agent to execute its checklist **from its own protocol**.

> [!constraint] A check lands on the surface that executes it
> WRONG — under retry pressure, land the check in the sibling's synthesis summary and satisfy a reworded anchor. It sits where no reviewer ever executes it: present, greppable, gate-passing, and inert.
>
> CORRECT — land the check in the reviewing agent's own protocol, the surface the handler tells it to execute.

**The authoring tell: precision about the wrong thing reads as diligence.** Being sharpened at review time is not evidence an anchor was measured.

---

## 2. Re-Derive Every Section Citation in Lifted Text Before Accepting the Lift

> [!constraint] A lifted `§N` stays syntactically valid while its meaning drifts
> **Re-derive every section citation in lifted text before accepting the lift.** `scripts/check_section_citations.py` enumerates the citations and resolves each against the file it names. A lift check uses its default scan: `--root <plugin root>` with no mode flag, plus `--extra-root <path>` for a target outside the plugin.
>
> WRONG — lift the fix-shape verbatim because the lift boundary was respected: read the source `## Fix shape`, paste it into the target, run the identifier gates, see an empty result, and accept.
>
> CORRECT — run the checker after the paste, confirm each row for the lifted lines resolves AND means what the text claims, and report the full citation list and its resolutions.
>
> An `ok` row proves only that the section exists. The enumeration alone proves nothing about meaning, and a per-citation check alone never learns which citations exist.

Rule bodies lifted verbatim from five upstream documents carried `§1.18`–`§1.22` and `§11.2`. Every one of the first five **is a live heading in the target file today**, denoting entirely different rules than the source authors meant.

**A wrong-but-live citation is worse than a dead one.** No link-checker or search flags it, the reader arrives somewhere plausible, and it survives review because it resolves. Age converts dead links into wrong-but-live ones.

**The gate that guards the lift does not guard what the lift says.** A *boundary* framing catches identifier leaks and has nothing to say about the *content* inside the sanctioned span, which is exactly where the stale numbers live.

Three obligations:

- **Treat a source document's section numbers exactly as line numbers are already treated — a cost hint, never an anchor.** The line-number rule is [`measurement-discipline.md`](measurement-discipline.md) §8.1 and [`scaffolding-hygiene.md`](scaffolding-hygiene.md) §12.1.
- **Require the enumerated list in the report.** "Citations checked" is unauditable.
- **A lift-based task frequently needs to cite section numbers it created itself**, which by definition cannot come from the source document.

**The significant half of a clean enumeration is what is absent.** An unenumerated "looks fine" would read identically while shipping five wrong-but-live citations.

---

## 3. A Status Gate Names the Artifact and the Specific Table or Field It Reads

> [!constraint] A gate asking "is X complete?" that names no artifact is a coin flip
> One plan of record answered that question three ways in one file. Its status line and its Sprint Overview table said COMPLETE, and its Session Completion Tracking table showed five of ten sessions ⏳ NOT STARTED. All five of those sessions had demonstrably shipped, their commits reachable from HEAD.
>
> WRONG — attach `STOP` to "is X complete?" and name no artifact. The gate could return a false FAIL against a prerequisite genuinely met, decided by which of three tables the orchestrator happened to open.
>
> CORRECT — name the authority, declare the tracking table non-authoritative with its five stale rows enumerated, and add a gate row recording the contradiction as observed-and-overridden.

Of the representations a plan of record accumulates, **the hand-maintained, most granular one lags hardest**, because it is updated last, at closeout. Check 31 of `scripts/lint_verification_gates.py` warns on a status gate that names no file and no table or field. It is a heuristic and never gates alone.

### The asymmetry that makes this dangerous rather than untidy

Machine-checkable evidence — a manifest version, a commit reachable from HEAD, a file that does or does not exist — cannot drift from the thing it describes. A hand-maintained status cell can, and it drifts **stale-negative** far more often than stale-positive, because the update marking completion is the one most likely to be skipped.

> [!constraint] A gate preferring the hand-maintained source fails in the halting direction
> WRONG — read the tracking table, find a stale pending row, and block work against a prerequisite that was genuinely met.
>
> CORRECT — read a commit reachable from HEAD, and record the stale row as a gate finding.

Five rules follow.

1. **Name the source in the gate text** — and name the ones that are *not* authoritative, when you know they disagree.
2. **Prefer machine-checkable evidence** over any hand-maintained status cell. Where a narrative status line and a table disagree, reach for the third kind of evidence, because both of those are hand-maintained.
3. **Record inter-artifact disagreement as a gate finding, never silently resolve it.**
4. **Do not repair another plan's artifact from inside a gated session.** Route it project-side. The gate's job is to read correctly, not to correct its input.
5. On the producing side, symmetrically: **fill the tracking row at closeout.** To a downstream mechanical gate, "pending" and "failed" are the same string.

The producing-side clause stays here deliberately: an unfilled Signoff once halted a plan's final session against a sprint that had passed 8/8.

---

## 4. A Set Selected by a Greppable Key Over an Existing Artifact Has a COUNT, Not an Estimate

> [!constraint] Record the number with the command that produced it
> WRONG:
> ```markdown
> | ~610 pulled | ~9.5K | The claims to design (largest probe family, ~45 claims expected) |
> ```
> CORRECT:
> ```markdown
> | 85 claims   | ~18K  | `Grep pattern='\*\*Modality:\*\* headless' output_mode='count'` over
>                         Parts 1a–1d of the register = 85 (34/6/14/31), measured 2026-08-19 |
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

## 5. A Re-Anchor Keeps a Fallback for Every Version the Snapshot Set Covers

> [!constraint] An anchor edit is a claim about every version in the committed snapshot set, not only the one that prompted it
> The committed snapshot for an older version is a reading the current extractor must be able to reproduce. If it cannot, that snapshot is no longer evidence of anything. A comment that names the older form is a note to a future reader. It is not a fallback.

An `<extractor>` anchors on a `new Set([...])` literal in a bundle. A commit re-anchored the constant for version N+2, re-captured N+2 only, and left a comment naming the older form. Three sessions later, the first forced re-capture of N and N+1 produced `count: 0`, `fallback_used: "absent"` and `UNANCHORED`. The extractor was wrong for two versions it no longer claimed to handle, and nothing had asked it about them.

> [!constraint] Keep the previous form as a marked fallback, and guard every snapshot
> WRONG — replace the anchor, re-capture the newest version, document the old form in a comment:
> ```python
> # Re-anchored on N+2: the Set gained a leading "<lead>" member.
> # N and N+1 carry the four-member form without it.
> ANCHOR = (b'new Set(["<lead>","a","b","c","d"])', ...)
> # the extractor searches this form only -> older versions now report UNANCHORED
> ```
> CORRECT — keep the previous form as a fallback, mark which form matched, prove every committed snapshot still anchors:
> ```python
> ANCHOR = (b'new Set(["<lead>","a","b","c","d"])', ...)
> ANCHOR_PRE_N2 = b'new Set(["a","b","c","d"])'
> # on zero hits for the first form, search the fallback; report under the
> # fallback key with fallback_used="pre-N2-anchor" and a note naming it
> ```
> ```python
> # tests/test_guard_<surface>.py — a guard that iterates every snapshot, not the newest
> for snap in every_snapshot_dir():
>     s = load(snap / "surfaces/<surface>.json")
>     assert s["count"] >= 1 and s["fallback_used"] != "absent"
> ```

Three operative points follow.

1. **After any anchor edit, re-extract every committed version, not only the newest.** A scratch capture of each archived binary costs seconds and proves the claim the comment makes.
2. **Keep the superseded form as a fallback with a marker.** The marker lets the diff and the report show which form a version matched. Dropping the form makes older snapshots unreproducible. Silently accepting either form makes anchor drift invisible.
3. **Guard the invariant across the snapshot set.** A test that iterates every snapshot directory catches the next re-anchor at commit time, three sessions earlier than a re-capture would.

**Dry-run pair.** Run the guard once over a snapshot set whose older version the extractor still anchors, and once over a set with the fallback removed. The first run MUST pass and the second MUST fail naming the older version. A guard that passes on both has never been shown to discriminate.

**Applies to** any extractor, parser or probe that anchors on a literal the subject can change between versions, where more than one version's output is committed. It also applies to any golden-file set that a later task re-captures in place, and to any commit whose message says "re-anchor", "re-baseline" or "re-pin" for one version. §1 states the base rule: measure the anchor against the artifact. This section adds that the artifact is every version in the set.

---

*Cross-references: [verify-before-cite.md](verify-before-cite.md) §9.B (verifying the internal artifact a brief cites), [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) §2 (verifying a third-party identifier before pinning it), [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) §2 (per-unit existence assertions over aggregate count thresholds — the gate-construction counterpart to §1), [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.4 (sweeping every restatement of a refreshed count in the same document), [read-confirm-act-protocol.md](read-confirm-act-protocol.md) §1.4 (reconciling an inherited flag, receiver side).*
