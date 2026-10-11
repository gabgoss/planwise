# Task: AutoModeTagGate

**Task ID:** VGL-FIX-S14-01-01
**Agent:** Sonnet
**Output:** `handlers/review.md`

---

## Objective

Tag every interactive prompt in the handler with its auto-mode behaviour, and gate on no untagged prompt remaining.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls handlers/review.md
> ```
> **After:** *(runner)*
> ```bash
> grep -B1 'AskUserQuestion' handlers/review.md | grep -c 'AUTO-MODE:'
> # pre-edit: 33 → expect 34
> ```

---

## Success Criteria

- [ ] Every AskUserQuestion call carries an AUTO-MODE tag
