---
description: A gate whose pattern is narrower than the claim it is cited to support returns its PASS value against known-bad input. Covers the paired-input control taken from version control, the three ways a pattern ends up narrower than its claim, case blindness in both directions, asserting a negative from a pattern shaped for a different positive, why a wrong figure in a briefing costs more than a wrong gate, and the diff-filter character class that silently drops a whole syntactic population. Consult when about to cite a grep, a count, or a diff filter as proof.
paths: {planwise_root}/{plans_dir}/**
---
# Gate Predicate Discrimination — a Pattern Narrower Than Its Claim Passes Against Known-Bad Input

**Purpose:** A verification command runs, exits clean, and prints an accurate number that answers a different question than the one asked. The machinery is not broken. The predicate is narrower than the claim it was cited to support, so the gate returns its PASS value over input that genuinely carries the defect.

**Read this when** you are about to cite a match pattern, a count, or a diff filter as evidence — in a status block, a review finding, a briefing figure, or a session closeout.

The failure is invisible in the passing direction. A `grep -c` returning `0` looks identical whether it scanned the defect and found it absent, or could never have matched the defect at any point, for any input. Both print `0`.

This is the predicate half of a two-part problem. [`measurement-discipline.md`](measurement-discipline.md) §8.7 owns the **input set** — the ways a gate ends up unable to fail because the thing it should have read never reached it. That section's own premise is that the input-set assertions *"are what make the gate's empty result mean anything"*. This file covers the case where the input set is complete and the **predicate** is vacuous. Both roads end at a green result over something nobody checked.

## Table of Contents

- [1. Prove the Pattern Discriminates Before Citing It as Evidence](#1-prove-the-pattern-discriminates-before-citing-it-as-evidence)
- [2. Three Corollaries on Pattern Width](#2-three-corollaries-on-pattern-width)
- [3. Case Blindness Is a Standing Hazard, and It Fires in Both Directions](#3-case-blindness-is-a-standing-hazard-and-it-fires-in-both-directions)
- [4. Never Assert a Negative From a Pattern Shaped for a Different Positive](#4-never-assert-a-negative-from-a-pattern-shaped-for-a-different-positive)
- [5. A Bad Figure in a Briefing Is Worse Than a Bad Gate](#5-a-bad-figure-in-a-briefing-is-worse-than-a-bad-gate)
- [6. Anchor a Diff Filter on the Sign Alone, and Strip Headers by Name](#6-anchor-a-diff-filter-on-the-sign-alone-and-strip-headers-by-name)
- [7. Fixture-Shape Discipline for Any Diff Instrument](#7-fixture-shape-discipline-for-any-diff-instrument)
- [8. The Author of a Check Cannot Be Its Auditor](#8-the-author-of-a-check-cannot-be-its-auditor)

---

## 1. Prove the Pattern Discriminates Before Citing It as Evidence

§8.7 of [`measurement-discipline.md`](measurement-discipline.md) mandates the dry-run: run every gate once against input that genuinely carries the pattern and once against clean input, and require the two runs to differ. What it does not give is the recipe. This section supplies one that needs no scratch file, because for a tracked file the known-bad state is already in version control.

```bash
# The paired-input control — no scratch file, no shipped-tree pollution:
git show HEAD:path/to/file.md | grep -cE "$PATTERN"   # known-bad  → expect N
grep -cE "$PATTERN" path/to/file.md                   # current    → expect M, M ≠ N
```

Report each anchor as `HEAD-value → current-value`. An anchor that cannot be shown to move is **non-discriminating**. Report it as such. Never cite it as a pass.

> [!constraint] A literal-string anchor run once, against one state, is not evidence
> ```
> WRONG — literal string, single run, cited as proof:
>   grep -c "owning backlog item has shipped" f.md   # 0  → "clean"
>   (returned 0 before the defect was fixed, too)
>
> CORRECT — regex covering the claim, paired against HEAD:
>   git show HEAD:f.md | grep -cE "owning (backlog )?item ship"   # 2
>   grep -cE "owning (backlog )?item ship" f.md                   # 0   ← moved, so it discriminates
> ```
> The live text read *"item shipped"* and *"item ships"*. The anchor was written against a third phrasing that appeared nowhere, so it returned the pass value in both states. A single clean run is consistent with "the defect is absent" and with "this pattern cannot see the defect", and those two readings are indistinguishable from the output alone.

The cost of skipping the control is not the one run you save. An anchor accepted as a pass is quoted downstream as settled, and every later consumer inherits it without re-deriving.

---

## 2. Three Corollaries on Pattern Width

Each is a real miss, and each is a different mechanism by which a pattern ends up narrower than the claim it stands for.

**Match the claim, not a sentence.** Write the pattern against the *concept* being retired, then verify it catches every phrasing present in the pre-edit text. `"has shipped"`, `"shipped"` and `"ships"` are three surfaces of one claim. A pattern anchored on the first is silent on the other two.

**Case matters when the same word appears as prose and as a heading or label.** Use `-i`, or give the capitalised form its own anchor. A lowercase `grep -c "orphaned"` proposed to verify a two-line change would have reported the work half-landed, because one of the two lines read `**Orphaned (owner closed, content absent):**`.

**A placeholder is not the identifier form.** A pattern written as `{PREFIX}-[0-9]` cannot see `{PREFIX}-{NNN}`, and a sweep scoped to one identifier family under-counts a corpus that carries several. State which family a count covers. [`measurement-discipline.md`](measurement-discipline.md) §8.7 sub-rule A carries the narrower case of this, where the same identifier reaches a file glued into a filename with no separator for the pattern to anchor on. The general form is the one stated here: **the spellings a claim covers are a set, and a pattern that matches one member is evidence about that member only.**

---

## 3. Case Blindness Is a Standing Hazard, and It Fires in Both Directions

A hazard shown to fail in both directions is a class rather than an anecdote. Both directions are cheap to produce and neither announces itself.

| Direction | Instance |
|---|---|
| Audit false-negative | An orchestrator's case-sensitive search failed to find a runner's `Duplicate label`, briefly making a **correct claim look wrong**. The search was at fault, not the claim. |
| Gate false-negative | A task's after-gate `grep -n 'owner'` ran against a section titled *"Every Verification Command Names Its **O**wner"*. A correct artifact whose only occurrence is the capitalised heading **fails a gate it satisfies**. |

The remedy is to fix the gate — `grep -ni 'owner'` — and never to adjust the wording. The next author of that section has no reason to preserve a lowercase occurrence they do not know is load-bearing, so a wording fix decays on the next edit while a pattern fix does not.

The second direction has an adjudication half, and it already ships: [`verification-gate-evidence.md`](verification-gate-evidence.md) §12 governs what to do when a runner discloses that it shaped an artifact to satisfy a gate. Read it alongside this section rather than re-deriving it. What §3 adds is the upstream half — the pattern property that puts a runner in that position in the first place.

---

## 4. Never Assert a Negative From a Pattern Shaped for a Different Positive

A presence query and an absence claim are different questions. A pattern built for the first is not evidence for the second, however correct its output.

> [!constraint] A negative claim needs a query whose positive result you would have believed
> ```
> WRONG — assert absence from the output of a pattern shaped for a different class of hit:
>   grep -nE '## [345]\.' <file>      # returns the numbered sites
>   → "these are the only ### headings in the file"     ← the pattern cannot see unnumbered ones
>
> CORRECT — query the class you intend to make a claim about, on its own terms:
>   grep -c '^### ' <file>            # the actual population
>   grep -n  '^### ' <file>           # and its members
>   → "6 third-level headings; 2 are numbered (### 4.A/4.B), 4 are not"
> ```
> The true count was 6, not 2. The presence query was correct for the question it asked, and the answer was written into a runner's spawn prompt as an absence claim about a different question.

The decision test is the memorable form: **if you would not have accepted this command's output as proof the class exists, do not accept its silence as proof the class is absent.**

---

## 5. A Bad Figure in a Briefing Is Worse Than a Bad Gate

The same wrong pattern costs differently depending on which register consumes it.

| Register | Bad pattern produces | Who consumes it | Failure mode |
|---|---|---|---|
| Gate | a false PASS | the verifier | defect ships unnoticed |
| Briefing figure | a false premise | the *runner*, as authoritative fact | runner acts on it, or must spend effort refuting its own orchestrator |

A briefing figure is handed down with institutional weight, so a runner that trusts it skips its own measurement — which is exactly the efficiency the figure exists to buy. A wrong figure does not merely fail to help. It **displaces** the correct measurement it was meant to substitute for.

The corrective is not to stop supplying figures. Handing them down is a genuine efficiency and should continue. What makes it safe is the standing clause every spawn prompt carries, stated in [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md): *"if a live measurement disagrees, the live measurement wins — report the disagreement."* That clause converts an orchestrator error from a directive into a hypothesis. Supply the figure, and supply the clause with it.

---

## 6. Anchor a Diff Filter on the Sign Alone, and Strip Headers by Name

A filter written to remove *noise* can remove a *population*, and the two are indistinguishable in the output.

> [!constraint] `^[+-]` and `^\+` are the safe anchors — any character class immediately after them is a candidate blind spot
> ```bash
> # WRONG — excludes +++/---, and silently also excludes every added or removed bullet (`+- item`):
> git diff -- <path> | grep -E '^[+-][^+-]'
> # Fed a diff whose only change is `+- [Native tool use](…) — …`, this returns nothing,
> # and the change reads as "file unmodified".
>
> # CORRECT — anchor on the sign alone and remove the headers by name:
> git diff -- <path> | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'
> # For added-lines-only gates the equivalent pair is: grep '^\+' | grep -v '^+++'
> ```

Markdown documentation is mostly bullets and tables, so a diff filter blind to bullets is blind to much of what a documentation change actually is. The `[^+-]` class was written to exclude two header shapes. It also excludes every line whose first content character is `-` or `+`, which is every list item in the corpus the filter was aimed at.

---

## 7. Fixture-Shape Discipline for Any Diff Instrument

Before trusting a diff filter, run it against a diff containing all four of these shapes:

- a bullet
- a table row
- an indented code line
- a plain paragraph line

If any of the four vanishes and you did not intend it to, the filter is wrong. Four shapes is the minimum set because each exercises a different leading character, and a character-class blind spot is invisible against any single shape.

Two cross-check rules follow:

- **Cross-check a "no changes" result against `git diff --name-only` or `--numstat` before concluding a file is unmodified.** Disagreement between two instruments is cheaper to notice than a false negative accepted downstream. It is what caught the bullet-blind filter.
- **`--numstat` is often the better instrument outright** for "did this file change, and by how much". It cannot be fooled by line shape at all, and a `+1/−1` result additionally proves nothing *else* in the file moved. That is stronger evidence than a battery of per-symbol searches.

---

## 8. The Author of a Check Cannot Be Its Auditor

> [!practice] Cross-reading is part of the verification design, not a happy accident
> A battery can be **correctly and thoroughly executed** and still miss, because the miss is in the battery's *specification* rather than its execution. Two of the instances in this file were caught only because a different session, holding a different brief, read the artifact for an unrelated reason. No self-check replaces that, because the reader who wrote the pattern reconstructs the claim from the same model that produced the pattern.
>
> Route the finding, rather than relying on the reader. **A runner that surfaces an out-of-scope defect without fixing it is behaving correctly.** Findings reach a decision only when a runner reports them in a status block instead of silently repairing them or silently ignoring them. Both silent options are always available, and neither leaves a trace. A status-block field that carries out-of-scope observations to the orchestrator is what converts a lucky read into a reliable mechanism.

This section is deliberately written without a mechanical gate. "Have a different session read it" cannot be asserted by a command, and dressing it as a constraint with a fabricated verification command would reproduce the exact defect this file describes.

---

*Cross-reference: [`measurement-discipline.md`](measurement-discipline.md) §8.7 (the gate's input set — the other half of an unfalsifiable gate, and the dry-run mandate this file gives a recipe for) · [`verification-gate-evidence.md`](verification-gate-evidence.md) §12 (adjudicating a disclosure that a gate shaped its own subject), §3 (the correct-post-state arm of the dry-run) · [`verification-gates.md`](verification-gates.md) §8 (the recorded baseline a diff-scoped gate pins) · [`verification-task-authoring.md`](verification-task-authoring.md) §10.9 (reading a gate command as a program) · [`read-confirm-act-protocol.md`](read-confirm-act-protocol.md) (the live-measurement-wins clause a briefing figure travels with)*
