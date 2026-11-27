#!/usr/bin/env python3
"""Tests for update_backlog.py --create under the backlog creation lock.

`--create --id next` takes `{backlog_dir}/.backlog-create.lock`, computes the
next free id from the index and the on-disk item files, substitutes it for
the literal NNN in the first --files entry, and opens the new item file with
exclusive create, all while it holds the lock. An explicit --id runs under
the same lock. These cases pin the allocation, the refusals, the lock
cleanup, the held-lock timeout and two concurrent subprocess creates.

A lock left by a killed owner is taken over. Those cases build the lock with
the real producer: a child process that enters `creation_lock` and is killed
or left alive.

Each test builds an isolated temp planwise tree; none mutate the live backlog.

Run with:  python -m pytest tests/test_update_backlog_create_lock.py -q
"""

import errno
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_create_lock as lock_module
import update_backlog
from update_backlog_fixture import _UpdateBacklogFixtureBase

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "plugins" / "planwise" / "scripts" / "update_backlog.py"
)

THREE_ROWS = "".join(
    f"| {n:03d} | Item {n} | Medium | NOT_STARTED | TEST | - | "
    f"[BB-{n:03d}-01-TEST-Item.md](BB-{n:03d}-01-TEST-Item.md) |\n"
    for n in (1, 2, 3)
)


# Enters the lock the way --create does, reports its pid, and waits to be killed.
HOLDER = """\
import os, sys, time
sys.path.insert(0, sys.argv[1])
from update_backlog import creation_lock
with creation_lock(sys.argv[2]):
    print("held", os.getpid(), flush=True)
    time.sleep(120)
"""


class _CreateUnderLockBase(_UpdateBacklogFixtureBase):
    """A temp backlog, a --create runner and real lock-holding child processes."""

    def setUp(self):
        super().setUp()
        self.lock = self.backlog_dir / ".backlog-create.lock"
        self.children: list[subprocess.Popen] = []

    def tearDown(self):
        # Before the base removes the temp tree: a live child holds the lock open.
        for child in self.children:
            self._end(child)
        super().tearDown()

    def _spawn(self, *argv: str) -> subprocess.Popen:
        child = subprocess.Popen(
            [sys.executable, "-B", *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.children.append(child)
        return child

    def _end(self, child: subprocess.Popen) -> None:
        child.kill()
        child.wait(timeout=60)
        child.stdout.close()
        child.stderr.close()

    def _start_holder(self) -> tuple[subprocess.Popen, int]:
        """A child that holds the creation lock, and the pid it holds it under."""
        child = self._spawn("-c", HOLDER, str(SCRIPT.parent), str(self.backlog_dir))
        words = child.stdout.readline().split()
        if words[:1] != [b"held"]:
            child.kill()
            self.fail(child.stderr.read().decode("utf-8", "replace"))
        return child, int(words[1])

    def _leave_dead_owner_lock(self) -> int:
        child, pid = self._start_holder()
        self._end(child)
        self.assertTrue(self.lock.exists())
        return pid

    def _launch_create(self, topic: str) -> subprocess.Popen:
        return self._spawn(
            str(SCRIPT),
            "--config", str(self.config_path),
            "--create",
            "--id", "next",
            "--feature", f"Concurrent {topic}",
            "--priority", "Low",
            "--abbrev", "TEST",
            "--files", f"BB-NNN-01-TEST-{topic}.md",
        )

    def _item_files(self) -> list[str]:
        return sorted(p.name for p in self.backlog_dir.glob("BB-*.md"))

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

class TestCreateNextIdUnderLock(_CreateUnderLockBase):
    """--create allocates its own id under the creation lock."""

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

        with mock.patch.object(lock_module, "CREATE_LOCK_TIMEOUT", 0.2):
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
            mock.patch.object(lock_module.os, "open", side_effect=flaky_open),
            lock_module.creation_lock(self.backlog_dir, timeout=5) as lock,
        ):
            self.assertTrue(lock.exists())

        self.assertGreaterEqual(len(calls), 2)
        self.assertFalse(self.lock.exists())

    def test_unwritable_folder_names_the_real_cause(self):
        self.write_index(THREE_ROWS)

        def denied_open(path, flags, *args):
            raise PermissionError(13, "Access is denied", path)

        with (
            mock.patch.object(lock_module.os, "open", side_effect=denied_open),
            mock.patch.object(lock_module, "CREATE_LOCK_TIMEOUT", 0.2),
        ):
            _out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertEqual(code, 1)
        self.assertIn("Access is denied", err)
        self.assertNotIn("delete the lock file", err)
        self.assertEqual(self._item_files(), [])

    def test_lock_removal_is_retried_on_permission_error(self):
        # On Windows another process that holds the lock file open makes
        # unlink raise PermissionError until it lets go.
        self.write_index(THREE_ROWS)
        real_unlink = Path.unlink
        calls = []

        def flaky_unlink(path, *args, **kwargs):
            if path == self.lock:
                calls.append(path)
                if len(calls) == 1:
                    raise PermissionError(13, "Access is denied", str(path))
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", flaky_unlink):
            out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        self.assertIn("Created backlog item 004", out)
        self.assertGreaterEqual(len(calls), 2)
        self.assertFalse(self.lock.exists())

    def test_unremovable_lock_warns_and_still_prints_the_id(self):
        self.write_index(THREE_ROWS)
        real_unlink = Path.unlink

        def stuck_unlink(path, *args, **kwargs):
            if path == self.lock:
                raise PermissionError(13, "Access is denied", str(path))
            return real_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(Path, "unlink", stuck_unlink),
            mock.patch.object(lock_module, "LOCK_RELEASE_TIMEOUT", 0.2),
        ):
            out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        self.assertIn("Created backlog item 004", out)
        self.assertIn("could not remove the backlog creation lock", err)
        # A released lock carries no record, so no later waiter takes it over.
        self.assertEqual(self.lock.read_bytes(), b"")
        self.assertEqual(self._item_files(), ["BB-004-01-TEST-Topic.md"])

    def test_lock_removal_failing_for_another_reason_warns_too(self):
        # The item file is written by now, so the caller must still see its id.
        self.write_index(THREE_ROWS)
        real_unlink = Path.unlink

        def broken_unlink(path, *args, **kwargs):
            if path == self.lock:
                raise OSError(errno.EIO, "Input/output error", str(path))
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", broken_unlink):
            out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        self.assertIn("Created backlog item 004", out)
        self.assertIn("could not remove the backlog creation lock", err)

    @unittest.skipIf(os.name == "nt", "Windows refuses to delete an open lock file")
    def test_release_leaves_a_lock_that_replaced_its_own(self):
        # A person deleted this owner's lock by hand, and another create took it.
        with lock_module.creation_lock(self.backlog_dir) as lock:
            lock.unlink()
            lock.write_bytes(b"another owner")

        self.assertEqual(self.lock.read_bytes(), b"another owner")

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

        procs = [self._launch_create("Alpha"), self._launch_create("Beta")]
        results = [p.communicate(timeout=120) for p in procs]

        for proc, (_out, err) in zip(procs, results):
            self.assertEqual(proc.returncode, 0, err.decode("utf-8", "replace"))
        names = self._item_files()
        self.assertEqual(len(names), 2, names)
        ids = {name.split("-")[1] for name in names}
        self.assertEqual(ids, {"004", "005"}, names)
        self.assertFalse(self.lock.exists())


