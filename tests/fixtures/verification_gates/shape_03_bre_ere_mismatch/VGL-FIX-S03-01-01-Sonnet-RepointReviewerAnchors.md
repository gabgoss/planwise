# Task: RepointReviewerAnchors

**Task ID:** VGL-FIX-S03-01-01
**Agent:** Sonnet
**Output:** `agents/plan-reviewer.md`, `references/skill-authoring.md`

---

## Objective

Repoint the reviewer's §-anchors and normalize the skill-authoring tag forms.

---

## Execution Steps

1. Repoint both `session-plan-requirements.md` anchors in `agents/plan-reviewer.md`.
2. Add the third `AUTO-MODE` tag mention to `references/skill-authoring.md`.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l agents/plan-reviewer.md
> ```
> **After:** *(runner)*
> ```bash
> grep -rn 'session-plan-requirements\.md.*§(9\|10)' agents/plan-reviewer.md   # expect 2 (both anchors present)
> # pre-edit: 0 → expect 2
> grep -c 'AUTO-MODE' references/skill-authoring.md   # expect 3 (the three tag mentions)
> # pre-edit: 2 → expect 3
> ```

---

## Success Criteria

- [ ] Both `session-plan-requirements.md` §-anchors resolve
- [ ] Three `AUTO-MODE` tag mentions are present
