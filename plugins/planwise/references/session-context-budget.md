---
description: Token budget management, context loading strategy, and conservation tactics for session planning
---

# Session Context Budget

**Purpose:** Token budget management, context loading strategy, and context conservation rules for planning sessions.
**Companion files:** [session-planning-protocol.md](session-planning-protocol.md) (protocol, hierarchy, delegation), [session-plan-requirements.md](session-plan-requirements.md) (file specifications, task templates)

---

## 5. Token Budget

### Context Window Tier

All token budgets in planwise scale with the user's Claude plan tier. The tier is recorded in `config.yaml` under the `context:` block:

```yaml
context:
  plan_tier: "pro"        # "pro" or "max"
  context_window: 200000  # 200000 or 1000000
```

| Plan tier | `context_window` | Source |
|-----------|-----------------|--------|
| `pro` | 200,000 | Claude Pro plan default |
| `max` | 1,000,000 | Claude Max plan default |

> [!constraint] Backward Compatibility — Default to Pro
> When the `context:` block is missing from `config.yaml` (configs generated before this field was added), handlers MUST default to `plan_tier: pro` / `context_window: 200000`. NEVER assume a missing block means Max — older configs were authored against Pro budgets and silently upgrading them would over-budget every plan.
>
> Reference pseudocode:
>
> ```python
> ctx = config.get("context", {}) or {}
> context_window = int(ctx.get("context_window", 200000))
> plan_tier = ctx.get("plan_tier", "pro")
> ```

### Tier-Specific Budget Table

The same fixed overhead applies on both tiers; only the available-for-work budget scales:

| Component | Pro (200K) | Max (1M) | Notes |
|-----------|-----------|----------|-------|
| System prompt | ~4K | ~4K | Fixed |
| System tools | ~22K | ~22K | Fixed |
| Global rules + CLAUDE.md | ~27K | ~27K | Always loaded |
| Skills + agents (descriptions) | ~1K | ~1K | Always loaded |
| **Subagent / fixed overhead total** | **~54K** | **~54K** | Empirical (from `/context` on fresh session) |
| Autocompact buffer | ~33K | ~33K | Reserved by system |
| Path-specific rules | ~6-23K | ~6-23K | Varies by domains touched |
| Safety margin | ~13K | ~13K | Errors, iteration, conversation growth |
| **Total fixed overhead** | **~100K** | **~100K** | Constant across tiers |
| **Available for work** | **~100K** | **~900K** | Window − overhead |
| Practical session limit | ~100K | ~400K | Soft target — above this, recovery + review get harder even if it fits |
| Meta-Plan threshold | > 100K | > 500K | `min(80% × available, 500K)` |
| Subagent context window | 200K | 1M | Subagents inherit the parent session's tier |
| DELEGATED check (per subagent) | `task + 54K < 200K` | `task + 54K < 1,000K` | Use `context_window` from config |

The Max practical session limit (400K) is intentionally below the available budget (900K). Sessions beyond ~400K become harder to review, recover, and reason about even when they technically fit — Meta-Plan is preferred for sustained work above this point.

### Threshold Formulas

When authoring or reviewing a plan, compute thresholds from `context_window`:

```
fixed_overhead          = 100_000            # constant across tiers
available_for_work      = context_window - fixed_overhead

# Meta-Plan threshold — work that does not fit in one session
meta_plan_threshold     = min(0.80 * available_for_work, 500_000)

# Practical session limit — soft target for one session's working set
practical_session_limit = min(available_for_work, 400_000)  # cap at 400K on Max

# DELEGATED check — per-subagent budget
delegated_cap           = context_window
```

| Variable | Pro (200K) | Max (1M) |
|----------|-----------|----------|
| `fixed_overhead` | 100,000 | 100,000 |
| `available_for_work` | 100,000 | 900,000 |
| `meta_plan_threshold` | 100,000 | 500,000 |
| `practical_session_limit` | 100,000 | 400,000 |
| `delegated_cap` | 200,000 | 1,000,000 |

Handlers that branch on a hardcoded number (e.g., "if total > 100K → Meta-Plan") MUST instead read the relevant variable from this table.

### Session Limits

**Available for work** scales by tier — see the Tier-Specific Budget Table above. On Pro (the backward-compatible default), available for work is ~100K. On Max, it's ~900K with a soft practical session limit of ~400K.

### Context Accumulation Patterns

The thresholds below are expressed for the Pro tier (the backward-compatible default). On Max, multiply each by `available_for_work / 100_000` and cap "Too Large" at `meta_plan_threshold` (see the Threshold Formulas table — on Max that cap is 500K, not 9×).

