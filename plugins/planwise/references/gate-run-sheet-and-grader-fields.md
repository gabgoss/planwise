---
description: A run sheet pins the field the observed mechanism reads, not the flag whose name matches the sheet's intent — a flag nothing reads is documentation, not control (§13); and a grader that reads a numeric field from a module's log fails on null, because a null where a number belongs is a failed measurement and a "row present" predicate passes a row whose every numeric field is null (§14); a driver or grader never defaults a missing input to 0, because an absent transcript, log or result file is a failed measurement (§14); a gate row a person runs names every valid mode and records the mode that ran, because a row that pins one mode makes a correct run disagree with its ledger (§15).
consult-when: Writing a run sheet or probe driver that pins flags, or a grader over a numeric log field — pin the field the hook reads, not the flag whose name matches the intent (§13); a null numeric field is a failed measurement (§14); a driver or grader never defaults a missing input to 0 (§14); a gate row a person runs accepts every valid mode and records the mode that ran (§15)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Run-Sheet Control and Grader Fields

**Purpose:** Three rules about the join between a sheet or grader and the mechanism it claims to control or measure. Every line of a sheet can run without error while its predicate stays unreachable, and every run can grade PASS while every measurement is unmeasured. A row a person runs can also pin one mode of a multi-mode run, so a correct run disagrees with its ledger. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** you write a run sheet, a probe driver or a test fixture that pins flags on a reset or launch line, two clean runs of a sheet give the same wrong outcome, or you write a grader predicate over a numeric field in a log or a driver that counts from a transcript or result file. Read it also when you write a gate row that a person runs in one of several valid modes.

## Table of Contents

