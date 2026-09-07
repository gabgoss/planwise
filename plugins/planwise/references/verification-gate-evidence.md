---
description: What a verification gate's output is evidence of — positive and mutation controls, the correct-post-state arm, and specifying the artifact the PASS branch must leave behind. Consult before citing any guard, linter, hook, or MUST-be-empty check as proof.
paths: {planwise_root}/{plans_dir}/**
---

# Verification-Gate Evidence (Proving the Instrument Before Citing It)

**Purpose:** Rules for the gap between *"the gate returned this"* and *"this is true"*. A gate's output becomes evidence only after the gate has been exercised in the direction that carries information, over an input set that could have contained the defect. This file governs the exercising; [`verification-task-authoring.md`](verification-task-authoring.md) governs the match pattern, and [`verification-gates.md`](verification-gates.md) §10 governs the instrument's four proof obligations.

**Read this when** you author a guard, hook, linter, validation pass, or "MUST be empty" check, and again when you are about to cite one of them as proof that work is correct.

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

*Cross-references: [verification-gates.md](verification-gates.md) §10 (the instrument's four proof obligations — fixture-vs-live-sweep, the gate that fails correct work, and the pattern that cannot see the shape it counts), §11 (change-detecting vs state-detecting shapes), [verification-task-authoring.md](verification-task-authoring.md) §10 (pre-edit value annotation) and §10.8 (command semantics that make a well-formed gate mean something else), [measurement-discipline.md](measurement-discipline.md) §8.5 (normalize on both read and write; annotated rather than clean fixtures) and §8.7 (verify the gate's input set before trusting its predicate).*
