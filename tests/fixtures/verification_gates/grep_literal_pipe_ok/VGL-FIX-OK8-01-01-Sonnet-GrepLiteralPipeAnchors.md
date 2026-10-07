# VGL-FIX-OK8-01-01 — Grep Literal Pipe Anchors

**Model:** Sonnet
**Output:** `Outputs/VGL-FIX-OK8-Anchors.md`

## Gate Rows

Every call below is correct for the native `Grep` tool, so none may draw a finding. This fixture is the false-positive guard for the escaped-pipe check. A check that fires here would also fire on every call that is already right.

| Row | Call | Why it is correct |
|-----|------|-------------------|
| 1 | `Grep  pattern='^\| 1[12] '  path='references/agent-orchestration.md'` | A literal pipe anchors a markdown table row. |
| 2 | `Grep  pattern='\| Check \|'  path='references/review-classification.md'` | Whitespace sits beside each escaped pipe, so both match literal pipes. |

## Steps

Alternation written as a bare pipe, in a fenced block:

```
Grep  pattern='transfer_review|review:'  path='scripts/doctor_cli.py'
```

A counter-example is not a gate, and a line marked WRONG is skipped:

WRONG — `Grep  pattern='alpha\|beta'  path='scripts/doctor_cli.py'`
