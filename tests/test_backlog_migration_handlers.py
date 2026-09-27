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

    def setUp(self):
        self.text = DOCTOR_HANDLER.read_text(encoding="utf-8-sig")

    def test_stage_20_heading_present(self):
        self.assertIn("### Stage 20: Backlog Index Shape Audit", self.text)

    def test_stage_20_sits_between_stage_19_and_token_saver_audit(self):
        stage19_idx = self.text.index("### Stage 19")
        stage20_idx = self.text.index("### Stage 20: Backlog Index Shape Audit")
        token_saver_idx = self.text.index("## Token Saver Audit")
        self.assertLess(stage19_idx, stage20_idx)
        self.assertLess(stage20_idx, token_saver_idx)

    def test_stage_20_contains_report_json_command(self):
        stage20_span = _span_between(
            self.text,
            "### Stage 20: Backlog Index Shape Audit",
            "## Token Saver Audit",
        )
        self.assertIn("--report --json", stage20_span)

    def test_stage_20_contains_changelog_budget_flags(self):
        stage20_span = _span_between(
            self.text,
            "### Stage 20: Backlog Index Shape Audit",
            "## Token Saver Audit",
        )
        self.assertIn("changelog_over_budget", stage20_span)
        self.assertIn("--split-changelog", stage20_span)

    def test_stage_heading_set_is_old_set_plus_20(self):
        found = set(_STAGE_HEADING_RE.findall(self.text))
        self.assertEqual(found, _PRE_EDIT_STAGE_SET | {"20"})


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
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
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
