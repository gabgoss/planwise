#!/usr/bin/env python3
"""Unit tests for parse_lessons.py: the single ID-cell regex (bare, bold,
linked, any digit count), both on-disk index shapes (legacy Master Table
and generated hub/leaf/shard family), duplicate-id reporting (on disk and
inside the index, always by id with every path — never last-wins), and the
`--next-id` allocation union across disk, the generated family, and a
legacy Master Table.

Every fixture is built from explicit bytes (`write_bytes`), never
`write_text`, so a bare CR embedded mid-cell survives byte-exact into the
row-splitting test below rather than being translated away by the fixture
itself.

Run with:  python -m pytest tests/test_parse_lessons.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
from parse_lessons import (
    collect_all_known_ids,
    compute_next_id,
    parse_index,
    parse_legacy_master_table,
)

MASTER_TABLE_HEADER = (
    b"| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
    b"|----|-------|----------|----------|----------|------------|--------|--------|--------|\n"
)

# A Rule Promotion Log row carries a lesson id in its SECOND cell and lives
# in a different section. It must never be read as a Master-Table entry.
PROMOTION_LOG = (
    b"\n---\n\n## Rule Promotion Log\n\n"
    b"| Date | Lesson ID | Artifact Created | File |\n"
    b"|------|-----------|-----------------|------|\n"
    b"| 2026-01-01 | LL-999 | fixture-artifact | references/fixture.md |\n"
)


def _row(id_cell: bytes, n: int) -> bytes:
    """One 9-cell fixture row, matching MASTER_TABLE_HEADER's column count."""
    return (
        b"| " + id_cell + b" | Fixture lesson " + str(n).encode("ascii")
        + b" | process | medium | - | - | PROC | fixture | documented |\n"
    )


class _ParseLessonsFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree (config.yaml + lessons index +
    lesson files) so parse_lessons functions run against a hermetic copy
    instead of the live project's lessons index. Fixtures are written with
    `write_bytes` throughout.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_lessons_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.archive_dir = self.lessons_dir / "Archive"
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.lessons_dir / "00-Index-LessonsLearned.md"

        (self.planwise_dir / "config.yaml").write_bytes(
            (
                b'project:\n'
                b'  name: "ParseLessonsFixtureProject"\n'
                b'  lessons_dir: "LessonsLearned"\n'
                b'  index_files:\n'
                b'    lessons: "00-Index-LessonsLearned.md"\n'
            )
        )

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_parse_lessons",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()

    def write_legacy_index(self, body: bytes) -> Path:
        content = (
            b"# Lessons Learned Index\n\n"
            b"**Purpose:** Fixture index.\n\n"
            b"---\n\n"
            b"## Master Table\n\n"
            + MASTER_TABLE_HEADER
            + body
            + PROMOTION_LOG
        )
        self.index_path.write_bytes(content)
        return self.index_path

    def write_generated_family(
        self, hub_rows: bytes, leaf_range: tuple, leaf_rows: bytes,
        shard_range: tuple, shard_rows: bytes,
    ) -> None:
        hub_content = (
            b"# Lessons Learned Index\n\n"
            b"**Purpose:** Fixture index.\n\n"
            b"Generated: 2026-09-24\n\n"
            + MASTER_TABLE_HEADER
            + hub_rows
        )
        self.index_path.write_bytes(hub_content)

        leaf_name = f"00-Index-LessonsLearned-{leaf_range[0]:03d}-{leaf_range[1]:03d}.md"
        leaf_content = b"Generated: 2026-09-24\n\n" + MASTER_TABLE_HEADER + leaf_rows
        (self.lessons_dir / leaf_name).write_bytes(leaf_content)

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shard_name = f"Index-LessonsLearned-{shard_range[0]:03d}-{shard_range[1]:03d}.md"
        shard_content = b"Generated: 2026-09-24\n\n" + MASTER_TABLE_HEADER + shard_rows
        (self.archive_dir / shard_name).write_bytes(shard_content)

    def write_lesson(self, number: int, directory=None, suffix: str = "") -> Path:
        target_dir = directory if directory is not None else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"LL-{number:03d}-PROC-Fixture{number}{suffix}.md"
        path.write_bytes(
            (
                f"---\nid: LL-{number:03d}\nstatus: documented\n---\n\n"
                f"# LL-{number:03d}-PROC: Fixture lesson {number}\n"
            ).encode("utf-8")
        )
        return path


class TestThreeFormFixture(_ParseLessonsFixtureBase):
    """The single regex: bare, bold, and linked ID cells all parse."""

    def test_bare_bold_and_linked_id_cells_all_parse(self):
        body = (
            _row(b"LL-101", 101)
            + _row(b"**LL-102**", 102)
            + _row(b"[LL-103](Archive/LL-103-x.md)", 103)
        )
        self.write_legacy_index(body)

        content = self.index_path.read_bytes().decode("utf-8")
        rows = parse_legacy_master_table(content)

        self.assertEqual({row.id for row in rows if not row.malformed}, {101, 102, 103})

    def test_five_digit_id_parses(self):
        body = _row(b"LL-10001", 10001)
        self.write_legacy_index(body)

        content = self.index_path.read_bytes().decode("utf-8")
        rows = parse_legacy_master_table(content)

        self.assertEqual([row.id for row in rows if not row.malformed], [10001])


