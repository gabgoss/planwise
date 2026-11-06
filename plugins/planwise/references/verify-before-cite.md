---
description: Verify-before-cite discipline (lesson IDs, schema files, field names, facade re-exports, upsert helper design, examples-repo version pinning, helper enumeration, field-mapping tables, tiered-fetch tactics, splitting an exemplar comparison into shape rows judged against the exemplar and data rows judged against the live source, tracing each hazard a guard names to a mechanism in code before the guard is retired, stating the signature outcome when a documentation check shows an inherited parameter is unsupported, and checking a brief's claim about an external source's coverage against the probe document it cites) for planwise task files and DELEGATED dispatch prompts
consult-when: A task brief cites a lesson ID, schema file, or field name — open and skim it before citing, split an exemplar comparison into shape rows and data rows, trace each hazard before retiring a guard, state the signature outcome when a documentation check shows an inherited parameter is unsupported, check a brief's claim about an external source's coverage against the probe document it cites
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
| Database schema | `CREATE TABLE` / `ALTER TABLE` DDL | Column names, types, constraints exist as cited. For a column the brief filters with a literal, the literal sits in the measured value vocabulary (`schema-pin-requirement.md` §5.1) |
| OpenAPI / Swagger spec | `openapi.yaml` / `swagger.json` | Path, operation, request/response schema exist as cited |
| protobuf / gRPC | `.proto` definition | Message, field number/name, service method exist as cited |
| GraphQL SDL | schema `.graphql` | Type, field, query/mutation exist as cited |
| TypeScript declarations | `.d.ts` file | Exported type, member, signature exist as cited |

§9.B.1-§9.B.3 and §9.B.6-§9.B.9 are stated generically for all contract types. §9.B.4 and §9.B.5 are the **database-schema instances** of the general rule and remain stated in DB terms.

For third-party SDK identifiers and shipped artifacts, see `verify-against-shipped-artifact.md`.

### 9.B.1 Verify user-prompt-cited artifacts during scaffolding

> [!constraint] User-cited artifacts MUST be verified at scaffold time, not deferred to the executing subagent
> When a user-provided plan brief names specific artifacts, the planner MUST open and skim each cited artifact during scaffolding. These include lesson IDs, schema file paths, notebook paths and zone references, helper function names and locations, ticket numbers, doc paths, citation ranges (line numbers, cell indices), and external-contract files of any shape. If the user's framing of an artifact is wrong, the task brief MUST cite the corrected reality verbatim and explicitly flag the mis-attribution.
>
> WRONG — accept the user's framing and propagate it: `Catalog {specific content described by user from lesson-id}`.
>
> CORRECT — correct the framing and flag it: `Catalog the actual content of {lesson-id}. The user's prompt described it as a {user-description-of-lesson}; that is incorrect. Do NOT invent that framing.`

The path mode of `scripts/check_section_citations.py` (`--paths {task-file}`) reports a cited path that does not resolve on disk.

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
> For DELEGATED task prompts that reference concrete code artifacts (config dataclass fields, function signatures, column names, table names, enum values), audit the prompt against the live artifact AT DISPATCH TIME — not only at scaffolding time. The "live contract" is whichever shape the identifier comes from — a DB schema, an OpenAPI spec, a protobuf `.proto`, a GraphQL SDL, or a TypeScript `.d.ts` — and the reconciliation search targets that artifact.
>
> Two failure modes share this remediation:
>
> **Mode 1 — Stale paraphrase.** Scaffolding-era specs use abbreviated forms that drift from the runtime schema (`{long_form_identifier}` vs `{abbreviated_identifier}`).
>
> **Mode 2 — Duplicate-purpose fields.** Task briefs prescribe field names that already exist in the target dataclass under a different name. Executing the brief verbatim would create duplicate fields covering the same semantics.
>
> WRONG — the brief says `{config-field}-long` and the live schema has `{config-field}-abbr` (Mode 1), or the brief adds `{config-field}` weights that the live `{contract-path}` already declares under another name (Mode 2).
>
> CORRECT — search the live source before authoring (preferred) or before dispatching. If names differ, reconcile them in the brief, not at execution time, or add a verify-first line to Notes for Agent:
> ```
> Grep  pattern='{config-field-pattern}'  path='{contract-path}'  output_mode='content'
> - VERIFY attribute names against `{contract-path}` lines {line-range} before implementing.
> ```
>
> The orchestrator MUST propagate any mid-flight reconciliation findings into ALL downstream dispatch prompts verbatim. The Recovery file's *Key Findings* table is the canonical channel.

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
> When a plan enforces a rule like "consumers import only from `{src/module/path}`", the planner MUST search the facade module for every type and function the downstream tasks consume.
>
> WRONG — declare the facade rule without checking it, so every downstream task hits ImportError on first execution.
>
> CORRECT — run `Grep pattern='^from |^import ' path='{src/module/file.ext}'` at scaffold time. If the facade is incomplete, the plan adds an "Update facade" prerequisite task, or adds a "Verify `{entry-point-file}` re-exports the needed functions; if not, add them" step to each downstream task and budgets extra tokens for it.

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
> Open the target function and categorize its design first. The check is meaningful for some designs and vacuous for others.
>
> | Upsert Design | Column-Presence Check |
> |---------------|----------------------|
> | **Static column list** (column names hardcoded in SQL template string) | Meaningful — search for the new column name in the SQL string |
> | **Dynamic column mapping** (columns derived from row metadata or a config-driven list) | Vacuous — any input column flows through; document the design instead |
> | **Whitelist-filtered dynamic** (dynamic keys filtered against an allowed-set) | Meaningful — verify the new column is in the allowlist |
>
> WRONG — `Verify {symbol} accepts the {column} column; add it if absent.` Under dynamic mapping this step is a no-op disguised as work.
>
> CORRECT — read `{symbol}` first. For a static list, confirm `{column}` is in the INSERT and UPDATE clauses and add it if absent. For dynamic mapping, record in Recovery Key Findings that no code change is needed.

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

