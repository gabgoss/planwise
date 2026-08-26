---
description: Cross-layer enforcement of exit-criteria fidelity — binding-refinement callout echo across plan layers, "surfaces" as an enforceable claim not a mention, sprint-signoff verbatim quoting with a mechanical anchor per row, BLI-cited audit-anchor re-verification, and metric-definition verification before reproduction
---

# Exit-Criteria Fidelity (Cross-Layer Enforcement)

**Purpose:** Binding rules for cross-layer enforcement of exit-criteria fidelity (§16) — binding-refinement callout echo across plan layers, "surfaces" as an enforceable claim rather than a mention, sprint-signoff verbatim quoting with a mechanical anchor per row (including the BLI-Cited Audit-Anchor Re-Verification extension), and metric-definition verification before reproduction. Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same issues.

This file is the §16 segment of a 3-way split of `discovery-and-exit-criteria.md` (the anchor, which keeps §15 and the shared 11-row Plan-Review Enforcement Summary — see the anchor for how each of that table's rows now resolves across the three files); §17-§20 live in [execution-time-binding-rules.md](execution-time-binding-rules.md). Extracted to keep all three files comfortably within a single Read call. Read it before authoring multi-layer binding refinements, BLOCKING-coverage task files, or sprint signoff checklists.

## Table of Contents

- [16. Cross-Layer Enforcement & Exit-Criteria Fidelity](#16-cross-layer-enforcement--exit-criteria-fidelity-binding)
  - [16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers](#161-binding-refinements-must-be-echoed-as--binding-callouts-across-plan-layers)
  - [16.2 "Surfaces" is an enforcement claim, not a mention](#162-surfaces-is-an-enforcement-claim-not-a-mention)
  - [16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row](#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row)
  - [16.4 Verify the Metric Definition Before Reproduction](#164-verify-the-metric-definition-before-reproduction)
  - [16.5 Verify Data-State Criteria by Query, Not by a Status Field](#165-verify-data-state-criteria-by-query-not-by-a-status-field)
  - [16.6 Every Audit States the Defect Classes It Did Not Check](#166-every-audit-states-the-defect-classes-it-did-not-check)
  - [16.7 Re-Verify at Fix Time Obligates a Full Re-Characterization](#167-re-verify-at-fix-time-obligates-a-full-re-characterization)
  - [16.8 Sample-Stop Permitted on Converged Validation, With Annotation](#168-sample-stop-permitted-on-converged-validation-with-annotation)
  - [16.9 An Absence Criterion Must Exclude Its Enactor and Prove Its Ownership](#169-an-absence-criterion-must-exclude-its-enactor-and-prove-its-ownership)
  - [16.10 A Mechanical Anchor Checks the Form of the Check, Not the Truth of the Claim](#1610-a-mechanical-anchor-checks-the-form-of-the-check-not-the-truth-of-the-claim)

---

## 16. Cross-Layer Enforcement & Exit-Criteria Fidelity (BINDING)

A rule mentioned in one place — even an authoritative place like a Sprint Plan — does not survive a single dispatch context's erratic compliance. Refinements that gate execution outcomes need redundant enforcement across plan layers (Sprint Plan, Orchestration, task files, signoff). And signoff itself must verify against the literal exit criteria, not a paraphrase.

### 16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers

> [!constraint] A single mention of a binding refinement is insufficient — the rule MUST be echoed as a `> [!binding]` callout in every layer that might execute or reference the gated behavior
> A refinement is *binding* when violation produces a latent bug or contract
> violation (e.g., writing config to the wrong file, mutating a forbidden
> table, omitting a UNCONFIRMED caveat). For binding refinements, a single
> narrative mention in a Sprint Plan is lost in 200+ lines of plan content.
> Subagents scanning for "what to do" read Execution Steps and Notes; a
> generic phrase ("phase-scoped", "do not embed X") is not specific enough
> to prevent the default behavior.
>
> Required layers for `> [!binding]` callout echo:
> 1. **Sprint Plan** — names the refinement, cites the source (verification
>    doc, design decision)
> 2. **Each Orchestration** that might execute the gated behavior — restates
>    the rule
> 3. **Each task file** that performs the gated action — restates as a `Notes
>    for Agent` callout
> 4. **Review/signoff task** — includes a grep verification step
>
> WRONG — single narrative mention in the Sprint Plan body:
> ```markdown
> The agent should write to the {phase_config_file} files.
> ```
> Cost: a dispatched subagent reads the Execution Steps and may default to the
> canonical config path because that is what most projects use. The refinement
> is only enforced if the agent sees the rule at dispatch time.
>
> CORRECT — `> [!binding]` callouts echoed across layers (4-8 sites is typical;
> the redundancy survives a single dispatch's erratic compliance):
>
> Sprint Plan:
> ```markdown
> > [!binding] Config Path
> > Config writes target `{phase_config_file}` AND `{canonical_config}`.
> > Root config is NEVER a write target. `{config-load-function}()` call site at
> > `{contract-path}:{line-range}`.
> ```
>
> Session Orchestration (config-writing session):
> ```markdown
> > [!binding] Config Path Enforcement
> > Task targets `{phase_config_file}` and `{canonical_config}` only.
> > Root config writes are prohibited.
> ```
>
> Task file (the actual writer):
> ```markdown
> ## Notes for Agent
>
> > [!binding] Phase-Scoped Config Only
> > OUTPUT target: `{phase_config_file}` + `{canonical_config}`
> > PROHIBITED: root config (NOT a write target; `{config-load-function}` does
> > NOT read it)
> ```
>
> Review task:
> ```markdown
> 5. Verify config-path refinement: grep `Exec-{Abbrev}/Sprint-{NN}/` for
>    config references; all must be phase-scoped.
> ```

Grep verification (review-task discipline):
```bash
# Every match must be a binding callout OR resolve to a phase-scoped path
# Adapt grep pattern to your config file naming convention
grep -rn '{config_pattern}' <sprint-root>/
```
Zero matches targeting the prohibited path as a write destination.

Applies to any refinement where:
- The operational risk is "agent defaults to canonical-looking path or value"
- The refinement is grep-verifiable against the sprint tree
- Violation is a latent bug rather than a runtime error (language tooling would catch the latter)

NOT applicable when there is only one valid path/value (no ambiguity, no default to override).

#### Reviewer Check 042 — §16.1 Binding Refinements Echo Across Layers

- **Severity / Role / Type:** BLOCKER | Coverage Reviewer | NEW
- **What:** Binding refinements (added enforcement language at one layer) MUST echo at all dependent layers (rule → reference → handler → agent → template).
- **Detection:** For each refinement, identify dependent layers; verify presence. Missing from any dependent layer → BLOCKER.
- **Finding template:**
```
[BLOCKER] Binding refinement not echoed across layers
File: {layer file path} | Location: {section}
Issue: Refinement "{quoted_text}" missing from dependent layer {layer_path}
Fix: Echo per references/exit-criteria-fidelity.md §16.1 | Confidence: HIGH
```

### 16.2 "Surfaces" is an enforcement claim, not a mention

> [!constraint] When a task file claims to "surface" a BLOCKING item, the body MUST contain an enforceable check — verbal mentions in Notes do not count
> Define **SURFACE** for task-file authoring purposes:
>
> A task SURFACES a BLOCKING item when its body contains AT LEAST ONE of:
> - Numeric assertion in test (e.g., `assert {value} {comparator} {threshold}`)
> - Grep / search command in lint or signoff (e.g., `{grep-cmd} {target-file}`
>   returns N matches)
> - Source-introspection check on the function body (adapt to language equivalent
>   or use grep; e.g., Python: `inspect.getsource()` excluding docstring)
> - Documentation content check (when the BLOCKING item requires a
>   docstring/comment warning)
> - Parametrized test case covering the boundary
>
> Verbal references in `Notes for Agent` do NOT count as surfacing. They
> reference; they do not enforce.
>
> WRONG — Notes line claims to surface a BLOCKING item but the test only checks
> an unrelated behavior:
> ```markdown
> ## Notes for Agent
> - Test {N} surfaces §X.Y (no `{prohibited_identifier}` in `{target_function}`)
>
> ## Execution Steps
> {N}. Test `{target_function}` bounds clamping behavior.
> ```
> Cost: §X.Y is BLOCKING. The bounds-clamping test does not check this — it
> tests something else entirely. The BLOCKING coverage matrix shows PASS, but
> the actual gate is open.
>
> CORRECT — Notes line is backed by an enforceable check inline in Execution
> Steps:
> ```markdown
> ## Notes for Agent
> - Test {N} surfaces §X.Y via source-introspection check
>
> ## Execution Steps
> {N}. Add a test that introspects `{target_function}` and asserts
>    `'{prohibited_identifier}' not in source_body` (where source_body is the
>    function body after stripping the docstring; adapt to language equivalent).
> ```

The distinction matters because BLOCKING items are BLOCKING. A non-enforceable mention does not reduce the risk the item describes — it gives false comfort that the gate is closed when it is not.

> [!practice] SURFACE Definition Block (paste into scaffold task-file template)
> A task SURFACES a BLOCKING item when its body contains AT LEAST ONE of:
> - Numeric assertion in test
> - Grep / search command in lint or signoff
> - Source-introspection check on the function body (excluding docstring; adapt
>   to language equivalent)
> - Documentation content check
> - Parametrized test case covering the boundary
>
> Verbal references in `Notes for Agent` are MENTIONS, not SURFACES. The
> fidelity-review task distinguishes SURFACES from MENTIONS — verbal-only
> claims are GAPs, not PASS. Multi-layer enforcement (test SURFACE + signoff
> SURFACE) is more robust than a single layer.

> [!constraint] Extend SURFACE-vs-MENTION to Master-Plan Risk-Mitigation cells and task Success Criteria, with an `Implemented by` column
> Extend the SURFACE-vs-MENTION enforceability requirement from EI exit criteria to Master-Plan Risk-Mitigation cells and task Success Criteria. Any mitigation that names an assertion MUST cite the task file **and** the Verification Command / Success Criterion that implements it:
>
> | Risk | Impact | Mitigation | Implemented by |
> |---|---|---|---|
> | (example row shape) | (impact) | (named assertion) | `{task-id}` §{section} + §Verification Commands |
>
> A criterion no command can check is not a criterion; it is a wish — one row per criterion, one mechanical anchor per row, applied upstream at authoring time. Prefer a deterministic structural gate over a runtime value tripwire: when a risk is "two orderings drift apart," compare the two orderings directly rather than asserting a value a drift would only sometimes disturb. A Risk-Mitigation cell is a claim about an artifact that does not exist yet, written by someone who will not be the one writing it — bind it to the artifact, or do not write it.
>
> Review gate: every assertion named in a Master-Plan Risk-Mitigation cell must appear in a task file; zero hits means the mitigation is a promise, not a fact. Catalog row: "Risk-Mitigation assertion not implemented in any task file" → ERROR.

### 16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row

> [!constraint] Signoff checklists MUST quote EI exit criteria verbatim, one row per criterion, with a mechanical anchor per row
> A signoff that silently paraphrases exit criteria is lossy by construction.
> The signer trusts the checklist as authoritative; if the checklist does not
> match the EI literal text, the gate's semantic contract is broken.
>
> Four failure modes that all share this remediation:
>
> | Failure | What goes wrong |
> |---------|------------------|
> | **Silent rename** | EI lists `{name_A}`; signoff lists `{name_B}`. Reader cannot tell if intentional deviation or implementation drift. |
> | **Silent helper substitution** | EI lists `{helper_A}`; signoff lists `{helper_B}`. Same problem — deviation not annotated. |
> | **Vague row** | "Tests pass" with no command, expected count, or test path. Forces signer to interpret. |
> | **Collapsed rows** | EI lists `{check_A}` AND `{check_B}` separately; signoff collapses to one row. If `{check_A}` fails but `{check_B}` passes, the collapsed row may show only `{check_B}` output and miss the failure. |
>
> WRONG — paraphrased rows, missing rows, vague rows, collapsed rows:
> ```markdown
> ## Sprint Signoff Checklist
> - [ ] {paraphrased_name_A}             ← rename, no source citation
> - [ ] {substituted_helper_B} works     ← helper substitution
> - [ ] Tests pass                        ← vague
> - [ ] Lint passes                       ← collapsed (multiple checks)
> ```
> EI listed {N} items; checklist shows {M} where M < N. Cost: signer issues
> `READY_FOR_NEXT` without verifying {N - M} of the gate.
>
> CORRECT — verbatim quote of EI exit-criteria text, one row per criterion,
> mechanical anchor per row, deviation annotation when implementation diverges:
> ```markdown
> ## Sprint Signoff Checklist (verbatim from EI §X.Y)
>
> - [ ] §X.Y row 1: "{verbatim EI exit-criterion text}"
>       Mechanical: `{test-cmd} {test-path}` reports `{N} passed, 0 failed`.
>
> - [ ] §X.Y row 2: "{verbatim EI exit-criterion text}"
>       Mechanical: `{lint-cmd} {src/module/file.ext}` exits 0.
>
> - [ ] §X.Y row 3: "{verbatim EI exit-criterion text}"
>       Mechanical: `{format-cmd} {src/module/file.ext}` reports no changes.
>       **Deviation:** implementation intentionally diverged — see
>       `{design-decision-path}` row D{N}.
>
> ... ({total-N} more rows for §X.Y items {remaining})
> ```

Binding rule for all sprint signoff tasks:

1. **Verbatim quote** at the head of the exit-criteria check — quote the EI exit-criteria section text. Do not paraphrase.
2. **One row per criterion** — if the EI section has N items, the checklist has N rows.
3. **Mechanical anchor per row** — `{test-cmd}` + expected count, grep + expected hits, file path + existence assertion, lint/format output, etc. Prose-only rows fail this rule.
4. **Deviation annotation** — when the implementation intentionally deviates from a verbatim text (rename, helper substitution, structural change), the row carries a `**Deviation:** <design-decision document path>` annotation. Silent deviations are GAPs, not PASS.

> [!checklist] Sprint Signoff Authoring
> - [ ] Quoted the EI exit-criteria section verbatim at the head of the check
> - [ ] Row count in the checklist matches item count in the EI section
> - [ ] Every row has a mechanical anchor (`{test-cmd}` / grep / lint / format / file existence)
> - [ ] Every intentional deviation from verbatim text carries a `**Deviation:** <design-decision document path>` annotation
> - [ ] No collapsed rows where the EI lists items separately
> - [ ] Every BLI-cited bug anchor has been re-verified against the audited file's current state at session start; any drift is reflected in the replacement criterion (per the BLI-Cited Anchor Re-Verification clause below)
> - [ ] Every grep anchor for a column name that may collide across tables in the audit scope is `{table}.{column}`-qualified (per the Qualified-Grep Discipline clause below)

#### Reviewer Check 043 — §16.3 EI Exit Criteria With Mechanical Anchors

- **Severity / Role / Type:** BLOCKER | Coverage Reviewer | NEW
- **What:** EI Exit Criteria MUST verbatim-quote source exit-criteria AND include mechanical anchor (grep pattern / file path).
- **Detection:** Quote present but no mechanical anchor → BLOCKER. Quote not verbatim → BLOCKER.
- **Finding template:**
```
[BLOCKER] EI Exit Criteria missing mechanical anchor
File: {EI file path} | Location: Exit Criteria section
Issue: Exit criterion lacks {grep_pattern}/{file_anchor}
Fix: Add mechanical anchor per references/exit-criteria-fidelity.md §16.3 | Confidence: HIGH
```

#### 16.3 Extension — BLI-Cited Audit-Anchor Re-Verification

§16.3 binds sprint signoffs to quote EI exit criteria verbatim with a mechanical anchor per row — but that rule assumes the EI exit criteria still reflect the audited code's *current* state at signoff time. In multi-week plans where the Discovery → Audit gap exceeds one sprint, the audited codebase keeps moving: bugs fixed in passing during other sprints silently invalidate the audit's "I expect to find these bugs" regression anchors.

> [!constraint] BLI-cited exit-criteria anchors MUST be re-verified against current code at session start
> When a Sprint Plan encodes "regression anchors" tied to specific known bugs
> (typically by BLI ID), and the plan has been waiting more than one sprint
> between authoring and execution, the orchestrator MUST re-verify each cited
> anchor against the audited code's current state BEFORE dispatching any session
> that uses those anchors as a success criterion.
>
> Three failure modes share the same root cause (codebase moves between BLI
> filing and audit execution):
>
> | Failure mode | What goes wrong |
> |--------------|------------------|
> | **False HALT** | A bug cited as a regression anchor has been quietly resolved during another sprint. The audit's "must find this bug" gate HALTs because the matching row is ALIGNED instead of HIGH. |
> | **False PASS via name collision** | A bare-column grep matches an unrelated finding on a different table. The consolidator sees "a row matches the anchor" and clears the gate; the real bug is missing. |
> | **Silent miss of a bug truly recurring** | If the resolution itself regresses later, the bare-column grep still matches *something* (the now-resolved row), masking the regression. |
>
> WRONG — Sprint Plan freezes the mechanical-grep success criterion at BLI filing time:
> ```
> grep -c "HIGH" Outputs/Cross-Tier-Diff.md
> # MUST return ≥ 2 matching specific table.column patterns
> ```
> When a cited bug gets fixed in passing, the gate trips at execution time on the resolved row — false HALT.
>
> CORRECT — Sprint Plan + Orchestration include a pre-flight re-verification step
> at session start. Each cited anchor is greped against the audited file's
> *current* state; if any anchor no longer matches the expected severity, replace
> the mechanical criterion with the actual current state BEFORE dispatching the
> consolidator/triager:
> ```
> ## Sprint-XX Success Criteria (replacement after pre-flight re-verification at session start)
>
> - [ ] {table_A}.{column_A} row in Cross-Tier-Diff is ALIGNED
>   (resolved in deployed code per pre-flight verification {YYYY-MM-DD}).
> - [ ] {table_B}.{column_B} row in Cross-Tier-Diff is HIGH and proposes
>   {specific fix} as the remediation.
> ```

> [!constraint] Grep anchors for BLI-cited bugs MUST be `{table}.{column}`-qualified when column names may collide across tables in audit scope
> WRONG — bare column name; matches every table that shares the column:
> ```
> grep -E "{column}"   # matches finding rows on {table_A} AND {table_B}
> ```
> CORRECT — `{table}.{column}` qualified; unique across the audit output:
> ```
> grep -E "{table_A}\.{column}"
> ```
>
> The `{table}.{column}` form costs one extra escape character per anchor and
> eliminates the collision class entirely. Bare column names collide in any
> cross-table audit; the qualified form is the safe default.

> [!practice] Consolidator/triager error-recovery clauses SHOULD report stale-criterion findings, not HALT
> When a BLI-cited anchor has been re-verified at session start and matches a
> different state than originally expected (resolved, regressed, or moved), the
> consolidator/triager task SHOULD document the stale criterion in its output
> (under a "Regression Check" or "Stale Criterion" section) and continue to a
> clean summary — NOT HALT mid-session. HALT-on-stale is reserved for cases where
> the orchestrator has not provided an explicit override authorising continued
> execution.
>
> This is a SHOULD, not a MUST. Some audit plans legitimately want a hard stop on
> stale criteria (e.g., when the stale state itself is a regression). The
> orchestrator decides; the task's error-recovery clause defaults to "report
> stale, continue" unless the Sprint Plan binds it to HALT.

#### Reviewer Check 044 — §16.3 BLI-Cited Audit Anchor Re-Verification

- **Severity / Role / Type:** BLOCKER | Coverage Reviewer | NEW
- **What:** BLI-cited audit anchors MUST be re-verified at session start (anchor may have moved due to upstream edits).
- **Detection:** For each BLI-cited anchor (`{file_path}:{line_range}` or `{file_path}#{section}`), open referenced file and verify content. Stale → BLOCKER.
- **Finding template:**
```
[BLOCKER] BLI-cited audit anchor stale
File: {Orchestration file path} | Location: BLI reference {BLI_id}
Issue: Anchor "{anchor}" no longer resolves; expected content not found
Fix: Re-verify per references/exit-criteria-fidelity.md §16.3 | Confidence: HIGH
```

#### Reviewer Check 054 — BLI-Cited Anchor Re-Verification (Session-Start)

- **Severity / Role:** BLOCKER | Design-Extension Reviewer | NEW
- **Detection:** At session-start, re-verify all BLI-cited audit anchors (also covered as Coverage Check 044; duplicated here for design-extension scope at session start).
- **Finding template:** `[BLOCKER] Session-start BLI anchor re-verification missing/failing | Fix per references/exit-criteria-fidelity.md §16.3`

### 16.4 Verify the Metric Definition Before Reproduction

> [!constraint] Confirm what N counts before asserting "reproduce N" — metric labelling differences are not data divergences
> When an exit criterion asserts "reproduce N", confirm **what N counts** before
> declaring pass/fail — especially when the baseline and the probe compute the
> value via different code paths.
>
> A single mislabelled metric ("curves" vs "runs") produces a false FAIL that can
> trigger a HALT or a wasted reconciliation cycle. The cheap disconfirming move is
> arithmetic on the columns you already have: if `paired + fallback == baseline`
> exactly, the extraction path is faithful and the divergent column is simply a
> different, additional metric — not a failure.
>
> WRONG — compare the first numeric column that resembles the baseline and HALT on
> mismatch:
> ```
> probe reports totalCurveCount = 82 / 958 / 248
> baseline asserts 82 / 499 / 176
> → HALT: counts don't match
> [The baseline numbers were wall-RUN counts (pairedRunCount + fallbackRunCount),
>  mislabelled "curves"; totalCurveCount is a different, raw metric.]
> ```
>
> CORRECT — enumerate every count the probe emits, find which combination
> reproduces the baseline exactly, and label both metrics explicitly in the
> findings. Reserve HALT for a genuine extraction or data divergence, not a
> labelling difference:
> ```
> probe: totalCurveCount = 82 / 958 / 248
>        pairedRunCount  =  0 / 263 /  60
>        fallbackRunCount= 82 / 236 / 116
> arithmetic check: paired + fallback = 82 / 499 / 176  ← matches baseline exactly
> → Finding: baseline counts were wall-RUN counts; totalCurveCount is the raw
>   exploded-segment census — a distinct, additional metric. Extraction is faithful.
>   Label both metrics explicitly; do NOT HALT.
> ```

#### Reviewer Check 045 — §15/§16 Cross-Layer Cohort Discovery Scope

- **Severity / Role / Type:** ERROR | Coverage Reviewer | NEW
- **What:** Discovery scope in Master Plan/Sprint Plan MUST match actual coverage produced by Discovery sessions (no orphaned spec sections, no unscoped findings).
- **Detection:** Compare Master Plan declared scope vs Discovery outputs. Declared cohort with 0 outputs OR outputs covering undeclared cohort → ERROR.
- **Finding template:**
```
[ERROR] Discovery scope mismatch
File: {Master Plan path} | Location: Discovery cohort declaration
Issue: Cohort "{name}" declared but no outputs (or outputs not scoped)
Fix: Reconcile per references/exit-criteria-fidelity.md §16 / references/discovery-and-exit-criteria.md §15 | Confidence: HIGH
```

### 16.5 Verify Data-State Criteria by Query, Not by a Status Field

> [!constraint] A data-state criterion is verified by query, never by a Status field
> When a prerequisite or exit criterion is a data-state claim ("tables populated", "N rows ingested"), its mechanical anchor MUST be a query against live data — never an upstream plan's `Status: COMPLETE`. An authoring sprint whose smoke tests were blocked is artifact-complete, not data-complete; say so explicitly rather than letting COMPLETE imply both. This is the data-state analogue of the existing one-mechanical-anchor-per-criterion discipline.

### 16.6 Every Audit States the Defect Classes It Did Not Check

> [!constraint] Every audit states the defect classes it did NOT check
> An audit MUST enumerate the defect classes outside its scope and scope its verdict vocabulary accordingly — "no defect of class X", never bare "clean". A "works" verdict requires the positive test (run it, assert the result), never the absence of one negative pattern.
>
> WRONG — "12 of 17 audited clean" from a single-lens column diff that could not have seen type mismatches, nullability drift, or an absent table.
> CORRECT — "12 of 17 show no column-name divergence. Not checked: types, nullability, table existence, constraint shape."

### 16.7 Re-Verify at Fix Time Obligates a Full Re-Characterization

> [!constraint] "Re-verify at fix time" obligates a full re-characterization
> A single-lens audit under-reports in two directions: false-clean, and under-specified-defect. A finding tagged provisional/unconfirmed/"re-verify at fix time" obligates a full re-characterization of the artifact at fix time — the whole-object catalog query, the complete live probe — not a re-run of the one-line check that produced the tag.

### 16.8 Sample-Stop Permitted on Converged Validation, With Annotation

> [!constraint] Sample-stop is permitted on a converged validation, with an annotation
> A validation iteration MAY stop early when its verdict is already determined by parent state — denominator known, threshold crossed, or set membership confirmed. Document with a `**Deviation:**` annotation recording what stopped, the convergence proof, and the schedule for any residual. Not applicable when the iteration IS the validation (a per-row drift check has no convergence point).

### 16.9 An Absence Criterion Must Exclude Its Enactor and Prove Its Ownership

An absence criterion becomes unsatisfiable in two ways, needing different detections. The **enactor** cause: the artifact that performs the removal must name what it removes — an `--exclude` on the removal artifact fixes this. The **ownership** cause: the searched token is not owned by what is being deleted, so occurrences survive in code the plan never touched — an exclusion qualifier cannot reach this, because the artifact excluded was never the source of the surviving matches.

#### 16.9.1 The Enactor Cause — Exclude the Artifact That Enacts the Absence

> [!constraint] An absence criterion MUST exclude the artifact that enacts the absence
> WRONG — the criterion cannot be satisfied by any correct execution:
>
> ```markdown
> - [ ] `grep -rn "{retired_name}" {roots}` returns **zero matches**
> ```
>
> The removal artifact must name what it removes. The executor's choices are an impossible literal pass, or deleting the very artifact that performs the retirement to make the number reach zero.
>
> CORRECT — scope the absence to everything except the enactor, and say so in the prose as well as in the command:
>
> ```markdown
> - [ ] `grep -rn "{retired_name}" {roots} --exclude={removal_artifact}` returns zero matches —
>       i.e. zero references **outside the removal script**, which necessarily names its target
> ```

Generalizes beyond retirement: this applies to any absence criterion whose subject necessarily appears in the artifact that enacts the absence — a deprecation notice naming the deprecated symbol, a changelog entry naming a removed flag, a migration naming a dropped column, a lint-suppression registry naming the rule being suppressed.

#### 16.9.2 The Ownership Cause — A Symbol-Keyed Absence Criterion Asserts Ownership; Measure It First

> [!constraint] A deletion criterion keyed on a symbol name asserts ownership; measure it first
> Before writing a success criterion of the form *"symbol X no longer appears anywhere in `{scope}`"*, **grep for X across `{scope}` and paste the count into the criterion.**
>
> If the count is non-zero, one of two things is true and the criterion MUST say which:
>
> 1. **X is owned** by what you are deleting and the other occurrences are also in scope → enumerate them in the criterion.
> 2. **X is shared by convention** → the criterion is about the *deleted module's* references, not about the symbol name. Re-key it.
>
> ```bash
> # WRONG — unsatisfiable; a symbol name is not owned by one module
> grep -rn "{helper}" {scope}          # MUST be 0
>
> # CORRECT — scope to the artifact actually being removed
> grep -rn "{helper_module}" {scope}   # MUST be 0
> ```
>
> **Prefer module / import-path scoping over symbol-name scoping for every deletion criterion.** An import path is genuinely unique to the thing being deleted; a helper name in a family of modules written from a shared template almost never is.
>
> Three corollaries:
>
> - **A single-file grep proves local ownership, not global.** *"This is the only definition I can see from here"* is not *"this is the only definition."*
> - **Convention-driven codebases replicate helper names by design.** Any project with a *"every module provides the same private helpers"* rule — and such a rule is often the very rule governing the modules in scope — will have N copies of every helper name. Deletion criteria in such a codebase MUST key on modules, not symbols.
> - **A prohibition on new code is not a claim about existing code.** *"No new module may use X"* is a forward-looking rule and can be entirely correct while *"X does not appear in the codebase"* is false. Inferring the second from the first is the specific move that produced the observed defect.
>
> **Where the claim acquires its authority.** In the observed instance the confidence grew at every hop — *"sole home"* in a brief, *"the ONLY consumer"* in a sprint-plan headline, then an executable gate — with nothing measuring it at any hop. A success criterion is the moment a factual claim gains the authority to make people change working code. That is the moment it must be measured.

### 16.10 A Mechanical Anchor Checks the Form of the Check, Not the Truth of the Claim

§16.3 requires every criterion to carry a mechanical anchor. §16.10 governs what that anchor is allowed to assert — it checks form, not truth. A criterion can name a command, name an expected value, satisfy §16.3 completely — and still be false, because nothing in the system produces the value it expects.

That combination is worse than a vague criterion, not better. A prose-only row gets interpreted; a mechanically anchored false row gets **executed**, and a red gate on a stated success criterion reads as a defect in the work rather than a defect in the criterion. The natural remediation is to change correct work until the gate goes green.

#### 16.10.1 A Literal in a Criterion Carries Its Provenance or It Is Not a Literal

> [!constraint] A literal in a criterion carries its provenance or it is not a literal
> State criteria as **relationships the system maintains**, not as literal counts — unless the count was measured at authoring time and **the measurement is cited in the criterion**.
>
> - WRONG: `{flag} = 1` reaches **5**
> - CORRECT: `{flag} = 1` equals the number of known instances the upstream step disposed `resolved` — read from `{artifact}`, with a reconciliation table accounting for all five
>
> **Every literal needs a provenance**, because the same number is usually true of a different fact. In the observed instance "six tables" was correct for tables that carry the column and was silently reinterpreted as tables that contribute unresolved values. Two facts, one number, and nothing recorded which one the criterion meant.
>
> **Prefer `after == before` to `after == {literal}`.** An invariant the pipeline maintains is checkable without predicting a value; a predicted value is a forecast wearing a gate's clothing. When a plan already asserts "this table is unchanged" rather than "this table has N rows", that discipline generalises to every criterion in the plan.
>
> The two failure directions are opposites and both are silent:
>
> | Direction | What happens |
> |---|---|
> | **Quietly ticked** | The criterion is unmeetable and nobody re-counts a checkbox at signoff |
> | **Met by harm** | A conscientious runner satisfies the number by doing the thing the plan exists to prevent |
>
> The second is the reason this is a MUST and not a practice. In the observed instance the only way to reach the stated count was to persist a row referencing an entity the reference catalog deliberately omits — the exact violation the sprint had been scoped to prevent.

#### 16.10.2 A Gate on a Derived Ratio Names Its Column, Grain and Denominator, and Forbids Re-Derivation

> [!constraint] A gate on a derived ratio names its column, grain and denominator, and forbids re-derivation
> When a gate threshold reads a **derived** value — a ratio, share, fraction, or rate — specifying the formula and the threshold is **not enough**. The criterion MUST name:
>
> 1. the **exact column** to read,
> 2. the **grain** that column is emitted at,
> 3. the **denominator**, as a number, and
> 4. an explicit prohibition on re-deriving the value from a neighbouring number that looks like the same thing.
>
> WRONG — formula and threshold only, grain left implicit:
> ```markdown
> If `{ratio} > {threshold}`, report PRECONDITION-FAILED and HALT.
> {ratio} = {category} count / total {entities}.
> ```
> The artifact contains a column literally labelled for the category, at a **different grain**. A reader takes it, divides by the entity count, and halts a healthy plan. Nothing in the brief tells them they read the wrong grain.
>
> CORRECT — name the column, the grain, the denominator; forbid the alternative; require the other grain be reported separately:
> ```markdown
> `{ratio}` = count of {entities} with `{entity}_exercised = 0` ÷ **{N}**, read DIRECTLY from
> the `{entity}_exercised` column emitted at {entity} grain by {upstream task}.
>
> Do NOT re-aggregate the {alias}-grain rows. The {alias}-grain denominator is {M} and the
> {entity}-grain denominator is {N}; they are different numbers about different things.
> Report the {alias}-grain count alongside, labelled separately.
> ```
>
> Four corollaries, each independently load-bearing:
>
> - **A producer emitting multi-grain data MUST emit the rollup, not leave it derivable.** "Derivable in principle" is exactly how the wrong derivation happens. The consumer should never have to aggregate.
> - **Say which error the gate is tuned against.** Halting a healthy plan and proceeding on a bad corpus are not symmetric costs. Where they are asymmetric, prefer the fail-open input and state the choice — **a HALT looks like diligence, and nobody re-checks the input of a gate that stopped the work.**
> - **Pre-verify a cheap gate input at the orchestrator before dispatch.** When the input is one query, computing it and shipping it in the spawn prompt as orchestrator-validated context spends the runner's judgement on the verdict rather than on a number that can invert the outcome.
> - **A magnitude estimate inside a warning is still an estimate.** A warning that quantifies a hazard as an approximation (*"differ by ~1.7x"*) when the real ratio is materially larger (*7.4x*, in the observed instance) has quietly misrepresented the risk. If a warning quantifies a hazard, measure the quantity or drop it.

#### 16.10.3 A Criterion Naming an Artifact as the Producer of a Result Must Assert the Artifact Reads Its Subject

> [!constraint] A criterion naming an artifact as the producer of a result MUST assert the artifact reads its subject
> When a criterion names an artifact as the producer of a result — *"re-run `{artifact}` and record the delta"*, *"(it produces the headline metric)"* — that parenthetical is a **claim about the artifact's capability**, and it is exactly the kind of claim that gets written as context and never verified.
>
> Before trusting a measurement, verify the instrument reads the thing it measures. **One grep.** Do it when the measurement is authored, and again whenever a criterion names it as a producer:
>
> ```bash
> grep -c '{subject_table_or_source}' {measurement_artifact}   # MUST be > 0
> ```
>
> **A null result deserves more scrutiny than a positive one, not less.** *"No change detected"* is what both *"nothing changed"* and *"I cannot see the change"* look like — and only one of them is a finding. An instrument blind to its subject does not crash; it returns a precise, plausible, internally consistent number from the canonical tool, which is the most credible possible form of a wrong answer.
>
> A plan that says *"re-run X and record the delta"* must also say **"…and X must read Y."**

#### 16.10.4 Changing How Something Is Measured Makes Baseline Reproduction a Hard Gate

> [!constraint] Changing how something is measured makes baseline reproduction a hard gate
> When a measurement method changes — a repaired instrument, a new source, a different code path — the new method MUST reproduce the **old baseline exactly** before any delta against that baseline is reported. Baseline reproduction is a hard gate that halts on mismatch, not a formality — and the baseline itself is never adjusted to fit the new method.
>
> Without it, the reported delta measures *the difference between two methods* rather than the effect of the work — and it is reported as the result.
>
> Prefer **one code path with a scope parameter** over two implementations of "before" and "after". Two implementations cannot be proven equivalent by inspection:
>
> ```text
> SCOPE = "all"          # "{baseline_scope}" reproduces the prior baseline
> predicate = {baseline_predicate} if SCOPE == "{baseline_scope}" else {always_true}
> ```
>
> In the observed instance the baseline pass had to reproduce two prior figures to **4 decimal places** before the full pass was permitted to run. That single gate proves three things at once: the new source is faithful to the old one, the new index is equivalent to the one it replaced, and the "before" figure is like-for-like rather than a second method quietly substituted for the first.
>
> This is the counterpart to §16.4 and the two should be read together. §16.4 prevents a **false FAIL** — do the arithmetic before declaring a labelling difference a data divergence. §16.10.4 prevents a **false PASS** — no delta is reported until baseline reproduction succeeds against the old number.

---

## Scaffolding Template 2 — Sprint Signoff Checklist Block (§16.3)

> [!practice] Canonical Scaffolding Template Lives Inline in This Rule
> Paste the block below verbatim into the sprint signoff task body — it is
> the canonical template for §16.3 (verbatim sprint-signoff checklist block).
> Maintaining it inline (rather than as a sibling template file) keeps the
> template, the rationale, and the WRONG/CORRECT contrast in a single source.
> Template 1 (§15.1 Discovery identification-query block) lives in
> [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md#scaffolding-templates-canonical-paste-ready-blocks).
>
> **Template 2 — Sprint signoff checklist block (§16.3).** Paste into the sprint
> signoff task body, one row per EI exit-criterion:
>
> ```markdown
> ## Sprint Signoff Checklist (verbatim from EI §{N}.{M})
>
> - [ ] §{N}.{M} row 1: "{verbatim EI exit-criterion text}"
>       Mechanical: `{verification command + expected result}`.
>       **Deviation:** {design-decision document path}  [omit when matches verbatim]
>
> - [ ] §{N}.{M} row 2: "{verbatim EI exit-criterion text}"
>       Mechanical: `{verification command + expected result}`.
>
> ... (one row per EI exit-criterion item; row count MUST equal EI item count)
> ```
>
> Authoring rules: (1) verbatim quote at the head; (2) one row per EI criterion;
> (3) one mechanical anchor per row; (4) `**Deviation:** <path>` annotation
> whenever the implementation deviates from verbatim text.

---

*Companion files: [discovery-and-exit-criteria.md](discovery-and-exit-criteria.md) (anchor — §15, shared Plan-Review Enforcement Summary, Template 1), [execution-time-binding-rules.md](execution-time-binding-rules.md) (§17-§20), [session-planning-protocol.md](session-planning-protocol.md#companion-files-and-extracted-protocols) (parent rule), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Task File Template), [session-plan-requirements.md](session-plan-requirements.md) (signoff sections), [task-content-fidelity.md](task-content-fidelity.md) (Required Context fidelity, verify-before-cite), [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md) (companion discipline — same re-verification principle, from the backlog-triage entry point rather than sprint-signoff).*
