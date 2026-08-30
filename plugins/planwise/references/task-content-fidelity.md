---
description: Required Context fidelity — measured estimates, freshness across file splits, bytes-per-token ratios, and the Token Saver large-file ladder — for planwise task files
---

# Task Content Fidelity

**Purpose:** Required Context fidelity rules (§9.A) for task files — measured estimates that stay fresh across file splits, bytes-per-token ratios, and the Token Saver large-file classification ladder. Extends [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9 (Task File Template) with the §9.A subsection; extracted into this sibling file to keep both rule files comfortably within a single Read call. Verify-before-cite discipline (§9.B) is the split sibling [verify-before-cite.md](verify-before-cite.md).

**Companion files:** [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Task File Template, Orchestration linkage, completion tracking), [verify-before-cite.md](verify-before-cite.md) (§9.B Verify-Before-Cite — split sibling: lesson IDs, schema files, field names, facade re-exports, upsert helper design).

---

## 9.A Required Context Fidelity (BINDING)

The Task File Template's Required Context table is a *contract* for the subagent's budget. Every cell MUST reflect a measured reality at the moment the plan is committed.

### 9.A.1 Update Required Context when prior tasks change file structure

> [!constraint] Downstream task files MUST be updated when an upstream task changes the files they reference
> When a task's output changes file structure (splits, renames, moves, deletions),
> every downstream task file in the same plan that references those files MUST
> have its Required Context updated. This includes:
> - File paths
> - `KiB` cells (re-measure the new files)
> - `~Tokens` cells (re-run `measure_files.py` on the new files)
> - Context subtotal and the task header's `Estimated Tokens`
>
> WRONG — Task 1 splits `{schema-file}` into `{schema-file-A}` ({K_A} KiB)
> and `{schema-file-B}` ({K_B} KiB); Task 2's Required Context still
> references `{schema-file}` (~{old_K} KiB) and is unchanged. The Task 2
> subagent reads a file that no longer exists OR reads only one of the two
> splits and silently misses the second part.
>
> CORRECT — after Task 1 completes, the planner (or the Task 1 subagent in its
> post-task hand-off) updates Task 2's Required Context to:
> ```
> | 1 | {schema-file-A} | {K_A} | ~{T_A}K | {purpose A} |
> | 1 | {schema-file-B} | {K_B} | ~{T_B}K | {purpose B} |
> ```
> and re-derives the Context subtotal and task header `Estimated Tokens`. The
> `Last verified:` comment in the Required Context block (if used) is bumped to
> the current date.

Applies to any planwise plan with sequential task dependencies, output-chaining sessions, and plans that may trigger read-gate file splits during execution.

### 9.A.2 Token estimates use measured values — no `~?` placeholders

> [!constraint] Required Context numerical cells MUST be measured, not placeholder
> Every `KiB` cell MUST be a measured value, and every `~Tokens` cell MUST be
> derived from the measured byte size ÷ the assigned model's bytes-per-token
> ratio (see §9.A.3) — produce both at once with `measure_files.py --model
> {assigned model} --md` over the cited paths. Placeholders like `~?`, `~TBD`,
> or qualitative ranges without an arithmetic basis fail review.
>
> WRONG — placeholders that bypass measurement, breaking task-header
> reconciliation:
> ```markdown
> | Priority | File | KiB | ~Tokens | Purpose |
> |----------|------|----:|--------:|---------|
> | 1 | {src/module/file_A.ext} | ~? | ~{T}K | {purpose} |
> | 1 | {src/module/file_B.ext} | ~? | ~{T}K | {purpose} |
>
> Context subtotal: ~{total}K reads + ~{out}K output = ~{total}K total
> ```
> Real-world cost: the actual files were far larger than estimated; the cascade
> invalidated session and sprint-level totals.
>
> CORRECT — measured sizes, derived token estimates, reconciled subtotal:
> ```markdown
> | Priority | File | KiB | ~Tokens | Purpose |
> |----------|------|----:|--------:|---------|
> | 1 | {src/module/file_A.ext} | {K_A}  | ~{T_A}K   | {purpose} |
> | 1 | {src/module/file_B.ext} | {K_B}  | ~{T_B}K   | {purpose} |
>
> Context subtotal: ~{reads_total}K reads + ~{out}K output = ~{grand_total}K total
> ```

For files that may legitimately not exist (conditional reads via `Glob`), use `conditional` in the `~Tokens` column rather than a numerical placeholder.

A complementary `/planwise review` check rejects any plan whose task files contain `~?`, `~TBD`, or `~?K` literals in Required Context numerical cells.

#### Reviewer Check 016 — Task Required Context KiB / Tokens Numeric

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Required Context table MUST have NUMERIC values in the KiB / ~Tokens columns. No `~?`, no `TBD`, no blank cells.
- **Detection:** Open Required Context table; Grep for `\|\s*(~?\?|TBD|—)\s*\|` within the size columns. Any match → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task Required Context KiB/Tokens non-numeric
File: {task file path} | Location: Required Context row {N}
Issue: Column {KiB|~Tokens} contains "{value}" instead of a measured value
Fix: Measure with measure_files.py and write the numeric value per references/task-content-fidelity.md §9.A.2 | Confidence: HIGH
```

### 9.A.3 Bytes-per-token ratio

> [!constraint] Tokens are derived from measured bytes ÷ the content-class ratio — never from a line count
> The canonical per-model ratio table lives in
> [session-context-budget.md](session-context-budget.md) § Read-Tool Hard
> Limits; `measure_files.py` applies it for you. Per-line token rates are
> unreliable (measured 7–365 tokens/line depending on content) and MUST NOT be
> used. When the reading model or content class is unknown, use the
> gate-conservative default (2.6 bytes/token) — it over-estimates rather than
> under-budgets.
>
> WRONG — a token estimate typed from a hunch, contradicting itself in Notes:
> ```markdown
> | 1 | {notebook-dir}/{notebook-file} | {K} | ~{T}K | Source for Analysis |
>
> ## Notes for Agent
> - Notebook is large (~{larger_T}K tokens). Read it fully...
> ```
>
> CORRECT — one measured figure, produced by the script, cited consistently:
> ```markdown
> | 1 | {notebook-dir}/{notebook-file} | {K} (JSON) | ~{T}K | Source for Analysis — measured via measure_files.py (conservative 2.6 B/tok; dense single-line JSON tokenizes heavy) |
>
> ## Notes for Agent
> - Notebook measured at {K} KiB → ~{T}K tokens (conservative ratio).
>   Subagent budget: ~{task_T}K + 54K overhead = ~{total_T}K, well within 200K.
> ```
>
> Content-class ratio guide (Opus/Fable-family; the Sonnet/Haiku family
> tokenizes ~1.44× lighter — more bytes per token):
>
> | Content class | Bytes/token | Heuristic |
> |---------------|-------------|-----------|
> | Dense markdown (tables, link-heavy rows) | ~2.6 | Gate-conservative default — use when unsure |
> | Prose / typical markdown | ~3.0 | |
> | Docs with code blocks / source code | ~3.3 | |
> | Wide-line reference docs | ~4.1+ | Light — measure, never assume |
> | Compressed JSON / minified JS / notebook JSON | ~1.9–2.6 | Dense structures tokenize heavy; keep the conservative default |
>
> The `KiB`/`~Tokens` values MUST come from `measure_files.py` (or `wc -c` ÷ ratio) on the actual file — NOT from eyeballing a `Read` tool output. A single `Read` page is capped (~25K tokens hard, ~21K delivered, 2,000-line window); a partial read produces a lower number that underestimates the cost and silently misroutes the file in the §9.A.8 Large-File Ladder.

#### Reviewer Check 017 — Task Byte-Ratio Band Conformance

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Per-file ratio (measured bytes ÷ `~Tokens`) MUST fall within the measured band for the assigned model family — `[2.4, 3.5]` Opus/Fable, `[3.5, 5.0]` Sonnet/Haiku (conservative-default estimates land in the Opus/Fable band).
- **Detection:** For each Required Context row, compute `bytes ÷ tokens`. Outside the assigned family's band → WARNING.
- **Finding template:**
```
[WARNING] Task byte-ratio band violation
File: {task file path} | Location: Required Context row {N} (file: {cited_file})
Issue: Ratio {ratio} B/tok outside the {family} band
Fix: Re-measure with measure_files.py per references/task-content-fidelity.md §9.A.3 | Confidence: MEDIUM
```

### 9.A.4 Re-glob file-set counts at task-author time

> [!constraint] Glob-cited file-set counts MUST be re-globbed when the task file is authored, not copied from an upstream estimate
> When a task's Required Context cites a file-set by glob pattern (e.g.
> `references/*.md`, `src/**/*.ext`), the file count and the derived
> `KiB` / `~Tokens` cells MUST be produced by running the glob at
> task-author time. A count copied from an upstream plan, an earlier sprint's
> estimate, or the Master Plan's Sprint Overview is stale the moment any task
> adds, splits, or deletes a matching file.
>
> WRONG — task cites `{glob-pattern}` and reuses the "{N} files" figure from the
> sprint plan written several sessions earlier:
> ```markdown
> | 1 | {glob-pattern} | ~{N} files, ~{old_K} KiB | ~{old_T}K | {purpose} |
> ```
> Two intervening tasks added files matching `{glob-pattern}`; the subagent's
> real read is larger than budgeted and the session total is wrong.
>
> CORRECT — re-glob when the task file is authored and record the live count
> (feed the glob's expansion to `measure_files.py` for the totals):
> ```markdown
> <!-- Re-globbed {YYYY-MM-DD}: {glob-pattern} → {N} files, {K} KiB total -->
> | 1 | {glob-pattern} | {N} files, {K} KiB | ~{T}K | {purpose} |
> ```
> The `~Tokens` cell is re-derived from the live measurement per §9.A.3, and
> the Context subtotal and task header are reconciled per §9.A.2.

Applies to any task whose Required Context references files by glob rather than by individual path — especially plans where earlier tasks create or split files that the glob matches.

#### Reviewer Check 025 — Task Re-Glob Live Counts Before Authoring

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Required Context citing file-glob counts (e.g., "12 adapter modules") MUST reflect a recent re-glob within session — not copy from prior task.
- **Detection:** Grep Purpose column for `(\d+)\s+(modules?|files?|tasks?|sessions?)`; perform Glob; compare. Mismatch → WARNING.
- **Finding template:**
```
[WARNING] Task Required Context glob count stale
File: {task file path} | Location: Required Context row {N} Purpose column
Issue: Declared count "{N}" differs from live disk count "{actual_N}"
Fix: Re-glob per references/task-content-fidelity.md §9.A.4 | Confidence: HIGH
```

### 9.A.5 Budget 1.5-2× the naive sum for consolidation tasks

> [!constraint] A consolidation task reading N upstream outputs MUST budget 1.5-2× the naive token sum
> When a task's job is to read N upstream artifacts and produce a consolidated,
> cross-referenced, or deduplicated output, the token estimate MUST be 1.5-2× the
> naive sum of the N inputs' sizes. The naive sum captures only the raw reads; it
> omits the cross-referencing overhead — re-reading earlier inputs to resolve a
> reference, holding partial state while merging, and an output larger than any
> single input.
>
> WRONG — consolidation task budgeted at the bare read sum:
> ```markdown
> Context subtotal: ~{sum}K reads + ~{out}K output = ~{sum_plus_out}K total
> <!-- {sum}K = naive sum of the {N} input files -->
> ```
> Mid-task the subagent re-reads inputs 1-3 to reconcile a contradiction flagged
> in input 7; actual context lands ~1.7× the estimate and the budget margin is gone.
>
> CORRECT — apply the consolidation multiplier and state it:
> ```markdown
> Context subtotal: ~{sum}K reads × 1.7 (consolidation overhead) + ~{out}K output = ~{total}K total
> <!-- {N} inputs cross-referenced; 1.5-2× per §9.A.5 — 1.7× chosen for moderate cross-reference density -->
> ```

Applies to Meta-Plan Discovery consolidation tasks, Execution-Input extraction tasks, and any task that merges multiple upstream outputs into one cross-referenced artifact.

#### Reviewer Check 026 — Task Consolidation 1.5-2× Budgeting

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Consolidation/synthesis tasks MUST budget 1.5-2× source-input tokens for output (consolidation expands).
- **Detection:** For tasks with "consolidate" / "synthesize" Objective, compute output/input ratio. <1.5 → WARNING.
- **Finding template:**
```
[WARNING] Task consolidation under-budgeted
File: {task file path} | Location: Required Context subtotal vs Output estimate
Issue: Ratio {ratio}x below 1.5-2× consolidation band
Fix: Increase per references/task-content-fidelity.md §9.A.5 | Confidence: MEDIUM
```

### 9.A.6 Cite the generator, not the walked file-set, for large generated inputs

> [!constraint] When a task's Required Context is produced by a generator walking ≥100 files (or a tree totaling ≥10K lines), cite the generator and its input root — not the individual files
> If a task consumes input produced by a script or tool that walks a large file
> tree — **≥100 files, OR a tree totaling ≥10K lines** — the Required Context
> table MUST cite (a) the generator command or script and (b) its input root
> directory — NOT 100+ individual file rows. Enumerating every walked file bloats
> the task file past the read-gate ceiling, makes the size arithmetic
> unauditable, and goes stale the instant one file is added.
>
> WRONG — 100+ rows, one per walked file:
> ```markdown
> | 1 | {input-root}/file-001.ext | {K} | ~{T}K | walked |
> | 1 | {input-root}/file-002.ext | {K} | ~{T}K | walked |
> | 1 | ... 130 more rows ... | | | |
> ```
>
> CORRECT — cite the generator + input root + the generated artifact:
> ```markdown
> | 1 | {generator-cmd} over {input-root}/ ({N} files) | {K} | ~{T}K | input produced by the generator; do not enumerate the walked tree |
> | 1 | {generated-output-path} | {K2} | ~{T2}K | the generator's consolidated output — this is what the task reads |
> ```
> The `KiB` / `~Tokens` cells reflect the generator's *output* (what
> the subagent actually reads), not the sum of the walked tree.

Applies to tasks fed by codebase-scan scripts, doc-index generators, manifest builders, or any tool whose input is a directory walk of ≥100 files or ≥10K total lines.

#### Reviewer Check 027 — Task Generator-Script Pattern (≥100-file Walks)

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Tasks walking ≥100 files MUST use generator-script pattern.
- **Detection:** Count file references in Required Context. ≥100 AND no generator-script reference in Execution Steps → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task generator-script pattern missing
File: {task file path} | Location: Execution Steps
Issue: Task walks {N} files (≥100) without generator-script architecture
Fix: Add per references/verify-before-cite.md §9.B.15 / references/task-content-fidelity.md §9.A.6 | Confidence: HIGH
```

### 9.A.7 Declare multi-artifact output splits at plan-author time

> [!constraint] When a task's output would exceed the one-read token budget, the split MUST be declared in the task file at plan-author time
> If a task's Expected Output is projected to exceed the Read-gate split target
> — **~22,000 tokens** (≈ 57 KiB of dense markdown at 2.6 B/tok; see
> [session-context-budget.md](session-context-budget.md) File Size Limits) — the
> planner MUST declare the multi-part split in the task file — naming each part
> and its topic — rather than leaving the executing subagent to discover the
> overflow and improvise a split mid-task.
>
> WRONG — single output path for an output that will not fit one Read:
> ```markdown
> **Output:** Outputs/{Abbrev}-{artifact}.md
> <!-- projected ~30K tokens -->
> ```
> The subagent writes ~30K tokens into one file (unreadable in a single Read
> downstream) or invents an ad-hoc split with names no downstream task
> references.
>
> CORRECT — pre-declare the split with the Multi-Part Output Convention:
> ```markdown
> **Output:** (projected ~30K tokens — pre-split per §9.A.7)
> - Outputs/{Abbrev}-{artifact}-Part-1-{Topic}.md  (~15K tokens)
> - Outputs/{Abbrev}-{artifact}-Part-2-{Topic}.md  (~15K tokens)
> ```
> Each part lands OK on all three Read gates (verify with `measure_files.py`
> after writing), carries a descriptive topic suffix, and is self-contained
> enough to feed a downstream task per the Multi-Part Output Convention.

Applies to any task — spec authoring, consolidation, large code generation — whose Expected Output is projected past the ~22K-token split target.

#### Reviewer Check 028 — Task Multi-Artifact Pre-Split Shape

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Tasks producing outputs projected past the one-read token budget MUST declare pre-split shape (which parts, content per part).
- **Detection:** Check Expected Output; if projected output tokens > ~22,000 AND no `-Part-{N}` declaration → ERROR.
- **Finding template:**
```
[ERROR] Task multi-artifact pre-split shape missing
File: {task file path} | Location: Expected Output
Issue: Output projected > ~22K tokens but no Part-{N} split declared
Fix: Declare split per references/task-content-fidelity.md §9.A.7 | Confidence: HIGH
```

### 9.A.8 Token Saver Large-File Ladder

This subsection is the **per-task-file enforcement anchor** the `handlers/plan.md` Step 8c scan (and its Scaffolding Step 5 mirror) implement and that `/planwise review` checks against. It documents the graduated warning ladder, the threshold-derivation formulas, the three FIXED Read-tool gates the ladder folds in, and the `reason=cost|read` distinction. Active only when `context.token_saver: true`; when false, the §9.A token-estimation rules above stand alone.

> [!constraint] Every Required Context file MUST be classified against the folded cost + read ladder when Token Saver is on
> When `context.token_saver: true`, each task's Required Context file MUST be classified by `token_saver.classify_file(path, model, projected_added_bytes, thresholds)`, which returns `{level, reason}` where `level = max(cost_level, read_level)`. A file the same task will modify MUST be classified on `current + projected delta` (pass `projected_added_bytes` — estimate it as projected added lines × that file's observed average bytes/line) so a file that *will* cross a gate post-edit is flagged pre-emptively — not after the runner overflows mid-task.
>
> WRONG — a ~54 KiB module is classified at its current size only; the task adds ~10 KiB, pushing it past the token page-cap, but the scan passes it Green and the runner gets a truncated Read mid-edit:
> ```
> classify_file(path, model="opus")                       # projected_added_bytes defaults to 0 → Green
> ```
> CORRECT — classify on current + projected delta so the will-exceed case is caught at plan-author time:
> ```
> classify_file(path, model="opus", projected_added_bytes=10_000, thresholds=th)   # → {level: Critical, reason: read}
> ```

