#!/usr/bin/env python3
"""Tests for worktree_scan.sibling_dirs and the linked-worktree union in the id allocators.

The allocators used to read only the current tree, so two linked worktrees of
one repository could allocate the same id. `parse_backlog --next-id` now also
reads the backlog and Archive folders of every other linked worktree. The two
lesson allocators, `parse_lessons --next-id` and `reconcile_lessons --next-id`,
read the other worktrees' lessons folders, and so does the renumber floor.

Each union fixture is a real git repository with a real linked worktree. Each
tree's hub file comes from `generate_backlog_index.main()` or
`generate_lessons_index.main()`, so the reader sees the producer's own output.
An item file with no index row comes from `update_backlog.main() --create`.
The last class mocks git and needs no installed copy.

Run with:  python -m pytest tests/test_worktree_scan.py -q
"""

import contextlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_backlog_index
import generate_lessons_index
import lessons_index_run
import parse_backlog
import parse_lessons
import reconcile_lessons
import update_backlog
import worktree_scan

CONFIG_YAML_FIXTURE = """project:
  name: "WorktreeScanFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

LESSONS_CONFIG_YAML_FIXTURE = """project:
  name: "WorktreeScanFixtureProject"
  lessons_dir: "LessonsLearned"
  index_files:
    lessons: "00-Index-LessonsLearned.md"
