#!/usr/bin/env python3
"""Unit tests for the `--body-status` mode of reconcile_backlog.py.

`reconcile_backlog.detect_body_status(config)` finds every legacy
`**Status:**` line left in a backlog item's header block: the lines after
the first H1 that follows the frontmatter, up to the first `---` or `## `
line, never counting a fenced line. `reconcile_backlog.reconcile_body_status`
strips exactly that line, with its own terminator, on explicit `--write`.

The value of the pass is where it refuses to match, so every fixture below
is real item bytes, copied byte-for-byte (line endings included) from the
live project by a generator script, never retyped. Each fixture keeps whole
source lines from the ranges its comment names. Every fixture is written
with `write_bytes` and every write assertion reads `read_bytes()`: a
`write_text` fixture would translate `\\n` to `os.linesep` and cancel out
the exact newline rewrite these tests exist to catch.

Each test builds an isolated temp planwise tree (config.yaml + item files +
an index); none read or mutate the live project's backlog.

Run with:  python -m pytest tests/test_reconcile_backlog_body_status.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import reconcile_backlog
import reconcile_common
from reconcile_backlog import (
    _body_start_index,
    _scan_body_status,
    detect_body_status,
    reconcile_body_status,
)

CONFIG_YAML_FIXTURE = """project:
  name: "BodyStatusFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

# A CRLF index, so a stray index write would show up as a byte change.
INDEX_BYTES = (
    b"| ID | Title | Priority | Status | Abbrev | Score | File |\r\n"
    b"|----|-------|----------|--------|--------|-------|------|\r\n"
)

# --- Fixtures: real item bytes, generated from the live files ---

# F1 - planwise/Backlog/Archive/BB-239-01-DOC-HookDenyContractMdPin.md,
# source lines 1-30, CRLF. Hazard: line 16 `**Status:** NOT_STARTED` under
# frontmatter `status: COMPLETE`. Pins the one live `disagrees` drift:
# archived, CRLF, first line after the H1's blank line.
F1_BB239 = (
    b'---\r\n'
    b'id: 239\r\n'
    b'title: "Fix: hook-deny-contract.md cites `2.1.233` pins 2.1.233, newest is 2.1.278"\r\n'
    b'priority: High\r\n'
    b'status: COMPLETE\r\n'
    b'abbrev: DOC\r\n'
    b'created: 2026-09-19\r\n'
    b'blocks: []\r\n'
    b'route_hint: A\r\n'
    b'route_evidence: "cliwatch 2.1.277 2.1.278: pin at `.claude/rules/hook-deny-contract.md` (surface permission_decision_enum), verified 2026-09-19"\r\n'
    b'route_dated: 2026-09-19\r\n'
    b'---\r\n'
    b'\r\n'
    b'# BB-239-01-DOC: Fix: hook-deny-contract.md cites `2.1.233` pins 2.1.233, newest is 2.1.278\r\n'
    b'\r\n'
    b'**Status:** NOT_STARTED\r\n'
    b'**Domain:** DOC\r\n'
    b'**Priority:** High\r\n'
    b'**Created:** 2026-09-19\r\n'
    b'**Source:** cliwatch 2.1.277 2.1.278\r\n'
    b'**Watch key:** 2.1.277__2.1.278 | .claude/rules/hook-deny-contract.md | permission_decision_enum | pin\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Problem\r\n'
    b'\r\n'
    b'The file `.claude/rules/hook-deny-contract.md` cites `2.1.233` at line 8.\r\n'
    b'Surface: `permission_decision_enum`. Change kind: `pin`.\r\n'
    b'Old \xe2\x86\x92 new: `2.1.277` \xe2\x86\x92 `2.1.278`.\r\n'
    b'Edit only `.claude/rules/hook-deny-contract.md`; touch no other file.\r\n'
)

# F2 - planwise/Backlog/BB-240-01-INFRA-VERSIONJsonPin.md, source lines 1-30,
# LF. Hazard: line 16 `**Status:** NOT_STARTED` under frontmatter
# `status: NOT_STARTED`. Pins the LF `redundant` drift shape.
F2_BB240 = (
    b'---\n'
    b'id: 240\n'
    b'title: "Fix: VERSION.json cites `2.1.274` pins 2.1.274, newest is 2.1.278"\n'
    b'priority: High\n'
    b'status: NOT_STARTED\n'
    b'abbrev: INFRA\n'
    b'created: 2026-09-19\n'
    b'blocks: []\n'
    b'route_hint: A\n'
    b'route_evidence: "cliwatch 2.1.277 2.1.278: pin at `hooks_wip/hook-module-poc/VERSION.json` (surface plugin_types), verified 2026-09-19"\n'
    b'route_dated: 2026-09-19\n'
    b'---\n'
    b'\n'
    b'# BB-240-01-INFRA: Fix: VERSION.json cites `2.1.274` pins 2.1.274, newest is 2.1.278\n'
    b'\n'
    b'**Status:** NOT_STARTED\n'
    b'**Domain:** INFRA\n'
    b'**Priority:** High\n'
    b'**Created:** 2026-09-19\n'
    b'**Source:** cliwatch 2.1.277 2.1.278\n'
    b'**Watch key:** 2.1.277__2.1.278 | hooks_wip/hook-module-poc/VERSION.json | plugin_types | pin\n'
    b'\n'
    b'---\n'
    b'\n'
    b'## Problem\n'
    b'\n'
    b'The file `hooks_wip/hook-module-poc/VERSION.json` cites `2.1.274` at line 1.\n'
    b'Surface: `plugin_types`. Change kind: `pin`.\n'
    b'Old \xe2\x86\x92 new: `2.1.277` \xe2\x86\x92 `2.1.278`.\n'
    b'Edit only `hooks_wip/hook-module-poc/VERSION.json`; touch no other file.\n'
)

# F3 - planwise/Backlog/BB-375-01-DOC-HookDenyContractDeferValueGap.md, source
# lines 1-19, CRLF. Hazard: line 14 `**Status:** NOT_STARTED` between
# `**Priority:**` and `**Domain:**` (the old template shape). Pins a status
# line that is not the first line of the header block.
F3_BB375 = (
    b'---\r\n'
    b'id: 375\r\n'
    b'title: "hook-deny-contract.md never documents the `defer` permission-decision value"\r\n'
    b'priority: Medium\r\n'
    b'status: NOT_STARTED\r\n'
    b'abbrev: DOC\r\n'
    b'created: 2026-09-19\r\n'
    b'blocks: []\r\n'
    b'---\r\n'
    b'\r\n'
    b'# BB-375-01-DOC: hook-deny-contract.md never documents the `defer` permission-decision value\r\n'
    b'\r\n'
    b'**Priority:** Medium\r\n'
    b'**Status:** NOT_STARTED\r\n'
    b'**Domain:** DOC\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Summary\r\n'
)

