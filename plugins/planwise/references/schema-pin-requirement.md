---
description: Schema Pin requirement and construction recipe for task files referencing DB tables — required structure, grep recipe, post-migration reconciliation, and review-time verification
---

# Schema Pin Requirement

Any task file whose Required Context references a DB table — directly (inline SQL, table name in Schema Pin), or indirectly (an instruction to read/write a table by name) — MUST include a Schema Pin section that quotes the live, post-migration column shape verbatim from the project's schema source files (`{schema_glob_path}`).

## Table of Contents

- [1. Schema Pin Requirement](#1-schema-pin-requirement)
- [2. Pin Construction Recipe](#2-pin-construction-recipe)
- [3. Pin Format](#3-pin-format)
  - [3.1 Abbreviated Pre-Execution Pin Form](#31-abbreviated-pre-execution-pin-form)
- [4. Plan-Review Enforcement](#4-plan-review-enforcement)
- [5. Pin Freshness and Drift Shapes](#5-pin-freshness-and-drift-shapes)
  - [§5.1 Omission Is the Silent Drift Shape](#51-omission-is-the-silent-drift-shape)
  - [§5.2 A Count in a Pin Is a Claim, Not a Label](#52-a-count-in-a-pin-is-a-claim-not-a-label)
  - [§5.3 A Recorded Shape Change Obligates a Pin Sweep](#53-a-recorded-shape-change-obligates-a-pin-sweep)
  - [§5.4 Reconcile Against the Catalog, Never a Sibling Brief](#54-reconcile-against-the-catalog-never-a-sibling-brief)
  - [§5.5 Prefer a Verification That Would Fail If the Column Were Absent](#55-prefer-a-verification-that-would-fail-if-the-column-were-absent)

---

## 1. Schema Pin Requirement

A Schema Pin section quotes actual columns + constraints from the schema file at the time of task authoring. The pin gives a DELEGATED subagent ground truth so it does not burn dispatch cycles re-discovering schema shape, and so it cannot silently drift the brief from live state.

> [!constraint] Schema Pin Required
> WRONG — task brief asserts column shapes from the planner's mental model:
> ```sql
> -- Required Context, brief authored from intuition:
> SELECT t.{id_col}, t.{col_A}, t.{col_B}
> FROM {table} t
> INNER JOIN {related_table} r
>     ON r.{id_col} = t.{fk_col}
> ```
> The columns `{col_A}` and `{col_B}` do NOT exist on `{table}` (the actual
> schema uses wide-format with `{col_home}` / `{col_away}` pattern). The
> DELEGATED executor will discover the mismatch at run-time, burn tool uses on
> schema discovery, and rebuild the query with the correct column shape.
>
> CORRECT — task brief includes a Schema Pin section quoting actual columns,
> with source-line citations:
> ```markdown
> ## Schema Pin (verified {YYYY-MM-DD} against {schema_glob_path})
>
> | Table | Columns + constraints (post-migration shape) | Source ranges |
> |-------|----------------------------------------------|---------------|
> | {table_name} | {col_1}, {col_2}, ... — UNIQUE ({unique_cols}) | {schema-file}:{create-range} (CREATE TABLE) + {schema-file}:{alter-range} ({migration description}) |
> | {related_table} | {col_1}, {col_2}, ... — wide format, no {absent_col} | {schema-file}:... |
> ```

The pin is authored once, at planning time, and quoted into every task file in the plan that references those tables. Sub-tasks inherit the parent plan's pin verbatim — they do NOT re-derive it.

---

## 2. Pin Construction Recipe

The pin MUST capture POST-MIGRATION state. Initial `CREATE TABLE` blocks alone are insufficient — schema files accumulate `ALTER TABLE` migrations downstream of the original create, and the live constraint shape may differ.

> [!constraint] Grep Both CREATE TABLE and ALTER TABLE
> WRONG — grep only `CREATE TABLE`:
> ```bash
> grep "CREATE TABLE {table}" {schema_glob_path}
> # captures only the original CREATE block
> # propagates STALE constraint into the Pin → Tasks → DELEGATED execution
> ```
> The original constraint may have been replaced by a later migration. A pin
> built from `CREATE TABLE` alone misses this. A reviewer or DELEGATED subagent
> treating the pin as authoritative would assume the original uniqueness
> constraint, conclude that two rows differing only in a later-added column are
> duplicates, and either fail at runtime or — worse — silently produce queries
> that miss the live constraint shape.
>
> CORRECT — grep CREATE + ALTER + DROP/ADD CONSTRAINT, reconcile to live state:
> ```bash
> grep -nE "CREATE TABLE {table}|ALTER TABLE {table}|{constraint_prefix}_{table}|DROP CONSTRAINT|ADD CONSTRAINT" {schema_glob_path}
> ```
> Capture the CREATE block + every subsequent ALTER + every constraint drop/add
> for the table. Reconcile to the post-migration shape and quote that into the
> pin. For precision, NULL/NOT NULL, and DEFAULT changes, capture the original
> column definition + every `ALTER COLUMN` that touches it; report the
> post-migration state with the migration line range cited.

### Recipe Steps

1. For each table referenced by the plan, run the grep command above against `{schema_glob_path}` (the project ships one or more schema files under `{schema_glob_path}`).
2. Order the matches by line number. The earliest match is the `CREATE TABLE`; later matches are migrations.
3. For each migration block, identify whether it adds a column, drops a constraint, adds a constraint, or alters a column type.
4. Reconcile to the live shape:
   - Columns: original list + every `ADD COLUMN` − every `DROP COLUMN`.
   - Constraints: every `ADD CONSTRAINT` not yet dropped by a later `DROP CONSTRAINT`.
   - Column types: latest `ALTER COLUMN` wins.
5. Quote the reconciled shape into the Pin. Cite both the CREATE source range and every ALTER source range that contributes to the live shape.

---

## 3. Pin Format

> [!template] Schema Pin Section
> ```markdown
> ## Schema Pin (verified {YYYY-MM-DD} against {schema_glob_path})
>
> | Table | Columns + constraints (post-migration shape) | Source ranges (CREATE + every ALTER cited separately) |
> |-------|----------------------------------------------|------------------------------------------------------|
> | {table_name} | {column list} — {constraint summary} | {file}:{create-range} (CREATE TABLE) + {file}:{alter-range} ({migration description}) |
> ```

Required columns of the Pin table:
- **Table**: bare table name (no schema prefix unless the project uses one).
- **Columns + constraints (post-migration shape)**: comma-separated column list with type/nullability when relevant, followed by an em-dash and a constraint summary (PK, UNIQUE, FK shorthand). Annotate post-migration state explicitly when it differs from the original CREATE.
- **Source ranges**: file path + line range for the CREATE block, plus every contributing ALTER block cited separately with a one-phrase description.

---

### 3.1 Abbreviated Pre-Execution Pin Form

The full Pin (§3) quotes a live, post-migration column shape from a schema file — which presupposes the table already exists. When one sprint creates a table (a DDL sprint) and a later sprint references it, the later sprint's task files cannot quote a schema file that has not been written yet. For that case — and only that case — an abbreviated **2-column pre-execution Pin form** is valid.

> [!template] Abbreviated Pre-Execution Schema Pin
> ```markdown
> ## Schema Pin (pre-execution — {table_name} authored by {Sprint-N}, not yet shipped)
>
> | Table | Planned column shape — source of truth |
> |-------|----------------------------------------|
> | {table_name} | {Abbrev}-S{XX}-Execution-Input.md §{N.M} ({DDL section title}) — columns + constraints are authored there; upgrade to a full §3 Pin once {Sprint-N} ships the schema file |
> ```

The abbreviated form names the table and points — by `§N.M` reference, never by prose restatement — at the Execution Input section (or DDL task file) that carries the planned column shape. It does not assert column names itself; the cited source-of-truth section does.

> [!practice] Pin format note
> A task file that uses the abbreviated 2-column form MUST carry a `> [!practice] Pin format note` callout directly beneath the Pin. The note states (1) that the target table does not yet exist because an earlier, not-yet-executed sprint creates it, (2) the `§N.M` reference to the Execution Input section (or DDL task file) holding the planned column shape, and (3) that the Pin MUST be upgraded to the full post-migration form (§3) once the creating sprint completes. Paste-ready form:
> ```markdown
> > [!practice] Pin format note
> > {table_name} does not yet exist — it is created by {Sprint-N}. Planned
> > column shape: {Abbrev}-S{XX}-Execution-Input.md §{N.M}. Upgrade this Pin to
> > the full post-migration form (schema-pin-requirement.md §3) once {Sprint-N}
> > ships the schema file.
> ```
> Without the format note, plan-review cannot distinguish a legitimate pre-execution Pin from a degraded full Pin and treats the abbreviated form as a §1 violation.

The abbreviated form is a planning-time bridge, not a substitute. Once the creating sprint ships, re-run the §2 grep recipe against the now-existing schema file and replace the abbreviated Pin with the full post-migration shape.

---

## 4. Plan-Review Enforcement

> [!binding] /planwise review Phase 1 — Schema Pin Staleness Check
> When the structural-reviewer encounters a Schema Pin section, it MUST grep `ALTER TABLE {table}` against the cited source files for every Pin entry. Any unreferenced ALTER block (i.e., an `ALTER TABLE {table}` that exists in the schema file but is not cited in the Pin) raises a Pin-staleness ERROR.

The reviewer's verification command:
```bash
# For each (table, source_file) pair cited in the Pin:
grep -nE "ALTER TABLE {table}|DROP CONSTRAINT.*{table}|ADD CONSTRAINT.*{table}" {source_file}
# Cross-check every match against the Pin's Source ranges column.
# Any match not cited → Pin-staleness ERROR.
```

> [!gate] Pin Required for SQL-Bearing Task Files
> A task file whose Required Context contains inline SQL OR references a DB table by name MUST include a Schema Pin section. Plan-review fails on absence; DELEGATED execution MUST NOT dispatch a task that lacks a required Pin.

#### Reviewer Check 022 — Task Schema Pin Pre-Execution Form

- **Severity / Role / Type:** BLOCKER | Task Reviewer | NEW
- **What:** DB-write tasks MUST include Schema Pin section in pre-execution form per `references/schema-pin-requirement.md` §4.
- **Detection:** Grep task for `^### Schema Pin`. If Execution Steps mention `INSERT|UPDATE|MERGE|UPSERT|ALTER` AND Schema Pin absent → BLOCKER.
- **Finding template:**
```
[BLOCKER] Schema Pin pre-execution form missing
File: {task file path} | Location: Expected ### Schema Pin section
Issue: DB-write task lacks Schema Pin section
Fix: Add Schema Pin per references/schema-pin-requirement.md §4 | Confidence: HIGH
```

### Authoring Checklist

> [!checklist] Pin Authoring (Pre-Dispatch)
> - [ ] Identified every table the task touches (read + write paths)
> - [ ] Ran the full grep recipe (CREATE + ALTER + DROP/ADD CONSTRAINT) against `{schema_glob_path}` for each table
> - [ ] Reconciled to post-migration shape (columns, constraints, types)
> - [ ] Quoted the live shape into a Pin table with the three required columns
> - [ ] Cited CREATE range AND every contributing ALTER range
> - [ ] Dated the Pin (`verified {YYYY-MM-DD}`)
> - [ ] Re-ran the grep on the day of dispatch if the pin was authored more than 7 days prior

---

## 5. Pin Freshness and Drift Shapes

A Schema Pin's staleness risk does not end at authoring — it resurfaces at dispatch and at every reconciliation after a shape change. The two dispatch-day requirements below are unnumbered lead constraints (they bind regardless of which sub-rule below they trigger); the five drift-shape sub-rules that follow keep their filed §5.1-§5.5 identities, since the Error Pattern Catalog cites them by number.

> [!constraint] Dispatch-Day Live Re-Verification Is Unconditional
> A Schema Pin authored at scaffold time records design intent. On dispatch day, re-verify every pinned column AND the table name itself against the live catalog — unconditionally, never gated on "if migrations shipped since". Two reasons the conditional form fails: drift can be design-vs-original-CREATE (not just a later ALTER), and a column-only check cannot detect a table invented in the design tier that was never built. Verify existence first, then columns.
> ```sql
> SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
>  WHERE s.name = '{schema}' AND t.name = '{table}';
> SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS
>  WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}' ORDER BY ORDINAL_POSITION;
> ```

> [!constraint] A Multi-Outcome Pin Makes Discovery the First Execution Step
> When a Pin enumerates alternative deployed states (outcome A/B/C), the consuming task's first Execution Step MUST be the discovery query, never a mechanical action premised on one outcome. Success Criteria are phrased "count determined at Discovery", never a hard-coded count. Gate wording must accommodate "zero because none ever existed" as distinct from "zero because all were already handled".

### 5.1 Omission Is the Silent Drift Shape

A Pin can be wrong in three ways, not equally detectable:

| Drift shape | Failure mode | When you find out |
|---|---|---|
| Names a column that does not exist | LOUD — Invalid column name | First execution |
| States the wrong type | LOUD-ish — data/type error on first incompatible row | First incompatible row, possibly much later |
| Omits columns that exist and are nullable/defaulted | SILENT — every row inserts; omitted columns hold DEFAULT/NULL forever | Never, unless something downstream reads them |

A statement authored from an under-declared Pin executes cleanly against the wider table — no driver, engine, linter, or row-count validation objects. A Pin's column list is not documentation of the shape; it IS the shape the derived statement will bind, and a short list quietly narrows the write.

### 5.2 A Count in a Pin Is a Claim, Not a Label

A bare number (`14 columns`) is a load-bearing factual claim about live state and must be verified the same way a cited line range is — a wrong count carries no signal of being wrong. When a Pin's shape includes columns whose omission would be silent per §5.1, the Pin MUST name those columns explicitly rather than relying on the count to imply them.
- WRONG: `| {table} (WRITE) | 14 columns; UNIQUE ({key_cols}) | {ddl_file} |`
- CORRECT: `| {table} (WRITE) | **16** columns; UNIQUE ({key_cols}). Includes **{flag_col} BIT NOT NULL DEFAULT 0** and **{reason_col} NVARCHAR(256) NULL** — a 14-column statement drops them silently | {ddl_file} |`

### 5.3 A Recorded Shape Change Obligates a Pin Sweep

When a plan's change log, decision register, or revision note records a table-shape change, the corresponding edit is a sweep of every Pin in the plan naming that table, not a single-row edit — Pins are scattered across sibling task files by design (write once, quote into every touching task file), which is exactly what makes the sweep necessary.
```bash
grep -rln "{schema}\.{table}" {plans_dir}/{plan}/**/*.md
# Every hit carrying a Pin row for this table must be reconciled in the same edit.
```

### 5.4 Reconcile Against the Catalog, Never a Sibling Brief

A Pin is reconciled against the deployed catalog, never another planning document — not the sibling task that authored the DDL, not the design artifact, not the change log. A file's intent and a database's state are separable; only the second is what a derived statement will meet.
```sql
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}' ORDER BY ORDINAL_POSITION;
SELECT name, definition FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('{schema}.{table}');
SELECT name, is_unique FROM sys.indexes WHERE object_id = OBJECT_ID('{schema}.{table}');
```

### 5.5 Prefer a Verification That Would Fail If the Column Were Absent

A criterion phrased as an implication over a column is satisfied trivially when nothing ever populates that column — precisely the state an under-declared write produces. It cannot distinguish "the mechanism works" from "the mechanism never ran."
- WRONG: `SELECT COUNT(*) FROM {table} WHERE {flag_col}=1 AND {reason_col} IS NULL; -- expect 0. Returns 0 when the write never set {flag_col}=1 for any row.`
- CORRECT: assert the column is bound (count where `{flag_col}=1` > 0) AND then the invariant over it (count where `{flag_col}=1 AND {reason_col} IS NULL` = 0). General form: a criterion whose pass condition is reachable by doing nothing is not a criterion.

---

*This rule applies to all task files that reference DB tables. The Schema Pin is the single source of truth for column and constraint shape during DELEGATED dispatch — keep it current.*

*Companion files: [verify-before-cite.md](verify-before-cite.md) (§9.B verify-before-cite discipline — the general form of this rule).*
