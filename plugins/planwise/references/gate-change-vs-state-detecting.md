---
description: A battery of only diff-shaped gates proves the change was clean and says nothing about the artifact's condition, so every plan names at least one state-detecting gate (§11); a pre-existing omission can arm a gate against correct work (§11.1); the cross-surface equality invariant (§11.2); compare sets, not counts (§11.3); emit the surface set at landing time (§11.4); and an extractor's own outputs cannot validate its anchor, so assert membership of an element taken from an independent surface (§11.5).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Change-Detecting Versus State-Detecting Shapes

**Purpose:** A gate can discharge every proof obligation and still be structurally blind to a defect that was already there when the session opened. This file sorts gates by the question their shape can answer, and gives the enumeration-drift and extractor-anchor cases their state-detecting form. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** you compose a verification battery, a change adds a member to an enumerated set that several surfaces restate, or you write or accept an extractor that anchors on a string in a bundle, a binary or a generated file.

## Table of Contents

- [11. Change-Detecting vs State-Detecting Gates](#11-change-detecting-vs-state-detecting-gates)
  - [11.1 The sharp edge — a pre-existing omission can arm a gate against correct work](#111-the-sharp-edge--a-pre-existing-omission-can-arm-a-gate-against-correct-work)
  - [11.2 The cross-surface equality invariant](#112-the-cross-surface-equality-invariant)
  - [11.3 Compare sets, not counts](#113-compare-sets-not-counts)
  - [11.4 Emit the surface set at landing time](#114-emit-the-surface-set-at-landing-time)
  - [11.5 An extractor's own outputs cannot validate its anchor](#115-an-extractors-own-outputs-cannot-validate-its-anchor)

---

## 11. Change-Detecting vs State-Detecting Gates

`gate-instrument-proof-obligations.md` §10 asks whether the instrument is sound. This section asks a different question about a battery that is *entirely* sound: **what question is its shape able to answer at all?** A gate can discharge all four proof obligations and still be structurally blind to a defect that was already there when the session opened.

Sort every gate into one of two shapes:

| Shape | Recognisable by | The question it answers |
|---|---|---|
| **Change-detecting** | It reads a diff — `\| grep '^\+'`, `\| grep '^-'`, `--name-only`, a removed-line-set count, any predicate over `git diff` output | *Did this change introduce a defect?* |
| **State-detecting** | It reads the artifact as it stands — a whole-file count, an equality between two surfaces, a directory listing compared against a declaration, a resolve-every-reference pass | *Does a defect exist?* |

The two are not interchangeable, and the gap is not a matter of degree. Anything predating the diff is a **context line**: invisible to a change-detecting gate by construction, not by oversight. A battery composed entirely of change-detecting gates proves your change was clean and says **nothing** about the artifact's condition.

> [!constraint] Every verification plan names at least one state-detecting gate
> Or it records explicitly that no state property is at risk. A battery of only change-shaped gates is not a strong battery with a gap — it is a battery that cannot answer the question a reader will assume it answered.

**Enumeration drift is the worst case for a change-shaped battery.** A missing entry is an *absence* — there is no line for any pattern to match — and a stale count is *syntactically valid*, so nothing is malformed; the number is merely false. Neither leaves a trace in a diff that did not touch them.

### 11.1 The sharp edge — a pre-existing omission can arm a gate against correct work

A pre-existing omission is not only invisible going in. It can **detonate on the way out**, and the resulting failure is undiagnosable from inside the task that hits it.

The shape: a task's exit gate derives its expected figure **from** the very enumeration it is checking. Landing the literal scope — add the new member, derive both figures live — moves one side and not the other, because the pre-existing omission was never in scope. The gate reports a mismatch and fails **correct work**, with the true cause sitting in a line the task had no reason to open.

```bash
# WRONG — the expected value is derived from the enumeration under test.
# A member missing from that parenthetical for reasons predating this task
# makes the gate fail work that is entirely correct.
grep -o '({first-member}.*{last-member})' {doc} | tr ',' '\n' | wc -l   # must equal the declared count
```

Derive the two sides from **independent** surfaces, or the gate is checking a thing against itself. When the enumeration is a source of truth that a change moved, the stale readers are the hazard: see [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §12 (Moving a Source of Truth Invalidates Every Reader of the Old One). The mirror direction (a count that passes while work is missing) and the balance-gate case are in [gate-denominator-integrity.md](gate-denominator-integrity.md) §2 and §4.

### 11.2 The cross-surface equality invariant

Where two surfaces enumerate the same set, assert their **equality**. Never assert either one against a remembered number.

```bash
# Table-of-contents entries must equal numbered body sections.
# Both sides derived live; no constant appears anywhere in the gate.
[ "$(grep -cE '^- \[[0-9]+\.' README.md)" = "$(grep -c '^## [0-9]' README.md)" ] || echo MISMATCH
```

Four properties make this the right shape, and a threshold gate has none of them:

| Property | Why |
|---|---|
| Absence-detecting | It compares cardinalities, so a missing member moves one side. No pattern has to match the thing that is not there. |
| State-based | It evaluates the file as it stands. A defect three sprints old fails it today. |
| Self-maintaining | Both sides are derived live. There is no baseline to re-measure and no threshold to drift. |
| Cannot false-fail correct work | Correct work moves both sides together — precisely the failure §11.1 describes. |

> [!verify] The equality gate must reference no constant
> If a number appears on either side, it is a threshold wearing an equality's clothes, and it will drift. The gate above names `README.md` and two patterns; it names no count.

### 11.3 Compare sets, not counts

Cardinality equality is necessary and **not sufficient**. Three surfaces at thirteen rows each can still disagree on membership — one lists a member another omits, and a fourth carries a member that no longer exists. Both counts read thirteen and every count-based gate passes.

Extract the member set from each surface and assert the **symmetric difference is empty** against a designated reference surface — typically the router or dispatch table, the one surface that is executable rather than descriptive:

```bash
# Extract each surface's members, then diff the sorted sets pairwise.
# A non-empty diff names the divergent member, which a count never can.
diff <(sort surface-a.txt) <(sort surface-b.txt)   # MUST be empty
```

Report the divergent member, not the counts. A gate that says `13 != 12` sends the reader to count rows; a gate that says `harvest present in the router, absent from the quick reference` sends them to the line.

### 11.4 Emit the surface set at landing time

The root cause of enumeration drift is that a feature's surfaces are **not mechanically linked**. Nothing fails when one of four is missed, so the set has to be *remembered* — and one landing routinely leaves two or three surfaces stale across sprints.

The durable fix is not a sharper reviewer. It is making the set **enumerable rather than remembered**: a task that lands a new member of any enumerated set names every surface that enumerates it, in the task file, as a checklist the exit gate walks. Where the surfaces live in one repo, §11.3's set comparison then holds the checklist honest without anyone re-deriving it.

> [!constraint] Dry-run an equality gate in BOTH directions before trusting it
> Run it against a state where the defect is genuinely present — an earlier revision is the cheapest source — and show it **FAIL**. Then run it against a correct state and show it **PASS**. The FAIL proves it discriminates; the PASS proves it does not fail correct work, which §11.1 shows is the specific way this gate class goes wrong. A gate never shown to fail is not evidence, and a gate never shown to pass on correct input is a retry loop waiting to happen.

### 11.5 An extractor's own outputs cannot validate its anchor

An extractor locates data by anchoring on a string and reading the enclosing object. The object may be a minified bundle, a packed binary or a generated `.d.ts`. An anchor can land on a real object of the right shape that is the wrong object.

Every property the extractor computes is then also true of the wrong object. The anchor is found. The object is bounded. The count is plausible. Two builds agree. The fallback path was not used. Count, boundedness and parity are necessary and never sufficient.

> [!constraint] The only discriminating check is membership of an element the extractor did not decide
> Take the element from an independent surface: a documented option, a name pinned in a finding, or a line in the tool's own `--help` capture. Assert that it is in the extracted set.

```
WRONG — accept the extractor on its own evidence:
anchor found → object bounded (byte-verified) → 81 names, all --flag shaped
→ parity across two builds → fallback null → ACCEPT
# Every fact is true. The object is an option-forwarding list, not the registry the help text renders from.
# The real registry held 138 names.

CORRECT — cross-check against a surface the extractor did not produce:
pick 3-6 members that MUST be present (spec-pinned, or read from the help capture)
assert each is in the extracted set                  # membership, never a count
on a miss: search the independent surface for the member (Grep over the help capture)
  present there, absent here -> the anchor is the wrong object, not the build
  absent there too           -> the build dropped it (a real finding)
```

Three rules follow.

- **Every extractor gets at least one membership assertion against an independent surface.** The task that writes the snapshot owns that assertion, not a later test tier. A wrong-object anchor in a first capture is invisible to every later diff, because each diff compares the same wrong object with itself.
- **A gate made only of properties the extractor computed is a gate the extractor grades itself on.** It cannot fail for the reason that matters.
- **On a membership miss, the first diagnostic is the cross-surface search.** It separates "the extractor missed it" from "the build removed it" in one call. It is the difference between fixing an anchor and filing a false removal against the subject.

§11.1 states the general form (derive the two sides from independent surfaces). [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 states what any instrument must prove before its output counts as evidence. For a "count unchanged" gate: [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §10.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the proof obligations a state-detecting gate still owes) · [gate-denominator-integrity.md](gate-denominator-integrity.md) §2 and §4 (a count that passes while work is missing; the balance-gate case) · [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §12 (moving a source of truth invalidates every reader of the old one) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §10 (a "count unchanged" gate beside an addition that shares its vocabulary) · [verification-gates.md](verification-gates.md) (the family index).*