# F4 - planwise/Backlog/Archive/BB-005-01-PROC-ScaffoldSprintStatus.md, source
# lines 1-49, CRLF. Hazard: line 43 `**Status:** PLANNED` at column 0 inside
# a ```markdown fence (lines 42-45) under `### 2.` in `## Proposed Solution`.
# Pins: a fenced example after the header block is never drift. The header
# block closes at line 16 (`---`), before the fence opens.
F4_BB005 = (
    b'---\r\n'
    b'id: 005\r\n'
    b'title: "Enforce PLANNED status for scaffolded sprint plans"\r\n'
    b'priority: Medium\r\n'
    b'status: COMPLETE\r\n'
    b'abbrev: PROC\r\n'
    b'created: 2026-03-19\r\n'
    b'blocks: []\r\n'
    b'---\r\n'
    b'\r\n'
    b'# BB-005-PROC: Enforce PLANNED status for scaffolded sprint plans\r\n'
    b'\r\n'
    b'**Priority:** Medium\r\n'
    b'**Domain:** PROC\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Summary\r\n'
    b'\r\n'
    b"When scaffolding multi-sprint plans, all Sprint Plans should use `**Status:** PLANNED` \xe2\x80\x94 only the Master Plan gets `READY_TO_EXECUTE`. Agents generating sprint files sometimes copy the Master Plan's status instead of using the Sprint Plan template's status, creating inconsistencies caught during review.\r\n"
    b'\r\n'
    b'## Problem\r\n'
    b'\r\n'
    b"The scaffolding Master Plan template correctly sets `Status: READY_TO_EXECUTE` (the plan itself is ready). But the Sprint Plan template uses `Status: PLANNED`. When agents generate sprint plans in parallel, they may copy the Master Plan's status rather than the Sprint Plan template's status, resulting in:\r\n"
    b'\r\n'
    b'1. Sprint 02 marked `READY_TO_EXECUTE` while Sprint 01 (a prerequisite) is still `NOT STARTED`\r\n'
    b'2. Inconsistency across sprints \xe2\x80\x94 some use `PLANNED`, others use `READY_TO_EXECUTE`\r\n'
    b'3. Review catches these as warnings, but the error should be prevented at generation time\r\n'
    b'\r\n'
    b'Source: LL-005-PROC from Deux-G-Plan-De-Retraite project (HBS Exec-HBS scaffolding review).\r\n'
    b'\r\n'
    b'## Proposed Solution\r\n'
    b'\r\n'
    b'Two changes:\r\n'
    b'\r\n'
    b'### 1. `handlers/plan.md` \xe2\x80\x94 Explicit agent prompt instruction\r\n'
    b'When generating scaffolding agent prompts for Sprint Plan files, add an explicit instruction:\r\n'
    b'> "Set Sprint Plan status to PLANNED (not READY_TO_EXECUTE). Only the Master Plan uses READY_TO_EXECUTE."\r\n'
    b'\r\n'
    b'### 2. `templates/sprint-plan.md` \xe2\x80\x94 Add inline comment\r\n'
    b'Add a comment or callout near the Status field:\r\n'
    b'```markdown\r\n'
    b'**Status:** PLANNED\r\n'
    b'<!-- All Sprint Plans start as PLANNED. Transition to IN_PROGRESS -> COMPLETE during execution. -->\r\n'
    b'```\r\n'
    b'\r\n'
    b'### 3. `agents/structural-reviewer.md` \xe2\x80\x94 Add specific check\r\n'
    b"Add to the structural reviewer's checklist: verify that no Sprint Plan has `READY_TO_EXECUTE` status while its prerequisites are incomplete.\r\n"
    b'\r\n'
)

