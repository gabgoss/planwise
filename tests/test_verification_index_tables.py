#!/usr/bin/env python3
"""Every index table in the three verification family indexes must resolve.

Predicate: every file named in an index table exists, and every section number
listed for it has a heading in that file. Each index may hold a ``## Topic
Files`` table, a ``## Section Map`` table, both or neither. The real-tree test
compares the rows read per table with ``EXPECTED_ROWS``, so one table cannot
vanish unseen. A section whose lines hold pipes but give no row fails too.

A Section Map row takes exactly one of these shapes:

- ``§N Title | `file.md```: each ``§`` token has a heading in the named file.
- A range ``§N-§M``, ``§N–§M`` or the shorthand ``§10.1-2``: both ends have a
  heading, and so does each number between them when the ends share a parent or
  the first end is the parent of the last. An inverted range fails.
- ``§N.x``: the named file holds at least one heading under ``N``. Such a range
  still checks its other end.
- ``§N Title | this file``: the heading is in the index itself.
- ``§N Title | `file.md` §M (relocated ...)``: the named file holds ``§M``.
- A row saying ``not a former section``: the named file exists, with no heading
  check.
- ``§N Title | redirect table``, the bare cell: skipped with its reason recorded,
  and the checker's redirect table must hold every number the row lists.

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

import check_section_citations as csc
from markdown_parser import extract_headings, numbered_heading_index, split_row_cells

REFERENCES = SCRIPTS.parent / "references"
INDEXES = ("verification-gates.md", "verification-gate-evidence.md", "verification-task-authoring.md")
TITLES = ("Topic Files", "Section Map")

# The rows of each table, read by hand from the shipped files and not through
# this parser. 0 means the table left. Re-pin when a table gains, loses or drops
# rows, in the task that edits the index.
EXPECTED_ROWS = {
    ("verification-gates.md", "Topic Files"): 0,
    ("verification-gates.md", "Section Map"): 12,
    ("verification-gate-evidence.md", "Topic Files"): 0,
    ("verification-gate-evidence.md", "Section Map"): 0,
    ("verification-task-authoring.md", "Topic Files"): 8,
    ("verification-task-authoring.md", "Section Map"): 0,
}

_FILE_RE = re.compile(r"[A-Za-z0-9_./-]+\.md")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)#\s]+)(?:#[^)\s]*)?\)")
_RELOCATED_RE = re.compile(rf"`([^`]+\.md)`[ \t]+§[ \t]?({csc._TOKEN})[ \t]+\(relocated\b[^)]*\)")
_SEPARATOR_RE = re.compile(r"^\|[ \t:|-]+\|?[ \t]*$")


def _numbers(path: Path) -> set[str]:
    return set(numbered_heading_index(extract_headings(path.read_text(encoding="utf-8"))))


def _is_placeholder(token: str) -> bool:
    return any(segment in csc._PLACEHOLDER_SEGMENTS for segment in token.split(".")[1:])


def _range_end(low: str, end: str, signed: bool) -> str:
    """Return a range's whole last number: a bare ``§10.1-2`` ends at ``10.2``."""
    first, last = low.split("."), end.split(".")
    if signed or len(last) >= len(first):
        return end
    return ".".join(first[: len(first) - len(last)] + last)


def _expand(low: str, high: str) -> tuple[list[str], bool]:
    """Return the numbers a range names and whether it is inverted.

    The list always holds both ends. Only the final segments need be digits, and
    the prefixes compare as strings, so ``9.B.1`` to ``9.B.3`` enumerates.
    """
    first, last = low.split("."), high.split(".")
    if _is_placeholder(low) or _is_placeholder(high) or not last[-1].isdigit():
        return [low, high], False
    if len(first) == len(last) and first[:-1] == last[:-1] and first[-1].isdigit():
        start, stop = int(first[-1]), int(last[-1])
        if start > stop:
            return [low, high], True
        stem = ".".join(first[:-1] + [""])
        return [f"{stem}{n}" for n in range(start, stop + 1)], False
    if last[: len(first)] == first and len(last) == len(first) + 1:
        return [low] + [f"{low}.{n}" for n in range(1, int(last[-1]) + 1)], False
    return [low, high], False


