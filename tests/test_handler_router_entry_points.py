"""A router's "Reading order by mode" line lists every Part step a mode's files link into.

A split handler's router names, per mode, the Part steps a reader follows a link into.
A task that adds a link into a Part step from a file that mode reads owes the router line.
"""

import re
from pathlib import Path

HANDLERS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "handlers"
LABEL = r"\d+[a-z]?(?:-\d+)?"


def router_gaps(handlers, router_name, line):
    """Return (gaps, checked): each unlisted (source, part, label), and the links read."""
    stem = router_name[:-3]
    gaps, checked = [], 0
    for sentence in re.split(r"(?<=\.)\s+", line):
        listed_by_part = {}
        clauses = re.findall(r"Part (\d+) when it follows a Step (.*?) link", sentence)
        clauses += re.findall(rf"Part (\d+) for Steps? ((?:{LABEL}(?:, | and | or )?)+)", sentence)
        for part, listed in clauses:
            listed_by_part.setdefault(part, set()).update(re.findall(LABEL, listed))
        for part, labels in listed_by_part.items():
            for source in re.findall(r"`([\w-]+\.md)`", sentence):
                text = (handlers / source).read_text(encoding="utf-8")
                # A heading with an em dash gives an anchor with two hyphens.
                pattern = rf"{stem}-Part-{part}-[\w-]+\.md#steps?-({LABEL})-+[a-z]"
                for label in re.findall(pattern, text):
                    checked += 1
                    if label not in labels:
                        gaps.append((source, part, label))
    return gaps, checked


def _router_lines(handlers):
    for path in sorted(handlers.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Reading order by mode:"):
                yield path.name, line


def test_every_linked_part_step_is_on_the_router_line():
    routers = list(_router_lines(HANDLERS))
    assert routers, "no router line found: the check saw nothing"
    total, gaps = 0, []
    for name, line in routers:
        found, checked = router_gaps(HANDLERS, name, line)
        gaps += found
        total += checked
    assert total > 0, "no link into a routed Part step was read: the check saw nothing"
    assert gaps == []


def test_a_link_missing_from_the_router_line_is_reported(tmp_path):
    (tmp_path / "doc.md").write_text(
        "Reading order by mode: Alt mode reads this file, then `doc-alt.md`, "
        "and Part 2 when it follows a Step 3 or Step 8c link.\n", encoding="utf-8")
    (tmp_path / "doc-alt.md").write_text(
        "See [Step 3](doc-Part-2-Gather.md#step-3-create-folders) and "
        "[Steps 4-7](doc-Part-2-Gather.md#steps-4-7-generate-files).\n", encoding="utf-8")
    line = (tmp_path / "doc.md").read_text(encoding="utf-8").splitlines()[0]
    gaps, checked = router_gaps(tmp_path, "doc.md", line)
    assert checked == 2
    assert gaps == [("doc-alt.md", "2", "4-7")]


def test_a_for_steps_clause_and_a_double_hyphen_anchor_are_read(tmp_path):
    line = "Alt mode reads `doc-alt.md`, then Part 3 for Steps 9a and 10."
    (tmp_path / "doc-alt.md").write_text(
        "See [9a](doc-Part-3-End.md#step-9a-emit), [10](doc-Part-3-End.md#step-10-review) "
        "and [8e](doc-Part-3-End.md#step-8e--populate).\n", encoding="utf-8")
    gaps, checked = router_gaps(tmp_path, "doc.md", line)
    assert checked == 3
    assert gaps == [("doc-alt.md", "3", "8e")]
