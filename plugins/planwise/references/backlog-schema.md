---
description: Backlog Schema Reference for /planwise backlog -- the backlog index table format, backlog item file naming and frontmatter, the 8-factor priority scoring system, script command-line interfaces, the status state machine, and error handling. Loaded on demand; the 8-phase triage pipeline itself stays in handlers/backlog.md.
consult-when: Working with `/planwise backlog` — index format, frontmatter, 8-factor priority scoring, status states
---

# Backlog Schema Reference

**Purpose:** Static schema and API reference for the backlog system -- consulted occasionally, not on every triage invocation, so it is split out from the triage pipeline that runs on every `/planwise backlog` call.
**Loaded by:** [handlers/backlog.md](../handlers/backlog.md), on demand.

---

## Backlog Index Format

**Source file:** `{backlog_dir}/{backlog_index}` (paths from `config.yaml`)

### Table Columns

The generated index is a 9-column table. Position matters as much as content:
more than one script reads a cell by its numeric index rather than by header
text, so a column that moved position would break them silently.

| Column | Position | Type | Description |
|--------|----------|------|-------------|
| ID | 0 | 3-digit zero-padded (001-999) | Unique backlog item number; both bare (`002`) and prefixed (`PFX-002`) ID-cell forms are accepted, matched on the numeric component (leading zeros and any alpha prefix are ignored) — a new row's written form follows the index's predominant existing form, or an explicit `id_format` config key (`"prefixed" \| "bare"`) |
| Title | 1 | ≤120 characters | One-line title; the narrative lives in the item file, never in this cell. A title over the cap is truncated at a word boundary in the rendered row and reported on stderr; scoring reads the item's raw, untruncated title |
| Priority | 2 | High, Medium, Low | Item priority level |
| Status | 3 | See status values below | Current item state. Read at this literal index by a downstream reader |
| Domain | 4 | 2-4 chars | Category domain (defined in `config.yaml`) |
| Created | 5 | date (YYYY-MM-DD) | Item creation date, from frontmatter |
| Blocks | 6 | List of item IDs or blank | IDs of open items this item blocks; the generated projection of the item's own `blocks:` frontmatter (single source of truth — see the frontmatter table below) |
| Score | 7 (second-to-last) | Integer or `-` | Computed priority score (open items only; `-` for COMPLETE/CLOSED) |
| File | 8 (last) | One markdown link | Reference file: `[003](path.md)` |

> [!note] A generated index's File cell always resolves against `backlog_dir`
> A `generate_backlog_index.py`-produced hub, hub overflow leaf, or Archive
> shard renders its single File cell as a link relative to `backlog_dir` --
> never relative to the row's own containing file. A reader resolves every
> File cell as `backlog_dir / <cell>`, even inside an Archive shard, whose
> own file lives one directory deeper (`backlog_dir/Archive/...`). The
> accepted cost: a human clicking that link from inside a shard lands one
> directory too deep. This is recorded, not fixed.

### Hub, Overflow Leaves, and Archive Shards

The generator partitions every item by status: an open item renders into the
hub; a closed item (COMPLETE/CLOSED) renders into an Archive shard. A closed
item's shard is `shard = (id - 1) // 100` -- a pure function of the id alone,
so there is no lookup table to maintain and no way for an id's shard to be
ambiguous.

Every generated file -- the hub, and any hub overflow leaf -- is kept under
a **12,500-token budget**. That is half the 25,000-token page cap, so a
growing hub keeps headroom before a table can outrun a single Read call.
Every Archive shard is kept under a separate, wider **22,000-token
budget**: a shard is written once and closed, so it does not need the same
headroom a growing hub does. The generator *enforces* both budgets rather
than merely reporting them: at `--write` time, a table that would exceed
its budget is split further before anything is written (the hub into
numbered overflow leaves, a shard century into more than one shard file),
so a file that would breach either budget is never produced in the first
place. `--check` reports a budget breach found on disk as drift. Every
file is measured on its shipped-bytes basis: UTF-8 bytes plus one byte per
line ending, the CRLF worst case. A byte count taken from a Windows
checkout, which writes CRLF and so adds one extra byte per line, therefore
never reads as larger than the count the generator enforced against.
Links are bidirectional: the hub's `## Shards` directory lists every
Archive shard and every hub overflow leaf, and each of those backlinks to
the hub. The open set a reader pages through can therefore span the hub
plus its own overflow leaves.

