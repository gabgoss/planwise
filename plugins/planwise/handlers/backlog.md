# Handler: /planwise backlog

**Purpose:** Parse the project backlog index, let the user select items, assess scope, route each item to the right action (direct fix, task list, or session planning), and update status.

**Arguments:**
- No args — interactive selection
- `$1` = item ID — direct item selection (e.g., `/planwise backlog 002`)
- `--priority High` — filter by priority
- `--abbrev APP` — filter by domain abbreviation
- `--status IN_PROGRESS` — filter by status
- `--no-check` — skip the Phase 1 archival-drift detect pass (fast triage)

---

## Config Gate (Auto-Init Fallback)

1. Resolve config.yaml:
   a. Check `planwise/config.yaml` (default planwise root)
   b. If not found, search one level down from project root for `*/config.yaml`

2. If found → continue to Required References (extract `plugin_root`, `project.planwise_root`, `project.backlog_dir`, `project.index_files.backlog`, `project.lessons_dir`, `project.index_files.lessons`, `build_commands.default`).

3. If NOT found:
   a. Announce: "Planwise not initialized in this project. Running /planwise init first…"
   b. Resolve `{plugin_root}` from the handler's own known location (SKILL.md plugin base path).
   c. Invoke init subroutine:
      - **If Auto Mode active:**
        ```bash
        python "{plugin_root}/scripts/init_project.py" \
          --name "{inferred_project_name}" \
          --root "planwise" \
          --plans-dir "Plans" \
          --backlog-dir "Backlog" \
          --lessons-dir "LessonsLearned" \
          --scope "project" \
          --auto-from "backlog"
        ```
      - **If Auto Mode NOT active (interactive):**
        Use `AskUserQuestion` to collect project info (project name, scope, dirs),
        then run `init_project.py` with those values + `--auto-from "backlog"`.
   d. After init completes, RE-RESOLVE `config.yaml` (loop to step 1).
   e. If still NOT found after init:
      FAIL LOUD: "Init did not produce config.yaml. See output above."
      STOP — do not continue.

Where `{inferred_project_name}` = current git repo name or `cwd` basename (strip trailing `-`, `_`, `.git` suffix).

> [!gate] Config Malformed → FAIL LOUD
> If `config.yaml` is present but malformed (YAMLError), DO NOT auto-init. FAIL LOUD: "config.yaml parse error at {path}: {error}. Fix or delete the file before running /planwise backlog." STOP.

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Backlog`). All script invocations should pass `--config {planwise_root}/config.yaml`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`, `do-the-hard-things.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`
- If resolving a backlog item that touches task files: Read `references/task-content-fidelity.md`
- If resolving a BLI cluster (≥ 2 BLIs same Surfaced by + created): Read `references/verify-against-shipped-artifact.md`

---

## Phase 1: FETCH

**Score and parse the backlog index:**

```bash
python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml
```

- `score_backlog.py` computes priority scores (8 configurable factors, weights from `config.yaml`) and writes the Score column to the index
  - Items that block other open items get a blocker bonus per blocked item
- `parse_backlog.py` reads the backlog index at `{backlog_dir}/{backlog_index}`
- Outputs a formatted table of **selectable** items (excludes COMPLETE, CLOSED, and items blocked by open dependencies)
- Blocked items appear in a separate summary below the main table
- Prints JSON temp file path on the last line: `JSON: /tmp/backlog-XXXXX/items.json`
- If no open items: print "No open backlog items." and **STOP**

**With filters (pass through from `$ARGUMENTS`):**

```bash
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --priority High
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --abbrev APP
python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --status IN_PROGRESS
```

**Detect archival drift (always-on unless `--no-check`):**

The backlog index is a denormalized cache: a COMPLETE/CLOSED item's file is moved to `Archive/` and its index link repointed as a **state-coupled** step in `update_backlog.py`. But an item that reaches a closed status by another path — a session closeout that hand-edits the index row + frontmatter — leaves the file stranded in the top-level backlog dir with an index link that never repointed, and nothing on the read side heals it. This detect pass is that read-side counterpart (the backlog analogue of `/planwise list` Step 2's plans-index drift check), reused unchanged in `/planwise doctor` Stage 12. It stays **non-mutating by default** — nothing is written without explicit consent.

