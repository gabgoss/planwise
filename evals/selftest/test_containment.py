#!/usr/bin/env python3
"""Selftests for the containment module (harness/containment.py).

`a4b_scan` is exercised directly on real tempdirs (pure filesystem, no
mocking needed): a clean arm and a synthesized-leak arm (a stray file
planted outside the case dir). `porcelain_delta` never shells out to a real
`git` here -- every `subprocess.run` call is monkeypatched, covering clean,
dirty, and repo-absent (recorded-scope) outcomes, plus a baseline-diff case
proving pre-existing repo dirt is not misattributed to the case under test.

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_containment.py
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import containment


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


class TestA4bScan(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.mkdtemp(prefix="rso_containment_"))
        self.addCleanup(shutil.rmtree, self.parent, ignore_errors=True)
        self.case_dir = self.parent / "case-1"
        self.case_dir.mkdir()
        (self.case_dir / "nested").mkdir()
        (self.case_dir / "nested" / "inside.txt").write_text("ok", encoding="utf-8")

    def test_clean_scenario_no_leak(self):
        leaked = containment.a4b_scan(self.parent, self.case_dir)
        self.assertEqual(leaked, [])

    def test_synthesized_leak_planted_outside_case_dir(self):
        stray = self.parent / "stray.txt"
        stray.write_text("leaked outside the case dir", encoding="utf-8")
        leaked = containment.a4b_scan(self.parent, self.case_dir)
        self.assertEqual(leaked, [stray])

    def test_declared_scaffolding_sibling_excluded_not_reported(self):
        """A caller-declared sibling (e.g. a scratch root's plugin-subtree
        copy) is legitimate scaffolding, not this case's output, and must
        NOT be reported as a leak -- even though it sits directly under
        `parent` alongside `case_dir`, exactly where a real leak would.
        """
        plugin_copy = self.parent / "plugin-copy"
        plugin_copy.mkdir()
        (plugin_copy / "handlers").mkdir()
        (plugin_copy / "handlers" / "help.md").write_text("x", encoding="utf-8")
        leaked = containment.a4b_scan(self.parent, self.case_dir, exclude=[plugin_copy])
        self.assertEqual(leaked, [])

    def test_stray_still_caught_alongside_a_declared_exclusion(self):
        """Excluding known scaffolding must not weaken the predicate into a
        no-op -- an actual stray file elsewhere under `parent` is still
        caught even while a legitimate sibling is excluded.
        """
        plugin_copy = self.parent / "plugin-copy"
        plugin_copy.mkdir()
        (plugin_copy / "handlers.md").write_text("x", encoding="utf-8")
        stray = self.parent / "stray.txt"
        stray.write_text("leaked", encoding="utf-8")
        leaked = containment.a4b_scan(self.parent, self.case_dir, exclude=[plugin_copy])
        self.assertEqual(leaked, [stray])


class TestPorcelainDelta(unittest.TestCase):
    def setUp(self):
        self.repo_a = Path(tempfile.mkdtemp(prefix="rso_repo_a_"))
        self.repo_b = Path(tempfile.mkdtemp(prefix="rso_repo_b_"))
        self.addCleanup(shutil.rmtree, self.repo_a, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.repo_b, ignore_errors=True)

    def test_clean_both_repos(self):
        with patch.object(containment.subprocess, "run", return_value=_completed("")):
            report = containment.porcelain_delta([self.repo_a, self.repo_b])
        self.assertTrue(report.any_checked)
        self.assertTrue(report.all_clean)
        self.assertTrue(all(status.checked for status in report.statuses))

    def test_dirty_repo_reported_and_not_clean(self):
        with patch.object(containment.subprocess, "run", return_value=_completed(" M leaked_file.py\n")):
            report = containment.porcelain_delta([self.repo_a])
        self.assertTrue(report.any_checked)
        self.assertFalse(report.all_clean)
        self.assertTrue(report.statuses[0].dirty)

    def test_repo_absent_is_recorded_scope_not_a_pass(self):
        """A repo path that does not exist on disk must be `checked=False`,
        distinguishable from a repo that was checked and found clean --
        an assertion that had nothing to check is never a passing report.
        """
        missing_repo = self.repo_a / "does-not-exist"
        report = containment.porcelain_delta([missing_repo])
        self.assertFalse(report.any_checked)
        self.assertFalse(report.all_clean)  # NOT the same thing as "checked and clean"
        self.assertFalse(report.statuses[0].checked)
        self.assertIsNone(report.statuses[0].dirty)

    def test_matches_baseline_stays_clean_despite_preexisting_dirt(self):
        """Pre-existing repo dirt that the baseline already recorded must
        NOT be attributed to the case under test -- only a DELTA from the
        baseline counts as dirty.
        """
        preexisting = " M unrelated_preexisting_change.py\n"
        baseline = {self.repo_a: preexisting}
        with patch.object(containment.subprocess, "run", return_value=_completed(preexisting)):
            report = containment.porcelain_delta([self.repo_a], baseline=baseline)
        self.assertTrue(report.statuses[0].checked)
        self.assertFalse(report.statuses[0].dirty)
        self.assertTrue(report.all_clean)

    def test_unrecorded_baseline_is_unknown_not_clean(self):
        """`capture_baseline` returning `None` for a repo means the baseline
        capture ITSELF failed -- not that the repo was clean. If the repo's
        `git status` later succeeds and reports pre-existing dirt, that must
        NOT be silently compared against an assumed-empty baseline (which
        would misattribute the pre-existing dirt to the case); the repo
        must come back `checked=False` (unknown) instead, and the current
        git call is never even required to discriminate this.
        """
        baseline = {self.repo_a: None}  # capture_baseline attempted and failed
        preexisting_dirt = " M some_preexisting_file.py\n"
        with patch.object(containment.subprocess, "run", return_value=_completed(preexisting_dirt)) as mock_run:
            report = containment.porcelain_delta([self.repo_a], baseline=baseline)
        self.assertFalse(report.statuses[0].checked)
        self.assertIsNone(report.statuses[0].dirty)
        self.assertFalse(report.any_checked)
        mock_run.assert_not_called()

    def test_capture_baseline_records_per_repo_snapshot(self):
        with patch.object(containment.subprocess, "run", return_value=_completed(" M a.py\n")):
            baseline = containment.capture_baseline([self.repo_a])
        self.assertEqual(baseline[self.repo_a], " M a.py\n")


if __name__ == "__main__":
    unittest.main()