# F5 - planwise/Backlog/BB-096-01-INFRA-ItemBodyStatusLineNeverSynced.md, source
# lines 1-97, CRLF. Hazards: line 3 (`**Status:**` in the frontmatter title);
# lines 14, 15, 17, 19 (inside a `> [!note]` callout before the H1 at line 21);
# lines 35 and 65 (inside fences); lines 30, 72, 96 (inline code and prose).
# Pins: none of these is a header-block status line (header block 22-25).
F5_BB096 = (
    b'---\r\n'
    b'id: 096\r\n'
    b'title: "Backlog item bodies carry a second **Status:** line that only the create path writes \xe2\x80\x94 52 of 61 archived items contradict their own frontmatter"\r\n'
    b'priority: Medium\r\n'
    b'status: PLANNING\r\n'
    b'abbrev: INFRA\r\n'
    b'created: 2026-08-12\r\n'
    b'blocks: []\r\n'
    b'---\r\n'
    b'\r\n'
    b'> [!note] Re-measured by BIR Sprint-04 Session-01 Task 6, 2026-09-23 \xe2\x80\x94 NOT closed, gate fails\r\n'
    b'> Master Plan Project Complete criterion names this item for closure with `delivered_by: BIR`. Both of its own gates were re-run against the current tree:\r\n'
    b'>\r\n'
    b"> - **Body `**Status:**` drift over `Archive/BB-*.md`:** the pre-edit baseline (2026-08-12) was 52; `BIR-S01-03-CorpusGate.md` (2026-09-19) measured 110 \xe2\x86\x92 1 (the sole survivor, `Archive/BB-005` line 43, inside a fenced example quoting `**Status:** PLANNED` as template text \xe2\x80\x94 not a real drift). Re-running the identical loop now over 194 archived files returns **2**: the same legitimate `Archive/BB-005` fenced-example survivor, plus a **new, genuine drift** at `Archive/BB-239-01-DOC-HookDenyContractMdPin.md` (frontmatter `status: COMPLETE`, body `**Status:** NOT_STARTED` at line 16, not inside any fence \xe2\x80\x94 a real desync). BB-239 was created 2026-09-19 (a cli-watch-generated item, `created:` in its own frontmatter), after Sprint-01's repair pass, so this is a fresh instance of the exact writer-gap class this item exists to fix, not a re-occurrence of the known BB-005 exception.\r\n"
    b'> - **Template no longer emits the body line:** confirmed \xe2\x80\x94 `Grep` for `**Status:**` over `cloned-repos/planwise/plugins/planwise/templates/backlog-item.md` returns zero matches.\r\n'
    b'>\r\n'
    b'> Per this task\'s Hard Constraint 5 and its own Notes for Agent ("if either fails, do not close it: report it"), **this item is NOT closed.** The drift count is 2, not the required 0 (excluding the one named legitimate fenced-example survivor), so Gate 1 fails on fresh evidence. This is reported rather than closed or excused. `BB-239`\'s writer path (cli-watch item creation, not `update_backlog.py --create`/`--status`) is outside this task\'s write-set to fix; filing a follow-up for the underlying writer gap is left to a future triage pass, since `update_backlog.py`\'s own status-update path already drops the body line entirely for items created through it (Sprint-01\'s chosen representation, option (b): frontmatter is now the single source and the template emits no body line at all), so the residual risk is confined to any item-creation path that still hand-writes a body `**Status:**` line outside that writer.\r\n'
    b'>\r\n'
    b"> **Closeout addendum (BIR-S04-01 Task 7 gate, 2026-09-23).** This item's measured gate covers `Archive/` only. The cutover gate also counted **136 active** item files still carrying a body `**Status:**` line that no script syncs. They are harmless while each one agrees with frontmatter, and they drift the moment a status changes through a frontmatter-only writer. Closing this item needs three things: the `Archive/BB-239` line removed; a decision on the 136 active body lines (strip them in one scripted pass, or declare the body line non-authoritative); and the cli-watch item-creation path writing no body `**Status:**` line.\r\n"
    b'\r\n'
    b'# BB-096-01-INFRA: Item Body `**Status:**` Line Is Never Synced\r\n'
    b'\r\n'
    b'**Priority:** Medium\r\n'
    b'**Domain:** INFRA\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Summary\r\n'
    b'\r\n'
    b"Every backlog item file carries its status **twice**: once in YAML frontmatter (`status:`) and once as a body display line (`**Status:**`). Only the *create* path writes the body line. `update_backlog.py`'s status-update path syncs frontmatter only \xe2\x80\x94 so the moment an item's status changes, the human-readable line a reader actually sees goes stale and never recovers.\r\n"
    b'\r\n'
    b'Measured on this repo at 2026-08-12 closeout of BB-039:\r\n'
    b'\r\n'
    b'```\r\n'
    b'archived items: 61 | with a body **Status:** line: 61 | body disagrees with frontmatter: 52\r\n'
    b'```\r\n'
    b'\r\n'
    b'**52 of 61 archived items** say `status: COMPLETE` in frontmatter and `**Status:** NOT_STARTED` (or `BLOCKED`) in the body. The 9 non-drifted ones are those whose body line happened to be hand-edited during execution.\r\n'
    b'\r\n'
    b'This is the **fourth instance** of the one-writer denormalized-status class already fixed three times \xe2\x80\x94 BB-046 (plans index), BB-048 (backlog index archival), BB-071 (lessons index next-ID) \xe2\x80\x94 but a new sub-shape: those were *cross-file* caches reconciled by a read-side pass, this is *within-file* dual representation.\r\n'
    b'\r\n'
    b'## Problem\r\n'
    b'\r\n'
    b'### The writer gap (verified in the shipped 1.0.4 script)\r\n'
    b'\r\n'
    b'`scripts/update_backlog.py` \xe2\x86\x92 `_render_bli_file()` emits the body line at creation:\r\n'
    b'\r\n'
    b'```python\r\n'
    b'def _render_bli_file(...):\r\n'
    b'    ...\r\n'
    b'    return (\r\n'
    b'        "---\\n"\r\n'
    b'        f"id: {item_id}\\n"\r\n'
    b'        f\'title: "{title}"\\n\'\r\n'
    b'        f"priority: {priority}\\n"\r\n'
    b'        f"status: {status}\\n"          # <-- frontmatter copy\r\n'
    b'        f"abbrev: {abbrev}\\n"\r\n'
    b'        f"created: {today}\\n"\r\n'
    b'        "blocks: []\\n"\r\n'
    b'        "---\\n"\r\n'
    b'        "\\n"\r\n'
    b'        f"# {stem}: {feature}\\n"\r\n'
    b'        "\\n"\r\n'
    b'        f"**Priority:** {priority}\\n"\r\n'
    b'        f"**Status:** {status}\\n"      # <-- body copy, written ONLY here\r\n'
    b'        f"**Domain:** {abbrev}\\n"\r\n'
    b'        ...\r\n'
    b'```\r\n'
    b'\r\n'
    b"`grep -n '\\*\\*Status' scripts/update_backlog.py` returns exactly **one** hit \xe2\x80\x94 line 316, inside `_render_bli_file()`. The status-update path has no corresponding write. Its own console output is honest about the scope: `YAML status synced: {file}`.\r\n"
    b'\r\n'
    b'The source is upstream of the script too: `templates/backlog-item.md:54` ships `**Status:** NOT_STARTED` as literal template text, so a hand-created item inherits the same dual representation.\r\n'
    b'\r\n'
    b'### Why it matters beyond cosmetics\r\n'
    b'\r\n'
    b'A reader opening an archived item sees `**Status:** NOT_STARTED` above a fully-satisfied acceptance list. That is the same failure mode as an unfilled Sprint Signoff: **a status artifact that reads as "not done" is indistinguishable from work that was not done**, to a human skimming and to any mechanical gate that greps the body.\r\n'
    b'\r\n'
    b'It has already produced one **recorded misdiagnosis**. The backlog index footer states of BB-047:\r\n'
    b'\r\n'
    b"> whose own status is self-contradictory: frontmatter/index/`Archive/` say COMPLETE but its body reads `NOT_STARTED` with all acceptance criteria unchecked and an open-decisions section \xe2\x80\x94 likely opened-then-mis-archived; reconcile BB-047's true state separately\r\n"
    b'\r\n'
    b'That diagnosis is **wrong**, and the note directing a reader to "reconcile BB-047\'s true state separately" sends them chasing a human error that never happened. BB-047 is not a mis-archive; it is 1 of 52 items hit by the writer gap. The single-instance reading was plausible precisely because nobody measured the population.\r\n'
    b'\r\n'
    b'## Files\r\n'
    b'\r\n'
    b'- `cloned-repos/planwise/plugins/planwise/scripts/update_backlog.py` \xe2\x80\x94 the status-update path; add the body-line sync beside the existing frontmatter sync\r\n'
    b'- `cloned-repos/planwise/plugins/planwise/templates/backlog-item.md` \xe2\x80\x94 line ~54 ships the duplicate `**Status:**` line\r\n'
    b'- `cloned-repos/planwise/plugins/planwise/scripts/reconcile_backlog.py` \xe2\x80\x94 natural home for the read-side detect pass (already owns backlog archival drift from BB-048)\r\n'
    b'- `cloned-repos/planwise/plugins/planwise/handlers/backlog.md` \xe2\x80\x94 Phase 1 detect banner + write-on-consent offer\r\n'
    b"- `cloned-repos/planwise/plugins/planwise/handlers/doctor.md` \xe2\x80\x94 reuse the detect pass as a doctor stage, matching how BB-048's pass is reused at Stage 12\r\n"
    b'- `cloned-repos/planwise/tests/` \xe2\x80\x94 fixture tests\r\n'
    b'- `planwise/Backlog/Archive/BB-*.md` (51 files) + `planwise/Backlog/00-Index-Backlog.md` footer \xe2\x80\x94 the project-side backfill and the BB-047 note correction\r\n'
    b'\r\n'
    b'## Tasks\r\n'
    b'\r\n'
    b"1. **Fix the writer.** In `update_backlog.py`'s status-update path, sync the body `**Status:**` line in the same write that syncs frontmatter. Anchor on `^\\*\\*Status:\\*\\*` (first occurrence, before the `---` that closes the header block) \xe2\x80\x94 do NOT blanket-replace, since `### Status Values` tables and prose mentioning statuses appear in item bodies. Update the console line to report both (`status synced: frontmatter + body`).\r\n"
    b'\r\n'
)

