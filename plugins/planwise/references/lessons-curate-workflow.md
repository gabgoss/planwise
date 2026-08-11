---
description: Two-phase lessons-learned curation workflow — categorise uncategorised lessons and track promotion artifacts. Loaded by /planwise lessons curate.
---

# Lessons-Curate Workflow

## Purpose

Keep `{lessons_dir}/00-Categorization-By-Domain.md` in sync with the master lesson index and track which lessons have landed as permanent artifacts (rules, CLAUDE.md, code, agents, skills, settings). This workflow categorises new lessons into the project's configured bucket taxonomy, classifies each lesson's promotion target type, and appends rows to the master index's Rule Promotion Log — it does NOT author new `LL-*` files.

---

## Table of Contents

- [1. Inputs and Outputs](#1-inputs-and-outputs)
- [2. Workflow Overview](#2-workflow-overview)
- [3. Phase 1 — Categorize New Lessons](#3-phase-1--categorize-new-lessons)
- [4. Phase 2 — Land Promoted Lessons (and heal documented→promoted)](#4-phase-2--land-promoted-lessons-and-heal-documentedpromoted)
- [5. Domain Bucket Decision Tree](#5-domain-bucket-decision-tree)
- [6. Reporting Format](#6-reporting-format)
- [7. Constraints](#7-constraints)
- [8. Example Invocations](#8-example-invocations)

---

## 1. Inputs and Outputs

All paths resolve from `config.yaml: project.planwise_root + project.lessons_dir`. The variable `{lessons_dir}` below denotes the resolved value (commonly `planwise/LessonsLearned/`).

| File | Role | Read | Write |
|------|------|------|-------|
| `{lessons_dir}/{lessons_index}` | Master table; ID range; Rule Promotion Log | Yes | Phase 1 — bump a stale "Next available ID" counter, on explicit consent only (§3.1). Phase 2 — append rows to Rule Promotion Log (deduplicated, §4.3); update Status column in Master Table; repoint a healed lesson's File link when §4.4 moves it to `Archive/` |
| `{lessons_dir}/00-Categorization-By-Domain.md` | Domain buckets (one section per `categorization.buckets[]` from `config.yaml`) | Yes | Phase 1 — append rows to relevant bucket tables |
| `{lessons_dir}/LL-{NNN}-*.md` | Individual lesson frontmatter + body | Yes (in full for new lessons; frontmatter only for promotion check) | Phase 1 — set/refine `promotion-target:`. Phase 2 — flip `promoted`→`rule`/`applied` and set `applied-as`; heal `documented`→`promoted` and set `promoted-to:` (user-gated, §4.1b). After any archive move, rewrite stale sibling-lesson cross-reference links to their `Archive/` path (§4.5) |
| `{lessons_dir}/Archive/` | Destination for `promoted`, `applied`, and `rule` lessons (may not exist yet) | List | Optional — move files here only for the heal step (§4.4); `promoted` lessons reaching Phase 2 via `promote-batch` are already archived at capture |
| `config.yaml: categorization` | Bucket schema, decision-tree order, default bucket | Yes | No |

---

## 2. Workflow Overview

> [!protocol] Two-Phase Curation
> 1. **Phase 1 — Categorize new lessons** (default first). Diff master index against the categorisation file; read uncategorised lessons in full; place each into one of the buckets declared in `config.yaml: categorization.buckets`; also classify each lesson's promotion target type (§3.6) — a lesson spanning more than one target type is flagged a split-candidate; update the categorisation tables.
> 2. **Phase 2 — Land promoted lessons (and heal documented→promoted).** Find lessons with `status: promoted` whose owning backlog item(s) have shipped; verify the artifact and flip them to `applied`/`rule`, setting `applied-as`; leave lessons with an unshipped owner at `promoted` and report them as "awaiting landing" (not an anomaly); also heal any `documented` lesson that is fully owned by a backlog item forward to `promoted` (user-gated, §4.1b — this is the only step in Phase 2 that moves a file to `Archive/`). Append rows to the master index's Rule Promotion Log.
>
> Run both phases unless `$ARGUMENTS` specifies `--phase=categorize` or `--phase=promote`. Default is `--phase=both`.

Report a summary at the end with the new ID ranges processed and any anomalies (missing files, frontmatter without `applied-as`, lessons referenced in the master table but missing from disk, etc.).

---

## 3. Phase 1 — Categorize New Lessons

### 3.1 Identify uncategorised lessons

> [!gate] Reconcile the "Next available ID" counter before reading the index
> That counter is a denormalized cache of one fact — the highest lesson ID that exists anywhere — and it has exactly one writer: capture mode. A lesson authored any other way (a hand-written closeout capture, a task-runner producing one as a sprint deliverable) leaves it stale, and curate is the read path best positioned to notice. Never consume the stated value as a boundary; derive the true one.
>
> Run the index-drift audit procedure in [`index-drift-audit.md`](index-drift-audit.md) against the **lessons** index (`reconcile_lessons.py`, banner `planwise lessons curate — lessons index counter drift audit`) — the lessons-index binding there carries the counter-drift specifics (the `next_id` JSON key, the four anomaly kinds, forward-only reconcile). This is the lessons-index analogue of `/planwise doctor` Stage 13; neither re-implements the other's comparison.
>
> Report every drift and anomaly under **Anomalies** in the §6 summary — a stale counter is not a fix-in-passing but a signal in its own right: some lesson was authored off the capture path, so its Master-Table row and its categorisation entry were hand-made too and may carry their own gaps.

1. Read `{lessons_dir}/{lessons_index}` and extract every `LL-NNN` row from the Master Table. The **Master Table section is the boundary**: a row inside it is a real lesson, and the `LL-{NNN}` forms in the Naming Convention and Lesson File Template sections are placeholders, not lessons. Do not use the "Next available ID" line's position or its value to bound the set — it is a counter, not a row.
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

Keep severity-formatting consistent with existing rows (HIGH/MEDIUM/LOW; bold the ID with `**LL-NNN**` only when status is `applied` or `rule`). Bump the `Last Updated:` line at the top of the file to today's date and append a parenthetical summary, e.g.: `2026-04-27 (added LL-N, LL-M; LL-M marked applied)`.

> [!practice] Sort Within a Bucket
> Order between severity tiers: HIGH → MEDIUM → LOW. Within a severity tier, append to the END of the matching block — do not rearrange existing rows. Preserve whichever ID ordering (ascending or descending) the bucket already uses.

### 3.5 Update cross-cutting observations (optional)

If the new batch of lessons reinforces an existing observation in the Cross-cutting observations section (recurring anti-patterns, severity-distribution counts, common technologies), refresh the count or append a new bullet.

> [!constraint] Categorisation File Is Append-Mostly
> WRONG: Rewrite existing observations to "improve" the file or reorder existing rows.
> CORRECT: Append new rows in the right severity slot. Update the `Last Updated:` line. Touch existing observations only if the new evidence makes them numerically wrong (e.g., severity-distribution counts).

### 3.6 Target-Type Classification

While reading each uncategorised lesson in full (§3.2), also determine — or refine — its `promotion-target` frontmatter value(s) from the lesson body: what kind of artifact would this lesson's fix ultimately become?

| Target type | Neutral artifact destination |
|-------------|------------------------------|
| `rule` | `.claude/rules/` |
| `code` | application code |
| `claude-md` | `CLAUDE.md` |
| `agent` | `.claude/agents/` |
| `skill` | `.claude/skills/` |
| `settings` | settings file |

Use the lesson's existing callout and markdown conventions to infer the type — no new markup is needed: a fenced code block or diff reads as `code`; a `MUST`/`NEVER` callout reads as `rule`; guidance meant for durable project-wide context reads as `claude-md`; a reusable multi-step procedure reads as `skill`; a delegatable role definition reads as `agent`; a permission or config toggle reads as `settings`.

A single value is a single-purpose lesson (promotes 1:1 to a backlog item). If the lesson body genuinely spans more than one target type, set all matching values on `promotion-target:` and report the lesson as a **split-candidate** in the chat summary (§6) — do not silently pick one.

---

## 4. Phase 2 — Land Promoted Lessons (and heal documented→promoted)

### 4.1 Find promoted lessons awaiting landing

Grep all `LL-NNN-*.md` files in `{lessons_dir}/` for `status: promoted` in their YAML frontmatter using the `Grep` tool:

```
pattern: ^status: promoted$
path: {lessons_dir}
glob: **/LL-*.md
output_mode: files_with_matches
```

Read each match and capture: `id`, `title`, `date`, `status`, `applied-as`, `promoted-to`, and the deprecated `rule-as` (a lesson written under the older scheme carries its artifact pointer there — see the Pointer Fields definition in `seed/00-Index-LessonsLearned.md`).

### 4.1b Heal fully-owned documented lessons

Some lessons remain `status: documented` even though every fragment of their content is already owned by a drafted backlog item — for example, ownership was recorded after the lesson was captured, rather than through `promote-batch`. Grep for candidates:

```
pattern: ^status: documented$
path: {lessons_dir}
glob: **/LL-*.md
output_mode: files_with_matches
```

For each match, check whether a backlog item now owns the lesson's ENTIRE content (not just a fragment of it). If so, it is a heal candidate: `documented` → `promoted`, with `promoted-to:` set to the owning item id(s).

> [!gate] Heal Is User-Gated
> Do NOT flip `documented` → `promoted` silently. Surface each heal candidate (lesson id, owning item id, evidence of full ownership) to the user and wait for approval before writing the frontmatter change. A lesson that is only PARTIALLY owned (some content still unowned) is NOT a heal candidate — leave it `documented`.

### 4.2 Resolve ownership and verify landing readiness

For each lesson found in §4.1 (`status: promoted`), resolve every id in its `promoted-to:` field to that backlog item's current status.

1. **All owning items shipped (status COMPLETE).** The lesson is ready to land. Verify the destination artifact now exists — the expected destination patterns (illustrative, not exhaustive) are:

   | Destination | Convention | Example |
   |-------------|-----------|---------|
   | `.claude/rules/**` | Promotion to a rule (highest tier) | `.claude/rules/{domain}/{name}.md` |
   | `CLAUDE.md` (project or global) | Promotion to durable project guidance | `CLAUDE.md` (root) |
   | `src/**` or other code path | Lesson encoded directly in code (with explanatory comment) | `src/{module}/{file}.{ext}` |
   | `.claude/settings.local.json` / `.claude/settings.json` | Lesson encoded as a setting/permission | `.claude/settings.local.json` |

   The list is illustrative: a rule/convention artifact may live outside `.claude/rules/**` (for example, a shared conventions or reference document a project treats as its rule surface). Match the artifact by the landing path the owning item recorded (or the lesson's `applied-as:`, falling back to a deprecated `rule-as:` on a legacy-scheme lesson), and let the lesson's `promotion-target:` — not the destination folder — determine the `rule` vs `applied` status in §4.3.

   If the artifact exists, proceed to §4.3 (log + flip). If it does not, flag it as an anomaly — the owning item claims completion but left no verifiable artifact; do NOT append a log row without a verifiable destination.

2. **Any owning item still active (not yet COMPLETE).** Leave the lesson at `status: promoted`. Report it in the chat summary as **"awaiting landing"** — this is NOT an anomaly; a `promoted` lesson with an unshipped owner is the expected resting state (archived ≠ landed).

> [!practice] Anomaly Rules — Resolve the Pointer Before Judging
> Evaluate "does this lesson carry an artifact pointer?" against **every recognised pointer key** — `applied-as:` first, then the deprecated `rule-as:` — before classifying. A key that is absent entirely counts the same as one set to `null`. Judging on `applied-as:` alone reports a legacy-scheme lesson as landed-without-a-pointer on every run, when the pointer is simply under the older key.
>
> - **Legitimate, not an anomaly:** `promoted` + no pointer — the lesson is owned and archived, awaiting its backlog item to ship.
> - **Legitimate, not an anomaly:** `promoted` + `applied-as: 'PENDING:BB-{NNN}'` — a coarse lesson where some fragments have already landed and others are still only owned.
> - **Migration suggestion, NOT an anomaly:** `rule` or `applied` with a pointer present **only** under `rule-as:`. The lesson is correctly landed; its frontmatter predates the current scheme. Report it in the chat summary as a migration candidate — remap per the Pointer Fields definition in `seed/00-Index-LessonsLearned.md` — and continue processing it normally.
> - **ANOMALY:** `rule` or `applied` with no pointer under `applied-as:` **or** `rule-as:` — the lesson claims to be landed but carries no artifact pointer anywhere. Flag this in the chat report.

### 4.3 Update the Rule Promotion Log, then flip the lesson

Append one row per promoted lesson to the table at the bottom of `{lessons_dir}/{lessons_index}`:

```markdown
| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| 2026-05-16 | LL-NNN | Rule promotion (parameterised query) | `.claude/rules/db/parameterised-queries.md` |
```

Use the lesson's frontmatter `date` if it represents the promotion date; otherwise use the date the `applied-as` artifact was created (read from `git log -1 --format=%ci -- <path>`).

Update the Master Table row's Status column to match the lesson frontmatter (`applied` or `rule`). Do NOT change the Status Definitions table.

> [!gate] Deduplicate Before Appending
> Single-lesson `/planwise lessons promote` (handler Stage 7) also appends a row to the Rule Promotion Log at promotion time. Before appending, parse the existing log and skip any `(lesson_id, artifact_path)` tuple that is already present. Dedup key is the pair — a lesson with multiple `applied-as` paths (§4.5) gets one row per *new* path, even if a sibling path is already logged. Count skipped tuples in the Phase 2 summary as `Already logged: N` so the anomaly section stays honest.

**After the log row is written**, flip the lesson's own frontmatter to reflect the landing:

1. Set the terminal status from the lesson's **`promotion-target:`** field — the intent recorded at capture is authoritative. A rule / convention / guidance / reusable-artifact target (`rule`, `claude-md`, `agent`, `skill`) → `status: rule`; an implementing code or config change (`code`, `settings`) → `status: applied`. Do NOT gate `rule` on the artifact living under `.claude/rules/**` — a project may site its rule/convention artifacts elsewhere (for example, a shared conventions or reference document it treats as its rule surface), so the `promotion-target:` intent, not the destination folder, decides `rule` vs `applied`. Only if `promotion-target:` is unset, fall back to inferring from the destination path (a rule/convention artifact → `rule`; a code path → `applied`).
2. Set `applied-as:` to the real, verified destination path — replacing `null` or a `PENDING:BB-{NNN}` placeholder. If the lesson carried its pointer under the deprecated `rule-as:`, complete the remap here: the artifact path moves into `applied-as:`, any owning-item value previously sitting in `applied-as:` moves into `promoted-to:` in id form, and `rule-as:` is dropped.
3. Leave `promoted-to:` untouched (unless step 2's legacy remap is populating it); it still records which backlog item(s) did the work.

Write the log row before the frontmatter flip — the log is the durable trail, and the flip only happens once that trail exists.

### 4.4 Archive move — heal step only

Landing a `promoted` lesson (§4.2–4.3) never moves its file: a lesson reaching §4.1 is already in `Archive/`, because `promote-batch` archives at capture (`documented` → `promoted` is archive-on-capture).

The archive move in this section applies ONLY to the heal step (§4.1b). When a `documented` lesson is healed to `promoted`, move it to `Archive/` in the same step — this mirrors `promote-batch`'s archive-on-capture behaviour and keeps `promoted` lessons consistently archived (see the branching lifecycle in [handlers/lessons.md](../handlers/lessons.md#lesson-status-lifecycle)).

> [!gate] Confirm Before Moving
> Moving a lesson file changes its path. Do NOT execute the heal-step move without explicit user approval — even in auto mode, this is a structural change to the lessons directory. Bundle this approval with the heal approval from §4.1b; do not ask twice.

If the user approves the heal, create `{lessons_dir}/Archive/` (or whatever archive folder is configured) if it does not exist and move the file with `git mv` (preserves history). After moving, update the master-table File-link column if any links break.

### 4.5 Cross-check Companion / Cross-references blocks

Some lessons reference each other (e.g., LL-X cites LL-Y). When a referenced lesson is moved to `Archive/`, the link target changes. After any move, grep the remaining lessons for stale `[LL-NNN](LL-NNN-*.md)` links and rewrite them to `[LL-NNN](Archive/LL-NNN-*.md)`. Skip this step if no files were moved.

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
| LL-N | C | MEDIUM | ... |
| LL-M | A | HIGH | ... |

**Split candidates (multi-target `promotion-target`):** K
- LL-N: `[rule, code]` — spans both a convention and an implementation; consider splitting

## Phase 2 — Landings

**Landed (promoted → rule/applied):** M
**Awaiting landing (owning item still active):** N
**Healed (documented → promoted):** K
**Already logged (deduplicated):** K2  _<!-- per §4.3 gate; pairs already present in the Rule Promotion Log -->_
**Legacy-scheme migration candidates:** K3  _<!-- per §4.2; pointer present only under the deprecated `rule-as:` — reported, not an anomaly -->_

| ID | Status | Artifact | Date |
|----|--------|----------|------|
| LL-NNN | applied | `src/lib/example.py` | 2026-05-16 |

## Anomalies

- "Next available ID" counter stale: stated LL-NNN, true next LL-NNN — a lesson was authored outside capture mode; corrected / left as-is per §3.1
- "Next available ID" counter ahead of the true next ID (an ID may have been retired) — reported, never lowered
- LL-NNN `status: applied`/`rule` with no pointer under `applied-as:` or the deprecated `rule-as:` (claims landed, no artifact pointer anywhere)
- LL-NNN referenced in master table but file not on disk
- LL-NNN on disk (or in `Archive/`) with no master-table row
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
| "Categorise new lessons added since LL-NNN" | Phase 1 only | `/planwise lessons curate --phase=categorize` |
| "Land lessons whose backlog items have shipped" | Phase 2 only — §4.1-§4.3 | `/planwise lessons curate --phase=promote` |
| "Which lessons became rules?" | Phase 2 read-only — list `status: rule` lessons without writing | `/planwise lessons curate --phase=promote` (then decline the log-update prompt) |
| "Heal a fully-owned documented lesson to promoted" | Phase 2 heal step (§4.1b) with the Archive move approved | `/planwise lessons curate --phase=promote` (approve the heal + Archive prompt) |

---

*Cross-references: [00-Index-LessonsLearned.md]({lessons_dir}/00-Index-LessonsLearned.md), [00-Categorization-By-Domain.md]({lessons_dir}/00-Categorization-By-Domain.md), [skill-authoring.md](skill-authoring.md).*
