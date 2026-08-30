---
description: 19 project-specific callout types for semantic markup in markdown files — syntax, usage rules, and decision matrix
paths: .claude/rules/**, .claude/skills/**, .claude/hooks/**, .claude/agents/**, Docs/**
---

# Callout Conventions

USE `> [!type]` callout syntax to mark content whose type would otherwise be ambiguous. Callouts render natively in Obsidian and GitHub; in other renderers they appear as readable blockquotes.

DO NOT add callouts to content that is already unambiguous from its structure (tables with standard column patterns, numbered lists, code blocks in obvious context). Only mark content that would confuse a reader (or classifier) about its purpose.

## 1. Callout Catalog

### `> [!constraint]` — Binding Rule with Comparison

```markdown
> [!constraint] Rule Name
> Content with WRONG/CORRECT or AVOID/PREFER examples
```

WRAP content in `> [!constraint]` when it shows BOTH the wrong way and the right way, with enforcement language (MUST, NEVER, REQUIRED). The defining characteristic is paired comparison.

DO NOT use for: anti-patterns alone (`> [!antipattern]`), advisory practices without enforcement (`> [!practice]`), or pure code examples without comparison (leave unmarked).

### `> [!pitfall]` — Pitfall with Solution

```markdown
> [!pitfall] Short Name
> **Problem:** What goes wrong
> **Solution:** How to fix or avoid it
```

WRAP content in `> [!pitfall]` when it pairs a known failure mode with its remediation. MUST have both Problem and Solution.

DO NOT use for: binding rules with WRONG/CORRECT (`> [!constraint]`), general troubleshooting tables (leave as tables), or warnings without remediation (`> [!hazard]`).

### `> [!binding]` — Binding Enforcement Policy

```markdown
> [!binding] Policy Name
> Enforcement description, mechanism, consequences
```

WRAP content in `> [!binding]` when it declares an enforcement mechanism (hooks, gates, blocks) and what gets enforced. This is about the SYSTEM of enforcement, not a specific rule comparison.

DO NOT use for: individual WRONG/CORRECT rules (`> [!constraint]`), advisory recommendations (`> [!practice]`), or informational tables that happen to mention "blocked" (leave as tables).

### `> [!protocol]` — Required Protocol Specification

```markdown
> [!protocol] Protocol Name
> Numbered mandatory steps with confirmation template or gate
```

WRAP content in `> [!protocol]` when it defines a multi-step protocol with REQUIRED emphasis, especially when it includes a confirmation template or output format. The key signal is numbered mandatory steps plus a template.

DO NOT use for: simple sequential workflows without enforcement (leave as numbered lists), decision trees (`> [!decide]`), or checklists (`> [!checklist]`).

### `> [!template]` — Output Format Template

```markdown
> [!template] Template Name
> Content with {placeholder} variables to fill in
```

WRAP content in `> [!template]` when it defines an output format with `{placeholder}` variables. This marks content that shows WHAT to produce, not HOW to behave.

DO NOT use for: rule specifications with code fences (`> [!constraint]` or `> [!protocol]`), task file structure definitions (`> [!taskspec]`), or code examples for reference (leave unmarked).

### `> [!decide]` — Decision Matrix or Flowchart

```markdown
> [!decide] Decision Name
> If X → do Y; if Z → do W
```

WRAP content in `> [!decide]` when it helps choose between options based on conditions. The defining feature is conditional branching.

DO NOT use for: pure lookup tables without conditions (leave as tables), quick reference cards (leave as tables), or simple Yes/No gates (`> [!gate]`).

### `> [!gate]` — Execution Gate

```markdown
> [!gate] Gate Name
> Condition that MUST be met before proceeding
```

WRAP content in `> [!gate]` when it defines a binary go/no-go condition. If the condition fails, execution MUST stop or redirect. This is a single checkpoint, not a multi-step process.

DO NOT use for: multi-step protocols (`> [!protocol]`), approval workflows with rollback (`> [!protocol]`), or decision trees with multiple outcomes (`> [!decide]`).

### `> [!checklist]` — Validation or Verification Checklist

```markdown
> [!checklist] Checklist Name
> - [ ] Item 1
> - [ ] Item 2
```

WRAP content in `> [!checklist]` when it uses `[ ]` checkbox items for verification. These are "did you do this?" lists, not "here is how to do this" workflows.

DO NOT use for: numbered workflow steps (leave as numbered lists), decision tables (`> [!decide]`), or post-action verification with bash commands (`> [!verify]`).

### `> [!verify]` — Verification Commands

```markdown
> [!verify] What You Are Verifying
> **Before:** bash commands
> **After:** bash commands
```

WRAP content in `> [!verify]` when it provides concrete bash/CLI commands to verify an operation completed correctly. Distinguished from `> [!checklist]` by containing actual executable commands.

DO NOT use for: abstract checklists without commands (`> [!checklist]`), code examples showing how to DO something (leave unmarked or `> [!constraint]`), or troubleshooting steps (leave as tables).

### `> [!antipattern]` — Anti-Pattern Warning

```markdown
> [!antipattern] What to Avoid
> Description of the bad pattern and why it fails
```

WRAP content in `> [!antipattern]` when it lists things to AVOID without showing the correct alternative. The key distinction from `> [!constraint]` is that anti-patterns are one-sided — "don't do this" without a paired "do this instead."

DO NOT use for: paired WRONG/CORRECT comparisons (`> [!constraint]`), pitfalls with explicit solutions (`> [!pitfall]`), or simple "When NOT to use" sections (leave inline).

### `> [!hazard]` — Environment or Context Assertion

```markdown
> [!hazard] Environment Name
> Critical environmental constraints
```

WRAP content in `> [!hazard]` when it declares critical environmental context that constrains ALL subsequent behavior. Typically uses CRITICAL emphasis and describes platform, shell, or path constraints. This is "here is the world you operate in."

DO NOT use for: specific rules about behavior in that environment (`> [!constraint]`), general informational context (leave as prose), or security warnings (`> [!security]`).

### `> [!security]` — Security or Credential Constraint

```markdown
> [!security] Constraint Name
> Security-sensitive rule content
```

WRAP content in `> [!security]` when it deals with credentials, authentication, authorization boundaries, or data exposure risks.

DO NOT use for: general binding constraints that mention "never" (`> [!constraint]`), environment assertions (`> [!hazard]`), or permission tables without security implications (leave as tables).

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

WRAP content in `> [!escalation]` when it defines a prioritized sequence of fallback actions (A fails, try B; B fails, try C). The defining feature is an ordered priority chain.

DO NOT use for: decision trees with independent branches (`> [!decide]`), error handling without escalation priority (leave as lists), or emergency procedures (`> [!hazard]` for trigger, this for response).

### `> [!practice]` — Best Practice or Convention

```markdown
> [!practice] Practice Name
> Advisory guidance using SHOULD/PREFER language
```

WRAP content in `> [!practice]` when it recommends behavior using SHOULD/PREFER language but does NOT enforce it. Distinguished from `> [!constraint]` by lacking enforcement (MUST/NEVER/REQUIRED).

DO NOT use for: binding rules with enforcement language (`> [!constraint]`), pure reference information (leave unmarked), or tool-specific recommendations (`> [!decide]`).

### `> [!taskspec]` — Task File Template Specification

```markdown
> [!taskspec] Template Name
> Structure that defines how to organize work documents
```

WRAP content in `> [!taskspec]` when it defines the structure of task files, orchestration files, or other plan artifacts. This is "how to structure a work document" not "what to produce as output."

DO NOT use for: output templates for deliverables (`> [!template]`), simple file naming conventions (leave as tables), or code templates (leave as code blocks).

### `> [!consequences]` — Rule Violation Consequences

```markdown
> [!consequences] What Happens When Rules Break
> Rule-to-consequence mapping
```

WRAP content in `> [!consequences]` when it maps rule violations to their consequences.

DO NOT use for: rules themselves (`> [!constraint]`, `> [!binding]`, etc.), error remediation tables (leave as tables), or general warnings (leave inline).

### `> [!tooldoc]` — Tool Documentation Block

```markdown
> [!tooldoc] Tool Name
> **Purpose:** ...
> **When to Use:** ...
> **When NOT to Use:** ...
```

WRAP content in `> [!tooldoc]` when it documents a specific tool with Purpose, When to Use, and When NOT to Use sections.

DO NOT use for: tool selection decisions (`> [!decide]`), anti-patterns about tool misuse (`> [!antipattern]`), or tool configuration details (leave as code blocks).

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

Applies to:
- Refactor pipelines where each stage depends on conventions established by prior stages
- Multi-step data migrations where a partial failure leaves the data store in an inconsistent state
- Schema evolution chains (Layer N → N+1 → N+2)
- Build dependency trees where each artifact is consumed by the next

NOT applicable to:
- Parallel task groups (they are explicitly independent by construction)
- Discovery-phase fan-out (each subagent reads sources independently)
- Single-task sessions (no chain to halt)

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

LIMIT nesting to 2 levels maximum. If deeper nesting is needed, split into separate sections.

---

*19 callout types designed from the 108-type unified content taxonomy. Apply these when writing or editing markdown to make content type explicit.*