# F6 - planwise/Backlog/Archive/BB-047-01-INFRA-ReconcileMetaPlanResolverFallback.md,
# source lines 1-86, CRLF. Hazard: line 85 `**Status: COMPLETE / CLOSED.**`
# (colon inside the bold) under `## Closeout`. Pins the near-miss bold form.
F6_BB047 = (
    b'---\r\n'
    b'id: 047\r\n'
    b'title: "reconcile_plans.py resolves each index row\'s Master Plan only as {ABBR}-Master-Plan.md, so Discovery/Meta plans (which use {ABBR}-META-Master-Plan.md) are reported as standing \'Master Plan not found\' anomalies on every list/doctor run. Add a Meta-naming fallback."\r\n'
    b'priority: Low\r\n'
    b'status: COMPLETE\r\n'
    b'abbrev: INFRA\r\n'
    b'created: 2026-07-07\r\n'
    b'target_version: "1.0.4"\r\n'
    b'source: "Surfaced 2026-07-06 during LID-S01-01 live-smoke dogfooding of reconcile_plans.py: the PRV row (Path PluginReview/Meta-PRV/) reported \'Master Plan not found (expected: Plans/PluginReview/Meta-PRV/PRV-Master-Plan.md)\' because the real file is PRV-META-Master-Plan.md. Correct anomaly HANDLING (no crash, never written), but a false anomaly the resolver\'s single-naming assumption produces for every Discovery/Meta plan in the index. Captured as LL-047."\r\n'
    b'blocks: []\r\n'
    b'---\r\n'
    b'\r\n'
    b'# BB-047-INFRA: `reconcile_plans.py` \xe2\x80\x94 Meta/Discovery Master-Plan naming fallback in the drift resolver\r\n'
    b'\r\n'
    b'**Priority:** Low\r\n'
    b'**Domain:** INFRA\r\n'
    b'**Target Version:** 1.0.4\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Summary\r\n'
    b'\r\n'
    b"`reconcile_plans.py` (the plans-index drift reconciler shipped by BB-046 / the ListIndexDriftReconcile plan) resolves each index row's Master Plan with a single filename convention: `resolve_master_plan_path()` builds `{plans_dir}/{Path}{ABBR}-Master-Plan.md`. Discovery/Meta plans name their master plan `{ABBR}-META-Master-Plan.md` (and their Path column carries a `Meta-{ABBR}/` marker), so the resolver never finds them and reports every such row as a `Master Plan not found` **anomaly**.\r\n"
    b'\r\n'
    b'The anomaly path is otherwise correct \xe2\x80\x94 it does not crash and never writes the row \xe2\x80\x94 but it is a **false anomaly**: the plan is well-formed, the file exists, only the filename convention differs. Every Discovery/Meta-only plan sitting in the index (before it is scaffolded into an `Exec-{ABBR}/` plan) will surface as standing noise on every `/planwise list` and `/planwise doctor` run.\r\n'
    b'\r\n'
    b'## Empirical evidence (2026-07-06, live)\r\n'
    b'\r\n'
    b'Live smoke of `reconcile_plans.py --config planwise/config.yaml --json` against the real index:\r\n'
    b'\r\n'
    b'```\r\n'
    b'Anomalies (1):\r\n'
    b'  - PRV: Master Plan not found (expected: Plans/PluginReview/Meta-PRV/PRV-Master-Plan.md)\r\n'
    b'```\r\n'
    b'\r\n'
    b'The file actually exists at `Plans/PluginReview/Meta-PRV/PRV-**META**-Master-Plan.md`. The index row:\r\n'
    b'\r\n'
    b'| Abbrev | Name | Status | Path |\r\n'
    b'|--------|------|--------|------|\r\n'
    b'| PRV | PluginReview (Meta / Discovery) | READY_TO_EXECUTE | `PluginReview/Meta-PRV/` |\r\n'
    b'\r\n'
    b'The `Meta-` prefix in the Path column is the marker that this is a Discovery/Meta plan using the `-META-Master-Plan.md` filename.\r\n'
    b'\r\n'
    b'## Problem\r\n'
    b'\r\n'
    b'1. **Single-naming assumption.** `resolve_master_plan_path()` only ever tries `{ABBR}-Master-Plan.md`; it has no knowledge of the `{ABBR}-META-Master-Plan.md` convention Discovery/Meta plans use.\r\n'
    b'2. **Recurring false anomaly.** Every Discovery/Meta-only plan in the index reports as a standing "Master Plan not found" anomaly on every `list`/`doctor` run, degrading the signal-to-noise of the very audit BB-046 added. Today that is PRV; any future Discovery plan added before it is scaffolded will join it.\r\n'
    b"3. **The status of a Meta plan is currently unreconcilable.** Because the file is never resolved, a Meta plan's index Status can never be drift-checked or healed by the tool.\r\n"
    b'\r\n'
    b'## Proposed Solution\r\n'
    b'\r\n'
    b'Teach `resolve_master_plan_path()` (and its display-path sibling `_relative_master_plan_path()`) a **Meta-naming fallback** in `cloned-repos/planwise/plugins/planwise/scripts/reconcile_plans.py`:\r\n'
    b'\r\n'
    b'1. Try the primary `{ABBR}-Master-Plan.md` first (unchanged, fast path).\r\n'
    b"2. If that file does not exist, try `{ABBR}-META-Master-Plan.md` in the same directory before declaring an anomaly. Prefer gating the fallback on the `Meta-` marker in the row's Path (e.g. Path segment starts with `Meta-`) so a genuinely-missing regular Master Plan still reports as an anomaly rather than silently probing a second name.\r\n"
    b'3. Only when neither resolves \xe2\x86\x92 report the anomaly (with an `expected_path` that names both tried conventions, or the Meta one when the Path marks it Meta, so the message is actionable).\r\n'
    b'\r\n'
    b'Keep the rest of the contract identical: detection, base-token normalization, race-safe write, and anomaly-never-written all unchanged.\r\n'
    b'\r\n'
    b'### Decisions (resolved at triage \xe2\x80\x94 RESOLVED)\r\n'
    b'\r\n'
    b"- **Fallback trigger \xe2\x80\x94 RESOLVED: Path-marker gate.** The fallback fires only when the primary `{ABBR}-Master-Plan.md` is absent **and** the row's Path is Meta-marked (final non-empty segment starts with `Meta-`), so a genuinely-missing regular Master Plan still reports as an anomaly instead of silently probing a second name. Implemented as `_is_meta_row()` gating the `-META-` probe in `resolve_master_plan_path()`.\r\n"
    b'- **Should Meta/Discovery plans be drift-checked at all? \xe2\x80\x94 RESOLVED: yes, checked (not excluded).** The fallback resolves the file; it does not exclude Meta rows from the drift check. Base-token normalization behaves correctly for Meta statuses (regression `test_meta_plan_status_drift_detected_after_resolve` confirms a resolved Meta plan is still drift-checked and heals).\r\n'
    b'\r\n'
    b'## Acceptance Criteria\r\n'
    b'\r\n'
    b"- [x] `resolve_master_plan_path()` resolves a Discovery/Meta plan's Master Plan via the `{ABBR}-META-Master-Plan.md` fallback (gated on the `Meta-` Path marker per the chosen decision), so a well-formed Meta plan no longer reports as a `Master Plan not found` anomaly.\r\n"
    b'- [x] A genuinely-missing regular Master Plan (no file under either convention) still reports as an anomaly (no silent pass).\r\n'
    b'- [x] Live `reconcile_plans.py --json` against the real index reports **0 anomalies** for PRV (the Meta plan resolves), with no new false drift.\r\n'
    b'- [x] A regression test reproduces the Meta-plan case: an index row whose Path is `Foo/Meta-BAR/` and whose Master Plan is `BAR-META-Master-Plan.md` resolves (no anomaly); a row whose Master Plan is absent under both conventions still anomalies.\r\n'
    b'- [x] Self-containment grep clean on the plugin edit \xe2\x80\x94 no `LL-`/`BB-`/`BLI-[0-9]`/`PLG-`/`D-[0-9]`/`Sprint-[0-9]`/`URC-` strings introduced into `cloned-repos/planwise/plugins/planwise/**` (both CLAUDE.md verification commands empty).\r\n'
    b'- [x] Full `scripts/` suite green (no regressions).\r\n'
    b'\r\n'
    b'## Related\r\n'
    b'\r\n'
    b'- **BB-046** \xe2\x80\x94 the parent item; added the `reconcile_plans.py` detect + reconcile feature this fallback extends.\r\n'
    b'- **LL-047** (`LessonsLearned/LL-047-LID-MetaPlanResolverAnomaly.md`) \xe2\x80\x94 the lesson this BB operationalizes: a plans-index resolver keyed on one Master-Plan filename convention flags every Discovery/Meta plan as a false anomaly.\r\n'
    b'- **`handlers/list.md` / `handlers/doctor.md`** \xe2\x80\x94 both call the resolver via `reconcile_plans.py`, so both surface the false anomaly today and both benefit from the fix (no handler change needed \xe2\x80\x94 the fix is in the shared script).\r\n'
    b'- **Meta-plan naming convention** \xe2\x80\x94 Discovery/Meta plans live under `Meta-{ABBR}/` and use `{ABBR}-META-Master-Plan.md`; regular execution plans live under `Exec-{ABBR}/` (or the plan root) and use `{ABBR}-Master-Plan.md`.\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Closeout (2026-07-07)\r\n'
    b'\r\n'
    b'**Status: COMPLETE / CLOSED.** All acceptance criteria met and verified. This BB was opened-then-mis-archived: its frontmatter, index row, and `Archive/` location were already COMPLETE, but the body had never been advanced from its draft state (Status line read `NOT_STARTED`, criteria unchecked, open-decisions section unresolved). This closeout reconciles the body to its true, verified state \xe2\x80\x94 the reconciliation-drift class BB-048 addresses.\r\n'
    b'\r\n'
)

