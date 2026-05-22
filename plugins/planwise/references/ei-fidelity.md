---
description: EI fidelity across scaffolding tiers — source preservation, threshold alignment, citation propagation, count-claim discipline, token reconciliation
---

# EI Fidelity (Cross-Tier Preservation)

**Purpose:** Rules for preserving source research content as it traverses the planwise scaffolding tiers — from raw discovery (Tier 1) → consolidated context (Tier 2) → Execution Input (Tier 3) → task files → implementation → tests / lint / signoff.

> [!binding] Scope
> These rules apply to scaffolded plans (those produced via `/planwise plan --scaffold`). Standard execution plans without a Discovery phase have no EI tier and are out of scope. The 8-task scaffolding pipeline (Source Inventory → Tier 2 binning → EI synthesis → Opus design → Sprint Plan → task scaffolding → fidelity review) is the canonical pipeline these rules harden.

## Table of Contents

- [1. EI as Archival — Transform at Task Layer](#1-ei-as-archival--transform-at-task-layer)
- [2. Source Severity Vocabulary Preservation](#2-source-severity-vocabulary-preservation)
- [3. Threshold Alignment with Operational Dispatch Contract](#3-threshold-alignment-with-operational-dispatch-contract)
  - [3.1 Algorithm-Sprint Retention-Band Calibration](#31-algorithm-sprint-retention-band-calibration)
- [4. UNCONFIRMED Caveats — Four-Site Redundant Enforcement](#4-unconfirmed-caveats--four-site-redundant-enforcement)
- [5. Cross-Tier Duplicate Preservation](#5-cross-tier-duplicate-preservation)
- [6. Cross-Tier Citation Propagation to Implementation Surface](#6-cross-tier-citation-propagation-to-implementation-surface)
- [7. §-Citation Discipline — Cite, Do Not Restate](#7--citation-discipline--cite-do-not-restate)
- [8. Token Reconciliation Gate — Arithmetic Beats Summary](#8-token-reconciliation-gate--arithmetic-beats-summary)
  - [8.1 Recompute Prose-Stated Numerical Exemplars at Design Review](#81-recompute-prose-stated-numerical-exemplars-at-design-review)

---

## 1. EI as Archival — Transform at Task Layer

> [!constraint] When source vocabulary diverges from the target schema, the rename happens in the TASK FILE, not in the EI
> Apply the *EI-faithful, task-enforced transform* pattern when source research
> vocabulary differs from the final target schema:
>
> 1. **EI layer (archival):** preserve source as-extracted. No renames. Keep all
>    citations intact. The EI is the audit trail.
> 2. **Task file layer (implementation):** apply the transform explicitly.
>    Include:
>    - Rename instruction in Execution Steps
>    - Before/after grep in Success Criteria
>    - Cross-reference to the design decision document
> 3. **Orchestration layer (audit):** flag the transform in a `> [!gate]` or
>    `> [!constraint]` callout so reviewers know the divergence is intentional.
> 4. **Sprint Plan / Master Plan layer:** list the transform in success criteria
>    to propagate enforcement upward.
>
> WRONG — EI rewrites source naming to match final target. Audit trail lost —
> when a reviewer compares the EI to source, both files agree but neither
> matches the original research vocabulary.
>
> WRONG — task file silently renames without citing the design decision. Future
> maintainer cannot tell whether the rename was a mistake or an intentional
> transform.
>
> CORRECT — EI keeps source-as-extracted; task file declares the transform with
> a verifiable success criterion; Orchestration carries the transform note. The
> EI remains archival, the transform is auditable, and the final artifact is
> correct.

Red flags during fidelity review:

- EI rewrites source naming to match the final target (audit trail lost)
- Task file silently renames without citing a design decision (traceability lost)
- Design decision documented in only one layer (no redundant enforcement)

---

## 2. Source Severity Vocabulary Preservation

> [!constraint] Severity / status / category tags MUST be preserved exactly as the source uses them
> Force-fitting source vocabulary into a canonical scheme is a silent fidelity
> defect — the EI looks fine but no longer matches the source when an auditor
> diffs them.
>
> WRONG — source files use a project-specific vocabulary (e.g., `{SOURCE_SEVERITY_TAG_A}`,
> `{SOURCE_SEVERITY_TAG_B}`, `{SOURCE_SEVERITY_TAG_C}`); EI rewrites to a
> different canonical scheme (e.g., `BLOCKING / HIGH / MEDIUM / LOW`). The
> mapping is lossy and the EI no longer reflects the source.
>
> CORRECT — quote source tags verbatim. Provide a short source-to-project-
> vocabulary mapping in the EI's header section so unfamiliar readers can
> interpret without losing fidelity.

How to apply:

1. In the EI's Open Questions section and any severity-tagged tables, quote the source tag verbatim.
2. In the EI's header (or a glossary subsection), provide a source-vocabulary-to-project-vocabulary mapping table.
3. In task-file templates, phrase fidelity checkpoints as "preserve source severity tag" rather than "find a `{specific tag}` tag." Allow for the possibility that the source uses a different scale.
4. Flag severity-vocabulary mismatches during the inventory task so downstream tasks know to preserve source terms.

Template phrasing for fidelity checkpoints: "most-severe tag in source" rather than a vocabulary mandate.

Red flags:

- EI uses canonical tags for items that source files tagged differently
- EI Open Questions section has tags not traceable to source files
- Template fidelity checks mandate a vocabulary without checking if source uses it

---

## 3. Threshold Alignment with Operational Dispatch Contract

> [!constraint] Hard-number thresholds in task-file templates MUST match the operational dispatch contract
> When a task-file template contains a hard-number threshold (retention floor,
> fidelity %, line-count ratio), that threshold MUST match the operational
> contract established by:
>
> 1. The **spawn prompt** when the orchestrator dispatches the task
> 2. The **upstream inventory task** that sets measurable baselines
> 3. The **Sprint Plan** success criteria that gate completion
> 4. The **Master Plan** binding enforcement policies
>
> If these sources diverge, the operational contract (what was dispatched
> against) wins over template boilerplate. Template conflicts are lessons to
> refine the template, not excuses to fail the task.
>
> WRONG — fidelity-review task template references "{template_threshold}%
> auto-reject" threshold; operational contract (Source Inventory + Sprint Plan +
> spawn prompt) sets a {operational_floor}% floor. Mechanically applying the
> template bar would auto-reject fidelity-correct work.
>
> CORRECT — fidelity-review task treats the operational contract as
> authoritative; the template's hard number is documented as a future
> template-refinement candidate, not used as a pass/fail gate.

Structural fix for future templates:

- Reference the source-of-truth (e.g., "floor as recorded in `{InventoryTaskOutputPath}`") rather than hard-coding numbers
- State fidelity checkpoints in terms of substance (spot-check items, compression signals) rather than line-count ratios
- Reserve hard numbers for true auto-reject cases

Red flags during template authoring:

- Two different retention percentages in the same task file
- Threshold in task file does not match threshold in Sprint Plan
- "Floor" defined without pointing to the source that sets it

---

### 3.1 Algorithm-Sprint Retention-Band Calibration

> [!constraint] Algorithm-sprint EIs are calibrated against an algorithm-specific retention band; retention >100% MUST be checked against the legitimate-driver checklist BEFORE it is flagged as bloat
> Retention (output line count ÷ source line count) is the cross-tier fidelity
> signal for an Execution Input. The default 80–120% band is sprint-type-agnostic.
> Algorithm sprints legitimately exceed 100% retention: preserved formula notes,
> pseudocode, and cross-tier duplicate annotations all add lines without adding
> drift. Applying the generic band to an algorithm-sprint EI auto-rejects
> fidelity-correct work.
>
> When a fidelity-review task computes retention >100% for an algorithm sprint,
> it MUST first check the legitimate-driver checklist; bloat is flagged only
> after a non-legitimate driver surfaces.
>
> Legitimate-driver checklist:
>
> | Driver | Adds lines? | Legitimate? |
> |--------|-------------|-------------|
> | Cross-tier duplicate notes (method signatures restated in EI body and in the cross-references section) | YES | YES — preserves verifiability |
> | Algorithm pseudocode | YES | YES — preserves implementation guidance |
> | Duplicate formula tables (one in body, one in tests section) | YES | YES — preserves test-source traceability |
> | Verbose section headers / explanatory prose | YES | Conditional — flag if not domain-justified |
> | Restated count claims (numerical exemplars cited multiple times) | YES | YES — preserves verification anchors |
> | Reworded verbatim source | YES | NO — counts as drift, not legitimate retention |
>
> Band interpretation:
>
> | Retention | Action |
> |-----------|--------|
> | < 80% | Investigate as GAP — content likely lost |
> | 80–100% | Standard band; PASS unless other signals fire |
> | 100–115% | Algorithm-sprint normal; check the legitimate-driver checklist before flagging |
> | 115–120% | Border zone; require explicit justification in the EI preamble |
> | > 120% | Likely bloat or duplicated source; investigate |
>
> Sprint-type calibration:
>
> | Sprint type | Expected retention band |
> |-------------|-------------------------|
> | Schema / harmonization | 80–105% |
> | Algorithm | 95–120% |
> | Integration | 85–110% |
> | Pure discovery | 70–95% (Discovery → EI compresses) |
>
> WRONG — a fidelity-review task computes 112% retention for an algorithm-sprint
> EI and flags it as bloat against the generic band, without checking what drove
> the extra lines. Those lines are preserved pseudocode and duplicate formula
> tables; the flag auto-rejects fidelity-correct work and burns a remediation
> cycle.
>
> CORRECT — the fidelity-review task reads the Sprint Plan Objective, recognises
> algorithmic / numerical-design work, applies the 95–120% algorithm band, and
> runs the legitimate-driver checklist against the extra lines. Pseudocode and
> duplicate formula tables are legitimate drivers → PASS. Only a non-legitimate
> driver (reworded verbatim source) converts the result to a bloat finding.

Apply order: when a fidelity-review task computes retention >100% for an algorithm sprint, FIRST check the legitimate-driver checklist; flag bloat only after a non-legitimate category surfaces.

---

## 4. UNCONFIRMED Caveats — Four-Site Redundant Enforcement

> [!constraint] UNCONFIRMED / UNVERIFIED / "deprecated" / "requires local download" caveats MUST appear in ≥4 reinforcing sites across the EI + task layers
> Single-site mentions of caveated items are easy to overlook during downstream
> implementation. Redundant enforcement is protective: any single layer might be
> misread or dropped, but four together make the caveat auditable and the
> enforcement mechanical.
>
> The four reinforcing sites:
>
> 1. **EI primary section** where the item first appears (e.g., contract / field
>    inventory table) — tag preserved verbatim
> 2. **EI Data Quality Caveats subsection** — restated with downstream
>    enforcement instruction (what to do / not do)
> 3. **Session Orchestration success criterion** — binary pass/fail on the
>    enforcement
> 4. **Task file Required Context or Success Criteria** — specific agent
>    instruction with verification step
>
> WRONG — `{api_field}` UNCONFIRMED appears only in the EI's contract inventory
> table. The Data Quality Caveats subsection does not mention it; no
> Orchestration success criterion enforces exclusion; the task file does not
> point at the caveat. An implementer reading only the contract inventory would
> mistakenly include `{api_field}` in the `{db_table}` DDL.
>
> CORRECT — `{api_field}` UNCONFIRMED appears in:
>
> 1. EI contract inventory table — row marked "UNCONFIRMED — not in API response"
> 2. EI Data Quality Caveats subsection — explicit instruction: "Do not include
>    in `{db_table}` DDL"
> 3. `{session_name}` Orchestration — success criterion: "DDL omits `{api_field}`"
> 4. `{task_name}` task file — Required Context points to the Data Quality
>    Caveats subsection
>
> The redundancy is the reason the caveated item does not leak into final DDL.

How to apply during scaffolding:

- The EI-drafting task should scan the binning bins for verification-status markers and ensure each appears in ≥2 EI sections
- The design task should route each caveated item to a specific session/task so the Orchestration / task-file authors can add the success criterion
- The fidelity-review task should spot-check one UNCONFIRMED item and verify the four-site coverage

Red flags during review:

- UNCONFIRMED item appears only in the EI's primary section (Data Quality Caveats subsection missing the entry)
- Source file says "unverified" but EI shows the field as normal (verification status dropped)
- Design document lists the table/field but no session/task is tagged as enforcing the exclusion

---

## 5. Cross-Tier Duplicate Preservation

> [!constraint] Findings cited in multiple source files MUST carry the dual/triple/N-citation in the EI as an explicit in-content note
> When a finding appears in N source files (e.g., a finding cited in Tier 1
> file A, Tier 1 file B, AND Tier 2 consolidated file C), the EI MUST preserve
> all N citations with an explicit `**Note (cross-tier duplicate preserved):**`
> line listing every source file and line range. The note converts an expensive
> verification step (re-read every source) into a single grep.
>
> WRONG — single citation hides the parallel mentions:
>
> ```markdown
> ### §X.Y {Finding Title}
>
> [Source: T{tier}-{N} {FileName} line {L}]
> > "{quoted finding}"
> ```
>
> A reviewer diffing only `T{tier}-{N} {FileName}` would miss the parallel
> citations in the other source files.
>
> CORRECT — explicit cross-tier note listing every source:
>
> ```markdown
> ### §X.Y {Finding Title}
>
> > "{quoted finding text}"
> > — {source attribution}
>
> **Note (cross-tier duplicate preserved):** This finding is cited in
> T{tier_1}-{N1} {FileName_1} (line {L1}), T{tier_1}-{N2} {FileName_2}
> (line {L2}), T{tier_1}-{N3} {FileName_3} (line {L3}), AND in
> T{tier_2}-{N4} {FileName_4} (lines {L4a-L4b}). All {count} citations
> preserved.
> ```

> [!template] Cross-Tier Duplicate Note
> ```
> **Note (cross-tier duplicate preserved):**
> {finding summary} — cited in {file1 line range}, {file2 line range}, ...,
> {fileN line range}. All N citations retained.
> ```

Applies to:

- Every Meta/Scaffold pipeline where discovery content spans multiple tiers
- Multi-source specifications where "cited N times" is load-bearing evidence (weights, findings, formulas, stabilization values)

NOT applicable when only a single source cites the finding — the note adds no value.

---

## 6. Cross-Tier Citation Propagation to Implementation Surface

> [!constraint] Cross-tier citations preserved in the EI MUST propagate into algorithm/code docstrings, lint gates, test fixtures, and signoff checklists
> Cross-tier citation preservation is a refactor-drift firewall. A future
> refactor that silently changes a weight or threshold would pass unit tests and
> lint if those gates do not check the citation text itself. The EI preserves
> the citation as semantic provenance; downstream artifacts MUST carry it
> forward to the boundary where drift would escape.
>
> Four enforcement surfaces, all required:
>
> 1. **Algorithm/helper docstring** — function consuming the cited value has a
>    docstring requirement citing BOTH (or all N) source locations verbatim.
>    Example: "per EI §X.Y Note: `{citation_author}` `{value}` from
>    `{SourceFile_1}` lines `{L1-L2}` AND `{SourceFile_2}` `{section}`."
> 2. **Lint gate grep** — lint task grep MUST find both citation tokens in the
>    implementation file. Example: `grep -n "{token_1}\|{token_2}" {src/module/file.ext}`
>    returns matches.
> 3. **Test fixture comment** — unit test using a value derived from the cited
>    source includes an inline comment restating the cross-tier citation; refactor
>    drift that silently changes the value fails the test semantically (not just
>    numerically).
> 4. **Signoff checklist** — sprint signoff task has a dedicated line-item
>    verifying cross-tier citation preservation greps pass.
>
> WRONG — EI preserves a dual citation; task file generating the docstring only
> cites the EI section reference (collapses to single ref). Test fixtures use
> the cited value with no comment tying input to the dual-source finding. A
> refactor changing the value silently passes all gates.
>
> CORRECT — task file scaffolding propagates the dual citation into all four
> surfaces. Refactor drift either fails a docstring lint, a citation-token grep,
> a test-fixture comment audit, or the signoff grep.

How to apply during the task-scaffolding step:

For every cross-tier duplicate identified in an EI Note (per §5 above), the task scaffolder MUST produce:

- A docstring requirement in the consuming code's task file
- A lint-gate grep in the lint task's verification step
- A test fixture with inline citation comment
- A signoff checklist line-item

If any of the four is missing, the propagation is incomplete and the cross-tier preservation is one refactor away from silent drift.

---

## 7. §-Citation Discipline — Cite, Do Not Restate

> [!constraint] Task prose MUST cite verbatim EI content by §-reference; do NOT inline-restate counts, formulas, or weight vectors
> When a task requires the agent to consume verbatim content (formulas, column
> lists, stabilization thresholds, weight vectors), the task file MUST cite the
> §ref and direct the agent to read the content AT the cited section. Restating
> the content inline (in prose or numbered steps) creates count-claim drift: if
> the EI is later edited, every task file that restated the values is silently
> wrong.
>
> WRONG — count claims and weights restated inline:
>
> ```markdown
> ## Execution Steps
>
> 1. Implement `{symbol}` with {N} components and weights `{weight_vector}`
>    summing to 1.0 per EI §X.Y.
> 2. Use `{input_field_1}` for w1 and `{input_field_2}` for wN.
> ```
>
> Cost: if EI §X.Y later changes (sensitivity analysis adds an N+1th component),
> every task file that restated "{N} components" with old weights is silently
> contradicting the source.
>
> CORRECT — §-citation discipline:
>
> ```markdown
> ## Required Context
>
> | Priority | File | Purpose |
> |----------|------|---------|
> | 1 | `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` — §X.Y {formula name}
> |   | (verbatim weight vector), §Z.W {related logic} | Source of truth for
> |   | {feature} implementation |
>
> ## Execution Steps
>
> 1. Read EI §X.Y for the {formula name} verbatim (weight vector is AT §X.Y).
> 2. Implement `{symbol}` per §X.Y formula block.
> 3. Apply §Z.W {related logic}.
> ```

When restatement IS acceptable:

- The restated value is MORE authoritative than the cited source (rare — typically the design task itself producing the EI for the first time).
- The restatement appears EXACTLY ONCE (e.g., in the EI itself).
- The prose explicitly claims "as of {YYYY-MM-DD}; verify against §X.Y current state" — i.e., dated snapshot with verification pointer.

Count-claim reconciliation grep — hunt for drift risk in scaffolded plans:

```bash
{consumer's grep command} -nE '(weights?|components?|columns?|metrics?|fields?) (with )?[0-9]+' <sprint-root>/**.md
# Every match should either be in the EI itself OR cite § where the count is authoritative.
```

NOT applicable when the task is explicitly producing the verbatim content for the first time (e.g., the EI-drafting task itself).

---

## 8. Token Reconciliation Gate — Arithmetic Beats Summary

> [!constraint] When a design task produces both a summary table AND per-task arithmetic, the arithmetic is authoritative; divergence MUST be flagged explicitly, not silently reconciled
> A design task (T05-equivalent in an 8-task scaffolding pipeline) that produces
> a sprint's session/task breakdown typically renders both a high-level Sessions
> Overview table and a detailed §-Token-Reconciliation block with per-task
> arithmetic. If those diverge — and they often do, because summary tables get
> written from drafts that don't survive the design task's final per-task
> balancing — the arithmetic wins.
>
> Divergence is not a mistake to be silently corrected; it is a signal that
> downstream tasks (Sprint Plan, task scaffolding) MUST be directed to use the
> arithmetic and ignore the summary.
>
> WRONG — silent reconciliation, no flag:
>
> ```markdown
> ## §2 Sessions Overview
>
> | Session | Est. Tokens |
> |---------|-------------|
> | Session-01 | ~{old_value_A}K |   ← outdated; not flagged
> | Session-02 | ~{old_value_B}K |
>
> ## §10 Token Reconciliation
> Sessions sum to ~{summary_total}K (uses values above).
> ```
>
> Cost: downstream tasks (Sprint Plan / task scaffolding) may pick either
> rollup; the error compounds through sprint planning.
>
> CORRECT — explicit divergence flag in the reconciliation block:
>
> ```markdown
> ## §10 Token Reconciliation
>
> Authoritative per-task arithmetic (use these values in downstream tasks):
>
> Session-01: {a1}K + {a2}K + {a3}K + ... = **{authoritative_A}K**
> Session-02: {b1}K + {b2}K + {b3}K + ... = **{authoritative_B}K**
> Sprint total: {authoritative_A}K + {authoritative_B}K = **{sprint_total}K**
>
> > [!binding] Divergence note
> > §2 Sessions Overview shows outdated rollups ({old_value_A}K /
> > {old_value_B}K) from earlier draft. Sprint Plan and task scaffolding
> > MUST use §10 values. §2 will be fixed retrospectively once Sprint
> > Plan is written.
> ```

Downstream propagation check (Sprint Plan / task scaffolding tasks MUST apply):

1. Read the design task output fully, including the reconciliation block.
2. If the reconciliation block flags divergence from the summary, use the reconciliation values.
3. Record in task Key Findings: "Token reconciliation uses §10 authoritative values: `{authoritative_A}K / {authoritative_B}K`."

Fidelity-review verification: a designated checkpoint confirms per-task estimates in task files sum to Orchestration totals, which sum to the Sprint total, which matches the design task's reconciliation block.

NOT applicable when there is only one token-estimate layer (no divergence possible).

---

### 8.1 Recompute Prose-Stated Numerical Exemplars at Design Review

> [!constraint] Design-review tasks MUST recompute every prose-stated numerical exemplar from its formula — never pass prose values through to implementation
> When an EI or Sprint Plan provides numerical exemplars meant to become
> regression tests, doctests, or success-criterion thresholds (e.g.,
> "x = 0.051 → y ≈ 0.952"), the design-review task that locks function
> signatures and doctests MUST recompute every exemplar from its formula and
> surface any divergence as a [BLOCKING] open question. It MUST NOT pass the
> prose values through to implementation tasks unverified.
>
> Prose exemplars drift from exact arithmetic. Recomputing during the design
> phase costs seconds; catching the drift at implementation time costs one extra
> subagent dispatch plus a doctest correction plus an EI errata note.
>
> **Tolerance:** flag any mismatch greater than 1e-9 as a [BLOCKING] open question.
>
> WRONG — the EI states "input 0.051 → output ≈ 0.952"; the Sprint Plan inherits
> the value verbatim; the implementation-time subagent computes
> `1 / (1 + 0.051) = 0.95147` → 0.951, not 0.952. The correction lands late as a
> doctest fix plus an EI errata note.
>
> CORRECT — the design-review task recomputes the exemplar during planning,
> surfaces "exemplar 0.952 → actual 0.951; flag [BLOCKING]", and the
> implementation task receives the corrected value.
>
> Template integration: a design-review task that locks function signatures and
> doctests MUST carry an explicit Execution Step — "Recompute every prose-stated
> numerical exemplar; flag mismatches > 1e-9 as a [BLOCKING] open question."

This recompute step is the algorithm-sprint extension of the §8 reconciliation gate: §8 reconciles token-estimate arithmetic; §8.1 reconciles every other prose-stated numerical exemplar an algorithm-sprint EI carries.

---

*Cross-references: [session-planning-protocol.md](session-planning-protocol.md) (plan hierarchy and naming), [session-plan-requirements.md](session-plan-requirements.md) (Required Context and task-file structure), [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context fidelity, §9.B verify-before-cite).*
