#!/usr/bin/env python3
"""Tests for promotion_log.py's guarded append writer: the five-way
century routing (imported, never re-derived), duplicate-tuple refusal
(normalized on both sides), malformed-cell refusal, the hub-missing
refusal, on-first-use century-file creation with the hub's `Parts:`
listing kept in step, byte-exact CRLF preservation, and `--dry-run`
writing nothing.

Every fixture is built with `write_bytes`, never `write_text`, so a CRLF
fixture stays CRLF until the code under test rewrites it (Archive/LL-149).
"""
import contextlib
import io
import sys
import tempfile
import typing
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from promotion_log import main

CONFIG_YAML_FIXTURE = (
    b'project:\n'
    b'  name: "PromotionLogFixtureProject"\n'
    b'  lessons_dir: "LessonsLearned"\n'
    b'  index_files:\n'
    b'    lessons: "00-Index-LessonsLearned.md"\n'
    b'lesson_statuses:\n'
    b'- documented\n'
    b'- promoted\n'
    b'- applied\n'
    b'- rule\n'
    b'- orphaned\n'
)

LOG_HEADER = "| Date | Lesson ID | Artifact Created | File |"
LOG_SEP = "|------|-----------|-----------------|------|"


class PromotionLogTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.planwise_dir = self.tmp_path / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.archive_dir = self.lessons_dir / "Archive"
        self.archive_dir.mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_bytes(CONFIG_YAML_FIXTURE)

    def _seed_log(self, rel_path: str, rows: list = (), crlf: bool = False) -> Path:
        path = self.lessons_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        index_name = "00-Index-LessonsLearned.md"
        lines = [f"[← {index_name}]({index_name})", "", LOG_HEADER, LOG_SEP]
        lines += list(rows)
        text = "\n".join(lines) + "\n"
        if crlf:
            text = text.replace("\n", "\r\n")
        path.write_bytes(text.encode("utf-8"))
        return path

    def _run(self, argv: list) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(argv)
        return code, out.getvalue()

    def _argv(self, lesson: str, artifact: str, file_: str, *extra: str) -> list:
        return ["--config", str(self.config_path), "--lesson", lesson,
               "--artifact", artifact, "--file", file_, *extra]


