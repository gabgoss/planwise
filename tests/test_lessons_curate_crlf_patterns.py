#!/usr/bin/env python3
"""The curate workflow reads lesson status through the shipped script, and a CRLF
lesson file is still found.

`references/lessons-curate-workflow.md` once pinned two Grep patterns, one for
`status: promoted` (section 4.1) and one for `status: documented` (section 4.1b).
A CRLF lesson file ends each line with a carriage return, so a bare `$` never
matched it and the curate pass saw no lessons. Nothing raised an error. Sections
4.1 and 4.1b now run `parse_lessons.py --status`, which reads the files through
the CRLF-safe frontmatter scanner, so no status Grep pattern remains.

These tests pin that shape:

- the extractor still recognises a pinned `pattern: ^status: ...` line (control),
- the workflow holds zero such lines,
- the workflow names the `--status promoted` command in 4.1 and the
  `--status documented` command in 4.1b, so the zero is not a blind extractor,
- the shipped script lists a CRLF lesson and an LF lesson, and a bare-`$` search
  over the same CRLF file misses (control).

Run with:  python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_lessons_curate_crlf_patterns.py
"""

import contextlib
import io
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins" / "planwise" / "scripts"))

import parse_lessons

CURATE_REF = HERE.parent / "plugins" / "planwise" / "references" / "lessons-curate-workflow.md"

# A pinned line reads `pattern: ^status: <word>...`.
PINNED_LINE = re.compile(r"^pattern: (\^status: .*)$")
# The command each section names, as one line of the workflow.
COMMAND_LINE = re.compile(r"parse_lessons\.py .*--status (\w+)")


def pinned_patterns(text: str) -> list[str]:
    """Return the pattern body of every `pattern: ^status: ...` line in the text."""
    found = []
    for line in text.splitlines():
        hit = PINNED_LINE.match(line)
        if hit:
            found.append(hit.group(1))
    return found


def named_statuses(text: str) -> list[str]:
    """Return the status word of every `parse_lessons.py ... --status X` line."""
    return [hit.group(1) for line in text.splitlines() if (hit := COMMAND_LINE.search(line))]


class CurateWorkflowUsesTheShippedStatusView(unittest.TestCase):
    """The workflow names the script, and carries no status Grep pattern."""

    @classmethod
    def setUpClass(cls):
        cls.text = CURATE_REF.read_bytes().decode("utf-8")

    def test_extractor_sees_a_pinned_pattern_line(self):
        # Direction test: the extractor returns the line it is meant to find.
        sample = "```\npattern: ^status: promoted$\npath: x\n```\n"
        self.assertEqual(pinned_patterns(sample), ["^status: promoted$"])

    def test_extractor_sees_a_command_line(self):
        sample = "`python {plugin_root}/scripts/parse_lessons.py --config {config_path} --status promoted --owners`"
        self.assertEqual(named_statuses(sample), ["promoted"])

    def test_no_status_grep_pattern_remains(self):
        self.assertEqual(pinned_patterns(self.text), [])

    def test_both_statuses_are_named_exactly_once(self):
        # Denominator: sections 4.1 and 4.1b. Zero would mean a blind extractor.
        self.assertEqual(sorted(named_statuses(self.text)), ["documented", "promoted"])


class ShippedViewFindsCrlfLessons(unittest.TestCase):
    """The command the workflow names lists a CRLF lesson, which a bare `$` Grep
    pattern cannot."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="curate_crlf_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        planwise_dir = self.tmp / "planwise"
        self.lessons_dir = planwise_dir / "LessonsLearned"
        self.lessons_dir.mkdir(parents=True)
        self.config_path = planwise_dir / "config.yaml"
        self.config_path.write_bytes(
            b'project:\n  name: "CurateCrlfFixture"\n  lessons_dir: "LessonsLearned"\n'
            b'  index_files:\n    lessons: "00-Index-LessonsLearned.md"\n'
        )

    def _lesson(self, number: int, status: str, eol: str) -> Path:
        lines = [
            "---", f"id: LL-{number:03d}", "title: Fixture", "category: process", "severity: medium",
            "language: [python]", "technology: []", "domain: []", "source: fixture",
            f"status: {status}", "---", "",
        ]
        path = self.lessons_dir / f"LL-{number:03d}-PROC-Fixture{number}.md"
        path.write_bytes(eol.join(lines).encode())
        return path

    def _listed(self, status: str) -> list[str]:
        argv = ["test_curate", "--config", str(self.config_path), "--status", status]
        out = io.StringIO()
        with unittest.mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            code = parse_lessons.main()
        self.assertEqual(code, 0)
        return [line.split("\t")[0] for line in out.getvalue().split("\n") if line.startswith("LL-")]

    def test_a_crlf_and_an_lf_lesson_are_both_listed(self):
        crlf = self._lesson(1, "promoted", "\r\n")
        self._lesson(2, "promoted", "\n")
        self._lesson(3, "documented", "\r\n")
        self.assertIn(b"\r\n", crlf.read_bytes())
        self.assertEqual(self._listed("promoted"), ["LL-001", "LL-002"])
        self.assertEqual(self._listed("documented"), ["LL-003"])

    def test_control_the_bare_dollar_pattern_misses_the_crlf_lesson(self):
        crlf = self._lesson(1, "promoted", "\r\n")
        text = crlf.read_bytes().decode("utf-8")
        self.assertIsNone(re.search(r"^status: promoted$", text, re.MULTILINE))
        self.assertIsNotNone(re.search(r"^status: promoted\r?$", text, re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
