#!/usr/bin/env python3
"""The index budget splitters at their boundary.

Both budget modules (`backlog_index_budget.split_items_to_budget` and
`lessons_index_budget.split_lessons_to_budget`) accept a table when
`body_tokens + wrapper_tokens < budget`. A body whose tokens equal exactly
`budget - wrapper_tokens` is therefore NOT accepted, and a body one token over
is not either. With two or more rows each must split into several leaves
instead of refusing. Only a single row that cannot fit alone is refused.

Each case builds a body of an exact token count: a fixed set of rows plus one
row whose title length is varied a character at a time, measured with the
module's own `_measure`, so the boundary window is the one the production
function computes and not a replica.

Run with:  python -m pytest -q -c pytest.ini tests/test_index_budget_boundary.py
"""

import sys
from pathlib import Path

import pytest

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import backlog_index_budget as bib
import lessons_index_budget as lib
from backlog_index_render import render_table_body
from backlog_index_schema import GeneratorError
from lessons_index_render import _render_lessons_table_body
from lessons_index_schema import LessonsGeneratorError
from test_generate_backlog_index import _make_item
from test_generate_lessons_index import _make_lesson_item

WRAPPER_TOKENS = 50
FIXED_ROWS = 4
MAX_TITLE = 100  # under the 120-character display cap, so each added character adds a byte
TOP_DIR = Path("Backlog")
LESSONS_DIR = Path("LessonsLearned")


def _backlog_items(title_len: int) -> list:
    items = [_make_item(i, title="fixed title for a row") for i in range(1, FIXED_ROWS + 1)]
    items.append(_make_item(FIXED_ROWS + 1, title="x" * title_len))
    return items


def _lesson_items(title_len: int) -> list:
    items = [_make_lesson_item(i, title="fixed title for a row") for i in range(1, FIXED_ROWS + 1)]
    items.append(_make_lesson_item(FIXED_ROWS + 1, title="x" * title_len))
    return items


def _backlog_tokens(items: list) -> int:
    return bib._measure(render_table_body(items, TOP_DIR)[0])[1]


def _lessons_tokens(items: list) -> int:
    return lib._measure(_render_lessons_table_body(items, LESSONS_DIR)[0])[1]


def _lengths_by_tokens(make_items, tokens_of) -> dict:
    """Smallest title length that renders each reachable token count."""
    found: dict = {}
    for length in range(1, MAX_TITLE + 1):
        found.setdefault(tokens_of(make_items(length)), length)
    return found


def _boundary_lengths(make_items, tokens_of) -> tuple:
    """(under, at, over, target): title lengths whose bodies are one token below,
    exactly at, and one token above a target that has both neighbours."""
    by_tokens = _lengths_by_tokens(make_items, tokens_of)
    target = next(t for t in sorted(by_tokens) if t - 1 in by_tokens and t + 1 in by_tokens)
    return by_tokens[target - 1], by_tokens[target], by_tokens[target + 1], target


CASES = {
    "backlog": {
        "make_items": _backlog_items, "tokens_of": _backlog_tokens,
        "split": lambda items, budget, wrapper=WRAPPER_TOKENS: bib.split_items_to_budget(
            items, TOP_DIR, wrapper, budget),
        "refusal": GeneratorError, "id_text": "item 005",
    },
    "lessons": {
        "make_items": _lesson_items, "tokens_of": _lessons_tokens,
        "split": lambda items, budget, wrapper=WRAPPER_TOKENS: lib.split_lessons_to_budget(
            items, LESSONS_DIR, wrapper, budget),
        "refusal": LessonsGeneratorError, "id_text": "lesson LL-005",
    },
}


@pytest.fixture(params=sorted(CASES))
def case(request):
    spec = CASES[request.param]
    under, at, over, target = _boundary_lengths(spec["make_items"], spec["tokens_of"])
    return {**spec, "under": under, "at": at, "over": over,
            "budget": target + WRAPPER_TOKENS}


def test_the_fixture_reaches_an_exact_boundary(case):
    tokens_of, make_items = case["tokens_of"], case["make_items"]
    budget = case["budget"]
    assert tokens_of(make_items(case["at"])) + WRAPPER_TOKENS == budget
    assert tokens_of(make_items(case["under"])) + WRAPPER_TOKENS == budget - 1
    assert tokens_of(make_items(case["over"])) + WRAPPER_TOKENS == budget + 1


def test_a_body_one_token_under_the_boundary_fits_in_one_leaf(case):
    leaves = case["split"](case["make_items"](case["under"]), case["budget"])

    assert len(leaves) == 1


def test_a_body_at_budget_minus_wrapper_splits_instead_of_refusing(case):
    items = case["make_items"](case["at"])

    leaves = case["split"](items, case["budget"])

    assert len(leaves) >= 2
    assert sorted(item["id"] for leaf in leaves for item in leaf[0]) == sorted(
        item["id"] for item in items)
    for _subset, _body, _num_bytes, tokens, _truncated in leaves:
        assert tokens + WRAPPER_TOKENS < case["budget"]


def test_a_body_one_token_over_the_boundary_also_splits(case):
    items = case["make_items"](case["over"])

    leaves = case["split"](items, case["budget"])

    assert len(leaves) >= 2
    for _subset, _body, _num_bytes, tokens, _truncated in leaves:
        assert tokens + WRAPPER_TOKENS < case["budget"]


def test_a_single_row_at_the_boundary_is_refused_naming_its_id(case):
    row = case["make_items"](case["at"])[-1:]
    row_tokens = case["tokens_of"](row)

    # One row with the wrapper reserve equal to the budget cannot shrink further.
    with pytest.raises(case["refusal"]) as caught:
        case["split"](row, row_tokens + WRAPPER_TOKENS, WRAPPER_TOKENS)

    assert case["id_text"] in str(caught.value)
    assert "cannot be reduced by sharding further" in str(caught.value)
