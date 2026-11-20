---
description: A run sheet pins the field the observed mechanism reads, not the flag whose name matches the sheet's intent — a flag nothing reads is documentation, not control (§13); and a grader that reads a numeric field from a module's log fails on null, because a null where a number belongs is a failed measurement and a "row present" predicate passes a row whose every numeric field is null (§14); a driver or grader never defaults a missing input to 0, because an absent transcript, log or result file is a failed measurement (§14); a gate row a person runs names every valid mode and records the mode that ran, because a row that pins one mode makes a correct run disagree with its ledger (§15); a grader, census rule or verdict rule that a task file restates from a design is checked clause by clause against that design, a census exempt list proves each entry at the base and is re-read after any corrective, and every arm or verdict rule carries a finished-the-job gate (§16).
consult-when: Writing a run sheet or probe driver that pins flags, or a grader over a numeric log field — pin the field the hook reads, not the flag whose name matches the intent (§13); a null numeric field is a failed measurement (§14); a driver or grader never defaults a missing input to 0 (§14); a gate row a person runs accepts every valid mode and records the mode that ran (§15); restating a design's Expect, a census rule or an arm verdict rule as a task-file gate — check each added clause against the design, prove a kept-whole class at the base and re-read exempt sections after a corrective, give every arm rule a finished-the-job gate (§16)
paths: {planwise_root}/{plans_dir}/**
---

# Gate Run-Sheet Control and Grader Fields

**Purpose:** Four rules about the join between a sheet or grader and the mechanism it claims to control or measure. Every line of a sheet can run without error while its predicate stays unreachable, and every run can grade PASS while every measurement is unmeasured. A row a person runs can also pin one mode of a multi-mode run, so a correct run disagrees with its ledger. A grader, census rule or verdict rule restated from a design can also be stricter or looser than the design, so a task file fails correct work or passes a run that stopped early. Split from `verification-gates.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gates.md §N` citation translates by filename alone. The family index is `verification-gates.md`.

**Read this when** you write a run sheet, a probe driver or a test fixture that pins flags on a reset or launch line, two clean runs of a sheet give the same wrong outcome, or you write a grader predicate over a numeric field in a log or a driver that counts from a transcript or result file. Read it also when you write a gate row that a person runs in one of several valid modes. Read it also when a task file restates a design's Expect, a census rule with an exempt list, or an arm's verdict rule as a gate.

## Table of Contents

- [13. A Run Sheet Pins the Field the Hook Reads](#13-a-run-sheet-pins-the-field-the-hook-reads)
- [14. A Grader Treats a Null Numeric Field as a Failed Measurement](#14-a-grader-treats-a-null-numeric-field-as-a-failed-measurement)
- [15. A Human Gate Row Accepts Every Valid Mode and Records the One That Ran](#15-a-human-gate-row-accepts-every-valid-mode-and-records-the-one-that-ran)
- [16. A Grader, Census Rule or Verdict Rule Restated From a Design Is Checked Against That Design](#16-a-grader-census-rule-or-verdict-rule-restated-from-a-design-is-checked-against-that-design)

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

### Reviewer Check 102 — Driver or Grader Defaults a Missing Input to 0

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

## 16. A Grader, Census Rule or Verdict Rule Restated From a Design Is Checked Against That Design

> [!constraint] Each clause a task file adds when it restates a design's expected outcome is a new claim
> A task file that turns a design's Expect column, census rule or verdict rule into a gate can be stricter than the design, looser than it, or in conflict with a brief beside it. A stricter gate fails correct work. A looser gate passes a run that did not do the job. Check each clause against the design and against the subject's designed behavior before the run.

Four shapes recur.

### 16.1 A Grader Adds Clauses the Subject Contradicts by Design

**Scenario.** A design gave one matrix row a three-clause Expect: a single fallback line naming the working folder, a reply that reports it, and no auto-init. The task's grader restated it as "the reply contains the fallback marker and the folder string, and the run made 0 tool uses". Both added clauses were wrong:

- The skill tells the model to Read a handler when the fallback line is present, so 1 tool use is the designed behavior.
- The model reports the fallback in its own words, so the literal marker never reaches the reply.

The row graded FAIL. A recompute from the raw evidence against the design's three clauses gave PASS. That row decided the plan's verdict. Under the task's grader the verdict would have been INCONCLUSIVE.

> [!constraint] Grade each design clause where its evidence lives
> ```python
> # WRONG — the restated grader adds clauses the subject contradicts by design:
> # design: "fallback line naming the folder; reply reports it; no auto-init"
> ok = "<FALLBACK_MARKER>:" in result and folder in result and tool_uses == 0
>
> # CORRECT — one predicate per design clause, each read from its own evidence:
> ok = (fallback_line and folder in fallback_line          # the injected line names the folder
>       and folder_reported_in(result)                     # the reply reports it
>       and set(tool_names) <= {"Read"} and not writes)    # no auto-init; the routed Read is allowed
> ```

Three rules follow.

1. **Check each added clause against the subject's own behavior before the run.** A clause the design does not state is a new claim, and it needs its own evidence.
2. **When a row fails, recompute the verdict against the design from the raw evidence.** Do this before you decide whether the defect is in the subject or in the grader.
3. **A grader fix re-grades the existing capture.** It is never a re-run that hunts for a pass. Record the clause that changed.

### 16.2 A Per-Section Census Rule Needs a Class for a Section a Brief Keeps Whole

**Scenario.** One census rule spanned files with three dispositions: compress, collapse and keep. It said each rule section holds exactly one labelled WRONG, unless the section is on a closed exempt list of five classes. Several sections fit none of the five. They held 0 labelled WRONG at the base, and their brief said "keep this section whole; do not add a pair". As written, the sweep would grade each of them FAIL on correct work. The rule and the briefs contradicted each other, and no runner could resolve that.

> [!constraint] Give the census a kept-whole class, and prove each entry at the base
> ```
> WRONG — the rule demands one WRONG everywhere, and the brief forbids adding one:
> rule:  every rule section holds exactly 1 labelled WRONG (closed exempt list of 5)
> brief: keep §6 whole; do not add a pair
> sweep: §6 reads 0/0 -> FAIL on correct work
>
> CORRECT — a kept-whole class with a census proof taken at the base:
> class 6 kept-whole: the brief keeps the section intact AND it read 0 labelled WRONG at <base>
> proof: git -C <repo> show <base>:<path> > <scratch>/<file>; census <scratch>/<file> -> "0 0  ### §6 ..."
> FAIL only when a section held a pair at <base> and has fewer now, with no pointer-only or dedupe record
> ```

- **Add the class whenever one structural rule spans files with different dispositions.** A brief that keeps a section untouched makes "every section holds X" false for that section.
- **Prove each entry against the base, not against the runner's word.**
- **Decide the class before dispatch.** A scaffold census line such as `headings=5 wrong=0` in a keep file is the signal.

### 16.3 A Corrective to an Exempt Section Re-Opens Its Exemption

**Scenario.** A task rewrote one section as an introduction, so it could claim the exempt class "a parent whose body only introduces its sub-sections". The rewrite dropped the section's general rule. The orchestrator caught the loss and sent a corrective: put the rule back in the intro sentence, and keep the section an introduction. Those two instructions cannot both hold, because a section that states a rule is not an introduction. The census still read 0/0 with the exemption claimed, because it counts labels and cannot read meaning. The sweep found the conflict only because its brief told it to read each exempt parent's body.

> [!constraint] Restore the rule and re-classify the section
> ```
> WRONG — restore the rule and keep the exemption:
> corrective: add the general claim to the §9 intro, keep it an introduction
> census:     0/0, exempt (c)          # the count cannot see the rule
>
> CORRECT — the restored rule voids the class, so the section takes its own pair:
> §9 now states a rule -> exempt class (c) no longer fits
> add its one labelled pair -> 1/1, no exemption needed
> ```

- **After any corrective to an exempt section, re-read the section's body against its exempt class.** An exemption is a claim about content, so an edit to the content re-opens it.
- **A count gate cannot check an exemption's premise.** Name a body read of each exempt section in the sweep's brief. Take the exempt list from outside the runner's Output.
- **Check a corrective's own wording before you send it.** Two instructions that cannot both hold are a defect in the corrective.
- **A rewrite that fits a section to an exempt class is a warning sign.** The class should describe the section, not the reverse.

### 16.4 An Effort-Only Verdict Rule Rewards a Run That Stops Early

**Scenario.** An arm matrix graded each arm by "every run below 58 main-session tool uses". One arm's runs made 24, 29 and 15 tool uses, and the verdict draft read PASS. The orchestrator then read each run's final result text. Only the first run built the deliverable. The second used its budget and stopped before the build. The third stopped BLOCKED and wrote nothing, and its 15 tool uses were the arm's lowest because it gave up.

> [!constraint] A run counts only if it finished its arm's job, and the verdict reports both
> ```
> WRONG — the rule counts effort only:
> PASS if every run < 58 main-session tool uses      # 24/29/15 -> PASS, 1 of 3 built
>
> CORRECT — a finished-the-job gate comes first, and the verdict reports both counts:
> finished = build exit 0 and gates pass (inline, workflow arms) | bodies filled, 0 FILL markers (delegated arm)
> PASS if every run finished AND every run < 58      # 1 of 3 finished -> NOT CONFIRMED
> ```

- **Every arm rule and every verdict rule carries a finished-the-job gate.** An efficiency metric is defined only over runs that did the job. Without an outcome gate, the cheapest way to pass is to stop.
- **Define "finished" per arm when the arms' jobs differ in scope.** An arm that only hands work to a subagent scores low by construction.
- **Read the end state from the run's own record.** Use the final result text and the build exit code, not the runner's summary.

**Review question.** For each clause of a grader, census rule or verdict rule in a task file, ask: which design clause does this restate, what does the subject do there by design, and can a run that did not finish the job satisfy it?

**Applies to** eval suites, headless matrices, probe sheets, structural census sweeps with a closed exempt list, and any benchmark that grades by tool uses, tokens, cost or wall time. It applies most when one row or one rule decides the plan's verdict.

**Sibling rules.** [gate-verdict-contract-and-adjudication.md](gate-verdict-contract-and-adjudication.md) §6 adjudicates a heuristic BLOCKER against source before routing rework. This section checks the grader itself against the design it restates. [gate-satisfiability.md](gate-satisfiability.md) "Pair the residue clause with an exempt-set count" keeps an exempt set from emptying silently. §16.2 and §16.3 keep each exempt class true of the sections it holds.

---

*Cross-references: [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the dry-run pair every predicate owes) · [gate-script-output-assertions.md](gate-script-output-assertions.md) (§19 and §23, grading a decision row's reason and a script's exit code) · [verify-against-shipped-artifact.md](verify-against-shipped-artifact.md) (a declared API that drifts between builds) · [verification-gates.md](verification-gates.md) (the family index).*
