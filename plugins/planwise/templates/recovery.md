# Recovery Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Recovery.md`.

---

```markdown
# Recovery State - {ABBREV}-S{XX}-{YY}

**Last Updated:** {timestamp}
*Bump to today's date with a short parenthetical (≤120 characters) naming what changed. **Replace the previous value — do not preserve it.** History belongs in a changelog file, not in this line.*
**Current Step:** NOT STARTED
**Session Status:** NOT_STARTED
**Orchestrator:** - (last write -)
*The token is the timestamp of the orchestrator's own Phase 1 READ, minted once per conversation. The run handler rewrites the token and the time at every Recovery write. A takeover writes a Change Log row with Status `OWNER` and both tokens in Notes.*

---

## Step Completion Status

| Step | Task | Agent | Status | Completed | Dispatch ID | Tokens (self-reported, per-window) |
|------|------|-------|--------|-----------|-------------|-------------------------------------|
| 1 | {Task 1} | {Agent} | PENDING | - | - | - |
| 2 | {Task 2} | {Agent} | PENDING | - | - | - |
| 3 | {Task 3} | {Agent} | PENDING | - | - | - |

`Dispatch ID` and `Tokens (self-reported, per-window)` cite the Consumption Record field definitions in `templates/summary-template.md` § Consumption Record (`dispatch_ids` and the per-window token fields) — semantics are not restated here. The `per-window` label is deliberate: this cell is one dispatched agent's own window, never summed across rows into a session total.

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

*Populated when a task surfaces an observation that constrains, sequences, or unlocks work in a DIFFERENT session, sprint, or plan. The orchestrator MUST record the row at surface time (not at closeout) and propagate each row into the downstream consumer's task or orchestration file at Phase 4 closeout. The orchestrator is the only writer of this table and the only allocator of `Flag #`. A task-runner returns a `FLAG:` bullet with no id. See `references/read-confirm-act-protocol.md` §1.3.*

| Flag # | Source Task | Downstream Consumer | Observation | Recommended Action |
|--------|-------------|---------------------|-------------|---------------------|
| - | - | - | - | - |

**Field reference:**

| Column | Content |
|--------|---------|
| Flag # | Allocated by the orchestrator only: the highest id in this section plus 1, carried rows included (1, 2, 3...). Never reuse an id |
| Source Task | Task ID that surfaced the flag (e.g., `{Abbrev}-S{XX}-{YY}-{##}`) |
| Downstream Consumer | The task / session / sprint / plan that must act on the flag (most specific identifier available) |
| Observation | One-paragraph description of the constraint, dependency, ambiguity, or opportunity |
| Recommended Action | What the downstream agent should do — sequence, route, resolve, evaluate |

---

## Scope-Expansion Decisions

*Populated only when Phase-1 READ surfaces a structural finding and the user approves an expansion beyond the literal task scope. See `references/read-confirm-act-protocol.md` §1.2.*

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

## Premise Corrections

*Populated when a measurement a plan file cites no longer holds when re-measured: a line count, a byte or token size, a file count, a symbol's line, a test count. Record the row at re-measure time, before acting on the moved value. See `references/verify-before-cite.md` §9.B.24 and §9.B.25.*

| Step | Cited Claim | Cited In | Measured | Measure Command | Effect |
|------|-------------|----------|----------|-----------------|--------|
| - | - | - | - | - | - |

**Field reference:**

| Column | Content |
|--------|---------|
| Step | Step number from Step Completion Status table, or `start` for a Session Start Census re-measure |
| Cited Claim | The figure or fact as the plan file states it (e.g., "`recovery.md` is 169 lines") |
| Cited In | The file and location that carries the claim |
| Measured | The value the re-measure returned |
| Measure Command | The exact command or tool call that produced the measured value |
| Effect | What changed because of the move (the task's output path, a gate threshold, an edit anchor), or "none" |

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

*A runner's planned stop is recorded as a row with Status `GATE_PENDING` and the `ROUTE/FLAGS` value in Notes, before the user gate is asked. A gate the Orchestration declares records its answer in the `## User-Action Gate` table. Any other stop records the answer verbatim in a later row.*

---

## Task List Map

*Track B only. Harness task ids minted by `TaskCreate` for this session's steps. Rewritten in full when the run handler re-hydrates the list after a `/clear`. Under Track A this section stays as shipped.*

| Step | Task ID |
|------|---------|
| - | - |

---

## User-Action Gate <!-- OPTIONAL — a session that stops for the user's answer -->

<!-- Include only when the session's Orchestration file carries a `User-Action Gate` section.
     Omit the section otherwise. The Gate cell holds the gate id from the Orchestration table.
     Record the user's answer verbatim in the Answer cell. -->

| Gate | Status | Date Asked | Answer |
|------|--------|------------|--------|
| {gate id} | OPEN | {YYYY-MM-DD} | {the user's answer, verbatim, or "pending"} |

*Status is `OPEN` until the user answers. It then becomes `RATIFIED` or `REJECTED`.*

---

## Plan-Specific Sections <!-- OPTIONAL -->

Write any section that no heading above covers here, as an `###` H3. Never add it as a new `##` H2 elsewhere in this file, and draft one `idea` feedback draft for each new H3 heading (see `references/feedback-drafting.md`).

### {Section Heading}

{content}
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