class TestStaleCreationLock(_CreateUnderLockBase):
    """A lock is taken over only when its recorded owner is proven dead."""

    def setUp(self):
        super().setUp()
        self.write_index(THREE_ROWS)

    def _refused_create(self) -> str:
        """Run a create that must time out and leave the lock as it was."""
        before = self.lock.read_bytes()

        with mock.patch.object(lock_module, "CREATE_LOCK_TIMEOUT", 0.3):
            _out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertEqual(code, 1, err)
        self.assertIn("delete the lock file", err)
        self.assertNotIn("took over", err)
        self.assertEqual(self._item_files(), [])
        self.assertEqual(self.lock.read_bytes(), before)
        return err

    def test_killed_owner_lock_is_taken_over(self):
        pid = self._leave_dead_owner_lock()

        out, err, code = self._create("next", "BB-NNN-01-TEST-Topic.md")

        self.assertIsNone(code, err)
        self.assertIn("Created backlog item 004", out)
        self.assertIn("took over", err)
        self.assertIn(f"pid {pid}", err)
        self.assertFalse(self.lock.exists())

    def test_live_owner_lock_is_never_taken_over(self):
        child, pid = self._start_holder()

        err = self._refused_create()

        self.assertIn(f"pid {pid}", err)
        self.assertIsNone(child.poll())
        # The owner's own byte lock leaves the record readable.
        self.assertEqual(json.loads(self.lock.read_bytes())["pid"], pid)

    def test_failed_takeover_write_keeps_the_dead_owner_record(self):
        pid = self._leave_dead_owner_lock()
        full = OSError(errno.ENOSPC, "No space left on device")

        with mock.patch.object(lock_module.os, "write", side_effect=full):
            self.assertIsNone(lock_module._take_over(self.lock))

        # A later create can still prove the owner dead.
        self.assertEqual(json.loads(self.lock.read_bytes())["pid"], pid)

    def test_record_from_another_machine_is_never_taken_over(self):
        pid = self._leave_dead_owner_lock()
        real = json.loads(self.lock.read_bytes())

        for key in ("host", "os"):
            with self.subTest(key=key):
                altered = dict(real, **{key: real[key] + "-elsewhere"})
                self.lock.write_bytes(json.dumps(altered).encode("utf-8"))

                err = self._refused_create()

                self.assertIn(f"pid {pid}", err)

    def test_unparsable_record_is_never_taken_over(self):
        self._leave_dead_owner_lock()
        self.lock.write_bytes(self.lock.read_bytes()[:10] or b"{")

        self._refused_create()

    def test_without_os_lock_support_the_create_runs_and_records_nothing(self):
        real_unlink = Path.unlink
        records = []

        def spy_unlink(path, *args, **kwargs):
            if path == self.lock:
                records.append(path.read_bytes())
            return real_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(lock_module, "_try_lock", return_value=False),
            mock.patch.object(lock_module, "OWNER_LOCK_TIMEOUT", 0.1),
            mock.patch.object(Path, "unlink", spy_unlink),
            lock_module.creation_lock(self.backlog_dir) as lock,
        ):
            self.assertEqual(lock.read_bytes(), b"")

        self.assertEqual(records, [b""])
        self.assertFalse(self.lock.exists())

    def test_two_concurrent_creates_on_a_stale_lock_file_distinct_ids(self):
        self._leave_dead_owner_lock()

        procs = [self._launch_create("Alpha"), self._launch_create("Beta")]
        results = [p.communicate(timeout=120) for p in procs]

        errors = [err.decode("utf-8", "replace") for _out, err in results]
        for proc, err in zip(procs, errors):
            self.assertEqual(proc.returncode, 0, err)
        self.assertEqual(sum("took over" in err for err in errors), 1, errors)
        ids = {name.split("-")[1] for name in self._item_files()}
        self.assertEqual(ids, {"004", "005"}, self._item_files())
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
