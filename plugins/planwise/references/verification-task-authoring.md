---
description: Verification-task match-pattern authoring discipline — per-unit existence assertions over aggregate counts, format-cross-reading from sibling extraction tasks, denominator scoping, PASS/FAIL contract, orchestrator adjudication of BLOCKER-from-heuristic
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Task Authoring (Match-Pattern Discipline)

**Purpose:** Rules for authoring `/planwise` verification tasks whose body is a grep/awk pattern plus a pass/fail criterion. Codifies the four recurring anti-patterns that produce false-PASS or false-BLOCKER verdicts requiring orchestrator hand-reconciliation: structurally unreachable count thresholds, keyword-proximity heuristics as pass/fail gates, denominators counting prose, and arithmetic-fudged PASS verdicts.

## Table of Contents

- [1. Failure Shape — Heuristic Verifiers Producing False Verdicts](#1-failure-shape--heuristic-verifiers-producing-false-verdicts)
- [2. Per-Unit Existence Assertions, Not Aggregate Count Thresholds](#2-per-unit-existence-assertions-not-aggregate-count-thresholds)
- [3. Match Patterns Derived From Sibling Extraction Tasks](#3-match-patterns-derived-from-sibling-extraction-tasks)
- [4. Denominator Scoping — Count Real Instances Only](#4-denominator-scoping--count-real-instances-only)
- [5. PASS Requires Actual = Expected — No Arithmetic Fudging](#5-pass-requires-actual--expected--no-arithmetic-fudging)
  - [5.1 A Check That Could Not Be Run Returns UNCERTAIN, Never PASS](#51-a-check-that-could-not-be-run-returns-uncertain-never-pass)
- [6. Orchestrator Adjudication of BLOCKER-From-Heuristic](#6-orchestrator-adjudication-of-blocker-from-heuristic)
- [7. Authoring Checklist](#7-authoring-checklist)
- [8. Absence and Consistency Gates — Scrub, Scope, and Sync](#8-absence-and-consistency-gates--scrub-scope-and-sync)
  - [8.1 An absence-grep requires scrubbing the token everywhere](#81-an-absence-grep-requires-scrubbing-the-token-everywhere)
  - [8.2 Assert against the right population](#82-assert-against-the-right-population)
  - [8.3 One file encoding a fact twice — every mutation updates both](#83-one-file-encoding-a-fact-twice--every-mutation-updates-both)
- [9. A bare heuristic in a task brief must state its exclusions](#9-a-bare-heuristic-in-a-task-brief-must-state-its-exclusions)

---

## 1. Failure Shape — Heuristic Verifiers Producing False Verdicts

Two recurring failure modes in verification-task specs share one root cause: a match pattern that *approximates* the intent is shipped as a pass/fail gate without checking it against the actual output formats the sibling extraction tasks produce.

| Anti-Pattern | Symptom | Cost |
|--------------|---------|------|
| Anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) | Verifier reports Actual<Expected yet marks PASS with arithmetic fudging, OR marks FAIL when source format produced fewer matchable instances than the threshold requires | Orchestrator hand-reconciles every flagged row; downstream tasks blocked or, worse, allowed to proceed on a fudged PASS |
| Keyword-proximity coverage gate (`grep -B1 keyword \| grep -c tag`) | Verifier reports `N/M` with `M` inflated by prose mentions, table headers, fenced pseudo-code; emits hard BLOCKER on zero genuine misses | Sibling tasks routed back for rework that is not needed; orchestrator must read source to adjudicate |

Both anti-patterns also share a secondary defect: when Actual contradicts Expected, the verifier either fudges to PASS or emits a hard BLOCKER instead of returning FAIL or `[UNCERTAIN]` for orchestrator adjudication. §2-§6 below state the binding rules that prevent each collapse.

---

## 2. Per-Unit Existence Assertions, Not Aggregate Count Thresholds

> [!constraint] Verification tasks MUST assert existence per unit, not aggregate counts over an anchored regex
> WRONG — a single anchored regex with a count threshold sweeps the file once and ships the count as the verdict. If the sibling extraction tasks produce more than one output format (line-start vs backtick-wrapped vs `{PLACEHOLDER}`-substituted), the threshold is structurally unreachable.
> ```bash
> grep -cE '^\[(BLOCKER|ERROR|WARNING|INFO)\]' {file}   # expect ≥{N}
> ```
> CORRECT — enumerate the units the verifier is checking, assert the property holds for each unit individually. The aggregate count, if needed, is *derived* from the per-unit results — not from a single regex sweep.
> ```bash
> # Per-unit: for each ### Check NNN block, assert it contains at least one
> # severity token in any accepted form (concrete word OR placeholder).
> awk '/^### Check [0-9]/{block=$0; next} /^---$/{ ... emit block + match check ... }'
> ```

A count-threshold whose target is structurally unreachable is a **spec bug**, not a verifier failure. The fix is to rewrite the verification step as a per-unit existence assertion, not to relax the threshold.

#### Reviewer Check 058 — Verification Task Anchored Aggregate Count Threshold

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A verification task MUST NOT ship an anchored aggregate count threshold (e.g., `grep -cE '^…' {file}` paired with `expect ≥N`) as its sole pass/fail gate. If sibling extraction tasks produce more than one output format for the measured construct, the threshold is structurally unreachable and the verifier will either FAIL incorrectly or fudge to PASS. Replace with per-unit existence assertions: enumerate the units the verifier is checking and assert the property holds per unit.
- **Detection:**
  1. For each task whose Objective contains verification-style language (`verify`, `count`, `coverage`, `expect ≥/≤`), open the Execution Steps and Verification Commands sections.
  2. Grep for the anchored-count pattern: a `grep -c…` or `grep -cE…` invocation paired with a comparator (`-ge`, `-le`, `≥`, `≤`) and a numeric threshold.
  3. Cross-read the sibling extraction tasks that write to the file the verifier scans; enumerate the output formats each produces.
  4. If ≥2 distinct formats exist AND the verifier's pattern is anchored (`^…` or a single format) → BLOCKER.
  5. If exactly 1 format exists AND the threshold is exactly equal to the produced count, also flag as WARNING (brittle to format drift).
- **Finding template:**
```
[BLOCKER] Verification task uses structurally unreachable anchored count threshold
File: {task file path} | Location: Verification Commands / Execution Steps
Issue: Verifier pattern `{anchored-grep}` paired with `expect {comparator}{N}`; sibling tasks produce {format_count} formats not all matched by the pattern
Fix: Replace with per-unit existence assertions per references/verification-task-authoring.md §2 (enumerate units, assert per unit, derive aggregate from per-unit results) | Confidence: HIGH
```

---

## 3. Match Patterns Derived From Sibling Extraction Tasks

> [!constraint] Verification match patterns MUST accept every output format the sibling extraction tasks actually produce
> A verification command's pattern is a contract with the sibling extraction tasks. Before authoring the pattern, cross-read every sibling task that writes to the file the verifier scans, and enumerate every format the source content can take:
>
> - line-start (`^[TAG]`)
> - backtick-wrapped mid-sentence (`` `[TAG] …` ``)
> - placeholder-substituted (`[{PLACEHOLDER}]`)
> - inline within a paragraph
>
> WRONG — author the verifier's regex against the format you happen to remember, ship without cross-reading. Whatever sibling task uses a different format silently fails the gate.
>
> CORRECT — the verifier's pattern accepts every enumerated format, OR the verification step is split per-format so each can be asserted independently.

> [!practice] Cross-read discipline
> When authoring a verification step that scans a file produced by N sibling tasks, the authoring sequence is:
>
> 1. Open every sibling task that appends content to the target file.
> 2. Enumerate the formats each produces (one row per format).
> 3. Design the verifier's pattern to match the union, OR design N per-format verifiers.
> 4. Document the format enumeration in the verification task's `## Required Context` so a reviewer can validate the union without re-deriving it.

---

## 4. Denominator Scoping — Count Real Instances Only

> [!constraint] A coverage check is only valid if its denominator counts real instances of the measured construct
> A coverage check has the shape `tagged / total ≥ threshold`. The denominator (`total`) MUST count actual occurrences of the thing being measured — NOT every line containing the keyword. Specifically exclude:
>
> - prose that *describes* the construct
> - table headers and column captions
> - fenced code blocks illustrating the construct
> - pseudo-code blocks naming the construct
>
> WRONG — denominator from a bare keyword grep:
> ```bash
> tagged=$(grep -B1 '{keyword}' {file} | grep -c '{tag}')
> total=$(grep -c '{keyword}' {file})            # inflated by prose & pseudo-code
> [ "$tagged" -ge "$total" ]                     # structurally guaranteed false negative
> ```
>
> CORRECT — denominator scoped to real call sites:
> ```bash
> # Match the construct's invocation pattern (e.g., tool-call shape, function-call shape),
> # exclude fenced code blocks (awk between ``` fences), exclude table rows (skip | columns).
> total=$(awk '!/^```/{...exclude fenced...} !/^\|/{...exclude tables...} /<invocation pattern>/' {file} | wc -l)
> ```
>
> If the denominator cannot be made precise (e.g., the construct's invocation shape varies and excluding prose is infeasible), the check is **NOT** a pass/fail gate. Re-classify it as an `INVESTIGATE` signal and surface the ambiguity to the orchestrator instead of emitting FAIL.

#### Reviewer Check 059 — Verification Task Keyword-Proximity Coverage Gate

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A verification task MUST NOT ship a keyword-proximity heuristic (e.g., `grep -B{N} keyword {file} | grep -c tag`) paired with a coverage-ratio denominator from a bare keyword grep (`grep -c keyword`) as its pass/fail gate. The denominator is inflated by prose, table headers, and fenced pseudo-code that mention the keyword without invoking the construct, and the proximity bound (`-B1`, `-A1`) misses correctly-tagged sites whose tag sits 2+ lines away. Replace with explicit-site enumeration: verify the spec's enumerated anchors are tagged, do not re-derive the site set from a keyword grep.
- **Detection:**
  1. Grep Verification Commands and Execution Steps for the proximity-gate shape: `grep -[BA]\d+ '{keyword}'` piped to `grep -c '{tag}'`, paired with a denominator `grep -c '{keyword}'` and a coverage comparator (`-ge`, `-eq`).
  2. If the bare denominator `grep -c '{keyword}'` is used AND the file under scan is a prose document (`.md`) — denominator includes prose / table rows / fenced code → BLOCKER.
  3. If the spec lists the explicit sites (e.g., an EI repoint map or an edit-group list) AND the verifier instead uses a keyword grep → BLOCKER (the spec's enumerated sites are the ground truth; verify them by anchor).
  4. Also flag: any verification step that maps `Actual<Expected` to BLOCKER directly without an `INVESTIGATE` escalation path → ERROR (denominator may be inflated; missing adjudication path forces false rework).
- **Finding template:**
```
[BLOCKER] Verification task uses keyword-proximity coverage gate with inflated denominator
File: {task file path} | Location: Verification Commands / Execution Steps
Issue: Verifier uses `grep -B{N} '{keyword}' | grep -c '{tag}'` over denominator `grep -c '{keyword}'`; denominator counts prose/table/fenced-code mentions, proximity bound misses tags ≥2 lines away
Fix: Replace with explicit-site enumeration per references/verification-task-authoring.md §4 (verify the spec's enumerated anchors by name, scope denominator to real construct instances, or re-classify as INVESTIGATE if denominator cannot be made precise) | Confidence: HIGH
```

---

## 5. PASS Requires Actual = Expected — No Arithmetic Fudging

> [!constraint] A verification subagent MUST NOT mark PASS when Actual contradicts Expected
> WRONG — verifier reports `Actual=44, Expected=≥54, Verdict=PASS` with a justification like "44 is ≥54." This is a contract violation. The orchestrator cannot trust any row in the verifier's report if arithmetic fudging is possible.
> ```markdown
> | Check | Actual | Expected | Verdict |
> |-------|--------|----------|---------|
> | … | 44 | ≥54 | PASS (44 is ≥54) |
> ```
> CORRECT — when Actual contradicts Expected, the verifier returns FAIL or `[UNCERTAIN]` for orchestrator adjudication. The verifier is not authorized to relax the threshold on its own.
> ```markdown
> | Check | Actual | Expected | Verdict |
> |-------|--------|----------|---------|
> | … | 44 | ≥54 | [UNCERTAIN] — Actual<Expected; possible structurally unreachable threshold (§2) or format enumeration gap (§3); escalating to orchestrator |
> ```

The verdict-arithmetic check is mechanical: if the comparison operator's evaluation against `(Actual, Expected)` returns false, the verdict cannot be PASS. A reviewer flagging this anti-pattern can grep the verifier's reported rows for `(Actual, Expected, Verdict)` triples where the arithmetic does not hold and flag every such row.

### 5.1 A Check That Could Not Be Run Returns UNCERTAIN, Never PASS

> [!constraint] A verifier reporting that a check could not be run MUST NOT return PASS or a bare narrative claim about the environment
> This is the adjacent case to arithmetic fudging above — not a check that ran and produced a contradicting Actual, but one that never ran at all. The verifier returns `[UNCERTAIN]` for orchestrator adjudication — never PASS, and never a bare narrative claim about the environment (e.g. "not available here," "the tool doesn't support it"). The report MUST carry the exact command attempted and the exact error observed; the orchestrator adjudicates from that evidence, not from a summary judgement.

---

## 6. Orchestrator Adjudication of BLOCKER-From-Heuristic

> [!constraint] When a verifier emits a BLOCKER from a heuristic (not from an explicit-site assertion), the orchestrator MUST adjudicate against source before routing rework
> A verifier's BLOCKER routes downstream tasks back for rework. If the BLOCKER originated from a heuristic that this rule's §2-§4 would flag (anchored count threshold, proximity heuristic, prose-inflated denominator), the orchestrator MUST cross-check the flagged sites against the actual source before sending the task back.
>
> WRONG — orchestrator forwards the BLOCKER directly to the implementing task author for rework. If the heuristic was wrong, the author rebuilds correct work to satisfy the false signal.
>
> CORRECT — orchestrator opens the flagged sites in source, applies the explicit-site assertion from §2 (the spec's enumerated sites are the ground truth), and either confirms the BLOCKER or rewrites the verification step to fix the heuristic. Only confirmed BLOCKERs route to rework.

> [!practice] Heuristic-BLOCKER triage
> The orchestrator's adjudication check at BLOCKER-receipt time:
>
> 1. Read the verifier's reported flagged sites.
> 2. For each site, open source at the cited line; classify as:
>    - **Genuine miss** — confirmed, route to rework.
>    - **Format gap** (§3) — the site IS tagged in a format the verifier's pattern did not match; rewrite the verification step's pattern, do NOT route to rework.
>    - **Denominator inflation** (§4) — the site is prose / table / fenced code, not a real call site; rewrite the denominator, do NOT route to rework.
> 3. If ≥1 site is a format gap or denominator inflation, the verification step is defective — block the task chain on fixing the verifier, not on rework.

#### Reviewer Check 060 — Verification Task Verdict-Arithmetic Contract

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** A verification task spec MUST require the verifier to return FAIL or `[UNCERTAIN]` when Actual contradicts Expected per the comparison operator — never PASS. The spec MUST also declare an orchestrator adjudication path for BLOCKER-from-heuristic findings (the orchestrator validates flagged sites against source before routing rework, per the rules above).
- **Detection:**
  1. Open Verification Commands and any output-template the verifier task instructs the subagent to emit (e.g., a results table with `Actual` / `Expected` / `Verdict` columns).
  2. If the template permits a PASS verdict on a row where the `Actual` value does not satisfy the `Expected` comparator → BLOCKER (verdict-arithmetic contract violation enabled).
  3. If the spec emits BLOCKER directly to downstream rework without an `INVESTIGATE` / orchestrator-adjudication branch → ERROR (denies the adjudication path required when a heuristic produces a false signal).
  4. If the spec contains language like "approximate", "close enough", or "within tolerance" without a numeric tolerance band → WARNING (arithmetic-fudging risk).
- **Finding template:**
```
[BLOCKER] Verification task spec permits PASS on contradicted comparator
File: {task file path} | Location: Verification Commands / output template
Issue: Spec permits Verdict=PASS when Actual does not satisfy Expected; orchestrator adjudication path for BLOCKER-from-heuristic not declared
Fix: Constrain verdict per references/verification-task-authoring.md §5 (FAIL or [UNCERTAIN] when Actual contradicts Expected) and §6 (orchestrator adjudicates BLOCKER-from-heuristic against source before routing rework) | Confidence: HIGH
```

---

## 7. Authoring Checklist

> [!checklist] Verification-task spec — pre-publish checks
> - [ ] No anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) used as the sole pass/fail gate — replace with per-unit existence assertions (§2).
> - [ ] Match patterns cross-read against every sibling extraction task's output formats; format union documented in Required Context (§3).
> - [ ] Coverage denominators scope-restricted to real construct instances; prose, table rows, and fenced code excluded — OR check re-classified as `INVESTIGATE` (§4).
> - [ ] Verdict-arithmetic contract honored: if Actual contradicts Expected per the comparison operator, the verdict is FAIL or `[UNCERTAIN]`, never PASS (§5).
> - [ ] BLOCKER-from-heuristic adjudication protocol declared in the orchestration — orchestrator validates flagged sites against source before routing rework (§6).

---

## 8. Absence and Consistency Gates — Scrub, Scope, and Sync

### 8.1 An absence-grep requires scrubbing the token everywhere

> [!constraint] An absence-grep criterion MUST scrub the literal token from every surface, not just data cells
> A criterion of the form `grep -c 'TOKEN' {file} == 0` proves absence of a TOKEN-class item. Satisfying it requires the literal token to appear nowhere — not merely absent from data cells. It must be scrubbed from the classification legend, count-block labels, section headers, descriptive prose, and any self-referential mention of the grep itself. Replace with a synonym. Grep is case-sensitive, so lowercase variants are safe; run the exact anchor command yourself before declaring the criterion met.
>
> Observed false-FAIL: the criterion's own grep returned 8 against a file with zero unresolved data cells — every hit was the legend, the label, and the criterion's own description.

### 8.2 Assert against the right population

> [!constraint] A consistency check MUST assert against the right population, not a conditional/optional set against an observed/union artifact
> A consistency check asserting a conditional/optional annotation set is a subset of an observed/union artifact encodes the wrong invariant — conditional annotations exist precisely to document things absent from the observed set. Assert "the root is a declared field" instead — skipping glob, brace, and condition-expression entries, failing only on an undeclared root. Scope comment-marker checks to comment-only lines so inline annotations are not matched.
>
> Observed false-FAIL: a `conditional ⊆ observed` assertion failed on 22 legitimate conditional fields.

### 8.3 One file encoding a fact twice — every mutation updates both

> [!constraint] When a file encodes one fact in two representations, every mutation MUST update both and verify against the file
> When a single file encodes the same fact in both a machine-checked form and a human-readable form, a passing gate only ever sees the form it parses. Every mutation MUST update every representation, and the change MUST then verify the written counts against the file.
>
> Observed false-PASS: a status flip updated the parsed code block to a new count but left the prose bullets, summary line, and callout's stated counts stale. The mechanical check stayed green while the document contradicted itself.

---

## 9. A bare heuristic in a task brief must state its exclusions

> [!constraint] A bare "condition X ⇒ defect" heuristic handed to a runner MUST state its exclusions in the same block
> A rule of the form "condition X ⇒ defect" is normally correct only after exclusions are applied. Stated bare in a task brief, it fires on every legitimately-excluded case, and each firing reads as a defect in work that is correct. When a brief hands a runner a rule of this shape, it MUST state, in the same block, the conditions under which X is expected and is **not** a bug.
>
> WRONG: "Any newly-wired column at 0 non-NULL is a wrong-key finding."
> CORRECT: "Any newly-wired column at 0 non-NULL is a wrong-key finding, EXCEPT where: the source is recorded absent in the reconciliation's evidence tier (expected NULL, not a failed fix); the value is conditional on state not present in the sampled window; the column is wired ahead of a producer that has not yet run. For each exclusion the runner cites the evidence row that establishes it."
>
> A runner who hits an excluded case with the bare rule in hand has three options, two of them bad: report a false defect, silently ignore the rule, or spend an investigation re-deriving the exclusion. Only the third is safe, and it is the most expensive.

**Applies to:** task briefs that hand a runner a bare "condition ⇒ defect" heuristic — distinct from §1's failure-shape table, which covers heuristic *verifiers* (structurally-unreachable count thresholds, keyword-proximity coverage gates) living inside verification commands. §9 covers a *correct* heuristic applied without its exclusions — a different failure shape, arising in task briefs rather than verification commands. This section reserves no further top-level number.

---

*Cross-references: [verification-gates.md](verification-gates.md) (cross-process runtime gates — orthogonal concern: round-trip evidence at session-COMPLETE, not match-pattern authoring), [ei-completeness.md](ei-completeness.md) §9 (EI completeness and audit-grep-table coverage — feeds the format enumeration §3 relies on).*
