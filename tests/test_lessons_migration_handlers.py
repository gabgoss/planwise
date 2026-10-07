#!/usr/bin/env python3
"""Text-pin regression tests for the lessons-index legacy-shape migration
across handlers/{upgrade,init,init-fallback,doctor-Part-2,lessons}.md.

Mirrors test_backlog_migration_handlers.py's pattern for the lessons side
of the migration BCR-Design gave the backlog index: `handlers/upgrade.md`
gains the shape probe, the step-list item, and the banner block;
`handlers/init.md` / `handlers/init-fallback.md` gain the init-time lines;
`handlers/doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md` gains a
read-only Stage 21 shape audit appended after Stage 20; `handlers/lessons.md`
names the regenerate command in List Mode and Capture. These tests pin the
handler text so a later edit cannot silently drop a banner branch, Stage 21,
or the gate's shape probe.

Run with:  python -m pytest tests/test_lessons_migration_handlers.py -q
"""

import re
import unittest
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
UPGRADE_HANDLER = _PLUGIN / "handlers" / "upgrade.md"
INIT_HANDLER = _PLUGIN / "handlers" / "init.md"
INIT_FALLBACK_HANDLER = _PLUGIN / "handlers" / "init-fallback.md"
DOCTOR_HANDLER_PART2 = (
    _PLUGIN / "handlers" / "doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md"
)
LESSONS_HANDLER = _PLUGIN / "handlers" / "lessons.md"
# Step 3 (Render the banner) through Step 4.6 were relocated out of
# upgrade.md into this Part-3 file by the read-gate token split (upgrade.md
# alone exceeded the OVER threshold after this task's lessons-migration
# wiring). The Step 3 banner test below reads this file, not UPGRADE_HANDLER.
UPGRADE_HANDLER_PART3 = (
    _PLUGIN / "handlers" / "upgrade-Part-3-BannerAndConflictResolution.md"
)
DOCTOR_HANDLER_PART3 = (
    _PLUGIN / "handlers" / "doctor-Part-3-TokenSaverAndBookkeepingReadGates.md"
)

_STAGE_HEADING_RE = re.compile(r"^### Stage ([0-9]+[a-z]?):", re.MULTILINE)


def _span_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


