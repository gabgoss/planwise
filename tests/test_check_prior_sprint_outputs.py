#!/usr/bin/env python3
"""Unit tests for check_prior_sprint_outputs.py, the closeout guard against
silently mutating a COMPLETE prior sprint's Outputs/ artifact.

Each test builds an isolated temp git repo with a synthetic planwise tree: a
Master Plan carrying a `## Session Completion Tracking` table naming a
COMPLETE session, and that session's own `Outputs/` directory. The guard is
invoked through its real CLI entry point (main() with an injected argv), so
the actual argument parsing, git-status parsing, and exit-code paths run.

Covers the behavior matrix:
  * a tracked modification inside a COMPLETE session's Outputs/ blocks, names
    the owning sprint/session, and exits 1;
  * an untracked addition in the same folder is allowed and exits 0;
  * `--current-session` excludes that session's own Outputs/ from the guard;
  * a repo with no git available (or the dir isn't a repo) never fails
    closed -- it reports "guard inactive" on the coverage line and exits 0;
  * a Master Plan with no parseable tracking table is reported as an
    uncovered plan (never silently inferred) and still exits 0;
  * a rename OUT of a COMPLETE Outputs/ dir blocks as a deletion -- the old
    path is one of the two NUL-separated fields a rename entry emits;
  * the REALISTIC deployment shape -- a git repo rooted ABOVE plans_dir (e.g.
    `{repo_root}/planwise/Plans/...`) -- is detected correctly and the
    reported path resolves to the real on-disk file. `git status --porcelain`
    always reports paths relative to the repository ROOT, never to the
    subprocess cwd; the script resolves them via `_git_context`'s
    `git rev-parse --show-toplevel` rather than assuming plans_dir is the
    root. TestNestedRepoRoot below is the regression guard for that fix.

Tests that need git are skipped when git is not on PATH.

Run with:  python -m pytest tests/test_check_prior_sprint_outputs.py -q
"""

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_prior_sprint_outputs  # noqa: E402


CONFIG_YAML_FIXTURE = """project:
  name: "CheckPriorSprintOutputsFixtureProject"
  backlog_dir: "Backlog"
  plans_dir: "Plans"
  index_files:
    backlog: "00-Index-Backlog.md"
"""


def _write_master_plan(
    plans_dir: Path,
    plan_dir_name: str,
    abbrev: str,
    sprint: str,
    session: str,
    status: str,
    summary_rel_path: str,
) -> Path:
    plan_dir = plans_dir / plan_dir_name
    plan_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "# Master Plan\n\n"
        "## Session Completion Tracking\n\n"
        "| Sprint | Session | Status | Summary File |\n"
        "|--------|---------|--------|---------------|\n"
        f"| {sprint} | {session} | {status} | [Summary]({summary_rel_path}) |\n"
    )
    path = plan_dir / f"{abbrev}-Master-Plan.md"
    path.write_text(content, encoding="utf-8")
    return path


def _run_main(argv_tail: list[str]) -> tuple[str, str, object]:
    """Invoke check_prior_sprint_outputs.main() with an injected argv.

    Returns (stdout, stderr, exit_code). main() always calls sys.exit(0 or 1).
    """
    saved_argv = sys.argv
    sys.argv = ["check_prior_sprint_outputs"] + argv_tail
    out, err = io.StringIO(), io.StringIO()
    exit_code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                check_prior_sprint_outputs.main()
            except SystemExit as e:
                exit_code = e.code
    finally:
        sys.argv = saved_argv
    return out.getvalue(), err.getvalue(), exit_code


