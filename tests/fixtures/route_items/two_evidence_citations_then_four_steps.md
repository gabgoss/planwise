---
id: 616
title: "Glob gates with a path and a folder-led pattern return nothing in this repo; fix ZCU Sprint-02 gates and sweep plans"
priority: Medium
status: COMPLETE
abbrev: GATEIX
created: 2026-10-14
blocks: []
route_hint: B
route_evidence: "Two ZCU Sprint-02 gate rows plus 12 more occurrences in 8 other plan files; each needs a per-row rewrite and a target check"
route_dated: 2026-10-14
---

# BB-616-01-GATEIX-FolderLedGlobPatternWithPathReturnsNothing: Glob gates with a path and a folder-led pattern return nothing in this repo; fix ZCU Sprint-02 gates and sweep plans

**Priority:** Medium
**Domain:** GATEIX

---

## Summary

Inside this repository, the `Glob` tool returns "No files found" when it gets a `path` argument and its `pattern` starts with a literal folder name, such as `rows/**` or `scripts/x.py`. It does so even when matching files exist. The same `path` with a pattern that starts with `**`, or that names files only, works. The same folder-led pattern also works against a folder outside the repo (the plugin cache).

Plan gates are written in exactly this shape. An absence gate of that shape always passes, and a presence gate always fails. Two ZeroCallUpgrade Sprint-02 gates are affected, and 12 more occurrences sit in 8 other plan files.

This item corrects a claim made at the ZCU-S01-01 closeout. That claim said any `path` under `skills_wip/zero-call-upgrade/` was blind, and named Sprint-02's "No bytecode" row. It was wrong on both points. The failure depends on the pattern's shape, not the folder, and the "No bytecode" row (`**/__pycache__/*`) uses the working shape.

## Problem

Each probe below ran on 2026-10-14 against files present on disk. The expected file is listed in each probe's own result or in the companion probe.

| # | `path` | `pattern` | Result |
|---|--------|-----------|--------|
| 1 | `C:/Users/gabgo/source/repos/planwise-development/skills_wip/zero-call-upgrade/plugin` | `scripts/*.py` | No files found (88 `.py` files exist there) |
| 2 | `…/skills_wip/zero-call-upgrade/plugin/scripts` | `*.py` | 88 files (all of them) |
| 3 | `…/skills_wip/zero-call-upgrade` | `**/upgrade_run.py` | 1 file |
| 4 | `…/skills_wip/zero-call-upgrade` | `**/scripts/upgrade_run.py` | 1 file |
| 5 | `…/skills_wip/zero-call-upgrade/plugin/handlers` | `full/*.md` | No files found (3 files exist in `full/`) |
| 6 | `…/skills_wip/zero-call-list/plugin` | `scripts/skill_preflight.py` | No files found (the file exists) |
| 7 | `C:/Users/gabgo/source/repos/planwise-development/planwise/Plans/ZeroCallUpgrade` | `Sprint-01-BuildAndSandbox/*.md` | No files found (`ZCU-S01-Sprint-Plan.md` exists) |
| 8 | `C:/Users/gabgo/.claude/plugins/cache/planwise-marketplace/planwise/1.0.5.3` (outside the repo) | `scripts/*.py` | 85 files (all of them) |
| 9 | none (project-relative) | `skills_wip/zero-call-upgrade/plugin/scripts/upgrade_*.py` | 5 files |

**Evidence:** folder-led pattern plus an in-repo `path` returns nothing, while `**`-led and file-only patterns work. Verified 2026-10-14 by the nine `Glob` calls in the table. The cause is not established. Probe 8 shows it is not a property of the pattern alone.

**The two ZeroCallUpgrade Sprint-02 gates this breaks:**

