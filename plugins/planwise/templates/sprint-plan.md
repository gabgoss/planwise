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

## Write-Set <!-- REQUIRED -->

List every directory or file this sprint **EDITS** — not the ones it merely
reads. The read/edit distinction is the whole point: an intersection computed
over read-sets is meaningless, since nearly every sprint reads broadly but only
a handful of paths are ever written to.

| Path | Task |
|------|------|
| `{path/or/directory}` | {ABBREV}-S{XX}-{YY}-{##} |
| `{path/or/directory}` | {ABBREV}-S{XX}-{YY}-{##} |

This declaration feeds the Master Plan's `## Execution Ordering` section, where
every declared-parallel pair's write-sets are intersected and the computed
result is shown in its Computed Write-Set Intersection table.

This section is distinct from `## Cross-Sprint File Touches` below:
**Cross-Sprint File Touches is sequential** — this sprint vs. a *prior*
sprint's already-landed delta, gated by a Step-1 prerequisite grep that HALTs
if the prior delta is missing. **Write-Set is the declaration an intersection
is computed from** — it states what this sprint edits so a *parallel*
sprint's write-set can be checked against it, independent of landing order.

---

## Success Criteria <!-- REQUIRED -->

<!-- Prefer a relationship the pipeline maintains (after == before, "equals the count the
     upstream step disposed X") over a literal. If a literal is used, cite the measurement
     that produced it in the same bullet. -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}
- [ ] {Measurable criterion 3}

---

## Deliverables <!-- REQUIRED -->

<!-- Removal / retirement deliverables: paste the sweep output that PRODUCED the list and cite
     the command. Do not enumerate from memory — see scaffolding-hygiene.md §13, and note that
     the creator artifact (schema/DDL, migration, generator, packaging declaration) is the member
     whose omission silently undoes the retirement. -->

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

<!-- Declaring a row here mechanically implies three obligations in the consuming task:
     (a) Step-1 prerequisite grep gate — see templates/task-file.md "Cross-Sprint
         Prerequisite Grep Gate" (already enforced).
     (b) A `cross-sprint:` entry in Depends On — see task-file-and-tracking-requirements.md
         §9 "Cross-sprint dependency mirroring" (Reviewer Check 037; already enforced
         generally — this row is what triggers it for THIS file).
     (c) Required Context for this file anchored by grep SYMBOL, never by line range —
         see scaffolding-hygiene.md §12.1. Any line number in a brief predates the prior
         sprint's edit; treat every cited line number as a cost hint only. -->

<!-- WRONG:   | src/{shared_module} | lines 890-905 (the export entries to delete) | 0.3K |
     CORRECT: | src/{shared_module} | grep -n '"{SymbolA}"\|"{SymbolB}"' then read ±10 lines | 0.3K |
              > Any line number in this brief predates {Abbrev}-S01-01-03's insertion. Locate by
              > symbol; treat every cited line number as a cost hint only. -->

The first task in this sprint that edits each listed file MUST include a Step-1 prerequisite grep gate verifying the prior delta marker is present (see `templates/task-file.md` "Cross-Sprint Prerequisite Grep Gate"). If the marker is missing, HALT — the prior sprint is incomplete and this sprint cannot run against the outdated baseline.

When this section is empty (no cross-sprint file touches in this sprint), delete the section entirely rather than leaving an empty table.

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| {today} | Sprint plan created | Claude |
```
