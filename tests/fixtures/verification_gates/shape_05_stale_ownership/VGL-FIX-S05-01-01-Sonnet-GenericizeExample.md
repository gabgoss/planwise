# Task: GenericizeExample

**Task ID:** VGL-FIX-S05-01-01
**Agent:** Sonnet
**Output:** `guides/guide-alpha.md`, `guides/guide-beta.md`

---

## Objective

Genericize the illustrative example in §8.1 so it no longer names a sibling guide
with a hardcoded line count, and relocate §8 to its new owner per the Sprint Plan.

---

## Execution Steps

1. Rewrite the §8.1 illustrative example to anchor by symbol, not by line count.
2. Relocate §8 to `guides/guide-beta.md` per the Sprint Plan's routing table.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l guides/guide-alpha.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'hardcoded line count' guides/guide-alpha.md   # §8.1 illustrative example no longer names a sibling with a hardcoded line count — expect 0
> # pre-edit: 1 → expect 0
> ```

---

## Success Criteria

- [ ] `guides/guide-alpha.md` §8.1 no longer names a sibling reference with a hardcoded line count
