# Task File Template

Use this template when creating `{Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md`.

---

```markdown
# Task: {Agent}-{TaskName}

**Task ID:** {Abbrev}-S{XX}-{YY}-{##}
**Agent:** {Haiku|Sonnet|Opus}
**Estimated Tokens:** ~{X}K
**Depends On:** {task numbers or "-"}
**Output:** {path where deliverable should be saved, e.g., Outputs/{Abbrev}-{description}.md}

---

## Objective

{Clear, specific goal for this task - what must be accomplished}

---

## Required Context

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

> **In DELEGATED sessions:** These files are read by the **subagent**, not the orchestrator. The orchestrator reads only plan files and passes this task's content to the subagent prompt. See the Orchestration's Execution Strategy for the declared mode.

---

## Execution Steps

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

---

## Expected Output

{What the subagent should produce - be specific about format and content}

---

## Success Criteria

- [ ] {Measurable criterion 1}
- [ ] {Measurable criterion 2}

---

## Notes for Agent

{Special instructions, edge cases, or context the agent needs}
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
