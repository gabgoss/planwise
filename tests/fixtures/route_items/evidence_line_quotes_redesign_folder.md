---
id: 415
title: "Resuming the same runner across new rounds of DELEGATED work lets its context grow unbounded"
priority: High
status: NOT_STARTED
abbrev: PROC
created: 2026-09-27
blocks: []
route_hint: B
route_evidence: "Scope is three known reference/handler files with an existing resume-protocol section to extend (Part-2 §1.17, Part-3 §1.25.2, run.md Step 3.4) -- a bounded task list, not a single-file fix or a session plan."
route_dated: 2026-09-27
---

# BB-415-PROC: Resuming the same runner across new rounds of DELEGATED work lets its context grow unbounded

**Priority:** High
**Domain:** PROC

---

## Summary

The DELEGATED dispatch discipline tells an orchestrator to "resume the SAME agent" / "resume the SAME runner via `SendMessage`" in several places, and every one of those rules is written for **finishing the task the runner was already dispatched for** -- a stall, a self-delegation, a mid-action stop, or unreported silence. None of them bounds resumption to that case, and none checks the runner's accumulated size before a resume. Nothing stops an orchestrator from reaching for the same "resume the SAME agent" instinct when a **new** round of work arrives (a fix loop, a caveat-closure pass, a review-fix round) for a runner that already finished its original task. Each resumed turn re-bills the runner's whole accumulated history, so the cost compounds silently across rounds with no ceiling anywhere in the discipline.

## Problem

**Observed, this session (BIR-S05-07, 2026-09-27).** A Sonnet task-runner (`bir-s05-07-02`) was dispatched for one task (Task 2, WireUpgradeAndInit). The orchestrator then resumed that same runner via `SendMessage` for three more rounds of NEW work after the original task completed: a fix loop after a release dry run, gate-caveat closure, and a code-review fix round. The user flagged it at roughly 750K tokens -- each resumed turn had re-billed the runner's whole accumulated history. The orchestrator stopped it with TaskStop mid-edit, then dispatched a fresh runner (`bir-s05-07-rfa`) with a lean brief: an on-disk inventory of the partial work marked UNVERIFIED, and pinned content hashes with a frozen-snapshot self-check before the first write.

**Evidence:** the session's own Recovery Change Log carries this exact account -- verified 2026-09-27 by reading `planwise/Plans/BacklogIndexRedesign/Sprint-05-LessonsIndexPort/Session-07-UpgradeWiringAndLogWriters/BIR-S05-07-Recovery.md` line 220:
> `| 2026-09-27 | RF | RUNNER REPLACED | The user flagged bir-s05-07-02 at about 750K tokens: it had been resumed four times (Task 2, the fix loop, the caveats, the review round). The orchestrator stopped it mid-edit (TaskStop). Inventory: promotion_log.py partly edited (new imports, _normalize_cell; ruff 2 errors); test_promotion_log.py and the docs untouched. Hashes pinned. A fresh Sonnet runner bir-s05-07-rfa was dispatched with the partial work marked UNVERIFIED and a frozen-snapshot self-check. Lesson candidate: start a fresh runner with a lean brief for each new round, instead of resuming a long-lived one.`

**Root cause, confirmed live in the plugin (dev tree, `cloned-repos/planwise/plugins/planwise/`) on 2026-09-27.** Every "resume the SAME" rule found is scoped to completing the runner's ORIGINAL dispatch, never to a new round:

