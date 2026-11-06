#!/usr/bin/env python3
"""Every index table in the three verification family indexes must resolve.

Predicate: every file named in an index table exists, and every section number
listed for it has a heading in that file. Each index may hold a ``## Topic
Files`` table, a ``## Section Map`` table, both or neither. The real-tree test
fails when no table survives anywhere, because an empty run proves nothing.

A Section Map row takes exactly one of these shapes:

- ``§N Title | `file.md```: each ``§`` token has a heading in the named file.
- A range ``§N-§M``: both ends have a heading, and so does each number between
  them when the ends share a parent or the first end is the parent of the last.
- ``§N.x``: the named file holds at least one heading under ``N``.
- ``§N Title | this file``: the heading is in the index itself.
- ``§N Title | `file.md` §M (relocated ...)``: the named file holds ``§M``.
- A row saying ``not a former section``: the named file exists, with no heading
  check.
- ``§N Title | redirect table``: skipped with its reason recorded, and the
  checker's redirect table must hold ``§N``.

A cell no rule classifies is a failure carrying the cell text, because a
skipped unknown shape would pass a broken index.

Run with:  python -m pytest -q tests/test_verification_index_tables.py
"""

import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_section_citations import REDIRECTS
from markdown_parser import extract_headings, numbered_heading_index, split_row_cells

REFERENCES = SCRIPTS.parent / "references"
INDEXES = ("verification-gates.md", "verification-gate-evidence.md", "verification-task-authoring.md")

_NUM = r"[0-9]+[a-z]?(?:\.[0-9A-Za-z]+)*"
_SECTION_RE = re.compile(rf"§({_NUM})(?:-§?({_NUM}))?")
_FILE_RE = re.compile(r"[A-Za-z0-9_.-]+\.md")


def _numbers(path: Path) -> set[str]:
    return set(numbered_heading_index(extract_headings(path.read_text(encoding="utf-8"))))


def _expand(low: str, high: str) -> list[str]:
    """List the numbers a range names: its ends, plus any it enumerates."""
    first, last = low.split("."), high.split(".")
    if not all(part.isdigit() for part in first + last):
        return [low, high]
    if len(first) == len(last) and first[:-1] == last[:-1]:
        stem = ".".join(first[:-1] + [""])
        return [f"{stem}{n}" for n in range(int(first[-1]), int(last[-1]) + 1)]
    if last[: len(first)] == first and len(last) == len(first) + 1:
        return [low] + [f"{low}.{n}" for n in range(1, int(last[-1]) + 1)]
    return [low, high]


def _missing_sections(cell: str, numbers: set[str]) -> list[str]:
    """Return each section ``cell`` lists that ``numbers`` does not hold."""
    missing = []
    for low, high in _SECTION_RE.findall(cell):
        if low.endswith(".x"):
            prefix = low[:-1]
            if not any(number.startswith(prefix) for number in numbers):
                missing.append(f"§{low}")
            continue
        for number in _expand(low, high) if high else [low]:
            if number not in numbers:
                missing.append(f"§{number}")
    return missing


def _redirect_holds(name: str, section: str, redirects) -> bool:
    key = section
    while True:
        if (name, key) in redirects:
            return True
        if "." not in key:
            return False
        key = key.rsplit(".", 1)[0]


def _check_file(name: str, cell: str, references: Path) -> tuple[list[str], str]:
    """Return ``(problems, name)``, with ``name`` empty when the file is missing."""
    if not (references / name).is_file():
        return [f"names a missing file {name}: {cell}"], ""
    return [], name


def _check_map_row(cells: list[str], index: Path, references: Path, redirects) -> tuple[list[str], list[str]]:
    """Classify one Section Map row. Return ``(problems, skips)``."""
    if len(cells) != 2:
        return [f"unclassified row: {' | '.join(cells)}"], []
    former, target = cells
    names = _FILE_RE.findall(target)
    if "not a former section" in former or "not a former section" in target:
        if not names:
            return [f"unclassified row: {former} | {target}"], []
        return _check_file(names[0], target, references)[0], []
    if not _SECTION_RE.search(former):
        return [f"unclassified row: {former} | {target}"], []
    if "redirect table" in target:
        sections = [low for low, _ in _SECTION_RE.findall(former)]
        absent = [s for s in sections if not _redirect_holds(index.name, s, redirects)]
        if absent:
            return [f"redirect table lacks {absent} for {index.name}: {former}"], []
        return [], [f"redirect-only row, the checker's table holds it: {former}"]
    if target.startswith("this file"):
        problems = [f"{index.name} has no heading {m}: {former}" for m in _missing_sections(former, _numbers(index))]
        for name in names:
            problems += _check_file(name, target, references)[0]
        return problems, []
    if "relocated" in target and names:
        problems, found = _check_file(names[0], target, references)
        if found:
            problems = [f"{found} has no heading {m}: {target}"
                        for m in _missing_sections(target, _numbers(references / found))]
        return problems, []
    if len(names) == 1 and target.strip("`") == names[0]:
        problems, found = _check_file(names[0], target, references)
        if found:
            problems = [f"{found} has no heading {m}: {former}"
                        for m in _missing_sections(former, _numbers(references / found))]
        return problems, []
    return [f"unclassified row: {former} | {target}"], []


