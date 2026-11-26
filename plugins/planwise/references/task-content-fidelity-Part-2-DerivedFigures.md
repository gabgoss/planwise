---
description: Part 2 of 2 of the Required Context fidelity reference — derived figures in a task brief (§9.A.20 to §9.A.22). A corrected figure re-derives every rule that cites it, a split count is checked per row against its membership rule, and every count names its denominator. Part 1, task-content-fidelity.md, carries §9.A.1 to §9.A.19
consult-when: A brief's derived figures: corrected figure, split count, denominator
---

# Task Content Fidelity — Part 2: Derived Figures

**Purpose:** Three rules for figures a brief derives rather than measures directly: a count, a ratio or a split. A runner treats each figure in a brief as checked by the orchestrator. A wrong or conflicting figure makes the runner either follow a visibly false rule or own a design decision it was not given.

This file continues [task-content-fidelity.md](task-content-fidelity.md), which carries §9.A.1 to §9.A.19 and the Plan-Review Enforcement Summary. Section numbers run on from Part 1.

---

## 9.A Required Context Fidelity, Continued

The three rules below cover figures inside the brief's prose, steps and criteria. Part 1 covers the Required Context cells.

### 9.A.20 A corrected figure re-derives every rule, gate or prohibition that cites it

A rule in a brief often carries its reason as a figure. When a later edit corrects the figure, the reason can vanish while the rule stays true. A diligent runner re-measures, finds the stated reason gone, and drops the rule.

**The authoring test.** Before you change a figure, ask: does any rule, gate or prohibition in this document cite the figure being changed? For each one that does, re-derive its argument from the corrected figure. Then record one of two results beside the rule. Either the conclusion falls with the figure, or the conclusion still holds on other grounds, which you name.

A check that the arithmetic adds up passes a corrected figure. A check that the conclusion still follows from the corrected figure is a different check, and it is the one this rule requires.

**The measured case.** A brief required named-parameter binding for a MERGE. Its rationale read: "the row carries about 161 fields against 112 bound columns, so positional `asdict()` binding is forbidden." A measurement gave 110 fields against 110 binds. A runner that re-measured concluded the brief was stale and switched to `asdict(row).values()`. That was still wrong. Two columns are derived or renamed, so positional binding shifts every later value one column left, and the MERGE still succeeds.

> [!constraint] Supersede a wrong rationale explicitly when its conclusion still holds
> WRONG — the figure is corrected in place, and the rule loses its only visible reason:
> ```markdown
> Named binding is mandatory: the row carries 110 fields against 110 bound columns.
> ```
> CORRECT — the callout states that the rationale is wrong and names the grounds that keep the conclusion:
> ```markdown
> > [!binding] The rationale is WRONG, the conclusion still holds
> > Measured: 110 fields against 110 binds + 2 audit. The counts now MATCH. Do NOT conclude asdict() is viable.
> > `region_id <- int(row.region_code)` (derived) and `site_label <- row.site_default` (rename) break 1:1 mapping.
> > Named binding stays mandatory, on rename grounds.
> ```

#### Reviewer Check 140 — Conclusion Not Re-Derived From a Corrected Figure

- **Severity / Role / Type:** WARNING (ERROR when the rule whose reason fell guards a parameter binding, a schema decision or a destructive step) | Task Reviewer | NEW
- **What:** A brief corrects a figure that a rule, gate or prohibition cites, and nobody asked: does the conclusion still follow from the corrected figure?
- **Detection:**
  1. List each figure the brief marks as corrected, re-measured or superseded. For each, find every rule, gate or prohibition that cites it. Confirm the conclusion is re-derived, either withdrawn or kept by a superseding callout that names its new grounds (§9.A.20).
  2. For each split count, such as "14 fall through, 16 need an entry", apply the stated membership rule to each row of the table it summarises. A sum check alone is not detection (§9.A.21).
  3. For each count in the brief, confirm it names its denominator. Where two counts of the same thing differ, confirm the brief writes their relation inline (§9.A.22).
