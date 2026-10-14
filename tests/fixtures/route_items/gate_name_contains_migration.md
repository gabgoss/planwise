---
id: 515
title: "Convenience gates in upgrade and doctor handlers have no Inference Defaults row in auto-mode-policy.md"
priority: Low
status: NOT_STARTED
abbrev: DOC
created: 2026-10-10
blocks: []
route_hint: B
route_evidence: "8 sites in 2 handler files plus one reference table; wording is known and edits are mechanical, but a new wording test is a design choice"
route_dated: 2026-10-10
---

# BB-515-DOC-ConvenienceGatesMissingInferenceDefaultsRows: Convenience gates in upgrade and doctor handlers have no Inference Defaults row in auto-mode-policy.md

**Priority:** Low
**Domain:** DOC

---

## Summary

`references/auto-mode-policy.md` § Inference Defaults says it is the single source for every convenience default. Eight `AUTO-MODE: convenience` gates in two handler files state their default only in the handler text and have no row in that table. The upgrade handler's gates for the stale mirror prune, the plan-status anomaly and the reciprocal-edge migration questions do have rows, so those three are excluded here.

Source: found while closing the upgrade-surfaces session of the UpgradeRunDefects plan, which added the three rows above. Severity is low because every handler already states a safe default in its own text. The gap is a drift risk, not a live defect.

## Problem

The table's own rule 2 reads: "Never leave a default stated only in a handler comment. Add the row. Otherwise a consumer reading this table sees no default while a consumer reading the handler sees one, which is the drift rule 1 exists to prevent."

**Evidence:** the table is at `auto-mode-policy.md` line 157 (`### § Inference Defaults`), rows at lines 170-194, and the last three rows are the reciprocal-edge, stale mirror prune and plan-status anomaly rows — verified 2026-10-10 at plugin HEAD 2d58ab4 by `Grep pattern='Inference Defaults' path=cloned-repos/planwise/plugins/planwise/references/auto-mode-policy.md` then `Read offset=157 limit=40`.

**Evidence:** the table has no row for any of the eight sites below — verified 2026-10-10 by `Grep -i pattern='additionalDirectories|THRIFTY|TODO_TOOLS|recovery artifact|transfer file|feedback|gh |prune-upgrade|doctor' path=.../references/auto-mode-policy.md`, which matched only line 55 (an unrelated sentence about outward-facing posts).

**Evidence:** the full set of `AUTO-MODE: convenience` hits in the two files — verified 2026-10-10 by `Grep pattern='AUTO-MODE: convenience' path=cloned-repos/planwise/plugins/planwise/handlers/` (files `upgrade-Part-3-BannerAndConflictResolution.md` and `doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md`), then a `Read` of each hit line.

### Uncovered gates (8)

Paths are relative to `cloned-repos/planwise/plugins/planwise/handlers/`.

| # | File:line | Step | Gate question | Default stated in the handler |
|---|---|---|---|---|
| 1 | `upgrade-Part-3-BannerAndConflictResolution.md:354` | Step 4.1 case C | Delete the transfer file `{path}`? (the shipped file now carries its content) | skip, "so an unattended run never deletes a transfer file" |
| 2 | `upgrade-Part-3-BannerAndConflictResolution.md:409` | Step 4.3 | Delete the {N} `{class}` recovery artifact(s) at `{path}`? (one question per prunable class) | skip, "an unattended/non-interactive run never deletes a recovery artifact" |
| 3 | `upgrade-Part-3-BannerAndConflictResolution.md:451` | Step 4.4 | Normalize version-pinned plugin-cache grants in `additionalDirectories` to the family root? | report-only, change nothing, "never rewrites `additionalDirectories`" |
| 4 | `upgrade-Part-3-BannerAndConflictResolution.md:473` | Step 4.5 | Install the GitHub CLI (offered as init.md Step 9.5 specifies)? | No, install nothing, "never invokes a package manager" |
| 5 | `upgrade-Part-3-BannerAndConflictResolution.md:497` | Step 4.6 | Add `CLAUDE_CODE_ENABLE_TODO_TOOLS: "1"` to {settings_path}'s env block? | report-only, change nothing, "never rewrites `env`" |
| 6 | `upgrade-Part-3-BannerAndConflictResolution.md:519` | Step 4.7 | Set `CLAUDE_CODE_THRIFTY_SONIC: "false"` in {the files that are missing or wrong}? | **add** (the one default that writes unattended) |
| 7 | `doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md:85` | Stage 14b (`--prune-upgrade-leftovers`) | Delete leftovers, one question per present prunable class (inert, safe-to-discard) | skip-all in unattended runs |
| 8 | `doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md:347` | Stage 17b (`--create-feedback-dir`) | Create the missing feedback directory at `{feedback_dir_path}`? | skip in unattended runs |

