---
description: Required Context fidelity — measured estimates, freshness across file splits, per-file-type token rate, and the Token Saver large-file ladder — for planwise task files
---

# Task Content Fidelity

**Purpose:** Required Context fidelity rules (§9.A) for task files — measured estimates that stay fresh across file splits, per-file-type token rates, and the Token Saver large-file classification ladder. Extends [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9 (Task File Template) with the §9.A subsection; extracted into this sibling file to keep both rule files under the project's 500-line limit. Verify-before-cite discipline (§9.B) is the split sibling [verify-before-cite.md](verify-before-cite.md).

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
> - `Est. Lines` cells (re-run `wc -l`)
> - `Est. Tokens` cells (re-derive from new line count)
> - Context subtotal and the task header's `Estimated Tokens`
>
> WRONG — Task 1 splits `{schema-file}` into `{schema-file-A}` ({N_A} lines)
> and `{schema-file-B}` ({N_B} lines); Task 2's Required Context still
> references `{schema-file}` (~{old_N} lines) and is unchanged. The Task 2
> subagent reads a file that no longer exists OR reads only one of the two
> splits and silently misses the second part.
>
> CORRECT — after Task 1 completes, the planner (or the Task 1 subagent in its
> post-task hand-off) updates Task 2's Required Context to:
> ```
> | 1 | {schema-file-A} | ~{N_A} | ~{T_A}K | {purpose A} |
> | 1 | {schema-file-B} | ~{N_B} | ~{T_B}K | {purpose B} |
> ```
> and re-derives the Context subtotal and task header `Estimated Tokens`. The
> `Last verified:` comment in the Required Context block (if used) is bumped to
> the current date.

Applies to any planwise plan with sequential task dependencies, output-chaining sessions, and plans that may trigger 500-line file splits during execution.

### 9.A.2 Token estimates use measured values — no `~?` placeholders

> [!constraint] Required Context numerical cells MUST be measured, not placeholder
> Every `Est. Lines` cell MUST be a measured value (`wc -l` of the file path);
> every `Est. Tokens` cell MUST be derived from the measured line count using
> the project's standard token rate (see §9.A.3 for the per-file-type rate).
> Placeholders like `~?`, `~TBD`, or qualitative ranges without an arithmetic
> basis fail review.
>
> WRONG — placeholders that bypass measurement, breaking task-header
> reconciliation:
> ```markdown
> | Priority | File | Est. Lines | Est. Tokens | Purpose |
> |----------|------|-----------|-------------|---------|
> | 1 | {src/module/file_A.ext} | ~? | ~{T}K | {purpose} |
> | 1 | {src/module/file_B.ext} | ~? | ~{T}K | {purpose} |
>
> Context subtotal: ~{total}K reads + ~{out}K output = ~{total}K total
> ```
> Real-world cost: the actual files were far larger than estimated; the cascade
> invalidated session and sprint-level totals.
>
> CORRECT — measured line counts, derived token estimates, reconciled subtotal:
> ```markdown
> | Priority | File | Est. Lines | Est. Tokens | Purpose |
> |----------|------|-----------|-------------|---------|
> | 1 | {src/module/file_A.ext} | ~{N_A}  | ~{T_A}K   | {purpose} |
> | 1 | {src/module/file_B.ext} | ~{N_B}  | ~{T_B}K   | {purpose} |
>
> Context subtotal: ~{reads_total}K reads + ~{out}K output = ~{grand_total}K total
> ```

For files that may legitimately not exist (conditional reads via `Glob`), use `conditional` in the `Est. Tokens` column rather than a numerical placeholder.

A complementary `/planwise review` check rejects any plan whose task files contain `~?`, `~TBD`, or `~?K` literals in Required Context numerical cells.

### 9.A.3 Per-file-type token rate

> [!constraint] Use `~13 tokens/line` as the universal estimate; denser file types may run higher — measure if uncertain
> The project's standard 13 tok/line rate is calibrated for prose and source
> code where most lines have meaningful identifiers and whitespace. Denser file
> types (notebooks, minified output) may run higher — measure if uncertain
> rather than defaulting to a lower estimate.
>
> WRONG — single-rate estimate that hides variance, then contradicts itself in
> Notes:
> ```markdown
> | 1 | {notebook-dir}/{notebook-file} | ~{N} | ~{T}K | Source for Analysis |
>
> ## Notes for Agent
> - Notebook is large (~{larger_T}K tokens). Read it fully...
> ```
>
> CORRECT — explicit rate acknowledgment, conservative estimate in the table,
> upper-bound budget called out in Notes:
> ```markdown
> | 1 | {notebook-dir}/{notebook-file} | ~{N} (JSON) | ~{T}K | Source for Analysis — read full file ({notebook-exec-cmd} format; rate may run higher than 13 tok/line; budget reflects ~13 tok/line conservative estimate) |
>
> ## Notes for Agent
> - Notebook is large ({N} lines JSON; ~{T}K at 13 tok/line, may run
>   higher at notebook JSON's greater density).
>   Subagent budget: ~{task_T}K + 54K overhead = ~{total_T}K, well within 200K.
> ```
>
> Per-file-type rate table:
>
> | File Type | Approx. Tokens | Heuristic |
> |-----------|----------------|-----------|
> | Source code | ~13 tok/line | Project standard |
> | Markdown / prose (`.md`) | ~13 tok/line | Project standard |
> | YAML / config | ~10–13 tok/line | Often slightly under |
> | SQL DDL (`.sql`) | ~13 tok/line | Project standard |
> | Notebook JSON | ~13–20 tok/line | Use 13 for the table; budget the upper bound when subagent budget margin is tight (>140K including overhead) |
> | Plain text logs | ~10 tok/line | Often light |
> | Minified / bundled JS | ~30–60 tok/line | Very high density — few line breaks, long lines; never assume 13, measure per file |
> | Compressed JSON | ~20–40 tok/line | Dense single-line or near-single-line structures; measure when it dominates a task's budget |
>
> The `Est. Lines` value fed to the token rate band MUST come from `wc -l <path>` on the actual file — NOT from the last line number observed in a `Read` tool output. `Read` may paginate (default cap ~2000 lines / ~25K tokens); a partial read produces a lower number that underestimates the token cost and silently misroutes the file in the §9.A.8 Large-File Ladder.

### 9.A.4 Re-glob file-set counts at task-author time

> [!constraint] Glob-cited file-set counts MUST be re-globbed when the task file is authored, not copied from an upstream estimate
> When a task's Required Context cites a file-set by glob pattern (e.g.
> `references/*.md`, `src/**/*.ext`), the file count and the derived
> `Est. Lines` / `Est. Tokens` cells MUST be produced by running the glob at
> task-author time. A count copied from an upstream plan, an earlier sprint's
> estimate, or the Master Plan's Sprint Overview is stale the moment any task
> adds, splits, or deletes a matching file.
>
> WRONG — task cites `{glob-pattern}` and reuses the "{N} files" figure from the
> sprint plan written several sessions earlier:
> ```markdown
> | 1 | {glob-pattern} | ~{N} files, ~{old_L} lines | ~{old_T}K | {purpose} |
> ```
> Two intervening tasks added files matching `{glob-pattern}`; the subagent's
> real read is larger than budgeted and the session total is wrong.
>
> CORRECT — re-glob when the task file is authored and record the live count:
> ```markdown
> <!-- Re-globbed {YYYY-MM-DD}: {glob-pattern} → {N} files, {L} lines total -->
> | 1 | {glob-pattern} | {N} files, ~{L} lines | ~{T}K | {purpose} |
> ```
> The `Est. Tokens` cell is re-derived from the live line total per §9.A.3, and
> the Context subtotal and task header are reconciled per §9.A.2.

