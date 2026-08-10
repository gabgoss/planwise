---
description: EI source-promise integrity — body⇄citation presence in Consolidated Context parts, pre-extraction verification protocol, fallback hierarchy, and verbatim-block behavioral freshness (ei-fidelity.md §10-§11)
---

# EI Source-Promise Integrity

**Segment D of a 4-way split of `ei-fidelity.md`** (934 lines, split 2026-08-10). Carries §10 (+10.1-10.3) and §11 verbatim; original §-numbers are preserved — a citation like "§10.2" names the section, not the file. See the anchor's segment index for the full 4-way map: [ei-fidelity.md](ei-fidelity.md) (§1-§4, this split's segment A), [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-completeness.md](ei-completeness.md) (§9, segment C).

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

*Anchor: [ei-fidelity.md](ei-fidelity.md) (§1-§4 EI-as-archival, severity vocabulary preservation, threshold alignment, UNCONFIRMED four-site enforcement — segment A of this file's 4-way split, 2026-08-10). Sibling segments: [ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) (§5-§8, segment B), [ei-completeness.md](ei-completeness.md) (§9, segment C).*
