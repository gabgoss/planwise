# Task: ExactSentenceGate

**Task ID:** VGL-FIX-S09-01-01
**Agent:** Sonnet
**Output:** `Outputs/deliverable.md`

---

## Objective

Write the deliverable so that its closing line is the exact required sentence, then gate on that sentence being present byte-for-byte.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls Outputs
> ```
> **After:** *(runner)*
> ```bash
> grep -c '^The exact required sentence\.$' Outputs/deliverable.md
> # pre-edit: 0 → expect 1
> ```

---

## Success Criteria

- [ ] The deliverable ends with the exact required sentence