# F7 - planwise/Backlog/Archive/BB-032-01-DOC-PromoteProcessTail.md, source lines
# 1-19, 27-29, 37-39 and 73-88, CRLF (dropped: paragraphs only; every `## `
# heading and the fence 73-84 are kept). Hazard: source line 86 (fixture
# line 39) `**Status flip:** ...` at column 0. Pins the near-miss label form.
F7_BB032 = (
    b'---\r\n'
    b'id: 032\r\n'
    b'title: "Promote three independent process-tail lessons: LL-017 (deferred-finding ownership), LL-023 (verify-under-older-plugin discipline), LL-027 (ratio-band assertion gap)"\r\n'
    b'priority: Medium\r\n'
    b'status: COMPLETE\r\n'
    b'abbrev: DOC\r\n'
    b'created: 2026-06-24\r\n'
    b'blocks: []\r\n'
    b'---\r\n'
    b'\r\n'
    b'# BB-032-DOC: Promote Three Independent Process-Tail Lessons\r\n'
    b'\r\n'
    b'**Priority:** Medium\r\n'
    b'**Domain:** PROC / RSO\r\n'
    b'**Source:** LL-017 (PRF-S04-01), LL-023 (RSO-S02-01), LL-027 (RSO-S04-01)\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Problem\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Evidence\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Proposal\r\n'
    b'```\r\n'
    b'### Check 0XX \xe2\x80\x94 Deferred Finding Owner Is a CLOSED Task\r\n'
    b'\r\n'
    b'- **Severity / Role / Source / Type:** BLOCKER | Dependency Reviewer | references/session-plan-requirements.md \xc2\xa79 Cross-Sprint Deferred-Finding Ownership | NEW\r\n'
    b'- **What:** A dependency or sequencing row that names a COMPLETE/CLOSED task as the owner of still-pending deferred work is stale and MUST be flagged.\r\n'
    b'- **Detection:** In the Master Plan and Sprint Plans, find rows whose status is \xe2\x8f\xb3 Pending and whose owner task is marked COMPLETE/CLOSED. Any such row \xe2\x86\x92 BLOCKER.\r\n'
    b'- **Finding template:**\r\n'
    b'[BLOCKER] Deferred-finding owner is CLOSED\r\n'
    b'File: {plan file path} | Location: {dependency/sequencing row}\r\n'
    b'Issue: Dependency row names {closed_task_id} (CLOSED) as owner of still-pending work\r\n'
    b'Fix: Reassign ownership to a live not-yet-run sprint/session per references/session-plan-requirements.md \xc2\xa79 | Confidence: HIGH\r\n'
    b'```\r\n'
    b'\r\n'
    b'**Status flip:** LL-017 \xe2\x86\x92 `rule`; `applied-as: plugins/planwise/references/session-plan-requirements.md \xc2\xa79 + agents/plan-reviewer.md Check 0XX`\r\n'
    b'\r\n'
    b'---\r\n'
)

# F8 - cloned-repos/planwise/plugins/planwise/templates/backlog-item.md, source
# lines 56-63 (the Body Structure skeleton inside the template's ```markdown
# fence), CRLF. No hazard line: the skeleton carries `**Priority:**` and
# `**Domain:**` only. Pins the goal state: absence reports nothing. Used as an
# item behind F8_SYNTHETIC_FRONTMATTER below.
F8_TEMPLATE_SKELETON = (
    b'# BB-{ID}-{Domain}: {Title}\r\n'
    b'\r\n'
    b'**Priority:** {High|Medium|Low}\r\n'
    b'**Domain:** {ABBREV}\r\n'
    b'\r\n'
    b'---\r\n'
    b'\r\n'
    b'## Summary\r\n'
)


# The template carries no item frontmatter of its own, so F8 gets a synthetic
# CRLF frontmatter block (matching the template's own CRLF endings). Every
# byte after it is the real template skeleton.
F8_SYNTHETIC_FRONTMATTER = (
    b"---\r\n"
    b"id: 900\r\n"
    b'title: "Template skeleton as an item"\r\n'
    b"priority: Medium\r\n"
    b"status: NOT_STARTED\r\n"
    b"abbrev: DOC\r\n"
    b"created: 2026-09-23\r\n"
    b"blocks: []\r\n"
    b"---\r\n"
    b"\r\n"
)
F8_ITEM = F8_SYNTHETIC_FRONTMATTER + F8_TEMPLATE_SKELETON

# name -> (bytes, real filename, lives in Archive/)
FIXTURES = {
    "F1": (F1_BB239, "BB-239-01-DOC-HookDenyContractMdPin.md", True),
    "F2": (F2_BB240, "BB-240-01-INFRA-VERSIONJsonPin.md", False),
    "F3": (F3_BB375, "BB-375-01-DOC-HookDenyContractDeferValueGap.md", False),
    "F4": (F4_BB005, "BB-005-01-PROC-ScaffoldSprintStatus.md", True),
    "F5": (F5_BB096, "BB-096-01-INFRA-ItemBodyStatusLineNeverSynced.md", False),
    "F6": (F6_BB047, "BB-047-01-INFRA-ReconcileMetaPlanResolverFallback.md", True),
    "F7": (F7_BB032, "BB-032-01-DOC-PromoteProcessTail.md", True),
    "F8": (F8_ITEM, "backlog-item.md", False),
}

F1_LINE = b"**Status:** NOT_STARTED\r\n"
F2_LINE = b"**Status:** NOT_STARTED\n"
F3_LINE = b"**Status:** NOT_STARTED\r\n"


def _lines_keepends(data: bytes) -> list:
    """Split on `\\n` only, each element keeping its own terminator."""
    parts = data.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _bare_lf_count(data: bytes) -> int:
    return data.count(b"\n") - data.count(b"\r\n")


def _frontmatter_bytes(data: bytes) -> bytes:
    """The frontmatter block, both delimiters included, as raw bytes."""
    terminator = b"\r\n" if data.startswith(b"---\r\n") else b"\n"
    closing = terminator + b"---" + terminator
    return data[: data.index(closing, 3) + len(closing)]


_REAL_OPEN = open


