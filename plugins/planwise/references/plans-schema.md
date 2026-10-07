---
description: The plans index's generated contract — the six columns, the enumeration rule, the status definitions and normalization, the one-writer rule, the Index Notes convention for harvested prose, and the one-file budget. Every consumer of the generated plans index defers here.
---

# Plans Schema

The plans index (`{plans_dir}/00-Index-Plans.md`, or the name `project.index_files.plans` gives) is a regenerated build artifact. Each plan's Master Plan states its own status, created date and last-updated date, and nothing is ever hand-edited into the index. This reference documents what `scripts/generate_plans_index.py` actually produces, read from the shipped script. The single read path is `scripts/parse_plans.py`.

## Index Format

The index is one file. It holds a title, a `Generated:` line, a one-line intro, one table, and a generated `## Status Legend` section. The intro line reads:

```
> Generated from each plan's Master Plan by generate_plans_index.py. Edit the Master Plan's **Status:** line, then run the generator.
```

The table has six columns, in this order:

```
| Abbrev | Name | Status | Created | Last Updated | Path |
```

| Column | Value |
|--------|-------|
| `Abbrev` | The Master Plan's filename prefix: the filename with `-META-Master-Plan.md` removed, else with `-Master-Plan.md` removed |
| `Name` | The top-level plan folder, plus ` (Meta / Discovery)` under a `Meta-` folder and ` (Exec)` under an `Exec-` folder |
| `Status` | The normalized leading token of the Master Plan's `**Status:**` line and nothing else (see Status Normalization) |
| `Created` | The first `**Created:** YYYY-MM-DD` in the Master Plan, or `-` when the field is missing |
| `Last Updated` | The first date on the last line that starts `*Last Updated:`, else the first date on the `**Last Updated:**` header line, or `-` when both are missing |
| `Path` | The Master Plan's directory relative to `plans_dir`, with POSIX separators and a trailing `/` |

Every cell is escaped, so a pipe in a value cannot split a row. The `Generated:` line carries the date of the last write. The check masks it, so a date change alone is never drift.

The `## Status Legend` section is rendered from `plan_statuses:` in `config.yaml`. It lists each configured status in list order, with its meaning from the table under Status Definitions.

## Enumeration Rule

The generator finds Master Plans by a depth-bounded walk of `plans_dir`. It reads the disk and never reads a previous index.

- **Depth 1:** `{Plan}/{Abbrev}-Master-Plan.md`.
- **Depth 2:** `{Plan}/{Meta-* or Exec-*}/{Abbrev}-Master-Plan.md`, or the `-META-` variant `{Plan}/{Meta-* or Exec-*}/{Abbrev}-META-Master-Plan.md`. A depth-2 folder whose name starts with neither prefix is ignored.
- **Any other depth is ignored.** A nested test fixture or a copied plan tree deeper down never becomes a row.
- **The `-META-` filename is accepted at depth 2 only.** At depth 1 a `-META-Master-Plan.md` file is not a Master Plan.

Each Master Plan file is one row. Two Master Plan files in one directory give two rows with one Path, and the generator reports a `duplicate-row` anomaly. Rows sort by (Created, Path), with a missing Created last, so a second run over an unchanged tree is byte-identical.

## Status Definitions

The value list is declared in `config.yaml` as `plan_statuses:` (beside `statuses:` and `lesson_statuses:`). When the key is absent, the config loader supplies the ten shipped values below as the default. This table defines what each shipped value means. The generator holds the same meanings in `PLAN_STATUS_MEANINGS`, and a test pins the two to each other.

| Status | Meaning |
|--------|---------|
| `NOT_STARTED` | Plan created but no work begun |
| `PLANNING` | Discovery or session planning in progress |
| `READY_TO_EXECUTE` | Plan files authored; ready for `/planwise run` |
| `REVIEWED` | Reviewed by `/planwise review`; no verdict recorded yet |
| `APPROVED` | Review verdict: validated for execution |
| `NEEDS_FIXES` | Review verdict: findings to fix before execution |
| `IN_PROGRESS` | Active execution underway |
| `BLOCKED` | Waiting on external dependency |
| `COMPLETE` | All sprints and sessions finished |
| `CLOSED` | Archived — no further work expected |

A project may add its own values to `plan_statuses:`. The generated legend lists an added value with the meaning `(project-defined)`. A Master Plan status that is not in `plan_statuses:` is an `unknown-status` anomaly.

## Status Normalization

`parse_plans.normalize_status` reduces a raw `**Status:**` value to the token the Status column holds. It works in three steps:

1. Strip the leading characters that are not letters or digits (an emoji, `*`, `_`, spaces).
2. Take the leading run that starts with a capital letter and continues with capitals, digits and underscores. The run must end at a character that is not a letter, a digit or an underscore. Punctuation after the run (`COMPLETE.`, or the `(` in `COMPLETE (2026-09-01)`) is outside the run and drops.
3. Drop trailing underscores from the run.

A run that a lowercase letter follows is no token. So `Complete` and `ON_hold` yield no token, and a project value may carry digits (`ON_HOLD2`). A value that yields no token renders as its raw first word, with `*` and `_` stripped from its ends, and the generator reports an `unknown-status` anomaly. A Master Plan with no `**Status:**` line renders `-` and gives a `missing-status` anomaly.

Both anomalies are tree anomalies, not drift. `--write` still writes the file, then exits 1. `--check` exits 1.

## The One-Writer Rule

The index is never hand-edited. To change a plan's row, a handler edits the Master Plan's `**Status:**` line and its footer date, then runs the generator:

```
python {plugin_root}/scripts/generate_plans_index.py --config {planwise_root}/config.yaml --write
```

Nothing edits a row by hand. The check compares each cell with a fresh render, so a hand-written free-form Name or Status is drift, and the next `--write` replaces it. A row whose Master Plan no longer exists on disk is an `orphan-row` finding, and `--write` drops it.

`--dry-run` (the default when no mode flag is given) renders and reports without writing. It reads the file on disk only to name its shape and never compares it with the render. `--check` compares the file on disk with a fresh render. `--json` prints the report as JSON. Exit codes:

| Exit | Meaning |
|------|---------|
| 0 | Clean. `--check`: the file equals the render, and the tree has no anomaly. `--write`: the file was written or already current, and the tree has no anomaly. `--dry-run`: the render has no anomaly and is within budget. Only `--check` compares with the file on disk |
| 1 | `--check` found drift, an over-budget render or a tree anomaly. `--dry-run` found a tree anomaly or an over-budget render. `--write` **wrote the file** and the tree has an anomaly |
| 2 | Refused. `--check` found a hand-authored (legacy-shaped) index and did not compare it; or `--write` met a legacy-shaped index without `--replace-legacy`, or a render over budget |

An exit 1 from `--write` is not a failed write. The file on disk is current, and the exit code reports the tree anomaly the write rendered around. `reconcile_plans.py --write` passes the same exit code through: it can print `Reconciled {N} row(s).` and still exit 1.

The legacy message points at `/planwise upgrade`. `--replace-legacy` lets `--write` overwrite a hand-authored index and lists the hand-written content it drops. The read-side audit that compares an index with the Master Plans is described in [index-drift-audit.md](index-drift-audit.md).

## Index Notes Convention

Prose that lived in the old hand-authored index (a comment, or narrative in a Status cell) moves into the Master Plan it describes. It is appended at the end of the Master Plan file, under a heading of this form:

```
## Index Notes (harvested YYYY-MM-DD)
```

The heading is followed by this banner, quoted exactly as `migrate_plans_index.py` writes it:

```
> [!note] Historical notes moved from the plans index on YYYY-MM-DD, each attached to the row it followed in the index. They record what was true when written; this Master Plan's **Status:** line is authoritative.
```

Each note is copied byte-exact. One italic line precedes it and names the index file and line it came from, in the form `*From 00-Index-Plans.md line N (KIND).*`. KIND is `HTML comment` or `Status cell text after the leading token`. The index file name in the label is the project's own configured index name. The banner says the notes are history: the `**Status:**` line stays the only authority for status.

Notes attach by position, never by content. A comment goes to the Master Plan of the nearest table row that precedes it in the index. A Status-cell narrative goes to its own row's Master Plan. A note with no preceding row, or whose row has no Master Plan on disk, stays in the migration ledger under `## Unattributed Index Notes`. The migrator never edits a `**Status:**` line. When a row's status token differs from its Master Plan's, the Master Plan wins and the ledger lists the row under `## Status Changes`.

An index harvested by hand before the migrator existed carries the shorter banner, without the words "each attached to the row it followed in the index". Both forms are valid history. Neither is rewritten.

The Last Updated reader takes the last line that starts `*Last Updated:`. An append after the footer therefore does not move the Last Updated column, unless a note line itself starts with that label.

## Budget

The index is one file and is never split into shards. The budget is 12,500 tokens. The generator measures the file that ships (title, `Generated:` line, table and legend) as UTF-8 bytes plus one byte per line, on the CRLF worst case, at 2.6 bytes per token.

- `--write` refuses a render over budget. It exits 2, writes nothing, and names the bytes, the tokens and the budget.
- `--check` reports an `over-budget` finding and exits 1.
- `--json` reports the byte and token counts, the budget, and `page_cap_ratio`.

A refusal is the signal to shard or shorten the index. The generator does not shard.
