# Task: LimitConstantGate

**Task ID:** VGL-FIX-S13-01-01
**Agent:** Sonnet
**Output:** `config/limits.md`

---

## Objective

Record the 40000-byte limit exactly once in the config notes.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls config
> ```
> **After:** *(runner)*
> ```bash
> grep -rn '40000' config/
> # pre-edit: 0 → expect 1
> ```

---

## Success Criteria

- [ ] The limit appears exactly once