class _FailingWriter:
    """Wraps a real write handle; fails inside `write()` for selected content.

    With `partial=True` it first writes half the content through the real
    handle, so a non-atomic writer leaves a truncated target behind.
    """

    def __init__(self, handle, select, partial):
        self._handle = handle
        self._select = select
        self._partial = partial

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._handle.close()
        return False

    def write(self, text):
        if self._select(text):
            if self._partial:
                self._handle.write(text[: len(text) // 2])
                self._handle.flush()
            raise OSError("simulated failure mid-write")
        return self._handle.write(text)


@contextlib.contextmanager
def _inject_write_failure(select, partial):
    """Fail at the real open/write step inside `reconcile_common`.

    Patches the `open` name `reconcile_common` resolves, so every write-mode
    open still opens the real file (a truncating open really truncates) and
    the failure fires inside the write itself. Read-mode opens pass through.
    """

    def fake_open(file, mode="r", *args, **kwargs):
        handle = _REAL_OPEN(file, mode, *args, **kwargs)
        if "w" not in mode:
            return handle
        return _FailingWriter(handle, select, partial)

    with patch("reconcile_common.open", new=fake_open, create=True):
        yield


def _temp_leftovers(directory: Path) -> list:
    """Names of leftover atomic-write temp files (`.{name}.tmp-*`)."""
    return sorted(p.name for p in directory.iterdir() if p.name.startswith(".") and ".tmp-" in p.name)


class _BodyStatusFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree, as in test_reconcile_backlog.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_body_status_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.backlog_dir / "00-Index-Backlog.md"
        self.index_path.write_bytes(INDEX_BYTES)

        (self.planwise_dir / "config.yaml").write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_reconcile_backlog_body_status",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()

    def put(self, name: str, data: bytes | None = None, filename: str | None = None) -> Path:
        """Write fixture `name` (or a derived variant) with its real bytes."""
        source, real_name, archived = FIXTURES[name]
        target = (self.archive_dir if archived else self.backlog_dir) / (filename or real_name)
        target.write_bytes(source if data is None else data)
        return target

    def detect(self) -> dict:
        return detect_body_status(self.config)

    def reconcile_quietly(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            stripped = reconcile_body_status(self.config)
        return stripped, out.getvalue()

    def run_main(self, *extra: str) -> str:
        sys.argv = [
            "reconcile_backlog.py",
            "--config",
            str(self.planwise_dir / "config.yaml"),
            *extra,
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reconcile_backlog.main()  # returning normally is exit 0
        return out.getvalue()


class TestDetectOnRealItems(_BodyStatusFixtureBase):
    """Tests 1-8: where the pass matches, and where it refuses to."""

    def test_01_f1_archived_crlf_line_disagrees(self):
        self.put("F1")

        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(
            result["drifts"],
            [
                {
                    "id": "239",
                    "status": "COMPLETE",
                    "body_status": "NOT_STARTED",
                    "kind": "disagrees",
                    "file": "BB-239-01-DOC-HookDenyContractMdPin.md",
                    "in_archive": True,
                    "line": 16,
                    "reason": "body status line disagrees with frontmatter",
                    "needs_strip": True,
                }
            ],
        )

    def test_02_f2_active_lf_line_is_redundant(self):
        self.put("F2")

        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(len(result["drifts"]), 1)
        drift = result["drifts"][0]
        self.assertEqual(drift["kind"], "redundant")
        self.assertEqual(
            drift["reason"], "redundant body status line — frontmatter is the only status field"
        )
        self.assertEqual((drift["line"], drift["in_archive"]), (16, False))

    def test_03_f3_old_template_shape_is_redundant(self):
        self.put("F3")

        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(
            [(d["kind"], d["line"], d["body_status"]) for d in result["drifts"]],
            [("redundant", 14, "NOT_STARTED")],
        )

    def test_04_f4_fenced_example_after_heading_is_not_drift(self):
        self.put("F4")

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_05_f5_callout_fences_and_inline_code_are_not_drift(self):
        self.put("F5")

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_06_f6_f7_near_miss_bold_forms_are_not_drift(self):
        self.put("F6")
        self.put("F7")

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_07_f8_template_skeleton_reports_nothing(self):
        # Absence of a body status line is the goal state, not an anomaly.
        self.put("F8")

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_08_discrimination_pair(self):
        for name in ("F4", "F5", "F6", "F7", "F8"):
            self.put(name)
        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

        self.put("F1")
        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(
            [d["file"] for d in result["drifts"]], ["BB-239-01-DOC-HookDenyContractMdPin.md"]
        )


class TestAnomalies(_BodyStatusFixtureBase):
    """Tests 9-11: each anomaly is reported, never drift."""

    def test_09_unreadable_frontmatter_status_is_anomaly(self):
        self.assertEqual(F2_BB240.count(b"status: NOT_STARTED\n"), 1)
        self.put("F2", F2_BB240.replace(b"status: NOT_STARTED\n", b"", 1))

        result = self.detect()

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        anomaly = result["anomalies"][0]
        self.assertEqual((anomaly["status"], anomaly["line"]), ("?", 15))
        self.assertIn("cannot be read", anomaly["reason"])

    def test_10_two_header_block_status_lines_is_anomaly(self):
        self.assertEqual(F3_BB375.count(F3_LINE), 1)
        self.put("F3", F3_BB375.replace(F3_LINE, F3_LINE + F3_LINE, 1))

        result = self.detect()

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertIn("2 header-block status lines (lines 14, 15)", result["anomalies"][0]["reason"])

    def test_11_no_h1_with_a_status_line_is_anomaly(self):
        lines = _lines_keepends(F2_BB240)
        h1_lines = [line for line in lines if line.startswith(b"# ")]
        self.assertEqual(len(h1_lines), 1)
        self.put("F2", b"".join(line for line in lines if not line.startswith(b"# ")))

        result = self.detect()

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["line"], 15)
        self.assertIn("no H1 title", result["anomalies"][0]["reason"])


class TestWrite(_BodyStatusFixtureBase):
    """Tests 12-17: --write removes exactly one line and nothing else."""

    def test_12_write_crlf_removes_exactly_the_line(self):
        path = self.put("F1")
        self.assertEqual(F1_BB239.count(F1_LINE), 1)
        self.assertEqual(_bare_lf_count(F1_BB239), 0)

        stripped, out = self.reconcile_quietly()

        after = path.read_bytes()
        self.assertEqual(stripped, 1)
        self.assertEqual(after, F1_BB239.replace(F1_LINE, b"", 1))
        self.assertEqual(len(F1_BB239) - len(after), len(F1_LINE))
        self.assertEqual(_bare_lf_count(after), 0)
        self.assertEqual(_frontmatter_bytes(after), _frontmatter_bytes(F1_BB239))
        self.assertIn("  + BB-239-01-DOC-HookDenyContractMdPin.md: stripped line 16", out)

    def test_13_write_lf_removes_exactly_the_line(self):
        path = self.put("F2")
        self.assertEqual(F2_BB240.count(F2_LINE), 1)
        self.assertEqual(F2_BB240.count(b"\r\n"), 0)

        stripped, _ = self.reconcile_quietly()

        after = path.read_bytes()
        self.assertEqual(stripped, 1)
        self.assertEqual(after, F2_BB240.replace(F2_LINE, b"", 1))
        self.assertEqual(after.count(b"\r"), 0)
        self.assertEqual(_frontmatter_bytes(after), _frontmatter_bytes(F2_BB240))

    def test_14_write_leaves_anomalies_clean_files_and_index_identical(self):
        self.put("F1")
        for name in ("F4", "F5", "F6", "F7", "F8"):
            self.put(name)
        self.put(
            "F2",
            F2_BB240.replace(b"status: NOT_STARTED\n", b"", 1),
            filename="BB-240-01-INFRA-VERSIONJsonPin-NoStatusKey.md",
        )
        self.put(
            "F3",
            F3_BB375.replace(F3_LINE, F3_LINE + F3_LINE, 1),
            filename="BB-375-01-DOC-HookDenyContractDeferValueGap-TwoLines.md",
        )
        self.put(
            "F2",
            b"".join(line for line in _lines_keepends(F2_BB240) if not line.startswith(b"# ")),
            filename="BB-240-01-INFRA-VERSIONJsonPin-NoH1.md",
        )
        drift_path = self.archive_dir / "BB-239-01-DOC-HookDenyContractMdPin.md"
        before = {
            path: path.read_bytes()
            for path in sorted(self.backlog_dir.rglob("*.md"))
            if path != drift_path
        }
        self.assertEqual(len(self.detect()["anomalies"]), 3)

        stripped, _ = self.reconcile_quietly()

        self.assertEqual(stripped, 1)
        self.assertIn(self.index_path, before)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data, path.name)
        self.assertEqual(self.index_path.read_bytes(), INDEX_BYTES)

    def test_15_race_safety_skips_a_line_already_gone(self):
        f1_path = self.put("F1")
        f2_path = self.put("F2")
        self.assertEqual(len(self.detect()["drifts"]), 2)

        # A concurrent writer strips F2's line between detect and reconcile.
        out_of_band = F2_BB240.replace(F2_LINE, b"", 1)
        f2_path.write_bytes(out_of_band)

        written = []
        real_write = reconcile_common.write_text_preserving_newlines

        def spy(path, content):
            written.append(Path(path).name)
            real_write(path, content)

        with patch("reconcile_common.write_text_preserving_newlines", side_effect=spy):
            stripped, out = self.reconcile_quietly()

        self.assertEqual(stripped, 1)
        self.assertEqual(written, [f1_path.name])
        self.assertEqual(f2_path.read_bytes(), out_of_band)
        self.assertNotIn(f2_path.name, out)

    def test_16_idempotence(self):
        for name in ("F1", "F2", "F3"):
            self.put(name)

        first, _ = self.reconcile_quietly()
        self.assertEqual(first, 3)
        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

        second, out = self.reconcile_quietly()
        self.assertEqual((second, out), (0, ""))

    def test_17_failed_write_exits_nonzero_and_names_the_file(self):
        # The failure fires at the real open/write step (not above it), so
        # "the file is unchanged" is a property of the writer, not of a mock
        # that skipped the write entirely.
        f1_path = self.put("F1")
        f2_path = self.put("F2")

        err = io.StringIO()
        with _inject_write_failure(select=lambda text: "id: 239" in text, partial=False):
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                self.run_main("--body-status", "--write")

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(f1_path.name, err.getvalue())
        self.assertIn("simulated failure mid-write", err.getvalue())
        self.assertEqual(f1_path.read_bytes(), F1_BB239)
        self.assertEqual(f2_path.read_bytes(), F2_BB240.replace(F2_LINE, b"", 1))


class TestCli(_BodyStatusFixtureBase):
    """Test 18: the flag selects the mode; without it, today's output."""

    def test_18_json_output_and_mode_separation(self):
        self.put("F1")
        self.put("F2")

        out = self.run_main("--body-status", "--json")

        self.assertIn(
            "Body status drift detected (2 header-block status line(s) to strip):", out
        )
        json_lines = [line for line in out.splitlines() if line.startswith("JSON: ")]
        self.assertEqual(len(json_lines), 1)
        json_path = Path(json_lines[0][len("JSON: "):])
        self.addCleanup(shutil.rmtree, json_path.parent, ignore_errors=True)
        self.assertTrue(json_path.parent.name.startswith("reconcile-backlog-body-status-"))
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"drifts", "anomalies"})
        self.assertEqual(len(payload["drifts"]), 2)

        default_out = self.run_main()

        self.assertEqual(
            default_out,
            "No archival drift detected. Every closed backlog item file is in Archive/.\n",
        )


