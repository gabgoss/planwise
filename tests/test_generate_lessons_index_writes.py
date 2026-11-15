#!/usr/bin/env python3
"""Unit tests for generate_lessons_index.py's refusal, drift and write half: the
legacy-shape refusal, the guard edits, drift classes, duplicate-id refusals,
write idempotence and line-ending preservation, the atomic-write rollback, the
unsplittable-row refusal, the wrapper-boundary split, and title truncation.

The shared fixture base and the lesson-item builder live in
test_generate_lessons_index.py, which holds the scan and render half.

Run with:  python -m pytest tests/test_generate_lessons_index_writes.py -q
"""

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import generate_lessons_index as gli
from test_generate_lessons_index import (
    _PURE_LESSONS_DIR,
    _GenerateLessonsIndexFixtureBase,
    _make_lesson_item,
)


class TestLegacyRefusal(_GenerateLessonsIndexFixtureBase):
    """A fixture hub with `## Master Table` makes --write exit 2 and write
    nothing; --replace-legacy overwrites it; --check reports legacy-shape."""

    def _write_legacy_hub(self) -> Path:
        content = (
            "# Lessons Learned Index\n\n"
            "## Master Table\n\n"
            "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
            "|----|----|----|----|----|----|----|----|----|----|\n"
        )
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(content.encode("utf-8"))
        return hub_path

    def test_write_refuses_legacy_hub_exit_two_writes_nothing(self):
        self.write_lesson(101, status="documented")
        hub_path = self._write_legacy_hub()
        before = hub_path.read_bytes()

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("legacy", err.lower())
        self.assertEqual(hub_path.read_bytes(), before)

    def test_replace_legacy_overwrites_it(self):
        self.write_lesson(101, status="documented")
        hub_path = self._write_legacy_hub()

        code, _out, _err = self.run_main("--write", "--replace-legacy")

        self.assertEqual(code, 0)
        self.assertNotIn("## Master Table", hub_path.read_text(encoding="utf-8"))

    def test_check_reports_legacy_shape(self):
        # BIR-S05-06-04 guard edit: --check on a legacy hub now exits 2,
        # naming /planwise upgrade, instead of the drift-report exit 1.
        self.write_lesson(101, status="documented")
        self._write_legacy_hub()

        code, _out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertIn("/planwise upgrade", err)

    def _write_legacy_hub_with_hand_written_sections(self) -> Path:
        content = (
            "# Lessons Learned Index\n\n"
            "## Naming Convention\n\n"
            "**Format:** `LL-{NNN}-{Domain}-{Name}.md`\n\n"
            "## Status Definitions\n\n"
            "| Status | Meaning |\n|--------|---------|\n\n"
            "## Quick Reference\n\n"
            "| Action | How |\n|--------|-----|\n\n"
            "## Master Table\n\n"
            "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
            "|----|----|----|----|----|----|----|----|----|----|\n\n"
            "## Lesson File Template\n\n"
            "```yaml\nid: LL-{NNN}\n```\n\n"
            "## Archive\n\n"
            "A lesson is moved to `Archive/` when fully captured.\n\n"
            "## Rule Promotion Log\n\n"
            "See the promotion log file.\n"
        )
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(content.encode("utf-8"))
        return hub_path

    def test_refusal_names_each_dropped_heading(self):
        # Code-review fix 4: the refusal on a legacy hub must name every
        # hand-written section --replace-legacy would drop, one per line,
        # never Master Table itself (its row DATA migrates).
        self.write_lesson(101, status="documented")
        self._write_legacy_hub_with_hand_written_sections()

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        for heading in (
            "Naming Convention", "Status Definitions", "Quick Reference",
            "Lesson File Template", "Archive", "Rule Promotion Log",
        ):
            self.assertIn(heading, err)
        self.assertNotIn("## Master Table", err)

    def test_replace_legacy_run_also_names_each_dropped_heading(self):
        self.write_lesson(101, status="documented")
        self._write_legacy_hub_with_hand_written_sections()

        code, out, _err = self.run_main("--write", "--replace-legacy")

        self.assertEqual(code, 0)
        for heading in (
            "Naming Convention", "Status Definitions", "Quick Reference",
            "Lesson File Template", "Archive", "Rule Promotion Log",
        ):
            self.assertIn(heading, out)
        self.assertNotIn("## Master Table", out)


