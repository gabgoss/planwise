# Task: DesignCoverageGate

**Task ID:** VGL-FIX-S10-01-01
**Agent:** Sonnet
**Output:** `design.md`

---

## Objective

Extend the design note so that it covers the six required intersection clauses, and gate on the coverage.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls design.md
> ```
> **After:** *(runner)*
> ```bash
> grep -ci 'intersection' design.md
> # pre-edit: 1 → expect >= 2
> ```

---

## Success Criteria

- [ ] The design note covers all six intersection clauses
