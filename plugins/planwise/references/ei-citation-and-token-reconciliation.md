---
description: EI cross-tier citation propagation and token reconciliation — duplicate preservation, implementation-surface citation propagation, §-citation discipline, arithmetic-over-summary token reconciliation gate (ei-fidelity.md §5-§8)
consult-when: Reconciling EI citations across tiers and token counts — arithmetic over summary
---

# EI Citation and Token Reconciliation

This file is segment B of the split of `ei-fidelity.md`, and its section numbers are the parent's. The `Segment Index` heading of [ei-fidelity.md](ei-fidelity.md) maps all four segments.

---

## 5. Cross-Tier Duplicate Preservation

**Rule.** When one finding is cited in N source files (for example two Tier 1 files and a Tier 2 consolidated file), the EI keeps all N citations in an explicit `**Note (cross-tier duplicate preserved):**` line that lists every source file and line range, so that verifying the duplicate takes one grep instead of a re-read of every source. Apply it in every Meta or Scaffold pipeline whose discovery content spans tiers, and wherever "cited N times" is load-bearing evidence (weights, findings, formulas, stabilization values). The note adds nothing when only one source cites the finding.

> [!template] Cross-Tier Duplicate Note
> ```
> **Note (cross-tier duplicate preserved):**
> {finding summary} — cited in {file1 line range}, {file2 line range}, ...,
> {fileN line range}. All N citations retained.
> ```

**Check.** `scripts/lint_execution_input.py` rule `cross-tier-note` reports a Cross-References finding cited at more than one `Tier-{N}` with no Note line that names every source. It cannot see a duplicate whose rows carry different Section cells, sources named without a `Spec #N` token, or which Note belongs to which section: any Note in the Part that names every source passes.

**Retention.** The same script's rule `retention-threshold` grades the EI's stated `Retention:` figure against the bands in [ei-fidelity.md](ei-fidelity.md) §3.1 (Algorithm-Sprint Retention-Band Calibration), which is the one home of those bands. It reads the stated figure and does not recompute it.

#### Reviewer Check 005 — EI Cross-Tier Duplicate Preservation

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** When the same finding appears at multiple Discovery tiers (Tier-1 raw / Tier-2 consolidated / Tier-3 final), EI MUST preserve cross-tier citations rather than dedup to one tier.
- **Detection:** Open EI; for each Cross-References row, count distinct `Tier-{N}` prefixes. If finding has single-tier prefix BUT source map indicates multiple tiers → ERROR. `scripts/lint_execution_input.py` rule `cross-tier-note` runs this check.
- **Finding template:**
```
[ERROR] EI cross-tier duplicate not preserved
File: {EI file path} | Location: Cross-References row {N}
Issue: Finding appears only at {one_tier}; source map shows {multiple_tiers}
Fix: Add tier-cross-cite per references/ei-citation-and-token-reconciliation.md §5 | Confidence: MEDIUM
```

#### Reviewer Check 008 — EI Extraction Retention Threshold

- **Severity / Role / Type:** BLOCKER/WARNING (tiered) | EI Reviewer | NEW
- **What:** Multi-tier Discovery extraction MUST meet the retention bands of [ei-fidelity.md](ei-fidelity.md) §3.1 (Algorithm-Sprint Retention-Band Calibration). Ratio = EI tokens / source tokens, measured over the whole EI.
- **Detection:** For each EI section, compute token count vs cited source Consolidated Context section, and grade the ratio by the band table of [ei-fidelity.md](ei-fidelity.md) §3.1. `scripts/lint_execution_input.py` rule `retention-threshold` grades the EI's stated `Retention:` figure.
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
> Cross-tier citation preservation is a refactor-drift firewall: a refactor that silently changes a cited weight or threshold passes unit tests and lint unless those gates check the citation text itself. For every cross-tier duplicate an EI Note records (§5), the task scaffolder produces all four surfaces:
>
> 1. **Algorithm/helper docstring** — the consuming code's task file requires a docstring citing BOTH (or all N) source locations verbatim.
>    Example: "per EI §X.Y Note: `{citation_author}` `{value}` from
>    `{SourceFile_1}` lines `{L1-L2}` AND `{SourceFile_2}` `{section}`."
> 2. **Lint gate grep** — the lint task's verification step MUST find both citation tokens in the
>    implementation file. Example: `grep -n "{token_1}\|{token_2}" {src/module/file.ext}`
>    returns matches.
> 3. **Test fixture comment** — a unit test using a value derived from the cited source carries an inline comment restating the cross-tier citation, so drift that changes the value fails the test semantically, not just numerically.
> 4. **Signoff checklist** — the sprint signoff task has a dedicated line item verifying that the citation-preservation greps pass.
>
> If any of the four is missing, the propagation is incomplete, and the preservation is one refactor away from silent drift.
>
> WRONG — the EI preserves a dual citation, and the task file generating the docstring cites only the EI section reference (one reference). Test fixtures use the cited value with no comment tying it to the dual-source finding. A refactor changing the value passes every gate.
>
> CORRECT — the task files propagate the dual citation into all four surfaces. Drift then fails a docstring lint, a citation-token grep, a test-fixture comment audit or the signoff grep.

