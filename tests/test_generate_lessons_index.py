#!/usr/bin/env python3
"""Unit tests for generate_lessons_index.py's scan/render half: frontmatter
extraction (including the ported inline-comment strip and both list-field
shapes), the 10-column row (escaping, truncation, the File-cell relative-
link convention), hub/Archive membership, the computed counter, and the
legacy-shape predicate. Sharding, budgeting, and the write path are covered
by a later module addition, not by this file.

Every fixture is built from explicit bytes (`write_bytes`), never
`write_text`.

Run with:  python -m pytest tests/test_generate_lessons_index.py -q
"""

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_backlog_index as gbi
import generate_lessons_index as gli
from generate_lessons_index import (
    COL_DOMAIN,
    COL_FILE,
    COL_LANGUAGE,
    COL_TECHNOLOGY,
    COLUMN_COUNT,
    LessonsGeneratorError,
    _extract_fields,
    _normalize_id_text,
    _parse_list_field,
    _read_frontmatter_map,
    _strip_inline_comment,
    detect_location_anomalies,
    is_legacy_index,
    partition_lessons,
    render_row,
    scan_lessons,
    shard_for,
)
from markdown_parser import split_row_cells
from parse_lessons import compute_next_id, format_id

# A directory for the pure in-memory rendering/splitter tests below, which
# never touch a filesystem -- render_row/split_lessons_to_budget only need a
# Path to compute a relative File-cell link, never to read or write.
_PURE_LESSONS_DIR = Path("LessonsLearned")


def _make_lesson_item(item_id, *, title="Fixture lesson", category="process",
                       severity="medium", language=None, technology=None,
                       domain=None, source="fixture", status="documented"):
    """Build an already-scanned lesson item dict, matching what scan_lessons
    would have produced, for tests that exercise rendering/splitting
    directly without writing any file."""
    return {
        "id": item_id,
        "title": title,
        "category": category,
        "severity": severity,
        "language": language or ["python"],
        "technology": technology or ["claude-code"],
        "domain": domain or ["PROC"],
        "source": source,
        "status": status,
        "_path": _PURE_LESSONS_DIR / f"LL-{item_id:03d}-PROC-Fixture{item_id}.md",
        "_in_archive": False,
    }


