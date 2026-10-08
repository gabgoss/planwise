# Task: HarvestAppendGate

**Task ID:** VGL-FIX-S12-01-01
**Agent:** Sonnet
**Output:** `plan.md`

---

## Objective

Append one Index Notes section to the plan, guarded by a pre-write check that the section is not already there.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> grep -c '## Index Notes' plan.md   # expect 0 before the harvest appends the section
> ```
> **After:** *(runner)*
> ```bash
> ls plan.md
> # pre-edit: 1 → invariant: 1
> ```

---

## Success Criteria

- [ ] Exactly one Index Notes section exists after the append
