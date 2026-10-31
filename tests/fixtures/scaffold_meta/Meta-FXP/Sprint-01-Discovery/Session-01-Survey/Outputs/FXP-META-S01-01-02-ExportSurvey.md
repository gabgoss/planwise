# FXP-META-S01-01-02 Export Survey

**Task:** FXP-META-S01-01-02
**Tier:** 1 (raw task output)
**Date:** 2026-10-31

---

## 1. CSV Columns

The export writes one CSV row per jar. The survey settled on seven columns, in this order.

| # | Column | Source | Notes |
|---|--------|--------|-------|
| 1 | `jar_id` | ledger | Verbatim |
| 2 | `label` | ledger | Quoted when it holds a comma |
| 3 | `shelf` | ledger | Verbatim |
| 4 | `slot` | ledger | Verbatim |
| 5 | `fill_pct` | ledger | Verbatim |
| 6 | `sealed_on` | ledger | Empty when unknown |
| 7 | `low_stock` | derived | `yes` when `fill_pct` is 20 or lower, else `no` |

The header row is always written, even for an empty ledger.

---

## 2. Filters

Two filters apply before rows are written.

1. `--shelf <letter>` keeps only one shelf.
2. `--low-only` keeps only rows whose `low_stock` is `yes`.

The two filters combine with AND. No other filter was requested.

---

## 3. Export Command

The command is `pantry export --out <path> [--shelf X] [--low-only]`. It refuses to overwrite an existing file unless `--force` is passed. It exits 0 on success, 1 on a filter that matched no row, and 2 on an unreadable ledger.

---

## 4. Open Observations

- Exit 1 for "no row matched" was debated. The survey kept it, because a script that pipes the export needs to tell an empty result from a full one.
- The sample pantry produced 9 low-stock rows out of 41 jars.