class TestLegacyBoundaryAndBlankLine(_ParseLessonsFixtureBase):
    """A blank line inside the table body does not end the walk; the Rule
    Promotion Log's rows are never counted as Master Table rows."""

    def test_blank_line_inside_table_survives_and_log_rows_excluded(self):
        body = _row(b"LL-101", 101) + b"\n" + _row(b"LL-102", 102)
        self.write_legacy_index(body)

        content = self.index_path.read_bytes().decode("utf-8")
        rows = parse_legacy_master_table(content)

        self.assertEqual({row.id for row in rows if not row.malformed}, {101, 102})
        self.assertNotIn(999, {row.id for row in rows})


class TestRowLineIsOneBased(unittest.TestCase):
    """Code-review fix 9: `Row.line` is 1-based (the file's own first line
    is line 1), matching every editor and every `{source}:{line}` display
    this project prints -- not the walker's internal 0-based offset."""

    def test_legacy_row_line_matches_its_1_based_position_in_the_file(self):
        content = (
            "# Header\n"
            "\n"
            "## Master Table\n"
            "\n"
            "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
            "|----|-------|----------|----------|----------|------------|--------|--------|--------|\n"
            "| LL-001 | Fixture lesson 1 | process | medium | - | - | PROC | fixture | documented |\n"
        )
        rows = parse_legacy_master_table(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].line, 7)


class TestBareCRInsideCell(_ParseLessonsFixtureBase):
    """A lone CR (0x0d) inside a cell is content, not a line terminator —
    row splitting is "\\n" only, never str.splitlines()."""

    def test_bare_cr_mid_cell_does_not_split_the_row(self):
        title_with_cr = b"Title with a bare CR\r inside it"
        row = (
            b"| LL-050 | " + title_with_cr
            + b" | process | medium | - | - | PROC | fixture | documented |\n"
        )
        self.write_legacy_index(row)

        content = self.index_path.read_bytes().decode("utf-8")
        rows = parse_legacy_master_table(content)

        matching = [r for r in rows if r.id == 50]
        self.assertEqual(len(matching), 1)
        self.assertFalse(matching[0].malformed)
        self.assertEqual(len(matching[0].cells), 9)


class TestGeneratedFamily(_ParseLessonsFixtureBase):
    """Rows are collected across the hub, an overflow leaf, and an Archive
    shard, resolved through the naming function."""

    def test_rows_collected_across_hub_leaf_and_shard(self):
        self.write_generated_family(
            hub_rows=_row(b"LL-101", 101),
            leaf_range=(102, 102),
            leaf_rows=_row(b"LL-102", 102),
            shard_range=(201, 300),
            shard_rows=_row(b"LL-201", 201),
        )

        parsed = parse_index(self.config)

        self.assertEqual(parsed.shape, "generated")
        ids = {row.id for row in parsed.rows if not row.malformed}
        self.assertEqual(ids, {101, 102, 201})
        self.assertEqual(len(parsed.per_file_row_counts), 3)


class TestDuplicates(_ParseLessonsFixtureBase):
    """A duplicate is reported by id, with every path — never last-wins —
    both on disk and inside the index, and --next-id still computes."""

    def test_duplicate_on_disk_and_in_index_both_reported_next_id_still_computes(self):
        self.write_lesson(5)
        self.write_lesson(5, suffix="B")
        body = _row(b"LL-010", 10) + _row(b"LL-010", 10)
        self.write_legacy_index(body)

        known = collect_all_known_ids(self.config)

        self.assertIn(5, known["duplicates_on_disk"])
        self.assertEqual(len(known["duplicates_on_disk"][5]), 2)
        self.assertIn(10, known["duplicates_in_index"])
        self.assertEqual(len(known["duplicates_in_index"][10]), 2)

        result = compute_next_id(self.config)
        self.assertEqual(result["next_id"], "LL-011")


class TestNextIdSourceIsolation(_ParseLessonsFixtureBase):
    """--next-id = max(disk ∪ generated family ∪ legacy table) + 1, with the
    max living in only one source at a time."""

    def test_next_id_when_max_lives_only_on_disk(self):
        self.write_lesson(50)
        body = _row(b"LL-010", 10)
        self.write_legacy_index(body)

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-051")
        self.assertIn("working directory", result["found_in"])

    def test_next_id_when_max_lives_only_in_index(self):
        self.write_lesson(5)
        body = _row(b"LL-050", 50)
        self.write_legacy_index(body)

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-051")
        self.assertIn("master table", result["found_in"])

    def test_next_id_when_max_lives_only_in_generated_family(self):
        self.write_lesson(5)
        self.write_generated_family(
            hub_rows=_row(b"LL-010", 10),
            leaf_range=(11, 11),
            leaf_rows=_row(b"LL-011", 11),
            shard_range=(200, 250),
            shard_rows=_row(b"LL-230", 230),
        )

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-231")
        self.assertIn("generated index", result["found_in"])


if __name__ == "__main__":
    unittest.main()