1. `planwise/Plans/ZeroCallUpgrade/Sprint-02-MeasureAndReport/Session-01-MatrixAndReadme/ZCU-S02-01-01-Sonnet-BuildMatrixDriver.md`, lines 166-169:
   ```
   Glob  pattern='rows/**'  path='C:/Users/gabgo/source/repos/planwise-development/skills_wip/zero-call-upgrade/results'
   # pre-edit: "No files found" (`rows/` does not exist yet; Task 02 creates it when it runs a row) → invariant: "No files found" after the suite and after the dry-run wrapper, because every test passes tmp_path and the dry-run writes no file
   Glob  pattern='smoke.md'  path='C:/Users/gabgo/source/repos/planwise-development/skills_wip/zero-call-upgrade/results'
   # pre-edit: smoke.md present (1 file, written by Sprint-01 Task 05) → invariant: 1 file (control: smoke.md exists, so this Glob over the same folder proves the `rows/**` Glob above could have listed files if any existed)
   ```
   The absence gate always passes. Its "control" uses a different pattern shape (file-only), so the control passes and proves nothing about the `rows/**` call.
2. `planwise/Plans/ZeroCallUpgrade/Sprint-02-MeasureAndReport/Session-01-MatrixAndReadme/ZCU-S02-01-02-Sonnet-RunUnattendedRows.md`, lines 123-124:
   ```
   Glob  pattern='rows/row-{3,4,5}.{json,transcript.jsonl}'  path='C:/Users/gabgo/source/repos/planwise-development/skills_wip/zero-call-upgrade/results'
   # pre-edit: "No files found" (`rows/` does not exist before the first row runs) → expect 6 files
   ```
   This presence gate fails on correct work.

**Evidence:** both rows are present as quoted. Verified 2026-10-14 by `Grep pattern="Glob\s+pattern='[A-Za-z0-9_.{}-]+/[^']*'\s+path='" path=planwise/Plans/ZeroCallUpgrade/Sprint-02-MeasureAndReport output_mode=content`.

**The wider sweep:** the same Grep over `planwise/Plans` counts 16 occurrences in 10 files. Two are the rows above. Two are in the completed ZCU Sprint-01 Task 01 (`scripts/{…}` and `hooks/**`), which passed vacuously. The rest are in ZCP (Sprint plan, `ZCP-S01-02-04`, a gate-lint review), BHH `BHH-S01-01-06`, BIR `BIR-S05-03-04` and `BIR-S05-03-06`, and `ZCU-GateLint-2026-10-13.md`. A row whose `path` lies outside the repo (as in probe 8) is not affected, so each row needs its target checked.

**Evidence:** 16 occurrences in 10 files. Verified 2026-10-14 by `Grep pattern="Glob\s+pattern='[A-Za-z0-9_.{}-]+/[^']*'\s+path='" path=planwise/Plans output_mode=count`.

**Records of the corrected claim:** these records carry the overbroad version and should be corrected when this item runs:

- `planwise/LessonsLearned/LL-412-TOOL-GlobPathArgumentReturnsNothingUnderAnUntrackedSubtree.md` (title and Context say "under an untracked subtree");
- the ZCU-S02-01 Orchestration's Pre-Known flag `S01-10`, which names the "No bytecode" row;
- the ZCU-S01-01 Recovery Issues row and Summary Issues row on the `Glob` `path`.

## Proposed Solution

1. **Fix the two Sprint-02 gates** so the pattern carries no leading folder. Point `path` at the folder itself (`path='…/results/rows'`, `pattern='row-{3,4,5}.{json,transcript.jsonl}'`), or lead the pattern with `**/`. In `ZCU-S02-01-01`, make the control use the same shape as the gate it controls. One way: a `**/smoke.md` control beside a `**/rows/**` gate, or a `**`-led positive control on a file known to exist. Run each rewritten row once against a scratch tree holding a matching file, and once without one, before pinning it (`pinned-command-contracts.md` §6).
2. **Sweep the other 14 occurrences.** For each, check whether its `path` lies inside the repo. Rewrite the in-repo ones the same way, and record the out-of-repo ones as unaffected. For rows in completed plans, add a dated note beside the row rather than re-running the plan.
3. **Correct the records** listed under Problem: LL-412 (title, Context, Lesson), flag `S01-10` in the ZCU-S02-01 Orchestration, and the S01-01 Recovery and Summary rows. Keep each original sentence and add the correction with this item's probe table as evidence.
4. **Prevent recurrence.** Decide whether the project's gate rules, or the plugin's static gate linter, should flag a `Glob` row whose `pattern` starts with a literal folder segment while a `path` is set. Record the decision. If it is a plugin change, file it against the plugin repo without citing this item's id inside the shipped tree.

## Acceptance Criteria

- [x] The two ZCU Sprint-02 rows are rewritten. Each passes on a scratch tree with a matching file and fails, or reports absence, without one. Both runs are recorded beside the row (2026-10-14, see Notes)
- [x] In `ZCU-S02-01-01`, the control row uses the same pattern shape as the absence gate it vouches for (`**/smoke.md` beside `**/rows/**`)
- [x] A recount with the Grep from Problem lists every remaining occurrence as either rewritten or marked out-of-repo. The count of 16 is taken from the sweep, not from this item (recount 2026-10-14 after the rewrite: 14 occurrences in 8 files, every one annotated; see the sweep table in Notes)
- [x] LL-412, flag `S01-10`, and the S01-01 Recovery and Summary rows state the pattern-shape cause, and no longer name the "No bytecode" row as affected
- [x] A recorded decision on a lint or rule guard for the folder-led-pattern-plus-`path` shape (Notes, "Recurrence guard decision")

## Related

- `planwise/LessonsLearned/LL-412-TOOL-GlobPathArgumentReturnsNothingUnderAnUntrackedSubtree.md`: the lesson this item corrects.
- `planwise/Plans/ZeroCallUpgrade/Sprint-02-MeasureAndReport/Session-01-MatrixAndReadme/ZCU-S02-01-Orchestration.md`: flag `S01-10`.
- `.claude/rules/pinned-command-contracts.md` §6: run a pinned pattern against the real subject before pinning it.

## Notes

**Resolved 2026-10-14 via `/planwise backlog` Route B (task list, four steps).**

**Cause established.** The item left the cause open. Two probes on 2026-10-14 settled it. With `path` set to `…/skills_wip/zero-call-upgrade/plugin`, the full project-relative pattern `skills_wip/zero-call-upgrade/plugin/scripts/upgrade_*.py` returned all five files, and with `path` at `…/plugin/handlers`, `skills_wip/zero-call-upgrade/plugin/handlers/full/*.md` returned all three. So inside the project, Glob anchors a pattern that contains a slash at the project root, and `path` only filters the results to its subtree. A folder-led pattern can never match. The nested plugin repo is inside the project too: `plugins/planwise/scripts/parse_backlog.py` with `path='…/cloned-repos/planwise'` returned nothing, `**/scripts/parse_backlog.py` returned the file.

**Gate proof (step 1).** A scratch `results/rows/` holding the six expected names was created, probed, and removed in its own call. Results, all with `path='…/results'`:

| Pattern | With `rows/` populated | Without `rows/` |
|---|---|---|
| `rows/**` (old) | No files found | No files found |
| `rows/row-{3,4,5}.{json,transcript.jsonl}` (old) | No files found | No files found |
| `**/rows/**` (new) | 6 files | No files found |
| `**/rows/row-{3,4,5}.{json,transcript.jsonl}` (new) | 6 files | No files found |
| `**/smoke.md` (new control) | 1 file | 1 file |

**Sweep (step 2).** The Grep from Problem counted 16 occurrences in 10 files before the rewrite and 14 in 8 files after it. Each remaining row carries a dated note:

| File | Rows | Class | Disposition |
|---|---|---|---|
| `ZCU-S01-01-01-Sonnet-ScaffoldAndCopy.md` | 104, 106 | in-repo, Sprint-01 complete | note beside each row |
| `BHH-S01-01-06-Sonnet-ClosingGates.md` | 81, 82 | in-repo (nested plugin repo), BHH complete | note after the rows |
| `BIR-S05-03-04-Sonnet-GeneratorTestsAndFlip.md` | 112, 113 | in-repo, session complete | note after the rows |
| `BIR-S05-03-06-Opus-DiscriminationProof.md` | 121, 122 | in-repo, session complete | note after the rows |
| `ZCP-S01-Sprint-Plan.md` | 58 | in-repo (relative `path`), ZCP complete | sub-bullet note |
| `ZCP-S01-02-04-Sonnet-PublishAndVerifyInstalled.md` | 87, 96 | out-of-repo (plugin cache), probe returned the file | note: unaffected |
| `ZCP-GateLint-2026-10-10.md` | 86, 92 | quotes of the out-of-repo rows | note: unaffected |
| `ZCU-GateLint-2026-10-13.md` | 73 | quote of the pre-rewrite Sprint-02 row | note: rewritten in the task file |

**Records (step 3).** LL-412's frontmatter title, H1, Context, Lesson (the WRONG example had shown the working `**`-led shape) and Applies To carry the correction. The filename keeps its capture wording. The lessons index was regenerated. Flag `S01-10` in the ZCU-S02-01 Orchestration, the S01-01 Recovery Issues row and flag row 10, and the S01-01 Summary Issues row, flag row 10 and lesson line carry the correction beside the original sentence.

**Recurrence guard decision (step 4).** Two guards, one shipped now and one filed:

1. **Project rule, shipped.** `.claude/rules/pinned-command-contracts.md` §6.4 states the mechanism, the probe table, WRONG and CORRECT rows and three rules. Its `paths:` already covers `planwise/Plans/**` and `planwise/Backlog/**`, so it loads where gates are authored. `CLAUDE.md` "Empty Is Not Clean" gained a fourth form naming the shape, and the Rules Index row points at §6.4.
2. **Plugin gate linter, filed as a follow-up.** `scripts/lint_verification_gates.py` has no `Glob` handling today (Grep for `Glob` over it returns nothing). A check that flags a `Glob` row whose `pattern` starts with a literal folder segment while `path` is set is a plugin change. It is filed as a separate backlog item at this item's close, worded without this item's id.

**Open bookkeeping.** LL-412 still reads `status: documented` with `promotion-target: [rule]`. §6.4 now carries its corrected content, so the lesson is ready for `/planwise lessons promote 412`, which records the pointer fields and the promotion log row. This item did not flip the lesson's lifecycle fields.

---

*Created: 2026-10-14*
