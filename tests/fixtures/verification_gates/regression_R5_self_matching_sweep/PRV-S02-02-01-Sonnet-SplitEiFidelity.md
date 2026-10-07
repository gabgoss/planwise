# Task: SplitEiFidelity

**Task ID:** PRV-S02-02-01
**Agent:** Sonnet
**Output:** `plugins/planwise/references/ei-fidelity-Part-1-SourcePreservation.md`, `plugins/planwise/references/ei-fidelity-Part-2-Thresholds.md`, `plugins/planwise/references/ei-fidelity-Part-3-UnconfirmedCaveats.md`, `plugins/planwise/references/ei-fidelity-Part-4-CrossTierReconciliation.md` (NEW — the split parts)

---

## Objective

Split the oversized fidelity reference into parts. Every new part is REQUIRED to
carry a backlink naming its anchor file and its section range on one line, so a
reader landing on a part can find the original.

---

## Execution Steps

1. Create the part files listed in `Output:` above.
2. Give each part the required one-line backlink naming its anchor and section range.
3. Repoint the surviving cross-references.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls plugins/planwise/references/
> ```
> **After:** *(runner)*
> ```bash
> grep -En 'ei-fidelity\.md.*§(5|6|7|8|9|10|11)' plugins/planwise/ -r --include='*.md'   # 0
> ```

---

## Success Criteria

- [ ] Every part file exists and carries its required backlink
- [ ] No stale section anchor remains anywhere in the shipped tree