lesson_statuses:
- documented
"""

CURRENT_ID = 5
SIBLING_ID = 120

# Variables that point git at another repository whatever `-C` says. A git hook
# exports some of them, and a fixture `git init` would then act on that repository.
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_NAMESPACE",
)


def _force_remove(func, path, _exc):
    """Clear a read-only bit that blocks a delete on Windows, then retry."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:
        shutil.rmtree(path, onerror=_force_remove)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestWorktreeScan(unittest.TestCase):
    """A real repository, one real linked worktree, and a hub per tree."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="worktree_scan_test_"))
        self.addCleanup(_rmtree, self.tmp)
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        environ = mock.patch.dict(os.environ)
        environ.start()
        self.addCleanup(environ.stop)
        for name in GIT_LOCATION_VARS:
            os.environ.pop(name, None)

    def git(self, repo: Path, *args: str) -> None:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"git {' '.join(args)} failed: {proc.stderr}")

    def make_repo(self, name: str = "repo") -> Path:
        repo = self.tmp / name
        repo.mkdir()
        self.git(repo, "init")
        self.git(
            repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
            "commit", "--allow-empty", "-m", "init",
        )
        return repo

    def add_worktree(self, repo: Path, name: str = "wt") -> Path:
        sibling = self.tmp / name
        self.git(repo, "worktree", "add", "-b", f"{name}-branch", str(sibling))
        return sibling

    def build_tree(self, root: Path, item_id: int) -> Path:
        """Write one item file and generate the hub in `root`. Return the config path."""
        planwise = root / "planwise"
        backlog = planwise / "Backlog"
        (backlog / "Archive").mkdir(parents=True)
        config_path = planwise / "config.yaml"
        config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        (backlog / f"BB-{item_id:03d}-01-BUG-Fixture.md").write_text(
            "---\n"
            f"id: {item_id}\n"
            "title: Fixture item\n"
            "priority: Medium\n"
            "status: NOT_STARTED\n"
            "abbrev: BUG\n"
            "created: 2026-01-01\n"
            "blocks: []\n"
            "---\n\n"
            "# Fixture item\n",
            encoding="utf-8",
        )
        sys.argv = ["generate_backlog_index", "--config", str(config_path), "--write"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = generate_backlog_index.main()
        self.assertEqual(code, 0, f"generator failed: {err.getvalue()}")
        return config_path

    def next_id(self, config_path: Path) -> str:
        sys.argv = ["parse_backlog", "--config", str(config_path), "--next-id"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            parse_backlog.main()
        return out.getvalue().strip()

    def test_next_id_reads_sibling_worktree(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_tree(repo, CURRENT_ID)
        self.build_tree(sibling, SIBLING_ID)
        found = worktree_scan.sibling_dirs(repo / "planwise" / "Backlog")
        self.assertEqual([p.resolve() for p in found], [(sibling / "planwise" / "Backlog").resolve()])
        self.assertEqual(self.next_id(config_path), f"{SIBLING_ID + 1:03d}")

    def test_no_git_folder_returns_empty(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        config_path = self.build_tree(plain, CURRENT_ID)
        # A repository above the temp folder must not be found.
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertEqual(worktree_scan.sibling_dirs(plain / "planwise" / "Backlog"), [])
            self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")

    def test_single_worktree_returns_empty(self):
        repo = self.make_repo()
        config_path = self.build_tree(repo, CURRENT_ID)
        self.assertEqual(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog"), [])
        self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")

    def test_removed_worktree_is_skipped(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_tree(repo, CURRENT_ID)
        self.build_tree(sibling, SIBLING_ID)
        # Positive control: the sibling is visible before its folder is deleted.
        self.assertEqual(len(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog")), 1)
        _rmtree(sibling)  # git still lists the worktree: no `git worktree prune`
        self.assertEqual(worktree_scan.sibling_dirs(repo / "planwise" / "Backlog"), [])
        self.assertEqual(self.next_id(config_path), f"{CURRENT_ID + 1:03d}")

    def create_item(self, config_path: Path, item_id: str, topic: str) -> tuple[object, str]:
        """Run the real `--create` writer. It writes the item file and no index row."""
        sys.argv = [
            "update_backlog", "--config", str(config_path), "--create", "--id", item_id,
            "--files", f"BB-{'NNN' if item_id == 'next' else item_id}-01-BUG-{topic}.md",
            "--feature", f"{topic} item", "--priority", "Medium",
            "--status", "NOT_STARTED", "--abbrev", "BUG",
        ]
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                update_backlog.main()
            except SystemExit as stop:
                code = stop.code
        return code, err.getvalue()

    def unindexed_pair(self) -> tuple[Path, Path, Path]:
        """Both trees index id 005. The linked worktree also holds id 120 with no row."""
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_tree(repo, CURRENT_ID)
        sibling_config = self.build_tree(sibling, CURRENT_ID)
        code, err = self.create_item(sibling_config, str(SIBLING_ID), "Sibling")
        self.assertEqual(code, 0, err)
        return repo, sibling, config_path

    def sibling_item(self, sibling: Path) -> Path:
        return sibling / "planwise" / "Backlog" / f"BB-{SIBLING_ID}-01-BUG-Sibling.md"

    def test_unindexed_sibling_item_file_raises_the_next_id(self):
        _repo, sibling, config_path = self.unindexed_pair()
        self.assertTrue(self.sibling_item(sibling).is_file())
        self.assertEqual(self.next_id(config_path), f"{SIBLING_ID + 1:03d}")

    def test_unindexed_sibling_archive_file_raises_the_next_id(self):
        _repo, sibling, config_path = self.unindexed_pair()
        item = self.sibling_item(sibling)
        item.rename(item.parent / "Archive" / item.name)
        self.assertEqual(self.next_id(config_path), f"{SIBLING_ID + 1:03d}")

    def test_sibling_item_file_with_no_readable_frontmatter_counts_by_its_name(self):
        _repo, sibling, config_path = self.unindexed_pair()
        self.sibling_item(sibling).write_bytes(b"\xe9 not UTF-8\n")
        sys.argv = ["parse_backlog", "--config", str(config_path), "--next-id"]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            parse_backlog.main()
        self.assertEqual(out.getvalue().strip(), f"{SIBLING_ID + 1:03d}")
        self.assertIn(self.sibling_item(sibling).name, err.getvalue())

    def test_sibling_archive_counts_when_this_tree_has_no_archive_folder(self):
        # git tracks no empty folder, so a fresh worktree can lack Archive/.
        repo, sibling, config_path = self.unindexed_pair()
        item = self.sibling_item(sibling)
        item.rename(item.parent / "Archive" / item.name)
        (repo / "planwise" / "Backlog" / "Archive").rmdir()
        self.assertEqual(self.next_id(config_path), f"{SIBLING_ID + 1:03d}")

    def test_unlistable_sibling_folder_is_named_on_stderr(self):
        repo, sibling, _config_path = self.unindexed_pair()
        backlog = repo / "planwise" / "Backlog"
        real = Path.iterdir

        def deny(path):
            if path.resolve().is_relative_to(sibling.resolve()):
                raise PermissionError(13, "Access is denied", str(path))
            return real(path)

        err = io.StringIO()
        with mock.patch.object(Path, "iterdir", deny), contextlib.redirect_stderr(err):
            found = parse_backlog.sibling_item_ids(
                backlog, backlog / "Archive", backlog / "00-Index-Backlog.md"
            )
        self.assertEqual(found, {})
        self.assertIn("could not read", err.getvalue())

    def test_only_a_file_name_this_tree_lacks_is_opened_in_a_sibling(self):
        # Both trees hold the id-005 file name. Opening every sibling item file
        # would hold the creation lock past its timeout on a large backlog.
        _repo, sibling, config_path = self.unindexed_pair()
        opened: list[Path] = []
        real = parse_backlog._read_frontmatter_map

        def spy(path, *args):
            opened.append(Path(path).resolve())
            return real(path, *args)

        with mock.patch.object(parse_backlog, "_read_frontmatter_map", spy):
            self.next_id(config_path)
        self.assertEqual(
            [path.name for path in opened if path.is_relative_to(sibling.resolve())],
            [self.sibling_item(sibling).name],
        )

    def test_create_refuses_an_id_that_only_a_sibling_item_file_holds(self):
        repo, sibling, config_path = self.unindexed_pair()
        backlog = repo / "planwise" / "Backlog"
        code, err = self.create_item(config_path, str(SIBLING_ID), "Here")
        self.assertEqual(code, 1, err)
        self.assertIn("already exists", err)
        self.assertIn(self.sibling_item(sibling).name, err)
        self.assertFalse((backlog / f"BB-{SIBLING_ID}-01-BUG-Here.md").exists())
        # Control: `--id next` still creates here, above the sibling's id.
        code, err = self.create_item(config_path, "next", "Free")
        self.assertEqual(code, 0, err)
        self.assertTrue((backlog / f"BB-{SIBLING_ID + 1}-01-BUG-Free.md").is_file())


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestLessonIdsAcrossWorktrees(unittest.TestCase):
    """The lesson side of the same union: one lesson file and a hub per tree."""

    # The git helpers are the backlog class's own. Borrowing them avoids
    # inheriting that class, which would run its backlog cases a second time.
    tmp: Path
    git = TestWorktreeScan.git
    make_repo = TestWorktreeScan.make_repo
    add_worktree = TestWorktreeScan.add_worktree
    setUp = TestWorktreeScan.setUp

    def build_lessons(self, root: Path, lesson_id: int) -> Path:
        """Write one lesson file and generate the hub in `root`. Return the config path."""
        planwise = root / "planwise"
        lessons = planwise / "LessonsLearned"
        (lessons / "Archive").mkdir(parents=True)
        config_path = planwise / "config.yaml"
        config_path.write_text(LESSONS_CONFIG_YAML_FIXTURE, encoding="utf-8")
        (lessons / f"LL-{lesson_id:03d}-PROC-Fixture.md").write_text(
            "---\n"
            f"id: LL-{lesson_id:03d}\n"
            "title: Fixture lesson\n"
            "category: process\n"
            "severity: medium\n"
            "language: [python]\n"
            "technology: [claude-code]\n"
            "domain: [PROC]\n"
            "source: fixture\n"
            "status: documented\n"
            "---\n\n"
            f"# LL-{lesson_id:03d}: Fixture lesson\n",
            encoding="utf-8",
        )
        code, _out, err = self.run_script(generate_lessons_index, config_path, "--write")
        self.assertEqual(code, 0, f"generator failed: {err}")
        return config_path

    def run_script(self, module, config_path: Path, *args: str):
        sys.argv = [module.__name__, "--config", str(config_path), *args]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main()
        return code, out.getvalue().strip(), err.getvalue()

    def load(self, config_path: Path) -> dict:
        sys.argv = ["test", "--config", str(config_path)]
        return config_loader.load_config()

    def pair(self) -> tuple[Path, Path]:
        """A repository holding LL-005 and a linked worktree holding LL-120."""
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_lessons(repo, CURRENT_ID)
        self.build_lessons(sibling, SIBLING_ID)
        return repo, config_path

    def test_next_id_reads_sibling_worktree(self):
        _repo, config_path = self.pair()
        expected = f"LL-{SIBLING_ID + 1:03d}"
        self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[1], expected)
        self.assertEqual(self.run_script(reconcile_lessons, config_path, "--next-id")[1], expected)
        result = parse_lessons.compute_next_id(self.load(config_path), include_siblings=True)
        self.assertIn("linked worktree", result["found_in"])

    def test_counter_and_check_stay_local(self):
        repo, config_path = self.pair()
        config = self.load(config_path)
        self.assertEqual(parse_lessons.compute_next_id(config)["next"], CURRENT_ID + 1)
        self.assertEqual(lessons_index_run.check_lessons_index(config)["findings"], [])
        # Regenerate while the sibling already holds its higher id.
        code, _out, err = self.run_script(generate_lessons_index, config_path, "--write")
        self.assertEqual(code, 0, f"generator failed: {err}")
        hub = repo / "planwise" / "LessonsLearned" / "00-Index-LessonsLearned.md"
        counter = reconcile_lessons.COUNTER_RE.search(hub.read_text(encoding="utf-8"))
        self.assertEqual(int(counter.group(2)), CURRENT_ID + 1)
        config = self.load(config_path)
        self.assertEqual(reconcile_lessons.detect_drift(config)["drifts"], [])
        self.assertFalse(reconcile_lessons.reconcile(config)["written"])

    def test_sibling_index_row_alone_raises_the_next_id(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_lessons(repo, CURRENT_ID)
        self.build_lessons(sibling, SIBLING_ID)
        lessons = sibling / "planwise" / "LessonsLearned"
        (lessons / f"LL-{SIBLING_ID:03d}-PROC-Fixture.md").unlink()
        self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[1], f"LL-{SIBLING_ID + 1:03d}")

    def test_sibling_archive_file_alone_raises_the_next_id(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_lessons(repo, CURRENT_ID)
        self.build_lessons(sibling, SIBLING_ID)
        lessons = sibling / "planwise" / "LessonsLearned"
        name = f"LL-{SIBLING_ID:03d}-PROC-Fixture.md"
        (lessons / name).rename(lessons / "Archive" / name)
        (lessons / "00-Index-LessonsLearned.md").unlink()  # leave the archived file as the only source
        self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[1], f"LL-{SIBLING_ID + 1:03d}")

    def test_renumber_floor_covers_sibling_ids(self):
        _repo, config_path = self.pair()
        config = self.load(config_path)
        with self.assertRaises(reconcile_lessons.RenumberRefused) as caught:
            reconcile_lessons.renumber(config, CURRENT_ID, CURRENT_ID + 2)
        self.assertIn(f"LL-{SIBLING_ID + 1:03d}", str(caught.exception))
        self.assertIn("linked worktree", str(caught.exception))

    def test_next_id_names_a_sibling_set_floor_on_stderr(self):
        _repo, config_path = self.pair()
        _code, out, err = self.run_script(parse_lessons, config_path, "--next-id")
        self.assertEqual(out, f"LL-{SIBLING_ID + 1:03d}")
        self.assertIn("linked worktree", err)
        self.assertIn(f"LL-{CURRENT_ID + 1:03d}", err)

    def test_sibling_holding_the_same_ids_prints_no_note(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_lessons(repo, CURRENT_ID)
        self.build_lessons(sibling, CURRENT_ID)
        self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[2], "")

    def test_unreadable_sibling_hub_keeps_its_file_name_ids(self):
        repo = self.make_repo()
        sibling = self.add_worktree(repo)
        config_path = self.build_lessons(repo, CURRENT_ID)
        self.build_lessons(sibling, SIBLING_ID)
        hub = sibling / "planwise" / "LessonsLearned" / "00-Index-LessonsLearned.md"
        hub.write_bytes(b"\xe9 not UTF-8\n")
        code, out, err = self.run_script(parse_lessons, config_path, "--next-id")
        self.assertEqual((code, out), (0, f"LL-{SIBLING_ID + 1:03d}"))
        self.assertIn("could not read", err)

    def test_single_worktree_stays_local(self):
        repo = self.make_repo()
        config_path = self.build_lessons(repo, CURRENT_ID)
        expected = f"LL-{CURRENT_ID + 1:03d}"
        self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[1], expected)

    def test_no_git_folder_stays_local(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        config_path = self.build_lessons(plain, CURRENT_ID)
        expected = f"LL-{CURRENT_ID + 1:03d}"
        # A repository above the temp folder must not be found.
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp)}):
            self.assertEqual(self.run_script(parse_lessons, config_path, "--next-id")[1], expected)


class TestNoGitBinary(unittest.TestCase):
    """git is mocked in every case, so this class needs no installed git."""

    # Borrowed helpers, so neither source class runs its cases a second time.
    tmp: Path
    setUp = TestWorktreeScan.setUp
    build_tree = TestWorktreeScan.build_tree
    next_id = TestWorktreeScan.next_id
    build_lessons = TestLessonIdsAcrossWorktrees.build_lessons
    run_script = TestLessonIdsAcrossWorktrees.run_script

    def test_launch_failure_returns_empty(self):
        for error in (FileNotFoundError(2, "git"), subprocess.TimeoutExpired("git", 10)):
            with (
                self.subTest(error=type(error).__name__),
                mock.patch.object(worktree_scan.subprocess, "run", side_effect=error) as run,
            ):
                self.assertEqual(worktree_scan.sibling_dirs(self.tmp / "plain"), [])
                self.assertEqual(run.call_count, 1)

    def test_next_ids_stay_local(self):
        backlog_config = self.build_tree(self.tmp / "backlog", CURRENT_ID)
        lessons_config = self.build_lessons(self.tmp / "lessons", CURRENT_ID)
        expected = f"LL-{CURRENT_ID + 1:03d}"
        error = FileNotFoundError(2, "git")
        with mock.patch.object(worktree_scan.subprocess, "run", side_effect=error) as run:
            self.assertEqual(self.next_id(backlog_config), f"{CURRENT_ID + 1:03d}")
            self.assertGreater(run.call_count, 0)
            for module in (parse_lessons, reconcile_lessons):
                with self.subTest(allocator=module.__name__):
                    # Reset per allocator, so each one must reach git by itself.
                    run.reset_mock()
                    self.assertEqual(self.run_script(module, lessons_config, "--next-id")[1], expected)
                    self.assertGreater(run.call_count, 0)

    def test_worktree_list_failure_returns_empty(self):
        top = subprocess.CompletedProcess([], 0, stdout=f"{self.tmp.as_posix()}\n".encode())
        failures = {
            "timeout": subprocess.TimeoutExpired("git", 10),
            "non-zero exit": subprocess.CompletedProcess([], 128, stdout=b""),
        }
        for name, second in failures.items():
            with (
                self.subTest(failure=name),
                mock.patch.object(worktree_scan.subprocess, "run", side_effect=[top, second]) as run,
            ):
                self.assertEqual(worktree_scan.sibling_dirs(self.tmp / "plain"), [])
                self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
