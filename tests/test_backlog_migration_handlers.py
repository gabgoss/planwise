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

    def test_stage_20_present_and_immediately_followed_by_stage_21_and_stage_23_is_the_last_heading(self):
        # Stage 21 (Lessons Index Shape Audit) was appended immediately after
        # Stage 20 by the lessons-migration handler wiring, Stage 22
        # (Plans Index Shape Audit) after Stage 21 by the plans-migration
        # handler wiring, and Stage 23 (Style Rules) after Stage 22 by the
        # style-rules handler wiring, so Stage 23 is now Part 2's last stage.
        # Stage 20's own heading must still be present, byte-unchanged, and
        # precede Stage 21 with no other stage heading between them.
        stage_headings = list(_STAGE_HEADING_RE.finditer(self.part2_text))
        self.assertTrue(stage_headings)
        stage20_idx = self.part2_text.index("### Stage 20: Backlog Index Shape Audit")
        stage21_idx = self.part2_text.index("### Stage 21: Lessons Index Shape Audit")
        stage22_idx = self.part2_text.index("### Stage 22: Plans Index Shape Audit")
        stage23_idx = self.part2_text.index("### Stage 23: Style Rules")
        self.assertLess(stage20_idx, stage21_idx)
        self.assertLess(stage21_idx, stage22_idx)
        self.assertLess(stage22_idx, stage23_idx)
        last_stage_idx = stage_headings[-1].start()
        self.assertEqual(last_stage_idx, stage23_idx)
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

    def test_stage_heading_set_is_old_set_plus_20_21_22_and_23(self):
        # Stages 8-13 now live in Part 1 (doctor.md); Stages 14-23 in Part 2
        # (Stage 21, Lessons Index Shape Audit, was appended after Stage 20
        # by the lessons-migration handler wiring, Stage 22, Plans Index
        # Shape Audit, after Stage 21 by the plans-migration handler wiring,
        # and Stage 23, Style Rules, after Stage 22 by the style-rules handler
        # wiring).
        found = set(_STAGE_HEADING_RE.findall(self.part1_text)) | set(
            _STAGE_HEADING_RE.findall(self.part2_text)
        )
        # Stage 15b (thrifty-sonic env var sweep) sits beside Stage 15, the
        # other settings-file sweep.
        self.assertEqual(found, _PRE_EDIT_STAGE_SET | {"15b", "20", "21", "22", "23"})

    def test_prune_upgrade_leftovers_command_carries_root(self):
        # init_project.py defaults --root to "planwise", so a command that
        # omits it scans the wrong directory on a custom planwise root.
        command_lines = [
            line
            for line in self.part2_text.splitlines()
            if "init_project.py" in line and "--prune-upgrade-leftovers" in line
        ]
        self.assertTrue(command_lines, "no prune-upgrade-leftovers command found")
        for line in command_lines:
            self.assertIn('--root "{planwise_root}"', line)


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

    def test_upgrade_step_2_4_names_no_reconcile_flag(self):
        # The handler's command never passes the flag, so naming it in the
        # prose documents an option the run cannot reach.
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.4", "### Step 2.5")
        self.assertNotIn("--backlog-reconcile", span)

    def test_upgrade_step_3_backlog_block_lists_parked_units(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        self.assertIn("parked ambiguous units:", span)

    def test_upgrade_step_3_unrecognized_branches_print_detail_not_a_command(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        self.assertNotIn("inspect it with", span)
        self.assertGreaterEqual(span.count("detail:"), 3)

    def test_upgrade_step_3_refused_blocks_carry_the_fix_alone(self):
        # The preflight asks before the write, so no REFUSED block tells the
        # user to re-run; each prints the migrator's fix and stops.
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        self.assertNotIn("then re-run /planwise upgrade", text)
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        for family in ("Backlog", "Lessons", "Plans"):
            block = _span_between(span, f"{family} index migration: REFUSED", "— or")
            self.assertIn("fix:    {the migrator's fix, verbatim}", block)

    def test_upgrade_step_2_3b_runs_the_preflight_and_writes_the_answers_file(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.3b", "### Step 2.4")
        self.assertIn("index_shape_preflight.py", span)
        self.assertIn("--questions", span)
        self.assertIn("AskUserQuestion", span)
        self.assertIn("upgrade-conflicts/{from}-to-{to}/migration-answers.json", span)
        self.assertIn("at most 4 questions", span)

    def test_upgrade_step_2_4_passes_the_answers_file(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.4", "### Step 2.5")
        self.assertIn('--migration-answers "{answers_path}"', span)

    def test_upgrade_step_4_3_prunes_through_the_writer(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 4.3", "### Step 4.4")
        self.assertIn("--prune-upgrade-leftovers", span)
        self.assertIn("--prune-classes", span)
        self.assertIn('--root "{planwise_root}"', span)
        self.assertIn("review-then-discard", span)
        self.assertNotIn("delete the matched files", span)

    def test_upgrade_step_3_offers_the_plan_status_writer_per_anomaly(self):
        # Anchor on the procedure paragraph itself. The banner template above
        # it already holds some of these tokens, so a whole-Step-3 span would
        # pass with the paragraph deleted. The paragraph is absent at the base
        # revision, where this slice cannot be taken at all.
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "**Plans anomalies.**", "**Lessons findings.**")
        self.assertIn("flip_plan_status.py", span)
        self.assertIn("map line:", span)
        self.assertIn("hand-fix:", span)
        self.assertIn("AskUserQuestion", span)

    def test_upgrade_step_3_regenerates_the_plans_index_on_any_change(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "**Plans anomalies.**", "**Lessons findings.**")
        self.assertIn("any change", span)
        self.assertIn("even if it exited 1", span)
        self.assertNotIn("After a clean run", span)

    def test_upgrade_step_3_mirror_prune_asks_over_the_full_removable_set(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "Orphaned agent mirrors:` block", "#### Style rule announcement")
        self.assertIn("read-only `/planwise doctor` report", span)
        self.assertIn("stale de-scoped rules", span)
        self.assertIn("never list a `PRESERVE` row as removable", span)
        self.assertLess(span.index("read-only `/planwise doctor` report"), span.index("AskUserQuestion"))

    def test_upgrade_step_4_3_backup_sentence_does_not_forbid_case_c_deletions(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 4.3", "### Step 4.4")
        self.assertNotIn("Never remove a recovery file by hand", span)
        self.assertIn("Never remove a file in these backup classes by hand", span)

    def test_upgrade_step_2_3b_answers_nothing_in_auto_mode_and_runs_step_2_4(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.3b", "### Step 2.4")
        self.assertIn("AUTO-MODE: convenience", span)
        self.assertNotIn("AUTO-MODE: critical", span)
        self.assertNotIn("STOP before Step 2.4", span)
        self.assertIn("run Step 2.4 without `--migration-answers`", span)
        self.assertIn("action required", span)
        self.assertIn("answer the reciprocal-edge question in an interactive /planwise upgrade", span)

    def test_upgrade_headless_note_and_step_table_cover_step_2_3b(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        table = _span_between(text, "[!decide] Interactive upgrade sequence", "### Step 2.1")
        self.assertIn("Step 2.3b", table)
        note = table[table.index("Headless / non-interactive"):]
        self.assertIn("Step 2.3b", note)
        self.assertIn("no `--migration-answers`", note)

    def test_doctor_prune_stale_command_carries_the_planwise_root(self):
        text = DOCTOR_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Stage 8b", "### Stage 9")
        commands = [ln for ln in span.splitlines() if "init_project.py" in ln and "--prune-stale" in ln]
        self.assertEqual(len(commands), 1, commands)
        self.assertIn('--root "{planwise_root}"', commands[0])
        part3 = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        prune = _span_between(part3, "Orphaned agent mirrors:` block", "#### Style rule announcement")
        self.assertIn("Stage 8b", prune)
        self.assertIn("doctor.md", prune)


GATE_REFERENCE = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "references" / "index-shape-gate.md"
)
RUN_HANDLER = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "run.md"
)
LESSONS_HANDLER_FOR_GATE = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "handlers" / "lessons.md"
)
_SHIPPED = Path(__file__).resolve().parent.parent / "plugins" / "planwise"


class TestIndexShapeGateIsDefinedOnce(unittest.TestCase):
    """The gate lives in references/index-shape-gate.md. The run, lessons and
    backlog handlers point at it, and every route into the Step 2.4 writer
    asks the Step 2.3b questions first."""

    def test_every_route_into_step_2_4_names_step_2_3b_first(self):
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        gate = _span_between(text, "[!gate] Upgrade Gate", "[!constraint] Compare the two versions")
        branches = [ln for ln in gate.splitlines() if "run Step 2.3b" in ln or "Step 2.4 script invocation" in ln]
        self.assertGreaterEqual(len(branches), 2)
        for line in branches:
            if "Step 2.4 script invocation" in line:
                self.assertLess(line.index("Step 2.3b"), line.index("Step 2.4 script invocation"), line)
        reference = GATE_REFERENCE.read_text(encoding="utf-8-sig")
        self.assertLess(reference.index("Step 2.3b"), reference.index("Step 2.4 with"))

    def test_reference_holds_the_rerun_and_stop_branches(self):
        text = GATE_REFERENCE.read_text(encoding="utf-8-sig")
        self.assertIn("index_shape_preflight.py", text)
        self.assertIn("any_legacy", text)
        self.assertIn("Run the preflight again", text)
        self.assertIn("a family reads `REFUSED`", text)
        self.assertIn("the writer exited non-zero", text)
        self.assertIn("the script is missing", text)
        self.assertIn("STOP", text)
        self.assertIn("AUTO-MODE: critical", text)
        self.assertIn("{install_scope}", text)

    def test_reference_binds_every_placeholder_of_the_step_2_4_command(self):
        # Derive the placeholder set from the Step 2.4 code fence at test time.
        upgrade = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        step = _span_between(upgrade, "### Step 2.4", "### Step 2.5")
        fence = re.search(r"```bash\n(.*?)```", step, re.DOTALL)
        self.assertIsNotNone(fence)
        placeholders = set(re.findall(r"\{([a-z_]+)\}", fence.group(1)))
        # The migration-answers flag sits in prose beside the fence.
        placeholders |= set(re.findall(r'--migration-answers "\{([a-z_]+)\}"', step))
        self.assertGreaterEqual(len(placeholders), 9, placeholders)
        reference = GATE_REFERENCE.read_text(encoding="utf-8-sig")
        for name in sorted(placeholders):
            self.assertIn("`{" + name + "}`", reference, name)
        self.assertIn("project.name", reference)
        self.assertIn("exit code 2", reference)
        self.assertIn("/planwise upgrade", reference)
        self.assertNotIn("{plugin_version}", reference)

    def test_run_lessons_and_backlog_point_at_the_reference(self):
        for path in (RUN_HANDLER, LESSONS_HANDLER_FOR_GATE, BACKLOG_HANDLER):
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("index_shape_preflight.py", text, path.name)
            self.assertIn("../references/index-shape-gate.md", text, path.name)
            self.assertNotIn("Step 2.4 with `--upgrade-pair", text, path.name)

    def test_no_shipped_file_names_the_removed_run_part_file(self):
        self.assertFalse((_SHIPPED / "handlers" / "run-Part-2-PreflightGate.md").exists())
        for path in sorted(_SHIPPED.rglob("*.md")):
            self.assertNotIn(
                "run-Part-2-PreflightGate", path.read_text(encoding="utf-8-sig"), path.name
            )
