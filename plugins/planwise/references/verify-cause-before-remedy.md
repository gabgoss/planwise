---
description: Count the population before naming a cause, and check whether the failure was already measured under the remedy you are proposing. Covers why a contradiction between two representations of one fact is evidence about the writers, why the plausible per-instance story stops you counting, the six-step procedure when two representations disagree, why the within-file duplicate hides longest, the treatment-arm check before proposing a remedy, the four moves that keep "undocumented" from standing in for "untried", and why a fallback recipe keyed on a predicted error string is a hypothesis and the printed rule is what gets fixed. Consult before naming a cause from one observed instance, before filing or routing a remedy, before pinning a fallback to a tool message the tool has not yet printed, and whenever a hypothesis proposes adding something to a system whose failure you are explaining, before choosing a remedy against a headline count that no one has grouped by category, and before recording a mechanism for a figure discrepancy without checking that it moves the number in the observed direction. Also covers why a would-file count is broken down by path segment before a destructive remedy is chosen, and why an unchecked "character count mislabeled as bytes" explanation predicts the wrong sign. Also covers why a fresh red test makes two claims (the code is wrong, and this assertion is the right one) and why its premise is checked, by naming what each operand measures and reading the code at the asserted line, before a module fix is routed.
consult-when: Naming a cause from one observed instance, filing or routing a remedy, or writing a hypothesis that proposes adding something to a failing system — count the population before diagnosing, read both writers, fix the writer before backfilling, correct the recorded misdiagnosis, and check whether the failure was already measured with the remedy in force, and treat a fallback recipe keyed to a predicted error string as a hypothesis, break a would-file count down by category before choosing a destructive remedy, and check that a proposed cause moves the number in the observed direction, and check a fresh red test's premise (what each operand measures, the code at the asserted line) before routing a module fix (§10)
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Cause Before the Remedy — Count the Population; Check Whether the Remedy Already Shipped

**Purpose:** Two diagnoses were plausible, wrong, and cheap to refute by opening the artifact rather than its description. One read a single contradictory record as a one-off human error, and counting showed it was **1 of 52**. The other proposed a remedy as its highest-priority open question, while the artifact under investigation had **already implemented that exact remedy**.

**Read this when** you are about to name a cause from one observed instance, file or route a remedy, or write a hypothesis that proposes adding something to the system whose failure you are explaining.

The two share a mechanism. A plausible per-instance story is precisely the thing that stops you counting, and "nobody has documented this technique" is allowed to stand in for "nobody has tried this technique." Both produce a remedy indistinguishable from the current state, and both displace attention from the real cause.

The check is cheap and asymmetric: reading the artifact costs minutes; shipping a remedy already in force costs a cycle and yields no observable change.

The two halves are one rule because they share a test. §1–§4 ask *"is this instance representative?"* and answer it by counting; §5–§6 ask *"is this remedy novel?"* and answer it by reading the source. Both are pre-commitment checks performed against the primary artifact, both are refuted in minutes, and both fail in the same direction — a plausible story that requires no further work. One neighbouring rule shares the instruction "open the artifact" and asks it a different question: [`verify-verdict-source.md`](verify-verdict-source.md) governs a *verdict about an artifact* and requires re-reading the source the claim disputes; this file governs a *causal story* and a *proposed remedy*.

## Table of Contents

