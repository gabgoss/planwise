#!/usr/bin/env python3
"""Text-pin regression tests for the two read-side handlers' hand-authored
(legacy) backlog index branches.

`handlers/backlog.md` Phase 1 stops before Phase 2 when the generator's
`--check` exits 2 on a hand-authored index, and points the user at
`/planwise upgrade`. `handlers/doctor.md` gains a read-only Stage 20 shape
audit appended after Stage 19. These tests pin the handler text so a later
edit cannot silently drop either branch.

Run with:  python -m pytest tests/test_backlog_migration_handlers.py -q
"""

import re
import unittest
from pathlib import Path

BACKLOG_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "backlog.md"
)
DOCTOR_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "doctor.md"
)
# Stages 14-20 were relocated out of doctor.md into this Part-2 file by the
# read-gate token split (doctor.md alone exceeded the WARN threshold). Stage
# 20's own tests below read this file, not DOCTOR_HANDLER.
DOCTOR_HANDLER_PART2 = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers"
    / "doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md"
)
DOCTOR_HANDLER_PART3 = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers"
    / "doctor-Part-3-TokenSaverAndBookkeepingReadGates.md"
)
# Step 3 (Render the banner) through Step 4.6 were relocated out of
# upgrade.md into this Part-3 file by the read-gate token split (upgrade.md
# alone exceeded the OVER threshold after the lessons-migration wiring).
# The Step 3 banner test below reads this file, not UPGRADE_HANDLER.
UPGRADE_HANDLER_PART3 = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers"
    / "upgrade-Part-3-BannerAndConflictResolution.md"
)

# The Stage heading set present in doctor.md BEFORE this task's Stage 20 was
# appended. Pinned as a literal so the post-edit set can be asserted by
# membership rather than by count.
_PRE_EDIT_STAGE_SET = {
    "8", "8b", "9", "10", "11", "12", "13", "14", "14b",
    "15", "16", "17", "17b", "18", "19",
}

_STAGE_HEADING_RE = re.compile(r"^### Stage ([0-9]+[a-z]?):", re.MULTILINE)


def _span_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


class TestBacklogHandlerHandAuthoredIndexBranch(unittest.TestCase):

    def setUp(self):
        self.text = BACKLOG_HANDLER.read_text(encoding="utf-8-sig")
        self.phase1_span = _span_between(self.text, "## Phase 1", "## Phase 2")

    def test_phase1_mentions_hand_authored_index(self):
        self.assertIn("hand-authored index", self.phase1_span)

    def test_phase1_points_at_upgrade_command(self):
        self.assertIn("/planwise upgrade", self.phase1_span)

    def test_phase1_stops_on_an_unrecognized_index_with_the_report_command(self):
        branch = _span_between(self.phase1_span, "`unrecognized index shape`", "\n")
        self.assertIn("--report", branch)
        self.assertIn("STOP", branch)
        self.assertNotIn("hand-authored", branch)


