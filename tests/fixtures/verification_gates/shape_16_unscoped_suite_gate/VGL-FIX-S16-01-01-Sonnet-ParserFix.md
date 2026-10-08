# Task: ParserFix

**Task ID:** VGL-FIX-S16-01-01
**Agent:** Sonnet
**Output:** `scripts/parser.py`

---

## Objective

Fix the parser's handling of a zero-padded identifier, and prove it with the parser's own tests.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls scripts/parser.py
> ```
> **After:** *(runner)*
> ```bash
> python -m pytest -q
> # pre-edit: 2590 passed → expect >= 2591 passed
> ```

---

## Success Criteria

- [ ] The parser test for the zero-padded identifier passes