def _sections(cell: str) -> tuple[list[str], list[str]]:
    """Return every number ``cell`` lists, and each inverted range it holds.

    The citation checker's own token and range forms read the cell, so this test
    and the checker agree on what a citation is.
    """
    numbers: list[str] = []
    inverted: list[str] = []
    consumed = 0
    for match in csc._NUMBERED_RE.finditer(cell):
        if match.start() < consumed:
            continue
        low = match.group(1)
        end = csc._RANGE_END_RE.match(cell, match.end())
        if end is None:
            numbers.append(low)
            continue
        consumed = end.end()
        high = _range_end(low, end.group(1), "§" in end.group(0))
        listed, backwards = _expand(low, high)
        numbers += listed
        if backwards:
            inverted.append(f"§{low}-§{high}")
    return numbers, inverted


def _holds(number: str, numbers: set[str]) -> bool:
    if not _is_placeholder(number):
        return number in numbers
    segments = number.split(".")
    stop = next(i for i, part in enumerate(segments) if i and part in csc._PLACEHOLDER_SEGMENTS)
    prefix = ".".join(segments[:stop]) + "."
    return any(held.startswith(prefix) for held in numbers)


def _file_problems(names: list[str], cell: str, references: Path) -> list[str]:
    return [f"names a missing file {name}: {cell}" for name in names if not (references / name).is_file()]


def _section_problems(name: str, cell: str, references: Path) -> list[str]:
    """Check that ``name`` exists and holds every section ``cell`` lists."""
    problems = _file_problems([name], cell, references)
    if problems:
        return problems
    held = _numbers(references / name)
    listed, inverted = _sections(cell)
    problems = [f"{name} has no heading §{number}: {cell}" for number in listed if not _holds(number, held)]
    return problems + [f"{name}: inverted range {span}: {cell}" for span in inverted]


def _redirect_problems(index: Path, former: str) -> list[str]:
    """Check that the checker's redirect table holds every section ``former`` lists."""
    listed, inverted = _sections(former)
    absent = [number for number in listed if csc._redirect_entry(index.name, number)[0] is None]
    problems = [f"redirect table lacks {absent} for {index.name}: {former}"] if absent else []
    return problems + [f"{index.name}: inverted range {span}: {former}" for span in inverted]


def _check_map_row(cells: list[str], index: Path, references: Path) -> tuple[list[str], list[str]]:
    """Classify one Section Map row. Return ``(problems, skips)``."""
    unclassified = [f"unclassified row: {' | '.join(cells)}"]
    if len(cells) != 2:
        return unclassified, []
    former, target = cells
    names = _FILE_RE.findall(target)
    if "not a former section" in former or "not a former section" in target:
        return (_file_problems(names, target, references) if names else unclassified), []
    if not csc._NUMBERED_RE.search(former):
        return unclassified, []
    if target == "redirect table":
        problems = _redirect_problems(index, former)
        return problems, [] if problems else [f"redirect-only row, the checker's table holds it: {former}"]
    if target.startswith("this file"):
        return _section_problems(index.name, former, index.parent) + _file_problems(names, target, references), []
    relocated = _RELOCATED_RE.fullmatch(target)
    if relocated:
        moved = _section_problems(relocated.group(1), f"§{relocated.group(2)}", references)
        return moved + _file_problems(names[1:], target, references), []
    if len(names) == 1 and target.strip("`") == names[0]:
        return _section_problems(names[0], former, references), []
    return unclassified, []