class TestDoctorHandlerStage20(unittest.TestCase):
    """Stages 14-20 now live in DOCTOR_HANDLER_PART2, and the Token Saver
    Audit that used to immediately follow Stage 20 in the same file now
    lives in DOCTOR_HANDLER_PART3 -- see the split's own pointer table in
    doctor.md. Assertions that used to span both within one file now assert
    Stage 20 is Part 2's last stage and that Part 2 hands off to Part 3."""

    def setUp(self):
        self.part1_text = DOCTOR_HANDLER.read_text(encoding="utf-8-sig")
        self.part2_text = DOCTOR_HANDLER_PART2.read_text(encoding="utf-8-sig")
        self.part3_text = DOCTOR_HANDLER_PART3.read_text(encoding="utf-8-sig")

    def test_stage_20_heading_present(self):
        self.assertIn("### Stage 20: Backlog Index Shape Audit", self.part2_text)

    def test_stage_20_present_and_immediately_followed_by_stage_21_and_stage_22_is_the_last_heading(self):
        # Stage 21 (Lessons Index Shape Audit) was appended immediately after
        # Stage 20 by the lessons-migration handler wiring, and Stage 22
        # (Plans Index Shape Audit) after Stage 21 by the plans-migration
        # handler wiring, so Stage 22 is now Part 2's last stage. Stage 20's
        # own heading must still be present, byte-unchanged, and precede
        # Stage 21 with no other stage heading between them.
        stage_headings = list(_STAGE_HEADING_RE.finditer(self.part2_text))
        self.assertTrue(stage_headings)
        stage20_idx = self.part2_text.index("### Stage 20: Backlog Index Shape Audit")
        stage21_idx = self.part2_text.index("### Stage 21: Lessons Index Shape Audit")
        stage22_idx = self.part2_text.index("### Stage 22: Plans Index Shape Audit")
        self.assertLess(stage20_idx, stage21_idx)
        self.assertLess(stage21_idx, stage22_idx)
        last_stage_idx = stage_headings[-1].start()
        self.assertEqual(last_stage_idx, stage22_idx)
        # no stage heading sits between Stage 20 and Stage 21
        between = [h for h in stage_headings if stage20_idx < h.start() < stage21_idx]
        self.assertEqual(between, [])

    def test_stage_19_precedes_stage_20_in_part2(self):
        stage19_idx = self.part2_text.index("### Stage 19")
        stage20_idx = self.part2_text.index("### Stage 20: Backlog Index Shape Audit")
        self.assertLess(stage19_idx, stage20_idx)

    def test_part2_hands_off_to_token_saver_audit_in_part3(self):
        self.assertIn("Continued in Part 3", self.part2_text)
        self.assertIn("## Token Saver Audit", self.part3_text)

    def test_stage_20_contains_report_json_command(self):
        stage20_span = _span_between(
            self.part2_text,
            "### Stage 20: Backlog Index Shape Audit",
            "**Continued in Part 3**",
        )
        self.assertIn("--report --json", stage20_span)

    def test_stage_20_contains_changelog_budget_flags(self):
        stage20_span = _span_between(
            self.part2_text,
            "### Stage 20: Backlog Index Shape Audit",
            "**Continued in Part 3**",
        )
        self.assertIn("changelog_over_budget", stage20_span)
        self.assertIn("--split-changelog", stage20_span)

    def test_stage_heading_set_is_old_set_plus_20_21_and_22(self):
        # Stages 8-13 now live in Part 1 (doctor.md); Stages 14-22 in Part 2
        # (Stage 21, Lessons Index Shape Audit, was appended after Stage 20
        # by the lessons-migration handler wiring, and Stage 22, Plans Index
        # Shape Audit, after Stage 21 by the plans-migration handler wiring).
        found = set(_STAGE_HEADING_RE.findall(self.part1_text)) | set(
            _STAGE_HEADING_RE.findall(self.part2_text)
        )
        self.assertEqual(found, _PRE_EDIT_STAGE_SET | {"20", "21", "22"})


if __name__ == "__main__":
    unittest.main()

# appended by the upgrade/init handler task

UPGRADE_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "upgrade.md"
)
INIT_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "init.md"
)
INIT_FALLBACK_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "init-fallback.md"
)


class TestUpgradeAndInitHandlersBacklogMigration(unittest.TestCase):
    """Pins the three entry handlers' surfacing of the automated backlog
    index migration (`scripts/backlog_migration.py`) so a later edit cannot
    silently drop a banner branch or the gate's shape probe."""

    def test_upgrade_step_2_4_calls_migrate_backlog_if_legacy(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.4", "### Step 2.5")
        self.assertIn("migrate_backlog_if_legacy", span)

    def test_upgrade_step_3_banner_contains_migration_block(self):
        # Step 3 now lives in UPGRADE_HANDLER_PART3 -- see the split's own
        # pointer table in upgrade.md.
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        self.assertIn("Backlog index migration:", span)

    def test_upgrade_step_1_gate_names_a_hand_authored_index(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "[!gate] Upgrade Gate", "[!constraint] Compare the two versions")
        self.assertIn("hand-authored", span)

    def test_init_step_10_banner_has_a_backlog_index_line_group(self):
        text = INIT_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 10 ", "### Step 11 ")
        self.assertIn("Backlog index:", span)

    def test_init_fallback_step_4_seeds_the_backlog_changelog(self):
        text = INIT_FALLBACK_HANDLER.read_text(encoding="utf-8-sig")
        self.assertIn("00-Changelog-Backlog.md", text)
