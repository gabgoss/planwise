---
description: Grade a delegated result or a probe from the record, never from the narration — and know which field of the record discriminates. Covers why a transcript-recovered synthesis is provisional and systematically softer than the delivered report, why a correct verdict is not evidence the attribution was correct, why `is_error` alone cannot separate a denial from a downstream failure, where the field that can separate them actually lives, and why a downstream proxy (token count, wall time) cannot substitute for a harness setting's own recorded value. Consult when a reviewer's reply did not route, when grading a probe's outcome or its cause, when scoring a permission dry-run, and when gating a sweep over a model or CLI setting. Also covers why a summary field whose name rhymes with the measure must be recomputed from the definition and tested against a control session, and why a field is traced to the code that writes it, including any conditional logging, rather than accepted from the first search hit.
consult-when: Synthesising from a subagent transcript because its reply did not route, recording why a probe produced its result, or scoring a permission probe — the synthesis is provisional, confirm which control fired, and capture `permission_denials` from stdout at invocation time, recompute a headline figure from its definition against a control session, and trace a field to the code that writes it, and a grader that archives "the transcript" enumerates every session id the log names (§7)
paths: {planwise_root}/{plans_dir}/**
---
# Grade From the Record — The Narration Got the Outcome Right and the Record Said Something Else

**Purpose:** Grade a delegated result from what the record *shows*, never from what an agent *said*. "Grade from `tool_use` / `tool_result` records, never from the child's prose" is usually justified by prose that misreports the outcome. In every case below **the outcome was reported correctly**. What was wrong was the detail, the attribution, the discriminating field, or the field a figure was read from. No pass/fail comparison can see any of them.

**Read this when** you synthesise a report from a subagent's transcript because its reply did not route, record *why* a probe produced its result, score a permission probe as DENY or PASS, or read a headline figure from a summary field.

Three neighbouring rules own adjacent machinery. [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §4 owns the recovery of a reply that did not route: the plateau check and the bounded extraction. §1 below is about what the recovered synthesis *is* once you have it. [`gate-fixture-provenance.md`](gate-fixture-provenance.md) §6 owns why a known-good probe aimed at a fake path is unpassable by construction. §3 below is the grading side of the same incident: which field separates that failure from a denial. [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 classifies a return before it is consumed. This file covers a return that classifies as complete and is still wrong in a way no outcome check sees.

## Table of Contents

- [1. A Transcript-Recovered Synthesis Is Provisional — Re-Diff It When the Real Reports Land](#1-a-transcript-recovered-synthesis-is-provisional--re-diff-it-when-the-real-reports-land)
- [2. Grade the Mechanism, Not Only the Outcome](#2-grade-the-mechanism-not-only-the-outcome)
- [3. Know Which Field Discriminates, and Capture It at the Moment It Exists](#3-know-which-field-discriminates-and-capture-it-at-the-moment-it-exists)
- [4. The Recovery Recipe](#4-the-recovery-recipe)
- [5. A Summary Field Whose Name Matches the Measure Is Not the Measure](#5-a-summary-field-whose-name-matches-the-measure-is-not-the-measure)
- [6. Trace a Field to the Code That Writes It, Not to the First Search Hit](#6-trace-a-field-to-the-code-that-writes-it-not-to-the-first-search-hit)
- [7. A Grader That Archives "The Transcript" Must Enumerate Every Session Id the Log Names](#7-a-grader-that-archives-the-transcript-must-enumerate-every-session-id-the-log-names)

---

## 1. A Transcript-Recovered Synthesis Is Provisional — Re-Diff It When the Real Reports Land

> [!constraint] A reviewer's final transcript block is written to close out its own turn; the delivered report is written to be acted on
> They are different artifacts with different audiences, and the transcript one is a **compression** of the other. Compression drops per-instance detail — `file:line`, exact quoted text, the comparison that makes a finding decisive — and **per-instance detail is precisely what severity classification runs on**, so the loss is not random. **A transcript-only synthesis under-counts and under-classifies.** It is biased toward under-classification, not merely lossy, so the re-diff is not optional tidying.
>
> **The recovery recipe is sound and is still the right move when nothing routes.** What goes wrong is treating its output as *final* rather than *provisional*. A clean completion signal proves the turn finished. It says nothing about whether the block is the report or a summary of it.
>
> WRONG — the plateau check passes, the last block ends with a clean completion signal, so the synthesis is treated as the reviewer's report:
> ```
> extract last assistant block → synthesize → file report → commit → done
> ```
> CORRECT — the synthesis is filed as provisional and reconciled on delivery:
> ```
> extract last assistant block → synthesize → file report (marked provisional) →
>   on delivery: diff delivered vs recovered, per reviewer →
>   expect the delivered copy to be RICHER (per-instance detail, file:line, exact quotes) →
>   revise in place with a superseding note stating what changed and why →
>   re-derive your OWN severities against the delivered evidence, both directions
> ```
>
> **Both directions.** The delivered reasoning can lower a severity as well as raise one. **Two independent reviewers rating something lower than you did is evidence, not noise.**
>
> Budget for the revision from the start.

---

## 2. Grade the Mechanism, Not Only the Outcome

> [!constraint] A correct verdict is not evidence the reasoning was correct
> This is distinct from the prose-is-unreliable rule everyone already holds. Here **the prose got the outcome right**, every outcome-level check passed, and only the causal attribution was false — so no pass/fail comparison can see it. A plausible attribution is what makes it durable.
>
> The damage is in the record, not in today's verdict. A later reader concludes the parked control is live and works. The measured reason it was parked gets overwritten by an anecdote. A regression that removes the real control sends the first search to the wrong file.
>
> WRONG — two probes in a `permissions.deny` dry-run were denied as designed, and the child's prose credited an installed hook; the grader checks only the outcome:
> ```
> did the probe report a denial?  → yes, twice → record two clean passes
> # the hook script was on disk, but settings.json had no `hooks` key; the deny entry passed via --settings fired
> ```
> CORRECT — confirm which control fired, from the record and the registration surface:
> ```
> outcome:   denied (read from the record)
> mechanism: the --settings deny entry; the hook is unregistered (settings.json has no `hooks` key)
> # record names no control → write "denied, mechanism not identified in record"
> ```
>
> Four rules:
>
> - **Grade the outcome AND the mechanism from the record.** Confirm *which* control fired, not merely that something denied.
> - **Treat any mechanism named only in prose as unverified.** If the record does not identify the control, the report must say *"denied, mechanism not identified in record"* rather than name a candidate.
> - **When a plausible-but-inactive control exists in the repository, expect it to be blamed.** A parked script, a commented-out rule, a disabled hook are attractors for false attribution. Verifying "unregistered" means checking the registration surface (`settings.json`), never the presence of the file.
> - **A correct verdict is not evidence the attribution was correct.** Right-answer-wrong-reason survives every outcome-shaped gate and is caught only by reading the evidence chain.

The parked script in the measured incident has since been deleted. The *class* — a parked script, a commented-out rule, a disabled hook — is the operative content, because the attractor pattern is what transfers.

---

## 3. Know Which Field Discriminates, and Capture It at the Moment It Exists

> [!constraint] `is_error:true` is not a permission denial
> It conflates "the rule blocked this" with "the rule allowed this and the command then failed". The conflation is silent, and it biases toward *over*-reporting denials — that is, toward declaring an over-broad rule correct. **An over-broad rule and a correctly-scoped rule produce identical `is_error` values on a known-good probe that fails downstream.**
>
> | `permission_denials` | `is_error` | Verdict |
> |---|---|---|
> | populated with this command | `true` | **DENY** — the rule fired |
> | `[]` | `false`, genuine stdout | **PASS** — allowed and ran |
> | `[]` | `true` | **NOT a permission result** — allowed, then failed downstream. Fix the probe and re-run; score neither way. |
>
> WRONG — `DENY` graded on `is_error` alone; two known-good probes were allowed through to the shell and then failed on their own:
> ```
> wc: /c/x/agents/a.md: No such file or directory   → is_error:true → scored DENY
> error: --name is required                         → is_error:true → scored DENY
> # the rule is credited with two blocks it never performed, on the probes built to show it is not too broad
> ```
> CORRECT — read `permission_denials` from the child's stdout `result` event, and score the third row neither way:
> ```
> permission_denials == []  and  is_error:true  → NOT a permission result → fix the probe, re-run
> ```
>
> **That field is not in the transcript.** `permission_denials` is emitted in the `result` event of the child's `--output-format stream-json` output — on **stdout, at invocation time**. Searching the persisted `~/.claude/projects/**/*.jsonl` for two probes graded on it found the string absent from both. An agent told to "grade from the transcript's `permission_denials` array" searches the `.jsonl`, finds nothing, and concludes either that the anchor is missing or that no denial occurred. **You cannot recover the field after the fact: capture the child's stdout stream at probe time or you lose it permanently.**
>
> **Fallback, with its stated weakness.** When only the `.jsonl` survives, test presence vs absence of the `has been denied` message on the probe's `tool_result`. It is weaker, because it matches on message text the harness may reword, but it does separate the two cases and it persists.
>
> **A probe that lands in the third row is a broken probe, not a result.** Fix it (bad path, missing flag) and re-run. Recording it as either PASS or DENY manufactures evidence.
>
> **The failure lands exclusively on the known-good half of a two-direction test — the half that proves the control is not over-broad.** Known-bad probes are robust, since a DENY is decided *before* execution and nothing downstream can confuse it. A gate run only against known-bad input never encounters this and reports clean.

The fixture-side half of the same incident — why a known-good probe aimed at a placeholder path is unpassable by construction, and how to name a real target — is [`gate-fixture-provenance.md`](gate-fixture-provenance.md) §6. [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §4 states the general principle this section instantiates: prefer a fingerprint over a flag, because `is_error:false` says only that the call did not fail.

### 3.1 A Downstream Proxy Passes on Noise When the Record Holds the Real Answer

> [!constraint] Gate an independent variable on its own recorded value, never on an effect of it
> Output tokens and wall time are downstream of the setting and of everything else in the run. On a task that exercises no reasoning they are noise, and a single `>` comparison on `n=1` passes by construction about half the time. The session transcript records the level the CLI actually applied, one field per assistant record, and it is exact. Gate on `recorded == requested`, read per run, so a wrong value fails on the first run instead of the last.
>
> A sweep of 524 runs passed its proxy gate on 342 vs 323 output tokens. Read after the fact, every run's transcript recorded the same level. The setting had never reached the CLI, so every verdict measured run-to-run variance, not the setting under test.
>
> Three consequences:
> 1. **Find the tool's own record of the setting before designing a proxy.** Here it is one field per assistant record in a file the CLI already writes for every session — a few lines of code answer the question for every row in seconds. The proxy gate this sweep used took a design section and a run budget and still could not fail.
> 2. **If a proxy really is all that exists, size it to detect a real effect.** Choose a task whose effect on the proxy is large (a reasoning-heavy task, not a lookup), run several reps per arm, and gate on a ratio of medians against a stated minimum effect size — then dry-run it once with the setting deliberately absent and confirm the gate fails.
> 3. **A monotone gradient across levels is not proof the variable moved.** One arm in the incident above showed the proxy rising smoothly across all four nominal levels, and that gradient was cited as evidence the setting had reached the tool. The real span, measured through the record, was fifty-fold — the gradient was an order of magnitude smaller than the mechanism's known effect, and the recorded value had not varied at all. A gradient far below the mechanism's known scale is a warning, not a confirmation.
>
> WRONG — one run per arm, a proxy, a bare comparison:
> ```
> discriminates = (high_tokens > low_tokens) or (high_ms > low_ms)
> # 342 > 323 → PASS; every run had actually executed at the SAME level
> ```
> CORRECT — the applied value, read from the record, asserted per run; the proxy only as a secondary signal on a task that exercises the mechanism:
> ```
> for run in readings:
>     if run.applied_value != run.requested_value: FAIL(run)
> if median(proxy[high_arm]) < 1.5 * median(proxy[low_arm]): FAIL("no separation")
> ```
>
> Generalises to any harness that varies a model or CLI setting (a thinking budget, a temperature, a model choice) and grades an outcome: assert the setting from the tool's own record on every row, and treat a small monotone proxy gradient as a reason to re-check the record rather than as confirmation the setting moved. The same instrument question as the rest of this section — which field discriminates — applied to a different record and a different proxy.

---

## 4. The Recovery Recipe

> [!verify] The operational form of §1's "provisional"
> Run the plateau check in the background, extract with a bounded script, and file the synthesis marked provisional. Never hand-poll, and never read a `.jsonl` whole.
>
> WRONG — poll the subagent folder by hand, read each transcript whole, and file the synthesis as final:
> ```
> re-check subagents/ by hand → read each agent-*.jsonl whole → synthesize → file as final
> ```
> CORRECT — the recipe, with the result filed as provisional:
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

## 5. A Summary Field Whose Name Matches the Measure Is Not the Measure

> [!constraint] Recompute a headline figure from its definition, and test it against a session that cannot have the property
> A summary field is named for what it stores, not for the question the task asks. When the two names rhyme, a runner takes the field. Every downstream gate passes, because the structure gate, the measure gate and the status block never test the definition.

A task defined a re-entry load as "the tokens from its first call through the context-loaded block". The runner reported the ledger summary field `first_call_read`, 28,192 on every post-clear session. The ORIGINAL session, which had no re-entry, also read 28,192. The field is the static-prefix cache read that the first call of every session pays. Recomputed from the definition, the load was the same order as the baseline arm, and the arm's conclusion reversed.

> ```
> WRONG — take the field whose name matches:
> ledgers[sid].first_call_read = 28,192 for every post-clear session
> → "re-entry load = 28,192 (n=3)"
>
> CORRECT — recompute from the definition, and test it against a session where the value must differ:
> definition: tokens accrued from the first call through the re-entry point
> → per-call table: context at the call that issues the first dispatch
> → 159,113 / 165,780 / 149,749
> control: the ORIGINAL session shows first_call_read = 28,192 as well
> → a "re-entry" figure that a non-re-entry session also has measures something else
> ```

Three rules follow.

1. **Name the computation in the brief, not the field.** Every headline figure in a grade task names how it is computed. The brief says "context at the call that issues the first dispatch, from the ledger tool's per-call table", never "the ledger's first-call figure". A field name in a brief is an invitation to copy it.
2. **Test a per-arm figure against the arm's own control.** A session in the same archive that cannot have the property is the cheapest control there is. If the figure is unchanged there, the field is wrong, whatever it is called.
3. **The orchestrator recomputes the one number that decides the arm.** A headline measurement is a verdict expressed as a number, so the rule in [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) § "1.16 Recompute Delegated Verdicts from Primary Evidence" applies to it. One read-only ledger run took one call and caught a 5.6x error.

**The control-session test.** Before comparing arms on a figure or a column, ask whether it has the same value on a session that cannot have the property. If it does, it measures something else, whatever it is called.

[`measure-aggregate-provenance.md`](measure-aggregate-provenance.md) is the sibling that governs sums and denominators. This section governs which field a figure is read from.

---

## 6. Trace a Field to the Code That Writes It, Not to the First Search Hit

> [!constraint] A field name found by searching data is a hypothesis, not a citation
> A superficially matching field name, found by searching data rather than reading the code that produces it, is a hypothesis. Confirm it by reading the producer.

A grader had to tell a real keystroke from a machine-relayed prompt by an `origin` field with the values `composer`, `peer` and `task-notification`. A search of archived transcripts found `"origin":{"kind":"human"}` first, in an unrelated derivative analysis file with its own vocabulary. The real field was the engine's `<EventOrigin>` type, written only in the hook log's `prompt.submit` rows. The handler logged those rows conditionally, so the log was complete for one arm only (`logAll: true`). A fix that read the log unchecked would have under-counted on every other arm.

> ```
> WRONG — search transcript data for the field name, accept the first hit:
> Grep  pattern='"origin"'  glob='**/*.jsonl'
> # finds "origin":{"kind":"human"} in an unrelated derivative analysis file
> # implement filtering on this field → silently wrong discriminator
>
> CORRECT — read the code that emits the field, confirm the vocabulary matches,
> and check for logging conditions that could make the source incomplete:
> Grep  pattern='<EventOrigin>'  glob='types/*.d.ts'                 # confirms composer/peer/task-notification
> Grep  pattern="on\('prompt.submit'"  path='<module>/hooks/'         # finds the actual producing code
> # → origin: e.origin.kind, logged only when (<ctx> !== null || <clearedQuestion> || <arm>.logAll)
> Grep  pattern='logAll'  path='<module>/hooks/arms/'                 # only one arm is a complete record
> ```

Two points follow.

- **Verify the vocabulary before trusting a hit.** When an item names a field and its value set, confirm the value set matches. A matching field name with a non-matching value set is a different schema, not a partial match.
- **Trace a data field to the code that writes it.** The absence of a row is exactly what a data-only search cannot see. Check the producing code for conditional logging before treating a log as an exhaustive source.

The rule that a verdict about a feature rests on a search of the implementation, not the prose, is [`verify-verdict-source.md`](verify-verdict-source.md) § "1. A Negative Verdict About a Feature Rests on a Symbol-Level Search of the Implementation, Never on Prose". This section applies it to a field in a record.

---

## 7. A Grader That Archives "The Transcript" Must Enumerate Every Session Id the Log Names

> [!constraint] "The transcript" is a singular that stops being true when a boundary mints a new session id
> A grader built on the singular fails silently. It still finds a file, computes a ledger, and prints a cost.

A grader archived one transcript per run and computed `Turns`, the per-call ledger and cost from it. A later arm ran `/clear` after each step, and each `/clear` minted a new session id, so the run spanned four. The grader archived one file under the last id, and that file held the first session's bytes. The sidecar's `Turns=4` and cost were one session's figures out of four.

Three consequences follow.

1. **Archive by the log, not by a lookup.** Enumerate every distinct `session_id` in the run's log. Archive the transcript at each `transcript_path`. Name each archive by its own id. A run with N ids produces N archives, or the grader says why not.
2. **Compute whole-run figures from the log's per-session rows when they exist.** The module's `turn.complete` rows carried cumulative usage per session (207,757 / 196,587 / 148,825 / 128,860 read tokens). Summing them was possible without the missing transcripts. Cost was not, because the cost formula lived only inside the grader. Expose it as a function that takes a transcript path.
3. **Print the scope beside the number.** `Turns=4 (session 1 of 4)` is honest. `Turns=4` is not. A results row that inherits a scoped number says so in its Notes cell, and the write-up does not compare it like for like.

> [!constraint] Every id the log names gets its own archive, and the scope prints beside the figure
> WRONG — one lookup, one archive, whole-run columns filled from it:
> ```
> last_id = last session_id in log            -> <id-4>
> archive(transcript_for(last_id))            -> writes <id-1>'s bytes as <id-4>.jsonl
> Turns, ledger, cost <- that file            -> 1 of 4 sessions, labelled as the run
> ```
> CORRECT — every id the log names, each archived under its own name, scope printed:
> ```
> ids = distinct session_id in log            -> [<id-1>, <id-2>, <id-3>, <id-4>]
> for id in ids: archive(transcript_path[id]) -> 4 files, 4 names
> Turns, ledger, cost <- sum over ids         -> "4 sessions; per-session rows below"
> ```

**Applies to** any grader, sidecar writer or cost reporter that archives or reads "the" session transcript. It also applies to arms, probes or hooks that call `/clear`, resume a session, or relaunch a child process mid-run, and to results tables where one row's `Turns` or `Cost` sits beside another row's.

---

*Cross-reference: [`dispatch-boundary-evidence.md`](dispatch-boundary-evidence.md) §4 (recovering a reply that did not route) · [`gate-positive-and-mutation-controls.md`](gate-positive-and-mutation-controls.md) §4 (fingerprint over flag) · [`gate-fixture-provenance.md`](gate-fixture-provenance.md) §6 (a known-good probe names a real target) · [`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`](agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md) §1.17 (classify every return before consuming it) · [`measure-scope-and-sample.md`](measure-scope-and-sample.md) §1 (validating the instrument is not validating the measurement)*
