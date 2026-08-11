---
description: Verify-before-cite discipline (lesson IDs, schema files, field names, facade re-exports, upsert helper design, examples-repo version pinning, helper enumeration, field-mapping tables, tiered-fetch tactics) for planwise task files and DELEGATED dispatch prompts
---

# Verify-Before-Cite

**Purpose:** Verify-before-cite discipline (§9.B) for task files — when a task brief asserts something about an external artifact (a lesson ID, a schema file, a column name, a notebook path, a helper function), the planner MUST open and skim that artifact at scaffold time rather than deferring verification to the executing subagent. Split sibling of [task-content-fidelity.md](task-content-fidelity.md), which keeps §9.A Required Context Fidelity.

**Companion files:** [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context Fidelity — split anchor), [schema-pin-requirement.md](schema-pin-requirement.md) (DB-table-specific verify-before-cite for SQL-bearing tasks), [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) (Task File Template, Interface Consumption guidance).

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

#### Reviewer Check 018 — Task Verify-Before-Cite (User-Cited Artifacts)

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** When task brief cites a user-introduced artifact (file path, function name, table name), task MUST verify it exists on disk before authoring dependent instructions.
- **Detection:** Identify cited file paths in Required Context + Execution Steps; Glob each. If 0 matches → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task cites unverified artifact
File: {task file path} | Location: {Required Context | Execution Steps}
Issue: Cited path "{cited_path}" does not resolve on disk
Fix: Verify artifact exists or correct citation per references/verify-before-cite.md §9.B.1 | Confidence: HIGH
```

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

#### Reviewer Check 019 — Task Field-Name Reconciliation

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Identifiers in task brief (`{column}`, `{symbol}`, `{config-field}`, env vars) MUST match live contracts. Detect drift between `{long_form_identifier}` and `{abbreviated_identifier}`.
- **Detection:** Extract identifiers from Execution Steps; grep referenced contract file. 0 matches → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task identifier not reconciled with live contract
File: {task file path} | Location: Execution Steps
Issue: Identifier "{identifier}" not found in cited contract {contract_path}
Fix: Reconcile per references/verify-before-cite.md §9.B.2 | Confidence: HIGH
```

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

#### Reviewer Check 020 — Task Facade Re-Export Verification

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** When task imports/calls a symbol expected to be re-exported by a facade module, task MUST verify the re-export exists.
- **Detection:** Identify imports from facade (e.g., `{src/module/__init__.ext}`); grep facade for re-export. Absent → ERROR.
- **Finding template:**
```
[ERROR] Task facade re-export unverified
File: {task file path} | Location: Execution Steps import statement
Issue: Symbol "{symbol}" not re-exported by facade "{facade_path}"
Fix: Verify per references/verify-before-cite.md §9.B.3 | Confidence: HIGH
```

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

#### Reviewer Check 021 — Task Helper-Function Design Categorization

- **Severity / Role / Type:** WARNING | Task Reviewer | NEW
- **What:** Tasks copying/referencing helpers from another module MUST categorize each as `{copy}`, `{adapt}`, or `{call-via-import}` before authoring presence checks.
- **Detection:** Grep Execution Steps for helper references; check for category tag adjacent. Untagged → WARNING.
- **Finding template:**
```
[WARNING] Task helper-function design not categorized
File: {task file path} | Location: Execution Steps helper reference
Issue: Helper "{symbol}" referenced without {copy|adapt|call-via-import} category
Fix: Categorize per references/verify-before-cite.md §9.B.4 | Confidence: MEDIUM
```

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
rules. Do not renumber these sections. -->

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

