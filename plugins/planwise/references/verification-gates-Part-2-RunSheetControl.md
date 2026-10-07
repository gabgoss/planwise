---
description: §13 — a run sheet pins the field the observed mechanism reads, not the flag whose name matches the sheet's intent. A flag nothing in the mechanism reads is documentation, not control. Trace each pinned flag to the line of the hook that reads it, give a mechanism whose default acts an off value before the sheet is written, and suspect the sheet's control before the operator when two operator-correct runs give the same wrong outcome. §14 — a grader that reads a numeric field from a module's log fails on null, because a null where a number belongs is a failed measurement and a "row present" predicate passes a row whose every numeric field is null.
paths: {planwise_root}/{plans_dir}/**
---

# Verification Gates, Part 2 — A Run Sheet Pins the Field the Hook Reads

**Purpose:** §13 and §14, split out of [verification-gates.md](verification-gates.md) when that file passed the Read-tool token warning. §1–§12 stay on that anchor, which keeps the original filename. Cite these sections as `verification-gates.md` §13 and §14 and read them here.

**Read this when** you write a run sheet, a probe driver or a test fixture that pins flags on a reset or launch line and then predicts behavior from them. Read it again when two clean runs of a sheet give the same wrong outcome. Read §14 when you write a grader predicate over a numeric field in a module's log.

## Table of Contents

- [13. A Run Sheet Pins the Field the Hook Reads](#13-a-run-sheet-pins-the-field-the-hook-reads)
- [14. A Grader Treats a Null Numeric Field as a Failed Measurement](#14-a-grader-treats-a-null-numeric-field-as-a-failed-measurement)

---

## 13. A Run Sheet Pins the Field the Hook Reads

> [!constraint] A sheet's control is the field the mechanism reads, not the flag whose name matches the intent
> A flag that nothing in the mechanism reads is documentation, not control. Every line on the sheet can run without error while the sheet's predicate stays unreachable.

**Scenario.** A run sheet described a typed sequence: `go`, wait for `STEP 1 COMPLETE`, type `/reload-plugins`, then `go`. Its predicate was a second `session.start` row between the two steps. That row would prove the module's own state survived a plugin reload.

The reset line pinned `--<mode-flag> chain`. The operator followed the sheet exactly. Step 2 ran inside the first `go` turn, before anything could be typed, and the reload landed after both steps.

The cause was two stores that two readers use:

- The reset's `--<mode-flag>` wrote `<composer-file>`. The handoff composer reads that file to add one sentence of instructions.
- The module's Stop hook reads a different field, `<field>`, from `<hook-store>`. That field's default was `feed`, which means: on every Stop, feed the next step into the same turn.
- Switching the reset to `--<mode-flag> manual` changed the sentence and nothing else. The reset offered `--<field-flag> stop|submit` and no way to turn the feed off.

Four attempts, three of them clean executions of a sheet whose control was not a control, cost 1.94 USD and about forty minutes. Then the module and the reset gained a `<field>: none` option.

> [!constraint] Trace each pinned flag to the hook line that reads it
> ```
> WRONG — the sheet pins a flag the composer reads, and the field the hook reads keeps its default:
> reset: --<mode-flag> manual --arm <module-store>        # <composer-file>: mode=manual
> hook:  <field> === 'feed' → feed step 2                 # <hook-store>: <field>=feed (default, unchanged)
> result: step 2 runs inside the step-1 turn; the typed reload lands after both steps
>
> CORRECT — the sheet pins the field the hook branches on, and that field has an off position:
> reset: --<mode-flag> manual --<field-flag> none --arm <module-store>   # <hook-store>: <field>=none
> hook:  <field> === 'none' → noted, no feed
> result: the reply stops at STEP 1 COMPLETE; the reload sits between the steps
> ```

**Three consequences.**

- **Trace each sheet flag to the code that reads it before you pin it.** For every flag on the reset line, search the hook for the field the flag writes. Confirm that the behavior the sheet needs is decided there.
- **A predicate that needs a pause needs an off switch, and the switch must exist before the sheet is written.** If the mechanism has no "do nothing" value, the sheet cannot pin one. The first run will show the mechanism doing its default thing.
- **When a clean run fails to produce the predicate, suspect the sheet's control before the operator or the module.** Two identical outcomes from two operator-correct runs is the signature. A third run of the same sheet measures nothing new.

**Review question.** For each pinned flag, ask: which line of the hook reads this, and what does the hook do when it is absent?

**Applies to** run sheets, probe drivers and test fixtures that pin flags on a reset or launch line and then predict behavior from them. It also applies to any mechanism with a default that acts, such as a hook that feeds, a timer that fires or a guard that blocks. The sheet must be able to name the value under which the mechanism does not act.

**Sibling rule.** `## 10. The Instrument's Four Proof Obligations` in the anchor file proves the instrument discriminates. This section proves the sheet's control reaches the mechanism. Both must hold before a run's outcome is evidence.

---

## 14. A Grader Treats a Null Numeric Field as a Failed Measurement

> [!constraint] A grader that reads a numeric field fails on `null`, the way it fails on a missing row
> A `null` where a number belongs is a failed measurement, not a missing one. A "row present" predicate passes a row whose every numeric field is `null`.

A module's log wrote one row per timed span. Arithmetic on an unresolved Promise had made every `span_ms` value `NaN`, which JSON writes as `null`. The grader's predicate asked only whether a `span_close` row existed. Every run graded PASS while every timing field held `null`. [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) § "A Declared API Drifts Between Builds: Regenerate the Declarations and Type-Check on Every Build Change" carries the cause.

> [!constraint] The predicate names the type of the field, not only the row
> ```
> WRONG:   predicate "span_close row exists"  -> PASS   (the row has "span_ms": null)
> CORRECT: predicate "span_close row exists AND span_ms is a number >= 0"
>          span_ms is null -> FAIL "timing field unmeasured"
> ```

Three rules follow.

1. **Grade the field, not the row.** Name the type and the range of every numeric field the predicate reads. A `null`, a string or a negative value is a FAIL.
2. **Record the failure beside every cost row.** When a run's timing fields are `null`, the arm table says so next to each cost row. A cost row with no usable timing data is not a zero.
3. **Run the dry-run pair.** Run the predicate once against a row with a number and once against a row with `null`. The two results MUST differ. A predicate that returns PASS on both has never been shown to discriminate. `## 10. The Instrument's Four Proof Obligations` in the anchor file states the general form.

**Applies to** any grader, assertion or report that reads a numeric field from a log, a store or a result file. Cross-reference: `## 6. Build-Fresh ≠ Deploy-Fresh` in the anchor file covers a build that is fresh while the deployed copy is not. This section covers the run that graded PASS on a build whose measurements were never taken.