**If `--no-check` is present:** skip this step (a fast triage) and go straight to displaying the table.

Otherwise run:

```bash
python {plugin_root}/scripts/reconcile_backlog.py --config {planwise_root}/config.yaml --json
```

Read the JSON file at the path it prints (`JSON: {path}`), shaped `{"drifts": [...], "anomalies": [...]}`. `drifts` are closed rows whose file is not archived (or whose index link is not repointed); `anomalies` are closed rows whose linked file exists in neither the top-level dir nor `Archive/` (deleted/renamed — reported, never fabricated). If either is non-empty, print a banner **before** the backlog table:

```
⚠ Backlog archival drift ({K} closed row(s) whose file is not archived):
  • {ID} ({STATUS}): {file} — {reason}
Anomalies:
  • {ID} ({STATUS}): {file} — linked file not found in backlog dir or Archive/
```

If both are empty, print nothing.

**Write on consent (READ-CONFIRM-ACT):** after the banner, use `AskUserQuestion` to offer reconciliation: "Archive {K} stranded closed row(s) — move the file(s) into `Archive/` and repoint the index link(s)?" On agreement:

```bash
python {plugin_root}/scripts/reconcile_backlog.py --config {planwise_root}/config.yaml --write
```

The script re-reads the index immediately before writing (race-safe against a concurrent closeout), heals only rows still drifted, and never touches an anomaly row. Report `Reconciled {N} row(s).` If the user declines, leave the backlog untouched — the banner already recorded what was found. If a write ran, re-run the Phase 1 parse so the reconciled links are reflected in this same invocation.

Display the table to the user.

---

## Phase 2: SELECT

**If `$1` was provided** (an item ID):
- Use that item ID directly — skip the selection prompt
- Read the JSON temp file to get the full item data

**If no arguments:**
- Present the table from Phase 1 (only selectable items — blocked items are excluded)
<!-- AUTO-MODE: convenience if $1 provided (use that item ID); critical if interactive (gate on user selection). -->
- Use `AskUserQuestion` to ask: "Which items would you like to triage?"
  - Provide the first 4 item IDs as options (highest priority from selectable items)
  - User can select one or more, or type a custom ID
  - Do NOT offer blocked items — they cannot be worked until their blockers are resolved