class _GitFixtureBase(unittest.TestCase):
    """A temp git repo with a `planwise/Plans` tree inside it.

    The repo root is pinned to plans_dir itself (not self.tmp), which keeps
    these fixtures focused on the guard's matching/blocking DECISION logic
    (blocking codes, coverage line, exit codes, rename handling,
    --current-session exclusion) in isolation. `_git_context` now resolves
    `git status --porcelain` paths against the real repo root (via
    `git rev-parse --show-toplevel`), not against plans_dir, so this
    repo-root == plans_dir layout is just the simplest case that contract
    supports -- it is no longer required for correctness. The REALISTIC
    deployment shape -- a repo rooted ABOVE plans_dir -- is covered
    separately by `_NestedGitFixtureBase` / `TestNestedRepoRoot` below,
    which is the regression guard for the path-base fix.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check_prior_sprint_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        self._git("init")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test Runner")

    def _git(self, *args, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(self.plans_dir), capture_output=True, check=check,
        )

    def _commit_all(self, message: str = "snapshot") -> None:
        self._git("add", "-A")
        self._git("commit", "-m", message)

    def write_master_plan(self, plan_dir_name, abbrev, sprint, session, status, summary_rel_path) -> Path:
        return _write_master_plan(
            self.plans_dir, plan_dir_name, abbrev, sprint, session, status, summary_rel_path
        )


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestTrackedModificationBlocks(_GitFixtureBase):
    def test_tracked_modification_blocks_names_owner_and_exits_1(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        # Filename carries a space -- the guard's git-status parsing must
        # split on NUL, not whitespace.
        summary_file = outputs_dir / "Session 01 Summary.md"
        summary_file.write_text("Original summary content.\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/Session 01 Summary.md",
        )
        self._commit_all()

        # Mutate the tracked artifact of record after the sprint closed.
        summary_file.write_text("Silently overwritten.\n", encoding="utf-8")

        out, err, code = _run_main(["--config", str(self.config_path)])

        self.assertEqual(code, 1)
        self.assertIn("BLOCKING", out)
        self.assertIn("TP Sprint-01-Core Session-01-Build", out)
        self.assertIn(
            "Coverage: 1 COMPLETE session Outputs/ dirs checked; "
            "0 plan(s) had no parseable tracking table.",
            out,
        )


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestUntrackedAddIsAllowed(_GitFixtureBase):
    def test_untracked_file_in_outputs_is_allowed_and_exits_0(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (outputs_dir / "existing.md").write_text("existing\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/existing.md",
        )
        self._commit_all()

        # A brand-new file, never staged -- untracked.
        (outputs_dir / "new-note.md").write_text("new\n", encoding="utf-8")

        out, err, code = _run_main(["--config", str(self.config_path)])

        self.assertEqual(code, 0)
        self.assertNotIn("BLOCKING", out)


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestCurrentSessionExclusion(_GitFixtureBase):
    def test_current_sessions_own_outputs_is_excluded(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        summary = outputs_dir / "summary.md"
        summary.write_text("v1\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/summary.md",
        )
        self._commit_all()

        summary.write_text("v2 -- modified by the session currently closing out\n", encoding="utf-8")

        session_dir = self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build"
        out, err, code = _run_main(
            ["--config", str(self.config_path), "--current-session", str(session_dir)]
        )

        self.assertEqual(code, 0)
        self.assertNotIn("BLOCKING", out)


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestRenameOutOfOutputsBlocksAsDeletion(_GitFixtureBase):
    def test_rename_out_of_a_complete_outputs_dir_blocks(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        original = outputs_dir / "summary.md"
        original.write_text("The artifact of record.\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/summary.md",
        )
        self._commit_all()

        # Rename the tracked artifact OUT of Outputs/ -- must block exactly
        # like a deletion. Stage it so git reports a rename (R) rather than a
        # delete+untracked-add pair.
        moved = self.plans_dir / "Widgets" / "summary-moved.md"
        original.rename(moved)
        self._git("add", "-A")

        out, err, code = _run_main(["--config", str(self.config_path)])

        self.assertEqual(code, 1)
        self.assertIn("BLOCKING", out)
        self.assertIn("TP Sprint-01-Core Session-01-Build", out)


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestNoParseableTrackingTable(_GitFixtureBase):
    def test_plan_without_a_tracking_table_is_reported_uncovered_not_inferred(self):
        plan_dir = self.plans_dir / "Untracked-Plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "TP2-Master-Plan.md").write_text(
            "# Master Plan\n\nNo Session Completion Tracking section here.\n",
            encoding="utf-8",
        )

        out, err, code = _run_main(["--config", str(self.config_path)])

        self.assertEqual(code, 0)
        self.assertIn(
            "Coverage: 0 COMPLETE session Outputs/ dirs checked; "
            "1 plan(s) had no parseable tracking table.",
            out,
        )


class _NestedGitFixtureBase(unittest.TestCase):
    """A temp git repo rooted ABOVE plans_dir -- the realistic deployment
    shape, where plans_dir sits nested under a project's real repo root
    (e.g. `{repo_root}/planwise/Plans/...`, with source code and other
    project files as siblings of `planwise/`). `git status --porcelain`
    reports paths relative to `self.repo_root`, not to `self.plans_dir` --
    this is the layout that was silently broken before `_git_context`
    resolved the actual root via `git rev-parse --show-toplevel` instead of
    assuming plans_dir was the root.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check_prior_sprint_nested_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.repo_root = self.tmp  # git root sits ABOVE planwise_dir
        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        self._git("init")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test Runner")

    def _git(self, *args, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(self.repo_root), capture_output=True, check=check,
        )

    def _commit_all(self, message: str = "snapshot") -> None:
        self._git("add", "-A")
        self._git("commit", "-m", message)

    def write_master_plan(self, plan_dir_name, abbrev, sprint, session, status, summary_rel_path) -> Path:
        return _write_master_plan(
            self.plans_dir, plan_dir_name, abbrev, sprint, session, status, summary_rel_path
        )


