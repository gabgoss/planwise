# FXP Consolidated Context Part 1: Ledger Core

**Part:** 1 of 3
**Scope:** Ledger Core Sprint
**Sources:** `FXP-META-S01-01-01-LedgerSurvey.md` (Tier 1)
**Cross-references:** Part 2 reads the ledger this part builds. Part 3 holds the decisions both sprints share.

---

## What This Enables

When this sprint is done, the ledger loads, changes and saves jar records with every rule below enforced. Part 2's export reads the in-memory ledger this sprint builds, so this sprint runs first.

---

## 1. Record Model

A jar record has six fields: `jar_id`, `label`, `shelf`, `slot`, `fill_pct` and `sealed_on`. Only `sealed_on` is optional.

| Field | Rule |
|-------|------|
| `jar_id` | `J-{shelf}{slot}` with the slot zero-padded to two digits, for example `J-B07` |
| `label` | 1 to 40 characters |
| `shelf` | One letter, `A` to `F` |
| `slot` | `1` to `12` |
| `fill_pct` | `0` to `100` in steps of 5. A non-step value rounds down on load, with a warning |
| `sealed_on` | ISO date, or empty |

---

## 2. Ledger File

The ledger is `pantry.ledger`, UTF-8, one record per line. Fields are tab-separated `key=value` pairs. `#` starts a comment line. Blank lines are ignored. Save writes records sorted by shelf, then slot, and keeps no comments.

---

## 3. Operations

| Operation | Rule | Error case |
|-----------|------|------------|
| load | Parse every line | Duplicate `jar_id`: report the line number |
| add | Place a jar in an empty slot | Occupied slot |
| move | Move a jar to an empty slot and recompute `jar_id` | Occupied target slot |
| refill | Set `fill_pct` only | Value outside `0` to `100` |
| save | Write the sorted ledger | none |

---

## 4. Suggested Work Breakdown

One session of three tasks:

1. Build the record model and its validation (Section 1).
2. Build the ledger file reader and writer (Section 2).
3. Build the four mutating operations and their error cases (Section 3), with one test per error case.

---

## 5. Write-Set

| Path | Task |
|------|------|
| `pantry/record.py` | 1 |
| `pantry/ledger_io.py` | 2 |
| `pantry/operations.py` | 3 |
| `tests/test_ledger.py` | 3 |
