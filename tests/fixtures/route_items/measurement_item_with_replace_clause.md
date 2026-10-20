---
id: 441
title: "Verify whether subagents inherit the project's permissions.deny entries and PreToolUse hooks"
priority: Medium
status: NOT_STARTED
abbrev: INFRA
created: 2026-10-06
blocks: []
route_hint: A
route_evidence: "a measurement item: three to six probe children graded on permission_denials, one §8.1 row and one §7 paragraph updated in hook-deny-contract.md; no code change unless the probe shows a gap"
route_dated: 2026-10-06
---

# BB-441-INFRA-SubagentDenyAndHookInheritanceUnverified: Verify whether subagents inherit the project's permissions.deny entries and PreToolUse hooks

**Priority:** Medium
**Domain:** INFRA
**Filed:** 2026-10-06 from the closeout of BB-440, at the user's request.

---

## Summary

The project's `cd` control is now two layers: the `"Bash(cd *)"` entry in `permissions.deny` and the `deny-cd.py` PreToolUse hook. Both were measured in a top-level `claude -p` child. Neither has been measured inside a subagent spawned by the Agent tool. One observation from the same day says the answer may be "not inherited": during a three-agent Explore fan-out, one subagent reported that a `cd … && ls` call **succeeded**, while its two siblings reported the same shape **denied**. The report is each agent's own prose, which `hook-deny-contract.md` §8.2 says is not evidence. Measure it.

## Problem

**Evidence, the conflicting reports (2026-10-06, three Explore subagents spawned in one message from the project root, CLI 2.1.292, before the hook was registered):**

| Subagent | What it reported about its own `cd` call |
|---|---|
| "Find cd deny mechanism and hooks" | "my first call in this search began `cd /c/Users/gabgo/source/repos/planwise-development; ls …` and came back as `Permission to use Bash with command cd /c/Users/... has been denied.`" |
| "Find pinned lint/test commands" | "`cd` is also actually denied here: my own `cd …` Bash call during this search was refused." |
| "Survey shell-discipline rules" | "My first Bash call in this search ran `cd /c/Users/gabgo/source/repos/planwise-development && ls …`, which breaks rule 3, and it succeeded without being denied." |

Two of three say denied; one says succeeded. The three commands differ in separator (`;` versus `&&`), which the permission entry should not care about (§8.1: "Denies `cd X && …`, quoted or not"). No `permission_denials` array was captured for any of the three, because the Agent tool's return is the subagent's prose, not its `result` event.

**Why it matters:** `references/rule-authoring.md` § Subagent Rule Loading already documents that path-scoped rules load dynamically in subagents, and `agent-orchestration.md` row 6 contradicts it. The same uncertainty now covers the harness controls. The project's task-runner, fix-agent, and backlog-author agents all hold `Bash`. If a subagent does not inherit `permissions.deny` or the hook, every `cd`-prohibition measurement made at the top level says nothing about where most of this project's shell work actually runs.

**What is known:** at the top level on CLI 2.1.292, the hook fires before the permission entry and its reason reaches the model verbatim (`hook-deny-contract.md` §5, §7). `rule-authoring.md` reports path rules load in subagents after file activity (7 rules observed). Nothing is recorded about `permissions.deny` or `hooks` in a subagent.

## Proposed Solution

Run the probe `hook-deny-contract.md` §7 asks for, and grade it on the record, not on prose (`references/measure-from-the-record.md`).

1. **Driver.** From the project root, a `claude -p --output-format stream-json --verbose --max-turns 4` parent whose prompt spawns one subagent via the Agent tool (type `general-purpose`, tools including `Bash`) with the instruction: run exactly `` `cd cloned-repos/planwise && git status --porcelain` `` once, then report the complete tool result text. Fence the command in backticks and say "adding no arguments" — the BB-440 run showed a child appends a sentence period as an argument otherwise.
2. **Grading.** The parent's `result` event `permission_denials` array, and the subagent's tool_result text if the stream exposes it. The subagent's prose is recorded but does not decide the row. If the parent's record does not carry the subagent's denials, say so explicitly and find the layer that does (the subagent transcript under the session directory) before concluding anything.
3. **Rows, both directions.** DENY side: `cd x && …`, `cd x; …`, `(cd x && …)`. Control side: `git -C cloned-repos/planwise status --porcelain` (must show real output). Run each row three times; the fan-out observation was 1-of-3, and §8.2 says a single clean reading is consistent with both "fixed" and "measuring the wrong thing".
4. **Discriminate the two layers.** If a subagent `cd` is denied, the reason text says which layer fired: the hook's text begins `cd is denied in this project`; the permission entry's text is the harness's `Permission to use Bash with command … has been denied`. Record which one.
5. **Record.** Update `hook-deny-contract.md` §7 (replace the "Subagent coverage is an open question" paragraph with the measured result) and §8.1 (add a "subagents" column or a note per row). If either layer is not inherited, file the remedy as its own item; this item is the measurement.