| Pattern | Initial Load (Pro) | Growth During Work | Total (Pro) | Guideline |
|---------|--------------------|-------------------|-------------|-----------|
| Discovery | < 30K | +40-50K | ~70-80K | Don't know all files upfront; discover as you work |
| Planned | 30-70K | +10-20K | ~80-90K | Know most files upfront; few discoveries during work |
| Front-loaded | 70-90K | +5-10K | ~95-100K | Know all files upfront; load everything before starting |
| **Too Large** | > `meta_plan_threshold` | - | - | **MUST use Meta-Plan** (delegate to agents with fresh context) |

**Key insight:** The problem isn't initial load — it's unplanned accumulation during execution. The tier sets the ceiling; the pattern names are tier-relative.

### Session Sizing Principle

**Quality over short sessions.** Each session gets its own orchestrator with a fresh `available_for_work` budget (~100K on Pro, ~900K on Max — but practically capped at ~400K on Max). If a sprint's tasks don't fit comfortably in one session, split into 2, 3, or 4 sessions — each with its own Orchestration and Recovery files. Never cram tasks into fewer sessions at the cost of execution quality.

> [!constraint] Session Sizing — Split Rather Than Cram
> The token figures below assume the Pro tier (`practical_session_limit = 100K`). On Max, substitute the tier's `practical_session_limit` (~400K) — the split-vs-cram principle is identical; the absolute thresholds scale.
>
> WRONG — all tasks crammed into one session regardless of token cost; no Orchestration/Recovery for the overflowed work:
> ```
> PI-S02-Sprint-Plan.md
>   Session-01-AllWork/
>     PI-S02-01-Orchestration.md      ← 8 tasks totaling ~140K tokens
>     PI-S02-01-Recovery.md
>     PI-S02-01-01-Haiku-ScanFiles.md
>     PI-S02-01-02-Haiku-CountRows.md
>     PI-S02-01-03-Sonnet-GenEntities.md
>     PI-S02-01-04-Sonnet-GenControllers.md
>     PI-S02-01-05-Sonnet-GenViews.md
>     PI-S02-01-06-Opus-ReviewDesign.md
>     PI-S02-01-07-Sonnet-GenMigration.md
>     PI-S02-01-08-Sonnet-GenSeeding.md
> ```
> CORRECT — sprint split into sessions that each fit within 100K budget; each has its own Orchestration and Recovery:
> ```
> PI-S02-Sprint-Plan.md
>   Session-01-ScanAndModel/           ← ~45K tokens
>     PI-S02-01-Orchestration.md
>     PI-S02-01-Recovery.md
>     PI-S02-01-01-Haiku-ScanFiles.md
>     PI-S02-01-02-Haiku-CountRows.md
>     PI-S02-01-03-Sonnet-GenEntities.md
>   Session-02-ControllersAndViews/    ← ~60K tokens
>     PI-S02-02-Orchestration.md
>     PI-S02-02-Recovery.md
>     PI-S02-02-01-Sonnet-GenControllers.md
>     PI-S02-02-02-Sonnet-GenViews.md
>     PI-S02-02-03-Opus-ReviewDesign.md
>   Session-03-DataLayer/              ← ~40K tokens
>     PI-S02-03-Orchestration.md
>     PI-S02-03-Recovery.md
>     PI-S02-03-01-Sonnet-GenMigration.md
>     PI-S02-03-02-Sonnet-GenSeeding.md
> ```

### Reading Discipline (BINDING)

> [!constraint] Read Files Fully
> | Behavior | Result |
> |----------|--------|
> | ✅ Read file completely before using | Accurate context, correct decisions |
> | ❌ Skim or read partial lines | Context confusion, failures, hallucinations |
> | ❌ Infer file contents without reading | Wrong assumptions, rework required |
>
> The accumulation patterns above describe HOW MANY files you'll load and WHEN — not how thoroughly you read them. All files are read fully. Always.

### Budget Allocation

The overhead is identical on both tiers; only the working budget changes. Read `context.context_window` from `config.yaml` and subtract fixed overhead:

```
Context Budget ({context_window} total)
├── System prompt             ~4K (fixed)
├── System tools              ~22K (fixed)
├── Autocompact buffer        ~33K (reserved by system)
├── Global rules + CLAUDE.md  ~27K (always loaded)
├── Skills + agents (desc.)   ~1K (always loaded)
├── Path-specific rules       ~6-23K (varies by domains touched)
├── Safety margin             ~13K (errors, iteration, conversation growth)
└── Available for work        ~{context_window − 100K} max
    Total fixed overhead:     ~54K subagent overhead + ~33K autocompact + ~13K safety
                              = ~100K (empirical, from /context on fresh session)
```

Pro (200K): available_for_work ≈ 100K. Max (1M): available_for_work ≈ 900K (with a 400K practical session cap — see the tier-specific budget table).

### Domain Rule Costs

Path-specific rules load based on files you're working with:

Run `/context` to measure your project's domain rule costs. Add rows with your project's file patterns and costs.

