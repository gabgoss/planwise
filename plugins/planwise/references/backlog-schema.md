---
description: Backlog Schema Reference for /planwise backlog -- the backlog index table format, backlog item file naming and frontmatter, the 8-factor priority scoring system, script command-line interfaces, the status state machine, and error handling. Loaded on demand; the 8-phase triage pipeline itself stays in handlers/backlog.md.
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

Every generated file -- the hub, any hub overflow leaf, and every Archive
shard -- is kept under a **22,000-token budget**. The generator *enforces*
this rather than merely reporting it: at `--write` time, a table that would
exceed the budget is split further before anything is written (the hub into
numbered overflow leaves, a shard century into more than one shard file), so
a file that would breach the budget is never produced in the first place.
`--check` reports a budget breach found on disk as drift. Links are
bidirectional: the hub's `## Shards` directory lists every Archive shard and
every hub overflow leaf, and each of those backlinks to the hub.

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

The three `route_*` fields are optional and non-binding: an item without
them is valid and scores normally, and triage always runs its own gates
regardless of what a hint says.

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
| `--files FILES` | Create only | Affected files, semicolon-separated; the first is written as the new BLI file from `templates/backlog-item.md` (required with `--create`) |

**Automatic archival (COMPLETE/CLOSED):** Moves the item file to `{backlog_dir}/Archive/`. It never edits the index. The next `generate_backlog_index.py --write` renders the new link from the file's new location.

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

### cleanup_backlog.py

```bash
python {plugin_root}/scripts/cleanup_backlog.py --target {index|archive|both}
```

**`--target index`'s row-stripping is obsolete under generation, and nothing
in the plugin invokes this script automatically.** It was written for a
hand-maintained index that only ever grew. `generate_backlog_index.py` makes
that redundant by construction: a closed item's row lands in its Archive
shard the moment `--write` runs, never in the hub, so there is nothing left
to strip.

> [!antipattern] Never wire `--target archive` to anything automatic
> `--target archive` (and `--target both`) `unlink()`s every `*.md` file
> under `Archive/`, with no confirmation and no undo. This is a standing
> hazard independent of the index-cleanup question above — keep it a
> manual, human-invoked operation.

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
| Item ID not found | Print error; ask user to verify ID (bare and prefixed forms both match on the numeric component; verify the numeric id exists) |
| Item file not found | Warn user; skip scope analysis, ask for manual route |
| Fix agent returns BLOCKED | Report blocker to user; offer Route C (Session Planning) |
| Status update fails | Print error; continue to next item |
| No items match filter | Print "No items match filters." and STOP |