class _GenerateLessonsIndexFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree (config.yaml + lessons dir +
    Archive dir) so this module's functions run against a hermetic copy
    instead of the live project's lessons corpus.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_lessons_index_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.archive_dir = self.lessons_dir / "Archive"
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.lessons_dir / "00-Index-LessonsLearned.md"

        (self.planwise_dir / "config.yaml").write_bytes(
            b'project:\n'
            b'  name: "GenerateLessonsIndexFixtureProject"\n'
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

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_generate_lessons_index",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()
        self.valid_statuses = frozenset(self.config.get("lesson_statuses") or [])

    def write_lesson(
        self,
        number: int,
        *,
        directory=None,
        status: str = "documented",
        title: str | None = None,
        category: str = "process",
        severity: str = "medium",
        language: str = "[python]",
        technology: str = "[claude-code]",
        domain: str = "[PROC]",
        source: str = "fixture",
        frontmatter_id: str | None = None,
        crlf: bool = False,
        suffix: str = "",
    ) -> Path:
        target_dir = directory if directory is not None else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        title = title or f"Fixture lesson {number}"
        id_value = frontmatter_id or f"LL-{number:03d}"
        text = (
            "---\n"
            f"id: {id_value}\n"
            f"title: {title}\n"
            f"category: {category}\n"
            f"severity: {severity}\n"
            f"language: {language}\n"
            f"technology: {technology}\n"
            f"domain: {domain}\n"
            f"source: {source}\n"
            f"status: {status}\n"
            "---\n\n"
            f"# LL-{number:03d}: {title}\n"
        )
        if crlf:
            text = text.replace("\n", "\r\n")
        path = target_dir / f"LL-{number:03d}-PROC-Fixture{number}{suffix}.md"
        path.write_bytes(text.encode("utf-8"))
        return path

    def run_main(self, *args):
        """Invoke gli.main() with an injected sys.argv (--config pointing at
        this fixture's config.yaml), capturing stdout/stderr."""
        old_argv = sys.argv
        sys.argv = [
            "generate_lessons_index.py", "--config", str(self.planwise_dir / "config.yaml"),
        ] + list(args)
        out, err = StringIO(), StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = gli.main()
        finally:
            sys.argv = old_argv
        return code, out.getvalue(), err.getvalue()

    def replace_cell_in_row(self, path: Path, lesson_id: int, col_index: int, new_value: str) -> None:
        """Rewrite exactly one cell of `lesson_id`'s row in the file at
        `path`, leaving every other line byte-identical. Used to fabricate
        a single-cell drift condition on an already-generated file."""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        id_str = format_id(lesson_id)
        for i, line in enumerate(lines):
            if line.startswith(f"| {id_str} |"):
                cells = split_row_cells(line)
                cells[col_index] = new_value
                lines[i] = "|" + "|".join(f" {c} " for c in cells) + "|"
                break
        else:
            raise AssertionError(f"row for {id_str} not found in {path}")
        path.write_bytes("\n".join(lines).encode("utf-8"))

    def write_lesson_missing_key(self, number: int, missing_key: str) -> Path:
        fields = {
            "id": f"LL-{number:03d}",
            "title": "t",
            "category": "process",
            "severity": "medium",
            "language": "[python]",
            "technology": "[x]",
            "domain": "[PROC]",
            "source": "s",
            "status": "documented",
        }
        del fields[missing_key]
        body = "\n".join(f"{key}: {value}" for key, value in fields.items())
        text = f"---\n{body}\n---\n\n# t\n"
        path = self.lessons_dir / f"LL-{number:03d}-PROC-Fixture{number}.md"
        path.write_bytes(text.encode("utf-8"))
        return path


class TestStripInlineComment(_GenerateLessonsIndexFixtureBase):
    """Ported from score_backlog.py's `_strip_inline_comment`."""

    def test_strips_trailing_comment_on_scalar_value(self):
        self.assertEqual(_strip_inline_comment("2026-01-15  # filed"), "2026-01-15")

    def test_strips_per_line_comment_on_block_form_value(self):
        raw = "\n- python  # lang one\n- yaml  # lang two"
        self.assertEqual(_strip_inline_comment(raw), "\n- python\n- yaml")


class TestQuoteAwareTitleCommentStrip(_GenerateLessonsIndexFixtureBase):
    """F3 remediation (BIR-S05-03-05 design review): the Title reader is
    quote-aware. A `#` inside a quoted scalar is text, never a comment
    start, and a quoted scalar's own escape sequences are unescaped."""

    def test_double_quoted_title_with_hash_and_escaped_quote_renders_unescaped(self):
        raw_title = '"A (Check #, x) y \\"z\\""'
        path = self.write_lesson(1, status="documented", title=raw_title)
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["title"], 'A (Check #, x) y "z"')

    def test_single_quoted_title_with_doubled_quote_renders_one_quote(self):
        raw_title = "'It''s fine'"
        path = self.write_lesson(2, status="documented", title=raw_title)
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["title"], "It's fine")

    def test_unquoted_title_with_trailing_comment_still_strips(self):
        raw_title = "Plain title # a trailing note"
        path = self.write_lesson(3, status="documented", title=raw_title)
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["title"], "Plain title")

    def test_quoted_title_followed_by_trailing_comment_keeps_title_drops_comment(self):
        raw_title = '"Quoted Title" # trailing comment'
        path = self.write_lesson(4, status="documented", title=raw_title)
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["title"], "Quoted Title")