- `references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.17 "Task-Runner Dispatch Failure Modes and Resume Protocol" -- the diagnosis table (lines 154-156) resumes the SAME agent for self-delegation, a message-boundary stall, and a mid-action stall "masquerading as completion." Line 215: `"On any miss, resume the SAME agent to finish (never re-dispatch a fresh one), then re-run the checks before accepting."` -- "to finish" is the operative scope in every instance; none of §1.17 addresses a runner being asked to start a DIFFERENT round of work.
- `references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` §1.25.2 "Pattern-divergence proposal", line 117: `"Redirect protocol -- resume the SAME runner via SendMessage (its context holds the task) with the rationale stated..."` -- again scoped to steering the runner back onto the task it already holds, not to handing it new work.
- `handlers/run.md` Step 3.4 "Handle Task Failure": line 447, `"4. Stalled -> resume the SAME agent per §1.17, never a fresh one."`; the Unreported-silence branch (line 442) is the same failure-recovery frame -- the runner's silence is being diagnosed as alive/stalled/dead, never as "finished and being asked to do something new."

**Evidence:** all four citations above verified 2026-09-27 by `Grep` for `SAME agent|resume the same|SendMessage|fresh runner` over the three files (`agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`, `agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md`, `handlers/run.md`) in the dev tree at `cloned-repos/planwise/plugins/planwise/`.

**No existing bound found.** Grepped the same three files plus `references/error-pattern-catalog.md` for `resume.{0,80}(budget|ceiling|token|size|accumulat)`. The only hit is §1.17.4's `"budget 1-2 resume round-trips into session-time estimates"` (`Part-2`, line 182) -- a *time-estimation* note for planning a session, not a size ceiling checked before a resume decision. `error-pattern-catalog.md` rows 21-23 flag a MISSING "SendMessage resume protocol" and a MISSING "N>25 resume protocol + tool-use budget estimation" as BLOCKER findings elsewhere in the discipline -- both about resume happening at all, not about bounding it to the original task or capping accumulated size. Nothing in the corpus checks a runner's accumulated context before a resume, and nothing distinguishes "resume to finish" from "resume for a new round." This is a gap, not a narrowing of an existing rule.

## Proposed Solution

1. **Add a resume-scope rule to the delegated dispatch discipline** (a new subsection near §1.17 in `agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md`, cross-referenced from §1.25.2 and `handlers/run.md` Step 3.4): resume the same runner ONLY to complete the task it was dispatched for (a stall, self-delegation, mid-action stop, or unreported silence per §1.17/Step 3.4's existing diagnosis table). For any NEW round of work on a runner that already reported completion -- a fix loop, a caveat-closure pass, a review-fix round, or any newly scoped task -- dispatch a FRESH runner instead. The fresh runner's brief carries: the findings/inventory file path, an on-disk inventory of prior work marked UNVERIFIED, and pinned content hashes with a frozen-snapshot self-check before its first write (the same shape `handlers/run.md` line 448 already prescribes for the "Genuinely dead" branch -- reuse that pattern rather than inventing a new one).
2. **Add a size check before any resume.** Before resuming a runner for ANY reason, the orchestrator estimates that runner's accumulated context (its original dispatch budget plus every round already resumed into it). Past a stated ceiling, dispatch fresh instead of resuming, even to finish the original task. Suggested starting ceiling: 2x the task's declared budget, or 200,000 tokens, whichever is lower -- state explicitly in the new rule that this figure is a starting point to measure and revise, not a derived value, consistent with how `handlers/run.md` §3.5 already labels its own 400,000/194 checkpoint defaults as "operating defaults derived from measured accumulation bands, not a statistical boundary."
3. **Wire `handlers/run.md`** Step 3.3 (Post-Task Update) and Step 3.4 (Handle Task Failure), and the parallel-batch reconciliation step, to point at the new rule rather than restating "resume the SAME agent" unqualified. Add a Recovery Change Log convention recording which runner id handled each round of a task's lifecycle (the RF row in this session's own Recovery file already does this ad hoc -- make it a named convention so reuse is visible without reading the whole Recovery file's prose).
4. **Record the measurement that motivated this** in the new rule's own rationale, generically stated (no session/task ids in the shipped text per `plugin-identifier-isolation.md`): one runner resumed across 4 rounds reached roughly 750K tokens against a roughly 48K-token planned task budget for its first round alone -- a documented instance of unbounded compounding, not a one-off.

## Acceptance Criteria

- [ ] A new resume-scope rule exists in the delegated dispatch discipline distinguishing "resume to finish the original dispatch" from "resume for a new round of work," with the latter routed to a fresh-runner dispatch carrying a lean brief, an UNVERIFIED inventory, and a frozen-snapshot self-check.
- [ ] A stated, explicitly-provisional context-size ceiling gates any resume decision (original-task or new-round), expressed in the same units and confidence framing `handlers/run.md` §3.5 already uses for its own checkpoint defaults.
- [ ] `handlers/run.md` Step 3.3, Step 3.4, and the parallel-batch reconciliation step each reference the new rule instead of restating an unqualified "resume the SAME agent."
- [ ] A Recovery Change Log convention for recording which runner id handled each round is documented somewhere in the discipline (not only demonstrated ad hoc in one session's Recovery file).
- [ ] No project-side bookkeeping ID (session names, task labels like `bir-s05-07-02`) ships into the plugin text -- the shipped wording states the generic condition and measurement, per `plugin-identifier-isolation.md`.

## Related

- Recovery evidence: `planwise/Plans/BacklogIndexRedesign/Sprint-05-LessonsIndexPort/Session-07-UpgradeWiringAndLogWriters/BIR-S05-07-Recovery.md` line 220 (RF row).
- `cloned-repos/planwise/plugins/planwise/references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md` §1.17, §1.17.4, §1.18-adjacent text at line 215.
- `cloned-repos/planwise/plugins/planwise/references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md` §1.25.2 (line 117).
- `cloned-repos/planwise/plugins/planwise/handlers/run.md` Step 3.4 (lines 433-449) and Step 3.5 (lines 451-479, the sibling session-length checkpoint whose defaults framing this item's ceiling should match).
- `cloned-repos/planwise/plugins/planwise/references/error-pattern-catalog.md` rows 21-23 (adjacent, unresolved resume-protocol gaps in the same discipline).

---

*Created: 2026-09-27*
