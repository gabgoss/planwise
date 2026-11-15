---
description: Bind an instrument to the event it measures, not to the plan's shape. Covers why a re-measure scheduled as "the last sprint, after the install" opens an empty window by construction, why n = 0 is a data gap that licenses nothing in either direction, why a cumulative "stop when spend approaches N" guard runs only between calls and cannot catch an overrun inside the first one, and why a failed probe must never be priced at zero on an agentic harness. Consult when scheduling a did-the-figure-fall re-measure, writing a plan's success criteria for one, or dispatching a probe under a budget guard.
consult-when: Scheduling a did-the-figure-fall re-measure, writing its success criteria, reporting an empty sample, or dispatching a probe under a budget guard — bind the window to a traffic precondition, treat n = 0 as a data gap, put the ceiling on the single call, never price a failed probe at zero
paths: {planwise_root}/{plans_dir}/**
---
# Instrument Placement — The Control Was Well-Designed, Correctly Worded, and Structurally Incapable of Firing

**Purpose:** Bind an instrument to the event it measures, not to the plan's shape. An instrument placed where it cannot observe its event fails quietly. It returns a reassuring empty result, or no signal at all.

**Read this when** you are scheduling a re-measure whose headline is "the figure fell", writing the success criteria that will judge it, reporting a measurement whose sample came back empty, or dispatching a probe whose cost is bounded by a budget guard in the task file.

The shared defect is that **the instrument was bound to the plan's structure rather than to the event's**. A re-measure scheduled as "the last sprint, after the install" opens its window at the newest event in the repository, so the window starts empty by construction. A budget guard worded as "stop when cumulative spend approaches N" can only be evaluated between units of work. An overrun inside the first unit happens before any evaluation point exists.

Two neighbouring rules own adjacent halves. [`dispatch-preflight-claim-expiry.md`](dispatch-preflight-claim-expiry.md) §6 requires a re-measure *instruction* to carry a threshold and a divergence action. §1 below is about *when* that instruction is scheduled to run. [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.3 states that a null result deserves more scrutiny than a positive one. §2 below is the case where the null result is an empty sample rather than an unchanged reading.

## Table of Contents

- [1. Schedule a Measurement Against a Traffic Precondition, Not Against Plan Position](#1-schedule-a-measurement-against-a-traffic-precondition-not-against-plan-position)
- [2. n = 0 Is a Data Gap, Not a Null Result](#2-n--0-is-a-data-gap-not-a-null-result)
- [3. Bound the Single Call, Not the Running Total](#3-bound-the-single-call-not-the-running-total)
- [4. Never Assume a Failed Probe Was a Cheap Probe](#4-never-assume-a-failed-probe-was-a-cheap-probe)

---

## 1. Schedule a Measurement Against a Traffic Precondition, Not Against Plan Position

> [!constraint] "Last sprint, after the install" and "the first window containing organic samples of the measured class" are not merely different — the first actively guarantees the failure
> The install is by construction the newest event in the repository, so a window opening at the install starts empty. The only traffic reliably inside it is the measuring session's own, which is precisely the traffic that must be excluded. A faultless method cannot rescue that window. Selftest first, attribution from spawn records, deny pairing on `is_error` plus the deny-record shape, both window endpoints declared, self-contamination quantified: the measurement still returns nothing.
>
> WRONG — the re-measure is scheduled by plan position, and the window holds only the measurer's own traffic:
> ```
> re-measure: the plan's final sprint, immediately after the install sprint
> window: install-commit → now (17 min)
> in-window shell calls: 25, of which 23 are the measuring session's own
> reviewer dispatches in-window: 0
> ```
> CORRECT — the re-measure is bound to a traffic precondition, and the result criterion carries an owner:
> ```
> re-measure: the first window containing organic samples of the measured class
> precondition: non-self samples of the measured class, n > 0, asserted before measuring
> result criterion: the headline figure, with a named owner; deferred past plan close if the traffic has not arrived
> ```
>
> **The exclusion step is the tell.** When self-contamination exclusion removes nearly the entire sample — "23 of 25 excluded, 0 remain" — the window is the defect, not the exclusion. The measurement was scheduled inside its own instrument's shadow.
>
> **Separate the method criterion from the result criterion in the plan's own success criteria.** A method criterion ("figures reported with windows, surfaces, and the corrected pairing method; deltas stated against the baselines") is satisfied completely by an empty window, and correctly so. A plan stating only the method criterion **can close having never obtained its headline number, with nothing recording that the number is still owed.** Write both, and let the result criterion carry the owner. Be willing to defer the re-measure past plan close with a named owner.

The result criterion is not free: it can leave a plan formally open past its last sprint. That is the intended outcome. A plan that closes without its headline number has not succeeded quietly. It has lost the number.

---

## 2. n = 0 Is a Data Gap, Not a Null Result

> [!constraint] Only the first two rows are results
> | Outcome | Shape | What it licenses |
> |---|---|---|
> | **Measured fall** | n > 0, figure below baseline | The success claim, bounded by n |
> | **Measured non-fall** | n > 0, figure at or above baseline | A negative finding — real, and useful |
> | **Data gap** | **n = 0** | **Nothing.** No delta is computable in either direction |
>
> The failure mode is collapsing the third row into the second. *"The figure did not rise"* reads as a reassuring negative result and is unsupported when the denominator is zero — **it claims a measurement that was never performed.** Collapsing it into the first row is worse and rarer, because it is obvious.
>
> WRONG — the window is declared, the exclusions are honest, and the conclusion silently rests on an empty set:
> ```
> window: install-commit → now (17 min)
> self-contamination: 23 of 25 calls excluded
> reviewer Bash traffic in-window: 0
> → "consistent with the control working"          ← measures nothing
> ```
> CORRECT — assert the precondition, and when it fails, say so and name an owner:
> ```
> window: install-commit → now (17 min)
> non-self samples of the measured class: n = 0
> → DATA GAP. No delta computable against the 218 floor in either direction.
>   Owner: re-run this instrument against the first real reviewer dispatch
>   after the release that ships this tree.
> ```
>
> **The same window that cannot show a fall also cannot show a regression.** An empty result is symmetric and therefore inert. It must never be counted toward either side of a verdict.
>
> **Gate the delta on sample count, and state n on every figure.**

§1 and §2 are one instrument seen from two ends: §1 is where the window was placed, §2 is what the empty window is allowed to mean. [`measure-scope-and-sample.md`](measure-scope-and-sample.md) §1 carries the general form of stating n beside a figure. This section is the degenerate case where n is zero.

---

## 3. Bound the Single Call, Not the Running Total

> [!constraint] A guard that only runs after the damage is a report, not a guard
> A cumulative guard can only be evaluated *between* calls, so an overrun inside the first call happens before any stop-point exists. The failure may also give no in-flight signal: a costly malformed probe can reply with a short non-answer that looks like the cheap silent pass. **A campaign-level budget is a planning figure; it is not a control. The control has to sit where the spend is incurred.**
>
> WRONG — a running-total guard, first evaluable only after probe #1 has overrun:
> ```
> Budget guard: if cumulative probe spend approaches ~100K tokens (sum the probes' own JSONL usage), STOP probing.
> # 4 calls, 276,511 tokens: probe #1 alone spent 222,447 before the guard could first be tested
> ```
> CORRECT — a per-call ceiling shown to bind, and the cost read after the first probe:
> ```
> per-probe ceiling: a turn cap, a spend cap, or a wrapper that kills the child past N turns or M seconds
> proof: one malformed probe with the ceiling and the same probe without it terminate differently
> check: read probe #1's cost before dispatching the rest
> ```
>
> Two remedies:
>
> - **Give every probe a per-call ceiling**, so that a probe *supposed* to be one turn is structurally unable to become eight. **Then verify, on the harness version in use, that the ceiling binds:** run one malformed probe under the ceiling and the same probe without it, and confirm the two terminate differently. A flag the harness accepts without error is not thereby a flag it honours. Grade whether the ceiling fired on the child's **stop reason** (the `result` event's subtype), not on its reported turn count. A turn cap counts API round-trips, and one round-trip may carry several parallel tool calls, so the reported count can exceed a cap that did bind. A spend cap stops after the call that crosses it, so budget the overshoot as one call's cost.
> - **Measure after probe #1, not after the batch.** The cheapest moment to discover a wrong cost model is immediately after the first observation, while every remaining decision is still open. A cumulative check defers that discovery to a point where it can only be reported.

The same shape one layer down — a guard placed where the work is *represented* rather than where the cost is *incurred*, such as a skip inside a test body that cannot prevent work its fixture setup already did — is the layer argument this section applies to probe budgets. Put the control at the layer that spends.

---

## 4. Never Assume a Failed Probe Was a Cheap Probe

> [!constraint] "It failed, so it cost nothing" is an assumption about the harness's failure mode, not an observation
> **On an agentic harness, a malformed input is an invitation to explore, not a hard stop.** Verify the cost of the failure path once, then budget it. When inheriting a cost model from prior art, re-derive the conclusion, not just the number. A cost model carries the configuration it was measured under. State that configuration beside the figure, and treat a configuration change as invalidating the figure.
>
> WRONG — the failure path is priced from an inherited cost model, measured under another configuration:
> ```
> failed probe (mangled path): "silent pass, one wasted call" → priced at 0
> ```
> CORRECT — the failure path is measured once under the configuration in use, and the configuration is stated beside the figure:
> ```
> failed probe (mangled path), Auto Mode with bashFirst: true (from the transcript's attachment records):
>   8 turns of real tool calls exploring the path, 222,447 tokens → budget it
>   inherited "one wasted call" model: low by more than two orders of magnitude
> ```

§3 and §4 stay separate because §3 corrects a *placement* and §4 corrects an *inherited belief*. A reader who fixes the placement and keeps pricing failed probes at zero will set the per-call ceiling from the wrong cost model.

---

*Cross-reference: [`dispatch-preflight-claim-expiry.md`](dispatch-preflight-claim-expiry.md) §6 (a re-measure instruction needs a threshold and a divergence action) · [`exit-criteria-fidelity.md`](exit-criteria-fidelity.md) §16.10.3 (a null result deserves more scrutiny than a positive one) · [`measure-scope-and-sample.md`](measure-scope-and-sample.md) §1 (state n beside every figure) · [`measure-from-the-record.md`](measure-from-the-record.md) §3 (the `is_error`-plus-deny-record pairing §1's method list names)*