class TestParseListField(_GenerateLessonsIndexFixtureBase):
    """Flow and block form both parse."""

    def test_flow_form(self):
        self.assertEqual(_parse_list_field("[python, yaml]"), ["python", "yaml"])

    def test_block_form(self):
        raw = "\n- python\n- yaml"
        self.assertEqual(_parse_list_field(raw), ["python", "yaml"])

    def test_empty_flow_form(self):
        self.assertEqual(_parse_list_field("[]"), [])


class TestQuoteAwareListFieldItems(_GenerateLessonsIndexFixtureBase):
    """R1 remediation (BIR-S05-03 design-review recheck): a quoted list
    item is stripped and unescaped per item, with the same quote-aware
    helpers the F3 title fix introduced -- `_strip_quotes` (flow and block
    form both) and a quote-aware comma split for the flow form, so a comma
    inside a quoted flow item never splits the item."""

    def test_flow_list_with_double_quoted_item_renders_unquoted(self):
        path = self.write_lesson(10, technology='[python, "claude-code"]')
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["technology"], ["python", "claude-code"])
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(split_row_cells(row)[COL_TECHNOLOGY], "python, claude-code")

    def test_block_list_with_single_quoted_item_renders_unquoted(self):
        path = self.write_lesson(11, language="\n- python\n- 'yaml'")
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["language"], ["python", "yaml"])
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(split_row_cells(row)[COL_LANGUAGE], "python, yaml")

    def test_quoted_flow_item_containing_a_comma_is_not_split(self):
        path = self.write_lesson(12, domain='[PROC, "A, B"]')
        raw_map = _read_frontmatter_map(path)
        fields = _extract_fields(path, raw_map, self.valid_statuses)
        self.assertEqual(fields["domain"], ["PROC", "A, B"])
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(split_row_cells(row)[COL_DOMAIN], "PROC, A, B")


class TestPipeEscapeRoundTrip(_GenerateLessonsIndexFixtureBase):
    """A literal `|` inside a code-span title, and a plain title, both
    round-trip through `split_row_cells` to exactly 10 cells."""

    def test_pipe_in_code_span_title_round_trips_to_ten_cells(self):
        lesson_path = self.write_lesson(101, title="A `cmd | grep x` pipeline title")
        raw_map = _read_frontmatter_map(lesson_path)
        fields = _extract_fields(lesson_path, raw_map, self.valid_statuses)
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(len(split_row_cells(row)), COLUMN_COUNT)

    def test_plain_title_round_trips_to_ten_cells(self):
        lesson_path = self.write_lesson(102, title="A plain title with no pipe")
        raw_map = _read_frontmatter_map(lesson_path)
        fields = _extract_fields(lesson_path, raw_map, self.valid_statuses)
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(len(split_row_cells(row)), COLUMN_COUNT)


class TestFileLinkConvention(_GenerateLessonsIndexFixtureBase):
    """The File cell resolves from the emitting file's own directory, for
    both a hub row and an Archive-shard row."""

    def _resolved_file_target(self, row: str, emit_dir: Path) -> Path:
        file_cell = split_row_cells(row)[COL_FILE]
        rel = file_cell[file_cell.index("(") + 1 : -1]
        return (emit_dir / rel).resolve()

    def test_file_link_resolves_from_hub_directory(self):
        lesson_path = self.write_lesson(101, status="documented")
        raw_map = _read_frontmatter_map(lesson_path)
        fields = _extract_fields(lesson_path, raw_map, self.valid_statuses)
        row, _truncated = render_row(fields, self.lessons_dir)
        self.assertEqual(self._resolved_file_target(row, self.lessons_dir), lesson_path.resolve())

    def test_file_link_resolves_from_archive_shard_directory(self):
        lesson_path = self.write_lesson(230, directory=self.archive_dir, status="rule")
        raw_map = _read_frontmatter_map(lesson_path)
        fields = _extract_fields(lesson_path, raw_map, self.valid_statuses)
        row, _truncated = render_row(fields, self.archive_dir)
        self.assertEqual(self._resolved_file_target(row, self.archive_dir), lesson_path.resolve())


