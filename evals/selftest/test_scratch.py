#!/usr/bin/env python3
"""Selftests for the containment layer (harness/scratch.py).

Pure/mocked, $0: every test builds its own synthesized temp tree via
`tempfile.mkdtemp` + `addCleanup(shutil.rmtree, ..., ignore_errors=True)`
(the idiom this module's own `teardown()` adapts) and never touches the
real project or `~/.claude/`. `shutil.rmtree` / `time.sleep` are
monkeypatched only where the retry path itself is under test.

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_scratch.py
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import scratch


class TestAncestorProjectAssertion(unittest.TestCase):
    """`ScratchRoot.create()` refuses a root planted under a live project."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_refuses_when_an_ancestor_carries_a_live_config(self):
        # Plant a live-looking project two levels above where the scratch
        # root would be chosen -- the failing arm the ancestor guard exists
        # to prove.
        ancestor = self.tmp / "fake-project"
        (ancestor / "planwise").mkdir(parents=True)
        (ancestor / "planwise" / "config.yaml").write_text("name: fake\n")
        nested_base = ancestor / "nested" / "deeper"
        nested_base.mkdir(parents=True)

        with self.assertRaises(scratch.ScratchContainmentError):
            scratch.ScratchRoot.create(run_id="probe", base_temp=nested_base)

        # The refusal must leave nothing behind under the would-be root.
        self.assertFalse((nested_base / "planwise-evals-probe").exists())

    def test_succeeds_with_no_ancestor_project(self):
        # The passing arm -- proves the guard discriminates rather than
        # refusing everything unconditionally.
        clean_base = self.tmp / "clean"
        clean_base.mkdir()

        scratch_root = scratch.ScratchRoot.create(
            run_id="probe", base_temp=clean_base,
            transcripts_root=self.tmp / "transcripts",
        )

        self.assertTrue(scratch_root.root.exists())
        # `create()` resolves the root (Fix 1's containment scan needs a
        # resolved path) -- compare resolved-vs-resolved so this assertion
        # doesn't itself depend on `clean_base` already being canonical.
        self.assertEqual(scratch_root.root, (clean_base / "planwise-evals-probe").resolve())

    def test_refuses_via_a_relative_base_path_reaching_a_planted_ancestor(self):
        # An unresolved relative `base_temp`'s `.parents` chain terminates
        # at "." -- for a single-component relative path (what `Path(".")
        # / name` collapses to) that chain is JUST `["."]`, which the
        # filesystem resolves against the process cwd and no further. The
        # marker is planted two levels ABOVE cwd, a level the unresolved
        # chain can never reach (it never walks past "."), so this arm
        # fails against the pre-fix code and is the one that proves the
        # resolve-before-walking fix actually matters.
        ancestor = self.tmp / "fake-project-relative"
        (ancestor / "planwise").mkdir(parents=True)
        (ancestor / "planwise" / "config.yaml").write_text("name: fake\n")
        nested_base = ancestor / "nested" / "deeper"
        nested_base.mkdir(parents=True)

        original_cwd = Path.cwd()
        os.chdir(nested_base)
        try:
            relative_base = Path(".")
            self.assertFalse(relative_base.is_absolute())

            with self.assertRaises(scratch.ScratchContainmentError):
                scratch.ScratchRoot.create(run_id="rel-probe", base_temp=relative_base)
        finally:
            os.chdir(original_cwd)


class TestExplicitRunIdCollision(unittest.TestCase):
    """A colliding explicit `run_id` must be refused, never silently
    adopted -- `copy_plugin_subtree()`'s unconditional `rmtree(dest)` on a
    second `create()` call would otherwise delete the first run's live
    plugin copy out from under it.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_colliding_explicit_run_id_is_refused_not_adopted(self):
        base = self.tmp / "collide-base"
        base.mkdir()

        first = scratch.ScratchRoot.create(
            run_id="dup-run", base_temp=base, transcripts_root=self.tmp / "transcripts",
        )
        # Content a silent adoption would put at risk.
        marker_file = first.root / "first-run-marker.txt"
        marker_file.write_text("first run's content\n")

        with self.assertRaises(scratch.ScratchContainmentError):
            scratch.ScratchRoot.create(
                run_id="dup-run", base_temp=base, transcripts_root=self.tmp / "transcripts",
            )

        # The refusal must leave the first run's tree completely intact --
        # nothing adopted, nothing deleted.
        self.assertTrue(marker_file.exists())
        self.assertEqual(marker_file.read_text(), "first run's content\n")

    def test_a_generated_run_id_never_spuriously_collides(self):
        base = self.tmp / "generated-base"
        base.mkdir()

        first = scratch.ScratchRoot.create(base_temp=base, transcripts_root=self.tmp / "transcripts")
        second = scratch.ScratchRoot.create(base_temp=base, transcripts_root=self.tmp / "transcripts")

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotEqual(first.root, second.root)


class TestPluginSubtreeManifest(unittest.TestCase):
    """`copy_plugin_subtree()` trusts the copy only on a matching manifest."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / "source-plugin"
        (self.source / "handlers").mkdir(parents=True)
        (self.source / "handlers" / "help.md").write_text("help body\n")
        (self.source / "README.md").write_text("readme body\n")

        self.scratch = scratch.ScratchRoot.create(
            run_id="mfst", base_temp=self.tmp / "base",
            transcripts_root=self.tmp / "transcripts",
        )

    def test_matching_manifest_is_trusted(self):
        dest = self.scratch.copy_plugin_subtree(self.source)

        self.assertTrue(dest.exists())
        self.assertEqual(self.scratch.plugin_copy, dest)
        self.assertTrue((dest / "handlers" / "help.md").exists())

    def test_mismatched_manifest_refuses(self):
        # The failing arm: simulate a partial/corrupt copy that silently
        # drops one source file, and prove the mismatch is caught rather
        # than silently trusted. Hand-rolled rather than wrapping the real
        # `shutil.copytree` -- that function recurses into subdirectories
        # via the module-global `copytree` name, so a naive wrapper would
        # re-enter this same patch for every subdirectory.
        def _partial_copytree(src, dst, *args, **kwargs):
            src, dst = Path(src), Path(dst)
            for path in src.rglob("*"):
                rel = path.relative_to(src)
                if rel.name == "README.md":
                    continue
                target = dst / rel
                if path.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
            return dst

        with patch.object(scratch.shutil, "copytree", side_effect=_partial_copytree):
            with self.assertRaises(scratch.ScratchContainmentError):
                self.scratch.copy_plugin_subtree(self.source)