@unittest.skipIf(shutil.which("git") is None, "git not on PATH")
class TestNestedRepoRoot(_NestedGitFixtureBase):
    """Regression guard for the path-base fix: the guard must still detect a
    hazard when the git repo root is a real ancestor of plans_dir, not
    plans_dir itself. Assertion (1) in
    test_tracked_modification_is_detected_in_a_nested_repo is the one that
    fails against the pre-fix `plans_dir`-based resolution -- against that
    code, `_enclosing_outputs_dir` joins `plans_dir` with an already
    repo-root-relative path like "planwise/Plans/Widgets/.../summary.md",
    producing a nonexistent, doubled
    ".../planwise/Plans/planwise/Plans/Widgets/.../summary.md" that never
    matches any entry in `complete_dirs` -- so the finding is silently
    dropped and the guard exits 0 on a real hazard.
    """

    def test_tracked_modification_is_detected_in_a_nested_repo(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        summary_file = outputs_dir / "summary.md"
        summary_file.write_text("Original summary content.\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/summary.md",
        )
        self._commit_all()

        # Mutate the tracked artifact of record after the sprint closed.
        summary_file.write_text("Silently overwritten.\n", encoding="utf-8")

        out, err, code = _run_main(["--config", str(self.config_path)])

        # (1) Detected -- this is the assertion that fails against the
        # pre-fix plans_dir-based path resolution; it is the point of this
        # test, not a restatement of the plans_dir-rooted tests above.
        self.assertEqual(code, 1)
        self.assertIn("BLOCKING", out)
        self.assertIn("TP Sprint-01-Core Session-01-Build", out)

        # (2) The reported path resolves to the real on-disk file -- not a
        # doubled ".../planwise/Plans/planwise/Plans/..." path.
        reported_path_line = next(
            line for line in out.splitlines() if line.strip().startswith("path:")
        )
        self.assertIn(str(summary_file.resolve()), reported_path_line)
        doubled_segment = str(Path("planwise") / "Plans" / "planwise" / "Plans")
        self.assertNotIn(doubled_segment, reported_path_line)

    def test_current_session_exclusion_in_a_nested_repo(self):
        outputs_dir = (
            self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build" / "Outputs"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        summary = outputs_dir / "summary.md"
        summary.write_text("v1\n", encoding="utf-8")

        self.write_master_plan(
            "Widgets", "TP", "Sprint-01-Core", "Session-01-Build", "✅ COMPLETE",
            "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/summary.md",
        )
        self._commit_all()

        summary.write_text("v2 -- modified by the session currently closing out\n", encoding="utf-8")

        session_dir = self.plans_dir / "Widgets" / "Exec-TP" / "Sprint-01-Core" / "Session-01-Build"
        out, err, code = _run_main(
            ["--config", str(self.config_path), "--current-session", str(session_dir)]
        )

        self.assertEqual(code, 0)
        self.assertNotIn("BLOCKING", out)


class TestNoGitRepo(unittest.TestCase):
    """Runs regardless of whether git is installed: a temp dir that was never
    `git init`-ed must never fail closed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check_prior_sprint_test_nogit_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

    def test_no_git_repo_reports_guard_inactive_and_exits_0(self):
        _write_master_plan(
            self.plans_dir, "Widgets", "TP", "Sprint-01-Core", "Session-01-Build",
            "✅ COMPLETE", "Exec-TP/Sprint-01-Core/Session-01-Build/Outputs/summary.md",
        )

        out, err, code = _run_main(["--config", str(self.config_path)])

        self.assertEqual(code, 0)
        self.assertIn("Not a git repository", out)
        self.assertIn(
            "Coverage: 1 COMPLETE session Outputs/ dirs checked; "
            "0 plan(s) had no parseable tracking table.",
            out,
        )


if __name__ == "__main__":
    unittest.main()