class TestMembershipPartition(_GenerateLessonsIndexFixtureBase):
    def test_hub_and_shard_split_by_status_not_directory(self):
        self.write_lesson(101, status="documented")
        self.write_lesson(230, directory=self.archive_dir, status="rule")
        result = scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)
        hub_items, by_century = partition_lessons(result.items)
        self.assertEqual([item["id"] for item in hub_items], [101])
        self.assertEqual([item["id"] for item in by_century[shard_for(230)]], [230])


class TestCounterValue(_GenerateLessonsIndexFixtureBase):
    def test_counter_is_max_on_disk_plus_one(self):
        self.write_lesson(101, status="documented")
        self.write_lesson(105, directory=self.archive_dir, status="rule")
        result = compute_next_id(self.config)
        self.assertEqual(result["next"], 106)
        self.assertEqual(result["next_id"], "LL-106")


class TestLegacyPredicate(_GenerateLessonsIndexFixtureBase):
    def test_true_on_master_table_heading(self):
        content = "# Index\n\n## Master Table\n\n| ID | Title |\n"
        self.assertTrue(is_legacy_index(content))

    def test_true_on_rule_promotion_log_heading(self):
        content = "# Index\n\n## Rule Promotion Log\n\n| Date | Lesson ID |\n"
        self.assertTrue(is_legacy_index(content))

    def test_false_on_generated_fixture(self):
        content = "Generated: 2026-09-24\n\n| ID | Title | Category |\n"
        self.assertFalse(is_legacy_index(content))


class TestCRLFFrontmatter(_GenerateLessonsIndexFixtureBase):
    """Anticipated breach: a CRLF lesson file's frontmatter still parses,
    and no stray `\\r` reaches an extracted value."""

    def test_crlf_lesson_file_parses_with_no_stray_cr(self):
        lesson_path = self.write_lesson(101, status="documented", crlf=True)
        raw_map = _read_frontmatter_map(lesson_path)
        fields = _extract_fields(lesson_path, raw_map, self.valid_statuses)
        self.assertEqual(fields["id"], 101)
        self.assertEqual(fields["language"], ["python"])
        self.assertNotIn("\r", fields["title"])
        self.assertNotIn("\r", fields["status"])


class TestNormalizeIdText(_GenerateLessonsIndexFixtureBase):
    def test_ll_prefixed_form(self):
        self.assertEqual(_normalize_id_text("LL-296"), 296)

    def test_bare_digit_form(self):
        self.assertEqual(_normalize_id_text("296"), 296)

    def test_quoted_form(self):
        self.assertEqual(_normalize_id_text('"LL-296"'), 296)


class TestFilenameIdMismatch(_GenerateLessonsIndexFixtureBase):
    def test_mismatch_is_reported_per_file(self):
        self.write_lesson(101, status="documented", frontmatter_id="LL-102")
        result = scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)
        self.assertEqual(len(result.id_mismatches), 1)
        self.assertEqual(result.id_mismatches[0]["filename_id"], 101)
        self.assertEqual(result.id_mismatches[0]["frontmatter_id"], 102)

    def test_check_reports_id_mismatch_anomaly_exit_one(self):
        # Code-review fix 7: id_mismatches were collected by scan_lessons
        # but never surfaced to any report or write path.
        self.write_lesson(101, status="documented", frontmatter_id="LL-102")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("id-mismatch", out)
        self.assertIn("LL-101", out)
        self.assertIn("LL-102", out)

    def test_write_refuses_id_mismatch_exit_two(self):
        self.write_lesson(101, status="documented", frontmatter_id="LL-102")

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("id-mismatch", err)