Applies to any task whose Required Context references files by glob rather than by individual path — especially plans where earlier tasks create or split files that the glob matches.

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

### 9.A.6 Cite the generator, not the walked file-set, for large generated inputs

> [!constraint] When a task's Required Context is produced by a generator walking ≥100 files (or a tree totaling ≥10K lines), cite the generator and its input root — not the individual files
> If a task consumes input produced by a script or tool that walks a large file
> tree — **≥100 files, OR a tree totaling ≥10K lines** — the Required Context
> table MUST cite (a) the generator command or script and (b) its input root
> directory — NOT 100+ individual file rows. Enumerating every walked file bloats
> the task file past the 500-line limit, makes the `Est. Lines` arithmetic
> unauditable, and goes stale the instant one file is added.
>
> WRONG — 100+ rows, one per walked file:
> ```markdown
> | 1 | {input-root}/file-001.ext | ~{L} | ~{T}K | walked |
> | 1 | {input-root}/file-002.ext | ~{L} | ~{T}K | walked |
> | 1 | ... 130 more rows ... | | | |
> ```
>
> CORRECT — cite the generator + input root + the generated artifact:
> ```markdown
> | 1 | {generator-cmd} over {input-root}/ ({N} files) | ~{L} | ~{T}K | input produced by the generator; do not enumerate the walked tree |
> | 1 | {generated-output-path} | ~{L2} | ~{T2}K | the generator's consolidated output — this is what the task reads |
> ```
> The `Est. Lines` / `Est. Tokens` cells reflect the generator's *output* (what
> the subagent actually reads), not the sum of the walked tree.

