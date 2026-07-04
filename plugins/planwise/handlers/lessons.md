# Handler: /planwise lessons

**Purpose:** Search, list, promote, and capture lessons learned.

**Invocation examples:**
```
/planwise lessons
/planwise lessons python regex
/planwise lessons promote LL-003
/planwise lessons capture
```

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml: a) `planwise/config.yaml`; b) `*/config.yaml` one level down from project root.
2. If found → continue (extract `plugin_root`, `project.planwise_root`, `project.plans_dir`, `project.lessons_dir`, `project.index_files.lessons`).
3. If NOT found: announce, resolve `{plugin_root}` from handler location, invoke `init_project.py` with `--auto-from "lessons"`, RE-RESOLVE, fail loud if still missing.

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed, DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise lessons." STOP.

All directory paths resolve as `{planwise_root}/{dir_name}`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If running curate mode: Read `references/lessons-curate-workflow.md`
- If running promote-batch mode: Read `references/lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md` and `references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md`
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

---

## Routing

| Input | Mode | Action |
|-------|------|--------|
| No arguments | **list** | Display lessons index table |
| `<terms>` (not `promote`, `promote-batch`, `capture`, or `curate`) | **search** | Search by keyword across lesson files |
| `curate [--phase=categorize|promote|both]` | **curate** | Run the two-phase curation workflow (see references/lessons-curate-workflow.md) |
| `promote-batch [--category=X | LL-NNN,LL-NNN | --all-documented] [--dry-run]` | **batch** | Draft promotion BB items bundling related documented lessons (see references/lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md) |
| `promote <lesson-id>` | **promote** | Promote a lesson to a Claude Code artifact |
| `capture` | **capture** | Create a new lesson mid-session |

Parse `$1` to determine the mode. If `$1` is `curate`, enter curate mode and parse `$2` for an optional `--phase=categorize|promote|both` flag (default `both`). If `$1` is `promote-batch`, enter batch mode and parse the remaining arguments for scope (one of `--category=X`, comma-separated LL IDs, or `--all-documented`) plus an optional `--dry-run` flag. If `$1` is `promote`, parse `$2` as the lesson ID (single-lesson mode — preserved verbatim from the pre-batch handler). If `$1` is `capture`, enter capture mode. If `$1` is absent, enter list mode. Otherwise, treat all arguments as search terms.

---

## List Mode (no arguments)

Read `{lessons_dir}/{lessons_index}` and display the Master Table.

If the file does not exist:

```
Lessons index not found at {lessons_dir}/{lessons_index}.
Run `/planwise init` to create the index, or check your config.yaml.
```

---

## Search Mode (`/planwise lessons <terms>`)

For each search term in `$ARGUMENTS`:

1. Use Grep to search YAML frontmatter in `{lessons_dir}/LL-*.md`:
   ```
   pattern: {term}
   path: {lessons_dir}
   glob: **/LL-*.md
   output_mode: files_with_matches
   ```
2. Intersect results across all search terms — files must match ALL terms (AND logic)
3. For each matching file, read the frontmatter and first line of each `## ` section

### Output Format

Present results as a table:

```
| ID | Title | Category | Severity | File |
|----|-------|----------|----------|------|
| LL-001 | Example Lesson Title | process | medium | [LL-001]({lessons_dir}/LL-001-DOC-ExampleTopic.md) |
```

After the table, include a 1-line summary of each lesson's key insight.

### No Results

If no lessons match, respond with:
- "No lessons found matching: {terms}"
- Suggest checking valid taxonomy values: `category` (anti-pattern, pattern, process), `domain` (from config.yaml abbreviations)
- Link to the index: `{lessons_dir}/{lessons_index}`

---

## Curate Mode (`/planwise lessons curate [--phase=categorize|promote|both]`)

**Purpose:** Sync `{lessons_dir}/00-Categorization-By-Domain.md` with the master index and track lessons promoted to permanent artifacts. Does NOT author new `LL-*` files.

### Pre-condition Gate

Verify `{lessons_dir}/00-Categorization-By-Domain.md` exists. If it does not, error:

```
Categorisation file not found at {path}. Run /planwise init to create it, or copy {plugin_root}/templates/categorization-by-domain.md and populate it from config.yaml.
```

Halt without modifying any files.

### Workflow