class TestCaseDirUniqueness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scratch = scratch.ScratchRoot.create(
            run_id="uniq", base_temp=self.tmp / "base",
            transcripts_root=self.tmp / "transcripts",
        )

    def test_new_case_dir_refuses_an_existing_path(self):
        case_dir = self.scratch.new_case_dir("case-1")
        case_dir.mkdir(parents=True)

        with self.assertRaises(scratch.ScratchContainmentError):
            self.scratch.new_case_dir("case-1")

    def test_new_case_dir_does_not_create_on_disk(self):
        case_dir = self.scratch.new_case_dir("case-2")

        self.assertFalse(case_dir.exists())


class TestTeardown(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.scratch = scratch.ScratchRoot.create(
            run_id="td", base_temp=self.tmp / "base",
            transcripts_root=self.tmp / "transcripts",
        )

    def _make_case_dir(self, name: str) -> Path:
        case_dir = self.scratch.root / name
        (case_dir / "sub").mkdir(parents=True)
        (case_dir / "sub" / "result.json").write_text("{}")
        return case_dir

    def test_refuses_a_target_outside_the_scratch_root(self):
        # The failing arm the containment assertion exists to prove: a
        # teardown pointed outside the scratch root must refuse and must
        # delete nothing.
        outside = self.tmp / "not-scratch"
        outside.mkdir()

        with self.assertRaises(scratch.ScratchContainmentError):
            scratch.teardown(outside, self.scratch.root)

        self.assertTrue(outside.exists())

    def test_keep_on_fail_retains_the_dir(self):
        case_dir = self._make_case_dir("failed-case")

        removed = scratch.teardown(case_dir, self.scratch.root, failed=True, keep_failed=True)

        self.assertFalse(removed)
        self.assertTrue(case_dir.exists())

    def test_failed_without_keep_still_deletes(self):
        case_dir = self._make_case_dir("failed-case-no-keep")

        removed = scratch.teardown(case_dir, self.scratch.root, failed=True, keep_failed=False)

        self.assertTrue(removed)
        self.assertFalse(case_dir.exists())

    def test_retries_a_transient_rmtree_failure_then_succeeds(self):
        case_dir = self._make_case_dir("retry-case")
        real_rmtree = shutil.rmtree
        calls = {"n": 0}

        def _flaky_rmtree(path, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("simulated held handle")
            return real_rmtree(path, *args, **kwargs)

        with patch.object(scratch.shutil, "rmtree", side_effect=_flaky_rmtree), \
             patch.object(scratch.time, "sleep", return_value=None):
            removed = scratch.teardown(case_dir, self.scratch.root, retries=3, backoff_s=0.01)

        self.assertTrue(removed)
        self.assertFalse(case_dir.exists())
        self.assertEqual(calls["n"], 2)

    def test_exhausting_retries_raises(self):
        case_dir = self._make_case_dir("stuck-case")

        with patch.object(scratch.shutil, "rmtree", side_effect=OSError("stuck")), \
             patch.object(scratch.time, "sleep", return_value=None):
            with self.assertRaises(scratch.ScratchContainmentError):
                scratch.teardown(case_dir, self.scratch.root, retries=2, backoff_s=0.01)


class TestTranscriptDelta(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scratch_selftest_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.transcripts = self.tmp / "transcripts"
        self.transcripts.mkdir()
        (self.transcripts / "existing-session").mkdir()

    def test_reports_only_the_delta_and_deletes_nothing(self):
        scratch_root = scratch.ScratchRoot.create(
            run_id="delta", base_temp=self.tmp / "base",
            transcripts_root=self.transcripts,
        )
        (self.transcripts / "new-session-1").mkdir()
        (self.transcripts / "new-session-2").mkdir()

        delta = scratch_root.report_transcript_delta()

        self.assertEqual(delta, 2)
        # Nothing was removed by the report -- all three entries remain.
        self.assertEqual(
            sorted(p.name for p in self.transcripts.iterdir()),
            ["existing-session", "new-session-1", "new-session-2"],
        )


if __name__ == "__main__":
    unittest.main()
