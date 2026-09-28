#!/usr/bin/env python3
"""Tests for lessons_changelog.py's guarded `--append`/`--split` writer:
newest-first entry numbering that never renumbers an existing entry
(BB-402), over-budget append spilling into the `-Archive-{YYYY}` part and,
beyond the page cap, `-Part-NN` continuations, `--split`'s no-op-within-
budget and re-pack-with-backups paths, and the foreign-content refusal.

The review fix round adds: the one-time renumber of an unstable family and
the `--append` refusal on one; backups, write order and rollback for every
multi-file write; per-file BOM and newline preservation with untouched
files left byte-identical; the `--append` text guards; `--date`
validation; and the strict archive glob.

Every fixture is built with `write_bytes`, never `write_text`, so a CRLF
fixture stays CRLF until the code under test rewrites it (Archive/LL-149).
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lessons_changelog
import lessons_migration
import migrate_backlog_support
from lessons_changelog import main

CONFIG_YAML_FIXTURE = (
    b'project:\n'
    b'  name: "LessonsChangelogFixtureProject"\n'
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

INDEX_NAME = "00-Index-LessonsLearned.md"
MAIN_NAME = "00-Changelog-LessonsLearned.md"
ARCHIVE_2026 = "00-Changelog-LessonsLearned-Archive-2026.md"
ARCHIVE_PART_02 = "00-Changelog-LessonsLearned-Archive-2026-Part-02.md"
BACKLINK = f"[← {INDEX_NAME}]({INDEX_NAME})"
FILLER = "Lorem ipsum filler text describing a fixture entry body in full. " * 90  # ~4.6 KB


def _entry_block(n: int, body: str, nl: str = "\n") -> str:
    return f"## Entry {n}{nl}{nl}{body}{nl}{nl}"


def _main_text(entries: list, nl: str = "\n", pointer: str | None = None) -> str:
    """`entries` newest-first: [(n, body), ...]."""
    text = f"{BACKLINK}{nl}{nl}" + "".join(_entry_block(n, b, nl) for n, b in entries)
    if pointer:
        text += f"Older entries: [{pointer}]({pointer}){nl}"
    return text


class LessonsChangelogTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.planwise_dir = self.tmp_path / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        (self.lessons_dir / "Archive").mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_bytes(CONFIG_YAML_FIXTURE)

    def _seed_main(self, entries: list = (), nl: str = "\n", pointer: str | None = None) -> Path:
        path = self.lessons_dir / MAIN_NAME
        path.write_bytes(_main_text(list(entries), nl, pointer).encode("utf-8"))
        return path

    def _seed_raw(self, name: str, text: str) -> Path:
        path = self.lessons_dir / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def _run(self, argv: list) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["--config", str(self.config_path)] + argv)
        return code, out.getvalue()


class TestFirstEntryOnOpenerOnlyFile(LessonsChangelogTestCase):
    def test_append_to_opener_only_file(self):
        self._seed_main([])
        code, out = self._run(["--append", "The very first note."])
        self.assertEqual(code, 0, out)
        text = (self.lessons_dir / MAIN_NAME).read_text(encoding="utf-8")
        self.assertIn("## Entry 1", text)
        self.assertIn("The very first note.", text)
        self.assertTrue(text.startswith(BACKLINK))


class TestEntryNumberingNewestFirst(LessonsChangelogTestCase):
    def test_second_append_is_entry_two_above_entry_one(self):
        self._seed_main([])
        code, _out = self._run(["--append", "First note."])
        self.assertEqual(code, 0)
        code, _out = self._run(["--append", "Second note."])
        self.assertEqual(code, 0)
        text = (self.lessons_dir / MAIN_NAME).read_text(encoding="utf-8")
        self.assertLess(text.index("## Entry 2"), text.index("## Entry 1"))
        self.assertIn("Second note.", text)
        self.assertIn("First note.", text)

    def test_second_append_leaves_entry_one_heading_byte_identical(self):
        self._seed_main([])
        self._run(["--append", "First note."])
        before = (self.lessons_dir / MAIN_NAME).read_bytes()
        entry_one_start = before.index(b"## Entry 1")
        entry_one_before = before[entry_one_start:]
        self._run(["--append", "Second note."])
        after = (self.lessons_dir / MAIN_NAME).read_bytes()
        entry_one_after = after[after.index(b"## Entry 1"):]
        self.assertEqual(entry_one_before, entry_one_after)


class TestOverBudgetAppendSpillsToArchive(LessonsChangelogTestCase):
    def setUp(self):
        super().setUp()
        # 30 entries, oldest last (lowest number), ~4.6 KB each -> well over
        # both READ_TOKEN_WARN (main) and READ_PAGE_CAP_TOKENS (one archive part).
        entries = [(n, FILLER) for n in range(30, 0, -1)]
        self._seed_main(entries)

    def test_moves_oldest_entries_into_archive_linked_both_ways(self):
        code, out = self._run(["--append", "A small new note.", "--date", "2026-01-15"])
        self.assertEqual(code, 0, out)
        main_text = (self.lessons_dir / MAIN_NAME).read_text(encoding="utf-8")
        self.assertIn(f"Older entries: [{ARCHIVE_2026}]({ARCHIVE_2026})", main_text)
        archive_path = self.lessons_dir / ARCHIVE_2026
        self.assertTrue(archive_path.is_file())
        archive_text = archive_path.read_text(encoding="utf-8")
        self.assertIn(f"[← {MAIN_NAME}]({MAIN_NAME})", archive_text)
        self.assertIn(BACKLINK, archive_text)

    def test_spills_into_part_02_beyond_the_page_cap(self):
        code, out = self._run(["--append", "A small new note.", "--date", "2026-01-15"])
        self.assertEqual(code, 0, out)
        part2 = self.lessons_dir / ARCHIVE_PART_02
        self.assertTrue(part2.is_file(), "expected the archive to spill into a Part-02 file")
        part2_text = part2.read_text(encoding="utf-8")
        self.assertIn(f"[← {ARCHIVE_2026}]({ARCHIVE_2026})", part2_text)

    def test_no_existing_entry_heading_is_renumbered(self):
        before_headings = {
            line for line in _main_text([(n, FILLER) for n in range(30, 0, -1)]).split("\n")
            if line.startswith("## Entry")
        }
        self._run(["--append", "A small new note.", "--date", "2026-01-15"])
        after_text = ""
        for name in (MAIN_NAME, ARCHIVE_2026, ARCHIVE_PART_02):
            p = self.lessons_dir / name
            if p.is_file():
                after_text += p.read_text(encoding="utf-8")
        for heading in before_headings:
            self.assertIn(heading, after_text)


class TestSplit(LessonsChangelogTestCase):
    def test_no_op_within_budget(self):
        self._seed_main([(2, "Second."), (1, "First.")])
        before = (self.lessons_dir / MAIN_NAME).read_bytes()
        code, out = self._run(["--split"])
        self.assertEqual(code, 0, out)
        self.assertIn("within budget", out)
        after = (self.lessons_dir / MAIN_NAME).read_bytes()
        self.assertEqual(before, after)

    def test_reparts_over_budget_with_backups_and_dispositions(self):
        entries = [(n, FILLER) for n in range(30, 0, -1)]
        self._seed_main(entries)
        before = (self.lessons_dir / MAIN_NAME).read_bytes()
        code, out = self._run(["--split", "--date", "2026-02-01"])
        self.assertEqual(code, 0, out)
        self.assertIn("WROTE", out)
        after = (self.lessons_dir / MAIN_NAME).read_bytes()
        self.assertNotEqual(before, after)
        archive_path = self.lessons_dir / ARCHIVE_2026
        self.assertTrue(archive_path.is_file())
        backup_dir = self.planwise_dir / "upgrade-backups" / "manual-split-2026-02-01" / "lessons"
        backed_up_main = backup_dir / MAIN_NAME
        self.assertTrue(backed_up_main.is_file())
        self.assertEqual(backed_up_main.read_bytes(), before)
        dispositions = backup_dir.parent / "DISPOSITIONS.md"
        self.assertTrue(dispositions.is_file())
        self.assertIn(MAIN_NAME, dispositions.read_text(encoding="utf-8"))

    def test_rerun_after_split_is_a_noop(self):
        entries = [(n, FILLER) for n in range(30, 0, -1)]
        self._seed_main(entries)
        code, out = self._run(["--split", "--date", "2026-02-01"])
        self.assertEqual(code, 0, out)
        self.assertIn("WROTE", out)
        code, out = self._run(["--split", "--date", "2026-02-02"])
        self.assertEqual(code, 0, out)
        self.assertIn("within budget", out)


class TestForeignTextRefused(LessonsChangelogTestCase):
    def test_stray_line_outside_any_entry_is_refused_naming_the_line(self):
        text = f"{BACKLINK}\n\nSome stray paragraph nobody wrapped in an entry.\n\n" + _entry_block(1, "Body.")
        self._seed_raw(MAIN_NAME, text)
        code, out = self._run(["--append", "New note."])
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn(MAIN_NAME, out)
        self.assertIn("line 3", out)

    def test_clean_file_is_not_refused(self):
        self._seed_main([(1, "Body.")])
        code, out = self._run(["--append", "New note."])
        self.assertEqual(code, 0, out)


class TestCRLFPreserved(LessonsChangelogTestCase):
    def test_crlf_file_stays_crlf_after_append(self):
        text = _main_text([(1, "First.")], nl="\r\n")
        (self.lessons_dir / MAIN_NAME).write_bytes(text.encode("utf-8"))
        code, out = self._run(["--append", "Second."])
        self.assertEqual(code, 0, out)
        raw = (self.lessons_dir / MAIN_NAME).read_bytes()
        # Exact bytes: a `\r\r\n` rewrite would still satisfy a count comparison.
        self.assertEqual(raw, _main_text([(2, "Second."), (1, "First.")], nl="\r\n").encode("utf-8"))


class TestDryRun(LessonsChangelogTestCase):
    def test_dry_run_writes_nothing(self):
        path = self._seed_main([(1, "First.")])
        before = path.read_bytes()
        code, out = self._run(["--append", "Second.", "--dry-run"])
        self.assertEqual(code, 0, out)
        after = path.read_bytes()
        self.assertEqual(before, after)


class TestAppendFile(LessonsChangelogTestCase):
    def test_append_file_reads_text_from_disk(self):
        self._seed_main([])
        note_path = self.tmp_path / "note.txt"
        note_path.write_text("A note supplied via --append-file.\n", encoding="utf-8")
        code, out = self._run(["--append-file", str(note_path)])
        self.assertEqual(code, 0, out)
        text = (self.lessons_dir / MAIN_NAME).read_text(encoding="utf-8")
        self.assertIn("A note supplied via --append-file.", text)


# ---------------------------------------------------------------------------
# Review fix round
# ---------------------------------------------------------------------------

ARCHIVE_BACK = f"[← {MAIN_NAME}]({MAIN_NAME})"
PART_BACK = f"[← {ARCHIVE_2026}]({ARCHIVE_2026})"
POINTER = f"Older entries: [{ARCHIVE_2026}]({ARCHIVE_2026})"
ARCHIVE_PART_03 = "00-Changelog-LessonsLearned-Archive-2026-Part-03.md"


def _family_file(heads: list, entries: list, nl: str = "\n", pointer: str | None = None,
                 bom: bool = False) -> bytes:
    """One family file by bytes. `entries` newest first: [(n, suffix, body)]."""
    text = "".join(f"{h}{nl}{nl}" for h in heads)
    text += "".join(f"## Entry {n}{s}{nl}{nl}{b.replace(chr(10), nl)}{nl}{nl}" for n, s, b in entries)
    if pointer:
        text += f"{pointer}{nl}"
    return (("﻿" if bom else "") + text).encode("utf-8")


def _marked(n: int) -> str:
    return f"{FILLER}marker-{n:03d}."


# The live project's changelog shape: a max + 1 entry (16) above the
# migrator's positional entries (1 = newest .. 15), a non-Entry heading
# inside entry 15's body, and an archive that restarts at Entry 1. CRLF.
LIVE_MAIN = (
    [(16, " — 2026-09-27", "Newest note, numbered max + 1 by a writer that assumed stable numbers."),
     (1, " — 2026-09-26", "The migrator's newest entry, numbered 1 by position."),
     (2, " — Hand-written index sections retired at cutover (2026-09-26)",
      "Relocated sections.\n\n### Quick Reference\n\nAdapted text.")]
    + [(n, f" — 2026-08-{n:02d}", f"Entry body {n}.") for n in range(3, 15)]
    + [(15, " — 2026-06-24", "Oldest main entry.\n\n## Drift Record\n\nCounter drift note.")]
)
LIVE_ARCHIVE = [(1, " — 2026-08-17", "The archive's only entry, numbered 1 again.")]


def _renumber(entries: list, top: int) -> list:
    return [(top - i, s, b) for i, (_n, s, b) in enumerate(entries)]


def _family_files(lessons_dir: Path) -> list:
    return sorted(lessons_dir.glob("00-Changelog-LessonsLearned*.md"))


def _family_text(lessons_dir: Path) -> str:
    return "".join(p.read_bytes().decode("utf-8") for p in _family_files(lessons_dir))


def _failing_replace(fail_on: int):
    calls = {"n": 0}

    def fake(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_on:
            raise PermissionError(13, "simulated: the file is locked", str(dst))
        os.replace(src, dst)
    return fake


class TestUnstableNumbering(LessonsChangelogTestCase):
    def _seed_live(self) -> tuple:
        main_bytes = _family_file([BACKLINK], LIVE_MAIN, "\r\n", POINTER)
        archive_bytes = _family_file([ARCHIVE_BACK, BACKLINK], LIVE_ARCHIVE, "\r\n")
        (self.lessons_dir / MAIN_NAME).write_bytes(main_bytes)
        (self.lessons_dir / ARCHIVE_2026).write_bytes(archive_bytes)
        return main_bytes, archive_bytes

    def test_append_refuses_an_unstable_family_naming_split(self):
        main_bytes, archive_bytes = self._seed_live()
        code, out = self._run(["--append", "A note that must not extend a mixed scheme."])
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSED", out)
        self.assertIn("--split", out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), main_bytes)
        self.assertEqual((self.lessons_dir / ARCHIVE_2026).read_bytes(), archive_bytes)

    def test_split_renumbers_the_live_shape_once_by_position(self):
        main_bytes, archive_bytes = self._seed_live()
        code, out = self._run(["--split", "--date", "2026-09-27"])
        self.assertEqual(code, 0, out)
        self.assertIn("RENUMBERED: 17", out)
        expected_main = _family_file([BACKLINK], _renumber(LIVE_MAIN, 17), "\r\n", POINTER)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), expected_main)
        # The archive's only entry is already Entry 1 by position: untouched.
        self.assertEqual((self.lessons_dir / ARCHIVE_2026).read_bytes(), archive_bytes)
        backup = self.planwise_dir / "upgrade-backups" / "manual-split-2026-09-27" / "lessons" / MAIN_NAME
        self.assertEqual(backup.read_bytes(), main_bytes)

        code, out = self._run(["--split", "--date", "2026-09-27"])
        self.assertEqual(code, 0, out)
        self.assertIn("within budget", out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), expected_main)

        code, out = self._run(["--append", "Next note."])
        self.assertEqual(code, 0, out)
        text = (self.lessons_dir / MAIN_NAME).read_bytes().decode("utf-8")
        self.assertTrue(text.startswith(f"{BACKLINK}\r\n\r\n## Entry 18\r\n\r\nNext note.\r\n\r\n## Entry 17 — "))

    def test_renumber_keeps_the_bom_and_every_other_byte(self):
        entries = [(1, "", "Newest."), (2, " — title", "Oldest.")]
        (self.lessons_dir / MAIN_NAME).write_bytes(_family_file([BACKLINK], entries, "\r\n", bom=True))
        code, out = self._run(["--split"])
        self.assertEqual(code, 0, out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(),
                         _family_file([BACKLINK], _renumber(entries, 2), "\r\n", bom=True))

    def test_a_stable_family_with_gaps_is_never_renumbered(self):
        main_bytes = _family_file([BACKLINK], [(9, "", "Newest."), (5, "", "Middle.")], pointer=POINTER)
        archive_bytes = _family_file([ARCHIVE_BACK, BACKLINK], [(2, "", "Oldest.")])
        (self.lessons_dir / MAIN_NAME).write_bytes(main_bytes)
        (self.lessons_dir / ARCHIVE_2026).write_bytes(archive_bytes)
        code, out = self._run(["--split"])
        self.assertEqual(code, 0, out)
        self.assertIn("within budget", out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), main_bytes)
        self.assertEqual((self.lessons_dir / ARCHIVE_2026).read_bytes(), archive_bytes)


class TestMultiFileWriteSafety(LessonsChangelogTestCase):
    """A write that moves entries between files: backups before the first
    replace, destinations before sources, rollback on failure, no traceback."""

    def setUp(self):
        super().setUp()
        self.before = _family_file([BACKLINK], [(n, "", _marked(n)) for n in range(30, 0, -1)])
        (self.lessons_dir / MAIN_NAME).write_bytes(self.before)

    def _backup(self, kind: str, date: str) -> Path:
        return self.planwise_dir / "upgrade-backups" / f"{kind}-{date}" / "lessons" / MAIN_NAME

    def test_append_second_replace_failure_rolls_back_without_a_traceback(self):
        with mock.patch.object(migrate_backlog_support, "_replace", _failing_replace(2)):
            code, out = self._run(["--append", "A new note.", "--date", "2026-03-03"])
        self.assertEqual(code, 1, out)
        self.assertIn("REFUSED", out)
        self.assertIn("manual-append-2026-03-03", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(_family_files(self.lessons_dir), [self.lessons_dir / MAIN_NAME])
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), self.before)
        self.assertEqual(self._backup("manual-append", "2026-03-03").read_bytes(), self.before)

    def test_failed_restore_leaves_entries_duplicated_never_missing(self):
        def restore_fails(report, _pre, _created, fix):
            report.state, report.fix = "write_failed", fix
            report.detail += "\nrestore failed (simulated)"
        with mock.patch.object(migrate_backlog_support, "_replace", _failing_replace(2)), \
                mock.patch.object(lessons_migration, "_write_failed", restore_fails):
            code, out = self._run(["--append", "A new note.", "--date", "2026-03-03"])
        self.assertEqual(code, 1, out)
        family = _family_text(self.lessons_dir)
        for n in range(1, 31):
            self.assertIn(f"marker-{n:03d}.", family, n)
        self.assertEqual(self._backup("manual-append", "2026-03-03").read_bytes(), self.before)

    def test_same_day_rerun_keeps_the_first_pre_image(self):
        with mock.patch.object(migrate_backlog_support, "_replace", _failing_replace(2)):
            code, out = self._run(["--split", "--date", "2026-03-04"])
        self.assertEqual(code, 1, out)
        backup = self._backup("manual-split", "2026-03-04")
        self.assertEqual(backup.read_bytes(), self.before)
        edited = self.before.replace(b"marker-030.", b"marker-030 edited.")
        (self.lessons_dir / MAIN_NAME).write_bytes(edited)

        code, out = self._run(["--split", "--date", "2026-03-04"])
        self.assertEqual(code, 0, out)
        self.assertEqual(backup.read_bytes(), self.before)  # the first pre-image wins
        self.assertEqual(backup.with_name(f"{MAIN_NAME}.1.bak").read_bytes(), edited)
        log = (backup.parent.parent / "DISPOSITIONS.md").read_text(encoding="utf-8")
        self.assertIn("kept, not overwritten", log)


class TestOrphanParts(LessonsChangelogTestCase):
    def _seed_gap(self):
        main = _family_file([BACKLINK], [(n, "", _marked(n)) for n in range(40, 10, -1)], pointer=POINTER)
        archive = _family_file([ARCHIVE_BACK, BACKLINK], [(n, "", _marked(n)) for n in range(10, 5, -1)])
        part3 = _family_file([PART_BACK], [(n, "", _marked(n)) for n in range(5, 0, -1)])
        (self.lessons_dir / MAIN_NAME).write_bytes(main)
        (self.lessons_dir / ARCHIVE_2026).write_bytes(archive)
        (self.lessons_dir / ARCHIVE_PART_03).write_bytes(part3)
        return part3

    def test_locate_finds_every_part_after_a_gap(self):
        self._seed_gap()
        files, year = lessons_changelog._locate_family_files(self.lessons_dir / INDEX_NAME, MAIN_NAME)
        self.assertEqual(year, "2026")
        self.assertEqual([p.name for p in files], [MAIN_NAME, ARCHIVE_2026, ARCHIVE_PART_03])

    def test_split_keeps_every_entry_of_an_orphan_part_and_logs_it_honestly(self):
        part3 = self._seed_gap()
        code, out = self._run(["--split", "--date", "2026-04-04"])
        self.assertEqual(code, 0, out)
        family = _family_text(self.lessons_dir)
        for n in range(1, 41):
            self.assertEqual(family.count(f"marker-{n:03d}."), 1, n)
        backup_dir = self.planwise_dir / "upgrade-backups" / "manual-split-2026-04-04" / "lessons"
        self.assertEqual((backup_dir / ARCHIVE_PART_03).read_bytes(), part3)
        rows = [ln for ln in (backup_dir.parent / "DISPOSITIONS.md").read_text(encoding="utf-8").splitlines()
                if ARCHIVE_PART_03 in ln]
        self.assertTrue(rows)
        self.assertTrue(all("created" not in ln for ln in rows), rows)


class TestConvergence(LessonsChangelogTestCase):
    def test_a_single_oversized_entry_is_left_alone(self):
        before = _family_file([BACKLINK], [(1, "", "x" * 70_000)])
        (self.lessons_dir / MAIN_NAME).write_bytes(before)
        code, out = self._run(["--split"])
        self.assertEqual(code, 0, out)
        self.assertIn("already split as far as it can be", out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(), before)
        self.assertFalse((self.planwise_dir / "upgrade-backups").exists())


class TestAppendGuards(LessonsChangelogTestCase):
    def test_unfenced_entry_heading_is_refused_naming_the_line(self):
        path = self._seed_main([(1, "First.")])
        before = path.read_bytes()
        code, out = self._run(["--append", "note\n## Entry 3\nmore"])
        self.assertEqual(code, 1, out)
        self.assertIn("line 2", out)
        self.assertIn("## Entry 3", out)
        self.assertEqual(path.read_bytes(), before)

    def test_unbalanced_fence_is_refused_naming_the_line(self):
        path = self._seed_main([(1, "First.")])
        before = path.read_bytes()
        code, out = self._run(["--append", "intro\n```python\nprint('never closed')"])
        self.assertEqual(code, 1, out)
        self.assertIn("line 2", out)
        self.assertIn("never closes", out)
        self.assertEqual(path.read_bytes(), before)

    def test_a_fenced_entry_heading_is_accepted(self):
        self._seed_main([(1, "First.")])
        code, out = self._run(["--append", "intro\n```markdown\n## Entry 9\n```"])
        self.assertEqual(code, 0, out)
        self.assertIn("```markdown\n## Entry 9\n```", (self.lessons_dir / MAIN_NAME).read_text(encoding="utf-8"))


class TestEncodingPerFile(LessonsChangelogTestCase):
    def test_crlf_main_with_lf_parts_leaves_untouched_parts_byte_identical(self):
        main_entries = [(n, "", _marked(n)) for n in range(25, 16, -1)]
        main = _family_file([BACKLINK], main_entries, "\r\n", POINTER)
        # The layout's own packing: 11 filler entries per archive part (measured).
        archive = _family_file([ARCHIVE_BACK, BACKLINK], [(n, "", _marked(n)) for n in range(16, 5, -1)])
        part2 = _family_file([PART_BACK], [(n, "", _marked(n)) for n in range(5, 0, -1)])
        (self.lessons_dir / MAIN_NAME).write_bytes(main)
        (self.lessons_dir / ARCHIVE_2026).write_bytes(archive)
        (self.lessons_dir / ARCHIVE_PART_02).write_bytes(part2)
        code, out = self._run(["--append", "Small."])
        self.assertEqual(code, 0, out)
        self.assertEqual((self.lessons_dir / ARCHIVE_2026).read_bytes(), archive)
        self.assertEqual((self.lessons_dir / ARCHIVE_PART_02).read_bytes(), part2)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(),
                         _family_file([BACKLINK], [(26, "", "Small.")] + main_entries, "\r\n", POINTER))

    def test_bom_is_kept_on_append(self):
        (self.lessons_dir / MAIN_NAME).write_bytes(_family_file([BACKLINK], [(1, "", "First.")], bom=True))
        code, out = self._run(["--append", "Second."])
        self.assertEqual(code, 0, out)
        self.assertEqual((self.lessons_dir / MAIN_NAME).read_bytes(),
                         _family_file([BACKLINK], [(2, "", "Second."), (1, "", "First.")], bom=True))


class TestCandidates(LessonsChangelogTestCase):
    def test_archive_glob_ignores_a_name_that_is_not_exactly_a_year(self):
        (self.lessons_dir / ARCHIVE_2026).write_bytes(b"x")
        (self.lessons_dir / "00-Changelog-LessonsLearned-Archive-2026_bak.md").write_bytes(b"x")
        found = lessons_changelog._existing_archive_main(self.lessons_dir, Path(MAIN_NAME).stem)
        self.assertEqual(found, self.lessons_dir / ARCHIVE_2026)

    def test_malformed_date_is_refused(self):
        path = self._seed_main([(1, "First.")])
        before = path.read_bytes()
        for bad in ("2026-13-45", "26-1-1", "../escape"):
            code, out = self._run(["--append", "Second.", "--date", bad])
            self.assertEqual(code, 1, (bad, out))
            self.assertIn("is not YYYY-MM-DD", out)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
