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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import migrate_backlog_support
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

# F3: both `lessons_changelog.py` modes and `promotion_log.py --append` refuse
# beside an index that is not generated. These mirror the fixtures
# `LessonsChangelogTestCase` uses for the same check.
INDEX_NAME = "00-Index-LessonsLearned.md"
GENERATED_INDEX = b"Generated: 2026-01-01\n**Next available ID:** LL-001\n\n| ID | Title |\n|---|---|\n"
LEGACY_INDEX = b"# Lessons Learned Index\n\n## Master Table\n\n| ID | Title |\n|---|---|\n"


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
        # Every test below appends against an already-generated index; the
        # index-not-generated refusal gets its own fixture (TestIndexNotGenerated).
        (self.lessons_dir / INDEX_NAME).write_bytes(GENERATED_INDEX)

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


class TestIndexNotGenerated(PromotionLogTestCase):
    """F3 (promotion-log side): `--append` refuses beside an index that is
    not generated, matching `lessons_changelog.py`'s own guard (reused via
    `lessons_changelog.index_refusal`, never re-derived here), so a
    bootstrap seed stays header-only for the migration."""

    def test_append_refuses_beside_a_legacy_index(self):
        (self.lessons_dir / INDEX_NAME).write_bytes(LEGACY_INDEX)
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 1, out)
        self.assertIn("not generated", out)
        self.assertIn("/planwise upgrade", out)

    def test_append_refuses_when_the_index_is_missing(self):
        (self.lessons_dir / INDEX_NAME).unlink()
        self._seed_log("00-PromotionLog-LessonsLearned.md")
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 1, out)  # not 2 -- the index guard fires before the hub-missing check
        self.assertIn("does not exist", out)


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