Curate runs two phases against the lesson set. **Phase 1** diffs the master index against the categorisation file, reads uncategorised `LL-*` files in full, applies the config-driven decision tree, and appends rows to the matching bucket tables. **Phase 2** greps for `status: applied` / `status: rule`, verifies each `applied-as` artifact exists, and appends rows to the Rule Promotion Log in the master index. Optional file moves to `Archive/` require explicit user approval.

See `references/lessons-curate-workflow.md` for the binding step-by-step protocol (bucket selection algorithm, reporting format, anomaly detection, and constraint set).

### Argument Parsing

Parse `$2` for the `--phase=` flag:

| Value | Behaviour |
|-------|-----------|
| `--phase=categorize` | Run Phase 1 only |
| `--phase=promote` | Run Phase 2 only |
| `--phase=both` (default) | Run both phases sequentially |

If `$2` is absent or not a recognised `--phase=` value, default to `both`.

### Output

Chat report only (markdown summary with Phase 1 / Phase 2 / Anomalies sections per the reference doc's §6). File writes are limited to: appending rows to `00-Categorization-By-Domain.md` and bumping its top-of-file `Last Updated:` line to the current date when Phase 1 appends new rows (Phase 1); appending rows to the Rule Promotion Log in `{lessons_dir}/{lessons_index}` (Phase 2); updating the Status column in the Master Table (Phase 2). No new `LL-*` files are created.

---

## Batch-Promote Mode (`/planwise lessons promote-batch <scope> [--dry-run]`)

**Purpose:** Draft promotion **backlog items (BBs)** that bundle related `documented` lessons into self-contained promotion artifacts. Each BB plans the work of authoring one or more rules, code applications, or settings entries; rule creation happens later at BB execution time via `/planwise backlog`. This mode is the batched, deferred complement to the single-lesson `promote` mode below — the two are not duplicates.

### Pre-condition Gates

Both gates are binding. Halt without modifying any files if either fails.

**Gate 1 — Categorisation file must exist.** Verify `{lessons_dir}/00-Categorization-By-Domain.md` exists. If it does not, error with the same message used by Curate Mode:

```
Categorisation file not found at {path}. Run /planwise init to create it, or copy {plugin_root}/templates/categorization-by-domain.md and populate it from config.yaml.
```

**Gate 2 — Categorisation must be up to date.** Diff `{lessons_dir}/{lessons_index}` against `{lessons_dir}/00-Categorization-By-Domain.md`. If any `LL-NNN` appears in the master table but NOT in any bucket table of the categorisation file, error with:

```
Lessons missing from categorisation file: {list of LL IDs}. Run /planwise lessons curate --phase=categorize first.
```

### Workflow

The four-phase workflow (Resolve scope / Group lessons / Draft BBs / Write files) is specified in [references/lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md](../references/lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md) (Phases 1-2) and [references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md](../references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md) (Phases 3-4, BB structure spec, self-containment grep, decomposition mechanics, constraints). Do NOT duplicate Phase 1-4 content here — read the reference doc when entering batch mode.

### Argument Parsing

Parse the arguments after `promote-batch` for one scope argument and an optional `--dry-run` flag:

| Argument form | Resolves to |
|---------------|-------------|
| `--category=X` (X is a top-level `bucket.id` or sub-bucket id from `config.yaml: categorization`) | All `documented` lessons currently listed under that bucket or sub-bucket. Sub-buckets are first-class scope targets. |
| `LL-NNN,LL-NNN,...` (comma-separated) | Exactly those lessons |
| `--all-documented` | Every `documented` lesson across all buckets — likely produces multiple BBs |
| (no scope argument) | Prompt the user via `AskUserQuestion`; do NOT assume `--all-documented` | <!-- AUTO-MODE: critical -->

The `--dry-run` flag is orthogonal to scope. When present, the workflow short-circuits after Phase 2 — Phase 1 lesson-body reads STILL happen (full-body reads are required for grouping decisions), but Phases 3 and 4 are skipped. The grouping plan is reported to chat without writing any BB files.

### Output

| Surface | Change |
|---------|--------|
| `{backlog_dir}/BB-{ID}-{SB}-DOC-PromoteLessons{BucketSlug}.md` | One new BB file per planned grouping |
| `{backlog_dir}/{backlog_index}` | Appended row per new BB; `Last Updated` bumped |
| Scoring | `python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml` is invoked after writes to compute Score columns |
| Lesson files | NOT modified — status flips happen at BB execution time, not BB drafting time |

The single-lesson `promote <id>` mode below is preserved verbatim. Batch promotion is a parallel path, not a replacement.

---

## Promote Mode (`/planwise lessons promote <lesson-id>`)

**Purpose:** Promote a lesson to a Claude Code artifact (rule, skill, hook, or agent).

The promotion flows through these stages:

```
Locate → Read → Confirm → Generate → Update → Archive → Log
```

### Stage 1: Locate

Find the lesson file by ID:
```
Glob: {lessons_dir}/**/LL-{id}*
```

This searches both the working directory and Archive in one pass.

If not found, use a broad search to list all available lessons:
```
Glob: {lessons_dir}/**/LL-*
```

List all lesson IDs found and ask the user to confirm the correct one.

### Stage 2: Read

Read the lesson content and determine the appropriate artifact type based on the lesson's content pattern:

| Lesson Content Pattern | Artifact Type | Generated Location |
|------------------------|---------------|-------------------|
| Prescriptive rule (MUST, NEVER, ALWAYS) | Rule | `.claude/rules/{name}.md` |
| Reusable workflow with steps | Skill | `.claude/skills/{name}/SKILL.md` |
| Enforcement check (pre/post action) | Hook | `.claude/hooks/{name}.sh` |
| Delegatable role with constraints | Agent | `.claude/agents/{name}.md` |

Most lessons describe patterns or anti-patterns that map to **Rule** type. Lessons about workflows may map to **Skill**. Hook and agent types are rare.

### Stage 3: Confirm (REQUIRED — never skip) <!-- AUTO-MODE: critical -->

Present to the user:
- Lesson ID and title
- Proposed artifact type (Rule, Skill, Hook, Agent)
- Proposed artifact name (kebab-case)
- Proposed file path
- Brief rationale for the classification
- **On approval, the lesson file will also be moved to `{lessons_dir}/Archive/`** (Stage 6). Approving this prompt covers the artifact generation, the frontmatter flip, the archive move, and the Rule Promotion Log row.

Wait for user approval before proceeding.

**If rejected:** Ask if they want a different artifact type, or abort. The lesson remains in its current status.

### Stage 4: Generate

Create the artifact file at the approved location:

| Artifact Type | Location |
|---------------|----------|
| Rule | `.claude/rules/{name}.md` |
| Skill | `.claude/skills/{name}/SKILL.md` |
| Hook | `.claude/hooks/{name}.sh` |
| Agent | `.claude/agents/{name}.md` |

Check if the file already exists before writing. If it exists, ask the user to rename or merge. <!-- AUTO-MODE: critical -->

**Self-containment verification (BINDING — do not skip):** After writing the artifact, run the grep from [`references/artifact-self-containment.md` §4](../references/artifact-self-containment.md#4-mechanical-verification) against the produced file. The artifact body MUST inline every WRONG/CORRECT example, recipe, and verification command from the source lesson — no `see LL-NNN` / `per BB-NNN` cross-references in the rule body, agent definition, skill body, or hook script.

```bash
grep -rnE '(LL-[0-9]{3}|BB-[0-9]{3})' {generated-artifact-path}
# MUST return zero matches.
```

If grep returns matches, revise the artifact to inline the cited content and re-run the grep. Do NOT proceed to Stage 5 (Update Frontmatter) until the grep returns zero. The `applied-as:` and Rule Promotion Log entries written in Stage 5 and Stage 7 ARE permitted to carry the `LL-NNN` reference — those are bookkeeping artifacts whose purpose is traceability.

### Stage 5: Update Frontmatter

Edit the lesson file's YAML frontmatter:

| Field | Value |
|-------|-------|
| `status` | `rule` (for rules) or `applied` (for skills, hooks, agents) |
| `applied-as` | Path to generated artifact (relative to project root) |
| `promoted-date` | ISO date: YYYY-MM-DD |

### Stage 6: Archive

Move the promoted lesson to the Archive folder to keep the working directory clean.

1. Create Archive directory if it does not exist:
   ```bash
   mkdir -p "{lessons_dir}/Archive"
   ```

2. Move the lesson file:
   ```bash
   mv "{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md" "{lessons_dir}/Archive/"
   ```

3. Update the index link in the Master Table using Edit:
   - Old: `](LL-{NNN}-{Domain}-{Name}.md)`
   - New: `](Archive/LL-{NNN}-{Domain}-{Name}.md)`

Skip if the file is already in `Archive/`.

### Stage 7: Log

Add a row to the Rule Promotion Log in `{lessons_dir}/{lessons_index}`:

```markdown
| Date | Lesson ID | Artifact Created | File |
|------|-----------|-----------------|------|
| YYYY-MM-DD | LL-{NNN} | {artifact-name} | `.claude/{type}/{name}` |
```

Also update the lesson's `Status` column in the Master Table from `documented` to `rule` (or `applied`).

### Promotion Error Handling

| Failure | Recovery |
|---------|----------|
| Lesson file not found | Check `{lessons_dir}/LL-{NNN}*` then `{lessons_dir}/Archive/LL-{NNN}*`. Use Glob `{lessons_dir}/**/LL-*` to list all. |
| Ambiguous artifact type | Present options to user and let them choose |
| Artifact file path conflict | Check if file exists; ask user to rename or merge |
| Lesson frontmatter edit fails | Use Edit tool manually on the YAML frontmatter block |
| Index update fails | Manually add row to Rule Promotion Log |

---

## Capture Mode (`/planwise lessons capture`)

Capture a lesson during an active session while context is fresh.

### Step 1: Identify

From the current session context, determine:
- What went wrong or what was learned
- Domain (infer from files being worked on, or ask user)
- Technology and language involved
- Severity assessment (high/medium/low)

Read domain abbreviations from `config.yaml` (`abbreviations` and `lesson_abbreviations` sections) to present valid domain options.

### Step 2: Draft

> [!important] Inline the content the capture depends on
> When a lesson's value rests on specific content — the block it will later promote, the evidence behind the finding, an exact spec, the failing command and its output — **paste that content into the lesson verbatim**. A pointer (a session reference, a scratch file, a path) is welcome *alongside* the inlined content for context or provenance, but it must NOT be the *sole* carrier of the substance: the lesson must stay promotable and usable if that source becomes unavailable.
> - **Inline:** the verbatim WRONG/CORRECT example, the failing command + its output, the exact before/after, the spec to promote.
> - **Reference-only is acceptable** for: large, stable in-repo files that will still exist later AND are not the unique carrier of the lesson's substance.
> - **Durability test:** "If this session's scratch and the originating repo vanished tomorrow, could someone promote this lesson from the file alone?" If no, inline more.
>
> This is a different concern from shipped-artifact self-containment (`references/artifact-self-containment.md`, which strips internal identifiers out of a promoted artifact) — here the goal is that the lesson itself carries its own substance so it survives to be promoted.

Create a candidate lesson with pre-filled YAML frontmatter:

```yaml
---
id: LL-{next-available}
title: {auto-generated from context}
date: {today}
source: {current session reference}
category: {inferred: anti-pattern | pattern | process}
severity: {inferred: low | medium | high}
language: [{inferred}]
technology: [{inferred}]
domain: [{inferred domain abbreviation}]
status: documented
applied-as: null
---
```

### Step 3: Approve

Present the draft to the user:
- Show pre-filled frontmatter and draft Context/Lesson/Applies To sections
- **Self-containment check:** confirm the draft inlines every block, example, or command output the lesson depends on — a reference may add context, but the substance required to promote it later is pasted in, not only linked. (Apply the durability test in Step 2.)
- Ask: "Capture this lesson? (approve / edit / skip)" <!-- AUTO-MODE: critical -->

### Step 4: Write

If approved:
1. Read `{lessons_dir}/{lessons_index}` to get the next available ID and the lesson file template
2. Determine `{Domain}` from the first value in the `domain:` field
3. Write file: `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md`
4. Add a row to the Master Table in `{lessons_dir}/{lessons_index}`
5. Update the "Next available ID" counter in the index

### Step 5: Skip

If skipped, discard the draft. No file is written.

---

## Lesson Status Lifecycle

Lessons graduate through three statuses:

```
documented → applied → rule
```

| Status | Meaning |
|--------|---------|
| `documented` | Lesson captured, available for reference |
| `applied` | Lesson has been manually applied in practice (proven useful) |
| `rule` | Lesson promoted to a Claude Code artifact |

### Promotion Criteria

Promote a lesson when ANY of these apply:
- Severity is `high`
- Lesson recurs 2+ times across different sessions or domains
- Lesson addresses a class of problems (not just one instance)

---

## Search Tips

- Search is case-insensitive against YAML frontmatter
- Multiple terms narrow results (AND logic)
- Common searches: `/planwise lessons python`, `/planwise lessons anti-pattern`, `/planwise lessons high`
