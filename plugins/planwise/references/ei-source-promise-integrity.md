---
description: EI source-promise integrity — body⇄citation presence in Consolidated Context parts, pre-extraction verification protocol, fallback hierarchy, verbatim-block behavioral freshness (ei-fidelity.md §10-§11), and a brief that cites a design pin quoting it verbatim with its fallback clause (§12)
consult-when: Checking EI body⇄citation presence, pre-extraction verification, verbatim-block freshness, and (§12) a task brief that cites a design pin quotes it verbatim with its fallback clause, never a restatement
---

# EI Source-Promise Integrity

This file is segment D of the 4-way split of [ei-fidelity.md](ei-fidelity.md). Its last section, on quoting a design pin, was added after the split. The Segment Index section of `ei-fidelity.md` holds the full map, and original section numbers name the section, not the file.

---

## 10. Source-Promise Integrity — Body⇄Citation Presence + Pre-Extraction Verification

[ei-citation-and-token-reconciliation.md](ei-citation-and-token-reconciliation.md) §5–§6 audit whether a cited finding propagates forward into implementation. §10 audits the condition that makes that possible: an artifact named as an authoritative source (a Consolidated Context part body, an EI section, a task extraction target) physically carries the prose its citations promise. A header that names a finding, a Cross-References row that lists it, and an EI section a task must "extract verbatim from" are each a *content promise*. The defect is silent. Every file passes its own structural review, and only the match between a citation and the cited body fails.

The three subsections below apply that promise at three tiers:

| Tier | Source promise made by | Subsection |
|------|-----------------------|-----------|
| Discovery (Consolidated Context part) | Header "Driving Findings" + Cross-References row | §10.1 Body⇄Citation Presence |
| Execution (task extraction step) | Task file Execution Step "extract verbatim from §X" | §10.2 Pre-Extraction Verification Protocol |
| Recovery (when prose is absent) | The fallback path the executor MUST follow | §10.3 Fallback Hierarchy |

---

### 10.1 Body⇄Citation Presence (Consolidated Context Parts)

> [!constraint] A Consolidated Context part that names a finding as a source MUST carry that finding's full prose in the part body
> A finding named in the part's "Driving Findings" header or in a Cross-References row is a promise that the body holds its full rule prose, not an index entry. When the promise breaks, a task told to "apply Consolidated Context prose verbatim" has nothing to apply. It invents rule content with no audit trail, or it re-publishes the divergence the audit meant to fix.
>
> 1. **Scaffolding-time self-check.** After authoring a part, list every finding its header and Cross-References rows name. Search the body for each finding's rule prose. Fold each missing finding into the body, or mark its row `[source-doc-only — see {path}]` with a pointer to the authoritative source document. Repeat the search until no unmarked absence remains.
> 2. **Pre-extraction verification (downstream).** When an Execution Input or task file cites the part as a verbatim-extraction source, or a task's Required Context cites it as authoritative, the executor verifies the cited section carries the prose before extracting. If it does not, fall back per §10.3.
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

The rule does not apply to a part explicitly marked as an index, map or scope-only artifact, such as a Cross-References-only summary that makes no body claim.

