#!/usr/bin/env python3
"""Flag a plugin test that reads a path above the plugin repo root.

The plugin repo ships on its own. A test that climbs out of the repo with
`Path(__file__).resolve().parents[N]` (or the same height of `.parent` hops)
reads a file the plugin repo does not hold. Outside the authoring project that
file is absent, and a `skipUnless` guard turns the test into a silent skip.

`outer_reads(root)` walks every `<root>/tests/**/*.py` except `tests/fixtures/`
and reports each file that climbs above `root`. The real-tree test requires the
flagged set to equal a reviewed allowlist exactly, so a new outer read and a
stale allowlist entry both fail. Each skip guard in an allowlisted file must
name the checkout state in its reason.

Dev-only: lives in tests/, which does not ship.

Run with:  python -m pytest tests/test_outer_repo_reads.py -q -rs
"""

import ast
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

PLUGIN_REPO = Path(__file__).resolve().parents[1]

# Reviewed outer reads. Each key is a test file that reads above the repo root
# on purpose, because its subject lives in the authoring project. The value
# names that subject. Re-review the list whenever it changes.
ALLOWED_OUTER_READS = {
    "tests/test_section_citations.py": "living source: outer .claude/rules/ and CLAUDE.md",
}

# Every skip guard in an allowlisted file names the checkout state in its reason.
SKIP_REASON_PHRASE = "checked out alone"

SKIP_NAMES = {"skipUnless", "skipIf", "skipif"}

# The fixture folder holds sample trees, not tests, so the walk leaves it out.
EXCLUDED_DIRS = ("tests/fixtures/",)


class Walk(NamedTuple):
    scanned: int
    flagged: dict
    unparsed: list


def _reads_file(node):
    """True when the expression is built from `__file__`."""
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


def _parent_hops(node):
    """Count consecutive `.parent` attributes ending at this node, and return the base."""
    hops = 0
    while isinstance(node, ast.Attribute) and node.attr == "parent":
        hops += 1
        node = node.value
    return hops, node


