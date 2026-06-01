---
description: Discovery scope rigor (deterministic-bug counts, ID persistence), cross-layer enforcement of exit-criteria fidelity (binding callout echo, "surfaces" enforceability, signoff verbatim quoting, BLI-cited anchor re-verification), design-extension traceability, and cross-tier audit-finding triage
---

# Discovery Scope Rigor & Exit-Criteria Fidelity

**Purpose:** Binding rules covering related plan-fidelity concerns — Discovery scope rigor (§15), cross-layer enforcement of exit-criteria fidelity (§16), design-extension traceability (§17), and cross-tier audit-finding triage (§18). Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same issues.

This file is the §15 + §16 expansion of [session-planning-protocol.md](session-planning-protocol.md). It was extracted into a sibling file to keep both rule files under the project's 500-line limit. Read it before authoring Discovery-phase Consolidated Context, Execution Inputs that name affected records, multi-layer binding refinements, BLOCKING-coverage task files, or sprint signoff checklists.

## Table of Contents

- [15. Discovery Scope Rigor](#15-discovery-scope-rigor-binding)
  - [15.1 Deterministic-bug scope MUST be counted by execution, not estimated](#151-deterministic-bug-scope-must-be-counted-by-execution-not-estimated)
  - [15.2 Persist specific IDs, not just counts](#152-persist-specific-ids-not-just-counts)
- [16. Cross-Layer Enforcement & Exit-Criteria Fidelity](#16-cross-layer-enforcement--exit-criteria-fidelity-binding)
  - [16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers](#161-binding-refinements-must-be-echoed-as--binding-callouts-across-plan-layers)
  - [16.2 "Surfaces" is an enforcement claim, not a mention](#162-surfaces-is-an-enforcement-claim-not-a-mention)
  - [16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row](#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row)
- [17. Design Extensions Introduced During Execution](#17-design-extensions-introduced-during-execution-binding)
- [18. Cross-Tier Audit-Finding Triage](#18-cross-tier-audit-finding-triage-binding)

---

## 15. Discovery Scope Rigor (BINDING)

Discovery is the only phase where scope is cheap to measure correctly. After Discovery, every downstream artifact (Execution Input, task files, token estimates, success criteria) inherits the Discovery scope — and a wrong scope cascades through the entire plan.

### 15.1 Deterministic-bug scope MUST be counted by execution, not estimated

> [!constraint] Bugs with deterministic trigger conditions MUST be counted by running the identification query during Discovery
> When a bug has a deterministic trigger condition (alphabetical ordering, date
> range, specific column value, foreign-key state, or any evaluable predicate),
> the Discovery phase MUST run the identification query against the actual data
> store and persist the exact count and IDs. Estimating from a sample, a
> user-reported subset, or "looks like ~{N}" fails this rule.
>
> WRONG — Discovery declares "{N} confirmed-affected records" based on a
> user-reported sample. Plan documents and query templates use {N} throughout.
> Execution discovers the actual count is {M} (where M is materially larger
> than N). The scope increase requires user confirmation mid-session and
> invalidates row-count estimates in all downstream task files.
>
> CORRECT — Discovery writes and executes the identification query, persists the
> exact count and IDs in the Consolidated Context, and propagates the real count
> to every downstream estimate:
>
> ```sql
> SELECT f.{id_col}, f.{date_col}, d.{name_col} AS {dim_label}
> FROM {fact_table} f
> JOIN {dim_table} d ON d.{id_col} = f.{fk_col}
> WHERE f.{date_col} > '{date_value}'
>   AND f.{snapshot_col} != '{snapshot_value}';
> -- Returns: {row_count} rows (verified {YYYY-MM-DD})
> ```

> [!checklist] Discovery Scope Counting (Deterministic-Bug Plans)
> - [ ] Wrote the identification query (selection criteria explicit, not paraphrased)
> - [ ] Executed the identification query against the live data store during Discovery
> - [ ] Persisted the result count in the Consolidated Context
> - [ ] Persisted the actual IDs (or the exact query) in the Execution Input
> - [ ] Used the real count for all downstream estimates (row counts, token budgets, runtime estimates)

Applies to:
- Any plan where a bug has deterministic affected-row criteria
- Meta-Plan Discovery phases that analyze data corruption scope
- Execution Input extraction where row counts drive token estimates

### 15.2 Persist specific IDs, not just counts

> [!constraint] Discovery MUST persist specific IDs (or the deterministic identification query), not count-only placeholders
> When Discovery identifies a specific set of affected records, the Execution
> Input and downstream query templates MUST contain either the actual IDs or the
> exact identification query (with parameters). Count-only placeholders like
> `{N_record_ids}` force re-derivation at execution time and lose information
> about which records are in scope.
>
> WRONG — count-only placeholder; no one knows which records:
> ```sql
> WHERE record_id IN ({N_record_ids})
> ```
> Cost: every downstream task either re-runs the identification query (extra
> data-store round-trip per task) or guesses, risking off-by-one drift between
> Discovery and execution.
>
> CORRECT — list the IDs OR document the deterministic query that produces them:
> ```sql
> -- Option A: inline IDs (when ≤100 records)
> WHERE record_id IN (
>   '{id1}', '{id2}', ...
> )
>
> -- Option B: deterministic query (when >100 records or list would dominate the file)
> WHERE {deterministic_criterion}
>   AND {date_criterion};
> ```

When the ID list is too long for inline inclusion (>100 IDs), persist the identification query with exact parameters so execution can reproduce the list deterministically. The query itself becomes the canonical artifact — citing it removes ambiguity about scope.

Applies to:
- Any data-repair plan targeting specific records
- Meta-Plan Discovery phases that identify corruption scope
- Execution Inputs referencing record subsets by count

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
> - [ ] Each new parameter is mentioned in the sprint signoff under a "Design Extensions" sub-section (per the §16.3 exit-criteria-fidelity verbatim-quote conventions)

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
> 1. **Does NOT apply when un-authored artifacts are months out** — the Findings doc's pre-emptive flag can rot. Re-run a fresh cross-tier diff when the future sprint kicks off (per the §16.3 BLI-Cited Anchor Re-Verification clause). Pre-emptive flags expire.
> 2. **Does NOT apply when the upstream change is needed to unblock current code** — use the combo bucket above.
> 3. **Does NOT save work in token count, only in session-orchestration overhead** — each task still gets executed; the saving is in scaffolding effort, agent-dispatch coordination, and Recovery-file churn.
>
> Concrete trigger:
> 1. For each HIGH/MEDIUM finding, look up the affected item's downstream artifact status (downstream module authored? consumer code present? tests?).
> 2. If ALL downstream artifacts exist and are in deployed code → Remediation bucket (next sprint).
> 3. If ANY downstream artifact is in a planned-but-unauthored sprint → pre-emptive flag bucket (defer to that sprint's author).
> 4. The pre-emptive flag table goes in the Findings doc Part-2 (or an equivalent location near the MEDIUM dispositions); add it to the future sprint's Orchestration prerequisites.

---

## Scaffolding Templates (canonical paste-ready blocks)

> [!practice] Canonical Scaffolding Templates Live Inline in This Rule
> When scaffolding a Discovery phase or a sprint signoff task, paste the two
> blocks below verbatim — they are the canonical templates for §15.1 (Discovery
> identification-query block) and §16.3 (verbatim sprint-signoff checklist
> block). Maintaining them inline (rather than as sibling template files) keeps
> the template, the rationale, and the WRONG/CORRECT contrast in a single
> source.
>
> **Template 1 — Discovery identification-query block (§15.1).** Paste into the
> Consolidated Context Part covering scope counting; adapt SELECT/WHERE to the
> deterministic trigger:
>
> ```sql
> -- Discovery identification query (executed against live data store at Discovery time)
> SELECT f.{id_col}, f.{date_col}, d.{name_col} AS {dim_label}
> FROM {fact_table} f
> JOIN {dim_table} d ON d.{id_col} = f.{fk_col}
> WHERE {deterministic_trigger_condition};
> -- Returns: {row_count} rows (verified {YYYY-MM-DD})
> ```
>
> Persist the row count + verification date inline. Then propagate the count +
> ID list (or the query + parameters when >100 IDs) into every Execution Input
> and downstream task file (§15.2).
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

## Plan-Review Enforcement Summary

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following violations:

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Discovery scope estimated, not counted | Discovery output cites a deterministic-bug count without an inline identification query that was executed against the live data store | §15.1 |
| 2 | Count-only placeholder in Execution Input | A `{N_ids}` or `{N_records}` style placeholder appears in any task file's Required Context or query template without an accompanying ID list or deterministic query | §15.2 |
| 3 | Single-layer binding refinement | A binding refinement is mentioned in the Sprint Plan but not echoed as `> [!binding]` callouts in at least the Orchestration and the gated task file | §16.1 |
| 4 | "Surfaces" without enforceable check | A task body claims to "surface" a BLOCKING item but contains no numeric assertion, grep, source-introspection check, documentation-content check, or parametrized test mechanism | §16.2 |
| 5 | Signoff row count mismatch or vague row | A sprint signoff checklist's row count differs from the EI exit-criteria item count, or any row lacks a mechanical anchor, or any rename/substitution lacks a deviation annotation | §16.3 |
| 6 | BLI-cited audit anchor without re-verification or with bare-column grep | A Sprint Plan / Orchestration encodes BLI-cited bugs as mechanical-grep success criteria AND does NOT include a pre-flight re-verification step at session start, OR uses bare-column grep anchors when ≥2 tables in the audit scope share the column name | §16.3 |
| 7 | Undocumented design extension | A sprint signoff cites a parameter / threshold that does not appear in the original design spec AND has no inline What/Why/Source comment AND is not in the project's config catalog | §17 |
| 8 | Audit Findings doc lacks a pre-emptive flags table | A cross-tier audit's Findings doc enumerates HIGH/MEDIUM findings on items whose downstream artifacts are NOT all in deployed code AND lacks a pre-emptive flags table sectioning those findings into the Sprint-M Authoring bucket | §18 |

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md) (parent rule, §15 + §16 cross-references), [session-plan-requirements.md](session-plan-requirements.md) (Task File Template, signoff sections), [task-content-fidelity.md](task-content-fidelity.md) (Required Context fidelity, verify-before-cite).*
