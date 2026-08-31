# Task: SummarizeTagForms

**Task ID:** PRV-S02-01-06
**Agent:** Sonnet
**Output:** `references/skill-authoring.md`

---

## Objective

Add a summary of the two invocation tag forms to the skill-authoring reference.

---

## Execution Steps

1. Open `references/skill-authoring.md`.
2. Add the tag-form summary, keeping both spellings.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l references/skill-authoring.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'AUTO-MODE' references/skill-authoring.md   # ≥2 (summary keeps both tag forms)
> ```

---

## Success Criteria

- [ ] The summary names both tag forms
