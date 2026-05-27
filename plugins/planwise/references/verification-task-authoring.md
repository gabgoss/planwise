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
- [6. Orchestrator Adjudication of BLOCKER-From-Heuristic](#6-orchestrator-adjudication-of-blocker-from-heuristic)
- [7. Authoring Checklist](#7-authoring-checklist)

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

---

## 7. Authoring Checklist

> [!checklist] Verification-task spec — pre-publish checks
> - [ ] No anchored aggregate count threshold (`grep -cE '^…' … expect ≥N`) used as the sole pass/fail gate — replace with per-unit existence assertions (§2).
> - [ ] Match patterns cross-read against every sibling extraction task's output formats; format union documented in Required Context (§3).
> - [ ] Coverage denominators scope-restricted to real construct instances; prose, table rows, and fenced code excluded — OR check re-classified as `INVESTIGATE` (§4).
> - [ ] Verdict-arithmetic contract honored: if Actual contradicts Expected per the comparison operator, the verdict is FAIL or `[UNCERTAIN]`, never PASS (§5).
> - [ ] BLOCKER-from-heuristic adjudication protocol declared in the orchestration — orchestrator validates flagged sites against source before routing rework (§6).

---

*Cross-references: [verification-gates.md](verification-gates.md) (cross-process runtime gates — orthogonal concern: round-trip evidence at session-COMPLETE, not match-pattern authoring), [ei-fidelity.md](ei-fidelity.md) §9 (EI completeness and audit-grep-table coverage — feeds the format enumeration §3 relies on).*
