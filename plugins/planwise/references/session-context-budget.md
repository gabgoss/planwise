---
description: Token budget management, and the read-gate canonical — Read-Tool Hard Limits, reading discipline, and Large-File Read Tactics — for session planning
---

# Session Context Budget

**Purpose:** Token budget management and the read-gate canonical (Read-Tool Hard Limits, reading discipline, Large-File Read Tactics) for planning sessions.
**Companion files:** [session-planning-protocol.md](session-planning-protocol.md) (protocol, hierarchy, delegation), [session-plan-requirements.md](session-plan-requirements.md) (file specifications, task templates), [token-saver-profile.md](token-saver-profile.md) (carrying-cost budget when Token Saver is on), [context-loading-and-conservation.md](context-loading-and-conservation.md) (Meta-Plan decision, conservation tactics)

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
| Subagent window (by model) | Sonnet/Haiku → 200K | Opus → 1M | **Set by the DISPATCHED model, NOT the parent tier.** See [§ Subagent Context Window](#subagent-context-window). |
| DELEGATED check (per subagent) | `task + rules + 54K < 200K` (Sonnet/Haiku) | `task + rules + 54K < 1M` (Opus) | Check the **dispatched model's** window — not the parent `context_window`. |

The Max practical session limit (400K) is intentionally below the available budget (900K). Sessions beyond ~400K become harder to review, recover, and reason about even when they technically fit — Meta-Plan is preferred for sustained work above this point.

### Subagent Context Window

> [!constraint] A subagent's window is the DISPATCHED MODEL's window — NOT the parent tier
> A spawned subagent (e.g., a DELEGATED `task-runner`) gets a fresh context window sized by **the model it runs on**, independent of the orchestrator's account tier:
>
> | Dispatched model | Window |
> |------------------|--------|
> | Haiku | 200K |
> | Sonnet | 200K |
> | Opus | 1M |
>
> A Sonnet runner has a **200K** window even when the orchestrator is on Max (1M) — the parent's tier does NOT raise the child's window. The per-subagent DELEGATED budget check is therefore:
>
> ```
> task estimate + injected path-rule tokens + ~54K overhead  <  the DISPATCHED MODEL's window
> ```
>
> NOT the parent `context_window`. When a project's plan-path rule surface is large enough to overflow a 200K-window model on its first plan-brief read, either raise the dispatch to a 1M-window model (see [`handlers/run.md`](../handlers/run.md) Model-Floor Bridge) or shrink the surface (`/planwise doctor`).

### Threshold Formulas

When authoring or reviewing a plan, compute thresholds from `context_window`:

```
fixed_overhead          = 100_000            # constant across tiers — TIER-SIZING domain only
                                             #   (see "Two Overhead Constants, Two Domains" below)
available_for_work      = context_window - fixed_overhead

# Meta-Plan threshold — work that does not fit in one session
meta_plan_threshold     = min(0.80 * available_for_work, 500_000)

# Practical session limit — soft target for one session's working set
practical_session_limit = min(available_for_work, 400_000)  # cap at 400K on Max

# DELEGATED check — per-subagent budget (see § Subagent Context Window)
# subagent_model_window = window of the model the DELEGATED task is dispatched to:
#   Opus 1,000,000; Sonnet 200,000; Haiku 200,000 — NOT the parent context_window
delegated_cap           = subagent_model_window
```

| Variable | Pro (200K) | Max (1M) |
|----------|-----------|----------|
| `fixed_overhead` | 100,000 | 100,000 |
| `available_for_work` | 100,000 | 900,000 |
| `meta_plan_threshold` | 100,000 | 500,000 |
| `practical_session_limit` | 100,000 | 400,000 |

`delegated_cap` is **independent of the parent tier** — it is the window of the model the DELEGATED task is dispatched to (see [§ Subagent Context Window](#subagent-context-window)):

| Variable | Opus | Sonnet | Haiku |
|----------|------|--------|-------|
| `delegated_cap` (= `subagent_model_window`) | 1,000,000 | 200,000 | 200,000 |

> **Note (threshold precedence):** Where the formula above and these per-tier tables disagree, the **tables are canonical**. On Pro the formula's `0.80 × available_for_work` yields 80K, but the Tier-Specific Budget Table and the per-tier table above both set `meta_plan_threshold = 100K` on Pro (500K on Max) — use the table value. The formula is a derivation aid for non-standard tiers; the tables are the binding decision boundary. `handlers/plan.md` branches on 100K/500K, matching the tables.

Handlers that branch on a hardcoded number (e.g., "if total > 100K → Meta-Plan") MUST instead read the relevant variable from this table.

> [!constraint] Two Overhead Constants, Two Domains — Scoped, Never Summed
> This file's `fixed_overhead` and Token Saver's calibrated per-actor overheads are **two quantities in two models**, not two measurements of one quantity. Each is operative in its own domain:
>
> | Constant | Operative domain | Drives | Source |
> |----------|------------------|--------|--------|
> | `fixed_overhead` = 100,000 | **Tier / Meta-Plan sizing boundary** | `available_for_work`, `meta_plan_threshold`, `practical_session_limit` — the per-tier tables above, which `handlers/plan.md` branches on | Documented constant, this file |
> | `token_saver_runner_overhead`, `token_saver_orchestrator_overhead` | **Token-Saver per-actor budgets** | `available_per_task`, `critical`, `warn` (the engine's `derive_thresholds`) | Measured per install by `/planwise calibrate`; see [token-saver-profile.md](token-saver-profile.md) |
>
> **Never sum them.** Their category breakdowns overlap — the system prompt and the system tools are counted inside both — so adding them double-counts that shared block. They also disagree in magnitude (a measured per-actor overhead runs well below 100,000), and that disagreement is expected rather than an error to reconcile: one bounds a whole session against a tier window, the other bounds a single actor's working set.
>
> **Outside its own domain, each constant is non-operative.** `fixed_overhead` never enters a Token-Saver per-actor budget, and a calibrated per-actor overhead never enters `available_for_work` / `meta_plan_threshold` / `practical_session_limit`. Neither replaces the other; deleting either would break a live consumer.
>
> **Which figure a formula uses.** Formulas in *this* file consume the tier model: `available_for_work = context_window − fixed_overhead`, and the `~54K` that appears in the Tier-Specific Budget Table, the DELEGATED checks, and the Context Budget Gate is the **always-loaded static component of that same 100,000** — not the calibrated per-actor constant. Formulas in [token-saver-profile.md](token-saver-profile.md) consume the calibrated constants by name. Token Saver's *uncalibrated fallback* starts near that same ~54K figure by construction; once `/planwise calibrate` has run, the Token-Saver formulas use the **measured** value while this file's tier tables keep their documented ones.

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

Task token estimates MUST be computed bottom-up from measured file sizes, not just matched to qualitative categories (Small/Medium/Large). The `/planwise plan` handler's Step 8c enforces this.

**Measurement:** run `measure_files.py` over every Required Context file — tokens = bytes ÷ the assigned model's bytes-per-token ratio (see [Read-Tool Hard Limits](#read-tool-hard-limits)). For a file that does not exist yet, estimate its byte size and divide: ≈ bytes ÷ 3.0 for prose/code, ÷ 2.6 for dense markdown (tables, link-heavy rows). Never derive a token figure from a line count.

**Formula:** `Task Estimate = (sum of Required Context file tokens) + (estimated output tokens)`
**DELEGATED check:** `Task Estimate + injected path-rule tokens + 54K overhead < the dispatched model's window` (Sonnet/Haiku 200K, Opus 1M — the window is set by the dispatched MODEL, NOT the parent tier; see [§ Subagent Context Window](#subagent-context-window))

### Task Sizing Categories

The task-size thresholds below are expressed for the Pro tier. On Max, scale by the same ratio used for session limits — a "Too Large" task on Pro is ~80% of `practical_session_limit`. The "always split a task above 80% of one session" principle is tier-invariant.

| Task Size | Token Estimate (Pro) | Guideline |
|-----------|---------------------|-----------|
| Small | < 20K | Single file, simple lookup |
| Medium | 20-50K | Multi-file, code generation |
| Large | 50-80K | Complex analysis, multiple entities |
| Too Large | > 80K (Pro) / > 320K (Max practical) | **MUST SPLIT** |

**These categories are a cross-check, not the primary estimate.** Always compute the bottom-up estimate first, then compare against the category. Use the HIGHER of the two.

### Per-Operation Cost Reference

Use these tables to compute bottom-up token estimates for each task.

**File Read Costs:**

| Operation | Approx. Tokens | Heuristic |
|-----------|----------------|-----------|
| Read file | bytes ÷ 2.6–3.3 | Measure with `measure_files.py`; ratio set by reading model + content class |
| Read 5 KiB file | ~2K | Small config, helper |
| Read 15 KiB file | ~5-6K | Medium file |
| Read 30 KiB file | ~10-12K | Large reference doc or entity |
| Read 60 KiB file | ~20-23K | At/near the 22K token warn — page it or split it |

**Output Generation Costs:**

| Operation | Approx. Tokens | Scaling Factor |
|-----------|----------------|----------------|
| Generate C# entity | ~3-5K per entity | Scale by property count |
| Generate controller | ~5-8K | Scale by action count |
| Generate Razor view | ~3-6K | Scale by complexity |
| Generate migration | ~2-4K | Scale by entity count |
| Error analysis + fix | ~5-10K | Includes iteration |
| Complex decision (Opus) | ~10-20K | Architecture/trade-offs |

**Overhead Costs (DELEGATED mode):** see the [Tier-Specific Budget Table](#tier-specific-budget-table) above (System prompt ~4K, System tools ~22K, Global rules + CLAUDE.md ~27K, Skills + agents ~1K — ~54K subagent overhead total).

### Per-Invocation Structural Floor

Every subcommand invocation carries a block of instruction text that a runtime `/context` snapshot **structurally cannot observe**: the skill body, the base-context references pre-injected with the skill, the handler body, and the always-load references. Calibration measures the static categories a *fresh* session reports; this block arrives as transcript content during the invocation, landing in `messages` rather than in any static category. It is therefore invisible to calibration by construction, and must be accounted for separately when budgeting a session that will issue subcommands.

Figures are labelled by the tree they were measured on — **dev** (the tree the plugin is developed in) or **installed** (the tree a consumer has on disk). The two differ in line counts, so a figure from one tree is not comparable to a figure from the other.

> [!note] Historical measurement basis
> The tables below were measured under the superseded per-line token model ("At 13 tok/line" columns). They are kept as the historical record of those probes; a fresh floor measurement should use `measure_files.py` (bytes ÷ bytes-per-token) instead of any per-line rate.

**Whole-path floor** — skill body + base context + handler body + always-load references:

| Tree | Lines | At 13 tok/line | At the measured 15.42–15.91 tok/line rate |
|------|-------|----------------|-------------------------------------------|
| dev | 2,193 | 28,509 | ≈34.2K |
| installed | 2,479 | 32,227 | ≈38.7K |

**Per-subcommand floors** (installed tree; **skill body EXCLUDED** — handler body + base context + always-load references only):

| Subcommand | Lines | At 13 tok/line |
|------------|-------|----------------|
| `plan` | 4,329 | ~56.3K |
| `review` | 2,953 | ~38.4K |
| `run` | 2,386 | ~31.0K |
| `backlog` | 1,901 | ~24.7K |

> [!constraint] The two tables cover DIFFERENT components — never compare a row across them
> The whole-path floor **includes** the skill body; the per-subcommand rows **exclude** it. So one subcommand legitimately carries three different numbers: `run` appears as **2,193** (dev, whole path), **2,386** (installed, skill body excluded), and **2,479** (installed, whole path). The `2,479 − 2,386 = 93`-line gap is exactly the installed skill body — a component boundary, not a disagreement between measurements. A floor figure quoted without both its tree and its component set is unusable; always carry both labels.

> [!constraint] This is an upper bound on what the instruction text MANDATES — not a measurement of what loads
> The line counts above say what the shipped text *instructs* an invocation to read. Whether every mandated read actually issues is a separate, empirical question, and predictions have missed in both directions: on one minimal handler the predicted floor over-shot the measured cost ~2.9×, while a heavier handler over-shot in the opposite direction.
>
> **Current verdict, from the most recent probe:** `mandated-loads-issue (measured +32,692 tok [dev tree] ≥ predicted floor 15,873 tok [dev tree]; measured is ~2.06× the prediction)` — the mandated base-context reads DO issue. (That probe predicted the floor for a *light* subcommand — 1,221 lines of skill + base context + handler body — so its 15,873 is not the whole-path figure in the table above; the comparison that matters is measured-vs-predicted *within one invocation*.)
>
> **Caveat, carried from the probe:** the excess above the floor is confounded with that subcommand's own live runtime work — real project-file reads plus a reconciliation script — so the measurement confirms compliance but cannot cleanly isolate the static floor from handler-specific runtime cost. Treat these figures as a planning upper bound on mandated text, not as a per-invocation cost prediction, and do not store one as a calibrated budget input.

**Future work, gated on the compliance answer above:** conditional loading of references a given subcommand cannot reach — an estimated 10–20K per invocation, unvalidated. It would have to be a per-reference reachability pass, never a blanket change: the failure mode is a handler silently losing a convention it depended on. Not landed.

### Agent Assignment

| Task Type | Agent | Examples |
|-----------|-------|----------|
| Lookups, validation | **Haiku** | Counts, find files, verify |
| Code generation | **Sonnet** | Entities, controllers, views |
| Architecture/decisions | **Opus** | Design, trade-offs, analysis |

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

#### Reviewer Check 024 — Task Token-Estimate Arithmetic Gate

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task header `Estimated Tokens` = Required Context subtotal + output tokens. No `~?` placeholders. Deviation ≤10%.
- **Detection:** Extract header value + subtotal line. `abs(header - subtotal) / header > 0.10` → BLOCKER. Any `~?` → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task token-estimate arithmetic gate failed
File: {task file path} | Location: Header Estimated Tokens vs Required Context subtotal
Issue: Header "{header_value}" deviates {deviation_pct}% from subtotal "{subtotal_value}"
Fix: Reconcile per references/session-context-budget.md Token Estimate Reconciliation | Confidence: HIGH
```

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

**No line limit.** File size is governed by the Read tool's mechanical gates, and those are **measured, never estimated from line counts**. Before assigning a file to a reader — and after generating any artifact a runner must read — measure it:

```bash
python "{plugin_root}/scripts/measure_files.py" {file} [{file} ...] [--model {reading model}] [--md]
```

Three criteria, in priority order — **whichever comes first binds**:

1. **Tokens (primary):** stay under **22,000** (`READ_TOKEN_WARN`) at the reading model's bytes-per-token ratio; the hard page-cap is 25,000 (`READ_PAGE_CAP_TOKENS`). On text this gate binds first — roughly 3.6× before the byte gate.
2. **Bytes:** stay under **245,760** (240 KiB, `READ_BYTE_WARN`); the hard refusal cap is 262,144 (256 KiB, `READ_FILE_BYTE_CAP`).
3. **Lines (distant third, defensive):** stay under **2,000** (`READ_LINE_CAP`) — the first-page line window. It binds alone only on many-short-line files that pass gates 1–2.

The binding targets are the **WARN thresholds**, deliberately below the hard caps, so a compliant file never even triggers a warning. When the reading model is unknown, use the most-restrictive ratio (2.6 bytes/token).

**Multi-Part Output Convention:**

Any artifact (task output, specification, consolidated context) may span multiple files:

```
{Abbrev}-{ArtifactName}-Part-1-{Topic}.md
{Abbrev}-{ArtifactName}-Part-2-{Topic}.md
{Abbrev}-{ArtifactName}-Part-3-{Topic}.md
```

Each part MUST:
- Land OK on all three gates above (measure with `measure_files.py`)
- Have a descriptive topic suffix
- Be self-contained enough to feed a downstream task independently
- Cross-reference other parts where needed

**Not limited to one file.** Tasks produce full-detail outputs. If a task needs 3 files to capture the full specification, that is correct — do NOT compress detail away to dodge a split.

### File Size Limits — Generated Artifacts (BINDING)

**Generated planwise artifacts that a runner MUST read** — task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, and task Output files — carry a **HARD** ceiling regardless of `context.token_saver`: each MUST land **OK on all three Read-tool gates** (see [Read-Tool Hard Limits](#read-tool-hard-limits) below) for the model that will read it. A generated artifact that trips any gate cannot be read cleanly in a single Read and MUST be split into multi-parts. (The gates are harness facts, not a carrying-cost policy — Token Saver's config-gated budget system is separate.)

> [!constraint] Generated-Artifact Split — Measured, Not Line-Counted
> WRONG — a planwise-generated Consolidated Context part is judged by its line count alone; at 9,200 bytes-per-100-lines of dense tables the file is ~44K tokens, and a runner's single Read returns only the first ~21K tokens of it:
> ```
> wc -l PI-Consolidated-Context-Part-1.md   # 480 → "small file, fine"  ← INSUFFICIENT: lines do not predict the gate
> ```
> CORRECT — measure all three gates at once; split on whichever trips first:
> ```
> python "{plugin_root}/scripts/measure_files.py" PI-Consolidated-Context-Part-1.md --model sonnet
> #   tokens (primary): must stay < 22,000 (warn) / 25,000 (hard cap)
> #   bytes:            must stay < 245,760 (warn) / 262,144 (hard cap)
> #   lines:            must stay < 2,000 (defensive first-page window)
> # → split into Part-1a / Part-1b if ANY gate reports WARN or OVER
> ```

The trigger is **token OR byte OR line — in that priority order, whichever fires first**. External source/context files a runner reads but does NOT generate (codebase modules, third-party docs) keep the advisory treatment: warn, apply the [Large-File Read Tactics](#large-file-read-tactics) ladder, and file a refactor backlog item — they are not hard-split because the runner does not own them.

---

## Read Gates and Large-File Read Tactics

The read-gate canonical: the Read tool's fixed mechanical limits, the discipline for respecting them, and the tactics for a file that exceeds one. These constants and rules apply regardless of `context.token_saver` — they are harness facts, not a carrying-cost policy (the config-gated Token Saver budget system lives in [token-saver-profile.md](token-saver-profile.md)).

### Read-Tool Hard Limits

The Read tool has three mechanical limits, SEPARATE from the carrying-cost budget — a file can fit the session budget yet be unreadable in one Read. These constants are **FIXED harness facts** (empirically re-measured 2026-08-26 across four models; re-validate via headless `claude -p --model X`), defined as module-level constants in `scripts/read_limits.py` (re-exported by `scripts/token_saver.py`) — they are **NOT** `/context`-measured and are **NOT** written by `calibrate()`. Measure any file against them with `scripts/measure_files.py`.

Gate priority: **tokens first, then bytes, then lines — whichever comes first.** The caps and warn thresholds are identical on every model; only the tokenizer weight (bytes-per-token) differs.

| Model family | Token cap (hard) | Token warn | Byte cap (hard) | Byte warn | Line gate | Bytes-per-token (measured) |
|---|---|---|---|---|---|---|
| Haiku | 25,000 | 22,000 | 262,144 (256 KiB) | 245,760 (240 KiB) | 2,000 (defensive) | prose ~4.7 |
| Sonnet | 25,000 | 22,000 | 262,144 | 245,760 | 2,000 (defensive) | ~3.7–4.7 (derived from the family ratio; worst measured case — synthetic filler — 2.15) |
| Opus | 25,000 | 22,000 | 262,144 | 245,760 | 2,000 (defensive) | dense markdown 2.6 · prose 3.0 · docs+code 3.3 |
| Fable | 25,000 | 22,000 | 262,144 | 245,760 | 2,000 (defensive) | tokenizer identical to Opus (same file → same token count): dense markdown 2.6 · prose 3.0 |

- **Token page-cap gate (PRIMARY; model-dependent ratio):** a file above **~25,000 tokens** (`READ_PAGE_CAP_TOKENS`) does not return whole. Without an explicit `limit`, the Read soft-truncates to a first page of **~21,200 tokens (~85% of the cap)** plus a `PARTIAL view` banner reporting the file's exact total; with an explicit `limit` spanning more than the cap it **hard-errors with zero content** (the error still reports the exact token count — a zero-cost measurement oracle). Warn at **~22,000 tokens** (`READ_TOKEN_WARN`) — the warn threshold produces **no runtime marker**, so it MUST be checked proactively (`measure_files.py`), never waited for.
- **Byte gate (model-independent):** a file ≥ **262,144 bytes (256 KiB)** (`READ_FILE_BYTE_CAP`) is refused outright unless `offset`/`limit` is passed — no partial page, no pointer. Warn at **245,760 bytes (240 KiB)** (`READ_BYTE_WARN`).
- **Line gate (DISTANT THIRD, defensive):** **2,000 lines** (`READ_LINE_CAP`) — the first-page line window; a per-model total-read ceiling of roughly 10–20 pages is reported but UNCONFIRMED (measured sessions returned 3,000+-line single pages). Treat < 2,000 lines as the defensive target for generated artifacts; it binds alone only on many-short-line files that pass the token and byte gates.

**Estimating tokens:** `tokens ≈ bytes ÷ bytes-per-token` for the READING model, gate-conservative — unknown reader or content class → **2.6 B/tok** (the densest measured content on the heaviest tokenizer). Line-based token rates are unreliable and MUST NOT be used: measured per-line rates ranged 7–365 tokens/line depending on content; bytes predict the gate, lines do not.

These FOLD into the per-file warning ladder. `token_saver.classify_file()` computes `level = max(cost_level, read_level)` and tags `reason = cost | read` naming whichever gate drove the level:

> [!constraint] A `read`-reason Critical Is NOT 1M-Exception-Resolvable
> WRONG — a runner hits a `read`-reason Critical and escalates the dispatch to Opus (1M window) expecting the larger window to absorb it:
> ```
> classify_file(...) → {level: Critical, reason: read}   → "route to Opus, the 1M window fixes it"  ← FALSE
> ```
> CORRECT — routing to Opus does NOT raise the per-Read page cap, and the Opus/Fable-family tokenizer trips the token gate on FEWER bytes (~65 KB of dense markdown vs ~92 KB for the Sonnet/Haiku family). The remedy is **paged reads** (`offset`/`limit`/Grep), and for a core or to-be-edited dependency, **refactor + backlog**:
> ```
> classify_file(...) → {level: Critical, reason: read}
>   → page it: Read(offset/limit) or Grep the needed section
>   → if it is a core/edited dependency: split/refactor the file + file a backlog item
> ```
> A `cost`-reason Critical is a budget overflow (split the task / trim Required Context). A `read`-reason Critical is a mechanical Read failure (page it / refactor). The 1M exception addresses neither.

### Reading Discipline With Read Gates (BINDING)

The [Read Files Fully](#reading-discipline-binding) rule still holds — read all relevant content, never skim or infer. This section adds one refinement: when a single Read **cannot** deliver a whole file (above the token page-cap, ≥ 256 KiB, or past the line window), reading "fully" means **paging** it, not trusting one Read returned everything.

> [!constraint] Page Large Files — Do Not Trust One Read
> WRONG — runner issues one Read on a ~70 KB dense file, gets the first page back, and proceeds as if it read the whole file:
> ```
> Read(path)   → returns only the first ~21,200 tokens (~85% of the 25K cap) silently truncated → runner acts on partial context
> ```
> CORRECT — when a file exceeds a gate, page it with `offset`/`limit` (or Grep the needed sections) AND check the returned content for the `PARTIAL view` truncation header before assuming completeness:
> ```
> Read(path, offset=1, limit=900) → check for "PARTIAL view" header
> Read(path, offset=901, limit=900) → … continue until the whole file is covered
> # or: Grep(pattern, path, output_mode: "content", context: 30) for a known section
> ```
> "Read fully" is satisfied by paged reads that together cover the file — NOT by one Read that silently returned only the first page. Size each page so its window stays under the cap: an explicit `limit` whose window spans MORE than ~25K tokens does not clamp — it hard-errors with zero content (budget ~21K tokens per page; the truncation banner's `offset`/`limit` hint is a safe next-page size).

### Large-File Read Tactics

> [!practice] Ladder for Files Exceeding a Read-Tool Gate
> The Read tool has three mechanical gates — tokens, bytes, lines; see [Read-Tool Hard Limits](#read-tool-hard-limits) above (NOT a single line-count budget). When a file crosses any gate, apply this ladder in order — stop at the first step that succeeds. A `read`-reason Critical is NOT resolvable by routing to a 1M-window model (see the constraint above).

**Step 1 — Paged Read (`offset`/`limit`):** Read the file in pages that each stay under the gate, then stitch them — see [Page Large Files — Do Not Trust One Read](#reading-discipline-with-read-gates-binding) above for the WRONG/CORRECT pattern and the `PARTIAL view` truncation-header check.

**Step 2 — Output-clear pre-step:** Clear conversation output buffer before reading. Freed budget enables a larger Read call. Effective when the conversation history is large but the file itself is borderline.

**Step 3 — Substitution:** Read a smaller substitute:
- Adjacent `*.md` documentation next to the `{src/module/file.ext}` source file
- A smaller version-compatible equivalent (e.g., a config file that describes the large source file's structure)

**Step 4 — Grep-based scanning:** Use Grep with `output_mode: "content"` and context lines to extract the needed sections without a full Read. Effective when you know which section or function you need.

```bash
# Example: extract a specific function from a large file
Grep(pattern: "def {symbol}", path: "{src/module/file.ext}", output_mode: "content", context: 30)
```

**Step 5 — Script-based extraction:** For structured files (JSON/YAML), use a Bash command via `jq`/`yq` to project only relevant fields:

```bash
# Example: extract a specific key from a large YAML config
Bash("yq '.{config-field}' {src/module/file.ext}")
```

#### Module Split Threshold (cross-reference)

For adapter/client modules whose row dataclass exceeds 75-80 fields, see the Module Split Threshold subsection in `references/task-file-and-tracking-requirements.md`. Large-file read tactics are orthogonal to the module split decision — apply both when applicable.

---

*Companion files: [session-planning-protocol.md](session-planning-protocol.md), [session-plan-requirements.md](session-plan-requirements.md), [token-saver-profile.md](token-saver-profile.md), [context-loading-and-conservation.md](context-loading-and-conservation.md)*
