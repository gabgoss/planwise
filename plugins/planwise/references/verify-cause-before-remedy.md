---
description: Count the population before naming a cause, and check whether the failure was already measured under the remedy you are proposing. Covers why a contradiction between two representations of one fact is evidence about the writers, why the plausible per-instance story stops you counting, the six-step procedure when two representations disagree, why the within-file duplicate hides longest, the treatment-arm check before proposing a remedy, and the four moves that keep "undocumented" from standing in for "untried". Consult before naming a cause from one observed instance, before filing or routing a remedy, and whenever a hypothesis proposes adding something to a system whose failure you are explaining.
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

*Cross-reference: [`verify-verdict-source.md`](verify-verdict-source.md) (a verdict versus the source it re-read — the other question asked of the same artifact) · [`task-content-fidelity.md`](task-content-fidelity.md) (a count beside a list is a cache with no invalidation) · [`backlog-triage-pivot-detection.md`](backlog-triage-pivot-detection.md) (the triage-time check that an item's premise still holds) · [`measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md`](measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md) §8.8 D (search for the instruction that regenerates the defect, not only for its instances)*
