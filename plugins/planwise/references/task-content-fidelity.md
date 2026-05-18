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

---

## 9.B Verify-Before-Cite (BINDING)

When a task brief asserts something about an external artifact — a lesson ID, a schema file, a column name, a notebook path, a helper function — the planner MUST open and skim that artifact at scaffold time. Deferring verification to the executing subagent is the load-bearing failure mode; DELEGATED subagents have no shared context with the user and either burn tokens reconciling the brief with reality or, worse, hallucinate content that matches the brief.

The cost is one Read + one Grep per cited artifact. The savings are at minimum one full subagent re-discovery cycle.

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
> (line numbers, cell indices).

A complementary `/planwise plan` enhancement: insert a Step 1.5 ("Verify cited artifacts") between Gather Information and Validate.

### 9.B.2 Field-name reconciliation against the live schema

> [!constraint] DELEGATED task briefs that reference concrete identifiers from another module MUST be reconciled against the live source at dispatch time
> For DELEGATED task prompts that reference concrete code artifacts (config
> dataclass fields, function signatures, column names, table names, enum values),
> audit the prompt against the live artifact AT DISPATCH TIME — not only at
> scaffolding time.
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

---

*Companion files: [session-plan-requirements.md](session-plan-requirements.md), [schema-pin-requirement.md](schema-pin-requirement.md), [agent-orchestration.md](agent-orchestration.md) §11 (DELEGATED dispatch discipline).*
