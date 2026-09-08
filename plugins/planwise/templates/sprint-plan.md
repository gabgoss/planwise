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

<!-- DRY-RUN AT SCAFFOLD CLOSE. Run every criterion's check against the PRE-CHANGE tree and
     record what it returned, inline. A criterion that already PASSES pre-change is a
     scaffold-time failure — it returns the same verdict on an untouched tree as on a
     finished sprint. Rewrite it; do not ship it annotated. The recorded value is also the
     Before baseline any "unchanged vs Before" / "Before + 1" criterion needs to be
     computable at all. See references/verification-task-authoring.md §10. -->

<!-- BRANCH-SET PARITY. Where a criterion enumerates outcomes, its accepted set MUST equal
     the terminal branch set of the task that produces them — count them from that task's
     Execution Steps, not from the outcome you expect. Zero-hit, nothing-to-do and
     already-resolved branches are the ones dropped most often, and are often the expected
     result. A criterion accepting fewer FAILs a correct execution. §10.7 of the same file. -->

- [ ] {Measurable criterion 1} <!-- pre-change: {measured} → expect {expectation} -->
- [ ] {Measurable criterion 2} <!-- pre-change: {measured} → expect {expectation} -->
- [ ] {Measurable criterion 3} <!-- accepts {a} outcomes; task {ID} defines {a} terminal branches -->

<!-- Before shipping any criterion above, check its command against the four semantics traps
     in references/verification-task-authoring.md §10.8: grep -c counts matching LINES not
     matches; -B1/-A1 emit the match line itself; a set-membership claim must not be hardened
     into a count equality; every path resolves from the cwd its own block declares. -->


---

## Deliverables <!-- REQUIRED -->

<!-- Removal / retirement deliverables: paste the sweep output that PRODUCED the list and cite
     the command. Do not enumerate from memory — see scaffolding-hygiene-Part-2-DerivationAndParallelism.md §13, and note that
     the creator artifact (schema/DDL, migration, generator, packaging declaration) is the member
     whose omission silently undoes the retirement. -->

| # | Deliverable | Class | Description |
|---|-------------|-------|-------------|
| 1 | {Deliverable 1} | edit | {What will be produced} |
| 2 | {Deliverable 2} | create | {What will be produced} |
| 3 | {Deliverable 3} | verified-absent | {What is deliberately NOT taken, and the check that proves it absent} |

> [!constraint] A row that lands new behaviour names its production caller
> For a `create` (or `edit`) row that adds a function, an optional parameter, a CLI flag, a config key, an event subscription or a guarded branch, `Description` also states where production invokes it — the call site that supplies the activating argument, the parser registration, the subscription. At signoff that row anchors on a call-site search over production paths, never on the definition; a definition no production caller reaches is not a landed deliverable, and a runner's "dormant until a follow-up wires it" is PARTIAL, not COMPLETE. See `references/verify-caller-before-complete.md`.

**Total: {N} deliverables** — count the rows above.

Every other artifact cites "every row of this table" rather than repeating {N}. That
includes the Orchestration, the Execution Input, the exit criteria, the Signoff, and any
sweep task that reconciles a ledger.

<!-- The total is a CAPTION of the table, derived by counting its rows. It is never an
     independent claim. Do NOT carry a total in from a source document — a source's own
     prose caption may disagree with the table it introduces, and that miscount is
     inherited silently. Count these rows. See references/scaffolding-hygiene.md §12.7. -->

<!-- If you also write a decomposition ("{a} edits + {b} creates"), the classes MUST sum
     to {N} in this same block. Draw every class name from the Class column above and
     nowhere else, so the arithmetic is checkable where it is written. -->

**Ledger treatment of the `verified-absent` class:** {one ledger row each | one aggregate
ledger row for the whole class | a landed deliverable AND a ledger row}. State the choice
here — a sweep reads this line to know how many rows to expect.

<!-- Why this is stated rather than assumed: a verified-absent set folded into one
     aggregate row in one artifact, and expanded to one row EACH in another, yields two
     different totals from the same table. A runner recomputing the ledger then either
     halts or manufactures a row to make the stated total true. -->

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

## Cross-Sprint File Touches <!-- OPTIONAL — include when this sprint edits a file ANY other sprint of the same plan also edits, ordered or not -->

List every file this sprint edits that ANOTHER sprint of the same plan also edits. Each row pairs the file with the co-writing sprint's edit so the executor can verify the other delta's state before applying this sprint's delta.

**Include a row whether or not the two sprints are ordered.** The unordered case is the more dangerous one: with no ordering edge, the two sprints may run in either order or at once, and nothing else in the plan records that the file has two owners. Per `references/scaffolding-hygiene-Part-2-DerivationAndParallelism.md` §16.6, an unordered pair also needs either an ordering edge or a `MUST NOT run concurrently (shared file: …)` row in the Master Plan's Sprint Dependencies table, and the row below goes in BOTH sprints' Sprint Plans.

| File | Co-Writer Task | Co-Writer Delta Marker (content anchor) | Ordering | This Sprint Adds |
|------|----------------|----------------------------------------|----------|------------------|
| `{path/to/file.ext}` | {Abbrev}-S{XX_prior}-{YY}-{##} | `{anchor text the prior sprint inserted}` | prior — that sprint runs first | {delta this sprint adds} |
| `{path/to/file2.ext}` | {Abbrev}-S{XX_other}-{YY}-{##} | `{anchor text the co-writer inserts}` | **none declared** — see Sprint Dependencies | {delta this sprint adds} |

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
