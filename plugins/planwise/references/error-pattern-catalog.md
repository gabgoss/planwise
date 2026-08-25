---
description: Error Pattern Catalog for /planwise review -- the quick-reference table of common plan-authoring defects and their severity classification, plus the mechanical DELEGATED-trigger-named check. Row numbers are cited externally and MUST NOT be renumbered.
---

# Error Pattern Catalog

**Purpose:** Quick reference for common plan-authoring error patterns and their correct severity classification. Used by the lead during `/planwise review` synthesis, and cited by row number from other planwise artifacts.
**Loaded by:** [handlers/review.md](../handlers/review.md) Required References, on demand when citing catalog rows during synthesis.

> [!constraint] Row Numbers Are a Stability Contract
> Row numbers are the external citation surface for this table -- other planwise artifacts cite rows as "Error Pattern Catalog row N". Treat the table as append-only: NEVER renumber, reorder, or merge rows. New patterns are appended after the highest existing number.

---

## Error Pattern Catalog

Quick reference for common patterns and their correct classification.

### Check — DELEGATED Trigger Named

This check is the mechanical, grep-determinable sibling of catalog row #11 (DELEGATED dispatch mandatory trigger violated): #11 checks whether a trigger *actually applies* to the session; this check verifies the Execution Strategy declaration *names* one. Do not merge the two — #11 requires reading task sizes/counts to judge, this one is a pure grep gate.

- **Severity:** BLOCKER
- **What:** Every session/sprint declaring `Execution Strategy: DELEGATED` MUST name which of the four mandatory triggers fired (2+ Opus tasks / META Discovery / >50K single task / output-chaining).
- **Detection:** Grep the Master Plan + each Orchestration for `Execution Strategy:\s*DELEGATED`. For each match, require an adjacent named trigger from the four. A DELEGATED declaration with no named trigger → BLOCKER.
- **Finding template:**
```
[BLOCKER] DELEGATED declaration without a named trigger
File: {Master Plan / Orchestration path} | Location: Execution Strategy section
Issue: Session declares DELEGATED but names no mandatory trigger (2+ Opus / META Discovery / >50K task / output-chaining)
Fix: Name the trigger that fired, or change to DIRECT per references/agent-orchestration-delegated.md §1.1 | Confidence: HIGH
```

