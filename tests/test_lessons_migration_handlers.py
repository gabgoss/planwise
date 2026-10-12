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

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
sys.path.insert(0, str(_PLUGIN / "scripts"))
# The doctor folds Stages 20-22 into doctor_audits.py and Step 8 into
# doctor_probes.py. The handler keeps only "the script prints this stage
# (banner: ...)", so the field and archive-source pins below assert against
# the script that now implements each behaviour.
DOCTOR_AUDITS_SCRIPT = _PLUGIN / "scripts" / "doctor_audits.py"
DOCTOR_PROBES_SCRIPT = _PLUGIN / "scripts" / "doctor_probes.py"
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


def _flat(text: str) -> str:
    """Collapse every whitespace run, so a banner wrapped across lines compares."""
    return " ".join(text.split())


def _function_source(path: Path, name: str) -> str:
    """The source text of the top-level function `name` in the script at `path`."""
    text = path.read_text(encoding="utf-8")
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"{path.name} defines no function {name}")


def _imported_modules(function_source: str) -> set:
    """The module names a function's `import` statements bind."""
    tree = ast.parse(function_source)
    return {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}


def _string_constants(function_source: str) -> set:
    """Every string literal a function holds, as whole values."""
    tree = ast.parse(function_source)
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _script_banner(path: Path, constant: str) -> str:
    """The banner string the script assigns to the module constant `constant`."""
    match = re.search(rf'^{constant} = "([^"\n]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name} assigns no banner constant {constant}"
    return match.group(1)


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

    def test_upgrade_step_3_lessons_refused_block_has_no_rerun_sentence(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        block = _span_between(span, "Lessons index migration: REFUSED", "— or")
        self.assertNotIn("re-run", block)
        self.assertIn("fix:    {the migrator's fix, verbatim}", block)

    def test_upgrade_step_3_lessons_findings_block_has_no_writer(self):
        text = UPGRADE_HANDLER_PART3.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 3 ", "### Step 4 ")
        self.assertIn("Lessons index: generated; --check reports", span)
        self.assertIn("has no writer", span)

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

    def test_upgrade_step_2_4_names_no_lessons_reconcile_flag(self):
        # The handler's command never passes the flag, so naming it in the
        # prose documents an option the run cannot reach.
        text = UPGRADE_HANDLER.read_text(encoding="utf-8-sig")
        span = _span_between(text, "### Step 2.4", "### Step 2.5")
        self.assertNotIn("--lessons-reconcile", span)


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

    def _stage_span(self, number: int, next_heading: str) -> str:
        headings = {
            20: "### Stage 20: Backlog Index Shape Audit",
            21: "### Stage 21: Lessons Index Shape Audit",
        }
        return _span_between(self.part2_text, headings[number], next_heading)

    def test_stage_20_unchanged_script_banner_and_changelog_budget_field(self):
        # Was: the handler lists `--report --json` and `changelog_over_budget`.
        # Now: the handler hands Stage 20 to the script (banner), names no
        # folded command, and the script owns the changelog_over_budget field.
        span = self._stage_span(20,"### Stage 21: Lessons Index Shape Audit")
        banner = _script_banner(DOCTOR_AUDITS_SCRIPT, "_BACKLOG_SHAPE_BANNER")
        self.assertIn(f"The script prints this stage (banner: {banner})", _flat(span))
        self.assertNotIn("--report --json", span)
        self.assertIn("changelog_over_budget", _function_source(DOCTOR_AUDITS_SCRIPT, "_stage_20"))
        self.assertIn("changelog_over_budget", _function_source(DOCTOR_AUDITS_SCRIPT, "_print_changelog_budget"))

    def test_stage_21_handler_names_the_script_banner_and_no_folded_command(self):
        # Was: the handler contains `--report --json` and `migrate_lessons_index.py`.
        # Now: the handler hands Stage 21 to the script (banner) and names
        # neither folded command. The script's Stage 21 imports the migrator.
        span = self._stage_span(21, "### Stage 22: Plans Index Shape Audit")
        banner = _script_banner(DOCTOR_AUDITS_SCRIPT, "_LESSONS_SHAPE_BANNER")
        self.assertIn(f"The script prints this stage (banner: {banner})", _flat(span))
        self.assertNotIn("--report --json", span)
        self.assertNotIn("migrate_lessons_index.py", span)
        stage_21 = _function_source(DOCTOR_AUDITS_SCRIPT, "_stage_21")
        self.assertIn("migrate_lessons_index", _imported_modules(stage_21))
        self.assertIn("_safe_report", stage_21)

    def test_stage_21_names_the_changelog_resplit_field(self):
        # Was: the handler names the field and its verdicts. Now: the script's
        # Stage 21 reads the field and branches on each verdict.
        # Exact string constants, so a message that merely mentions a name
        # does not stand in for the read or the branch.
        constants = _string_constants(_function_source(DOCTOR_AUDITS_SCRIPT, "_stage_21"))
        for name in ("changelog_resplit", "within_budget", "would_split", "refused"):
            self.assertIn(name, constants)

    def test_stage_21_has_no_no_check_escape(self):
        # Was: the handler says "no `--no-check` escape hatch". Now: the
        # handler is a pass-through and offers no `--no-check` flag, and the
        # script's Stage 21 carries none either.
        span = self._stage_span(21, "### Stage 22: Plans Index Shape Audit")
        self.assertIn("Pass it through verbatim.", _flat(span))
        self.assertNotIn("--no-check", span)
        self.assertNotIn("no-check", _function_source(DOCTOR_AUDITS_SCRIPT, "_stage_21"))

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
        self.family_source = _function_source(DOCTOR_PROBES_SCRIPT, "_changelog_family")

    def _family(self, *extra_names):
        """`(names, base)`: the file names `doctor_probes._changelog_family`
        returns for a lessons directory holding `extra_names`, where each
        `{base}` in an extra name stands for the writer's archive stem."""
        import doctor_probes
        import lessons_changelog
        from backlog_index_schema import _changelog_filename, _index_naming

        with tempfile.TemporaryDirectory() as tmp:
            lessons_dir = Path(tmp)
            naming = _index_naming(lessons_dir / "00-Index-LessonsLearned.md")
            changelog_name = _changelog_filename(naming)
            base = lessons_changelog._archive_base(naming, changelog_name)
            for name in extra_names:
                (lessons_dir / name.format(base=base)).write_text("x", encoding="utf-8")
            files = doctor_probes._changelog_family(lessons_dir, naming)
            return [p.name for p in files], base, changelog_name

    def test_step_8_hands_the_scan_to_the_script(self):
        # The folded handler keeps one sentence: the script prints the scan.
        span = _span_between(self.part3_text, "### Step 8", "*Cross-reference:")
        banner = _script_banner(DOCTOR_PROBES_SCRIPT, "_READ_GATE_BANNER")
        self.assertIn(f"The script prints this stage (banner: {banner})", _flat(span))

    def test_step_8_names_the_archive_filename_glob_pattern(self):
        # Was: the handler names the `-Archive-*.md` glob. Now: the script
        # finds an archive part by that filename shape, and reads its Part-NN
        # continuations by the year taken from the name.
        names, base, changelog = self._family(
            "{base}-Archive-2024.md", "{base}-Archive-2024-Part-02.md"
        )
        self.assertEqual(
            names,
            [changelog, f"{base}-Archive-2024.md", f"{base}-Archive-2024-Part-02.md"],
        )

    def test_step_8_names_the_shipped_year_resolver(self):
        # Was: the handler names the two resolvers. Now: the script's
        # changelog-family function calls both.
        self.assertIn("lc._existing_archive_main", self.family_source)
        self.assertIn("lc._ARCHIVE_YEAR_RE", self.family_source)

    def test_step_8_names_the_archive_stem_resolver_and_the_four_digit_rule(self):
        """The stem `_existing_archive_main` globs is not a naive changelog
        stem (a custom index name can make those differ) -- it comes from
        `_archive_base`, which derives it from the writer's own namer. The
        script must call that resolver, and must keep a suffix that is not
        exactly four digits out of the family."""
        self.assertIn("lc._archive_base", self.family_source)
        names, _base, changelog = self._family(
            "{base}-Archive-24.md", "{base}-Archive-20245.md", "{base}-Archive-2024-Part-02.md"
        )
        self.assertEqual(names, [changelog])

    def test_step_8_states_no_archive_means_nothing_to_measure(self):
        # Was: the handler says "A tree with no archive part on disk has none
        # to measure". Now: with no archive on disk the family is the main
        # changelog alone, and the script invents no year.
        names, _base, changelog = self._family()
        self.assertEqual(names, [changelog])


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


class TestLessonsIndexShapeGatePointer(unittest.TestCase):
    """lessons.md holds one gate line that points at the shared reference. The
    reference carries the branches, so the handler never restates them."""

    def setUp(self):
        self.text = LESSONS_HANDLER.read_text(encoding="utf-8-sig")
        self.reference = (_PLUGIN / "references" / "index-shape-gate.md").read_text(encoding="utf-8-sig")

    def test_gate_subsection_points_at_the_reference_and_names_the_script(self):
        span = _span_between(self.text, "### Index shape gate", "## List Mode")
        self.assertIn("index_shape_preflight.py", span)
        self.assertIn("../references/index-shape-gate.md", span)
        self.assertIn("AUTO-MODE: critical", span)
        self.assertNotIn("--upgrade-pair", span)

    def test_every_mode_still_links_the_gate_subsection(self):
        self.assertGreaterEqual(self.text.count("(#index-shape-gate)"), 4)

    def test_reference_runs_step_2_3b_before_step_2_4_and_reruns_the_preflight(self):
        self.assertLess(self.reference.index("Step 2.3b"), self.reference.index("Step 2.4 with"))
        self.assertLess(self.reference.index("Step 2.4 with"), self.reference.index("Run the preflight again"))

    def test_no_handler_names_the_removed_run_part_file(self):
        for path in sorted((_PLUGIN / "handlers").glob("*.md")):
            self.assertNotIn("run-Part-2-PreflightGate", path.read_text(encoding="utf-8-sig"), path.name)


if __name__ == "__main__":
    unittest.main()