class TestDuplicateId(_GenerateLessonsIndexFixtureBase):
    def test_duplicate_id_across_files_is_recorded_not_raised(self):
        self.write_lesson(101, status="documented")
        self.write_lesson(101, status="rule", directory=self.archive_dir, suffix="-dup")
        result = scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)
        self.assertIn(101, result.duplicate_ids)
        self.assertEqual(len(result.duplicate_ids[101]), 2)


class TestMissingKeyError(_GenerateLessonsIndexFixtureBase):
    def test_missing_required_key_raises(self):
        self.write_lesson_missing_key(101, "status")
        with self.assertRaises(LessonsGeneratorError):
            scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)


class TestBadStatus(_GenerateLessonsIndexFixtureBase):
    def test_status_outside_declared_set_raises(self):
        self.write_lesson(101, status="bogus")
        with self.assertRaises(LessonsGeneratorError):
            scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)


class TestLessonStatusesFallback(_GenerateLessonsIndexFixtureBase):
    """Code-review fix 6: a config.yaml with no `lesson_statuses:` key must
    NOT resolve to an empty set -- `status in frozenset()` is never True,
    so an empty fallback would refuse every lesson in the project."""

    def test_config_without_the_key_generates_cleanly(self):
        (self.planwise_dir / "config.yaml").write_bytes(
            b'project:\n'
            b'  name: "GenerateLessonsIndexFixtureProject"\n'
            b'  lessons_dir: "LessonsLearned"\n'
            b'  index_files:\n'
            b'    lessons: "00-Index-LessonsLearned.md"\n'
        )
        self.write_lesson(101, status="documented")

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertIn("lesson_statuses", err)


class TestDiscoveryIgnoresNonNumberedNames(_GenerateLessonsIndexFixtureBase):
    """Code-review fix 8: discovery must go through `parse_lessons.lesson_files`
    (numbered ids only), not a bare `glob('LL-*.md')` -- a non-numbered
    name like `LL-template.md` has no `LL-\\d+` id and must be ignored, not
    scanned (where it would refuse the whole run over missing frontmatter
    keys)."""

    def test_ll_template_md_is_ignored_and_does_not_refuse_the_run(self):
        self.write_lesson(101, status="documented")
        (self.lessons_dir / "LL-template.md").write_bytes(
            b"# LL-template\n\nNot a real lesson file -- no frontmatter at all.\n"
        )

        code, out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertIn("Wrote", out)


class TestLocationAnomaly(_GenerateLessonsIndexFixtureBase):
    def test_hub_status_lesson_in_archive_is_anomaly_but_still_hub_routed(self):
        self.write_lesson(101, status="documented", directory=self.archive_dir)
        result = scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)
        anomalies = detect_location_anomalies(result.items)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["status"], "documented")
        self.assertTrue(anomalies[0]["in_archive"])
        hub_items, _by_century = partition_lessons(result.items)
        self.assertEqual([item["id"] for item in hub_items], [101])

    def test_non_hub_status_lesson_at_top_level_is_anomaly_but_still_shard_routed(self):
        self.write_lesson(230, status="rule", directory=self.lessons_dir)
        result = scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses)
        anomalies = detect_location_anomalies(result.items)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["status"], "rule")
        self.assertFalse(anomalies[0]["in_archive"])
        hub_items, by_century = partition_lessons(result.items)
        self.assertEqual(hub_items, [])
        self.assertEqual([item["id"] for item in by_century[shard_for(230)]], [230])


