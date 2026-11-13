#!/usr/bin/env python3
"""The promotion-target, origin and enforcement-kind vocabularies are declared
once, in code, and every surface that restates them cannot drift from it.

The constants are `lessons_index_schema.PROMOTION_TARGETS`,
`lessons_index_schema.LESSON_ORIGINS` and `config_loader.DEFAULT_LESSON_CHECK_KINDS`.
Each test extracts the value set from one surface and requires an empty
symmetric difference against the constant, and a failure names the divergent
members. Each extractor has a direction test on a known-bad text, so a pass
means the extractor saw its subject. Two frozen copies of the six-value line
(the seed body and the migration test) are read, never edited.

Run with:  python -m unittest tests/test_promotion_vocabulary_parity.py
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import lessons_index_schema
import migrate_lessons_support

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "planwise"

SCHEMA_REF = PLUGIN / "references" / "lessons-schema.md"
LESSON_TEMPLATE = PLUGIN / "templates" / "lesson.md"
LESSONS_HANDLER = PLUGIN / "handlers" / "lessons.md"
CURATE_REF = PLUGIN / "references" / "lessons-curate-workflow.md"
CONFIG_TEMPLATE = PLUGIN / "config.yaml.template"
MIGRATION_E2E = HERE / "test_lessons_migration_e2e.py"

TARGETS = set(lessons_index_schema.PROMOTION_TARGETS)
ORIGINS = tuple(lessons_index_schema.LESSON_ORIGINS)
KINDS = set(config_loader.DEFAULT_LESSON_CHECK_KINDS)

SIX_VALUE_LINE = "promotion-target: [rule|code|claude-md|agent|skill|settings]"

H_TARGET = "## Promotion Target — Authoritative Definition"
H_MATRIX = "## Resolution Matrix"
H_KINDS = "## Enforcement Answer"
H_CURATE = "### 3.6 Target-Type Classification"
TIP_ANCHOR = "> [!tip] Prefer single-purpose lessons"
STATUS_ANCHOR = "Set the terminal status from the lesson's"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


# --- extractors -----------------------------------------------------------


def section(text: str, heading: str) -> str:
    """The body under `heading`, bounded at the next heading of equal or higher level."""
    match = re.search(r"^" + re.escape(heading) + r"[^\n]*\n", text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"heading not found: {heading!r}")
    level = len(heading) - len(heading.lstrip("#"))
    rest = text[match.end():]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def table_first_cells(text: str, heading: str) -> list[str]:
    """The first backticked cell of each table row under `heading`."""
    return re.findall(r"^\|\s*`([^`]+)`\s*\|", section(text, heading), re.MULTILINE)


def bracket_line_values(text: str) -> set[str]:
    """The values of the literal `promotion-target: [a|b|...]` line."""
    match = re.search(r"^promotion-target: \[([^\]]*)\]", text, re.MULTILINE)
    if match is None:
        raise AssertionError("no promotion-target: [...] line")
    return set(match.group(1).split("|"))


def tip_values(text: str) -> set[str]:
    """The parenthesised list of backticked values in the Capture Step 2 tip."""
    start = text.index(TIP_ANCHOR)
    paragraph = text[start:].split("\n\n", 1)[0]
    match = re.search(r"\(((?:`[a-z-]+`(?:, (?:or )?)?)+)\)", paragraph)
    if match is None:
        raise AssertionError("no parenthesised backticked list in the tip")
    return set(re.findall(r"`([a-z-]+)`", match.group(1)))


def status_mapping_values(text: str) -> set[str]:
    """The union of the parenthesised backticked lists in the status-mapping sentence."""
    start = text.index(STATUS_ANCHOR)
    line = text[start:].split("\n", 1)[0]
    lists = re.findall(r"\(((?:`[a-z-]+`(?:, (?:or )?)?)+)\)", line)
    values: set[str] = set()
    for item in lists:
        values.update(re.findall(r"`([a-z-]+)`", item))
    return values


def origin_brace_values(text: str) -> set[str]:
    """The brace list of the `origin:` line."""
    match = re.search(r"^origin: \{([^}]*)\}", text, re.MULTILINE)
    if match is None:
        raise AssertionError("no origin: {...} line")
    return {part.strip() for part in match.group(1).split("|")}


def config_kinds(text: str) -> list[str]:
    """The ordered `lesson_check_kinds:` list of config.yaml.template."""
    match = re.search(r"^lesson_check_kinds:\n((?:[ \t]+- [A-Za-z_]+[ \t]*\n)+)", text, re.MULTILINE)
    if match is None:
        raise AssertionError("no lesson_check_kinds: block")
    return re.findall(r"- ([A-Za-z_]+)", match.group(1))


# --- helpers --------------------------------------------------------------


def drop_row(text: str, heading: str, value: str) -> str:
    """`text` with the first table row for `value` after `heading` removed."""
    base = text.index(heading)
    start = text.index(f"| `{value}` |", base)
    end = text.index("\n", start)
    return text[:start] + text[end + 1:]


def drop_once(text: str, needle: str, replacement: str = "") -> str:
    assert needle in text, f"known-bad setup: {needle!r} not in text"
    return text.replace(needle, replacement, 1)


class ParityBase(unittest.TestCase):
    def assertSameSet(self, surface: str, got, want) -> None:
        got_set, want_set = set(got), set(want)
        self.assertEqual(
            got_set,
            want_set,
            f"{surface}: extra: {sorted(got_set - want_set)}; missing: {sorted(want_set - got_set)}",
        )

    def assertSameOrder(self, surface: str, got, want) -> None:
        got_list, want_list = list(got), list(want)
        self.assertEqual(
            got_list,
            want_list,
            f"{surface}: extra: {sorted(set(got_list) - set(want_list))}; "
            f"missing: {sorted(set(want_list) - set(got_list))}; order: {got_list} vs {want_list}",
        )


class TestPromotionTargetSurfaces(ParityBase):
    def setUp(self):
        self.schema = read(SCHEMA_REF)
        self.template = read(LESSON_TEMPLATE)
        self.handler = read(LESSONS_HANDLER)
        self.curate = read(CURATE_REF)

    def test_schema_promotion_target_table(self):
        self.assertSameSet("lessons-schema.md Promotion Target table", table_first_cells(self.schema, H_TARGET), TARGETS)

    def test_template_bracket_line(self):
        self.assertSameSet("templates/lesson.md promotion-target line", bracket_line_values(self.template), TARGETS)

    def test_handler_draft_block_bracket_line(self):
        self.assertSameSet("handlers/lessons.md draft block promotion-target line", bracket_line_values(self.handler), TARGETS)

    def test_handler_capture_tip_list(self):
        self.assertSameSet("handlers/lessons.md Capture Step 2 tip", tip_values(self.handler), TARGETS)

    def test_curate_target_type_table(self):
        self.assertSameSet("lessons-curate-workflow.md 3.6 table", table_first_cells(self.curate, H_CURATE), TARGETS)

    def test_curate_status_mapping_sentence(self):
        self.assertSameSet("lessons-curate-workflow.md status-mapping sentence", status_mapping_values(self.curate), TARGETS)


class TestOriginSurfaces(ParityBase):
    def test_schema_resolution_matrix_is_ordered_origins(self):
        self.assertSameOrder("lessons-schema.md Resolution Matrix", table_first_cells(read(SCHEMA_REF), H_MATRIX), ORIGINS)

    def test_template_origin_brace_list(self):
        self.assertSameSet("templates/lesson.md origin line", origin_brace_values(read(LESSON_TEMPLATE)), ORIGINS)


class TestKindSurfaces(ParityBase):
    def test_schema_enforcement_answer_table(self):
        self.assertSameSet("lessons-schema.md Enforcement Answer table", table_first_cells(read(SCHEMA_REF), H_KINDS), KINDS)

    def test_config_template_kinds_ordered(self):
        self.assertSameOrder(
            "config.yaml.template lesson_check_kinds",
            config_kinds(read(CONFIG_TEMPLATE)),
            config_loader.DEFAULT_LESSON_CHECK_KINDS,
        )


class TestFrozenCopies(unittest.TestCase):
    """D13: both copies keep the six-value line and never gain the new keys."""

    def test_seed_body_keeps_six_value_line_and_no_new_keys(self):
        body = migrate_lessons_support.SEED_BODIES["Lesson File Template"]
        self.assertEqual(body.count(SIX_VALUE_LINE), 1, "seed body: six-value line must appear exactly once")
        self.assertNotIn("origin:", body, "seed body: gained an origin: key")
        self.assertNotIn("enforced-by:", body, "seed body: gained an enforced-by: key")

    def test_migration_e2e_keeps_six_value_line(self):
        self.assertIn(SIX_VALUE_LINE, read(MIGRATION_E2E), "test_lessons_migration_e2e.py: six-value line missing")


class TestExtractorDirection(unittest.TestCase):
    """Each extractor, run on a known-bad text with one value removed, sees the smaller set."""

    def setUp(self):
        self.schema = read(SCHEMA_REF)
        self.template = read(LESSON_TEMPLATE)
        self.handler = read(LESSONS_HANDLER)
        self.curate = read(CURATE_REF)
        self.config = read(CONFIG_TEMPLATE)

    def test_schema_target_table_extractor(self):
        mutated = drop_row(self.schema, H_TARGET, "settings")
        self.assertEqual(set(table_first_cells(mutated, H_TARGET)), TARGETS - {"settings"})

    def test_template_bracket_extractor(self):
        mutated = drop_once(self.template, "|settings]", "]")
        self.assertEqual(bracket_line_values(mutated), TARGETS - {"settings"})

    def test_handler_bracket_extractor(self):
        mutated = drop_once(self.handler, "|settings]", "]")
        self.assertEqual(bracket_line_values(mutated), TARGETS - {"settings"})

    def test_handler_tip_extractor(self):
        start = self.handler.index(TIP_ANCHOR)
        head, tail = self.handler[:start], self.handler[start:]
        mutated = head + drop_once(tail, ", or `settings`", "")
        self.assertEqual(tip_values(mutated), TARGETS - {"settings"})

    def test_curate_table_extractor(self):
        mutated = drop_row(self.curate, H_CURATE, "settings")
        self.assertEqual(set(table_first_cells(mutated, H_CURATE)), TARGETS - {"settings"})

    def test_status_mapping_extractor(self):
        start = self.curate.index(STATUS_ANCHOR)
        head, tail = self.curate[:start], self.curate[start:]
        mutated = head + drop_once(tail, "(`code`, `settings`)", "(`code`)")
        self.assertEqual(status_mapping_values(mutated), TARGETS - {"settings"})

    def test_matrix_extractor(self):
        mutated = drop_row(self.schema, H_MATRIX, "other")
        self.assertEqual(table_first_cells(mutated, H_MATRIX), list(ORIGINS[:-1]))

    def test_origin_brace_extractor(self):
        mutated = drop_once(self.template, " | other}", "}")
        self.assertEqual(origin_brace_values(mutated), set(ORIGINS) - {"other"})

    def test_kinds_table_extractor(self):
        mutated = drop_row(self.schema, H_KINDS, "script")
        self.assertEqual(set(table_first_cells(mutated, H_KINDS)), KINDS - {"script"})

    def test_config_kinds_extractor(self):
        mutated = drop_once(self.config, "  - script\n", "")
        self.assertEqual(config_kinds(mutated), list(config_loader.DEFAULT_LESSON_CHECK_KINDS[:-1]))


if __name__ == "__main__":
    unittest.main()
