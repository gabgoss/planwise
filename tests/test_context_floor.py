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
PLAN_FLOOR_PIN = 103640  # dev tree 4f84134+wt (plan.md router + 2 parts, Steps 4-8c render path, router reading order), 2026-10-22, folded; checkout bytes (CRLF under core.autocrlf), lower on an LF checkout
RUN_FLOOR_PIN = 63630  # dev tree 0cd43b8+wt, 2026-10-27, folded (the plan Config Gate routing note and the base-references repair in SKILL.md raised it; the --answer help lines in SKILL.md raised it by 46); checkout bytes (CRLF under core.autocrlf), lower on an LF checkout
BACKLOG_FLOOR_PIN = 36438  # dev tree 0cd43b8+wt, 2026-10-27, folded (the Part 2 dry-run, Q-block, verify-list and summary text raised it; backlog.md net of its cuts; Part 3 and the --answer help lines raised it; the Part 2 refine-step legacy-section sentence raised it by 48); checkout bytes (CRLF under core.autocrlf), lower on an LF checkout

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