def _check_topic_row(cells: list[str], references: Path) -> list[str]:
    """Classify one Topic Files row: a named file, its sections, its read-when.

    A link is read from its target, kept as a path. Its label must name the same
    file.
    """
    unclassified = [f"unclassified row: {' | '.join(cells)}"]
    if len(cells) != 3 or not cells[2] or not csc._NUMBERED_RE.search(cells[1]):
        return unclassified
    links = _LINK_RE.findall(cells[0])
    names = _FILE_RE.findall(cells[0])
    if len(links) == 1:
        label, name = links[0]
        if Path(label.strip("`")).name != Path(name).name:
            return [f"link label disagrees with its target: {cells[0]}"]
    elif not links and len(names) == 1:
        name = names[0]
    else:
        return unclassified
    return _section_problems(name, cells[1], references)


def _rows_of(section: list[str], title: str) -> tuple[list[list[str]], list[str]]:
    """Return the data rows of ``section``, and a problem per line a table hides."""
    rows: list[list[str]] = []
    run: list[str] = []
    for line in [*section, ""]:
        if line.startswith("|"):
            run.append(line)
        elif run:
            has_header = len(run) > 1 and _SEPARATOR_RE.match(run[1])
            rows += [split_row_cells(row) for row in (run[2:] if has_header else run)]
            run = []
    piped = [line for line in section if "|" in line]
    if not rows:
        return rows, [f"## {title} holds pipes but no table rows: {piped[0]}"] if piped else []
    quoted = [line for line in piped if line.lstrip().startswith(">")]
    return rows, [f"## {title} holds a blockquoted table line: {line}" for line in quoted]


def _table_rows(text: str, title: str) -> tuple[list[list[str]], list[str]]:
    """Read the ``## title`` section, which ends at the next heading of level 2 or lower."""
    headings = extract_headings(text)
    lines = text.replace("\r\n", "\n").split("\n")
    for position, heading in enumerate(headings):
        if heading.level == 2 and heading.title == title:
            later = [h.line for h in headings[position + 1:] if h.level <= 2]
            return _rows_of(lines[heading.line:later[0] - 1 if later else len(lines)], title)
    return [], []


def check_index(index: Path, references: Path) -> tuple[list[str], list[str], dict[str, int]]:
    """Check one index file. Return ``(problems, skips, rows read per table)``."""
    text = index.read_text(encoding="utf-8")
    problems: list[str] = []
    skips: list[str] = []
    tables: dict[str, int] = {}
    for title in TITLES:
        rows, table_problems = _table_rows(text, title)
        problems += table_problems
        tables[title] = len(rows)
        for cells in rows:
            if title == "Topic Files":
                problems += _check_topic_row(cells, references)
                continue
            row_problems, row_skips = _check_map_row(cells, index, references)
            problems += row_problems
            skips += row_skips
    return problems, skips, tables


def check_tree(references: Path) -> tuple[list[str], list[str], dict[tuple[str, str], int]]:
    """Check every family index under ``references``."""
    problems: list[str] = []
    skips: list[str] = []
    tables: dict[tuple[str, str], int] = {}
    for name in INDEXES:
        index = references / name
        if not index.is_file():
            problems.append(f"family index is missing: {name}")
            continue
        got = check_index(index, references)
        problems += [f"{name}: {problem}" for problem in got[0]]
        skips += got[1]
        tables.update({(name, title): rows for title, rows in got[2].items()})
    return problems, skips, tables


def coverage_problems(tables: dict[tuple[str, str], int]) -> list[str]:
    """Compare the rows read per table with ``EXPECTED_ROWS``."""
    return [
        f"{name} ## {title}: expected {rows} rows, read {tables.get((name, title))}"
        for (name, title), rows in EXPECTED_ROWS.items()
        if tables.get((name, title)) != rows
    ]


def test_every_surviving_index_table_resolves_in_the_shipped_tree():
    problems, _, tables = check_tree(REFERENCES)
    assert coverage_problems(tables) == []
    assert problems == []


# ------------------------------------------------------------------ fixtures