#### Reviewer Check 031 — Task Planning-Tier Schema Pin Reconciliation

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Schema Pins in planning-tier docs MUST reconcile against deployed-tier schema (`{schema-file}` / `{schema_glob_path}`).
- **Detection:** Extract Schema Pin block; grep deployed schema for pinned column/constraint names. Unknown → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task Schema Pin planning-vs-deployed drift
File: {task file path} | Location: Schema Pin section
Issue: Pinned identifier "{name}" not found in deployed {schema-file}
Fix: Reconcile per references/verify-before-cite.md §9.B.6 + schema-pin-requirement.md | Confidence: HIGH
```

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

#### Reviewer Check 030 — Task USED-Helper Enumeration

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Tasks copying helpers from reference modules MUST enumerate USED helpers (exactly which functions are called) — not "all helpers from module X".
- **Detection:** Check for `## USED-Helper Enumeration` section. Reference to helper module without enumeration → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task USED-Helper enumeration missing
File: {task file path} | Location: Expected USED-Helper Enumeration section
Issue: Task references helper module without enumerating USED helpers
Fix: Add enumeration per templates/task-file.md | Confidence: HIGH
```

#### Reviewer Check 032 — Task Env Var / Function Signature / Config Key Drift

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** Env vars (`{ENV_VAR_NAME}`), function signatures (`{symbol}`), config keys (`{config-field}`) cited in tasks MUST match live source.
- **Detection:** Extract references; grep live source. Absent → ERROR.
- **Finding template:**
```
[ERROR] Task env/signature/config-key drift
File: {task file path} | Location: Execution Steps
Issue: Reference "{name}" not found in live source "{source_path}"
Fix: Verify per references/verify-before-cite.md §9.B.7 | Confidence: HIGH
```

### 9.B.8 Field-mapping table for consumed data models; `wc -l ≤ 500` output gate

> [!constraint] A task consuming another module's data model MUST carry a field-mapping table, and task-file outputs MUST be gated at `wc -l ≤ 500`
> Two distinct contract-fidelity gates share this subsection:
>
> **Field-mapping table.** When a task's input is another module's data model (a
> struct / dataclass, a typed record, a deserialized payload), the task file MUST
> include a field-mapping table showing which fields are consumed and how — per
> the Interface Consumption guidance in
> [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9. The subagent
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

Cross-referenced by [templates/task-file.md](../templates/task-file.md) (Interface Consumption block) and [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9 (Task File Template).

#### Reviewer Check 029 — Task `wc -l` Pre-COMPLETE Gate

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task Success Criteria MUST include `wc -l` (or equivalent line-count) verification gate before COMPLETE. Orchestrator-level `wc -l` between dispatches also required.
- **Detection:** Grep Success Criteria for `wc -l|line.*count|line-count`. File-producing task lacking line-count gate → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task wc -l pre-COMPLETE gate missing
File: {task file path} | Location: Success Criteria checklist
Issue: File-producing task lacks line-count verification
Fix: Add wc -l gate per references/verify-before-cite.md §9.B.8 | Confidence: HIGH
```

#### Reviewer Check 033 — Task MERGE/Upsert Field Mapping Subsection

- **Severity / Role / Type:** BLOCKER (MERGE/upsert tasks) | Task Reviewer | NEW
- **What:** Tasks performing MERGE/upsert MUST include `### Field Mapping` subsection with Row↔DDL alignment.
- **Detection:** Grep Execution Steps for `MERGE|UPSERT|ON CONFLICT`; check for `^### Field Mapping`. MERGE present + Field Mapping absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] MERGE/upsert task Field Mapping subsection missing
File: {task file path} | Location: Expected ### Field Mapping section
Issue: Task performs MERGE/upsert without Field Mapping
Fix: Add Field Mapping per templates/task-file.md | Confidence: HIGH
```

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

## Plan-Review Enforcement Summary (Verify-Before-Cite)

The structural and content reviewers in `/planwise review` MUST surface BLOCKING findings for the following Verify-Before-Cite violations. Numbering restarts at 1 in this file; for the §9.A Required Context Fidelity rows, see [task-content-fidelity.md](task-content-fidelity.md)'s Enforcement Summary.

| # | Check | Trigger | Source rule |
|---|-------|---------|-------------|
| 1 | Cited artifact verification | A task brief cites a lesson ID, schema file path, or function name that the structural reviewer cannot verify against the cited artifact | §9.B.1 |
| 2 | Field-name drift | A DELEGATED task references a config dataclass field name that does not appear in the cited schema file | §9.B.2 |
| 3 | Facade re-export gap | A plan enforces a facade architecture rule but the facade module does not re-export every type referenced in downstream task briefs | §9.B.3 |
| 4 | Vacuous column-presence check | A task says "verify column X is in INSERT/UPDATE" against an upsert helper that uses dynamic column mapping | §9.B.4 |
| 5 | Missing Schema Pin OR Pre-SQL Schema Verification on SQL-emitting task | A task file's Execution Steps include SQL-emitting verbs against project tables AND the file has neither a Schema Pin section nor a `Pre-SQL Schema Verification` block in Notes for Agent | §9.B.5 |

---

*Anchor: [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context Fidelity — split anchor, R1 filename-frozen). Companion: [schema-pin-requirement.md](schema-pin-requirement.md).*