**Executable check.** `scripts/lint_execution_input.py` runs this rule as `body-citation-presence`, defined in `scripts/lint_execution_input_plan.py`. It exits 1 on a finding and skips the rule without `--plan-root`. It cannot see prose that names the finding in other words, or a finding item that holds a comma.

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
> An Execution Input's `Extracted from:` header or per-section source citation is the same content promise §10.1 audits, one tier down. Treat every verbatim-extraction instruction as falsifiable:
>
> 1. **Open the cited section.** Read the named §X / Spec #N / Part path before drafting any output that depends on it.
> 2. **Match the cited prose against the section body.** If the expected rule, callout, table or paragraph is present and matches the cited scope, extract it verbatim.
> 3. **Halt on absence or divergence.** If the section is missing, or carries divergent prose (such as the defect the audit flagged), stop the extract step. Never extract the divergent prose, and never invent replacement prose from generic reasoning.
> 4. **Fall back per §10.3.** Author the output from the first authoritative input in the priority order that carries the substantive prose.
> 5. **Record the deviation in Recovery.** Add an Issues-table row naming the cited section, the gap (absent / divergent), the fallback source used, and a one-line rationale ("Faithful to {audit-described-intent}").
> 6. **Surface the deviation in the session Summary.** Add a Context Notes / Issues line so reviewers validate the output against the audit description, not the absent or divergent section.
>
> WRONG — skip the verification, or skip the record of the fallback:
>
> ```
> Task Step: "Source: Spec #N §X.Y — extract the {pattern} verbatim"
> Action: open Spec #N §X.Y → it carries divergent prose (the defect the audit
>         flagged) → re-publish that prose as the "{pattern} restoration"
>         — or — it lacks the prose → author the pattern from generic
>         reasoning → publish, no Recovery note.
> Result: The divergence is re-published and the fix does nothing, or the
>         reviewer cannot tell whether the output matches the intent or was
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

- Any task whose Execution Steps say "extract verbatim from {EI Section}", "apply the Consolidated Context prose verbatim", "copy the {rule/callout/table} from {Spec #N}", or equivalent verbatim-extraction language.
- Both DIRECT (orchestrator executes) and DELEGATED (subagent executes) modes. The verification step is mandatory whoever runs the task.
- Audit-driven remediation sessions where the audit describes a lost rule and no intermediate Consolidated Context artifact carries its prose. The audit description IS the authoritative source under §10.3.

**Executable check.** `scripts/lint_execution_input.py` runs this rule as `pre-extraction-step`, defined in `scripts/lint_execution_input_plan.py`. It is an existence test only. It exits 1 when the cited section is absent and 2 when the task is verification-aware. A present section passes whether or not it carries the cited prose, so step 2 stays a read by the executor. It cannot see a step outside an Execution Steps section.

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
> Author from the FIRST source in this list that carries the substantive prose. Record the fallback level used in the Recovery Issues row.
>
> 1. **Audit description / line-cited prose.** The audit or upstream investigation that surfaced the defect almost always describes the lost rule in prose, even when no intermediate artifact carries its body. That description is a valid authoritative source. Author from it, mark the deviation, and let the reviewer validate against the audit description.
> 2. **EI directive text.** The Execution Input's imperative sentence often pins the intent, such as "adopt {Pattern-X} as the preferred approach". Use it to constrain the output's shape.
> 3. **Recorded user-memory / project-rule preference.** Where project rule files, memory pointers or earlier-promotion artifacts set a binding preference for the pattern, that preference is the operational shape of the rule.
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

The levels are *priority-ordered, not interchangeable*. Skipping a higher level for a lower one is itself a deviation to record.

See also: §10.1 (the upstream cause — the cited section is empty because the body⇄citation promise was broken), §10.2 (the verification step that triggers this hierarchy).

---

### 10.4 Cited-Authority Currency — A Citation Names a Position, Not Just a File

> [!constraint] Citing another artifact as the AUTHORITY for a conclusion is a promise that the authority's CURRENT position still supports the conclusion — not merely that the artifact exists and is reachable
> §10.1-§10.3 audit whether a cited section carries the promised prose. This subsection audits a different promise. A row that cites a backlog item, a prior review or an audit as the AUTHORITY for a conclusion ("per {authority}, X") claims the authority still says X today. An authority that has since corrected, reversed or qualified the claim is not a source to compress from. Meeting one is a HALT, not a footnote.
>
> Before compressing a row that cites an authority for a CONCLUSION (not a citation that only locates a fact at a page number):
>
> 1. **Open the cited authority in full**, including any Corrections, Related or Acceptance Criteria section, not only the quoted paragraph.
> 2. **Check that its current position still matches the claim.** The authority is current if nothing in it revises, reverses or qualifies the claim after the citation's own date.
> 3. **If it still supports the claim**, compress normally, citing the re-confirmed position and the date checked.
> 4. **If it revised or reversed the claim**, HALT compression of that row. Never fold the stale conclusion into the EI, an exit criterion or a Signoff anchor. Re-derive the claim from the current position, or drop the row and record why.
> 5. **Record the authority state checked**, date and section, inline beside the citation, the way a Required-Context path pointer carries a cost-hint date (see `references/scaffolding-hygiene.md` §12.1 / §12.3).
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

- Any EI row, Deliverable or exit criterion that names a project-side backlog item, a prior review or an audit as the AUTHORITY for a conclusion, not only as the source of a fact with a locator.
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
> An EI block marked "paste verbatim — do not reword", enforced by a line-count gate, protects the block's *wording and placement*. It says nothing about whether the block's *factual claims* still hold. An intervening sprint can change the behavior a sentence describes between scaffold time and paste time. The task then pastes faithfully, passes every gate, and ships a reference that asserts the old behavior. No line-count or verbatim gate can catch it.
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

Three timing rules make the staleness surface auditable:

1. **Authoring time.** When an EI marks a block "paste verbatim", record beside it, in one line, which behavioral facts it asserts (e.g. "describes upgrade-divergence handling"). The staleness surface is then greppable.
2. **Execution time.** Before pasting a block that describes tool or handler behavior, the runner or orchestrator MUST check its behavioral claims against the LIVE code and handler state, as cross-sprint grep gates do for structural anchors. If a claim no longer matches, HALT the paste, surface and note the divergence, and reconcile before writing.
3. **Flag-routing time.** A sprint that changes a behavior described in a later sprint's PENDING verbatim block MUST flag it, naming that sprint (or its session) as the downstream consumer. Route the flag per the two-hop model in [`handlers/run.md`](../handlers/run.md): closeout delivers to the downstream front door, and the receiving session routes it into its task files at its Phase-1 preflight.

This rule is the behavioral-claim analogue of §10.2. §10.2 verifies that the cited section CARRIES the prose before extraction. §11 verifies that the prose's factual CLAIMS still hold before paste. A block can pass §10.2 and still fail §11, because the world it describes has moved.

---

## 12. A Brief That Cites a Design Pin Quotes It Verbatim, Fallback Included

> [!constraint] When a task brief depends on a design pin, quote the pin verbatim, with its fallback and exception clauses. Never restate it
> A paraphrase keeps the main rule and tends to drop the conditional branch. The branch is the part the runner needs when the measurement comes in. A brief that restates a pin can also invent a stop rule the pin never had, and the runner obeys the brief.

> [!constraint] WRONG and CORRECT — quote the pin and point at its fallback
> WRONG — the brief restates the pin and invents a stop rule:
> ```text
> If any <unit> file measures WARN or OVER, return HOLD. <pin> pins three files; do not invent a fourth.
> ```
> CORRECT — the brief quotes the pin and points at its fallback:
> ```text
> <pin> (<Execution Input section>), verbatim: "If a <unit> file would exceed 22,000 tokens, split that <unit> at 50
> (<file>-001-050.md, <file>-051-100.md)." Apply it when the measurement trips it. HOLD only when the pin's own
> fallback does not cover the case.
> ```

**Review step.** At review, check every "because pin X says" sentence in a brief against pin X's text. A brief whose stated reason points at a pin that says otherwise is a finding.

**Where it applies.** Scaffolded task briefs that cite design pins, decision rows or Execution Input sections. The risk is highest for pins that carry a size, count or budget threshold with a remedy attached.

**Relationship to §11.** This section is the brief-side counterpart of §11 (verbatim-block behavioral freshness). §11 freezes wording and re-verifies the claims. This section forbids a restatement where a quotation is available.

#### Reviewer Check 097 — Brief Restates a Design Pin and Drops Its Fallback

- **Severity / Role / Type:** WARNING (HIGH confidence) | Task Reviewer | NEW
- **What:** For each task brief that cites a pin, a decision row or an Execution Input section as the reason for a stop rule, locate the cited text. Confirm the brief quotes it verbatim, or that the brief's paraphrase carries every fallback and exception clause.
- **Detection:**
  1. Find each brief sentence of the form "because `<pin>` says" or "`<pin>` fixes N" that supports a HOLD, stop or do-not rule.
  2. Open the cited pin, decision row or Execution Input section and read its full text, including every "if", "unless" and "split" clause.
  3. Compare. A paraphrase that omits a fallback or exception clause the pin carries → WARNING.
  4. A stop rule whose stated reason the cited text contradicts → WARNING.
- **Finding template:**
```
[WARNING] Brief restates a design pin and drops its fallback clause
File: {task file path} | Location: {step or stop-rule sentence}
Issue: Brief cites {pin} as the reason to {stop rule}; the pin also says "{fallback clause}", which decides the case the stop rule halts on
Fix: Quote the pin verbatim and point the runner at its fallback, per references/ei-source-promise-integrity.md §12 | Confidence: HIGH
```
