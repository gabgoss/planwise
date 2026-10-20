"""Cross-pin: the draft name regex and the frontmatter key order must agree between
hooks/feedback/names.ts and scripts/feedback_drafts.py, and the slug fixtures must
agree with the Python slugify.

Mutation control: set CDF_PIN_NAMES_TS to the path of an altered copy of names.ts and
the TypeScript side is read from that copy. The shipped test ignores the variable when
it is unset.
"""

import ast
import os
import re
import unittest
from pathlib import Path

import feedback_drafts

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "planwise"
FEEDBACK_PY = PLUGIN / "scripts" / "feedback_drafts.py"
OVERRIDE_ENV = "CDF_PIN_NAMES_TS"

# (title, expected slug): every direct slugOf(...) assertion in feedback-slug.test.ts, in order.
SLUG_FIXTURES = (
    ("Hello, World!", "hello-world"),
    ("  --A__b  ", "a-b"),
    ("CamelCase TITLE", "camelcase-title"),
    ("a" * 50, "a" * 40),
    ("a" * 39 + "!!!b", "a" * 39),
    ("!!!", "untitled"),
    ("", "untitled"),
)
SLUG_TEST_TS = HERE / "hooks" / "feedback-slug.test.ts"

ACCEPTED = ("2026-10-07-draft-bug-a.md", "2026-10-07-draft-idea-z9.md")
REJECTED = ("2026-10-07-bug-a.md", "2026-10-07-draft-note-a.md")


def _names_ts_path() -> Path:
    override = os.environ.get(OVERRIDE_ENV)
    if override:
        return Path(override)
    return PLUGIN / "hooks" / "feedback" / "names.ts"


def _ts_source() -> str:
    return _names_ts_path().read_text(encoding="utf-8")


def _py_source() -> str:
    return FEEDBACK_PY.read_text(encoding="utf-8")


def _ts_regex_body() -> str:
    found = re.search(r"^export const DRAFT_NAME_RE = /(.+)/[a-z]*\s*$", _ts_source(), re.MULTILINE)
    assert found is not None, "DRAFT_NAME_RE literal not found in names.ts"
    return found.group(1)


def _py_regex_body() -> str:
    found = re.search(r'^DRAFT_NAME_RE = re\.compile\(r"(.+)"\)\s*$', _py_source(), re.MULTILINE)
    assert found is not None, "DRAFT_NAME_RE literal not found in feedback_drafts.py"
    return found.group(1)


def _ts_keys() -> list:
    found = re.search(r"^export const FRONTMATTER_KEYS = \[(.+?)\]", _ts_source(), re.MULTILINE)
    assert found is not None, "FRONTMATTER_KEYS literal not found in names.ts"
    return re.findall(r"'([^']*)'", found.group(1))


def _py_keys() -> list:
    found = re.search(r"^FRONTMATTER_KEYS = (\(.+?\))\s*$", _py_source(), re.MULTILINE)
    assert found is not None, "FRONTMATTER_KEYS literal not found in feedback_drafts.py"
    return list(ast.literal_eval(found.group(1)))


def _ts_int(name: str) -> int:
    found = re.search(r"^export const " + name + r" = (\d+)\s*$", _ts_source(), re.MULTILINE)
    assert found is not None, name + " literal not found in names.ts"
    return int(found.group(1))


def _py_int(name: str) -> int:
    found = re.search(r"^" + name + r" = (\d+)\s*$", _py_source(), re.MULTILINE)
    assert found is not None, name + " literal not found in feedback_drafts.py"
    return int(found.group(1))


def _ts_string_expr(expr: str) -> str:
    """Evaluate a TypeScript string expression made of quoted literals, `.repeat(N)` and `+`."""
    out = ""
    for term in expr.split(" + "):
        found = re.fullmatch(r"'([^']*)'(?:\.repeat\((\d+)\))?", term.strip())
        assert found is not None, "unsupported slug fixture term: " + term
        out += found.group(1) * (int(found.group(2)) if found.group(2) else 1)
    return out


def _ts_slug_fixtures() -> list:
    text = SLUG_TEST_TS.read_text(encoding="utf-8")
    pairs = re.findall(r"^\s*assert\.equal\(slugOf\((.+?)\), (.+)\)\s*$", text, re.MULTILINE)
    return [(_ts_string_expr(src), _ts_string_expr(want)) for src, want in pairs]


class DraftPinTest(unittest.TestCase):
    def test_name_regex_is_byte_equal(self):
        self.assertEqual(_ts_regex_body(), _py_regex_body())

    def test_frontmatter_keys_equal_in_order(self):
        ts_keys = _ts_keys()
        self.assertGreater(len(ts_keys), 0)
        self.assertEqual(ts_keys, _py_keys())

    def test_both_patterns_accept_and_reject_samples(self):
        for body in (_ts_regex_body(), _py_regex_body()):
            pattern = re.compile(body)
            for name in ACCEPTED:
                self.assertIsNotNone(pattern.match(name), name)
            for name in REJECTED:
                self.assertIsNone(pattern.match(name), name)

    def test_slug_fixtures_agree_with_python_slugify(self):
        for title, expected in SLUG_FIXTURES:
            self.assertEqual(feedback_drafts.slugify(title), expected, repr(title))

    def test_queue_cap_and_expiry_days_agree(self):
        self.assertEqual(_ts_int("MAX_QUEUED"), _py_int("QUEUE_CAP"))
        self.assertEqual(_ts_int("EXPIRY_DAYS"), _py_int("EXPIRY_DAYS"))

    def test_ts_slug_fixture_table_equals_python_table(self):
        ts_table = _ts_slug_fixtures()
        self.assertGreater(len(ts_table), 0)
        self.assertEqual(ts_table, list(SLUG_FIXTURES))


if __name__ == "__main__":
    unittest.main()
