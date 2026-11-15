#!/usr/bin/env python3
"""Regression tests for the Sprint Overview Row Encoding section of the
sprint-signoff template.

The Master Plan's Sprint Overview table is authored per plan. A plan can carry
eight columns (Sprint, Name, Claims, Sessions, Tasks, Est. Tokens, Ungated /
Gated bill, Status) or any other set. The template once gave the closer a
fenced four-column row to paste for the sprint, with a fixed column set and a
`Signoff Date` column that no plan has. Following it overwrote a populated
row and dropped every column the snippet did not carry. The callout directly
above the snippet already said to update the row's Status, so only the worked
example was wrong, and the worked example is the part that gets copied.

The section now instructs a single-cell edit of the Status column. This suite
reads the live template and an eight-column Sprint Overview fixture. It proves
the section holds no table-row line, no fenced block and no instruction that
names a column other than Status. It also proves the checks fail on the
pre-fix section text, so a passing run is not a vacuous one.

Run with:  python -m pytest tests/test_sprint_signoff_template.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
TEMPLATES = PLUGIN_ROOT / "templates"
SIGNOFF_TEMPLATE = TEMPLATES / "sprint-signoff.md"
BASELINE_PINNING_REFERENCE = PLUGIN_ROOT / "references" / "gate-diff-baseline-pinning.md"

SECTION_HEADING = "## Sprint Overview Row Encoding"

# An eight-column Sprint Overview table as one plan authored it.
FIXTURE_HEADER = (
    "| Sprint | Name | Claims | Sessions | Tasks | Est. Tokens "
    "| Ungated / Gated bill | Status |"
)
FIXTURE_ROW = "| 03 | Closeout | 12 | 4 | 22 | 150K | 1.2M / 480K | IN_PROGRESS |"
FIXTURE_COLUMNS = tuple(cell.strip() for cell in FIXTURE_HEADER.strip("|").split("|"))

# Columns the section must never restate. "Sprint" is left out because the
# section title and its own prose say "Sprint Overview" legitimately.
RESTATED_COLUMN_CANDIDATES = tuple(
    column for column in FIXTURE_COLUMNS if column not in ("Sprint", "Status")
)

# The section as it read before the fix, kept as a fixture so the checks can be
# shown to fail on it. The snippet body is byte-for-byte the shipped old text.
PRE_FIX_SECTION = """\
## Sprint Overview Row Encoding

> [!practice] Sprint Overview Row vs Master Plan Status
> The Sprint Overview row state reflects the **exit-gate verdict**, NOT the session-count fraction (per `references/gate-exit-verdict-and-smoke-reports.md` §4). When this signoff records PASS, update the Master Plan's Sprint Overview row Status to COMPLETE. PARTIAL or FAIL retains IN_PROGRESS until remediated.

