# VGL-FIX-S08-01-01 — Landing Gate Grep Rows

**Model:** Sonnet
**Output:** `Outputs/VGL-FIX-S08-LandingGate.md`

## Gate Rows

The landing gate names the native `Grep` tool. The row 7 call is reproduced verbatim from a real task file. A backslash before the pipe was copied from the table-cell escape, so ripgrep reads it as a literal pipe and the call matches nothing.

| Row | Check | Call | Expect |
|-----|-------|------|--------|
| 7 | Doctor transfer review wiring | `Grep  pattern='transfer_review\|review:'  path='scripts/doctor_cli.py'` | at least 1 hit |

## Steps

Run the second call from a fenced block. The same escape is wrong here, because nothing in a fenced block needs a table escape.

```
Grep  pattern='STATUS_NOW_UPSTREAM\|now-upstream'  path='scripts/doctor_cli.py'
```

## Placeholder Row

A template slot in the output cell must not hide the defect in the call cell. This row is reproduced verbatim from a finished plan's probe table. Its output cell carries `{plans-dir}` style slots.

| # | Probe | Output | Expected |
|---|-------|--------|----------|
| 3 | `Grep pattern='plans_dir\|backlog_dir\|lessons_dir' path='plugins/planwise/config.yaml.template'` | `9:   plans_dir: "{plans-dir}"`; `10:   backlog_dir: "{backlog-dir}"` | all three |