class TestFiveWayRouting(PromotionLogTestCase):
    """Each of the five century files, by id: <=50, 51-75, 76-100, 101-200,
    >=201 -- `log_destination` is imported from migrate_lessons_support,
    never re-derived here."""

    CASES: typing.ClassVar = [
        (10, "Archive/PromotionLog-LessonsLearned-001-050.md"),
        (60, "Archive/PromotionLog-LessonsLearned-051-075.md"),
        (90, "Archive/PromotionLog-LessonsLearned-076-100.md"),
        (150, "Archive/PromotionLog-LessonsLearned-101-200.md"),
        (250, "00-PromotionLog-LessonsLearned.md"),
    ]

    def test_each_destination_appends_one_row(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        for lesson_id, rel in self.CASES:
            with self.subTest(lesson_id=lesson_id):
                # The hub must exist (it is the one refusal precondition); the
                # dest file itself is pre-seeded too, so this exercises the
                # ordinary append path, not century-file creation.
                self._seed_log(hub_rel)
                self._seed_log(rel)
                code, out = self._run(self._argv(f"LL-{lesson_id:03d}", "a rule", "some/path.md"))
                self.assertEqual(code, 0, out)
                text = (self.lessons_dir / rel).read_text(encoding="utf-8")
                self.assertIn(f"LL-{lesson_id:03d}", text)
                self.assertIn("| a rule |", text)


class TestDedupRefusal(PromotionLogTestCase):
    def test_duplicate_tuple_refused(self):
        rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(rel, rows=["| 2026-01-01 | LL-201 | a rule | some/path.md |"])
        code, out = self._run(self._argv("LL-201", "a rule", "some/other.md"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("already logged", out)

    def test_same_lesson_different_artifact_not_refused(self):
        rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(rel, rows=["| 2026-01-01 | LL-201 | a rule | some/path.md |"])
        code, out = self._run(self._argv("LL-201", "a different rule", "some/other.md"))
        self.assertEqual(code, 0, out)

    def test_duplicate_refused_despite_surrounding_whitespace(self):
        """Both sides of the comparison are normalized (`_normalize_cell`):
        a stored cell is already stripped by `row_cells` on read-back, and
        a fresh `--artifact` argument is stripped the same way, so `" a
        rule "` collides with the stored `"a rule"` instead of silently
        evading the duplicate check."""
        rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(rel, rows=["| 2026-01-01 | LL-201 | a rule | some/path.md |"])
        code, out = self._run(self._argv("LL-201", " a rule ", "some/other.md"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("already logged", out)


class TestMalformedArgumentRefusal(PromotionLogTestCase):
    def test_empty_artifact_refused(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "  ", "some/path.md"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)

    def test_nonempty_artifact_accepted(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)

    def test_unescaped_pipe_refused(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a | rule", "some/path.md"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)

    def test_escaped_pipe_accepted(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", r"a \| rule", "some/path.md"))
        self.assertEqual(code, 0, out)

    def test_bad_date_refused(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md", "--date", "01-01-2026"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)

    def test_good_date_accepted(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md", "--date", "2026-01-01"))
        self.assertEqual(code, 0, out)


class TestMissingFileRefusal(PromotionLogTestCase):
    def test_missing_destination_refused_naming_seed_command(self):
        # No file seeded at all -- LL-010 routes to the Archive 001-050 file.
        code, out = self._run(self._argv("LL-010", "a rule", "some/path.md"))
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", out)
        self.assertIn("migrate_lessons_index.py", out)


class TestCenturyFileCreation(PromotionLogTestCase):
    """A missing Archive century file whose hub-side sibling exists (a fresh
    project, or a family migrated before this id range ever had a row) is
    created on first use -- never refused -- with the opener
    `render_promotion_logs` produces, and the hub's `Parts:` listing is
    updated to name it."""

    def test_fresh_project_creates_century_file_and_parts_listing(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(hub_rel)  # zero rows, zero Archive files -- a fresh project
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        self.assertFalse(century_path.is_file())
        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)
        self.assertTrue(century_path.is_file())
        century_text = century_path.read_text(encoding="utf-8")
        self.assertIn(LOG_HEADER, century_text)
        self.assertIn(LOG_SEP, century_text)
        self.assertIn("LL-007", century_text)
        self.assertIn("| a rule |", century_text)
        hub_text = (self.lessons_dir / hub_rel).read_text(encoding="utf-8")
        self.assertIn(
            "Parts: [Archive/PromotionLog-LessonsLearned-001-050.md]"
            "(Archive/PromotionLog-LessonsLearned-001-050.md)",
            hub_text,
        )

    def test_second_promotion_appends_to_the_created_century_file(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(hub_rel)
        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)
        code, out = self._run(self._argv("LL-008", "a different rule", "some/other.md"))
        self.assertEqual(code, 0, out)
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        text = century_path.read_text(encoding="utf-8")
        self.assertIn("LL-007", text)
        self.assertIn("LL-008", text)
        hub_text = (self.lessons_dir / hub_rel).read_text(encoding="utf-8")
        self.assertEqual(hub_text.count("Parts:"), 1)

    def test_crlf_family_stays_crlf_through_century_creation(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(hub_rel, crlf=True)
        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        century_raw = century_path.read_bytes()
        self.assertNotIn(b"\r\r\n", century_raw)
        self.assertGreater(century_raw.count(b"\r\n"), 0)
        hub_raw = (self.lessons_dir / hub_rel).read_bytes()
        self.assertNotIn(b"\r\r\n", hub_raw)
        self.assertGreater(hub_raw.count(b"\r\n"), 0)


class TestCRLFPreserved(PromotionLogTestCase):
    def test_crlf_file_stays_crlf_byte_exact(self):
        """Byte-exact, not a `\\n`-vs-`\\r\\n` count: the weak form this
        replaces (`count(b"\\n") == count(b"\\r\\n")`) is satisfied even when
        every pre-existing line was corrupted into `\\r\\r\\n`, because that
        corruption adds one `\\r` and zero bare `\\n` per line -- both counts
        still move together. Assert `b"\\r\\r\\n"` never occurs, and that every
        pre-existing line survives byte-for-byte, in order, once the one new
        row is removed."""
        rel = "00-PromotionLog-LessonsLearned.md"
        path = self._seed_log(rel, rows=["| 2026-01-01 | LL-050 | a rule | some/existing.md |"], crlf=True)
        before = path.read_bytes()
        self.assertNotIn(b"\r\r\n", before)
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)
        raw = path.read_bytes()
        self.assertNotIn(b"\r\r\n", raw)
        before_lines = before.split(b"\r\n")
        after_lines = raw.split(b"\r\n")
        new_row_hits = [ln for ln in after_lines if b"LL-201" in ln]
        self.assertEqual(len(new_row_hits), 1)
        after_lines.remove(new_row_hits[0])
        self.assertEqual(after_lines, before_lines)


class TestDryRun(PromotionLogTestCase):
    def test_dry_run_writes_nothing(self):
        rel = "00-PromotionLog-LessonsLearned.md"
        path = self._seed_log(rel)
        before = path.read_bytes()
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md", "--dry-run"))
        self.assertEqual(code, 0, out)
        after = path.read_bytes()
        self.assertEqual(before, after)
        self.assertIn("LL-201", out)


class TestExitCodes(PromotionLogTestCase):
    def test_append_is_zero(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, _out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 0)

    def test_refusal_is_one(self):
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, _out = self._run(self._argv("LL-201", "", "some/path.md"))
        self.assertEqual(code, 1)

    def test_missing_file_is_two(self):
        code, _out = self._run(self._argv("LL-010", "a rule", "some/path.md"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
