---
description: A verifier returns FAIL or [UNCERTAIN] when Actual contradicts Expected and never fudges a PASS (§5, Check 060), a check that could not be run returns UNCERTAIN with the exact command and error rather than a narrative claim (§5.1), and an orchestrator adjudicates a BLOCKER raised from a heuristic against source before routing rework (§6).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Verdict Contract and Orchestrator Adjudication

**Purpose:** Rules for what a verifier reports and what the orchestrator does with it. The match-pattern rules in `gate-heuristic-verifier-patterns.md` §1-§4 say how a heuristic goes wrong; this file says what the verdict must be when it does, and who checks it before work is sent back. Split from `verification-task-authoring.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-task-authoring.md §N` citation translates by filename alone. The family index is `verification-task-authoring.md`.

**Read this when** you write the output template of a verification task, a verifier reports Actual that contradicts Expected, or a BLOCKER arrives from a count, proximity or denominator heuristic and you are about to route rework.

## Table of Contents

- [5. PASS Requires Actual = Expected — No Arithmetic Fudging](#5-pass-requires-actual--expected--no-arithmetic-fudging)
  - [5.1 A Check That Could Not Be Run Returns UNCERTAIN, Never PASS](#51-a-check-that-could-not-be-run-returns-uncertain-never-pass)
- [6. Orchestrator Adjudication of BLOCKER-From-Heuristic](#6-orchestrator-adjudication-of-blocker-from-heuristic)

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
> | … | 44 | ≥54 | [UNCERTAIN] — Actual<Expected; possible structurally unreachable threshold (`gate-heuristic-verifier-patterns.md` §2) or format enumeration gap (§3 there); escalating to orchestrator |
> ```

The verdict-arithmetic check is mechanical: if the comparison operator's evaluation against `(Actual, Expected)` returns false, the verdict cannot be PASS. A reviewer flagging this anti-pattern can grep the verifier's reported rows for `(Actual, Expected, Verdict)` triples where the arithmetic does not hold and flag every such row.

### 5.1 A Check That Could Not Be Run Returns UNCERTAIN, Never PASS

> [!constraint] A verifier reporting that a check could not be run MUST NOT return PASS or a bare narrative claim about the environment
> This is the adjacent case to arithmetic fudging above — not a check that ran and produced a contradicting Actual, but one that never ran at all. The verifier returns `[UNCERTAIN]` for orchestrator adjudication — never PASS, and never a bare narrative claim about the environment (e.g. "not available here," "the tool doesn't support it"). The report MUST carry the exact command attempted and the exact error observed; the orchestrator adjudicates from that evidence, not from a summary judgement.

## 6. Orchestrator Adjudication of BLOCKER-From-Heuristic

> [!constraint] When a verifier emits a BLOCKER from a heuristic (not from an explicit-site assertion), the orchestrator MUST adjudicate against source before routing rework
> A verifier's BLOCKER routes downstream tasks back for rework. If the BLOCKER originated from a heuristic that `gate-heuristic-verifier-patterns.md` §2-§4 would flag (anchored count threshold, proximity heuristic, prose-inflated denominator), the orchestrator MUST cross-check the flagged sites against the actual source before sending the task back.
>
> WRONG — orchestrator forwards the BLOCKER directly to the implementing task author for rework. If the heuristic was wrong, the author rebuilds correct work to satisfy the false signal.
>
> CORRECT — orchestrator opens the flagged sites in source, applies the explicit-site assertion from `gate-heuristic-verifier-patterns.md` §2 (the spec's enumerated sites are the ground truth), and either confirms the BLOCKER or rewrites the verification step to fix the heuristic. Only confirmed BLOCKERs route to rework.

> [!practice] Heuristic-BLOCKER triage
> The orchestrator's adjudication check at BLOCKER-receipt time:
>
> 1. Read the verifier's reported flagged sites.
> 2. For each site, open source at the cited line; classify as:
>    - **Genuine miss** — confirmed, route to rework.
>    - **Format gap** (`gate-heuristic-verifier-patterns.md` §3) — the site IS tagged in a format the verifier's pattern did not match; rewrite the verification step's pattern, do NOT route to rework.
>    - **Denominator inflation** (`gate-heuristic-verifier-patterns.md` §4) — the site is prose / table / fenced code, not a real call site; rewrite the denominator, do NOT route to rework.
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
Fix: Constrain verdict per references/gate-verdict-contract-and-adjudication.md §5 (FAIL or [UNCERTAIN] when Actual contradicts Expected) and §6 (orchestrator adjudicates BLOCKER-from-heuristic against source before routing rework) | Confidence: HIGH
```

---

*Cross-references: [gate-heuristic-verifier-patterns.md](gate-heuristic-verifier-patterns.md) (§1-§4, the heuristic shapes §6's triage classifies) · [verification-task-authoring.md](verification-task-authoring.md) (the family index and the §7 authoring checklist).*