This replaces a retired idea: a manual rotation trigger keyed on line count.
A line count was never the real constraint -- a live hub can sit at a few
hundred lines and well under 250 KB while individual item titles and links
still push a table's real cost, in bytes and tokens, past what a single Read
call can return. The token budget above targets that real constraint
directly, and unlike a threshold that lived only in this reference's prose
with nothing checking it, the generator enforces this one structurally: there
is no step where an author has to remember to run a cleanup script before the
threshold is silently exceeded. A later doctor read-gate extension
independently re-checks the same budget across the backlog, lessons, and
plans indexes from outside the generator -- useful for anything the generator
itself does not own, such as a hand-authored item file that grows past
budget on its own.

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
| `SB` | Sub-backlog number; split when the file approaches the ~22K-token one-read budget. Advisory only — no checker enforces this threshold | `01`, `02` |
| `Domain` | Category domain (defined in `config.yaml`) | `APP` |
| `Topic` | Descriptive name (PascalCase) | `UserProfilePage` |

**YAML frontmatter is the single source of truth for the item's index row.**
The generator reads it and renders the row; it never writes an item file,
and it never invents a value for a missing required key -- a missing key is
reported and the run aborts rather than silently patching the gap.

```yaml
---
id: 003
title: "Item title"
priority: High
status: NOT_STARTED
abbrev: APP
created: 2026-01-15
blocks: []
---
```

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `id` | integer | Yes | Row identity; Score/File cell derivation |
| `title` | string | Yes | Display -- ≤120 characters; the narrative belongs in the item file's body, never here |
| `priority` | enum (`High`\|`Medium`\|`Low`) | Yes | Scoring factor 1 |
| `status` | string | Yes | Hub-vs-shard partitioning; scoring factors 3 and 5 |
| `abbrev` | string | Yes | Scoring factor 2 (Bug/Fix); rendered as the row's Domain cell |
| `created` | date (YYYY-MM-DD) | Yes | Scoring factor 8 (age) |
| `blocks` | list of item IDs | Yes (may be `[]`) | Scoring factor 6 (blocks count); the generated projection is the row's Blocks cell |
| `route_hint` | enum (`A`\|`B`\|`C`) | No | The filing author's provisional triage route (Direct Fix / Task List / Session Planning) |
| `route_evidence` | string | No | One line: why that route, from what the author verified live at filing time |
| `route_dated` | date (YYYY-MM-DD) | No | The date the route was judged -- a stored route is a dated claim that rots like any other, and this date makes that staleness visible at triage |
| `needs_plan` | bool | No | Written as `true` by the Route C marker-and-skip (`update_backlog.py --mark-needs-plan`, `backlog_loop.py --mark --needs-plan`); marks an item that needs a planning session. Read by `score_backlog.decide_route` and `backlog_loop.py --init`, and by a planning hand-off |
| `refined` | bool | No | `true` when the item carries a chosen `## Resolution` with numbered steps, a `## Verification` recipe and no open question. Written only by `backlog-author`. Absent reads `false`. Read by `compute_item_shape` and `backlog_loop.py --init/--next` |

Read `id`, `blocks`, and `created` as text. A typed YAML load turns an unquoted zero-padded id into an octal integer.

A `refined` key that is absent reads `false`, so existing items need no migration.

The three `route_*` fields are optional and non-binding: an item without
them is valid and scores normally, and triage always runs its own gates
regardless of what a hint says.