| Domain | Files Matching | Additional Rules |
|--------|----------------|------------------|
| *(your domain)* | *(your file pattern)* | *(measured cost)* |

**Estimate before starting:** Global (check with /context) + Domain rules + Work files + Growth = Total

### Task-Level Estimation (BINDING)

Task token estimates MUST be computed bottom-up from measured or estimated file sizes, not just matched to qualitative categories (Small/Medium/Large). The `/planwise plan` handler's Step 8c enforces this.

**Conversion factor:** ~13 tokens/line (midpoint for mixed code/prose content).

**Formula:** `Task Estimate = (sum of Required Context file tokens) + (estimated output tokens)`
**DELEGATED check:** `Task Estimate + 54K overhead < context_window per subagent` (subagents inherit the parent tier; read `context.context_window` from `config.yaml` — defaults to 200,000)

For detailed per-operation costs, see the [Token Estimation Reference](reference.md#token-estimation-reference) in the planwise plugin.

### Token Estimate Reconciliation (BINDING)

Token estimates appear at three levels. They MUST reconcile arithmetically:

```
Task context subtotal  ──must equal──►  Task header Estimated Tokens
     ↓ (sum of all tasks)
Orchestration Total Estimated  ──must equal──►  Sprint Plan Sessions table Est. Tokens
     ↓ (sum of all sessions)
Sprint Plan header Estimated Tokens
```

| Check | Formula | When to Verify |
|-------|---------|----------------|
| Task internal | Context subtotal = Task header `Estimated Tokens` | After writing each task file |
| Session total | Sum of task `Est. Tokens` = Orchestration `Total Estimated` | After writing orchestration |
| Sprint total | Sum of session `Est. Tokens` = Sprint Plan header `Estimated Tokens` | After writing sprint plan |

**Enforcement:** The `/planwise plan` handler's Step 8c computes estimates bottom-up. The `/planwise review` handler checks reconciliation as part of structural review. Template comments in orchestration, sprint plan, and task file templates remind the planner to verify.

### Context Accumulation Formula

> [!gate] Context Budget Gate
> ```
> Total Context = Fixed Overhead (54K) + Autocompact (33K)
>               + Domain Rules (6-23K) + Files Loaded + Conversation Growth
>
> Available for work ≈ context_window − 100K (from config.yaml; default 200K → 100K)
>
> If (Files to Load + Expected Growth) > meta_plan_threshold → Use Meta-Plan
>   Pro tier: meta_plan_threshold = 100K
>   Max tier: meta_plan_threshold = 500K
> ```

### File Size Limits

**Soft limit: 500 lines per file.** When creating or modifying files:
- Task files, plans, and documentation SHOULD stay under 500 lines
- Files exceeding 500 lines MUST be split into multiple focused parts
- Exception: Generated code files may exceed if logically cohesive

**Multi-Part Output Convention:**

Any artifact (task output, specification, consolidated context) may span multiple files:

```
{Abbrev}-{ArtifactName}-Part-1-{Topic}.md
{Abbrev}-{ArtifactName}-Part-2-{Topic}.md
{Abbrev}-{ArtifactName}-Part-3-{Topic}.md
```

Each part MUST:
- Stay under 500 lines
- Have a descriptive topic suffix
- Be self-contained enough to feed a downstream task independently
- Cross-reference other parts where needed

**Not limited to one file.** Tasks produce full-detail outputs. If a task needs 3 files of 400 lines each to capture the full specification, that is correct — do NOT compress into one 500-line file.

---

## 6. Context Loading Strategy

> [!decide] Context Loading Decision
> Compare total context to the tier's `meta_plan_threshold` (from the Threshold Formulas table — 100K on Pro, 500K on Max):
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

**Key insight:** Subagents don't inherit your context accumulation. Each gets a fresh `available_for_work` budget at the parent's tier (~100K on Pro, ~900K on Max). Use this to your advantage.

### When to Use Meta-Plan

> [!decide] Standard vs Meta-Plan
> | Condition | Action |
> |-----------|--------|
> | Total context needed < `meta_plan_threshold` | Proceed with standard plan |
> | Total context needed > `meta_plan_threshold` | **Use Meta-Plan** (3-phase: Discovery → Scaffolding → Execution) |
> | Multiple complex source documents need cross-referencing | **Use Meta-Plan** |
> | Work spans multiple sessions and context must be preserved | **Use Meta-Plan** |
>
> `meta_plan_threshold` = 100K on Pro, 500K on Max — see §5 Threshold Formulas.

### Meta-Plan Purpose

1. **Fresh context per agent** - Each subagent gets its own `available_for_work` budget at the parent's tier
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

*Companion files: [session-planning-protocol.md](session-planning-protocol.md), [session-plan-requirements.md](session-plan-requirements.md)*