**Partial check.** `scripts/lint_execution_input_plan.py` rule `cross-tier-propagation`, loaded by `scripts/lint_execution_input.py`, reports a Note whose task files lack a surface. It is partial: it cannot see a surface that names the sources by filename only, a Note with under two `Spec #N` tokens (printed as a note), or whether code consumes the cited value at all. The four-surface rule above governs.

---

## 7. §-Citation Discipline — Cite, Do Not Restate

> [!constraint] Task prose MUST cite verbatim EI content by §-reference; do NOT inline-restate counts, formulas, or weight vectors
> When a task consumes verbatim content (formulas, column lists, stabilization thresholds, weight vectors), the task file cites the §ref and directs the agent to read the content AT the cited section. Restating it inline creates count-claim drift: once the EI is edited, every task file that restated the values is silently wrong. If EI §X.Y later gains an N+1th component, every task that restated "{N} components" contradicts the source.
>
> WRONG — count claims and weights restated inline:
>
> ```markdown
> 1. Implement `{symbol}` with {N} components and weights `{weight_vector}`
>    summing to 1.0 per EI §X.Y.
> ```
>
> CORRECT — cite the section in Required Context and read the content there:
>
> ```markdown
> | 1 | `{Abbrev}-S{XX}-Execution-Input-Part-{N}-{Topic}.md` — §X.Y {formula name} (verbatim weight vector) | Source of truth |
>
> 1. Read EI §X.Y for the {formula name} verbatim (weight vector is AT §X.Y).
> 2. Implement `{symbol}` per §X.Y formula block, and apply §Z.W {related logic}.
> ```

Restatement is acceptable only when the restated value is MORE authoritative than the cited source (rare: the design task producing the EI for the first time, which is also the one task this rule does not bind), when it appears EXACTLY ONCE (e.g., in the EI itself), or when the prose claims "as of {YYYY-MM-DD}; verify against §X.Y current state", a dated snapshot with a verification pointer.

**Spec citations.** Every `Spec #N (filename)` citation in an EI's `Extracted from:` header and its Cross-References table resolves to the Master Plan's Global Source Map **as a pair**, number AND filename. A number on the wrong filename, the right filename with the wrong number, and a bare `Spec #N` all fail. Every sprint cites under the map's one global numbering, so a sprint that restarts a local count fails even when its header and table agree. Sparse numbering is allowed. `scripts/lint_execution_input.py` rule `spec-citation-pair` checks this: run it at scaffold time and again after any pass that adds, removes, splits, or renumbers a source. It cannot see citations outside the `Extracted from:` line and the Cross-References Source cells, plural forms such as `Specs #31, #32`, or two sources that share the tail of an elided map name.

Count-claim reconciliation grep — hunt for drift risk in scaffolded plans:

```bash
{consumer's grep command} -nE '(weights?|components?|columns?|metrics?|fields?) (with )?[0-9]+' <sprint-root>/**.md
# Every match should either be in the EI itself OR cite § where the count is authoritative.
```

`scripts/lint_execution_input.py` rule `count-claim` runs this pattern over sprint markdown and prints candidates (advisory, exit 0 always). It does not replace the rule above. It cannot see counts phrased with other nouns or in words, and any `§` on the line counts as a citation.