class TestUpgradeAndInitHandlersLessonsMigration(unittest.TestCase):
    """Pins the three entry handlers' surfacing of the automated lessons
    index migration (`scripts/lessons_migration.py`), mirroring the backlog
    coverage in test_backlog_migration_handlers.py."""

    def test_upgrade_step_2_4_calls_migrate_lessons_if_legacy_after_backlog(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.4", "### Step 2.5")
        self.assertIn("migrate_lessons_if_legacy", span)
        # the lessons item sits after the backlog item in the numbered list
        self.assertLess(
            span.index("migrate_backlog_if_legacy"),
            span.index("migrate_lessons_if_legacy"),
        )

    def test_upgrade_step_3_banner_contains_lessons_migration_block(self):
        # Step 3 now lives in UPGRADE_HANDLER_PART3 -- see the split's own
        # pointer table in upgrade.md.
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        self.assertIn("Lessons index migration:", span)
        self.assertIn("Lessons index:", span)

    def test_upgrade_step_1_gate_names_the_lessons_migration_block(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(
            text, "[!gate] Upgrade Gate", "[!constraint] Compare the two versions"
        )
        self.assertIn("Lessons index migration:", span)

    def test_init_step_10_banner_has_a_lessons_index_line_group(self):
        text = INIT_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 10 ", "### Step 11 ")
        self.assertIn("Lessons index:", span)

    def test_init_step_2_mentions_lessons_index_migration_block(self):
        text = INIT_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2 ", "### Step 5.1")
        self.assertIn("Lessons index migration:", span)

    def test_init_fallback_step_4_names_the_lessons_upgrade_instruction(self):
        text = INIT_FALLBACK_HANDLER.read_text(encoding="utf-8-sig")
        self.assertIn("hand-shaped lessons index", text)


class TestDoctorHandlerStage21(unittest.TestCase):
    """Stage 21 lives in DOCTOR_HANDLER_PART2, appended after Stage 20 on
    the same template. Stage 20 itself must stay unchanged."""

    def setUp(self):
        self.part2_text = DOCTOR_HANDLER_PART2.read_text(encoding="utf-8-sig")

    def test_stage_21_heading_present(self):
        self.assertIn(
            "### Stage 21: Lessons Index Shape Audit", self.part2_text
        )

    def test_stage_20_precedes_stage_21(self):
        stage20_idx = self.part2_text.index(
            "### Stage 20: Backlog Index Shape Audit"
        )
        stage21_idx = self.part2_text.index(
            "### Stage 21: Lessons Index Shape Audit"
        )
        self.assertLess(stage20_idx, stage21_idx)

    def test_stage_20_unchanged_report_json_command(self):
        stage20_span = _span_between(
            self.part2_text,
            "### Stage 20: Backlog Index Shape Audit",
            "### Stage 21: Lessons Index Shape Audit",
        )
        self.assertIn("--report --json", stage20_span)
        self.assertIn("changelog_over_budget", stage20_span)

    def test_stage_21_contains_report_json_command(self):
        stage21_span = _span_between(
            self.part2_text,
            "### Stage 21: Lessons Index Shape Audit",
            "**Continued in Part 3**",
        )
        self.assertIn("--report --json", stage21_span)
        self.assertIn("migrate_lessons_index.py", stage21_span)

    def test_stage_21_names_the_changelog_resplit_field(self):
        stage21_span = _span_between(
            self.part2_text,
            "### Stage 21: Lessons Index Shape Audit",
            "**Continued in Part 3**",
        )
        self.assertIn("changelog_resplit", stage21_span)
        self.assertIn("within_budget", stage21_span)
        self.assertIn("would_split", stage21_span)
        self.assertIn("refused", stage21_span)

    def test_stage_21_has_no_no_check_escape(self):
        stage21_span = _span_between(
            self.part2_text,
            "### Stage 21: Lessons Index Shape Audit",
            "**Continued in Part 3**",
        )
        # Mirrors Stage 20's own wording: the flag name is mentioned only to
        # say the escape hatch does not exist for this stage.
        self.assertIn("no `--no-check` escape hatch", stage21_span)

    def test_stage_22_follows_stage_21_and_stage_23_is_the_last_stage_heading_in_part2(self):
        stage_headings = list(_STAGE_HEADING_RE.finditer(self.part2_text))
        self.assertTrue(stage_headings)
        last_stage_idx = stage_headings[-1].start()
        stage21_idx = self.part2_text.index(
            "### Stage 21: Lessons Index Shape Audit"
        )
        stage22_idx = self.part2_text.index(
            "### Stage 22: Plans Index Shape Audit"
        )
        stage23_idx = self.part2_text.index("### Stage 23: Style Rules")
        self.assertLess(stage21_idx, stage22_idx)
        self.assertLess(stage22_idx, stage23_idx)
        self.assertEqual(last_stage_idx, stage23_idx)

    def test_closing_cross_reference_still_points_at_part_3(self):
        self.assertIn("Continued in Part 3", self.part2_text)


class TestDoctorStep8ArchiveYearSource(unittest.TestCase):
    """Step 8's Lessons row must name where the changelog archive part's
    `{YYYY}` comes from -- read off the one existing filename on disk, via
    Glob, never guessed or defaulted for this read-gate scan."""

    def setUp(self):
        self.part3_text = DOCTOR_HANDLER_PART3.read_text(encoding="utf-8-sig")

    def test_step_8_names_the_archive_filename_glob_pattern(self):
        self.assertIn("-Archive-*.md", self.part3_text)

    def test_step_8_names_the_shipped_year_resolver(self):
        self.assertIn("lessons_changelog._existing_archive_main", self.part3_text)
        self.assertIn("lessons_changelog._ARCHIVE_YEAR_RE", self.part3_text)

    def test_step_8_names_the_archive_stem_resolver_and_the_four_digit_rule(self):
        """The stem `_existing_archive_main` globs is not a naive changelog
        stem (a custom index name can make those differ) -- it comes from
        `_archive_base`, which derives it from the writer's own namer. Step
        8 must name that resolver, not just the glob/year functions, and
        must state the exactly-four-digits rule the glob is filtered by."""
        span = _span_between(self.part3_text, "### Step 8", "*Cross-reference:")
        self.assertIn("lessons_changelog._archive_base", span)
        self.assertIn(r"-Archive-\d{4}", span)

    def test_step_8_states_no_archive_means_nothing_to_measure(self):
        span = _span_between(
            self.part3_text, "### Step 8", "*Cross-reference:"
        )
        self.assertIn("A tree with no archive part on disk has none to measure", span)


class TestLessonsHandlerRegenerateCommands(unittest.TestCase):
    """List Mode and Capture Step 4's regenerate sentence -- this task's
    only two headings in lessons.md."""

    def setUp(self):
        self.text = LESSONS_HANDLER.read_text(encoding="utf-8-sig")

    def test_list_mode_states_the_hub_is_generated_and_names_check(self):
        span = _span_between(self.text, "## List Mode", "## Search Mode")
        self.assertIn("generated", span)
        self.assertIn("--check", span)

    def test_capture_step_4_names_the_write_command_and_companion_flag(self):
        span = _span_between(self.text, "### Step 4: Write", "### Step 5: Skip")
        self.assertIn("generate_lessons_index.py", span)
        self.assertIn("{plugin_root}", span)
        self.assertIn("--write", span)
        self.assertIn("--companion --write", span)


if __name__ == "__main__":
    unittest.main()
