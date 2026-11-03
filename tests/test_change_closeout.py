"""Tests for scripts/change_closeout.py: open plans and items listed, closed ones skipped.

Every fixture tree is built under `tempfile.mkdtemp()` and removed in
`tearDown`; nothing is written under the plugin repo.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from change_closeout import backlog_status, basename_regex, master_plan_status, scan

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "change_closeout.py"
NAME = "ref-file.md"


class ChangeCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="change_closeout_test_"))
        self.plans = self.tmp / "Plans"
        self.backlog = self.tmp / "Backlog"
        self.plans.mkdir()
        self.backlog.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def plan(self, name, status, task_text):
        root = self.plans / name
        self.write(root / f"{name}-Master-Plan.md", f"# Plan\n\n**Status:** {status} (note)\n")
        return self.write(root / "Sprint" / "task.md", task_text)

    def item(self, name, status, body):
        return self.write(self.backlog / name, f"---\nid: \"001\"\nstatus: {status}\n---\n{body}")

    def run_cli(self, *args):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--plans", str(self.plans),
             "--backlog", str(self.backlog), *args],
            capture_output=True, check=False,
        )
        return proc.returncode, proc.stdout.decode("utf-8")

    def test_every_unfinished_plan_status_is_open(self):
        # The plan vocabulary comes from list_plans.ACTIVE_STATUSES; a private
        # list once skipped REVIEWED, APPROVED, NEEDS_FIXES and PLANNING.
        statuses = ["PLANNING", "REVIEWED", "APPROVED", "NEEDS_FIXES", "READY_TO_EXECUTE", "IN_PROGRESS"]
        tasks = [self.plan(f"P{i}", s, f"cites {NAME}\n") for i, s in enumerate(statuses)]
        result = scan([NAME], self.plans, self.backlog)
        self.assertEqual(sorted(h[0] for h in result["hits"]), sorted(t.as_posix() for t in tasks))
        self.assertEqual(result["skipped"], {})

    def test_unfinished_backlog_statuses_are_open_and_unknown_is_skipped(self):
        blocked = self.item("BB-001-a.md", "BLOCKED", f"cites {NAME}\n")
        planning = self.item("BB-002-b.md", "PLANNING", f"cites {NAME}\n")
        self.item("BB-003-c.md", "PLANNED", f"cites {NAME}\n")
        result = scan([NAME], self.plans, self.backlog)
        self.assertEqual(sorted(h[0] for h in result["hits"]), sorted([blocked.as_posix(), planning.as_posix()]))
        self.assertEqual(result["skipped"], {"PLANNED": 1})

    def test_empty_quoted_status_is_counted_not_a_traceback(self):
        self.item("BB-001-a.md", '""', f"cites {NAME}\n")
        self.item("BB-002-b.md", "NOT_STARTED", f"cites {NAME}\n")
        code, out = self.run_cli("--changed", NAME)
        self.assertEqual(code, 0, out)
        self.assertIn("skipped: (none) 1\n", out)
        self.assertIn("1 hits", out)

    def test_open_plan_is_listed_and_complete_plan_is_not(self):
        open_task = self.plan("OpenPlan", "REVIEWED", f"Read `references/{NAME}` first.\n")
        closed_task = self.plan("DonePlan", "COMPLETE", f"Read `references/{NAME}` first.\n")
        result = scan([NAME], self.plans, self.backlog)
        paths = [hit[0] for hit in result["hits"]]
        self.assertIn(open_task.as_posix(), paths)
        self.assertNotIn(closed_task.as_posix(), paths)
        self.assertEqual(result["skipped"].get("COMPLETE"), 1)

    def test_status_outside_both_sets_is_skipped_and_counted(self):
        held = self.plan("HeldPlan", "ON_HOLD", f"cites {NAME}\n")
        code, out = self.run_cli("--changed", NAME)
        self.assertEqual(code, 0)
        self.assertNotIn(held.as_posix(), out)
        self.assertIn("skipped: ON_HOLD 1\n", out)
        self.assertNotIn("\r", out)

    def test_open_backlog_item_is_listed_and_closed_item_is_skipped(self):
        open_item = self.item("BB-001-a.md", "NOT_STARTED", f"Edit `{NAME}`.\n")
        closed_item = self.item("BB-002-b.md", "CLOSED", f"Edit `{NAME}`.\n")
        code, out = self.run_cli("--changed", NAME)
        self.assertEqual(code, 0)
        self.assertIn(f"{open_item.as_posix()}: NOT_STARTED: {NAME}\n", out)
        self.assertNotIn(closed_item.as_posix(), out)
        self.assertIn("skipped: CLOSED 1\n", out)

    def test_name_character_before_the_basename_is_not_a_hit(self):
        self.plan("OpenPlan", "IN_PROGRESS", f"see old-{NAME} and x{NAME}\n")
        result = scan([NAME], self.plans, self.backlog)
        self.assertEqual(result["hits"], [])

    def test_changed_path_is_reduced_to_its_basename(self):
        task = self.plan("OpenPlan", "READY_TO_EXECUTE", f"cites {NAME}\n")
        code, out = self.run_cli("--changed", f"plugins/references/{NAME}")
        self.assertEqual(code, 0)
        self.assertIn(f"{task.as_posix()}: READY_TO_EXECUTE: {NAME}\n", out)

    def test_part_file_is_not_a_master_plan(self):
        root = self.plans / "P"
        self.write(root / "P-Master-Plan.md", "**Status:** COMPLETE\n")
        self.write(root / "P-Master-Plan-Part-2-X.md", f"**Status:** IN_PROGRESS\ncites {NAME}\n")
        result = scan([NAME], self.plans, self.backlog)
        self.assertEqual(result["hits"], [])
        self.assertEqual(result["plans"], 1)

    def test_status_parsers(self):
        self.assertEqual(master_plan_status("x\n**Status:** IN_PROGRESS — all sprints\n"), "IN_PROGRESS")
        self.assertEqual(master_plan_status("no status line\n"), "(none)")
        self.assertEqual(backlog_status("---\nstatus: 'in_progress'\n---\nbody\n"), "IN_PROGRESS")
        self.assertEqual(backlog_status("# no frontmatter\n"), "(none)")
        self.assertEqual(backlog_status("---\nstatus: \"\"\n---\nbody\n"), "(none)")
        self.assertIsNotNone(basename_regex(NAME).search(f"path/{NAME}."))

    def test_missing_directory_exits_2(self):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--changed", NAME,
             "--plans", str(self.tmp / "nope"), "--backlog", str(self.backlog)],
            capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
