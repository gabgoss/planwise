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
