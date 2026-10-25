---
description: A battery of only diff-shaped gates proves the change was clean and says nothing about the artifact's condition, so every plan names at least one state-detecting gate (§11); a pre-existing omission can arm a gate against correct work (§11.1); the cross-surface equality invariant (§11.2); compare sets, not counts (§11.3); emit the surface set at landing time (§11.4); and an extractor's own outputs cannot validate its anchor, so assert membership of an element taken from an independent surface (§11.5).
consult-when: Composing a verification battery, adding a member to an enumerated set, or accepting an extractor that anchors on a string — name at least one state-detecting gate (§11), a pre-existing omission arms a gate against correct work (§11.1), the cross-surface equality (§11.2), sets not counts (§11.3), emit the surface set at landing (§11.4), membership from an independent surface (§11.5)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Change-Detecting Versus State-Detecting Shapes

**Purpose:** A gate can discharge every proof obligation and still be structurally blind to a defect that was already there when the session opened. This file sorts gates by the question their shape can answer. It gives the enumeration-drift and extractor-anchor cases their state-detecting form. The section numbers come from `verification-gates.md`, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

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

`gate-instrument-proof-obligations.md` §10 asks whether the instrument is sound. This section asks a different question about a battery that is *entirely* sound: **what question is its shape able to answer at all?**

Sort every gate into one of two shapes:

| Shape | Recognisable by | The question it answers |
|---|---|---|
| **Change-detecting** | It reads a diff — `\| grep '^\+'`, `\| grep '^-'`, `--name-only`, a removed-line-set count, any predicate over `git diff` output | *Did this change introduce a defect?* |
| **State-detecting** | It reads the artifact as it stands — a whole-file count, an equality between two surfaces, a directory listing compared against a declaration, a resolve-every-reference pass | *Does a defect exist?* |

Anything predating the diff is a **context line**: invisible to a change-detecting gate by construction, not by oversight. A battery composed entirely of change-detecting gates proves your change was clean and says **nothing** about the artifact's condition.

> [!constraint] Every verification plan names at least one state-detecting gate
> Or it records explicitly that no state property is at risk. A battery of only change-shaped gates is not a strong battery with a gap — it is a battery that cannot answer the question a reader will assume it answered.
>
> WRONG — every gate reads the diff, so a defect older than the diff passes:
> ```
> git diff <base> -- <file> | grep '^\+' | grep -c '<forbidden>'   # 0: this change added none
> ```
> CORRECT — keep the change gate, and add one gate that reads the artifact as it stands:
> ```
> git diff <base> -- <file> | grep '^\+' | grep -c '<forbidden>'   # 0: this change added none
> Grep  pattern='<forbidden>'  path='<file>'  output_mode='count'  # 0: none exists in the file
> ```

**Enumeration drift is the worst case for a change-shaped battery.** A missing entry is an *absence*, so there is no line for any pattern to match. A stale count is *syntactically valid*, so nothing is malformed and the number is merely false. Neither leaves a trace in a diff that did not touch them.

### 11.1 The sharp edge — a pre-existing omission can arm a gate against correct work

A pre-existing omission is not only invisible going in. It can **detonate on the way out**, and the resulting failure is undiagnosable from inside the task that hits it. The shape: a task's exit gate derives its expected figure **from** the very enumeration it is checking. Landing the literal scope moves one side and not the other, because the pre-existing omission was never in scope. The gate reports a mismatch and fails **correct work**, with the true cause sitting in a line the task had no reason to open.

> [!constraint] Derive the two sides from **independent** surfaces, or the gate is checking a thing against itself
> WRONG — the expected value is derived from the enumeration under test. A member missing from that parenthetical for reasons predating this task makes the gate fail work that is entirely correct:
> ```bash
> grep -o '({first-member}.*{last-member})' {doc} | tr ',' '\n' | wc -l   # must equal the declared count
> ```
> CORRECT — each side comes from a surface the other does not derive from:
> ```
> expected = members of the router table           # the executable surface
> actual   = members of the {doc} parenthetical
> assert expected == actual                         # a pre-existing omission fails here, at its own line
> ```

