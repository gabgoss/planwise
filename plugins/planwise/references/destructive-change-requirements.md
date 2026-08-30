---
description: Destructive-path and config-gated change requirements — interaction-matrix spec, independent test authorship, gated-branch pin discipline, and pre-commit adversarial review
---

# Destructive-Path and Config-Gated Change Requirements

**Purpose:** Requirements for any task that adds or extends a branch that can DELETE, OVERWRITE, MIGRATE, PRUNE, or SWEEP user data or user customizations.
**Extends session-plan-requirements.md §8; extracted to keep both comfortably within a single Read call.**

---

## 10. Destructive-Path & Config-Gated Change Requirements

*Applies to any task that adds or extends a branch which can DELETE, OVERWRITE, MIGRATE, PRUNE, or SWEEP user data or user customizations. For such code the ordinary per-task gates — lint clean, unit suite green, smoke passing, self-containment greps empty — certify nothing about the inputs and adjacent states nobody named. These four requirements are a chain, not duplicates: §10.1 makes the spec cover the whole interaction matrix; §10.2 has an independent test task re-derive the contract; §10.3 pins the gated branch without disturbing default-path evidence; §10.4 backstops all three with an adversarial review before the commit.*

### 10.1 Enumerate the config-interaction matrix in the spec

> [!constraint] For any change that can DELETE user data, the spec enumerates the interaction matrix and assigns every cell an outcome — it does not transcribe the directive
>
> WRONG — the spec treats the failure modes the directive happened to name as the whole safety surface:
> "the user listed transfer-failure and backup-failure, so those are the safety cases."
>
> CORRECT — the spec decides every combination the target code region can produce:
> "the user listed two cases; the code region has four gates; the spec decides all combinations and says which the user's ruling covers."
>
> Four-step method:
> 1. **Enumerate at spec time.** Grep the target region for every config gate, opt-out, and degraded/fallback state that already influences the sibling branches (e.g. `get_upgrade_config()` keys, `not_analyzed`-style verdict stand-ins, absent-key fallbacks). Each one × the new behavior = a cell the spec must decide: proceed, preserve, or report.
> 2. **Precedence rule of thumb.** An existing protective opt-out must bind the NEW destructive branch at least as strongly as it binds existing branches — a more-customized file must never get weaker protection than a less-customized one. Any cell where the new branch is more aggressive than a sibling is a spec bug until explicitly ruled otherwise.
> 3. **Tests mirror the matrix, not the directive.** The regression class should have one case per cell, including the adjacent-gate cells — not just the failure modes the directive happened to name.
> 4. **Guard the mid-session path.** A spec authored from a chat directive under time pressure is exactly where adjacent-gate enumeration gets skipped. Make the grep-for-gates step mandatory before the spec is dispatched.

#### Reviewer Check 072 — Destructive-Path Spec Missing Interaction Matrix

- **Severity / Role / Type:** ERROR | Plan/Task Reviewer | NEW
- **What:** A task that adds or extends a branch which can DELETE, OVERWRITE, or MIGRATE user data MUST have a spec section enumerating the config-gate / opt-out / degraded-state interaction matrix, with a decided outcome per cell (proceed / preserve / report). A spec that names ONLY the failure modes the directive happened to mention, when the target code region has additional gates the sibling branches honor, is an ERROR — an adjacent opt-out the new destructive branch fails to consult is the likeliest silent-loss vector (a more-customized file getting weaker protection than a less-customized one).
- **Detection:**
  1. Identify tasks whose Objective / Execution Steps add or widen a delete/overwrite/migrate/prune/sweep branch.
  2. For each, check the task spec (or its Execution Input section) for an enumeration of the target region's config gates / opt-outs / degraded states with a per-cell outcome. Absence, or coverage of only the directive-named failure modes → ERROR.
  3. Apply the precedence rule: any cell where the new destructive branch is more aggressive than a sibling preserve/skip branch, without an explicit ruling, is a spec bug.
- **Finding template:**
```
[ERROR] Destructive-path spec missing config-interaction matrix
File: {task file path} | Location: spec / Execution Steps
Issue: Spec covers only directive-named failure modes; target region has additional gates ({list}) with no decided outcome — adjacent-opt-out silent-loss risk
Fix: Enumerate every config gate/opt-out/degraded state × the new behavior, decide each cell (proceed/preserve/report), and mirror the matrix in tests per references/destructive-change-requirements.md §10.1 | Confidence: HIGH
```

### 10.2 Schedule tests as an independent same-sprint task with a surface-don't-patch brief

