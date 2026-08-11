---
description: EI cross-tier citation propagation and token reconciliation — duplicate preservation, implementation-surface citation propagation, §-citation discipline, arithmetic-over-summary token reconciliation gate (ei-fidelity.md §5-§8)
---

# EI Citation and Token Reconciliation

**Segment B of a 4-way split of `ei-fidelity.md`** (934 lines, split 2026-08-10). Carries §5-§8 (+8.1, 8.2) verbatim; original §-numbers are preserved — a citation like "§8.1" names the section, not the file. See the anchor's segment index for the full 4-way map: [ei-fidelity.md](ei-fidelity.md) (§1-§4, this split's segment A), [ei-completeness.md](ei-completeness.md) (§9, segment C), [ei-source-promise-integrity.md](ei-source-promise-integrity.md) (§10-§11, segment D).

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

#### Reviewer Check 005 — EI Cross-Tier Duplicate Preservation

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** When the same finding appears at multiple Discovery tiers (Tier-1 raw / Tier-2 consolidated / Tier-3 final), EI MUST preserve cross-tier citations rather than dedup to one tier.
- **Detection:** Open EI; for each Cross-References row, count distinct `Tier-{N}` prefixes. If finding has single-tier prefix BUT source map indicates multiple tiers → ERROR.
- **Finding template:**
```
[ERROR] EI cross-tier duplicate not preserved
File: {EI file path} | Location: Cross-References row {N}
Issue: Finding appears only at {one_tier}; source map shows {multiple_tiers}
Fix: Add tier-cross-cite per references/ei-citation-and-token-reconciliation.md §5 | Confidence: MEDIUM
```

#### Reviewer Check 008 — EI Extraction Retention Threshold

- **Severity / Role / Type:** BLOCKER/WARNING (tiered) | EI Reviewer | NEW
- **What:** Multi-tier Discovery extraction MUST achieve ≥95% retention (pass), 80-95% (WARNING), <80% (BLOCKER auto-reject). Ratio = extraction tokens / source tokens per EI section.
- **Detection:** For each EI section, compute token count vs cited source Consolidated Context section. Ratio <0.80 → BLOCKER; 0.80-0.95 → WARNING; ≥0.95 → pass.
- **Finding template:**
```
[{SEVERITY}] EI extraction retention below threshold
File: {EI file path} | Location: section {section_name} (source: {source_file} §{N})
Issue: Retention ratio {ratio}% below {threshold}%
Fix: Re-extract verbatim per references/ei-citation-and-token-reconciliation.md §5 — extraction ≠ summarization | Confidence: HIGH
```

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

#### Reviewer Check 006 — EI §-Citation Format Discipline

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Every Cross-References row MUST use canonical format `Spec #{N} ({filename.md})` with global numbering matching Master Plan Global Source Map.
- **Detection:** Grep `Spec #\d+ \([^\)]+\.md\)` on Cross-References table; verify each `{N}` against Master Plan Global Source Map. Mismatch → BLOCKER.
- **Finding template:**
```
[BLOCKER] EI Cross-Reference §-citation format violated
File: {EI file path} | Location: Cross-References row {N}
Issue: Citation "{quoted_citation}" does not match Spec #{N} ({filename.md}) format
Fix: Reformat per references/ei-citation-and-token-reconciliation.md §7 + verify against Global Source Map | Confidence: HIGH
```

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

#### Reviewer Check 007 — EI Token Reconciliation Gate

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** EI section token totals MUST reconcile with Sprint Plan Sessions Est. Tokens AND Master Plan Sprint Overview row tokens, deviation ≤10%. Algorithm-sprint EIs additionally MUST recompute numerical exemplars rather than verbatim-copy from source.
- **Detection:** Compute `abs(EI_total - Sprint_total) / Sprint_total`; >10% → BLOCKER. For algorithm sprints, grep EI for verbatim numerical-exemplar tables from source; unmodified copy → BLOCKER.
- **Finding template:**
```
[BLOCKER] EI token reconciliation gate failed
File: {EI file path} | Location: EI token total {EI_total}
Issue: Deviates {deviation_pct}% from Sprint Plan / Master Plan
Fix: Recompute per references/ei-citation-and-token-reconciliation.md §8 (and §8.1 for algorithm sprints) | Confidence: HIGH
```

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

#### Reviewer Check 061 — EI Verbatim-Copy Task Line-Count Body-Block Scope

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** When a task instruction is "copy verbatim from EI §X" (or equivalent), the task's success-criteria `wc -l` smoke-check range MUST be computed against the EI's marked verbatim body block only — NOT the surrounding EI section, which embeds scaffolding metadata (Substitution Log, EI-only headers, EI-only Notes) the task instructions strip from the written file. The EI section authoring a verbatim block MUST contain explicit body delimiters (start/end markers or an unambiguous demarcating callout) so the task-scaffolder can count the body without inferring the boundary.
- **Detection:**
  1. Grep the EI for verbatim-copy task references: `copy.*verbatim.*from.*§|Verbatim Body|Body Content runs from|copy verbatim from EI`.
  2. For each verbatim-copy task: open the cited EI §X and confirm explicit body delimiters are present (start-line + end-line markers, or a callout that demarcates the body block from surrounding EI metadata). Absent → ERROR.
  3. Open the corresponding task file's Success Criteria; extract the `wc -l` range (e.g., `~{min}-{max} lines`).
  4. Count the marked body block of EI §X (between the delimiters). Count the full EI §X section. If the documented range is within ±5% of the FULL section line count AND >10% above the body-block line count → ERROR (estimate measured the EI section, not the body block).
- **Finding template:**
```
[ERROR] EI verbatim-copy line-count estimate measures EI section, not body block
File: {task file path} | Location: Success Criteria
Issue: wc -l range {documented_range} matches EI §{section} section length ({section_lines}) rather than body block ({body_lines})
Fix: Recompute range against the marked body block per references/ei-citation-and-token-reconciliation.md §8.2 (and add body delimiters to EI §{section} if missing) | Confidence: MEDIUM
```

---

*Anchor: [ei-fidelity.md](ei-fidelity.md) (§1-§4 EI-as-archival, severity vocabulary preservation, threshold alignment, UNCONFIRMED four-site enforcement — segment A of this file's 4-way split, 2026-08-10). Sibling segments: [ei-completeness.md](ei-completeness.md) (§9, segment C), [ei-source-promise-integrity.md](ei-source-promise-integrity.md) (§10-§11, segment D).*