| # | Pattern | Severity | Where to Check |
|---|---------|----------|----------------|
| 1 | Vague section references ("Sections 2-5" instead of individual listings) | BLOCKER | Task file Required Context table |
| 2 | Cross-sprint citation without source listing in EI header | ERROR | EI header + Cross-References table |
| 3 | Rigid mapping where domain+description inference needed | ERROR | Task execution steps |
| 4 | Stale API reference (function renamed or moved) | ERROR | Task steps vs actual codebase |
| 5 | Sequential numbering assumption (global numbering is non-sequential) | FALSE POSITIVE | See Known Patterns Whitelist |
| 6 | Missing dependency in chain | WARNING | Task dependency field |
| 7 | Token estimate too low for declared context | WARNING | Task token estimate vs file count |
| 8 | Orphaned spec section (appears in no EI) | WARNING | EI completeness check |
| 9 | Reviewer prompt missing plan context | ERROR | Reviewer spawn prompt |
| 10 | Idle teammate treated as error | INFO | Normal behavior -- not a failure |
| 11 | DELEGATED dispatch mandatory trigger violated (`agent-orchestration-delegated.md` §1.1) | BLOCKER | Orchestration Execution Strategy |
| 12 | Task-file error recovery semantics missing (`agent-orchestration-delegated.md` §1.2) | BLOCKER | Task file Notes for Agent |
| 13 | Schema Pin pre-execution form missing (`schema-pin-requirement.md` §4) | BLOCKER | Task file Required Context |
| 14 | Token estimate uses `~?` placeholder (`task-content-fidelity.md` §9.A.2) | BLOCKER | Task file Estimated Tokens |
| 15 | Cross-sprint Required Context not mirrored in Depends On (`task-file-and-tracking-requirements.md` §9 cross-sprint) | BLOCKER | Task file Depends On |
| 16 | EI bidirectional consistency violation (every Spec in `Extracted from:` MUST appear in ≥ 1 Cross-References row and vice versa) | WARNING (HIGH confidence) | EI header + Cross-References |
| 17 | DELEGATED inter-dispatch lint/precheck diagnostics missing on shared file (`agent-orchestration-delegated.md` §1.4) | BLOCKER | Orchestration between dispatches |
| 18 | DELEGATED output `wc -l` verification missing after dispatch (`agent-orchestration-delegated.md` §1.4) | BLOCKER | Orchestration between dispatches |
| 19 | DELEGATED spawn prompt missing HARD CONSTRAINTS skeleton + SCOPE BOUNDARY clause (`agent-orchestration-delegated.md` §1.8) | BLOCKER | Orchestration spawn prompts |
| 20 | DELEGATED follow-up fixes not tier-ranked by invasiveness (`agent-orchestration-delegated.md` §1.9) | BLOCKER | Orchestration follow-up dispatches |
| 21 | DELEGATED forward-looking-verb detection + SendMessage resume protocol missing (`agent-orchestration-delegated.md` §1.10) | BLOCKER | Orchestration post-dispatch scan |
| 22 | DELEGATED spawn prompt missing operational-ceiling disclaimer (`agent-orchestration-delegated.md` §1.11) | BLOCKER | Orchestration spawn prompts |
| 23 | DELEGATED edit-heavy task missing N>25 resume protocol + tool-use budget estimation (`agent-orchestration-delegated.md` §1.12) | BLOCKER | Orchestration spawn prompts |
| 24 | DELEGATED shared-edit-target dispatches missing parallelism cap/shard/delta strategy (`agent-orchestration-delegated.md` §1.13) | BLOCKER | Orchestration dispatch matrix |
| 25 | Verify-before-cite round-2 (`verify-before-cite.md` §9.B.6 examples-repo pin verification, §9.B.7 spawn-prompt helper enumeration, §9.B.8 field-mapping + `wc -l` output gate, §9.B.9 tiered-fetch ladder) | BLOCKER (varies by sub-rule) | Task file spawn prompts, Required Context, and Verification Commands |
| 26 | Sprint exit-gate verdict not reflecting gate-defining step (`verification-gates.md` §3) | BLOCKER | Sprint Plan + Sprint Overview row |
| 27 | Sprint Overview row encoding session-count fraction instead of gate verdict (`verification-gates.md` §4) | ERROR | Master Plan Sprint Overview |
| 28 | EI Cross-References §-citation format violated (`ei-citation-and-token-reconciliation.md` §7) | BLOCKER | EI Cross-References table |
| 29 | UNCONFIRMED claim missing four-site enforcement (`ei-fidelity.md` §4) | BLOCKER | EI body |
| 30 | Sprint Plan has `READY_TO_EXECUTE` at scaffolding time (`scaffolding-hygiene.md` §4) | WARNING | Sprint Plan Status field |
| 31 | Per-session `Outputs/` directory missing (`scaffolding-hygiene.md` §5) | BLOCKER | Session folder |
| 32 | Orchestration `**Prerequisite:**` declaration missing for sequential session (`scaffolding-hygiene.md` §6) | ERROR | Orchestration Prerequisites |
| 33 | Orchestration Context Boundary callout missing (`agent-orchestration-delegated.md` §1.3) | BLOCKER | Orchestration Execution Strategy |
| 34 | Verification Commands section missing for runnable-artifact task (`verification-gates.md` §3) — exempt if `<!-- VERIFICATION: not-applicable (reason) -->` comment present in task's Notes for Agent | BLOCKER | Task file Verification Commands |
| 35 | Per-file-type Verification Commands table empty (`verification-gates.md` §3) — applies to runnable-artifact tasks per `templates/task-file.md` §Per-File-Type Commands | BLOCKER | Task file Verification Commands |
| 36 | Verify Before/After callout missing for runnable artifact (`verification-gates.md` §4) | BLOCKER | Task file Verification Commands |
| 37 | Required Context not updated when a prior task changed file structure (`task-content-fidelity.md` §9.A.1) | ERROR | Task Required Context |
| 38 | Per-file-type token rate band violation (`task-content-fidelity.md` §9.A.3) | WARNING | Task Required Context |
| 39 | User-prompt-cited artifact unverified at scaffolding (`verify-before-cite.md` §9.B.1) | BLOCKER | Task file cited paths |
| 40 | Identifier not reconciled with live contract (`verify-before-cite.md` §9.B.2) | BLOCKER | Task Execution Steps |
| 41 | Helper-function design not categorized in column-presence check (`verify-before-cite.md` §9.B.4) | WARNING | Task helper refs |
| 42 | EI archival fidelity violated — transform happens at EI not Task layer (`ei-fidelity.md` §1) | ERROR | EI body |
| 43 | EI source severity vocabulary not preserved (`ei-fidelity.md` §2) | ERROR | EI body |
| 44 | EI threshold misaligned with operational dispatch contract (`ei-fidelity.md` §3) | BLOCKER | EI vs Sprint Plan |
| 45 | EI cross-tier duplicate not preserved (`ei-citation-and-token-reconciliation.md` §5) | ERROR | EI Cross-References |
| 46 | EI cross-tier citation not propagated to implementation surface (`ei-citation-and-token-reconciliation.md` §6) | ERROR | EI Cross-References |
| 47 | EI token reconciliation gate failed (`ei-citation-and-token-reconciliation.md` §8) | BLOCKER | EI token totals |
| 48 | Discovery count missing execution citation (`discovery-and-exit-criteria.md` §15.1) | BLOCKER | Discovery outputs |
| 49 | Binding refinement not echoed across plan layers (`exit-criteria-fidelity.md` §16.1) | BLOCKER | Multi-layer files |
| 50 | "Surfaces" used as non-enforceable mention not enforcement claim (`exit-criteria-fidelity.md` §16.2) | ERROR | EI / Sprint Plan |
| 51 | Sprint signoff row-count mismatch with EI exit criteria (`exit-criteria-fidelity.md` §16.3) | BLOCKER | Sprint signoff |
| 52 | Cross-session dependency not mirrored in task `Depends On` (`task-file-and-tracking-requirements.md` §9 cross-session) | BLOCKER | Task Depends On |
| 53 | Post-scaffold back-propagation missed after task edit (`task-file-and-tracking-requirements.md` §9 post-scaffold sync) | ERROR | Task file + EI section |
| 54 | BLI-cited audit anchor not re-verified before execution (`verify-discovery-consolidation.md` §6) | BLOCKER | Orchestration BLI refs |
| 55 | Cohort token-uplift missing for known high-divergence cohort (`scaffolding-hygiene.md` §10) | WARNING | Master Plan Sprint Overview Notes |
| 56 | Cross-tier audit-finding triage table missing (`execution-time-binding-rules.md` §18) | WARNING | Discovery/audit sessions |
| 57 | EI multi-sprint cumulative state not reconciled (`ei-completeness.md` §9.1) | BLOCKER | Later-sprint EI Current state block + Sprint Plan Cross-Sprint File Touches + task-file Step-1 prerequisite grep gate |
| 58 | EI repoint map cluster incomplete — fewer enumerated rows than audit cluster cites (`ei-completeness.md` §9.2) | BLOCKER | EI repoint map vs audit cluster |
| 59 | EI audit-grep-table coverage gap — verification scope wider than upstream repair scope (`ei-completeness.md` §9.3) | BLOCKER | EI verification task vs repair task Required Context |
| 60 | Consolidated Context body⇄citation promise broken — header names a finding as a Driving Finding (or Cross-References row lists it) but body lacks the prose AND no `[source-doc-only]` marker (`ei-source-promise-integrity.md` §10.1) | ERROR | Consolidated Context part body |
| 61 | Task verbatim-extraction targets a section that does not physically carry the cited prose — pre-extraction verification missing AND no fallback-hierarchy step (`ei-source-promise-integrity.md` §10.2 + §10.3) | ERROR | Task file Execution Steps |
| 62 | Mega-scaffold skipped review gate — `n_sprints_scaffolded_this_pass ≥ 2` AND Master Plan Status is `READY_TO_EXECUTE` AND no `/planwise review` report referenced (`scaffolding-hygiene.md` §11) | BLOCKER | Master Plan / scaffold-session transcript |
| 63 | Token Saver large-file ladder not applied — `context.token_saver: true` AND (over-ceiling task without `1M-exception`; OR Warn+ Required Context file with no backlog item; OR a `read`-reason Critical wrongly flagged `1M-exception`; OR a `1M-exception` task on a Sonnet/Haiku agent without override note; OR a runner-read generated artifact past the line/byte/token read gate without a Multi-Part split) (`task-content-fidelity.md` §9.A.8) — no-op when Token Saver is off | ERROR (read-Critical mis-flag / over-ceiling / artifact split) · WARNING (missing backlog item / uncovered read gate) | Task Required Context + Notes for Agent ([Token Saver Compliance Check](review-classification.md#token-saver-compliance-check)) |
| 64 | Orchestrator consumes sub-agent verdict label without recomputing from reported finding counts — systematic under-classification risk (`agent-orchestration-delegated.md` §1.16.1) | ERROR | Orchestration synthesis step; rollup tables |
| 65 | Orchestrator accepts cross-file control-flow claim ("symbol X never used → feature Y is broken") without tracing the full consumer call path — false-positive over-classification risk (`agent-orchestration-delegated.md` §1.16.2) | WARNING | Orchestration finding acceptance; release-signoff verdicts |
| 66 | DELEGATED declaration without a named trigger (`agent-orchestration-delegated.md` §1.1) — grep `Execution Strategy:\s*DELEGATED`; each match MUST carry an adjacent named trigger from the four | BLOCKER | Master Plan / Orchestration Execution Strategy |
| 67 | Rule/reference citation not re-verified against live state after the cited file changed (`verify-before-cite.md` §9.B.18) | WARNING | Change-closeout back-propagation grep |
| 68 | Prose count disagrees with the list it summarises (`task-content-fidelity.md` §9.A.9) | WARNING (ERROR when it feeds a parameter binding or schema decision) | Task file prose counts vs enumerated list |
| 69 | Risk-Mitigation assertion not implemented in any task file (`exit-criteria-fidelity.md` §16.2) | ERROR | Master Plan Risk-Mitigation cell vs Task files |
| 70 | Action tier contradicts its own evidence tier (`task-content-fidelity.md` §9.A.11) | BLOCKER | Derived status cells vs evidence-tier observations |
| 71 | Defect heuristic stated without its exclusions (`verification-task-authoring.md` §9) | ERROR | Task file bare heuristic wording |
| 72 | Comparison task sized without reference coverage (`task-content-fidelity.md` §9.A.12) | WARNING | Task Required Context / Comparison-Task Coverage row |
| 73 | Schema Pin consumed at dispatch without dispatch-day live re-verification (`schema-pin-requirement.md` §5) | BLOCKER | Task file Schema Pin section at dispatch |
| 74 | Multi-outcome Schema Pin whose consuming task does not open with the discovery query (`schema-pin-requirement.md` §5) | ERROR | Task file Execution Steps (Step 1) |
| 75 | Data literal inline-copied from a design artifact instead of §-cited and reconciled at execution (`ei-citation-and-token-reconciliation.md` §7.1) | WARNING | Task file literal construction vs cited design artifact |
| 76 | Ingestion/load task verified by exit code alone — no post-run row-count assertion (`session-plan-requirements.md` §9) | ERROR | Task file Verification Commands |
| 77 | Data-state criterion anchored to an upstream Status field instead of a live query (`exit-criteria-fidelity.md` §16.5) | ERROR | Exit criteria / signoff data-state anchor |
| 78 | Audit verdict does not state the defect classes it did NOT check (`exit-criteria-fidelity.md` §16.6) | WARNING | Audit / sweep report verdict statement |
| 79 | Absence-grep criterion whose token is not scrubbed from the gate's own prose/legend (`verification-task-authoring.md` §8.1) | ERROR | Verification Commands absence-grep gate |
| 80 | Schema Pin sourced from a design artifact, not reconciled against deployed state before SQL emission (`verify-before-cite.md` §9.B.13) | BLOCKER | Task file Schema Pin vs deployed DDL |
| 81 | Template or brief cites env var / function signature / config key with no grep-backed `file:line` citation (`verify-before-cite.md` §9.B.14) | ERROR | Template / task brief cited symbols |
| 82 | Brief says "re-run script X" with no architecture classification (parser / static-data / config-loader) (`verify-before-cite.md` §9.B.15) | WARNING (ERROR when X's output is Required Context to a later task) | Task brief generator-script instruction |
| 83 | Bare column-count claim in a Pin with no catalog reconciliation (`schema-pin-requirement.md` §5.2 + §5.4) | ERROR | Task file Schema Pin vs live schema catalog |
| 84 | Constraint-adding deploy with no data-side pre-flight (`session-plan-requirements.md` §9) | BLOCKER | Task file pre-flight / Verification Commands |
| 85 | External-service task with no probe step (`verify-before-cite.md` §9.B.16) | ERROR | Task Execution Steps vs live service probe |
| 86 | Line-anchored Required Context row for a file listed in Cross-Sprint File Touches, instead of a grep-symbol anchor (`templates/sprint-plan.md` Cross-Sprint File Touches) | ERROR | Task file Required Context vs Sprint Plan Cross-Sprint File Touches |
| 87 | Unresolvable `D{N}` citation — resolves to no entry in the plan's own Master Plan `Decisions (Locked)` section; a plans-index row does not count (`templates/master-plan.md` Decisions (Locked) + `session-plan-requirements.md` §10) | ERROR | Plan files' `D{N}` citations vs Master Plan Decisions (Locked) |
| 88 | Duplicate assertion label within a task file (`task-content-fidelity.md` §9.A.13) | ERROR | Task file assertion-label ↔ validation-cell table |
| 89 | Assert-vs-report disposition mismatch for one label across two files (`task-content-fidelity.md` §9.A.13) | ERROR | Task file vs sibling file assertion-label disposition |
| 90 | Removal deliverable enumerated, not derived — no Creator-role member and no explicit retained-creator statement (`scaffolding-hygiene.md` §13.1 + §13.2) | BLOCKER | Deliverables section vs sweep-derived deletion set |
| 91 | Unsatisfiable absence criterion — zero-match assertion on a token the removal artifact must itself contain (`exit-criteria-fidelity.md` §16.9.1) | ERROR | Success criteria absence-grep vs removal artifact |
| 92 | Success criterion asserts a bare literal with no provenance cited (`exit-criteria-fidelity.md` §16.10.1) | ERROR | Success Criteria literal counts |
| 93 | Derived-ratio gate omits column, grain, denominator, or the re-derivation prohibition (`exit-criteria-fidelity.md` §16.10.2) | WARNING | Success Criteria / Verification Commands ratio gates |
| 94 | Producer-artifact criterion with no reads-its-subject assertion (`exit-criteria-fidelity.md` §16.10.3) | WARNING | Success Criteria producer-artifact claims |
| 95 | Symbol-keyed absence criterion with no measured count — a bare identifier scoped instead of the module/import path being removed (`exit-criteria-fidelity.md` §16.9.2) | ERROR | Success criteria deletion-scoped grep target |
| 96 | Task whose steps predictably breach a binding rule, with no halt-and-report instruction in its Notes for Agent (`agent-orchestration-delegated.md` §1.25) | ERROR | Task file Notes for Agent |
| 97 | DELEGATED spawn prompt opening with a session-scoped identity frame ("You are a task-runner in session {session-id}") and no task-scoped clause in the same sentence — the framing measured to override a correctly-stated single-task constraint (`agent-orchestration-delegated.md` §1.23) | ERROR | Orchestration spawn prompts (opener framing) |
| 98 | DELEGATED spawn prompt naming the task scope in fewer than three positions — the mechanical, grep-countable tally across Opener / Hard-constraint block / Return instructions (`agent-orchestration-delegated.md` §1.23) | BLOCKER | Orchestration spawn prompts (position count) |
| 99 | Structurally-consumed output specified only as prose + illustrative code block — no template pointer, no heading/column checklist (`agent-orchestration-delegated.md` §1.24) | ERROR | Task file Expected Output |
| 100 | Verification command that mutates the artifact it checks, unattributed, where that artifact is a runner's declared output (`agent-orchestration-delegated.md` §1.26) | ERROR | Task file Verification Commands |
| 101 | Task file's own Verification Commands invoking a project tool by bare name, in a project declaring an isolated environment, with no interpreter path present (`agent-orchestration-delegated.md` §1.27) | ERROR | Task file Verification Commands |
| 102 | DELEGATED spawn prompt's dispatched command invoking a bare interpreter rather than the project-relative path (`agent-orchestration-delegated.md` §1.27) | WARNING | Orchestration spawn prompts / ENVIRONMENT DISCIPLINE block |
| 103 | Normalization-before-mechanical-batch task scoped by inherited severity/triage tier rather than the blocking property (`discovery-and-exit-criteria.md` §15.3) | ERROR | Discovery/audit sessions |
| 104 | Task file carries a routed coordination flag whose text contradicts an Execution Step / Success Criterion / Schema Pin stated verbatim in the same file (`handlers/run.md` Step 1.1a + `read-confirm-act-protocol.md` §1.3) | BLOCKER | Task file vs routed coordination flag |
| 105 | Plan with a task whose declared Output is under `.claude/**` and no Orchestration declares the expected permission round-trip, or one task batching edits across multiple config files with no smallest-coherent-set scoping (`scaffolding-hygiene.md` §14) | ERROR | Orchestration Execution Strategy / Task file Output |
| 106 | Unresolved conditional branch in a dispatchable task file — task file carries a criterion phrased conditionally on an upstream measurement AND the gating task is already COMPLETE (`read-confirm-act-protocol.md` §1.3, Conditional Spec Branches Are Flags) | BLOCKER | Task file Execution Steps + Success Criteria |
| 107 | Coordination flag duplicating or contradicting an indexed lesson — a coordination-flag entry restates an artifact-class finding the lessons index already carries, without citing it (`read-confirm-act-protocol.md` §1.3, Checking the Lessons Index Before Recording) | WARNING | Coordination-flag block; Recovery Cross-Task Coordination Flags table |
| 108 | Item-filing task with no re-verification step — a task file's Execution Steps create backlog items from a pre-computed list AND contain no re-verification of each condition before filing (`verify-backlog-citation-freshness.md` §10) | ERROR | Task file Execution Steps |
| 109 | Re-alignment prescription with no existence probe — a task file or backlog item applies a re-alignment verb to an outside-the-repo target AND its Execution Steps contain no family-level probe before the edit steps (`verify-backlog-citation-freshness.md` §11) | WARNING | Task file or backlog item Execution Steps |
| 110 | Verification task produces a verdict about code state without naming the tree under test or pinning its state at both ends of the read window (`verify-backlog-citation-freshness.md` §12) | ERROR | Task file Steps / Expected Output |
