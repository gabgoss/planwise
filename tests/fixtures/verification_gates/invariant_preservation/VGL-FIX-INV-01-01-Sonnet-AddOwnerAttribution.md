# Task: AddOwnerAttribution

**Task ID:** VGL-FIX-INV-01-01
**Agent:** Sonnet
**Output:** `templates/task-file.md`

---

## Objective

Add the owner-attribution constraint to the task-file template's Verification
Commands section, **without disturbing** the baseline-scoping constraint that
already lives there. The three `_BASE` mentions that carry the baseline-scoping
rule must survive this edit untouched.

---

## Execution Steps

1. Add the owner-attribution constraint block to the Verification Commands section.
2. Leave the existing baseline-scoping constraint byte-for-byte intact.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l templates/task-file.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'Names Its Owner' templates/task-file.md   # expect >=1 — the constraint this task adds
> # pre-edit: 0 → expect >=1
> grep -c '_BASE' templates/task-file.md   # the baseline-scoping rule must survive this edit unchanged
> # pre-edit: 3 → invariant: 3 (this count must NOT move — a revert drops it, a duplicate raises it)
> ```

---

## Success Criteria

- [ ] The owner-attribution constraint is present
- [ ] The baseline-scoping constraint's three `_BASE` mentions are preserved unchanged