> [!constraint] Tasks that produce inline SQL MUST search the live schema for EVERY column name BEFORE the query string is written
> Subagents hallucinate column names whenever the task brief does not pin the live schema. The Schema Pin requirement (`schema-pin-requirement.md`) is the planning-time gate: every task file whose Required Context references a DB table MUST include a Schema Pin section quoting the live, post-migration column shape. **§9.B.5 is the runtime backstop** for the gap that opens when plan-review misses that gate. The executing subagent (DELEGATED) or the orchestrator (DIRECT) MUST search `{schema_glob_path}` for every column name that will appear in a query string, and reconcile any drift before emitting the SQL.
>
> Two failure modes share this remediation:
>
> **Mode 1 — Invented column.** The subagent transcribes a column name from memory or from the brief's prose, and the table has no such column. Runtime fails with `{driver-error-class}: {error-message-pattern}`.
>
> **Mode 2 — Drifted column.** An intervening migration renamed a column that existed at scaffold time. Runtime fails the same way, and the cause is harder to diagnose.
>
> WRONG — the task file lacks a Schema Pin, and the subagent writes `SELECT t.{nonexistent_col} FROM {table} t`.
>
> CORRECT — search the live schema for every table the SQL touches, covering CREATE + ALTER + DROP/ADD COLUMN, then write `SELECT {actual_col_or_coalesce} FROM {table} t`.
>
> Applies to any task whose Execution Steps build a query against `{table}`, run INSERT INTO, UPDATE or DELETE FROM `{table}`, JOIN `{table}`, or write a build script that queries `{table}`.
>
> **DIRECT mode** — the orchestrator runs the search before authoring the SQL.
>
> **DELEGATED mode** — the spawn prompt MUST contain an explicit `Pre-SQL Schema Verification` instruction:
>
> ```markdown
> ## Pre-SQL Schema Verification (mandatory before any query is written)
>
> 1. Run `Grep pattern='CREATE TABLE {table}|ALTER TABLE {table}' path='{schema_glob_path}'`
>    for each table the SQL touches.
> 2. List every column name that will appear in the SQL.
> 3. Verify each listed column appears in the search output, including post-migration ALTER blocks.
> 4. If any column does not match: HALT, report the discrepancy in Recovery's
>    Issues Identified, and request the orchestrator clarify. Do NOT guess.
> 5. After verification: write the SQL using only verified column names.
> ```
>
> Plan-review enforcement: `/planwise review` flags as a BLOCKING finding any task file whose Execution Steps mention writing SQL against project tables AND lacks BOTH (a) a Schema Pin section per `schema-pin-requirement.md` AND (b) a `Pre-SQL Schema Verification` instruction in the Notes for Agent.

The rule `schema-pin` in `scripts/lint_task_file_structure.py` reports an SQL-emitting task that lacks either item. It reports at WARNING and does not replace the reviewer check.

### 9.B.6 Verify examples-repo citations against the pinned version

<!-- Canonical numbering: §9.B.6-§9.B.9 are the canonical numbers for these four
rules. Do not renumber these sections. -->

> [!constraint] An example cited from a versioned examples repository MUST be verified against the version the project actually pins
> This covers a code sample, config snippet, or usage pattern from an SDK examples repo, a framework cookbook, or a sample-app repo. Verify it against the *exact version* the project pins. Examples repos track their library's latest release.
>
> WRONG — `Follow the {feature} example in {examples-repo} for the call shape.` The `main` branch may use an API that exists only in `{newer-version}`.
>
> CORRECT — `The project pins {library}@{pinned-version}. Follow the {feature} example at tag {ref-matching-pinned-version}, NOT main. If the pinned version predates the example, adapt the older call shape and note the divergence.`

