#!/usr/bin/env python3
"""Pins the delegated part table to the `## 1.N` headings on disk.

Section Map pinned: the part table in `agent-orchestration-delegated.md`, which
`agent-orchestration.md` §11 and every other `agent-orchestration-delegated*.md`
file point at with one pointer line. Each table row names one delegated file and
the `§1.N-§1.M` range that file holds. Callers cite those ranges, so a range that
disagrees with the headings sends a reader to a section the named file does not
contain.

Predicate, read from disk with no copy of any range held here:

  (a) at least one part table exists;
  (b) each row's range equals the set of `## 1.N` heading numbers in the file the
      row names, and the headings across the whole family leave no gap and no
      duplicate;
  (c) every `agent-orchestration-delegated*.md` file on disk is named by a row;
  (d) a family file that holds no table carries a pointer line naming a file
      that does, and so does `agent-orchestration.md`.

The check is layout-agnostic: it finds a table wherever one sits, so it holds for
several copies of the table and for one table plus pointer lines. Every copy of a
row that names the same file must give the same range. The live tree carries one
table, in the base file, and the live-tree test asserts that.

Input: the markdown files under `plugins/planwise/references/`. Exit contract
under pytest: a failed assertion names each mismatched row or file.

Cannot see: a range cited in prose rather than a table row, a table whose file
name is not a markdown link or code span, and the `§` citations elsewhere in the
tree. `scripts/check_section_citations.py` checks those citations, so this test
is not a second resolver.

Run with:  python -m pytest tests/test_delegated_section_citations.py -q
"""

import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from markdown_parser import split_row_cells

REFERENCES = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "references"
BASE_NAME = "agent-orchestration.md"
TABLE_HOME = "agent-orchestration-delegated.md"
FAMILY_GLOB = "agent-orchestration-delegated*.md"

FILE_NAME = re.compile(r"agent-orchestration-delegated[A-Za-z0-9-]*\.md")
RANGE = re.compile(r"§1\.(\d+)\s*[–-]\s*§1\.(\d+)")
HEADING = re.compile(r"^## 1\.(\d+)\b", re.MULTILINE)
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _unfenced(text: str) -> str:
    return FENCE.sub("", text.replace("\r\n", "\n"))


def table_rows(text: str) -> list[tuple[str, int, int]]:
    """Return (file name, first, last) for each table row that names a delegated file with a range."""
    rows = []
    for line in _unfenced(text).split("\n"):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_row_cells(line)
        name = next((m.group(0) for c in cells for m in [FILE_NAME.search(c)] if m), None)
        span = next((m for c in cells for m in [RANGE.search(c)] if m), None)
        if name and span:
            rows.append((name, int(span.group(1)), int(span.group(2))))
    return rows


def heading_numbers(text: str) -> list[int]:
    return [int(n) for n in HEADING.findall(_unfenced(text))]


def table_holders(texts: dict[str, str]) -> set[str]:
    return {holder for holder, text in texts.items() if table_rows(text)}


def problems(texts: dict[str, str], on_disk: list[str]) -> list[str]:
    """Return one line per mismatch. `texts` maps a file name to its text."""
    found: list[str] = []
    ranges: dict[str, set[tuple[int, int]]] = {}
    holds_table: set[str] = set()
    for holder, text in texts.items():
        for name, lo, hi in table_rows(text):
            ranges.setdefault(name, set()).add((lo, hi))
            holds_table.add(holder)
    if not ranges:
        return ["no part table found: no row names a delegated file with a range"]
    for name, spans in sorted(ranges.items()):
        if len(spans) > 1:
            found.append(f"{name}: copies of the table disagree: {sorted(spans)}")
        if name not in texts:
            found.append(f"{name}: a row names a file that is not on disk")
            continue
        numbers = heading_numbers(texts[name])
        for lo, hi in sorted(spans):
            if set(numbers) != set(range(lo, hi + 1)):
                found.append(f"{name}: row range §1.{lo}-§1.{hi} but headings found {sorted(set(numbers))}")
    seen: dict[int, str] = {}
    for name in sorted(on_disk):
        for n in heading_numbers(texts.get(name, "")):
            if n in seen:
                found.append(f"§1.{n} is a heading in both {seen[n]} and {name}")
            seen[n] = name
    if seen:
        gaps = sorted(set(range(min(seen), max(seen) + 1)) - set(seen))
        if gaps:
            found.append(f"no file holds heading(s) §1.{gaps}")
    for name in sorted(on_disk):
        if name not in ranges:
            found.append(f"{name}: on disk but named by no table row")
    for name in sorted(on_disk) + ([BASE_NAME] if BASE_NAME in texts else []):
        if name in holds_table:
            continue
        pointed = {n for n in FILE_NAME.findall(texts.get(name, "")) if n in holds_table}
        if not pointed:
            found.append(f"{name}: holds no table and carries no pointer to a file that does")
    return found


