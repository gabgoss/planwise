"""Ratchet on the folded always-load floor for the plan, run and backlog flows.

Derives the structural floor from the plugin tree with
`context_calibration.derive_structural_floor` and asserts each flow's token
figure stays at or below its pin. A split handler's Parts are folded into the
parent key, so the figure counts every Part (load per mode is not verified).

Run with:  python -m pytest tests/test_context_floor.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from context_calibration import derive_structural_floor

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# The pins are ceilings. Sprint-01 re-pins after its last floor-changing edit in
# each session: RFH-S01-03-06 (after the `consult-when:` lines and the `SKILL.md`
# change) and RFH-S01-04-03 (after the Page-Cap Procedure text). Later sprints
# re-pin in their own write-sets (EI 39.1 rule 3). Do not loosen the comparison
# to absorb those edits: a tolerance would defeat the ratchet.
# The pins are ceilings measured on CRLF checkout bytes (`_file_extent` counts
# checkout bytes under core.autocrlf=true), so an LF checkout passes with slack
# and cannot false-fail.
PLAN_FLOOR_PIN = 48774  # dev tree 1bc4e0a+wt, 2026-11-09, folded: +365 for the three-step workflow opt-in in plan-Part-2 Steps 4-7 (preflight, launch, wait), measured 48774 with derive_structural_floor; previously 48409 at dev tree 2511e87, 2026-11-09, folded: +1353 never re-pinned by the commits that added it (98bf2cb build_plan tool branch +354, 3aaf770 plan-bodies opt-in step +999), measured per commit on git archive exports whose 12df6d2 reading reproduced the old pins exactly; previously 47056 at dev tree ba39d07+wt, 2026-11-07, folded: +36 for the doctor --verbose help line in SKILL.md (measured 47056); previously 47020 at dev tree ba39d07+wt, 2026-11-07, folded: +311 for the estimate-reconcile paragraph in plan-Part-3 Step 9b, the only dirty file of the four the plan floor folds; previously 46709 at dev tree 7c2ff62+wt, 2026-11-07, folded (re-pinned to the live floor from 103640, which had left 56,931 tokens of slack and defeated the ratchet; measured with derive_structural_floor on the same tree that measured run 67968 and backlog 40779 at their pins); dev tree 4f84134+wt (plan.md router + 2 parts, Steps 4-8c render path, router reading order), 2026-10-22, folded; checkout bytes (CRLF under core.autocrlf), lower on an LF checkout
RUN_FLOOR_PIN = 68084  # dev tree 2511e87, 2026-11-09, folded: +80 never re-pinned by ba39d07 (the flag_subject_diff.py checklist line in run.md), measured per commit as for the plan pin; previously 68004 at dev tree ba39d07+wt, 2026-11-07, folded (the doctor --verbose help line in SKILL.md raised it by 36; the live floor measured 68084, because the flag_subject_diff.py checklist line ba39d07 added to run.md raised it by 80 with no re-pin, and that commit's own session owns that re-pin); previously 67968 at dev tree 8d08363+wt, 2026-11-06, folded (the SKILL.md Plan card rule re-pinned the floor from 67867 to 67968, raising it by 101; the --answer briefing change in SKILL.md and handlers/backlog-Part-3-Answers.md re-pinned the floor from 67845 to 67867;the run.md Step 4.4 flag-id uniqueness assert and the read-confirm-act-protocol.md flag-id ownership sentences raised it by 200;the run.md Step 1.1b resume-compare and per-file-base sentences raised it by 205;the run.md Project root: spawn-prompt line and definition raised it by 136;the run.md spawn-template tool-path annotation and per-tool-class first-spawn probe lines raised it by 102;the run.md Step 1.1 Before-command re-run item, the Step 1.1a between-CONFIRM-and-dispatch re-verify item and the read-confirm-act-protocol.md §1.3 measured-against stamp, live-artifact paragraph and split template sentence raised it by 685;the --refine <ids> help lines in SKILL.md raised it by 63; the flag mechanism-versus-count test, its Moved stub and the carried-measurement versus carried-inference rewrite in read-confirm-act-protocol.md, plus the one-clause pointer in run.md Step 3.3, re-pinned the floor from 65212 to 65577; the --refine-max help lines in SKILL.md raised it by 53;the run.md Step 1.1e Consumes fill block raised it by 316; the run.md Step 1.1d Session Start Census block raised it by 279;the run.md runner-id, size-ceiling and fresh-runner pointers in Steps 3.3 and 3.4 raised it by 278;the plan Config Gate routing note and the base-references repair in SKILL.md raised it; the --answer help lines in SKILL.md raised it by 46; the session-execution-protocol.md §7 commit-before-COMPLETE precondition and its frontmatter clauses raised it by 161; the run_in_background: false line on the run.md task-runner spawn raised it by 11; the run.md Step 1.1c plugin-path currency check raised it by 388; the run.md Plugin root: spawn-prompt line raised it by 96; the run.md Step 1.1a absence-check before-count bullet raised it by 203; the run.md Step 1.1a per-destination and leftover-placeholder items, the Step 4.4 every-consuming-task wording and the matching read-confirm-act-protocol.md §1.3 and §1.4.A wording raised it by 486; the read-confirm-act-protocol.md §1.4.G native Grep example and its exact-path exclusion sentence raised it by 163; the run.md Parallel dispatch Output-path read clause raised it by 25); checkout bytes (CRLF under core.autocrlf), lower on an LF checkout
BACKLOG_FLOOR_PIN = 40815  # dev tree ba39d07+wt, 2026-11-07, folded (the doctor --verbose help line in SKILL.md raised it by 36, measured 40815); previously 40779 at dev tree d0fd33b+wt, 2026-11-07, folded (the SKILL.md Plan card rule re-pinned the floor from 40678 to 40779, raising it by 101; the Part 4 Step 4 and backlog.md Step 7.3 Question briefing pointers re-pinned the floor from 40495 to 40678; d0fd33b itself already measured 40582, 87 over its pin, and the pointers added 96; the Part 3 Step 2b Why fallback, option label row and other-option description rewrite re-pinned the floor from 40350 to 40495; the --answer briefing change in SKILL.md and handlers/backlog-Part-3-Answers.md re-pinned the floor from 39160 to 40350;the backlog.md compression, which cut duplicated prose or pointed it at its source, lowered it by 1502; the Phase 3 step 2 refine offer, its policy row and the Part 3 Step 4 bullets raised it by 618; the --refine <ids> help lines in SKILL.md raised it by 63; the Part 4 Step 2 batch-cap measurement paragraph raised it by 138;the new Part 4 refine-mode file and its three backlog.md hooks (Arguments row, Required References row, Phase 2 branch) raised it by 2241;the --refine-max Arguments row in backlog.md, the Part 2 --init line and pass-through sentence, the Part 3 Step 4 wording and the SKILL.md help lines raised it by 216;the Part 2 answered-questions Eligibility row and the opt-in exception sentence raised it by 120;the Part 2 dry-run, Q-block, verify-list and summary text raised it; backlog.md net of its cuts; Part 3 and the --answer help lines raised it; the Part 2 refine-step legacy-section sentence raised it by 48; the run_in_background: false line on the backlog.md fix-agent spawn raised it by 10; the Part 2 Phase 6 worked-item row and the Unattended close label sentence raised it by 112; the Part 2 REFINED-ends-the-iteration rows in the result, Phase 6 and No-questions tables plus the Purpose and 5a sentences raised it by 250; the backlog.md Phase 3 step 5 Conditional check sub-bullet and its Part 2 decision-table row raised it by 456); checkout bytes (CRLF under core.autocrlf), lower on an LF checkout

PINS = {"plan": PLAN_FLOOR_PIN, "run": RUN_FLOOR_PIN, "backlog": BACKLOG_FLOOR_PIN}

# Rule 6: the `run["includes_parts"]` assertion is armed when the `run.md` split
# lands (Sprint-12). Before that, this module asserts nothing about `run`'s
# `includes_parts`.


class TestContextFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.subcommands = derive_structural_floor(PLUGIN_ROOT)["subcommands"]

    def test_floor_keys_exist(self):
        for key in PINS:
            self.assertIn(key, self.subcommands, f"floor dict has no {key!r} key")

    def test_floor_within_pins(self):
        for key, pin in PINS.items():
            tokens = self.subcommands[key]["tokens"]
            self.assertGreater(tokens, 0, f"{key} floor is not above 0")
            self.assertLessEqual(tokens, pin, f"{key} floor {tokens} exceeds pin {pin}")

    def test_floor_dict_has_no_part_keys(self):
        part_keys = [key for key in self.subcommands if "-Part-" in key]
        self.assertEqual(part_keys, [], "a Part key survived the fold")


if __name__ == "__main__":
    unittest.main()