#### Reviewer Check 031 — Task Planning-Tier Schema Pin Reconciliation

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Schema Pins in planning-tier docs MUST reconcile against deployed-tier schema (`{schema-file}` / `{schema_glob_path}`).
- **Detection:** Extract Schema Pin block; run the §9.B.13 three-step protocol — (1) grep deployed DDL for CREATE/ALTER on the pinned table, (2) grep the consumer-side data model for any Pin column an adapter populates, (3) confirm the reconciliation is recorded via a `> [!binding] Schema Pin reconciled to live deployed DDL` callout naming both source files. A pinned identifier unresolved against deployed DDL, or a reconciliation missing its callout → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task Schema Pin planning-vs-deployed drift
File: {task file path} | Location: Schema Pin section
Issue: Pinned identifier "{name}" not found in deployed {schema-file}
Fix: Reconcile per references/verify-before-cite.md §9.B.13 + schema-pin-requirement.md | Confidence: HIGH
```

### 9.B.7 Enumerate the specific helpers a spawn prompt tells an agent to use

> [!constraint] A spawn prompt that says "use the project's helpers" MUST enumerate the specific helpers — name, location, signature
> When a DELEGATED task's spawn prompt instructs the executing subagent to "use the existing helpers", "reuse the project's utilities", or any equivalent blanket phrasing, the prompt MUST instead enumerate each helper the task is expected to use: its name, the file it lives in, and its signature (or a one-line contract). A subagent has no shared context. A blanket instruction forces it to re-discover the helper set (token burn) or reimplement functionality that already exists (duplication).
>
> WRONG — `Use the project's existing helpers; do not reinvent utilities.`
>
> CORRECT — enumerate the USED helpers, and report an absent helper in Recovery rather than inventing one:
> ```markdown
> | Helper | Location | Signature / contract |
> |--------|----------|----------------------|
> | {helper-1} | {module-path} | {signature} |
> ```

Cross-referenced by [templates/task-file.md](../templates/task-file.md) (Notes for Agent guidance) and the `/planwise review` reviewer check for blanket-helper references.

The rule `used-helper` in `scripts/lint_task_file_structure.py` reports a task that references a helper module with no `## USED-Helper Enumeration` section. It reports at WARNING and does not replace the reviewer check.

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
Fix: Verify per references/verify-before-cite.md §9.B.14 | Confidence: HIGH
```

### 9.B.8 Field-mapping table for consumed data models; measured output-size gate

> [!constraint] A task consuming another module's data model MUST carry a field-mapping table, and task-file outputs MUST be gated at the measured token budget
> **Field-mapping table.** When a task's input is another module's data model (a struct / dataclass, a typed record, a deserialized payload), the task file MUST include a field-mapping table showing which fields are consumed and how — per the Interface Consumption guidance in [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9. The subagent must not infer the consumed fields from the type's name. For **MERGE / upsert** task briefs specifically, the field-mapping table MUST also state the Row↔DDL alignment strategy — which row field maps to which target column, and how name or position mismatches are resolved.
>
> **Measured output-size gate.** A task whose output is itself a task file (or any plan artifact) MUST be gated so the produced file lands OK on all three Read gates — under 22,000 measured tokens (the reading model's ratio), under 240 KiB, under 2,000 lines. Verify with `measure_files.py`. If the projected output exceeds the token budget, pre-split per `task-content-fidelity.md` §9.A.7.
>
> WRONG — `Read {ModelType} and generate the downstream config.` No field map, and nobody measures the output.
>
> CORRECT — `Read {ModelType}; consume only the mapped fields`, with a table of `Input Field | Used For`, then verify each produced file with `python "{plugin_root}/scripts/measure_files.py" {file} --model {reader}`.

Cross-referenced by [templates/task-file.md](../templates/task-file.md) (Interface Consumption block) and [task-file-and-tracking-requirements.md](task-file-and-tracking-requirements.md) §9 (Task File Template).

Check 32 in `scripts/lint_gate_checks_verify.py` reports a file-producing task with no measured size gate. The rule `field-mapping` in `scripts/lint_task_file_structure.py` reports a MERGE or upsert task with no `### Field Mapping` subsection. That rule reports at WARNING and does not replace the reviewer check.