TOPIC = "## 1. One\n\n## 2. Two\n\n### 2.1 Sub\n\n### 2.2 Sub\n\n## 3. Three\n"
INDEX = "# Index\n\n{topic}## Section Map\n\n| Former section | Now in |\n|---|---|\n{row}\n\n## 9. Kept\n"
TOPIC_TABLE = "## Topic Files\n\n| File | Sections | Read when |\n|---|---|---|\n{row}\n\n"


@pytest.fixture(autouse=True)
def _fake_redirect(monkeypatch):
    monkeypatch.setitem(csc.REDIRECTS, ("index.md", "7"), csc.Redirect("topic.md", "1", "fixture"))


def _tree(tmp_path: Path, row: str, topic_row: str = "") -> Path:
    references = tmp_path / "references"
    references.mkdir(parents=True)
    (references / "topic.md").write_text(TOPIC, encoding="utf-8")
    topic = TOPIC_TABLE.format(row=topic_row) if topic_row else ""
    (references / "index.md").write_text(INDEX.format(topic=topic, row=row), encoding="utf-8")
    return references


def _check(references: Path) -> tuple[list[str], list[str], int]:
    problems, skips, tables = check_index(references / "index.md", references)
    return problems, skips, sum(tables.values())


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
    problems, _, tables = check_tree(references)
    assert sum(tables.values()) == 2
    assert any("gone.md" in problem for problem in problems)
    assert any("§8" in problem for problem in problems)


def test_no_surviving_table_fails_coverage(tmp_path):
    references = tmp_path / "references"
    references.mkdir()
    for name in INDEXES:
        (references / name).write_text("# Stub\n", encoding="utf-8")
    problems, skips, tables = check_tree(references)
    assert (problems, skips, sum(tables.values())) == ([], [], 0)
    assert len(coverage_problems(tables)) == 2


def test_a_missing_family_index_is_a_problem(tmp_path):
    references = tmp_path / "references"
    references.mkdir()
    assert len(check_tree(references)[0]) == len(INDEXES)


# ---------------------------------------------- false passes a review found

MAP_HEAD = "| Former section | Now in |\n|---|---|\n"


def _body_tree(tmp_path: Path, body: str) -> Path:
    """Build a tree whose index holds ``body`` as written."""
    references = _tree(tmp_path, "| §1 One | `topic.md` |")
    (references / "index.md").write_text(f"# Index\n\n{body}\n## 9. Kept\n", encoding="utf-8")
    return references


def test_a_row_after_a_subheading_is_checked(tmp_path):
    body = f"## Section Map\n\n{MAP_HEAD}| §1 One | `topic.md` |\n\n### Later\n\n{MAP_HEAD}| §4 Gone | `topic.md` |\n"
    problems, _, rows = _check(_body_tree(tmp_path, body))
    assert rows == 2
    assert [p for p in problems if "§4" in p]


def test_a_subheading_does_not_hide_a_row_with_no_header(tmp_path):
    body = f"## Section Map\n\n{MAP_HEAD}| §1 One | `topic.md` |\n\n### Later\n\n| §4 Gone | `topic.md` |\n"
    problems, _, _ = _check(_body_tree(tmp_path, body))
    assert [p for p in problems if "§4" in p]


def test_an_inverted_range_is_a_problem(tmp_path):
    problems, _, _ = _check(_tree(tmp_path, "| §3-§1 | `topic.md` |"))
    assert [p for p in problems if "inverted" in p]


def test_an_inverted_range_in_a_subsection_is_a_problem(tmp_path):
    problems, _, _ = _check(_tree(tmp_path, "| §2.2-§2.1 | `topic.md` |"))
    assert [p for p in problems if "inverted" in p]


@pytest.mark.parametrize(
    "row",
    [
        pytest.param("| §6 Moved | `topic.md` (relocated earlier) |", id="no-target-section"),
        pytest.param("| §6 Moved | `relocated-topic.md` |", id="file-name-holds-the-word"),
        pytest.param("| §6 Moved | `topic.md` §2 (relocated from `gone.md`) |", id="second-file-missing"),
    ],
)
def test_a_row_not_in_the_relocated_shape_fails(tmp_path, row):
    references = _tree(tmp_path, row)
    (references / "relocated-topic.md").write_text(TOPIC, encoding="utf-8")
    problems, _, _ = _check(references)
    assert problems


