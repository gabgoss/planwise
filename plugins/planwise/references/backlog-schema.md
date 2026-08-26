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

| Column | Type | Description |
|--------|------|-------------|
| ID | 3-digit zero-padded (001-999) | Unique backlog item number; both bare (`002`) and prefixed (`PFX-002`) ID-cell forms are accepted, matched on the numeric component (leading zeros and any alpha prefix are ignored) — a new row's written form follows the index's predominant existing form, or an explicit `id_format` config key (`"prefixed" \| "bare"`) |
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
| `SB` | Sub-backlog number; split when the file approaches the one-read token budget (~22K measured tokens) | `01`, `02` |
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

*Documentation of the `config.yaml` `scoring:` block's defaults, not a second source of truth — authoritative values live in the consumer's `config.yaml` `scoring:` block.*

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

Run when the index approaches the one-read token budget (~22K measured tokens — check with `measure_files.py`) to remove COMPLETE/CLOSED rows. `--target archive` deletes archived files; `--target both` does both operations.

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
