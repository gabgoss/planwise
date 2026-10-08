# Task: SeverityTagGate

**Task ID:** VGL-FIX-S15-01-01
**Agent:** Sonnet
**Output:** `report.md`

---

## Objective

Verify that every check block in the consolidated report carries a severity tag.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls report.md
> ```
> **After:** *(runner)*
> ```bash
> grep -cE '^\[(BLOCKER|ERROR|WARNING|INFO)\]' report.md
> # pre-edit: 3 → expect >= 54
> ```

---

## Success Criteria

- [ ] Every check block carries a severity tag