- [1. A Contradiction Between Two Representations of One Fact Is Evidence About the Writers, Not About the Instance](#1-a-contradiction-between-two-representations-of-one-fact-is-evidence-about-the-writers-not-about-the-instance)
- [2. The Plausible Per-Instance Story Is What Stops You Counting](#2-the-plausible-per-instance-story-is-what-stops-you-counting)
- [3. The Procedure When Two Representations Disagree](#3-the-procedure-when-two-representations-disagree)
- [4. The Class Generalises Past Status Fields, and the Within-File Member Hides Longest](#4-the-class-generalises-past-status-fields-and-the-within-file-member-hides-longest)
- [5. Before Proposing a Remedy, Check Whether the Failure Was Already Measured Under It](#5-before-proposing-a-remedy-check-whether-the-failure-was-already-measured-under-it)
- [6. Why the Mistake Is Easy, and the Four Moves That Prevent It](#6-why-the-mistake-is-easy-and-the-four-moves-that-prevent-it)
- [7. A Fallback Recipe Keyed on a Predicted Error String Is a Hypothesis; Fix the Printed Rule](#7-a-fallback-recipe-keyed-on-a-predicted-error-string-is-a-hypothesis-fix-the-printed-rule)
- [8. Break a Would-File Count Down by Category Before Choosing a Remedy](#8-break-a-would-file-count-down-by-category-before-choosing-a-remedy)
- [9. Check That a Proposed Cause Moves the Number in the Observed Direction](#9-check-that-a-proposed-cause-moves-the-number-in-the-observed-direction)
- [10. A Fresh Red Test Is Two Claims — Check Its Premise Before Routing a Module Fix](#10-a-fresh-red-test-is-two-claims--check-its-premise-before-routing-a-module-fix)

---

## 1. A Contradiction Between Two Representations of One Fact Is Evidence About the Writers, Not About the Instance

When one fact has two representations, count the population before you diagnose the instance, because whether they agree is a property of the **writers**. If the same code path writes both, they cannot disagree. If they disagree even once, some path writes one and not the other, and **that path will have run on every record that passed through it.**

Item files carried status twice, as YAML frontmatter and as a `**Status:**` display line. The update script wrote the display line only in its *create* path, so closing an item left the body stale.

> [!constraint] The instance carries no information about whether it is unique; only the population does
> WRONG — one contradictory record is diagnosed as a human error and written into the index footer:
> ```
> frontmatter says COMPLETE, body reads NOT_STARTED -> "likely opened-then-mis-archived"
> ```
> CORRECT — one loop counts the population, and the broken writer appears:
> ```
> archived items: 61 | with a body **Status:** line: 61 | body disagrees with frontmatter: 52
> ```
> Not a mis-archive. **1 of 52.**

---

## 2. The Plausible Per-Instance Story Is What Stops You Counting

> [!constraint] A per-instance diagnosis produces a per-instance remedy
> The single-instance reading stuck because *"someone opened this and mis-archived it"* explains the observation completely, requires no code to be at fault, and needs no further work. Had someone reconciled that one item's true state, the count would have gone 52 → 51, the writer would still be broken, and the next closeout would have re-created the drift. **The repair would have looked like progress while leaving the generator untouched.**

That last sentence is what separates this rule from generic root-cause advice: the per-instance remedy is not merely insufficient, it is actively reassuring.

---

## 3. The Procedure When Two Representations Disagree

> [!constraint] Six steps, in this order
> ```
> 1. Count the population before naming a cause. One loop over the corpus
>    separates "one-off" from "systemic". Do this FIRST.
> 2. Read the writers, both of them. Grep the writing code for each
>    representation. One hit where you expected two is the answer.
>    (Here: searching the update script for the display-line marker returned
>     exactly one line, inside the create-path renderer.)
> 3. Fix the writer, then backfill — in that order, and say which is which.
>    A backfill that lands before the writer fix is undone by the next write.
> 4. Prefer removing the second representation over maintaining a second
>    writer, when the display copy earns nothing that rendering could not.
>    Two writers for one fact is a cache with no invalidation; syncing them
>    is a permanent tax on every future status path.
> 5. Go correct the recorded misdiagnosis, not just the data. A wrong cause
>    written into an index or a footer is itself a rotting citation — it will
>    be read as established fact and will misdirect the next reader.
> 6. Then re-check what the wrong diagnosis was covering. A corrected
>    diagnosis narrows the unexplained set; it does not empty it.
> ```

Step 6 needs its instance to be usable: the footer note also flagged unchecked acceptance criteria and an open-decisions section, and **the writer gap explains the status line and nothing else** — so the residual still needed its own look. Steps 5 and 6 stay separate: a reader who merges them fixes the data and leaves the wrong cause in the footer, which is the specific failure the incident carried forward.

Step 4's principle for counts is already stated in [`task-content-fidelity.md`](task-content-fidelity.md) — the list is the source of truth, the number typed beside it is a cache with no invalidation, prefer no cache. This section applies it to any duplicated fact, and adds the writer-first ordering.

---

## 4. The Class Generalises Past Status Fields, and the Within-File Member Hides Longest

Treat any duplicated fact as a member of this class, and look hardest where both copies sit in one file. It applies to a count restated in a header and a table, a version in two manifests, and a threshold quoted in a rule and in the gate that enforces it. **The cross-file instances were caught because a reader compared a cache against its source. The within-file instance survived longer because both copies read as one statement, and a disagreement looks like a typo instead of a broken pipeline.**

> [!constraint] Both copies in one file read as one statement, and a disagreement looks like a typo
> WRONG — the rule is read as being about cross-file caches, which keeps only the instances already caught:
> ```
> compare each index row with its source -> all reconciled -> stop
> ```
> CORRECT — the rule is read as covering any duplicated fact, wherever the copies sit:
> ```
> compare each index row with its source -> then compare the copies that share a file
> frontmatter against display line, header count against table -> a mismatch is a writer defect until counted
> ```

---

## 5. Before Proposing a Remedy, Check Whether the Failure Was Already Measured Under It

Before you propose a remedy, read the source of the artifact under investigation, and ask whether the failure was already measured with that remedy in force.

A `PreToolUse` hook denied plain shell reads and exempted anything containing a pipe or redirect. Of 47 traced deny→next-call pairs, **19 retried in a shell — 15 of them by adding a pipe.** A discovery plan's highest-priority open question asked whether a deny phrased as a redirect to a named alternative would reduce that rate.

> [!constraint] The two-line read is the argument
> WRONG — the remedy is proposed from the description of the hook:
> ```
> both sampled hooks and the published corpus are silent on wording -> "does a redirect message help?" -> top open question
> ```
> CORRECT — the parked hook's source is opened first, and two lines answer the question:
> ```powershell
> permissionDecision       = 'deny'
> permissionDecisionReason = 'Use the native Read tool instead of a shell command to view this file.
>                             Read returns line numbers, handles images/PDFs/notebooks, and its
>                             offset/limit parameters cover partial views (the head/tail use case).
>                             Shell readers are fine mid-pipeline, but this command is a plain file read.'
> ```
> **That is the treatment arm**, and `permissionDecisionReason` is the *only* channel whose text reaches the model on a deny. **The 15-of-19 pipe-bypass rate was measured under the treatment.** The actual cause sat one line up: `if ($cmd -match '[|><]') { exit 0 }`. **Agents were not resisting the tone; they were exploiting the predicate.**

---

## 6. Why the Mistake Is Easy, and the Four Moves That Prevent It

Before you treat a question as open, read the local artifact, because the silence of a corpus is not evidence about the local system.

> [!constraint] Nothing about it was careless
> The hypothesis was well-formed, correctly prioritised, and honestly researched. **The gap was that "nobody has documented this technique" was allowed to stand in for "nobody has tried this technique."**
>
> WRONG — a true statement about the corpus is read as a statement about the system:
> ```
> no upstream documentation, no guidance in sampled implementations -> the technique is untried -> test whether it helps
> ```
> CORRECT — the local source settles what the corpus cannot:
> ```
> no guidance in the corpus -> open the file the plan cites -> the technique is present -> ask why it did not help
> ```

Four moves prevent the mistake:

- **Open the artifact, not the description of it.** Descriptions record what an artifact is FOR. Only the source records what it DOES.
- **When a hypothesis proposes adding X, ask whether the failure was observed with X present.** If it was, the hypothesis is not "does X help". It is "X did not help here, why not."
- **Distinguish "undocumented" from "untried."** An absence of guidance in a corpus is a statement about the corpus. It says nothing about what the local system already does.
- **Prefer the mechanism you can read over the mechanism you must infer.** When both are available, read first.

---

## 7. A Fallback Recipe Keyed on a Predicted Error String Is a Hypothesis; Fix the Printed Rule

A recipe written before the tool ran is a prediction wearing an instruction's clothes, so when the tool prints its own rule, the printed rule outranks the predicted one. §5 ("Before Proposing a Remedy, Check Whether the Failure Was Already Measured Under It") asks whether the remedy already shipped. This section asks whether the failure the recipe targets is the failure the tool printed.

> [!constraint] Read the refusal for the property it names, and fix that property
> WRONG — the refusal names the function, so the pre-written recipe fires:
> ```
> refusal: "<helper> ... is not a function declared at the top of this file"
> action:  apply the fallback recipe -> bind in the early hook, rewrite 4 helpers to take raw <ctx>
>          (targets "used as a value", which the validator never said)
> ```
> CORRECT — the refusal names a scope rule, so the fix changes scope:
> ```
> refusal: "<helper> ... is not a function declared at the top of this file"
> action:  hoist <helper> to module scope; an <env> parameter replaces its closure
>          (+8 lines, validate passes; mismatch with the design routed as a flag)
> ```

Three consequences follow.

1. **Fix the measured cause.** Read the refusal for the property it names. Choose the smallest edit that changes exactly that property.
2. **Name the trigger text as a hypothesis.** "If the refusal says X, do Y" is fine. "On any refusal naming `<helper>`, do Y" binds Y to refusals Y was never designed for.
3. **Route the mismatch, do not absorb it.** Put the wrong assumption and the new fix shape in a coordination flag to the session that next type-checks or re-validates the file.

**Applies to** any design that pins a fallback to an error string from a tool that has not yet run against the artifact. That covers static scans, linters, schema validators and CLI `validate` subcommands. When you review a "fallback applied" report, ask whether the fix matched the measured text or the anticipated one, and whether the difference was routed downstream.

---

## 8. Break a Would-File Count Down by Category Before Choosing a Remedy

> [!constraint] A headline count is an aggregate, and a remedy chosen against an aggregate treats every unit as the same kind of thing
> Before choosing between remedies, spend one call finding out what the units are. The question is "how many of what". The answer is usually a `Counter` over one path segment.

The first real dry run of a version-watch scan on `<vN> → <vN+1>` reported 686 would-file items against 372 rows of index headroom. The verdict was HALT. The plan had one remedy ready: `<cleanup-script> --target index`, a destructive user-run script that removes every COMPLETE and CLOSED row. The orchestrator framed the choice on the two headline numbers. 686 is "far over any headroom the remedy can create", so the choice was cleanup or nothing. Both halves of that framing were wrong.

Grouping the 686 rows by top-level directory gave `<plans-dir> 573, <docs-dir> 59, <wip-dir> 33, <tooling-dir> 15, <config-dir> 5, <vendored-dir> 1`. One level down, 551 of the 573 sat under `<plan>/**`, and 545 of those were `Results/raw/*.json`. These are frozen output dumps, and each happens to contain a CLI version string. Nobody edits a measurement record when the CLI moves.

Adding `Results` to the scan scope's excluded-directories list (beside `Outputs` and `Reviews`, excluded for the same reason) dropped the count to 135, under the unchanged headroom. The cleanup was never run. A derived JSON file fell from 84.4 MB to 35.6 MB as a side effect.

The capacity claim was also uncounted. 189 of the index's 239 rows were COMPLETE or CLOSED, so the cleanup would have freed roughly 1,080 rows of headroom. The orchestrator had asserted "cannot free enough" without counting. A `Grep` with `output_mode='count'` for `| COMPLETE |` over the index settles it.

> WRONG — choose against the aggregate:
> ```
> 686 would-file > 372 headroom → HALT → the plan's remedy is the cleanup script → ask cleanup-or-nothing
> ```
> CORRECT — break the aggregate down, then choose:
> ```
> Counter(top-level dir) → <plans-dir> 573
> Counter(second level under <plans-dir>/Plans) → <plan> 551 → Results/raw 545
> → 545 of 686 are frozen artifacts → one exclude entry → 135 < 372 → OK, no cleanup
> ```

Three points follow.

- **Group before you decide.** One `Counter` over the first path segment, then over the second for the largest bucket, took under a minute. It changed the remedy class from destructive to one config line.
- **Prefer the exclude that names a category over the remedy that makes room.** Excluding `Results/` states what kind of file is never a work item and holds on every future run. Cleaning the index states how much room there is and buys one run.
- **Do not assert a capacity claim you have not counted.** "The cleanup cannot free 314 rows" reasoned about a script's purpose. It did not count the rows the script would remove.

**Applies to** any gate that compares a count against a capacity, where the remedy on offer is destructive or expensive. That covers index headroom, a token budget, a file-count cap and a review queue. A large bucket of one kind is usually a scope defect, not a capacity problem.

---

## 9. Check That a Proposed Cause Moves the Number in the Observed Direction

> [!constraint] A mechanism recorded for a discrepancy must move the number in the direction observed
> A plausible-sounding unit confusion can predict the opposite sign. If no checked cause fits, record the measured value and write "cause unknown". Do not supply a cause that reads well.

Two runners each found a brief figure larger than the bytes they measured:

| Brief figure | Measured |
|---|---|
| 6,950 for the pre-cut section | 5,510 bytes |
| 83,732 for a sum | 82,984 bytes |

Both runners explained the gap the same way: "the brief's figure is a character count, mislabeled as bytes". That cause cannot be true. A UTF-8 character is one to four bytes, so a span's character count is never larger than its byte count. A character count would sit below the byte figure, not above it. The explanation was recorded in a snapshot, a Recovery row and a ledger before the orchestrator caught it.

> WRONG — a familiar mechanism, recorded without checking its direction:
> ```text
> Brief says 83,732; measured 82,984 bytes. The brief's figure is a char count, not bytes.
> ```
> CORRECT — the direction is checked, and the cause is left open when nothing fits:
> ```text
> Brief says 83,732; measured 82,984 bytes. A char count cannot exceed bytes for UTF-8 text, so
> "char count" does not explain a larger figure. Cause unknown. The measured value stands.
> ```

**Applies to** any reconciliation between a recorded figure and a fresh measurement: byte, character and token counts, row totals and before/after deltas. The rule bites hardest when the explanation is a well-known trap that sounds right at a glance. The byte-versus-character trap itself is in [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) § "5. Every Operand of a Byte Identity Comes From One Byte Instrument". It invites this error.

---

## 10. A Fresh Red Test Is Two Claims — Check Its Premise Before Routing a Module Fix

A new test that goes red claims "the code is wrong" and "this assertion is the right one", so spend one read on the premise before you dispatch a module fix. When the test was written in the same round as the fix, nothing has ever shown the second claim true.

> [!constraint] A new test that goes red claims "the code is wrong" and "this assertion is the right one"
> WRONG — the red assertion is taken as the diagnosis:
> ```
> new test red: 1 == 4 -> "the --report path is broken" -> dispatch a module fix -> retract later
> ```
> CORRECT — the premise is checked first:
> ```
> new test red: 1 == 4 -> what produced 1? (--report, all repair flags on)
>                      -> what produced 4? (plan, no flags)
>                      -> unlike operands -> fix the test, leave the module
> ```

Three operative steps:

- **Ask what each side of the failing assertion measures.** Name the inputs, flags and mode that produced each operand.
- **Read the code at the line the assertion exercises** before calling it broken.
- **Route by what you found.** A wrong premise gets a test fix. Only a confirmed code defect gets a module fix, and the dispatch names the line that is wrong.

The general question, which side is wrong before a fix is routed, belongs to [`verify-verdict-source.md`](verify-verdict-source.md) §8: classify the failure by cause from primary evidence, and keep an instrument fix apart from a subject finding.

**Report the diagnosis as provisional.** Before this check, tell the user "the new test fails at X; checking whether the test or the code is wrong". A confident wrong diagnosis costs a retraction.

**Applies to** orchestrators reading a runner's newly written failing test, failing-first fix rounds, and any assertion that compares the outputs of two entry points or configurations: report versus write, all flags versus none, dry-run versus write.

---

*Cross-reference: [`verify-verdict-source.md`](verify-verdict-source.md) (a verdict versus the source it re-read — the other question asked of the same artifact) · [`task-content-fidelity.md`](task-content-fidelity.md) (a count beside a list is a cache with no invalidation) · [`backlog-triage-pivot-detection.md`](backlog-triage-pivot-detection.md) (the triage-time check that an item's premise still holds) · [`measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md`](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8 D (search for the instruction that regenerates the defect, not only for its instances)*
