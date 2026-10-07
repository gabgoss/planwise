#!/usr/bin/env python3
"""Regression tests for review fixes to backlog_loop.py.

One test per fixed defect. Each fails on the script as it stood before the fix.
The fixture and driver come from test_backlog_loop.py.

Run with:  python -m pytest tests/test_backlog_loop_review.py -q
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import backlog_loop
from test_backlog_loop import RUN_ID, _LoopFixtureBase


class TestReviewFixes(_LoopFixtureBase):
    def test_next_halts_when_current_has_no_outcome_before_acting(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        # The pop sets `current` with no phase; a session that died here must
        # not lose the item to a second pop.
        self.loop("--next", "--run", run_id)
        for phase in (None, "selected"):
            with self.subTest(phase=phase):
                if phase:
                    self.loop("--mark", "--run", run_id, "--id", "001", "--phase", phase)
                before = self.run_path(payload).read_bytes()

                code, _text, halted = self.loop("--next", "--run", run_id)

                self.assertEqual(code, 3)
                self.assertTrue(halted["halt"])
                self.assertEqual(halted["item"], "001")
                self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_boundary_ends_a_run_whose_queue_was_all_skipped(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        for item_id, kind in (("001", "short"), ("002", "steps"), ("006", "short"), ("007", "short")):
            self.write_item(item_id, "COMPLETE", kind)

        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertIsNone(popped["next"])
        self.assertEqual(popped["skipped"], ["001", "002", "006", "007"])

        code, text, boundary = self.loop("--boundary", "--run", run_id)

        self.assertEqual(code, 0)
        self.assertEqual(boundary["remaining"], 0)
        self.assertEqual(boundary["done"], "007")
        self.assertEqual(text.splitlines()[-2], boundary["marker"])
        self.assertTrue(self.read_run(payload)["ended"])

    def test_ended_run_refuses_next_and_mark(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        code, _text, ended = self.loop("--end", "--run", run_id)
        self.assertEqual(code, 0)
        before = self.run_path(payload).read_bytes()

        code, _text, refused = self.loop("--next", "--run", run_id)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "run already ended")
        code, _text, refused = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE"
        )
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "run already ended")
        self.assertEqual(self.run_path(payload).read_bytes(), before)

        # --end and --boundary stay idempotent on an ended run.
        code, _text, again = self.loop("--end", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertTrue(again["already_ended"])
        self.assertEqual(again["ended"], ended["ended"])

    def test_next_keeps_an_item_whose_frontmatter_cannot_be_read(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        # 001 loses its frontmatter: no evidence of a status flip, so it stays.
        (self.backlog_dir / "001-INFRA-fixture-item.md").write_text(
            "# Item 001\n\nNo frontmatter here.\n", encoding="utf-8"
        )
        # 002 is gone from the backlog directory (archived): not selectable.
        (self.backlog_dir / "002-INFRA-fixture-item.md").unlink()

        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual((code, popped["next"], popped["skipped"]), (0, "001", []))

        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE")
        _code, _text, second = self.loop("--next", "--run", run_id)
        self.assertEqual((second["next"], second["skipped"]), ("006", ["002"]))

    def test_init_cannot_take_a_name_another_init_is_about_to_write(self):
        real_save = backlog_loop.save_run
        inner: dict = {}
        entered: list = []

        def save_after_a_competing_init(path, data):
            if not entered:
                entered.append(True)
                # A second --init lands between this one's allocation and write.
                inner.update(self.init("--mode", "n", "--n", "1"))
            real_save(path, data)

        with patch.object(backlog_loop, "run_id_now", return_value=RUN_ID), patch.object(
            backlog_loop, "save_run", side_effect=save_after_a_competing_init
        ):
            outer = self.init("--mode", "all")

        self.assertNotEqual(outer["run"], inner["run"])
        self.assertEqual(sorted(p.name for p in self.runs_dir.glob("*.json")),
                         [f"{RUN_ID}-2.json", f"{RUN_ID}.json"])
        self.assertEqual(len(self.read_run(outer)["queue"]), 4)
        self.assertEqual(len(self.read_run(inner)["queue"]), 1)

    def test_failed_init_write_leaves_no_placeholder(self):
        with (
            patch.object(backlog_loop, "run_id_now", return_value=RUN_ID),
            patch.object(backlog_loop, "save_run", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            self.loop("--init", "--mode", "all")

        self.assertEqual(list(self.runs_dir.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
