---
description: Context loading strategy (standard-plan vs. Meta-Plan decision) and context conservation tactics for planning sessions
---

# Context Loading and Conservation

**Purpose:** When to load context directly vs. split into a Meta-Plan, and tactics for conserving context during execution.
**Anchor:** [session-context-budget.md](session-context-budget.md) (Token Budget §5, Read-Tool Hard Limits, Large-File Read Tactics)

---

## 6. Context Loading Strategy

> [!decide] Context Loading Decision
> Compare total context to the tier's `meta_plan_threshold` (from the Threshold Formulas table in [session-context-budget.md](session-context-budget.md) §5 — 100K on Pro, 500K on Max):
>
> | If... | Then... |
> |-------|---------|
> | Total context < `meta_plan_threshold` | Create plan directly using standard structure |
> | Total context > `meta_plan_threshold` | Create **Meta-Plan** first, then **Execution Plan** |

### The Core Insight

| Action | Context Impact |
|--------|----------------|
| Load file with Read | **+adds** to context (read fully!) |
| Claude produces output | **minimal** (just response text) |
| Back-and-forth messages | **+adds** each turn |
| Subagent runs | **Fresh context** (doesn't inherit your accumulation) |

**Key insight:** Subagents don't inherit your context accumulation. Each gets a fresh context window sized by its **dispatched model** (Sonnet/Haiku 200K, Opus 1M — see [§ Subagent Context Window](session-context-budget.md#subagent-context-window)), NOT the parent's tier. Use this to your advantage.

### When to Use Meta-Plan

> [!decide] Standard vs Meta-Plan
> | Condition | Action |
> |-----------|--------|
> | Total context needed < `meta_plan_threshold` | Proceed with standard plan |
> | Total context needed > `meta_plan_threshold` | **Use Meta-Plan** (3-phase: Discovery → Scaffolding → Execution) |
> | Multiple complex source documents need cross-referencing | **Use Meta-Plan** |
> | Work spans multiple sessions and context must be preserved | **Use Meta-Plan** |
>
> `meta_plan_threshold` = 100K on Pro, 500K on Max — see [session-context-budget.md](session-context-budget.md) §5 Threshold Formulas.

### Meta-Plan Purpose

1. **Fresh context per agent** - Each subagent gets its own fresh context window, sized by its dispatched model (Sonnet/Haiku 200K, Opus 1M — not the parent's tier)
2. **Persistent artifacts** - File outputs survive session boundaries
3. **Recovery points** - Written documents survive context compaction
4. **Fan-out, not compression** - More detail = more execution units, not fewer

The goal is NOT to summarize and reduce context. The goal is to **organize and consolidate** source material into structured specification parts that can be consumed by downstream agents. Only remove duplicated or trivial information — preserve all substantive detail.

**Three Phases:**

| Phase | Purpose | Produces |
|-------|---------|----------|
| **Discovery (Meta)** | Read sources, organize findings | Specification parts (full detail, multi-part) |
| **Scaffolding** | Create execution plan files | Sprint/Session/Task files from spec parts |
| **Execution** | Implement the tasks | Code, configs, artifacts per task files |

Each phase uses subagents with fresh context. Each agent reads only the specification part relevant to its scope.

**For Meta-Plan folder structure:** See [Section 2: Folder Structure](session-planning-protocol.md#2-naming-conventions-binding)
**For Meta-Plan required files:** See [Section 8: Required Files Per Level](session-plan-requirements.md#8-required-files-per-level)

### Patterns

> [!constraint] Context Accumulation
> **WRONG:**
> ```
> ❌ Load 40K → work → load 30K more → work → load 30K more → CONTEXT EXPLODES
> ```
>
> **CORRECT:**
> ```
> ✅ Load 80K upfront (all files read fully) → work without loading more → stays ~90K → FINE on Pro
>
> ✅ Need more than `meta_plan_threshold` total (100K on Pro / 500K on Max)? → Use Meta-Plan (3-phase):
>    Discovery agents (fresh `available_for_work` each): Read sources → produce full-detail spec parts
>    Consolidation agent: Organize + deduplicate spec parts (NOT summarize)
>    Scaffolding: Read spec parts → extract Execution Inputs (per sprint) + create plan files
>    Execution agents (fresh `available_for_work` each): Read sprint Execution Input + execute tasks
> ```
>
> More sessions is not an issue. Context loss is the issue. Meta-Plan prevents context loss by creating file artifacts.

---

## 7. Context Conservation

### Task List Format

Every session MUST have a task list with token estimates:

```markdown
| # | Task | Agent | Est. Tokens | Depends On |
|---|------|-------|-------------|------------|
| 1 | {task} | Haiku | ~{X}K | - |
| 2 | {task} | Sonnet | ~{X}K | 1 |
```

### Conservation Tactics

Operational rules for managing token usage during execution:

1. **Summarize, don't repeat** — Reference previous work, don't copy it
2. **Use file references** — "See `Outputs/step1-results.md`" instead of inline content
3. **Incremental updates** — Only report changes, not full state
4. **Prune completed work** — Remove detailed logs after success

### Compaction Triggers

```
At each major milestone:
1. Summarize progress in Recovery file
2. Move detailed output to Outputs/ folder
3. Reference files instead of inline content
4. If context > 80% full: trigger compaction

Compaction Triggers:
- After completing each phase
- Before starting complex analysis
- When error loops exceed 5 iterations
```

### Minimal Prompt Pattern

Keep iteration prompts minimal:

```markdown
## Iteration Prompt (Minimal)

Current state: {1-2 sentences}
Remaining: {bullet list of incomplete items}
Next action: {single action to take}
Completion criteria: {reference to criteria doc}
```

### Output File Strategy

```
Outputs/
├── step1-table-counts.json     # Structured data as JSON
├── step2-fk-validation.json    # Machine-readable results
├── step3-analysis.md           # Human-readable analysis
└── final-decision.md           # Final summary only
```

---

*Companion files: [session-context-budget.md](session-context-budget.md) (Token Budget, read-gate canonical), [session-planning-protocol.md](session-planning-protocol.md), [session-plan-requirements.md](session-plan-requirements.md)*