#### Reviewer Check 029 — Task Measured Output-Size Pre-COMPLETE Gate

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** Task Success Criteria MUST include a measured output-size verification gate (`measure_files.py` — tokens/bytes/lines) before COMPLETE. Orchestrator-level measurement between dispatches also required.
- **Detection:** Grep Success Criteria for `measure_files|token.*(gate|budget|measure)`. File-producing task lacking a measured size gate → BLOCKER.
- **Finding template:**
```
[BLOCKER] Task measured output-size pre-COMPLETE gate missing
File: {task file path} | Location: Success Criteria checklist
Issue: File-producing task lacks measured size verification
Fix: Add a measure_files.py gate per references/verify-before-cite.md §9.B.8 | Confidence: HIGH
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
> This covers a web page, a paginated API, a large remote document, or a registry. An unbounded fetch either blows the subagent's context budget or fails silently on a source larger than expected.
>
> | Tier | Probe | Use When |
> |------|-------|----------|
> | 1 | Targeted query / search / `HEAD` request | A specific fact or existence check is all that is needed |
> | 2 | Single section / page / paginated slice | The relevant content is a known sub-range |
> | 3 | Full fetch with an explicit size cap + budget note | The whole source is genuinely required |
>
> WRONG — `Fetch {external-source} and extract {data}.`
>
> CORRECT — stop at the first hit and escalate only on a miss. If a Tier 3 cap is hit, report it in Recovery rather than truncating silently.

### 9.B.10 Reconcile the design tier against deployed state before authoring

> [!constraint] Reconcile a design artifact's claims about deployed shape before authoring any statement that binds to it
> When Discovery precedes Execution by more than a few days, a design artifact's claims about a data structure are a hypothesis. Search the deployed definition (CREATE + every subsequent ALTER) and the consuming code's data model first. The live shape wins.
>
> WRONG — author a MERGE from the design artifact's field list, and discover the mismatch at smoke-test time.
>
> CORRECT — search both sources BEFORE authoring, reconcile to the live shape, and record any divergence in Recovery rather than silently conforming.

### 9.B.11 Locate the mechanism before editing it

> [!constraint] Open the live artifact and locate the mechanism before editing it
> Briefs drift on WHERE a mechanism lives, not only on whether it exists. An edit aimed at the wrong location is a silent no-op that reports success.
>
> WRONG — the brief says the workaround is a set of aliases in a MERGE, so the editor rewrites the MERGE. The actual mechanism, an attribute reference in a closure, is untouched.
>
> CORRECT — search for the symbol the workaround acts on, read the surrounding block, confirm the mechanism, then edit. If the brief disagrees with the live artifact, the live artifact wins, and the same change corrects the brief.
>
> To retire a guard rather than edit a workaround, see §9.B.23.

### 9.B.12 Split a ratification item rather than widening it

> [!constraint] A ratification item stays inside its own acceptance criteria; code reconciliation gets a follow-up item
> This applies when triage finds deployed code authored ahead of schedule under provisional markers that now disagree with a ratified design.
>
> WRONG — do everything in one pass, so the item closes claiming work its criteria never described.
>
> CORRECT — the ratification item lands the plan-demote chain only. A new item owns the code reconciliation, cites the design source of truth, and is sized to what triage actually found.

### 9.B.13 Reconcile a planning-tier Schema Pin against deployed state before emitting SQL

*Database-schema instance of the general verify-before-cite rule (see §9.B intro).*

> [!constraint] A Schema Pin MUST be reconciled against deployed state via a three-step protocol before any SQL is authored against it
> A well-formed, honestly-cited Pin can still be wrong, because the deployed table can change after the design artifact was written. The orchestrator HALTS before authoring SQL and runs three steps:
> 1. Search CREATE + ALTER for the table in deployed DDL.
> 2. Search the consumer-side data model whenever the Pin describes columns an adapter populates.
> 3. When deployed DDL and the consumer-side model agree, that pairing is canonical. Reconcile to it and record an inline `> [!binding] Schema Pin reconciled to live deployed DDL ({date})` callout naming both source files.
>
> When they disagree with the design artifact, the design artifact is stale. Reconcile forward and file a back-propagation item. Include a brief-vs-deployed comparison table (column / brief says / deployed says / verdict) as the auditable artifact.
>
> WRONG — author a 15-column INSERT against a well-formed Pin when the deployed table has 17 columns, or silently conform the code to the plan.
>
> CORRECT — search the deployed DDL and the adapter's dataclass, reconcile, annotate, then author.

### 9.B.14 Verify-before-cite applies to every deployed symbol, not only SQL columns

> [!constraint] Grep the live source-of-truth and cite `file:line` for every deployed symbol a template, brief, or reference doc names
> A template, brief, or reference doc that names an environment variable, function signature, file path, helper name, config key, or dataclass field MUST Grep the live source-of-truth at authoring time and cite it with `file:line`. The search is the discipline, and the citation is the binding artifact. A one-character defect in a widely-inherited template is worth a binding rule precisely because it is never escalated. Each consumer fixes it locally, and the true cost (paid N times) stays invisible.
>
> WRONG — paste an env-var name from memory into a template that N notebooks will inherit.
>
> CORRECT — run `Grep pattern='os\.environ\.get\(.\w+_SQL_\w+.\)' path='{connection_helper}'`. The set of names it returns IS the canonical list, and the template cites exactly that set with its `file:line`.

### 9.B.15 Open a cited generator script during scaffolding and classify its architecture

> [!constraint] Open a cited generator script and classify it as parser, static-data, or config-loader before encoding "re-run it"
> When a brief says "re-run X to refresh Y", determine whether X READS the upstream dynamically (parser), CONTAINS a snapshot of it (static-data), or LOADS it from config (config-loader). If X is a parser, confirm its logic keys on the structures the upstream added. For a multi-session pipeline with one canonical generated artifact, settle the generator's architecture in the Master Plan.
>
> WRONG — `Step 4: re-run build_matrix.py to pick up the new rows.`
>
> CORRECT — `Step 4: build_matrix.py is STATIC DATA, so re-running it is a no-op. Author a sibling parser that reads the new blocks and emits the delta.`

### 9.B.16 Probe the live service before authoring against its shape

> [!constraint] Probe the live service before authoring code, queries, or iteration structure bound to it
> The service is the authority, and the design artifact's claims about it are hypotheses. Applies when a design phase preceded execution by more than a couple of weeks AND the task binds to an external service. Before authoring:
> 1. Call the target endpoint with a representative request. Record status code, response container shape and error body.
> 2. Record the exact request shape that worked, including which parameters the endpoint rejects.
> 3. Record the endpoint's cardinality (what granularity it accepts). Field-level reconciliation cannot surface these defects.
> 4. Reconcile against the design artifact. The live shape wins, and Recovery records the divergence for back-propagation.
>
> WRONG — author an iteration loop straight from the spec, and the endpoint rejects the per-item filter the spec assumed.
>
> CORRECT — probe first (period-scoped request succeeds, per-item-filtered request 4xx), then author against the observed shape.

### 9.B.17 A canonical helper's signature is a claim about shape, not a guarantee

> [!constraint] Verify a canonical helper's signature assumption against the actual producer per task; a genuine mismatch earns a purpose-built helper, not a forced workaround
> A shared helper's signature encodes an assumption about the shape it receives. Target constraints (e.g. a uniqueness constraint forbidding identical per-batch stamps) are part of the shape too.
>
> WRONG — force the producer through the canonical helper because the plan standardized on it. The divergence moves somewhere less visible.
>
> CORRECT — read the producer's actual output shape to verify the incompatibility, write the purpose-built helper, record in Recovery which property forced it, and flag it for cross-artifact review.

### 9.B.18 A rule/reference-file edit triggers closeout re-verification of open plans citing it

> [!constraint] Any change that edits a file cited by plans MUST run a closeout back-propagation search, with a non-negotiable COMPLETE-is-archival carve-out
> At closeout, run `scripts/change_closeout.py` for each changed file. Back-propagation targets every status that is not finished, and it stops at `COMPLETE`. A plan whose Status is COMPLETE is ARCHIVAL — do NOT rewrite it. Its brief is a record of what the runner was told, and rewriting it destroys the audit trail.
>
> WRONG — bring a COMPLETE plan's brief up to date with the edited file.
>
> CORRECT — re-run verify-before-cite on the citations of every hit the script lists:
> ```
> python "{plugin_root}/scripts/change_closeout.py" --changed {changed_file_basename} --plans {plans_dir} --backlog {backlog_dir}
> ```

### 9.B.19 Cite by contract, not by condition

> [!practice] A brief should assert invariants, not the current state of someone else's file
> WRONG — "rule X is broken, don't trust it": a claim about a mutable external file, which rots the moment the file is fixed.
>
> CORRECT — "an `.ipynb` is JSON, so never anchor a grep with `^`": states the underlying invariant, which never rots.

### 9.B.20 Citing the current state of a file requires recording which tree and when

A task that cites the current state of a file must record which tree it read and when: see [verify-backlog-citation-freshness.md](verify-backlog-citation-freshness.md) §12 (Verification Task Tree-State Pin).

### 9.B.21 A target's structure is verified in that file, never generalised from its siblings

> [!constraint] "In native format" / "matching the existing" names a structure that MUST be proven to exist in the NAMED target
> [verify-anchor-against-artifact.md](verify-anchor-against-artifact.md) §1 holds the rule: verify a named landing zone exists in the live artifact before briefing work into it. This section adds the row form.
>
> A phrase like *"a {row} in native format"*, *"matching the existing"*, *"verbatim, as the other {N} files carry it"*, or a named section of the target, generalises a structure seen across a **family** of files onto **one** file that may not have it. The runner then invents the structure, which is unscoped work, or lands something that cannot satisfy its own success criterion. Before such a row ships, run a locator against **that file** and record the result in the row. A count of 0 does not block the row. It changes what the row must say.
>
> WRONG — `| {row-id} | Add a Required-References row in native format | {target-handler}.md |`, when the named file has no such section.
>
> CORRECT — the locator result sits in the row, and the row states the form:
> ```markdown
> <!-- Verified {YYYY-MM-DD}: Grep '^## Required References' {target-handler}.md → 0 (present in {M} of {N} handlers) -->
> | {row-id} | Section absent — add the text as an INLINE note above `## {Existing Section}`. Creating the section is NOT in scope. | {target-handler}.md |
> ```

**Where the structure is absent, the row states the fallback form.** A row whose target lacks the structure MUST name the form to use — an inline note, or a new section — rather than leaving the runner to choose. When creating the section is genuinely intended, that is its own named deliverable with its own scope and its own success criterion, never a side effect of a citation row.

**Copyable text can lack a structural home.** Where the "verbatim" text a row calls for lives *inside* the missing section, the text is copyable but its position is not. State the form first, then the text.

The zone mode of `scripts/check_section_citations.py` (`--zone {target} --brief {file}`) reports a row with no locator result or no fallback form. It is a heuristic report and does not replace Check 085.

#### Reviewer Check 085 — Target Structure Proven in the Named File

- **Severity / Role / Type:** ERROR | Structural Reviewer | NEW
- **What:** Any row or instruction specifying an edit "in native format", "matching the existing", "verbatim as the other {N} carry", or naming a section of its target, MUST carry a locator result measured against the **named target** — not its siblings. Where the locator returns 0, the row MUST state the fallback form.
- **Detection:** The zone mode of `scripts/check_section_citations.py` covers steps 1 to 3 in part, as a heuristic report. Step 4 needs a reader.
  1. Grep plan rows and task Execution Steps for `native format|matching the existing|verbatim as|the existing \w+ carry` and for rows naming a `^##`/`^###` section of a named target file.
  2. For each hit, run the locator against the named target and compare with the row's recorded evidence. No recorded evidence → ERROR.
  3. Where the live locator returns 0 and the row does not state a fallback form (inline note vs. new section) → ERROR.
  4. Where the row's success criterion is measured against sibling files' text but the target lacks the surrounding structure → ERROR.
