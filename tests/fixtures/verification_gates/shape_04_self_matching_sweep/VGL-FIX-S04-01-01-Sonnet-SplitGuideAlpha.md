# Task: SplitGuideAlpha

**Task ID:** VGL-FIX-S04-01-01
**Agent:** Sonnet
**Output:** `guide-part-1.md`, `guide-part-2.md`, `guide-part-3.md` (NEW — the three split parts)

---

## Objective

Split the oversized guide into three parts. Each new part MUST open with a backlink
naming its source file and the section range it carries, so a reader landing on a
part can find the original.

---

## Execution Steps

1. Create the three part files listed in `Output:` above.
2. Give each part the required backlink line naming its source and section range.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls *.md
> ```
> **After:** *(runner)*
> ```bash
> grep -Ern 'guide-alpha\.md.*§(2|3|4)' . --include='*.md'   # expect 0 — no stale anchors remain anywhere in the tree
> # pre-edit: 3 → expect 0
> ```

---

## Success Criteria

- [ ] The three part files exist, each carrying its required backlink
- [ ] No stale anchors remain in the tree
