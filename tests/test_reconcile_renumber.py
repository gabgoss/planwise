"""Tests for the anchored-write helper and the `--renumber` mode.

Three groups:
  - `TestAnchoredWriteHelper`: `reconcile_common.apply_anchored_edits` refuses a
    bad anchor, a failed pre-state, a failed invariant and an existing rename
    target. Each refusal leaves every byte unchanged and no `.tmp-` file.
  - `TestRenumberLesson`: `reconcile_lessons.py --renumber`.
  - `TestRenumberBacklog`: `reconcile_backlog.py --renumber`.

The lesson files, item files and indexes are built the way the producers
build them. The files follow the template frontmatter shape, and each index
comes from the real generator (`generate_lessons_index.py`,
`generate_backlog_index.py`), not from a hand-typed table.
"""

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_loader
import reconcile_backlog
import reconcile_common
import reconcile_lessons
from reconcile_common import (
    AnchoredEdit,
    AnchoredWriteError,
    Rename,
    apply_anchored_edits,
    prose_mentions,
    regenerate_index,
)

CONFIG_YAML = """project:
  name: "RenumberFixtureProject"
  backlog_dir: "Backlog"
  lessons_dir: "LessonsLearned"
  index_files:
    backlog: "00-Index-Backlog.md"
    lessons: "00-Index-LessonsLearned.md"
"""


