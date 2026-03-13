# Orchestration Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Orchestration.md`.

---

```markdown
# Session Orchestration - {ABBREV}-S{XX}-{YY}: {Session Name}

**Session ID:** {ABBREV}-S{XX}-{YY}
**Sprint:** {XX} - {SprintName}
**Status:** PLANNED

---

## Session Objective

{2-3 sentences describing what this session accomplishes}

---

## Required Context Files

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

## Execution Strategy

**Mode:** {DIRECT | DELEGATED}
**Reason:** {Why this mode — e.g., "3 sequential Opus tasks each needing fresh context"}

### Context Boundary (DELEGATED mode only)

**Orchestrator reads:** Orchestration, Recovery, task files (plan files only)
**Orchestrator NEVER reads:** {list the heavy files — Consolidated Context parts, reference docs, source code}
**Subagents read:** Per-task Required Context (each subagent gets fresh ~100K)

> **Subagent overhead:** Each subagent consumes ~54K (system ~26K + global rules/CLAUDE.md ~27K + skills ~1K) before any task work begins. Verify that each task's estimate + 54K < 200K. See [Token Estimation Reference](../reference.md#token-estimation-reference) for per-operation costs.

---

## Session Task List

| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | {Task 1} | Haiku | ~{X}K | - |
| 2 | {Task 2} | Sonnet | ~{X}K | 1 |
| 3 | {Task 3} | Opus | ~{X}K | 2 |

**Total Estimated:** ~{XX}K tokens
<!-- Reconciliation: this total MUST equal the sum of Est. Tokens above.
     This session's total MUST match the Est. Tokens in the Sprint Plan Sessions table. -->

---

## Success Criteria

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}
- [ ] {Measurable criterion 3}

---

## Recovery Protocol

Update `{Abbrev}-S{XX}-{YY}-Recovery.md` after EACH task completion.

---

## Task Files

| # | Task File | Agent |
|---|-----------|-------|
| 1 | [{Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-01-{Agent}-{Task}.md) | {Agent} |
| 2 | [{Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-02-{Agent}-{Task}.md) | {Agent} |
| 3 | [{Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md]({Abbrev}-S{XX}-{YY}-03-{Agent}-{Task}.md) | {Agent} |

---

## Post-Session Checklist

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
