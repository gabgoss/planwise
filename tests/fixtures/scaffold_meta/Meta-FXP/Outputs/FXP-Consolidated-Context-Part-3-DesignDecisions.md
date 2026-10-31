# FXP Consolidated Context Part 3: Design Decisions

**Part:** 3 of 3
**Scope:** Cross-sprint reference
**Sources:** `FXP-META-S01-01-01-LedgerSurvey.md`, `FXP-META-S01-01-02-ExportSurvey.md` (Tier 1)
**Cross-references:** Decisions 1 and 2 apply to Part 1. Decisions 2 and 3 apply to Part 2.

---

## What This Enables

This part is not a sprint. Each sprint's Execution Input extracts the decisions it needs.

---

## Decision 1: Round Down a Non-Step Fill Value

**Applies to:** Ledger Core Sprint.

A `fill_pct` that is not a step of 5 rounds down on load, and the loader logs one warning per jar. Rejecting the value was considered. It was dropped, because two sample jars held `33` and a hand-edited ledger should still load.

---

## Decision 2: Standard Library Only

**Applies to:** both sprints.

The tool uses the Python standard library only. The ledger reader uses plain string splitting. The export uses the `csv` module. No third-party package is added.

---

## Decision 3: Exit 1 Means No Row Matched

**Applies to:** Export Pipeline Sprint.

The export exits 1 when its filters match no row, and it still writes the header-only file. A caller that pipes the export can then tell an empty result from a full one without reading the file.

---

## Sprint Ordering

Ledger Core runs before Export Pipeline, because the export reads the ledger's load operation. The two sprints' write-sets share no path, but the code dependency alone orders them.
