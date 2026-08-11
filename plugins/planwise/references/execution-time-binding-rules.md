---
description: Execution-time binding rules — design-extension traceability with inline What/Why/Source documentation, cross-tier audit-finding triage into Remediation vs pre-emptive-flag buckets, the bounded-temp-fix that seeds a deferred Discovery, and spike-instrument synthetic-fixture verdict partitioning
---

# Execution-Time Binding Rules

**Purpose:** Binding rules covering plan-fidelity concerns that surface during execution rather than at Discovery or signoff time — design-extension traceability (§17), cross-tier audit-finding triage (§18), the bounded-temp-fix that seeds a deferred Discovery (§19), and spike-instrument verdict discipline (§20). Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same issues.

This file is the §17-§20 segment of a 3-way split of `discovery-and-exit-criteria.md` (the anchor, which keeps §15 and the shared 11-row Plan-Review Enforcement Summary — see the anchor for how each of that table's rows now resolves across the three files); §16 lives in [exit-criteria-fidelity.md](exit-criteria-fidelity.md). Extracted to keep all three files under the project's 500-line limit. Read it before authoring design-extension documentation, cross-tier audit triage, bug-fix sessions that surface a recurring defect class, or de-risk spikes that run on synthetic fixtures.

## Table of Contents

- [17. Design Extensions Introduced During Execution](#17-design-extensions-introduced-during-execution-binding)
- [18. Cross-Tier Audit-Finding Triage](#18-cross-tier-audit-finding-triage-binding)
- [19. Narrow Fix Reveals a Systemic Gap — Bounded Temp Fix That Seeds the Deferred Discovery](#19-narrow-fix-reveals-a-systemic-gap--bounded-temp-fix-that-seeds-the-deferred-discovery-binding)
- [20. Spike Instrument Verdict Discipline](#20-spike-instrument-verdict-discipline-binding)
  - [20.1 Synthetic-Fixture Verdict Partitioning](#201-synthetic-fixture-verdict-partitioning)

---

## 17. Design Extensions Introduced During Execution (BINDING)

Plan execution often introduces parameters, thresholds, or behaviors that do not appear in the original design spec (the Discovery output, Execution Input, or equivalent). Without traceable documentation, a future reviewer cannot determine whether such a parameter was deliberate, inherited, or arbitrary.

> [!constraint] Design extensions introduced during execution MUST be documented inline + back-referenced to the project's config catalog
> When plan execution introduces parameters or behaviors NOT present in the
> original design spec (Consolidated Context, EI, or equivalent), those design
> extensions MUST carry three fields at their first declaration site:
>
> - **What** — the parameter / behavior and its value.
> - **Why** — the rationale (domain reason, calibration result, planning decision).
> - **Source** — where the value came from (research paper, domain knowledge, calibration run, planning decision).
>
> WRONG — new parameter appears in a task file + downstream consumer with no origin:
> ```
> SOME_THRESHOLD: float = 0.75   # no comment
> ```
> A reviewer cannot determine whether this is deliberate, inherited, or arbitrary.
>
> CORRECT — design extension documented inline with a What/Why/Source comment + back-reference:
> ```
> # Design extension (not in original design spec):
> # WHAT:   SOME_THRESHOLD = 0.75 — partial-credit scoring threshold
> # WHY:    Domain rules give partial weight when condition X holds; full credit
> #         only under condition Y. 0.75 reflects the partial-credit ratio agreed
> #         in {decision document}.
> # SOURCE: Planning decision (sprint-{NN} signoff); no original-spec citation
> #         exists. Backlog item: BLI-NNN.
> ```
>
> **Back-reference requirement:** new configurable parameters MUST be added to the
> project's config catalog (the equivalent of the project's CLAUDE.md
> "Configuration" section, or whatever design-spec catalog the plan inherited
> from) so future reviewers can trace every parameter to either:
> - (a) the original spec, OR
> - (b) a documented extension.
>
> Inline-comment-only documentation is not sufficient — config-catalog drift would silently rebuild the same problem.

> [!checklist] Design-Extension Authoring (Per Sprint Closeout)
> - [ ] Identified every parameter or threshold introduced this sprint that does NOT appear in the original design spec
> - [ ] Each new parameter has an inline What/Why/Source comment at its first declaration site
> - [ ] Each new parameter is added to the project's config catalog
> - [ ] Each new parameter is mentioned in the sprint signoff under a "Design Extensions" sub-section (per [exit-criteria-fidelity.md](exit-criteria-fidelity.md#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row) §16.3's verbatim-quote conventions)

#### Reviewer Check 051 — Undocumented Design Extension

- **Severity / Role:** WARNING | Design-Extension Reviewer | NEW
- **Detection:** Grep execution-time files for design extensions (new sections / new callouts) not documented in EI or source spec. Undocumented → WARNING.
- **Finding template:** `[WARNING] Undocumented design extension during execution | Fix per references/execution-time-binding-rules.md §17 (inline What/Why/Source comment)`

---

## 18. Cross-Tier Audit-Finding Triage (BINDING)

A cross-tier audit with a Discovery → Audit gap longer than one sprint produces HIGH-severity findings in two categories: findings on items whose downstream artifacts already exist in deployed code, and findings on items whose downstream artifacts are still un-authored in future sprints. A naïve "bundle every finding into one Remediation sprint" plan double-handles the second category.

> [!constraint] Cross-tier audit findings on un-authored downstream artifacts MUST be pre-emptively flagged in the Findings doc, NOT bundled into a separate remediation sprint
> Failure mode: the naïve plan for a cross-tier audit's HIGH findings is "bundle
> all findings into Sprint-N Remediation." This works for findings on items whose
> downstream artifacts already exist in deployed code, but DOUBLE-HANDLES findings
> on items whose downstream artifacts are scheduled for future sprints (Sprint-N
> ships a DDL ALTER + adapter patch in incomplete form; Sprint-M re-reads the DDL
> + adapter + writes the downstream module / test / consumer + smoke runs).
>
> Three-bucket triage workflow:
> - **Sprint-N Remediation bucket** — findings on items whose downstream artifacts ALL exist in deployed code. Fix in a dedicated Remediation sprint; smoke re-run to verify; flip BLOCKED status in the upstream sprint Recovery.
> - **Sprint-M Authoring (pre-emptive flag) bucket** — findings on items whose downstream artifacts are scheduled for a future sprint not yet authored. Surface in the Findings doc with:
>   1. A pre-emptive flags table (item | severity | future Sprint-M session | recommendation for author).
>   2. The full fix description embedded inline OR cross-linked from the table.
>   3. A note in the future Sprint-M's Orchestration prerequisites that says "read {Audit-ID} Findings Part-N pre-emptive flags table before drafting task files."
> - **Sprint-N Remediation + Sprint-M Flag combo** — findings where the upstream change (DDL ALTER, adapter patch, etc.) is needed to unblock current code AND the downstream artifact can wait for the future sprint. Ship the upstream fix in Sprint-N; flag the downstream artifact for Sprint-M.
>
> The Findings doc becomes the cross-sprint coordination artifact. The Sprint-M
> author reads the flags during their Orchestration draft, then ships the audit
> fix as part of authoring rather than as a separate remediation pass.
>
> Three caveats:
> 1. **Does NOT apply when un-authored artifacts are months out** — the Findings doc's pre-emptive flag can rot. Re-run a fresh cross-tier diff when the future sprint kicks off (per [exit-criteria-fidelity.md](exit-criteria-fidelity.md#163-extension--bli-cited-audit-anchor-re-verification) §16.3's BLI-Cited Anchor Re-Verification clause). Pre-emptive flags expire.
> 2. **Does NOT apply when the upstream change is needed to unblock current code** — use the combo bucket above.
> 3. **Does NOT save work in token count, only in session-orchestration overhead** — each task still gets executed; the saving is in scaffolding effort, agent-dispatch coordination, and Recovery-file churn.
>
> Concrete trigger:
> 1. For each HIGH/MEDIUM finding, look up the affected item's downstream artifact status (downstream module authored? consumer code present? tests?).
> 2. If ALL downstream artifacts exist and are in deployed code → Remediation bucket (next sprint).
> 3. If ANY downstream artifact is in a planned-but-unauthored sprint → pre-emptive flag bucket (defer to that sprint's author).
> 4. The pre-emptive flag table goes in the Findings doc Part-2 (or an equivalent location near the MEDIUM dispositions); add it to the future sprint's Orchestration prerequisites.

#### Reviewer Check 053 — Cross-Tier Audit Triage Table Presence

- **Severity / Role:** WARNING | Design-Extension Reviewer | NEW
- **Detection:** For Discovery/audit sessions, verify `## Cross-Tier Audit Finding Triage` table presence with three buckets (remediation / pre-emptive flag / combo). Absent → WARNING.
- **Finding template:** `[WARNING] Cross-tier audit triage table missing | Fix per references/execution-time-binding-rules.md §18`

---

## 19. Narrow Fix Reveals a Systemic Gap — Bounded Temp Fix That Seeds the Deferred Discovery (BINDING)

A narrowly-scoped bug fix sometimes surfaces a *recurring defect class* — a failure that is one of a family, where the proper solution is a cross-cutting framework (a policy registry, a shared preprocessor, a result-surface change) spanning many call sites. Resolving that framework inline, mid-bug-fix, explodes the session's scope and blast radius before the verification gate even re-runs. Pinning only the observed instances recurs the moment a sibling appears. The discipline is to split the work — and to make the cheap fix pay for the expensive plan.

This rule cross-links the count-by-execution discipline in [§15.1](discovery-and-exit-criteria.md#151-deterministic-bug-scope-must-be-counted-by-execution-not-estimated): the seeding tactic below is how a bug-fix session hands the deferred Discovery the count-by-execution evidence §15.1 requires.

> [!decide] Narrow Fix Reveals a Systemic Gap
> When a narrowly-scoped fix surfaces a *recurring defect class* you intend to generalize later, SPLIT it:
> - Ship a **bounded temp fix** that closes the gate now (one file, no cross-cutting framework change), AND
> - Spin a **separate discovery/framework plan** (a planwise Meta-Plan) for the principled solution.
>
> Do NOT resolve the systemic design inline in the bug-fix session, and do NOT under-fix by enumerating only the observed instances.

> [!constraint] Two Failure Modes to Avoid — Over-Build and Under-Fix
> WRONG — **over-build**: implement the whole framework (registry + policy preprocessor + result-surface change + migrate callers) inline mid-bug-fix → scope explosion + large blast radius before the verification gate even re-runs.
>
> WRONG — **under-fix**: pin only the observed instances (e.g. the two observed identifiers) → recurs the moment a sibling instance appears (the failure family had dozens of variants across two severity groups).
>
> CORRECT — **bounded temp fix**: close the gate with the *robust-but-bounded* option (severity-class handling beats instance enumeration when the failure is one of a family) + bound it (an iteration cap) + stay one file (no cross-cutting framework change). Pair it with a separate discovery/framework plan for the principled solution.
>
> Concretely, a bounded temp fix:
> - **Closes the gate with the bounded-robust option, not the narrow one.** Handling the entire sibling family by severity class (e.g. dismiss-all-`Warning` + an iteration cap), bounded to the non-blocking cases, resolves every sibling at once; pinning the observed instances would recur on the next one. *Severity classification beats instance enumeration when the failure is one of a family.*
> - **Stays one file.** No result-surface change, no registry, no caller migration — those are the framework plan's scope, explicitly deferred.

> [!practice] Make the Temp Fix Seed the Deferred Discovery
> Make the bounded temp fix EMIT the diagnostic data the deferred plan will need — a structured count-by-execution catalog (one record per distinct failure: identifier, severity, action, description), written via the project's diagnostic logging pattern (a durable, append-only, machine-readable log). The future Discovery then starts from count-by-execution evidence ([§15.1](discovery-and-exit-criteria.md#151-deterministic-bug-scope-must-be-counted-by-execution-not-estimated)) instead of forward-estimating which of thousands of candidate cases actually matter. The deferred work becomes a planwise Meta-Plan (Discovery), not an inline build — letting the systemic design (ordering conflicts, placement, new dispositions, caller migration) be explored and reviewed before any framework code is written.

Applies to:
- Any session where a narrow fix (a single failing tool, a one-instance patch) reveals a repo-wide / recurring defect class the team wants to generalize.
- Especially when the proper solution is a cross-cutting framework (a policy registry, a shared preprocessor, a result-surface change) that would explode a bug-fix session's scope and blast radius.
- The seeding tactic applies whenever the deferred plan needs empirical scope data: emit a structured catalog (via the project's diagnostic logging pattern) in the temp fix so Discovery counts-by-execution instead of estimating.

NOT applicable when the surfaced gap is a one-off (no sibling family, no recurrence risk) — then the in-line fix IS the principled fix and there is nothing to defer.

---

## 20. Spike Instrument Verdict Discipline (BINDING)

A spike instrument fed synthetic input can confirm that the instrument is correct and structurally sound. It cannot confirm that tolerance or threshold *magnitudes* are production-appropriate.

### 20.1 Synthetic-Fixture Verdict Partitioning

> [!constraint] Partition spike verdicts by what synthetic input can actually decide — do not over-claim
> When a spike instrument runs on synthetic (non-production) input because the real
> artifact is gated behind a later live step, the verdict must be partitioned by
> what the input is capable of stressing:
>
> | Verdict class | Synthetic fixture can resolve? |
> |---------------|-------------------------------|
> | Instrument correctness (compiles/runs, stages fire, no-throw on edge inputs) | YES |
> | Structural behaviour (dedup-before-pairing, input normalization, NaN/Inf dropped) | YES |
> | Perf *scaling shape* + an upper-bound timing anchor | YES |
> | Tolerance/threshold *magnitudes* (production default values) | **NO — defer to real-input data** |
>
> WRONG — report "the defaults are confirmed" because the tolerance sweep ran clean
> on synthetic data:
> ```
> Synthetic-fixture sweep: 5 of 6 defaults show zero sensitivity to ±50% perturbation.
> Finding: the six defaults are confirmed.
> ```
> A synthetic fixture is pathologically clean (exact, degenerate-free, near-total
> overlap), so slack tolerances are never the deciding constraint. A real "dirty"
> input is precisely what exercises them.
>
> CORRECT — report the magnitude verdict as DEFERRED to the real artifact; name
> the single most outcome-sensitive parameter for priority confirmation; ship a
> re-runnable instrument so the magnitude pass is a re-run, not a rebuild:
> ```
> Instrument correctness: CONFIRMED (all pipeline stages fire, no-throw on edge inputs)
> Structural behaviour: CONFIRMED (dedup-before-pairing, NaN/Inf dropped)
> Perf scaling shape: CONFIRMED O(n²); upper-bound anchor: 32,610 ms @ 5,000 items
> Tolerance magnitudes: DEFERRED to live real-input data
>   Priority parameter for confirmation: TOL_PRIMARY (the only default that moved
>   output under ±50% perturbation; the other five showed zero sensitivity on synthetic).
> ```

Corollary for guessed perf budgets: a plan-mode budget constant (e.g. `< 500 ms`) is a placeholder until measured. Anchor it against measured scaling and a stated language-speedup extrapolation; surface the algorithmic risk (whether the approach can meet the budget at the stress-n) rather than inheriting the guess into a test assertion.

Applies to:
- Discovery / de-risk spikes whose probe instrument runs on synthetic or stand-in input because the real artifact is gated behind a later live step.
- Any tolerance / threshold-sweep finding: separate "instrument validated + structural behaviour confirmed" from "magnitude confirmed" and defer the latter to real-input data.
- Perf-budget constants written as plan-mode placeholders: anchor against measured scaling before pinning them into a test assertion.

---

*Companion files: [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md) (anchor — §15, shared Plan-Review Enforcement Summary), [exit-criteria-fidelity.md](exit-criteria-fidelity.md) (§16), [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols) (parent rule), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Task File Template), [session-plan-requirements.md](session-plan-requirements.md) (signoff sections), [task-content-fidelity.md](task-content-fidelity.md) (Required Context fidelity, verify-before-cite).*
