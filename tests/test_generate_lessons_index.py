#!/usr/bin/env python3
"""Unit tests for generate_lessons_index.py's scan/render half: frontmatter
extraction (including the ported inline-comment strip and both list-field
shapes), the 10-column row (escaping, truncation, the File-cell relative-
link convention), hub/Archive membership, the computed counter, and the
legacy-shape predicate. The refusal, drift and write tests live in
test_generate_lessons_index_writes.py, and the companion tests in
test_generate_lessons_index_companion.py. Both import the shared fixture base
and the lesson-item builder from this file.

Every fixture is built from explicit bytes (`write_bytes`), never
`write_text`.

Run with:  python -m pytest tests/test_generate_lessons_index.py -q
"""

import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