Applies to tasks fed by codebase-scan scripts, doc-index generators, manifest builders, or any tool whose input is a directory walk of ≥100 files or ≥10K total lines.

### 9.A.7 Declare multi-artifact output splits at plan-author time

> [!constraint] When a task's output would exceed the 500-line soft limit, the split MUST be declared in the task file at plan-author time
> If a task's Expected Output is projected to exceed the 500-line soft limit (see
> [session-context-budget.md](session-context-budget.md) File Size Limits), the
> planner MUST declare the multi-part split in the task file — naming each part
> and its topic — rather than leaving the executing subagent to discover the
> overflow and improvise a split mid-task.
>
> WRONG — single output path for an output that will not fit:
> ```markdown
> **Output:** Outputs/{Abbrev}-{artifact}.md
> <!-- projected ~900 lines -->
> ```
> The subagent writes 900 lines into one file (violating the limit) or invents an
> ad-hoc split with names no downstream task references.
>
> CORRECT — pre-declare the split with the Multi-Part Output Convention:
> ```markdown
> **Output:** (projected ~900 lines — pre-split per §9.A.7)
> - Outputs/{Abbrev}-{artifact}-Part-1-{Topic}.md  (~450 lines)
> - Outputs/{Abbrev}-{artifact}-Part-2-{Topic}.md  (~450 lines)
> ```
> Each part stays under 500 lines, carries a descriptive topic suffix, and is
> self-contained enough to feed a downstream task per the Multi-Part Output
> Convention.

Applies to any task — spec authoring, consolidation, large code generation — whose Expected Output is projected past the 500-line soft limit.

### 9.A.8 Token Saver Large-File Ladder

This subsection is the **per-task-file enforcement anchor** the `handlers/plan.md` Step 8c scan (and its Scaffolding Step 5 mirror) implement and that `/planwise review` checks against. It documents the graduated warning ladder, the threshold-derivation formulas, the two FIXED Read-tool gates the ladder folds in, and the `reason=cost|read` distinction. Active only when `context.token_saver: true`; when false, the §9.A token-estimation rules above stand alone.

> [!constraint] Every Required Context file MUST be classified against the folded cost + read ladder when Token Saver is on
> When `context.token_saver: true`, each task's Required Context file MUST be classified by `token_saver.classify_file(path, model, projected_added_lines, thresholds)`, which returns `{level, reason}` where `level = max(cost_level, read_level)`. A file the same task will modify MUST be classified on `current + projected delta` (pass `projected_added_lines`) so a file that *will* cross a gate post-edit is flagged pre-emptively — not after the runner overflows mid-task.
>
> WRONG — a 1,900-line module is classified at its current size only; the task adds ~250 lines, pushing it past the per-model token page-cap, but the scan passes it Green and the runner gets a truncated Read mid-edit:
> ```
> classify_file(path, model="opus")                       # projected_added_lines defaults to 0 → Green
> ```
> CORRECT — classify on current + projected delta so the will-exceed case is caught at plan-author time:
> ```
> classify_file(path, model="opus", projected_added_lines=250, thresholds=th)   # → {level: Critical, reason: read}
> ```

**Canonical homes — do not restate.** The cost-threshold derivation formulas (`available_per_task`, `critical`, `warn`) are computed by `token_saver.derive_thresholds()`; see [token-saver-profile.md](token-saver-profile.md) § Token Saver Threshold Derivation for the formulas and the `40,000`-guaranteed-warn-ceiling explanation. The Read tool's two FIXED mechanical gates — `READ_FILE_BYTE_CAP` / `READ_PAGE_CAP_TOKENS`, their byte/token values and warn bands, the per-model tokenizer rate (13 tok/line Sonnet/Haiku, 19 tok/line Opus), and the `wc -c`-alongside-`wc -l` measurement discipline — live in [session-context-budget.md](session-context-budget.md) § Read-Tool Hard Limits. Both are module-level constants in `scripts/token_saver.py`, NOT `/context`-measured.