## Acceptance Criteria

- [ ] At least 3 DENY-shape rows and 1 control row, each run 3 times inside an Agent-tool subagent, graded on `permission_denials` or the subagent's own transcript, never on its prose
- [ ] For every denied row, the record names which layer fired (hook reason text versus harness permission sentence)
- [ ] `hook-deny-contract.md` §7's open-question paragraph is replaced by the measured result with the CLI version, and §8.1 states subagent coverage for both the `Bash(cd *)` entry and the hook
- [ ] If the result is "not inherited" for either layer, a follow-up item is filed and linked from this item's closing note; the fix is out of this item's scope
- [ ] The identifier predicate over `hook-deny-contract.md` is empty after the edit: `Grep pattern='(LL-[0-9]|BB-[0-9]|BLI-[0-9]|PLG-[0-9]|\bD-[0-9])' path='.claude/rules/hook-deny-contract.md'` returns no match

## Related

- `.claude/rules/hook-deny-contract.md` §5, §7, §8.1 — the top-level measurements and the open question this item closes
- `.claude/settings.json` — `permissions.deny` `"Bash(cd *)"` and the `hooks.PreToolUse` registration
- `.claude/hooks/deny-cd.py` — the hook whose reason text discriminates the layers
- `cloned-repos/planwise/plugins/planwise/references/measure-from-the-record.md` — grade a permission probe on `permission_denials`, not prose
- `cloned-repos/planwise/plugins/planwise/references/rule-authoring.md` § Subagent Rule Loading — the only existing subagent-inheritance measurement (rules, not controls)
- Originating item: BB-440 (closed 2026-10-06)

---

*Created: 2026-10-06*

## Loop Decision Needed

<!-- loop-decision run=20261012-222015 -->
> [!gate] User input needed
> Loop run 20261012-222015, 2026-10-12. The loop skipped this item without working it. Answer the question below, then triage it again.

Item 441 asks to measure whether Agent-tool subagents inherit the project's Bash(cd *) permissions.deny entry and the deny-cd.py PreToolUse hook, then record the result in .claude/rules/hook-deny-contract.md sections 7 and 8.1. The premise holds. Line 68 of hook-deny-contract.md still carries the paragraph 'Subagent coverage is an open question', and no section 8.1 subagent note exists. The loop skipped the item without working it for three reasons. First, the acceptance criteria need at least 4 rows (3 DENY shapes plus 1 control) run 3 times each, so 12 or more paid claude -p parent runs, each spawning a general-purpose subagent. The driver for them does not exist yet, and pinned-command-contracts.md section 1 requires running the pinned command once before trusting it, which a spend of that size needs your approval for. Second, the destination file is covered by scoped rules in .claude/rules/ (native-tool-promotion-gate.md, promotion-sync-target-scoping.md, rule-authoring.md), and loop mode treats a scoped-rule conflict as a documented skip. The item is a measurement item, not a lesson promotion, so the promotion exemption does not apply. Third, grading needs a human check on where a subagent's permission_denials surface. The item itself says the parent result event may not carry them and the subagent transcript under the session directory may be the only record. Route is B, score 25, matching route_at_init. The item carries route_hint A dated 2026-10-06, and the script wins because the live signals disagree with the hint (the clear-fix signal is mechanical only: line_anchor no, edit_target no, before_after yes, scope_bound no). Choose: (A) confirm the item as written, so 441 is triaged on the next run in an interactive session where you approve the 12-run probe spend and watch the first run; (B) take a smaller first pass of one DENY row (cd x && ...) and the control row, 3 runs each (6 runs), and extend to the other DENY shapes only if the first pass shows a subagent does not inherit a layer; or (C) name a different approach.