class TestFenceInsideHeaderBlock(_BodyStatusFixtureBase):
    """Test 19: fence tracking is load-bearing inside the header block.

    In F4 and F5 the header block closes (`---`) before any fence opens, so
    they pass with fence tracking disabled. This variant moves F4's own
    fenced example (source lines 42-45, the four real lines unchanged) into
    its header block, directly after the `**Priority:**` line, so only
    fence tracking keeps its `**Status:** PLANNED` line from matching.
    """

    def test_19_fenced_status_line_inside_header_block_is_not_drift(self):
        lines = _lines_keepends(F4_BB005)
        fence = lines[41:45]
        self.assertEqual(fence[0], b"```markdown\r\n")
        self.assertEqual(fence[1], b"**Status:** PLANNED\r\n")
        self.assertEqual(fence[3], b"```\r\n")
        self.assertEqual(lines[12], b"**Priority:** Medium\r\n")
        variant = b"".join(lines[:13] + fence + lines[13:])
        self.put("F4", variant)

        self.assertEqual(_scan_body_status(variant.decode("utf-8"))["header_hits"], [])
        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})


class TestHeaderBlockClose(_BodyStatusFixtureBase):
    """Test 20: the header-block close is load-bearing on its own.

    No real item carries an unfenced column-0 status line after its header
    block, so nothing above isolates the `---` / `## ` close. This variant
    drops only F4's fence delimiters (source lines 42 and 45), leaving its
    `**Status:** PLANNED` line unfenced at column 0 after the `---` that
    closes the header block at line 16.
    """

    def test_20_unfenced_status_line_after_header_block_is_not_drift(self):
        lines = _lines_keepends(F4_BB005)
        self.assertEqual(lines[15], b"---\r\n")
        self.assertEqual(lines[41], b"```markdown\r\n")
        self.assertEqual(lines[42], b"**Status:** PLANNED\r\n")
        self.assertEqual(lines[44], b"```\r\n")
        variant = b"".join(lines[:41] + lines[42:44] + lines[45:])
        self.put("F4", variant)

        self.assertEqual(_scan_body_status(variant.decode("utf-8"))["header_hits"], [])
        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})


# --- Review remediation: tests 21-37 ---


def _f2_around_status(before: bytes, after: bytes = b"") -> bytes:
    """F2 with `before` and `after` placed around its one header status line."""
    assert F2_BB240.count(F2_LINE) == 1
    return F2_BB240.replace(F2_LINE, before + F2_LINE + after, 1)


class TestAtomicWrite(_BodyStatusFixtureBase):
    """Test 21: a write that fails partway leaves the original bytes."""

    def test_21_partial_write_failure_leaves_original_and_no_temp_file(self):
        f1_path = self.put("F1")

        err = io.StringIO()
        with _inject_write_failure(select=lambda text: "id: 239" in text, partial=True):
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                self.run_main("--body-status", "--write")

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(f1_path.name, err.getvalue())
        self.assertEqual(f1_path.read_bytes(), F1_BB239)
        self.assertEqual(_temp_leftovers(self.archive_dir), [])
        self.assertEqual(_temp_leftovers(self.backlog_dir), [])


