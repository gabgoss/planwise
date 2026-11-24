---
description: A finding is scoped to the sample it was taken from, the project it was measured in, and the corpus that was searched — and the sentence that states it has to carry that boundary. Covers why one dispatch is an anecdote and how to sample without cherry-picking, why a hypothesis about a consuming project cannot be settled in the tool's own repository, why "the record does not capture X" is true only of the shelf that was swept, and the three sentence forms that keep the boundary attached. Consult when measuring model or harness behaviour, testing a hypothesis whose magnitude lives outside the tool, or accepting an evidence-gap statement. Also covers why a column that reads the same value before the first boundary measures the floor every session pays, and must be baselined before arms are compared on it. Also covers why a harness behaviour measured on one surface is a claim about that surface only. Also covers why a baseline figure carries the fixture it was measured on, so a prediction computed from it stays a prediction. Also covers why a count is a reading until it names the invocation that produced it, the match key and the date the tree was read, so a bare stem, a sibling's name or a moved tree cannot set its corpus.
consult-when: Measuring model or harness behaviour, testing a hypothesis whose magnitude lives in a consuming project, or accepting "the record does not capture X" — declare n per cell, classify the hypothesis, enumerate the record-keeping layers, write the boundary into the sentence, and baseline a column that reads the same before the first boundary because it measures the floor every session pays, and scope a negative to the invocation that produced it and read an under-run cost as a broken chain (§6), and scope a harness behaviour to the surface that measured it before shipping guidance (§7), and read the fixture behind a recorded figure before computing a prediction from it (§8), and state the invocation, the match key and the read date beside every count before citing it (§9)
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
- [7. A Harness Behaviour Measured on One Surface Is a Claim About That Surface Only](#7-a-harness-behaviour-measured-on-one-surface-is-a-claim-about-that-surface-only)
- [8. A Baseline Figure Carries the Fixture It Was Measured On](#8-a-baseline-figure-carries-the-fixture-it-was-measured-on)
- [9. A Count Names Its Invocation, Its Match Key and the Tree It Read](#9-a-count-names-its-invocation-its-match-key-and-the-tree-it-read)

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

## 7. A Harness Behaviour Measured on One Surface Is a Claim About That Surface Only

> [!constraint] Record the surface beside the build, and check every surface the guidance reaches
> A probe ran headless with `claude -p` on one CLI build. It found that an `Agent` call omitting `run_in_background` ran in the background in 15 of 15 spawns. It also found that `run_in_background: false` gave a foreground child.
>
> A backlog item proposed adding the flag to every writer spawn, and a shipped reference already said the flag triggers the foreground. On the next build the two surfaces disagreed. The table lists each surface's reading.
>
> | Surface | `run_in_background` on the `Agent` schema | Flag `false` passed | Child ran in |
> |---|---|---|---|
> | headless `claude -p` | accepted | yes | foreground |
> | interactive session | absent, with `additionalProperties: false` | yes, accepted without error | background |
>
> The interactive harness ignored the flag and still routed the child's approval request to the user as a prompt. The defect the item fixed is a background child denied with no prompt. That defect exists headless, and the interactive surface behaves differently. The triage caught this only because it read its own `Agent` schema.
>
> WRONG — the surface is implicit, so the claim reads as universal:
> ```
> Measured 2026-10-25 on Claude Code 2.1.310: run_in_background: false gives a foreground run.
> How to trigger foreground: run_in_background: false on the Agent call.
> ```
> CORRECT — the surface is named, and the other surface is measured or marked unmeasured:
> ```
> Measured 2026-10-28 on 2.1.312, headless (claude -p): run_in_background: false gives a foreground run.
> Interactive, same build: the Agent schema has no run_in_background field; the flag is accepted
> and ignored, and the child runs in the background. Its approval prompts still reach the user.
> ```

Three rules follow.

- **Scope a harness measurement to the surface that produced it.** The surfaces are headless `-p`, interactive and SDK. Record the surface beside the build.
- **Check the parameter on every surface the guidance reaches.** A plugin's handlers run on both surfaces. Guidance about a parameter reaches both.
- **Read the live tool schema first, because it costs nothing.** Then spawn one trivial agent with the parameter set, because that is cheap.

**Applies to** any reference, handler or backlog item that states what a Claude Code tool parameter, permission mode or spawn mode does. It applies most where the evidence comes from a `claude -p` probe harness. §6 covers the same boundary for a negative result.

---

## 8. A Baseline Figure Carries the Fixture It Was Measured On

> [!constraint] Read the fixture behind a recorded figure before doing arithmetic on it
> At the confirm step, an orchestrator predicted that a task's new report lines would break the pin `assert len(report) < 2_000`. The build had 35 tasks. The orchestrator took a 716-character baseline from an earlier record and added about 1,540 characters. It reported about 2,250 as a structural finding.
>
> The 716 came from a build with a stray H2 and no sibling file. That is not the clean build the pin measures. The clean build measured about 400 characters, and the comment one line above the pin said so. The true total was 1,887, under the pin.
>
> The false figure then did damage. The brief told the runner the pin would fail. The runner loosened the pin to `< 2_500` and copied "about 716 of gate lines" into the test comment. The correction cost one corrective resume and three plan-file notes.
>
> WRONG — take the number from a record and do arithmetic on it:
> ```text
> record: "The report is 716 characters"      (a run with a stray H2)
> finding: 716 + 1,540 = 2,256 -> past the 2,000 pin -> widen the write-set
> brief:   "the pin fails"
> ```
> CORRECT — read the fixture, then measure the subject the claim is about:
> ```text
> record: "with a stray H2 in one session objective" -> not the clean build
> pin comment: "about 400 characters" -> disagrees, so measure
> measure once: 453 + 1,434 = 1,887 -> under the pin -> no finding
> ```

Three rules follow.

1. **State a prediction as a prediction in the brief.** "Expect about N, measure it" lets a runner disagree. "The pin fails" tells the runner what to do to a passing gate.
2. **When two sources disagree, measure before raising a finding.** Here the pin comment said about 400 and the record said 716.
3. **Treat a runner's surprising number as a test of the author's premise.** It is evidence about the brief, not only about the runner.

**Applies to** any finding, brief or flag that computes an expected value from a recorded figure. It applies most where the arithmetic predicts a gate failure, because the prediction then authorizes a change to the gate.

---

## 9. A Count Names Its Invocation, Its Match Key and the Tree It Read

Three counts were each accurate about what they measured and each was cited for a claim about something else. The first took its corpus from the invocation. The second took it from the names of sibling files. The third took it from a tree that had changed since the count was made.

A bare number is not a measurement. What it counted depends on the invocation, on what else shares the name, and on when the tree was read. Any of the three can move without a commit.

### 9.1 A Search on a Bare Filename Stem Finds Siblings, Not Only Citations

Artifacts in this corpus are named after the concepts they govern. Sibling artifacts therefore extend a reference's stem: `foo.md` beside `foo-reviewer.md`, or `foo.md` beside `foo-Part-2-Whatever.md`. Every sibling is a false positive in a citation census. **Each one inflates the count in the direction that makes the census look thorough.**

A backlog item recorded "60 occurrences across 20 files, of which 47 carry a section anchor". It built a per-destination map on that figure. A re-run at execution gave 59 for `scaffolding-hygiene\.md` and 62 for the bare stem `scaffolding-hygiene`. The recorded 60 matched neither.

Three of the hits were an agent's name, `scaffolding-hygiene-reviewer`, which only begins with the reference's stem. Two real citations had arrived after the item was written. The recorded figure was `62 − 2`, so two errors of opposite sign cancelled and the total looked plausible.

> [!constraint] Re-measure both ways, reconcile the difference, then classify
> WRONG — take the recorded count as the inventory and work the map:
> ```
> item says: 60 occurrences, 20 files, review.md carries 4
> → open review.md expecting 4 citation sites
> → 3 of them are an agent's name; 2 real citations elsewhere are missing from the map
> ```
> CORRECT — re-measure both ways, reconcile the delta, then classify:
> ```
> Grep 'foo\.md'   → N_anchored     ← the citation corpus
> Grep 'foo'       → N_bare         ← superset
> N_bare - N_anchored = the name-sharing siblings — inspect each, do not assume noise
> reconcile N_anchored against the item's recorded figure; explain every unit of drift
> ```

Two rules follow, and the second matters more.

1. **Anchor the extension when you want citations.** `foo\.md` excludes `foo-reviewer` and `foo-Part-2-…` by construction. Run the bare stem too. Treat the difference between the two counts as a work list, because that difference is exactly the set of name-sharing siblings and some may need attention.
2. **A census is a claim with a date, and it decays from both ends.** Hits vanish when prose is reworded. Hits appear when a sibling lands. Re-run the census at execution time and reconcile the delta against the recorded figure. Do not accept the new number. Reconciling 60 against 62 exposed the three phantom hits. Accepting 59 would have left the map's rows unexplained.

The count was not the damage. **The destination map built on top of it was.** Three mapped citations did not exist and two real ones were absent. An executor working the map as an inventory would have hunted for three phantom sites and shipped two stale pointers.

Verify the destinations mechanically, not by eye. For each citation, extract the section anchor that follows it and check the anchor against the part file that holds that section.

### 9.2 State the Invocation Beside Every Reported Count, and Never Inherit One

A runner reported its green gate as 564 passed. The orchestrator re-measured against the same commit, the same working tree and the same second, and got 723 passed. Neither reading was a lie.

The mechanism has three parts, and each is true on its own:

- `rootdir` sets where relative config values resolve, and it sets the root for node ids.
- The path arguments set collection scope. With no path argument, pytest collects from the invocation directory.
- `testpaths` is honoured only when the invocation directory is `rootdir`. In any other directory it sits inert.

The invocation passed `--rootdir` and no path argument. It also ran from a directory that was not the root, so `testpaths = tests` never resolved. Collection fell back to scanning from the project root. The three rows of the table below show what that scan swept in.

| Source | Tests | What it is |
|---|---:|---|
| `tests/` | 564 | the genuine suite |
| `evals/` | 116 | a separate eval corpus, unrelated to the suite under test |
| another session's in-flight files | 43 | **untracked helper scripts, written minutes earlier** |

The third row is the reason for this section. The gate's denominator was set, in real time, by work unrelated to the change under test. No commit separated one reading from the next.

An inflated count is the dangerous one, because it reads as better. A count of 723 looks like broader coverage than 564, and a reviewer comparing the two would reasonably prefer the larger. The number went up, nothing failed and the gate is green, so every instinct points the wrong way. The count also drifts silently. The same invocation returns a different denominator depending on what an unrelated session has on disk, and a re-run an hour later changes it again.

The collection census separates the sources. It counts collected test ids by top-level folder:

```bash
python -m pytest -q --collect-only <...> | grep -oE '^[a-zA-Z_./-]+\.py' \
  | sed 's|/.*||' | sort | uniq -c
#   116 evals
#    43 planwise      ← should never appear
#   564 tests
```

Four rules follow.

- **State the invocation beside every reported count.** A bare number is not a measurement.
- **Treat a count above the expected one as a failure, not a bonus.** Investigate any increase that no commit explains.
- **Never inherit a green-gate count across a hand-off.** An upstream signoff had pinned 680, which was 564 plus the 116 evals, captured before the concurrent session existed. Anyone re-running it later gets 723, "fails" against 680, and hunts a regression that never happened. Re-measure and re-state the invocation each time. An inherited count is a claim about a tree that has since moved.
- **A runner's number can be right when yours is wrong.** Here the runner reported 564 and was correct. The orchestrator's independent re-measurement was the contaminated one. Independent verification is still good practice, but the resolution is to reconcile the two readings. Do not assume the larger, the later, or the orchestrator's.

The durable gate is the one that asserts scope: zero collected node ids outside the intended tree. A pass count alone is satisfied by a run that collected the wrong tests.

### 9.3 Re-Run Every Signoff Anchor at Closeout, and Investigate a Failure Before Judging the Anchor

An earlier verification ran against a tree that no longer exists. A signoff anchor earns its place because it asks a different question, from a different vantage point, after all the work has landed. Re-running it is not ceremony.

A signoff anchor expected three files to contain `feedback_dir` and returned 2. The tempting reading was that the anchor was too narrow. The criterion said the handler must "specify creating the directory", and by the letter the handler did.

Opening the file showed the real defect. A hardcoded literal sat beside three placeholder siblings, so `init --feedback-dir Drafts` creates `Drafts/` while the banner claims `Feedback/`. The defect shipped to the user.

```
  ✓ {planwise_root}/{plans_dir}/
  ✓ {planwise_root}/{backlog_dir}/
  ✓ {planwise_root}/{lessons_dir}/
  ✓ {planwise_root}/Feedback/          ← hardcoded literal, siblings are placeholders
```

The owning runner's reasoning had been sound when written. A later edit by another task falsified it. Three causes can fail an anchor, and each calls for a different response:

| Cause | Response |
|---|---|
| The anchor asks the wrong question (a real instrument defect) | Fix the anchor, record why, and verify the substance by other means |
| The anchor is right and the artifact is wrong | Fix the artifact — this is the anchor earning its keep |
| The anchor is right and the artifact is right, but a *sibling task's* later edit invalidated an earlier correct decision | Fix the artifact; record that the original reasoning expired rather than being wrong |

The third row is invisible to any per-task gate by construction. No task checks whether another task's later edit falsified its premises. Only a whole-session check run after everything lands can see it. [`verify-anchor-against-artifact.md`](verify-anchor-against-artifact.md) §1 covers the sibling rule that an anchor is measured against the artifact and never derived from the criterion it verifies.

Four rules follow.

1. Re-run every anchor at signoff, from the closing session, against the final tree.
2. On a failure, open the file before judging the anchor. A "too narrow" anchor and a genuine defect look identical from the exit code alone.
3. When the fix lies inside an existing write-set, re-dispatch the owning task with one corrective instruction. Do not edit its output from the orchestrator, because the ownership window still applies at closeout.
4. Record the failure and its resolution in the signoff itself, not only the final pass. A signoff that shows "anchor 3 failed first, and here is what it caught" is stronger evidence of a real gate than five uneventful passes.

Do not skip an anchor because the criterion "was already verified".

### 9.4 Three Questions to Ask of Any Count Before Citing It

> [!practice] Ask three questions of a count before it leaves your hands
> 1. **What invocation produced this, and would a different one produce a different corpus?** (§9.2)
> 2. **What else shares the name I matched on?** (§9.1)
> 3. **When was the tree this counted read, and has a sibling written to it since?** (§9.3)
>
> A count that cannot answer all three is a reading, not evidence.

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §1 (three or more observations on any surface a plan calls deterministic) · [`session-context-budget.md`](session-context-budget.md) § Read-Tool Hard Limits (why a harness transcript must be streamed, never read whole) · [`token-saver-profile.md`](token-saver-profile.md) (the consumption band the §3 corpus produced)*
