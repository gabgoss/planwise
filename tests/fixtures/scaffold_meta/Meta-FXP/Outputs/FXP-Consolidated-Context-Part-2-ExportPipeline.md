# FXP Consolidated Context Part 2: Export Pipeline

**Part:** 2 of 3
**Scope:** Export Pipeline Sprint
**Sources:** `FXP-META-S01-01-02-ExportSurvey.md` (Tier 1)
**Cross-references:** Reads the in-memory ledger from Part 1. Part 3 holds the decisions both sprints share.

---

## What This Enables

When this sprint is done, `pantry export` writes a filtered CSV of the ledger and returns the exit codes below. It depends on the Ledger Core sprint's load operation.

---

## 1. CSV Layout

Seven columns, in this order: `jar_id`, `label`, `shelf`, `slot`, `fill_pct`, `sealed_on`, `low_stock`. The header row is always written. `label` is quoted when it holds a comma. `low_stock` is `yes` when `fill_pct` is 20 or lower, otherwise `no`.

---

## 2. Filters

| Flag | Keeps |
|------|-------|
| `--shelf <letter>` | Rows on that shelf only |
| `--low-only` | Rows whose `low_stock` is `yes` |

Both flags together combine with AND.

---

## 3. Command and Exit Codes

`pantry export --out <path> [--shelf X] [--low-only] [--force]`

| Exit | Meaning |
|------|---------|
| 0 | CSV written |
| 1 | Filters matched no row. The header-only file is still written |
| 2 | Ledger unreadable, or `--out` exists without `--force` |

---

## 4. Suggested Work Breakdown

One session of three tasks:

1. Build the row mapper, including the derived `low_stock` column (Section 1).
2. Build the two filters (Section 2).
3. Build the `export` command, its overwrite guard and its exit codes (Section 3), with one test per exit code.

---

## 5. Write-Set

| Path | Task |
|------|------|
| `pantry/export_rows.py` | 1 |
| `pantry/export_filters.py` | 2 |
| `pantry/cli_export.py` | 3 |
| `tests/test_export.py` | 3 |

This write-set shares no path with Part 1's.
