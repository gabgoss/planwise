---
description: Mandatory READ-CONFIRM-ACT pattern — confirmation block, structural-findings gate, cross-task coordination flags (sender §1.3, including an ordering flag read against the pinned command, a produce-flag reconciled against the write-set, and a Key Finding that names another session's file re-filed as a flag; receiver-side reconciliation §1.4), attributing a dirty path before choosing a remedy (§1.5), probing a commit-shaped criterion's paths in `git log` at CONFIRM so history satisfies it (§1.6), and reading two disagreeing representations through their writers before calling either stale (§1.7)
---

# READ-CONFIRM-ACT Protocol

> [!binding] Enforcement
> These are not guidelines. Violations cause context loss and incomplete work.

**Purpose:** Mandatory READ-CONFIRM-ACT pattern — confirmation block, structural-findings gate, cross-task coordination flags (sender §1.3, receiver-side reconciliation §1.4), dirty-path attribution (§1.5), commit-shaped criteria satisfied by history (§1.6), and disagreeing representations read through their writers before either is called stale (§1.7).
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

A flag is NOT a scope-expansion (§1.2 governs that — work done outside the literal scope) and is NOT a generic finding (those go in `Key Findings`, unless the observation names a file or task another session owns — see "A Key Finding That Names Another Session's File Is a Flag" below). A flag specifically names a DOWNSTREAM consumer who needs to ACT on the observation.

#### Recording the Flag (At Surface Time)

When a task surfaces a coordination flag during execution, the orchestrator adds a row to the Recovery file's `Cross-Task Coordination Flags` section IMMEDIATELY — not at closeout. The same context-compaction risk that motivates per-task Recovery updates applies here: a flag held only in conversation context dies on the next compaction.

> [!template] Coordination Flag Row
> ```
> | Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
> |--------|-------------|---------------------|-------------|---------------------|
> | 1      | {abbrev}-S{XX}-{YY}-{##} | {abbrev}-S{XX}-{YY}-{##} or {sprint} or {plan} | {one-paragraph description of the constraint / dependency / opportunity} | {what the downstream agent should do — sequence, route, resolve, evaluate} |
> ```

#### A Key Finding That Names Another Session's File Is a Flag

**Moved.** This subsection lives in [read-confirm-act-protocol-Part-2-FlagAuthoringSurfaces.md](read-confirm-act-protocol-Part-2-FlagAuthoringSurfaces.md), split out when this file neared the Read-tool token gate. The test for a flag is whether the observation names a file or task that a different session owns and that session must act on it. If so, re-file the `Key Findings` bullet as a `Cross-Task Coordination Flags` row at the moment it is written, because closeout propagates only that table.

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

The test applies to the write-set as well as to the steps. A flag that makes the task produce three artifacts where the brief declares one tells the runner to do something differently, even when no step forbids it. See "A Produce-Flag Is a Write-Set Delta" below.

A Coordination Flag Row is either **informational** — safe to deliver as context; spawn-prompt injection alone suffices — or a **binding contract**, which must be reconciled against the receiving task's own Execution Steps, Success Criteria, Schema Pins, `**Output:**` line, and the orchestration's write-target row before dispatch, and must be authored as a spec delta per the callout above. See [handlers/run.md](../handlers/run.md) Step 1.1a's Flag-Reconciliation Preflight — its "a binding contract belongs in the task file so it survives session resumption and is visible to reviewers" sentence is the vocabulary source for this distinction; it is not re-derived here.

#### A Produce-Flag Is a Write-Set Delta

**Moved.** This subsection lives in the Part-2 file named above. A flag that tells a task to file, write or create something changes the task's write-set. Reconcile it against the `**Output:**` line, the orchestration's write-target row and the sprint write-set, and count produce-verbs against the `Output:` artifact count before CONFIRM.

#### An Ordering Flag Reads the Pinned Command First

**Moved.** This subsection lives in the Part-2 file named above. Before writing "run X before Y", read X's pinned command and ask what Y produces. State the intent beside the order. A receiver resolves a contradiction through a spec delta, never a quiet reorder.

#### Conditional Spec Branches Are Flags

> [!constraint] An Unresolved Conditional Branch Is a Flag, Not a Finished Spec
> A task-file criterion of the form "expect X if the upstream step found Y; otherwise Z" is a flag-shaped hole, not a finished specification. Writing both branches at scaffold time is correct — the author declined to guess a fact nobody had measured. But the branch is an open dependency, and resolving it once the measurement lands is the orchestrator's job at post-task time, not the runner's job at read time. Being present in an artifact the task lists as Required Context is NOT sufficient — Required Context establishes the runner MAY read it, not that they will connect a number in an unrelated table to a conditional several sections away. The default (assert) branch is not the safe one: on a false positive it manufactures a defect report against correct work, at exactly the moment the team is primed to believe it. Resolve the branch from the landed measurement and write it into the consuming task as a binding contract with evidence inline.

#### Propagating the Flag (At Closeout)

A flag reaches an executing task in **two hops**, and each hop has exactly one owner. At Phase 4 closeout the closing orchestrator (the **sender**) MUST deliver each flag to the downstream consumer's **front door** — an orchestration file, a sprint plan, or a Master Plan — and never into another session's task files. The downstream session's orchestrator (the **receiver**) routes each flag the last hop into its own task files at its Phase-1 Flag-Reconciliation Preflight ([handlers/run.md](../handlers/run.md) Step 1.1a): it is the single writer of its own decomposition, it already reads every task file, and it re-derives every value the flag supplies before acting on it. The destination depends on who the consumer is:

| Downstream Consumer | Propagate To |
|---------------------|--------------|
| A specific named task in a later session that is already scaffolded on disk | That session's orchestration file under a `## Pre-Known Cross-Task Coordination Flags` section, naming the consuming task — the receiver routes it into that task's file at Step 1.1a |
| A whole session (consumer task unclear) | That session's orchestration file under a `## Pre-Known Cross-Task Coordination Flags` section |
| A future sprint (downstream session not yet scaffolded on disk) | The sprint plan's `## Carried-Forward Coordination Flags` section, to be re-propagated when tasks are scaffolded |
| A follow-up plan not yet written | The current Master Plan's `## Carried-Forward Coordination Flags` section + the rollup/handoff task file |

> [!constraint] The sender delivers to the front door; the receiver routes the last hop and stamps it
> WRONG — the closing session writes the flag straight into a downstream task file. That bypasses the receiving orchestrator's dispatch-time validation entirely: nothing re-derives the flag's counts, scope forecast or supplied gate when the gap finally clears (in one measured case every authoring-time consumer had already completed and the corpus figures had turned over before the flag reached a runner), and a concurrent session editing the same task files is raced.
> CORRECT — the sender writes the entry at the front door, tagged as below. At its Step 1.1a the receiver routes it into the task file(s) and stamps the entry in place, so the delivery is auditable from either end:
> ```
> ✅ ROUTED {YYYY-MM-DD} into {task file} § Pre-Known Cross-Task Coordination Flags
> ```
> An entry with no stamp after the receiving session's Phase 1 is an unrouted flag, and the receiver's Recovery routing table (Step 1.1a) is where the miss is recorded.

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

#### Shared-File Flags Must Be Reciprocal

> [!constraint] A flag about a file two writers share must be reciprocal
> When a coordination flag concerns a file that **more than one** sprint or session writes, the flag must be **reciprocal**: each writer's flag chain names the other writer(s) and the shared path — not only the one direction the surfacing task happened to be looking in.
>
> The reason is arithmetic, not etiquette. A one-directional flag lets each writer measure a **shared** threshold — a file-size gate, a line budget, a section-count cap — against **its own contribution alone**, while the baseline it measures from has already been moved by the writer it was never told about. Both readings pass; the combined result breaches. Each writer's arithmetic is locally correct, which is exactly why the breach survives both reviews: nothing either writer can see from where it stands is wrong.
>
> The return edge goes to the **same destinations the propagation table above already defines** — the named task's file, the session's orchestration file, the sprint plan's `## Carried-Forward Coordination Flags` section, or the Master Plan — applied in **both** directions, each entry tagged with its own source session ID and surface date. Propagating one direction and leaving the other for a downstream orchestrator to infer fails the same way as not propagating at all: the writer who was never named has no reason to go looking, and a threshold nobody was told they share is measured by each of them alone.
>
> The plan-level counterpart is [scaffolding-hygiene-Part-2-DerivationAndParallelism.md](scaffolding-hygiene-Part-2-DerivationAndParallelism.md) §16.5, which imposes the same reciprocal requirement on cross-sprint flags at scaffold time, where the write-sets that make a file shared are first declared. This section governs the same reciprocity at flag-propagation time.

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

### 1.4 Reconciling an Inherited Flag (Receiver Side)

§1.3 governs the sender — how a flag is recorded, authored and propagated. This section governs the receiver: the session that inherits a flag and has to act on it. The two failure modes are symmetric. The receiver reads too few sources, and it trusts the ones it does read too much.

#### 1.4.A Enumerate the input set before reading any of it

The preflight's first step is to enumerate its sources, not to open one file. A preflight that reads its single named source, finds nothing missing there, and reports success has proved nothing. The failure is silent in the passing direction.

> [!checklist] The four flag sources — read ALL of them
> - [ ] This session's own orchestration file, `## Pre-Known Cross-Task Coordination Flags`
> - [ ] **Every immediately-upstream session's Recovery `Cross-Task Coordination Flags` table** — the session(s) named in this session's `Prerequisite:` field
> - [ ] The sprint plan's `## Carried-Forward Coordination Flags` section
> - [ ] The Master Plan's `## Carried-Forward Coordination Flags` section
>
> Then **diff that union against what actually appears in the task files**, and route the difference. Record the routing as a table, one row per flag, so the count is auditable rather than asserted:
>
> | Flag | Source file | Destination task | Disposition |
> |---|---|---|---|
> | {headline} | {upstream Recovery / sprint plan / orchestration / Master Plan} | {task-id}, or "none — no consumer in this session" | routed / already present / resolved-with-measurement / no consumer |
>
> **A flag with no task-file hit is unrouted, however many plan files mention it.** Presence in a plan file is not routing.

The upstream Recovery table is the source most often left out, and it carries the highest-value class: flags discovered by doing the work, which no planner could have written at scaffold time. In one measured preflight nine flags had reached zero task files. Five of them — every flag raised by the immediately preceding session — lived only in that session's Recovery. One of the five recorded a measurement that **resolved** a conditional blocker; without it the downstream battery would have recorded a passing criterion as BLOCKED against a user decision that was never required. Another assigned a fourth work item no task owned, against criteria reading "all 3 sites".

#### 1.4.B The scaffold-vs-execute seam

A sprint-plan `Carried-Forward` entry reaches a session only at *that session's scaffold time*. Once the session exists on disk it never re-reads the sprint plan. A flag dropped there afterwards is invisible. The sender did its job, the receiver never looks again, and the flag dies in a file both parties consider correct.

So the upstream Recovery sweep in §1.4.A is not a convenience. It is the only path an execution-time flag has into an already-scaffolded session.

#### 1.4.C Treat the location as reliable and every value as expired

> [!constraint] The flag tells you where to look, never what you will find
> A flag's **location** — the file, the symbol, the section it points at — is usually still good. Every **value** it carries is expired by the time you read it. Three things go stale independently, and each needs its own re-derivation:
>
> 1. **The defect may already be gone.** Grep for the **defect**, not for the fix. An unrelated sweep can close a flagged problem without ever touching the flag. One flag reporting five identifier leaks measured **0** tree-wide.
> 2. **A supplied count may be wrong — and the flag's own verify command may encode it.** Re-derive every count a flag hands you, including one that looks freshly written. A flag asserting "the handler count is now 10" measured **13**, and shipped a gate returning 10.
> 3. **A scope forecast may be wrong in MEMBERSHIP, not only in size.** Compute the final set from measurements. **Never sum the forecasts.** Two flags each forecasting the final write-set produced a *different* seven than either had predicted.
>
> Item 2 is the expensive direction. A stale gate that fails correct work reads as *"your fix is broken"*, not as *"my number is old"* — so the reader debugs a fix that was right.
>
> WRONG — run the flag's supplied gate against the fix and believe the result:
> ```
> flag: "handler count is now 10; verify with the count gate below"
> → apply the fix → run the flag's gate → returns 13, expected 10 → FAIL
> → conclude the fix is broken and start debugging correct work
> ```
> CORRECT — re-derive the count first, then reconcile the two readings:
> ```
> → measure the live tree BEFORE trusting the gate → 13 handlers
> → the flag's 10 was correct on the day it was written; 3 landed since
> → both numbers are real and mean different things
> → update the gate to 13; write text that contradicts neither reading
> ```

#### 1.4.D Re-derive the CONCLUSION, not just the count

> [!constraint] A flag's classification and its prescribed remedy are claims too
> §1.4.C expires a flag's *magnitudes*. This expires its *judgements*. A flag's classification of a finding, and the fix it prescribes, are each still plausible on their face and each capable of being wrong once traced.
>
> Two worked shapes:
>
> - **The classification does not survive tracing.** A finding correctly identified a concrete identifier, and prescribed rewriting it as a placeholder. Tracing showed the surrounding fields of that structured example are concrete **by design** — demonstrating their composition is the example's whole purpose — so the prescribed rewrite would have left the example internally incoherent.
> - **The count is wrong in the direction that inverts the remedy.** At one outlier against a canonical form, "make the outlier conform" is right. At three of six call sites, each carrying real distinguishing meaning, the correct fix is the opposite one: widen the canonical. The same remedy is right or backwards depending on a number the flag supplied.
>
> **Where a flag says "this is a defect, fix it thus", verify both halves** — that it is a defect, and that the prescribed fix does not degrade the artifact.
>
> Both failing flags came from sessions that had done real work and written carefully. Diligence at write time is not what expires. The corpus moving underneath the flag is.

#### 1.4.E Preserve the sender's text; record the correction beside it

> [!constraint] Never silently rewrite a flag to match reality
> The sender's wording is the trace a later reviewer needs to understand why the executed scope differs from the recorded plan. A quietly edited flag destroys the evidence that reality moved — it leaves a plan that looks like it always said the right thing, and no record of the correction. Keep the original text and record the re-derived value, the classification change, or the retraction **beside** it, with the measurement that settled it.
>
> Routing corollary: a **conditional** flag whose condition was measured and **not** met is routed as *resolved, with its measurement*, not dropped and not left open. "Flag exists" and "flag is open" are different facts. A downstream runner that re-evaluates stale conditional text from scratch can reach the opposite conclusion.

#### 1.4.F Verify a claim before laundering it into a flag

> [!constraint] A maintenance note asserting a defect elsewhere is a citation, and rots identically
> A precise, confidently-worded note is not evidence. In one measured case every factual claim in such a note was false: the cited symbol existed nowhere in the tree except the note itself, the line locator pointed at a different section, the named catalog row was about a different file, and the real row already cited correctly. Of three forward-references examined in one session, two were defective.
>
> Three checks, before the claim goes anywhere:
>
> 1. **Grep for the cited symbol tree-wide**, not only at the named location. If the only hit is the note itself, the claim is dead. This one command settles most cases.
> 2. **Check the locator independently.** Line numbers drift with every edit above them, so a locator is a hint, never an address.
> 3. **Check whether the defect was already fixed.** This is the most common failure mode and the easiest to mistake for live work.
>
> Then dispose of it:
>
> | Verdict | Disposition |
> |---|---|
> | Claim false | Delete the false clause. Keep any load-bearing instruction sitting beside it — the note may be wrong about the defect and still right about the procedure. |
> | Claim true | Act on it, and record the **generic condition** ("until a transfer flow exists"), never a schedule naming a specific plan or session. |
>
> **Do not launder an unverified claim into a coordination flag.** A flag carries institutional authority: the receiving session treats it as established fact and routes it straight into a task file. Recording "the note says X" as "do X" moves a rotted citation into a plan artifact, where it is harder to challenge and further from the evidence than it was in the note.
>
> Verify in **both** directions. When a subordinate agent challenges a flag, re-derive from primary evidence rather than deferring to either party's confidence.

#### 1.4.G Resolve the claim's REFERENT before re-deriving its truth

> [!constraint] A check confirms a true statement about whichever object it was pointed at
> §1.4.C expires a flag's values. §1.4.D expires its judgements. Both assume the claim's **referent** is unambiguous, and that only its truth value can drift. When the referent is the thing that is wrong, running the check harder converges on the same wrong answer.
>
> Nothing in a reproducing measurement reports which object it measured. The confirmation therefore reads identically whether the referent was right or wrong.
>
> ```bash
> # WRONG — confirms the claim inside the scope the claim chose:
> grep -n '<positional-label>' <the-one-file-the-claim-named>   # → nothing. Claim "confirmed".
>
> # CORRECT — asks whether the SUBJECT is referenced anywhere at all:
> grep -rn '<subject-symbol>' <whole-tree> | grep -v '<subject-own-file>'
> ```
>
> Both greps are correct. Both return what they should. The referent table is what makes the failure legible:
>
> | | The claim | What was checked | Verdict |
> |---|---|---|---|
> | Referent | "the agent is dispatched from nowhere" | the one handler the claim named | correctly identified as dispatching nothing |
> | Referent actually needed | the same agent | the *other* handler, carrying its own route of the same name | never looked at |
>
> **The CORRECT grep excludes the subject's own file, and that exclusion is load-bearing.** A definition site is not a caller. The subject's own file always contains the symbol, so leaving it in the result set guarantees at least one hit — which turns an absence check into a tautology.

Three corollaries follow.

- **An absence claim is only as wide as the search that produced it.** Grep for the thing alleged to be orphaned, never for the container alleged to be empty.
- **A short, positional identifier is a warning sign.** `Route C`, `Step 3`, `Phase 2` and `stage 4` are labels that recur across files by construction. An inherited claim hinging on one must have its referent resolved before anything acts on it.
- **Where an inherited claim prescribes a fix, check the fix against the live tree, not just the claim.** "Wire X so the citation becomes true" is falsified the moment X turns out already wired. That check is one grep, and it holds independently of whether the claim itself reproduces. §1.4.D requires verifying that a prescribed fix does not degrade the artifact. This requires verifying that the fix is still needed at all.

The same shape appears wherever a coordination artifact hands forward a defect *description* rather than a defect *location* — a section number that exists in two files, a step number two handlers both use, a config key present in a template and in an instance. The receiving session re-measures faithfully inside the frame it was handed, and the frame is the error.

The cost is not tidiness. In the measured case, acting on the confirmed claim would have added a second dispatcher for an already-dispatched agent. That manufactures the exact defect the work existed to remove, and reports the row closed.

#### 1.4.H Availability is not applicability — verify the source covers the scope it is cited for

> [!practice] A presence check measures the wrong property, and reads exactly like measuring the right one
> ```
> WRONG — the dependency check that shipped:
> file exists?  ✅   wc -l → 2,325   → record "Present", assign to the PreToolUse cluster
>
> CORRECT — one additional question, answerable in a single call:
> file exists?  ✅   does it REGISTER for the event I am citing it for?
>   grep -nE '"(PreToolUse|PostToolUse|Stop)"' hooks.json   → no PreToolUse key → NOT ground truth
> ```
>
> A source can be genuinely rich and still be rich about the wrong thing. That asymmetry is the whole point:
>
> | Fact class | Transfers to the cited event? | Why |
> |---|---|---|
> | `tool_input` shapes | **Yes** | the same object is passed at both events |
> | `tool_response` shapes (`stdout`/`stderr`/`interrupted`, no `exit_code`) | **No** | `tool_response` does not exist before the tool runs |

Ask the applicability question of every cited source. It generalises by artifact class:

| Citing a… | Availability check | Applicability check |
|---|---|---|
| Hook script, for an event's contract | file exists | its manifest registers **that event** |
| Test file, as coverage for a behaviour | file exists | a test in it actually exercises that behaviour |
| Doc page, as the spec for a field | page loads | the page documents **that** field, not a sibling |
| Reference implementation, for a version | repo present | it targets the version under discussion |

Three guardrails govern what you do with the answer.

- **A presence check produces a concrete measurement of the wrong property**, and that reads exactly like a concrete measurement of the right one. `2,325 lines` and `✅ Present` feel like verification.
- **A rich source that fails the applicability check is re-scoped, not discarded.** It stops being the second independent implementation a criterion counted on. It remains excellent evidence for the events it does register.
- **Label the event, version or platform on every extracted fact.** Once one source spans several, an unlabelled fact is un-auditable, and downstream readers will silently promote it into the wrong contract.

The cost asymmetry is stark. The applicability check above was one grep of a 96-line manifest at plan time. Skipping it surfaced the problem inside the session's largest task, where it cost a coordination flag, a re-brief and a weakened exit criterion.

This check is deliberately not written as one universal command. It is artifact-class-specific — a manifest for a hook, a test body for a test file, a version target for a reference implementation. A one-size command would be exactly the concrete measurement of the wrong property this section warns about.

#### 1.4.I An existence claim expires differently from a count — deliver the RESULT, not the claim

> [!constraint] Counts get re-measured by habit — existence claims rot
> §1.4.C item 1 already requires grepping for the defect rather than for the fix. This section governs what you owe **downstream** when that grep returns zero on a claim you are about to relay.
>
> Nothing in a flag's own text changes when the tree does. So run both commands before relaying any carried ABSENT / EXISTS / UNVERIFIED claim:
>
> ```bash
> # does the thing still exist?
> grep -rn '<the string>' <tree>
> # if not, WHEN did it stop existing — the answer belongs in the handoff
> git log -S'<the string>' -- <the named files>
> ```
>
> Then deliver the **result**, not the claim: `DISCHARGED, closed by <commit>`. Never silently drop it — the next scaffold re-adds it from the sprint plan. Never pass it on unqualified either.

**The danger inverts on relay.** As a *prohibition* an expired scope boundary is harmless, forbidding an action nobody can take. As an *open item* delivered downstream it is actively dangerous, because **a "fix this absence" instruction handed to an agent whose job is filling absences can produce the defect it was written to prevent.**

Three tells identify the class before it bites.

- A flag phrased as a scope boundary ("do NOT fix X") is a latent existence claim.
- A flag whose recorded date precedes any refactor commit touching its named files is suspect by construction.
- A runner's politely-framed disagreement ("returns zero, before and after my edit") is a finding, not noise.

Preflight figures save real work and should keep being handed down. One standing clause is what makes handing them down safe, and every spawn prompt carrying a preflight figure MUST carry it verbatim:

> **"if a live measurement disagrees, the live measurement wins — report the disagreement."**

The clause earns its place only when runners actually exercise it. Recovering the case above depended on a runner doing exactly that.

#### 1.4.J The refresh you produce is itself a derived artifact — dry-run its own claims before dispatch

> [!constraint] A successor map feels like ground truth because it was just measured
> A refresh exists to protect downstream agents from stale claims. It is produced by the same inference shortcuts it exists to protect against, and every downstream agent consumes it as authoritative. **A wrong entry is worse than a stale task file, because the task file announces its age while the map announces freshness.**
>
> Four entries in one ten-file refresh were wrong. Each came from treating a cheap proxy as the fact:
>
> | Asserted in the refresh | Live reality | The proxy that produced the error |
> |---|---|---|
> | pointer "ends near §1.15" | reads `§1.1–§1.18` | read the **shipped cache** copy, not the dev tree |
> | "both files carry section X" | one hosts it; the other merely *mentions* it | counted `grep` hits without checking for a **heading** |
> | "the subcommand count is no longer N" | still N — a retirement changed a row's **disposition** | inferred a count change from a file deletion |
> | "symbol moved out of `<module>`" | still **defined** there; others **import** it | read a `grep -l` filename list as evidence of relocation |
>
> Distinguish all four explicitly, in their generic form:
>
> - definition vs **import** — `Grep` the symbol with `output_mode='content'`, never a `files_with_matches` filename list
> - heading vs **mention** — `Grep` for `^#+.*X`, not for a bare `X`
> - existence vs **disposition** — a row can survive with new behaviour
> - dev tree vs **shipped cache** — they diverge, so name which one you read

The dispatching side carries two obligations.

- **Tell the runners the map is fallible, and require corrections as an explicit status-block field** rather than an afterthought. All four errors above were caught only because that field existed. It is what makes shipping an unverified map safe.
- **Verify each correction yourself before propagating it.** A runner's correction is also a derived claim. Two of these were confirmed only after an independent heading dump and a definition-vs-import check.

One authoring rule follows. Prefer stating the *generic condition* over a specific number wherever the runner will re-derive anyway. An unnecessary figure in a brief is a liability with no upside.

### 1.5 Attribute a Dirty Path Before Choosing a Remedy

> [!constraint] A whole-tree gate and a revert authority both assume one writer
> Gates that read a whole tree assume one writer. So does any revert authority. The first moment to find a second writer is Phase 1, before a base is pinned. After the pin, the peer's edits are indistinguishable from this session's. A remedy aimed at this session's mistakes then lands on someone else's work.
>
> A plan's clean-tree precondition was written against the tree at authoring time. At session start, an idle peer session had left four modified files in the tree. Dispatched as-is, the first task would HALT on its clean-tree gate. Had the tree been accepted dirty, a later gate task holding revert authority (`git checkout -- <path>`) would have destroyed the peer's finished work.
>
> WRONG — dispatch the first task and let its clean-tree gate find the peer work:
> ```
> Phase 1 CONFIRM -> dispatch Task 1 -> gate: tree dirty -> HALT
>   (or, with a looser gate: pin base = HEAD over a dirty tree
>    -> gate task: "never-edit file changed" -> git checkout -- <peer's file>)
> ```
> CORRECT — read every repo at Phase 1, attribute each dirty path, decide before dispatch:
> ```
> git status --porcelain                              # outer repo
> git -C <nested repo> status --porcelain             # nested repo
> # a dirty path the plan did not write -> find its owner (backlog item, peer session)
> # surface as a structural finding: commit it as its own work item / wait for the owner / stop
> # if committing: verify first (suite + pinned linter), stage by name, commit by pathspec,
> #   and only then let Task 1 pin the base
> ```

Three operative rules follow.

1. **Read every repo at Phase 1.** The Phase 1 READ includes `git status --porcelain` on every repo the session touches, nested repos included.
2. **Attribute before you remedy.** A dirty path is foreign until this session's Files Modified list claims it. HALT, revert, and override are remedies for this session's own changes only.
3. **Committing a peer's finished work is the user's decision.** Surface it in the CONFIRM block as a structural finding (§1.2) with explicit options: commit the peer's work here after verification, the owner commits it, or dispatch literally and HALT. Record the approval reference and name the peer's item in the commit message.

**Closeout counterpart.** The session-end form of the same hazard is a bare commit that sweeps another session's staged entries, and a prior-sprint guard finding that accuses the closing session of a change a peer made. [session-execution-protocol.md](session-execution-protocol.md) §7 carries the commit-by-pathspec rule, and the run handler's Step 4.0 carries the foreign-mutation disposition.

### 1.6 A Commit-Shaped Criterion Is Probed at CONFIRM and Satisfied by History, Not by Re-Committing

> [!constraint] A criterion "make commit X" is a recorded claim about the tree, and any session that shares the tree can commit first
> The criterion decays like every other recorded claim. When a peer commits first, the criterion is not failed and not blocked. History satisfies it. The task that owns the criterion records that evidence. It does not manufacture an empty commit and does not halt forever.
>
> A plan ended with a commit task. It asked for two commits on the outer repository: a reference file with its index row first, then a proof-of-concept folder, with `git status --porcelain` showing nothing else changed. The task pinned the expected status entries (`??` for the two new paths, ` M` for the index) and halted on any deviation. The master plan and the sprint plan each carried the same criterion.
>
> Two days later an external commit titled "Commit" swept both reference files, the folder's README and a large batch from another plan into history. By the next session's start the tree was clean, the folder was tracked (87 files), and `git log --oneline -- <the two paths>` named two commits. The task as written halted at step 1 with nothing to stage. The session surfaced it at CONFIRM as a structural finding. The user chose one commit of the session's own deliverables (the finalized README and a new memo). The commit proof recorded the history evidence for the content the first commit would have carried. The plan criterion was amended at closeout.
>
> WRONG — execute the task as pinned against a tree another session already committed:
> ```
> git status --porcelain             -> (empty)
> git add -- <two reference paths>   -> nothing staged
> git diff --cached --name-only      -> (empty) != the two paths -> HALT
> # criterion "two commits" stays unmet; the session's own README and memo stay uncommitted
> ```
> CORRECT — probe at CONFIRM, commit the session's own work, cite history for the rest:
> ```
> git log --oneline -- <two reference paths>   -> <hash-a>, <hash-b>
> Option A: one commit of README.md + <memo>.md, staged by path, proven
> Commits proof, "Original criterion" heading: the clause quoted + "first commit's content is in history at <hash-a> / <hash-b>"
> master plan criterion amended with the three hashes
> ```

Three operative rules follow.

1. **Probe history at CONFIRM, before dispatch.** For every path a commit task pins, run `git status --porcelain` and `git log --oneline -- <paths>` during READ. A clean tree with the paths already in history is a structural finding for the Option A / Option B gate (§1.2). It is not a runtime halt three tasks later.
2. **Rewrite the task to commit what this session produced.** The session's own deliverables are still uncommitted at that point. Scope the commit to them. Keep the by-path staging and the `git diff --cached --name-only` proof. Put the history hashes for the overtaken content in the proof file beside the original criterion, quoted.
3. **Amend the plan criterion at closeout, with the hashes.** "Two commits" becomes "deliverables in history: <paths> via <hash>, <paths> via <hash>". A criterion left unamended reads as unmet to the next reviewer. Amend it in the master plan and the sprint plan both.

**Sibling note.** The gate-side failure is a concurrent session's sweep making every `HEAD`-relative diff gate under-inspect. This rule is the criterion side: the same sweep makes a commit-shaped criterion unsatisfiable by action. The remedy is evidence, not action. [measure-artifact-identity.md](measure-artifact-identity.md) § "Commit Only What This Session Wrote" carries the shared-tree commit-scope rule, and §1.5 above carries the attribution of a dirty path.

### 1.7 Two Disagreeing Representations Are Read Through Their Writers Before Either Is Called Stale

> [!constraint] A disagreement names the writers, not the wrong side
> When two representations of one fact disagree (an index row and its source file, a plan status and a narrative note, a record and the tree), the disagreement says something about their writers. It does not say which side is wrong. A status line that reads as lagging may be a reset mechanism's deliberate restored state. A "fix" at source is then overwritten at the next reset, and the real stale side (often a derived index row the reset never restored) stays stale.
>
> Before calling a status line stale, take three steps:
> 1. **Read the file's declared writers.** `Grep` its decisions for "writer", "reset", "restore", "fixture".
> 2. **Read the line's git history.** `git log -L<line>,<line>:<file>` shows whether the current value was restored on purpose after the "newer" value.
> 3. **Present both options with that evidence in the CONFIRM block**, as an Option A / Option B pair (§1.2). Recommend "accept as-is" when a reset mechanism owns the line. The user decides.
>
> WRONG — index row says IN_PROGRESS, Master Plan says READY_TO_EXECUTE; call the Master Plan stale and edit it:
> ```
> read both values -> the index and a narrative note agree -> edit <plan> Status line to IN_PROGRESS
> (the next reset restores READY_TO_EXECUTE and the edit is lost; the index row stays out of sync)
> ```
> CORRECT — read the writers and the line's history before proposing any edit:
> ```
> Grep "writer|reset|restore|fixture" in <plan>'s decisions
>   -> a decision names <reset script> as the only writer outside /planwise run
> git log -L4,4:<plan>/Master-Plan.md
>   -> commit A set line 4 to IN_PROGRESS; the next commit deliberately restored READY_TO_EXECUTE
> present Option A (edit the Master Plan) and Option B (accept as-is, regenerate the index row)
>   with that evidence; recommend Option B; the user decides
> ```

**Scope.** The rule applies to status reconciliation between an index and its source files, including cutovers, migrations, and drift audits. It also applies to any plan tree that holds test fixtures beside real plans. A reset script is one declared writer. A hook, a generator, and a migration are others.

**Where it is applied.** [index-drift-audit.md](index-drift-audit.md) § "A Disagreeing Pair Is Read Through Its Writers Before Any Source File Is Edited" carries the audit-side form. [plans-schema.md](plans-schema.md) § "The One-Writer Rule" names the writers of a Master Plan's `**Status:**` line.

---

*Anchor: [session-execution-protocol.md](session-execution-protocol.md) — §2-§7 operational session rules (Reference Documents, Settings Modification Protocol, Session Rules, Discovery/Meta-Plan Status Gates, Task Tracking, Refactoring Safety, Git Workflow).*
