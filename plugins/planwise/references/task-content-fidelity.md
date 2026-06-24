---
description: Required Context fidelity (measured estimates, freshness across file splits, per-file-type token rate) and verify-before-cite discipline (lesson IDs, schema files, field names, facade re-exports, upsert helper design) for planwise task files
---

# Task Content Fidelity

**Purpose:** Required Context fidelity rules and verify-before-cite discipline for task files. Extends [session-plan-requirements.md](session-plan-requirements.md) §9 (Task File Template) with the §9.A and §9.B subsections; extracted into this sibling file to keep both rule files under the project's 500-line limit.

**Companion files:** [session-plan-requirements.md](session-plan-requirements.md) (Task File Template, Orchestration linkage, completion tracking), [schema-pin-requirement.md](schema-pin-requirement.md) (DB-table-specific verify-before-cite for SQL-bearing tasks).

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

**Cost thresholds (derived, never hardcoded)** — from `token_saver.derive_thresholds(session_target, runner_overhead)`:

```
available_per_task = token_saver_session_target − runner_overhead − growth_margin(6000)
critical           = available_per_task − output_reserve(10000)   # file won't fit a lean task even alone
warn               = min(40000, round(0.5 × available_per_task))   # 40K = guaranteed-warn ceiling
```

`40,000` is the **guaranteed-warn ceiling**: every install warns by at least 40K, but on a heavy install where `0.5 × available_per_task < 40,000` the lower derived value wins. Token counts use the runner model's tokenizer — **13 tok/line** Haiku/Sonnet, **19 tok/line** Opus.

**Read gates (FIXED, per-file readability)** — module-level constants in `scripts/token_saver.py`, NOT `/context`-measured:

```
READ_FILE_BYTE_CAP   = 262144 (256 KiB)  warn 245760 (240 KiB)   # model-independent — measure with `wc -c`
READ_PAGE_CAP_TOKENS = 25000             warn 22000              # tokens = lines × {haiku/sonnet 13, opus 19}
```

The byte gate is measured with **`wc -c`** alongside the line-count `wc -l`; a file can pass `wc -l ≤ 500` yet trip the byte gate when it is dense (tables, JSON). `level = max(cost_level, read_level)`; `reason` records the driver:

| Level | Cost threshold | Read threshold (per assigned model) | Action |
|-------|---------------|-------------------------------------|--------|
| Green | < `warn` AND ≤ ~6.5K tok | < 240 KiB AND < 22K tok | none |
| Notice | > 500 lines or > ~6.5K, < `warn` | — | advisory; docs → Multi-Part split; code → note |
| Warn | ≥ `warn` | ≥ 240 KiB OR ≥ 22K tok | warn + refactor recommendation + file a backlog item |
| Critical / `cost` | ≥ `critical` | — | warn + backlog + flag task **`1M-exception`** (Opus/1M); plan still completes |
| Critical / `read` | — | ≥ 256 KiB OR ≥ 25K model-tok | warn + backlog + **paged read / refactor**; **NOT** `1M-exception` |

> [!constraint] A `read`-reason Critical Is NOT `1M-Exception`-Resolvable
> A **cost-reason** Critical earns the `1M-exception` flag — the file is simply too big for a lean per-task budget, and the 1M window absorbs it. A **read-reason** Critical does NOT: the per-Read page cap is unchanged by the window, and Opus's tokenizer (19 tok/line) trips the token gate *sooner* than Sonnet/Haiku (13 tok/line). The remedy is a **paged read** (`offset`/`limit`/Grep) for read-only context, or **refactor/split + backlog item** for a core or to-be-edited dependency. A source-file Critical is never a hard stop — it advises and files an item.