**Canonical homes — do not restate.** The cost-threshold derivation formulas (`available_per_task`, `critical`, `warn`) are computed by `token_saver.derive_thresholds()`; see [token-saver-profile.md](token-saver-profile.md) § Token Saver Threshold Derivation for the formulas and the `40,000`-guaranteed-warn-ceiling explanation. The Read tool's three FIXED mechanical gates — `READ_PAGE_CAP_TOKENS` / `READ_FILE_BYTE_CAP` / `READ_LINE_CAP`, their values and warn bands, the per-model bytes-per-token ratios, and the `measure_files.py` measurement discipline — live in [session-context-budget.md](session-context-budget.md) § Read-Tool Hard Limits. All are module-level constants in `scripts/read_limits.py` (re-exported by `scripts/token_saver.py`), NOT `/context`-measured.

`level = max(cost_level, read_level)`; `reason` records the driver:

| Level | Cost threshold | Read threshold (per assigned model) | Action |
|-------|---------------|-------------------------------------|--------|
| Green | < `warn` | < 22K tok AND < 240 KiB AND < 2,000 lines | none |
| Warn | ≥ `warn` | ≥ 22K tok OR ≥ 240 KiB | warn + refactor recommendation + file a backlog item |
| Critical / `cost` | ≥ `critical` | — | warn + backlog + flag task **`1M-exception`** (Opus/1M); plan still completes |
| Critical / `read` | — | ≥ 25K model-tok OR ≥ 256 KiB OR ≥ 2,000 lines | warn + backlog + **paged read / refactor**; **NOT** `1M-exception` |