#### Reviewer Check 006 — EI §-Citation Format Discipline

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** Every `Extracted from:` header entry and every Cross-References row MUST use canonical format `Spec #{N} ({filename.md})` with global numbering matching Master Plan Global Source Map.
- **Detection:** Run over every `*-Execution-Input*.md` in the plan, Parts included. Enumerate every `Spec #\d+` token on the `Extracted from:` line and in every Cross-References row's Source cell. A token not immediately followed by ` ({filename.md})` is a format violation → BLOCKER. Verify each `{N}` **and its paired filename together** against Master Plan Global Source Map — a number matching the wrong filename, or the right filename carrying the wrong number, is a Mismatch → BLOCKER. Report one finding per EI file per mismatch. `scripts/lint_execution_input.py` rule `spec-citation-pair` runs this check.
- **Finding template:**
```
[BLOCKER] EI Cross-Reference §-citation format violated
File: {EI file path} | Location: {Extracted from: entry {k} | Cross-References row {N}}
Issue: Citation "{quoted_citation}" does not match Spec #{N} ({filename.md}) format
Fix: Reformat per references/ei-citation-and-token-reconciliation.md §7 + verify against Global Source Map | Confidence: HIGH
```

### 7.1 Cite Data Literals by §-Reference — the Temporal-Freshness Sibling

> [!constraint] Cite data literals by §-reference; do not inline-copy them
> A set, list, threshold, or ID list copied into a task file at scaffold time is a point-in-time snapshot of a design artifact that keeps changing. Cite the artifact's §-reference and reconcile at execution, most of all for literals gating PASS/FAIL/DEFERRED logic, where a stale copy silently changes the verdict. Make the session's first design or inventory task the **reconciliation firewall**: it reads the live design artifact and emits the resolved literal for downstream tasks.
>
> WRONG — `DEFERRED_TABLES = {"a", "b", "c"}   # copied from source §-ref at scaffold time` — the source artifact gained a fourth entry after scaffolding, and downstream processes a table the plan had since deferred.
>
> CORRECT — build the set from the cited §-reference AT EXECUTION TIME, and state the citation next to the construction so provenance is checkable.

§7 is the copy-paste-drift argument: restated content diverges from an EDITED source. This extension is the temporal-freshness argument (the cited artifact keeps changing with no edit to the copy) plus the reconciliation-firewall task position.

---

## 8. Token Reconciliation Gate — Arithmetic Beats Summary

> [!constraint] When a design task produces both a summary table AND per-task arithmetic, the arithmetic is authoritative; divergence MUST be flagged explicitly, not silently reconciled
> A design task (T05-equivalent in an 8-task scaffolding pipeline) that produces a sprint's session and task breakdown typically renders both a Sessions Overview table and a §-Token-Reconciliation block with per-task arithmetic. When they diverge, the arithmetic wins: summary tables get written from drafts that do not survive the design task's final per-task balancing.
>
> Divergence is not a mistake to correct silently. It is a signal that downstream tasks (Sprint Plan, task scaffolding) MUST be directed to use the arithmetic and ignore the summary.
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

**Check.** `scripts/lint_execution_input_plan.py` rule `token-reconciliation`, loaded by `scripts/lint_execution_input.py`, exits 1 when the EI total deviates from the Sprint total by more than 0.10, or when task estimates do not sum to the Orchestration and Sprint totals. It cannot see the Master Plan Sprint Overview row, a figure stated in other words, or a task file without an `Estimated Tokens:` header line.

#### Reviewer Check 007 — EI Token Reconciliation Gate

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** EI section token totals MUST reconcile with Sprint Plan Sessions Est. Tokens AND Master Plan Sprint Overview row tokens, deviation ≤10%. Algorithm-sprint EIs additionally MUST recompute numerical exemplars rather than verbatim-copy from source.
- **Detection:** Compute `abs(EI_total - Sprint_total) / Sprint_total`; >10% → BLOCKER. For algorithm sprints, grep EI for verbatim numerical-exemplar tables from source; unmodified copy → BLOCKER. `scripts/lint_execution_input_plan.py` rule `token-reconciliation` runs the first half.
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
> When an EI or Sprint Plan provides numerical exemplars meant to become regression tests, doctests, or success-criterion thresholds (e.g., "x = 0.051 → y ≈ 0.952"), the design-review task that locks function signatures and doctests MUST recompute every exemplar from its formula and surface any divergence as a [BLOCKING] open question. It MUST NOT pass the prose values through to implementation tasks unverified. Prose exemplars drift from exact arithmetic: recomputing at design costs seconds, and a late catch costs one extra subagent dispatch plus a doctest correction plus an EI errata note.
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