class TestBIRS0506_04GuardEdits(_GenerateLessonsIndexFixtureBase):
    """BIR-S05-06-04's three surgical guard edits: fence-aware heading
    detection, the exit-2 --check on a legacy hub, and the --replace-legacy
    help text pointing at the migrator."""

    def test_legacy_headings_to_drop_is_fence_aware(self):
        content = (
            "# Lessons Learned Index\n\n"
            "## Naming Convention\n\nOutside the fence, a real heading.\n\n"
            "## Lesson File Template\n\n"
            "```yaml\n"
            "id: LL-{NNN}\n"
            "---\n\n"
            "# LL-{NNN}-{Domain}: {Title}\n\n"
            "## Context\n\n{body}\n\n"
            "## Lesson\n\n{body}\n\n"
            "## Applies To\n\n{body}\n"
            "```\n\n"
            "## Archive\n\nAlso outside the fence, a real heading.\n"
        )
        dropped = gli._legacy_headings_to_drop(content)
        self.assertIn("Naming Convention", dropped)
        self.assertIn("Lesson File Template", dropped)
        self.assertIn("Archive", dropped)
        for fenced in ("Context", "Lesson", "Applies To"):
            self.assertNotIn(fenced, dropped)

    def test_check_exit_two_on_legacy_hub_names_upgrade(self):
        self.write_lesson(101, status="documented")
        content = (
            "# Lessons Learned Index\n\n## Master Table\n\n"
            "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
            "|----|----|----|----|----|----|----|----|----|----|\n"
        )
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(content.encode("utf-8"))

        code, out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertIn(str(hub_path), err)
        self.assertIn("/planwise upgrade", err)
        self.assertEqual(out, "")

    def test_check_json_on_legacy_hub_prints_the_report_then_exits_two(self):
        self.write_lesson(101, status="documented")
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(
            b"# Lessons Learned Index\n\n## Master Table\n\n"
            b"| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
            b"|----|----|----|----|----|----|----|----|----|----|\n"
        )

        code, out, err = self.run_main("--check", "--json")

        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertIn("legacy-shape", [f["class"] for f in payload["drift"]])
        self.assertIn("/planwise upgrade", err)

    def test_check_help_text_describes_the_legacy_hub_exit(self):
        old_argv = sys.argv
        sys.argv = ["generate_lessons_index.py", "--help"]
        out = StringIO()
        try:
            with redirect_stdout(out), self.assertRaises(SystemExit):
                gli.main()
        finally:
            sys.argv = old_argv
        text = " ".join(out.getvalue().split())
        self.assertNotIn("only --write stops early", text)
        self.assertIn("legacy-shape finding", text)

    def test_lessons_exit_code_for_refuses_report_mode_on_legacy_shape(self):
        findings = [{"class": "legacy-shape", "id": "00-Index-LessonsLearned.md", "detail": "x"}]
        self.assertEqual(gli.lessons_exit_code_for(write_mode=False, findings=findings),
                         gli.LessonsDisposition.REFUSED)
        self.assertEqual(gli.lessons_exit_code_for(write_mode=False, findings=[]),
                         gli.LessonsDisposition.CLEAN)

    def test_write_refusal_names_upgrade_before_the_flag(self):
        self.write_lesson(101, status="documented")
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(
            b"# Lessons Learned Index\n\n## Master Table\n\n"
            b"| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status | File |\n"
            b"|----|----|----|----|----|----|----|----|----|----|\n"
        )

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        upgrade_at = err.find("/planwise upgrade")
        flag_at = err.find("--replace-legacy")
        self.assertNotEqual(upgrade_at, -1)
        self.assertNotEqual(flag_at, -1)
        self.assertLess(upgrade_at, flag_at)

    def test_replace_legacy_help_text_points_to_migrator(self):
        old_argv = sys.argv
        sys.argv = ["generate_lessons_index.py", "--help"]
        out = StringIO()
        try:
            with redirect_stdout(out), self.assertRaises(SystemExit):
                gli.main()
        finally:
            sys.argv = old_argv
        text = out.getvalue()
        self.assertIn("migrate_lessons_index.py", text)
        self.assertIn("relocated", text)