- **Finding template:**
```
[ERROR] Target structure assumed from siblings
File: {plan or task file path} | Location: row {id} / Execution Step {N}
Issue: {row specifies "{phrase}" against {target}, which has no {structure} (live locator → 0; present in {M} of {N} siblings) | row records no locator evidence for the named target | locator returns 0 and no fallback form is stated}
Fix: Run the locator against the named target and state the fallback form per references/verify-before-cite.md §9.B.21 | Confidence: HIGH
```

### 9.B.22 An exemplar's data claims expire independently of its shape

> [!constraint] An exemplar is a shape plus a set of data claims. Judge each against its own source
> The shape (section order, table columns, wording) is stable. Each data claim (this key, these neighbours, this consumer exists) is a reading of a live source at one moment, and it expires silently when that source moves. Applies to any regenerate-against-exemplar task (a hand-written report, a golden file, a reference render).
>
> WRONG — treat every exemplar line as the expected value and every divergence as a tool defect.
>
> CORRECT — re-read the live source, then classify:
> ```
> Expected: after `<N1>`     (exemplar, written <date>)
> Observed: between `<N1>` and `<N2>`
> Source:   <file> now holds `<N2>` (+4 rows since <date>)
> -> verdict: live-file drift; tool correct; exemplar claim expired
> ```

