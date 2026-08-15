# Orchestration Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Orchestration.md`.

---

```markdown
# Session Orchestration - {ABBREV}-S{XX}-{YY}: {Session Name}

**Session ID:** {ABBREV}-S{XX}-{YY}
**Sprint:** {XX} - {SprintName}
**Status:** PLANNED
**Prerequisite:** {previous session or sprint that must be COMPLETE before this session can run, or "None" if first session of a plan}

<!-- Scaffolding CONFIRM block placeholder:
     When this orchestration is part of a scaffolded plan, ensure the handler emits the CONFIRM block
     before reading Consolidated Context parts. See handlers/plan.md Scaffolding Step 1
     and references/scaffolding-hygiene.md §1. -->

---

## Session Objective <!-- REQUIRED -->

{2-3 sentences describing what this session accomplishes}

---

## Required Context Files <!-- REQUIRED -->

<!-- DIRECT mode: list all context files needed for the session -->
<!-- DELEGATED mode: list ONLY plan files (Orchestration, Recovery, task files) -->
<!-- Heavy context files go in individual task file Required Context sections -->

| Priority | File | Purpose |
|----------|------|---------|
| 1 | `session-planning-protocol.md` | Planning hierarchy, delegation, checklists |
| 1 | `session-context-budget.md` | Token budget, context loading |
| 1 | `session-plan-requirements.md` | Required files, task templates |
| 2 | `{Abbrev}-Master-Plan.md` | Project overview |
| 3 | `{Abbrev}-S{XX}-{YY}-Recovery.md` | Resume point |

---

## Execution Strategy <!-- REQUIRED -->

**Mode:** {DIRECT | DELEGATED} <!-- REQUIRED -->
**Reason:** {Why this mode — e.g., "3 sequential Opus tasks each needing fresh context"}

### DELEGATED Mandatory Triggers Reminder

> [!checklist] When DELEGATED is Mandatory
> Set `Mode: DELEGATED` if ANY of these triggers apply:
> - [ ] Session has 2 or more Opus tasks
> - [ ] Session is part of a META Discovery phase
> - [ ] Any single task estimates > 50 K token context load
> - [ ] Sequential tasks where one task's output is the next task's input (output-chaining)
>
> See `references/session-plan-requirements.md` § Execution Strategy (Set by Planner) for the binding rule (canonical); `references/agent-orchestration-delegated.md` §1.1 Mandatory Triggers cites it.

### Context Boundary (DELEGATED mode only)

> [!constraint] Mandatory Context Boundary
> In DELEGATED mode, the orchestrator reads ONLY plan files (Orchestration, Recovery, task files). Heavy context files (Consolidated Context parts, reference docs, source code) are read by subagents only.
>
> WRONG (orchestrator reads heavy context):
> ```
> Orchestrator reads:
> - Orchestration, Recovery, task files
> - Consolidated Context Part 4 (large file)   ← blows budget; defeats DELEGATED
> ```
> CORRECT (orchestrator reads only plan files):
> ```
> Orchestrator reads:
> - Orchestration, Recovery, task files
> Orchestrator NEVER reads:
> - Consolidated Context parts, reference docs, source code
> ```

**Orchestrator reads:** Orchestration, Recovery, task files (plan files only)
**Orchestrator NEVER reads:** {list the heavy files — Consolidated Context parts, reference docs, source code}
**Subagents read:** Per-task Required Context (each subagent gets a fresh window sized by the **dispatched model** — 200K for Sonnet/Haiku, 1M for Opus — regardless of the parent tier; see [`references/session-context-budget.md` § Subagent Context Window](../references/session-context-budget.md#subagent-context-window))

> **Subagent overhead:** Each subagent consumes ~54K (system ~26K + global rules/CLAUDE.md ~27K + skills ~1K) before any task work begins. Verify that each task's estimate + injected path-rule tokens + ~54K < the **dispatched model's** window (Sonnet/Haiku 200K, Opus 1M — NOT the parent `context_window`; see [§ Subagent Context Window](../references/session-context-budget.md#subagent-context-window)). See [Task-Level Estimation](../references/session-context-budget.md#task-level-estimation-binding) for the bottom-up estimation formula and conversion factor.

<!-- Uncomment when any task's declared Output is under `.claude/**` — declares the
     expected permission round-trip (see references/scaffolding-hygiene.md):
> [!note] Task {NN} edits `.claude/**`
> The harness permission classifier gates these writes independently of planwise
> authorization. `/planwise run` invocation does not pre-clear it: expect a user
> permission prompt mid-task, expect per-call (not all-or-nothing) denials, and
> expect that some denials may not be clearable at all. Recovery records the
> applied-vs-denied list on first denial. -->

---

## Session Task List <!-- REQUIRED -->

| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | {Task 1} | Haiku | ~{X}K | - |
| 2 | {Task 2} | Sonnet | ~{X}K | 1 |
| 3 | {Task 3} | Opus | ~{X}K | 2 |

**Total Estimated:** ~{XX}K tokens <!-- REQUIRED -->
<!-- Reconciliation: this total MUST equal the sum of Est. Tokens above.
     This session's total MUST match the Est. Tokens in the Sprint Plan Sessions table. -->

---

## Success Criteria <!-- REQUIRED -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}
- [ ] {Measurable criterion 3}

---

## Recovery Protocol <!-- REQUIRED -->

Update `{Abbrev}-S{XX}-{YY}-Recovery.md` after EACH task completion.

---

## Task Files <!-- REQUIRED -->

| # | Task File | Agent |
|---|-----------|-------|
| 1 | [{Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md) | {Agent} |
| 2 | [{Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md) | {Agent} |
| 3 | [{Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md) | {Agent} |

---

## Post-Session Checklist <!-- REQUIRED -->

> Corresponds to Phase 4 of the run handler. Complete these steps after all tasks finish.

- [ ] **Verify outputs** — confirm all expected output files were written to `Outputs/`
- [ ] **Finalize recovery** — mark Session Status: COMPLETE, update all task statuses, add final Key Findings
- [ ] **Generate session summary** — write `Outputs/{Abbrev}-S{XX}-{YY}-Summary.md` using [summary-template.md](summary-template.md)
- [ ] **Capture lessons** — ask "Were any lessons learned?" If yes, create lesson file and update lessons index
- [ ] **Update plan status** — mark this orchestration COMPLETE; update sprint plan and master plan status fields
- [ ] **Git commit and push** — stage specific files (`git add` by name, never `git add .`), commit, push

---

**Next Step:** Execute Task 1
```