class TestCenturyCreationAllOrNothing(PromotionLogTestCase):
    """F5: century-file creation writes the new file and updates the hub's
    `Parts:` listing as one all-or-nothing step -- a failure restores every
    file already written and removes whatever this call created, with a
    clean REFUSED message, never a raw traceback."""

    def test_a_failure_after_the_century_file_lands_restores_the_hub_and_removes_it(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        hub_path = self._seed_log(hub_rel)  # zero rows, zero Archive files -- a fresh project
        before_hub = hub_path.read_bytes()
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        real_replace = migrate_backlog_support._replace
        calls: list = []

        def _second_replace_fails(tmp, path):
            calls.append(path)
            if len(calls) == 2:  # the century file's own replace lands first; the hub's fails
                raise OSError("simulated failure writing the hub")
            return real_replace(tmp, path)

        with patch("migrate_backlog_support._replace", _second_replace_fails):
            code, out = self._run(self._argv("LL-007", "a rule", "some/path.md"))
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSED", out)
        self.assertNotIn("Traceback", out)
        self.assertFalse(century_path.is_file())  # the created file is removed, not left orphaned
        self.assertEqual(hub_path.read_bytes(), before_hub)  # the hub is untouched


class TestStalePartsListingRepair(PromotionLogTestCase):
    """F5: a re-run repairs a hub `Parts:` listing a century file's
    existence has outgrown (an earlier interrupted run, a hand edit), even
    when the row itself is already logged and the call ends up refusing."""

    def test_a_duplicate_append_still_repairs_a_stale_listing(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        hub_path = self._seed_log(hub_rel)  # zero rows, zero Parts: line
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        century_path.parent.mkdir(parents=True, exist_ok=True)
        index_name = "00-Index-LessonsLearned.md"
        century_text = (f"[← {index_name}]({index_name})\n\n{LOG_HEADER}\n{LOG_SEP}\n"
                       "| 2026-01-01 | LL-007 | a rule | some/path.md |\n")
        century_path.write_bytes(century_text.encode("utf-8"))
        self.assertNotIn("Parts:", hub_path.read_text(encoding="utf-8"))

        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md"))  # a duplicate of the row above
        self.assertEqual(code, 1, out)
        self.assertIn("already logged", out)
        hub_text = hub_path.read_text(encoding="utf-8")
        self.assertIn(
            "Parts: [Archive/PromotionLog-LessonsLearned-001-050.md]"
            "(Archive/PromotionLog-LessonsLearned-001-050.md)",
            hub_text,
        )

    def test_dry_run_does_not_repair_a_stale_listing(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        hub_path = self._seed_log(hub_rel)
        century_path = self.lessons_dir / "Archive" / "PromotionLog-LessonsLearned-001-050.md"
        century_path.parent.mkdir(parents=True, exist_ok=True)
        index_name = "00-Index-LessonsLearned.md"
        century_text = (f"[← {index_name}]({index_name})\n\n{LOG_HEADER}\n{LOG_SEP}\n"
                       "| 2026-01-01 | LL-007 | a rule | some/path.md |\n")
        century_path.write_bytes(century_text.encode("utf-8"))
        before_hub = hub_path.read_bytes()

        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md", "--dry-run"))
        self.assertEqual(code, 1, out)
        self.assertEqual(hub_path.read_bytes(), before_hub)


# B: a refused promotion-log retry must not rewrite the hub. The bug
# (`_with_parts_listing` recognised only `Parts: `) fires on THIS project's
# own live hub, which carries `Archive parts: `, middle-dot separated,
# link text just the href's filename -- an earlier migrator's form, not
# produced anywhere in the current tree.
MIDDOT = "·"
ARCHIVE_PARTS_LISTING = (
    f"Archive parts: [PromotionLog-LessonsLearned-001-050.md](Archive/PromotionLog-LessonsLearned-001-050.md) "
    f"{MIDDOT} [PromotionLog-LessonsLearned-051-075.md](Archive/PromotionLog-LessonsLearned-051-075.md) "
    f"{MIDDOT} [PromotionLog-LessonsLearned-076-100.md](Archive/PromotionLog-LessonsLearned-076-100.md) "
    f"{MIDDOT} [PromotionLog-LessonsLearned-101-200.md](Archive/PromotionLog-LessonsLearned-101-200.md)"
)
CENTURY_BANDS = ("001-050", "051-075", "076-100", "101-200")


class TestArchivePartsListingForm(PromotionLogTestCase):
    """B: the hub's Archive-parts listing line may be `Parts: ` (the
    current writer's own form) or `Archive parts: ` (an earlier
    migrator's form, carried by this project's own live hub) -- both must
    be recognised, repaired in place on their existing line and in their
    existing form, and never duplicated onto a second line."""

    def _seed_archive_parts_hub(self, rows: list = ()) -> Path:
        index_name = "00-Index-LessonsLearned.md"
        hub_path = self.lessons_dir / "00-PromotionLog-LessonsLearned.md"
        lines = [f"[← {index_name}]({index_name})", "", ARCHIVE_PARTS_LISTING, "", LOG_HEADER, LOG_SEP]
        lines += list(rows)
        hub_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        for band in CENTURY_BANDS:
            century_path = self.archive_dir / f"PromotionLog-LessonsLearned-{band}.md"
            century_path.write_bytes(f"[← {index_name}]({index_name})\n\n{LOG_HEADER}\n{LOG_SEP}\n".encode())
        return hub_path

    def test_a_retried_append_leaves_the_archive_parts_hub_byte_identical(self):
        # LL-201 routes to the hub itself (>= 201), so a retry's own stale-
        # listing repair check runs against the very line this test seeds.
        hub_path = self._seed_archive_parts_hub()
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 0, out)
        after_first = hub_path.read_bytes()
        self.assertEqual(after_first.count(b"Archive parts:"), 1)
        self.assertNotIn(b"\nParts: ", after_first)

        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md"))
        self.assertEqual(code, 1, out)
        self.assertIn("already logged", out)
        self.assertEqual(hub_path.read_bytes(), after_first)  # byte-identical: the listing was not stale

    def test_a_truly_stale_listing_is_repaired_in_place_with_the_line_recomputed_after(self):
        # No listing line at all yet, though all four century files already
        # exist on disk (an earlier interrupted run, a hand edit) -- so a
        # repair inserts a fresh default-form line, shifting the duplicate
        # row (also in the hub, since LL-201 >= 201) down by one line.
        index_name = "00-Index-LessonsLearned.md"
        hub_path = self.lessons_dir / "00-PromotionLog-LessonsLearned.md"
        lines = [f"[← {index_name}]({index_name})", "", LOG_HEADER, LOG_SEP,
                "| 2026-01-01 | LL-201 | a rule | some/path.md |"]
        hub_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        for band in CENTURY_BANDS:
            century_path = self.archive_dir / f"PromotionLog-LessonsLearned-{band}.md"
            century_path.write_bytes(f"[← {index_name}]({index_name})\n\n{LOG_HEADER}\n{LOG_SEP}\n".encode())
        # The row sits at line 5 before any repair (backlink, blank, header,
        # separator, row).
        code, out = self._run(self._argv("LL-201", "a rule", "some/path.md", "--date", "2026-04-01"))
        self.assertEqual(code, 1, out)
        self.assertIn("already logged", out)
        self.assertIn("line 6", out)  # shifted down by the inserted listing line, measured AFTER the repair
        self.assertNotIn("line 5", out)

        hub_text = hub_path.read_text(encoding="utf-8")
        self.assertEqual(hub_text.count("Parts:"), 1)
        self.assertIn(
            "Parts: [Archive/PromotionLog-LessonsLearned-001-050.md]"
            "(Archive/PromotionLog-LessonsLearned-001-050.md)",
            hub_text,
        )

        dispositions = (self.planwise_dir / "upgrade-backups" / "manual-promotion-log-2026-04-01"
                        / "DISPOSITIONS.md")
        self.assertTrue(dispositions.is_file())
        self.assertIn("promotion-log-listing-repair", dispositions.read_text(encoding="utf-8"))


class TestPromotionLogDispositionsRow(PromotionLogTestCase):
    """B / info-to-fix: every promotion-log write into an existing family
    now goes through `lessons_migration.write_with_dispositions`, the same
    helper `lessons_changelog.py --append` already uses -- so the
    `manual-promotion-log-{date}` backup directory gets a DISPOSITIONS.md
    row, exactly as `manual-append-{date}` does. Before this fix,
    `_write_backed_up` called `write_changelog_plan` directly and never
    logged a row at all -- the sibling directory had no DISPOSITIONS.md."""

    def test_century_creation_logs_a_dispositions_row(self):
        hub_rel = "00-PromotionLog-LessonsLearned.md"
        self._seed_log(hub_rel)
        code, out = self._run(self._argv("LL-007", "a rule", "some/path.md", "--date", "2026-04-01"))
        self.assertEqual(code, 0, out)
        dispositions_path = (self.planwise_dir / "upgrade-backups" / "manual-promotion-log-2026-04-01"
                             / "DISPOSITIONS.md")
        self.assertTrue(dispositions_path.is_file())
        text = dispositions_path.read_text(encoding="utf-8")
        self.assertIn("promotion-log-century-create", text)
        self.assertIn("00-PromotionLog-LessonsLearned.md", text)


class TestPlainAppendTakesABackup(PromotionLogTestCase):
    """(fix): every promotion-log append into an ALREADY-EXISTING file now
    takes a backup, the same `manual-promotion-log-{date}` scheme
    `lessons_changelog.py --append` already uses -- first pre-image of the
    day wins, a later same-day write whose pre-image differs gets a
    numbered `.n.bak` sibling, and a DISPOSITIONS row is logged. Before
    this fix, an append into a file that already existed wrote bare
    (`write_text_preserving_newlines`, no backup helper at all) -- RR3's
    rehearsal call 3."""

    def test_append_into_an_existing_file_takes_a_backup(self):
        rel = "00-PromotionLog-LessonsLearned.md"
        path = self._seed_log(rel, rows=["| 2026-01-01 | LL-201 | a rule | some/path.md |"])
        before = path.read_bytes()
        code, out = self._run(self._argv("LL-202", "a different rule", "some/other.md", "--date", "2026-05-01"))
        self.assertEqual(code, 0, out)
        backup_path = (self.planwise_dir / "upgrade-backups" / "manual-promotion-log-2026-05-01"
                       / "lessons" / rel)
        self.assertTrue(backup_path.is_file())
        self.assertEqual(backup_path.read_bytes(), before)
        dispositions = (self.planwise_dir / "upgrade-backups" / "manual-promotion-log-2026-05-01"
                        / "DISPOSITIONS.md")
        self.assertTrue(dispositions.is_file())
        self.assertIn("promotion-log-append", dispositions.read_text(encoding="utf-8"))

    def test_a_second_same_day_append_with_a_different_pre_image_gets_a_numbered_sibling(self):
        rel = "00-PromotionLog-LessonsLearned.md"
        path = self._seed_log(rel, rows=["| 2026-01-01 | LL-201 | a rule | some/path.md |"])
        first_before = path.read_bytes()
        code, out = self._run(self._argv("LL-202", "a different rule", "some/other.md", "--date", "2026-05-01"))
        self.assertEqual(code, 0, out)
        second_before = path.read_bytes()
        self.assertNotEqual(second_before, first_before)  # the file grew after the first append
        code, out = self._run(self._argv("LL-203", "yet another rule", "some/third.md", "--date", "2026-05-01"))
        self.assertEqual(code, 0, out)
        backup_dir = self.planwise_dir / "upgrade-backups" / "manual-promotion-log-2026-05-01" / "lessons"
        self.assertEqual((backup_dir / rel).read_bytes(), first_before)  # first pre-image wins, kept
        sibling_backup = backup_dir / f"{rel}.1.bak"
        self.assertTrue(sibling_backup.is_file())
        self.assertEqual(sibling_backup.read_bytes(), second_before)


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