**Migrating a hand-authored index.** An index that still uses the
pre-generation table shape -- one table, one footer line for the whole
changelog -- is hand-authored. `/planwise init`
detects that shape and defers it. Only `/planwise upgrade` migrates it: backfilling missing or partial
frontmatter, moving the changelog footer and dependency notes into their
own files, then regenerating and checking the index. An ambiguous
feature-cell sentence, one that only partly matches its item file, is
parked verbatim in the migration ledger, never appended and never refused.
`generate_backlog_index.py
--write` refuses to overwrite a hand-authored index until that migration
has run. Pass `--replace-legacy` to overwrite it directly instead, WITHOUT
a backup. An index the migration recognizes as neither hand-authored nor
generated is left untouched and reported through `migrate_backlog_index.py
--report`.

**Changelog layout.** The changelog lives in its own file, not in the
index footer.

- Part 1, `00-Changelog-Backlog.md`, is the file the hub links to.
- Later entries go to `00-Changelog-Backlog-Part-NN.md` files.
- Every file stays at or under the read budget.
- A grown changelog is re-split by `/planwise upgrade`, or directly by
  `migrate_backlog_index.py --split-changelog`.

---

## Scoring System

Items are ranked by a computed priority score using 8 weighted factors. All weights are configurable in `config.yaml` under the `scoring` section.

*Documentation of the `config.yaml` `scoring:` block's defaults, not a second source of truth — authoritative values live in the consumer's `config.yaml` `scoring:` block.*

### Scoring Factors

| # | Factor | Default Points | Source |
|---|--------|---------------|--------|
| 1 | Priority | High=30, Med=20, Low=10 | `config.yaml: scoring.priority_*` |
| 2 | Bug/Fix classification | +15 | `bug_fix_bonus`, applied when `abbrev == "BUG"`. Resolved from the item frontmatter's `abbrev:` field first, falling back to the index row's Domain cell when frontmatter carries none -- the title is never consulted |
| 3 | IN_PROGRESS boost | +10 | Index: Status column |
| 4 | File count | +5 per extra file (beyond 1) | Index: File column (last cell) -- the number of links in it |
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

# Mark an item as needing a planning session (status unchanged)
python {plugin_root}/scripts/update_backlog.py --id ID --mark-needs-plan

# Close an item whose criteria are already met, with its proof record
python {plugin_root}/scripts/update_backlog.py --id ID --status COMPLETE --resolution-file PATH

