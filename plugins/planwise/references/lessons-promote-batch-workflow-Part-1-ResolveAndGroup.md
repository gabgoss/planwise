---
description: Four-phase batch promotion workflow (Part 1 — Resolve scope and group lessons). Loaded by /planwise lessons promote-batch.
---

# Lessons Promote-Batch Workflow — Part 1 (Resolve and Group)

## Purpose

Draft promotion **backlog items (BBs)** that bundle related `documented` lessons into self-contained promotion artifacts. Each BB plans the work of authoring one or more rules, code applications, or settings entries — but it does NOT create those artifacts directly. Rule creation happens later, when the BB is executed via `/planwise backlog` or by hand.

This part covers **Phases 1-2** (resolve scope and group lessons). Phases 3-4 (draft and write BB files), the BB structure specification, self-containment verification, decomposition mechanics, constraints, and examples live in [lessons-promote-batch-workflow-Part-2-DraftAndWrite.md](lessons-promote-batch-workflow-Part-2-DraftAndWrite.md).

---

## Skill Scope vs `/planwise lessons promote`

> [!practice] When to Use Which Mode
> | Workflow | When to use |
> |----------|-------------|
> | `/planwise lessons promote LL-NNN` | Promote ONE lesson to ONE artifact, immediate execution. Generates the rule/skill/hook/agent inline, archives the lesson, writes the Rule Promotion Log row in one pass. |
> | `/planwise lessons promote-batch` | Plan promotion of MULTIPLE lessons grouped by domain bucket. Drafts BB files that describe the rule(s) to be created, the inlined content, scope, CLAUDE.md callouts, and acceptance criteria. Execution is deferred. |
>
> The two are not duplicates. Use the single-lesson `promote` for ad-hoc work; use `promote-batch` when consolidating a category, designing batched rules, or producing reviewable plans.

---

## Table of Contents

