---
description: A finding is scoped to the sample it was taken from, the project it was measured in, and the corpus that was searched — and the sentence that states it has to carry that boundary. Covers why one dispatch is an anecdote and how to sample without cherry-picking, why a hypothesis about a consuming project cannot be settled in the tool's own repository, why "the record does not capture X" is true only of the shelf that was swept, and the three sentence forms that keep the boundary attached. Consult when measuring model or harness behaviour, testing a hypothesis whose magnitude lives outside the tool, or accepting an evidence-gap statement. Also covers why a column that reads the same value before the first boundary measures the floor every session pays, and must be baselined before arms are compared on it.
consult-when: Measuring model or harness behaviour, testing a hypothesis whose magnitude lives in a consuming project, or accepting "the record does not capture X" — declare n per cell, classify the hypothesis, enumerate the record-keeping layers, write the boundary into the sentence, and baseline a column that reads the same before the first boundary because it measures the floor every session pays, and scope a negative to the invocation that produced it and read an under-run cost as a broken chain (§6)
paths: {planwise_root}/{plans_dir}/**
---
# Measurement Scope and Sample — Write the Boundary Into the Sentence

**Purpose:** A finding is scoped to **how many runs, which project, which shelf was searched**. Each section below covers one boundary that drops out. In every case a scoped observation was written down as an unscoped conclusion, and nothing in the sentence marked the change.

**Read this when** you are about to dispatch a probe and call its result a baseline, test a hypothesis whose answer could change with the consuming project, accept a task's report that something "is not recorded", or write any of those three findings into a sentence a downstream reader will act on.

The underlying work can be sound and the defect still lands. It enters at the moment a *finding* becomes a *verdict*, which is a sentence-level event that no verification gate is watching.

[`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 requires three or more observations on any surface a plan intends to call deterministic. §1 below is the general form: why one observation is never a baseline, and how to sample without cherry-picking.

A task that builds or operates the measurement harness itself reads [`harness-instrument-integrity.md`](harness-instrument-integrity.md): validate the instrument against live artifacts, couple every duplicated fact, and route every terminal state.

## Table of Contents

- [1. A Single Observation of Model or Harness Behaviour Is an Anecdote, Never a Baseline](#1-a-single-observation-of-model-or-harness-behaviour-is-an-anecdote-never-a-baseline)
- [2. Classify a Hypothesis as Tool-Intrinsic or Consumer-Conditional Before Testing It](#2-classify-a-hypothesis-as-tool-intrinsic-or-consumer-conditional-before-testing-it)
- [3. An Evidence Gap Is Scoped to the Corpus You Swept — Enumerate the Record-Keeping Layers First](#3-an-evidence-gap-is-scoped-to-the-corpus-you-swept--enumerate-the-record-keeping-layers-first)
- [4. Write the Boundary Into the Sentence](#4-write-the-boundary-into-the-sentence)
- [5. A Column That Reads the Same Before the Boundary Measures the Floor — Baseline It](#5-a-column-that-reads-the-same-before-the-boundary-measures-the-floor--baseline-it)
- [6. A Negative Is Scoped to the Invocation That Produced It](#6-a-negative-is-scoped-to-the-invocation-that-produced-it)

---

## 1. A Single Observation of Model or Harness Behaviour Is an Anecdote, Never a Baseline

> [!constraint] State the intended n per cell, and dispatch all n before looking at any result
> A single dispatch always produces a clean-looking datum. Nothing in the output announces that a second run would have said something else. The same byte-identical prompt, dispatched three times, produced 3, 0 and 2 shell calls that changed directory. A matrix of *N* one-shot cells is *N* chances for this to go unnoticed, and every cell will look like data.
>
> The anti-cherry-picking rule is right: re-running until you like the answer is selection bias. Conflating it with "run once" **silently sets the sample size to one**. **State the intended n per cell explicitly and dispatch all n unconditionally, before looking at any result.** Cherry-picking is choosing which runs to *keep* after seeing them, not running more than once.
>
> WRONG — the anti-selection rule read as "sample once", and the cell hides its uncertainty:
> ```
> "Do not re-roll for a better answer"  →  n = 1
> cell: "used the shell"
> ```
> CORRECT — n declared before dispatch, every run kept, and the count in the cell:
> ```
> n = 3 per cell, all dispatched before any result is read
> cell: "2 of 3 runs used the shell"
> ```

- **Replicate on a byte-identical input.** Recover the prompt verbatim from its transcript, and confirm it by comparing the first `type:"user"` record of both transcripts. A prompt reconstructed from a description destroys the identical-input property.
- **Validating the instrument is not validating the measurement.** A parser proven correct against a fixed transcript says nothing about whether re-running the process reproduces that transcript. These are two separate gates. The first is much easier, so it tends to be mistaken for both.
- **When a prior figure will not replicate, that is a finding about the premise — report it as one.** Do not reconcile it away, and do not treat non-reproduction as a defect in the re-measurement.

This is the section most likely to be cut for cost, because its remedy multiplies dispatch count. The cheapest replication, the same input twice, exposes a premise that does not reproduce before any matrix is designed.

---

## 2. Classify a Hypothesis as Tool-Intrinsic or Consumer-Conditional Before Testing It

> [!constraint] Ask what would have to change for the answer to change — if the answer is "something in a consuming project", one project cannot settle it
> The two classes are indistinguishable on the page:
>
> | Class | Example | What settles it |
> |---|---|---|
> | **Tool-intrinsic** | "the handler loads its references unconditionally" | A property of the artifact. One correct measurement settles it everywhere. |
> | **Consumer-conditional** | "path-scoped rules inflate consumption" | The tool supplies the *mechanism*. The consuming project supplies the *magnitude*. Measuring the tool's repository measures one sample of a variable that lives outside the tool. |
>
> **The tool's own repository is always the most convenient project to measure, and it is systematically the least representative.** Its rules are scoped to plugin-authoring paths. A project that uses the tool for application work accumulates domain rules on other paths. **A false REFUTED closes a line of inquiry permanently**, because nobody re-opens a hypothesis marked settled.
>
> WRONG — one project measured, and the verdict written for every project:
> ```
> path-scoped rules inflate consumption: REFUTED
>   (tool repository: 8 rule files, 1,705 lines, zero scoped to the plan tree)
> ```
> CORRECT — the verdict names the deciding property:
> ```
> path-scoped rules inflate consumption: PROJECT-CONDITIONAL
>   refuted in the tool repository (1,705 lines, 30% of sessions affected)
>   confirmed in a consuming project (6,273 lines, 96% of sessions, +91,718 tokens in one turn)
> ```

Two reporting rules:

- **Report the range, not a representative value.** 1,705 vs 6,273 lines and 30% vs 96% incidence *are* the finding. An average across two projects would describe neither.
- **A per-project config constant is a measurement of one project even when the tool ships the key.** Two projects carried overhead calibrations of 29,500 and 48,000 on the same date. Both were correctly measured, and neither generalises.

---

## 3. An Evidence Gap Is Scoped to the Corpus You Swept — Enumerate the Record-Keeping Layers First

> [!constraint] A project's planning artifacts and its harness's logs are different corpora with different authors
> The artifacts record what a session *believed and decided*. The logs record what the runtime *actually did*. A sweep of one is silent about the other, but an evidence-gap statement rarely says so — **it reads as a statement about the world, not about the shelf that was searched.**
>
> Before accepting any "the record does not capture X", enumerate the record-keeping layers and name which were swept and which were not:
>
> 1. the project's own artifacts;
> 2. the harness's session transcripts (`~/.claude/projects/**/*.jsonl`);
> 3. tool and CLI state and caches;
> 4. the version-control history.
>
> WRONG — a true finding about one shelf restated as a verdict about the history:
> ```
> swept: 149 planning artifacts, one figure found
> "The history cannot quantify this."
> ```
> CORRECT — the finding keeps its shelf, and the unswept layers are named:
> ```
> "No artifact records an orchestrator-window total."
> not swept: harness transcripts, tool and CLI state, version-control history
> ```

**A gap statement is load-bearing downstream.** It licenses fallback conclusions ("if we can't measure it, the figure is probably an accounting artifact"), and those inherit the unexamined scope. Three operative rules:

- **Write gap statements with their scope in the sentence.** "The planning artifacts do not record X", never the unscoped "X is not recorded".
- **Treat a gap statement as a dispatch trigger, not a conclusion.** When a task returns "cannot be quantified from my corpus", the next question is *which corpus would carry it*, asked before any downstream synthesis consumes the gap.
- **Suspect the gap hardest when the question is about runtime behaviour.** A runtime measures token consumption, latency, tool-call counts and context growth continuously. A document records them only if someone chose to. So the absence of a *written* figure is weak evidence about a *measured* one.

**Sweep the harness corpus by streaming, never by reading.** These files run to hundreds of megabytes, and a whole-file read fails the task outright. Write an aggregation script and run it.

**When the new corpus lands, stop the downstream work rather than let it finish.** A synthesis primed on a refuted premise does not partially recover.

§2 and §3 look like one section and are not. §2's fix is to **measure a second instance** (another project) and return a conditional verdict. §3's fix is to **search a different shelf** (another corpus) before concluding anything is unmeasurable. A merged section collapses to "consider your scope", which supplies neither action.

---

## 4. Write the Boundary Into the Sentence

> [!practice] Every finding above was correct, and became wrong by losing a qualifier the author knew at the time
> Write the sample size, the project boundary and the corpus boundary into the sentence that states the finding. A downstream reader needs the discriminator, not the conclusion.
>
> WRONG — each sentence drops its qualifier:
> ```
> sample size: "the agent used the shell"
> project:     "refuted"
> corpus:      "X is not recorded"
> ```
> CORRECT — each sentence carries its boundary:
> ```
> sample size: "2 of 3 runs used the shell"
> project:     "refuted where the rule surface is under ~2K lines and unscoped to plan paths; confirmed where it exceeds ~6K"
> corpus:      "the planning artifacts do not record X; the harness transcripts were not swept"
> ```

---

## 5. A Column That Reads the Same Before the Boundary Measures the Floor — Baseline It

> [!constraint] A figure that already appears before the first boundary is the floor every session pays
> A mechanism cannot be credited with carrying a figure that the session read before the mechanism existed. A number the mechanism cannot change is not evidence about the mechanism. Compare each arm against the pre-boundary first call, the control that cannot have the property, before crediting the arm with the figure.

A ledger's `carry` column is the first call's cached-prefix read after each boundary. It read 39,383 for compaction, auto-compaction and a clear into a fresh session id. The original session's first call, before any boundary existed, read 39,383 too. A clear starts from nothing, so the figure is the cache hit on the static prefix: system prompt, tool schemas, project instructions and plugin context.

> ```
> WRONG — the design reads carry as preserved state and compares arms on it:
> compaction:  carry 39383 × 3   → "carries 39K across each boundary"
> /clear:      carry 39383 × 3   → "carries 39K across each clear"   ← a clear preserves nothing
>
> CORRECT — the pre-boundary first call fixes the floor, and the arms are compared on what moved:
> original session, call 1: read 39383      → static-prefix floor = 39383
> compaction:  carry − floor = 0, rebuild 14.8K / 13.4K / 13.8K
> /clear:      carry − floor = 0, rebuild  2.6K /  2.5K /  2.7K
> ```

Three consequences follow.

1. **Baseline the column on the pre-boundary first call.** Print the baseline in the ledger header and report `carry − baseline`. Zero is the honest reading for a mechanism that starts fresh.
2. **Name the substrate the metric can see.** A metric that reads identically across compaction, auto-compaction and a fresh session id measures their shared substrate, not any one of them. Say which substrate in the column's definition.
3. **Route the comparison to the columns that moved.** Rebuild (creation on the first post-boundary call) and true post-context are where a boundary choice shows its cost. Here they differed five-fold: 2.6K for the clear and 13K to 15K for compaction. A write-up that ranks mechanisms on carry ranks them on their prompt cache.

The general control-session test, for any figure or column, is stated once in [`measure-from-the-record.md`](measure-from-the-record.md) §5.

---

## 6. A Negative Is Scoped to the Invocation That Produced It

> [!constraint] A negative result is true of the exact invocation that produced it
> An error text that names the modes where an API would bind scopes the negative to the modes it does not name. Do not generalize "this failed under print mode" to "this fails headless". Name the invocation (`-p`, `-p --input-format stream-json`, an SDK-built session) in the sentence that records the result.

A deferred call threw `no session is bound in this process`. The error text named two modes where the API binds: the interactive REPL, and a built headless session. A print-mode run (`<cli> -p`) is neither, because it answers one prompt and exits. A session built through the SDK, and `-p --input-format stream-json` with one process held open, are separate questions. The honest sentence is "failed under `-p`".

**An under-run cost is a signal, not a saving.** A cost estimate for a chained run assumes the chain. A healthy `num_turns` and `is_error: false` do not show that the chain ran. Report the cost beside its cause. Treat a large under-run as evidence that the chain broke.

> [!constraint] Name the invocation in the result sentence
> WRONG — the scope drops out of the sentence, and a later design reads it as a ruling on every headless mode:
> ```
> deferred boundary: FAIL, does not work headless
> cost: 0.68 USD (under budget)
> ```
> CORRECT — the invocation stays attached, and the cost carries its cause:
> ```
> deferred boundary: FAIL under `<cli> -p` (error names the REPL and a built headless session; -p is neither)
> NOT TESTED: -p --input-format stream-json, an SDK-built session
> cost: 0.68 USD against a 3-4 USD estimate — the chain stopped after step 1
> ```

**Applies to** probe designs that ask "does X survive headless", cost estimates for chained runs, and any hook or plugin that schedules work for "after the answer".

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 (three or more observations on any surface a plan calls deterministic) · [`session-context-budget.md`](session-context-budget.md) § Read-Tool Hard Limits (why a harness transcript must be streamed, never read whole) · [`token-saver-profile.md`](token-saver-profile.md) (the consumption band the §3 corpus produced)*
