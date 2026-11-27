"""Every split Part file keeps its position, and its parent keeps a pointer to it.

A reference or a handler that is split into Part files stays findable only while
two things hold. The Part says where it sits in the family. The file a reader
opens first says which Part holds the rest. This module checks both on the
shipped tree, then strips one token from a copy of a real family and requires the
checker to report it.
"""

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
REFERENCES = PLUGIN / "references"
HANDLERS = PLUGIN / "handlers"

PART_NAME = re.compile(r"^(?P<stem>.+?)-Part-(?P<k>\d+)-.+\.md$")
NUMBERED_HEADING = re.compile(r"^#{2,4} +§? ?\d+(?:\.[0-9A-Za-z]+)*[.:]? ")
HELD_IN = re.compile(r"held in", re.IGNORECASE)
HANDLER_OPENER_LINES = 6


def part_files(folder):
    # By name: a Windows path sorts without regard to case, a name string does not.
    return sorted(folder.glob("*-Part-*.md"), key=lambda path: path.name)


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def body_of(lines):
    """The lines after the frontmatter, where a reader looks for a pointer."""
    if lines and lines[0] == "---" and "---" in lines[1:]:
        return lines[lines.index("---", 1) + 1 :]
    return lines


def states_wrong_total(text, k, total):
    """True when `text` says `Part k of N` with a number that is not `total`."""
    return any(int(n) != total for n in re.findall(rf"\bPart {k} of (\d+)\b", text))


def description_of(lines):
    """The frontmatter `description:` line, or "" when there is none."""
    if not lines or lines[0] != "---":
        return ""
    for line in lines[1:]:
        if line == "---":
            break
        if line.startswith("description:"):
            return line
    return ""


def has_numbered_heading(lines):
    fenced = False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and NUMBERED_HEADING.match(line):
            return True
    return False


def check_reference_part(part):
    """Findings for one `references/*-Part-*.md` file."""
    match = PART_NAME.match(part.name)
    if not match:
        return ["the filename carries no readable Part number"]
    stem, k = match["stem"], int(match["k"])
    folder = part.parent
    siblings = {
        int(found["k"]): path
        for path in part_files(folder)
        if (found := PART_NAME.match(path.name)) and found["stem"] == stem
    }
    parent = folder / f"{stem}.md"
    total = len(siblings) + parent.is_file()
    first = parent if parent.is_file() else siblings.get(1)
    if first is None:
        return ["the family has no parent file and no Part 1"]

    lines = read_lines(part)
    description = description_of(lines)
    findings = []
    if not re.search(rf"\bPart {k} of {total}\b", description):
        findings.append(f"position: the description does not say `Part {k} of {total}`")
    if k >= 2 and first.name not in description:
        findings.append(f"first-part: the description does not name {first.name}")
    if has_numbered_heading(lines) and "§" not in description:
        findings.append("sections: the description names no section it holds")

    if parent.is_file():
        parent_lines = read_lines(parent)
        if states_wrong_total(description_of(parent_lines), 1, total):
            findings.append(f"position: {parent.name} states a total other than {total}")
        if not any(HELD_IN.search(line) and part.name in line for line in body_of(parent_lines)):
            findings.append(f"pointer: {parent.name} has no `held in` line that names this Part")
    elif part != first and f"]({part.name}" not in first.read_text(encoding="utf-8"):
        findings.append(f"pointer: {first.name} does not link this Part")
    return findings


def check_handler_part(part):
    """Findings for one `handlers/*-Part-*.md` file."""
    match = PART_NAME.match(part.name)
    if not match:
        return ["the filename carries no readable Part number"]
    stem, k = match["stem"], int(match["k"])
    findings = []
    parent = part.parent / f"{stem}.md"
    total = parent.is_file() + sum(
        1
        for path in part_files(part.parent)
        if (found := PART_NAME.match(path.name)) and found["stem"] == stem
    )
    opener = "\n".join(read_lines(part)[:HANDLER_OPENER_LINES])
    if not re.search(rf"\bPart {k} of\b", opener):
        findings.append(
            f"position: no `Part {k} of` in the first {HANDLER_OPENER_LINES} lines"
        )
    elif states_wrong_total(opener, k, total):
        findings.append(f"position: the opener states a total other than {total}")
    if not parent.is_file() or part.name not in parent.read_text(encoding="utf-8"):
        findings.append(f"pointer: {stem}.md does not name this Part")
    return findings


class TestShippedPartFiles(unittest.TestCase):
    def assert_family_clean(self, folder, check):
        listed = sorted(
            name for name in os.listdir(folder) if "-Part-" in name and name.endswith(".md")
        )
        parts = part_files(folder)
        self.assertTrue(listed, f"no Part file under {folder}: the check saw nothing")
        self.assertEqual([part.name for part in parts], listed)
        for part in parts:
            with self.subTest(part=part.name):
                self.assertEqual(check(part), [])

    def test_every_reference_part_is_indexed(self):
        self.assert_family_clean(REFERENCES, check_reference_part)

    def test_every_handler_part_is_indexed(self):
        self.assert_family_clean(HANDLERS, check_handler_part)