When the enumeration is a source of truth that a change moved, the stale readers are the hazard: see [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §12 (Moving a Source of Truth Invalidates Every Reader of the Old One). The mirror direction (a count that passes while work is missing) and the balance-gate case are in [gate-denominator-integrity.md](gate-denominator-integrity.md) §2 and §4.

### 11.2 The cross-surface equality invariant

Where two surfaces enumerate the same set, assert their **equality**. Never assert either one against a remembered number.

> [!constraint] Both sides of the gate are derived live
> WRONG — one surface is checked against a remembered number:
> ```bash
> [ "$(grep -c '^## [0-9]' README.md)" = "13" ] || echo MISMATCH
> ```
> CORRECT — table-of-contents entries must equal numbered body sections. Both sides derived live; no constant appears anywhere in the gate:
> ```bash
> [ "$(grep -cE '^- \[[0-9]+\.' README.md)" = "$(grep -c '^## [0-9]' README.md)" ] || echo MISMATCH
> ```

The gate is Absence-detecting (a missing member moves one side), State-based (a defect three sprints old fails it today) and Self-maintaining (no baseline to re-measure). Its fourth property, Cannot false-fail correct work, holds because correct work moves both sides together. A threshold gate has none of these properties. **The equality gate must reference no constant.** If a number appears on either side, it is a threshold wearing an equality's clothes, and it will drift.

### 11.3 Compare sets, not counts

Cardinality equality is necessary and **not sufficient**. Three surfaces at thirteen rows each can still disagree on membership, and every count-based gate passes. Extract the member set from each surface and assert the **symmetric difference is empty** against a designated reference surface. That is typically the router or dispatch table, the one surface that is executable rather than descriptive.

> [!constraint] Diff the member sets, and report the divergent member
> WRONG — the gate compares counts, so two different sets of thirteen pass:
> ```bash
> [ "$(wc -l < surface-a.txt)" = "$(wc -l < surface-b.txt)" ] || echo MISMATCH   # 13 = 13
> ```
> CORRECT — extract each surface's members, then diff the sorted sets pairwise. A non-empty diff names the divergent member, which a count never can:
> ```bash
> diff <(sort surface-a.txt) <(sort surface-b.txt)   # MUST be empty
> ```

Report the divergent member, not the counts: `harvest present in the router, absent from the quick reference` sends the reader to the line, and `13 != 12` sends them to count rows.

### 11.4 Emit the surface set at landing time

The root cause of enumeration drift is that a feature's surfaces are **not mechanically linked**. Nothing fails when one of four is missed, so the set has to be *remembered*. The durable fix is making the set **enumerable rather than remembered**: a task that lands a new member of any enumerated set names every surface that enumerates it, in the task file, as a checklist the exit gate walks. Where the surfaces live in one repo, §11.3's set comparison then holds the checklist honest without anyone re-deriving it.

> [!constraint] The task file names every surface, and the exit gate walks the list
> WRONG — the set of surfaces lives in a reviewer's memory:
> ```
> task: add member "harvest" to the router      # exit gate: "reviewer checks the docs"
> ```
> CORRECT — the task file enumerates the surfaces, so a missed one fails the gate:
> ```
> surfaces: router table, help text, quick reference, README   # exit gate walks all four
> ```

**Dry-run an equality gate in BOTH directions before trusting it.** Run it against a state where the defect is genuinely present (an earlier revision is the cheapest source) and show it **FAIL**. Then run it against a correct state and show it **PASS**. The FAIL proves it discriminates. The PASS proves it does not fail correct work, which §11.1 shows is the specific way this gate class goes wrong. A gate never shown to fail is not evidence, and a gate never shown to pass on correct input is a retry loop waiting to happen.

### 11.5 An extractor's own outputs cannot validate its anchor

An extractor anchors on a string in a bundle, a binary or a generated `.d.ts`, and reads the enclosing object. An anchor can land on a real object of the right shape that is the wrong object, and every property the extractor computes is then also true of it. Count, boundedness and parity are necessary and never sufficient.

> [!constraint] The only discriminating check is membership of an element the extractor did not decide
> Take the element from an independent surface: a documented option, a name pinned in a finding, or a line in the tool's own `--help` capture. Assert that it is in the extracted set.
>
> WRONG — accept the extractor on its own evidence:
> ```
> anchor found → object bounded (byte-verified) → 81 names, all --flag shaped
> → parity across two builds → fallback null → ACCEPT
> # Every fact is true. The object is an option-forwarding list, not the registry the help text renders from.
> # The real registry held 138 names.
> ```
> CORRECT — cross-check against a surface the extractor did not produce:
> ```
> pick 3-6 members that MUST be present (spec-pinned, or read from the help capture)
> assert each is in the extracted set                  # membership, never a count
> on a miss: search the independent surface for the member (Grep over the help capture)
>   present there, absent here -> the anchor is the wrong object, not the build
>   absent there too           -> the build dropped it (a real finding)
> ```

Three rules follow.

- **Every extractor gets at least one membership assertion against an independent surface.** The task that writes the snapshot owns that assertion, not a later test tier. A wrong-object anchor in a first capture is invisible to every later diff, because each diff compares the same wrong object with itself.
- **A gate made only of properties the extractor computed is a gate the extractor grades itself on.** It cannot fail for the reason that matters.
- **On a membership miss, the first diagnostic is the cross-surface search.** It separates "the extractor missed it" from "the build removed it" in one call.

§11.1 states the general form (derive the two sides from independent surfaces). [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 states what any instrument must prove before its output counts as evidence. For a "count unchanged" gate: [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §10.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the proof obligations a state-detecting gate still owes) · [gate-denominator-integrity.md](gate-denominator-integrity.md) §2 and §4 (a count that passes while work is missing; the balance-gate case) · [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §12 (moving a source of truth invalidates every reader of the old one) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §10 (a "count unchanged" gate beside an addition that shares its vocabulary) · [verification-gates.md](verification-gates.md) (the family index).*