@pytest.mark.parametrize(
    "row, clean",
    [
        pytest.param("| [topic.md](gone.md) | §1 | you write a gate |", False, id="target-missing"),
        pytest.param("| [topic.md](sub/topic.md) | §1 | you write a gate |", False, id="target-lacks-the-section"),
        pytest.param("| [topic.md](sub/topic.md) | §5 | you write a gate |", True, id="target-holds-the-section"),
        pytest.param("| [sub/topic.md](sub/topic.md) | §5 | you write a gate |", True, id="path-label"),
        pytest.param("| [gone.md](topic.md) | §1 | you write a gate |", False, id="label-disagrees"),
    ],
)
def test_a_topic_row_is_read_from_its_link_target(tmp_path, row, clean):
    references = _tree(tmp_path, "| §1 One | `topic.md` |", row)
    (references / "sub").mkdir()
    (references / "sub" / "topic.md").write_text("## 5. Five\n", encoding="utf-8")
    problems, _, _ = _check(references)
    assert (problems == []) is clean


def test_a_map_target_keeps_its_path(tmp_path):
    references = _tree(tmp_path, "| §5 Five | `sub/topic.md` |")
    (references / "sub").mkdir()
    (references / "sub" / "topic.md").write_text("## 5. Five\n", encoding="utf-8")
    assert _check(references)[0] == []


def test_the_redirect_shape_is_the_bare_cell(tmp_path):
    problems, skips, _ = _check(_tree(tmp_path, "| §7 Moved | `gone.md`, see redirect table |"))
    assert problems and skips == []


def test_a_redirect_range_needs_every_number_held(tmp_path, monkeypatch):
    problems, _, _ = _check(_tree(tmp_path / "bad", "| §7-§9 | redirect table |"))
    assert [p for p in problems if "'8'" in p and "'9'" in p]
    for number in ("8", "9"):
        monkeypatch.setitem(csc.REDIRECTS, ("index.md", number), csc.Redirect("topic.md", "1", "fixture"))
    problems, skips, _ = _check(_tree(tmp_path / "good", "| §7-§9 | redirect table |"))
    assert problems == [] and len(skips) == 1


def test_a_placeholder_range_checks_its_high_end(tmp_path):
    problems, _, _ = _check(_tree(tmp_path, "| §2.x-§8 | `topic.md` |"))
    assert [p for p in problems if "§8" in p]


@pytest.mark.parametrize(
    "row, missing",
    [
        pytest.param("| §1–§5 | `topic.md` |", "§5", id="en-dash"),
        pytest.param("| §1 – §5 | `topic.md` |", "§5", id="spaced-en-dash"),
        pytest.param("| §1–5 | `topic.md` |", "§5", id="bare-en-dash"),
        pytest.param("| §2.1-3 | `topic.md` |", "§2.3", id="shorthand"),
    ],
)
def test_the_checker_grammar_reaches_a_range_end(tmp_path, row, missing):
    problems, _, _ = _check(_tree(tmp_path, row))
    assert [p for p in problems if missing in p]


def test_an_en_dash_range_checks_the_numbers_between(tmp_path):
    references = _tree(tmp_path, "| §1–§3 | `topic.md` |")
    (references / "topic.md").write_text("## 1. One\n\n## 3. Three\n", encoding="utf-8")
    assert [p for p in _check(references)[0] if "§2" in p]


def test_a_shorthand_range_passes_when_its_end_exists(tmp_path):
    assert _check(_tree(tmp_path, "| §2.1-2 | `topic.md` |"))[0] == []


