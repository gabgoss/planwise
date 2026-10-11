---
description: A decision-row gate asserts the reason's value, because a fallback reason is a FAIL even when the resulting action matches the expected one, and an arm whose expected action equals the fallback action needs a positive proof of evaluation (§19); and an exit-code gate is derived from the script's return paths, never from design prose, gating on exit code plus status field plus coverage count together (§23).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Script Output Assertions (Grade What the Script Emitted)

**Purpose:** Two gates over what a script actually emitted. A row that exists and carries a reason can carry the reason that the logic never ran, and an exit code a design document calls a verdict can be the code a shipped script uses for a missing input. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** you write a grader over a decision log, or a gate, success criterion or handler branch interprets a script's exit code.

## Table of Contents

- [19. A Decision-Row Gate Asserts the Reason's Value, and a Fallback Reason Is a FAIL](#19-a-decision-row-gate-asserts-the-reasons-value-and-a-fallback-reason-is-a-fail)
- [23. Derive an Exit-Code Gate From the Script's Return Paths, Never From Design Prose](#23-derive-an-exit-code-gate-from-the-scripts-return-paths-never-from-design-prose)

---

## 19. A Decision-Row Gate Asserts the Reason's Value, and a Fallback Reason Is a FAIL

> [!constraint] Grade the reason a row carries, not the fact that it carries one
> A gate that asserts "the row exists and has a reason" passes on a row whose reason says the logic did not run. The predicate must assert the reason's value: the token the code emits when the decision table produced the row. Every fallback token is a failure of the run, whatever the action field says.
>
> A hook module decides at every layer boundary whether to compact, clear or do nothing. It reads the run's orchestration file and evaluates a seven-clause predicate. The observe arm's expected outcome is `none` at every boundary. A grader predicate counted `decide` rows against boundary lines (4 = 4) and checked that each row carried a `reason`. It reported PASS.
>
> Every row read `reason: "read-failed"`, `decision: null`, `action: "no decision (file read failed)"`. The module had stored `<plan-path>` with the `@` from the pasted `/command @<plan-path>`. The file read returned ENOENT at every boundary, so the predicate table never evaluated. The arm's `none` was the read-failure fallback. It matched the expected outcome because "do nothing" is what both the policy and the failure produce. A grading task caught it by reading the rows' contents. The same path bug would have hit every later arm whose policy needs the file.
>
> ```
> WRONG — count rows, check a reason is present, accept the action:
> decide rows = 4, boundary lines = 4, rows missing reason = 0   → PASS
> every row: reason="read-failed", decision=null, action="no decision"   # unread
> arm expected none, got "no decision" → grades as none                  # coincidence
>
> CORRECT — assert the reason's value; require an evaluated-path field:
> for row in decide_rows:
>     assert row["reason"] == "policy", f"fallback reason {row['reason']!r} at layer {row['layer']}"
>     assert row["true_context"] is not None      # written only by the evaluated path
> # read-failed at every boundary → FAIL: the predicate never evaluated; path bug
> ```
>
> Dry run on a scratch log of four rows that all read `reason: read-failed`. The row-count predicate printed PASS. The value predicate printed FAIL.

Three consequences:

- **Grade the reason, not the row.** The gate is `reason == <the value the logic emits>` on every row. `read-failed`, `parse-failed`, `no decision` and their kin are FAIL rows even when the resulting action is the expected one. Write the accepted value into the sheet's watch-for list and into the task file's success criterion.
- **An arm whose expected action equals the fallback action needs a positive proof of evaluation.** When "do nothing" is both the policy's answer and the failure's, require a field that only the evaluated path writes. Examples: the failing clause name, the measured context size, the layer number the answer named. Grade on its presence.
- **Fix path construction where the input enters, and test it with the input's real shape.** The `@` came from the user's own command syntax. A fixture path without the `@` cannot catch it. The test carries the `@`-prefixed spelling in both path separators.

**Sibling rule.** `gate-positive-and-mutation-controls.md` §3 requires a gate to run against its pinned content. This section is the row-shaped form: a gate that checks a decision was recorded must check the decision was made.

**Applies to** any grader over a decision log (hook modules, policy engines, rule evaluators). It applies to any arm, control or fixture whose expected outcome coincides with the failure outcome (`none`, `skip`, `no-op`). It applies to any path handling for user-typed reference syntax (`@path`, `~`, quotes).

## 23. Derive an Exit-Code Gate From the Script's Return Paths, Never From Design Prose

A gate on an exit code is a claim about the code's return paths. Derive it from those paths, never from a design document's description of them. Design prose assumes the diff-tool convention: 0 means clean and 1 means differences found. A shipped script may overload one code.

**Scenario.** A gate copied "exit 0 or 1 is a real verdict" from design prose. The script used exit 1 for "index not found". A deleted or mis-pathed index would have counted as a passing verdict. The observed return paths of that script:

| Exit | What the code prints |
|------|----------------------|
| 0 | `No drift detected. ...` **or** `Drift detected ({n} row(s) ...):` |
| 1 | `Error: <index> not found at {path}` |
| 2 | the legacy-shape error |
| 3 | `Drift audit could not run ...` or `Drift audit incomplete ...` |

Exit 0 carries two outcomes, and exit 1 carries none of the diff-tool meaning.

**How it surfaced.** A later task's brief said to quote the script's strings from the code, never from the design prose, and that the code wins. The task quoted the report function before it rewrote the handlers. The contradiction appeared at that quote. The quote step made the defect visible.

Three operative rules:

- **Quote before pinning.** Before writing "exit N means X" into a gate or a success criterion, search the script for each `return` and `sys.exit` path. Quote each message beside its code.
- **Gate on the outcome, not the code alone.** When the script emits a machine-readable status, gate on the exit code, the status field and the coverage count (`compared == total`) together. Exit codes get overloaded. A status field names the outcome.
- **Route the correction the moment it lands.** A later task's gate that rests on the refuted reading is an unresolved conditional branch. The orchestrator rewrites it as a binding spec delta at post-task time. The later runner does not rediscover it. The spec-delta mechanics are in [read-confirm-act-protocol.md](read-confirm-act-protocol.md).

> [!constraint] The gate names the observed outcome
> ```
> # WRONG — the gate inherits the convention from prose:
> <audit> --json  ->  exit 0 or 1 is a real verdict (never 3)
> # Result: a deleted or mis-pathed index (exit 1) counts as a passing verdict.
>
> # CORRECT — the gate names the observed outcome:
> <audit> --json  ->  exit 0 AND status == "ran" AND compared == total
> exit 1 (index missing), 2 (legacy shape), 3 (could not run / incomplete)  ->  FAIL
> ```

This section derives the gate before it is pinned. [verify-verdict-source.md](verify-verdict-source.md) § "8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result" classifies an exit that was already observed. The two are different questions.

**Applies to** any plan gate, success criterion or handler branch that interprets a script's exit code. It applies most to scripts that overload one code for several outcomes.

---

*Cross-references: [gate-run-sheet-and-grader-fields.md](gate-run-sheet-and-grader-fields.md) §14 (a grader fails a null numeric field) · [verify-verdict-source.md](verify-verdict-source.md) § "8. Classify Every Non-Zero Exit by Cause Before Treating It as a Bug or a Result" (an exit already observed) · [read-confirm-act-protocol.md](read-confirm-act-protocol.md) (the spec-delta mechanics a refuted reading is routed through) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