- **Finding template:**
```
[{WARNING|ERROR}] Derived figure in a brief not re-derived, checked per row, or given a denominator
File: {task file path} | Location: {section}, line {N}
Issue: {figure} was corrected and {rule} still cites the old reason | the split {a}/{b} reads {c}/{d} by its membership rule | {count} names no denominator and {other count} reads as a contradiction
Fix: Re-derive the conclusion and add a superseding callout | restate the split from a per-row application of its rule | name each denominator and write the relation inline | Confidence: MEDIUM
```

### 9.A.21 A split count is checked by applying its membership rule to each row

A brief can summarise a table with a split: so many rows fall in one class and the rest in the other. Both halves of a wrong split can still sum to the table's length, so a sum check passes. Check a split by applying the stated membership rule to each row and counting the result.

**The measured case.** A brief carried a 30-row mapping table and said "14 fall through to the default, 16 need an entry." Applying the stated rule to each row gave 15 and 15, because one row was an identity mapping. Review passed the brief, since 14 + 16 and 15 + 15 both sum to 30.

**Never satisfy the count with a no-op entry.** Adding an entry that maps a key to itself makes the stated 16 true. The next reader deletes the no-op and trips the criterion again. Assert the rule, not the length.

**A disagreement goes to the orchestrator before the code does.** A runner whose own derivation disagrees with a stated count surfaces both readings before it implements. The correction touches a success criterion, so the runner does not choose alone.

> [!constraint] Assert the membership rule, not the length of the list
> WRONG — the criterion pins the stated split, so a no-op entry is the cheapest pass:
> ```python
> assert len(_SELECT_EXPRESSIONS) == 16
> ```
> CORRECT — the criterion asserts the rule each entry must meet:
> ```python
> noop = {k: v for k, v in _SELECT_EXPRESSIONS.items() if v == f"b.{k}"}
> assert not noop, noop
> ```

### 9.A.22 Every count in a brief names its denominator

Two correct counts over different denominators read as a contradiction. A careful runner then reports a discrepancy that does not exist, or widens its own coverage to be safe. The failure grows with the runner's diligence.

**The measured case.** One flag said "18 NULL", meaning 18 of the 30 repaired columns. Another section listed 19 NULL columns, meaning 19 of all columns on the table. The runner reported that the two "disagree by one column" and widened its coverage. The true relation was 19 = 7 + 12. The phantom finding would have reached the census and the signoff.

Four obligations follow:

- **Name the denominator with every count.** Write "18 of the 30 repaired columns", never "18".
- **Reconcile related counts at scaffold time, and write the relation inline.** Where two counts of one property cover different sets, state how they join, such as "19 = 7 + 12".
- **The orchestrator recomputes a reported discrepancy before it consumes it.** A runner's "these disagree" is a claim to re-derive, not a finding to act on.
- **Route the resolution downstream.** Write the reconciled relation into the next session's brief, so that session does not re-derive it.

> [!constraint] A count carries its denominator, and two related counts carry their relation
> WRONG — two bare counts in one brief, each true over its own set:
> ```markdown
> Flag: 18 NULL.
> Columns to cover: 19 NULL columns (listed below).
> ```
> CORRECT — each count names its set, and the brief states how they join:
> ```markdown
> Flag: 18 of the 30 repaired columns are NULL.
> Columns to cover: 19 of all columns on the table are NULL (19 = 7 + 12; see the list below).
> ```

---

## Cross-References

Each rule below sits beside the three rules of this file. Each line says what that rule does not cover.

- [task-content-fidelity.md](task-content-fidelity.md) §9.A.9 re-derives a single count that summarises a list. It does not cover a split count whose halves sum correctly, which §9.A.21 covers.
- [scaffolding-hygiene.md](scaffolding-hygiene.md) §12.7 checks a caption that counts a table before the caption is carried forward. It does not cover a corrected figure that a rule cites, or two counts over different denominators.
- [measure-aggregate-provenance.md](measure-aggregate-provenance.md) §2 states the denominator with a number in a report. It does not cover a count briefed to a runner, or the scaffold-time reconciliation of related counts.
- [measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8, sub-rule G, puts a retraction inline at every citation of a retracted finding. It does not cover a figure that is corrected while the rule citing it stays true.

---

*Companion files: [task-content-fidelity.md](task-content-fidelity.md) (Part 1, §9.A.1 to §9.A.19 and the Plan-Review Enforcement Summary), [verify-before-cite.md](verify-before-cite.md) (§9.B Verify-Before-Cite).*