class _DriftFixtureBase(_GenerateLessonsIndexFixtureBase):
    """A 5-lesson fixture (LL-001/002 documented, LL-003 orphaned -- hub;
    LL-004 rule, LL-005 promoted -- Archive) written once via --write. Each
    drift test mutates the on-disk generated set exactly one way and
    asserts the resulting class, id/path, and exit code."""

    def setUp(self):
        super().setUp()
        self.write_lesson(1, status="documented")
        self.write_lesson(2, status="documented")
        self.write_lesson(3, status="orphaned")
        self.write_lesson(4, status="rule", directory=self.archive_dir)
        self.write_lesson(5, status="promoted", directory=self.archive_dir)
        code, _out, _err = self.run_main("--write")
        assert code == 0, "drift fixture setUp must --write cleanly"
        self.hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        self.shard_path = next(self.archive_dir.glob("Index-LessonsLearned-*.md"))


class TestDriftClasses(_DriftFixtureBase):
    """Each Step 6 drift class, produced by one targeted mutation of the
    on-disk generated set, asserted by class name, id/path, and exit code."""

    def test_stale_title_reports_class_id_and_exit_code(self):
        self.replace_cell_in_row(self.hub_path, 1, gli.COL_TITLE, "Edited title")
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-title] LL-001", out)

    def test_stale_status_reports_class_id_and_exit_code(self):
        self.replace_cell_in_row(self.hub_path, 3, gli.COL_STATUS, "documented")
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-status] LL-003", out)

    def test_stale_cell_reports_class_id_and_exit_code(self):
        self.replace_cell_in_row(self.hub_path, 2, gli.COL_CATEGORY, "different-category")
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-cell] LL-002", out)

    def test_stale_counter_reports_class_and_exit_code(self):
        # Code-review fix 2: BELOW the derived value (LL-006) is
        # stale-counter; ABOVE it is counter_ahead (see the sibling test).
        text = self.hub_path.read_text(encoding="utf-8")
        text = text.replace("**Next available ID:** LL-006", "**Next available ID:** LL-003")
        self.hub_path.write_bytes(text.encode("utf-8"))
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-counter]", out)
        self.assertNotIn("counter_ahead", out)

    def test_counter_ahead_reports_class_and_exit_code(self):
        text = self.hub_path.read_text(encoding="utf-8")
        text = text.replace("**Next available ID:** LL-006", "**Next available ID:** LL-999")
        self.hub_path.write_bytes(text.encode("utf-8"))
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[counter_ahead] LL-999", out)
        self.assertNotIn("stale-counter", out)

    def test_missing_row_reports_class_id_and_exit_code(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = [line for line in text.split("\n") if not line.startswith("| LL-002 |")]
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[missing-row] LL-002", out)

    def test_extra_row_reports_class_id_and_exit_code(self):
        (self.archive_dir / "LL-005-PROC-Fixture5.md").unlink()
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[extra-row] LL-005", out)

    def test_stale_generated_file_reports_class_and_exit_code(self):
        bogus = self.lessons_dir / "00-Index-LessonsLearned-900-999.md"
        bogus.write_bytes(b"stale\n")
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-generated-file]", out)
        self.assertIn("900-999", out)

    def test_row_shape_anomaly_reports_class_and_exit_code(self):
        text = self.shard_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("| LL-004 |"):
                idx = line.index("|", 1)
                lines[i] = line[:idx] + line[idx + 1 :]
                break
        else:
            raise AssertionError("LL-004 row not found in shard")
        self.shard_path.write_bytes("\n".join(lines).encode("utf-8"))
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[row-shape]", out)
        self.assertIn(self.shard_path.name, out)

    def test_duplicate_id_anomaly_reports_class_id_and_exit_code(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        dup_line = next(line for line in lines if line.startswith("| LL-001 |"))
        idx = lines.index(dup_line)
        lines.insert(idx + 1, dup_line)
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[duplicate-id] LL-001", out)

    def test_location_anomaly_reports_class_and_exit_code(self):
        lesson_path = self.lessons_dir / "LL-002-PROC-Fixture2.md"
        moved = self.archive_dir / lesson_path.name
        lesson_path.rename(moved)
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[location-anomaly]", out)
        self.assertIn("LL-002-PROC-Fixture2.md", out)


class TestF1StaleWrapperAndMisplacedRow(_DriftFixtureBase):
    """F1 remediation (design review BIR-S05-03-05): --check compares every
    generated file's non-table content, so a pointer edit, a removed
    '## Shards' line, a renamed header cell, or a row moved into the wrong
    generated file all report -- and a row-level class keeps precedence
    over stale-wrapper for the same edit."""

    def _replace_in_hub(self, old: str, new: str) -> None:
        text = self.hub_path.read_text(encoding="utf-8")
        self.assertIn(old, text, "corruption fixture must find its target text")
        self.hub_path.write_bytes(text.replace(old, new, 1).encode("utf-8"))

    def test_promotion_log_pointer_edit_reports_stale_wrapper(self):
        self._replace_in_hub(
            "[Promotion Log](00-PromotionLog-LessonsLearned.md)",
            "[Promotion Log](00-Somewhere-Else.md)",
        )
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-wrapper]", out)
        self.assertIn(self.hub_path.name, out)

    def test_changelog_pointer_edit_reports_stale_wrapper(self):
        self._replace_in_hub(
            "[Changelog](00-Changelog-LessonsLearned.md)",
            "[Changelog](00-Somewhere-Else.md)",
        )
        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[stale-wrapper]", out)
        self.assertIn(self.hub_path.name, out)

    def test_shards_directory_line_removed_reports_stale_wrapper(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = [line for line in text.split("\n") if not line.startswith("## Shards")]
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("[stale-wrapper]", out)
        self.assertIn(self.hub_path.name, out)

    def test_header_cell_renamed_reports_stale_wrapper(self):
        self._replace_in_hub("| Severity |", "| Sev |")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("[stale-wrapper]", out)
        self.assertIn(self.hub_path.name, out)

    def test_row_moved_to_wrong_generated_file_reports_misplaced_row(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        moved_line = next(line for line in lines if line.startswith("| LL-002 |"))
        lines.remove(moved_line)
        self.hub_path.write_bytes("\n".join(lines).encode("utf-8"))
        shard_text = self.shard_path.read_text(encoding="utf-8")
        self.shard_path.write_bytes(
            (shard_text.rstrip("\n") + "\n" + moved_line + "\n").encode("utf-8")
        )

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("[misplaced-row] LL-002", out)

    def test_single_stale_title_reports_stale_title_not_stale_wrapper(self):
        self.replace_cell_in_row(self.hub_path, 1, gli.COL_TITLE, "Edited title")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("[stale-title] LL-001", out)
        self.assertNotIn("[stale-wrapper]", out)


class TestDuplicateIdWriteRefusal(_GenerateLessonsIndexFixtureBase):
    """D18: two lesson FILES claiming the same id. --write refuses, naming
    the id and both paths; --check exits non-zero too (drift, since
    nothing has been written yet)."""

    def test_write_refuses_naming_both_paths(self):
        self.write_lesson(1, status="documented")
        self.write_lesson(1, status="documented", suffix="-dup", directory=self.archive_dir)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("LL-001", err)
        self.assertIn("Fixture1.md", err)
        self.assertIn("Fixture1-dup.md", err)
        self.assertFalse((self.lessons_dir / "00-Index-LessonsLearned.md").exists())

    def test_check_also_exits_nonzero(self):
        self.write_lesson(1, status="documented")
        self.write_lesson(1, status="documented", suffix="-dup", directory=self.archive_dir)

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("[duplicate-id] LL-001", out)


class TestF2DuplicateIdOnDiskAfterWrite(_GenerateLessonsIndexFixtureBase):
    """F2 remediation: the index is written BEFORE the duplicate id exists
    on disk, so the on-disk generated set itself never carried a
    duplicate row -- only the second lesson FILE does. --check must still
    report duplicate-id, naming the id and both paths; --write must still
    refuse."""

    def test_duplicate_id_added_after_write_reports_class_and_refuses_write(self):
        self.write_lesson(2, status="documented")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        self.write_lesson(2, status="rule", directory=self.archive_dir, suffix="-dup")

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("[duplicate-id] LL-002", out)
        self.assertIn("Fixture2.md", out)
        self.assertIn("Fixture2-dup.md", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 2)


class TestWriteThenCheckIdempotent(_GenerateLessonsIndexFixtureBase):
    """--write then --check exits 0; a second --write is byte-identical
    (compared as bytes, not text)."""

    def test_write_then_check_exits_zero_and_second_write_is_byte_identical(self):
        self.write_lesson(1, status="documented")
        self.write_lesson(2, status="rule", directory=self.archive_dir)
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)

        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        shard_path = next(self.archive_dir.glob("Index-LessonsLearned-*.md"))
        hub_before = hub_path.read_bytes()
        shard_before = shard_path.read_bytes()

        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertEqual(hub_path.read_bytes(), hub_before)
        self.assertEqual(shard_path.read_bytes(), shard_before)


class TestLineEndingPreservation(_GenerateLessonsIndexFixtureBase):
    """CRLF preservation: a CRLF hub fixture stays CRLF after --write; an
    LF fixture stays LF."""

    def test_crlf_hub_stays_crlf_after_write(self):
        self.write_lesson(1, status="documented")
        self.run_main("--write")
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        hub_path.write_bytes(hub_path.read_bytes().replace(b"\n", b"\r\n"))

        self.write_lesson(2, status="documented")
        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        content = hub_path.read_bytes()
        self.assertNotIn(b"\n", content.replace(b"\r\n", b""))

    def test_lf_hub_stays_lf_after_write(self):
        self.write_lesson(1, status="documented")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        self.assertNotIn(b"\r\n", hub_path.read_bytes())


class TestAtomicWriteRollsBackOnMidFailure(_GenerateLessonsIndexFixtureBase):
    """A simulated mid-write failure leaves the prior set intact -- no
    partial shard set, no committed new file."""

    def test_mid_write_failure_leaves_prior_state_intact(self):
        self.write_lesson(1, status="documented")
        self.write_lesson(2, status="rule", directory=self.archive_dir)
        self.run_main("--write")
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        shard_path = next(self.archive_dir.glob("Index-LessonsLearned-*.md"))
        hub_before = hub_path.read_bytes()
        shard_before = shard_path.read_bytes()

        self.write_lesson(3, status="documented")

        real_replace = gbi.os.replace
        call_count = {"n": 0}

        def flaky_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("simulated mid-write failure")
            return real_replace(src, dst)

        with patch.object(gbi.os, "replace", side_effect=flaky_replace):
            code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("rolled back", err)
        self.assertEqual(hub_path.read_bytes(), hub_before)
        self.assertEqual(shard_path.read_bytes(), shard_before)


class TestStaleGeneratedFileWriteRemovalScope(_DriftFixtureBase):
    """The only delete this generator performs: a stale generated file is
    removed by --write, and nothing else is ever touched."""

    def test_write_removes_only_the_stale_generated_file(self):
        bogus = self.lessons_dir / "00-Index-LessonsLearned-900-999.md"
        bogus.write_bytes(b"stale\n")
        unrelated = self.lessons_dir / "NOTES.md"
        unrelated.write_bytes(b"unrelated, not generated\n")
        unrelated_before = unrelated.read_bytes()
        lesson_files_before = {p: p.read_bytes() for p in self.lessons_dir.rglob("LL-*.md")}

        code, out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertIn("Removed stale generated file", out)
        self.assertFalse(bogus.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(unrelated.read_bytes(), unrelated_before)
        for path, before in lesson_files_before.items():
            self.assertEqual(path.read_bytes(), before)


class TestGeneratorNeverWritesALessonFile(_GenerateLessonsIndexFixtureBase):
    """Every lesson fixture is byte-identical after --write."""

    def test_every_lesson_file_byte_identical_after_write(self):
        paths = [
            self.write_lesson(1, status="documented"),
            self.write_lesson(2, status="rule", directory=self.archive_dir),
            self.write_lesson(3, status="orphaned", crlf=True),
        ]
        before = {p: p.read_bytes() for p in paths}

        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)


class TestUnsplittableRowRefusal(_GenerateLessonsIndexFixtureBase):
    """F4: one lesson whose row alone (plus the wrapper reserve) exceeds
    HUB_TOKEN_BUDGET raises LessonsGeneratorError naming its id, and the
    CLI's --write exits 2, writing nothing."""

    def test_single_oversized_row_refuses_write_naming_the_id(self):
        self.write_lesson(1, status="documented", category="x" * 40000)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("LL-001", err)
        self.assertFalse((self.lessons_dir / "00-Index-LessonsLearned.md").exists())


class TestF4RealWrapperBoundarySplit(unittest.TestCase):
    """F4: a body that fits HUB_TOKEN_BUDGET on its own must still split
    once build_lessons_hub_files adds the REAL hub_wrapper_tokens reserve
    -- not the synthetic reserve TestBudgetOnShippedBytes uses -- and
    every resulting leaf then measures under budget on shipped bytes."""

    def test_body_under_budget_alone_splits_with_the_real_wrapper_reserve(self):
        naming = gbi._index_naming(_PURE_LESSONS_DIR / "00-Index-LessonsLearned.md")
        next_id = 3
        header_block = gli.render_header_block(next_id)
        real_wrapper_tokens = gli.hub_wrapper_tokens(
            gli.render_shards_section([]), naming, next_id, header_block
        )
        self.assertGreater(real_wrapper_tokens, 0, "the real wrapper must carry a nonzero reserve")

        def body_tokens_for(pad):
            items = [
                _make_lesson_item(1, category="x" * pad),
                _make_lesson_item(2, category="x" * pad),
            ]
            body, _truncated = gli._render_lessons_table_body(items, _PURE_LESSONS_DIR)
            _num_bytes, tokens = gli._measure(body)
            return items, tokens

        # Binary-search for the LARGEST pad whose bare body still fits
        # under HUB_TOKEN_BUDGET alone -- the smallest possible margin, so
        # adding any nonzero real wrapper reserve must cross the budget.
        lo, hi = 0, 1
        while body_tokens_for(hi)[1] < gli.HUB_TOKEN_BUDGET:
            lo, hi = hi, hi * 2
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if body_tokens_for(mid)[1] < gli.HUB_TOKEN_BUDGET:
                lo = mid
            else:
                hi = mid
        items, body_tokens = body_tokens_for(lo)
        self.assertLess(body_tokens, gli.HUB_TOKEN_BUDGET, "fixture must fit by body-only measurement")

        hub_files = gli.build_lessons_hub_files(items, _PURE_LESSONS_DIR, [], naming, next_id=next_id)

        self.assertGreater(len(hub_files), 1, "the real wrapper reserve alone must force a split")
        for entry in hub_files:
            shipped_tokens = gli.estimate_tokens(gli._shipped_bytes(entry["content"]))
            self.assertLess(shipped_tokens, gli.HUB_TOKEN_BUDGET, "every leaf must measure under budget on _shipped_bytes")


class TestTitleTruncation(_GenerateLessonsIndexFixtureBase):
    """A title over 120 characters is cut at a word boundary, and the run
    prints one stderr summary line naming the truncation count (F6 --
    supersedes the earlier one-line-per-title warning)."""

    def test_title_over_120_chars_truncated_at_word_boundary_with_stderr_summary(self):
        long_title = (
            "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet "
            "Kilo Lima Mike November Oscar Papa Quebec Romeo Sierra Tango"
        )
        self.assertGreater(len(long_title), 120)
        expected, was_truncated = gli.truncate_title(long_title)
        self.assertTrue(was_truncated)

        self.write_lesson(1, status="documented", title=long_title)
        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        text = hub_path.read_text(encoding="utf-8")
        self.assertIn(expected, text)
        self.assertNotIn(long_title, text)
        self.assertIn('1 title(s) truncated at 120 characters; see --json "truncated" for ids', err)

    def test_multiple_truncations_produce_exactly_one_summary_line_with_the_count(self):
        long_title = (
            "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet "
            "Kilo Lima Mike November Oscar Papa Quebec Romeo Sierra Tango"
        )
        self.write_lesson(1, status="documented", title=long_title)
        self.write_lesson(2, status="rule", directory=self.archive_dir, title=long_title)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertEqual(err.count("title(s) truncated"), 1)
        self.assertIn('2 title(s) truncated at 120 characters; see --json "truncated" for ids', err)

    def test_json_truncated_lists_every_truncated_id(self):
        long_title = (
            "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet "
            "Kilo Lima Mike November Oscar Papa Quebec Romeo Sierra Tango"
        )
        self.write_lesson(1, status="documented", title=long_title)
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        code, out, _err = self.run_main("--check", "--json")

        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["truncated"], ["LL-001"])

    def test_no_truncation_prints_no_summary_line(self):
        self.write_lesson(1, status="documented", title="A short title")

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertNotIn("truncated", err)


if __name__ == "__main__":
    unittest.main()