- **Split the comparison table by claim kind.** Judge shape rows against the exemplar. Judge data rows against the live source, with the exemplar as the prior reading.
- **Date the exemplar's data claims and expect the shortest-lived to be wrong first.** State the condition next to the claim.
- **Name the tiebreaker before dispatch where two authoritative inputs disagree.** A runner that cannot settle it records both readings and routes the question.

Any briefing that says "a different result is a finding" should add "after re-reading the live source".

### 9.B.23 Before retiring a guard, find in code the mechanism that removed its hazard

> [!constraint] A guard's rationale for retirement is a claim about a mechanism. Verify the mechanism in code, not in the decision that asserts it
> A decision table records what its author believed at planning time. The code records what happens. When a guard names two hazards, check each one separately. This extends §9.B.11 ("Locate the mechanism before editing it") from editing a workaround to retiring a protection. **Applies to** any concurrency guard, lock, ordering constraint or "never do X" rule that a redesign supposedly made unnecessary.
>
> WRONG — retire the guard because the decision says the race is gone:
> ```
> <decision>: "--next-id derives from live files" -> delete "Never dispatch two" -> state "concurrent dispatch is safe"
> ```
> CORRECT — trace each hazard the guard names, and keep what survives with its reason:
> ```
> index-file race    -> --create writes item files only; --write is atomic          -> retired
> id-allocation race -> the id collector reads generated files only                 -> KEPT, re-grounded, with a retirement condition
> ```