> [!constraint] A `read`-reason Critical Is NOT `1M-Exception`-Resolvable
> A **cost-reason** Critical earns the `1M-exception` flag — the file is simply too big for a lean per-task budget, and the 1M window absorbs it. A **read-reason** Critical does NOT: the per-Read page cap is unchanged by the window, and the Opus/Fable-family tokenizer trips the token gate on *fewer bytes* than Sonnet/Haiku's. The remedy is a **paged read** (`offset`/`limit`/Grep) for read-only context, or **refactor/split + backlog item** for a core or to-be-edited dependency. A source-file Critical is never a hard stop — it advises and files an item.

**Single oversized file vs. per-task sum.** On a default/light install the cost bands sit *above* the FIXED 25K read cap (`warn` is 40K, derived `critical` higher still), so any single file large enough to be cost-Warn/Critical has already crossed the read gate — it classifies `reason=read` (paged-read/refactor), **never** cost-`1M-exception`. Cost-`1M-exception` therefore surfaces for a single file only on a **heavy** install where derived `critical` drops below 25K; otherwise it fires on a **per-task sum** of several mid-size files whose combined estimate trips `critical` while no single file trips the read cap. Do **not** expect a lone giant file to be `1M-exception`'d on a default install — that is the intended `max(cost, read)` + ties-go-to-`read` behavior, not a miss.

