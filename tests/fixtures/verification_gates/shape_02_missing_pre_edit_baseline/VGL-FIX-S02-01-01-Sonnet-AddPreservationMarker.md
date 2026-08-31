# Task: AddPreservationMarker

**Task ID:** VGL-FIX-S02-01-01
**Agent:** Sonnet
**Output:** `references/verification-task-authoring.md`

---

## Objective

Add the preservation-marker rule to §10 of the authoring reference, so a gate that
must not move can be marked and exempted.

---

## Execution Steps

1. Open `references/verification-task-authoring.md`.
2. Add the preservation-marker subsection to §10.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> wc -l references/verification-task-authoring.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'invariant:' references/verification-task-authoring.md   # expect >=1 (the marker the task introduces)
> ```

---

## Success Criteria

- [ ] §10 carries the preservation-marker rule
