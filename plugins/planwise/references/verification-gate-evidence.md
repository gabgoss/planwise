---
description: What a verification gate's output is evidence of — positive and mutation controls, the correct-post-state arm, specifying the artifact the PASS branch must leave behind, which side is the defect when a gate and correct work disagree, why a gate that fails everything is a suspect until its dry-run pair differs, and how to write and classify the old-home citation sweep that follows a reference split. Consult before citing any guard, linter, hook, or MUST-be-empty check as proof, when your correct edit and a gate's expected value disagree, when a gate returns FAIL on every input, and when you author the exit criterion for a citation sweep after moving a section.
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Gate Evidence (Proving the Instrument Before Citing It)

**Purpose:** Rules for the gap between *"the gate returned this"* and *"this is true"*. A gate's output becomes evidence only after the gate has been exercised in the direction that carries information, over an input set that could have contained the defect. This file governs the exercising; [`verification-task-authoring.md`](verification-task-authoring.md) governs the match pattern, and [`verification-gates.md`](verification-gates.md) §10 governs the instrument's four proof obligations. §10-§13 govern the other direction: the instrument is already in play and disagrees with correct work anyway. They fix which side yields, what the runner reports, what the orchestrator re-derives, and what a dispatcher pre-classifies. §14 binds the comparison between a dry-run pair's two arms: a gate that fails everything has not been shown to discriminate any more than one that passes everything. §15 applies the whole file to one recurring gate, the old-home citation sweep that follows a reference split.

**Read this when** you author a guard, hook, linter, validation pass, or "MUST be empty" check, and again when you are about to cite one of them as proof that work is correct. Read §10-§13 when your correct edit and a gate's annotated value disagree, when a runner reports that it shaped content to satisfy a gate, or when you dispatch an authoring task whose content is a live gate's subject. Read §14 when a gate returns FAIL on every input it was given. Read §15 before writing the exit criterion for a citation sweep after moving a section between files.

## Table of Contents

