---
description: EI source-promise integrity — body⇄citation presence in Consolidated Context parts, pre-extraction verification protocol, fallback hierarchy, and verbatim-block behavioral freshness (ei-fidelity.md §10-§11)
---

# EI Source-Promise Integrity

**Segment D of a 4-way split of `ei-fidelity.md`** (934 lines, split 2026-08-10). Carries §10 (+10.1-10.4) and §11 verbatim; original §-numbers are preserved — a citation like "§10.2" names the section, not the file. See the anchor's segment index for the full 4-way map: [ei-fidelity.md](ei-fidelity.md) (§1-§4, this split's segment A), [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-completeness.md](ei-completeness.md) (§9, segment C).

---

## 10. Source-Promise Integrity — Body⇄Citation Presence + Pre-Extraction Verification

> [!binding] Why this section exists
> [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) §5–§6 audit whether a cited finding propagates *forward* into implementation. §10 audits the prerequisite condition that makes that propagation possible: every artifact named as an authoritative source (Consolidated Context part body, EI section, task extraction target) MUST physically carry the prose its citations promise. A header that names a finding, OR a Cross-References row that lists it, OR an EI section that an instruction tells the executor to "extract verbatim from" — each of these is a *content promise*. The defect this section closes is silent: every file passes individual structural review; only the consistency between a citation and the cited-section's body is wrong.

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

See also: [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) §5 (Cross-Tier Duplicate Preservation — what to do when N sources cite the same finding), §10.2 (the downstream pre-extraction protocol that catches a broken promise at execution time).

#### Reviewer Check 063 — Consolidated Context Body⇄Citation Presence

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** Every finding named in a Consolidated Context part's header "Driving Findings" list or in a Cross-References row MUST have its full rule prose physically present in the part body — OR the Cross-References row MUST mark the citation explicitly as `[source-doc-only — see {path}]` (or equivalent deferred-marker syntax). Naming a finding in a header or table is a content promise; an unmarked absence in the body fails the promise.
- **Detection:**
  1. Locate Consolidated Context parts in the plan (typically under `Meta-{Abbrev}/Outputs/*-Consolidated-Context-Part-*.md`).
  2. For each part: extract the list of findings named in the header "Driving Findings" line(s) AND in every Cross-References row.
  3. For each named finding: grep the part body for the finding's rule prose (a heading match, a callout, or a recognizable paragraph keyed off the finding identifier).
  4. If no body match AND no `[source-doc-only]` / `[deferred]` / equivalent marker on the Cross-References row → ERROR.
- **Finding template:**
```
[ERROR] Consolidated Context body⇄citation promise broken
File: {Consolidated Context part path} | Location: Cross-References row {N} / header Driving Findings
Issue: Finding {finding-identifier} named as a source but no body prose found AND no [source-doc-only] marker
Fix: Either fold {finding-identifier}'s prose into the part body OR amend the Cross-References row with [source-doc-only — see {path}] per references/ei-source-promise-integrity.md §10.1 | Confidence: HIGH
```

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

See also: §10.1 (the Consolidated Context tier where the promise is made), §10.3 (the priority-ordered fallback chain), [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) §8 (token reconciliation — a related arithmetic-beats-summary discipline).

#### Reviewer Check 064 — Pre-Extraction Verification (Task Cites Section That Does Not Carry the Cited Prose)

- **Severity / Role / Type:** ERROR | EI Reviewer | NEW
- **What:** When a task file's Execution Steps include "extract verbatim from {EI Section}", "apply the Consolidated Context prose verbatim", or equivalent verbatim-extraction language, the cited EI/Consolidated Context section MUST physically carry the cited prose. If the cited section is absent or carries divergent prose (e.g., the same defect an upstream audit flagged), the task is at risk of either re-publishing the divergence or inventing replacement content.
- **Detection:**
  1. Grep task files in the plan for verbatim-extraction language: `extract verbatim|copy verbatim|apply.*verbatim|verbatim from §|prose verbatim`.
  2. For each match: parse the cited EI/Consolidated Context section (`§X.Y`, `Spec #N`, or explicit Part path).
  3. Open the cited section; verify the prose the task expects to extract is physically present and not a divergent variant.
  4. If absent → ERROR. If divergent (the section carries prose that contradicts the task brief's stated intent or an upstream audit's described intent) → ERROR.
  5. If the task brief includes an explicit fallback-hierarchy reference (per `references/ei-source-promise-integrity.md` §10.3) or pre-extraction-verification step in its Execution Steps, downgrade to WARNING (the task is verification-aware; the gap may be intentional).
- **Finding template:**
```
[ERROR] Task verbatim-extraction targets a section that does not carry the cited prose
File: {task file path} | Location: Execution Step {N}
Issue: Cites {section-ref} as authoritative for verbatim extraction; section is {absent/divergent}
Fix: Add a pre-extraction verification step + fallback hierarchy per references/ei-source-promise-integrity.md §10.2 + §10.3, OR repoint the citation to the actually-authoritative source (audit description, EI directive, recorded project-rule preference) | Confidence: MEDIUM
```

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