### Excluded (already covered by a row, or out of this item)

| File:line | Gate | Why excluded |
|---|---|---|
| `upgrade-Part-3-BannerAndConflictResolution.md:244` | Stale mirror prune (`/planwise doctor --prune-stale`) | Row "Stale mirror prune question" at `auto-mode-policy.md:193` |
| `upgrade-Part-3-BannerAndConflictResolution.md:286` | Plan status anomaly | Row "Plan status anomaly question" at `auto-mode-policy.md:194` |
| `upgrade.md` Step 2.3b (not in the two files scanned) | Reciprocal-edge migration questions | Row at `auto-mode-policy.md:192` |

### Observations for whoever fixes this

- Gates 1, 2 and 7 share one default (delete nothing) and gate 2's text says doctor's prune uses "the same per-class confirm contract". One shared row may cover all three, or two rows if the maintainer wants the per-class gate separate from the per-file gate.
- Gates 3 and 5 share the shape "settings-file write, report-only when unattended". Gate 6 breaks that shape by defaulting to **add**. A row for it must state why an additive env write is safe unattended, or the handler default should be revisited. That decision belongs to the fixer.
- The line numbers are hints. Handlers drift, so re-locate by content (`Grep pattern='AUTO-MODE: convenience'`) rather than by line.

## Proposed Solution

For each uncovered gate, either:

1. Add one row to `references/auto-mode-policy.md` § Inference Defaults naming the handler and step, the default, and the rationale (use the existing rows at lines 192-194 as the shape: `{Question} ({handler} {Step})` | `{default}. {rationale}.`), and make the handler text cite the row instead of restating the default (rule 1 of the table), or
2. Record in the item's closing note why the gate needs no row.

Then consider a wording test in `cloned-repos/planwise/tests/` that walks every `AUTO-MODE: convenience` site in `plugins/planwise/handlers/` and asserts that each maps to a table row. A prior item added `test_auto_mode_policy_lists_each_loop_default` for the loop-mode rows, which is the closest existing shape. The test must key on a stable marker, not on line numbers, and per the project's gate rules it needs a dry run in both directions (it fails when a row is removed and passes when present).

Out of scope: any change to the `AUTO-MODE: critical` gates, and any change to which handlers ask the questions.

## Acceptance Criteria

- [ ] Each of the eight gates in the table above has a row in `auto-mode-policy.md` § Inference Defaults, or a recorded reason it needs none.
- [ ] The handler text for each gate cites the row and does not contradict it.
- [ ] Gate 6 (`CLAUDE_CODE_THRIFTY_SONIC`, default **add**) has an explicit rationale in its row, or its handler default is changed.
- [ ] If the wording test is added, a set comparison (not a count) shows every `AUTO-MODE: convenience` site in `handlers/` maps to a row, and removing one row makes the test fail.
- [ ] Plugin tests and `python -m ruff check cloned-repos/planwise` pass.

## Related

- [BB-499-APP-LoopModeNoMidLoopQuestions.md](Archive/BB-499-APP-LoopModeNoMidLoopQuestions.md) - added the loop-mode rows and the `test_auto_mode_policy_lists_each_loop_default` pattern this item would extend

---

*Created: 2026-10-10*
