# Recovery Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-Recovery.md`.

---

```markdown
# Recovery State - {ABBREV}-S{XX}-{YY}

**Last Updated:** {timestamp}
**Current Step:** NOT STARTED
**Session Status:** NOT_STARTED

---

## Step Completion Status

| Step | Task | Agent | Status | Completed |
|------|------|-------|--------|-----------|
| 1 | {Task 1} | {Agent} | PENDING | - |
| 2 | {Task 2} | {Agent} | PENDING | - |
| 3 | {Task 3} | {Agent} | PENDING | - |

---

## Key Findings

*Populated as steps complete*

---

## Issues Identified

| Issue | Severity | Impact | Resolution |
|-------|----------|--------|------------|
| None yet | - | - | - |

---

## Scope-Expansion Decisions

*Populated only when Phase-1 READ surfaces a structural finding and the user approves an expansion beyond the literal task scope. See [references/session-execution-protocol.md §1.2](../references/session-execution-protocol.md#12-structural-findings-beyond-literal-scope).*

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

## Change Log

| Date | Step | Status | Notes |
|------|------|--------|-------|
| {today} | - | CREATED | Recovery file initialized |
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
