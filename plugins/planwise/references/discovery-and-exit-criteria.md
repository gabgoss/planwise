---
description: Discovery scope rigor (deterministic-bug counts, ID persistence) and cross-layer enforcement of exit-criteria fidelity (binding callout echo, "surfaces" enforceability, signoff verbatim quoting)
---

# Discovery Scope Rigor & Exit-Criteria Fidelity

**Purpose:** Five binding rules covering two related plan-fidelity concerns — Discovery scope rigor (§15) and cross-layer enforcement of exit-criteria (§16). Each rule has been re-derived in independent sessions; review-cycle tokens are wasted relitigating the same five issues.

This file is the §15 + §16 expansion of [session-planning-protocol.md](session-planning-protocol.md). It was extracted into a sibling file to keep both rule files under the project's 500-line limit. Read it before authoring Discovery-phase Consolidated Context, Execution Inputs that name affected records, multi-layer binding refinements, BLOCKING-coverage task files, or sprint signoff checklists.

## Table of Contents

- [15. Discovery Scope Rigor](#15-discovery-scope-rigor-binding)
  - [15.1 Deterministic-bug scope MUST be counted by execution, not estimated](#151-deterministic-bug-scope-must-be-counted-by-execution-not-estimated)
  - [15.2 Persist specific IDs, not just counts](#152-persist-specific-ids-not-just-counts)
- [16. Cross-Layer Enforcement & Exit-Criteria Fidelity](#16-cross-layer-enforcement--exit-criteria-fidelity-binding)
  - [16.1 Binding refinements MUST be echoed as `> [!binding]` callouts across plan layers](#161-binding-refinements-must-be-echoed-as--binding-callouts-across-plan-layers)
  - [16.2 "Surfaces" is an enforcement claim, not a mention](#162-surfaces-is-an-enforcement-claim-not-a-mention)
  - [16.3 Sprint signoff MUST quote EI exit criteria verbatim with one mechanical anchor per row](#163-sprint-signoff-must-quote-ei-exit-criteria-verbatim-with-one-mechanical-anchor-per-row)

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

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md) (parent rule, §15 + §16 cross-references), [session-plan-requirements.md](session-plan-requirements.md) (Task File Template, signoff sections), [task-content-fidelity.md](task-content-fidelity.md) (Required Context fidelity, verify-before-cite).*
