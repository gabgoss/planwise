# Task File Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md`.

---

```markdown
# Task: {Agent}-{TaskName}

**Task ID:** {Abbrev}-S{XX}-{YY}-{##}
**Agent:** {Haiku|Sonnet|Opus}
**Estimated Tokens:** ~{X}K
**Token Budget:** ~{X}K (exception: {none | 1M (cost) | paged-read (read) | refactor-pending})  <!-- OPTIONAL — Token Saver only. Add only when the warning engine flags this task. `1M (cost)` raises the dispatch to Opus/1M (cost-reason Critical, oversized indivisible file); `paged-read (read)` means a Required Context file trips a Read gate and the runner pages it (read-reason Critical — NOT 1M-resolvable); `refactor-pending` means a core/edited file must be split before this task is safe. -->
**Depends On:** {task numbers, or "cross-sprint: {Abbrev}-S{XX}-{YY}-{##}", or "-"}
**Cross-Sprint Refs:** {list of cross-sprint files in Required Context, or "None"}  <!-- Add only when Required Context cites cross-sprint files (per task-file-and-tracking-requirements.md cross-sprint dependency convention) -->
**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}

---

## Objective <!-- REQUIRED -->

{Clear, specific goal for this task - what must be accomplished}

---

## Required Context <!-- REQUIRED -->

| Priority | File | Est. Lines | Est. Tokens | Purpose |
|----------|------|-----------|-------------|---------|
| 1 | {file path} | ~{N} | ~{X}K | {why needed} {⚠ PAGED ≥25K {model}-tok / ⚠ REFACTOR ≥256 KiB — OPTIONAL read-handling annotation, Token Saver only} |
| 2 | {file path} | ~{N} | ~{X}K | {why needed} |

<!-- OPTIONAL read-handling annotation (Token Saver only): append to a row's Purpose for any file the doctor read-gate scan flagged.
     `⚠ PAGED ≥25K {model}-tok` — file is above the per-assigned-model 25K-token page cap; the runner MUST page it (offset/limit/Grep), it does NOT all arrive in one Read.
     `⚠ REFACTOR ≥256 KiB` — file is at/over the 256 KiB byte gate; Read refuses it without offset/limit — page it, and refactor + backlog if it is a core/edited dependency.
     Both are read-reason flags — NOT resolved by the 1M-exception (Opus trips the page cap sooner). -->

**Context subtotal:** ~{X}K tokens (reads) + ~{X}K (output) = ~{X}K total
<!-- Reconciliation: this total MUST match the Estimated Tokens in this task's header. -->
<!-- Use ~13 tokens/line for reads. See reference.md Token Estimation Reference for output costs. -->
<!-- Read-gate note (Token Saver): the read-gate token count uses the task's ASSIGNED-MODEL rate (Sonnet/Haiku 13, Opus 19 tok/line) — a separate per-model check, NOT a change to this reconciliation. The budget Est. Tokens / reconciliation above stay on the existing ~13/line convention. -->
<!-- Shared-context rule: a file cited by MULTIPLE tasks MUST carry the same measured Est. Lines (from wc -l on the live file) in every task — it is a single source of truth, not a per-task guess. -->

**Section Reference Rule (scaffolded plans):** When referencing Execution Inputs, enumerate INDIVIDUAL section numbers with purpose — never ranges.

| Pattern | Acceptable? |
|---------|-------------|
| `EI.md (Sections 2-5)` | **NO** — agent doesn't know which section provides what |
| `EI.md — Section 2 (event types), Section 3 (patterns)` | **YES** — each section annotated with purpose |

### Comparison-Task Coverage Row (Required when the task's deliverable is a comparison or reconciliation)

Where the task's deliverable is a comparison or reconciliation (enumerate discrepancies, reconcile A against B, find drift between a spec and an implementation), the Required Context table MUST carry the reference source's **measured coverage** as its own row — the sample size, the coverage fraction, and the date measured. The brief's framing follows the measurement (per `references/task-content-fidelity.md` §9.A.12 — Size comparison tasks by reference coverage): high coverage → a reconciliation; near-zero coverage → a census with an actionable tail, budgeted for listing volume.

### Schema Pin (Required when task touches DB writes)

When this task emits SQL touching `{table_name}`, include a Schema Pin block per `references/schema-pin-requirement.md` §3:

```
**Schema Pin** — {schema_file}#{section}
```sql
{verbatim DDL slice — CREATE TABLE + relevant ALTER TABLEs}
```
Live as of: {YYYY-MM-DD}
```

Missing Schema Pin for SQL-emitting tasks = BLOCKER at `/planwise review`.

> [!constraint] No `~?` Placeholders in Token Estimates
> WRONG: `**Estimated Tokens:** ~?K` or `Est. Tokens: ~?`
> CORRECT: Compute bottom-up estimate per `references/task-content-fidelity.md` §9.A.2 + §9.A.3 token rate band. Final estimate MUST be a concrete integer.

> **In DELEGATED sessions:** These files are read by the **subagent**, not the orchestrator. The orchestrator reads only plan files and passes this task's content to the subagent prompt. See the Orchestration's Execution Strategy for the declared mode.

---

## Execution Steps <!-- REQUIRED -->

1. {Step 1 - specific action}
2. {Step 2 - specific action}
3. {Step 3 - specific action}

### Cross-Sprint Prerequisite Grep Gate (Required when this task edits a file already edited by a prior sprint)

When this task edits a file that an earlier sprint of the same plan also edited (per the Sprint Plan's `## Cross-Sprint File Touches` section), Step 1 MUST be a grep gate that verifies the prior sprint's delta marker is present in the file. The gate makes the cross-sprint dependency mechanical: the executor cannot proceed against an outdated baseline.