def _snapshot(root: Path) -> dict:
    """Every file under `root` as {relative path: bytes}."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class _TmpBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_renumber_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def no_temp_files(self, root: Path):
        leftovers = [p.name for p in root.rglob("*") if ".tmp-" in p.name]
        self.assertEqual(leftovers, [], "a refused or rolled-back write left a temp file")


class TestAnchoredWriteHelper(_TmpBase):
    def write(self, name: str, text: str, newline: str = "\n") -> Path:
        path = self.tmp / name
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
        return path

    def assert_refused(self, edits, renames=(), invariant=None, message=None):
        before = _snapshot(self.tmp)
        with self.assertRaises(AnchoredWriteError) as ctx:
            apply_anchored_edits(edits, renames, invariant)
        if message:
            self.assertIn(message, str(ctx.exception))
        self.assertEqual(_snapshot(self.tmp), before, "a refusal changed a byte")
        self.no_temp_files(self.tmp)

    def test_single_match_applies_once(self):
        path = self.write("a.md", "alpha\nbeta\n")
        report = apply_anchored_edits([AnchoredEdit(path, "beta", "gamma")])
        self.assertEqual(path.read_text(encoding="utf-8"), "alpha\ngamma\n")
        self.assertEqual(len(report), 1)

    def test_zero_and_multiple_matches_are_refused(self):
        path = self.write("a.md", "dup\nx\ndup\n")
        cases = {
            "zero": (AnchoredEdit(path, "absent", "y"), "matches 0 times"),
            "two": (AnchoredEdit(path, "dup", "y"), "matches 2 times"),
            "empty anchor": (AnchoredEdit(path, "", "y"), "empty anchor"),
        }
        for key, (edit, message) in cases.items():
            with self.subTest(case=key):
                self.assert_refused([edit], message=message)

    def test_pinned_anchor_allows_a_repeated_line_and_refuses_a_wrong_offset(self):
        path = self.write("a.md", "dup\nx\ndup\n")
        self.assert_refused([AnchoredEdit(path, "dup", "y", at=1)], message="not at offset 1")
        apply_anchored_edits([AnchoredEdit(path, "dup\n", "", at=6)])
        self.assertEqual(path.read_text(encoding="utf-8"), "dup\nx\n")

    def test_pre_state_and_invariant_failures_are_refused(self):
        path = self.write("a.md", "one\ntwo\n")
        self.assert_refused(
            [AnchoredEdit(path, "two", "2", expect_pre=lambda text: text.startswith("zero"))],
            message="pre-state check failed",
        )
        self.assert_refused(
            [AnchoredEdit(path, "two", "2")],
            invariant=lambda planned: "two must survive" if "two" not in planned[path] else None,
            message="two must survive",
        )

    def test_overlapping_edits_are_refused(self):
        path = self.write("a.md", "abcdef\n")
        self.assert_refused(
            [AnchoredEdit(path, "abcd", "x", at=0), AnchoredEdit(path, "cdef", "y", at=2)],
            message="overlap",
        )

    def test_existing_rename_target_is_refused_after_planning_every_edit(self):
        src = self.write("a.md", "one\n")
        dst = self.write("b.md", "taken\n")
        self.assert_refused([AnchoredEdit(src, "one", "1")], [Rename(src, dst)], message="already exists")

    def test_missing_rename_source_and_shared_target_are_refused(self):
        src = self.write("a.md", "one\n")
        other = self.write("c.md", "two\n")
        free = self.tmp / "free.md"
        self.assert_refused([], [Rename(self.tmp / "gone.md", free)], message="does not exist")
        self.assert_refused([], [Rename(src, free), Rename(other, free)], message="share this target")

    def test_write_failure_rolls_back_files_and_renames(self):
        first = self.write("a.md", "one\n")
        second = self.write("b.md", "two\n")
        moved = self.write("c.md", "three\n")
        renamed = self.tmp / "c-new.md"
        before = _snapshot(self.tmp)
        real = reconcile_common.write_text_preserving_newlines
        calls = []

        def flaky(path, content):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("injected write failure")
            real(path, content)

        with patch.object(reconcile_common, "write_text_preserving_newlines", flaky), self.assertRaises(OSError):
            apply_anchored_edits(
                [AnchoredEdit(first, "one", "1"), AnchoredEdit(second, "two", "2")],
                [Rename(moved, renamed)],
            )
        self.assertEqual(_snapshot(self.tmp), before)
        self.assertFalse(renamed.exists())
        self.no_temp_files(self.tmp)

    def test_rename_failure_rolls_back_the_written_files(self):
        path = self.write("a.md", "one\n")
        src = self.write("b.md", "two\n")
        before = _snapshot(self.tmp)
        rename_fails = patch.object(reconcile_common.os, "rename", side_effect=OSError("injected rename failure"))
        with rename_fails, self.assertRaises(OSError):
            apply_anchored_edits([AnchoredEdit(path, "one", "1")], [Rename(src, self.tmp / "x.md")])
        self.assertEqual(_snapshot(self.tmp), before)

    def test_crlf_lines_the_edit_never_touches_round_trip(self):
        path = self.write("a.md", "keep one\nchange me\nkeep two\n", newline="\r\n")
        apply_anchored_edits([AnchoredEdit(path, "change me", "changed")])
        data = path.read_bytes()
        self.assertEqual(data, b"keep one\r\nchanged\r\nkeep two\r\n")

    def test_prose_mentions_match_the_whole_token(self):
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "p.md").write_text("see BB-12 here\nBB-123 is other\nXBB-12 no\nBB-12-01 yes\n", encoding="utf-8")
        rows = prose_mentions(self.tmp, "BB-12")
        self.assertEqual(rows, ["sub/p.md:1", "sub/p.md:4"])


class _RenumberBase(_TmpBase):
    """A planwise tree with a config, lesson files and item files."""

    def setUp(self):
        super().setUp()
        self.planwise = self.tmp / "planwise"
        self.lessons = self.planwise / "LessonsLearned"
        self.backlog = self.planwise / "Backlog"
        for folder in (self.lessons / "Archive", self.backlog / "Archive"):
            folder.mkdir(parents=True)
        self.config_path = self.planwise / "config.yaml"
        self.config_path.write_text(CONFIG_YAML, encoding="utf-8")
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["test_reconcile_renumber", "--config", str(self.config_path)]
        self.config = config_loader.load_config()

    def lesson(self, number: int, name: str = "Fixture", promoted_to: str | None = None, newline: str = "\n") -> Path:
        owner = f"promoted-to: {promoted_to}\n" if promoted_to else ""
        text = (
            f"---\nid: LL-{number:03d}\ntitle: Fixture lesson {number}\ndate: 2026-01-01\nsource: fixture\n"
            "category: pattern\nseverity: medium\nlanguage: [python]\ntechnology: [fixture]\ndomain: [PROC]\n"
            f"status: documented\napplied-as: null\n{owner}---\n\n"
            f"# LL-{number:03d}-PROC: Fixture lesson {number}\n\n## Context\n\nBody line.\n"
        )
        path = self.lessons / f"LL-{number:03d}-PROC-{name}.md"
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
        return path

    def item(self, number: int, name: str = "Fixture", blocks: str = "[]", archived: bool = False, status: str = "NOT_STARTED") -> Path:
        text = (
            f"---\nid: {number:03d}\ntitle: \"Fixture item {number}\"\npriority: Medium\nstatus: {status}\n"
            f"abbrev: INFRA\ncreated: 2026-01-01\nblocks: {blocks}\nrefined: false\n---\n\n"
            f"# BB-{number:03d}-01-INFRA: Fixture item {number}\n\n## Summary\n\nBody line.\n"
        )
        path = (self.backlog / "Archive" if archived else self.backlog) / f"BB-{number:03d}-01-INFRA-{name}.md"
        path.write_bytes(text.encode("utf-8"))  # bytes: write_text would turn each LF into CRLF on Windows
        return path

    def generate(self):
        self.assertEqual(regenerate_index("generate_lessons_index.py", self.config), 0)
        self.assertEqual(regenerate_index("generate_backlog_index.py", self.config), 0)

    def cli(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / script), "--config", str(self.config_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def index_family_text(self, folder: Path) -> str:
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(folder.rglob("*.md")) if p.name.startswith(("00-", "Index-")))

    def quiet(self, func, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return func(*args)


class TestRenumberLesson(_RenumberBase):
    def setUp(self):
        super().setUp()
        for number in (1, 2, 3):
            self.lesson(number)
        self.generate()

    def test_renumber_one_lesson(self):
        old = self.lessons / "LL-002-PROC-Fixture.md"
        (self.planwise / "notes.md").write_text("A note about LL-002 and LL-0020.\n", encoding="utf-8")
        lines = self.quiet(reconcile_lessons.renumber, self.config, 2, 9)
        new = self.lessons / "LL-009-PROC-Fixture.md"
        self.assertFalse(old.exists())
        text = new.read_text(encoding="utf-8")
        self.assertIn("id: LL-009\n", text)
        self.assertIn("# LL-009-PROC: Fixture lesson 2\n", text)
        index = self.index_family_text(self.lessons)
        self.assertIn("LL-009-PROC-Fixture.md", index)
        self.assertNotIn("LL-002-PROC-Fixture.md", index)
        report = "\n".join(lines)
        self.assertIn("id: LL-002 -> LL-009", report)
        self.assertIn("notes.md:1", report, "the prose mention is reported by path:line")
        self.assertIn("LL-002 and", (self.planwise / "notes.md").read_text(encoding="utf-8"), "prose stays unchanged")

    def test_refuses_renumber_on_duplicate_anchor(self):
        twin = self.lessons / "LL-002-PROC-Twin.md"
        twin.write_text(self.lesson(2).read_text(encoding="utf-8"), encoding="utf-8")
        before = _snapshot(self.tmp)
        done = self.cli("reconcile_lessons.py", "--renumber", "LL-002", "LL-009")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("LL-002-PROC-Fixture.md", done.stderr)
        self.assertIn("LL-002-PROC-Twin.md", done.stderr)
        self.assertEqual(_snapshot(self.tmp), before)
        self.no_temp_files(self.tmp)

    def test_file_selector_moves_one_of_two_claimants(self):
        twin = self.lessons / "LL-002-PROC-Twin.md"
        twin.write_text(self.lesson(2).read_text(encoding="utf-8"), encoding="utf-8")
        done = self.cli("reconcile_lessons.py", "--renumber", "2", "9", "--file", "LL-002-PROC-Twin.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.lessons / "LL-009-PROC-Twin.md").exists())
        self.assertTrue((self.lessons / "LL-002-PROC-Fixture.md").exists())

    def test_refusals_exit_2_and_write_nothing(self):
        cases = {
            "new below the floor": (("--renumber", "2", "3"), "below the next free id"),
            "new claimed by a file": (("--renumber", "2", "1"), "below the next free id"),
            "old unclaimed": (("--renumber", "50", "60"), "no lesson file claims"),
            "not an id": (("--renumber", "two", "60"), "not a lesson id"),
        }
        for key, (args, message) in cases.items():
            with self.subTest(case=key):
                before = _snapshot(self.tmp)
                done = self.cli("reconcile_lessons.py", *args)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(message, done.stderr)
                self.assertEqual(_snapshot(self.tmp), before)

    def test_refuses_renumber_with_write_flag(self):
        done = self.cli("reconcile_lessons.py", "--renumber", "2", "9", "--write")
        self.assertEqual(done.returncode, 2)

    def test_legacy_index_shape_is_refused(self):
        index = self.lessons / "00-Index-LessonsLearned.md"
        index.write_text("# Lessons\n\n## Master Table\n\n| ID | Title |\n|----|-------|\n| LL-001 | x |\n", encoding="utf-8")
        before = _snapshot(self.tmp)
        done = self.cli("reconcile_lessons.py", "--renumber", "2", "9")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("/planwise upgrade", done.stderr)
        self.assertEqual(_snapshot(self.tmp), before)

    def test_crlf_lines_the_renumber_never_touches_round_trip(self):
        path = self.lesson(5, name="Crlf", newline="\r\n")
        self.generate()
        before = path.read_bytes()
        self.quiet(reconcile_lessons.renumber, self.config, 5, 9)
        after = (self.lessons / "LL-009-PROC-Crlf.md").read_bytes()
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"), "a bare LF appeared")
        self.assertEqual(after.replace(b"LL-009", b"LL-005"), before)


class TestRenumberBacklog(_RenumberBase):
    def setUp(self):
        super().setUp()
        self.target = self.item(10, "Target")
        self.blocker = self.item(11, "Blocker", blocks="[010, 013]")
        self.block_form = self.item(12, "BlockForm", blocks="\n  - 010\n  - 013")
        self.archived = self.item(13, "Done", blocks="[10]", archived=True, status="COMPLETE")
        self.owner_lesson = self.lesson(1, promoted_to="BB-010, BLI-010, BB-011")
        self.generate()

    def test_renumber_one_backlog_item(self):
        (self.planwise / "plan.md").write_text("Item BB-010 and BB-0100.\n", encoding="utf-8")
        lines = self.quiet(reconcile_backlog.renumber, self.config, 10, 20)
        moved = self.backlog / "BB-020-01-INFRA-Target.md"
        self.assertFalse(self.target.exists())
        text = moved.read_text(encoding="utf-8")
        self.assertIn("id: 020\n", text)
        self.assertIn("# BB-020-01-INFRA: Fixture item 10\n", text)
        self.assertIn("blocks: [020, 013]", self.blocker.read_text(encoding="utf-8"))
        self.assertIn("blocks: \n  - 020\n  - 013\n", self.block_form.read_text(encoding="utf-8"))
        self.assertIn("blocks: [20]", self.archived.read_text(encoding="utf-8"), "an entry keeps its own width")
        self.assertIn("promoted-to: BB-020, BLI-020, BB-011", self.owner_lesson.read_text(encoding="utf-8"))
        self.assertIn("BB-020-01-INFRA-Target.md", self.index_family_text(self.backlog))
        report = "\n".join(lines)
        self.assertIn("plan.md:1", report)
        self.assertIn("BB-010 and", (self.planwise / "plan.md").read_text(encoding="utf-8"), "prose stays unchanged")

    def test_refuses_renumber_on_duplicate_anchor(self):
        twin = self.item(10, "Twin")
        before = _snapshot(self.tmp)
        done = self.cli("reconcile_backlog.py", "--renumber", "10", "20")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(self.target.name, done.stderr)
        self.assertIn(twin.name, done.stderr)
        self.assertEqual(_snapshot(self.tmp), before)
        self.no_temp_files(self.tmp)

    def test_duplicate_with_file_selector_leaves_the_ambiguous_references(self):
        self.item(10, "Twin")
        blocker_before = self.blocker.read_bytes()
        done = self.cli("reconcile_backlog.py", "--renumber", "10", "20", "--file", "BB-010-01-INFRA-Twin.md")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.backlog / "BB-020-01-INFRA-Twin.md").exists())
        self.assertTrue(self.target.exists())
        self.assertEqual(self.blocker.read_bytes(), blocker_before)
        self.assertIn("ambiguous", done.stdout)

    def test_refusals_exit_2_and_write_nothing(self):
        cases = {
            "new below the floor": (("--renumber", "10", "12"), "below the next free id"),
            "new is claimed": (("--renumber", "10", "13"), "below the next free id"),
            "old unclaimed": (("--renumber", "99", "100"), "no item file claims"),
            "not an id": (("--renumber", "ten", "100"), "not a backlog id"),
        }
        for key, (args, message) in cases.items():
            with self.subTest(case=key):
                before = _snapshot(self.tmp)
                done = self.cli("reconcile_backlog.py", *args)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(message, done.stderr)
                self.assertEqual(_snapshot(self.tmp), before)

    def test_combining_with_body_status_exits_2(self):
        done = self.cli("reconcile_backlog.py", "--renumber", "10", "20", "--body-status")
        self.assertEqual(done.returncode, 2, done.stderr)

    def test_unknown_body_status_form_still_falls_through(self):
        done = self.cli("reconcile_backlog.py", "--body-status=1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unrecognized arguments", done.stderr)

    def test_crlf_lines_the_renumber_never_touches_round_trip(self):
        crlf = self.item(14, "Crlf")
        crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
        self.generate()
        before = crlf.read_bytes()
        self.quiet(reconcile_backlog.renumber, self.config, 14, 30)
        after = (self.backlog / "BB-030-01-INFRA-Crlf.md").read_bytes()
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"), "a bare LF appeared")
        self.assertEqual(after.replace(b"030", b"014"), before)


if __name__ == "__main__":
    unittest.main()