**Generated-artifact hard-split (§9.A.7 trigger extension).** §9.A.7 declares multi-part splits when output exceeds the 500-line soft limit. When Token Saver is on, the split trigger for **generated artifacts a runner MUST read** (task files, Orchestration, Recovery, Consolidated Context parts, Execution Inputs, task Output files) is **line OR byte OR token gate** — whichever fires first forces a Multi-Part split, and the read-gate ceiling is **HARD**, not advisory. External source files the runner reads but does not generate stay advisory (warn + backlog + read tactics). See `references/session-context-budget.md` [§ File Size Limits — Generated Artifacts](session-context-budget.md#file-size-limits--generated-artifacts-binding-when-token-saver-is-on).

---

## 9.B Verify-Before-Cite (BINDING)

When a task brief asserts something about an external artifact — a lesson ID, a schema file, a column name, a notebook path, a helper function — the planner MUST open and skim that artifact at scaffold time. Deferring verification to the executing subagent is the load-bearing failure mode; DELEGATED subagents have no shared context with the user and either burn tokens reconciling the brief with reality or, worse, hallucinate content that matches the brief.

The cost is one Read + one Grep per cited artifact. The savings are at minimum one full subagent re-discovery cycle.

**External contracts come in many shapes.** A *contract* here is any artifact whose exact shape another piece of work depends on. The rules below are stated for the general case; a database schema is one example among several, not the only one:

| Contract Type | Artifact | What "verify" means |
|---------------|----------|---------------------|
| Database schema | `CREATE TABLE` / `ALTER TABLE` DDL | Column names, types, constraints exist as cited |
| OpenAPI / Swagger spec | `openapi.yaml` / `swagger.json` | Path, operation, request/response schema exist as cited |
| protobuf / gRPC | `.proto` definition | Message, field number/name, service method exist as cited |
| GraphQL SDL | schema `.graphql` | Type, field, query/mutation exist as cited |
| TypeScript declarations | `.d.ts` file | Exported type, member, signature exist as cited |

§9.B.1-§9.B.3 and §9.B.6-§9.B.9 are stated generically for all contract types. §9.B.4 and §9.B.5 are the **database-schema instances** of the general rule and remain stated in DB terms.

For third-party SDK identifiers and shipped artifacts, see `verify-against-shipped-artifact.md`.

### 9.B.1 Verify user-prompt-cited artifacts during scaffolding

> [!constraint] User-cited artifacts MUST be verified at scaffold time, not deferred to the executing subagent
> When a user-provided plan brief names specific artifacts (lesson IDs, schema
> files, notebook paths, helper function names, ticket numbers, doc paths), the
> planner MUST open and skim each cited artifact during scaffolding. If the
> user's framing of the artifact is wrong, the task brief MUST cite the
> corrected reality verbatim and explicitly flag the mis-attribution.
>
> WRONG — accept the user's framing verbatim and propagate it into task briefs:
> ```markdown
> ## Task 02: Read {file} + {lesson-id}
> Catalog {specific content described by user from lesson-id}
> ```
> Real-world cost: the cited lesson had zero of the described content. The
> DELEGATED subagent would either burn tokens trying to find content that does
> not exist OR hallucinate a framing that pollutes downstream Consolidated
> Context Parts.
>
> CORRECT — verify each cited artifact, correct the framing, flag the
> mis-attribution explicitly so it does not re-enter the conversation later:
> ```markdown
> ## Task 02: Read {file} + {lesson-id}
> Catalog the actual content of {lesson-id}. **The user's prompt described it
> as a {user-description-of-lesson} — that is incorrect.** {lesson-id} is about
> {actual-lesson-content}. Report the actual content; do NOT invent a
> {user-description-of-lesson} framing to match the prompt.
> ```
>
> Common artifact types to verify: lesson IDs, schema file paths, notebook paths
> and zone references, helper function names and locations, citation ranges
> (line numbers, cell indices), and external-contract files of any shape —
> OpenAPI / Swagger specs, protobuf `.proto` definitions, GraphQL SDL, and
> TypeScript declaration (`.d.ts`) files.

A complementary `/planwise plan` enhancement: insert a Step 1.5 ("Verify cited artifacts") between Gather Information and Validate.

### 9.B.2 Identifier reconciliation against the live contract

**Note:** Both scaffold-time (§9.B.1) AND dispatch-time verification are mandatory for DELEGATED tasks. This rule extends §9.B.1, it does not replace it.

> [!constraint] DELEGATED task briefs that reference concrete identifiers from another module MUST be reconciled against the live source at dispatch time
> For DELEGATED task prompts that reference concrete code artifacts (config
> dataclass fields, function signatures, column names, table names, enum values),
> audit the prompt against the live artifact AT DISPATCH TIME — not only at
> scaffolding time. The "live contract" is whichever shape the identifier comes
> from — a DB schema, an OpenAPI spec, a protobuf `.proto`, a GraphQL SDL, or a
> TypeScript `.d.ts` — and the reconciliation grep targets that artifact.
>
> Two failure modes share this remediation:
>
> **Mode 1 — Stale paraphrase.** Scaffolding-era specs use abbreviated forms
> that drift from the runtime schema (`{long_form_identifier}` vs
> `{abbreviated_identifier}`).
>
> **Mode 2 — Duplicate-purpose fields.** Task briefs prescribe field names that
> already exist in the target dataclass under a different name; executing the
> brief verbatim would create duplicate fields covering the same semantics.
>
> WRONG (Mode 1) — task brief says `{config-field}-long`; live schema has
> `{config-field}-abbr`. Subagent either implements wrong name (type-checker
> fail) or burns extra tokens reconciling on its own.
>
> WRONG (Mode 2) — task brief specifies new `{config-field}` weights. Live
> `{contract-path}` already declared the same weights under a different name.
> Executing verbatim would produce duplicate fields.
>
> CORRECT — orchestrator greps the live source before authoring (or before
> dispatching), and either reconciles the field names directly OR adds an
> explicit verify-first instruction to the task brief:
>
> ```bash
> # At scaffold time (preferred — fix before commit):
> grep -n "{config-field-pattern}" {contract-path}
> # Compare against the field names in the EI / spec doc.
> # If names differ → reconcile in the brief, not at execution time.
> ```
>
> ```markdown
> # In every DELEGATED task that reads/writes attributes of a configured dataclass:
> ## Notes for Agent
> - The weights parameter type is `{config-class}`. VERIFY attribute names
>   against `{contract-path}` lines {line-range} before implementing — field
>   name drift between this task file and the live schema is a known failure mode.
> ```
>
> The orchestrator MUST propagate any mid-flight reconciliation findings into ALL
> downstream dispatch prompts verbatim. The Recovery file's *Key Findings* table
> is the canonical channel.

A complementary `/planwise review` check: structural reviewer greps the target artifact for each field name mentioned in task files before execution; mismatches are flagged as pre-flight blockers.

### 9.B.3 Pipeline facade re-export verification (architecture-rule plans)

*Generalizes to any single-entry-point contract — a package facade, a barrel / index module, or a declared public API surface.*

> [!constraint] Plans enforcing a facade-import architecture rule MUST verify the facade re-exports everything downstream tasks consume
> When a plan enforces an architecture rule like "consumers import only from
> `{src/module/path}`" (or any equivalent facade restriction), the planner MUST
> grep the facade module and confirm it re-exports every type/function the
> downstream tasks will consume. If the facade is incomplete, add an explicit
> "Verify `{entry-point-file}` re-exports the needed functions; if not, add
> them" step to each affected task — and account for that work in the task
> token estimate.
>
> WRONG — plan declares facade rule; `{src/module/file.ext}` re-exports adapters
> but not algorithm functions; every downstream task hits ImportError on first
> execution. Subagents waste tokens debugging an import-system problem that the
> planner could have caught with one Grep at scaffold time.
>
> CORRECT — at scaffold time:
> ```bash
> grep -nE "^from |^import " {src/module/file.ext}
> ```
> If the facade is incomplete, the plan EITHER:
> 1. Adds an "Update facade" task as a prerequisite step in Sprint 01, OR
> 2. Adds a "Verify facade re-export; add if missing" step to each downstream
>    task and budgets extra tokens per task to cover it.

### 9.B.4 Upsert-helper design verification before authoring column-presence checks

*Database-schema instance of the general verify-before-cite rule (see §9.B intro).*

> [!constraint] Tasks that ask "verify column X is in the INSERT/UPDATE list" MUST first categorize the upsert helper's design
> Before writing a task that requires a column-presence verification on a DB
> upsert helper, open the target function and categorize its design. The
> verification step is meaningful for some designs and vacuous for others.
>
> | Upsert Design | Column-Presence Check |
> |---------------|----------------------|
> | **Static column list** (column names hardcoded in SQL template string) | Meaningful — grep for the new column name in the SQL string |
> | **Dynamic column mapping** (columns derived from row metadata or a config-driven list) | Vacuous — any input column flows through; document the design instead |
> | **Whitelist-filtered dynamic** (dynamic keys filtered against an allowed-set) | Meaningful — verify the new column is in the allowlist |
>
> WRONG — task file with ambiguous verification step:
> ```markdown
> - Verify `{symbol}` accepts the `{column}` column; add it if absent.
> ```
> If the helper uses dynamic column mapping, this step is a no-op disguised as
> work — the column flows through automatically.
>
> CORRECT — task file that acknowledges the upsert design:
> ```markdown
> - Read `{symbol}` in `{db-helper-module}`.
> - If the function uses a static column list (hardcoded in the INSERT SQL),
>   confirm `{column}` is present; add it to the INSERT and UPDATE clauses if
>   absent.
> - If the function uses dynamic column mapping (e.g., from row metadata),
>   record in Recovery Key Findings that no code change is needed; the column
>   flows through the dynamic mapping.
> ```

### 9.B.5 SQL column-name verification for SQL-emitting tasks

*Database-schema instance of the general verify-before-cite rule (see §9.B intro).*

> [!constraint] Tasks that produce inline SQL MUST grep the live schema for EVERY column name BEFORE the query string is written
> Subagents executing SQL-emitting tasks hallucinate column names whenever the
> task brief does not pin the live schema. The Schema Pin requirement
> (`schema-pin-requirement.md`) is the planning-time gate — every task file
> whose Required Context references a DB table MUST include a Schema Pin section
> quoting the live, post-migration column shape. **§9.B.5 is the runtime
> backstop** for the gap that opens when the Schema Pin gate is missed during
> plan-review: the executing subagent (DELEGATED) or the orchestrator (DIRECT)
> MUST grep `{schema_glob_path}` for every column name that will appear in a
> query string and reconcile any drift before emitting the SQL.
>
> Two failure modes share this remediation:
>
> **Mode 1 — Invented column.** Subagent transcribes a column name from memory
> (or from the task brief's prose) that does not exist on the table. Runtime
> fails with `{driver-error-class}: {error-message-pattern}`.
>
> **Mode 2 — Drifted column.** Subagent uses a column name that DID exist at
> scaffold time but was renamed by an intervening migration. Runtime fails the
> same way; harder to diagnose.
>
> WRONG — task file lacks a Schema Pin; subagent writes SQL referencing a
> fictional `{table}.{nonexistent_col}` column:
> ```sql
> SELECT t.{id_col}, t.{nonexistent_col} AS {alias}
> FROM {table} t
> WHERE t.{date_col} >= ?
> ```
> Reality: `{table}` has multiple source-specific name columns, none named
> `{nonexistent_col}`. The query fails on first execution.
>
> CORRECT — grep the live schema for every table the SQL touches BEFORE writing
> the query string:
> ```bash
> # Before authoring the SQL — covers CREATE + ALTER + DROP/ADD COLUMN:
> grep -nE "CREATE TABLE {table}|ALTER TABLE {table}" {schema_glob_path}
> ```
> ```sql
> -- Reconcile to the live shape — pick the consumer-appropriate column
> SELECT t.{id_col}, {actual_col_or_coalesce} AS {alias}
> FROM {table} t
> WHERE t.{date_col} >= ?
> ```
>
> Applies to any task whose Execution Steps include:
> - "build a query against `{table}`"
> - "INSERT INTO `{table}`" / "UPDATE `{table}`" / "DELETE FROM `{table}`"
> - "JOIN `{table}` ON ..."
> - "write a build script that queries `{table}`"
>
> **DIRECT mode** — the orchestrator runs the grep before authoring the SQL.
>
> **DELEGATED mode** — the spawn prompt MUST contain an explicit `Pre-SQL Schema
> Verification` instruction:
>
> ```markdown
> ## Pre-SQL Schema Verification (mandatory before any query is written)
>
> Before emitting ANY SQL string in the output, the executing subagent MUST:
>
> 1. Run: `grep -nE "CREATE TABLE {table}|ALTER TABLE {table}" {schema_glob_path}`
>    for each table the SQL touches.
> 2. List every column name that will appear in the SQL.
> 3. Verify each listed column appears in the grep output — including any
>    post-migration ALTER blocks.
> 4. If any column does not match: HALT, report the discrepancy in Recovery's
>    Issues Identified, and request the orchestrator clarify. Do NOT guess.
> 5. After verification: write the SQL using only verified column names.
> ```
>
> Plan-review enforcement: `/planwise review` flags as a BLOCKING finding any
> task file whose Execution Steps mention writing SQL against project tables AND
> lacks BOTH (a) a Schema Pin section per `schema-pin-requirement.md` AND (b) a
> `Pre-SQL Schema Verification` instruction in the Notes for Agent.

### 9.B.6 Verify examples-repo citations against the pinned version

<!-- Canonical numbering: §9.B.6-§9.B.9 are the canonical numbers for these four
rules. handlers/review.md:608 (Error Pattern Catalog row 18) currently mis-cites
them as §9.B.11-§9.B.14; Sprint-07 session S07-02 repoints that citation to
§9.B.6-§9.B.9. Do not renumber these sections. -->

> [!constraint] An example cited from a versioned examples repository MUST be verified against the version the project actually pins
> When a task brief cites a code sample, config snippet, or usage pattern drawn
> from an external **examples repository** (an SDK examples repo, a framework
> cookbook, a sample-app repo), the planner MUST verify the cited example against
> the *exact version* the consuming project pins — not the examples repo's
> default branch. Examples repos track their library's latest release; a project
> pinned to an older (or pre-release) version may need a materially different form.
>
> WRONG — cite a sample from the examples repo's `main` branch:
> ```markdown
> ## Notes for Agent
> - Follow the {feature} example in {examples-repo} for the call shape.
> ```
> The project pins `{library}@{pinned-version}`; the `main`-branch example uses
> an API that exists only in `{newer-version}`. The subagent writes code that
> fails to resolve against the pinned version.
>
> CORRECT — pin the example to the consumed version and cite the matching ref:
> ```markdown
> ## Notes for Agent
> - The project pins `{library}@{pinned-version}` (see {manifest-file}).
>   Follow the {feature} example from {examples-repo} at tag/branch
>   `{ref-matching-pinned-version}` — NOT `main`. If the pinned version predates
>   the example, adapt the older call shape and note the divergence.
> ```

Applies to any task whose brief cites an external examples / cookbook / sample repository for an API usage pattern — verify the example against the project's pinned dependency version.

### 9.B.7 Enumerate the specific helpers a spawn prompt tells an agent to use

> [!constraint] A spawn prompt that says "use the project's helpers" MUST enumerate the specific helpers — name, location, signature
> When a DELEGATED task's spawn prompt instructs the executing subagent to "use
> the existing helpers", "reuse the project's utilities", or any equivalent
> blanket phrasing, the prompt MUST instead enumerate each helper the task is
> expected to use: its name, the file it lives in, and its signature (or a
> one-line contract). A subagent has no shared context — a blanket instruction
> forces it to either re-discover the helper set (token burn) or reimplement
> functionality that already exists (duplication).
>
> WRONG — blanket reuse instruction:
> ```markdown
> ## Notes for Agent
> - Use the project's existing helpers; do not reinvent utilities.
> ```
>
> CORRECT — enumerate the USED helpers explicitly:
> ```markdown
> ## Notes for Agent — Helpers to use (do not reimplement)
> | Helper | Location | Signature / contract |
> |--------|----------|----------------------|
> | {helper-1} | {module-path} | {signature} |
> | {helper-2} | {module-path} | {signature} |
>
> Use ONLY these; if a needed helper is absent, report it in Recovery rather
> than inventing one.
> ```

Cross-referenced by [templates/task-file.md](../templates/task-file.md) (Notes for Agent guidance) and the `/planwise review` reviewer check for blanket-helper references.

### 9.B.8 Field-mapping table for consumed data models; `wc -l ≤ 500` output gate

> [!constraint] A task consuming another module's data model MUST carry a field-mapping table, and task-file outputs MUST be gated at `wc -l ≤ 500`
> Two distinct contract-fidelity gates share this subsection:
>
> **Field-mapping table.** When a task's input is another module's data model (a
> struct / dataclass, a typed record, a deserialized payload), the task file MUST
> include a field-mapping table showing which fields are consumed and how — per
> the Interface Consumption guidance in
> [session-plan-requirements.md](session-plan-requirements.md) §9. The subagent
> must not infer the consumed fields from the type's name. For **MERGE / upsert**
> task briefs specifically, the field-mapping table MUST also state the Row↔DDL
> alignment strategy — which row field maps to which target column, and how name
> or position mismatches are resolved.
>
> **`wc -l ≤ 500` output gate.** A task whose output is itself a task file (or
> any plan artifact) MUST be gated so the produced file satisfies `wc -l ≤ 500` —
> the project soft limit. If the projected output exceeds it, pre-split per §9.A.7.
>
> WRONG — consume a data model with no field map; emit a 700-line task file:
> ```markdown
> ## Execution Steps
> 1. Read {ModelType} and generate the downstream config.
> ```
>
> CORRECT — field-mapping table + explicit output-size gate:
> ```markdown
> ## Execution Steps
> 1. Read {ModelType}; consume only the mapped fields:
>
>    | Input Field | Used For |
>    |-------------|----------|
>    | {field-a} | {purpose} |
>    | {field-b} | {purpose} |
>
> 2. Emit the config; verify `wc -l` of each produced file ≤ 500 (pre-split
>    per §9.A.7 if not).
> ```

Cross-referenced by [templates/task-file.md](../templates/task-file.md) (Interface Consumption block) and [session-plan-requirements.md](session-plan-requirements.md) §9 (Task File Template).

### 9.B.9 Tiered-fetch tactics for large external sources

> [!constraint] A task that fetches from a large external source MUST use the tiered-fetch ladder — cheapest probe first
> When a task must pull data from a large external source (a web page, a
> paginated API, a large remote document, a registry), the task file MUST
> prescribe a tiered-fetch ladder rather than an unbounded "fetch the source"
> instruction. Start with the cheapest probe that can answer the question and
> escalate only on a miss. An unbounded fetch either blows the subagent's context
> budget or fails silently on a source larger than expected.
>
> Tiered-fetch ladder (cheapest → most expensive):
>
> | Tier | Probe | Use When |
> |------|-------|----------|
> | 1 | Targeted query / search / `HEAD` request | A specific fact or existence check is all that is needed |
> | 2 | Single section / page / paginated slice | The relevant content is a known sub-range |
> | 3 | Full fetch with an explicit size cap + budget note | The whole source is genuinely required |
>
> WRONG — unbounded fetch:
> ```markdown
> - Fetch {external-source} and extract {data}.
> ```
>
> CORRECT — laddered fetch with a stop-at-first-hit rule:
> ```markdown
> - Tier 1: query {external-source} for `{specific-key}`; if found, stop.
> - Tier 2: on a miss, fetch the `{known-section}` slice only.
> - Tier 3: on a miss, full-fetch with a {N}K cap; if the cap is hit, report in
>   Recovery rather than truncating silently.
> ```

Applies to tasks that fetch from web pages, paginated APIs, large remote documents, or external registries.

---

## Plan-Review Enforcement Summary

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following violations:

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Required Context line drift | A `Est. Lines` cell disagrees with live `wc -l` of the cited file by more than ±10% | §9.A.1, §9.A.2 |
| 2 | Placeholder in numerical cell | Any Required Context cell contains `~?`, `~TBD`, or `~?K` | §9.A.2 |
| 3 | Notebook upper-bound budget | A notebook Required Context entry uses 13 tok/line and the resulting subtotal places the subagent budget within 60K of the 200K ceiling | §9.A.3 |
| 4 | Cited artifact verification | A task brief cites a lesson ID, schema file path, or function name that the structural reviewer cannot verify against the cited artifact | §9.B.1 |
| 5 | Field-name drift | A DELEGATED task references a config dataclass field name that does not appear in the cited schema file | §9.B.2 |
| 6 | Facade re-export gap | A plan enforces a facade architecture rule but the facade module does not re-export every type referenced in downstream task briefs | §9.B.3 |
| 7 | Vacuous column-presence check | A task says "verify column X is in INSERT/UPDATE" against an upsert helper that uses dynamic column mapping | §9.B.4 |
| 8 | Missing Schema Pin OR Pre-SQL Schema Verification on SQL-emitting task | A task file's Execution Steps include SQL-emitting verbs against project tables AND the file has neither a Schema Pin section nor a `Pre-SQL Schema Verification` block in Notes for Agent | §9.B.5 |
| 9 | Token Saver large-file ladder not applied | `context.token_saver: true` AND a Required Context file classifies Warn+ (cost or read) but the task carries no recommendation/backlog item; OR a read-reason Critical task is wrongly flagged `1M-exception`; OR a runner-read generated artifact trips the line/byte/token gate without a Multi-Part split | §9.A.8 |

---

*Companion files: [session-plan-requirements.md](session-plan-requirements.md), [schema-pin-requirement.md](schema-pin-requirement.md), [agent-orchestration.md](agent-orchestration.md) §11 (DELEGATED triggers, task-file error recovery, orchestration context boundary) and [agent-orchestration-delegated.md](agent-orchestration-delegated.md) (§1.4–§1.15 DELEGATED dispatch protocols).*
