---
description: Token Saver's config-gated carrying-cost budget system — two-tier policy, carrying-cost rationale, and threshold derivation
---

# Token Saver Profile

Active when `context.token_saver: true` — companion to `session-context-budget.md`.

This section activates when `context.token_saver: true` in `config.yaml`. It layers a carrying-cost budget on top of the tier budgets in [session-context-budget.md](session-context-budget.md) §5 and is keyed to the **measured** overheads captured by `/planwise calibrate` (the `token_saver.calibrate()` engine in `scripts/token_saver.py`). When `token_saver: false`, ignore this file and use the anchor's §5 tier budgets alone.

> [!constraint] Numbers Are Measured, Never Hardcoded
> Every threshold below is **derived** from `token_saver_runner_overhead` (and `token_saver_orchestrator_overhead`) — the overheads `/planwise calibrate` writes back into `config.yaml` from a real `/context` report. NEVER hardcode a runner overhead or a per-task ceiling in a plan: read the calibrated value and run the formulas. Until a live capture runs, the engine writes a conservative fallback (`runner_overhead ≈ 54,000`, `orchestrator_overhead ≈ 60,000`, flagged `uncalibrated`); a plan authored against the fallback is intentionally pessimistic and should be re-checked after calibration.

Read-tool mechanical limits (the byte gate and token page-cap gate) are FIXED harness facts, SEPARATE from this carrying-cost system — they are documented in the anchor's [Read-Tool Hard Limits](session-context-budget.md#read-tool-hard-limits) section and are not duplicated here.

## Token Saver Two-Tier Policy

Token Saver sizes work by **carrying cost**, not by "does it fit". `token_saver_session_target` (default 150,000) is a **per-dispatched-window budget** — the HARD ceiling a task-runner subagent is held to, minus that actor's measured overhead. It is **not** an orchestrator-session target: measured orchestrator windows run several times larger, and no lever this tool owns could hold one to that figure. The orchestrator side is governed instead by the **model floor** plus the measured session-length advisory in [Orchestrator-Window Expectation](#orchestrator-window-expectation) below.

