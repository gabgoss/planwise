---
description: Error Pattern Catalog for /planwise review -- the 66-row quick-reference table of common plan-authoring defects and their severity classification, plus the mechanical DELEGATED-trigger-named check. Row numbers are cited externally and MUST NOT be renumbered.
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
| 25 | Verify-before-cite round-2 (`verify-before-cite.md` §9.B.6..§9.B.9) | BLOCKER (varies by sub-rule) | Task file SQL/MERGE briefs |
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
