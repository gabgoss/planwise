# Task File Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md`.

---

```markdown
# Task: {Agent}-{TaskName}

**Task ID:** {Abbrev}-S{XX}-{YY}-{##}
**Agent:** {Haiku|Sonnet|Opus}
**Estimated Tokens:** ~{X}K
**Depends On:** {task numbers, or "cross-sprint: {Abbrev}-S{XX}-{YY}-{##}", or "-"}
**Cross-Sprint Refs:** {list of cross-sprint files in Required Context, or "None"}  <!-- Add only when Required Context cites cross-sprint files (per session-plan-requirements.md cross-sprint dependency convention) -->
**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}

---

## Objective <!-- REQUIRED -->

{Clear, specific goal for this task - what must be accomplished}

---

## Required Context <!-- REQUIRED -->

| Priority | File | Est. Lines | Est. Tokens | Purpose |
|----------|------|-----------|-------------|---------|
| 1 | {file path} | ~{N} | ~{X}K | {why needed} |
| 2 | {file path} | ~{N} | ~{X}K | {why needed} |

**Context subtotal:** ~{X}K tokens (reads) + ~{X}K (output) = ~{X}K total
<!-- Reconciliation: this total MUST match the Estimated Tokens in this task's header. -->
<!-- Use ~13 tokens/line for reads. See reference.md Token Estimation Reference for output costs. -->

**Section Reference Rule (scaffolded plans):** When referencing Execution Inputs, enumerate INDIVIDUAL section numbers with purpose — never ranges.

| Pattern | Acceptable? |
|---------|-------------|
| `EI.md (Sections 2-5)` | **NO** — agent doesn't know which section provides what |
| `EI.md — Section 2 (event types), Section 3 (patterns)` | **YES** — each section annotated with purpose |

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

**Mapping Disambiguation:** When a task creates X→Y mapping logic (enum→domain, type→template, event→category), include either:
- A complete mapping table in the task file, OR
- Explicit decision rules with fallback (e.g., "if X matches pattern A → Y1; else → default")

Never leave many-to-many mappings for the agent to infer.

**Interface Consumption:** When a task's input is another module's data model (e.g., reads `ClassifiedChunk` or `HookDetectionResult`), include a field mapping showing which fields are consumed and how:

| Input Field | Used For |
|-------------|----------|
| {field_name} | {how it is used in this task} |

### Field Mapping (Required for MERGE/upsert tasks)

When this task emits MERGE or upsert SQL, include a Field Mapping subsection with Row↔DDL alignment per `references/task-content-fidelity.md` §9.B.8:

| Source Field | DDL Column | Type Cast | Default | Notes |
|--------------|------------|-----------|---------|-------|
| `{source_field_name}` | `{ddl_column_name}` | `{type}` | `{default}` | {1-line note} |

Missing Field Mapping for MERGE/upsert tasks = BLOCKER at `/planwise review`.

### USED-Helper Enumeration (Required when copying helpers from reference modules)

When this task copies helpers from a reference module, explicitly enumerate USED helpers and NOT-USED helpers per `references/task-content-fidelity.md` §9.B.7:

**USED helpers** (will be invoked in this task):
- `{helper_name_1}` — {1-line purpose}
- `{helper_name_2}` — {1-line purpose}

**NOT-USED helpers** (in the reference module but NOT invoked):
- `{helper_name_3}` — {why not used}

Ambiguous copy-paste of helpers without enumeration = BLOCKER at `/planwise review`.

---

## Expected Output <!-- REQUIRED -->

{What the subagent should produce - be specific about format and content}

---

## Verification Commands <!-- CONDITIONAL — required if task touches code, tests, or schemas -->

> [!verify] Before / After Commands
> **Before:**
> ```
> {cmd_before_1}   # e.g., {lint-cmd} on changed files
> {cmd_before_2}   # e.g., grep current row count
> ```
> **After:**
> ```
> {cmd_after_1}    # e.g., {lint-cmd} on changed files (expect: pass)
> {cmd_after_2}    # e.g., {test-cmd} or specific test
> {cmd_after_3}    # e.g., grep updated row count
> ```

### Per-File-Type Commands

| File Type | Verification Command (example) |
|-----------|--------------------------------|
| `.py` | `{lint-cmd} check {path}` |
| `.ipynb` (notebooks) | `{notebook-exec-cmd} {path}` |
| `.sql` | `psql -f {path}` (or `{driver-cli} -f {path}`) |
| `.{ext}` | `{cmd}` |

> [!practice] Connectivity Precheck Placement
> When the task requires network/DB connectivity, the connectivity precheck command MUST appear in the **Before** block (not inline in Execution Steps).

---

## Success Criteria <!-- REQUIRED -->

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}

---

## Notes for Agent

{Special instructions, edge cases, or context the agent needs}

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
