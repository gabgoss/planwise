#!/usr/bin/env python3
"""Unit tests for flip_lesson_status.py's frontmatter status-flip and its
guards (D25: repurposed to flip a lesson FILE's frontmatter `status:`
directly, never opening the index).

The load-bearing property is still not the rewrite -- it is the REFUSALS:
an id claimed by zero or more than one lesson file is refused outright, a
file already at the target status is skipped rather than rewritten, a
landed status (`rule` / `applied`) is never downgraded even when the
caller's map says so, and a file with no parseable `status:` line inside
its frontmatter is reported rather than silently skipped.

18 of these tests are ported from the pre-D25 index-row suite, one test
per original name and property, re-targeted at a lesson-file fixture.
`TestHeaderBumpMachineryAbsent` (formerly `TestLastUpdatedHeaderBump`)
keeps one retargeted port: it pins that the header-bump helper and its
regexes are gone, and that a real flip leaves an arbitrary body line
untouched. The port's other four original cases duplicated a property
already pinned elsewhere (`TestNeverDowngrade`, `TestIdempotentSkip`,
`TestUnknownFlagRefused`) or asserted nothing beyond a basic flip, so they
were deleted rather than kept as dead weight.
`TestBB210OrphanedStatus` and `TestStatusWordInBodyNeverTouched` are new,
per Step 5's explicit additions (the fifth status BB-210 added, and the
two D25-specific write-discipline cases).
`TestF5IndexNeverTouchedAndRegenerateCommandPrinted` is new per the F5
design-review remediation: it pins that the lessons index file stays
byte-identical after any flip, and that the regenerate-command hint
prints only after a real, non-dry-run change. Set-equality (`VALID` ==
config's declared set) is already covered by
`test_lesson_statuses_config.py` and is not repeated here.

Every fixture is built with `write_bytes`, never `write_text`.

Run with:  python -m pytest tests/test_flip_lesson_status.py -q
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from flip_lesson_status import main

CONFIG_YAML_FIXTURE = (
    b'project:\n'
    b'  name: "FlipLessonStatusFixtureProject"\n'
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


class FlipLessonStatusTestCase(unittest.TestCase):
    """Base fixture: an isolated temp planwise tree (config.yaml +
    LessonsLearned/ + Archive/) per test, cleaned up automatically."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.planwise_dir = self.tmp_path / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.archive_dir = self.lessons_dir / "Archive"
        self.lessons_dir.mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_bytes(CONFIG_YAML_FIXTURE)

    def write_lesson(
        self, number: int, status: str, *, directory=None, title: str | None = None,
        crlf: bool = False, body_extra: str = "", suffix: str = "",
    ) -> Path:
        """Write one lesson-file fixture, byte-for-byte (never write_text,
        which would normalize line endings and defeat the CRLF tests)."""
        target_dir = directory if directory is not None else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        lid = f"LL-{number:03d}"
        title = title or "A fixture lesson"
        text = (
            "---\n"
            f"id: {lid}\n"
            f"title: {title}\n"
            "category: process\n"
            "severity: medium\n"
            "language: [python]\n"
            "technology: [claude-code]\n"
            "domain: [PROC]\n"
            "source: fixture\n"
            f"status: {status}\n"
            "---\n\n"
            f"# {lid}: {title}\n"
            f"{body_extra}"
        )
        if crlf:
            text = text.replace("\n", "\r\n")
        path = target_dir / f"LL-{number:03d}-PROC-Fixture{number}{suffix}.md"
        path.write_bytes(text.encode("utf-8"))
        return path

    def _write_map(self, content: str) -> Path:
        path = self.tmp_path / "map.txt"
        path.write_bytes(content.encode("utf-8"))
        return path

    def _argv(self, map_path: Path, *extra: str) -> list[str]:
        return ["--config", str(self.config_path), str(map_path), *extra]

    def _run_main(self, argv: list[str]):
        """Invoke main() with an injected sys.argv, capturing stdout."""
        old_argv = sys.argv
        sys.argv = ["flip_lesson_status.py"] + argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = main()
        finally:
            sys.argv = old_argv
        return code, out.getvalue()


