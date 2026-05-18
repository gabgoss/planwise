---
description: Two-phase lessons-learned curation workflow — categorise uncategorised lessons and track promotion artifacts. Loaded by /planwise lessons curate.
---

# Lessons-Curate Workflow

## Purpose

Keep `{lessons_dir}/00-Categorization-By-Domain.md` in sync with the master lesson index and track which lessons have been promoted to permanent artifacts (rules, CLAUDE.md, code, settings). This workflow categorises new lessons into the project's configured bucket taxonomy and appends rows to the master index's Rule Promotion Log — it does NOT author new `LL-*` files.

---

## Table of Contents

- [1. Inputs and Outputs](#1-inputs-and-outputs)
- [2. Workflow Overview](#2-workflow-overview)
- [3. Phase 1 — Categorize New Lessons](#3-phase-1--categorize-new-lessons)
- [4. Phase 2 — Track Promotions to Permanent Artifacts](#4-phase-2--track-promotions-to-permanent-artifacts)
- [5. Domain Bucket Decision Tree](#5-domain-bucket-decision-tree)
- [6. Reporting Format](#6-reporting-format)
- [7. Constraints](#7-constraints)
- [8. Example Invocations](#8-example-invocations)

---

## 1. Inputs and Outputs

All paths resolve from `config.yaml: project.planwise_root + project.lessons_dir`. The variable `{lessons_dir}` below denotes the resolved value (commonly `planwise/LessonsLearned/`).

| File | Role | Read | Write |
|------|------|------|-------|
| `{lessons_dir}/{lessons_index}` | Master table; ID range; Rule Promotion Log | Yes | Phase 2 only — append rows to Rule Promotion Log; update Status column in Master Table |
| `{lessons_dir}/00-Categorization-By-Domain.md` | Domain buckets (one section per `categorization.buckets[]` from `config.yaml`) | Yes | Phase 1 — append rows to relevant bucket tables |
| `{lessons_dir}/LL-{NNN}-*.md` | Individual lesson frontmatter + body | Yes (in full for new lessons; frontmatter only for promotion check) | No |
| `{lessons_dir}/Archive/` | Destination for `applied`/`rule` lessons (may not exist yet) | List | Optional — move files here only when user opts in |
| `config.yaml: categorization` | Bucket schema, decision-tree order, default bucket | Yes | No |

---

## 2. Workflow Overview

> [!protocol] Two-Phase Curation
> 1. **Phase 1 — Categorize new lessons** (default first). Diff master index against the categorisation file; read uncategorised lessons in full; place each into one of the buckets declared in `config.yaml: categorization.buckets`; update the categorisation tables.
> 2. **Phase 2 — Track promotions.** Find lessons with `status: applied` or `status: rule` in their frontmatter; verify the artifact path in `applied-as`; append rows to the master index's Rule Promotion Log; optionally move the lesson file to `Archive/` (user-gated).
>
> Run both phases unless `$ARGUMENTS` specifies `--phase=categorize` or `--phase=promote`. Default is `--phase=both`.

Report a summary at the end with the new ID ranges processed and any anomalies (missing files, frontmatter without `applied-as`, lessons referenced in the master table but missing from disk, etc.).

---

## 3. Phase 1 — Categorize New Lessons

### 3.1 Identify uncategorised lessons

1. Read `{lessons_dir}/{lessons_index}` and extract every `LL-NNN` row from the Master Table. Note the "Next available ID" line — anything below it is a real lesson.
2. Read `{lessons_dir}/00-Categorization-By-Domain.md` and extract every `LL-NNN` ID currently listed in any bucket table (every section declared in `config.yaml: categorization.buckets` plus the Classification edge cases table at the bottom).
3. Compute `uncategorized = master_ids − categorized_ids`. List the result in the chat before reading any lesson body.
4. If the result is empty, skip to Phase 2 with the message *"All lessons are already categorised."*

### 3.2 Read each uncategorised lesson in full

For each `LL-NNN` not in the categorisation file, read the file with the `Read` tool. Do NOT skim or rely on the index title — bucket placement depends on the lesson body and frontmatter (`category`, `severity`, `language`, `technology`, `domain`).

### 3.3 Classify into a bucket

Apply the decision tree from §5. The first bucket whose `triggers:` match the lesson's frontmatter wins; if no triggers match, the lesson lands in `categorization.default_bucket`.

If the lesson genuinely spans buckets, place it in the bucket matching the **lesson's primary failure surface** (where the bug landed, not where the fix was authored) and add a row to the Classification edge cases table at the bottom of the categorisation file with a one-line justification.

### 3.4 Update the categorisation file

> [!gate] Confirm Bucket Assignment Before Writing
> If any lesson's bucket assignment is ambiguous (multiple `triggers:` matched, or no triggers matched but the `default_bucket` feels wrong), surface the candidates to the user and request approval before appending the row. Silent mis-bucketing is harder to undo than a brief pause to confirm.

Append a row to the matching table preserving the existing column order. The column schema is determined by the bucket's optional `code_bucket: true` flag in `config.yaml`:

| Bucket variant | Required columns |
|----------------|------------------|
| Default (3-col) | `ID`, `Title`, `Severity` |
| `code_bucket: true` (4-col) | `ID`, `Title`, `Module`, `Severity` |

Keep severity-formatting consistent with existing rows (HIGH/MEDIUM/LOW; bold the ID with `**LL-NNN**` only when status is `applied` or `rule`). Bump the `Last Updated:` line at the top of the file to today's date and append a parenthetical summary, e.g.: `2026-04-27 (added LL-002, LL-003; LL-003 marked applied)`.

> [!practice] Sort Within a Bucket
> Order between severity tiers: HIGH → MEDIUM → LOW. Within a severity tier, append to the END of the matching block — do not rearrange existing rows. Preserve whichever ID ordering (ascending or descending) the bucket already uses.

### 3.5 Update cross-cutting observations (optional)

If the new batch of lessons reinforces an existing observation in the Cross-cutting observations section (recurring anti-patterns, severity-distribution counts, common technologies), refresh the count or append a new bullet.

> [!constraint] Categorisation File Is Append-Mostly
> WRONG: Rewrite existing observations to "improve" the file or reorder existing rows.
> CORRECT: Append new rows in the right severity slot. Update the `Last Updated:` line. Touch existing observations only if the new evidence makes them numerically wrong (e.g., severity-distribution counts).

---

## 4. Phase 2 — Track Promotions to Permanent Artifacts

### 4.1 Find promoted lessons

Grep all `LL-NNN-*.md` files in `{lessons_dir}/` for `status: applied` or `status: rule` in their YAML frontmatter using the `Grep` tool:

```
pattern: ^status: (applied|rule)$
path: {lessons_dir}
glob: **/LL-*.md
output_mode: files_with_matches
```

Read each match and capture: `id`, `title`, `date`, `status`, `applied-as`.

### 4.2 Verify the destination artifact

For each promoted lesson, confirm the file path in `applied-as` actually exists. The four expected destination patterns are:

| Destination | Convention | Example |
|-------------|-----------|---------|
| `.claude/rules/**` | Promotion to a rule (highest tier) | `.claude/rules/{domain}/{name}.md` |
| `CLAUDE.md` (project or global) | Promotion to durable project guidance | `CLAUDE.md` (root) |
| `src/**` or other code path | Lesson encoded directly in code (with explanatory comment) | `src/{module}/{file}.{ext}` |
| `.claude/settings.local.json` / `.claude/settings.json` | Lesson encoded as a setting/permission | `.claude/settings.local.json` |

If `applied-as` is `null` but `status` is not `documented`, flag it in the chat as an anomaly. Do NOT append a row to the log without a verifiable destination.

### 4.3 Update the Rule Promotion Log

Append one row per promoted lesson to the table at the bottom of `{lessons_dir}/{lessons_index}`:

```markdown
| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| 2026-05-16 | LL-001 | Rule promotion (parameterised query) | `.claude/rules/db/parameterised-queries.md` |
```

Use the lesson's frontmatter `date` if it represents the promotion date; otherwise use the date the `applied-as` artifact was created (read from `git log -1 --format=%ci -- <path>`).

Update the Master Table row's Status column to match the lesson frontmatter (`applied` or `rule`). Do NOT change the Status Definitions table.

> [!gate] Deduplicate Before Appending
> Single-lesson `/planwise lessons promote` (handler Stage 7) also appends a row to the Rule Promotion Log at promotion time. Before appending, parse the existing log and skip any `(lesson_id, artifact_path)` tuple that is already present. Dedup key is the pair — a lesson with multiple `applied-as` paths (§4.5) gets one row per *new* path, even if a sibling path is already logged. Count skipped tuples in the Phase 2 summary as `Already logged: N` so the anomaly section stays honest.

### 4.4 Optional — Move file to Archive/

The master index typically says: *"Lessons with status `applied` or `rule` are moved to `Archive/` as part of the promotion workflow."*

This workflow SHOULD NOT move files automatically. Surface the candidates and ask the user whether to move them.

> [!gate] Confirm Before Moving
> Moving a lesson file changes its path. Do NOT execute the move without explicit user approval — even in auto mode, this is a structural change to the lessons directory.

If the user approves, create `{lessons_dir}/Archive/` (or whatever archive folder is configured) if it does not exist and move each file with `git mv` (preserves history). After moving, update the master-table File-link column if any links break.

### 4.5 Cross-check Companion / Cross-references blocks

Some lessons reference each other (e.g., LL-002 cites LL-001). When a referenced lesson is moved to `Archive/`, the link target changes. After any move, grep the remaining lessons for stale `[LL-NNN](LL-NNN-*.md)` links and rewrite them to `[LL-NNN](Archive/LL-NNN-*.md)`. Skip this step if no files were moved.

> [!constraint] Decompose Multi-Destination Lessons
> WRONG: A single lesson promoted to two artifacts is logged as one ambiguous row.
> CORRECT: If a lesson's `applied-as` field lists multiple paths (comma-separated or array), append ONE row to the Rule Promotion Log per destination artifact. The lesson keeps a single Status value (`applied` or `rule`) but the log preserves the per-artifact trail.

---

## 5. Domain Bucket Decision Tree

The decision tree is config-driven. Do NOT hard-code bucket IDs in workflow logic. Read the project's taxonomy from `config.yaml: categorization` and apply the rules below.

### 5.1 Algorithm

> [!protocol] Bucket Selection (in order)
> 1. Read `categorization.buckets` from `config.yaml`. Iterate in the order declared by `categorization.decision_tree_order` (a list of `bucket.id` values).
> 2. For each bucket, inspect its optional `triggers:` block. A bucket matches the lesson when ANY of:
>    - `triggers.technology` shares at least one value with the lesson frontmatter's `technology:` list, OR
>    - `triggers.domain` shares at least one value with the lesson frontmatter's `domain:` list.
> 3. The first matching bucket wins. Stop iterating.
> 4. If no bucket matches, use `categorization.default_bucket` (a `bucket.id` value).
> 5. If the matched bucket declares `sub_buckets:`, repeat steps 2-4 over the sub-bucket list to select a sub-bucket. If no sub-bucket matches, place the row in the parent bucket's table without a sub-bucket assignment.

### 5.2 Concrete example (4-bucket generic ship default)

Given the ship-default `config.yaml`:

```yaml
categorization:
  buckets:
    - id: A
      slug: database
      name: "Database / SQL"
    - id: B
      slug: code
      name: "Application Code"
    - id: C
      slug: process
      name: "Planwise / Process"
      sub_buckets: []
    - id: D
      slug: tooling
      name: "Tooling / Ergonomics"
  decision_tree_order: [A, B, C, D]
  default_bucket: D
```

The ship default carries no `triggers:` blocks, so every uncategorised lesson lands in `default_bucket: D` until the project adds `triggers:` per bucket. A typical post-customisation `config.yaml` might add:

```yaml
- id: A
  triggers:
    technology: [sql, mssql, postgres, pyodbc, sqlite]
    domain: [DB, SCHEMA]
- id: B
  triggers:
    technology: [python, javascript, typescript, pyright, ruff, eslint]
    domain: [APP]
- id: C
  triggers:
    domain: [PROC, PMS]
```

With those triggers, a lesson with `technology: [sql, mssql]` matches bucket A on the first iteration. A lesson with `technology: [notebook]` matches no `triggers:` block and falls through to `default_bucket: D`.

### 5.3 Edge-case heuristics

Edge-case rules below use the project's `lesson_abbreviations` (from `config.yaml`) as the source of truth for `domain:` values. Generic phrasing — substitute the project's own abbreviations.

- A lesson tagged with multiple `domain:` values (e.g., `[PROC, APP]`) is bucketed by the first matching bucket per the decision tree order. If the bucket choice still feels ambiguous, add it to the Classification edge cases table with a one-line note explaining why the alternative bucket was rejected.
- A lesson whose `technology:` matches one bucket but whose `domain:` matches a different bucket goes to the FIRST matching bucket per `decision_tree_order` (technology and domain triggers are OR-combined within a bucket but bucket order itself is strict).
- A lesson tagged `domain: [BUG]` (or whatever the project uses for bug-fix tagging) is informational only — do NOT bucket on `BUG` alone; fall back to the `technology:` field.
- Lessons missing both `technology:` and `domain:` go to `default_bucket` and SHOULD be flagged as anomalies in the chat report so the user can add the missing frontmatter.

---

## 6. Reporting Format

After both phases run, emit a markdown summary to the chat (NOT to a file) with three sections. If a section has zero entries, replace its body with `_None._`.

### 6.1 Summary template

```markdown
## Phase 1 — Categorisation

**New lessons categorised:** N
| ID | Bucket | Severity | One-line title |
|----|--------|----------|----------------|
| LL-002 | C | MEDIUM | ... |
| LL-003 | A | HIGH | ... |

## Phase 2 — Promotions

**Lessons promoted since last sync:** M
**Already logged (deduplicated):** K  _<!-- per §4.3 gate; pairs already present in the Rule Promotion Log -->_

| ID | Status | Artifact | Date |
|----|--------|----------|------|
| LL-001 | applied | `src/lib/example.py` | 2026-05-16 |

## Anomalies

- LL-NNN missing `applied-as` despite `status: applied`
- LL-NNN referenced in master table but file not on disk
- LL-NNN in categorisation file but missing from master table
- LL-NNN missing both `technology:` and `domain:` in frontmatter
```

---

## 7. Constraints

> [!constraint] Do Not Author Lessons
> WRONG: Create a new `LL-NNN-*.md` file because a recurring problem hasn't been documented.
> CORRECT: Tell the user the gap exists and point them at `/planwise lessons capture` (or manual creation per the template in `{lessons_dir}/{lessons_index}`). This workflow only curates existing lessons; it does not author them.

> [!constraint] Categorisation File Is Append-Mostly
> WRONG: Reorder existing rows or rewrite cross-cutting observations to "improve" the file.
> CORRECT: Append new rows in the right severity slot. Update the `Last Updated:` line. Touch existing observations only if the new evidence makes them numerically wrong (e.g., severity-distribution counts).

> [!constraint] Resolve Paths from config.yaml
> WRONG: Hard-code `planwise/LessonsLearned/` (or any other project-specific path) inside rule prose, error messages, or grep commands.
> CORRECT: Resolve `{lessons_dir}` and related paths from `config.yaml: project.planwise_root + project.lessons_dir` at workflow invocation time. Every consumer project may use a different layout — the workflow MUST be path-agnostic.

> [!practice] Date Conversion
> Today's date comes from the runtime — do not hard-code it. Read it from the most recent system reminder (`# currentDate`) or via Bash `date +%Y-%m-%d`.

---

## 8. Example Invocations

| User says | Workflow action | CLI form |
|-----------|-----------------|----------|
| "Refresh the lessons categorisation" | Both phases | `/planwise lessons curate` |
| "Categorise new lessons added since LL-005" | Phase 1 only | `/planwise lessons curate --phase=categorize` |
| "Update the rule promotion log" | Phase 2 only | `/planwise lessons curate --phase=promote` |
| "Which lessons became rules?" | Phase 2 read-only — list `status: rule` lessons without writing | `/planwise lessons curate --phase=promote` (then decline the log-update prompt) |
| "Move applied lessons to Archive/" | Phase 2 with the move-to-Archive step explicitly approved | `/planwise lessons curate --phase=promote` (approve the Archive prompt) |

---

*Cross-references: [00-Index-LessonsLearned.md]({lessons_dir}/00-Index-LessonsLearned.md), [00-Categorization-By-Domain.md]({lessons_dir}/00-Categorization-By-Domain.md), [skill-authoring.md](skill-authoring.md).*