def _live() -> tuple[dict[str, str], list[str]]:
    on_disk = sorted(p.name for p in REFERENCES.glob(FAMILY_GLOB))
    texts = {name: (REFERENCES / name).read_text(encoding="utf-8") for name in on_disk}
    texts[BASE_NAME] = (REFERENCES / BASE_NAME).read_text(encoding="utf-8")
    return texts, on_disk


class TestDelegatedPartTable(unittest.TestCase):
    def test_live_tree_agrees(self):
        texts, on_disk = _live()
        self.assertEqual(problems(texts, on_disk), [])

    def test_live_tree_holds_one_table_in_the_base_file(self):
        texts, _ = _live()
        self.assertEqual(table_holders(texts), {TABLE_HOME})

    def test_the_walk_saw_the_family(self):
        texts, on_disk = _live()
        self.assertGreaterEqual(len(on_disk), 4)
        self.assertTrue(table_rows(texts[TABLE_HOME]))
        self.assertTrue(heading_numbers(texts[on_disk[0]]))

    def test_an_off_by_one_range_fails(self):
        texts, on_disk = _live()
        # Mutation: the base file's part-table row for
        # agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md
        # (§1.14-§1.22) becomes §1.14-§1.21.
        part2 = "agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md"
        old = "| §1.14–§1.22 |"
        self.assertIn(old, texts[TABLE_HOME])
        texts[TABLE_HOME] = texts[TABLE_HOME].replace(old, "| §1.14–§1.21 |")
        found = problems(texts, on_disk)
        self.assertTrue(any(part2 in line for line in found), found)

    def test_a_file_named_by_no_row_fails(self):
        texts, on_disk = _live()
        # Fixture: an invented agent-orchestration-delegated-Part-9-Invented.md
        # with no `## 1.N` heading and no row in any part table.
        texts["agent-orchestration-delegated-Part-9-Invented.md"] = "# stub\n"
        on_disk = on_disk + ["agent-orchestration-delegated-Part-9-Invented.md"]
        found = problems(texts, on_disk)
        self.assertTrue(any("Part-9-Invented" in line and "no table row" in line for line in found), found)

    def test_one_table_plus_pointers_layout_passes(self):
        texts, on_disk = _live()
        pointer = f"See the part table in `{TABLE_HOME}` for the ranges.\n"
        for name in on_disk:
            if name == TABLE_HOME:
                continue
            texts[name] = pointer + "\n".join(
                f"## 1.{n} Heading" for n in heading_numbers(texts[name])
            )
        texts[BASE_NAME] = pointer
        self.assertEqual(problems(texts, on_disk), [])

    def test_a_pointerless_tableless_file_fails(self):
        texts, on_disk = _live()
        part3 = "agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md"
        texts[part3] = "\n".join(f"## 1.{n} Heading" for n in heading_numbers(texts[part3]))
        texts[BASE_NAME] = f"See {TABLE_HOME}\n"
        for name in on_disk:
            if name not in (TABLE_HOME, part3):
                texts[name] = "\n".join(f"## 1.{n} Heading" for n in heading_numbers(texts[name])) + f"\nSee {TABLE_HOME}\n"
        found = problems(texts, on_disk)
        self.assertTrue(any(part3 in line and "no pointer" in line for line in found), found)

    def test_a_pointerless_section_11_fails(self):
        texts, on_disk = _live()
        # Fixture: agent-orchestration.md §11 without its pointer line to the
        # base file's part table.
        texts[BASE_NAME] = "## 11. DELEGATED Dispatch Discipline\n\nNo pointer here.\n"
        found = problems(texts, on_disk)
        self.assertTrue(any(BASE_NAME in line and "no pointer" in line for line in found), found)

    def test_no_table_at_all_fails(self):
        self.assertEqual(len(problems({"a.md": "text\n"}, ["a.md"])), 1)


if __name__ == "__main__":
    unittest.main()