Two checks apply before a guard is removed.

1. **Name the code path that now makes the hazard impossible, and open it.**
2. **Keep the surviving half with its real reason, and state when it can retire.**

### 9.B.24 A live-tree figure is a census row, re-measured at Session Start

> [!constraint] A figure about the live tree is a claim about one tree at one moment. Record where it was read, and re-derive it at dispatch
> WRONG — a task gate pins a scaffold measurement (a file count, a split point, a line-ending assumption) as a bare literal: `# expect 104`.
>
> CORRECT — the gate takes the census row's value: `# pre-edit: 104 (references/*.md at <sha>, <date>) -> expect {census:ref_count}`.

1. **Every such figure is one census row.** The row holds the scaffold value, artifact, commit, date, a runnable re-measure command and an on-drift mode. The rows live in the orchestration file's Session Start Census.
2. **The orchestrator re-measures, and the runner never reads Recovery.** Before the first dispatch the orchestrator runs each row's command at the session base, records it in Recovery, and injects the value into each spawn prompt's `Census:` line. This applies the shared-pin injection rule (`agent-orchestration-delegated.md` §1.6) to figures other than a commit SHA.
3. **The on-drift mode splits two cases.** A `substitute` row takes the session-base value, because the figure only parameterizes a check. A `halt` row surfaces a structural finding at CONFIRM, because the figure decides a task's Output paths or a layer's write-target intersection.

The generic pin rule is in `measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md` §8.11.

### 9.B.25 A planner-authored citation is opened in the named file before it ships

> [!constraint] A citation from an audit or from memory is verified like a user-cited one
> §9.B.1 verifies the artifacts a user cites. A planner or an audit cites too: a test name, an `except` clause, a helper, a rule file's size. Each is a claim about one named file at one moment. A path Glob proves none of them. Five sprints scaffolded in one pass from an audit shipped all four shapes below.
>
> WRONG — cite from the audit's wording after the path check passed:
> ```
> Step: "update test_upgrade_messages in tests/test_upgrade.py"   # the test lives in tests/test_upgrade_flow.py
> Step: "change `except ValueError as exc:`"                      # live code: `except (ValueError, TypeError, AttributeError): return None`, no binding
> Context: "reuse make_fixture from tests/helpers.py"             # defined in tests/fixtures_util.py; the only match in helpers.py is a parametrize tuple
> Context: "rules/foo.md, about 4K tokens"                        # measured 12K tokens after three sections landed
> ```
> CORRECT — open the named file and write the reading beside the citation:
> ```
> Read  file_path='tests/test_upgrade.py'  offset=<cited line>  limit=20
> Grep  pattern='def test_upgrade_messages'  path='tests/test_upgrade.py'  output_mode='count'   # 0 -> wrong module; find the real home first
> Grep  pattern='except \(ValueError'  path='<module>.py'  output_mode='content'  -n=true       # quote the live clause, not the paraphrase
> python -B scripts/measure_files.py rules/foo.md                                               # fresh size, not the audit's
> ```

1. **Open the named file at the cited line.** Treat the line number as a hint and read the text around it.
2. **Search each cited symbol, test name and quoted code line inside that file, never repo-wide.** A symbol found only in a sibling file is a wrong citation, not a pass.
3. **Take a fresh size reading for each cited rule file.** Use `measure_files.py` or `wc -c`. The method is in [task-content-fidelity.md](task-content-fidelity.md) §9.A.14.
4. **Quote the live clause.** Copy the exact `except` clause, signature or heading from the file, so the step cannot narrow or widen it by paraphrase.

### 9.B.26 A documentation check on an inherited parameter changes the signature, not only the audit value

> [!constraint] A verify-before-send rule answers what goes on the wire. The brief must also answer what the signature promises
> A plan decision gave two new client methods the same keyword parameters as a sibling method, including a `{filter}` parameter and a boolean flag. The task brief then added a rule: send each parameter only if the endpoint's reference document lists it. If the document does not list it, do not send it. Record the audit value as `False` or `None` and say so in the findings.
>
> Neither endpoint document listed the parameters. The runner followed the brief exactly. The result was two public methods that accept `{filter}="x"` and silently ignore it. The caller pays for every default value, while the audit row truthfully records `None`. The plan review rated this HIGH. The type checker had flagged both parameters as "not accessed" all along.
>
> WRONG — the brief changes the audit value and leaves the signature spec alone:
> ```text
> if a flag is not documented there, do not send it, record the audit value as False/None,
> and say so in the findings
> ```
> CORRECT — the brief names one of two signature outcomes, and the audit column records what was sent:
> ```text
> if a parameter is not documented there, do not send it. Signature outcome: {remove it from the
> signature spec | keep it for parity with {sibling} and raise on a non-default value}.
> The audit column records what was sent.
> ```