**For each selected item**, update status to IN_PROGRESS:

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status IN_PROGRESS
```

---

## Phase 3: RESOLVE

**For each selected item:**

1. Get the item's file paths from the JSON data (the `files` array)
2. Read each backlog item file (files have YAML frontmatter with `created`, `blocks`, and `status` fields)
3. **Citation-Freshness Preflight (run before scoping or routing):** A backlog item's body is a snapshot — every reference it pins (a sequential identifier, a `file:line` anchor, an acceptance criterion, a "test/section X does Y" note) is a hypothesis about a live artifact that rots between authoring and execution. Re-prove each against the current artifact before scoping. See `references/verify-backlog-citation-freshness.md` §9.

   > [!checklist] Citation-Freshness Preflight (run before scoping or routing a backlog item)
   > - [ ] For every pinned sequential identifier the item cites (Check NNN, Error Pattern Catalog row N, reference §N.N), grep the live target for the current max and re-derive the next-free value; renumber the item's deliverables + self-references to match
   > - [ ] For every `file:line` anchor, re-locate the symbol by content grep; treat the cited line number as a cost hint only
   > - [ ] For every acceptance criterion, run the cheapest proof it is still unsatisfied before writing a fix; mark any already-satisfied criterion "already satisfied — verified"
   > - [ ] For every pre-drafted note/callout that asserts "test/section/function X does Y", verify against the live file and re-word to name the artifact that actually carries the behavior

4. **Staleness check:** If the item has measurable acceptance criteria (counts, percentages, coverage targets), run `{build_command}` (from config.yaml `build_commands.default`) *before* routing. If criteria are already met or nearly met, present a "Close as COMPLETE" option instead of routing through a fix workflow.
   - If the BLI's motivating driver is a runtime symptom (keywords: collision, race, hang, missing endpoint, intermittent), run a `grep -rn` for the symptom in `src/` and cross-check against recent session summaries in `Plans/**/Sessions/**/Outputs/`. If the driver is no longer active (no recent matches, fix landed), mark the BLI as STALE per `verify-backlog-citation-freshness.md §3h` and skip routing. Include §3h.untested-axes and §3h.cluster signal checks per the same reference.

5. Assess the item's scope using the routing decision tree in the [Routing Decision Tree](#routing-decision-tree) section below.

6. **Scoped-rule pre-delegation check (§3g):** Read the BLI's `Files` section. For each named destination path, grep `.claude/rules/**/*.md` for `paths:` declarations that include the destination. If any rule scopes a path matching the BLI's destination, flag the placement decision for human review BEFORE spawning the fix-agent.

   ```bash
   grep -rn "paths:" .claude/rules/
   ```

   Compare each `paths:` value against the BLI's destination paths. If a match is found, present a warning:

   > **Scoped-rule conflict detected:** destination `{path}` is covered by a scoped rule in `{rule-file}`. Verify the fix targets the correct file before delegating.

   This gate applies regardless of route (Route A or Route B) — do not skip it.

7. Present the scope assessment to the user:

> [!template] Scope Assessment Block
> ```
> ─────────────────────────────────────────────
> ITEM: {ID} — {Feature}
> Priority: {Priority} | Domain: {Domain}
> ─────────────────────────────────────────────
>
> ## What This Is About
>
> {2-4 sentence plain-language summary of what the backlog item describes}
>
> ## Files Touched
>
> - `{path/to/file1.ext}` — {brief role}
> - `{path/to/file2.ext}` — {brief role}
>
> ## Tasks at a Glance
>
> 1. {First discrete task or step}
> 2. {Second discrete task or step}
> 3. ...
>
> ## Scope Assessment
>
> Route: {DIRECT_FIX | TASK_LIST | SESSION_PLANNING}
> Reason: {why this route was chosen}
> ─────────────────────────────────────────────
> ```

---

## Phase 4: ACT

<!-- AUTO-MODE: convenience -->
<!-- Default: Accept Phase 3 recommended route (DIRECT_FIX / TASK_LIST / SESSION_PLANNING). -->
**Use `AskUserQuestion` to confirm the routing:**
- Option 1: Recommended route (from Phase 3 assessment)
- Option 2: Alternative route
- Option 3: Skip this item

### Route A: Direct Fix (fix-agent delegation)

For bugs and targeted fixes with clear scope:

**Pre-spawn: extract cross-cutting audit candidates (§3i):** Before building the spawn prompt, read the BLI file and look for sections named `Cross-cutting check`, `Cross-cutting consideration`, or `Notes`. Extract any cross-cutting items listed there to include in the spawn prompt. If none are found, use `"none identified"`.

Delegate to the `fix-agent` via the Task tool:

```
Task {
  subagent_type: "planwise:fix-agent"
  description: "Fix backlog item {item-id}: {item-summary}"
  prompt: |
    Fix the following backlog item:

    Item ID: {item-id}
    Summary: {item-summary}
    Description: {item-description}
    Affected files: {file-list}
    Build command: {build-command-from-config}
    Cross-cutting audit candidates (in-scope by default): {list extracted from BLI cross-cutting sections, or "none identified" if absent}
}
```

**Result handling:**
- If fix-agent returns status FIXED → proceed to Phase 5 (verify + approve)
- If fix-agent returns status BLOCKED → report blocker to user, offer to route to Session Planning (Route C)

### Route B: Task List

For medium-scope items with 3-5 discrete steps:

1. Analyze the backlog item file to extract discrete steps
2. Create tasks using `TaskCreate` for each step
3. Work through each task sequentially
4. After all tasks complete, proceed to Phase 5

### Route C: Session Planning

For large-scope or architectural items:

1. Summarize the item context (title, files, scope signals)
2. Tell the user: "This item needs a full plan. Use `/planwise plan` with the backlog item context to create a session plan when ready."
3. Proceed to Phase 6 (status → PLANNING)

---

## Phase 5: VERIFY

**After Route A (Direct Fix):**

1. Show the diff:
   ```bash
   git diff --stat
   ```
   ```bash
   git diff
   ```

2. **Self-containment grep gate (BINDING when the BB touches content-bearing artifacts):** If the diff includes any added or modified files under `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, or `CLAUDE.md`, run the grep from [`references/artifact-self-containment.md` §4](../references/artifact-self-containment.md#4-mechanical-verification) on the changed files:

   ```bash
   grep -rnE '(LL-[0-9]{3}|BB-[0-9]{3})' {changed-content-artifact-paths}
   # MUST return zero matches.
   ```

   If matches → mark VERIFY as failing, return the grep output to the fix-agent (Route A) or open a follow-up task (Route B) requesting the cited content be inlined. Do NOT proceed to step 3 with grep hits outstanding. A BB whose diff touches ONLY bookkeeping zones (lessons index, backlog index, lesson frontmatter, BB Notes) skips this gate. See [§4.1](../references/artifact-self-containment.md#41-what-the-grep-deliberately-does-not-cover) for the exempt zones.

<!-- AUTO-MODE: critical -->
3. Use `AskUserQuestion`:
   - **Approve** — Accept changes, mark COMPLETE
   - **Revert** — Discard changes, mark NOT_STARTED
   - **Skip** — Keep changes, don't update status

4. If Revert:
   ```bash
   git checkout -- {list of modified files}
   ```

**After Route B (Task List):**
1. Verify all tasks are marked completed
2. Show summary of changes made
<!-- AUTO-MODE: critical -->
3. Use `AskUserQuestion`: Approve (COMPLETE) or Revert (NOT_STARTED)

**After Route C (Session Planning):**
- No verification needed — plan creation is the deliverable

---

## Phase 6: CLOSE

**Update backlog index status based on Phase 5 decision:**

| Outcome | Status Update |
|---------|---------------|
| Fix approved | `--status COMPLETE` |
| Fix reverted | `--status NOT_STARTED` |
| Task list completed | `--status COMPLETE` |
| Session plan created | `--status PLANNING` |
| Skipped | No change |

```bash
python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --id "{item_id}" --status "{new_status}"
```

**Re-score after status changes** (skip if outcome was "Skipped" — nothing changed):

```bash
python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
```

**Automatic archival:** When status is set to COMPLETE or CLOSED, `update_backlog.py` automatically:
- Moves item file(s) to the Archive/ directory within `{backlog_dir}`
- Updates index links to point to `Archive/` subfolder

**Twin-plan reconciliation (run when the outcome is COMPLETE/CLOSED):** If this item shipped deliverables that a live plan was authored to produce, retire that twin plan in the **same** closeout. A plan's status fields and its plans-index row are written only by session closeout (`/planwise run`); a plan whose deliverables were instead satisfied through this backlog route is written nowhere, so it is left live and independently runnable — and a later `/planwise run` will accept it and re-execute idempotency-unsafe steps ("append N rows", "insert at max+1", "add the next check number") against already-satisfied state, corrupting it.

> [!constraint] Retire or link the twin plan at backlog closeout
> 1. **Detect the twin.** Grep the plans index (`{plans_dir}/{plans_index}`) and the Master Plans under `{plans_dir}/**` for a plan that names the same deliverables — or targets the same files — this item just shipped.
> 2. **Reconcile it in this closeout.** For each twin found, set its Master Plan / sprint / orchestration `Status: COMPLETE (superseded — shipped via BB-{item_id} {route} {date})` and update its plans-index row — OR explicitly link the two so the plan is not independently runnable.
> 3. **If you cannot reconcile now, do not leave it silently runnable** — record the twin plan and the blocker so a later closeout retires it.
>
> WRONG — close the item, leave the twin plan alone → `/planwise run` starts it → a task step "append N rows" runs against rows that already exist → N duplicate rows, or a duplicate `## N` section colliding with the shipped one.
> CORRECT — retire/link the twin plan in the same closeout so it is no longer independently runnable.

**Print summary table:**

> [!template] Session Summary
> ```
> ID  | Feature                              | Action        | Status
> ----|--------------------------------------|---------------|--------
> 002 | Fix login redirect bug               | Direct Fix    | COMPLETE
> 001 | Setup project CI pipeline            | Plan Created  | PLANNING
> 003 | Add user profile page                | Skipped       | IN_PROGRESS
> ```

---

## Phase 7: FOLLOW-UP BLI CAPTURE

After closing all triaged items, auto-surface actionable recommendations from resolution Outputs as candidate backlog items.

### Step 7.1: Grep Resolution Outputs

Use Grep to scan resolution Outputs in `{plans_dir}/**/Outputs/` for the declarative follow-up block convention:

```
pattern: > \[!followup\]
path: {plans_dir}
output_mode: content
-A: 20
```

Identify candidate recommendations. Also check task files of recently-closed items for inline `> [!followup]` callouts (per `references/task-file-and-tracking-requirements.md` Declarative Follow-Up Block Convention).

**Field extraction:** For each `> [!followup]` callout found, parse the body lines for fields in the form:

```
- {Recommendation}: {description} (target: {file_path}; severity: {high|medium|low})
```

Extract structured fields using these patterns:

```
target pattern:   /target:\s*([^\s;)]+)/    →  Target file (in Follow-Up Candidate Block)
severity pattern: /severity:\s*(high|medium|low)/i  →  Severity (in Follow-Up Candidate Block)
```

Fallback values when fields are absent or malformed:
- `target:` absent → default `Target file` to the session's source file path
- `severity:` absent → default `Severity` to `medium`

### Step 7.2: Surface Candidates to User

Present each candidate to the user with the auto-recommendation heuristic:

> [!template] Follow-Up Candidate Block
> ```
> ─────────────────────────────────────────────
> CANDIDATE: from {Outputs/source-file.md}
> ─────────────────────────────────────────────
>
> Recommendation: {description}
> Target file: {file_path}
> Severity: {high|medium|low}
> Originating item: {BLI-NNN-..}
> ─────────────────────────────────────────────
> ```

<!-- AUTO-MODE: convenience -->
<!-- Default: skip all (do not auto-create BBs unattended; user explicitly invokes /planwise backlog to surface). -->
Use `AskUserQuestion`: "Create backlog item from this candidate?"
- Option 1: Yes — create BLI
- Option 2: No — skip
- Option 3: Edit — modify before creating

### Step 7.3: Auto-Create BLI Files

> [!important] Inline the content the capture depends on
> When a backlog item's value rests on specific content — a block to promote, the evidence behind a finding, an exact spec or recipe — **paste that content into the item verbatim**. A pointer (another repo, a path, a session-only artifact) is welcome *alongside* the inlined content for context or provenance, but it must NOT be the *sole* carrier of the substance: the item must stay fully executable if that source becomes unavailable.
> - **Inline:** the verbatim text to promote, the failing command + its output, the exact before/after, the spec.
> - **Reference-only is acceptable** for: large, stable in-repo files that will still exist at execution time AND are not the unique carrier of the item's substance.
> - **Durability test:** "If the originating session or repo vanished tomorrow, could someone execute this item from the file alone?" If no, inline more.
>
> This is a different concern from shipped-artifact self-containment (`references/artifact-self-containment.md`, which strips internal identifiers out of distributed artifacts) — here the goal is that the capture itself carries its own substance.

For each accepted candidate:

1. **Get next BLI ID:**
   ```bash
   python {plugin_root}/scripts/parse_backlog.py --config {planwise_root}/config.yaml --next-id
   ```

2. **Create BLI file** at `{backlog_dir}/BLI-{NNN}-{Domain}-{Topic}.md` using the [backlog-item.md](../templates/backlog-item.md) template; pre-fill:
   - Title from recommendation
   - `created:` today's date
   - `status: NOT_STARTED`
   - Body from candidate description + target file + severity
   - **Self-containment check:** the body inlines every block, spec, or piece of evidence the item depends on — a reference may add context, but the substantive content required to act is pasted in, not only linked. (Apply the durability test above.)

3. **Append row to backlog index:**
   ```bash
   python {plugin_root}/scripts/update_backlog.py --config {planwise_root}/config.yaml --create --id "{NNN}" --feature "{recommendation}" --priority "{inferred from severity}" --abbrev "{Domain}" --files "BLI-{NNN}-{Domain}-{Topic}.md"
   ```

4. **Re-score backlog** after all candidates processed:
   ```bash
   python {plugin_root}/scripts/score_backlog.py --config {planwise_root}/config.yaml
   ```

### Step 7.4: Output Summary

```
PHASE 7 — FOLLOW-UP BLIs CAPTURED

Candidates surfaced: {N}
BLIs created: {M}
Skipped: {N - M}

New BLI IDs: BLI-{NNN}, BLI-{NNN+1}, ...
```

---

## Phase 8: LESSON CAPTURE

After closing all triaged items, prompt for lessons learned.

<!-- AUTO-MODE: convenience -->
<!-- Default: No. -->
**Ask the user:** "Were any lessons learned during this triage session? (y/n)"

**If no:** Skip this phase and finish.

**If yes:** Read `{lessons_dir}/{lessons_index}` for the lesson file template and the next available lesson number. Create a lesson file at `{lessons_dir}/LL-{NNN}-{Domain}-{Name}.md` and add a row to the master table in the lessons index.

### Backlog Lesson Categories

| Category | When to Capture | Example |
|----------|-----------------|---------|
| `triage-routing` | Routing decision was non-obvious | "Item appeared simple but required planning due to cross-cutting dependencies" |
| `scope-assessment` | Scope signals were misleading | "Bug keyword but actual issue was architectural" |
| `resolution-outcome` | Fix succeeded or failed in a noteworthy way | "Direct fix worked but revealed a related issue" |

---

## Routing Decision Tree

> [!practice] Route by What the Defect Needs
> Pick the route that fully resolves the item, not the cheapest one to execute — a session-sized fix gets Route C, never a quick patch that leaves known incoherence behind. Full principle and exception clause: [do-the-hard-things.md](../references/do-the-hard-things.md).

Use this logic to determine the recommended route in Phase 3.

### Scope Assessment Signals

| Signal | How to Detect | Weight |
|--------|---------------|--------|
| "Bug" in feature name | Case-insensitive check on Feature column | Strong → Direct Fix |
| Item file < 50 lines | Line count on read | Moderate → Direct Fix (a *proxy* for a small fix — a file that is long only because it is thoroughly documented is NOT large scope) |
| Exact fix evidence: named files + line anchors + before/after content + scope-confinement bound | BB body supplies concrete, bounded edit targets | Strong → Direct Fix — sets `HAS_CLEAR_FIX` regardless of file length |
| Specific file paths mentioned | Regex for code file extensions | Moderate → Direct Fix |
| "multi-sprint" / "phased" keywords | Case-insensitive content search | Strong → Session Planning |
| "refactor" / "redesign" / "architecture" / "migration" | Content keywords | Strong → Session Planning |
| 6+ sub-items or ## headings | Count numbered list items and H2 headers | Moderate → Session Planning |
| Multiple reference files (YY > 01) | Files column has 2+ links | Moderate → Session Planning |
| 3-5 numbered steps | Count discrete steps | Moderate → Task List |

### Decision Logic

```
1. Read item file(s)
2. Compute signals.
   HAS_CLEAR_FIX is true when EITHER the item is short (< 50 lines) OR the BB
   supplies exact fix evidence — named files, line anchors, before/after content,
   and an explicit scope-confinement bound ("do NOT touch X"). Route on the
   *measured* edit scope, never on file length alone: a BB that is long only
   because it is thoroughly documented still has a clear, surgical fix.

IF HAS_CLEAR_FIX AND NOT (IS_ARCHITECTURAL OR HAS_MULTI_SPRINT OR SUB_ITEMS >= 6):
    -> DIRECT FIX (Route A)          # IS_BUG strengthens this signal but is not required

ELIF HAS_MULTI_SPRINT OR IS_ARCHITECTURAL OR (SUB_ITEMS >= 6):
    -> SESSION PLANNING (Route C)

ELIF 2 <= STEP_COUNT <= 5:
    -> TASK LIST (Route B)

ELSE:
    -> SESSION PLANNING (Route C) [conservative default]

3. Present recommendation via AskUserQuestion
4. User can override to any route or skip
```

---

## Backlog Index Format

**Source file:** `{backlog_dir}/{backlog_index}` (paths from `config.yaml`)

### Table Columns

| Column | Type | Description |
|--------|------|-------------|
| ID | 3-digit zero-padded (001-999) | Unique backlog item number |
| Feature | Free text | Short description of the item |
| Priority | High, Medium, Low | Item priority level |
| Status | See status values below | Current item state |
| Abbrev | 2-4 chars | Category domain (defined in `config.yaml`) |
| Score | Integer or `-` | Computed priority score (open items only; `-` for COMPLETE/CLOSED) |
| Files | Markdown links | Reference files: `[01](path.md) [02](path2.md)` |

### Status Values

| Status | Description |
|--------|-------------|
| NOT_STARTED | Item identified but no work begun |
| PLANNING | Requirements gathering or design in progress |
| IN_PROGRESS | Active development |
| BLOCKED | Waiting on dependency or decision |
| COMPLETE | Implemented and verified |
| CLOSED | Resolved without implementation (duplicate, won't fix, etc.) |

### Backlog Item File Format

**Naming pattern:** `BB-{ID}-{SB}-{Domain}-{Topic}.md`

| Component | Description | Example |
|-----------|-------------|---------|
| `BB` | Fixed prefix | `BB` |
| `ID` | Backlog index number (3-digit, zero-padded) | `003` |
| `SB` | Sub-backlog number; split when file exceeds 500 lines | `01`, `02` |
| `Domain` | Category domain (defined in `config.yaml`) | `APP` |
| `Topic` | Descriptive name (PascalCase) | `UserProfilePage` |

**YAML frontmatter:**

```yaml
---
title: "Item title"
created: 2026-01-15
status: NOT_STARTED
blocks: []
---
```

| Field | Type | Used By |
|-------|------|---------|
| `title` | string | Display |
| `created` | date (YYYY-MM-DD) | Scoring factor 8 (age) |
| `status` | string | Synced by `update_backlog.py` |
| `blocks` | list of item IDs | Scoring factor 6 (blocks count) |

---

## Scoring System

Items are ranked by a computed priority score using 8 weighted factors. All weights are configurable in `config.yaml` under the `scoring` section.

### Scoring Factors

| # | Factor | Default Points | Source |
|---|--------|---------------|--------|
| 1 | Priority | High=30, Med=20, Low=10 | `config.yaml: scoring.priority_*` |
| 2 | Bug/Fix keyword | +15 | Index: Feature contains "Bug" or "Fix" |
| 3 | IN_PROGRESS boost | +10 | Index: Status column |
| 4 | File count | +5 per extra file (beyond 1) | Index: Files column |
| 5 | PLANNING penalty | -5 | Index: Status = PLANNING |
| 6 | Blocks count | +20 per open item blocked | Item YAML: `blocks` field |
| 7 | Abbrev momentum | +5 | Archive: same-abbrev item recently completed |
| 8 | Age | +1 per week (cap: +12) | Item YAML: `created` field |

### Priority Review

`score_backlog.py --review` surfaces items needing attention:
- Items with age > 8 weeks (approaching cap)
- Score/priority mismatch
- All IN_PROGRESS items (staleness check)
- High-impact blockers (blocks 2+ items)

---

## Script Interfaces

All scripts are in `{plugin_root}/scripts/`. They locate `config.yaml` in the planwise root directory (e.g., `planwise/config.yaml`). Pass `--config {planwise_root}/config.yaml` explicitly.

### parse_backlog.py

```bash
python {plugin_root}/scripts/parse_backlog.py [OPTIONS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--status STATUS` | No | Filter by status (case-insensitive) |
| `--priority PRIORITY` | No | Filter by priority (case-insensitive) |
| `--abbrev ABBREV` | No | Filter by abbreviation (case-insensitive) |
| `--id ID` | No | Filter by specific item ID |
| `--include-closed` | No | Include COMPLETE/CLOSED items |
| `--show-blocked` | No | Include items blocked by open dependencies (hidden by default) |
| `--next-id` | No | Print the next available BLI ID (NNN form, zero-padded) and exit |

**Output:** Formatted table of selectable items + blocked items summary + `JSON: /tmp/backlog-XXXXX/items.json` path on last line.

**JSON schema:**

```json
[
  {
    "id": "002",
    "feature": "Fix login redirect bug",
    "priority": "High",
    "status": "NOT_STARTED",
    "abbrev": "BUG",
    "files": [
      {"label": "01", "path": "BB-002-01-BUG-LoginRedirectBug.md"}
    ]
  }
]
```

### update_backlog.py

Two modes: **status update** (default) and **create** (`--create`).

```bash
# Update an existing item's status
python {plugin_root}/scripts/update_backlog.py --id ID --status STATUS

# Create a new backlog item (writes the BLI file from the template + appends an index row)
python {plugin_root}/scripts/update_backlog.py --create --id ID --feature FEATURE \
  --priority PRIORITY --abbrev ABBREV --files FILES [--status STATUS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--id ID` | Yes | Item ID (e.g., 002); in create mode, the new item's ID |
| `--status STATUS` | Update: Yes — Create: No | New status (NOT_STARTED, PLANNING, IN_PROGRESS, BLOCKED, COMPLETE, CLOSED). In `--create` mode it is optional and defaults to NOT_STARTED |
| `--create` | No | Create a new backlog item instead of updating an existing item's status |
| `--feature FEATURE` | Create only | Feature / recommendation summary (required with `--create`) |
| `--priority PRIORITY` | Create only | Priority — High, Medium, or Low (required with `--create`) |
| `--abbrev ABBREV` | Create only | Domain abbreviation (required with `--create`) |
| `--files FILES` | Create only | Affected files, semicolon-separated; the first is written as the new BLI file from `templates/backlog-item.md` (required with `--create`) |

**Automatic archival (COMPLETE/CLOSED):** Moves item files to `{backlog_dir}/Archive/` and updates index links.

### score_backlog.py

```bash
python {plugin_root}/scripts/score_backlog.py [OPTIONS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--dry-run` | No | Compute and print scores without writing to the index |
| `--review` | No | Output a priority review report (no index writes) |

### cleanup_backlog.py

```bash
python {plugin_root}/scripts/cleanup_backlog.py --target {index|archive|both}
```

Run when the index exceeds ~500 lines to remove COMPLETE/CLOSED rows. `--target archive` deletes archived files; `--target both` does both operations.

---

## Status Flow

```
NOT_STARTED --[select in Phase 2]--> IN_PROGRESS
                                          |
                  +-----------------------+-----------------------+
                  |                       |                       |
                  v                       v                       v
            DIRECT FIX               TASK LIST              SESSION PLAN
            (Route A)                (Route B)              (Route C)
                  |                       |                       |
            +-----+                       |                       |
            |     |                       v                       v
   Approved v  Reverted v         All done --> COMPLETE    Plan --> PLANNING
         COMPLETE  NOT_STARTED
```

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `config.yaml` not found | Print "Project not initialized. Run `/planwise init` first." and STOP |
| Index file not found | Script exits with error; print path and STOP |
| Item ID not found | Print error; ask user to verify ID (IDs are zero-padded: 002, not 2) |
| Item file not found | Warn user; skip scope analysis, ask for manual route |
| Fix agent returns BLOCKED | Report blocker to user; offer Route C (Session Planning) |
| Status update fails | Print error; continue to next item |
| No items match filter | Print "No items match filters." and STOP |
