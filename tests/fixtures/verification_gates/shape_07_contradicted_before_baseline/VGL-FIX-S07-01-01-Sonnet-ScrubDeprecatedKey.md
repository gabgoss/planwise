# Task: ScrubDeprecatedKey

**Task ID:** VGL-FIX-S07-01-01
**Agent:** Sonnet
**Output:** `references/legacy-notes.md`

---

## Objective

Remove every remaining mention of the superseded key so the reference documents only
the current scheme.

---

## Execution Steps

1. Open `references/legacy-notes.md`.
2. Remove the superseded-field section and the migration note that depends on it.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> grep -c 'DEPRECATED' references/legacy-notes.md   # baseline: 5 — the five mentions this task removes
> wc -l references/legacy-notes.md                  # baseline: 21 lines
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'DEPRECATED' references/legacy-notes.md   # expect 0 — every mention removed
> # pre-edit: 2 → expect 0
> ```

---

## Success Criteria

- [ ] No mention of the superseded key remains in `references/legacy-notes.md`
