---
description: 19 project-specific callout types for semantic markup in markdown files — syntax, usage rules, and decision matrix
consult-when: Writing `> [!type]` callouts — the 19 callout types, syntax, when to use which
paths: .claude/rules/**, .claude/skills/**, .claude/hooks/**, .claude/agents/**, Docs/**
---

# Callout Conventions

USE `> [!type]` callout syntax to mark content whose type would otherwise be ambiguous. Callouts render natively in Obsidian and GitHub; in other renderers they appear as readable blockquotes.

DO NOT add callouts to content that is already unambiguous from its structure (tables with standard column patterns, numbered lists, code blocks in obvious context). Only mark content that would confuse a reader (or classifier) about its purpose.

## 1. Callout Catalog

The 19 type headings below are the closed list of types. `scripts/lint_markdown.py` reads them from this section at run time: its `callout-type` rule flags a callout outside the list, and its `pitfall-shape` rule flags a pitfall that lacks `Problem:` or `Solution:`. A plugin test runs it with `--strict` over the shipped `references/` and requires zero findings.

### `> [!constraint]` — Binding Rule with Comparison

```markdown
> [!constraint] Rule Name
> Content with WRONG/CORRECT or AVOID/PREFER examples
```

WRAP content in `> [!constraint]` when it shows BOTH the wrong way and the right way, with enforcement language (MUST, NEVER, REQUIRED).

DO NOT use for pure code examples without comparison (leave unmarked).

### `> [!pitfall]` — Pitfall with Solution

```markdown
> [!pitfall] Short Name
> **Problem:** What goes wrong
> **Solution:** How to fix or avoid it
```

WRAP content in `> [!pitfall]` when it pairs a known failure mode with its remediation. MUST have both Problem and Solution.

DO NOT use for: general troubleshooting tables (leave as tables), or warnings without remediation (`> [!hazard]`).

### `> [!binding]` — Binding Enforcement Policy

```markdown
> [!binding] Policy Name
> Enforcement description, mechanism, consequences
```

WRAP content in `> [!binding]` when it declares an enforcement mechanism (hooks, gates, blocks) and what gets enforced.

DO NOT use for informational tables that happen to mention "blocked" (leave as tables).

### `> [!protocol]` — Required Protocol Specification

```markdown
> [!protocol] Protocol Name
> Numbered mandatory steps with confirmation template or gate
```

WRAP content in `> [!protocol]` when it defines a multi-step protocol with REQUIRED emphasis, especially when it includes a confirmation template or output format.

DO NOT use for simple sequential workflows without enforcement (leave as numbered lists).

### `> [!template]` — Output Format Template

```markdown
> [!template] Template Name
> Content with {placeholder} variables to fill in
```

WRAP content in `> [!template]` when it defines an output format with `{placeholder}` variables. This marks content that shows WHAT to produce, not HOW to behave.

DO NOT use for: rule specifications with code fences (`> [!constraint]` or `> [!protocol]`), or code examples for reference (leave unmarked).

### `> [!decide]` — Decision Matrix or Flowchart

```markdown
> [!decide] Decision Name
> If X → do Y; if Z → do W
```

WRAP content in `> [!decide]` when it helps choose between options based on conditions.

DO NOT use for pure lookup tables without conditions or quick reference cards (leave as tables).

### `> [!gate]` — Execution Gate

```markdown
> [!gate] Gate Name
> Condition that MUST be met before proceeding
```

WRAP content in `> [!gate]` when it defines a binary go/no-go condition. If the condition fails, execution MUST stop or redirect.

DO NOT use for approval workflows with rollback (`> [!protocol]`).

### `> [!checklist]` — Validation or Verification Checklist

```markdown
> [!checklist] Checklist Name
> - [ ] Item 1
> - [ ] Item 2
```

WRAP content in `> [!checklist]` when it uses `[ ]` checkbox items for verification.

DO NOT use for numbered workflow steps (leave as numbered lists).

### `> [!verify]` — Verification Commands

```markdown
> [!verify] What You Are Verifying
> **Before:** bash commands
> **After:** bash commands
```

WRAP content in `> [!verify]` when it provides concrete bash/CLI commands to verify an operation completed correctly.

DO NOT use for: code examples showing how to DO something (leave unmarked or `> [!constraint]`), or troubleshooting steps (leave as tables).

### `> [!antipattern]` — Anti-Pattern Warning

```markdown
> [!antipattern] What to Avoid
> Description of the bad pattern and why it fails
```

WRAP content in `> [!antipattern]` when it lists things to AVOID without showing the correct alternative.

DO NOT use for simple "When NOT to use" sections (leave inline).

### `> [!hazard]` — Environment or Context Assertion

```markdown
> [!hazard] Environment Name
> Critical environmental constraints
```

WRAP content in `> [!hazard]` when it declares critical environmental context that constrains ALL subsequent behavior. Typically uses CRITICAL emphasis and describes platform, shell, or path constraints.

DO NOT use for: specific rules about behavior in that environment (`> [!constraint]`), or general informational context (leave as prose).

### `> [!security]` — Security or Credential Constraint

```markdown
> [!security] Constraint Name
> Security-sensitive rule content
```

WRAP content in `> [!security]` when it deals with credentials, authentication, authorization boundaries, or data exposure risks.

DO NOT use for: general binding constraints that mention "never" (`> [!constraint]`), or permission tables without security implications (leave as tables).

### `> [!delegate]` — Agent Assignment Rule

```markdown
> [!delegate] Assignment Name
> Agent-to-task mapping with enforcement
```

WRAP content in `> [!delegate]` when it assigns tasks to specific agents (Haiku/Sonnet/Opus) with MANDATORY enforcement.

DO NOT use for: general role descriptions (leave as prose) or subagent type documentation without enforcement (leave as tables).

### `> [!escalation]` — Escalation or Fallback Chain

```markdown
> [!escalation] Chain Name
> Prioritized fallback steps
```

WRAP content in `> [!escalation]` when it defines a prioritized sequence of fallback actions (A fails, try B; B fails, try C).

DO NOT use for: error handling without escalation priority (leave as lists), or emergency procedures (`> [!hazard]` for trigger, this for response).

### `> [!practice]` — Best Practice or Convention

```markdown
> [!practice] Practice Name
> Advisory guidance using SHOULD/PREFER language
```

WRAP content in `> [!practice]` when it recommends behavior using SHOULD/PREFER language but does NOT enforce it.

DO NOT use for: pure reference information (leave unmarked), or tool-specific recommendations (`> [!decide]`).

### `> [!taskspec]` — Task File Template Specification

```markdown
> [!taskspec] Template Name
> Structure that defines how to organize work documents
```

WRAP content in `> [!taskspec]` when it defines the structure of task files, orchestration files, or other plan artifacts.

DO NOT use for: simple file naming conventions (leave as tables), or code templates (leave as code blocks).

### `> [!consequences]` — Rule Violation Consequences

```markdown
> [!consequences] What Happens When Rules Break
> Rule-to-consequence mapping
```

WRAP content in `> [!consequences]` when it maps rule violations to their consequences.

DO NOT use for: error remediation tables (leave as tables), or general warnings (leave inline).

### `> [!tooldoc]` — Tool Documentation Block

```markdown
> [!tooldoc] Tool Name
> **Purpose:** ...
> **When to Use:** ...
> **When NOT to Use:** ...
```

WRAP content in `> [!tooldoc]` when it documents a specific tool with Purpose, When to Use, and When NOT to Use sections.

DO NOT use for tool configuration details (leave as code blocks).

### `> [!followup]` — Follow-Up BLI Recommendation

WRAP content in `> [!followup]` when encoding an actionable recommendation that should auto-surface as a backlog item during `/planwise backlog` Phase 7. Fields: Recommendation, Target file, Severity, Originating item.

DO NOT use for: general notes or commentary (leave as prose), lessons-learned candidates (use lesson capture instead).

### `> [!binding]` — Sequential Chain (Halt-on-Failure) PATTERN

This is a named **PATTERN**, not a new callout type — it uses the existing `> [!binding]` type. It is catalogued here so plans with serial chains do not re-derive the halt rule per plan.

When a sprint contains a sequential chain of N tasks where each task's correctness gates the next (refactor pipelines, multi-step migrations, schema-evolution chains, dependency-tree builds), the orchestration MUST carry a `> [!binding]` callout in its Critical Path section AND each task in the chain MUST carry a matching halt Success Criterion.

**Orchestration template (paste into the Critical Path section, fill in the `{N}`-task chain identifier):**

> [!binding] Halt-on-{verification-name}-Failure (Tasks {first}–{last})
> If any per-stage task's {verification check} fails, **HALT** the session chain. Do NOT proceed to the next task.
>
> 1. Mark the failing task `BLOCKED` in `{Recovery file path}`.
> 2. Record the {verification} delta + suspected root cause in Recovery Issues Identified.
> 3. Mark Session Status `BLOCKED` until the failure is resolved (triage + fix shipped + {verification} re-run green).
>
> **Why:** {one-sentence cascade explanation — what silently breaks downstream if the chain proceeds against a broken stage}.

**Task-file template (paste into each chain-task's Success Criteria — one per task in the chain):**

```markdown
- [ ] {Verification check} passes on {input window}
- [ ] If {verification} fails: this task is NOT complete. HALT the chain. Record the failure in `{Recovery file path}` Issues Identified, mark this task `BLOCKED`, mark Session Status `BLOCKED`. Do NOT proceed to Task {next-task-id} — {one-sentence cascade explanation}. (See {Orchestration path} Critical Path > Halt-on-{verification-name}-Failure binding callout.)
```

WRONG — sequential chain with parity tests but no halt rule:

```markdown
## Success Criteria

- [ ] Module under 22,000 measured tokens
- [ ] Parity tests pass
- [ ] `{lint}` clean
```

The agent could ship a task with failing parity tests, mark it complete (all code written, lint clean), and the next agent in the chain would refactor against the broken pattern.

CORRECT — halt rule encoded as a dedicated SC backed by an orchestration-level binding callout:

```markdown
## Success Criteria

- [ ] Module under 22,000 measured tokens
- [ ] Parity tests pass
- [ ] If parity tests fail: this task is NOT complete. HALT the chain. {full halt instruction}. (See {Orchestration} Critical Path > Halt-on-Parity-Failure binding callout.)
- [ ] `{lint}` clean
```

NOT applicable to parallel task groups (independent by construction), discovery-phase fan-out (each subagent reads sources independently) or single-task sessions (no chain to halt).

---

## 2. Decision Matrix

When writing content and unsure which callout to use, follow this matrix:

| What You Are Writing | Has Enforcement? | Has Comparison? | Use This Callout |
|---------------------|------------------|-----------------|------------------|
| Rule with WRONG/CORRECT examples | MUST | Yes (paired) | `> [!constraint]` |
| Known failure mode with fix | Advisory | Yes (problem/fix) | `> [!pitfall]` |
| Enforcement mechanism description | MUST | No | `> [!binding]` |
| Multi-step mandatory protocol | MUST | No | `> [!protocol]` |
| Output format with placeholders | None | No | `> [!template]` |
| Conditional choice/branching | Varies | No (multi-path) | `> [!decide]` |
| Go/no-go binary checkpoint | MUST | No (single gate) | `> [!gate]` |
| Did-you-do-this checkbox list | Varies | No | `> [!checklist]` |
| Post-action verification commands | MUST | Yes (before/after) | `> [!verify]` |
| "Don't do this" without alternative | Advisory | No (one-sided) | `> [!antipattern]` |
| Environmental constraint assertion | MUST | No | `> [!hazard]` |
| Credential/auth/security rule | MUST | No | `> [!security]` |
| Agent-to-task assignment | MUST | No | `> [!delegate]` |
| Prioritized fallback chain | MUST/Advisory | Yes (ordered) | `> [!escalation]` |
| Advisory best practice | Advisory (SHOULD) | No | `> [!practice]` |
| Work document structure template | MUST | No | `> [!taskspec]` |
| Rule-to-consequence mapping | MUST | Yes (rule/impact) | `> [!consequences]` |
| Tool reference documentation | None | No | `> [!tooldoc]` |
| Actionable backlog recommendation (target + severity) | Advisory | No | `> [!followup]` |

## 3. Quick Disambiguation

**Content has code blocks — which callout?**
- Shows WRONG/CORRECT? --> `> [!constraint]`
- Has `{placeholders}`? --> `> [!template]`
- Bash verification commands? --> `> [!verify]`
- Reference documentation? --> `> [!tooldoc]` or leave unmarked

**Content has a table — which callout?**
- Conditional logic (If/Then)? --> `> [!decide]`
- Rules mapped to consequences? --> `> [!consequences]`
- Agents mapped to tasks? --> `> [!delegate]`
- Pure lookup data? --> Leave as table (no callout)

**Content says MUST — which callout?**
- Paired WRONG/CORRECT? --> `> [!constraint]`
- Describes enforcement mechanism? --> `> [!binding]`
- Multi-step numbered process? --> `> [!protocol]`
- Single binary go/no-go? --> `> [!gate]`
- Security-related? --> `> [!security]`

## 4. Callout Groups

### Group A: Binding Enforcement (MUST-level)

| Callout | Key Distinction |
|---------|-----------------|
| `> [!constraint]` | Paired comparison (WRONG/CORRECT) |
| `> [!binding]` | Enforcement mechanism (hooks, blocks) |
| `> [!protocol]` | Multi-step mandatory process |
| `> [!gate]` | Binary go/no-go checkpoint |
| `> [!security]` | Credential/auth/exposure rules |
| `> [!consequences]` | Rule-to-impact mapping |

### Group B: Advisory Guidance

| Callout | Key Distinction |
|---------|-----------------|
| `> [!pitfall]` | Problem/Solution pairing |
| `> [!antipattern]` | One-sided "don't do this" |
| `> [!practice]` | SHOULD/PREFER language |
| `> [!escalation]` | Ordered fallback priority |
| `> [!delegate]` | Agent assignment (overlaps Group A) |
| `> [!followup]` | Actionable backlog recommendation (auto-surfaces in `/planwise backlog`) |

### Group C: Verification

| Callout | Key Distinction |
|---------|-----------------|
| `> [!checklist]` | Checkbox items (planning) |
| `> [!verify]` | Executable verification commands |

### Group D: Template/Specification

| Callout | Key Distinction |
|---------|-----------------|
| `> [!template]` | Output with `{placeholders}` (deliverable format) |
| `> [!taskspec]` | Work document structure definition |
| `> [!decide]` | Conditional branching logic |

### Group E: Context/Environment

| Callout | Key Distinction |
|---------|-----------------|
| `> [!hazard]` | Platform/environment constraints |

### Group F: Reference Documentation

| Callout | Key Distinction |
|---------|-----------------|
| `> [!tooldoc]` | Tool Purpose/When/When Not blocks |

## 5. Nesting Rules

NEST callouts when a block contains multiple content types. The outer callout sets the primary signal; the inner callout refines it:

```markdown
> [!protocol] Protocol Name
> 1. Step one
> 2. Step two — produce this output:
>
> > [!template] Output Format
> > FIELD: {value}
>
> 3. Step three
```

LIMIT nesting to 2 levels maximum. If deeper nesting is needed, split into separate sections. The `callout-nesting` rule of `scripts/lint_markdown.py` flags a callout nested deeper than 2 levels.

---

*19 callout types designed from the 108-type unified content taxonomy. Apply these when writing or editing markdown to make content type explicit.*