class TestBudgetOnShippedBytes(unittest.TestCase):
    """A hub fixture that fits by body-only measurement but exceeds
    HUB_TOKEN_BUDGET once the per-file wrapper (header block, '## Shards'
    directory, footer) is counted must still split -- the splitter decides
    on body-plus-wrapper, never the bare body alone. Every resulting leaf's
    shipped content then measures under budget."""

    def test_wrapper_reserve_forces_a_split_a_bare_body_would_not_need(self):
        items = [_make_lesson_item(1), _make_lesson_item(2)]
        body, _truncated = gli._render_lessons_table_body(items, _PURE_LESSONS_DIR)
        _num_bytes, body_tokens = gli._measure(body)
        self.assertLess(body_tokens, gli.HUB_TOKEN_BUDGET, "fixture must fit by body-only measurement")

        # A wrapper reserve close to the whole budget forces a split of the
        # same two items that would otherwise ship as a single leaf.
        wrapper_tokens = gli.HUB_TOKEN_BUDGET - body_tokens + 10
        leaves = gli.split_lessons_to_budget(
            items, _PURE_LESSONS_DIR, wrapper_tokens=wrapper_tokens, budget=gli.HUB_TOKEN_BUDGET
        )
        self.assertGreater(len(leaves), 1, "the wrapper reserve alone must force a split")

        naming = gbi._index_naming(_PURE_LESSONS_DIR / "00-Index-LessonsLearned.md")
        hub_files = gli.build_lessons_hub_files(items, _PURE_LESSONS_DIR, [], naming, next_id=3)
        self.assertGreater(len(hub_files), 0)
        for entry in hub_files:
            shipped_tokens = gli.estimate_tokens(gli._shipped_bytes(entry["content"]))
            self.assertLess(shipped_tokens, gli.HUB_TOKEN_BUDGET, "every leaf must measure under budget on _shipped_bytes")


class TestBudgetBasisIsShippedBytes(unittest.TestCase):
    """T6-1 (BIR-S05-03-06 Discrimination Proof, mutation rows M05/M05b): no
    prior test pinned the budget's CRLF basis directly, so a regression that
    measures with plain `len(text.encode())` (dropping the one-byte-per-`\\n`
    CRLF allowance) passed every test in the suite.

    Two distinct mutations need two distinct tests:

    * M05 rebinds the module-level `_shipped_bytes`/`_measure` names
      themselves -- caught by pinning the formula directly against those
      names (first test below).
    * M05b leaves `_shipped_bytes`/`_measure` untouched and mutates only the
      generator's INTERNAL call sites (e.g. inside `split_lessons_to_budget`)
      to bypass them -- invisible to a test that only calls `gli._measure()`
      directly, since that function's own code is never exercised by the
      mutant. Catching M05b requires driving the real splitter with a
      fixture whose LF-only byte count sits under `HUB_TOKEN_BUDGET` while
      the real CRLF-worst-case count is already at or over it (second test
      below) -- exactly the gap a dropped `\\n` count would erase.
    """

    def test_measure_basis_is_utf8_bytes_plus_newline_count(self):
        items = [_make_lesson_item(i) for i in range(1, 6)]
        body, _truncated = gli._render_lessons_table_body(items, _PURE_LESSONS_DIR)
        num_bytes, tokens = gli._measure(body)
        expected_bytes = len(body.encode("utf-8")) + body.count("\n")
        self.assertEqual(num_bytes, expected_bytes, "basis must be UTF-8 bytes plus one per newline")
        self.assertEqual(tokens, gli.estimate_tokens(expected_bytes))
        # Same pin through the other imported name the splitter also uses.
        self.assertEqual(gli._shipped_bytes(body), expected_bytes)

    def test_many_short_rows_split_on_crlf_basis_but_not_on_lf_only_bytes(self):
        budget = gli.HUB_TOKEN_BUDGET
        items: list = []
        straddle_found = False
        lf_only_tokens = real_tokens = None
        for i in range(1, 2000):
            items.append(_make_lesson_item(
                i, title="T", language=["a"], technology=["a"], domain=["a"], source="a",
            ))
            body, _truncated = gli._render_lessons_table_body(items, _PURE_LESSONS_DIR)
            lf_only_tokens = gli.estimate_tokens(len(body.encode("utf-8")))
            _real_bytes, real_tokens = gli._measure(body)
            if lf_only_tokens < budget <= real_tokens:
                straddle_found = True
                break
            if lf_only_tokens >= budget:
                break
        self.assertTrue(
            straddle_found,
            f"could not grow a fixture straddling the CRLF/LF-only budget boundary "
            f"(last lf_only={lf_only_tokens}, real={real_tokens}, budget={budget})",
        )

        leaves = gli.split_lessons_to_budget(items, _PURE_LESSONS_DIR, wrapper_tokens=0, budget=budget)
        self.assertGreater(len(leaves), 1, "the CRLF-basis straddle alone must force a split")
        for _subset, _leaf_body, _num_bytes, leaf_tokens, _truncated_ids in leaves:
            self.assertLess(leaf_tokens, budget, "every leaf must measure under budget on the real basis")


