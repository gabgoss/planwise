# Task: RepointReviewerAnchors

**Task ID:** PRV-S01-01-06
**Agent:** Sonnet
**Output:** `agents/plan-reviewer.md`

---

## Objective

Remove every anchor in the plan-reviewer agent that cites the required-file
reference by section number, so the agent anchors by symbol instead.

---

## Execution Steps

1. Open `agents/plan-reviewer.md`.
2. Replace each numbered §-anchor with a symbol-based reference.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l agents/plan-reviewer.md
> ```
> **After:** *(runner)*
> ```bash
> grep -rn 'session-plan-requirements\.md.*§(9\|10)' agents/plan-reviewer.md   # expect 0
> ```

---

## Success Criteria

- [ ] No numbered §-anchor to the required-file reference remains
