---
description: Cross-layer enforcement of exit-criteria fidelity — binding-refinement callout echo across plan layers, "surfaces" as an enforceable claim not a mention, sprint-signoff verbatim quoting with a mechanical anchor per row, BLI-cited audit-anchor re-verification, and metric-definition verification before reproduction
---

# Exit-Criteria Fidelity (Cross-Layer Enforcement)

**Purpose:** Binding rules for cross-layer enforcement of exit-criteria fidelity (§16) — binding-refinement callout echo across plan layers, "surfaces" as an enforceable claim rather than a mention, sprint-signoff verbatim quoting with a mechanical anchor per row (including the BLI-Cited Audit-Anchor Re-Verification extension), and metric-definition verification before reproduction. Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same issues.

This file is the §16 segment of a 3-way split of `discovery-and-exit-criteria.md` (the anchor, which keeps §15 and the shared 11-row Plan-Review Enforcement Summary — see the anchor for how each of that table's rows now resolves across the three files); §17-§20 live in [execution-time-binding-rules.md](execution-time-binding-rules.md). Extracted to keep all three files under the project's 500-line limit. Read it before authoring multi-layer binding refinements, BLOCKING-coverage task files, or sprint signoff checklists.

## Table of Contents

- [16. Cross-Layer Enforcement & Exit-Criteria Fidelity](#16-cross-layer-enforcement--exit-criteria-fidelity-binding)
  - [16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers](#161-binding-refinements-must-be-echoed-as--binding-callouts-across-plan-layers)
  - [16.2 "Surfaces" is an enforcement claim, not a mention](#162-surfaces-is-an-enforcement-claim-not-a-mention)
  - [16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row](#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row)
  - [16.4 Verify the Metric Definition Before Reproduction](#164-verify-the-metric-definition-before-reproduction)

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