def outer_reads_in_source(source, depth):
    """Return the line numbers where the source climbs above the repo root.

    `depth` is the number of path parts of the file below the root, so
    `tests/test_x.py` has depth 2. Index N of `parents` is N + 1 hops up from the
    file. The file's directory is index 0 and the root is index depth - 1, so any
    index of depth or more is above the root.
    """
    first_outside = depth
    lines = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Subscript):
            target = node.value
            index = node.slice
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "parents"
                and _reads_file(target.value)
                and isinstance(index, ast.Constant)
                and isinstance(index.value, int)
                and index.value >= first_outside
            ):
                lines.add(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "parent":
            hops, base = _parent_hops(node)
            if _reads_file(base) and hops - 1 >= first_outside:
                lines.add(node.lineno)
    return sorted(lines)


def skip_reasons(source):
    """Return the reason text of every skip guard in the source, or None when unreadable."""
    reasons = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in SKIP_NAMES:
            continue
        reason = None
        for keyword in node.keywords:
            if keyword.arg == "reason":
                reason = keyword.value
        if reason is None and len(node.args) > 1:
            reason = node.args[1]
        if isinstance(reason, ast.Constant) and isinstance(reason.value, str):
            reasons.append(reason.value)
        else:
            reasons.append(None)
    return reasons


def outer_reads(root):
    """Walk `<root>/tests/**/*.py` and return what climbs above `root`."""
    root = Path(root)
    scanned = 0
    flagged = {}
    unparsed = []
    for path in sorted((root / "tests").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(folder) for folder in EXCLUDED_DIRS):
            continue
        scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
            hits = outer_reads_in_source(source, len(path.relative_to(root).parts))
        except (SyntaxError, UnicodeDecodeError):
            unparsed.append(rel)
            continue
        if hits:
            flagged[rel] = hits
    return Walk(scanned, flagged, unparsed)


KNOWN_BAD = (
    "import unittest\n"
    "from pathlib import Path\n"
    'CONTRACT = Path(__file__).resolve().parents[3] / "x.md"\n'
    '@unittest.skipUnless(CONTRACT.is_file(), "outside")\n'
    "class T(unittest.TestCase):\n"
    "    pass\n"
)

KNOWN_GOOD = (
    "import unittest\n"
    "from pathlib import Path\n"
    'CONTRACT = Path(__file__).resolve().parents[1] / "x.md"\n'
    '@unittest.skipUnless(CONTRACT.is_file(), "outside")\n'
    "class T(unittest.TestCase):\n"
    "    pass\n"
)


class TestKnownArms(unittest.TestCase):
    def test_known_bad_outer_read_is_flagged(self):
        self.assertEqual([3], outer_reads_in_source(KNOWN_BAD, depth=2))

    def test_known_good_repo_read_is_not_flagged(self):
        self.assertEqual([], outer_reads_in_source(KNOWN_GOOD, depth=2))

    def test_parent_hops_are_read_at_the_same_height(self):
        two = "from pathlib import Path\nX = Path(__file__).resolve().parent.parent\n"
        three = "from pathlib import Path\nX = Path(__file__).resolve().parent.parent.parent\n"
        self.assertEqual([], outer_reads_in_source(two, depth=2))
        self.assertEqual([2], outer_reads_in_source(three, depth=2))

    def test_depth_moves_the_root(self):
        source = "from pathlib import Path\nX = Path(__file__).parents[2]\n"
        self.assertEqual([], outer_reads_in_source(source, depth=3))
        self.assertEqual([2], outer_reads_in_source(source, depth=2))

    def test_unrelated_parents_index_is_not_flagged(self):
        source = "X = other.parents[9]\nY = some.parent.parent.parent.parent\n"
        self.assertEqual([], outer_reads_in_source(source, depth=2))

    def test_skip_reason_reader_sees_both_decorator_shapes(self):
        source = (
            "import pytest, unittest\n"
            '@unittest.skipUnless(True, "plugin repo checked out alone")\n'
            "def a(): pass\n"
            '@pytest.mark.skipif(True, reason="elsewhere")\n'
            "def b(): pass\n"
        )
        self.assertEqual(["plugin repo checked out alone", "elsewhere"], skip_reasons(source))

    def test_bad_arm_skip_reason_lacks_the_phrase(self):
        self.assertEqual(["outside"], skip_reasons(KNOWN_BAD))
        self.assertNotIn(SKIP_REASON_PHRASE, skip_reasons(KNOWN_BAD)[0])


class TestPlantedFile(unittest.TestCase):
    def test_a_planted_outer_read_and_the_fixtures_folder(self):
        with tempfile.TemporaryDirectory() as scratch:
            tests = Path(scratch) / "tests"
            (tests / "fixtures").mkdir(parents=True)
            (tests / "test_ok.py").write_text(KNOWN_GOOD, encoding="utf-8")
            (tests / "test_probe_outer.py").write_text(KNOWN_BAD, encoding="utf-8")
            (tests / "fixtures" / "sample.py").write_text(KNOWN_BAD, encoding="utf-8")
            (tests / "test_broken.py").write_text("def (:\n", encoding="utf-8")
            walk = outer_reads(scratch)
        self.assertEqual(3, walk.scanned)
        self.assertEqual({"tests/test_probe_outer.py": [3]}, walk.flagged)
        self.assertEqual(["tests/test_broken.py"], walk.unparsed)


class TestRealTree(unittest.TestCase):
    def test_flagged_set_equals_the_allowlist(self):
        walk = outer_reads(PLUGIN_REPO)
        self.assertGreater(walk.scanned, 0, "the walk saw no test files")
        self.assertEqual([], walk.unparsed, f"test files the walk could not parse: {walk.unparsed}")
        self.assertEqual(
            sorted(ALLOWED_OUTER_READS),
            sorted(walk.flagged),
            "tests that read above the plugin repo root differ from the reviewed list",
        )

    def test_allowlisted_skip_guards_name_the_checkout_state(self):
        for rel in ALLOWED_OUTER_READS:
            with self.subTest(file=rel):
                source = (PLUGIN_REPO / rel).read_text(encoding="utf-8")
                reasons = skip_reasons(source)
                self.assertTrue(reasons, f"{rel} holds no skip guard, so the outer read is unguarded")
                for reason in reasons:
                    self.assertIsNotNone(reason, f"{rel} has a skip guard whose reason is not a literal")
                    self.assertIn(SKIP_REASON_PHRASE, reason)


if __name__ == "__main__":
    unittest.main()