def test_a_hyphenated_token_is_read_whole(tmp_path):
    references = _tree(tmp_path, "| §3h.untested-axes Axes | `topic.md` |")
    (references / "topic.md").write_text("### 3h.untested-axes Axes\n", encoding="utf-8")
    assert _check(references)[0] == []
    (references / "topic.md").write_text("### 3h.untested Axes\n", encoding="utf-8")
    assert [p for p in _check(references)[0] if "§3h.untested-axes" in p]


@pytest.mark.parametrize(
    "row, headings, missing",
    [
        pytest.param("| §9.B.1-§9.B.3 | `topic.md` |", ("9.B.1", "9.B.3"), "§9.B.2", id="capital-segment"),
        pytest.param("| §3a.1-§3a.3 | `topic.md` |", ("3a.1", "3a.3"), "§3a.2", id="letter-suffix"),
    ],
)
def test_a_range_enumerates_past_a_non_numeric_prefix(tmp_path, row, headings, missing):
    references = _tree(tmp_path, row)
    text = "".join(f"### {number} Title\n\n" for number in headings)
    (references / "topic.md").write_text(text, encoding="utf-8")
    assert [p for p in _check(references)[0] if missing in p]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(f"## Section Map\n\n> {MAP_HEAD.replace(chr(10), chr(10) + '> ')}| §4 Gone | `topic.md` |\n",
                     id="blockquoted"),
        pytest.param(f"## Section Map\n\n{MAP_HEAD}\n", id="header-only"),
        pytest.param("## Topic Files\n\n> | File | Sections | Read when |\n", id="blockquoted-topic"),
    ],
)
def test_a_section_with_pipes_and_no_rows_fails(tmp_path, body):
    problems, _, rows = _check(_body_tree(tmp_path, body))
    assert rows == 0 and problems


def test_a_blockquoted_table_beside_a_real_one_fails(tmp_path):
    body = f"## Section Map\n\n{MAP_HEAD}| §1 One | `topic.md` |\n\n> | §4 Gone | `topic.md` |\n"
    assert _check(_body_tree(tmp_path, body))[0]


def _family_tree(tmp_path: Path, gates: str, authoring: str) -> Path:
    references = _tree(tmp_path, "| §1 One | `topic.md` |")
    (references / "verification-gates.md").write_text(gates, encoding="utf-8")
    (references / "verification-gate-evidence.md").write_text("# Stub\n", encoding="utf-8")
    (references / "verification-task-authoring.md").write_text(authoring, encoding="utf-8")
    return references


TOPIC_ROWS = "".join("| [topic.md](topic.md) | §1 | you write a gate |\n" for _ in range(8))
MAP_ROWS = "".join("| §1 One | `topic.md` |\n" for _ in range(12))


def test_the_tree_gate_passes_when_every_expected_table_holds_its_rows(tmp_path, monkeypatch):
    gates = f"# Gates\n\n## Section Map\n\n{MAP_HEAD}{MAP_ROWS}"
    references = _family_tree(tmp_path, gates, TOPIC_TABLE.format(row=TOPIC_ROWS))
    monkeypatch.setattr(sys.modules[__name__], "REFERENCES", references)
    test_every_surviving_index_table_resolves_in_the_shipped_tree()


def test_one_vanished_table_fails_the_tree_gate(tmp_path, monkeypatch):
    references = _family_tree(tmp_path, "# Gates lost its map\n", TOPIC_TABLE.format(row=TOPIC_ROWS))
    monkeypatch.setattr(sys.modules[__name__], "REFERENCES", references)
    with pytest.raises(AssertionError):
        test_every_surviving_index_table_resolves_in_the_shipped_tree()


def test_the_redirect_branch_calls_the_checker(tmp_path, monkeypatch):
    held = csc.Redirect("topic.md", "1", "fixture")
    monkeypatch.setattr(csc, "_redirect_entry", lambda name, section: (held, ""))
    assert _check(_tree(tmp_path, "| §6 Moved | redirect table |"))[0] == []
