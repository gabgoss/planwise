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
fixed_overhead          = 100_000            # constant across tiers
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
**DELEGATED check:** `Task Estimate + injected path-rule tokens + 54K overhead < the dispatched model's window` (Sonnet/Haiku 200K, Opus 1M — the window is set by the dispatched MODEL, NOT the parent tier; see [§ Subagent Context Window](#subagent-context-window))

For detailed per-operation costs, see the [Token Estimation Reference](../handlers/plan.md#token-estimation-reference) in the planwise plugin.

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

### File Size Limits — Generated Artifacts (BINDING when Token Saver is on)

The 500-line soft limit above is advisory. When `context.token_saver: true`, **generated planwise artifacts that a runner MUST read** — task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, and task Output files — carry a **HARD** ceiling: each MUST stay under **both** Read-tool gates (see [Read-Tool Hard Limits](#read-tool-hard-limits) below), not just the line limit. A generated artifact that trips either gate cannot be read in a single Read and MUST be split into multi-parts.

> [!constraint] Generated-Artifact Split — Hard, Not Advisory
> WRONG — a planwise-generated Consolidated Context part is checked against the line limit alone, passes at 480 lines, but is 9,200 bytes-per-100-lines of dense tables → exceeds the 256 KiB byte gate / 25K-token page-cap and a Sonnet runner can only read its first page:
> ```
> wc -l RSO-Consolidated-Context-Part-1.md   # 480 → "under 500, fine"  ← INSUFFICIENT
> ```
> CORRECT — check the line gate, the byte gate, AND the token gate; split on whichever trips first:
> ```
> wc -l RSO-Consolidated-Context-Part-1.md   # line gate
> wc -c RSO-Consolidated-Context-Part-1.md   # byte gate: must stay < 245,760 (warn) / 262,144 (hard)
> # token gate: lines × per-model rate must stay < 22,000 (warn) / 25,000 (hard)
> # → split into Part-1a / Part-1b if line OR byte OR token gate trips
> ```

The trigger is **line OR byte OR token** — whichever fires first forces the split. External source/context files a runner reads but does NOT generate (codebase modules, third-party docs) keep the advisory treatment: warn, apply the [Large-File Read Tactics](#large-file-read-tactics) ladder, and file a refactor backlog item — they are not hard-split because the runner does not own them.

---

## Read Gates and Large-File Read Tactics

The read-gate canonical: the Read tool's fixed mechanical limits, the discipline for respecting them, and the tactics for a file that exceeds one. These constants and rules apply regardless of `context.token_saver` — they are harness facts, not a carrying-cost policy (the config-gated Token Saver budget system lives in [token-saver-profile.md](token-saver-profile.md)).

### Read-Tool Hard Limits

The Read tool has two mechanical limits, SEPARATE from the carrying-cost budget — a file can fit the session budget yet be unreadable in one Read. These constants are **FIXED harness facts** (measured 2026-06-23; re-validate via headless `claude -p --model X`), defined as module-level constants in `scripts/token_saver.py` — they are **NOT** `/context`-measured and are **NOT** written by `calibrate()`.

- **Byte gate (model-independent):** a file ≥ **262,144 bytes (256 KiB)** (`READ_FILE_BYTE_CAP`) is refused unless `offset`/`limit` is passed. Warn at **245,760 bytes (240 KiB)** (`READ_BYTE_WARN`).
- **Token page-cap gate (model-dependent):** a file above **~25,000 tokens** (`READ_PAGE_CAP_TOKENS`) returns only its first page (truncates). Tokens use the **runner model's** tokenizer — `~13 tok/line` Sonnet/Haiku, `~19 tok/line` Opus (`TOKENS_PER_LINE`). Opus tokenizes ≈1.44× heavier, so it trips the gate at **~1,340 lines** vs Sonnet/Haiku's **~1,920**. Warn at **~22,000 tokens** (`READ_TOKEN_WARN`).

These FOLD into the per-file warning ladder. `token_saver.classify_file()` computes `level = max(cost_level, read_level)` and tags `reason = cost | read` naming whichever gate drove the level:

> [!constraint] A `read`-reason Critical Is NOT 1M-Exception-Resolvable
> WRONG — a runner hits a `read`-reason Critical and escalates the dispatch to Opus (1M window) expecting the larger window to absorb it:
> ```
> classify_file(...) → {level: Critical, reason: read}   → "route to Opus, the 1M window fixes it"  ← FALSE
> ```
> CORRECT — routing to Opus does NOT raise the per-Read page cap, and Opus's heavier tokenizer trips the gate *sooner* (~1,340 lines vs ~1,920). The remedy is **paged reads** (`offset`/`limit`/Grep), and for a core or to-be-edited dependency, **refactor + backlog**:
> ```
> classify_file(...) → {level: Critical, reason: read}
>   → page it: Read(offset/limit) or Grep the needed section
>   → if it is a core/edited dependency: split/refactor the file + file a backlog item
> ```
> A `cost`-reason Critical is a budget overflow (split the task / trim Required Context). A `read`-reason Critical is a mechanical Read failure (page it / refactor). The 1M exception addresses neither.

### Reading Discipline With Read Gates (BINDING)

The [Read Files Fully](#reading-discipline-binding) rule still holds — read all relevant content, never skim or infer. This section adds one refinement: when a single Read **cannot** deliver a whole file (≥ 256 KiB, or above the runner model's token page-cap), reading "fully" means **paging** it, not trusting one Read returned everything.

> [!constraint] Page Large Files — Do Not Trust One Read
> WRONG — runner issues one Read on a 2,400-line file, gets the first page back, and proceeds as if it read the whole file:
> ```
> Read(path)   → returns first ~1,920 lines (Sonnet) silently truncated → runner acts on partial context
> ```
> CORRECT — when a file exceeds a gate, page it with `offset`/`limit` (or Grep the needed sections) AND check the returned content for the `PARTIAL view` truncation header before assuming completeness:
> ```
> Read(path, offset=1, limit=900) → check for "PARTIAL view" header
> Read(path, offset=901, limit=900) → … continue until the whole file is covered
> # or: Grep(pattern, path, output_mode: "content", context: 30) for a known section
> ```
> "Read fully" is satisfied by paged reads that together cover the file — NOT by one Read that silently returned only the first page.

### Large-File Read Tactics

> [!practice] Ladder for Files Exceeding a Read-Tool Gate
> The Read tool has two mechanical gates — see [Read-Tool Hard Limits](#read-tool-hard-limits) above (NOT a single ~13K/~1000-line budget). When a file crosses either gate, apply this ladder in order — stop at the first step that succeeds. A `read`-reason Critical is NOT resolvable by routing to a 1M-window model (see the constraint above).

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
