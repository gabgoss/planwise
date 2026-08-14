#!/usr/bin/env python3
"""Unit tests for flip_lesson_status.py's Status-cell flip and its guards.

`flip_lesson_status.py` rewrites the Status cell of lessons-index Master
Table rows at batch scale. The load-bearing property is not the rewrite —
it is the REFUSALS: a landed row (`rule` / `applied`) must never be
downgraded to `promoted` / `documented` even when the caller's map says so,
a row already at its target status is skipped rather than rewritten, and a
mapped id with no row or a row with no parseable Status cell is reported
rather than silently skipped.

These tests exercise `main()` directly with an injected `sys.argv` (mirroring
`test_score_backlog.py`'s direct-import shape), against `tempfile`-built
index and map files — never `/tmp` literals, so the suite is Windows-safe.

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

from flip_lesson_status import main  # noqa: E402


INDEX_HEADER = (
    "# Lessons Learned Index\n\n"
    "## Master Table\n\n"
    "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
    "|----|-------|----------|----------|----------|------------|--------|--------|--------|\n"
)


def _row(lid: str, title: str, status: str) -> str:
    return f"| {lid} | {title} | Category | Severity | Language | Technology | Domain | Source | {status} |\n"


class FlipLessonStatusTestCase(unittest.TestCase):
    """Base fixture: a fresh temp dir per test, cleaned up automatically."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

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
    """Case 1 (EI Part-2 §3.1): a landed row must never be downgraded, even
    when the caller's map explicitly asks for it. This is the guard the
    source item's acceptance criteria require a test for — if the guard
    were removed, this test would fail (the row would silently rewrite to
    `documented`, exit 0, no REFUSED message)."""

    def test_never_downgrade_landed_row_is_refused(self):
        index = self._write(
            "index.md",
            INDEX_HEADER + _row("LL-001", "Some landed lesson", "rule"),
        )
        map_file = self._write("map.txt", "LL-001: documented\n")
        before = index.read_bytes()

        code, out = self._run_main([str(index), str(map_file)])

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("rule", out)
        self.assertIn("documented", out)
        self.assertEqual(index.read_bytes(), before, "row must be byte-unchanged on refusal")


class TestIdempotentSkip(FlipLessonStatusTestCase):
    """Case 2: a row already at the target status is skipped, not rewritten."""

    def test_row_already_at_target_is_skipped_not_rewritten(self):
        index = self._write(
            "index.md",
            INDEX_HEADER + _row("LL-002", "Already promoted lesson", "promoted"),
        )
        map_file = self._write("map.txt", "LL-002: promoted\n")
        before = index.read_bytes()

        code, out = self._run_main([str(index), str(map_file)])

        self.assertEqual(code, 0)
        self.assertIn("already promoted", out)
        self.assertEqual(index.read_bytes(), before)


class TestUnmatchedId(FlipLessonStatusTestCase):
    """Case 3: a mapped id with no matching row is reported, not ignored."""

    def test_unmatched_id_is_reported_and_exit_is_nonzero(self):
        index = self._write(
            "index.md",
            INDEX_HEADER + _row("LL-003", "A different lesson", "documented"),
        )
        map_file = self._write("map.txt", "LL-999: promoted\n")

        code, out = self._run_main([str(index), str(map_file)])

        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND IN MASTER TABLE", out)
        self.assertIn("LL-999", out)


class TestUnparseableStatusCell(FlipLessonStatusTestCase):
    """Case 4: a row matched by id but whose trailing cell isn't one of the
    four valid statuses is reported, not silently skipped, and left
    untouched."""

    def test_malformed_status_cell_is_reported_and_row_untouched(self):
        index = self._write(
            "index.md",
            INDEX_HEADER
            + "| LL-004 | A lesson with a bad tail | Category | Severity | Language | Technology | Domain | Source | not-a-status |\n",
        )
        map_file = self._write("map.txt", "LL-004: promoted\n")
        before = index.read_bytes()

        code, out = self._run_main([str(index), str(map_file)])

        self.assertEqual(code, 1)
        self.assertIn("check by hand", out)
        self.assertEqual(index.read_bytes(), before)


class TestFinalCellOnlyRewrite(FlipLessonStatusTestCase):
    """Case 5: only the trailing Status cell is rewritten, even when the
    Title prose contains the plain-text words "documented" and "promoted"
    — TAIL_RE is anchored on end-of-line, so mid-row prose is never
    mistaken for the Status cell."""

    def test_title_containing_status_words_is_left_alone(self):
        title = "Docs said documented but the code still says promoted"
        index = self._write(
            "index.md",
            INDEX_HEADER + _row("LL-005", title, "promoted"),
        )
        map_file = self._write("map.txt", "LL-005: rule\n")

        code, out = self._run_main([str(index), str(map_file)])

        self.assertEqual(code, 0)
        rewritten = index.read_text(encoding="utf-8")
        self.assertIn(title, rewritten, "Title prose must survive verbatim")
        self.assertIn(f"| {title} |", rewritten, "the words in the Title cell are untouched")
        # Only the trailing Status cell changed: promoted -> rule.
        self.assertIn("| rule |\n", rewritten)


class TestCleanDryRun(FlipLessonStatusTestCase):
    """Case 6: a dry-run over an already-correct index reports a reason per
    id and changes nothing on disk."""

    def test_dry_run_over_already_correct_index_changes_nothing(self):
        index = self._write(
            "index.md",
            INDEX_HEADER
            + _row("LL-006", "First already-correct lesson", "documented")
            + _row("LL-007", "Second already-correct lesson", "rule"),
        )
        map_file = self._write("map.txt", "LL-006: documented\nLL-007: rule\n")
        before = index.read_bytes()

        code, out = self._run_main([str(index), str(map_file), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertIn("would change: 0", out)
        self.assertIn("already documented", out)
        self.assertIn("already rule", out)
        self.assertEqual(index.read_bytes(), before)


class TestMapFileParseErrors(FlipLessonStatusTestCase):
    """Case 7: a malformed map-file line raises SystemExit naming the
    offending file:line, for each of the three malformed forms."""

    def test_bad_lesson_id_form_raises_systemexit(self):
        index = self._write("index.md", INDEX_HEADER + _row("LL-008", "A lesson", "documented"))
        map_file = self._write("map.txt", "NOT-AN-ID: promoted\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main([str(index), str(map_file)])

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("bad lesson id", message)

    def test_bad_status_value_raises_systemexit(self):
        index = self._write("index.md", INDEX_HEADER + _row("LL-009", "A lesson", "documented"))
        map_file = self._write("map.txt", "LL-009: retired\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main([str(index), str(map_file)])

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("retired", message)

    def test_missing_colon_raises_systemexit(self):
        index = self._write("index.md", INDEX_HEADER + _row("LL-010", "A lesson", "documented"))
        map_file = self._write("map.txt", "LL-010 promoted\n")

        with self.assertRaises(SystemExit) as ctx:
            self._run_main([str(index), str(map_file)])

        message = str(ctx.exception)
        self.assertIn(str(map_file), message)
        self.assertIn(":1:", message)
        self.assertIn("expected 'LL-NNN: status'", message)


if __name__ == "__main__":
    unittest.main()
