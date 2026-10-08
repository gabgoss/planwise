# Task: SnapshotGate

**Task ID:** VGL-FIX-S11-01-01
**Agent:** Sonnet
**Output:** `Outputs/VGL-FIX-S11-Summary.md`

---

## Objective

Gate the downstream task on the capture snapshot having passed its own gate.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> grep -c 'Gate: PASS' Outputs/snapshot.md   # expect 1 — the capture passed
> ```
> **After:** *(runner)*
> ```bash
> ls Outputs/VGL-FIX-S11-Summary.md
> # pre-edit: 0 → expect 1
> ```

---

## Success Criteria

- [ ] The summary exists and the snapshot gate read PASS
