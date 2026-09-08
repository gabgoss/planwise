---
description: Grade a delegated result or a probe from the record, never from the narration — and know which field of the record discriminates. Covers why a transcript-recovered synthesis is provisional and systematically softer than the delivered report, why a correct verdict is not evidence the attribution was correct, why `is_error` alone cannot separate a denial from a downstream failure, and where the field that can separate them actually lives. Consult when a reviewer's reply did not route, when grading a probe's outcome or its cause, and when scoring a permission dry-run.
paths: {planwise_root}/{plans_dir}/**
---
# Grade From the Record — The Narration Got the Outcome Right and the Record Said Something Else

**Purpose:** Three incidents where a delegated result was graded from what an agent *said* rather than from what the record *shows*, and every outcome-level check passed. This is the sharp form of an already-known rule. "Grade from `tool_use` / `tool_result` records, never from the child's prose" is usually justified by the risk that prose misreports the outcome — narrating a block that did not happen, claiming success over a call that errored. In all three cases below **the outcome was reported correctly**. What was wrong was the detail, the attribution, or the discriminating field — none of which any pass/fail comparison can see.

**Read this when** you are synthesising a report from a subagent's transcript because its reply did not route, when you are about to record *why* a probe produced its result, or when you are scoring a permission probe as DENY or PASS.

The three failures sit at different points of one pipeline: what the agent wrote at the end of its turn, why it says the result happened, and which field of the harness's output actually separates two outcomes that look identical. Each one is invisible to a grader that has already confirmed "the probe reported a denial" or "the reviewer reported N findings".

Three neighbouring rules own adjacent machinery. [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §4 owns the recovery of a reply that did not route — the plateau check and the bounded extraction. §1 below is about what the recovered synthesis *is* once you have it. [`verification-gate-evidence.md`](verification-gate-evidence.md) §6 owns why a known-good probe aimed at a fake path is unpassable by construction; §3 below is the grading side of the same incident — which field separates that failure from a denial. [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 classifies a return before it is consumed; this file is about what to do with a return that classifies as complete and is still wrong in a way no outcome check sees.

## Table of Contents

- [1. A Transcript-Recovered Synthesis Is Provisional — Re-Diff It When the Real Reports Land](#1-a-transcript-recovered-synthesis-is-provisional--re-diff-it-when-the-real-reports-land)
- [2. Grade the Mechanism, Not Only the Outcome](#2-grade-the-mechanism-not-only-the-outcome)
- [3. Know Which Field Discriminates, and Capture It at the Moment It Exists](#3-know-which-field-discriminates-and-capture-it-at-the-moment-it-exists)
- [4. The Recovery Recipe](#4-the-recovery-recipe)

---

## 1. A Transcript-Recovered Synthesis Is Provisional — Re-Diff It When the Real Reports Land

> [!constraint] A reviewer's final transcript block is written to close out its own turn; the delivered report is written to be acted on
> They are different artifacts with different audiences, and the transcript one is a **compression** of the other. Compression drops per-instance detail — `file:line`, exact quoted text, the comparison that makes a finding decisive — and **per-instance detail is precisely what severity classification runs on**, so the loss is not random. **A transcript-only synthesis under-counts and under-classifies.**
>
> In a review fan-out of eight, all eight reported "delivered to team-lead via SendMessage" and none routed. The established recovery worked — poll each subagent's `agent-*.jsonl` until it plateaus, extract the last assistant text block, synthesise — and the report was filed and committed on it. Then the messages routed in bulk, and diffing the delivered copies against the recovered ones was **not** clean: **every difference made a finding stronger, never weaker.** One reviewer's transcript block compressed six sites into three vague phrases ("a systematic-but-consistent drop of a trailing citation column…"), where the delivered message enumerated the same findings with file, location and exact dropped text — including one the summary had no room for: *the Execution Input fabricates a period where the source has an em-dash mid-sentence*. A fabricated sentence boundary inside a block labelled "verbatim" is a different and worse defect than "truncates without ellipsis". In a second case the summary omitted the decisive half of a finding entirely, and the lead **demoted it to INFO** on what remained; the delivered message carried the comparison that showed the plan solves one problem two ways with only one passing its own reviewer check, and the finding was **restored to WARNING**. Net across the re-diff: 20 findings → 22, one new systemic finding, one demotion reversed, two materially expanded, **none moving the other way.**
>
> **The recovery recipe is sound and is still the right move when nothing routes.** What was wrong was treating its output as *final* rather than *provisional*.
>
> ```
> WRONG — the plateau check passes, the last block ends with a clean completion
>         signal, so the synthesis is treated as the reviewer's report:
> extract last assistant block → synthesize → file report → commit → done
> # The completion signal proves the TURN finished. It says nothing about whether
> # the block is the report or a summary of it.
>
> CORRECT — the synthesis is filed as provisional and reconciled on delivery:
> extract last assistant block → synthesize → file report (marked provisional) →
>   on delivery: diff delivered vs recovered, per reviewer →
>   expect the delivered copy to be RICHER (per-instance detail, file:line, exact quotes) →
>   revise in place with a superseding note stating what changed and why →
>   re-derive your OWN severities against the delivered evidence, both directions
> ```
>
> **Both directions.** In the same review the lead had rated a shared-file finding BLOCKER over two reviewers who both called the practical risk low. Their delivered reasoning — the two edits target disjoint regions, and both tasks edit by content anchor — was better than the lead's first pass, and the finding was demoted to ERROR. **Two independent reviewers rating something lower than you did is evidence, not noise.**
>
> Budget for the revision from the start.

A reader who takes "the transcript block may differ from the report" without the direction treats the re-diff as optional tidying. The finding is that a transcript-only synthesis is *biased*, not merely lossy, and the bias runs toward under-classification.

---

## 2. Grade the Mechanism, Not Only the Outcome

> [!constraint] A correct verdict is not evidence the reasoning was correct
> This is distinct from the prose-is-unreliable rule everyone already holds. Here **the prose got the outcome right**, every outcome-level check passed, and only the causal attribution was false — so no pass/fail comparison can see it.
>
> Two probes in a `permissions.deny` dry-run were denied exactly as designed, and the child sessions' prose attributed the denial to an installed hook whose purpose was denying shell readers. That hook was not an active control: the script file was on disk, but the project's `.claude/settings.json` carried no `hooks` key at all, so nothing registered it. The actual cause was the `permissions.deny` entry passed via `--settings` for the probe. A grader checking only "did the probe report a denial?" records two clean passes and never notices that the evidence credits a control that was never running. The model had every reason to say it — the repository contained a hook script whose entire purpose was denying shell readers, and the deny message was about exactly that. **It is a plausible attribution, which is what makes it durable.**
>
> The damage is entirely in the record rather than in today's verdict:
>
> - A later reader concludes the parked control is live **and that it works** — and either declines to ship the mechanical control as redundant, or "restores" the parked one expecting behaviour it never produced.
> - The measured reason it was parked (its predicate exempted any command containing a pipe, which was most of the traffic it was meant to catch) gets quietly overwritten by an anecdote that it denies things correctly.
> - A regression later removes the real control, and the anecdote makes the wrong file the first place anyone looks.
>
> Four rules:
>
> - **Grade the outcome AND the mechanism from the record.** Confirm *which* control fired, not merely that something denied.
> - **Treat any mechanism named only in prose as unverified.** If the record does not identify the control, the report must say *"denied, mechanism not identified in record"* rather than name a candidate.
> - **When a plausible-but-inactive control exists in the repository, expect it to be blamed.** A parked script, a commented-out rule, a disabled hook are attractors for false attribution. Verifying "unregistered" means checking the registration surface (`settings.json`), never the presence of the file.
> - **A correct verdict is not evidence the reasoning was correct.** Right-answer-wrong-reason survives every outcome-shaped gate and is caught only by reading the evidence chain.

The parked script in the measured incident has since been deleted. The *class* — a parked script, a commented-out rule, a disabled hook — is the operative content, because the attractor pattern is what transfers.

---

## 3. Know Which Field Discriminates, and Capture It at the Moment It Exists

> [!constraint] `is_error:true` is not a permission denial
> It conflates "the rule blocked this" with "the rule allowed this and the command then failed". The conflation is silent, and it biases toward *over*-reporting denials — that is, toward declaring an over-broad rule correct.
>
> A sprint dry-ran two `permissions.deny` patterns against known-bad and known-good probes, grading `DENY` as `tool_result.is_error:true` and `PASS` as `is_error:false` with genuine stdout. Two of six known-good probes landed in neither bucket: they returned `is_error:true` because the command **was allowed through to the shell and then failed on its own** (`wc: /c/x/agents/a.md: No such file or directory`; `error: --name is required`). Both were over-correction controls whose entire point was showing the rule does *not* block them. Graded on `is_error` alone, both read as DENY — crediting the rule with two blocks it never performed, on exactly the probes designed to catch it being too broad. **An over-broad rule and a correctly-scoped rule produce identical `is_error` values on these rows.**
>
> | `permission_denials` | `is_error` | Verdict |
> |---|---|---|
> | populated with this command | `true` | **DENY** — the rule fired |
> | `[]` | `false`, genuine stdout | **PASS** — allowed and ran |
> | `[]` | `true` | **NOT a permission result** — allowed, then failed downstream. Fix the probe and re-run; score neither way. |
>
> **That field is not in the transcript.** `permission_denials` is emitted in the `result` event of the child's `--output-format stream-json` output — on **stdout, at invocation time**. Searching the persisted `~/.claude/projects/**/*.jsonl` for two probes graded on it found the string absent from both. An agent told to "grade from the transcript's `permission_denials` array" searches the `.jsonl`, finds nothing, and concludes either that the anchor is missing or that no denial occurred. **You cannot recover the field after the fact: capture the child's stdout stream at probe time or you lose it permanently.**
>
> **Fallback, with its stated weakness.** When only the `.jsonl` survives, test presence vs absence of the `has been denied` message on the probe's `tool_result`. It is weaker, because it matches on message text the harness may reword, but it does separate the two cases and it persists.
>
> **A probe that lands in the third row is a broken probe, not a result.** Fix it (bad path, missing flag) and re-run. Recording it as either PASS or DENY manufactures evidence.
>
> **The failure lands exclusively on the known-good half of a two-direction test — the half that proves the control is not over-broad.** Known-bad probes are robust, since a DENY is decided *before* execution and nothing downstream can confuse it. A gate run only against known-bad input never encounters this and reports clean.

The fixture-side half of the same incident — why a known-good probe aimed at a placeholder path is unpassable by construction, and how to name a real target — is [`verification-gate-evidence.md`](verification-gate-evidence.md) §6. §4 of that file states the general principle this section instantiates: prefer a fingerprint over a flag, because `is_error:false` says only that the call did not fail.

---

## 4. The Recovery Recipe

> [!verify] The operational form of §1's "provisional"
> ```bash
> # 1. Plateau check, in the background — do not hand-poll.
> D=~/.claude/projects/<project-slug>/<session-id>/subagents
> until [ $(find $D -name '*.jsonl' -newermt '-90 seconds' | wc -l) -eq 0 ]; do sleep 20; done
>
> # 2. Extract the last assistant text block per reviewer (bounded script → scratchpad,
> #    never read the .jsonl whole). Confirm each ends with its own completion signal —
> #    that proves a complete turn, NOT that the block is the full report.
> # 3. File the synthesis, marked provisional in the report itself.
> # 4. When the delivered reports arrive, diff EVERY delivered copy against what you synthesized.
> #    Expect the delivered version to be strictly richer. Revise in place; say what changed.
> ```
>
> Step 2's bounded extraction form — a small-window `-o` match on the status-block field names, taking the last hit — is [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §4. If this recipe drifts out of sync with the harness's transcript layout, fix the recipe and leave §1's rule untouched.

§1 and §3 are both "the artifact you are reading is not the artifact you need", but the missing artifact differs in kind and so does the remedy: §1's exists and will arrive later (wait and diff), §3's was never persisted and must be captured at invocation or it is gone forever. Merged, they produce "check your sources", which supplies neither action.

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §4 (recovering a reply that did not route) · [`verification-gate-evidence.md`](verification-gate-evidence.md) §4, §6 (fingerprint over flag; a known-good probe names a real target) · [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 (classify every return before consuming it) · [`measure-scope-and-sample.md`](measure-scope-and-sample.md) §1 (validating the instrument is not validating the measurement)*
