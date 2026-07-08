---
description: Project motto — favor the coherent, complete treatment over the easy partial one, at every workflow stage
---

# Do the Hard Things

> [!binding] The Motto
> When two treatments of the same problem differ in completeness, favor the complete one and cost it honestly. Overall project quality comes from doing the hard thing once, not the easy thing twice.

## The Principle

Every workflow stage eventually faces the same fork: a **complete treatment** that touches more surface (a full renumber, a schema migration, propagating a change through every consumer, rewriting the tests that pinned the old behavior) versus a **narrower patch** that is cheaper to execute and leaves known incoherence behind (an annotation instead of a fix, a shim instead of a migration, a "known issue" note instead of a resolution).

Effort is not a tiebreaker. Diff size, ripple through dependent files, renumbering churn, or test-rewrite volume is never by itself a reason to choose the partial path — dependent references are exactly what reconciliation steps exist to update, and pinned tests are updated in the same change that changes the behavior.

## The Exception Clause (real constraints only)

The partial path is legitimate ONLY when a real constraint forces it:

- an interface external consumers already depend on,
- an irreversible boundary (data already migrated, a version already shipped),
- an explicit user-set deadline or budget the user has confirmed.

When a constraint forces the partial path, record BOTH the constraint AND the residual defect where the next reader will look (plan, recovery, summary, or code comment) — the gap must be a visible decision, not an accident.

## Stage Applications

| Stage | The easy thing | The hard (right) thing |
|-------|----------------|------------------------|
| Planning (`/planwise plan`) | Shrink scope to what fits the budget | Scope the complete treatment; SPLIT it across tasks/sessions to fit the budget |
| Execution (`/planwise run`) | Label the low-churn option "(Recommended)" | Recommend the coherent option; churn is not a cost argument |
| Review (`/planwise review`) | Downgrade a finding because the fix is large | Rate severity by impact; fix size never discounts severity |
| Backlog (`/planwise backlog`) | Route to a quick patch because a session feels heavy | Route by what the defect needs; a session-sized fix gets a session |
| Upgrade / doctor | Sidestep a structural conflict with a sidecar note | Resolve the divergence through the documented flow |

> [!constraint] Effort Is Not a Tiebreaker
> WRONG — the partial option is recommended because the complete one "ripples":
> ```
> Option A (complete renumber): touches the ToC, 12 cross-references, and 3 dependent docs
> Option B (annotation): one line
> Recommendation: B — A churns too many files            ← churn is the ONLY argument given
> ```
> CORRECT — the complete option is recommended; only a real, named constraint flips it:
> ```
> Option A (complete renumber): touches the ToC, 12 cross-references, and 3 dependent docs — (Recommended)
> Option B (annotation): one line; leaves the numbering incoherent for every future reader
> Recommendation: A. (B only under a named constraint — e.g. an external consumer pins the
>                 current anchors; if B is chosen, the residual defect is recorded in the plan.)
> ```

The user still chooses. This motto governs which option a handler endorses and how honestly the alternatives are framed.
