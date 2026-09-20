#!/usr/bin/env python3
"""Unit tests for score_backlog.py's index write-back under escaped pipes.

`write_scores_to_index` hand-rolls its own parse of each row so it can rebuild
the line in place. Under the old naive `line.split("|")` an escaped pipe in the
Feature cell shifted every segment right by one, with two consequences that a
clean-input-only test could never surface:

  - the COMPLETE/CLOSED guard read the Priority cell, so it never fired and a
    closed item was scored as if open;
  - the write itself landed on the Abbrev cell, replacing `DOC` with the score.

The row was also dropped by the shared reader, so the item silently vanished
from every prioritisation pass while the headline count still looked complete.

These tests run the write-back against both a clean row and an escaped row and
assert the two produce the same column assignment — demonstrably correct, not
merely different.

Run with:  python -m pytest tests/test_score_backlog.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import score_backlog
from markdown_parser import split_row_cells
from score_backlog import ScoreBreakdown, parse_index_table, write_scores_to_index


def _bd(total: int) -> ScoreBreakdown:
    """A minimal `ScoreBreakdown` fixture for tests that only care about the
    total `write_scores_to_index` writes, not any particular factor split."""
    return ScoreBreakdown(factors={}, total=total)


HEADER_WITH_SCORE = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)
HEADER_WITHOUT_SCORE = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Files |\n"
    "|-----|---------|----------|--------|--------|-------|\n"
)

ESCAPED_FEATURE = r"Run `git diff --name-only \| grep dir` first"
PLAIN_FEATURE = "Run a diff and grep it first"


def _row_cells(content: str, item_id: str) -> list[str]:
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_row_cells(stripped)
        if cells and cells[0] == item_id:
            return cells
    raise AssertionError(f"row {item_id} not found")


class TestWriteBackWithScoreColumn(unittest.TestCase):
    def _index(self, feature: str, status: str = "NOT_STARTED") -> str:
        return (
            HEADER_WITH_SCORE
            + f"| 062 | {feature} | High | {status} | DOC | - | [01](BB-062.md) |\n"
        )

    def test_score_lands_in_score_column_not_abbrev(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)})
        cells = _row_cells(out, "062")

        self.assertEqual(cells[2], "High")            # Priority intact
        self.assertEqual(cells[3], "NOT_STARTED")     # Status intact
        self.assertEqual(cells[4], "DOC")             # Abbrev NOT clobbered
        self.assertEqual(cells[5], "45")              # Score written here
        self.assertEqual(cells[6], "[01](BB-062.md)")

    def test_escaped_and_clean_rows_agree_column_for_column(self):
        escaped = _row_cells(
            write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)}), "062"
        )
        clean = _row_cells(
            write_scores_to_index(self._index(PLAIN_FEATURE), {"062": _bd(45)}), "062"
        )
        for idx in (0, 2, 3, 4, 5, 6):
            self.assertEqual(clean[idx], escaped[idx], f"column {idx} diverged")

    def test_closed_guard_fires_on_an_escaped_row(self):
        # The guard used to read Priority ("High"), never match COMPLETE, and
        # score a closed item as open.
        out = write_scores_to_index(
            self._index(ESCAPED_FEATURE, status="COMPLETE"), {"062": _bd(45)}
        )
        self.assertEqual(_row_cells(out, "062")[5], "-")

    def test_escaping_survives_the_write_verbatim(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)})
        self.assertIn(r"\|", out)
        self.assertEqual(
            _row_cells(out, "062")[1], "Run `git diff --name-only | grep dir` first"
        )

    def test_row_is_not_dropped_by_the_reader(self):
        items = parse_index_table(self._index(ESCAPED_FEATURE))
        self.assertEqual([i["id"] for i in items], ["062"])
        self.assertEqual(items[0]["status"], "NOT_STARTED")
        self.assertEqual(items[0]["abbrev"], "DOC")

    def test_sibling_rows_unaffected(self):
        content = (
            HEADER_WITH_SCORE
            + "| 061 | Before | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
            + f"| 062 | {ESCAPED_FEATURE} | High | NOT_STARTED | DOC | - | [01](b.md) |\n"
            + "| 063 | After | Low | NOT_STARTED | DOC | - | [01](c.md) |\n"
        )
        out = write_scores_to_index(content, {"061": _bd(10), "062": _bd(45), "063": _bd(20)})

        self.assertEqual(_row_cells(out, "061")[5], "10")
        self.assertEqual(_row_cells(out, "062")[5], "45")
        self.assertEqual(_row_cells(out, "063")[5], "20")
        for item_id in ("061", "062", "063"):
            self.assertEqual(_row_cells(out, item_id)[4], "DOC")


class TestWriteBackInsertingScoreColumn(unittest.TestCase):
    """The 6-column index gets a Score column inserted before Files."""

    def _index(self, feature: str) -> str:
        return (
            HEADER_WITHOUT_SCORE
            + f"| 062 | {feature} | High | NOT_STARTED | DOC | [01](BB-062.md) |\n"
        )

    def test_insert_keeps_columns_aligned_on_an_escaped_row(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)})
        cells = _row_cells(out, "062")

        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[2], "High")
        self.assertEqual(cells[3], "NOT_STARTED")
        self.assertEqual(cells[4], "DOC")
        self.assertEqual(cells[5], "45")
        self.assertEqual(cells[6], "[01](BB-062.md)")

    def test_header_and_separator_gain_the_column(self):
        out = write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)})
        header = next(
            line for line in out.split("\n") if line.strip().startswith("| ID")
        )
        self.assertIn("Score", header)
        self.assertEqual(len(split_row_cells(header)), 7)

    def test_escaped_and_clean_rows_agree_after_insert(self):
        escaped = _row_cells(
            write_scores_to_index(self._index(ESCAPED_FEATURE), {"062": _bd(45)}), "062"
        )
        clean = _row_cells(
            write_scores_to_index(self._index(PLAIN_FEATURE), {"062": _bd(45)}), "062"
        )
        for idx in (0, 2, 3, 4, 5, 6):
            self.assertEqual(clean[idx], escaped[idx], f"column {idx} diverged")


class TestBoundaryFirstWalker(unittest.TestCase):
    """A1 -- the boundary check must run BEFORE any skip branch, so the walker
    terminates cleanly at a section boundary instead of running off the end of
    the table. A blank line inside the table body is NOT a boundary."""

    def test_blank_line_inside_table_body_does_not_truncate(self):
        # Every row below the blank line must still be scored.
        content = (
            HEADER_WITH_SCORE
            + "| 061 | First | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
            + "\n"
            + "| 062 | Second | High | NOT_STARTED | DOC | - | [01](b.md) |\n"
        )
        out = write_scores_to_index(content, {"061": _bd(10), "062": _bd(20)})
        self.assertEqual(_row_cells(out, "061")[5], "10")
        self.assertEqual(_row_cells(out, "062")[5], "20")

    def test_write_back_does_not_cross_into_a_following_table(self):
        # Two tables separated by a blank line, a blockquote, and a "---":
        # the walker must terminate at the "---" boundary and never touch the
        # second table's rows.
        content = (
            HEADER_WITH_SCORE
            + "| 061 | First | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
            + "\n"
            + "> A note about the table above.\n"
            + "\n"
            + "---\n"
            + "\n"
            + "| ID  | Other | Value |\n"
            + "|-----|-------|-------|\n"
            + "| 900 | Should | NotBeTouched |\n"
        )
        second_table_before = content[content.index("| ID  | Other |"):]

        out = write_scores_to_index(content, {"061": _bd(10)})

        self.assertEqual(_row_cells(out, "061")[5], "10")
        second_table_after = out[out.index("| ID  | Other |"):]
        self.assertEqual(
            second_table_after, second_table_before,
            "the second table must be byte-unchanged after write-back",
        )


class TestReconciliationWarning(unittest.TestCase):
    """A2 -- write_scores_to_index compares computed vs written counts and
    warns loudly on stderr when they diverge. The warning is a data-shape
    signal about the caller's index, not a script failure: it never raises
    SystemExit, so the caller's exit code stays 0."""

    def _clean_index(self) -> str:
        return (
            HEADER_WITH_SCORE
            + "| 061 | First | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
        )

    def test_no_warning_on_a_clean_write(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            write_scores_to_index(self._clean_index(), {"061": _bd(10)})
        self.assertEqual(err.getvalue(), "")

    def test_warning_fires_verbatim_on_a_shortfall(self):
        # scores names an item the walker never reaches -- exactly the
        # "computed N, wrote M" shortfall the reconciliation check exists to
        # surface. Assert the exact shipped warning text.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            write_scores_to_index(self._clean_index(), {"061": _bd(10), "062": _bd(20)})
        self.assertEqual(
            err.getvalue().strip(),
            "WARNING: computed 2 score(s) but wrote 1. "
            "1 row(s) did not receive a Score cell -- the table walk "
            "terminated early. Check for a malformed row or a stray section "
            "boundary inside the table body.",
        )

    def test_shortfall_does_not_raise_systemexit(self):
        try:
            write_scores_to_index(self._clean_index(), {"061": _bd(10), "062": _bd(20)})
        except SystemExit:
            self.fail(
                "write_scores_to_index must not sys.exit on a reconciliation "
                "shortfall -- exit code stays 0"
            )

    def test_shortfall_on_the_two_table_boundary_fixture(self):
        # A realistic source of the shortfall: the walker terminates at the
        # section boundary before reaching a row in a following table.
        content = (
            HEADER_WITH_SCORE
            + "| 061 | First | Low | NOT_STARTED | DOC | - | [01](a.md) |\n"
            + "\n"
            + "---\n"
            + "\n"
            + "| ID  | Other | Value |\n"
            + "|-----|-------|-------|\n"
            + "| 900 | Should | NotBeTouched |\n"
        )
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            write_scores_to_index(content, {"061": _bd(10), "900": _bd(5)})
        self.assertIn("WARNING: computed 2 score(s) but wrote 1.", err.getvalue())


class TestReadItemFrontmatter(unittest.TestCase):
    """Characterization coverage for `read_item_frontmatter`, the module's own
    frontmatter parse.

    This path feeds the scoring inputs directly — `blocks` and `created` are
    read straight off the returned dict — so a parse discrepancy silently
    reorders the backlog rather than raising. It was a zero-coverage path;
    these tests pin its contract (a `dict`, never `None`; an empty dict for
    every absence and every malformed shape) so a consolidation onto a shared
    parser is verifiable rather than taken on inspection.

    `id`, `created`, and `blocks` are read at the text level (see
    `_text_level_scoring_fields`), never through YAML's implicit resolvers —
    so `blocks` entries are plain strings exactly as authored, not the ints
    `yaml.safe_load` would produce for an unquoted numeric list entry. The
    return also carries the item's body under `_body` whenever the
    frontmatter block itself parses successfully, alongside whatever keys it
    yields — see `test_body_is_retained_alongside_the_frontmatter`.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="score_backlog_fm_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _item(self, body: str) -> Path:
        path = self.tmp / "item.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_missing_file_returns_empty_dict(self):
        missing = self.tmp / "nope.md"
        self.assertEqual(score_backlog.read_item_frontmatter(missing), {})

    def test_file_without_frontmatter_returns_empty_dict(self):
        # The real corpus carries these: an older item whose header is a plain
        # H1 with bold key/value lines and no YAML block at all.
        path = self._item("# BB-143-01 - A legacy item\n\n**ID:** BB-143\n")
        self.assertEqual(score_backlog.read_item_frontmatter(path), {})

    def test_unterminated_frontmatter_returns_empty_dict(self):
        path = self._item("---\nid: 081\nstatus: NOT_STARTED\n\n# No closing fence\n")
        self.assertEqual(score_backlog.read_item_frontmatter(path), {})

    def test_wellformed_frontmatter_parses_to_typed_values(self):
        path = self._item(
            "---\n"
            "id: 081\n"
            'title: "Frontmatter parse consolidation"\n'
            "priority: Low\n"
            "status: NOT_STARTED\n"
            "created: 2026-08-12\n"
            "blocks: [143, 185]\n"
            "---\n"
            "\n"
            "# Body\n"
        )

        fm = score_backlog.read_item_frontmatter(path)

        # A leading zero keeps the id a string in YAML — the index and the
        # frontmatter therefore agree on "081", not on 81.
        self.assertEqual(fm["id"], "081")
        self.assertEqual(fm["priority"], "Low")
        # Read at the text level (not through yaml.safe_load), so entries are
        # plain strings exactly as authored, not ints.
        self.assertEqual(fm["blocks"], ["143", "185"])
        # YAML types a bare date; compute_score's age factor also accepts the
        # plain-string form the text-level overlay produces (see
        # test_regex_fallback_reads_created_and_blocks_without_yaml).
        self.assertEqual(str(fm["created"]), "2026-08-12")

    def test_octal_looking_id_is_not_mistyped(self):
        """The bug `_text_level_scoring_fields` exists to fix: `yaml.safe_load`
        reads an unquoted all-octal-digit id like "061" as octal 61 = decimal
        49. The text-level overlay keeps it "061"."""
        path = self._item("---\nid: 061\nblocks: [061, 009]\n---\n\n# Body\n")

        fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(fm["id"], "061")
        self.assertEqual(fm["blocks"], ["061", "009"])

    def test_empty_blocks_list_survives_as_a_list(self):
        path = self._item("---\nid: 081\nblocks: []\n---\n\n# Body\n")

        fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(fm["blocks"], [])

    def test_malformed_yaml_returns_empty_dict_rather_than_raising(self):
        path = self._item("---\nid: 081\n  bad: [unclosed\n---\n\n# Body\n")
        self.assertEqual(score_backlog.read_item_frontmatter(path), {})

    def test_empty_frontmatter_block_returns_empty_dict(self):
        # "---\n---\n" has no CLOSING "\n---\n" distinct from the opening
        # delimiter (the two dash-lines share their one newline) -- so
        # `split_frontmatter_block` reports no frontmatter block at all here,
        # same as an unterminated one. No body is attached, since `parts` is
        # `None` before the body is ever split out.
        path = self._item("---\n---\n\n# Body\n")
        self.assertEqual(score_backlog.read_item_frontmatter(path), {})

    def test_a_value_containing_three_dashes_no_longer_truncates_the_block(self):
        """The one deliberate behaviour change of the parser consolidation.

        The old inline split closed the block at the first `---` found
        anywhere from offset 3, so a value merely containing `---` cut the
        frontmatter mid-token; YAML then failed on the fragment and the item
        scored with no frontmatter at all — silently, since every failure
        here returns an empty dict. The shared split requires a full
        `\\n---\\n` delimiter line, so the block survives intact.
        """
        path = self._item(
            "---\n"
            'title: "a---b"\n'
            "id: 081\n"
            "blocks: [143]\n"
            "---\n"
            "\n"
            "# Body\n"
        )

        fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(fm["title"], "a---b")
        self.assertEqual(fm["blocks"], ["143"])  # scoring input recovered

    def test_body_is_retained_alongside_the_frontmatter(self):
        """Step 6: the whole file is already read here; the body must come
        back with the frontmatter rather than being thrown away, and with no
        second read of the file."""
        path = self._item(
            "---\nid: 081\npriority: Low\n---\n\n# Body text\n\nMore body.\n"
        )
        original_read_text = Path.read_text

        with unittest.mock.patch.object(Path, "read_text", autospec=True) as mocked:
            mocked.side_effect = lambda self, *a, **kw: original_read_text(self, *a, **kw)
            fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(fm["_body"], "\n# Body text\n\nMore body.\n")

    def test_regex_fallback_reads_created_and_blocks_without_yaml(self):
        """The no-yaml branch is a real shipped contract: it extracts only
        `created` and `blocks`, the two keys scoring consumes."""
        path = self._item(
            "---\n"
            "id: 081\n"
            "created: 2026-08-12\n"
            "blocks: [143, 185]\n"
            "---\n"
            "\n"
            "# Body\n"
        )

        with unittest.mock.patch.object(score_backlog, "HAS_YAML", False):
            fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(fm["created"], "2026-08-12")
        self.assertEqual(fm["blocks"], ["143", "185"])
        self.assertNotIn("id", fm)  # the fallback reads only the scoring keys

    def test_regex_fallback_reads_a_yaml_block_sequence(self):
        path = self._item(
            "---\n"
            "id: 081\n"
            "blocks:\n"
            "  - 143\n"
            "  - 185\n"
            "---\n"
            "\n"
            "# Body\n"
        )

        with unittest.mock.patch.object(score_backlog, "HAS_YAML", False):
            fm = score_backlog.read_item_frontmatter(path)

        self.assertEqual(fm["blocks"], ["143", "185"])


CONFIG_YAML_FIXTURE = """project:
  name: "ScoreBacklogFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""


class TestLineEndingsPreserved(unittest.TestCase):
    """The score write-back must not translate the index's line endings.

    `main()` reads the index and writes the Score column back in place. A
    `read_text` / `write_text` pair round-trips through Python's
    universal-newline translation: the read collapses any line ending to
    "\\n", and the write turns every "\\n" back into the running platform's
    `os.linesep`. A one-cell score update then rewrites every line in the
    file — including the prose section below the table, which the write-back
    walker deliberately stops before. The content survives; the diff does
    not, and reviewing what a destructive script actually changed becomes
    impossible.

    Both directions are asserted because each fails on only one platform:
    the LF case fails on Windows (`os.linesep == "\\r\\n"`), the CRLF case
    on POSIX. One direction alone is a coin flip on which platform catches
    the regression.

    Fixtures are written with `write_bytes`, never `write_text` —
    `write_text` applies the same `os.linesep` translation the defect
    applies, so a fixture built with it matches the platform by
    construction, cancels the defect out, and leaves the test vacuous
    everywhere.
    """

    LF_INDEX = (
        b"# Backlog Index\n"
        b"\n"
        b"## Backlog Items\n"
        b"\n"
        b"| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
        b"|-----|---------|----------|--------|--------|-------|-------|\n"
        b"| 062 | An open item | High | NOT_STARTED | DOC | - | [01](a.md) |\n"
        b"| 063 | A closed item | Low | COMPLETE | DOC | - | [01](b.md) |\n"
        b"\n"
        b"## Notes\n"
        b"\n"
        b"A bystander line the write-back walker never reaches.\n"
    )
    CRLF_INDEX = LF_INDEX.replace(b"\n", b"\r\n")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="score_backlog_eol_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        self.index_path = self.backlog_dir / "00-Index-Backlog.md"

    def write_index_bytes(self, content: bytes) -> Path:
        self.index_path.write_bytes(content)
        return self.index_path

    def run_score(self) -> str:
        """Invoke score_backlog.main() via an injected argv; return stdout."""
        saved_argv = sys.argv
        sys.argv = ["score_backlog", "--config", str(self.config_path)]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                score_backlog.main()
        finally:
            sys.argv = saved_argv
        return buf.getvalue()

    def _score_cell(self, item_id: str) -> str:
        text = self.index_path.read_text(encoding="utf-8")
        return _row_cells(text, item_id)[5]

    def test_lf_index_stays_lf(self):
        self.write_index_bytes(self.LF_INDEX)

        self.run_score()

        raw = self.index_path.read_bytes()
        self.assertNotIn(
            b"\r\n", raw, "an LF index must not gain a single CRLF line ending"
        )
        # The write really ran — otherwise the assertion above passes vacuously.
        self.assertNotEqual(self._score_cell("062"), "-")

    def test_crlf_index_stays_crlf(self):
        self.write_index_bytes(self.CRLF_INDEX)

        self.run_score()

        raw = self.index_path.read_bytes()
        self.assertEqual(
            raw.count(b"\n"),
            raw.count(b"\r\n"),
            "every line ending in a CRLF index must still be CRLF",
        )
        self.assertNotEqual(self._score_cell("062"), "-")

    def test_bystander_prose_below_the_table_is_byte_identical(self):
        """The walker breaks at the `## Notes` boundary, so this line is one
        the score write-back never intended to touch. It must come back
        byte-for-byte, newline included."""
        self.write_index_bytes(self.LF_INDEX)

        self.run_score()

        self.assertIn(
            b"A bystander line the write-back walker never reaches.\n",
            self.index_path.read_bytes(),
        )


class TestScoreRowProcessorNineColumnFixture(unittest.TestCase):
    """Session-01 Key Finding, bounded into this task: `_score_row_processor`
    had never seen a 9-column generated row. The fixture row is built from
    `generate_backlog_index.HEADER_CELLS`, never a hand-typed width, so a
    future column-order change fails this test instead of silently drifting
    out of sync with the generator's own contract."""

    def test_nine_column_row_reads_score_and_file_position_relative(self):
        from generate_backlog_index import COLUMN_COUNT, HEADER_CELLS

        self.assertEqual(COLUMN_COUNT, 9)
        cells = [""] * COLUMN_COUNT
        cells[HEADER_CELLS.index("ID")] = "042"
        cells[HEADER_CELLS.index("Title")] = "Bug: a generated-shape title"
        cells[HEADER_CELLS.index("Priority")] = "High"
        cells[HEADER_CELLS.index("Status")] = "NOT_STARTED"
        cells[HEADER_CELLS.index("Domain")] = "BUG"
        cells[HEADER_CELLS.index("Created")] = "2026-01-01"
        cells[HEADER_CELLS.index("Blocks")] = "001"
        cells[HEADER_CELLS.index("Score")] = "77"
        cells[HEADER_CELLS.index("File")] = "[042](BB-042-01-BUG-Thing.md)"

        result = score_backlog._score_row_processor(cells, 0, {})

        self.assertEqual(result["id"], "042")
        self.assertEqual(result["feature"], "Bug: a generated-shape title")
        self.assertEqual(result["priority"], "High")
        self.assertEqual(result["status"], "NOT_STARTED")
        self.assertEqual(result["abbrev"], "BUG")
        # A cells[5]-indexed read (the pre-fix behaviour) would have picked up
        # "2026-01-01" (Created) here instead of "77" (Score).
        self.assertEqual(result["score"], "77")
        self.assertEqual(result["file_count"], 1)

    def test_six_column_row_still_has_no_score(self):
        # The oldest legacy shape carries no Score column at all; cells[-2]
        # would misread the Abbrev cell as Score, so this width keeps its own
        # branch and must be unaffected by the position-relative fix.
        cells = ["062", "Title", "Low", "NOT_STARTED", "DOC", "[01](a.md)"]

        result = score_backlog._score_row_processor(cells, 0, {})

        self.assertIsNone(result["score"])
        self.assertEqual(result["files_raw"], "[01](a.md)")


class TestHeadingLessGeneratedContent(unittest.TestCase):
    """A `generate_backlog_index.py`-produced hub/leaf/shard carries no
    "## Backlog Items" heading at all -- only a `Generated:`/backlink line,
    the table, and the `## Shards` directory. Mirrors Task 1's fixture style
    for `parse_backlog.py`'s sibling fix; representation-only for the legacy
    path, since content that already carries the heading is untouched."""

    NINE_COLUMN_NO_HEADING = (
        "Generated: 2026-01-01\n\n"
        "| ID  | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
        "|-----|-------|----------|--------|--------|---------|--------|-------|------|\n"
        "| 042 | A generated-shape title | High | NOT_STARTED | BUG | 2026-01-01 "
        "| 001 | 77 | [042](BB-042-01-BUG-Thing.md) |\n"
    )

    def test_parse_index_table_reads_a_heading_less_nine_column_file(self):
        items = parse_index_table(self.NINE_COLUMN_NO_HEADING)
        self.assertEqual([i["id"] for i in items], ["042"])
        self.assertEqual(items[0]["score"], "77")

    def test_write_scores_to_index_updates_a_heading_less_file_without_adding_the_heading(self):
        out = write_scores_to_index(self.NINE_COLUMN_NO_HEADING, {"042": _bd(99)})

        self.assertNotIn("## Backlog Items", out)
        self.assertEqual(_row_cells(out, "042")[-2], "99")


WEIGHTS = {
    "priority_high": 30,
    "priority_medium": 20,
    "priority_low": 10,
    "bug_fix_bonus": 15,
    "in_progress_bonus": 10,
    "file_count_bonus": 5,
    "planning_penalty": -5,
    "blocks_bonus": 20,
    "momentum_bonus": 5,
    "age_bonus_per_week": 1,
    "age_cap": 12,
}

FACTOR_NAMES = (
    "priority", "bug/fix", "in_progress", "file_count",
    "planning_penalty", "blocks", "momentum", "age",
)


class TestComputeScoreBreakdown(unittest.TestCase):
    """`compute_score` now returns a `ScoreBreakdown` instead of a bare int.
    This is a representation change only: `total` must equal what the old
    bare-int arithmetic computed for the same inputs."""

    def test_baseline_item_shows_every_factor_including_zeros(self):
        item = {"priority": "Low", "feature": "Plain title", "status": "NOT_STARTED",
                "file_count": 1, "abbrev": "DOC"}
        breakdown = score_backlog.compute_score(item, {}, {}, WEIGHTS)

        self.assertEqual(list(breakdown.factors.keys()), list(FACTOR_NAMES))
        self.assertEqual(
            breakdown.factors,
            {"priority": 10, "bug/fix": 0, "in_progress": 0, "file_count": 0,
             "planning_penalty": 0, "blocks": 0, "momentum": 0, "age": 0},
        )
        self.assertEqual(breakdown.total, 10)
        self.assertEqual(breakdown.total, sum(breakdown.factors.values()))

    def test_every_factor_contributing_sums_to_the_same_total_the_old_int_computed(self):
        item = {"priority": "High", "feature": "Bug: fix the thing", "status": "IN_PROGRESS",
                "file_count": 3, "abbrev": "BUG"}
        frontmatter = {"blocks": ["001", "002", "999"], "created": "2026-01-01"}
        archive_counts = {"BUG": 1}
        open_item_ids = {"001", "002"}

        breakdown = score_backlog.compute_score(
            item, frontmatter, archive_counts, WEIGHTS, open_item_ids
        )

        expected = {
            "priority": 30,        # High
            "bug/fix": 15,         # "Bug" in feature
            "in_progress": 10,     # status IN_PROGRESS
            "file_count": 10,      # 5 * (3 - 1)
            "planning_penalty": 0, # not PLANNING
            "blocks": 40,          # 2 open blocks (999 excluded) * 20
            "momentum": 5,         # BUG archived
            "age": 12,             # capped at age_cap
        }
        self.assertEqual(breakdown.factors, expected)
        self.assertEqual(breakdown.total, sum(expected.values()))

    def test_planning_penalty_is_negative_and_included(self):
        item = {"priority": "Medium", "feature": "Plain", "status": "PLANNING",
                "file_count": 1, "abbrev": "DOC"}
        breakdown = score_backlog.compute_score(item, {}, {}, WEIGHTS)

        self.assertEqual(breakdown.factors["planning_penalty"], -5)
        self.assertEqual(breakdown.total, 20 - 5)


class TestFactor2AbbrevRekey(unittest.TestCase):
    """Factor 2 is keyed on `abbrev == "BUG"`, a controlled vocabulary a
    title cap cannot truncate -- not the old `\\b(Bug|Fix)\\b` regex read
    against the (truncatable) Feature cell. One test per population from
    this task's live-corpus enumeration (`BIR-S02-02-ScoreDeltas.md`)."""

    def _bug_fix_points(self, feature: str, abbrev: str, frontmatter: dict | None = None) -> int:
        item = {"priority": "Low", "feature": feature, "status": "NOT_STARTED",
                "file_count": 1, "abbrev": abbrev}
        breakdown = score_backlog.compute_score(item, frontmatter or {}, {}, WEIGHTS)
        return breakdown.factors["bug/fix"]

    def test_bug_abbrev_with_keyword_title_scores_the_bonus(self):
        self.assertEqual(self._bug_fix_points("Bug: the thing is broken", "BUG"), 15)

    def test_bug_abbrev_without_keyword_title_still_scores_the_bonus(self):
        # This is the case the old regex missed entirely -- an item titled
        # past the keyword, or never using it, still gets credited once the
        # bonus reads the controlled vocabulary instead of free text.
        self.assertEqual(self._bug_fix_points("A plain title with no keyword", "BUG"), 15)

    def test_non_bug_abbrev_with_keyword_title_scores_nothing(self):
        # The old regex would have awarded +15 here, reading a "Fix:"
        # title prefix used by an unrelated, non-bug class of item.
        self.assertEqual(
            self._bug_fix_points("Fix: VERSION.json pins a stale build", "INFRA"), 0
        )

    def test_non_bug_abbrev_without_keyword_title_scores_nothing(self):
        self.assertEqual(self._bug_fix_points("A plain title with no keyword", "INFRA"), 0)

    def test_frontmatter_abbrev_is_preferred_over_the_index_row_domain_cell(self):
        # The frontmatter `abbrev:` wins over the index row's Domain cell --
        # the frontmatter cannot go stale relative to a regenerated index.
        self.assertEqual(
            self._bug_fix_points("Plain", "INFRA", frontmatter={"abbrev": "BUG"}), 15
        )

    def test_explanation_parenthetical_names_the_resolved_abbrev(self):
        item = {"priority": "Low", "feature": "Plain", "status": "NOT_STARTED",
                "file_count": 1, "abbrev": "BUG"}
        breakdown = score_backlog.compute_score(item, {}, {}, WEIGHTS)
        text = score_backlog.format_score_explanation("001", item, breakdown, {}, None)
        self.assertIn("bug/fix(BUG)", text)


class TestScoreExplanation(unittest.TestCase):
    """`--id N --explain` -- every factor shown, zeros included, and the
    printed points sum to the printed total."""

    def _parse_points(self, line: str) -> int:
        return int(line.rsplit(None, 1)[-1])

    def test_explanation_shows_every_factor_and_sums_to_total(self):
        item = {"priority": "High", "feature": "Bug: fix the thing", "status": "IN_PROGRESS",
                "file_count": 3, "abbrev": "BUG"}
        frontmatter = {"blocks": ["001", "002", "999"], "created": "2026-01-01"}
        archive_counts = {"BUG": 1}
        open_item_ids = {"001", "002"}
        breakdown = score_backlog.compute_score(
            item, frontmatter, archive_counts, WEIGHTS, open_item_ids
        )

        text = score_backlog.format_score_explanation(
            "099", item, breakdown, frontmatter, open_item_ids
        )
        lines = text.split("\n")

        self.assertEqual(lines[0], f"099  score {breakdown.total}")
        self.assertEqual(len(lines), 1 + len(FACTOR_NAMES))
        points = [self._parse_points(line) for line in lines[1:]]
        self.assertEqual(sum(points), breakdown.total)
        # Every factor line is present, in schema order, zeros included.
        for name, line in zip(FACTOR_NAMES, lines[1:]):
            self.assertIn(name, line)

    def test_zero_contributing_factor_still_prints_a_line(self):
        item = {"priority": "Low", "feature": "Plain", "status": "NOT_STARTED",
                "file_count": 1, "abbrev": "DOC"}
        breakdown = score_backlog.compute_score(item, {}, {}, WEIGHTS)

        text = score_backlog.format_score_explanation("001", item, breakdown, {}, None)

        self.assertIn("bug/fix", text)
        self.assertIn("in_progress", text)
        self.assertIn("momentum", text)


if __name__ == "__main__":
    unittest.main()