def _check_topic_row(cells: list[str], references: Path) -> list[str]:
    """Classify one Topic Files row: a named file, its sections, its read-when."""
    names = _FILE_RE.findall(cells[0]) if cells else []
    if len(cells) != 3 or not names or not cells[2] or not _SECTION_RE.search(cells[1]):
        return [f"unclassified row: {' | '.join(cells)}"]
    problems, found = _check_file(names[0], cells[0], references)
    if found:
        numbers = _numbers(references / found)
        problems = [f"{found} has no heading {m}: {cells[1]}" for m in _missing_sections(cells[1], numbers)]
    return problems


def _table_rows(text: str, title: str) -> list[list[str]]:
    """Return the data rows of the table under the ``## title`` heading."""
    headings = extract_headings(text)
    lines = text.replace("\r\n", "\n").split("\n")
    for position, heading in enumerate(headings):
        if heading.level == 2 and heading.title == title:
            end = headings[position + 1].line - 1 if position + 1 < len(headings) else len(lines)
            table = [ln for ln in lines[heading.line:end] if ln.startswith("|")]
            return [split_row_cells(ln) for ln in table[2:]]
    return []


def check_index(index: Path, references: Path, redirects=REDIRECTS) -> tuple[list[str], list[str], int]:
    """Check one index file. Return ``(problems, skips, rows read)``."""
    text = index.read_text(encoding="utf-8")
    problems: list[str] = []
    skips: list[str] = []
    topic_rows = _table_rows(text, "Topic Files")
    map_rows = _table_rows(text, "Section Map")
    for cells in topic_rows:
        problems += _check_topic_row(cells, references)
    for cells in map_rows:
        row_problems, row_skips = _check_map_row(cells, index, references, redirects)
        problems += row_problems
        skips += row_skips
    return problems, skips, len(topic_rows) + len(map_rows)


def check_tree(references: Path, redirects=REDIRECTS) -> tuple[list[str], list[str], int]:
    """Check every family index under ``references``."""
    problems: list[str] = []
    skips: list[str] = []
    rows = 0
    for name in INDEXES:
        index = references / name
        if not index.is_file():
            problems.append(f"family index is missing: {name}")
            continue
        got = check_index(index, references, redirects)
        problems += [f"{name}: {problem}" for problem in got[0]]
        skips += got[1]
        rows += got[2]
    return problems, skips, rows


def test_every_surviving_index_table_resolves_in_the_shipped_tree():
    problems, _, rows = check_tree(REFERENCES)
    assert rows > 0, "no index table survives: the check read nothing"
    assert problems == []


# ------------------------------------------------------------------ fixtures

TOPIC = "## 1. One\n\n## 2. Two\n\n### 2.1 Sub\n\n### 2.2 Sub\n\n## 3. Three\n"
INDEX = "# Index\n\n{topic}## Section Map\n\n| Former section | Now in |\n|---|---|\n{row}\n\n## 9. Kept\n"
TOPIC_TABLE = "## Topic Files\n\n| File | Sections | Read when |\n|---|---|---|\n{row}\n\n"
FAKE_REDIRECTS = {("index.md", "7"): None}


def _tree(tmp_path: Path, row: str, topic_row: str = "") -> Path:
    references = tmp_path / "references"
    references.mkdir(parents=True)
    (references / "topic.md").write_text(TOPIC, encoding="utf-8")
    topic = TOPIC_TABLE.format(row=topic_row) if topic_row else ""
    (references / "index.md").write_text(INDEX.format(topic=topic, row=row), encoding="utf-8")
    return references


def _check(references: Path) -> tuple[list[str], list[str], int]:
    return check_index(references / "index.md", references, FAKE_REDIRECTS)