# Create a new backlog item (writes the BLI file from the template only; the
# caller regenerates the index with generate_backlog_index.py --write)
python {plugin_root}/scripts/update_backlog.py --create --id ID --feature FEATURE \
  --priority PRIORITY --abbrev ABBREV --files FILES [--status STATUS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--id ID` | Yes | Item ID (e.g., 002); in create mode, the new item's ID |
| `--status STATUS` | Update: Yes — Create: No | New status (NOT_STARTED, PLANNING, IN_PROGRESS, BLOCKED, COMPLETE, CLOSED). In `--create` mode it is optional and defaults to NOT_STARTED |
| `--create` | No | Create a new backlog item instead of updating an existing item's status |
| `--feature FEATURE` | Create only | Feature / recommendation summary, 120 characters or fewer once escaped for frontmatter storage — `--create` rejects a value that overflows the cap after escaping and writes nothing (required with `--create`) |
| `--priority PRIORITY` | Create only | Priority — High, Medium, or Low (required with `--create`) |
| `--abbrev ABBREV` | Create only | Domain abbreviation (required with `--create`) |
| `--files FILES` | Create only | Semicolon-separated (required with `--create`). The first entry is the new item file, written from `templates/backlog-item.md`. It must sit directly inside the backlog folder: give a bare file name, a path from the project root, or an absolute path. A path to any other folder is refused and nothing is written. The heading and the first Related link use the bare file name. Later entries are affected-file references and are listed under Related as given |
| `--mark-needs-plan` | No | Write `needs_plan: true` into the item's frontmatter without changing its status (the Route C marker-and-skip; regenerate the index afterwards) |
| `--resolution-file PATH` | No (with `--status COMPLETE` only) | After the status flip and the archive move, append the file's text under `## Resolution`; when `## Resolution` already exists, the file's text is appended below it as a dated `### Closed {date}` block; on an item already COMPLETE the append still runs |

**Automatic archival (COMPLETE/CLOSED):** Moves the item file to `{backlog_dir}/Archive/`. It never edits the index. The next `generate_backlog_index.py --write` renders the new link from the file's new location. `--mark-needs-plan` writes `needs_plan: true` without changing the status. `--status COMPLETE --resolution-file P` appends the file's text under `## Resolution` after the status flip and the archive move, and, when `## Resolution` already exists, appends the file's text below it as a dated `### Closed {date}` block.

### score_backlog.py

```bash
python {plugin_root}/scripts/score_backlog.py [OPTIONS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--dry-run` | No | Compute and print scores; every mode is report-only and never writes to the index |
| `--review` | No | Output a priority review report (no index writes) |
| `--id ID` | No | Look up one item's score by ID (bare or prefixed, matched on the numeric component) |
| `--explain` | No | With `--id`, print the per-factor score derivation instead of just the total |
| `--route` | No | Report the mechanical half of the triage routing signals and the provisional route for every open item; with `--id`, one item's full vector, keyword hit lines, and `route_hint` verdict. Report-only; with `--id`, also the `scoped_rules` block: the item's destinations, the rules whose `paths:` match each one, and the verdict `none`, `inject` or `placement` |
| `--json` | No | With `--route`, also write the report to a JSON temp file and print `JSON: {path}` on the last line |

`--route` applies the Decision Logic in `handlers/backlog.md` § Routing Decision Tree without modification; the handler's pseudocode is the source and the script follows it. It computes the eight mechanical signals from the index row and the item body it already loaded for scoring. It never runs the pivot check, the existence premise, citation freshness or staleness, which stay with the handler; it computes the scoped-rule gate from the item's destinations and the project's rule frontmatter (the `scoped_rules` block); it reports `HAS_CLEAR_FIX` as its mechanical half only, and never adopts a `route_hint:` -- it reports whether the hint agrees and whether `route_dated` predates the item's newest dated evidence line. A fresh, valid hint that differs from the computed route reports `undecided` when the hint's route is one that the reader's judgment of `IS_ARCHITECTURAL`, `HAS_MULTI_SPRINT` or the sufficiency half of `HAS_CLEAR_FIX` could reach, and `script wins` otherwise. `IS_ARCHITECTURAL` reads only the `## Proposed Solution` section when the item has one (the whole body otherwise), ignores a stem inside a file name, a multi-segment path, a snake_case identifier, an `**Evidence:**` line or a table row, and `--id` lists every ignored hit with its reason. `SUB_ITEMS` is the larger of the non-template `##` heading count and the longest consecutive numbered run.

With `--route`, the item vector also carries a `shape` block, computed by `compute_item_shape`. Its keys are:

- `refined`: the frontmatter flag (absent reads `false`).
- `needs_plan`: the frontmatter flag.
- `resolution_steps`: the longest consecutively numbered run (`1.`, `2.`, `3.` …) of column-0 steps under `## Resolution`. A restarted or lazily numbered list counts only its longest run, so `1. 1. 1.` reads 1 and two 4-step lists read 4. Write the steps as one consecutively numbered list.
- `has_verification`: whether `## Verification` holds a fenced command.
- `open_questions`: one of `absent`, `empty`, `unanswered` or `answered`.
- `shape_ok`: true when `refined` is true, `## Resolution` has at least one numbered step, `## Verification` exists with a fence, and `open_questions` is `absent` or `empty`.
- `missing`: the absent parts, joined with `"; "` on the shape line (`shape gate: FAIL -- missing: ...`).

The `--route` line for each item adds a `ref=y|n` column for `refined`.

The `open_questions` state reads the `## Open Questions` section. The reading stops at the first thematic break (`---`, `***` or `___` on its own line), so an item footer after the section is ignored. `None.`, a bare `None` (any case) or a blank body is `empty`. A `### Q` block without an `Answer:` line that carries text makes the state `unanswered`. When every block has one, the state is `answered`. A loop skip writes its question here as a `### Q{n}. Loop decision (run …)` block with an empty `Answer:` line (`backlog_loop.py --mark --decision`).

`has_verification` accepts a fence at any indent. `refined` and `needs_plan` read true for the YAML boolean and for the text `true`, `yes`, `on` or `y` in any case.

### backlog_loop.py

```bash
python {plugin_root}/scripts/backlog_loop.py --config {planwise_root}/config.yaml <SUBCOMMAND> [OPTIONS]
```

Run-state writer for `/planwise backlog` loop mode (see `handlers/backlog-Part-2-LoopMode.md`). Give exactly one subcommand. Every subcommand prints short human lines, then one final single-line JSON object.

| Subcommand | Arguments | Description |
|------------|-----------|-------------|
| `--init` | `--mode all\|specific\|n` `[--n N]` `[--refine-max N]` `[--items 004,009]` `[--priority P]` `[--abbrev A]` `[--status S]` `[--no-check]` `[--dry-run]` | Build the loop queue and write the run file. An item with `refined: false` selected by `--refine-max N` (default 0) or `--mode specific` is queued with disposition `refine`; an unrefined Route C item past the cap is excluded with `needs refine`. A `refined: true` Route C item, a `needs_plan: true` item, an item with a legacy `## Loop Decision Needed` section (`decision pending`), an item with the scoped-rule verdict `placement` and an item with unanswered `## Open Questions` go to `excluded` with their reasons (`plans deferred in loop mode` for a strong Route C signal). `--dry-run` prints the same report and writes no run file. An empty queue exits 1, prints an `error` JSON line, and writes no run file |
| `--next` | `--run <run-id>` | Pop the next still-selectable item into `current`. Prints `{"next": id, "remaining": N, "refined": bool, "disposition": "refine"|..., "run": ..., "state": ...}`, or `"next": null` on an empty queue (an item skipped as no longer selectable becomes `current`, so `--boundary` can still end the run). Exits 1 on an ended run |
| `--mark` | `--run <run-id> --id X` and `--phase selected\|acting\|verifying`, or `--outcome COMPLETE\|NOT_STARTED\|SKIPPED` `[--resolution-file P]` `[--route A\|B]` `[--note "..."]` `[--decision "..."]` `[--needs-plan]`, or `--lessons "LL-NNN,..."` | Record the item's phase, close it with an outcome, or record the lesson ids Phase 8 filed. A `SKIPPED` outcome restores the item's pre-loop status. `--decision` (SKIPPED only) also writes a `### Q{n}. Loop decision (run …)` block under the item's `## Open Questions` and flags the item `user_input_needed`. `--needs-plan` (SKIPPED only) also writes `needs_plan: true` into the item. `--resolution-file` (COMPLETE only) appends the file's text under `## Resolution` and records an unattended close; when the section exists, a dated `### Closed {date}` block is appended below it. `--decision` is capped at 1,200 characters, and a repeated call in the same run writes nothing. Without `--route`, `--outcome` records the item's `route_at_init`; an explicit `--route` wins, and `--needs-plan` leaves the route null. Exits 1 on an ended run |
| `--mark --refined` | `--run <run-id> --id X --refined REFINED\|QUESTIONS\|ALREADY_MET\|DECOMPOSE\|NEEDS_PLAN [--sub-items a,b]` | Record the refine outcome and append a `refine` history event. Stands alone: give no other `--mark` option with it |
| `--mark --check` | `--run <run-id> --id X --check "<command>" --exit <code>` | Record one `build_commands.verify` command's exit code in the item's `checks` list and append a `check` history event. Stands alone: give no other `--mark` option with it |
| `--boundary` | `--run <run-id>` | Print the end summary (only when remaining is 0), then the marker line, then a final JSON object with a `marker` field. Idempotent |
| `--end` | `--run <run-id>` | Set `ended` and print the cross-run summary table |
| `--status` | `[--run <run-id>]` | Alone: one run's record, or a listing of every run file. Combined with `--init`: a status filter for the queue |

The run id is the file stem `YYYYMMDD-HHMMSS`. An absolute path to the run file is accepted too.

The marker line is built from one constant and is not the last stdout line of `--boundary`:

```
BACKLOG LOOP: run=<run-id> done=<item-id> remaining=<N> state=<abs path>
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | ok |
| 1 | usage or config error |
| 2 | run file missing or unparseable. The file is never overwritten on this path |
| 3 | ambiguous resume: `current` carries no outcome, in any phase (none, `selected`, `acting`, `verifying`). `--next` writes nothing |

**Run file** (`{backlog_dir}/Backlog-Runs/{run-id}.json`):

```json
{
  "schema_version": 1,
  "run_id": "20261007-141502",
  "created": "2026-10-07T14:15:02-04:00",
  "ended": null,
  "mode": "n", "n": 2,
  "filters": {"priority": null, "abbrev": null, "status": null},
  "no_check": false,
  "excluded": [{"id": "012", "route": "C", "large_scope": true, "feature": "...", "reason": "plans deferred in loop mode"}],
  "queue": ["009"],
  "queue_meta": {"009": {"score": 31, "route_at_init": "A", "feature": "..."}},
  "known_ids_at_init": ["004", "009", "012"],
  "current": "004",
  "items": {
    "004": {"route_at_init": "A", "score": 31, "phase": "acting", "outcome": null,
            "route": null, "started": "2026-10-07T14:15:40-04:00", "closed": null, "note": null}
  },
  "history": [{"at": "2026-10-07T14:15:02-04:00", "event": "init", "id": null, "detail": "mode=n n=2 queue=2 excluded=1"}]
}
```

`queue` holds the ids not yet popped. `items` holds every id that was ever popped. `queue_meta` holds each queued item's score, initial route and feature. `known_ids_at_init` lists every item id present at init, so the end summary can name items filed during the run. `history` events are `init`, `next`, `mark`, `refine`, `boundary`, `end`. An item that was refined carries an `items.<id>.refine` record with `outcome`, `at` and `sub_items`.

`Backlog-Runs/` holds `.json` only; every reader globs `*.md` at the top level, so the folder is never an item.

---

## Status Flow

```
NOT_STARTED --[select in Phase 2]--> IN_PROGRESS
                                          |
   refined: false --> preflight, planner, author
        REFINED ------> re-route (the three routes below)
        QUESTIONS ----> wait for an Answer: line in ## Open Questions
        ALREADY_MET --> COMPLETE (close record appended under ## Resolution)
                                          |
                  +-----------------------+-----------------------+
                  |                       |                       |
                  v                       v                       v
            DIRECT FIX               TASK LIST              SESSION PLAN
            (Route A)                (Route B)              (Route C)
                  |                       |                       |
            +-----+                       |                       |
            |     |                       v                       v
   Approved v  Reverted v         All done --> COMPLETE    needs_plan: true
                                                                    --> /planwise plan --> PLANNING
         COMPLETE  NOT_STARTED                                      |
                                              /planwise run closeout, Master Plan
                                              COMPLETE, item listed in the Master
                                              Plan's `**Resolves:**` field
                                                                    v
                                                                COMPLETE
```

A `PLANNING` item is closed by `/planwise run` closeout (`handlers/run.md` Step 4.3), never by a backlog route. The Master Plan's `**Resolves:**` header field is what links the two.

In loop mode, an item whose acceptance criteria are already met goes `IN_PROGRESS → COMPLETE` with the proof record under `## Resolution`. When the item already holds a `## Resolution` section (the chosen approach and steps), the close writer appends a dated `### Closed {date}` block below it. The block records the proving command and output for each criterion, and the writer does not skip the item. A Route C re-assessment restores the pre-loop status and writes `needs_plan: true`.

---

## Error Handling

| Situation | Action |
|-----------|--------|
| `config.yaml` not found | Print "Project not initialized. Run `/planwise init` first." and STOP |
| Index file not found | Script exits with error; print path and STOP |
| Item ID not found | Print error; ask user to verify ID (bare and prefixed forms both match on the numeric component; verify the numeric id exists) |
| Item file not found | Warn user; skip scope analysis, ask for manual route |
| Fix agent returns BLOCKED | Report blocker to user; offer Route C (Session Planning) |
| Status update fails | Print error; continue to next item |
| No items match filter | Print "No items match filters." and STOP |