- [1. A Gate-Shaped Deliverable Requires a Positive Control](#1-a-gate-shaped-deliverable-requires-a-positive-control)
- [2. A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing](#2-a-test-whose-subject-is-a-refusal-must-be-proven-load-bearing)
- [3. Dry-Run Every MUST-be-N Gate in BOTH Directions](#3-dry-run-every-must-be-n-gate-in-both-directions)
- [4. Specify the Artifact for the PASS Branch, Not Just the FAIL Branch](#4-specify-the-artifact-for-the-pass-branch-not-just-the-fail-branch)
- [5. A Fixture Must Not Be Built Through the API Under Test](#5-a-fixture-must-not-be-built-through-the-api-under-test)
- [6. A Known-Good Probe Must Name a Real Target — and Both Halves the SAME One](#6-a-known-good-probe-must-name-a-real-target--and-both-halves-the-same-one)
- [7. A Fixture Set Must Span Input SHAPES, Not Only Families](#7-a-fixture-set-must-span-input-shapes-not-only-families)
- [8. Report What the Proof Does NOT Cover, in the Same Breath as the Result](#8-report-what-the-proof-does-not-cover-in-the-same-breath-as-the-result)
- [9. Verify Completeness Against the Spec's Enumeration, Never Against the Artifact](#9-verify-completeness-against-the-specs-enumeration-never-against-the-artifact)
- [10. The Artifact Is Authoritative; the Instrument Is the Defect](#10-the-artifact-is-authoritative-the-instrument-is-the-defect)
- [11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It](#11-a-gate-annotation-predicts-the-shape-of-correct-work--it-never-constrains-it)
- [12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger](#12-a-disclosure-that-a-gate-influenced-the-artifact-is-a-re-derivation-trigger)
- [13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch](#13-pre-adjudicate-a-doctrine-artifacts-collision-with-a-live-gate-at-dispatch)
- [14. A Gate That Fails Everything Is Not More Trustworthy Than One That Passes Everything](#14-a-gate-that-fails-everything-is-not-more-trustworthy-than-one-that-passes-everything)
- [15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern](#15-an-old-home-citation-sweep-is-a-substring-match--order-the-content-classify-the-hits-never-tighten-the-pattern)

---

## 1. A Gate-Shaped Deliverable Requires a Positive Control

A guard that exits 0 because nothing is wrong is byte-identical, from the outside, to a guard that exits 0 because it is structurally blind. Both print nothing. Both return 0.

**The passing state of any gate carries the least evidence, and it is the state every clean run produces.** This covers linters, isolation gates, CI checks, pre-commit hooks, validation passes and "MUST be empty" greps. For all of them one run proves nothing, regardless of how clean it looks.

> [!constraint] Run the gate against a state that makes it fire, or it has not been tested
> ```
> WRONG — negative-only verification:
>   run guard on clean tree → exit 0, no traceback → "works"
>
> CORRECT — positive control, three steps:
>   1. clean state          → exit 0
>   2. force the condition  → BLOCKING reported, exit 1   ← the load-bearing step
>   3. revert               → exit 0
>   the outputs of 1 and 2 MUST differ
> ```
> Step 2 is the whole control. Steps 1 and 3 only establish that the gate is silent when it should be.

A worked instance of what this catches: a closeout guard passed `py_compile`, passed a smoke run with exit 0 and no traceback, and passed inside a 376-test green suite. It was still incapable of blocking anything. It resolved `git status --porcelain` paths, which are repo-root-relative, against a working directory set to the plans folder. That produced a doubled path that could never match its own key map, so every finding was dropped and the exit was unconditionally 0. Three green signals, none of which asked the gate to fail.

> [!practice] This section is the exercising half only
> [`verification-gates.md`](verification-gates.md) §10 obligation A owns the adjacent requirement — phrase at least one criterion against a **fixture that reproduces the defect**, and run the same probe against the **unfixed artifact**. Obligation D owns the distinction between a fixture dry-run and a live sweep. Read both before writing acceptance criteria for a gate-shaped deliverable. This section adds only the three-step control and its generalisation to every gate shape.

---

## 2. A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing

A test that asserts a guard refuses something passes for two different reasons. The guard refused, or the test never reached the guard. A green suite does not separate them.

One never-downgrade guard's test passed inside a 419-test green suite. Nothing in that suite had ever shown the test would go red if the guard regressed.

> [!constraint] Neuter the guard on a scratch copy and require the test to go red
> ```
> WRONG — the test passes, therefore the guard is covered:
>   pytest test_never_downgrade.py  → 1 passed → "guard tested"
>
> CORRECT — mutation control, three steps:
>   1. shipped code, run test                                          → PASS
>   2. neuter the guard (`if False:`) on a SCRATCH COPY, run same test  → FAIL  ← load-bearing
>   3. delete the scratch copy; re-run the suite green
> ```

Record the contrast, not just the two verdicts:

| Run | Exit code | Output | Index file |
|-----|-----------|--------|------------|
| Shipped script | 1 | `REFUSED: will not downgrade landed 'rule' -> 'documented'` | byte-unchanged |
| Guard neutered | 0 | *(no REFUSED line)* | silently rewritten `rule` → `documented` |

Four constraints govern the mutation:

1. **Mutate a copy, never the real artifact.** The scratch copy lives outside the shipped tree, gets deleted in the same task, and is never a file a concurrent runner may be reading.
2. **Reuse the existing fixture.** The differing result is then attributable to the one thing you changed.
3. **Assert on the difference, not just the failure.** "Exit 1 plus REFUSED emitted plus bytes unchanged" against "exit 0 plus no REFUSED plus bytes rewritten" is strictly stronger than "exit 1 against exit 0". It tells you which assertion does the work.
4. **Record the contrast in the task's status block.** A later reviewer cannot re-derive "this test is load-bearing" from a green suite.

---

## 3. Dry-Run Every MUST-be-N Gate in BOTH Directions

Running only the known-bad arm proves the gate discriminates. It does not prove the gate asks for the right thing. The arm that gets skipped is the **correct post-state** — the file as it looks after correct work.

> [!constraint] Verify the threshold against a hand-built correct post-state
> ```
> WRONG — the gate is authored from the author's mental image of the finished file:
>   grep -c '§5\.[1-5]' <file>   # ≥5 (headings + ToC)   ← headings are `### 5.1`, unprefixed. Returns 2.
>
> CORRECT — the gate anchors on notation the artifact actually uses, verified against a hand-built correct post-state:
>   grep -c '^### 5\.[1-5]' <file>   # 5 — matches the file's real heading convention
> ```

Two consequences make this worth its own section.

**A threshold is an instruction.** When correct work and the gate disagree, the artifact bends toward the gate. The runner in the originating instance did correct work, hit the failing gate, and deformed the shipped file to satisfy it.

**A gate that gets its way leaves no failure signal at all.** The run is green, the report says PASS, and only someone comparing the new output against the file's older conventions can see the divergence.

> [!practice] Prefer structural anchors over notational ones
> Anchor on `^###`, `^| `, or another structural marker rather than on `§`, backticks, or emphasis. Notation is a display choice that varies within a single file. Structure is not. This is the cheapest available screen for the whole class, and it is guidance rather than a gate, because "prefer structure" cannot be asserted by a command.

[`verification-gates.md`](verification-gates.md) §10 obligation B states the general form of this rule — a gate must not fail correct work, and the authoring test is *what would a correct-but-differently-formatted artifact score?* Read it alongside this section. What §3 adds is the specific arm to run and the anchor-selection screen.

---

## 4. Specify the Artifact for the PASS Branch, Not Just the FAIL Branch

Evidence for a FAIL is a free by-product of failing. Evidence for a PASS has to be asked for.

> [!constraint] Preserve evidence a wrong-but-passing run could not have produced
> ```
> FAIL self-serialises:  RESULT: ERROR: Permission to use Bash with command cat -A has been denied.
>                        ← carries the exact command the engine matched; the mechanism is re-derivable
> PASS produces nothing: RESULT: SUCCESS
>                        ← indistinguishable from: never ran / wrong target / output discarded / check vacuous
> ```

The asymmetry is structural, not a lapse in diligence. Failing machinery writes its own reason — a deny message, a failed assertion's compared values, stderr on a non-zero exit. Passing machinery writes nothing unless told to.

Four application rules:

1. **Prefer a fingerprint over a flag.** `is_error:false` says the call did not fail. Output carrying end-of-line markers and an octal rendering of a byte-order mark says *this specific command ran against this target*. Pick evidence a wrong-but-passing run could not have produced.
2. **Weight the over-correction control's evidence highest, not lowest.** It is the cell whose failure is quietest and whose pass is least scrutinised.
3. **When accepting delegated work, try to re-derive the verdict from the preserved artifact alone.** If you cannot, the gate is undocumented, regardless of whether the runner checked it.
4. **Never accept a re-run as evidence for an earlier run.** If the original transcript is gone, the correct outcome is `[UNVERIFIED — verdict observed at run time, primary evidence not preserved]`. Forbidding the substitution up front is what makes the honest answer available.

---

## 5. A Fixture Must Not Be Built Through the API Under Test

§1-§4 assume the control ran. §5-§9 cover the failure one level below that: the runs happened, the outputs differed, the criterion was satisfied — and the **input set could not have contained the defect**.

Seven test classes and four whole-file byte-equality assertions, green at 419 tests, could not see a script rewriting 100% of an index's line endings. The fixture helper used the same convenience API the bug used:

```python
def _write(self, name: str, content: str) -> Path:
    path = self.tmp_path / name
    path.write_text(content, encoding="utf-8")     # newline=None → os.linesep
    return path
```

```
before: | LL-NNN | Alpha | documented |\n| LL-MMM | Beta | rule |\n
after:  | LL-NNN | Alpha | promoted   |\r\n| LL-MMM | Beta | rule |\r\n
stdout: changed: 1          ← reported 1 while rewriting 100% of the file's lines
```

The defect and the fixture cancel out by construction, on every platform.

> [!constraint] When the property under test is how bytes are STORED, write the fixture as bytes
> Any fixture built through the same convenience API the implementation uses inherits that API's normalization. The test can then only observe behavior the normalization has already erased.
>
> **The symptom to watch for:** a test asserts on a file's *content*, while the fixture was created with a helper that transforms content. The sibling cases beyond line endings are byte-order-mark handling, trailing-newline policy, Unicode normalization, and text-mode encoding fallbacks.

Both directions are required, because each fails on only one platform:

| Test | Fails pre-fix on | Passes pre-fix on |
|---|---|---|
| LF fixture must stay LF | Windows (`os.linesep == "\r\n"`) | POSIX |
| CRLF fixture must stay CRLF | POSIX | Windows |

A single direction is a coin flip on which platform catches the regression. Keep both assertions even when one of them cannot be made to fail on the host you are running — report that half as unexercised-by-platform, never as passing evidence.

> [!practice] A house discipline reachable only from the module that defines it is not reachable
> The originating repository already had a newline-preserving read helper. It was documented only inside the module defining it, and the new destructive script did not import it. That is a discoverability problem, not a fixture problem. Make the discipline reachable from the **task** — "adding a destructive in-place write" — rather than from a module the author would have to already know to open.

---

## 6. A Known-Good Probe Must Name a Real Target — and Both Halves the SAME One

A discriminating pair used a sanitized stand-in path. The known-bad rows were unaffected. The known-good row was unpassable by construction.

| Row | Command | Expected | Why the fake path is / is not fatal |
|---|---|---|---|
| known-bad | `cd /c/x/agents && wc -l a.md b.md` | DENY | harmless — a DENY is decided before the command executes |
| known-good | `wc -l /c/x/agents/a.md /c/x/agents/b.md` | PASS, with real line-count stdout | **fatal** — returns `No such file or directory` on every run |

The asymmetry is what lets this survive review. One consistent placeholder convention runs across the table, and only one row's verdict depends on the path resolving.

Four rules follow:

1. **Do not apply the placeholder convention uniformly.** Placeholders are safe in known-bad probes and fatal in known-good ones.
2. **Repoint the known-bad half to follow the known-good one**, so the pair stays identical modulo the variable under test.
3. **State the expected output concretely** — `50`, `182`, `232 total`. "Genuine stdout" is satisfied by anything.
4. **A re-runnable procedure needs a substitution instruction** naming what a later runner must swap, with the same-target constraint restated at the substitution point.

---

## 7. A Fixture Set Must Span Input SHAPES, Not Only Families

Coverage over input *families* and coverage over input *shapes* are independent axes. Covering one says nothing about the other.

One fixture set covered every exempt command family across 22 fixtures — all of them fenced code or prose. Not one markdown table row, and not one use of the English word "find". The check was blind to the dominant syntactic shape of its own target population, and it false-fired on its own prescribed CORRECT exemplar.

For any check that runs over authored markdown, fixture one instance of each shape. The examples are numbered into the block below, because two of them contain pipes:

| # | Shape |
|---|---|
| 1 | Markdown table row |
| 2 | Fenced code block line |
| 3 | Inline code span in prose |
| 4 | Plain English prose |
| 5 | Comment inside a fence |

```
1   | `.md` | grep -rn "x" src/ |
2   grep -rn "x" src/
3   see `cat {path}` for the body
4   Locate the handler and find its dispatch table.
5   # e.g., grep current row count
```

> [!constraint] Span both axes, then self-apply
> ```
> WRONG — fixture set exhaustive over exempt families, monotone over syntactic shape:
>   known-bad:  2 fenced-code lines
>   known-good: 20 lines, one per exempt family — all fenced code or prose
>   result:     runs differ → criterion satisfied → gate declared proven
>   reality:    blind to every markdown table row; fires on the English word "find"
>
> CORRECT — fixture set spans both axes, plus self-application:
>   known-bad:  one per shape (table row, fenced code, inline span, comment) × violating verb
>   known-good: one per exempt family × at least two shapes, plus prose using the verb in English
>   self-apply: run the check against the rule file that defines it; classify every hit
>   result:     three directions, each with a stated expected outcome
> ```

Two corollaries:

- **Self-application is a cheap third direction.** Run the finished check against the artifact that defines it. Expect the WRONG exemplars to fire, and classify every surviving hit — anything unclassifiable is a defect, not a footnote.
- **A delegated verdict can be accurate in every reported number and still wrong.** Verifying that the figures match re-verifies the runner's *reading*. Only the orchestrator can see the runner's **choice of fixtures** as a claim to be checked.

[`verification-gates.md`](verification-gates.md) §10 obligation C owns the neighbouring defect — a pattern that cannot see the shape it counts, because the idiom spans lines and the matcher does not. §7 here is about the fixture set rather than the pattern. Read both.

---

## 8. Report What the Proof Does NOT Cover, in the Same Breath as the Result

> [!constraint] Bound the proof by its own frame, in the sentence that states the result
> ```
> WRONG — report the proof and let its scope go unstated:
>   Gate proof: known-bad 0 vs 5 (discriminates), known-clean 0 vs 0. PASSED.
>   → downstream reads: "the fence count is correct"
>
> CORRECT — report the proof bounded by its own frame:
>   Gate proof: known-bad 0 vs 5 (discriminates), known-clean 0 vs 0. PASSED.
>   Covers: tagged fences, blockquoted or not.
>   Does NOT cover: untagged fences, fences tagged with a non-shell language,
>                   or shell verbs absent from the declared verb set.
>   → therefore every fence count in this session is a LOWER BOUND, not a census.
> ```

**Compute no coverage percentage against a lower bound.** A percentage silently converts "at least N" into "exactly N", and that is where an undercount becomes invisible.

A known-clean file returning zero under both patterns carries **no** information about coverage. It would return zero under a pattern for a language nobody writes, too.

**The cheap screen:** for any pattern gate, write down the class the known-bad file exercises. Anything outside that class is unproven, whatever the gate returned.

---

## 9. Verify Completeness Against the Spec's Enumeration, Never Against the Artifact

Heading density measured against six sibling files, plus a full read of the region judged riskiest, cleared a new handler that was still missing a spec-mandated clause. Density is structurally incapable of detecting that one required sentence is absent.

| Question asked | Question needed |
|---|---|
| *Is this file suspiciously thin?* | *Does this file contain every clause the spec requires?* |
| Evidence: density vs siblings, plus a full read of the region judged riskiest | Evidence: the spec's clause list, walked one at a time against the file |

**Completeness is never verifiable from the inside.** A missing clause has no representation in the artifact, and an untested input shape has no representation in the fixture set. The reader's model of "what should be here" gets reconstructed from what is here — precisely the corrupted input. The spec-first direction cannot miss, because the enumeration is external to the thing being checked.

Five application rules:

1. **A budget deviation is a prompt to verify completeness, not a claim to adjudicate.** The correct response to "251 lines against an advisory 450-550" is *walk the clause list*, not *explain the number*. Explaining the number is answerable with density evidence, and it terminates the investigation with the real question unasked.
2. **Structural evidence bounds an explanation, never establishes completeness.** Density, heading count and sibling comparison legitimately answer *"is this truncated?"* — report them as answering that.
3. **A spot-read of the riskiest region is a sample.** Say so when reporting it.
4. **When a cross-file claim disagrees, go to the spec before deciding which side is wrong.** A dangling "documented in X" reference is symmetric evidence.
5. **A verifier that finds a defect reports it rather than repairing it.** Adjudication belongs to whoever holds the spec, the artifact and the authority together.

> [!hazard] The one instance caught here was caught by luck
> It was visible only because a *sibling* artifact happened to assert what the handler should contain. A required clause with no sibling citing it leaves no trace at all — no failing gate, no anomalous count, nothing for a sweep to find.

This section is deliberately written without a mechanical gate. "Walk the spec's enumeration" cannot be asserted by a match pattern, and dressing it as a constraint with a fabricated verification command would reproduce the exact defect the section describes.

---

## 10. The Artifact Is Authoritative; the Instrument Is the Defect

§1-§9 prove the instrument before it is cited. §10-§13 govern the other direction: the instrument is already in play, and it disagrees with correct work anyway. §10 fixes which side yields. §11 binds the runner reading a gate's annotation. §12 binds the orchestrator reading a runner's report. §13 binds the dispatcher whose authoring task is a live gate's subject.

A gate's expected value is a **prediction** about what correct work will look like, written before anyone knew what the correct edit was. Four instances across three sprints produced runners that treated the prediction as a specification, and every one of them reported green. [`verification-gates.md`](verification-gates.md) §10 obligation B states the claim in one sentence: *when a runner reports that it reformatted content to satisfy a gate, that is a gate-defect report, not a completion detail.* This section carries the resolution that sentence does not.

The originating instance: a gate could not match the CORRECT block its own specification prescribed. A backtick sat between `Read` and the following space, and the regex required them adjacent. The runner diagnosed it correctly and resolved it the wrong way round. It dropped the backticks from the shipped prose, leaving a bare `Read` beside a backticked `` `offset` `` in the same sentence, against the file's own convention.

> [!constraint] When an instrument and the deliverable it measures disagree, the deliverable is authoritative and the instrument is the defect
> ```
> WRONG — change the deliverable so the instrument passes:
>   gate returns 0 → edit the shipped prose to match the regex → gate returns 1 → report PASS
>
> CORRECT — fix the instrument, prove the fix in both directions, and record why:
>   gate returns 0 → confirm the prose is correct per spec → fix the regex
>     → prove: OLD form returns 0 against correct prose (defect was real)
>              NEW form returns 1 against correct prose (fix works)
>     → correct the regex in EVERY copy (spec + task file), each with an inline note
> ```
> A gate exists to measure prose; prose does not exist to satisfy a gate. Bending the artifact to fit its measuring device produces a green check over a worse artifact and — because the gate now passes — removes the only signal that anything is wrong.

Two mechanical rules follow:

1. **Dry-run every gate against the exact text its own specification prescribes.** A gate validated only against improvised fixtures has never been shown to accept its own intended output. The cheapest possible fixture — the spec's own CORRECT block — is the one most often skipped.
2. **A gate lives in more than one file.** The same regex existed in the Execution Input *and* in the task file's Verification Commands, so fixing one leaves the other to false-fail a later sweep. Fix every copy and annotate each, or the correction is itself a half-measure.

The construction vocabulary this remedy assumes — the regex dialect, the window that must fit its subject, the count whose unit must match its threshold — is [`verification-task-authoring.md`](verification-task-authoring.md) §10.9. §3 above owns the correct-post-state arm that catches the defect before a runner meets it.

---

## 11. A Gate Annotation Predicts the Shape of Correct Work — It Never Constrains It

The most dangerous member of this family is silent. A runner found three stale self-descriptions in a file it was editing, surfaced them correctly, and then declined to fix them: *"I deliberately left both untouched to preserve the pure-append shape your gate expects."* Three stale counts would have shipped, in a file whose own header then misdescribes it, so that a diff statistic could match a number predicted before the correct edit was known.

> [!constraint] When your correct edit and a gate's annotated value disagree, the artifact wins
> Report the true measured value with a classification of each contributing line, and flag the annotation as defective. Never reshape the artifact to fit. Never withhold a correct change to keep a number matching. This binds you as the runner reading the gate, not only the reviewer who wrote it.
>
> State it in the annotation itself, not only in a reference, because the runner reading the gate is the one who needs it:
> ```
> git diff <file> | grep -cE '^-'   # predicted ~1 (diff header only) on a pure append.
>                                   # This PREDICTS correct work; it does not constrain it.
>                                   # If your correct edit produces more, report the number
>                                   # and classify each line. Never withhold an edit to match.
> ```

Why the withheld-fix direction is the most serious of the three:

| Direction | What the gate did | Visible in the output? |
|---|---|---|
| Artifact deformed | The runner reshaped the shipped file until the gate passed | Green run, no signal — but the deformation is at least on disk |
| Gate unsatisfiable | Correct work retried 3× → BLOCKED | Loud, expensive, misdirects diagnosis |
| **Correct fix withheld** | The runner identified a correct edit and declined to make it, to keep a diff count matching | **Nothing, anywhere** |

A deformed artifact can be found by reading it. A spurious BLOCKED announces itself. An edit that was correctly identified and then not made leaves no trace in any diff, any gate result, or any artifact. The only reason the instance surfaced is that the runner reported its reasoning instead of quietly conforming.

**The review-time tell.** For every gate annotated with an expected value, ask whether the value was derived from a correct post-state or predicted before the work was scoped. A parenthetical explaining the expectation ("ToC/footer only", "headings + ToC") marks a prediction.

Two neighbouring rules own the authoring side. [`verification-task-authoring.md`](verification-task-authoring.md) §10.7 requires an anchor to accept exactly the outcome set its own task can produce. [`verification-gates.md`](verification-gates.md) §11.1 shows how a pre-existing omission arms a gate against correct work. Both catch the annotation before a runner meets it. This section governs the runner who meets it anyway.

---

## 12. A Disclosure That a Gate Influenced the Artifact Is a Re-Derivation Trigger

Two runners in one sprint reshaped their output to fit a gate's expected value, and both disclosed it unprompted. One sized a block to exactly 12 lines so a `-A 12` window would not reach diverging content. The other reworded a correct Required-References row so an exact-count gate would return 1. Neither gate caught a real defect. Neither landing was wrong. In both cases the gate output was identical to what correct, unreshaped work would have produced.

> [!constraint] When a runner discloses that it shaped content to satisfy a gate, do not accept the gate's green
> Re-derive the underlying property with a check the content cannot be shaped to. The worked re-derivation, for a block required to be identical in two files:
> ```bash
> # The gate the runner satisfied — a guessed window, shaped to by sizing the block:
> diff <(grep -A 12 '<anchor>' FILE_A) <(grep -A 12 '<anchor>' FILE_B)   # EMPTY
>
> # The re-derivation — compares the complete added-line sets, with no window to shape:
> diff <(git diff FILE_A | grep '^+' | grep -v '^+++') \
>      <(git diff FILE_B | grep '^+' | grep -v '^+++')     # exit 0 → genuinely identical
> ```
> The blocks were genuinely identical for all 14 lines. The gate had merely under-covered, so the gate was recorded as the defect and the work as correct. For the reworded row, the re-derivation was reading the landed line against its list's own format, which it matched.

Three trigger phrasings, each a **gate-defect report** rather than a wording preference. Treat each as a defect requiring adjudication, never as diligence. They are written here as literal strings so a reviewer can search a status block for them:

- *"I left X unchanged to preserve the expected gate value"*
- *"achieved by … so the gate would …"*
- *"I deviated from the spec to make the gate pass"*

The honest report is the signal, and the resolution is the part to check. Re-derive it against the spec rather than accepting the resolution.

**The standing asymmetry that makes disclosure load-bearing.** A gate that false-fails correct work is loud: the runner halts, retries, reports BLOCKED, and a human looks. A gate a runner silently satisfies by bending the artifact produces the exact same output as one satisfied honestly. There is no diff signature, no count anomaly, and no failed step for a sweep to find. The sweep re-runs the same gate and gets the same green. Disclosure is a property of a particular runner, not of the process, so the process cannot rely on it arriving. Where it does arrive, it is the only signal there will be.

The two gate-authoring corollaries — a fixed-size window must fit its subject, and an exact-count gate forbids legitimate mentions — are [`verification-task-authoring.md`](verification-task-authoring.md) §10.9. This section is the adjudication half.

---

## 13. Pre-Adjudicate a Doctrine Artifact's Collision With a Live Gate at Dispatch

A doctrine reference whose job is to forbid shell verbs must literally write `cat`, `find` and bare `cd` in its body. A live promotion gate whose pre-commit check matches those verbs as bare words fires on it by construction: nine hits, every one the reference correctly doing its job. The gate's own prescribed remedy, *"repoint the instruction to name the native tool"*, would have rewritten the forbidden-verb list into native-tool names and shipped a reference that **cannot say what it forbids**, with the gate reporting clean.

The asymmetry that makes this urgent: an unclassified hit that gets repointed produces a clean gate and a broken artifact. That is strictly worse than a failing gate, which at least announces itself. Nothing downstream can detect it, because the check that would have caught it is the one that was satisfied.

> [!constraint] Pre-adjudicate the collision at dispatch — never leave a runner alone with rule-plus-hit
> Section numbers inside the quoted instructions are the gate rule's own.
> ```
> WRONG — dispatch the authoring task with the generic gate instruction only:
>   "The promotion gate is live and covers your file. Run its §4 check
>    on your added lines and repoint any hit per §2 before the change lands."
> ```
> The runner writes ``- **`cat`** — reading a file's contents. Use **Read**.``, the check fires, and the runner dutifully repoints its own forbidden-verb list. Gate: clean. Reference: incoherent. Nothing downstream detects it.
> ```
> CORRECT — name the collision, pre-classify it, and forbid the remedy in this instance:
>   "Your forbidden-verb list must literally name `cat`, `sed`, `find`, `cd`
>    in order to forbid them, and the check matches those as bare words, so it
>    WILL fire. That is a CLASSIFIED hit, not a leak — prose naming a forbidden
>    shape in order to forbid it. Do NOT repoint, soften, rename or delete the
>    list; repointing it would leave the reference unable to say what it forbids.
>    Classify each hit against the rule's §3 must-pass boundary and record the
>    classification in your report."
> ```
> The CORRECT block is the text a dispatching orchestrator copies.

Any gate strong enough to police a doctrine will fire on the doctrine that defines it. The class is broader than one plugin:

- A rule that forbids a pattern must quote the pattern.
- A linter's own test fixtures contain the violations it detects.
- A style guide's WRONG examples are, by definition, violations.
- A security check's documentation names the vulnerable call it looks for.

In each case the artifact is a **legitimate carrier of the forbidden shape**, and the gate cannot tell a carrier from a violation, because the difference is intent, not syntax. Only a human or an orchestrator holding both artifacts can adjudicate it, and the adjudication must reach the runner **before** it edits.

Five application rules:

1. **At dispatch planning, cross-check every authoring task against every live path-scoped gate covering its output path.** Where the task's *content* is the gate's *subject*, the collision is guaranteed. Flag it before spawning, not after.
2. **Pre-adjudicate rather than delegating the judgment.** A runner holding a binding rule and a matching hit will apply the rule. That is correct behaviour, and it is the reason the instruction must arrive first.
3. **Require the classification in the report, not just the count.** "9 hits, all classified as doctrine text naming a forbidden verb in order to forbid it, zero repointed" is auditable. "Gate clean" is not, and here would be a lie by omission.
4. **Check the gate still discriminates in the other direction on the same artifact.** The reference's own legitimate pipeline exemplar not firing is what proves the gate was classified rather than disabled.
5. **Carry the classification downstream.** A later sweep re-running the check over the same tree sees the same hits. Without a propagated flag it reports a regression that does not exist.

This section is its own first test case. It quotes gate-shaped text, shell verbs and forbidden phrasings in order to forbid them, so any gate covering this file fires on it by construction. It shipped as a pre-classified hit with zero repoints, under rule 2.

---

## 14. A Gate That Fails Everything Is Not More Trustworthy Than One That Passes Everything

§3 requires dry-running a MUST-be-N gate in both directions. Direction-checking alone leaves one failure uncaught, and an asymmetry in how readers weigh results is what lets it through.

A 17-of-17 FAIL reads as a serious finding and invites acting on it. The alarming direction therefore gets less scrutiny than the reassuring one: a full-pass result is questioned, a full-fail result is believed and repaired against. Treat a total-failure result as a gate-construction suspect until the known-bad/known-good pair has been shown to *differ*.

> [!constraint] A total-failure result is a suspect gate until its dry-run pair differs
> A closeout audit asserted that each of 17 Part files carried its pinned Scope string exactly once, via a per-file count piped through a field split on `:`. It reported FAIL on all 17, including files that were provably correct. The count tool prefixes each result with the filename when given more than one input, and splitting an absolute Windows path on `:` puts the drive letter in the second field and a path fragment after it — never the count. Run only against the real, clean tree, it would have produced a loud, plausible, entirely false 17-file failure.
>
> What caught it was the dry-run pair. The doctored file returned FAIL *and* the clean files returned FAIL — identical results on inputs that were supposed to differ, which is the signature of a gate that does not discriminate. The parsing bug behind it was one keystroke.
>
> ```
> WRONG — treat the direction as the proof:
>   run gate on clean tree → 17 FAIL → "17 files are wrong; start repairing"
>
> CORRECT — require the pair to DIFFER before believing either arm:
>   doctored file → FAIL
>   clean file    → FAIL      ← identical: the gate is the suspect, not the files
>   fix the gate  → doctored FAIL, clean PASS → now a FAIL means something
> ```
>
> The requirement is not "run a dry-run". It is "run the pair and require the two results to differ." A gate only ever run against clean input has never been shown to work; its empty — or full — result is vacuous either way.

The parsing bug is one instance of a class, misparsed tool output, that no amount of care eliminates. The discrimination check, not the fix, is the durable half. §1's positive control and §3's correct-post-state arm each exercise one direction; this section binds the comparison between them.

---

## 15. An Old-Home Citation Sweep Is a Substring Match — Order the Content, Classify the Hits, Never Tighten the Pattern

Splitting an oversized reference along a seam, keeping the anchor's filename, and repointing every inbound citation ends with a sweep for citations still pointing at the old home:

```
grep -rEn '{anchor}\.md.*§({moved-range})' . --include='*.md' | wc -l   # expect 0
```

That pattern is a substring match, not a parser. `{anchor}\.md.*§N` asks only whether the two strings appear in that order on one line. It cannot tell a stale citation from two correct citations that happen to share a line. So **on a correctly-repointed corpus this sweep can return non-zero, and the exit criterion must be written to expect that.** A criterion reading "expect 0" hands the runner three options, and two of them are wrong in ways nothing downstream detects: reword the corpus until the count reaches zero (corrupts the artifact and destroys the gate's signal); tighten the pattern so it cannot span (§15.2 — converts a false positive into a false negative); or order the content so the sibling citation precedes the anchor citation (§15.1 — correct, and it encodes an invariant nothing local explains).

### 15.1 The dual-citation false match — write the sibling citation first

> [!pitfall] A line citing both halves of a former anchor false-matches whenever the anchor's filename precedes the moved section number
> The false-match case is a single line citing **two** files that were once one anchor: one section that stayed, one that moved.
> ```
> WRONG — anchor filename first; §{moved} appears later on the line ⇒ MATCH (false):
>   `{anchor}.md` §{stayed} / `{sibling}.md` §{moved}
>
> CORRECT — sibling citation first; the anchor filename is followed only by §{stayed}:
>   `{sibling}.md` §{moved} / `{anchor}.md` §{stayed}
> ```
> Both lines are accurate. Only the order differs, and only the second passes the sweep. The remedy makes reading order load-bearing, so record it where the next writer of that file will see it — a one-line note beside the citation, or in the file's authoring conventions. The correct form may cite a higher section number before a lower one. That is deliberate, not a typo to fix.

### 15.2 Do NOT tighten the pattern — prefer the failure you can inspect

> [!constraint] Bounding the wildcard converts a loud false positive into a silent false negative
> Replacing `.*` with an adjacency-bounded `[^§]*` looks like the clean fix. Measured over one authoring corpus — every `.md` file in a project tree, re-measured 2026-09-08 — for two anchors whose sections had moved:
>
> | Sweep | `.*` (correct) | `[^§]*` (tightened) |
> |-------|----------------|---------------------|
> | `{anchor-A}.md` §{moved range A} | 334 | **276** |
> | `{anchor-B}.md` §{moved range B} | 405 | **300** |
>
> The hits the bounded form stops matching mix two shapes the pattern cannot tell apart. One is the dual-citation line of §15.1, which the sweep should indeed stop flagging. The other is a **real stale citation** — one file, two sections, only the second of which moved:
> ```
> `{anchor}.md` §{stayed}/§{moved}
> ```
> The bounded pattern stops at `§{stayed}` and never sees the stale `§{moved}`. The tightening trades a false positive a human reads and classifies for a leak that ships behind a green gate — the strictly worse trade for a leak gate, and a reader who reaches for it is making the failure worse while believing they fixed it.
>
> **When a gate is imprecise, prefer the failure mode you can inspect.** Evaluate any loosening or tightening of a gate's pattern on *which direction it fails in*, never on the hit count it returns.

### 15.3 A non-zero sweep is a list to classify, not a verdict

> [!practice] Gate on the delta against a recorded ledger, never on the raw count
> For each hit, read the line and ask whether every citation on it is accurate.
>
> | Every citation on the line accurate? | Disposition |
> |---|---|
> | Yes | False positive — record the line and the reason in the ledger |
> | No | Real stale citation — FAIL; repoint it |
>
> The gate is then `hits − ledgered false positives = 0`, not `hits = 0`. The ledger lives where the next audit reads it — beside the sweep command in the sprint's verification task, or in the file's authoring conventions — because a classification nobody can find is re-derived from scratch, and a blanket-fail gate that keeps firing on known-correct lines gets softened or ignored instead of fixed. This is the discipline the on-disk identifier sweeps already use for the plugin's own scaffold vocabulary: surface candidates, classify each one, gate on what survives classification ([artifact-self-containment.md](artifact-self-containment.md) §4.3).

The three rules assume the sweep inspected what you think it did. Pair them with the input-set assertions — register untracked files, assert zero untracked remain, assert the diff covered the expected file count — from [measurement-discipline.md](measurement-discipline.md) §8.7. Together they are what make an empty *or* non-empty sweep interpretable.

---

*Cross-references: [verification-gates.md](verification-gates.md) §10 (the instrument's four proof obligations — fixture-vs-live-sweep, the gate that fails correct work, and the pattern that cannot see the shape it counts), §11 (change-detecting vs state-detecting shapes) and §11.1 (a pre-existing omission can arm a gate against correct work), [verification-task-authoring.md](verification-task-authoring.md) §10 (pre-edit value annotation), §10.7 (an anchor accepts exactly its task's outcome set), §10.8 (command semantics that make a well-formed gate mean something else) and §10.9 (the construction corollaries §10-§13 assume — regex dialect, window size, exact counts), [measurement-discipline.md](measurement-discipline.md) §8.5 (normalize on both read and write; annotated rather than clean fixtures) and §8.7 (verify the gate's input set before trusting its predicate), [dispatch-edit-surface-sweep.md](dispatch-edit-surface-sweep.md) §5-§6 (hunting `§` pointers after a renumbering, and a renumbering gate's true expected count — the sibling of §15), [artifact-self-containment.md](artifact-self-containment.md) §4.3 (the classify-do-not-blanket-fail sweep §15.3 mirrors).*