class TestKnownBadCopies(unittest.TestCase):
    """Each arm copies a real family, strips one token and expects one finding."""

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def copy_family(self, folder, stem):
        sources = [*folder.glob(f"{stem}-Part-*.md"), folder / f"{stem}.md"]
        for source in sources:
            if source.is_file():
                shutil.copy2(source, self.tmp / source.name)

    def strip(self, name, token, keep=lambda line: True, new=""):
        """Replace `token` on every line of the copy that `keep` selects."""
        path = self.tmp / name
        lines = path.read_text(encoding="utf-8").split("\n")
        stripped = [
            line.replace(token, new) if keep(line) else line for line in lines
        ]
        self.assertNotEqual(stripped, lines, f"{token!r} is not in {name}: the arm proves nothing")
        path.write_text("\n".join(stripped), encoding="utf-8")

    def assert_one_finding(self, check, part, kind):
        findings = check(self.tmp / part)
        self.assertEqual(len(findings), 1, findings)
        self.assertTrue(findings[0].startswith(f"{kind}:"), findings)

    def reference_case(self, part, token, kind, in_file=None, keep=lambda line: True):
        self.copy_family(REFERENCES, part.split("-Part-")[0])
        self.assertEqual(check_reference_part(self.tmp / part), [], "the copy starts clean")
        self.strip(in_file or part, token, keep)
        self.assert_one_finding(check_reference_part, part, kind)

    PART = "agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md"
    PARENT = "agent-orchestration-delegated.md"

    def test_part_that_loses_its_position(self):
        self.reference_case(self.PART, "Part 2 of 4", "position")

    def test_parent_that_loses_its_held_in_pointer(self):
        self.reference_case(
            self.PART, "held in", "pointer", in_file=self.PARENT,
            keep=lambda line: self.PART in line,
        )

    def test_part_that_stops_naming_part_one(self):
        self.reference_case(
            self.PART, self.PARENT, "first-part",
            keep=lambda line: line.startswith("description:"),
        )

    def test_part_that_stops_naming_its_sections(self):
        self.reference_case(
            self.PART, "§", "sections", keep=lambda line: line.startswith("description:")
        )

    def test_part_one_that_drops_its_link_in_a_family_with_no_parent(self):
        second = "lessons-promote-batch-workflow-Part-2-DraftAndWrite.md"
        self.reference_case(
            second, f"]({second}", "pointer",
            in_file="lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md",
        )

    def test_handler_part_that_loses_its_opener(self):
        part = "backlog-Part-2-LoopMode.md"
        self.copy_family(HANDLERS, "backlog")
        self.assertEqual(check_handler_part(self.tmp / part), [], "the copy starts clean")
        self.strip(part, "Part 2 of")
        self.assert_one_finding(check_handler_part, part, "position")

    def test_handler_parent_that_stops_naming_a_part(self):
        part = "backlog-Part-2-LoopMode.md"
        self.copy_family(HANDLERS, "backlog")
        self.assertEqual(check_handler_part(self.tmp / part), [], "the copy starts clean")
        self.strip("backlog.md", part)
        self.assert_one_finding(check_handler_part, part, "pointer")

    def test_pointer_that_survives_only_in_the_parent_frontmatter(self):
        part = "measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md"
        # The parent's description still says `held in` and still names the Part.
        self.reference_case(
            part, "held in", "pointer", in_file="measurement-discipline.md",
            keep=lambda line: part in line and not line.startswith("description:"),
        )

    def test_parent_that_states_a_stale_total(self):
        self.copy_family(REFERENCES, "agent-orchestration-delegated")
        self.strip(self.PARENT, "Part 1 of 4", new="Part 1 of 3")
        self.assert_one_finding(check_reference_part, self.PART, "position")

    def test_handler_part_that_states_a_stale_total(self):
        part = "doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md"
        self.copy_family(HANDLERS, "doctor")
        self.assertEqual(check_handler_part(self.tmp / part), [], "the copy starts clean")
        self.strip(part, "Part 2 of 3", new="Part 2 of 2")
        self.assert_one_finding(check_handler_part, part, "position")

    def test_part_files_sort_as_their_names_do(self):
        # A family whose stem extends another family's stem, differing in case.
        names = ["plan-Part-2-A.md", "plan-discovery-Part-2-A.md"]
        for name in names:
            (self.tmp / name).write_text("", encoding="utf-8")
        self.assertEqual([path.name for path in part_files(self.tmp)], sorted(names))


if __name__ == "__main__":
    unittest.main()