`level = max(cost_level, read_level)`; `reason` records the driver:

| Level | Cost threshold | Read threshold (per assigned model) | Action |
|-------|---------------|-------------------------------------|--------|
| Green | < `warn` AND ≤ ~6.5K tok | < 240 KiB AND < 22K tok | none |
| Notice | > 500 lines or > ~6.5K, < `warn` | — | advisory; docs → Multi-Part split; code → note |
| Warn | ≥ `warn` | ≥ 240 KiB OR ≥ 22K tok | warn + refactor recommendation + file a backlog item |
| Critical / `cost` | ≥ `critical` | — | warn + backlog + flag task **`1M-exception`** (Opus/1M); plan still completes |
| Critical / `read` | — | ≥ 256 KiB OR ≥ 25K model-tok | warn + backlog + **paged read / refactor**; **NOT** `1M-exception` |

> [!constraint] A `read`-reason Critical Is NOT `1M-Exception`-Resolvable
> A **cost-reason** Critical earns the `1M-exception` flag — the file is simply too big for a lean per-task budget, and the 1M window absorbs it. A **read-reason** Critical does NOT: the per-Read page cap is unchanged by the window, and Opus's tokenizer (19 tok/line) trips the token gate *sooner* than Sonnet/Haiku (13 tok/line). The remedy is a **paged read** (`offset`/`limit`/Grep) for read-only context, or **refactor/split + backlog item** for a core or to-be-edited dependency. A source-file Critical is never a hard stop — it advises and files an item.

**Single oversized file vs. per-task sum.** On a default/light install the cost bands sit *above* the FIXED 25K read cap (`warn` is 40K, derived `critical` higher still), so any single file large enough to be cost-Warn/Critical has already crossed the read gate — it classifies `reason=read` (paged-read/refactor), **never** cost-`1M-exception`. Cost-`1M-exception` therefore surfaces for a single file only on a **heavy** install where derived `critical` drops below 25K; otherwise it fires on a **per-task sum** of several mid-size files whose combined estimate trips `critical` while no single file trips the read cap. Do **not** expect a lone giant file to be `1M-exception`'d on a default install — that is the intended `max(cost, read)` + ties-go-to-`read` behavior, not a miss.

**Generated-artifact hard-split (§9.A.7 trigger extension).** §9.A.7 declares multi-part splits when output exceeds the 500-line soft limit. When Token Saver is on, the split trigger for **generated artifacts a runner MUST read** (task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files) is **line OR byte OR token gate** — whichever fires first forces a Multi-Part split, and the read-gate ceiling is **HARD**, not advisory. External source files the runner reads but does not generate stay advisory (warn + backlog + read tactics). See `references/session-context-budget.md` [§ File Size Limits — Generated Artifacts](session-context-budget.md#file-size-limits--generated-artifacts-binding-when-token-saver-is-on).

---

## Plan-Review Enforcement Summary

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following violations:

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Required Context line drift | A `Est. Lines` cell disagrees with live `wc -l` of the cited file by more than ±10% | §9.A.1, §9.A.2 |
| 2 | Placeholder in numerical cell | Any Required Context cell contains `~?`, `~TBD`, or `~?K` | §9.A.2 |
| 3 | Notebook upper-bound budget | A notebook Required Context entry uses 13 tok/line and the resulting subtotal places the subagent budget within 60K of the 200K ceiling | §9.A.3 |
| 4 | Token Saver large-file ladder not applied | `context.token_saver: true` AND a Required Context file classifies Warn+ (cost or read) but the task carries no recommendation/backlog item; OR a read-reason Critical task is wrongly flagged `1M-exception`; OR a runner-read generated artifact trips the line/byte/token gate without a Multi-Part split | §9.A.8 |

For the Verify-Before-Cite checks (§9.B: cited-artifact verification, field-name drift, facade re-export, upsert column-presence, Schema Pin / Pre-SQL verification), see [verify-before-cite.md](verify-before-cite.md)'s Plan-Review Enforcement Summary.

---

*Companion files: [session-plan-requirements.md](session-plan-requirements.md), [verify-before-cite.md](verify-before-cite.md), [agent-orchestration-delegated.md](agent-orchestration-delegated.md) §1.1–§1.3 (DELEGATED triggers, task-file error recovery, orchestration context boundary) and §1.4–§1.15 (DELEGATED dispatch protocols).*