Master Plan Sprint Overview row to update:
```
| {Abbrev}-S{XX} | {Sprint Name} | {Status: COMPLETE | IN_PROGRESS} | {Signoff Date} |
```
"""

# A table-row line, bare or inside a blockquote.
_TABLE_ROW_RE = re.compile(r"^\s*(?:>\s*)*\|")
_FENCE_RE = re.compile(r"^\s*(?:>\s*)*```")
_PLACEHOLDER_RE = re.compile(r"\{[^}\n]+\}")


def extract_section(text: str) -> str:
    """Return the Sprint Overview Row Encoding section of the template text."""
    start = text.find(SECTION_HEADING)
    if start == -1:
        raise AssertionError(
            f"heading {SECTION_HEADING!r} not found -- the section moved or was renamed"
        )
    rest = text[start + len(SECTION_HEADING):]
    following = re.search(r"^(?:## |---\s*$)", rest, re.MULTILINE)
    end = following.start() if following else len(rest)
    return SECTION_HEADING + rest[:end]


def section_violations(section: str) -> list[str]:
    """Name every way the section fails to be a pure single-cell Status edit."""
    problems: list[str] = []
    for number, line in enumerate(section.splitlines(), start=1):
        if _TABLE_ROW_RE.match(line):
            problems.append(f"line {number}: table-row line: {line.strip()}")
        if _FENCE_RE.match(line):
            problems.append(f"line {number}: fenced block marker: {line.strip()}")
    for placeholder in _PLACEHOLDER_RE.findall(section):
        problems.append(f"placeholder cell text: {placeholder}")
    if "Signoff Date" in section:
        problems.append("names a Signoff Date column that no plan carries")
    for column in RESTATED_COLUMN_CANDIDATES:
        if re.search(rf"(?<![A-Za-z]){re.escape(column)}(?![A-Za-z])", section):
            problems.append(f"restates the column {column!r}")
    if "`Status`" not in section:
        problems.append("does not name the `Status` column as the one to edit")
    if not re.search(r"`Status` column only", section):
        problems.append("does not say the edit is the Status column only")
    return problems


class SprintSignoffRowEncodingTests(unittest.TestCase):
    def setUp(self):
        self.text = SIGNOFF_TEMPLATE.read_text(encoding="utf-8")
        self.section = extract_section(self.text)

    def test_fixture_is_the_eight_column_table(self):
        self.assertEqual(len(FIXTURE_COLUMNS), 8)
        self.assertEqual(FIXTURE_COLUMNS[-1], "Status")
        self.assertEqual(FIXTURE_ROW.count("|"), FIXTURE_HEADER.count("|"))

    def test_section_has_no_table_row_and_no_fence(self):
        for line in self.section.splitlines():
            self.assertIsNone(_TABLE_ROW_RE.match(line), line)
            self.assertIsNone(_FENCE_RE.match(line), line)

    def test_section_is_a_single_cell_status_edit(self):
        self.assertEqual(section_violations(self.section), [])

    def test_section_names_no_fixture_column_but_status(self):
        for column in RESTATED_COLUMN_CANDIDATES:
            self.assertNotRegex(
                self.section, rf"(?<![A-Za-z]){re.escape(column)}(?![A-Za-z])"
            )

    def test_section_covers_a_table_without_a_status_column(self):
        self.assertIn("no `Status` column", self.section)
        self.assertIn("carries the sprint's verdict", self.section)

    def test_section_agrees_with_the_practice_callout(self):
        # The callout above the edit instruction says to update the row Status.
        self.assertIn("update the Master Plan's Sprint Overview row Status", self.section)
        practice = self.section.index("[!practice]")
        constraint = self.section.index("Update the `Status` column only")
        self.assertLess(practice, constraint)

    def test_section_stays_the_only_sprint_overview_encoding_section(self):
        self.assertEqual(self.text.count(SECTION_HEADING), 1)

    def test_no_shipped_template_carries_the_signoff_date_column(self):
        for path in sorted(TEMPLATES.glob("*.md")):
            body = path.read_text(encoding="utf-8")
            self.assertNotIn("{Signoff Date}", body, path.name)


class DiscriminationControlTests(unittest.TestCase):
    """The checks must fail on the pre-fix text, or a green run proves nothing."""

    def test_pre_fix_fixture_matches_the_real_old_line(self):
        # The pinned patterns run against the real old snippet line once.
        old_row = "| {Abbrev}-S{XX} | {Sprint Name} | {Status: COMPLETE | IN_PROGRESS} | {Signoff Date} |"
        self.assertIn(old_row, PRE_FIX_SECTION)
        self.assertIsNotNone(_TABLE_ROW_RE.match(old_row))
        self.assertIsNotNone(_PLACEHOLDER_RE.search(old_row))

    def test_checks_fail_on_the_pre_fix_section(self):
        section = extract_section(PRE_FIX_SECTION)
        problems = section_violations(section)
        self.assertTrue(problems)
        joined = "\n".join(problems)
        self.assertIn("table-row line", joined)
        self.assertIn("fenced block marker", joined)
        self.assertIn("Signoff Date", joined)
        self.assertIn("restates the column 'Name'", joined.replace('"', "'"))

    def test_checks_fail_on_a_section_that_restates_a_column(self):
        mutated = (
            SECTION_HEADING
            + "\n\n> [!constraint] Edit\n"
            + "> Update the `Status` column only. Also set the Claims column.\n"
        )
        self.assertTrue(
            any("Claims" in problem for problem in section_violations(mutated))
        )


class WholeRowPasteSweepTests(unittest.TestCase):
    """The same defect elsewhere in shipped content: a fixed-column row shown
    as the way to write into a Sprint Overview table that each plan authors."""

    def test_baseline_pinning_reference_shows_a_cell_not_a_row(self):
        text = BASELINE_PINNING_REFERENCE.read_text(encoding="utf-8")
        self.assertNotIn("| {Sprint-N} | {Session-Name} |", text)
        self.assertIn("Edit that one cell of the sprint's existing row", text)


if __name__ == "__main__":
    unittest.main()