> [!constraint] For a new primitive/module with a written contract, schedule its test suite as its own same-sprint task (fresh runner context, spec-first), before any consumer sprint wires it in
>
> Two disciplines make a spec-vs-implementation divergence productive instead of destabilizing:
> 1. **Independent test authorship in the same sprint.** A separate task (fresh context, spec-first reading) writing tests against the shipped artifact is a cheap adversarial re-derivation of the contract. Same-author self-verification tends to inherit the implementation's reading of the spec, so it misses the alternate readings the spec actually permits.
> 2. **"Surface, don't silently patch" in the test task's brief.** The test task is forbidden from editing the artifact under test (unless the fix is trivially correct and noted). A spec-vs-impl discrepancy therefore becomes a Recovery Issue + Cross-Task Coordination Flag routed to the consumer sprint, instead of the test author quietly changing the primitive or the assertion to force green — which would destroy the signal.
>
> **Route by failure direction, and classify before deferring:** a conservative divergence (the implementation over-preserves relative to the spec) → coordination flag to the consumer sprint, safe to defer; a divergence in the deleting direction (the implementation removes what the spec would keep) → blocker in-sprint.

### 10.3 Non-default-gated changes add gated-branch pins; keep absent-key pins as default-path evidence

> [!constraint] When new behavior is gated on a non-default config value and the default/absent-key path is deliberately unchanged, budget a NEW pinned test class — never a rewrite of the absent-key pins
>
> - Existing absent-key pins keep passing **by construction** — do not budget task scope to rewrite them. Budget a new pinned test class that sets the gating value explicitly and covers the gated branch plus its failure paths.
> - **Invert the signal.** If an existing absent-key pin DOES break during such a change, that is not "expected pin churn" — it means the default path changed, a spec violation to investigate, not an assertion to update.
> - At plan/spec time, phrase the requirement as "verify existing pins still pass unchanged (default path untouched) + add gated-branch pins," never "update the pinning tests" — the latter invites a runner to modify load-bearing default-path evidence.
>
> For review synthesis: a diff that rewrites absent-key pin assertions during a non-default-gated change is a red flag, not diligence.

#### Reviewer Check 073 — Absent-Key Pin Rewrite During Non-Default-Gated Change

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** When a task's spec gates new behavior on a NON-default config value AND deliberately keeps the default/absent-key path unchanged, the test plan MUST add a new gated-branch pin class — NOT rewrite existing absent-key pin assertions. A task plan that budgets "update the pinning tests" (rather than "verify existing pins still pass unchanged + add gated-branch pins") is a red flag: absent-key pins are load-bearing evidence of default-path stability, and rewriting them during a change that keeps the default path fixed hides a possible default-path regression.
- **Detection:**
  1. Identify tasks whose spec gates new behavior on a non-default config value while stating the default/absent-key path is unchanged.
  2. Inspect the task's test plan / Success Criteria. If it directs rewriting existing absent-key pin assertions rather than adding a new pinned class that sets the gating value → WARNING.
  3. Invert the signal: if the plan expects existing absent-key pins to break, flag it — a broken absent-key pin means the default path changed (a spec violation to investigate), not routine pin churn.
- **Finding template:**
```
[WARNING] Absent-key pins rewritten during non-default-gated change
File: {task file path} | Location: test plan / Success Criteria
Issue: Spec keeps default path fixed but plan rewrites absent-key pin assertions instead of adding a gated-branch pin class — default-path evidence disturbed
Fix: Phrase as "verify existing pins still pass unchanged (default path untouched) + add gated-branch pins"; investigate any absent-key pin that breaks as a default-path regression | Confidence: MEDIUM
```

### 10.4 A green suite is not a review: pre-commit adversarial review for destructive diffs

> [!constraint] For any diff that adds or widens a destructive disposition (delete / overwrite / migrate), run an adversarial multi-agent review BEFORE the commit, then fix-and-regression-test in the same session
>
> WRONG — treat per-task verification (lint + suite green + smoke) as sufficient to commit a new destructive path.
>
> CORRECT — run the adversarial review pre-commit; a fresh feature's tests are written by the same mind that wrote its bugs, so a green suite says nothing about the inputs nobody imagined (BOMs, block-style YAML, non-dict JSON cache entries, retry-after-crash staleness, filename collisions).
>
> "Run script verification" and "run code review" are DIFFERENT gates; the second is mandatory when the diff touches destructive dispositions, even when the first is fully green.

---

*Anchor: [session-plan-requirements.md](session-plan-requirements.md) §8 Required Files Per Level, Execution Strategy (the DELEGATED-trigger canonical). Companion: [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md).*
