# Task: GateOnVerificationReport

**Task ID:** VGL-FIX-S06-01-01
**Agent:** Sonnet
**Output:** `Outputs/VGL-FIX-S06-VerificationReport.md`

---

## Objective

Produce the sprint's verification report from the shipped template, then gate the
downstream chain on the report showing no failed criterion.

---

## Execution Steps

1. Fill `templates/verification-report.md` into `Outputs/VGL-FIX-S06-VerificationReport.md`.
2. Re-measure every criterion and record its verdict in the status cell.

---

## Verification Commands

> [!verify] Before / After Commands
> **Before:** *(runner)*
> ```bash
> ls templates/verification-report.md
> ```
> **After:** *(runner)*
> ```bash
> grep -c 'FAIL' Outputs/VGL-FIX-S06-VerificationReport.md   # expect 0 — no criterion failed
> # pre-edit: 3 → expect 0
> ```

---

## Success Criteria

- [ ] The report is generated from the template and no criterion failed