class TestCommonMarkFences(_BodyStatusFixtureBase):
    """Tests 22-27: fences follow the CommonMark opener/closer rules."""

    def test_22_tilde_fence_hides_a_status_line(self):
        variant = _f2_around_status(b"~~~\n", b"~~~\n")
        path = self.put("F2", variant)

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})
        stripped, _ = self.reconcile_quietly()
        self.assertEqual((stripped, path.read_bytes()), (0, variant))

    def test_23_four_backtick_fence_is_not_closed_by_a_shorter_run(self):
        # A: a ```python line inside the fence opens nothing new.
        self.put("F2", _f2_around_status(b"````\n```python\n", b"```\n````\n"))
        # B: a bare ``` run shorter than the opener does not close it, so the
        # status line after it is still fenced.
        self.put(
            "F2",
            _f2_around_status(b"````\n```\n", b"````\n"),
            filename="BB-240-01-INFRA-VERSIONJsonPin-ShortRun.md",
        )

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_24_inline_code_at_line_start_is_not_a_fence(self):
        self.put("F2", _f2_around_status(b"```inline``` code at line start\n"))

        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual([d["line"] for d in result["drifts"]], [17])

    def test_25_four_space_indented_backticks_are_not_a_fence(self):
        self.put("F2", _f2_around_status(b"    ```\n"))

        result = self.detect()

        self.assertEqual(result["anomalies"], [])
        self.assertEqual([d["line"] for d in result["drifts"]], [17])

    def test_26_a_closer_carries_no_info_string(self):
        self.put("F2", _f2_around_status(b"```\n```python\n", b"```\n"))

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_27_unterminated_fence_runs_to_end_of_file(self):
        self.put("F2", _f2_around_status(b"~~~~\n"))

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})


class TestBareCarriageReturn(_BodyStatusFixtureBase):
    """Test 28: a lone `\\r` inside a status line is an anomaly, never written."""

    def test_28_status_line_with_a_bare_cr_is_an_anomaly(self):
        variant = F2_BB240.replace(F2_LINE, b"**Status:** OPEN\rKeep this text\n", 1)
        path = self.put("F2", variant)

        result = self.detect()

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["line"], 16)
        self.assertIn("carriage return", result["anomalies"][0]["reason"])
        stripped, _ = self.reconcile_quietly()
        self.assertEqual((stripped, path.read_bytes()), (0, variant))


class TestBodyStartIndex(unittest.TestCase):
    """Test 29: `_body_start_index` returns the first line after the closing `---`."""

    def test_29_body_start_index_is_the_line_after_the_closing_delimiter(self):
        for text in ("---\nid: 1\n---\n\n# T\n", "---\r\nid: 1\r\n---\r\n\r\n# T\r\n"):
            index = _body_start_index(text)
            lines = text.split("\n")
            self.assertEqual(index, 3)
            self.assertEqual(lines[index - 1].rstrip("\r"), "---")
        self.assertEqual(_body_start_index("# T\n**Status:** X\n"), 0)
        f2_lines = F2_BB240.decode("utf-8").split("\n")
        self.assertEqual(f2_lines[_body_start_index(F2_BB240.decode("utf-8")) - 1], "---")
        self.assertEqual(_body_start_index(F2_BB240.decode("utf-8")), 12)


class TestBomWithoutFrontmatter(_BodyStatusFixtureBase):
    """Test 30: a leading BOM never hides the H1."""

    def test_30_bom_and_no_frontmatter_is_the_unreadable_status_anomaly(self):
        variant = b"\xef\xbb\xbf" + b"".join(_lines_keepends(F2_BB240)[13:])
        self.assertTrue(variant[3:].startswith(b"# BB-240"))
        path = self.put("F2", variant)

        result = self.detect()

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertIn("cannot be read", result["anomalies"][0]["reason"])
        stripped, _ = self.reconcile_quietly()
        self.assertEqual((stripped, path.read_bytes()), (0, variant))


class TestMalformedModeFlag(_BodyStatusFixtureBase):
    """Test 31: a malformed flag passes through, exactly as before the mode existed."""

    def test_31_body_status_with_a_value_falls_through_to_the_default_mode(self):
        self.put("F1")
        self.put("F2")

        out = self.run_main("--body-status=1")  # must not exit 2

        self.assertEqual(
            out, "No archival drift detected. Every closed backlog item file is in Archive/.\n"
        )


class TestEachCloseRuleAlone(_BodyStatusFixtureBase):
    """Tests 32-33: each header-block close rule is load-bearing by itself."""

    def test_32_dash_close_alone_excludes_a_later_status_line(self):
        lines = _lines_keepends(F3_BB375)
        self.assertEqual((lines[13], lines[16], lines[18]), (F3_LINE, b"---\r\n", b"## Summary\r\n"))
        # Drop the header status line and the only `## ` line; put the status
        # line after the `---` close instead.
        variant = b"".join(lines[:13] + lines[14:18] + [F3_LINE])
        self.assertFalse(any(line.startswith(b"## ") for line in _lines_keepends(variant)))
        self.put("F3", variant)

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})

    def test_33_heading_close_alone_excludes_a_later_status_line(self):
        lines = _lines_keepends(F4_BB005)
        # Lines 1 and 9 delimit the frontmatter; line 16 is the body's only `---`.
        self.assertEqual(lines[9:].count(b"---\r\n"), 1)
        self.assertEqual((lines[15], lines[41], lines[44]), (b"---\r\n", b"```markdown\r\n", b"```\r\n"))
        # Drop the only `---` line and the fence delimiters around line 43.
        variant = b"".join(
            line for index, line in enumerate(lines) if index not in (15, 41, 44)
        )
        self.put("F4", variant)

        self.assertEqual(self.detect(), {"drifts": [], "anomalies": []})


class TestLineIndexing(_BodyStatusFixtureBase):
    """Tests 34-36: the scan index and the write agree on which line is removed."""

    def test_34_form_feed_line_does_not_shift_the_removed_line(self):
        variant = F2_BB240.replace(F2_LINE, b"\x0c\n" + F2_LINE, 1)
        path = self.put("F2", variant)

        self.assertEqual([d["line"] for d in self.detect()["drifts"]], [17])
        stripped, _ = self.reconcile_quietly()
        self.assertEqual(stripped, 1)
        self.assertEqual(path.read_bytes(), variant.replace(F2_LINE, b"", 1))
        self.assertIn(b"\x0c\n", path.read_bytes())

    def _assert_last_line_strip(self, name, source, terminator):
        variant = b"".join(_lines_keepends(source)[:16])
        self.assertTrue(variant.endswith(b"**Status:** NOT_STARTED" + terminator))
        variant = variant[: -len(terminator)]
        path = self.put(name, variant)

        self.assertEqual([d["line"] for d in self.detect()["drifts"]], [16])
        stripped, _ = self.reconcile_quietly()
        after = path.read_bytes()
        self.assertEqual(stripped, 1)
        self.assertEqual(after, variant[: -len(b"**Status:** NOT_STARTED")])
        self.assertTrue(after.endswith(terminator + terminator))
        return after

    def test_35_last_line_without_terminator_lf(self):
        self._assert_last_line_strip("F2", F2_BB240, b"\n")

    def test_36_last_line_without_terminator_crlf(self):
        after = self._assert_last_line_strip("F1", F1_BB239, b"\r\n")
        self.assertEqual(_bare_lf_count(after), 0)


class TestStaleFailureState(_BodyStatusFixtureBase):
    """Test 37: a failed --write never leaks into a later run in one process."""

    def test_37_failed_write_then_clean_runs_exit_zero(self):
        f1_path = self.put("F1")
        with _inject_write_failure(select=lambda text: "id: 239" in text, partial=False):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_main("--body-status", "--write")

        detect_out = self.run_main("--body-status")  # must not raise
        write_out = self.run_main("--body-status", "--write")  # must not raise

        self.assertIn("Body status drift detected (1 ", detect_out)
        self.assertIn("Stripped 1 body status line(s).", write_out)
        self.assertEqual(f1_path.read_bytes(), F1_BB239.replace(F1_LINE, b"", 1))


if __name__ == "__main__":
    unittest.main()
