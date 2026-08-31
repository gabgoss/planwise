# Task: CiteCanonicalBudgetReference

**Task ID:** PRV-S02-01-03
**Agent:** Sonnet
**Output:** `references/task-content-fidelity.md`

---

## Objective

Add a citation to the canonical budget reference in §9.A.8.

---

## Execution Steps

1. Open `references/task-content-fidelity.md`.
2. Add the canonical citation to §9.A.8, preserving §9.A.7 and §10 verbatim.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l references/task-content-fidelity.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'session-context-budget' references/task-content-fidelity.md   # ≥1 (§9.A.8 cites the canonical)
> # line 210 (§9.A.7, not modified) and line 283 (text the task preserves verbatim)
> ```

---

## Success Criteria

- [ ] §9.A.8 cites the canonical budget reference
