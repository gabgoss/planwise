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
  - [8.2 Verbatim-Copy Task Line-Count Estimates Exclude EI Scaffolding Metadata](#82-verbatim-copy-task-line-count-estimates-exclude-ei-scaffolding-metadata)
- [9. EI Completeness — Three-Axis Scope Coverage](#9-ei-completeness--three-axis-scope-coverage)
  - [9.1 Multi-Sprint Cumulative File-Touch Reconciliation](#91-multi-sprint-cumulative-file-touch-reconciliation)
  - [9.2 Cluster Enumeration in EI Repoint Maps](#92-cluster-enumeration-in-ei-repoint-maps)
  - [9.3 Audit-Grep-Table Coverage — Repair Scope ⊇ Verification Scope](#93-audit-grep-table-coverage--repair-scope--verification-scope)
- [10. Source-Promise Integrity — Body⇄Citation Presence + Pre-Extraction Verification](#10-source-promise-integrity--bodycitation-presence--pre-extraction-verification)
  - [10.1 Body⇄Citation Presence (Consolidated Context Parts)](#101-bodycitation-presence-consolidated-context-parts)
  - [10.2 Pre-Extraction Verification Protocol (Task Execution)](#102-pre-extraction-verification-protocol-task-execution)
  - [10.3 Fallback Hierarchy (When the Cited Section Is Absent or Divergent)](#103-fallback-hierarchy-when-the-cited-section-is-absent-or-divergent)
- [11. Verbatim-Block Behavioral Freshness — A Wording Freeze Is Not a Fact Freeze](#11-verbatim-block-behavioral-freshness--a-wording-freeze-is-not-a-fact-freeze)

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

### 8.2 Verbatim-Copy Task Line-Count Estimates Exclude EI Scaffolding Metadata

> [!constraint] When a task copies verbatim content from an EI section, the success-criteria line-count range MUST be computed from the marked body block, NOT from the surrounding EI section
> When the task instruction is "copy verbatim from EI Section N", the EI section
> typically embeds scaffolding metadata (Substitution Log, EI-only headers,
> EI-only Notes, source-vocabulary glossaries) that the task instructions
> explicitly strip from the written file. A line-count range computed against
> the full EI section overcounts by the metadata length, and the agent's `wc -l`
> smoke check fires false positives on fidelity-correct work.
>
> A 10%+ `wc -l` delta is meant to signal one of two conditions — content
> fidelity loss (real bug, executor MUST HALT) or an estimate defect (this
> rule) — and cannot do both jobs reliably when estimates routinely include
> metadata the task strips.
>
> WRONG — task success criteria pegged to the EI section length:
>
> ```markdown
> ## Success Criteria
> - [ ] File line count is ~415-445 lines  ← matches EI §X
>       (verbatim body + Substitution Log + EI Note + EI-only header ≈ 430)
> ```
>
> Cost: agent writes the verbatim body correctly (~367 lines, body only); `wc -l`
> reports -48 vs the documented range; agent flags the content-fidelity gate
> and burns investigation cycles before concluding the estimate was stale.
>
> CORRECT — estimate computed against the marked body block only:
>
> 1. **Mark the verbatim body in the EI.** The EI section authoring the
>    verbatim block MUST mark its body precisely — explicit start- and end-line
>    delimiters (e.g., "Body Content runs from `# {Heading}` through
>    `*{Closing italic line}*`") or an unambiguous callout demarcating the
>    block.
> 2. **Count the marked body, not the EI section.** When writing the task's
>    success-criteria line-count range, count ONLY the marked body lines (plus
>    any YAML frontmatter the task adds), NOT the EI metadata surrounding it
>    (Substitution Log, EI-only Notes, glossaries, source-vocabulary tables).
> 3. **Tolerance band.** ±3-5 lines for renderer differences (LF vs CRLF,
>    trailing newline). A 10%+ delta is NOT acceptable as a smoke pass — it
>    indicates either an EI-metadata leak (real bug; executor MUST HALT and
>    investigate) or a stale estimate (this rule; fix the EI's body markers
>    and recompute the range).
>
> ```markdown
> ## Success Criteria
> - [ ] File line count is ~360-380 lines  ← marked body block only
>       (matches the content the task instructions actually require)
> ```

How to apply during EI authoring:

1. For every "copy verbatim from §X" task, the EI's §X MUST contain explicit body delimiters (start-line + end-line markers, or a callout demarcating the verbatim block).
2. The task-scaffolding step counts the delimited body block — not the §X section length — when emitting the task's `wc -l` smoke-check range.
3. If §X embeds Substitution Logs, EI-only Notes, or EI-only headers, those lines are excluded from the count by construction (they fall outside the marked body).
4. The Token Reconciliation Gate (§8) and this rule combine: §8 reconciles totals across the planning tiers; §8.2 reconciles per-task verbatim line-counts against the body-only scope the task actually writes.

Red flags during review:

- Task success-criteria `wc -l` range matches the EI section line count rather than the marked body-block length.
- EI section authoring a verbatim block has no explicit body delimiters — body and metadata are visually intermixed.
- Task-runner Status Block reports a 10%+ negative line-count delta on a verbatim-copy task whose downstream content-fidelity verification PASSes.

NOT applicable when the task is producing transformed content (extraction + restructure), where line counts are expected to diverge from any single source section.

---

## 9. EI Completeness — Three-Axis Scope Coverage

> [!binding] EI Completeness — what the EI scopes IS the work
> When the Scaffolding agent extracts an EI from a multi-sprint plan or from an audit, the EI defines the entire scope the executor will be authorized to touch. Any in-scope work the EI does NOT enumerate becomes one of three failure modes at execution time:
>
> 1. **Wrong-baseline edits** — executor writes against a pre-plan baseline that has since shifted, duplicating or HALTing on anchor-quote mismatch.
> 2. **Mid-execution scope-expansion gates** — executor detects the gap, pauses for `AskUserQuestion`, blocks on user approval to extend scope.
> 3. **Exit-gate failure with no in-sprint remediation path** — final verification finds defects in files no upstream task was authorized to edit; the sprint cannot close.
>
> Three completeness axes prevent each mode. Apply all three when authoring an EI; flag any EI that omits one.

The three axes are independent — an EI may pass one and fail another. The §9.1/§9.2/§9.3 subsections below define each axis and its WRONG/CORRECT contract. The companion `/planwise review` checks (in `agents/plan-reviewer.md` under the EI Reviewer role) enforce them mechanically.

---

### 9.1 Multi-Sprint Cumulative File-Touch Reconciliation

> [!constraint] Sprint-N's EI "Current state" anchor blocks MUST reflect POST-prior-sprint state, not pre-plan baseline
> When a multi-sprint plan touches the same file across two or more sprints, the Scaffolding agent that extracts Sprint-N's EI from upstream sources (Consolidated Context parts, Tier-2 binning outputs, audit documents) MUST reconcile the cumulative deltas from sprints 1..N-1 before writing the per-sprint EI "Current state" blocks.
>
> **Identity:**
>
> - Sprint-N `Current state` block = pre-plan baseline + Σ deltas from sprints 1..N-1
> - Sprint-N `Proposed change` block = ONLY the delta this sprint adds
>
> WRONG — Sprint-N EI extracts "Current state" verbatim from a Consolidated Context part that predates the plan's own Sprint-1, declaring a pre-plan baseline:
>
> ```markdown
> **Current state** (existing rows 1-10, last row quoted for anchoring):
> | 10 | ...row-10 anchor... |
>
> **Proposed change** — APPEND 8 new rows after row 10:
> | 11 | ...new row... |
> | 12 | ...new row... |
> ...
> ```
>
> If Sprint-1 already appended rows 11-15 to this file, naive Sprint-N execution either (a) duplicates rows 11-15 (writing them twice), or (b) HALTs at the anchor-quote check because the file now has 15 rows, not 10.
>
> CORRECT — Sprint-N EI declares the post-prior-sprint baseline and a Cross-Sprint Precondition gate:
>
> ```markdown
> > [!gate] Cross-Sprint Precondition
> > This {N}-row baseline assumes Sprint-{M} Task {prior_task_id} has completed.
>
> **Current state — POST Sprint-{M} Task {prior_task_id} ({N} rows; rows {M+1}-{N} already present)**:
> | {row-N} | ...current anchor... |
>
> **Proposed change** — APPEND ONLY {remaining_count} rows ({N+1}-{N+remaining}):
> | {row-N+1} | ...new row... |
> ```
>
> And the matching task file (Sprint-N's first task that edits this file) MUST include a Step-1 prerequisite grep gate verifying Sprint-M's marker is present in the file. If the marker is missing, HALT — Sprint-M is incomplete and Sprint-N cannot run against an outdated baseline. See `templates/task-file.md` "Cross-Sprint Prerequisite Grep Gate" pattern.

How to apply during scaffolding:

1. Build a Cross-Sprint File-Touch matrix: for each file edited by the plan, list every (sprint, session, task) that touches it.
2. For each file edited by ≥2 sprints, walk the sprints in order. For each later sprint, the EI "Current state" anchor block MUST reflect the post-prior-sprint state, not the source's pre-plan snapshot.
3. The Sprint Plan for the later sprint SHOULD include a `## Cross-Sprint File Touches` section listing the file and the prior sprint that already edited it (see `templates/sprint-plan.md`).
4. The task file for the first session that touches a previously-touched file MUST include a Step-1 prerequisite grep gate.

Red flags during review:

- Sprint-N EI "Current state" anchor quotes content from a Consolidated Context part dated before Sprint-1.
- Sprint-N "Proposed change" overlaps numerically with a delta already applied by Sprint-M < N.
- Sprint-N task file edits a cross-sprint-touched file with no Step-1 prerequisite grep.

---

### 9.2 Cluster Enumeration in EI Repoint Maps

> [!constraint] EI repoint maps MUST enumerate every row of an audit-identified cluster — listing only the canonical example forces a mid-execution scope-expansion gate
> When an audit identifies a range cluster (multiple dangling anchors all belonging to the same canonical range, the same misnumbered series, or the same defect-class set), the EI repoint map MUST enumerate every row of the cluster — with explicit source anchor and target anchor per row. Implicit scope expansion via parenthetical hints ("canonical §X.Y.{first}-{last}") is forbidden.
>
> WRONG — list only the canonical mis-number; assume executor will infer the cluster:
>
> ```markdown
> | line {L_canonical} (Check {N_canonical}) | `§X.Y.{misnumbered_canonical}` | `§X.Y.{canonical_target}` (the §X.Y.{misnumbered_canonical} mis-number → canonical §X.Y.{first}-{last}) |
> ```
>
> Cost: the executor running the mechanical repoint task hits dangling anchors at lines `{L_2}`, `{L_3}`, `{L_4}` that the EI map does NOT cover, pauses for `AskUserQuestion`, and waits for user approval to scope-expand. The repoint is no longer mechanical.
>
> CORRECT — enumerate every row of the audit-identified cluster, with explicit per-row target:
>
> ```markdown
> | line {L_1} (Check {N_1}) | `§X.Y.{misnumbered_1}` | `§X.Y.{target_1}` |
> | line {L_2} (Check {N_2}) | `§X.Y.{misnumbered_2}` | `§X.Y.{target_2}` |
> | line {L_3} (Check {N_3}) | `§X.Y.{misnumbered_3}` | `§X.Y.{target_3}` |
> | line {L_4} (Check {N_4}) | `§X.Y.{misnumbered_4}` | `§X.Y.{target_4}` |
> ```
>
> If the cluster has a sequential canonical mapping (`§X.Y.{m_1}→§X.Y.{t_1}`, `§X.Y.{m_2}→§X.Y.{t_2}`, ...), state the mapping rule explicitly in EI prose ABOVE the table. The prose makes the mapping auditable; the per-row enumeration makes it mechanical.

Why mechanical tasks must not require inference:

The repoint task is mechanical — open file, find anchor, change anchor, move on. Mechanical tasks must not require the executor to interpret which other rows of an audit's range table are also in scope. Either the EI is complete (executor proceeds mechanically) or the EI carries an explicit out-of-scope marker for the rows it deliberately omits. Implicit scope expansion based on parenthetical hints ("canonical §X.Y.{first}-{last}") is ambiguous and one mid-execution-pause away from incorrect scope.

How to apply during scaffolding:

1. Open the audit's range row and enumerate every file:line cited.
2. For each line, identify the specific check and the specific anchor used (Source field, Fix-pointer).
3. Emit one repoint-map row per cited line, with the explicit source anchor + target anchor.
4. If the cluster has a sequential canonical mapping, state it explicitly in EI prose above the table.

How to apply during execution:

If the executor finds a dangling anchor that the EI map does NOT cover, the executor MUST surface the gap before applying any silent extrapolation. Mid-execution `AskUserQuestion` is the correct fallback — but the better outcome is that the EI map is complete to begin with.

Red flags during review:

- EI repoint map has fewer rows than the audit's cited-line count for the same cluster.
- EI prose references a "canonical range" without enumerating every line in that range.
- Downstream verification task references anchors no upstream repoint task enumerated.

---

### 9.3 Audit-Grep-Table Coverage — Repair Scope ⊇ Verification Scope

> [!constraint] When an audit lists a multi-file defect-class grep table, the EI MUST scope explicit repair tasks for EVERY file in the table — not the high-visibility subset
> An exit-gate verification task ("0 defects across N files") is only achievable if every one of those N files was scoped for repair somewhere upstream. If the EI scopes repair in M < N files and verification across N, the exit gate is structurally guaranteed to fail at the verification task. The verification task has no remediation hook — its mandate is "do not edit."
>
> WRONG — EI scopes repair only to the "primary" or "most-visible" files in the audit's defect-class table; other files appear only in the final-sweep "verification only" task:
>
> ```markdown
> # EI §1: repoint citations in {primary_file_1}                       ← repair
> # EI §2: repoint citations in {primary_file_2}                       ← repair
> # EI §5: verify ALL FOUR files have 0 dangling (verification only)   ← verify scope wider than repair scope
> ```
>
> Cost: `{secondary_file_1}` and `{secondary_file_2}` were in §5's verification scope but never in §1-§2's repair scope. They retain their dangling citations. The §5 sweep FAILS. Exit gate FAILS. No in-sprint path to remediate because no task was authorized to edit them. The sprint can complete its task work and still fail its exit gate.
>
> CORRECT — every file in the audit's defect-class grep table gets an explicit repair task; the final sweep is then a true verification:
>
> ```markdown
> # EI §1: repoint citations in {primary_file_1}                       ← repair
> # EI §2: repoint citations in {primary_file_2}                       ← repair
> # EI §3: repoint citations in {secondary_file_1}                     ← repair (was missing)
> # EI §4: repoint citations in {secondary_file_2}                     ← repair (was missing)
> # EI §5: verify all four files have 0 dangling (verification only)   ← verify scope = repair scope
> ```
>
> Result: §5 sweep finds 0 dangling because §1-§4 covered every file. Exit gate is achievable; the verification task confirms the work.

The invariant:

> Repair scope ⊇ Verification scope.
>
> If a file is in the verification scope, it MUST be in at least one upstream repair task's Required Context (with the EI authorizing that task to edit it). Verification scope = ∪ (Repair scope_i) is the only configuration that closes an exit gate.

How to apply during scaffolding:

1. Find every grep table or file enumeration in the audit that lists files where defect instances live.
2. For each file in that table, emit an explicit repair task in the EI — even if the per-file defect count is small (1-3 lines).
3. Schedule the final verification task AFTER all repair tasks complete (cross-session or cross-sprint dependencies if needed).
4. Pre-flight check: for each file in the audit table, ask "which EI section authorizes editing this file?" If the answer is none, add it.

How to apply during execution:

If the executor running the final verification finds defect instances in files no upstream task touched, the executor MUST report it as a BLOCKER on the exit gate — not silently fix it. Silent fix masks the EI scoping defect and the same gap recurs in the next plan.

Red flags during review:

- Audit `## Dangling Anchors` (or equivalent) grep table lists N files; EI repair sections cover M < N of them.
- Final-sweep verification task names files no upstream repair task was authorized to edit.
- The phrase "verification only — do not edit" appears in a sweep that covers files the EI's earlier sections did not scope for repair.

---

## 10. Source-Promise Integrity — Body⇄Citation Presence + Pre-Extraction Verification

> [!binding] Why this section exists
> §5–§6 audit whether a cited finding propagates *forward* into implementation. §10 audits the prerequisite condition that makes that propagation possible: every artifact named as an authoritative source (Consolidated Context part body, EI section, task extraction target) MUST physically carry the prose its citations promise. A header that names a finding, OR a Cross-References row that lists it, OR an EI section that an instruction tells the executor to "extract verbatim from" — each of these is a *content promise*. The defect this section closes is silent: every file passes individual structural review; only the consistency between a citation and the cited-section's body is wrong.

The three subsections below cover the three tiers at which this defect class recurs:

| Tier | Source promise made by | Subsection |
|------|-----------------------|-----------|
| Discovery (Consolidated Context part) | Header "Driving Findings" + Cross-References row | §10.1 Body⇄Citation Presence |
| Execution (task extraction step) | Task file Execution Step "extract verbatim from §X" | §10.2 Pre-Extraction Verification Protocol |
| Recovery (when prose is absent) | The fallback path the executor MUST follow | §10.3 Fallback Hierarchy |

---

### 10.1 Body⇄Citation Presence (Consolidated Context Parts)

> [!constraint] A Consolidated Context part that names a finding as a source MUST carry that finding's full prose in the part body
> A Consolidated Context part lists "Driving Findings" / source identifiers in its header AND a Cross-References table mapping each section to its source. Those citations are a **promise that the part's body contains that finding's full rule prose** — not merely an index entry. The downstream consequence of a broken promise: tasks instructed to "apply Consolidated Context prose verbatim" have nothing to apply and either invent rule content (no audit trail) or re-publish a divergence the audit was meant to fix.
>
> The two paired guards:
>
> 1. **Scaffolding-time self-check.** When authoring or reviewing a Consolidated Context part, verify the cited prose is physically present in the part body before declaring the part complete. If the prose is NOT present, either fold it in OR mark the citation explicitly as deferred / source-doc-only with a pointer to the authoritative source document.
> 2. **Pre-extraction verification (downstream).** When an Execution Input or task file cites a Consolidated Context part as the verbatim-extraction source, the executor MUST verify the cited section physically carries the cited prose before extracting. If absent, fall back per §10.3.
>
> WRONG — Cross-References row claims a finding as the section source; body omits its prose:
>
> ```markdown
> | Section | Source Findings |
> | 2 ({target-file}.md) | {finding-A}, {finding-B}, {finding-C}, {finding-D} |
> ```
>
> (body content authors only {finding-A}; {finding-B} / {finding-C} / {finding-D} prose is absent — a downstream task that "applies the Consolidated Context prose verbatim" has nothing to apply)
>
> CORRECT — every finding named in the Cross-References row has its full rule body in the part, OR the row explicitly marks the finding as deferred / source-doc-only with a path pointer:
>
> ```markdown
> | 2 ({target-file}.md) | {finding-A} §X-Y [body included]; {finding-B} §Z, {finding-C} §W-ext, {finding-D} §V [source-doc-only — see {source-path}/{source-file}.md] |
> ```
>
> The "source-doc-only" marker is a legitimate completion; the *unmarked absence* is the defect.

How to apply during Consolidated Context authoring:

1. After authoring each part, list every finding named in the part header AND in any Cross-References row.
2. For each named finding, grep the part body for the finding's rule prose. A match means the promise is kept; no match means the promise is broken.
3. For broken promises: either fold the finding's prose into the body OR amend the Cross-References row with an explicit `[source-doc-only — see {path}]` marker.
4. Re-run the grep to confirm zero unmarked absences.

Red flags during review:

- A part's Cross-References row lists N findings; grepping the body finds prose for fewer than N (no `[source-doc-only]` markers explaining the gap).
- A part's header declares "Driving Findings: A, B, C" but only one of A/B/C appears in the body.
- A task file's Required Context cites the part as authoritative for content the part does not physically carry.

NOT applicable when the part is explicitly marked as an index / map / scope-only artifact (e.g., a Cross-References-only summary that has no body claim).

See also: §5 (Cross-Tier Duplicate Preservation — what to do when N sources cite the same finding), §10.2 (the downstream pre-extraction protocol that catches a broken promise at execution time).

---

### 10.2 Pre-Extraction Verification Protocol (Task Execution)

> [!protocol] When a task instruction says "extract verbatim from {EI Section} → {Spec #N}" or "apply the prose verbatim from {Consolidated Context Part}", the executor MUST verify the cited section physically carries the cited prose BEFORE beginning the extract step
> An Execution Input's `Extracted from:` header or per-section source citation is a content promise about the cited part — the same kind of promise §10.1 audits at the Consolidated Context tier, surfacing one tier down. When a task instruction says "extract the prose verbatim from {Part}", the executor MUST treat that instruction as falsifiable.
>
> Mandatory steps before any verbatim extraction:
>
> 1. **Open the cited section.** Read the named §X / Spec #N / Part path *before* drafting any output that depends on it.
> 2. **Match the cited prose against the section body.** If the rule, callout, table, or paragraph the task expects to extract IS present and matches the cited scope — proceed with extraction verbatim.
> 3. **Halt on absence or divergence.** If the cited section is missing, or carries divergent prose (e.g., the same defect the audit flagged is still present in the cited section), STOP the extract step. Do NOT extract the divergent prose; do NOT invent replacement prose from generic reasoning.
> 4. **Fall back per §10.3.** Walk the fallback hierarchy in priority order; author the output from the first authoritative input that carries the substantive prose.
> 5. **Record the deviation in Recovery.** Add an Issues-table row naming the cited section, the nature of the gap (absent / divergent), the fallback source used, and a one-line rationale ("Faithful to {audit-described-intent}").
> 6. **Surface the deviation in the session Summary.** Add a Context Notes / Issues line so reviewers can validate the authored output against the audit description (not the absent or divergent cited section).
>
> WRONG — extract verbatim from the cited section without verifying the section carries the cited prose:
>
> ```
> Task Step: "Source: Spec #N §X.Y — extract the {pattern} verbatim"
> Action: open Spec #N §X.Y → it carries divergent prose (the defect the audit
>         flagged) → re-publish that divergent prose as the "{pattern} restoration."
> Result: The divergence is re-published; the fix does nothing.
> ```
>
> WRONG — silently author rule content without recording the deviation:
>
> ```
> Task Step: "extract from Spec #N §X.Y"
> Action: discover Spec #N §X.Y lacks the prose → author the pattern from
>         generic reasoning → publish, no Recovery note.
> Result: Reviewer cannot tell whether the output matches the intent or was
>         invented; no audit trail back to the audit description.
> ```
>
> CORRECT — verify, then fall back with explicit deviation note:
>
> ```
> Task Step: "extract from Spec #N §X.Y (authoritative {pattern})"
> Action:
> 1. Open Spec #N §X.Y — confirm the prose actually present.
> 2. If present and matches: extract verbatim.
> 3. If absent or divergent: walk §10.3 fallback hierarchy.
>    For typical tasks: (a) audit's prose description of the lost rule,
>    (b) EI directive text, (c) recorded user-memory / project-rule preference.
> 4. Author from the fallback inputs, faithful to their joint specification.
> 5. Record in Recovery Issues table:
>    "EI cited Spec #N §X.Y as authoritative; Spec #N §X.Y was {absent/divergent}.
>     Authored from {fallback-source(s)}. Faithful to {audit-described-intent}."
> 6. Surface the deviation in the session Summary (Context Notes / Issues).
> ```

Applies to:

- Any task whose Execution Steps include "extract verbatim from {EI Section}", "apply the Consolidated Context prose verbatim", "copy the {rule/callout/table} from {Spec #N}", or equivalent verbatim-extraction language.
- Both DIRECT (orchestrator executes) and DELEGATED (subagent executes) modes — the verification step is mandatory regardless of who runs the task.
- Audit-driven remediation sessions where the audit *describes* a lost rule but no intermediate Consolidated Context artifact carries the rule's prose — the audit description IS the authoritative source under §10.3.

See also: §10.1 (the Consolidated Context tier where the promise is made), §10.3 (the priority-ordered fallback chain), §8 (token reconciliation — a related arithmetic-beats-summary discipline).

---

### 10.3 Fallback Hierarchy (When the Cited Section Is Absent or Divergent)

> [!escalation] Fallback priority when §10.2 verification fails
> When pre-extraction verification (§10.2) finds the cited section absent or divergent, walk this priority list. Author from the FIRST source that carries the substantive prose; document which fallback level was used in the Recovery Issues row.
>
> **Priority order:**
>
> 1. **Audit description / line-cited prose.** The audit (or upstream investigation) that surfaced the original defect almost always carries a prose *description* of the lost rule, even when no intermediate artifact carries the rule's body. That description is a valid authoritative source — author from it, mark the deviation, and let the reviewer validate against the audit description rather than the absent extracted-from artifact.
> 2. **EI directive text.** The Execution Input's own directive prose (the imperative sentence telling the task what to do) often pins the substantive intent — e.g., "adopt {Pattern-X} as the preferred approach." Use it to constrain the authored output's shape.
> 3. **Recorded user-memory / project-rule preference.** Where the project's accumulated rule files, memory pointers, or earlier-promotion artifacts establish a binding preference for the pattern at hand, that preference is the operational shape of the rule.
>
> WRONG — silent fallback to generic reasoning, no Recovery record:
>
> ```
> Cited section absent → "I'll just write something plausible" → publish.
> Recovery: silent. Reviewer cannot tell the cited path failed.
> ```
>
> CORRECT — explicit fallback walk with Recovery deviation row:
>
> ```
> Cited section absent → check priority 1 (audit description) → present, sufficient.
> Author from audit description. Recovery Issues row:
>   "Cited §X.Y absent; authored from audit description {audit-line-cite}.
>    Faithful to audit's stated intent."
> ```
>
> Two reinforcing guards:
>
> - **Pre-extraction verification (§10.2 step 1).** Open the cited section before the extract step — never after.
> - **Audit description as fallback authority.** When the audit carries a description and the cited intermediate artifact does not, the description IS the source; cite it explicitly in Recovery.

The fallback levels are *priority-ordered, not interchangeable*. Skipping a higher-priority fallback in favor of a lower-priority one is itself a deviation worth recording.

See also: §10.1 (the upstream cause — the cited section is empty because the body⇄citation promise was broken), §10.2 (the verification step that triggers this hierarchy).

---

## 11. Verbatim-Block Behavioral Freshness — A Wording Freeze Is Not a Fact Freeze

> [!constraint] A verbatim-copy mandate freezes wording and placement — it NEVER freezes the factual claims the block asserts; re-verify those against live state before pasting
> When an EI marks a block "paste verbatim — do not reword" and a task enforces it with a line-count gate, the mandate protects the block's *wording and placement*. It says nothing about whether the *factual claims* inside the block are still true. Between the moment a block is authored at scaffold time and the moment a later-executing task pastes it, an intervening sprint can change the very behavior one of the block's sentences describes. The task pastes faithfully, passes every gate, and ships a reference doc asserting the pre-change behavior — a silent fidelity defect no line-count or verbatim gate can catch.
>
> WRONG — treat the verbatim mandate as covering the claims too:
>
> ```
> "the spec says verbatim, the gates passed, ship it"
> ```
>
> The pasted block asserts a tool behavior an intervening sprint has since changed, so the shipped doc now describes the pre-change behavior.
>
> CORRECT — separate the wording freeze from the fact check:
>
> ```
> "verbatim for wording; behavioral claims re-verified against live state;
>  any deviation surfaced and noted before paste"
> ```

Three timing rules make the staleness surface auditable and the check mechanical:

1. **Authoring time.** When an EI marks a block "paste verbatim," record — in one line beside the block — which behavioral facts the block asserts (e.g. "describes upgrade-divergence handling"). This makes the staleness surface greppable later.
2. **Execution time.** Before pasting a verbatim block that describes tool / handler behavior, the runner or orchestrator MUST check the block's behavioral claims against the LIVE code / handler state — the same discipline cross-sprint grep gates apply to structural anchors. If a claim no longer matches live behavior, HALT the paste: surface the divergence, note it, and reconcile before writing.
3. **Flag-routing time.** A sprint that changes a behavior described in a later sprint's PENDING verbatim block MUST flag it, naming the later sprint (or its session) as the downstream consumer, so the paste-time check has a pointer to what changed. Route the flag per the two-hop model in [`handlers/run.md`](../handlers/run.md) (closeout delivers to the downstream front door; the receiving session routes it into its task files at its Phase-1 preflight).

This rule is the behavioral-claim analogue of §10.2's source-presence check: §10.2 verifies the cited section physically CARRIES the prose before extraction; §11 verifies the prose's factual CLAIMS still hold against the live world before paste. A block can pass §10.2 (the source carries it verbatim) and still fail §11 (the world it describes has moved).

---

*Cross-references: [session-planning-protocol.md](session-planning-protocol.md) (plan hierarchy and naming), [session-plan-requirements.md](session-plan-requirements.md) (Required Context and task-file structure), [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context fidelity, §9.B verify-before-cite), [scaffolding-hygiene.md](scaffolding-hygiene.md) §11 (mega-scaffold review-gate — the scaffold-time enforcement that prevents §10.1 promises from being silently introduced).*