**Rule.** When a task copies verbatim content from EI §X, its success-criteria `wc -l` range is computed from the marked body block (plus any YAML frontmatter the task adds), never from the surrounding EI section, whose Substitution Log, EI-only headers, EI-only Notes and source-vocabulary glossaries the task strips. The EI section that authors the block marks its body with explicit start- and end-line delimiters (e.g., "Body Content runs from `# {Heading}` through `*{Closing italic line}*`") or an unambiguous callout. Allow ±3-5 lines for renderer differences (LF vs CRLF, trailing newline). A 10%+ delta is NOT a smoke pass: it means an EI-metadata leak (real bug; the executor MUST HALT and investigate) or a stale estimate (fix the EI's body markers and recompute the range). The tell in review: a task-runner Status Block reports a 10%+ negative line-count delta on a verbatim-copy task whose content-fidelity verification PASSes. The Token Reconciliation Gate (§8) reconciles totals across the planning tiers, and §8.2 reconciles per-task verbatim line counts against the body-only scope the task writes. The rule does not apply to transformed content (extraction plus restructure), whose line count is expected to diverge from any single source section.

**Check.** `scripts/lint_execution_input_plan.py` rule `verbatim-line-range`, loaded by `scripts/lint_execution_input.py`, exits 1 on a verbatim-copy section with no body delimiters, or on a task range within 5 percent of the section length and more than 10 percent above the body block. It cannot see a delimiter in other words, a range stated outside the task's Success Criteria, or a section cited in a Consolidated Context part. `templates/task-file.md` carries the same rule for task authors.

#### Reviewer Check 061 — EI Verbatim-Copy Task Line-Count Body-Block Scope

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** When a task instruction is "copy verbatim from EI §X" (or equivalent), the task's success-criteria `wc -l` smoke-check range MUST be computed against the EI's marked verbatim body block only — NOT the surrounding EI section, which embeds scaffolding metadata (Substitution Log, EI-only headers, EI-only Notes) the task instructions strip from the written file. The EI section authoring a verbatim block MUST contain explicit body delimiters (start/end markers or an unambiguous demarcating callout) so the task-scaffolder can count the body without inferring the boundary.
- **Detection:** `scripts/lint_execution_input_plan.py` rule `verbatim-line-range` runs this check.
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

### 8.3 Estimating a Refactor's Output Size — State the Derivation, Model the Constraints, Ship the Band as a Signal

§8.2 fixes the *scope* an estimate is computed over. This subsection fixes the *arithmetic*: how a computed size band goes wrong when its inputs move or when it models the wrong operation, and what the band may do once it is wrong. An enforced wrong band leaves one route to its number: deleting content the objective said to keep.

> [!constraint] Sub-rule A — re-derive downstream figures when you correct an input, and prefer the derivation to the result
> Two failure modes, kept distinct because they are caught by different means:
>
> - **Premise corrected, arithmetic stale.** A fix lands in one paragraph, and a number further down still encodes the old premise. Both halves sit in one file, so the self-inconsistency is checkable statically.
> - **Derivation omits a governing rule.** Internally consistent arithmetic models the wrong operation. Nothing static catches it, only execution. That is why the band must be **reported as a finding, never enforced as a target**.
>
> WRONG — the result only. When the premise moves, nothing signals the number is stale:
>
> ```markdown
> Anchor ~295-310 lines.
> ```
>
> CORRECT — the derivation inline, so a premise change makes the contradiction visible:
>
> ```markdown
> Anchor ~338 lines (472 total - 134 extracted: lines 99-147 = 49, 186-270 = 85).
> Steps 5.1/8.5/9 stay on the anchor and are NOT in the extracted span.
> ```
>
> Three detection rules:
>
> 1. **Re-add the file's own stated spans before trusting any figure derived from them.** Where two numbers describe the same extraction, **the ranges are authoritative over the total — the ranges were measured, the total was typed.**
> 2. **When a review corrects a scope decision, treat every downstream number as dirty**: sizes, token estimates, line counts, any "N of M" phrasing.
> 3. **Ask whether a governing rule changes the *shape* of the transformation rather than its volume.** That question is the whole of sub-rule B.

> [!constraint] Sub-rule B — enumerate the constraint classes before computing a band
> At least four constraint classes break naive subtraction, and more than one can apply to the same file at once:
>
> | Constraint | Effect on size | Naive estimate assumes |
> |---|---|---|
> | **Relocate a block** | full removal from source | correct |
> | **In-place citation** (interleaved clauses) | ~net zero | full removal |
> | **Verbatim / byte-freeze** (contracts, row-numbered tables) | zero change, cannot be touched | available for trimming |
> | **Anchor-protected** (named by no seam, explicitly kept) | zero change | implicitly trimmable |
>
> The in-place class is the one that surprises, because the content genuinely IS redundant — it just cannot be *removed*. Where redundant math is braided through sentences carrying unique load-bearing content, the governing rule replaces it **in place with a citation of comparable length**, so the region's length does not change.
>
> **The detection question, asked per region:** *what rule governs this edit?* If the answer is "replace in place", "keep verbatim", or "do not touch", that region contributes **zero** to the reduction — regardless of how redundant its content is. **Sum only the regions that genuinely leave.**

> [!constraint] Sub-rule C — every computed band ships as a signal, not a target
> Inline this clause verbatim beside every computed band:
>
> > The band is a signal, not a target. An anchor outside it is a finding to report with its residual driver named, never something to hit by trimming content the seams did not name.
>
> The asymmetry that justifies it: **a wrong band that is advisory costs a correction; a wrong band that is binding costs an artifact.** An enforced band leaves one route to the number — deleting content the objective said to keep.
>
> **Orchestrator-side corollary.** When a runner lands outside a band, names a residual driver, and refuses to trim, **that is the correct outcome, not a failure to report.** Four steps follow:
>
> 1. Check the driver against the file.
> 2. Correct the band.
> 3. Record the correction where the plan states the band.
> 4. **Tell the verification task the corrected band explicitly.** It has no way to know the plan text was wrong, and will otherwise re-fail correct work against a superseded number.
>
> Sub-rule A here covers the band's *construction*. [`measurement-discipline.md`](measurement-discipline.md) §8.9 sub-rule C covers a projection's *expiry* — a derivation that was correct when written and was invalidated by a later decision. Neither restates the other.

**Check.** `scripts/lint_execution_input_plan.py` rule `size-band-derivation`, loaded by `scripts/lint_execution_input.py`, exits 2, a WARNING, on a band with no inline derivation or no signal-not-target clause, or whose stated spans do not sum to its total. It cannot see a band in tokens or rows, a band phrased "between N and M", a derivation in another paragraph, or a modelling error in arithmetic that adds up, so sub-rule B stays a review step.

#### Reviewer Check 090 — Size Band Stated Without Its Derivation

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** A size or count band stated for a refactor MUST carry an **inline derivation** (the total, the spans subtracted, and what stays) and the **signal-not-target clause**. A bare band cannot be checked when its premise moves — nothing signals that the number is stale — and a band read as a target sends a runner to trim content the seams never named. The check also covers the modelling defect: a derivation that subtracts the full volume of a region the same plan elsewhere marks verbatim-frozen, anchor-protected, or subject to in-place replacement is internally consistent arithmetic over the wrong operation, and no static reading of the number alone will catch it.
- **Detection:** `scripts/lint_execution_input_plan.py` rule `size-band-derivation` runs steps 2 to 4.
  1. Collect every size or count band the plan states for a refactor, decomposition, or extraction — Expected Output ranges, anchor-size targets, "reduce to ~N lines" criteria.
  2. For each, check the band's own text for an inline derivation naming the total, the spans removed, and what stays. Absent → WARNING.
  3. Check for the signal-not-target clause beside the band. Absent → WARNING.
  4. Where the plan states spans elsewhere, re-add them and compare against the band's total. Disagreement → WARNING, and report the **spans** as authoritative: ranges are measured, totals are typed.
  5. Cross-check each subtracted region against the plan's own constraint markers. A region marked verbatim/byte-frozen, anchor-protected, or subject to in-place clause replacement, yet counted at full volume in the derivation → WARNING (name the region and the class).
  6. Where a review or binding callout elsewhere in the same file corrected which content moves, check every downstream figure was re-derived. Unamended → WARNING.
- **Finding template:**
```
[WARNING] Size band stated without its derivation
File: {plan or task file path} | Location: {Expected Output | Success Criteria}
Issue: Band {range} carries {no inline derivation | no signal-not-target clause | a total contradicting the file's own stated spans, which sum to {N} | a subtraction counting {region}, marked {verbatim-frozen|anchor-protected|in-place replacement}, at full volume}
Fix: State the derivation inline (total, spans removed with their line ranges, what stays), sum only regions that genuinely leave, and add the signal-not-target clause, per references/ei-citation-and-token-reconciliation.md §8.3 | Confidence: MEDIUM
```
