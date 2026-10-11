# Task: ScopedParserFix

**Task ID:** VGL-FIX-OK3-01-01
**Agent:** Sonnet
**Output:** `scripts/parser.py`

---

## Objective

Fix the parser's handling of a zero-padded identifier, and prove it with the parser's own test module. The gate is scoped to that module, and the one context-window reading is not counted.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> grep -B1 'AskUserQuestion' handlers/review.md   # the lines around each call, read by eye, never counted
> ```
> **After:** *(runner)*
> ```bash
> python -m pytest -q tests/test_parser.py
> # pre-edit: 41 passed → expect 43 passed
> ```

---

## Success Criteria

- [ ] The parser test for the zero-padded identifier passes