| Actor | Target | Enforcement |
|-------|--------|-------------|
| Task-runner subagent — the dispatched window | **HARD ~150K per window** | `task_estimate + token_saver_runner_overhead ≤ token_saver_session_target`. The plan-time per-task ceiling is `available_per_task = token_saver_session_target − token_saver_runner_overhead − growth_margin` (the engine's `derive_thresholds`). A task projected above its `critical` threshold MUST be split or its Required Context trimmed. This side is **design-coherent, not measurement-confirmed**: the estimated per-window cost sits inside the target, but dispatched-subagent windows are not directly observed. |
| Orchestrator session | **No 150K target** — model floor + measured advisory | `token_saver_session_target` does not govern here. Enforcement is the **model floor**: escalate the dispatch or split the session when the projected window approaches the real ceiling of the model that session runs on (see [§ Subagent Context Window](session-context-budget.md#subagent-context-window)). Keep the DELEGATED Context Boundary (§1.3 of [agent-orchestration-delegated.md](agent-orchestration-delegated.md)) so the orchestrator reads only plan files, and surface the session-length advisory in [Orchestrator-Window Expectation](#orchestrator-window-expectation) when `context.token_saver_orchestrator_advisory` is `measured`. |

## Orchestrator-Window Expectation

The orchestrator's window is not held to `token_saver_session_target`. What replaces it is an **expectation band derived from measurement**, with the model floor as the only mechanism that actually enforces anything.

**Measured band** (n = 99 single-window main-session transcripts):

| Session class | Median peak | p90 peak |
|---------------|-------------|----------|
| All measured sessions | 363,620 | 565,189 |
| Dispatching (delegated) sessions | 455,119 | 586,726 |

94% of measured sessions ran above 150,000, every measured dispatching session did, and the dispatching class ran ≈1.68× the direct class's median. A session projected inside this band is normal, not a defect; one projected well above its p90 is worth splitting on iteration-quality grounds.

> [!constraint] The delegated-vs-direct figures are directional bounds, not point facts
> Session mode was classified by whether the transcript issued a dispatch call, so a session that only *continued* an already-dispatched agent classifies as direct. Delegated is therefore a **lower bound**: "every dispatching session exceeded the target" and the ≈1.68× ratio each state a direction, not a settled magnitude. Cite them as bounds wherever they are used as motivation.

**The driver is session length, not task count.** Peak window tracks turns plus the auto-injected rule surface (see [Injection Visibility](#injection-visibility) below); correlation with task count is weak. Splitting a session into more tasks does not lower its window — ending the session sooner does, and so does shrinking the injected surface.

**Enforcement is the model floor.** Project the session's window forward — it starts at the measured `token_saver_orchestrator_overhead` and grows with turns — then escalate the dispatch or split the session when that projection approaches the real ceiling of the model the session runs on: Haiku/Sonnet 200K, Opus 1M (see [§ Subagent Context Window](session-context-budget.md#subagent-context-window)). That ceiling is a mechanical limit, so it holds whether or not anyone is watching; the band above is planning context, not a split trigger.

**Reporting is config-gated.** `context.token_saver_orchestrator_advisory` (`measured` | `off`) controls whether the band is surfaced in reports. With `off`, the model floor still applies — it is a hard limit, not an advisory. Nothing here changes the dispatched window's HARD ceiling.

## Token Saver Carrying-Cost Rationale

A session's billed cost is not just its peak size — it is roughly `carried_context × 0.1 × turns`: every cached turn re-bills the carried context at the **cache-read rate (0.1× base input)**, so a large session pays its whole footprint again on every turn. Two practical consequences:

- **Size by `context × turns`, not by "does it fit".** A 180K session that technically fits the window still costs far more per turn than a lean 120K one — and it iterates worse (recovery, review, and re-reading all get harder). The 150K dispatched-window target is a *usage-pattern* ceiling that keeps per-turn carrying cost low, not a hard window limit; the same arithmetic is why a long orchestrator session is expensive even when it comfortably fits.
- **Cache writes cost more than reads.** Writing context into the cache bills **1.25× base input (5-minute TTL)** or **2× (1-hour TTL)**; subsequent reads are 0.1×. Front-load reads once (one cache write) rather than dribbling context in across turns (repeated writes).
- **No long-context premium on Opus 4.8.** Opus 4.8 bills its full 1M window at standard pricing — there is no surcharge past 200K. So **the 150K dispatched-window target is a usage-pattern choice, not a billing cliff**; the motivation is per-turn carrying cost and iteration quality, not a step in the price curve.

Operationally: `/clear` between sessions (drop the carried context entirely) and `/compact` at task boundaries within a session (shrink the carried context before the next turn re-bills it).

## Token Saver Threshold Derivation

Thresholds are computed by `token_saver.derive_thresholds(session_target, runner_overhead)` — never hardcoded:

```
available_per_task = token_saver_session_target − token_saver_runner_overhead − growth_margin(6000)
critical           = available_per_task − output_reserve(10000)
warn               = min(40000, round(0.5 × available_per_task))   # 40K = guaranteed-warn ceiling; lower on heavy installs
```

- `available_per_task` is the working budget a single runner has for its Required Context after subtracting the measured overhead and a 6,000-token growth margin.
- `critical` reserves 10,000 tokens for the runner's own output; a task estimated at or above `critical` overflows and MUST be split.
- `warn` is the lighter caution band: **40,000 is the guaranteed-warn ceiling** (every install warns by at least 40K), but on a heavy install where `0.5 × available_per_task < 40,000`, the lower derived value wins. A task at or above `warn` should be reviewed for trimming.

> [!constraint] Subagent Window = Dispatched MODEL, Not Parent Tier
> A Token Saver runner's window is set by the **model it runs on**, NOT the orchestrator's tier (see [§ Subagent Context Window](session-context-budget.md#subagent-context-window)): Haiku/Sonnet = **200K**, Opus = **1M**. The `~150K` Token Saver target is a carrying-cost ceiling that sits *below* even a Sonnet runner's 200K window — it is about per-turn cost and iteration quality, not about fitting the window. Do NOT raise the Token Saver target to a runner's window size; the target is deliberately tighter than the window.

## Injection Visibility

The thresholds above budget for a task's own Required Context; they do not by themselves surface a separate carrying cost — auto-injected path-scoped rule content. A `.claude/rules/**` file scoped to a plan/backlog/lessons glob is injected into every context that reads a matching path, including a DELEGATED task-runner subagent, and every rule sharing a glob co-injects together on a single path match. `handlers/doctor.md`'s over-scope linter makes this measurable: it reports each flagged rule's size, groups flagged rules into glob families, and flags any family whose worst-case injection exceeds the configurable `context.token_saver_injection_ceiling` (default 40000 tokens). Run `/planwise doctor` to check a project's rule surface before relying on the thresholds above.

---

*Anchor: [session-context-budget.md](session-context-budget.md) (Token Budget §5, and the Read-Tool Hard Limits / Large-File Read Tactics read-gate canonical). Companion: [context-loading-and-conservation.md](context-loading-and-conservation.md).*
