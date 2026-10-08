---
description: A gate-shaped deliverable requires a positive control (§1); a test whose subject is a refusal is proven load-bearing with a mutation control (§2); every MUST-be-N gate is dry-run in both directions, with the correct-post-state arm (§3); the PASS branch's artifact is specified as well as the FAIL branch's (§4); and a gate that fails everything is no more trustworthy than one that passes everything, so the dry-run pair's two arms must differ (§14).
paths: {planwise_root}/{plans_dir}/**
---

# Gate Positive and Mutation Controls (Proving the Instrument Fires)

**Purpose:** Rules for the gap between "the gate returned this" and "this is true". A gate's output becomes evidence only after the gate has been exercised in the direction that carries information. This file governs the exercising. Split from `verification-gate-evidence.md` on 2026-10-08. Section numbers are kept from that reference, so an existing `verification-gate-evidence.md §N` citation translates by filename alone. The family index is `verification-gate-evidence.md`.

**Read this when** you author a guard, hook, linter, validation pass or "MUST be empty" check, you are about to cite one as proof that work is correct, or a gate returns FAIL on every input it was given.

## Table of Contents

- [1. A Gate-Shaped Deliverable Requires a Positive Control](#1-a-gate-shaped-deliverable-requires-a-positive-control)
- [2. A Test Whose Subject Is a Refusal Must Be Proven Load-Bearing](#2-a-test-whose-subject-is-a-refusal-must-be-proven-load-bearing)
- [3. Dry-Run Every MUST-be-N Gate in BOTH Directions](#3-dry-run-every-must-be-n-gate-in-both-directions)
- [4. Specify the Artifact for the PASS Branch, Not Just the FAIL Branch](#4-specify-the-artifact-for-the-pass-branch-not-just-the-fail-branch)
- [14. A Gate That Fails Everything Is Not More Trustworthy Than One That Passes Everything](#14-a-gate-that-fails-everything-is-not-more-trustworthy-than-one-that-passes-everything)

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
> [`gate-instrument-proof-obligations.md`](gate-instrument-proof-obligations.md) §10 obligation A owns the adjacent requirement — phrase at least one criterion against a **fixture that reproduces the defect**, and run the same probe against the **unfixed artifact**. Obligation D owns the distinction between a fixture dry-run and a live sweep. Read both before writing acceptance criteria for a gate-shaped deliverable. This section adds only the three-step control and its generalisation to every gate shape.

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

Five constraints govern the mutation:

1. **Mutate a copy, never the real artifact.** The scratch copy lives outside the shipped tree, gets deleted in the same task, and is never a file a concurrent runner may be reading.
2. **Reuse the existing fixture.** The differing result is then attributable to the one thing you changed.
3. **Assert on the difference, not just the failure.** "Exit 1 plus REFUSED emitted plus bytes unchanged" against "exit 0 plus no REFUSED plus bytes rewritten" is strictly stronger than "exit 1 against exit 0". It tells you which assertion does the work.
4. **Record the contrast in the task's status block.** A later reviewer cannot re-derive "this test is load-bearing" from a green suite.
5. **Name the scratch root, prove its removal, and sweep for scratch directories.** See [gate-environment-inputs.md](gate-environment-inputs.md) §20.

Which assertion must go red, and how to give each guard its own input, is in [`gate-predicate-discrimination.md`](gate-predicate-discrimination.md) §14 and §15.

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
> Anchor on `^###`, `^| `, or another structural marker rather than on `§`, backticks, or emphasis. For a verdict line, whose label carries emphasis, copy the skeleton's bytes instead: [`gate-pinned-from-real-content.md`](gate-pinned-from-real-content.md) §10.5 and §11.4. Notation is a display choice that varies within a single file. Structure is not. This is the cheapest available screen for the whole class, and it is guidance rather than a gate, because "prefer structure" cannot be asserted by a command.

[`gate-instrument-proof-obligations.md`](gate-instrument-proof-obligations.md) §10 obligation B states the general form of this rule — a gate must not fail correct work, and the authoring test is *what would a correct-but-differently-formatted artifact score?* Read it alongside this section. What §3 adds is the specific arm to run and the anchor-selection screen.

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

*Cross-references: [gate-fixture-provenance.md](gate-fixture-provenance.md) (§5-§9, an input set that could have contained the defect: the failure one level below a control that ran) · [gate-instrument-proof-obligations.md](gate-instrument-proof-obligations.md) (§10, the four obligations these controls discharge) · [gate-predicate-discrimination.md](gate-predicate-discrimination.md) §14 and §15 (which assertion must go red, and one input per guard) · [gate-environment-inputs.md](gate-environment-inputs.md) §20 (the scratch root a mutation run writes to) · [verification-gate-evidence.md](verification-gate-evidence.md) (the family index).*
