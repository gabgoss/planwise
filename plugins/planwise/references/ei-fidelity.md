---
description: EI fidelity across scaffolding tiers — source preservation, threshold alignment, and UNCONFIRMED caveat enforcement (§1-§4; §5-§11 split to sibling files)
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
- [4.5 Hedge Preservation — Compression Must Not Flatten a Qualifier Into a Fact](#45-hedge-preservation--compression-must-not-flatten-a-qualifier-into-a-fact)

### Segment Index — This File Was Split 4 Ways (2026-08-10)

`ei-fidelity.md` was 934 lines — the plugin's largest reference — and was split into 4 segments along its existing §-boundaries. This file (segment A) keeps the filename and §1-§4. Original §-numbers are preserved verbatim in every segment: a citation like "§9.1" or "§10.2" names the section, not the file — only the FILE changed.

| Segment | §-Range | Content | File |
|---------|---------|---------|------|
| A | §1-§4 | EI-as-archival, severity vocabulary preservation, threshold alignment (+3.1 retention-band calibration), UNCONFIRMED four-site enforcement | `ei-fidelity.md` (this file) |
| B | §5-§8 (+8.1, 8.2) | Cross-tier duplicate preservation, citation propagation to implementation, §-citation discipline, token reconciliation gate | [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) |
| C | §9 (+9.1-9.3) | EI completeness — three-axis scope coverage | [ei-completeness.md](ei-completeness.md) |
| D | §10-§11 (+10.1-10.4) | Source-promise integrity (body⇄citation presence, pre-extraction verification, fallback hierarchy), verbatim-block behavioral freshness | [ei-source-promise-integrity.md](ei-source-promise-integrity.md) |

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

#### Reviewer Check 001 — EI Severity Tag Catalog Present

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** Every EI body MUST declare the source severity tag catalog (BLOCKER/ERROR/WARNING/INFO/UNCONFIRMED vocabulary).
- **Detection:** Open each `*-Execution-Input*.md`; grep `^##\s+Severity\s+Vocabulary` heading. If absent AND EI contains `\[(BLOCKER|ERROR|WARNING|INFO|UNCONFIRMED)\]` references → ERROR.
- **Finding template:**
```
[ERROR] EI severity tag catalog missing
File: {EI file path} | Location: EI body — expected Severity Vocabulary section
Issue: EI cites severity-tagged claims but does not declare the catalog
Fix: Append "## Severity Vocabulary" per references/ei-fidelity.md §2 | Confidence: HIGH
```

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

#### Reviewer Check 002 — EI Threshold Alignment With Operational Dispatch Contracts

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Numerical thresholds in an EI (retention bands, token budgets, `{numeric-threshold}` values) MUST match operational dispatch contracts in companion Sprint Plan / Orchestration.
- **Detection:** Open EI + Sprint Plan + Orchestration; extract numeric values from EI "Threshold" / "Budget" sections; compare against Sprint Plan Sessions table + Orchestration Total Estimated. Deviation >10% → BLOCKER.
- **Finding template:**
```
[BLOCKER] EI threshold misaligned with dispatch contract
File: {EI file path} | Location: EI section {section_name}, value {EI_value}
Issue: EI threshold {EI_value} differs from {plan_file} {plan_value} by >10%
Fix: Reconcile per references/ei-fidelity.md §3 | Confidence: HIGH
```

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

#### Reviewer Check 003 — EI Algorithm-Sprint Retention Band Calibration

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Algorithm sprints (Objective declares algorithmic / numerical-design work) MUST apply algorithm-band retention threshold (tighter than generic band).
- **Detection:** Open Sprint Plan Objective; check keywords (`algorithm`, `numerical design`, `model`). Open EI §3.1 retention-band declaration. If Sprint Plan matches keywords AND EI uses generic band → BLOCKER.
- **Finding template:**
```
[BLOCKER] Algorithm-sprint retention band miscalibrated
File: {EI file path} | Location: EI §3.1 retention band
Issue: Sprint Plan declares algorithm work but EI applies generic band
Fix: Apply algorithm-band per references/ei-fidelity.md §3.1 | Confidence: HIGH
```

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

#### Reviewer Check 004 — EI UNCONFIRMED Four-Site Enforcement

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Every UNCONFIRMED claim MUST appear at all four sites: (a) EI header note, (b) inline `> [!constraint]` callout (NOT `> [!practice]`), (c) Cross-References annotation column, (d) Exit-Criteria caveat.
- **Detection:** Grep EI for `UNCONFIRMED`. For each occurrence, verify presence at all four sites. If `> [!practice]` callout used → BLOCKER. If missing from any site → BLOCKER.
- **Finding template:**
```
[BLOCKER] UNCONFIRMED claim missing four-site enforcement
File: {EI file path} | Location: claim "{quoted_claim_text}"
Issue: Flagged UNCONFIRMED but absent from {missing_site_name}
Fix: Replicate per references/ei-fidelity.md §4 | Confidence: HIGH
```

---

## 4.5 Hedge Preservation — Compression Must Not Flatten a Qualifier Into a Fact

> [!constraint] A source sentence that hedges its own claim MUST keep that hedge through compression, or have the hedge explicitly resolved by a recorded measurement — never silently dropped
> §4 covers explicit status markers (UNCONFIRMED / UNVERIFIED / deprecated / requires-local-download). This subsection covers a related but distinct failure: a source sentence that hedges its own claim in ordinary prose — "most likely", "per the preliminary hypothesis", "except X", "reconfirmed (pending Y)", "appears to", "tentative", "subject to change" — without using one of §4's formal markers. Compression that keeps the flat claim and drops the hedge word manufactures a certainty the source never asserted.
>
> Rule: when compressing a source sentence into an EI row (or any downstream artifact — exit criterion, Signoff anchor), scan the sentence for hedge language. If present:
>
> 1. **Preserve the hedge verbatim** in the compressed row, OR
> 2. **If the hedge has since been resolved by measurement**, replace the hedge with the measured resolution and cite what was measured and when — do not just delete the hedge and keep the flat claim.
>
> Never drop the hedge silently and keep only the flat claim. A dropped hedge is the same failure mode §4 already forbids for formal UNCONFIRMED markers — this subsection extends the same discipline to informal hedge language that never got a formal tag.
>
> WRONG — hedge dropped on compression, flat claim kept:
> ```
> Source: "the citations most likely map to §1.2/§1.3."
> EI row: "The citations map to §1.2/§1.3."
> ```
> The reader of the EI row has no way to know the source was not certain.
>
> CORRECT — hedge preserved, or resolved with cited evidence:
> ```
> Source: "the citations most likely map to §1.2/§1.3."
> EI row (hedge preserved): "The citations most likely map to §1.2/§1.3 (source not certain)."
> — or, if since measured —
> EI row (hedge resolved): "The citations map to §1.2/§1.3 (confirmed by {measurement}, {date}; source's original 'most likely' hedge is now resolved)."
> ```

How to apply during compression:

- Grep the source passage for hedge markers before drafting the compressed row: "most likely", "probably", "appears to", "pending", "preliminary", "tentative", "subject to", "except", "reconfirmed".
- If a hedge marker is present and the compressed row states the claim as flat fact with no hedge and no cited resolution, that is the defect this subsection names.
- A hedge that has been resolved needs the resolution's evidence cited inline (what was measured, when) — not just the hedge word deleted.

Red flags during review:

- A compressed row states a claim as settled fact when the source sentence carried a hedge word.
- A word like "reconfirmed" survives compression but nothing records what re-confirmation actually checked or when.

#### Reviewer Check 080 — Hedge Preservation Through Compression

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** A compressed EI row, exit criterion, or Signoff anchor whose source sentence carried a hedge marker ("most likely", "probably", "appears to", "pending", "preliminary", "tentative", "subject to", "except X", "reconfirmed") MUST either preserve that hedge verbatim or cite the measurement that resolved it. A flat, unhedged claim compressed from hedged source prose, with no cited resolution, is an ERROR.
- **Detection:**
  1. Open the source document(s) the EI/plan cites as `Extracted from:`.
  2. Grep the source for hedge markers in passages the EI compresses.
  3. For each hedge marker found in source, check the corresponding compressed row for either the same hedge or a cited resolution.
  4. If the compressed row states the claim flatly with neither → ERROR.
- **Finding template:**
```
[ERROR] Hedge dropped during compression
File: {EI/plan file path} | Location: {row/section}
Issue: source hedge "{hedge phrase}" dropped; compressed row states the claim as settled fact with no cited resolution
Fix: Restore the hedge or cite the resolving measurement, per references/ei-fidelity.md §4.5 | Confidence: MEDIUM
```

---

*Cross-references: [session-planning-protocol.md](session-planning-protocol.md) (plan hierarchy and naming), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Required Context and task-file structure), [verify-before-cite.md](verify-before-cite.md) (§9.B verify-before-cite), [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context fidelity), [scaffolding-hygiene.md](scaffolding-hygiene.md) §11 (mega-scaffold review-gate — the scaffold-time enforcement that prevents [destructive-change-requirements.md](destructive-change-requirements.md) §10.1 promises from being silently introduced).*

**Companion files (this split, 2026-08-10):** [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, cross-tier citation propagation and token reconciliation), [ei-completeness.md](ei-completeness.md) (§9, three-axis scope coverage), [ei-source-promise-integrity.md](ei-source-promise-integrity.md) (§10-§11, source-promise integrity and verbatim-block freshness).
