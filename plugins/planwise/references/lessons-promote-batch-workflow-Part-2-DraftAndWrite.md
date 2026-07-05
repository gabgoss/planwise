---
description: Four-phase batch promotion workflow (Part 2 — Draft BBs, write files, BB structure, self-containment, decomposition, constraints). Loaded by /planwise lessons promote-batch.
---

# Lessons Promote-Batch Workflow — Part 2 (Draft and Write)

This part covers **Phases 3-4** of the batch-promotion workflow, the BB Structure Specification, the binding self-containment grep check, the decomposition mechanics, the constraint set, and example invocations. For Phases 1-2 (resolve scope and group lessons), see [Part-1](lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md).

---

## Table of Contents

- [5. Phase 3 — Draft Each BB](#5-phase-3--draft-each-bb)
- [6. Phase 4 — Write BB Files and Update the Backlog Index](#6-phase-4--write-bb-files-and-update-the-backlog-index)
- [7. BB Structure Specification](#7-bb-structure-specification)
- [8. Self-Containment Verification](#8-self-containment-verification)
- [9. Decomposition Mechanics](#9-decomposition-mechanics)
- [10. Constraints](#10-constraints)
- [11. Example Invocations](#11-example-invocations)

---

## 5. Phase 3 — Draft Each BB

### 5.1 Lesson bodies are already in context (from Phase 1)

Part-1 §3.4 read every in-scope lesson body in full. Do NOT re-read those files in Phase 3 — the content is already loaded. Re-reading wastes tokens and risks the file changing between Phase 1 and Phase 3 reads (the user may have edited a lesson mid-workflow-run).

If a Phase 1 read was missed (e.g., a lesson surfaced via decomposition only after grouping), do that read now — but treat it as an exception, not the routine path.

### 5.2 The self-containment principle (BINDING)

**Canonical reference:** [artifact-self-containment.md](artifact-self-containment.md) is the canonical doc for the self-containment rule. It states the asymmetry between content-bearing artifacts (rules, agents, handlers, CLAUDE.md callouts) and bookkeeping artifacts (indexes, promotion logs, BB Notes), and defines the mechanical grep gate. The examples below specialise that rule for the promote-batch workflow context.

> [!constraint] Promoted Artefacts Are Self-Contained
> WRONG — rule body cites the lesson it came from, leaving the lesson as a load-bearing reference:
> ```markdown
> ## §1. Schema Pin requirement
> Per LL-X, every task file must include a Schema Pin (see LL-X for the
> WRONG/CORRECT examples and the construction recipe).
> ```
> CORRECT — rule body inlines every WRONG/CORRECT example, recipe, and command from the source lessons. The lesson file becomes archival and is NOT cited:
> ```markdown
> ## §1. Schema Pin requirement
> Every task file whose Required Context references a DB table MUST include
> a Schema Pin section.
> WRONG: the brief asserts column shapes from the author's mental model.
>     {full WRONG SQL example inlined verbatim from the lesson body}
> CORRECT: the brief includes a Schema Pin section quoting actual columns.
>     {full CORRECT example inlined verbatim from the lesson body}
> ```

This applies in both directions:

1. **Rules never contain `see LL-XXX` references.** If LL-X's content is needed, it is inlined verbatim in the rule body (or a paraphrase that preserves all WRONG/CORRECT examples and verification commands). If not, the rule does NOT mention LL-X at all.
2. **CLAUDE.md callouts describe the trigger and consequence in plain language.** They point at rules, not lessons. They never reason like *"Reason: LL-X (timezone-mismatch...)"* — they state the reason directly.

> [!constraint] Out-of-Scope Lessons Are Not Cited
> WRONG — BB's rule design includes a "§N. Cross-references" section listing related lessons that were not promoted:
> ```markdown
> ## §5. Cross-references
> Related lessons: LL-X (field-name audit), LL-Y (orchestrator verify).
> ```
> CORRECT — out-of-scope lessons are mentioned ONLY in the BB's "Notes" section as a planning artefact (the BB itself, not the rule). The rule body does not include any cross-reference section pointing at lessons:
> ```markdown
> ## Notes (in the BB file)
> - **Out of scope (intentionally NOT promoted in this BB):** LL-X, LL-Y.
>   They share themes with this rule but describe a different layer; they
>   remain as standalone documented lessons. The rule does NOT cite them.
> ```

### 5.3 Decide rule scope (`paths:` field)

Per [rule-authoring.md](rule-authoring.md):

| Lesson domain | Suggested `paths:` |
|---------------|--------------------|
| Database / SQL / pyodbc | `src/pipeline/**, src/db/**, notebooks/**` |
| Python type-checking, doctest, scipy in `src/` | `src/**, tests/**` |
| Notebook execution ergonomics | `notebooks/**` |
| Planwise plan-authoring discipline | `{planwise_root}/Plans/**, {planwise_root}/Backlog/**` |

Use comma-separated multi-path format; never YAML arrays with 2+ items (per `rule-authoring.md` §1 — broken parser).

### 5.4 Draft the BB deliverables

Each BB has between 2 and 5 deliverables, in this order:

1. **Rule deliverable(s)** — one per target rule. Outline the §-sections, name each promoted lesson whose content is being inlined, state explicitly *"the rule does NOT cite LL-X"*.
2. **Code/settings application deliverable(s)** — one per file that gets a docstring/comment/settings edit.
3. **CLAUDE.md update deliverable** — list each `> [!binding]` callout to add or replace, with the exact text of the callout (rule-pointer language, no lesson references). Include the new row(s) for the "Skills, Rules, and LSPs" Rules table.
4. **Lesson status flip deliverable** — the immediate capture-time flip is `documented → promoted` (done in Phase 4, §6.6, not deferred). The deliverable's table maps each in-scope lesson to its **eventual** landing status (`rule` | `applied`) and `applied-as` path — what curate flips it to once the owning item ships. Note the Rule Promotion Log row count for that eventual landing (curate writes the rows then, not at capture).
5. **Acceptance Criteria** — must include a self-containment grep check (see §8).

### 5.5 Write the Notes section last

The Notes section is the only place where lessons NOT promoted **by THIS specific BB** are mentioned. Two valid framings:

**(a) Lesson decomposed across BBs** — the lesson is fully accounted for, but other fragments live in sibling BBs:

```markdown
- **Decomposed across BBs:** LL-X fragments split across this BB ({fragment-1 description}) + BB-{P} ({fragment-2 description}) + BB-{Q} ({fragment-3 description}). At capture LL-X archives as `promoted` (all fragments are owned); its status flips to `rule` only when ALL three BBs ship.
```

**(b) Lesson owned by another active BB** — already excluded in Part-1 §3.2 step 5; mention only for traceability:

```markdown
- **Owned by other active BB (excluded from this batch run):** LL-X, LL-Y → BB-{Z} (IN_PROGRESS).
```

> [!constraint] No "Stays Documented" Without an Owner
> WRONG — Notes section says: *"LL-X stays documented; shares theme but describes a different layer."* This is the limbo failure mode (Part-1 §4.2).
> CORRECT — every in-scope `documented` lesson has either landed in this BB's deliverables, decomposed across sibling BBs (framing a), or been excluded as owned-by-other-BB (framing b). If a lesson survives Part-1 §3.2 and is not in any deliverable, the BB is incomplete — find its destination per Part-1 §4.2 before writing the file.

---

## 6. Phase 4 — Write BB Files and Update the Backlog Index

### 6.1 Determine the next BB number

Read `{backlog_dir}/{backlog_index}`, find the highest `BB-{NNN}` row across both the active table and `{backlog_dir}/Archive/`, and assign sequential numbers starting from `{highest + 1}`. If the user is producing multiple BBs in one run, assign sequentially — do not skip numbers.

### 6.2 Write each BB file

Path: `{backlog_dir}/BB-{ID}-{SB}-DOC-PromoteLessons{BucketSlug}.md`

| Component | Source | Example |
|-----------|--------|---------|
| `{ID}` | 3-digit zero-padded, sequential from §6.1 | `001` |
| `{SB}` | 2-digit sub-backlog number (`01` for a single-file BB; bump on file splits per the 500-line rule) | `01` |
| `DOC` | Fixed domain abbreviation for promotion BBs (matches `config.yaml: abbreviations.DOC`) | `DOC` |
| `{BucketSlug}` | PascalCase of the bucket's `slug` field from `config.yaml: categorization.buckets[].slug` (e.g., `database` → `Database`, `task-files` → `TaskFiles`) | `Database` |

Use the structure specification in §7. Stay under 500 lines per file (per project file-size rule).

### 6.3 Update the backlog index

Append rows to the master table in `{backlog_index}`:

```markdown
| BB-{NNN} | {one-line title} | {High|Medium|Low} | NOT_STARTED | DOC | {score} | [01](BB-{NNN}-{SB}-DOC-PromoteLessons{BucketSlug}.md) |
```

Leave the Score column placeholder (e.g., `-`) when first writing the row — the score is computed by `score_backlog.py` in §6.4. Set `Abbrev` = `DOC` (these BBs are documentation/rule-authoring work).

Bump the `Last Updated` line at the bottom of the index.

### 6.4 Re-score the backlog

After writing all BB files and appending all rows, run the scoring script to compute Score column values:

```bash
python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
```

This overwrites the Score column with the computed score (8-factor weighting from `config.yaml: scoring`). Promotion BBs typically receive `priority_medium` (default 20) with no bug-fix bonus.

If the script errors, fall back to a manual Medium-priority placeholder and surface the error to the user.

### 6.5 Report summary to chat

Emit a markdown summary with three sections:

```markdown
## BBs drafted

| BB | Title | Lessons archived as promoted | Out-of-scope lessons (stay documented) |
|----|-------|------------------------------|-----------------------------------------|
| BB-{NNN} | ... | LL-X, LL-Y, LL-Z | LL-W |

## Files written

- `{backlog_dir}/BB-{NNN}-{SB}-DOC-PromoteLessons{BucketSlug}.md` ({L} lines)
- `{backlog_dir}/{backlog_index}` (appended {N} rows; re-scored)
- `{lessons_dir}/Archive/` ({N} lessons flipped to `promoted` and `git mv`d from `{lessons_dir}/`)
- `{lessons_dir}/{lessons_index}` (Master Table Status + File-link updated for the {N} archived lessons)

## Anomalies

- {Lessons skipped because already promoted}
- {Lessons missing from categorisation file (if any)}
```

### 6.6 Capture the in-scope lessons (archive-on-capture)

Every in-scope lesson is now fully captured into a drafted backlog item, so it is captured immediately: it flips to `promoted` and moves to the archive. This is the **archive-on-capture** step — completeness of capture IS the gate; there is no per-file prompt.

For each in-scope lesson that landed in a BB deliverable:

1. **Flip the frontmatter.** Set `status: promoted` and populate `promoted-to:` with the owning backlog item id(s) — e.g. `promoted-to: BB-{NNN}`, listing every owner when the lesson decomposed across several BBs.
2. **Move the file to the archive.** `git mv {lessons_dir}/LL-{NNN}-*.md {lessons_dir}/Archive/`. A fully-captured lesson belongs in `Archive/` (archived ≠ landed).
3. **Update the Master Table** in `{lessons_dir}/{lessons_index}`: set the lesson's Status column to `promoted` and repoint its File link to the new `Archive/` path.

**Do NOT write the Rule Promotion Log.** The Promotion Log records a *landing* event — the owning item shipped and its artifact now exists — but at capture the item has only been drafted. Those rows are written later by `/planwise lessons curate --phase=promote`, when the owning item lands and the status flips `promoted → rule|applied`.

Under `--dry-run`, skip this entire step: report the planned flips and archive moves without touching any lesson file, frontmatter, or index row.

---

## 7. BB Structure Specification

> [!taskspec] Promotion BB Structure
> Every promotion BB MUST follow this structure. Frontmatter follows [templates/backlog-item.md](../templates/backlog-item.md); body sections are binding and replace the default `Summary / Problem / Proposed Solution / Acceptance Criteria / Related` body template.
>
> ```markdown
> ---
> id: {NNN}
> title: "{One-line summary including which LL IDs are promoted}"
> priority: {High|Medium|Low}
> status: NOT_STARTED
> abbrev: DOC
> created: {YYYY-MM-DD}
> blocks: []
> ---
>
> # BB-{NNN}-DOC: {Title}
>
> **Priority:** {High|Medium|Low}
> **Status:** NOT_STARTED
> **Domain:** DOC
> **Source:** /planwise lessons promote-batch — Bucket {X} ({BucketName})
>
> ---
>
> ## Problem
>
> {Why these lessons need promoting; recurrence count, evidence, blast radius. 1-3 paragraphs.}
>
> ## Evidence
>
> | Lesson | Status today | Recurrences | Already-applied artefact (if any) | Fragment scope |
> |--------|--------------|-------------|------------------------------------|----------------|
> | LL-X | promoted | 3 | - | full lesson |
> | LL-Y | promoted | 2 | - | covers (a) only — (b) in BB-{P} |
>
> ## Proposal
>
> ### Deliverable 1 — Rule: {name} (LL-X + LL-Y content fully inlined)
>
> File: `.claude/rules/{path}.md` ({new} | {extend existing})
> Scope: `paths: {comma-separated paths}`
>
> The rule is self-contained. The rule does NOT cite LL-X or LL-Y.
>
> Content outline:
> 1. **§1. ...** — `> [!constraint]` with WRONG (...) vs CORRECT (...). Includes the full WRONG/CORRECT examples currently in LL-X's body.
> 2. ...
>
> ### Deliverable 2 — {applied-to-code | applied-to-settings} (if any)
>
> {file path, what to inline as a docstring/comment, content fully self-contained, no LL refs}
>
> ### Deliverable 3 — CLAUDE.md updates (rule-pointer only, no LL references)
>
> {exact `> [!binding]` callouts to add — content describes the WHEN-trigger and consequence in plain language; no lesson IDs cited}
>
> ### Deliverable 4 — Lesson status flips + Rule Promotion Log
>
> This table lists each lesson's **eventual** landing status — what it becomes when this item ships. At capture the lesson flips to `promoted` (the immediate status); the flip to `rule`/`applied` below happens later, at landing.
>
> | Lesson | Eventual status (at landing) | applied-as |
> |--------|------------------------------|------------|
> | LL-X | rule | `.claude/rules/{path}.md` §1 |
> | LL-Y | rule | `.claude/rules/{path}.md` §2 |
>
> Capture (this workflow, §6.6) flips each lesson `documented → promoted`, writes `promoted-to:`, and `git mv`s it to `Archive/` — but writes **no** Rule Promotion Log rows yet (the log records landing events). After the owning item lands, `/planwise lessons curate --phase=promote` verifies each `applied-as` path, flips `promoted → rule|applied`, updates the Master Table Status column, and appends the {N} Rule Promotion Log rows in `{lessons_dir}/{lessons_index}`.
>
> ## Acceptance Criteria
>
> - [ ] `{file}` exists with frontmatter `paths: {scope}` and §1-§N from Deliverable 1, all content self-contained
> - [ ] CLAUDE.md updated per Deliverable 3
> - [ ] {N} lesson frontmatters updated; {N} rows added to Rule Promotion Log
> - [ ] {regression checks specific to this BB's domain}
> - [ ] `grep -rnE '(LL-[0-9]{3}|BB-[0-9]{3})' .claude/rules/{path}.md .claude/agents/{paths-touched} .claude/skills/{paths-touched} .claude/commands/{paths-touched} CLAUDE.md` returns zero matches (artifact self-containment check — see `references/artifact-self-containment.md` §4)
> - [ ] `/planwise lessons curate` reports no anomalies after the run
>
> ## Notes
>
> - {execution order hints}
> - **Out of scope (intentionally NOT promoted in this BB):** {LL IDs with one-line reason each}. They remain as standalone documented lessons. They are NOT cited from any rule produced by this BB.
> ```

**Why this body replaces the default template:** Promotion BBs are descriptions of rule-authoring work, not generic feature work. The default `Summary / Problem / Proposed Solution / Acceptance Criteria / Related` body in `templates/backlog-item.md` is generic and lacks the Deliverables structure needed to encode the self-containment principle. The deliverable-based body above is the binding shape for promotion BBs and overrides the default template body. Frontmatter remains identical to other BBs so `score_backlog.py`, `parse_backlog.py`, and `update_backlog.py` continue to work unchanged.

---

## 8. Self-Containment Verification

**Canonical reference:** [artifact-self-containment.md §4 Mechanical Verification](artifact-self-containment.md#4-mechanical-verification) defines the canonical grep — it covers BOTH `LL-NNN` and `BB-NNN` patterns and scans rules, agents, skills, handlers/commands, AND `CLAUDE.md`. Every BB drafted by this workflow MUST include that grep as an Acceptance Criterion. The minimal acceptance row to insert into a BB drafted by this workflow:

> [!verify] Self-Containment Grep (BB Acceptance Row)
> ```bash
> # Bash / POSIX — replace {paths-touched} with the files this BB writes:
> grep -rnE '(LL-[0-9]{3}|BB-[0-9]{3})' \
>   .claude/rules/{paths-touched} \
>   .claude/agents/{paths-touched} \
>   .claude/skills/{paths-touched} \
>   .claude/commands/{paths-touched} \
>   CLAUDE.md
> # MUST return zero matches.
> ```
>
> ```powershell
> # PowerShell (Windows shells):
> Get-ChildItem -Path .claude/rules, .claude/agents, .claude/skills, .claude/commands, CLAUDE.md `
>   -Recurse -Include *.md `
>   | Select-String -Pattern '(LL-\d{3}|BB-\d{3})'
> # MUST return zero matches.
> ```

If grep returns matches, the BB executor MUST inline the cited content into the rule body or remove the reference. The check is binary — any `LL-NNN` or `BB-NNN` reference in any content-bearing artifact is a fail.

This check is what prevents the BB from drifting back into "see LL-XXX" or "per BB-XXX" cross-references during implementation. Do not omit it. See [artifact-self-containment.md §4.1](artifact-self-containment.md#41-what-the-grep-deliberately-does-not-cover) for the exempt zones (lessons/backlog dirs, README changelog, plugin-internal design labels) and [§7 Exemptions](artifact-self-containment.md#7-exemptions) for handling the rare legitimate sample/placeholder patterns.

---

## 9. Decomposition Mechanics

A single lesson MAY span multiple BBs when its body covers content for distinct rules (see Part-1 §4.4 for the decomposition trigger). This section specifies the mechanics: how each fragment is tracked, how `applied-as` accumulates, and when the lesson's lifecycle state flips.

### 9.1 Mechanics table

| Mechanic | Rule |
|----------|------|
| **Each BB cites LL-X in its Evidence row** | Add a *Fragment scope* column noting "covers (a) only", "covers (b)+(c)", etc. |
| **Lesson archives as `promoted` once every fragment is OWNED** | When each fragment is owned by a drafted backlog item, the lesson flips `documented → promoted` and archives at capture (archive-on-capture, §6.6) — regardless of how many BBs its fragments span. It does not linger in `documented`; a fully-owned lesson rests at `promoted` until its fragments land. |
| **`applied-as` accumulates as fragments land (a post-`promoted`, curate-driven mechanism)** | After the lesson rests at `promoted`, each fragment that ships adds its artifact path to `applied-as` (curate writes this at landing). Example: `applied-as: '.claude/rules/X.md §1, .claude/rules/Y.md §2, PENDING:BB-{NNN}'` while the third fragment is still owned-but-unshipped. Drop each `PENDING:` marker once its fragment lands. |
| **Promotion Log tracks each fragment** | One Rule Promotion Log row per fragment per BB, written by curate when that fragment lands (never at capture). The same LL-X appears in N rows when it decomposes across N BBs. |
| **Status flips `promoted → rule` (or `applied`) only when the last fragment lands (a post-`promoted`, curate-driven mechanism)** | The curate workflow's Phase-2 promotion check is the gate: it verifies every path in `applied-as` exists, then flips the Status column off `promoted`. A partially-landed lesson stays `promoted` (never back to `documented`) until the last fragment ships. |
| **Self-containment grep is per-BB** | Each BB's grep check (§8) covers ONLY the fragment files it produces. Cross-BB orchestration is the user's responsibility. |

### 9.2 Why `promoted` is a stable capture state

`promoted` is a **resting state**, not a transient one. It answers one durable question about a lesson: *is this lesson already owned by an actionable backlog item and merely awaiting that item to land, or is it not yet promoted?* A lesson fully captured into drafted backlog item(s) rests at `promoted` — indefinitely, if the owning item sits in the backlog for months — until that item ships. Nothing about `promoted` is mid-transition; it is the stable answer to "owned-and-awaiting-landing vs not-yet-promoted."

This is deliberately **distinct** from the transient partial-landing state an earlier version of this workflow introduced for decomposed lessons — a working state that existed only while *some* fragments had landed and others had not. That transient state was rejected: a lesson's lifecycle status must not flicker as individual fragments ship. The intra-transition bookkeeping — *which* fragments have landed while the lesson is mid-decomposition — is handled instead by the `applied-as` field accumulating real paths and `PENDING:BB-{NNN}` markers (§9.1). That accumulation is **kept**.

The two mechanisms **compose**; they are not alternatives:

- **`status: promoted`** (the resting lifecycle state) records that the lesson is fully owned and archived, awaiting landing. It does not change as fragments land — only the final landing (last fragment) flips it to `rule`/`applied`.
- **`applied-as` with `PENDING:` markers** (the bookkeeping field) records the fine-grained landing progress of each fragment *within* the `promoted → rule|applied` transition.

So a decomposed lesson can legitimately read `status: promoted` **and** `applied-as: '.claude/rules/X.md §1, PENDING:BB-{NNN}'` at once: owned and archived (resting `promoted`), with one fragment already landed and one still awaiting its BB. The lifecycle stays coarse and stable; the per-fragment detail lives in `applied-as`. Both the lesson template in `seed/00-Index-LessonsLearned.md` and the curate workflow's Phase-2 check understand this pairing.

---

## 10. Constraints

> [!constraint] Do Not Create Rule Files
> WRONG — this workflow writes `.claude/rules/{name}.md` directly.
> CORRECT — this workflow writes a BB that DESCRIBES the rule to be created. Rule creation happens at BB execution time (via `/planwise backlog`), not at BB drafting time.

> [!constraint] Modify Lesson Frontmatter at Capture
> WRONG — this workflow flips `status: documented → rule` (or `applied`) in the lesson file, claiming the artifact has landed when only a BB has been drafted.
> CORRECT — this workflow flips `status: documented → promoted` and writes `promoted-to:` at capture time (§6.6), because a fully-captured lesson is now owned by a live backlog item. It does NOT flip to `rule`/`applied` — that landing flip happens later, when the owning item ships, via `/planwise lessons curate --phase=promote` (or the single-lesson `/planwise lessons promote`). Archived ≠ landed.

> [!constraint] Do Not Run /planwise lessons promote
> WRONG — invoke `/planwise lessons promote LL-X` from inside this workflow.
> CORRECT — this workflow is the *batched, deferred* alternative. Promotions happen later when the BB is executed; the single-lesson `promote` mode is for ad-hoc work.

> [!constraint] Categorisation Must Be Up to Date
> WRONG — proceed with grouping when LL-X is in the master index but missing from `00-Categorization-By-Domain.md`.
> CORRECT — STOP and tell the user to run `/planwise lessons curate --phase=categorize` first. Part-1 §3.2's gate catches this.

> [!constraint] Skip Lessons Already Owned By Any BB (Active or Archived)
> WRONG — a `documented` lesson is bundled into a new BB without checking whether an active or archived BB already cites it; result: duplicate promotion paths, conflicting rule edits, corrupted Promotion Log.
> CORRECT — Part-1 §3.2 step 5 greps `LL-{NNN}` against `{backlog_dir}/` (recursive, includes `Archive/`); exclude any hit. Active BB hits → exclude as "owned by BB-{NNN}"; archived COMPLETE BB hits → flag as `/planwise lessons curate --phase=promote` reconciliation needed.

> [!constraint] No `documented` Limbo for In-Scope Lessons
> WRONG — a lesson survives Part-1 §3.2's gate (passed all 5 checks) but ends up in a BB's *Out of scope* notes because it "lacks a clean WRONG/CORRECT pair" or "is just a platform constraint." It re-surfaces on every future `--all-documented` run.
> CORRECT — every lesson that passes Part-1 §3.2 lands in at least one BB deliverable and, once captured, rests at `promoted` (archived), not `documented`. Use the Part-1 §4.2 destination table to route advisory patterns to `> [!practice]` callouts and platform constraints to `> [!hazard]` callouts. The capture-time flip to `promoted` (§6.6) is what removes the lesson from `documented`.

> [!constraint] Archive Fully-Captured Lessons
> WRONG — this workflow leaves a fully-captured lesson in `{lessons_dir}/` and defers its archive to a later, per-file, user-approved step, even though the lesson is already owned by a drafted backlog item and has flipped to `promoted`.
> CORRECT — a lesson fully captured into backlog item(s) is `git mv`d to `{lessons_dir}/Archive/` automatically at capture (§6.6). Completeness of capture IS the gate — there is no per-file prompt. Archived ≠ landed: the move records that the lesson is owned and awaiting landing, not that its artifact has shipped; the later `promoted → rule|applied` landing flip is [lessons-curate-workflow.md](lessons-curate-workflow.md)'s Phase-2 responsibility. Skipped only under `--dry-run`.

> [!constraint] Use score_backlog.py for Scoring
> WRONG — this workflow computes the Score column manually using its own priority-to-points logic.
> CORRECT — write the row with a placeholder Score (e.g., `-`), then invoke `python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml` to compute and write the Score column. The script is the single source of truth for scoring; manual scores drift from `config.yaml: scoring` weights.

---

## 11. Example Invocations

| User says | Workflow action |
|-----------|-----------------|
| `/planwise lessons promote-batch --category=A` | Drafts one BB for top-level bucket A's documented lessons |
| `/planwise lessons promote-batch --category=C1` | Drafts one BB for sub-bucket C1's documented lessons |
| `/planwise lessons promote-batch LL-001,LL-002,LL-003` | Drafts one BB containing exactly those three lessons (asks user how to group if they span buckets) |
| `/planwise lessons promote-batch --all-documented` | Drafts one BB per top-level bucket; reports total count to chat first for confirmation |
| `/planwise lessons promote-batch --category=C3 --dry-run` | Phases 1+2 only — reports the grouping plan without writing BB files. Phase 1 full-body lesson reads still happen. |
| `/planwise lessons promote-batch` (no args) | Asks the user what scope to use via `AskUserQuestion`; does NOT assume a default |

---

*Cross-references: [Part-1](lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md), [lessons-curate-workflow.md](lessons-curate-workflow.md), [rule-authoring.md](rule-authoring.md), [00-Index-LessonsLearned.md]({lessons_dir}/{lessons_index}), [00-Index-Backlog.md]({backlog_dir}/{backlog_index}), [templates/backlog-item.md](../templates/backlog-item.md).*