class TestNeverDowngrade(FlipLessonStatusTestCase):
    """Case 1 (EI Part-2 §3.1): a landed file must never be downgraded, even
    when the caller's map explicitly asks for it. If the guard were
    removed, this test would fail (the file would silently rewrite to
    `documented`, exit 0, no REFUSED message)."""

    def test_never_downgrade_landed_row_is_refused(self):
        target = self.write_lesson(1, "rule")
        before = target.read_bytes()
        map_file = self._write_map("LL-001: documented\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("rule", out)
        self.assertIn("documented", out)
        self.assertEqual(target.read_bytes(), before, "file must be byte-unchanged on refusal")


class TestIdempotentSkip(FlipLessonStatusTestCase):
    """Case 2: a file already at the target status is skipped, not rewritten."""

    def test_row_already_at_target_is_skipped_not_rewritten(self):
        target = self.write_lesson(2, "promoted")
        before = target.read_bytes()
        map_file = self._write_map("LL-002: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn("already promoted", out)
        self.assertEqual(target.read_bytes(), before)


class TestQuotedStatusUnquoted(FlipLessonStatusTestCase):
    """Code-review fix 3: `status: "rule"` (a quoted scalar) must read as
    the same value as an unquoted `status: rule` -- both for the LANDED
    refusal and for the idempotent-skip comparison. Before the fix, the
    captured value kept its literal quote characters, so `'"rule"' in
    LANDED` was False and the downgrade refusal never fired."""

    def test_quoted_landed_status_downgrade_is_still_refused(self):
        target = self.write_lesson(1, '"rule"')
        before = target.read_bytes()
        map_file = self._write_map("LL-001: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("rule", out)
        self.assertEqual(target.read_bytes(), before, "file must be byte-unchanged on refusal")

    def test_quoted_status_equal_to_target_is_skipped(self):
        target = self.write_lesson(2, "'promoted'")
        before = target.read_bytes()
        map_file = self._write_map("LL-002: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn("already promoted", out)
        self.assertEqual(target.read_bytes(), before)


class TestUnmatchedId(FlipLessonStatusTestCase):
    """Case 3: a mapped id with zero matching lesson files is refused and
    reported, not ignored -- D25 folds "not found" into the same 0-or-more-
    than-1-file refusal as an ambiguous match."""

    def test_unmatched_id_is_reported_and_exit_is_nonzero(self):
        self.write_lesson(3, "documented")
        map_file = self._write_map("LL-999: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("no lesson file found", out)
        self.assertIn("LL-999", out)


class TestUnparseableStatusCell(FlipLessonStatusTestCase):
    """Case 4: a lesson file matched by id but whose frontmatter has no
    parseable `status:` line is reported, not silently skipped, and left
    untouched."""

    def test_malformed_status_cell_is_reported_and_row_untouched(self):
        lid = "LL-004"
        text = (
            "---\n"
            f"id: {lid}\n"
            "title: A lesson with a bad tail\n"
            "category: process\n"
            "severity: medium\n"
            "language: [python]\n"
            "technology: [claude-code]\n"
            "domain: [PROC]\n"
            "source: fixture\n"
            "---\n\n# lesson\n"
        )
        path = self.lessons_dir / "LL-004-PROC-Fixture4.md"
        path.write_bytes(text.encode("utf-8"))
        before = path.read_bytes()
        map_file = self._write_map("LL-004: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("no parseable", out)
        self.assertIn("check by hand", out)
        self.assertEqual(path.read_bytes(), before)


class TestFinalCellOnlyRewrite(FlipLessonStatusTestCase):
    """Case 5: only the frontmatter status word is rewritten, even when the
    Title prose contains the plain-text words "documented" and "promoted"
    -- the frontmatter bounds restrict the match, so mid-file prose is
    never mistaken for the status line."""

    def test_title_containing_status_words_is_left_alone(self):
        title = "Docs said documented but the code still says promoted"
        target = self.write_lesson(5, "promoted", title=title)
        map_file = self._write_map("LL-005: rule\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        rewritten = target.read_text(encoding="utf-8")
        self.assertIn(title, rewritten, "Title prose must survive verbatim")
        self.assertIn(f"title: {title}", rewritten, "the title field is untouched")
        self.assertIn("status: rule\n", rewritten, "only the status field changed")


class TestCleanDryRun(FlipLessonStatusTestCase):
    """Case 6: a dry-run over already-correct files reports a reason per id
    and changes nothing on disk."""

    def test_dry_run_over_already_correct_index_changes_nothing(self):
        first = self.write_lesson(6, "documented")
        second = self.write_lesson(7, "rule")
        first_before, second_before = first.read_bytes(), second.read_bytes()
        map_file = self._write_map("LL-006: documented\nLL-007: rule\n")

        code, out = self._run_main(self._argv(map_file, "--dry-run"))

        self.assertEqual(code, 0)
        self.assertIn("would change: 0", out)
        self.assertIn("already documented", out)
        self.assertIn("already rule", out)
        self.assertEqual(first.read_bytes(), first_before)
        self.assertEqual(second.read_bytes(), second_before)


class TestMapFileParseErrors(FlipLessonStatusTestCase):
    """Case 7: a malformed map-file line raises SystemExit naming the
    offending file:line, for each of the three malformed forms."""

    def test_bad_lesson_id_form_raises_systemexit(self):
        map_file = self._write_map("NOT-AN-ID: promoted\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main(self._argv(map_file))

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("bad lesson id", message)

    def test_bad_status_value_raises_systemexit(self):
        map_file = self._write_map("LL-009: retired\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main(self._argv(map_file))

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("retired", message)

    def test_missing_colon_raises_systemexit(self):
        map_file = self._write_map("LL-010 promoted\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main(self._argv(map_file))

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("expected 'LL-NNN: status'", message)


class TestLineEndingsPreserved(FlipLessonStatusTestCase):
    """Case 8: the flip must not translate a lesson file's line endings.
    Both directions are asserted because each fails on only one platform:
    the LF case fails on Windows, the CRLF case fails on POSIX. The CRLF
    case also asserts the flip actually happened (a specific byte
    replacement), not just that CRLF survived -- a flip that silently did
    nothing would pass a CRLF-only check with zero information."""

    def test_lf_index_stays_lf_and_only_the_status_word_changes(self):
        target = self.write_lesson(20, "documented", crlf=False)
        bystander = self.write_lesson(21, "rule", crlf=False)
        bystander_before = bystander.read_bytes()
        map_file = self._write_map("LL-020: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        content = target.read_bytes()
        self.assertNotIn(b"\r\n", content)
        self.assertIn(b"status: promoted\n", content)
        self.assertNotIn(b"status: documented", content)
        self.assertEqual(bystander.read_bytes(), bystander_before)

    def test_crlf_index_stays_crlf_and_only_the_status_word_changes(self):
        target = self.write_lesson(22, "documented", crlf=True)
        before = target.read_bytes()
        map_file = self._write_map("LL-022: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        after = target.read_bytes()
        self.assertEqual(after, before.replace(b"status: documented", b"status: promoted"))
        self.assertNotIn(b"\n", after.replace(b"\r\n", b""), "every line ending must stay CRLF")

    def test_untouched_rows_are_byte_identical_after_a_flip(self):
        self.write_lesson(23, "documented")
        bystander = self.write_lesson(24, "rule")
        bystander_before = bystander.read_bytes()
        map_file = self._write_map("LL-023: promoted\n")

        self._run_main(self._argv(map_file))

        self.assertEqual(bystander.read_bytes(), bystander_before)


class TestUnknownFlagRefused(FlipLessonStatusTestCase):
    """Case 9: a misspelled safety flag must abort, never silently write."""

    def test_misspelled_dry_run_aborts_without_writing(self):
        target = self.write_lesson(30, "documented")
        before = target.read_bytes()
        map_file = self._write_map("LL-030: promoted\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main(self._argv(map_file, "--dryrun"))

        self.assertIn("--dryrun", str(ctx.exception))
        self.assertIn("unknown option", str(ctx.exception))
        self.assertEqual(target.read_bytes(), before, "nothing may be written")

    def test_correctly_spelled_dry_run_still_works(self):
        target = self.write_lesson(31, "documented")
        before = target.read_bytes()
        map_file = self._write_map("LL-031: promoted\n")

        code, out = self._run_main(self._argv(map_file, "--dry-run"))

        self.assertEqual(code, 0)
        self.assertIn("would change: 1", out)
        self.assertEqual(target.read_bytes(), before)


class TestDuplicateIdRefused(FlipLessonStatusTestCase):
    """Case 10: an id claimed by two lesson FILES is refused, not flipped
    on either — the ambiguous match is itself the corruption signal."""

    def test_duplicate_rows_are_refused_and_left_untouched(self):
        first = self.write_lesson(40, "documented")
        second = self.write_lesson(40, "documented", suffix="-dup", directory=self.archive_dir)
        first_before, second_before = first.read_bytes(), second.read_bytes()
        map_file = self._write_map("LL-040: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("2 lesson files claim this id", out)
        self.assertEqual(first.read_bytes(), first_before)
        self.assertEqual(second.read_bytes(), second_before)


class TestStatusCellFormattingPreserved(FlipLessonStatusTestCase):
    """Case 11: the splice replaces the status WORD, not the whole line.
    Retargeted for D25: a table cell's bold markers / padding have no
    frontmatter equivalent, so these ports pin the closest true analogues
    in the frontmatter write path -- trailing content on the status line,
    and leading whitespace before the value -- both spliced back verbatim,
    exactly like the old table-cell splice."""

    def _write_raw(self, name: str, status_line: str) -> Path:
        text = (
            "---\n"
            "id: LL-050\n"
            "title: A lesson\n"
            "category: process\n"
            "severity: medium\n"
            "language: [python]\n"
            "technology: [claude-code]\n"
            "domain: [PROC]\n"
            "source: fixture\n"
            f"{status_line}\n"
            "---\n\n# lesson\n"
        )
        path = self.lessons_dir / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_bold_markers_survive_the_flip(self):
        path = self._write_raw("LL-050-PROC-Fixture50.md", "status: documented  # verified live")
        map_file = self._write_map("LL-050: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn(b"status: promoted  # verified live\n", path.read_bytes())

    def test_cell_padding_survives_the_flip(self):
        path = self._write_raw("LL-051-PROC-Fixture51.md", "status:    documented")
        map_file = self._write_map("LL-051: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn(b"status:    promoted\n", path.read_bytes())


class TestHeaderBumpMachineryAbsent(FlipLessonStatusTestCase):
    """D25 drops the Last-Updated header bump entirely: there is no index-
    level header for a per-file frontmatter flip to bump. This is the one
    retargeted port kept from the original five-test `TestLastUpdated
    HeaderBump` class -- it pins that the bump helper and its regexes are
    gone, and that a real flip leaves a body line it doesn't understand
    (something that could be mistaken for an old-style header stamp)
    exactly as written.

    The other four original cases are gone, not merely renamed: they
    duplicated a property already pinned elsewhere -- a dry-run leaves the
    file unchanged (`TestUnknownFlagRefused.
    test_correctly_spelled_dry_run_still_works`), a no-op skip leaves the
    file unchanged (`TestIdempotentSkip.
    test_row_already_at_target_is_skipped_not_rewritten`), a refused
    downgrade leaves the file unchanged (`TestNeverDowngrade.
    test_never_downgrade_landed_row_is_refused`) -- or asserted nothing
    beyond "a basic flip still works," which every other class in this
    module already exercises with a real status change."""

    DECOY_BODY = "**Last Updated:** 2020-01-01 (decoy body line, not a real index header)\n"

    def test_header_bump_helpers_absent_and_body_line_untouched(self):
        import flip_lesson_status

        self.assertFalse(
            hasattr(flip_lesson_status, "_bump_last_updated_header"),
            "D25 removes the header-bump helper entirely",
        )
        self.assertFalse(hasattr(flip_lesson_status, "HEADER_RE"))
        self.assertFalse(hasattr(flip_lesson_status, "TAIL_RE"))
        target = self.write_lesson(100, "documented", body_extra=self.DECOY_BODY)
        map_file = self._write_map("LL-100: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        content = target.read_text(encoding="utf-8")
        self.assertIn("status: promoted", content)
        self.assertIn(self.DECOY_BODY.strip(), content)


class TestBB210OrphanedStatus(FlipLessonStatusTestCase):
    """BB-210: `flip_lesson_status.VALID` gained `orphaned` (Task 1). These
    are the four acceptance criteria, "fixture index" read as "fixture
    lesson file" per D25. Set equality is already covered by
    test_lesson_statuses_config.py and is not repeated here."""

    def test_dry_run_orphaned_target_against_promoted_file_reports_the_change(self):
        self.write_lesson(200, "promoted")
        map_file = self._write_map("LL-200: orphaned\n")

        code, out = self._run_main(self._argv(map_file, "--dry-run"))

        self.assertEqual(code, 0)
        self.assertIn("would change: 1", out)
        self.assertIn("LL-200: promoted -> orphaned", out)

    def test_orphaned_file_flips_back_to_promoted(self):
        target = self.write_lesson(201, "orphaned")
        map_file = self._write_map("LL-201: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn("LL-201: orphaned -> promoted", out)
        self.assertIn(b"status: promoted", target.read_bytes())

    def test_rule_mapped_to_orphaned_is_refused(self):
        target = self.write_lesson(202, "rule")
        before = target.read_bytes()
        map_file = self._write_map("LL-202: orphaned\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("rule", out)
        self.assertIn("orphaned", out)
        self.assertEqual(target.read_bytes(), before)


class TestF5IndexNeverTouchedAndRegenerateCommandPrinted(FlipLessonStatusTestCase):
    """F5 remediation (design review BIR-S05-03-05): the two properties the
    retargeted TestLastUpdatedHeaderBump ports never pinned -- the lessons
    index file is byte-identical after any flip run, including a real
    flip, and the regenerate command prints only after a real, non-dry-run
    change (never on --dry-run, an all-skipped map, or an all-refused
    map)."""

    def _write_index_fixture(self) -> Path:
        index_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        index_path.write_bytes(b"Generated: 2026-01-01\n\n| ID | Title |\n|---|---|\n")
        return index_path

    def test_index_file_byte_identical_after_a_real_flip(self):
        index_path = self._write_index_fixture()
        before = index_path.read_bytes()
        self.write_lesson(300, "documented")
        map_file = self._write_map("LL-300: promoted\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertEqual(index_path.read_bytes(), before)

    def test_regenerate_command_prints_only_after_a_real_change(self):
        self._write_index_fixture()
        self.write_lesson(301, "documented")
        map_file = self._write_map("LL-301: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertIn("Regenerate the index:", out)
        self.assertIn("generate_lessons_index.py", out)
        self.assertIn(str(self.config_path), out)

    def test_regenerate_command_never_prints_on_dry_run(self):
        self._write_index_fixture()
        self.write_lesson(302, "documented")
        map_file = self._write_map("LL-302: promoted\n")

        code, out = self._run_main(self._argv(map_file, "--dry-run"))

        self.assertEqual(code, 0)
        self.assertNotIn("Regenerate the index", out)

    def test_regenerate_command_never_prints_on_all_skipped_map(self):
        self._write_index_fixture()
        self.write_lesson(303, "promoted")
        map_file = self._write_map("LL-303: promoted\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assertNotIn("Regenerate the index", out)

    def test_regenerate_command_never_prints_on_all_refused_map(self):
        self._write_index_fixture()
        self.write_lesson(304, "rule")
        map_file = self._write_map("LL-304: documented\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertNotIn("Regenerate the index", out)


class TestStatusWordInBodyNeverTouched(FlipLessonStatusTestCase):
    """Added per Step 5: a file with `status:` also appearing in the body
    is edited only inside the frontmatter -- the body's own occurrence, at
    a different value, must survive verbatim while the frontmatter flips."""

    def test_status_word_in_body_is_left_alone_only_frontmatter_changes(self):
        target = self.write_lesson(
            210, "promoted",
            body_extra="This paragraph mentions status: bogus-not-real in passing.\n",
        )
        map_file = self._write_map("LL-210: orphaned\n")

        code, _out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        content = target.read_text(encoding="utf-8")
        self.assertIn("status: orphaned", content)
        self.assertNotIn("status: promoted", content)
        self.assertIn("status: bogus-not-real", content)


class TestFrontmatterBoundsEnforced(FlipLessonStatusTestCase):
    """T6-2 (BIR-S05-03-06 Discrimination Proof, mutation row M15): dropping
    the frontmatter-bounds check entirely passed all 27 flip tests, because
    `TestStatusWordInBodyNeverTouched` puts its body `status:` MID-line --
    the line-start `_STATUS_VALUE_RE` regex never reaches it whether or not
    the bounds exist, so that test cannot discriminate the bounds check.

    This fixture instead has NO `status:` key anywhere in the frontmatter,
    and a BODY line that STARTS at column 0 with `status: promoted`. If the
    bounds were ever dropped, the line-start regex would match that body
    line first (it is the first line-start `status:` in the file) and
    silently flip it. With the bounds enforced, no frontmatter `status:`
    line exists, so the file is reported "no parseable" and left untouched.
    """

    def test_no_frontmatter_status_with_line_start_status_in_body_is_reported_untouched(self):
        lid = "LL-220"
        text = (
            "---\n"
            f"id: {lid}\n"
            "title: A lesson with no frontmatter status\n"
            "category: process\n"
            "severity: medium\n"
            "language: [python]\n"
            "technology: [claude-code]\n"
            "domain: [PROC]\n"
            "source: fixture\n"
            "---\n\n"
            f"# {lid}: A lesson with no frontmatter status\n"
            "status: promoted -- this line starts at column 0, in the BODY\n"
        )
        path = self.lessons_dir / "LL-220-PROC-Fixture220.md"
        path.write_bytes(text.encode("utf-8"))
        before = path.read_bytes()
        map_file = self._write_map("LL-220: orphaned\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("no parseable", out)
        self.assertEqual(
            path.read_bytes(), before,
            "file must be byte-unchanged when no frontmatter status: line exists",
        )


if __name__ == "__main__":
    unittest.main()
