# Handler: /planwise backlog

**Purpose:** Parse the project backlog index, let the user select items, assess scope, route each item to the right action (direct fix, task list, or session planning), and update status.

**Arguments:**
- No args — interactive selection
- `$1` = item ID — direct item selection (e.g., `/planwise backlog 002`)
- `--priority High` — filter by priority
- `--abbrev APP` — filter by domain abbreviation
- `--status IN_PROGRESS` — filter by status

---

## Config Gate

Locate `config.yaml` by checking:
1. `planwise/config.yaml` (default planwise root)
2. If not found, search one level down from the project root for `*/config.yaml`
3. If not found: "Project not initialized. Run `/planwise init` first."

Extract from `config.yaml`:
- `plugin_root` — the plugin installation path
- `project.planwise_root` — the planwise root folder (default: `planwise`)
- `project.backlog_dir` — the Backlog directory name (relative to planwise_root)
- `project.index_files.backlog` — the backlog index filename
- `project.lessons_dir` — the LessonsLearned directory name (relative to planwise_root)
- `project.index_files.lessons` — the lessons index filename
- `build_commands.default` — the build command for fix-agent delegation

All directory paths resolve as `{planwise_root}/{dir_name}` (e.g., `planwise/Backlog`). All script invocations should pass `--config {planwise_root}/config.yaml`.

---

## Required References

Before proceeding, read these reference files from `{plugin_root}/references/`:

**Base references** (`markdown-conventions.md`, `callout-conventions.md`, `agent-orchestration.md`) are pre-injected by SKILL.md.

**Conditional references:**
- If a task creates or modifies agents: Read `references/agent-authoring.md`
- If a task creates or modifies skills: Read `references/skill-authoring.md`
- If a task creates or modifies rules: Read `references/rule-authoring.md`

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

Display the table to the user.

---

## Phase 2: SELECT

**If `$1` was provided** (an item ID):
- Use that item ID directly — skip the selection prompt
- Read the JSON temp file to get the full item data

**If no arguments:**
- Present the table from Phase 1 (only selectable items — blocked items are excluded)
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
3. **Staleness check:** If the item has measurable acceptance criteria (counts, percentages, coverage targets), run `{build_command}` (from config.yaml `build_commands.default`) *before* routing. If criteria are already met or nearly met, present a "Close as COMPLETE" option instead of routing through a fix workflow.

4. Assess the item's scope using the routing decision tree in the [Routing Decision Tree](#routing-decision-tree) section below.

5. Present the scope assessment to the user:

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

**Use `AskUserQuestion` to confirm the routing:**
- Option 1: Recommended route (from Phase 3 assessment)
- Option 2: Alternative route
- Option 3: Skip this item

### Route A: Direct Fix (fix-agent delegation)

For bugs and targeted fixes with clear scope:

Delegate to the `fix-agent` via the Task tool:

```
Task {
  subagent_type: "fix-agent"
  description: "Fix backlog item {item-id}: {item-summary}"
  prompt: |
    Fix the following backlog item:

    Item ID: {item-id}
    Summary: {item-summary}
    Description: {item-description}
    Affected files: {file-list}
    Build command: {build-command-from-config}
    Backlog index: {backlog-dir}/{backlog-index}
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
2. Use `AskUserQuestion`:
   - **Approve** — Accept changes, mark COMPLETE
   - **Revert** — Discard changes, mark NOT_STARTED
   - **Skip** — Keep changes, don't update status

3. If Revert:
   ```bash
   git checkout -- {list of modified files}
   ```

**After Route B (Task List):**
1. Verify all tasks are marked completed
2. Show summary of changes made
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

## Phase 7: LESSON CAPTURE

After closing all triaged items, prompt for lessons learned.

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

Use this logic to determine the recommended route in Phase 3.

### Scope Assessment Signals

| Signal | How to Detect | Weight |
|--------|---------------|--------|
| "Bug" in feature name | Case-insensitive check on Feature column | Strong → Direct Fix |
| Item file < 50 lines | Line count on read | Strong → Direct Fix |
| Specific file paths mentioned | Regex for code file extensions | Moderate → Direct Fix |
| "multi-sprint" / "phased" keywords | Case-insensitive content search | Strong → Session Planning |
| "refactor" / "redesign" / "architecture" / "migration" | Content keywords | Strong → Session Planning |
| 6+ sub-items or ## headings | Count numbered list items and H2 headers | Moderate → Session Planning |
| Multiple reference files (YY > 01) | Files column has 2+ links | Moderate → Session Planning |
| 3-5 numbered steps | Count discrete steps | Moderate → Task List |

### Decision Logic

```
1. Read item file(s)
2. Compute signals

IF (IS_BUG AND IS_SHORT) OR (IS_SHORT AND HAS_CLEAR_FIX):
    -> DIRECT FIX (Route A)

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

```bash
python {plugin_root}/scripts/update_backlog.py --id ID --status STATUS
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--id ID` | Yes | Item ID (e.g., 002) |
| `--status STATUS` | Yes | New status (NOT_STARTED, PLANNING, IN_PROGRESS, BLOCKED, COMPLETE, CLOSED) |

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