**Generated-artifact hard-split (§9.A.7 trigger extension).** §9.A.7 declares multi-part splits when projected output exceeds the one-read token budget. The split trigger for **generated artifacts a runner MUST read** (task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files) is **token OR byte OR line gate — in that priority order**, whichever fires first forces a Multi-Part split, and the read-gate ceiling is **HARD** regardless of `context.token_saver`. External source files the runner reads but does not generate stay advisory (warn + backlog + read tactics). See `references/session-context-budget.md` [§ File Size Limits — Generated Artifacts](session-context-budget.md#file-size-limits--generated-artifacts-binding).

#### Reviewer Check 065 — Task Token Saver Large-File Ladder Applied

- **Severity / Role / Type:** ERROR / WARNING (tiered) | Task Reviewer | NEW
- **Gate:** Runs ONLY when `context.token_saver: true` in `config.yaml`. When Token Saver is off this check is a **no-op** — skip it (zero behavior change). Read §9.A.8 for level definitions, the `reason=cost|read` contract, and the FIXED Read-tool gates before authoring findings.
- **What:** When Token Saver is on, every task's Required Context MUST obey the folded cost + read ladder. Six failure modes, each tiered:
  1. **Over-ceiling without exception** (ERROR) — `task_estimate + context.token_saver_runner_overhead > context.token_saver_session_target` AND the task is not flagged `1M-exception`.
  2. **Warn+ file with no backlog item** (WARNING) — a Required Context file classifies Warn or Critical (cost or read) but the task records no large-file recommendation / backlog item.
  3. **`1M-exception` on a 200K-window agent** (ERROR) — a `1M-exception` task is declared `Agent: Sonnet`/`Haiku` without the run-time override note (the flag dispatches on Opus/1M).
  4. **Uncovered read-gate crossing** (WARNING) — a Required Context file crosses a FIXED read gate (measured bytes ≥ 256 KiB, OR `bytes ÷ {assigned-model B/tok}` ≥ 25K tokens, OR ≥ 2,000 lines) and the task records neither a paged-read note (`offset`/`limit`/Grep) nor a refactor+backlog item.
  5. **Read-reason Critical mis-flagged `1M-exception`** (ERROR) — a file classifying Critical with `reason=read` is flagged `1M-exception`. The 1M window does not raise the per-Read page cap / byte refusal, and the Opus/Fable-family tokenizer trips the token gate on *fewer bytes* than Sonnet/Haiku's — read-Critical is paged or refactored, never `1M-exception`'d. Only `reason=cost` Critical earns the flag.
  6. **Oversized generated artifact not split** (ERROR) — a plan-generated artifact a runner MUST read (task file, Orchestration, Recovery, Consolidated Context part, Execution Input, task Output file) exceeds the HARD read ceiling (≥ 25K tokens at the reading model's ratio, OR ≥ 256 KiB, OR ≥ 2,000 lines) without a Multi-Part split. External source files the runner reads but does not generate stay advisory (sub-checks 2 and 4).
- **Detection:**
  1. Read `context.token_saver` from `config.yaml`. If false → emit no findings (no-op).
  2. Derive ceilings (never hardcode): `available_per_task = token_saver_session_target − token_saver_runner_overhead − 6000`; `critical = available_per_task − 10000`; `warn = min(40000, round(0.5 × available_per_task))`. Read gates are FIXED: token page-cap ≥ 25,000 model-tok (warn 22,000), `tokens = bytes ÷ {model-family B/tok — opus/fable 2.6, sonnet/haiku 3.7 gate-conservative}`; byte ≥ 262,144 (warn 245,760); line ≥ 2,000 — measure with `measure_files.py --model {assigned} --json`.
  3. For each task: recompute the bottom-up estimate and apply sub-check 1.
  4. For each Required Context file: classify against the task's assigned-Agent tokenizer (`level = max(cost_level, read_level)`, with `reason`); apply sub-checks 2, 4, 5.
  5. Apply sub-check 3 to any task flagged `1M-exception`.
  6. For each generated artifact the plan authors and a runner reads: apply sub-check 6 against the HARD read ceiling.
- **Finding template:**
```
[{ERROR|WARNING}] Token Saver large-file ladder not applied
File: {task file path} | Location: Required Context row {N} / Notes for Agent / Estimated Tokens
Issue: {over-ceiling task lacks 1M-exception | Warn+ file {cited_file} has no backlog item | 1M-exception task on {Sonnet|Haiku} without override note | {cited_file} crosses read gate ({bytes}B / {tokens}tok) with no paged-read or refactor+backlog | read-reason Critical {cited_file} wrongly flagged 1M-exception | generated artifact {artifact} past HARD read gate without Multi-Part split}
Fix: Apply the §9.A.8 remedy — flag 1M-exception (cost-Critical) / file a backlog item (Warn+) / page or refactor (read-Critical) / Multi-Part split (generated artifact) per references/task-content-fidelity.md §9.A.8 | Confidence: HIGH
```

### 9.A.9 Count re-derivation for enumerated lists

> [!constraint] A count summarising an enumerated list MUST be re-derived at authoring time and stated exactly once
> A count that summarises an enumerated list MUST be re-derived by counting the list at authoring time, and MUST appear exactly once. Do not restate it in a heading and again in the body — a count stated twice is a count that will disagree with itself.
>
> WRONG: `MERGE column list — 26 columns:`
> CORRECT: `MERGE column list — must match the DDL order exactly:` (or, where the number is genuinely load-bearing: "…one `?` per column below; count them.")
>
> A count of sibling tables, adapters, or notebooks is a claim about the repository, not about the task — it belongs to the verify-against-shipped-artifact discipline, and a plan may not count an artifact that a different, unshipped plan is going to create.
>
> Review check: `grep -rnE '\b[0-9]+ (columns?|fields?|placeholders?|symbols?|tables?|rows?)\b'` over task files; for each hit, locate the list it refers to and count it — they must agree. Catalog row: "Prose count disagrees with the list it summarises" → WARNING (ERROR when the count feeds a parameter binding or a schema decision).

> [!practice] The list is the source of truth — prefer no cached count
> The list is the source of truth; the number is a cache with no invalidation. Every count typed next to a list is correct at the instant it is written and decays on the next edit to either side. Prefer no cache.

Applies to: the narrower glob-cited file-set case is §9.A.4 — this rule generalises it to any prose count adjacent to an enumerated list.

### 9.A.10 Cross-file enumeration sweep on item-set change

> [!constraint] A plan item-set change is a cross-file sweep, not a single-file edit
> When a plan's item set changes after task files, Orchestrations or Master-Plan rows already enumerate it, the change is a cross-file sweep — not a single-file edit. Two things must be swept: the old cardinality words, and the old enumerated ID list. The preceding count rule alone cannot reach this failure, for two reasons: it is scoped within one document (here the count is restated across several self-consistent files, and the drift is between them), and an enumerated ID list is not a count — there is no adjacent list to check a short enumeration against; the authoritative set lives in a different file.
>
> WRONG — an Expected Output template that caches the item set the runner will author from:
> ```
> ## Verified Known-Issue State   (per-claim ledger, three items)
> ## Verified Work Items   (the three filed defects: verdicts, fix recipes, landing surfaces)
> ```
> CORRECT — the template refers to the set by contract; the Objective remains the single source of truth:
> ```
> ## Verified Known-Issue State   (per-claim ledger — one row per atomic claim of every filed defect named in the Objective)
> ## Verified Work Items   (one per filed defect named in the Objective: verdict, fix recipe, landing surface)
> ```
>
> The sweep recipe:
> ```bash
> # 1. Old cardinality words, anywhere in the plan tree
> grep -rniE '\b(one|two|three|four|five|six|seven|eight|nine|ten|[0-9]+)\b' \
>   {plan_dir}/ | grep -iE '(item|defect|task|part|cluster|famil)'
>
> # 2. The OLD enumerated ID list — the half a count rule cannot catch
> grep -rn '<superseded enumeration>' {plan_dir}/
> grep -rn '<superseded boundary set>' {plan_dir}/
>
> # 3. Reconcile every hit against the Objective's set, and against any
> #    sibling file that states the same set (Master Plan rows, Sprint Plan
> #    Success Criteria, other tasks' Required Context).
> ```
>
> Two supporting practices: **Expected Output templates are the highest-risk site** — a runner authors its deliverable's section structure from the template verbatim, so a narrower set there silently beats a broader Objective on the same page; sweep templates first. And **enumerations restated across files need one owner** — when the same set appears in a task file, a Sprint Plan and a Master-Plan row, name the owning file and have the others refer to it by contract rather than re-listing: the same no-cache-without-invalidation argument, extended from counts to membership.

### 9.A.11 Derived status cells are generated, not restated

> [!constraint] A status cell derived from an evidence section MUST be generated from it, never hand-typed
> This rule generalises the preceding count-re-derivation rule from numerals to status cells. An artifact with an evidence section and an action/findings/prescription section has two tiers, not two documents. Every status cell in the second tier (`VERIFIED`, `UNVERIFIED`, `CONFIRMED`, `ABSENT`, `PRESENT`) is a function of an observation recorded in the first. When an author re-types the tag instead of deriving it, the two tiers drift — and the action tier is the one everyone downstream actually executes.
>
> Generate each action row's status from the evidence section's observation count for that item; do not hand-type it:
>
> | Observations recorded in the evidence tier | Status the action tier MUST carry |
> |---|---|
> | 0 across all probed seeds / samples / sources | `UNVERIFIED — absent at source` |
> | ≥1 | `VERIFIED` |
> | not probed at all | `UNVERIFIED — not observed` (distinct from *absent*; do not collapse the two) |
>
> An item the evidence section records as absent cannot carry a bare confirmation in the action list — that is an internal contradiction, detectable from the file alone, with no external access. The CORRECT form cites its derivation in the cell: `UNVERIFIED — absent at source (0/4 seeds, §3). Expect continued NULL after wiring; that is not a failed fix.`
>
> Before dispatching an artifact with an action tier, scan for rows on equal evidentiary footing that carry different statuses. When sibling rows on equal footing disagree, one of them is wrong — you do not need to know which one to know that.
>
> A task that produces an evidence-plus-action artifact MUST, as its final step, cross-check every action row's status against the evidence section's observation for that item, and record the check in its Recovery. Any row asserting presence for an item the evidence records as absent or unobserved is a **blocking** contradiction — resolve it before the artifact is written.
>
> Catalog row: "Action tier contradicts its own evidence tier" → BLOCKER.

Cross-reference: `measurement-discipline.md` §8.6 covers cross-route APPEND safety against a live target that moved — an adjacent but distinct concern. This rule governs intra-document tier consistency at authoring time, with no external state involved; cite §8.6, do not merge it into this rule.

### 9.A.12 Size comparison tasks by reference coverage

> [!constraint] Size and shape a comparison task by the reference side's coverage, not the subject side's population
> When a task's deliverable is a comparison — enumerate discrepancies, reconcile A against B, find drift between a spec and an implementation — its size and shape are set by the coverage of the **reference** side, not by the population of the subject side. Measure that coverage before writing the brief: `coverage = (items the reference makes a claim about) / N sampled subject items`.
>
> | Reference coverage | What the task actually is | How the brief must read |
> |---|---|---|
> | High | A genuine reconciliation; discrepancies are the output | "Enumerate the discrepancies between A and B" |
> | Low (e.g. <1%) | A census with a small actionable tail | "Enumerate the N classes of actionable finding, and tally coverage" |
>
> Three obligations when coverage is low: (1) budget for the listing volume, not the analysis volume — the token cost is dominated by emitting uncovered rows, not classifying covered ones; (2) lead the output with the actionable section and put the census in a separate part; (3) name the coverage in the brief — its absence is why the default framing survives.
>
> Applicability boundary: this does NOT apply where the reference genuinely covers the subject (a well-documented vendor API, a spec-governed service, a schema with an authoritative published type source) — there, the ordinary framing is correct. The rule fires on measured low coverage, never on a hunch.
>
> Corollary: when a reference makes no claim, the observation is the authority — downstream tasks should consume the observed inventory rather than re-consulting a reference already measured at near-zero coverage.
>
> Cross-reference: distinct from the cohort token-uplift discipline (divergence-triggered budgeting overhead between two artifacts that both exist) — this rule fires on a different measurement and re-shapes the deliverable rather than its overhead.
>
> Catalog row: "Comparison task sized without reference coverage" → WARNING.

### 9.A.13 Assertion labels and validation cells need a 1:1 table

> [!constraint] Every validation cell a task file enumerates MUST resolve to exactly one assertion label, including cells deliberately left unlabelled
> When a plan names its validation assertions at one tier (Master Plan / Sprint Plan / Orchestration: `A1`…`AN`) but the cells implementing them are enumerated later at task level, the two registers can drift. If there are more cells than labels, the unlabelled cell attracts a reused label — and the reuse can silently flip a gate's semantics, hardening a report-only cell into an assert or the reverse.
>
> Any task file enumerating validation cells (assertion labels, gate IDs, check cells) MUST carry a 1:1 assertion-label ↔ cell-ID table, listing every cell — including deliberately unlabelled ones, which are marked `*(none — deliberately un-numbered)*` so a blank reads as a statement, not an invitation to fill in.
>
> WRONG — a validation-cell list with one cell left blank and the disposition carried only in prose, three lines from the citation that gets it wrong:
> ```
> | Cell | Purpose | Label |
> |------|---------|-------|
> | 8a   | row count | A2 |
> | 8b   | spine completeness | A1 |
> | 8c   | column / rename integrity | *(none)* |
> | 8d   | duplicated-flag agreement | A3 — report-only, must NOT assert |
> | 8e   | preseason NULL classification | A4 |
> ```
> The blank at `8c` invites reuse. `8d`'s report-only disposition lives only in a prose aside, and a later Success Criterion cites "**A3 (8c)** passes" — contradicting the Master Plan, the Sprint Plan, the Orchestration, and the task's own Notes-for-Agent, all of which say A3 reports and must not assert.
>
> CORRECT — a dedicated Disposition column, and the deliberately-unlabelled marking instead of a blank:
> ```
> | Cell | Purpose | Label | Disposition |
> |------|---------|-------|-------------|
> | 8a   | row count | A2 | assert |
> | 8c   | column integrity | *(none — deliberately un-numbered)* | assert |
> | 8d   | flag agreement | A3 | **report only — do NOT assert** |
> ```
>
> Review check: within a task file, every assertion label appears exactly once; and every label named in the Master Plan / Sprint Plan / Orchestration resolves to exactly one cell. Duplicate label → ERROR.
>
> Review check: a label whose assert-vs-report disposition differs between two files → ERROR — the failure mode with real execution consequences, since one file treats the label as asserted and a sibling treats it as merely reported.

> [!practice] A deliberately unlabelled cell must say so
> The gap that invites reuse is a cell with an empty Label column. An author scanning the table reads the blank as "not yet filled in" and fills it. Mark it `*(none — deliberately un-numbered)*` so the blank is a statement rather than an invitation.

Catalog row: "Duplicate assertion label within a task file" → ERROR.
Catalog row: "Assert-vs-report disposition mismatch for one label across two files" → ERROR.

---

## Plan-Review Enforcement Summary

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following violations:

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Required Context size drift | A `KiB`/`~Tokens` cell disagrees with a live `measure_files.py` measurement of the cited file by more than ±10% | §9.A.1, §9.A.2 |
| 2 | Placeholder in numerical cell | Any Required Context cell contains `~?`, `~TBD`, or `~?K` | §9.A.2 |
| 3 | Dense-content upper-bound budget | A dense-content Required Context entry (notebook JSON, minified/compressed) uses a looser-than-conservative ratio and the resulting subtotal places the subagent budget within 60K of the 200K ceiling | §9.A.3 |
| 4 | Token Saver large-file ladder not applied | `context.token_saver: true` AND a Required Context file classifies Warn+ (cost or read) but the task carries no recommendation/backlog item; OR a read-reason Critical task is wrongly flagged `1M-exception`; OR a runner-read generated artifact trips the token/byte/line gate without a Multi-Part split | §9.A.8 |
| 5 | Prose count disagrees with the list it summarises | A prose count adjacent to an enumerated list does not match a recount of that list | §9.A.9 |
| 6 | Cross-file enumeration not swept | A plan's item-set change leaves stale cardinality words or a superseded enumerated ID list in a sibling file (Orchestration, Master-Plan row, task file) | §9.A.10 |
| 7 | Action tier contradicts its own evidence tier | A derived status cell in the action tier disagrees with the evidence section's recorded observation for the same item | §9.A.11 |
| 8 | Comparison task sized without reference coverage | A comparison/reconciliation task brief omits the reference-side coverage measurement that should set its size and shape | §9.A.12 |
| 9 | Assertion label and validation cell not 1:1 | A task file enumerating validation cells carries no assertion-label ↔ cell-ID table; or a label appears twice within one task file; or one label's assert-vs-report disposition differs between two files | §9.A.13 |

For the Verify-Before-Cite checks (§9.B: cited-artifact verification, field-name drift, facade re-export, upsert column-presence, Schema Pin / Pre-SQL verification), see [verify-before-cite.md](verify-before-cite.md)'s Plan-Review Enforcement Summary.

---

*Companion files: [session-plan-requirements.md](session-plan-requirements.md), [verify-before-cite.md](verify-before-cite.md), [agent-orchestration-delegated.md](agent-orchestration-delegated.md) §1.1–§1.3 (DELEGATED triggers, task-file error recovery, orchestration context boundary) and §1.4–§1.22 (DELEGATED dispatch protocols).*
