# Verification Report Template

Use this template when writing the output of a verification pass — a review's evidence report, a sprint's own verification writeup, or any artifact whose job is to state whether a set of checks passed or failed. It defines the convention every downstream gate should rely on: a single machine-readable verdict line plus per-criterion status cells, so a consumer never has to invent an ad-hoc substring search over free prose.

---

## Why This Convention Exists

A verification report necessarily *describes* the checks it ran — which means its own column headers, legend, and residual prose legitimately contain words like `PASS` and `FAIL`. A downstream gate that greps the report for a bare token cannot tell the difference between "the report is discussing the word FAIL" and "a criterion actually failed." A report that correctly documents zero failures can still contain the substring `FAIL` several times over — in a table header, in a legend explaining the column, in a sentence like "no criteria failed." A gate built on a bare substring count therefore halts a downstream chain on a report that in fact PASSED.

The fix is structural, not lexical: put the verdict somewhere a consumer can match unambiguously, and never rely on a bare token search of the whole document.

> [!constraint] Read the Verdict Line or the Row Pattern — Never a Bare Substring
> WRONG — a gate that counts occurrences of the token anywhere in the report, including its own headers and legend:
> ```bash
> grep -c 'FAIL' {report}.md   # expects 0 for a passing report
> ```
> This fails on a genuinely passing report the moment the report's own column header, legend, or a sentence like "0 criteria failed" contains the word — the report's own vocabulary satisfies the gate's forbidden pattern even though nothing actually failed.
>
> CORRECT — match the machine-readable verdict line, or the dedicated status cell pattern, never free prose:
> ```bash
> grep -c '^\*\*Verdict:\*\* PASS$' {report}.md   # expect exactly 1 on a passing report
> grep -cE '\| *FAIL *\|' {report}.md              # expect 0 failing rows on a passing report
> ```

---

## Required Elements

### 1. Trailing Verdict Line

The report MUST end with a single machine-readable verdict line, appearing **exactly once** per report, as the last substantive line of the document:

```markdown
**Verdict:** PASS
```

or

```markdown
**Verdict:** FAIL
```

No other line in the report may use this exact `**Verdict:** {PASS|FAIL}` form. A downstream gate matches this line directly rather than scanning the document for the word `PASS` or `FAIL` in isolation.

### 2. Per-Criterion Status Cell

Every criterion the report evaluates gets one row in a criteria table, with its result carried in a **dedicated table cell** — never inline in prose. This lets a consumer match the `| FAIL |` cell pattern specifically, rather than a bare token that could appear anywhere in the row's description text.

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | {criterion 1 description} | {command/anchor/observation that verifies it} | PASS |
| 2 | {criterion 2 description} | {command/anchor/observation that verifies it} | FAIL |
| 3 | {criterion 3 description} | {command/anchor/observation that verifies it} | PASS |

A consumer scanning for failures matches the row pattern `| *FAIL *|`, which only fires on an actual status cell — never on the word appearing in a criterion's description or evidence text.

### 3. No Bare Substring Gates Downstream

Any script, task file, or gate that consumes this report MUST read the trailing verdict line or the per-row status cell pattern described above. It MUST NOT run a bare substring search (`grep -c 'FAIL' {report}`) against the whole document, because the report's own required vocabulary — its column header (`Status`), its legend, and any prose explaining the convention itself — legitimately contains the token being searched for. A bare substring gate is satisfied by the report's own scaffolding regardless of the actual result, which is precisely the failure this template exists to prevent.

---

## Copyable Skeleton

```markdown
# Verification Report: {subject}

**Date:** {YYYY-MM-DD}
**Scope:** {what was verified}

---

## Criteria

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | {criterion 1} | {evidence} | PASS |
| 2 | {criterion 2} | {evidence} | PASS |
| 3 | {criterion 3} | {evidence} | FAIL |

---

## Notes

{Free-form notes on any FAIL rows: what failed, what remediation is needed.}

---

**Verdict:** FAIL
```

---

## Naming Convention

**Pattern:** `{Report-Name}.md`, placed in the producing task's or session's `Outputs/` directory (or the location its own spec names).

**When to use:** any artifact whose purpose is to state a PASS/FAIL result for a set of checks — a review's evidence report, a sprint's own dogfooded verification writeup, or a standalone verification pass over a batch of gates.
