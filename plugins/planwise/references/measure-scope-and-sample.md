---
description: A finding is scoped to the sample it was taken from, the project it was measured in, and the corpus that was searched — and the sentence that states it has to carry that boundary. Covers why one dispatch is an anecdote and how to sample without cherry-picking, why a hypothesis about a consuming project cannot be settled in the tool's own repository, why "the record does not capture X" is true only of the shelf that was swept, and the three sentence forms that keep the boundary attached. Consult when measuring model or harness behaviour, testing a hypothesis whose magnitude lives outside the tool, or accepting an evidence-gap statement.
paths: {planwise_root}/{plans_dir}/**
---
# Measurement Scope and Sample — Write the Boundary Into the Sentence

**Purpose:** Three findings, each correctly measured and each stated as though it described the world rather than the slice it was taken from. The boundary that was dropped differs — **how many runs, which project, which shelf was searched** — but the failure is identical in shape and in consequence: a scoped observation was written down as an unscoped conclusion, and nothing in the sentence marked the transition.

**Read this when** you are about to dispatch a probe and call its result a baseline, test a hypothesis whose answer could change with the consuming project, accept a task's report that something "is not recorded", or write any of those three findings into a sentence a downstream reader will act on.

What makes the class dangerous is that the underlying work was good in all three cases. The sweeps were thorough, the reasoning was sound, the numbers were right. The defect enters at the moment a *finding* becomes a *verdict*, which is a sentence-level event that no verification gate is watching. And each of the three then licensed a downstream decision: a matrix design, a closed line of inquiry, a remediation aimed at the wrong problem.

One neighbouring rule owns a corollary this file generalises. [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 requires three or more observations on any surface a plan intends to call deterministic. §1 below is the general form: why one observation is never a baseline, and how to sample without cherry-picking.

## Table of Contents

- [1. A Single Observation of Model or Harness Behaviour Is an Anecdote, Never a Baseline](#1-a-single-observation-of-model-or-harness-behaviour-is-an-anecdote-never-a-baseline)
- [2. Classify a Hypothesis as Tool-Intrinsic or Consumer-Conditional Before Testing It](#2-classify-a-hypothesis-as-tool-intrinsic-or-consumer-conditional-before-testing-it)
- [3. An Evidence Gap Is Scoped to the Corpus You Swept — Enumerate the Record-Keeping Layers First](#3-an-evidence-gap-is-scoped-to-the-corpus-you-swept--enumerate-the-record-keeping-layers-first)
- [4. Write the Boundary Into the Sentence](#4-write-the-boundary-into-the-sentence)

---

## 1. A Single Observation of Model or Harness Behaviour Is an Anecdote, Never a Baseline

> [!constraint] The same byte-identical prompt, dispatched three times, produced 3, 0 and 2 `cd`-bearing shell calls
> An entire discovery plan rested on one measurement. Of three probe agents dispatched with prompts naming no tools, the one two-question probe failed with **3 shell calls, all carrying `cd`**, and from that the plan drew its central hypothesis — *task shape, not command text, predicts tool-discipline failure* — and built a probe matrix to test it. When a regression suite re-dispatched the failing prompt, it made **1 shell call with zero `cd`**. The control arm replayed it again: **2 `cd`-bearing calls**. Three runs, three readings — 3, 0, 2.
>
> The prompt was verified byte-identical, and without that verification the reading is "two different prompts" and the whole finding evaporates. It was recovered verbatim from its transcript rather than reconstructed from a description, because reconstructing it would silently destroy the identical-input property, and it was confirmed by comparing the first `type:"user"` record of both transcripts, wrapper and sender attribute included.
>
> **A single dispatch always produces a clean-looking datum.** One run, one tool sequence, one verdict; nothing about the output announces that a second run would have said something else. A matrix of *N* one-shot cells is *N* independent opportunities for this to go unnoticed, and every cell will look like data.
>
> ```
> "Do not re-roll for a better answer"  ≠  "Sample once"
> ```
>
> The anti-cherry-picking rule is right — re-running until you like the answer is selection bias — but conflating it with "run once" **silently sets the sample size to one**. The resolution is to **state the intended n per cell explicitly and dispatch all n unconditionally, before looking at any result.** That preserves the anti-selection property while giving a sample, because cherry-picking is choosing which runs to *keep* after seeing them, not running more than once.
>
> A cell reading **"2 of 3 runs used the shell"** carries its own uncertainty; one reading "used the shell" hides it.
>
> **Validating the instrument is not validating the measurement.** The scorer was never in question, and that is the trap: it read the original transcript correctly every time, because a transcript is a fixed artifact and parsing it is deterministic. A parser proven correct against a fixed artifact tells you nothing about whether re-running the underlying process reproduces that artifact. These are two separate gates, and the first is much easier, so it tends to be mistaken for both.
>
> **When a prior figure will not replicate, that is a finding about the premise — report it as one.** Do not reconcile it away, and do not treat non-reproduction as a defect in the re-measurement.

This is the section most likely to be cut for cost, because its remedy multiplies dispatch count. The cheapest possible replication — the same input, twice — is what would have exposed the incident before any matrix was designed. The alternative is not cheaper. It is a matrix of cells that cannot be compared honestly.

---

## 2. Classify a Hypothesis as Tool-Intrinsic or Consumer-Conditional Before Testing It

> [!constraint] Ask what would have to change for the answer to change — if the answer is "something in a consuming project", one project cannot settle it
> The two classes are indistinguishable on the page:
>
> | Class | Example | What settles it |
> |---|---|---|
> | **Tool-intrinsic** | "the handler loads its references unconditionally" | A property of the artifact. One correct measurement settles it everywhere. |
> | **Consumer-conditional** | "path-scoped rules inflate consumption" | The tool supplies the *mechanism*; the consuming project supplies the *magnitude*. Measuring the tool's repository measures one sample of a variable that lives outside the tool. |
>
> A hypothesis held that path-scoped auto-injected rules were inflating session token consumption. A static-analysis task tested it against the tool's own repository and refuted it cleanly: 8 rule files, **1,705 lines**, and decisively **zero** scoped to the plan tree, so ordinary plan work triggers no injection at all — with the orchestrator independently measuring the same surface and reaching the same number. Two confirmations, correctly reasoned, hypothesis apparently closed. Then a second project entered the corpus: same plugin, same Token Saver settings, same 1M window, also 8 rule files — but **6,273 lines**, 3.7× larger. Its transcripts showed the single largest attributable jump anywhere in the corpus, **+91,718 tokens in one turn** from 96,066 tokens of rule content, affecting **96%** of that project's sessions against 30% in the tool's repository and averaging **56,360 tokens per affected session** — and it was the causal mechanism behind a recorded "Prompt is too long" failure. A flat REFUTED would have discarded the second-largest measured cause in the entire investigation.
>
> The verdict that was actually returned: **PROJECT-CONDITIONAL** — refuted here, confirmed there, with the deciding property named.
>
> **The tool's own repository is always the most convenient project to measure — and it is systematically the least representative.** It is where the source is, where the task is running, and where the analyst already has context. But a plugin-development repository's rules are scoped to plugin-authoring paths; a project that uses the tool to manage application work accumulates domain rules on entirely different paths. The convenient sample was the atypical one, and it produced the reassuring answer.
>
> **A false REFUTED closes a line of inquiry permanently.** Nobody re-opens a hypothesis marked settled.
>
> Two reporting rules:
>
> - **Report the range, not a representative value.** 1,705 vs 6,273 lines and 30% vs 96% incidence *are* the finding; an average across two projects would describe neither.
> - **A per-project config constant is a measurement of one project even when the tool ships the key.** Two projects carried different overhead calibrations of the same date, 29,500 against 48,000, a 63% gap traced almost entirely to `memory_files` at 4,300 vs 24,000. Both figures were correctly measured, and neither generalises.

---

## 3. An Evidence Gap Is Scoped to the Corpus You Swept — Enumerate the Record-Keeping Layers First

> [!constraint] A project's planning artifacts and its harness's logs are different corpora with different authors
> The artifacts record what a session *believed and decided*; the logs record what the runtime *actually did*. A sweep of one is silent about the other, but an evidence-gap statement rarely says so — **it reads as a statement about the world, not about the shelf that was searched.**
>
> A sprint swept a project's historical corpus — 149 summary and recovery files across 14 plans — for recorded token-consumption figures. The sweep was executed well: it found **exactly one** figure in 149 files, correctly classified it as a per-subagent-window sum rather than an orchestrator-window total, and delivered a first-class evidence-gap statement. That finding was true. The conclusion drawn from it was not:
>
> ```
> AIRTIGHT:  "No artifact records an orchestrator-window total."
> DIFFERENT: "The history cannot quantify this."
> ```
>
> Nothing in the task's output marked the transition, and the task had no way to catch it either — its Required Context named the artifact corpus, so it swept exactly what it was told to sweep and reported honestly. The orchestrator read "no artifact records it" as "the history cannot answer this" and primed the downstream synthesis toward a headline that the reported consumption was largely an **accounting-semantics artifact** — a reporting defect, implying a reporting remediation. The user then asked a one-line question: *do you need more log files of past sessions?* 99 already existed, unread, in `~/.claude/projects/**/*.jsonl`, carrying `usage` on every API call, one file alone holding 331 such records. Measured across 99 sessions: peak prompt **734,723**, median **363,620**, **94% over the 150K target, 84% over 200K, 22% over 500K** — all main-session, `isSidechain:false` verified per file. The phenomenon was real window pressure, not an accounting artifact, and the measurement surfaced two dominant causes **no hypothesis had named**: unbounded monotonic accumulation in a never-reset window (86.5% of a representative session) and auto-injected path-scoped rule content (+91,718 tokens in a single turn).
>
> Before accepting any "the record does not capture X", enumerate the record-keeping layers and name which were swept and which were not:
>
> 1. the project's own artifacts;
> 2. the harness's session transcripts (`~/.claude/projects/**/*.jsonl`);
> 3. tool and CLI state and caches;
> 4. the version-control history.
>
> **A gap statement is load-bearing downstream.** It licenses fallback conclusions ("if we can't measure it, the figure is probably an accounting artifact"), and those inherit the unexamined scope. Here that nearly converted a load problem into a reporting problem, and would have misdirected an entire remediation sprint toward instrumenting a number instead of bounding a window.
>
> Three operative rules:
>
> - **Write gap statements with their scope in the sentence.** "The planning artifacts do not record X", never the unscoped "X is not recorded".
> - **Treat a gap statement as a dispatch trigger, not a conclusion.** When a task returns "cannot be quantified from my corpus", the next question is *which corpus would carry it*, asked before any downstream synthesis consumes the gap.
> - **Suspect the gap hardest when the question is about runtime behaviour.** Token consumption, latency, tool-call counts and context growth are things a runtime measures continuously and a document records only if someone chose to, so the absence of a *written* figure is weak evidence about a *measured* one.
>
> **Sweep the harness corpus by streaming, never by reading.** These files run to hundreds of megabytes, and a whole-file read fails the task outright. Write an aggregation script and run it.
>
> **When the new corpus lands, stop the downstream work rather than let it finish.** A synthesis primed on a refuted premise does not partially recover.

§2 and §3 look like one section and are not. Both are "you measured a slice", but the remedy differs in kind: §2's fix is to **measure a second instance** (another project) and return a conditional verdict; §3's fix is to **search a different shelf** (another corpus) before concluding anything is unmeasurable. A merged section collapses to "consider your scope", which supplies neither action.

---

## 4. Write the Boundary Into the Sentence

> [!practice] Every finding above was correct, and became wrong by losing a qualifier the author knew at the time
> | Boundary | Unscoped (wrong) | Scoped (right) |
> |---|---|---|
> | Sample size | "the agent used the shell" | "2 of 3 runs used the shell" |
> | Project | "refuted" | "refuted where the rule surface is under ~2K lines and unscoped to plan paths; confirmed where it exceeds ~6K" |
> | Corpus | "X is not recorded" | "the planning artifacts do not record X; the harness transcripts were not swept" |
>
> A downstream reader needs the discriminator, not the conclusion.

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 (three or more observations on any surface a plan calls deterministic) · [`session-context-budget.md`](session-context-budget.md) § Read-Tool Hard Limits (why a harness transcript must be streamed, never read whole) · [`token-saver-profile.md`](token-saver-profile.md) (the consumption band the §3 corpus produced)*
