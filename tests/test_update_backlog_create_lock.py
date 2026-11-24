#!/usr/bin/env python3
"""Tests for update_backlog.py --create under the backlog creation lock.

`--create --id next` takes `{backlog_dir}/.backlog-create.lock`, computes the
next free id from the index and the on-disk item files, substitutes it for
the literal NNN in the first --files entry, and opens the new item file with
exclusive create, all while it holds the lock. An explicit --id runs under
the same lock. These cases pin the allocation, the refusals, the lock
cleanup, the held-lock timeout and two concurrent subprocess creates.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest tests/test_update_backlog_create_lock.py -q
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import parse_backlog
import update_backlog
from test_update_backlog import _UpdateBacklogFixtureBase

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "scripts" / "update_backlog.py"
)

THREE_ROWS = "".join(
    f"| {n:03d} | Item {n} | Medium | NOT_STARTED | TEST | - | "
    f"[BB-{n:03d}-01-TEST-Item.md](BB-{n:03d}-01-TEST-Item.md) |\n"
    for n in (1, 2, 3)
)


class TestCreateNextIdUnderLock(_UpdateBacklogFixtureBase):
    """--create allocates its own id under the creation lock."""

    def setUp(self):
        super().setUp()
        self.lock = self.backlog_dir / ".backlog-create.lock"

    def _create(self, item_id: str, files: str, feature: str = "Locked create"):
        return self._run_main(
            [
                "--config", str(self.config_path),
                "--create",
                "--id", item_id,
                "--feature", feature,
                "--priority", "Low",
                "--abbrev", "TEST",
                "--files", files,
            ]
        )

    def _item_files(self) -> list[str]:
        return sorted(p.name for p in self.backlog_dir.glob("BB-*.md"))

    def test_next_substitutes_the_allocated_id(self):
        self.write_index(THREE_ROWS)

        out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        new_file = self.backlog_dir / "BB-004-01-TEST-Topic.md"
        self.assertTrue(new_file.exists(), self._item_files())
        self.assertIn("\nid: 004\n", new_file.read_text(encoding="utf-8"))
        self.assertIn("Created backlog item 004", out)
        self.assertFalse(self.lock.exists())

        # The exclusive write keeps the bytes the old write_text produced.
        text = update_backlog._render_bli_file(
            "004", "Locked create", "Low", "NOT_STARTED", "TEST",
            ["BB-004-01-TEST-Topic.md"],
        )
        reference = self.tmp / "write_text-reference.md"
        reference.write_text(text, encoding="utf-8")
        self.assertEqual(new_file.read_bytes(), reference.read_bytes())

    def test_second_next_sees_the_first_without_regeneration(self):
        self.write_index(THREE_ROWS)

        _out1, err1, code1 = self._create("next", "BB-NNN-01-TEST-First.md")
        _out2, err2, code2 = self._create("next", "BB-NNN-01-TEST-Second.md")

        self.assertIsNone(code1, err1)
        self.assertIsNone(code2, err2)
        self.assertEqual(
            self._item_files(),
            ["BB-004-01-TEST-First.md", "BB-005-01-TEST-Second.md"],
        )

    def test_next_without_nnn_is_refused(self):
        self.write_index(THREE_ROWS)

        _out, err, code = self._create("next", "BB-004-01-TEST-Topic.md")

        self.assertEqual(code, 1)
        self.assertIn("NNN", err)
        self.assertEqual(self._item_files(), [])
        self.assertFalse(self.lock.exists())

    def test_held_lock_times_out_and_writes_nothing(self):
        self.write_index(THREE_ROWS)
        self.lock.write_text("", encoding="utf-8")

        with mock.patch.object(parse_backlog, "CREATE_LOCK_TIMEOUT", 0.2):
            _out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertEqual(code, 1)
        self.assertIn(str(self.lock), err)
        self.assertIn("delete the lock file", err)
        self.assertEqual(self._item_files(), [])
        self.assertTrue(self.lock.exists())

    def test_refused_create_leaves_no_lock(self):
        self.write_index("")
        self.write_item_file("BB-100-01-TEST-Held.md", status="NOT_STARTED", item_id="100")

        _out, err, code = self._create("100", "BB-100-01-TEST-Duplicate.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "BB-100-01-TEST-Duplicate.md").exists())
        self.assertFalse(self.lock.exists())

    def test_permission_error_on_lock_create_is_retried(self):
        # On Windows a lock file another process is still deleting makes
        # os.open raise PermissionError; the lock retries it like a held lock.
        real_open = os.open
        calls = []

        def flaky_open(path, flags, *args):
            calls.append(path)
            if len(calls) == 1:
                raise PermissionError(13, "Access is denied", path)
            return real_open(path, flags, *args)

        with (
            mock.patch.object(parse_backlog.os, "open", side_effect=flaky_open),
            parse_backlog.creation_lock(self.backlog_dir, timeout=5) as lock,
        ):
            self.assertTrue(lock.exists())

        self.assertGreaterEqual(len(calls), 2)
        self.assertFalse(self.lock.exists())

    def test_explicit_id_with_nnn_is_refused(self):
        self.write_index(THREE_ROWS)

        _out, err, code = self._create("050", "BB-NNN-01-TEST-Topic.md")

        self.assertEqual(code, 1)
        self.assertIn(
            "Error: --files carries the literal NNN, which only --id next replaces. "
            "Pass --id next, or name the file with its id. Nothing was written.",
            err,
        )
        self.assertEqual(self._item_files(), [])
        self.assertFalse(self.lock.exists())

    def test_inline_comment_id_is_seen_by_the_duplicate_guard(self):
        self.write_index("")
        self.write_item_file(
            "BB-047-01-TEST-Held.md", status="NOT_STARTED", item_id="047  # note"
        )

        _out, err, code = self._create("047", "BB-047-01-TEST-Duplicate.md")

        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.backlog_dir / "BB-047-01-TEST-Duplicate.md").exists())
        self.assertFalse(self.lock.exists())

    def test_next_on_non_numeric_ids_warns_and_allocates_001(self):
        self.write_index(
            "| ALPHA | Item A | Medium | NOT_STARTED | TEST | - | [a](a.md) |\n"
            "| BETA | Item B | Medium | NOT_STARTED | TEST | - | [b](b.md) |\n"
        )

        _out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        self.assertIn("none carried a numeric ID", err)
        self.assertEqual(self._item_files(), ["BB-001-01-TEST-Topic.md"])
        self.assertFalse(self.lock.exists())

    def test_two_concurrent_next_creates_file_distinct_ids(self):
        self.write_index(THREE_ROWS)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

        def launch(topic: str) -> subprocess.Popen:
            return subprocess.Popen(
                [
                    sys.executable, "-B", str(SCRIPT),
                    "--config", str(self.config_path),
                    "--create",
                    "--id", "next",
                    "--feature", f"Concurrent {topic}",
                    "--priority", "Low",
                    "--abbrev", "TEST",
                    "--files", f"BB-NNN-01-TEST-{topic}.md",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

        procs = [launch("Alpha"), launch("Beta")]
        results = [p.communicate(timeout=120) for p in procs]

        for proc, (_out, err) in zip(procs, results):
            self.assertEqual(proc.returncode, 0, err.decode("utf-8", "replace"))
        names = self._item_files()
        self.assertEqual(len(names), 2, names)
        ids = {name.split("-")[1] for name in names}
        self.assertEqual(ids, {"004", "005"}, names)
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
