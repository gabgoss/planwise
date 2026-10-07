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

## Lessons-Index Write Convention

The lessons index is generated from lesson frontmatter — never hand-edited. Every mode below that touches a lesson file runs the generator afterward:

```bash
python {plugin_root}/scripts/generate_lessons_index.py --config {planwise_root}/config.yaml --write
```

> [!gate] Exit 2, class `legacy-shape` → the index has not been migrated
> If the command refuses with exit 2 and names class `legacy-shape`, this project's lessons index is still the legacy hand-written shape. Print the generator's error line to the user verbatim. Say the index has not been migrated to the generated format. Never hand-edit the index. Never run `--replace-legacy` without the user — it drops the hand-written sections, including the Rule Promotion Log. STOP.

The changelog file (`{lessons_dir}/00-Changelog-LessonsLearned.md`) receives a dated entry naming what changed, in the same edit as the lesson-file write. Its current-value line follows **"Replace the previous value — do not preserve it. History belongs in a changelog file, not in this line."** History belongs in the changelog file, never in the index. The Rule Promotion Log lives in its own files (see [Stage 7: Log](#stage-7-log)), not in the index.

Pointer-field semantics (`applied-as:`, `promoted-to:`, and the deprecated `rule-as:`) are defined once, in [`references/lessons-schema.md`](../references/lessons-schema.md) § Pointer Fields — Authoritative Definition, and are not restated here.

This binds every mode below that writes a lesson file — Curate, Batch-Promote, Promote, and Capture — and is stated here once rather than restated per mode.

---

## List Mode (no arguments)

Read `{lessons_dir}/{lessons_index}` (the hub) and display its table. The hub is generated from lesson frontmatter — see [Lessons-Index Write Convention](#lessons-index-write-convention) — and stays under the Read-tool page cap by construction; the rest of the population lives in its overflow leaves and the Archive shards named in its `## Shards` directory line — see [`references/lessons-schema.md`](../references/lessons-schema.md) § Hub, Overflow Leaves and Archive Shards. To confirm the hub is current against lesson frontmatter, run `python {plugin_root}/scripts/generate_lessons_index.py --config {planwise_root}/config.yaml --check`.

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

**Purpose:** Keep the generated companion (`{lessons_dir}/00-Categorization-By-Domain.md`, regenerated by `generate_lessons_index.py --companion --write` from lesson frontmatter) in sync with the master index and track lessons promoted to permanent artifacts. Does NOT author new `LL-*` files.

### Pre-condition Gate

Verify `{lessons_dir}/00-Categorization-By-Domain.md` exists. If it does not, error:

```
Categorisation file not found at {path}. Run /planwise init to create it, or run `generate_lessons_index.py --config {config_path} --companion --write` to generate it from config.yaml.
```

Halt without modifying any files.

### Workflow

Curate runs two phases against the lesson set. **Phase 1** diffs the master index against the companion (`--companion --check --json`), reads uncategorised `LL-*` files in full, tags each lesson's frontmatter — the `domain:` bucket discriminator per the reference's §3.4, and, from the lesson's body, its `promotion-target` using its existing callout/markdown conventions (a fenced code block or diff reads as `code`; a `MUST`/`NEVER` callout reads as `rule`; and so on) — and regenerates the companion; a lesson whose body maps to more than one target type is flagged as a split candidate. **Phase 2** finds `status: promoted`, lands each lesson whose content is verified present in its destination artifact (per lesson, by content, never per item by status) — reconciling `applied-as` and flipping status to `rule`/`applied` with a Rule Promotion Log row — and also heals any `documented` lesson that turns out to be fully owned by a backlog item forward to `promoted`. Optional file moves to `Archive/` require explicit user approval.

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

Chat report only (markdown summary with Phase 1 / Phase 2 / Anomalies sections per the reference doc's §6). The authoritative write scope — which files each phase writes, and what it writes to them — is the Write column of [`references/lessons-curate-workflow.md`](../references/lessons-curate-workflow.md) §1. It is deliberately not restated here: a restated list is a cache with no invalidation, and it drifts the moment either phase gains a write. Note that Phase 1 writes lesson frontmatter (`promotion-target:`, per §3.6) and Phase 2 writes lesson status/`applied-as`/`promoted-to:` — read the table rather than assuming lesson files are read-only. No new `LL-*` files are created (§7, Do Not Author Lessons).

Any phase that writes lesson frontmatter runs the generator afterward — see [Lessons-Index Write Convention](#lessons-index-write-convention).

---

## Batch-Promote Mode (`/planwise lessons promote-batch <scope> [--dry-run]`)

**Purpose:** Draft promotion **backlog items (BBs)** that bundle related `documented` lessons into self-contained promotion artifacts. Each BB plans the work of authoring one or more rules, code applications, or settings entries; rule creation happens later at BB execution time via `/planwise backlog`. This mode is the batched, deferred complement to the single-lesson `promote` mode below — the two are not duplicates.

### Pre-condition Gates

Both gates are binding. Halt without modifying any files if either fails.

**Gate 1 — Categorisation file must exist.** Verify `{lessons_dir}/00-Categorization-By-Domain.md` exists. If it does not, error with the same message used by Curate Mode:

```
Categorisation file not found at {path}. Run /planwise init to create it, or copy {plugin_root}/templates/categorization-by-domain.md and populate it from config.yaml.
```

**Gate 2 — the generated index must be current, and categorisation must be up to date.** Run:

```bash
python {plugin_root}/scripts/generate_lessons_index.py --config {planwise_root}/config.yaml --check --json
```

Read the JSON result's `drift` and `anomalies` lists. The gate passes on exit 0, or on exit 1 where every listed finding is a class `--write` never heals — `counter_ahead` (the on-disk counter sits above the true next id) or `location-anomaly` (a lesson's directory disagrees with its status; the generator never moves a file) — per [`references/index-drift-audit.md`](../references/index-drift-audit.md) § Lessons. Any other finding is healable drift: tell the user to run `--write` (see [Lessons-Index Write Convention](#lessons-index-write-convention)), then re-run Gate 2.

A listed finding of class `legacy-shape` is never healable drift — plain `--write` refuses on it too (exit 2). Follow the [Lessons-Index Write Convention](#lessons-index-write-convention)'s refusal branch instead: print the line verbatim, say the index has not been migrated, and STOP.

See [`references/lessons-schema.md`](../references/lessons-schema.md) § The One-Writer Rule for what each exit code means generically. This gate also covers the categorisation-file companion: run `python {plugin_root}/scripts/generate_lessons_index.py --config {planwise_root}/config.yaml --companion --check --json` and read its `drift` list. A `missing-row` finding (with no `legacy-shape` present) means a lesson the index carries has no row in `{lessons_dir}/00-Categorization-By-Domain.md` yet — error with:

```
Lessons missing from categorisation file: {list of LL IDs}. Run /planwise lessons curate --phase=categorize first.
```

A `legacy-shape` finding means the companion has not been migrated to the generated shape — follow [`references/lessons-curate-workflow.md`](../references/lessons-curate-workflow.md) §7's legacy line instead, never diff it by hand.

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

New backlog-item files, the regenerated backlog index, and — at capture — modified lesson files. The authoritative write scope is the Write column of [Part-1 §1](../references/lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md#1-inputs-and-outputs), with the capture-time lesson writes specified in [Part-2 §6.5](../references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md#65-capture-the-in-scope-lessons-archive-on-capture). As with Curate Mode above, it is deliberately not restated here. Under `--dry-run` the workflow short-circuits after Phase 2 and writes nothing.

Writes that touch a lesson file are followed by the generator — see [Lessons-Index Write Convention](#lessons-index-write-convention).

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

**Native-tool promotion check (BINDING — do not skip):** Also check the artifact body for any instruction that tells an agent to run a shell command against files. If a native tool (`Read`/`Grep`/`Glob`/`Edit`) covers the same act, repoint the instruction to name the native tool call instead. A command counts as flagged only when it sits in command position — the thing an agent is told to run now, or a shell shape a template hands future agents to copy — not when the same word appears in ordinary prose or inside a legitimate pipeline. Exempt any command whose input is not a file tree (git output, a database, an interpreter, or the filesystem itself: `git`, `python`, `psql`, `yq`, `wc -l`, `mkdir`, `mv`) and any build/test/lint invocation — those are correct shell and must never be flagged.

```bash
grep -nE '\b(grep|cat|sed -n|find|cd)\b' {generated-artifact-path}
# Inspect each hit in context: repoint it to the equivalent native tool call unless it
# falls in an exempt class above, or the word appears in prose rather than as a command
# an agent is told to run.
```

If a hit needs repointing, edit the artifact before proceeding to Stage 5.

The artifact write itself may prompt for permission; if denied, record what was written and stop rather than retrying the write.

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

3. Run the generator; the File column follows the file — no hand-edited link.

Skip if the file is already in `Archive/`.

### Stage 7: Log

Append a row to the promotion-log file for the lesson's id with:

```
python {plugin_root}/scripts/promotion_log.py --config {planwise_root}/config.yaml --lesson LL-{NNN} --artifact "…" --file "…"
```

The script resolves the append target — which of the five files — as a pure function of the lesson id (see [`references/lessons-schema.md`](../references/lessons-schema.md) § Promotion-Log Contract for the id ranges and file list), refuses a duplicate `(lesson, artifact)` tuple, and prints the regenerate command. A missing Archive century file is created on first use when its hub-side sibling exists; only a missing hub-side file is refused, naming the command that creates it — never hand-create either file.

The lesson's `Status` cell in the generated index follows from Stage 5's frontmatter flip the next time the generator runs — run it. No separate header bump: the generator writes its own `Generated:` line.

### Promotion Error Handling

| Failure | Recovery |
|---------|----------|
| Lesson file not found | Check `{lessons_dir}/LL-{NNN}*` then `{lessons_dir}/Archive/LL-{NNN}*`. Use Glob `{lessons_dir}/**/LL-*` to list all. |
| Ambiguous artifact type | Present options to user and let them choose |
| Artifact file path conflict | Check if file exists; ask user to rename or merge |
| Lesson frontmatter edit fails | Use Edit tool manually on the YAML frontmatter block |
| Index update fails | Append the row with `python {plugin_root}/scripts/promotion_log.py --config {planwise_root}/config.yaml --lesson LL-{NNN} --artifact "…" --file "…"` (see [`references/lessons-schema.md`](../references/lessons-schema.md) § Promotion-Log Contract); re-run the generator once the lesson file itself is correct |

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

> [!tip] Prefer single-purpose lessons
> Building on the inlining principle above — once the substance is pasted in, keep each lesson's promotion scope to **one target type** (`rule`, `code`, `claude-md`, `agent`, `skill`, or `settings`). Infer the type from the lesson's structure: a fenced code block or diff usually promotes to `code`; a `MUST`/`NEVER` callout usually promotes to `rule`. When a single insight genuinely spans multiple target types, capture **2+ small, cross-linked lessons** instead of one coarse lesson — inlined, single-purpose lessons are easier to promote cleanly than one that tries to cover several targets at once.

Create a candidate lesson with pre-filled YAML frontmatter:

```yaml
---
id: LL-{next-available}   # derived in Step 4, never read from the index counter
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
promotion-target: [rule|code|claude-md|agent|skill|settings]   # one or more target types; multi-value = coarse / split-candidate
# promoted-to:                                                  # owning backlog item id(s), e.g. BB-{NNN}; set at capture-archive
---
```

### Step 3: Approve

Present the draft to the user:
- Show pre-filled frontmatter and draft Context/Lesson/Applies To sections
- **Self-containment check:** confirm the draft inlines every block, example, or command output the lesson depends on — a reference may add context, but the substance required to promote it later is pasted in, not only linked. (Apply the durability test in Step 2.)
- Ask: "Capture this lesson? (approve / edit / skip / approve + report upstream)" <!-- AUTO-MODE: critical -->
  - **approve + report upstream:** writes the local lesson first, same as plain approve (Step 4, unchanged — the consumer keeps their own record regardless), then passes the draft to `references/feedback-submission.md` to submit it upstream. Surface this option prominently when the draft's `technology:`/`domain:` frontmatter carries a planwise-ish token, but it is ALWAYS selectable — a non-match never hides it, and no heuristic decides on the user's behalf.

### Step 4: Write

If approved:

> [!gate] Derive the next ID — never read it from the generated counter
> The hub's `**Next available ID:**` line is `max(derived + 1, the counter already on disk)` — a forward-only floor, never a source of which ids are known — and its only writer is the generator, run in step 5 below. Derive the true value directly instead:
>
> ```bash
> python "{plugin_root}/scripts/parse_lessons.py" --config "{planwise_root}/config.yaml" --next-id
> ```
>
> It prints `LL-{NNN}` computed from the union of the working lessons directory, `Archive/`, and the index; the stated counter is not an input. If that value differs from the counter line, report the gap rather than silently correcting it — some lesson was authored off this path, and its categorisation entry may carry its own gap. `/planwise doctor` Stage 13 surfaces this drift on its next run.

1. Take `{NNN}` from the `--next-id` command above; take the lesson file template from `templates/lesson.md`
2. Determine `{Domain}` from the first value in the `domain:` field
3. **Assert `{NNN}` is unused, in BOTH directories, immediately before writing.** Glob `{lessons_dir}/LL-{NNN}-*.md` and `{lessons_dir}/Archive/LL-{NNN}-*.md`. A hit means a concurrent session claimed the ID between derivation and write. FAIL LOUD and STOP — never overwrite, and never silently pick the next free number, because the draft's frontmatter `id:` and any cross-reference already written into the body still name `{NNN}`:
   ```
   Lesson ID collision: LL-{NNN} already exists at {path}.
   The draft was not written. Re-run `/planwise lessons capture` to re-derive the ID.
   ```
4. Write file: `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md`
5. Run the generator (`python {plugin_root}/scripts/generate_lessons_index.py --config {planwise_root}/config.yaml --write`); append the changelog entry with `python {plugin_root}/scripts/lessons_changelog.py --config {planwise_root}/config.yaml --append "…"` (see [Lessons-Index Write Convention](#lessons-index-write-convention), which also covers the exit 2 `legacy-shape` refusal branch). The companion (`00-Categorization-By-Domain.md`) regenerates separately, with `--companion --write`, when the lesson's `domain:` changes a bucket's membership. Two files that still end up claiming one id despite step 3's check make `--write` refuse (exit 2, `duplicate-id`) rather than pick one — it names both.

### Step 5: Skip

If skipped, discard the draft. No file is written.

---

## Lesson Status Lifecycle

Lessons graduate through a branching set of five statuses. The value list is declared once, as `lesson_statuses:` in `config.yaml` beside the backlog `statuses:` (declarative — the workflows below match the literals as written; the template's comment records the decision):

```
                  ┌─ single-lesson promote / already-landed ──────────────────────┐
                  │                                                                ▼
   documented ────┤                                                          applied | rule
                  │                                                                ▲
                  └─ promote-batch (fully captured into backlog item[s]) ─→ promoted ┘
                         (archive-on-capture)                    (curate --phase=promote:
                                                                  content verified present → land)

   promoted ─→ orphaned    (owner closed without landing this content)
   orphaned ─→ promoted    (re-bundled into a new owning item)
```

- `documented → applied | rule` directly: single-lesson promote, or a lesson already landed at capture time (capture and landing simultaneous; never enters `promoted`).
- `documented → promoted`: promote-batch, when every fragment is owned by a drafted backlog item (archive-on-capture).
- `promoted → applied | rule`: curate `--phase=promote`, when its content is verified present in the destination artifact (landing).
- `promoted → orphaned`: the owning backlog item closed without this content ever landing, and no other live item owns it.
- `orphaned → promoted`: re-bundled into a new owning backlog item.

| Status | Meaning |
|--------|---------|
| `documented` | Captured; not yet owned by any backlog item. |
| `promoted` | Fully captured into actionable backlog item(s); archived; awaiting landing; the backlog item is the live owner. **archived ≠ landed.** |
| `orphaned` | Owner closed without landing this content; no live owner. Work-surfacing: resurfaces ahead of `documented` in the next promotion pass. |
| `applied` | Lesson has been manually applied in practice (proven useful) |
| `rule` | Lesson promoted to a Claude Code artifact |

The fifth status, `orphaned`, covers content that was fully captured into an owning backlog item, but where that item closed without the content ever landing and no other live item owns it. `orphaned` is a work-surfacing state, not a resting one — it sorts ahead of `documented` in the next batch-promotion scope resolution rather than hiding inside `documented`. Pair it with an `owner-anomaly:` frontmatter key carrying the evidence: which owner closed, what grep proved the content absent, and the date.

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
