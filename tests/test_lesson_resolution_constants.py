"""Tests for the resolution vocabulary constants and the two value parsers in
`lessons_index_schema`."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lessons_index_schema as schema

TEMPLATE_VALUE = "[rule|code|claude-md|agent|skill|settings]"
SPACED_TEMPLATE_VALUE = "rule | code | claude-md | agent | skill | settings"


def test_promotion_targets_order():
    assert schema.PROMOTION_TARGETS == (
        "rule", "code", "claude-md", "agent", "skill", "settings",
    )


def test_lesson_origins_order():
    assert schema.LESSON_ORIGINS == (
        "planwise", "owned-tool", "foreign-tool", "model-call", "own-rules", "own-code", "other",
    )


def test_derived_sets_are_subsets():
    assert schema.EXECUTABLE_TARGETS == frozenset({"code", "settings"})
    assert schema.EXECUTABLE_TARGETS <= set(schema.PROMOTION_TARGETS)
    assert schema.CODE_ORIGINS == frozenset({"owned-tool", "own-code"})
    assert schema.CODE_ORIGINS <= set(schema.LESSON_ORIGINS)
    assert schema.NO_CHECK == "none"


@pytest.mark.parametrize("value, expected", [
    ("test: tests/test_x.py::test_y", ("test", "tests/test_x.py::test_y")),
    ("hook: .claude/hooks/x.py", ("hook", ".claude/hooks/x.py")),
    ("none: a judgement about prose", ("none", "a judgement about prose")),
    ("none:", ("none", "")),
    ('"hook: .claude/hooks/x.py"', ("hook", ".claude/hooks/x.py")),
    ("'test: a'", ("test", "a")),
    ("Test: a", ("test", "a")),
])
def test_parse_enforced_by_valid(value, expected):
    assert schema.parse_enforced_by(value) == expected


@pytest.mark.parametrize("value", [
    None,
    "",
    "   ",
    "no colon here",
    "test: line one\nline two",
    ": text",
])
def test_parse_enforced_by_returns_none(value):
    assert schema.parse_enforced_by(value) is None


@pytest.mark.parametrize("value, expected", [
    ("[rule]", ["rule"]),
    ("[rule, code]", ["rule", "code"]),
    ("rule", ["rule"]),
    ("Rule", ["rule"]),
    ("'rule', \"code\"", ["rule", "code"]),
    (TEMPLATE_VALUE, ["rule|code|claude-md|agent|skill|settings"]),
    (SPACED_TEMPLATE_VALUE, [SPACED_TEMPLATE_VALUE]),
    ("", []),
    (None, []),
])
def test_split_targets(value, expected):
    assert schema.split_targets(value) == expected


def test_template_value_is_one_token_and_not_a_target():
    for value in (TEMPLATE_VALUE, SPACED_TEMPLATE_VALUE):
        tokens = schema.split_targets(value)
        assert len(tokens) == 1
        assert tokens[0] not in schema.PROMOTION_TARGETS