1. **Treat "undocumented" as a signature finding.** When the documentation check says the endpoint does not take a parameter, the brief changes the signature spec. Changing only the audit value is not enough.
2. **Name one of two outcomes.** If the endpoint does not take the parameter, it is not a parameter, so the brief removes it from the signature spec. If the parameter must stay for parity with a sibling, the brief requires that a non-default value raise an error. The caller asked for something the method cannot do.
3. **Record what was sent in the audit column.** Nothing else was possible, so the column no longer hides a dead parameter.
4. **Read two mechanical tells as proof the wrong shape landed.** The type checker reports `"<param>" is not accessed` on a public method's parameter. A test passes a non-default value and asserts its absence on the wire. That test is correct, but a correct signature would not have needed it.

#### Reviewer Check 118 — Documentation Check on an Inherited Parameter With No Signature Outcome

- **Severity / Role / Type:** ERROR | Task Reviewer | NEW
- **What:** A brief that sends an inherited parameter only when the endpoint's reference document lists it MUST also state the signature outcome for the unlisted case. The outcome is either removal from the signature spec or a raise on a non-default value. A brief that only records `False` or `None` as the audit value leaves a silently ignored public parameter.
- **Detection:** Search task briefs and Execution Steps for a rule shaped "send only if documented", "if it is not listed, do not send it" or "record the audit value as False/None". For each hit, read the same brief for a signature outcome. Flag a brief with neither a removal from the signature spec nor a raise on a non-default value. Flag a public parameter the brief leaves unread by the method body. → ERROR.
- **Finding template:**
```
[ERROR] Inherited-parameter documentation check with no signature outcome
File: {task file path} | Location: {Execution Step or Notes for Agent line}
Issue: The brief sends "{parameter}" only when the endpoint document lists it and records {False/None} otherwise, but it states no signature outcome, so the public method accepts and ignores the parameter
Fix: State one outcome, either remove "{parameter}" from the signature spec or raise on a non-default value, per references/verify-before-cite.md §9.B.26 | Confidence: HIGH
```

### 9.B.27 A brief's claim about an external source's coverage is checked against the probe document it cites

> [!constraint] A coverage claim in a brief is checked against the probe document, never written from memory
> A brief said an external source's listing "may return 0 entries" before a given date. The probe document in the same brief's Required Context already recorded the real coverage rule. The planner wrote the sentence from memory and never opened the document. The sprint's sequencing then depended on a case the plan had not written down.
>
> WRONG — coverage asserted from memory beside a probe document that states the rule:
> ```text
> Required Context: {probe document}
> Note: the source begins listing on {date}. Before that the listing may return 0 entries.
> ```
> CORRECT — the rule is quoted from the document, with the probe date:
> ```text
> Required Context: {probe document}
> Source coverage ({probe document}, probed {date}): {the rule, quoted}.
> ```

1. **Open the cited probe document at scaffold time.** A date, a coverage window or a "may return nothing" caveat about an external source is a claim about that document.
2. **Quote the rule and record the probe date.** A paraphrase can narrow or widen the rule.
3. **Reconcile every sentence about the source.** When the brief and the document disagree, the document wins until a fresh probe says otherwise. Correct the brief at its source.
4. **Pair the claim with a criterion that names every cell.** A criterion over the source's listing follows [gate-anchor-outcome-set.md](gate-anchor-outcome-set.md) §10.12.

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
| 6 | Target structure assumed from siblings | A row specifying an edit "in native format" / "matching the existing" / naming a section of its target carries no locator evidence measured against that target; or the live locator returns 0 and the row states no fallback form | §9.B.21 |
| 7 | Live-tree figure pinned as a literal | A task gate or step asserts a file count, split boundary, scan-set size, line number or line-ending tally as a bare literal, with no census row naming its artifact, commit and date | §9.B.24 |
| 8 | Planner-authored citation not opened in the named file | A task cites a test, symbol, quoted code line or rule-file size taken from a planner or an audit, and the row records no reading from the named file (a symbol found only in a sibling file, or a size not freshly measured) | §9.B.25 |
| 9 | Documentation check on an inherited parameter states no signature outcome | A brief sends an inherited parameter only when the endpoint document lists it, records `False` or `None` otherwise, and neither removes the parameter from the signature spec nor raises on a non-default value | §9.B.26 |
| 10 | Coverage claim about an external source not checked against the probe document | A brief states a date, a coverage window or a "may return nothing" caveat for an external source, and its row quotes no rule from the probe document the brief cites | §9.B.27 |

---

*Anchor: [task-content-fidelity.md](task-content-fidelity.md) (§9.A Required Context Fidelity — split anchor, filename frozen by that split). Companion: [schema-pin-requirement.md](schema-pin-requirement.md).*
