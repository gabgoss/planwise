# Task: WellFormedShapes

**Task ID:** VGL-FIX-OK2-01-01
**Agent:** Sonnet
**Output:** `Outputs/VGL-FIX-OK2-Summary.md`

---

## Objective

Six Before-block readings whose shapes are each the correct form of a shape Checks 9 to 15 flag. None of them may raise a finding.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> grep -cE '^## Index Notes' plan.md   # 1 today — the heading, anchored at the line start
> grep -c 'Index Notes harvested' plan.md   # 3 today — a two-word phrase, not a single term
> grep -cF '**Gate:** PASS' Outputs/snapshot.md   # 0 today — the bytes copied from the skeleton; the snapshot reads HALT
> grep -rnE '(^|[^0-9])40000([^0-9]|$)' config/   # 1 today — digit boundaries guarded
> grep -c 'intersection' design.md   # 1 today — a count, not a coverage threshold
> grep -cE '^\[(BLOCKER|ERROR)\]' report.md   # 2 today — a count, not a threshold
> grep -c 'sentence\.\r\?$' notes.md   # 0 today — the carriage-return guard is present
> ```
> **After:** *(runner)*
> ```bash
> ls Outputs/VGL-FIX-OK2-Summary.md
> # pre-edit: 0 → expect 1
> ```

---

## Success Criteria

- [ ] The summary exists