```bash
# Step 1: Cross-sprint prerequisite — verify {prior-sprint-task-id} delta landed
grep -c '{prior-delta-marker}' {path/to/cross-sprint-file.ext}
# Expected: ≥1 (marker inserted by {prior-sprint-task-id}). If 0 → HALT, prior sprint incomplete.
```

Authoring rules:

- `{prior-delta-marker}` MUST be specific enough to disambiguate the prior delta from unrelated content (e.g., a row anchor, a named callout, a unique identifier — not a generic word).
- The HALT message MUST name the specific prior-sprint task ID so the executor knows which sprint is incomplete.
- If multiple prior sprints touched this file, the gate runs once per prior delta — each with its own grep + HALT pair.
- The gate is Step 1 (before any read of the file's "Current state" anchor) — anchor reads against an outdated baseline produce false matches that mask the real defect.

Missing prerequisite grep gate when the Sprint Plan declares a Cross-Sprint File Touch for this file = BLOCKER at `/planwise review`.

**Mapping Disambiguation:** When a task creates X→Y mapping logic (enum→domain, type→template, event→category), include either:
- A complete mapping table in the task file, OR
- Explicit decision rules with fallback (e.g., "if X matches pattern A → Y1; else → default")

Never leave many-to-many mappings for the agent to infer.

**Interface Consumption:** When a task's input is another module's data model (e.g., reads `ClassifiedChunk` or `HookDetectionResult`), include a field mapping showing which fields are consumed and how:

| Input Field | Used For |
|-------------|----------|
| {field_name} | {how it is used in this task} |

### Field Mapping (Required for MERGE/upsert tasks)

When this task emits MERGE or upsert SQL, include a Field Mapping subsection with Row↔DDL alignment per `references/verify-before-cite.md` §9.B.8:

| Source Field | DDL Column | Type Cast | Default | Notes |
|--------------|------------|-----------|---------|-------|
| `{source_field_name}` | `{ddl_column_name}` | `{type}` | `{default}` | {1-line note} |

Missing Field Mapping for MERGE/upsert tasks = BLOCKER at `/planwise review`.

### USED-Helper Enumeration (Required when copying helpers from reference modules)

When this task copies helpers from a reference module, explicitly enumerate USED helpers and NOT-USED helpers per `references/verify-before-cite.md` §9.B.7:

**USED helpers** (will be invoked in this task):
- `{helper_name_1}` — {1-line purpose}
- `{helper_name_2}` — {1-line purpose}

**NOT-USED helpers** (in the reference module but NOT invoked):
- `{helper_name_3}` — {why not used}

Ambiguous copy-paste of helpers without enumeration = BLOCKER at `/planwise review`.

---

## Expected Output <!-- REQUIRED -->

{What the subagent should produce - be specific about format and content}

<!-- Structure-as-checklist + template pointer: when this task's output is consumed
     structurally by a named downstream task (an aggregator reading a named section, a
     script parsing headers, a table cell read by column position), point at a template file
     rather than inlining the shape, and list every required heading and table-column header
     here as an explicit checklist. State that the post-dispatch acceptance step greps the
     produced file for these headings/columns before accepting it. -->

---

## Verification Commands <!-- CONDITIONAL — required if task touches code, tests, or schemas -->

> [!verify] Before / After Commands
> **Before:**
> ```
> {cmd_before_1}   # e.g., {lint-cmd} on changed files
> {cmd_before_2}   # e.g., wc -l on the edited file
> ```
> **After:**
> ```
> {cmd_after_1}    # e.g., {lint-cmd} on changed files (expect: pass)
> {cmd_after_2}    # e.g., {test-cmd} or specific test
> {cmd_after_3}    # e.g., {test-cmd} on the touched module
> ```
> If one of the three command types (connectivity/precondition, lint/format, exec/smoke)
> does not apply to this task, replace that type's `{cmd_after_N}` line above with
> `<!-- NEEDS-COMMAND -->` so the gap stays visible at review time — never leave the line blank.

### Per-File-Type Commands

| File Type | Verification Command (example) |
|-----------|--------------------------------|
| `.py` | `{lint-cmd} check {path}` |
| `.ipynb` (notebooks) | `{notebook-exec-cmd} {path}` |
| `.sql` | `psql -f {path}` (or `{driver-cli} -f {path}`) |
| `.{ext}` | `{cmd}` |

> [!practice] Connectivity Precheck Placement
> When the task requires network/DB connectivity, the connectivity precheck command MUST appear in the **Before** block (not inline in Execution Steps).

> [!constraint] Every Verification Command Names Its Owner
> Each command in the Before/After blocks MUST name its owner — **runner** or **orchestrator** — the one who runs it. An unattributed command that mutates the artifact it checks is the specific shape that invites a double execution: both the runner and the orchestrator may run it, and a mutating check run against a file the runner still owns produces a two-writer measurement that is indistinguishable from a settled one.

---

## Success Criteria <!-- REQUIRED -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}

### Verbatim-Copy Line-Count Range (Required when task copies verbatim content from an EI section)

When the task instruction is "copy verbatim from EI §X" (or equivalent), the `wc -l` smoke-check range MUST be computed against the EI's marked verbatim body block only — NOT the surrounding EI section, which typically embeds scaffolding metadata (Substitution Log, EI-only headers, EI-only Notes) the task instructions strip from the written file. Tolerance band ±3-5 lines for renderer differences; a 10%+ delta is NOT a smoke pass. See `references/ei-citation-and-token-reconciliation.md` §8.2.

Example success-criteria phrasing:

- [ ] File line count is ~{body-block-min}-{body-block-max} lines (marked body block only — excludes EI Substitution Log, EI-only Notes, EI-only headers)

EI-section-length estimates for verbatim-copy tasks (instead of body-block estimates) = BLOCKER at `/planwise review`.

---

## Notes for Agent

{Special instructions, edge cases, or context the agent needs}

<!-- Anticipated-breach prompt: if this task's work predictably collides with a binding
     rule — a file already near a size limit, a change that would push a module across a
     layering boundary — name the collision and the required halt-and-report instruction
     here explicitly. A brief that anticipates the breach routes it; a brief that is silent
     leaves the runner to decide. -->

**DELEGATED retry-limited error recovery:** When this task runs as a delegated task-runner subagent, retry a failed step up to 3 times before reporting BLOCKED in the Recovery file (per `handlers/run.md` Self-Correction Pattern — never loop indefinitely).
```

---

## Naming Convention

**Pattern:** `{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md`

| Part | Description | Example |
|------|-------------|---------|
| `{Abbrev}` | Plan abbreviation | `PI` |
| `S{XX}` | Sprint number | `S01` |
| `{YY}` | Session number | `01` |
| `{##}` | Task number (two digits) | `01`, `02`, `03` |
| `{Agent}` | Agent type | `Haiku`, `Sonnet`, `Opus` |
| `{TaskName}` | Short name (PascalCase) | `ValidateSchema`, `GenerateEntity` |

**Example:** `PI-S01-01-02-Sonnet-GenerateEntity.md`

---

## Agent Selection Guide

| Use | When Task Involves |
|-----|-------------------|
| **Haiku** | Lookups, validation, counts, file search |
| **Sonnet** | Code generation, implementation, refactoring |
| **Opus** | Architecture decisions, trade-offs, complex analysis |
