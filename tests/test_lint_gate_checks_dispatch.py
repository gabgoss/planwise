"""Tests for the dispatch-rule lint checks in ``lint_gate_checks_dispatch``.

Each check gets one known-bad fixture that must produce a finding naming it, and
the same fixture repaired, which must produce none for it. The fixtures are built
in temporary directories.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_gate_checks_dispatch as dispatch_module
import lint_verification_gates as lint_module
from lint_verification_gates import lint_plan


def _task(objective="Do the work.", steps="1. Read the file.", output="`out/result.md`",
          context_rows=(), extra=""):
    rows = "".join(f"{row}\n" for row in context_rows)
    table = (
        "| Priority | File | KiB | Purpose |\n|---|---|---:|---|\n" + rows if context_rows else ""
    )
    return (
        "# Task: Fixture\n\n"
        f"**Output:** {output}\n\n"
        f"## Objective\n\n{objective}\n\n"
        f"## Required Context\n\n{table}\n"
        f"## Execution Steps\n\n{steps}\n\n"
        f"{extra}"
    )


def _lint(check, text, name="TASK-01-Fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
        return [f for f in lint_plan(Path(tmp), execute=False) if f["check"] == check]


class TestCheck42PremisePhrase(unittest.TestCase):
    def test_bad_premise_in_objective(self):
        findings = _lint(42, _task(objective="You will probably find the cause is the cache."))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(42, "WARNING")])

    def test_bad_premise_in_step(self):
        findings = _lint(42, _task(steps="1. Be willing to conclude the count is wrong."))
        self.assertEqual(len(findings), 1)

    def test_good_repaired_as_context(self):
        self.assertEqual(_lint(42, _task(objective="The cache holds 12 files, measured today.")), [])

    def test_good_phrase_in_code_span(self):
        self.assertEqual(_lint(42, _task(steps="1. Flag any sentence with `probably find`.")), [])

    def test_good_phrase_outside_brief_sections(self):
        self.assertEqual(_lint(42, _task(extra="## Notes for Agent\n\nYou will probably find it.\n")), [])

    def test_bad_premise_in_orchestration_spawn_prompt(self):
        text = "# Orchestration\n\n```\nBe willing to conclude the cache is stale.\n```\n"
        findings = _lint(42, text, name="XX-S01-01-Orchestration.md")
        self.assertEqual(len(findings), 1)


class TestCheck43WriteOutsideOutput(unittest.TestCase):
    BAD = "1. Stamp the duplicate in `register/Part-1b.md` as absorbed."

    def test_bad_stamp_to_path_not_in_output(self):
        findings = _lint(43, _task(steps=self.BAD))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(43, "WARNING")])

    def test_good_path_added_to_output(self):
        self.assertEqual(_lint(43, _task(steps=self.BAD, output="`out/result.md`, `register/Part-1b.md`")), [])

    def test_good_step_without_write_verb(self):
        self.assertEqual(_lint(43, _task(steps="1. Read `register/Part-1b.md`.")), [])

    def test_good_negated_step(self):
        self.assertEqual(_lint(43, _task(steps="1. Do not amend `register/Part-1b.md`.")), [])

    def test_good_no_output_field(self):
        text = _task(steps=self.BAD).replace("**Output:** `out/result.md`\n\n", "")
        self.assertEqual(_lint(43, text), [])


class TestCheck44FigureWithoutDateAndSource(unittest.TestCase):
    BARE = "| 1 | `a/b.py` — 620 lines | 27.3 | the sibling shape |"
    STAMPED = "| 1 | `a/b.py` — 620 lines, measured 2026-11-07 by `measure_files.py` | 27.3 | the sibling shape |"

    def test_bad_figure_with_no_date_or_source(self):
        findings = _lint(44, _task(context_rows=[self.BARE]))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(44, "WARNING")])

    def test_bad_figure_with_date_and_no_source(self):
        row = "| 1 | `a/b.py` — 620 lines, measured 2026-11-07 | 27.3 | the sibling shape |"
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)

    def test_good_figure_with_date_and_source(self):
        self.assertEqual(_lint(44, _task(context_rows=[self.STAMPED])), [])

    def test_good_row_without_a_figure(self):
        row = "| 1 | `a/b.py` | whole | the sibling shape |"
        self.assertEqual(_lint(44, _task(context_rows=[row])), [])

    def test_bad_number_under_a_size_header(self):
        row = "| 1 | `a/b.py` | 27.3 | the sibling shape |"
        self.assertEqual(len(_lint(44, _task(context_rows=[row]))), 1)


class TestCheck45RemeasureWithoutClauses(unittest.TestCase):
    def test_bad_bare_remeasure(self):
        extra = "<!-- Register rows (projected) -- re-measure at dispatch. -->\n"
        findings = _lint(45, _task(extra=extra))
        self.assertEqual([(f["check"], f["severity"]) for f in findings], [(45, "WARNING")])

    def test_bad_threshold_without_action(self):
        extra = "Re-measure the pull count at dispatch if it is more than 10% off.\n"
        self.assertEqual(len(_lint(45, _task(extra=extra))), 1)

    def test_good_threshold_and_action(self):
        extra = "Re-measure the pull count at dispatch. If it is more than 10% off, re-roll the budget.\n"
        self.assertEqual(_lint(45, _task(extra=extra)), [])

    def test_good_code_span_mention(self):
        self.assertEqual(_lint(45, _task(extra="The phrase `re-measure at dispatch` is checked.\n")), [])

    def test_good_wrong_labelled_line(self):
        extra = "WRONG: re-measure at dispatch.\n"
        self.assertEqual(_lint(45, _task(extra=extra)), [])


class TestSubjectCounts(unittest.TestCase):
    def test_counts_distinguish_empty_from_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = dispatch_module.subject_counts(_context(Path(tmp)))
            self.assertEqual(empty["task_files"], 0)
            self.assertEqual(empty["brief_lines"], 0)
            (Path(tmp) / "TASK-01-Fixture.md").write_text(_task(), encoding="utf-8", newline="\n")
            context = _context(Path(tmp))
            counts = dispatch_module.subject_counts(context)
        self.assertEqual(counts["task_files"], 1)
        self.assertGreater(counts["brief_lines"], 0)


def _context(root):
    class _Context:
        plan_root = root

        def markdown_files(self):
            return sorted(p for p in root.rglob("*.md") if p.is_file())

    return _Context()


class TestRegistrationContract(unittest.TestCase):
    def test_every_check_is_registered_once(self):
        for check in dispatch_module.CHECKS:
            self.assertEqual(lint_module.CHECK_REGISTRY.count(check), 1, check.__name__)

    def test_check_numbers(self):
        names = [check.__name__.split("_")[1] for check in dispatch_module.CHECKS]
        self.assertEqual(names, ["check42", "check43", "check44", "check45"])

    def test_severity_constant_matches_the_linter(self):
        self.assertEqual(dispatch_module.SEVERITY_WARNING, lint_module.SEVERITY_WARNING)

    def test_finding_keys_match_make_finding(self):
        fields = {"check": 1, "severity": "WARNING", "file": "f", "line": 1, "command": "c", "message": "m"}
        self.assertEqual(dispatch_module._finding(**fields), lint_module.make_finding(**fields))

    def test_module_imports_nothing_from_the_linter(self):
        source = (SCRIPTS / "lint_gate_checks_dispatch.py").read_text(encoding="utf-8")
        self.assertNotIn("lint_verification_gates", source.split('"""', 2)[2])

    def test_cli_run_as_script_reports_a_new_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "TASK-01-Fixture.md").write_text(
                _task(objective="You will probably find the cause."), encoding="utf-8", newline="\n"
            )
            completed = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), tmp, "--no-execute"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )
        self.assertIn("Check 42:", completed.stdout, completed.stderr)
        self.assertIn("[WARNING] Check 42:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
