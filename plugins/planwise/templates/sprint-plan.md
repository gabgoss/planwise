# Sprint Plan Template

Use this template when creating `{Abbrev}-S{XX}-Sprint-Plan.md`.

---

```markdown
# Sprint {XX}: {Sprint Name}

**Sprint ID:** {ABBREV}-S{XX}
**Status:** PLANNED
<!-- All Sprint Plans start as PLANNED. Only the Master Plan uses READY_TO_EXECUTE. Lifecycle: PLANNED → IN_PROGRESS → COMPLETE. -->
**Estimated Tokens:** ~{XX}K total across all sessions
<!-- Reconciliation: this total MUST equal the sum of Est. Tokens in the Sessions table below. -->

---

## Sprint Objective <!-- REQUIRED -->

{2-3 sentences describing what this sprint accomplishes and its purpose within the larger plan}

---

## Sessions <!-- REQUIRED -->

| Session | ID | Name | Objective | Est. Tokens |
|---------|----|----- |-----------|-------------|
| 1 | {ABBREV}-S{XX}-01 | {SessionName} | {What this session delivers} | ~{XX}K |
| 2 | {ABBREV}-S{XX}-02 | {SessionName} | {What this session delivers} | ~{XX}K |

---

## Prerequisites <!-- REQUIRED -->

- {Prerequisite 1 - e.g., Sprint {XX-1} completed}
- {Prerequisite 2 - e.g., Required document exists}

---

## Success Criteria <!-- REQUIRED -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}
- [ ] {Measurable criterion 3}

---

## Deliverables <!-- REQUIRED -->

1. **{Deliverable 1}:** {Description of what will be produced}
2. **{Deliverable 2}:** {Description of what will be produced}

---

## Session Details

### Session 01: {SessionName} ({ABBREV}-S{XX}-01)

**Objective:** {What this session accomplishes}

**Tasks:**
| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | {Task description} | Haiku | ~{X}K | - |
| 2 | {Task description} | Sonnet | ~{X}K | 1 |
| 3 | {Task description} | Opus | ~{X}K | 2 |

**Key Requirements:**
- {Requirement 1}
- {Requirement 2}

---

## Cross-Sprint File Touches <!-- OPTIONAL — include when this sprint edits a file already edited by a prior sprint -->

List every file this sprint edits that was ALSO edited by an earlier sprint of the same plan. Each row pairs the file with the prior sprint's edit so the executor can verify the prior delta landed before applying this sprint's delta.

| File | Prior Sprint Task | Prior Delta Marker (grep target) | This Sprint Adds |
|------|-------------------|----------------------------------|------------------|
| `{path/to/file.ext}` | {Abbrev}-S{XX_prior}-{YY}-{##} | `{grep-anchor text the prior sprint inserted}` | {delta this sprint adds} |
| `{path/to/file2.ext}` | {Abbrev}-S{XX_prior}-{YY}-{##} | `{grep-anchor text}` | {delta this sprint adds} |

The first task in this sprint that edits each listed file MUST include a Step-1 prerequisite grep gate verifying the prior delta marker is present (see `templates/task-file.md` "Cross-Sprint Prerequisite Grep Gate"). If the marker is missing, HALT — the prior sprint is incomplete and this sprint cannot run against the outdated baseline.

When this section is empty (no cross-sprint file touches in this sprint), delete the section entirely rather than leaving an empty table.

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| {today} | Sprint plan created | Claude |
```
