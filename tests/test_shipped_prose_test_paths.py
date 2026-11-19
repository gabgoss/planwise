"""Shipped prose that names a plugin test file must say the file is development-only.

A script under `scripts/` ships with the plugin, so a pointer to it needs no
qualifier. A test under the plugin repo's `tests/` folder does not ship. A
consumer who reads an unqualified pointer cannot open the file.

The predicate keys on files that exist under the plugin repo's `tests/` folder.
Example names that a reference gives a consumer to copy (a made-up
`tests/test_adapter.py`) name no real file, so they are exempt.

Pinned run, from the project root:
    python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_shipped_prose_test_paths.py
"""

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = TESTS_DIR.parent / "plugins" / "planwise"

# A tests/ path that starts a token: no word character, slash, dot or hyphen before it.
TEST_PATH = re.compile(r"(?<![\w/.-])tests/[\w/.-]+\.py")
QUALIFIER = re.compile(r"in plugin development|development-only|plugin repo's", re.IGNORECASE)
FENCE = re.compile(r"^[ \t>]*(```|~~~)")


def real_test_file(path):
    """True when the pointer names a file that exists in the plugin repo's tests folder."""
    return (TESTS_DIR / path.split("/", 1)[1]).is_file()


def unqualified_pointers(line, exists=real_test_file):
    """The tests/ pointers on one prose line that name a real file and carry no qualifier."""
    if QUALIFIER.search(line):
        return []
    return [m.group(0) for m in TEST_PATH.finditer(line) if exists(m.group(0))]


def prose_lines(text):
    """Yield (line number, line) for every line outside a fenced block."""
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, line


def scan(root=PLUGIN_ROOT, exists=real_test_file):
    """Return (files walked, offending 'relative path:line: pointer' strings)."""
    walked = 0
    offenders = []
    for md in sorted(root.rglob("*.md")):
        walked += 1
        text = md.read_text(encoding="utf-8")
        for number, line in prose_lines(text):
            for pointer in unqualified_pointers(line, exists):
                offenders.append(f"{md.relative_to(root).as_posix()}:{number}: {pointer}")
    return walked, offenders


def test_shipped_prose_qualifies_every_test_pointer():
    walked, offenders = scan()
    assert walked > 0, "the walk saw no markdown files, so an empty result proves nothing"
    assert offenders == [], "unqualified pointers to unshipped test files:\n" + "\n".join(offenders)


WRONG_LINE = (
    "`tests/test_import_order.py` imports each globbed `scripts/*.py` module first "
    "in its own fresh `python -B` subprocess."
)
CORRECT_LINE = "In plugin development, " + WRONG_LINE


def always(path):
    """Stand-in for a real test file: every tests/ pointer counts."""
    return path.startswith("tests/")


def never(path):
    """Stand-in for a consumer example: no pointer names a real file."""
    return path == ""


def test_wrong_line_fails_the_predicate():
    assert unqualified_pointers(WRONG_LINE, always) == ["tests/test_import_order.py"]


def test_corrected_line_passes_the_predicate():
    assert unqualified_pointers(CORRECT_LINE, always) == []


def test_other_qualifiers_pass():
    assert unqualified_pointers("The reachability test is a development-only file, `tests/test_x.py`.", always) == []
    assert unqualified_pointers("The plugin repo's `tests/test_x.py` covers it.", always) == []


def test_example_name_with_no_real_file_is_exempt():
    assert unqualified_pointers(WRONG_LINE, never) == []


def test_pointer_inside_a_longer_path_is_not_a_token():
    assert unqualified_pointers("see `plugins/planwise/tests/test_x.py` here", always) == []


def test_fenced_lines_are_skipped_including_quoted_fences():
    text = "plain\n> ```text\n> `tests/test_x.py` here\n> ```\n`tests/test_y.py` after\n"
    lines = [number for number, _ in prose_lines(text)]
    assert lines == [1, 5]


def test_scan_reports_the_pointer_with_its_file_and_line(tmp_path):
    (tmp_path / "ref.md").write_text("ok\n" + WRONG_LINE + "\n", encoding="utf-8")
    walked, offenders = scan(tmp_path, always)
    assert walked == 1
    assert offenders == ["ref.md:2: tests/test_import_order.py"]
