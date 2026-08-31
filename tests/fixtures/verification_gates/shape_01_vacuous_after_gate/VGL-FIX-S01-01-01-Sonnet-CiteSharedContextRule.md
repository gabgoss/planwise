# Task: CiteSharedContextRule

**Task ID:** VGL-FIX-S01-01-01
**Agent:** Sonnet
**Output:** `references/task-content-fidelity.md`

---

## Objective

Add a cross-reference to the shared-context rule in §9.A.8 of the fidelity reference.

---

## Execution Steps

1. Open `references/task-content-fidelity.md`.
2. Add the canonical cross-reference to the shared-context rule.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l references/task-content-fidelity.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'shared-context' references/task-content-fidelity.md   # expect >=1 (the new cross-reference)
> # pre-edit: 2 → expect >=1
> ```

---

## Success Criteria

- [ ] The cross-reference to the shared-context rule is present