- [13. A Run Sheet Pins the Field the Hook Reads](#13-a-run-sheet-pins-the-field-the-hook-reads)
- [14. A Grader Treats a Null Numeric Field as a Failed Measurement](#14-a-grader-treats-a-null-numeric-field-as-a-failed-measurement)
- [15. A Human Gate Row Accepts Every Valid Mode and Records the One That Ran](#15-a-human-gate-row-accepts-every-valid-mode-and-records-the-one-that-ran)

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

**Sibling rule.** [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 proves the instrument discriminates. This section proves the sheet's control reaches the mechanism. Both must hold before a run's outcome is evidence.

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

Four rules follow.

1. **Grade the field, not the row.** Name the type and the range of every numeric field the predicate reads. A `null`, a string or a negative value is a FAIL.
2. **Record the failure beside every cost row.** When a run's timing fields are `null`, the arm table says so next to each cost row. A cost row with no usable timing data is not a zero.
3. **Run the dry-run pair.** Run the predicate once against a row with a number and once against a row with `null`. The two results MUST differ. A predicate that returns PASS on both has never been shown to discriminate. [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) §10 states the general form.
4. **Never default a missing input to 0.** A driver or grader that cannot find its transcript, log or result file exits non-zero and names the path. An absent input is a failed measurement, and a default turns it into a count of zero.

A missing input fails closed. A driver counted the main-agent calls in a transcript and defaulted a missing count to 0. A "0 main calls" result then passed on a run that had no transcript at all.

```
WRONG:   count = data.get("main_calls", 0)      # or: n=${n:-0}
         assert count == 0                       -> PASS   (no transcript existed)
CORRECT: if not os.path.exists(path): sys.exit("input missing: " + path)
         count = data["main_calls"]              -> KeyError is a FAIL, not a zero
         n=$(wc -l < "$path") || { echo "input missing: $path"; exit 1; }
```

**Applies to** any grader, assertion or report that reads a numeric field from a log, a store or a result file. Cross-reference: [gate-runtime-boundary-evidence.md](gate-runtime-boundary-evidence.md) §6 covers a build that is fresh while the deployed copy is not. This section covers the run that graded PASS on a build whose measurements were never taken.

#### Reviewer Check 102 — Driver or Grader Defaults a Missing Input to 0

- **Severity / Role / Type:** ERROR (HIGH confidence) | Verification-Gate Reviewer | NEW
- **What:** A driver, grader or gate in the plan MUST NOT turn an absent input (transcript, log, result file or field) into the number 0.
- **Detection:** Use Grep over the plan's drivers, graders and gates for `.get(…, 0)`, `or 0`, `:-0`, `|| 0`, `|| echo 0`, and `2>/dev/null` placed before a count. Flag each hit where an absent input can reach the zero and the zero can satisfy the predicate. A hit that first asserts the input exists is not flagged.
- **Finding template:**
```
[ERROR] Driver or grader defaults a missing input to 0
File: {plan or task file path} | Location: {gate or grader line}
Issue: "{expression}" turns a missing {input} into 0, so a run with no {input} can pass
Fix: Exit non-zero with "input missing: {path}" before reading the value, per references/gate-run-sheet-and-grader-fields.md §14 | Confidence: HIGH
```

## 15. A Human Gate Row Accepts Every Valid Mode and Records the One That Ran

> [!constraint] A gate row a person runs names every valid mode, not the one its author expected
> A row that pins one mode of a multi-mode run predicts what the operator will do. The operator runs the committed default, the evidence no longer matches the row, and the ledger needs hand reconciliation.

**Scenario.** A backfill gate row told the operator to run three notebooks with `SOURCE_MODE="local"` and to paste each summary into the ledger. The operator ran the committed defaults, where `SOURCE_MODE` is `"download"`, the nightly path. The summaries went into chat. Seven of 55 partitions were skipped on resume, so each ledger held 48 rows. Throughput was bound by the download, not by the local read.

The data was correct. Three things still needed hand reconciliation at the next preflight: the mode that ran, the place the summaries were pasted and the row count.

> [!constraint] The row names every valid mode, and the run records which one ran
> ```
> WRONG — the row pins one mode and one paste location, and the verifying task counts ledger rows:
> row:       run the three notebooks with SOURCE_MODE="local"; paste each summary into the ledger
> verifier:  expect 55 ledger rows per notebook; compute throughput from the ledger
>
> CORRECT — the row accepts every valid mode and records the one that ran:
> row:       run the three notebooks with SOURCE_MODE="local" or SOURCE_MODE="download"
>            record the mode that ran, the date and the resume-skipped partitions
>            paste each summary into the ledger or into chat
> ledger:    one row per partition, with a source-of-marker column
> preflight: accepts either paste location and writes the canonical ledger copy itself
> verifier:  take denominators from the rows that carry seconds; verify by query against the store
> ```

Five rules follow.

1. **Name every valid mode on the row.** List each value the run accepts. Pin one mode only when the others are invalid for this gate, and say so on the row.
2. **Record what ran.** The row holds the mode that ran, the date and the resume-skipped units. A reader can then tell what the evidence covers.
3. **Give the ledger one row per unit and a source-of-marker column.** The column records where each row's completion marker came from, such as this run or an earlier resumed pass.
4. **Accept either paste location.** The next preflight reads the ledger or the chat paste and writes the canonical copy itself. The operator does not own that reconciliation.
5. **Take denominators from measured rows, and verify by query.** Count only the rows that carry a measured value, such as seconds. A resume-skipped unit has none. Query the store for the result. The ledger row count records what was pasted, not what exists.

**Applies to** any gate row, run sheet or checklist step that a person runs, where the run has more than one valid mode or more than one place to record its result.

**Sibling rule.** Section 13 pins the field the hook reads. This section keeps the row from pinning a mode the operator may reasonably not run.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the dry-run pair every predicate owes) · [gate-script-output-assertions.md](gate-script-output-assertions.md) (§19 and §23, grading a decision row's reason and a script's exit code) · [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) (a declared API that drifts between builds) · [verification-gates.md](verification-gates.md) (the family index).*
