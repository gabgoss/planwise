# Recovery Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Recovery.md`.

---

```markdown
# Recovery State - {ABBREV}-S{XX}-{YY}

**Last Updated:** {timestamp}
*Bump to today's date with a short parenthetical (≤120 characters) naming what changed. **Replace the previous value — do not preserve it.** History belongs in a changelog file, not in this line.*
**Current Step:** NOT STARTED
**Session Status:** NOT_STARTED

---

## Step Completion Status

| Step | Task | Agent | Status | Completed | Dispatch ID | Tokens (self-reported, per-window) |
|------|------|-------|--------|-----------|-------------|-------------------------------------|
| 1 | {Task 1} | {Agent} | PENDING | - | - | - |
| 2 | {Task 2} | {Agent} | PENDING | - | - | - |
| 3 | {Task 3} | {Agent} | PENDING | - | - | - |

`Dispatch ID` and `Tokens (self-reported, per-window)` cite the Consumption Record field definitions in [summary-template.md § Consumption Record](summary-template.md#consumption-record) (`dispatch_ids` and the per-window token fields) — semantics are not restated here. The `per-window` label is deliberate: this cell is one dispatched agent's own window, never summed across rows into a session total.

---

## Session Boundary Note

**Next Dispatch:** none
**Resume State:** incomplete
**Written At:** -

*Written by the run handler at each dependency-layer edge when `context.run_layer_stop` is `on`, and by the session-length checkpoint when it offers a boundary. `--resume` accepts a session only when `Resume State` reads `complete`.*

**Field reference:**

| Line | Content |
|------|---------|
| Next Dispatch | `task {n} ({Agent}), layer L{k}` — the exact next dispatch, or `none` |
| Resume State | `complete` only when every box of the Resume-State Completeness checklist holds (`references/session-execution-protocol.md` § Session-Length Checkpoint); otherwise `incomplete` |
| Written At | timestamp of the last write, or `-` |

---

## Key Findings

*Populated as steps complete*

---

## Issues Identified

| Issue | Severity | Impact | Resolution |
|-------|----------|--------|------------|
| None yet | - | - | - |

---

## Cross-Task Coordination Flags

*Populated when a task surfaces an observation that constrains, sequences, or unlocks work in a DIFFERENT session, sprint, or plan. The orchestrator MUST record the row at surface time (not at closeout) and propagate each row into the downstream consumer's task or orchestration file at Phase 4 closeout. See [references/read-confirm-act-protocol.md §1.3](../references/read-confirm-act-protocol.md#13-cross-task-coordination-flags).*

| Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
|--------|-------------|---------------------|-------------|---------------------|
| - | - | - | - | - |

**Field reference:**

| Column | Content |
|--------|---------|
| Flag # | Sequence number within this Recovery file (1, 2, 3...) |
| Source Task | Task ID that surfaced the flag (e.g., `{Abbrev}-S{XX}-{YY}-{##}`) |
| Downstream Consumer | The task / session / sprint / plan that must act on the flag (most specific identifier available) |
| Observation | One-paragraph description of the constraint, dependency, ambiguity, or opportunity |
| Recommended Action | What the downstream agent should do — sequence, route, resolve, evaluate |

---

## Scope-Expansion Decisions

*Populated only when Phase-1 READ surfaces a structural finding and the user approves an expansion beyond the literal task scope. See [references/read-confirm-act-protocol.md §1.2](../references/read-confirm-act-protocol.md#12-structural-findings-beyond-literal-scope).*

| Step | Literal Scope | Expanded Scope | Structural Rationale | Impact | Phase-1 Approval Ref |
|------|---------------|----------------|----------------------|--------|----------------------|
| - | - | - | - | - | - |

**Field reference:**

| Column | Content |
|--------|---------|
| Step | Step number from Step Completion Status table |
| Literal Scope | The directive's literal words (e.g., "add §X to ToC") |
| Expanded Scope | What was actually touched (e.g., "promote §X → H2, relocate after §Y, add §X/§Y/§Z to ToC") |
| Structural Rationale | Why the literal scope produced a self-inconsistent artifact |
| Impact | Concrete delta (lines moved, heading levels changed, files touched beyond directive) |
| Phase-1 Approval Ref | AskUserQuestion turn / timestamp from CONFIRM block where user picked Option A |

---

## Files Modified

*Populated as steps complete*

---

## Session Commit Pin

| Field | Value |
|-------|-------|
| Session commit | - |
| Push state | not pushed |
| Recorded At | - |

*The run handler writes this row immediately after the session commit and again after the push. `-` means no commit has been recorded. On resume, a `-` here is not evidence that no commit exists: compare it with the git tree (`handlers/run.md` Step 1.1).*

---

## Change Log

| Date | Step | Status | Notes |
|------|------|--------|-------|
| {today} | - | CREATED | Recovery file initialized |

*A runner's planned stop is recorded as a row with Status `GATE_PENDING` and the `ROUTE/FLAGS` value in Notes, before the user gate is asked. The user's answer is recorded verbatim in a later row.*

---

## Task List Map

*Track B only. Harness task ids minted by `TaskCreate` for this session's steps. Rewritten in full when the run handler re-hydrates the list after a `/clear`. Under Track A this section stays as shipped.*

| Step | Task ID |
|------|---------|
| - | - |
```

---

## Status Values

| Status | Meaning |
|--------|---------|
| `NOT_STARTED` | Session hasn't begun |
| `IN_PROGRESS` | At least one task started |
| `COMPLETE` | All tasks finished |

## Task Status Values

| Status | Meaning |
|--------|---------|
| `PENDING` | Task not yet started |
| `IN_PROGRESS` | Currently working on task |
| `COMPLETE` | Task finished successfully |

## Change Log Status Values

`GATE_PENDING` is a Change Log status only. It marks a runner's planned stop at a user gate the orchestrator owns. It is not a Step status and not a Session status. `Session Status` stays `NOT_STARTED | IN_PROGRESS | COMPLETE`.