class TestCenturySharding(unittest.TestCase):
    """`shard_for` is a pure function of the id alone -- no lookup table
    backs it, so it must agree with the formula at any id, not just the
    ids a fixture happens to plant."""

    def test_century_boundary_and_no_lookup_table(self):
        self.assertEqual(shard_for(1), shard_for(100))
        self.assertNotEqual(shard_for(100), shard_for(101))
        for probe in (1, 99, 100, 101, 250, 501, 999):
            self.assertEqual(shard_for(probe), (probe - 1) // 100)


class TestCounterLineDrift(_GenerateLessonsIndexFixtureBase):
    """The hub carries `**Next available ID:** LL-NNN` equal to max id + 1.
    Hand-editing it BELOW that value must make --check report
    stale-counter, exit 1 (code-review fix 2: `stale-counter` fires only
    when the on-disk counter is BELOW the derived value -- an on-disk
    counter ABOVE it is `counter_ahead` instead, see TestCounterFloor)."""

    def test_hand_edited_counter_reports_stale_counter_and_exits_one(self):
        self.write_lesson(101, status="documented")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        text = hub_path.read_text(encoding="utf-8")
        self.assertIn("**Next available ID:** LL-102", text)
        bad = text.replace("**Next available ID:** LL-102", "**Next available ID:** LL-050")
        hub_path.write_bytes(bad.encode("utf-8"))

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("stale-counter", out)
        self.assertNotIn("stale-wrapper", out)


class TestCounterFloor(_GenerateLessonsIndexFixtureBase):
    """Code-review fix 2 (amends D18, user decision): the counter a
    `--write` ships is `max(derived, on-disk counter)` -- the on-disk line
    is read only as a floor, never lowered."""

    def test_removing_the_top_lesson_after_write_does_not_lower_the_counter(self):
        self.write_lesson(101, status="documented")
        self.write_lesson(102, status="documented")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        self.assertIn("**Next available ID:** LL-103", hub_path.read_text(encoding="utf-8"))

        # Delete the highest-numbered lesson file. The pure derivation would
        # now compute LL-102 -- but the shipped counter must never move
        # backward on the next --write.
        (self.lessons_dir / "LL-102-PROC-Fixture102.md").unlink()

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertIn("**Next available ID:** LL-103", hub_path.read_text(encoding="utf-8"))

    def test_counter_ahead_of_derived_is_reported_and_never_lowered(self):
        self.write_lesson(101, status="documented")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        hub_path = self.lessons_dir / "00-Index-LessonsLearned.md"
        text = hub_path.read_text(encoding="utf-8")
        self.assertIn("**Next available ID:** LL-102", text)
        ahead = text.replace("**Next available ID:** LL-102", "**Next available ID:** LL-500")
        hub_path.write_bytes(ahead.encode("utf-8"))

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("counter_ahead", out)
        self.assertNotIn("stale-counter", out)

        # A subsequent --write must not lower the counter back to derived.
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertIn("**Next available ID:** LL-500", hub_path.read_text(encoding="utf-8"))


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
        self.write_lesson(101, status="documented")
        self._write_legacy_hub()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("legacy-shape", out)

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
