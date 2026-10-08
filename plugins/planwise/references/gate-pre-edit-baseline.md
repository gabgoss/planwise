---
description: Every Before/After gate records its measured pre-edit value inline beside its post-edit expectation, written from a run against the live pre-edit tree (§10.1); a gate whose pre-edit value already satisfies its expectation is vacuous by construction and is rewritten, never shipped with a caveat (§10.2); a preservation gate is marked `invariant:` on the annotation line (§10.3); why the annotation and not only the discipline, and the WARNING/ERROR split (§10.4); Reviewer Check 082.
paths: {planwise_root}/{plans_dir}/**
---

# Gate Pre-Edit Baseline (Every Gate Records Its Measured Pre-Edit Value)

**Purpose:** A verification gate answers one question, did the work happen, and it can only answer it if its value differs before and after the work. This file holds the annotation grammar, the vacuity test, the preservation exemption and the reviewer check. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write an After-block gate or a Success Criteria expectation over a measured value, you review one, or `scripts/lint_verification_gates.py` reports Check 1 or Check 2.

## Table of Contents

- [10. Every Gate Records Its Measured Pre-Edit Value](#10-every-gate-records-its-measured-pre-edit-value)
  - [10.1 The annotation](#101-the-annotation)
  - [10.2 A gate whose pre-edit value already satisfies its expectation is vacuous by construction](#102-a-gate-whose-pre-edit-value-already-satisfies-its-expectation-is-vacuous-by-construction)
  - [10.3 Invariant and preservation gates are exempt — and must be marked](#103-invariant-and-preservation-gates-are-exempt--and-must-be-marked)
  - [10.4 Why the annotation, and not just the discipline](#104-why-the-annotation-and-not-just-the-discipline)

---

## 10. Every Gate Records Its Measured Pre-Edit Value

A verification gate exists to answer one question: *did the work happen?* It answers that question only if its value **differs** before and after the work. A gate whose pre-edit value already satisfies its post-edit expectation returns the same verdict against an untouched tree as against a finished one — green before the task starts, and nothing the task does or fails to do can change it. That is not a weak gate; it is not a gate at all.

The defect is invisible on the page. The command is well-formed, the expectation is reasonable, and the gate reports green — which is exactly what a correct gate reports. The one fact separating the two is the value the command returned *before* the edit, and that fact is cheap to obtain only while the pre-edit tree still exists. Afterwards it is gone.

**Distinct from baseline-commit scoping.** [verification-gates.md](verification-gates.md) §8 requires a diff-derived gate to name a recorded baseline **commit** — it governs *which tree state* the gate reads. This section requires a recorded pre-edit **value** — it governs *whether the gate can discriminate at all*, whatever tree it reads. The two are independent: a perfectly baseline-scoped diff gate is still vacuous if its pre-edit value already met its expectation, and a gate carrying a correct pre-edit annotation still misattributes work if it diffs an unpinned tree. Apply both; neither restates the other.

### 10.1 The annotation

> [!constraint] Every Before/After gate records its measured pre-edit value inline beside its post-edit expectation
> WRONG — the expectation stands alone. Nothing in the artifact records what the value was before the edit, so neither the author, a reviewer, nor a later checker can tell whether this gate could ever have failed:
> ```bash
> grep -c '{token}' {file}   # expect >=1
> ```
> CORRECT — the measured pre-edit value sits inline, immediately beside the expectation it is supposed to contradict:
> ```bash
> grep -c '{token}' {file}
> # pre-edit: 0 → expect >=1
> ```
> The annotation is written **from a run against the live pre-edit tree**, never from intent. A value recalled from memory, inferred from the task's own objective, or copied from a sibling gate is not a measurement and does not satisfy this rule.

The annotation's grammar is one comment line adjacent to the command it annotates:

```
# pre-edit: {measured value} → expect {post-edit expectation}
```

The literal token `pre-edit:` is the load-bearing part — a reviewer or a mechanical checker keys on it — so keep it verbatim and keep the measured value immediately after it. The arrow and the surrounding wording are readability, not syntax.

### 10.2 A gate whose pre-edit value already satisfies its expectation is vacuous by construction

Once both numbers sit side by side, the test is arithmetic. If the recorded pre-edit value **already satisfies** the stated expectation, the gate is vacuous by construction: it passes with zero work done, so it cannot answer the only question a gate exists to answer. Such a gate MUST be rewritten before it ships — not relaxed, not shipped with a caveat, and not retained "as a sanity check". A gate that always passes contributes nothing to an exit battery except false confidence, and it displaces the gate that would have caught the failure.

> [!constraint] Rewrite a vacuous gate — never ship one with a caveat
> WRONG — a count gate measured against an untouched file that already met its threshold. The token the edit is meant to introduce is already present elsewhere in the file: in a section this task does not modify, or in text this task preserves verbatim. The count clears the threshold before the task begins:
> ```bash
> grep -c '{token}' {file}
> # pre-edit: 2 → expect >=1        # 2 already satisfies >=1 — green on an untouched tree
> ```
> CORRECT — rewrite so the pre-edit value **fails** the expectation. Either raise the threshold past the measured baseline, or narrow the pattern to the construct the edit actually introduces so the baseline is zero:
> ```bash
> grep -c '{token}' {file}
> # pre-edit: 2 → expect 3          # the 2 pre-existing matching lines plus the 1 this task adds
> grep -c '{anchor-the-edit-introduces}' {file}
> # pre-edit: 0 → expect 1
> ```
> Both rewrites share the property the original lacked: the pre-edit value contradicts the expectation. That property — not the presence of an annotation — is what makes a gate discriminate. The annotation is what makes the property checkable by someone other than the author.

The same arithmetic governs the mirror shapes:

| Gate shape | Vacuous when | Rewrite |
|------------|--------------|---------|
| `expect >=N` presence gate | the pre-edit value is already `>=N` | Raise the threshold past the measured baseline, or narrow the pattern to what the edit adds |
| `expect 0` absence gate | the pre-edit value is already `0` | The token being scrubbed was never in this population; assert against the population that actually carries it, or drop the gate |
| `expect {exact}` equality gate | the pre-edit value already equals `{exact}` | Either the edit genuinely does not move this value — mark it invariant per §10.3 — or the expectation is wrong |

The second row deserves particular attention: an absence gate measuring `0` before the edit is the shape most often mistaken for a passing check, because "expect 0, got 0" reads as success in every report format.

### 10.3 Invariant and preservation gates are exempt — and must be marked

Some gates exist precisely to assert that a value does **not** move: a count the edit must preserve, a block that must survive a refactor untouched, a section a split must leave in place. For these, `pre == post` is the correct and intended outcome, and §10.2's test would flag every one of them.

They are exempt — but only when the author marks them, because a marked preservation gate and an unmarked vacuous gate are textually identical. Both record a pre-edit value that satisfies the expectation. The marking is the only thing separating an author who measured the value and intends it to hold from an author who never measured at all.

> [!constraint] Mark a preservation gate with `invariant:` in place of `expect` on the annotation line
> CORRECT — the marker sits on the annotation line and names what must not move:
> ```bash
> grep -c '{token}' {file}
> # pre-edit: 3 → invariant: 3 (this count must NOT move — a revert drops it, a duplicate raises it)
> ```
> A gate carrying `invariant:` is exempt from the vacuity finding and MUST NOT be flagged for it. A gate whose pre-edit value satisfies an `expect` is **not** exempt, whatever the surrounding prose asserts: the marker lives on the annotation line or it does not exist, because the annotation line is the only place a checker can read it.
>
> WRONG — adding the marker to silence a finding on a gate that was written to detect a change. `invariant:` is a claim that the author measured the value and intends it unchanged; used to quiet a true finding, it converts a detectable defect into an undetectable one — strictly worse than the vacuous gate it replaced.

### 10.4 Why the annotation, and not just the discipline

A rule saying only "make sure your gates can fail" would be correct and unenforceable. Without the recorded value, vacuity is **unknowable** from the artifact: the command and the expectation are both present and both look fine, and the one fact that decides the question exists nowhere in the file. A reviewer cannot recover it without re-running every command against a tree state that no longer exists. The measurement therefore has to be written down at the only moment it is cheap — before the edit, by the author who is running the command anyway to decide what to expect.

That asymmetry is why the two findings carry different severities:

- **No annotation → WARNING.** The gate may be perfectly good; nothing in the artifact establishes that. Absence of evidence is not evidence of a defect — but it is exactly indistinguishable from an author who never measured, which is why it cannot be silently accepted.
- **Annotation present and already satisfied → ERROR.** Here the artifact carries positive evidence that the gate cannot fail. No further investigation is needed, and none should be spent.

Recording the value costs nothing beyond writing down what the author already ran. It is the cheapest available defence against the class, which is why it is required rather than recommended.

#### Reviewer Check 082 — Verification Gate Without a Measured Pre-Edit Baseline

- **Severity / Role / Type:** ERROR (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** Every After-block gate MUST record its measured pre-edit value inline beside its post-edit expectation. A gate whose recorded pre-edit value already satisfies its expectation is vacuous by construction — it passes with zero work done, so it cannot answer whether the work happened — and MUST be rewritten before it ships. An After-gate carrying no pre-edit annotation is a WARNING: the value was never recorded, so vacuity is unknowable from the artifact.
- **Detection:**
  1. Open the task file's Verification Commands After block, plus every Success Criteria item stating an expectation over a measured value.
  2. For each command, look for an inline pre-edit annotation on an adjacent line (`# pre-edit: {N} → expect …`, or an equivalent recording of the measured pre-edit value). Absent → WARNING.
  3. Annotation present: evaluate the recorded pre-edit value against the stated expectation using the gate's own comparator. If the pre-edit value already satisfies it → ERROR (vacuous by construction).
  4. An author-marked invariant/preservation gate — the annotation line reads `invariant:` rather than `expect`, and `pre == post` is the intended outcome — is exempt and MUST NOT be flagged by steps 2 or 3.
  5. Where the pre-edit tree state is still reachable, re-measure and compare against the recorded value; a recorded baseline that disagrees with the measured one → ERROR (the annotation was authored from intent, not from a run).
  6. A gate whose subject is a report the same work produces: if it greps a bare token the report's own template emits, rather than the machine-readable verdict line or the status-cell row pattern → WARNING.
- **Finding template:**
```
[ERROR] Verification gate is vacuous — pre-edit value already satisfies its expectation
File: {task file path} | Location: Verification Commands After block / Success Criteria step {n}
Issue: Gate `{command}` states `expect {comparator}{N}`; recorded/measured pre-edit value is {M}, which already satisfies it — the gate passes with zero work done and cannot detect whether the work happened
Fix: Rewrite so the pre-edit value contradicts the expectation per references/gate-pre-edit-baseline.md §10 (raise the threshold past the measured baseline, or narrow the pattern to the construct the edit introduces), or mark the gate `invariant:` if pre == post is the intended outcome | Confidence: HIGH
```

---

*Cross-references: [gate-diff-baseline-pinning.md](gate-diff-baseline-pinning.md) (the recorded baseline **commit** a diff gate reads; today `verification-gates.md` §8 — this file governs the recorded pre-edit **value**) · [gate-input-set-and-compared-window.md](gate-input-set-and-compared-window.md) §10.6 (the input-set counts a diff-pinned criterion records beside its verdict) · [gate-pinned-from-real-content.md](gate-pinned-from-real-content.md) §10.5 (a gate over a report the work itself produces has no pre-edit tree; it reads the verdict line) · [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.7 (the mirror defect: a gate that cannot pass) · [gate-command-semantics.md](gate-command-semantics.md) §10.8-§10.9 (a well-formed gate that measures something else) · [verification-task-authoring.md](verification-task-authoring.md) (the family index).*