MAP_SHAPES = [
    pytest.param("| §1 One | `topic.md` |", "| §4 One | `topic.md` |", id="plain"),
    pytest.param("| §1 One, §2-§3 | `topic.md` |", "| §1 One, §2-§4 | `topic.md` |", id="range"),
    pytest.param("| §2 Two, §2.1-§2.2 | `topic.md` |", "| §2 Two, §2.1-§2.3 | `topic.md` |", id="subsection-range"),
    pytest.param("| §2-§2.2 | `topic.md` |", "| §2-§2.3 | `topic.md` |", id="parent-range"),
    pytest.param("| §2.x | `topic.md` |", "| §3.x | `topic.md` |", id="placeholder-range"),
    pytest.param("| §9 Kept | this file |", "| §8 Kept | this file |", id="this-file"),
    pytest.param("| §9 Kept | this file (pointer to `topic.md`) |", "| §9 Kept | this file (pointer to `gone.md`) |",
                 id="this-file-pointer"),
    pytest.param("| §6 Moved | `topic.md` §2 (relocated earlier) |", "| §6 Moved | `topic.md` §5 (relocated earlier) |",
                 id="relocated"),
    pytest.param("| §1 One | `topic.md` |", "| §1 One | `gone.md` |", id="missing-file"),
    pytest.param("| (not a former section) | `topic.md` |", "| (not a former section) | `gone.md` |",
                 id="not-a-former-section"),
    pytest.param("| §7 Moved | redirect table |", "| §6 Moved | redirect table |", id="redirect-only"),
]


@pytest.mark.parametrize("good, bad", MAP_SHAPES)
def test_each_map_row_shape_passes_good_and_fails_bad(tmp_path, good, bad):
    problems, _, rows = _check(_tree(tmp_path / "good", good))
    assert (problems, rows) == ([], 1)
    problems, _, rows = _check(_tree(tmp_path / "bad", bad))
    assert rows == 1 and len(problems) >= 1


def test_redirect_only_row_records_its_reason(tmp_path):
    _, skips, _ = _check(_tree(tmp_path, "| §7 Moved | redirect table |"))
    assert skips == ["redirect-only row, the checker's table holds it: §7 Moved"]


@pytest.mark.parametrize(
    "row",
    [
        pytest.param("| Some title | `topic.md` |", id="no-section-sign"),
        pytest.param("| §1 One | see the topic file |", id="no-target-file"),
        pytest.param("| §1 One | `topic.md` | extra |", id="three-cells"),
        pytest.param("| §1 One | `topic.md` and `other.md` |", id="two-target-files"),
    ],
)
def test_an_unclassified_map_cell_fails_with_its_text(tmp_path, row):
    problems, _, _ = _check(_tree(tmp_path, row))
    assert len(problems) == 1 and problems[0].startswith("unclassified row: ")
    assert "§1 One" in problems[0] or "Some title" in problems[0]


TOPIC_SHAPES = [
    pytest.param("| [topic.md](topic.md) | §1-§3, Check 001 | you write a gate |", True, id="good"),
    pytest.param("| [gone.md](gone.md) | §1 | you write a gate |", False, id="missing-file"),
    pytest.param("| [topic.md](topic.md) | §1-§5 | you write a gate |", False, id="missing-section"),
    pytest.param("| [topic.md](topic.md) | Check 001 | you write a gate |", False, id="no-section"),
    pytest.param("| no file here | §1 | you write a gate |", False, id="no-file-cell"),
]


@pytest.mark.parametrize("row, clean", TOPIC_SHAPES)
def test_each_topic_row_shape(tmp_path, row, clean):
    problems, _, rows = _check(_tree(tmp_path, "| §1 One | `topic.md` |", row))
    assert rows == 2
    assert (problems == []) is clean


def test_a_known_bad_index_fails_the_tree_check(tmp_path):
    references = _tree(tmp_path, "| §1 One | `gone.md` |", "| [topic.md](topic.md) | §8 | you write a gate |")
    (references / "index.md").rename(references / "verification-gates.md")
    (references / "verification-gate-evidence.md").write_text("# Stub\n", encoding="utf-8")
    (references / "verification-task-authoring.md").write_text("# No tables\n", encoding="utf-8")
    problems, _, rows = check_tree(references)
    assert rows == 2
    assert any("gone.md" in problem for problem in problems)
    assert any("§8" in problem for problem in problems)


def test_no_surviving_table_is_visible_as_zero_rows(tmp_path):
    references = tmp_path / "references"
    references.mkdir()
    for name in INDEXES:
        (references / name).write_text("# Stub\n", encoding="utf-8")
    assert check_tree(references) == ([], [], 0)


def test_a_missing_family_index_is_a_problem(tmp_path):
    references = tmp_path / "references"
    references.mkdir()
    assert len(check_tree(references)[0]) == len(INDEXES)