### 10.4 Cited-Authority Currency — A Citation Names a Position, Not Just a File

> [!constraint] Citing another artifact as the AUTHORITY for a conclusion is a promise that the authority's CURRENT position still supports the conclusion — not merely that the artifact exists and is reachable
> §10.1-§10.3 audit whether a cited section physically CARRIES the prose a citation promises. This subsection audits a different promise: when a row cites another artifact — a backlog item, a prior review, an audit — as the AUTHORITY that a conclusion is true ("per {authority}, X"), the citation claims the authority's conclusion is still X as of today, not as of whenever the authority was first read. An authority that has since corrected, reversed, or qualified the cited claim is not a source to compress from — encountering one is a HALT, not a footnote.
>
> Mandatory steps before compressing a row that cites an authority for a CONCLUSION (as distinct from a citation that merely locates a fact at a page number):
>
> 1. **Open the cited authority in full** — including any Corrections, Related, or Acceptance Criteria section, not only the paragraph the row quotes from.
> 2. **Check whether the authority's current position still matches the claim being compressed.** An authority is current for this purpose if nothing in it revises, reverses, or qualifies the cited claim after the citation's own date.
> 3. **If the authority still supports the claim:** compress normally, citing the authority's re-confirmed position and the date checked.
> 4. **If the authority has revised or reversed the claim:** HALT compression of that row. Do not fold the stale conclusion into the EI, an exit criterion, or a Signoff anchor. Either re-derive the claim from the authority's current position, or drop the row and record why.
> 5. **Record which authority state was checked** — date and section — inline next to the citation, the same way a Required-Context path pointer carries a cost-hint date (see `references/scaffolding-hygiene.md` §12.1 / §12.3).
>
> WRONG — a row cites an authority as support without opening its corrections:
> ```
> Row: "Wire {target} into {consumer} — {authority} confirms {target} is unreferenced."
> (authority's own Corrections section, dated one day before this row was compressed,
>  already reverses "unreferenced" — never opened during compression)
> ```
> The row hardens into a priority order; the authority it cites had already said the opposite.
>
> CORRECT — the authority's current position is checked before compressing:
> ```
> Open {authority} in full, including Corrections.
> Corrections (dated {date}) reverse the "unreferenced" claim.
> HALT: do not compress this row as stated. Re-derive from {authority}'s current
> position, or drop the row with a one-line note citing the correction.
> ```

Applies to:

- Any EI row, Deliverable, or exit criterion that names a project-side backlog item, a prior review, or an audit as the AUTHORITY for a conclusion (not merely a source of a fact-with-a-locator).
- Scaffolding Step 4 (Create Execution Inputs) of the scaffolding workflow — see `handlers/plan-scaffolding.md`.

See also: §10.1 (the tier below this one — whether a cited SECTION carries its promised prose), §10.2 (pre-extraction verification for verbatim-copy instructions), §10.3 (the fallback hierarchy this subsection's HALT feeds into when a replacement claim must be authored).

#### Reviewer Check 079 — Cited-Authority Currency Before Compression

- **Severity / Role / Type:** BLOCKER | EI Reviewer | NEW
- **What:** When an EI row, Deliverable, or exit criterion cites a project-side backlog item, prior review, or audit as the AUTHORITY for a conclusion, the cited authority's current state (including its Corrections/Related/Acceptance-Criteria section) MUST support the claim as compressed. A cited authority that has since revised or reversed the claim, uncontradicted in the compressing row, is a BLOCKER.
- **Detection:**
  1. Grep the EI/Sprint Plan/Orchestration for rows citing an authority as support for a conclusion (phrasing like "{authority} confirms", "per {authority}", "{authority} establishes").
  2. Open each cited authority in full, including any Corrections/Related/Acceptance-Criteria section.
  3. Compare the authority's current position against the compressed row's claim.
  4. If the authority's current position contradicts, qualifies, or reverses the claim → BLOCKER.
- **Finding template:**
```
[BLOCKER] Cited-authority currency violated
File: {EI/plan file path} | Location: {row/section citing the authority}
Issue: {authority} has since revised/reversed the cited claim ({correction summary}); the row was compressed without reconciling
Fix: Re-derive from {authority}'s current position or drop the row, per references/ei-source-promise-integrity.md §10.4 | Confidence: HIGH
```

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

*Anchor: [ei-fidelity.md](ei-fidelity.md) (§1-§4 EI-as-archival, severity vocabulary preservation, threshold alignment, UNCONFIRMED four-site enforcement — segment A of this file's 4-way split, 2026-08-10). Sibling segments: [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-completeness.md](ei-completeness.md) (§9, segment C).*
