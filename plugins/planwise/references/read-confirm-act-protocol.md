---
description: Mandatory READ-CONFIRM-ACT pattern — confirmation block, structural-findings gate, cross-task coordination flags
---

# READ-CONFIRM-ACT Protocol

> [!binding] Enforcement
> These are not guidelines. Violations cause context loss and incomplete work.

**Purpose:** Mandatory READ-CONFIRM-ACT pattern — confirmation block, structural-findings gate, cross-task coordination flags.
**Extracted from session-execution-protocol.md; that file keeps the operational session rules (§2-§7).**

---

## 1. READ-CONFIRM-ACT Pattern

**Before ANY task:**
1. **READ** all referenced documents completely (not skim)
2. **CONFIRM** understanding with a confirmation block (see format below)
3. **ACT** only after user approval

### 1.1 Confirmation Block

> [!template] Context Confirmation
> ```
> CONTEXT LOADED
> File: {filename or "multiple files"}
> Current State: {status from document}
> Last Completed: {step/task from Recovery file}
> Next Action: {what the document says to do}
> Structural Finding: {none, or one-line summary — see §1.2}
> ```

After outputting, use `AskUserQuestion` tool: "Ready to proceed with [next action]?"

> [!constraint] Confirmation Block — All Fields Required
> WRONG — missing Current State and Last Completed fields; Next Action is vague:
> ```
> CONTEXT LOADED
> File: PRJ-S01-02-Orchestration.md
> Next Action: Continue with tasks
> ```
> CORRECT — all 4 fields present; Next Action is specific and actionable:
> ```
> CONTEXT LOADED
> File: PRJ-S01-02-Orchestration.md, PRJ-S01-02-Recovery.md
> Current State: IN_PROGRESS — Task 01 complete, Task 02 pending
> Last Completed: PRJ-S01-02-01 (Haiku-ValidateInputs) — inputs verified
> Next Action: Execute PRJ-S01-02-02-Sonnet-ImplementFeature.md
> ```

> [!binding] READ-CONFIRM-ACT Cannot Be Waived
> READ-CONFIRM-ACT applies in **every** operating configuration: Auto Mode, background mode, skill-forked contexts, plan mode, `claude --agent` sessions, and any other runtime configuration of Claude Code. There is no mode that exempts a session from CONFIRM. The Auto-Mode directive "prefer action over planning" applies to ad-hoc decisions inside a routine task — it does NOT waive the CONFIRM step for protocol-driven workflows.
>
> **For `/planwise plan --scaffold` specifically:** before writing any plan file (Master Plan, Execution Input, Sprint Plan, Orchestration, Recovery, task file, Outputs/), the scaffolding agent MUST emit a confirmation block enumerating expected outputs and wait for user approval. The block MUST list:
>
> ```
> CONTEXT LOADED
> Plan: {plan name + abbreviation}
> Expected outputs: 1 Master Plan + N Execution Inputs + M Sprint Plans
> Per-sprint session count: Sprint-{XX}: K1 sessions, Sprint-{YY}: K2 sessions, ...
> Total file count: F files (Σ session-folder × per-session file count + Master Plan + EIs + Sprint Plans)
> Next Action: Write {first file path}
> ```
>
> Skipping CONFIRM in any of these contexts is a known root-failure pattern: a scaffolder run in Auto Mode that wrote 20+ plan files with no CONFIRM, producing an incoherent plan tree. It is not a stylistic preference; it is the protocol's load-bearing gate.

### 1.2 Structural Findings Beyond Literal Scope

> [!binding] Phase-1 Scope-Expansion Gate
> When the READ step uncovers a structural defect that makes the literal scope produce a self-inconsistent artifact, the CONFIRM block MUST surface it BEFORE asking the user to proceed. Executing the literal scope silently — when the executor knows it publishes a defective artifact — is a protocol violation. Executing an expanded coherent scope silently — without an explicit user choice — is also a protocol violation.

Apply this rule whenever a single, narrowly-scoped task (typically from an audit punch-list, a backlog item, or a remediation directive) references a defect inside a larger artifact, AND the READ step reveals that the minimum *coherent* fix requires touching adjacent latent defects the task did not name. Typical patterns:

- Table-of-contents ↔ body ordering mismatches (literal "add §X to ToC" leaves §X anchoring into a mid-section H3, or leaves adjacent §Y/§Z still absent)
- Anchor ↔ heading-level mismatches (literal "add cross-reference to §X" requires promoting §X's heading first)
- Partial enumerations (literal "fix item 3 in the list" requires renumbering 4-7)
- Schema-pin ↔ deployed-schema drift discovered during a narrow column change

When the READ surfaces such a finding, the CONFIRM block MUST add a `Structural finding` paragraph and offer the user TWO explicit options:

> [!template] Structural Finding + Option Block
> ```
> Structural finding: {one-paragraph description of the latent adjacent defect
>                       and why the literal scope produces a self-inconsistent
>                       artifact}.
>
> Option A (Coherent): {describe the expanded scope, the structural rationale,
>                       and the expected line / heading-level / file-touch impact}.
> Option B (Literal):  {acknowledge that the literal scope produces a known-
>                       defective artifact and the original directive's intent
>                       is not satisfied; name the residual defect class}.
> ```

Then call `AskUserQuestion` with both options. The executor MUST NOT pick a path before the user answers; the option block is not a recommendation paragraph.

> [!constraint] Structural Finding Must Surface, Not Disappear
> WRONG — executor reads, notices the literal scope is incoherent, silently expands and writes:
> ```
> (reads target file)
> → notices §11 is H3 inside §9, and §12/§13 are absent from ToC
> → silently promotes §11→H2, relocates after §10, adds §11/§12/§13 to ToC
> → writes the file
> ```
> Result: ~270 lines moved and 15 heading levels changed during what the
> directive called a "ToC fix." User has no record of the expansion.
>
> WRONG — executor reads, notices the incoherence, executes the literal scope anyway:
> ```
> (reads target file)
> → notices §11 H3-inside-H2 misplacement and §12/§13 ToC absence
> → adds only the literal §11 ToC entry; leaves §11 anchoring into §9 mid-section,
>   leaves §12/§13 absent
> → writes the file
> ```
> Result: ToC lists §11 but skips §12/§13; §11 anchor points into §9; body order
> remains non-monotonic. The "fix" publishes an internally inconsistent document.
>
> CORRECT — executor surfaces the finding in CONFIRM with two options and gates on `AskUserQuestion`:
> ```
> CONTEXT LOADED
> File: {target file}
> Current State: directive scope = "add §11 to ToC"
> Last Completed: prior task complete
> Next Action: gated on user choice below
> Structural Finding: §11 is currently H3 inside §9, and §12/§13 are absent from
>                     the ToC. Adding only §11 produces a ToC that lists §11 but
>                     skips §12/§13 and anchors §11 into a mid-section H3.
>
> Option A (Coherent): promote §11→H2, relocate after §10, promote 15 H4
>                       children→H3, add §11/§12/§13 to ToC (~270 lines moved,
>                       15 heading-level changes).
> Option B (Literal):  add only the literal §11 ToC entry; leave §11 anchored
>                       inside §9 and §12/§13 absent from ToC. Residual defect:
>                       internally inconsistent ToC vs body ordering.
> → AskUserQuestion("Choose Option A (coherent expansion) or Option B (literal scope)")
> ```

#### Audit-Trail Requirement When Expansion Is Approved

When the user picks Option A (or any expansion beyond the literal directive), the session MUST record the decision in two places:

| File | What to Record | See |
|------|----------------|-----|
| Recovery file | A row in the `Scope-Expansion Decisions` section naming: directive scope (literal), expanded scope, structural rationale, line / heading / file-touch impact, Phase-1 approval reference (timestamp or AskUserQuestion turn) | [templates/recovery.md](../templates/recovery.md) |
| Summary file | A `Scope-Expansion Decisions` block in Context Notes linking back to the Phase-1 approval reference (so later reviewers can reconcile "why did you also touch X?") | [templates/summary-template.md](../templates/summary-template.md) |

The audit trail is NOT optional when the expansion is approved. A scope-expanded execution without a Recovery + Summary trail looks indistinguishable from a silent expansion to any later reviewer.

> [!practice] When in Doubt, Surface It
> If the executor is uncertain whether a finding is "structural" enough to warrant Option A/B, surface it anyway. The cost of asking is a single `AskUserQuestion` round-trip; the cost of NOT asking is either a defective artifact or an undocumented scope expansion. Bias toward surfacing.

> [!practice] Doctrinal Sweep Before Declaring a Claim Fixed
> When the session's scope involves correcting a factual claim (a rule, a parameter, a threshold, an assertion) that is stated in a source file and cited by consumers, do NOT declare it fixed after editing the source alone. First grep the entire plugin surface for every phrasing of the claim (the exact assertion text, common paraphrases, and any regex that catches the misconception). If instances fall outside the literal task scope, surface them as a structural finding and let the user decide (Option A / Option B above). Re-run the sweep at the end of the session and confirm only correct/negated phrasings remain. A citation chain is coherent only when the source and every consumer agree.

#### Reviewer Check 062 — Phase-1 Scope-Expansion Approval Reference Required

- **Severity / Role / Type:** BLOCKER | Design-Extension Reviewer | NEW
- **What:** When a Recovery file's `Scope-Expansion Decisions` section contains a row (or when the session diff shows changes outside the literal task scope declared in the Orchestration), the row MUST cite a Phase-1 approval reference (AskUserQuestion turn or timestamp), AND the Summary file's Context Notes MUST mirror the row. Recovery without Summary mirror, or Summary without Recovery row, or a Recovery row missing the approval reference → BLOCKER.
- **Detection:**
  1. Open the session Recovery file; grep `^## Scope-Expansion Decisions` and read the table rows.
  2. For each row, verify the `Phase-1 Approval Ref` column is populated with a non-`-` value (AskUserQuestion turn or timestamp).
  3. Open the session Summary file; grep `^### Scope-Expansion Decisions` under Context Notes. Verify a mirroring row exists for each Recovery row (same Step number).
  4. If the Orchestration task scope and the session diff show file/heading/line changes outside the literal scope AND Recovery has no `Scope-Expansion Decisions` row → BLOCKER (silent expansion).
  5. If a Recovery row exists but Summary mirror is absent → BLOCKER (audit-trail gap).
  6. If a Recovery row exists but `Phase-1 Approval Ref` is `-` or empty → BLOCKER (untraceable expansion).
- **Finding template:**
```
[BLOCKER] Phase-1 scope-expansion approval reference missing
File: {Recovery file path | Summary file path | session diff}
Location: {Recovery Scope-Expansion Decisions row N | Summary Context Notes | diff hunks outside literal scope}
Issue: {silent expansion (no Recovery row) | missing Summary mirror | empty Phase-1 Approval Ref}
Fix: Add the Phase-1 approval reference + mirror per references/read-confirm-act-protocol.md §1.2 (and templates/recovery.md + templates/summary-template.md) | Confidence: HIGH
```

### 1.3 Cross-Task Coordination Flags

> [!binding] Downstream-Propagation Gate
> When a task surfaces an observation that constrains, sequences, or unlocks work in a DIFFERENT session, sprint, or plan, the orchestrator MUST (a) record the observation as a Cross-Task Coordination Flag in this session's Recovery file at the moment it is surfaced, AND (b) propagate every flag into the downstream consumer's task or orchestration file as part of session closeout. Closeout without propagation leaves the downstream agent to re-derive context the orchestrator already validated — wasting tokens at best, dropping a constraint on the floor at worst.

Apply this rule whenever an upstream task's output names a sequencing constraint, a content-routing dependency, a cluster-classification ambiguity, a release-quality tradeoff, or any other observation whose CONSUMER is a downstream task the upstream orchestrator can name. Typical patterns:

- **Sequencing constraints:** "Task X's SPLIT must land before Task Y's MOVE-IN, otherwise Y has nowhere correct to route its additions."
- **Content-routing dependencies:** "After the SPLIT, references to §A go to Part-1, references to §B go to Part-2 — downstream link updates must respect this routing."
- **Cluster-classification ambiguity:** "After the SPLIT, Part-2's topical cluster membership is unresolved; downstream themeing must pick a home."
- **Release-quality wins beyond scope:** "Doing this restructure also unlocks a base-context token reduction — flag as a candidate even though it wasn't the proximate goal."
- **Cross-plan flow-through:** an upstream plan's findings constrain the scope or sequencing of a follow-up plan that hasn't been written yet.

A flag is NOT a scope-expansion (§1.2 governs that — work done outside the literal scope) and is NOT a generic finding (those go in `Key Findings`). A flag specifically names a DOWNSTREAM consumer who needs to ACT on the observation.

#### Recording the Flag (At Surface Time)

When a task surfaces a coordination flag during execution, the orchestrator adds a row to the Recovery file's `Cross-Task Coordination Flags` section IMMEDIATELY — not at closeout. The same context-compaction risk that motivates per-task Recovery updates applies here: a flag held only in conversation context dies on the next compaction.

> [!template] Coordination Flag Row
> ```
> | Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
> |--------|-------------|---------------------|-------------|---------------------|
> | 1      | {abbrev}-S{XX}-{YY}-{##} | {abbrev}-S{XX}-{YY}-{##} or {sprint} or {plan} | {one-paragraph description of the constraint / dependency / opportunity} | {what the downstream agent should do — sequence, route, resolve, evaluate} |
> ```

#### Checking the Lessons Index Before Recording

> [!constraint] Search Before You Record
> The duplicate check conventionally attaches to lesson capture at session end; coordination flags are authored earlier and propagate immediately, so an unchecked flag can reach downstream plan files before anyone consults the index. Before recording a flag, search the lessons index for the artifact class it concerns. Where the flag and an existing lesson agree, cite the lesson rather than restating it. Where they disagree, treat the lesson as the considered position and the flag as a fresh, unreviewed reaction — reconcile toward the lesson, or argue explicitly why the lesson should change and amend it in the same edit rather than shipping its opposite alongside it. Re-deriving a documented decision is not free and does not reliably reproduce it: the second derivation sees one incident; the original saw the incident and its consequences.

#### Authoring the Flag (Spec Delta, Not Observation)

> [!constraint] A Flag That Must Change Behaviour Is a Spec Delta
> A flag that must change behaviour is a spec delta, not an observation. Name the step it supersedes and give the replacement. A flag phrased as a measurement reads as background and loses to the step it sits beside.
>
> ```markdown
> WRONG (advisory — reads as context, loses to the step):
> > [!binding] The mechanical {X} split badly understates what is decidable.
>
> CORRECT (spec delta — names the step and its replacement):
> > [!binding] Task {NN} Execution Step {N} — "{term}" is REDEFINED
> > Step {N} as written ("{old definition}") is the defect this flag exists to prevent:
> > {the measurement}. Replace the definition with {new definition}.
> > The original wording is superseded, not supplemented.
> ```
>
> The distinguishing test: does the flag tell the runner something, or tell it to do something differently? If the second, it must name the step.

A Coordination Flag Row is either **informational** — safe to deliver as context; spawn-prompt injection alone suffices — or a **binding contract**, which must be reconciled against the receiving task's own Execution Steps, Success Criteria, and Schema Pins before dispatch, and must be authored as a spec delta per the callout above. See [handlers/run.md](../handlers/run.md) Step 1.1a's Flag-Reconciliation Preflight — its "a binding contract belongs in the task file so it survives session resumption and is visible to reviewers" sentence is the vocabulary source for this distinction; it is not re-derived here.

#### Conditional Spec Branches Are Flags

> [!constraint] An Unresolved Conditional Branch Is a Flag, Not a Finished Spec
> A task-file criterion of the form "expect X if the upstream step found Y; otherwise Z" is a flag-shaped hole, not a finished specification. Writing both branches at scaffold time is correct — the author declined to guess a fact nobody had measured. But the branch is an open dependency, and resolving it once the measurement lands is the orchestrator's job at post-task time, not the runner's job at read time. Being present in an artifact the task lists as Required Context is NOT sufficient — Required Context establishes the runner MAY read it, not that they will connect a number in an unrelated table to a conditional several sections away. The default (assert) branch is not the safe one: on a false positive it manufactures a defect report against correct work, at exactly the moment the team is primed to believe it. Resolve the branch from the landed measurement and write it into the consuming task as a binding contract with evidence inline.

#### Propagating the Flag (At Closeout)

At Phase 4 closeout, the orchestrator MUST add each flag to the downstream consumer's task file (preferred) or orchestration file. The destination depends on who the consumer is:

| Downstream Consumer | Propagate To |
|---------------------|--------------|
| A specific named task in a later session | That task's file under a `## Pre-Known Cross-Task Coordination Flags` section |
| A whole session (consumer task unclear) | That session's orchestration file under a `## Pre-Known Cross-Task Coordination Flags` section |
| A future sprint (consumer task not yet authored) | The sprint plan's `## Carried-Forward Coordination Flags` section, to be re-propagated when tasks are scaffolded |
| A follow-up plan not yet written | The current Master Plan's `## Carried-Forward Coordination Flags` section + the rollup/handoff task file |

Each propagated entry MUST be tagged with the source session ID and the surface date so the downstream agent recognizes it as orchestrator-validated context (do NOT re-derive) and can age it for staleness.

> [!template] Propagated Flag Block
> ```markdown
> ## Pre-Known Cross-Task Coordination Flags
>
> These flags were surfaced and reconciled by upstream session orchestrators. Treat them as orchestrator-validated context — do NOT re-derive.
>
> ### From {source-session-id} ({source-session-name}) — recorded {YYYY-MM-DD}
>
> 1. **{Short flag headline}.** {Paragraph describing the constraint / dependency / opportunity and the recommended action.}
> 2. **{Short flag headline}.** {...}
>
> ### From {next-source-session-id} — to be appended when session completes
>
> *(none yet)*
> ```

The reserved placeholder for later sources is intentional — it tells future closeout orchestrators where to append without re-deriving the section structure.

#### Audit-Trail Requirement

| File | What to Record | See |
|------|----------------|-----|
| Recovery file | A row in the `Cross-Task Coordination Flags` section per flag | [templates/recovery.md](../templates/recovery.md) |
| Summary file | A `Cross-Task Coordination Flags` block in Context Notes mirroring the Recovery rows (so later reviewers see what was handed off without opening Recovery) | [templates/summary-template.md](../templates/summary-template.md) |
| Downstream task / orchestration / sprint plan | A `Pre-Known Cross-Task Coordination Flags` section per the propagation table above | — |

Mirror requirement is the same as §1.2: a flag recorded only in Recovery and never propagated looks indistinguishable from a dropped constraint to any later reviewer.

> [!constraint] Flag Lifecycle Discipline
> WRONG — task surfaces a coordination flag in conversation, orchestrator notes it mentally, never writes it down:
> ```
> (task 03 completes, reports "by the way, this SPLIT has to precede task 04's MOVE-IN")
> → orchestrator: "noted, I'll remember"
> → continues to task 04
> → next session orchestrator never sees the flag
> ```
> Result: downstream agent either re-discovers the constraint (cost: tokens + risk of missing it) or executes in the wrong order and breaks the artifact.
>
> WRONG — orchestrator writes flag to Recovery but never propagates at closeout:
> ```
> (records flag in Recovery `Cross-Task Coordination Flags` section)
> → closeout runs through summary, lessons, git commit
> → flag stays buried in upstream Recovery; downstream task file never updated
> → downstream agent reads only its own task file → flag is invisible
> ```
> Result: a recorded-but-stranded flag is functionally identical to a dropped one.
>
> CORRECT — surface-time recording in Recovery, closeout-time propagation to downstream:
> ```
> (task surfaces flag)
> → orchestrator writes Recovery row immediately
> → Phase 4 closeout reads every Recovery flag row
> → for each row, propagates to the downstream consumer per the destination table
> → tagged with source session + date so the downstream agent treats as validated context
> ```

> [!practice] Default to Propagation
> If the consumer is ambiguous between a specific task and a whole session, propagate to BOTH — the task file for the agent that will act on it, the orchestration file for the orchestrator who will dispatch. Cost of duplication is two short paragraphs; cost of misrouting is a missed constraint.

---

*Anchor: [session-execution-protocol.md](session-execution-protocol.md) — §2-§7 operational session rules (Reference Documents, Settings Modification Protocol, Session Rules, Discovery/Meta-Plan Status Gates, Task Tracking, Refactoring Safety, Git Workflow).*