- [1. Inputs and Outputs](#1-inputs-and-outputs)
- [2. Workflow Overview](#2-workflow-overview)
- [3. Phase 1 — Resolve Scope](#3-phase-1--resolve-scope)
- [4. Phase 2 — Group Lessons into BBs](#4-phase-2--group-lessons-into-bbs)

For Phase 3-4, BB structure spec, self-containment grep, decomposition mechanics, constraints, and examples, see [Part-2](lessons-promote-batch-workflow-Part-2-DraftAndWrite.md).

---

## 1. Inputs and Outputs

All paths resolve from `config.yaml` (`project.planwise_root`, `project.lessons_dir`, `project.backlog_dir`, `project.index_files.*`). The variables below denote the resolved values (commonly `planwise/LessonsLearned/` and `planwise/Backlog/`).

| File | Role | Read | Write |
|------|------|------|-------|
| `{lessons_dir}/00-Categorization-By-Domain.md` | Source of truth for which lesson belongs to which bucket | Yes | No (this workflow does not modify categorisation) |
| `{lessons_dir}/{lessons_index}` | Master table; lesson statuses; cross-check against categorisation | Yes | No |
| `{lessons_dir}/LL-{NNN}-*.md` | Lesson body — promoted content is INLINED into BB rule designs from these files. **Read in full during Phase 1** for every non-archived in-scope lesson before any grouping decision (§3.4). | Yes (in full, Phase 1) | No |
| `{lessons_dir}/Archive/LL-{NNN}-*.md` | Archived (already-promoted) lesson bodies. Skip — these are not promotion candidates. | No | No |
| `{backlog_dir}/{backlog_index}` | Backlog master table; **also the BB ownership index** for cross-checking whether a lesson is already named in any active BB's title or row (§3.2 step 5). | Yes | Append rows for new BBs; bump `Last Updated` |
| `{backlog_dir}/BB-*-*.md` | Active BB files. **Grep all of them for `LL-{NNN}` mentions** to detect lessons already owned by an active BB (regardless of status: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`). | Yes (Grep, Phase 1) | No |
| `{backlog_dir}/Archive/BB-*-*.md` | Archived (COMPLETE/CLOSED) BB files. **Also greppable** — a lesson named in an archived COMPLETE BB is already promoted; do not re-bundle. | Yes (Grep, Phase 1) | No |
| `{backlog_dir}/BB-{ID}-{SB}-DOC-PromoteLessons{BucketSlug}.md` | New BB files | No | Yes (one per planned promotion grouping) |
| `.claude/rules/**` | Existing rules — check whether a target rule already exists (extend rather than create) | Yes (`Glob` + read frontmatter) | No |
| `CLAUDE.md` | Force-read binding callouts pointing to the new rules | Yes | No (BB describes the CLAUDE.md edit; the BB executor performs it) |
| `config.yaml: categorization` | Bucket schema, slug list, sub-bucket structure | Yes | No |

**Pre-condition:** `00-Categorization-By-Domain.md` must be up to date. If new lessons exist in the master index but not in the categorisation file, this workflow MUST stop and tell the user to run `/planwise lessons curate --phase=categorize` first. See [lessons-curate-workflow.md](lessons-curate-workflow.md) for the upstream sync mechanism.

---

## 2. Workflow Overview

> [!protocol] Four-Phase BB Drafting
> 1. **Phase 1 — Resolve scope AND read every in-scope lesson body in full.** Parse `$ARGUMENTS`. Read the categorisation file and the master index. Validate each lesson against the five-step gate in §3.2 (file exists, NOT archived, status is `documented`, categorised, NOT cited by any BB in `{backlog_dir}/` or `{backlog_dir}/Archive/`). Then **read every surviving in-scope lesson body in full** — Context, Lesson, Applies To. Grouping cannot be decided from index summaries alone; multi-part lessons (Part-2 §9) require body content to detect decomposition opportunities.
> 2. **Phase 2 — Group lesson fragments into BBs.** Group by destination artifact using the decision tree in §4. A single lesson MAY be decomposed across multiple BBs when its body covers content for multiple distinct rules (Part-2 §9). Each group becomes one BB. Default grouping = one BB per top-level bucket (or per sub-bucket if `--category=C1` targets a sub-bucket id). **No-limbo principle (§4.2):** every in-scope `documented` lesson MUST land in at least one BB deliverable — `documented` is not a valid resting state for a lesson the workflow has accepted into scope.
> 3. **Phase 3 — Draft each BB.** Use the lesson bodies already in context from Phase 1 (no re-read). Decide each lesson fragment's promotion strategy (rule / applied-to-code / applied-to-settings / CLAUDE.md addition / decomposed across N BBs), and draft deliverables — including the rule's outline with content INLINED (no `see LL-XXX` references) and a CLAUDE.md binding callout when relevant.
> 4. **Phase 4 — Write files.** Write each BB to `{backlog_dir}/BB-{ID}-{SB}-DOC-PromoteLessons{BucketSlug}.md`, append rows to `{backlog_index}`, run `score_backlog.py` to compute scores, bump the index `Last Updated` line. Report summary to chat.

If the user only wants Phase 1+2 (a grouping plan without draft BBs), accept `--dry-run` and skip Phase 3+4. **Phase 1 lesson-body reads still happen under `--dry-run`** — without them, the grouping plan is just an index re-shuffle and misses decomposition opportunities.

---

## 3. Phase 1 — Resolve Scope

### 3.1 Parse arguments

| Argument form | Resolves to |
|---------------|-------------|
| `--category=X` (X is a top-level `bucket.id` from `config.yaml: categorization.buckets`) | All `documented` lessons currently listed under bucket X in the categorisation file |
| `--category=Cn` (a sub-bucket id from `bucket.sub_buckets[]`) | All `documented` lessons under that specific sub-bucket. Sub-buckets are first-class scope targets — they are addressed identically to top-level buckets. |
| `LL-001,LL-002,LL-003` (comma-separated) | Exactly those lessons |
| `--all-documented` | Every `documented` lesson across all buckets — likely produces multiple BBs |
| (no arguments) | Ask the user what scope to use via `AskUserQuestion`; do NOT assume `--all-documented` |

The `--dry-run` flag is orthogonal to scope — it stops execution after Phase 2 regardless of which scope argument was used.

### 3.2 Validate the scope (5-step gate)

For each resolved lesson ID, run all five checks:

1. **File exists.** Confirm `{lessons_dir}/LL-{NNN}-*.md` exists. If missing, flag as anomaly and exclude from this run.
2. **NOT archived.** Confirm the file is in `{lessons_dir}/` (active) and NOT in `{lessons_dir}/Archive/`. Archived lessons are already promoted; exclude with the note *"already in {lessons_dir}/Archive/; skipping"*.
3. **Frontmatter status check.** Read the YAML frontmatter (body load is deferred to §3.4 after this gate). If `status` is already `applied` or `rule`, exclude with the note *"already promoted to {applied-as}; skipping"*.
4. **Categorised.** Verify the lesson is listed in `00-Categorization-By-Domain.md` under its expected bucket (or sub-bucket). If not, flag as anomaly: *"LL-NNN is not in `00-Categorization-By-Domain.md`; run `/planwise lessons curate --phase=categorize` first."*
5. **NOT owned by an existing BB.** Run `Grep 'LL-{NNN}' {backlog_dir}/` (recursive — covers active + Archive). If any BB cites this lesson:
   - **Active BB** (`NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `PLANNING`): exclude with the note *"already owned by BB-{NNN} ({status}); will be promoted via that BB"*.
   - **Archived BB** (`COMPLETE` / `CLOSED`, in `{backlog_dir}/Archive/`): exclude with the note *"already promoted via archived BB-{NNN}; flag as anomaly because the lesson frontmatter should have been flipped to `rule`/`applied`"* — recommend the user run `/planwise lessons curate --phase=promote` to reconcile.

> [!gate] Categorisation Gate
> If any in-scope lesson is missing from `00-Categorization-By-Domain.md`, STOP. Tell the user to run `/planwise lessons curate --phase=categorize` first. Do NOT attempt to grouping-decision a lesson whose bucket is unknown — silent default-bucketing distorts the BB clustering.

> [!gate] BB Ownership Gate
> A lesson cited in any active or archived BB is already accounted for. Do NOT re-bundle. The grep in step 5 is mandatory — silent re-bundling produces conflicting promotion paths and corrupts the Rule Promotion Log.

### 3.3 Report scope to chat

Before doing any further work, emit a short table to the chat:

```markdown
**Scope resolved:** {N_in_scope} lessons in scope; {N_excluded} excluded.

| ID | Bucket | Severity | Status | Title |
|----|--------|----------|--------|-------|
| LL-... | A | HIGH | in scope | ... |
| LL-... | B | MEDIUM | excluded — owned by BB-{Y} (IN_PROGRESS) | ... |
```

### 3.4 Read every in-scope lesson body in full (BINDING)

After §3.2 produces the in-scope set, **read each surviving lesson's full body** (Context, Lesson, Applies To, code examples) with the `Read` tool. This MUST happen BEFORE §4 grouping decisions. Index summaries and the categorisation table's one-line descriptions are NOT sufficient grounds for grouping or decomposition decisions.

> [!constraint] Read Lesson Bodies Before Grouping (Not After)
> WRONG — defer lesson-body reads to Phase 3 to "save tokens on lessons that get dropped." Body reads after grouping miss decomposition opportunities and produce groupings grounded in one-line index summaries.
>
> CORRECT — §3.4 reads every surviving in-scope lesson body in full BEFORE Phase 2 grouping. Bodies inform decomposition, destination assignment, and BB clustering.

Two consequences if Phase 1 grouping happens without full body reads:

| Problem | What goes wrong |
|---------|-----------------|
| Multi-part lessons missed | A lesson with content for 3 distinct rules gets force-fit into one bucket; two-thirds of its content is dropped at promotion time |
| Wrong destination | A lesson categorised under "C3 — Task-file authoring" turns out, on full-body read, to be primarily about adapter purity (a B-bucket concern); grouping it in C3 wastes the C3 BB's coherence |

Under `--dry-run`, this read still happens — the dry-run output is meaningless without it.

---

## 4. Phase 2 — Group Lessons into BBs

### 4.1 Default grouping rule

> [!decide] Grouping Strategy
> | Scope | Default grouping |
> |-------|------------------|
> | One top-level bucket (e.g., `--category=A`) | One BB for the whole bucket |
> | One sub-bucket (e.g., `--category=C1`) | One BB for that sub-bucket; sub-buckets cluster more loosely than top-level buckets |
> | Mixed buckets (`--all-documented`) | One BB per top-level bucket; never bundle a database lesson with a tooling lesson into one BB |
> | A specific list of LL IDs | If the IDs span buckets, ask the user whether to merge or split via `AskUserQuestion` |

### 4.2 Sub-grouping inside a BB — by destination artefact

Within one BB, lessons can target multiple deliverables. Decide each lesson's destination using:

| Lesson character | Destination artefact | BB deliverable |
|------------------|----------------------|----------------|
| Prescriptive convention with WRONG/CORRECT examples (MUST/NEVER language) | A *rule* in `.claude/rules/**` (new file or extend existing) | "Rule: {name}.md (LLs X+Y content fully inlined)" |
| Advisory pattern (SHOULD/PREFER) without enforcement teeth | A `> [!practice]` callout inside an existing rule, OR a `> [!practice]` section in a new rule | "Add `> [!practice]` to `.claude/rules/{path}.md §N` covering LL-X" |
| Behaviour that belongs in code with an explanatory comment | An *applied-to-code* edit | "Apply LL-X to {file}.py via inline docstring/comment" |
| Behaviour that belongs in `.claude/settings.json` or `settings.local.json` | An *applied-to-settings* edit | "LL-X applied via {settings file} (already in place — bookkeeping flip)" |
| Project-wide invariant or Critical Rule | A `> [!binding]` callout in `CLAUDE.md` + a Critical Rule entry | "Add Critical Rule #N to CLAUDE.md citing the new rule (no LL reference)" |
| Claude Code platform constraint with no fix surface | A `> [!hazard]` callout in an existing rule (e.g., `agent-orchestration.md` Constraints section), OR a CLAUDE.md operational-guidance entry | "Document LL-X as `> [!hazard]` in `agent-orchestration.md`" |

> [!constraint] Every In-Scope Lesson Lands Somewhere
> WRONG — a lesson the workflow accepted into scope is left in `documented` status with the BB's Notes section saying "stays documented, no project-side fix":
> ```markdown
> ## Notes
> - LL-X (a Claude Code platform constraint, e.g., a tool the runtime auto-denies) stays documented:
>   Platform constraint with no project-side fix.
> ```
> This is the `documented`-as-limbo failure mode. The lesson re-surfaces in the next `/planwise lessons promote-batch --all-documented` run, and the next, indefinitely.
>
> CORRECT — even platform constraints land in a destination row of the table above. LL-X belongs as a `> [!hazard]` operational-guidance entry in `agent-orchestration.md` (a short statement of the constraint + its operational workaround). Status flips to `rule` once the hazard callout lands.
>
> The only valid reason for an in-scope lesson to remain `documented` AFTER this workflow run is: another active BB in `{backlog_dir}/` already owns it (caught by §3.2 step 5; the lesson was already excluded). Anything else is the limbo failure.

### 4.3 Bundling rule

> [!practice] Prefer One Rule per Cluster
> When 2+ lessons share a root cause (e.g., LL-X, LL-Y, LL-Z all surface from one root cause like "two independent lint/type gates"), bundle them into ONE rule rather than producing N near-duplicate rules. The rule body inlines all WRONG/CORRECT examples from each lesson, organised by sub-section.

### 4.4 Lesson decomposition across multiple BBs

A single lesson MAY span multiple destination artefacts when its body covers content for distinct rules. Force-fitting a multi-part lesson into one BB either drops two-thirds of its content or pollutes the receiving rule with off-topic material.

> [!constraint] Decompose Multi-Destination Lessons
> WRONG — LL-X has content covering four distinct fragments (a)/(b)/(c)/(d) that map to different destination rules. The workflow bundles all of LL-X into one BB (say, the C1 bucket BB). The receiving BB either inflates beyond 500 lines OR the (c)/(d) fragments get summarised away because they don't fit C1's narrative.
>
> CORRECT — LL-X is decomposed: the (a) fragment lands in the C1 BB; the (c) fragment lands in a tooling/agent-extension BB; the (d) fragment lands in a CLAUDE.md hooks BB. Each BB's Evidence table cites LL-X with the specific fragment it owns; each BB's rule design inlines ONLY the WRONG/CORRECT examples relevant to its destination.

Decomposition signal: during Phase 1 full-body reads (§3.4), an LL whose Context section names ≥2 distinct rule files OR whose "Applies To" lists ≥2 distinct file domains is a decomposition candidate. Flag in the Phase 2 grouping output: *"LL-X decomposes across BBs P, Q, R — fragments listed below."*

See [Part-2 §9 — Decomposition Mechanics](lessons-promote-batch-workflow-Part-2-DraftAndWrite.md#9-decomposition-mechanics) for the full mechanics (Evidence column shape, `applied-as` accumulation, Rule Promotion Log rows, lifecycle-state policy).

### 4.5 Existing-rule check

For each target rule path, run `Glob` to detect whether the rule already exists. If it does:

- **Extend** (preferred): the BB deliverable becomes "Extend `.claude/rules/{path}.md` with new §N covering LL-X content (fully inlined)" — no new file, just an `Edit` of the existing rule.
- **Replace** (rare): the BB deliverable explicitly states the existing rule is being replaced, with rationale.

---

*Part 2 continues at [lessons-promote-batch-workflow-Part-2-DraftAndWrite.md](lessons-promote-batch-workflow-Part-2-DraftAndWrite.md). Cross-references: [lessons-curate-workflow.md](lessons-curate-workflow.md), [00-Index-LessonsLearned.md]({lessons_dir}/{lessons_index}), [00-Index-Backlog.md]({backlog_dir}/{backlog_index}), [rule-authoring.md](rule-authoring.md).*
