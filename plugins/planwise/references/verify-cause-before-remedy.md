---
description: Count the population before naming a cause, and check whether the failure was already measured under the remedy you are proposing. Covers why a contradiction between two representations of one fact is evidence about the writers, why the plausible per-instance story stops you counting, the six-step procedure when two representations disagree, why the within-file duplicate hides longest, the treatment-arm check before proposing a remedy, the four moves that keep "undocumented" from standing in for "untried", and why a fallback recipe keyed on a predicted error string is a hypothesis and the printed rule is what gets fixed. Consult before naming a cause from one observed instance, before filing or routing a remedy, before pinning a fallback to a tool message the tool has not yet printed, and whenever a hypothesis proposes adding something to a system whose failure you are explaining, before choosing a remedy against a headline count that no one has grouped by category, and before recording a mechanism for a figure discrepancy without checking that it moves the number in the observed direction. Also covers why a would-file count is broken down by path segment before a destructive remedy is chosen, and why an unchecked "character count mislabeled as bytes" explanation predicts the wrong sign. Also covers why a fresh red test makes two claims (the code is wrong, and this assertion is the right one) and why its premise is checked, by naming what each operand measures and reading the code at the asserted line, before a module fix is routed.
paths: {planwise_root}/{plans_dir}/**
---
# Verify the Cause Before the Remedy — Count the Population; Check Whether the Remedy Already Shipped

**Purpose:** Two diagnoses, both plausible, both wrong, and both cheap to refute by opening the artifact rather than its description. One read a single contradictory record as a one-off human error and wrote that reading into an index footer as established fact. Counting took one loop: the "one-off" was **1 of 52**, and the real cause was a writer that had never once synced the second copy. The other proposed a remedy as its highest-priority open question, correctly establishing that no upstream documentation and neither sampled production implementation offered guidance on it — while the artifact under investigation had **already implemented that exact remedy**, and the failure rate the investigation existed to explain had been measured with it in force.

**Read this when** you are about to name a cause from one observed instance, file or route a remedy, or write a hypothesis that proposes adding something to the system whose failure you are explaining.

The two share a mechanism. A plausible per-instance story is precisely the thing that stops you counting, and "nobody has documented this technique" is allowed to stand in for "nobody has tried this technique." Both produce a remedy indistinguishable from the current state, and both displace attention from the real cause — in the second case four independent findings had to converge before the true defect was named, and three of them were about the wrong thing.

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

> [!constraint] The instance carries no information about whether it is unique; only the population does
> When one fact has two representations, whether they agree is a property of the **writers**: if both are written by the same code path, they cannot disagree; if they disagree even once, some path writes one and not the other — and **that path will have run on every record that passed through it.** So *"this one record is inconsistent"* is not a finding about the record — it is an unfalsified hypothesis about the writers, and the cheapest way to test it is to count.
>
> Closing a backlog item set its index row and frontmatter to `COMPLETE` while its body still read `**Status:** PLANNING`, because item files carry status **twice** — once as YAML frontmatter, once as a `**Status:**` display line — and the update script wrote the body copy only in its *create* path (`_render_bli_file()`). The update path synced frontmatter alone; its own output said so: `YAML status synced: {file}`. The same contradiction had been seen before, on a single item, and written into the index footer as a diagnosis:
>
> > *"…whose own status is self-contradictory: frontmatter/index/`Archive/` say COMPLETE but its body reads `NOT_STARTED` with all acceptance criteria unchecked and an open-decisions section — **likely opened-then-mis-archived**; reconcile its true state separately"*
>
> Counting the population took one loop:
>
> ```
> archived items: 61 | with a body **Status:** line: 61 | body disagrees with frontmatter: 52
> ```
>
> Not a mis-archive. **1 of 52.**

The same loop that took one command turned a human-error story into a broken-writer finding. A paraphrase ("most items were affected") removes the reader's ability to see how cheap the test was.

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

> [!practice] Both copies in one file read as one statement, and a disagreement looks like a typo
> This is the within-file member of a class fixed three times across files — a plans-index row, a backlog-index archival link, and a lessons-index next-ID counter, each a denormalized copy with exactly one writer and no read-side reconciliation. **The cross-file instances were caught because a reader compared a cache against its source. The within-file instance survived longer precisely because both copies sit in the same file, where they read as one statement rather than two, and where a disagreement looks like a typo instead of a broken pipeline.**

Nothing in the reasoning depends on the artifact being a status field. It applies to any duplicated fact — a count restated in a header and a table, a version in two manifests, a threshold quoted in a rule and in the gate that enforces it. A reader who treats the rule as being about cross-file caches has kept only the instances that were already caught.

---

## 5. Before Proposing a Remedy, Check Whether the Failure Was Already Measured Under It

> [!constraint] The two-line read is the argument
> A `PreToolUse` hook was built to stop agents reading files through the shell: it denied plain reads and exempted anything containing a pipe or redirect. Measured over two days it fired 48 times, and of 47 traced deny→next-call pairs, **19 retried in a shell — 15 of them by adding a pipe.** A discovery plan was opened to work out what to do instead, and one hypothesis became its highest-priority open question: *does phrasing a deny as a redirect to a named alternative reduce the retry-as-workaround rate, compared with a bare prohibition?* Both sampled production hooks were silent on message wording, the published corpus documented none, and every deny example in it was a bare statement of what was blocked.
>
> Late in the plan, someone opened the parked hook's source. Two lines:
>
> ```powershell
> permissionDecision       = 'deny'
> permissionDecisionReason = 'Use the native Read tool instead of a shell command to view this file.
>                             Read returns line numbers, handles images/PDFs/notebooks, and its
>                             offset/limit parameters cover partial views (the head/tail use case).
>                             Shell readers are fine mid-pipeline, but this command is a plain file read.'
> ```
>
> **That is the treatment arm** — a redirect, naming the alternative, with a rationale and an honest exception. The same plan had separately proved, by an A/B with distinct sentinel tokens on each channel, that `permissionDecisionReason` is the *only* channel whose text reaches the model on a deny. So it was not merely written; it was delivered and read. **The 15-of-19 pipe-bypass rate was measured under the treatment.** And the actual cause sat one line up in the same file — `if ($cmd -match '[|><]') { exit 0 }`. The 15 retries that added a pipe were routing around that exemption. **Agents were not resisting the tone; they were exploiting the predicate.**

The proposed remedy was not merely present but well-executed. A summarised version of the two lines reads as though a better message might still have helped, which is why they ship verbatim.

---

## 6. Why the Mistake Is Easy, and the Four Moves That Prevent It

> [!constraint] Nothing about it was careless
> The hypothesis was well-formed, correctly prioritised, and honestly researched — the team established that no upstream documentation and neither sampled production implementation offered guidance on deny-message wording, which is *true* and made the question look genuinely open. **The gap was that "nobody has documented this technique" was allowed to stand in for "nobody has tried this technique."** The artifact under investigation had tried it, and the evidence was a two-line read of a file the plan referenced by path in a dozen places and had never opened for this purpose.
>
> ```
> - Open the artifact, not the description of it. A backlog item, a baseline
>   table, and a plan's prose all described this hook. None quoted the two
>   lines that mattered. Descriptions record what an artifact is FOR; only
>   the source records what it DOES.
> - When a hypothesis proposes adding X, ask whether the failure was observed
>   with X present. If it was, the hypothesis is not "does X help" — it is
>   "X did not help here, why not." A different and more productive question.
> - Distinguish "undocumented" from "untried." An absence of guidance in a
>   corpus is a statement about the corpus. It says nothing about what the
>   local system already does.
> - Prefer the mechanism you can read over the mechanism you must infer.
>   The pipe exemption was a visible one-line predicate; the message-effect
>   hypothesis required a behavioural experiment. When both are available,
>   read first.
> ```

The exculpation comes first because a rule a reader believes is about carelessness will be filed as not-applicable-to-me, and the incident's defining feature is that the research was correct and the inference from it was not. The cost asymmetry closes it: reading the artifact costs minutes, while shipping a remedy already in force costs a cycle and produces a result **indistinguishable from the current state** — and worse, displaces attention from the real cause.

---

## 7. A Fallback Recipe Keyed on a Predicted Error String Is a Hypothesis; Fix the Printed Rule

> [!constraint] A recipe written before the tool ran is a prediction wearing an instruction's clothes
> It carries the same authority as a spec step, and a runner has no reason to doubt it. That holds until the tool prints its own rule. At that moment the printed rule outranks the predicted one. The fix has to satisfy the validator that exists, not the one the design imagined. §5 ("Before Proposing a Remedy, Check Whether the Failure Was Already Measured Under It") asks whether the remedy already shipped. This section asks whether the failure the recipe targets is the failure the tool printed.

A module design pinned an assumption about a validator that had never run on the module. The design said the static scan would refuse a closure table over `<ctx>` with the text `"<ctx>.<noun> is used as a value"`. It wrote a fallback recipe for that refusal: move the bind into the early hook, and spell `<ctx>` calls in-hook for the hooks that can fire earlier. The task file made the recipe binding: "on a refusal naming `<helper>`, apply the fallback".

The validator refused the file on the first run, naming `<helper>`. Its text was a different rule: `<ctx> is passed to "<helper>", which is not a function declared at the top of this file (a function declaration, or a const bound to one)`. The refusal was about the declaration's scope, because `<helper>` was nested inside `register()`. It was not about `<ctx>` being used as a value.

The recipe's restructuring would have rewritten every helper the early-firing hook calls to take raw `<ctx>`. That is a far larger change than the refusal asked for, aimed at a rule the validator did not state. The runner applied the fix the measured text asked for. It hoisted `<helper>` to module scope and replaced its one closure with an `<env>` parameter. The change was eight lines, with fifteen call sites gaining one argument and no hook body changed. Validation passed on the next run.

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

1. **Fix the measured cause.** Read the refusal for the property it names (here, declaration scope). Choose the smallest edit that changes exactly that property. Applying the pre-written recipe because it is "the fallback" fixes a rule nobody observed.
2. **Name the trigger text as a hypothesis.** "If the refusal says X, do Y" is fine. "On any refusal naming `<helper>`, do Y" binds Y to refusals Y was never designed for.
3. **Route the mismatch, do not absorb it.** The design's assumption is now known wrong, and the fix has a shape the design did not anticipate. Put both in a coordination flag to the session that next type-checks or re-validates the file. That session then checks the hoisted shape against the real declarations instead of assuming it sound.

**Applies to** any design that pins a fallback to an error string from a tool that has not yet run against the artifact. That covers static scans, linters, schema validators and CLI `validate` subcommands. When you review a "fallback applied" report, ask whether the fix matched the measured text or the anticipated one, and whether the difference was routed downstream.

---

## 8. Break a Would-File Count Down by Category Before Choosing a Remedy

> [!constraint] A headline count is an aggregate, and a remedy chosen against an aggregate treats every unit as the same kind of thing
> Before choosing between remedies, spend one call finding out what the units are. The question is "how many of what". The answer is usually a `Counter` over one path segment.

The first real dry run of a version-watch scan on `<vN> → <vN+1>` reported 686 would-file items against 372 rows of index headroom. The verdict was HALT. The plan had one remedy ready: `<cleanup-script> --target index`, a destructive user-run script that removes every COMPLETE and CLOSED row. The orchestrator framed the choice on the two headline numbers. 686 is "far over any headroom the remedy can create", so the choice was cleanup or nothing. Both halves of that framing were wrong.

Grouping the 686 rows by top-level directory gave `<plans-dir> 573, <docs-dir> 59, <wip-dir> 33, <tooling-dir> 15, <config-dir> 5, <vendored-dir> 1`. One level down, 551 of the 573 sat under `<plan>/**`, and 545 of those were `Results/raw/*.json`. These are frozen output dumps, and each happens to contain a CLI version string. Nobody edits a measurement record when the CLI moves.

Adding `Results` to the scan scope's excluded-directories list (beside `Outputs` and `Reviews`, excluded for the same reason) dropped the count to 135, under the unchanged headroom. The cleanup was never run. A derived JSON file fell from 84.4 MB to 35.6 MB as a side effect.

The capacity claim was also uncounted. 189 of the index's 239 rows were COMPLETE or CLOSED, so the cleanup would have freed roughly 1,080 rows of headroom. The orchestrator had asserted "cannot free enough" without counting. A `Grep` with `output_mode='count'` for `| COMPLETE |` over the index settles it.

> ```
> WRONG — choose against the aggregate:
> 686 would-file > 372 headroom → HALT → the plan's remedy is the cleanup script → ask cleanup-or-nothing
>
> CORRECT — break the aggregate down, then choose:
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

> ```text
> WRONG — a familiar mechanism, recorded without checking its direction:
> Brief says 83,732; measured 82,984 bytes. The brief's figure is a char count, not bytes.
>
> CORRECT — the direction is checked, and the cause is left open when nothing fits:
> Brief says 83,732; measured 82,984 bytes. A char count cannot exceed bytes for UTF-8 text, so
> "char count" does not explain a larger figure. Cause unknown. The measured value stands.
> ```

**Applies to** any reconciliation between a recorded figure and a fresh measurement: byte, character and token counts, row totals and before/after deltas. The rule bites hardest when the explanation is a well-known trap that sounds right at a glance. The byte-versus-character trap itself is in [`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) § "5. Every Operand of a Byte Identity Comes From One Byte Instrument". It invites this error.

---

## 10. A Fresh Red Test Is Two Claims — Check Its Premise Before Routing a Module Fix

> [!constraint] A new test that goes red claims "the code is wrong" and "this assertion is the right one"
> When the test was written in the same round as the fix, nothing has ever shown the second claim true. Before you dispatch a module fix for a fresh red test, spend one read on the premise.

**Worked case.** A fix round added a test asserting that the migrator reports every refusal in one run. The suite showed `assert len(report["would_refuse"]) == len(exc.value.items)` as `1 == 4`. The orchestrator told the user the `--report` path was still broken and sent the runner a module fix. The runner returned a collision note instead. The report builder plans with every repair flag on, so every flag-closable refusal is closed and exactly one survives. The module already enumerated every refusal item. The test compared an all-flags report against a no-flag plan's four items. A test-only fix closed it, and the orchestrator retracted its diagnosis twice.

Three operative steps:

- **Ask what each side of the failing assertion measures.** Name the inputs, flags and mode that produced each operand. The `1 == 4` failure compared two configurations, and that was visible from the two call sites without running anything.
- **Read the code at the line the assertion exercises** before calling it broken. Two lines settled the worked case.
- **Route by what you found.** A wrong premise gets a test fix. Only a confirmed code defect gets a module fix, and the dispatch names the line that is wrong.

```
# WRONG — the red assertion is taken as the diagnosis:
new test red: 1 == 4 -> "the --report path is broken" -> dispatch a module fix -> retract later

# CORRECT — the premise is checked first:
new test red: 1 == 4 -> what produced 1? (--report, all repair flags on)
                     -> what produced 4? (plan, no flags)
                     -> unlike operands -> fix the test, leave the module
```

**Report the diagnosis as provisional.** Before this check, tell the user "the new test fails at X; checking whether the test or the code is wrong". A confident wrong diagnosis costs a retraction.

**Applies to** orchestrators reading a runner's newly written failing test, failing-first fix rounds, and any assertion that compares the outputs of two entry points or configurations: report versus write, all flags versus none, dry-run versus write.

---

*Cross-reference: [`verify-verdict-source.md`](verify-verdict-source.md) (a verdict versus the source it re-read — the other question asked of the same artifact) · [`task-content-fidelity.md`](task-content-fidelity.md) (a count beside a list is a cache with no invalidation) · [`backlog-triage-pivot-detection.md`](backlog-triage-pivot-detection.md) (the triage-time check that an item's premise still holds) · [`measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md`](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8 D (search for the instruction that regenerates the defect, not only for its instances)*
