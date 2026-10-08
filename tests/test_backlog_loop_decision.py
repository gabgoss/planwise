#!/usr/bin/env python3
"""Tests for the loop-mode documented skip and the no-question contract.

Two groups:

  * Script behaviour. `--mark --outcome SKIPPED` restores the item's pre-loop
    status, `--decision` writes a `## Loop Decision Needed` section into the
    item file, and `--mark --lessons` records lesson ids in the run file.
  * Text pins. After the setup questions, the loop-mode text of
    `handlers/backlog.md` and `handlers/backlog-Part-2-LoopMode.md` issues no
    question except the HALT question.

Run with:  python -m pytest tests/test_backlog_loop_decision.py -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_backlog_loop import _LoopFixtureBase

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
BACKLOG_HANDLER = PLUGIN / "handlers" / "backlog.md"
LOOP_PART2 = PLUGIN / "handlers" / "backlog-Part-2-LoopMode.md"
AUTO_MODE_POLICY = PLUGIN / "references" / "auto-mode-policy.md"

HEADING = "## Loop Decision Needed"
DECISION = "Question: route A or B?\nOptions: A, B.\nEvidence: the premise probe found no target."


class TestDocumentedSkip(_LoopFixtureBase):
    def pop_and_select(self, run_id: str, item_id: str = "001") -> None:
        """Pop the next item and flip it IN_PROGRESS, as the handler's Phase 2 does."""
        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual((code, popped["next"]), (0, item_id))
        self.write_item(item_id, "IN_PROGRESS", "short")

    def item_file(self, item_id: str) -> Path:
        return self.backlog_dir / f"{item_id}-INFRA-fixture-item.md"

    def test_next_records_pre_loop_status(self):
        payload = self.init("--mode", "all")
        code, _text, popped = self.loop("--next", "--run", payload["run"])

        self.assertEqual(code, 0)
        self.assertEqual(popped["pre_status"], "NOT_STARTED")
        self.assertEqual(self.read_run(payload)["items"]["001"]["pre_status"], "NOT_STARTED")

    def test_documented_skip_writes_section_and_restores_status(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id)

        code, text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION,
        )

        self.assertEqual(code, 0)
        self.assertEqual(marked["restored_status"], "NOT_STARTED")
        self.assertTrue(marked["decision_written"])
        self.assertIn("Restored 001 status to NOT_STARTED", text)

        body = self.item_file("001").read_text(encoding="utf-8")
        self.assertIn("status: NOT_STARTED", body)
        self.assertNotIn("status: IN_PROGRESS", body)
        self.assertEqual(body.count(HEADING), 1)
        self.assertIn("> [!gate] User input needed", body)
        self.assertIn(f"Loop run {run_id}", body)
        self.assertIn("Evidence: the premise probe found no target.", body)

        record = self.read_run(payload)["items"]["001"]
        self.assertEqual((record["phase"], record["outcome"]), ("closed", "SKIPPED"))
        self.assertTrue(record["user_input_needed"])
        self.assertTrue(record["note"].startswith("USER INPUT NEEDED"))

    def test_repeated_mark_does_not_stack_a_second_section(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id)
        args = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION)

        self.loop(*args)
        _code, _text, again = self.loop(*args)

        self.assertFalse(again["decision_written"])
        self.assertEqual(self.item_file("001").read_text(encoding="utf-8").count(HEADING), 1)

    def test_skip_without_decision_restores_status_and_writes_no_section(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id)

        code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--note", "halted-mid-item",
        )

        self.assertEqual(code, 0)
        self.assertEqual(marked["restored_status"], "NOT_STARTED")
        self.assertFalse(marked["decision_written"])
        self.assertNotIn(HEADING, self.item_file("001").read_text(encoding="utf-8"))
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(record["note"], "halted-mid-item")
        self.assertNotIn("user_input_needed", record)

    def test_skip_leaves_an_item_that_was_already_in_progress(self):
        self.write_item("001", "IN_PROGRESS", "short")
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual((code, popped["next"], popped["pre_status"]), (0, "001", "IN_PROGRESS"))

        _code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION,
        )

        self.assertIsNone(marked["restored_status"])
        self.assertIn("status: IN_PROGRESS", self.item_file("001").read_text(encoding="utf-8"))

    def test_decision_keeps_crlf_line_endings(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id)
        path = self.item_file("001")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION)

        raw = path.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF entered a CRLF file")

    def test_decision_rejects_other_outcomes_and_empty_text(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id)
        before = self.run_path(payload).read_bytes()

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE", "--decision", DECISION,
        )
        self.assertEqual(code, 1)
        self.assertIn("SKIPPED only", error["error"])
        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", "  ",
        )
        self.assertEqual(code, 1)
        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--phase", "acting", "--decision", DECISION,
        )
        self.assertEqual(code, 1)
        self.assertEqual(self.run_path(payload).read_bytes(), before)
        self.assertNotIn(HEADING, self.item_file("001").read_text(encoding="utf-8"))

    def test_end_summary_lists_flagged_items_and_lessons(self):
        payload = self.init("--mode", "n", "--n", "2")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION)
        code, _text, lessons = self.loop("--mark", "--run", run_id, "--id", "001", "--lessons", "LL-900, LL-901")
        self.assertEqual((code, lessons["lessons"]), (0, ["LL-900", "LL-901"]))
        self.loop("--boundary", "--run", run_id)
        self.loop("--next", "--run", run_id)
        self.loop("--mark", "--run", run_id, "--id", "002", "--outcome", "COMPLETE")

        _code, text, boundary = self.loop("--boundary", "--run", run_id)

        self.assertEqual(boundary["remaining"], 0)
        self.assertIn("User input needed", text)
        self.assertIn("Lessons filed during this run:", text)
        self.assertIn("001: LL-900, LL-901", text)


class TestLessonsMark(_LoopFixtureBase):
    def test_lessons_merge_without_duplicates_and_keep_the_boundary_event(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE")
        self.loop("--boundary", "--run", run_id)

        self.loop("--mark", "--run", run_id, "--id", "001", "--lessons", "LL-900")
        _code, _text, merged = self.loop("--mark", "--run", run_id, "--id", "001", "--lessons", "LL-900,LL-901")

        self.assertEqual(merged["lessons"], ["LL-900", "LL-901"])
        run = self.read_run(payload)
        self.assertEqual(run["items"]["001"]["lessons"], ["LL-900", "LL-901"])
        self.assertEqual(run["items"]["001"]["outcome"], "COMPLETE")
        # A lessons record is not a mark event, so the recorded boundary still stands.
        self.assertEqual([e["event"] for e in run["history"] if e["id"] == "001"][-3:],
                         ["boundary", "lessons", "lessons"])

    def test_lessons_stands_alone(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--lessons", "LL-900", "--outcome", "COMPLETE",
        )
        self.assertEqual(code, 1)
        self.assertIn("stands alone", error["error"])
        code, _text, error = self.loop("--mark", "--run", run_id, "--id", "001", "--lessons", " , ")
        self.assertEqual(code, 1)


def _question_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if "AskUserQuestion" in line]


class TestNoQuestionsAfterSetup(unittest.TestCase):
    """Text pins: the loop-mode sections ask nothing after Q1-Q3 and the HALT question."""

    def test_part_2_questions_are_the_setup_questions_and_halt(self):
        allowed = ("**Q1.**", "**Q2.**", "**HALT question.**", "a trailing `AskUserQuestion` defers")
        for line in _question_lines(LOOP_PART2.read_text(encoding="utf-8")):
            with self.subTest(line=line[:80]):
                self.assertTrue(any(anchor in line for anchor in allowed), f"unexpected question site: {line}")

    def test_backlog_loop_mode_lines_issue_no_question(self):
        for line in BACKLOG_HANDLER.read_text(encoding="utf-8").splitlines():
            if "In loop mode" in line or "in loop mode" in line:
                with self.subTest(line=line[:80]):
                    self.assertNotIn("AskUserQuestion", line)

    def test_part_2_carries_the_no_question_contract(self):
        text = LOOP_PART2.read_text(encoding="utf-8")
        for needle in (
            "## No questions after setup",
            "### Documented skip",
            "### Phase 8 in loop mode",
            "--decision",
            "--lessons",
            "Loop Decision Needed",
            "user_input_needed",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_backlog_handler_hooks_point_at_the_contract(self):
        text = BACKLOG_HANDLER.read_text(encoding="utf-8")
        for needle in ("--mark --lessons", "§ No questions after setup", "§ Documented skip"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_auto_mode_policy_lists_each_loop_default(self):
        text = AUTO_MODE_POLICY.read_text(encoding="utf-8")
        for row in (
            "Lessons capture (backlog.md Phase 8, loop mode)",
            "Phase 5 approval (backlog.md Phase 5, loop mode)",
            "Phase 3 conflict or failed premise (backlog.md Phase 3, loop mode)",
            "Route C or fix-agent `BLOCKED` (backlog.md Phase 4, loop mode)",
            "Follow-up candidate filing (backlog.md Phase 7, loop mode)",
            "Held-item notice (backlog.md Phase 2, loop mode)",
        ):
            with self.subTest(row=row):
                self.assertIn(row, text)

    def test_pin_discriminates_a_planted_question(self):
        planted = LOOP_PART2.read_text(encoding="utf-8") + "\nUse `AskUserQuestion`: route or skip?\n"
        allowed = ("**Q1.**", "**Q2.**", "**HALT question.**", "a trailing `AskUserQuestion` defers")
        unexpected = [line for line in _question_lines(planted) if not any(a in line for a in allowed)]
        self.assertEqual(len(unexpected), 1)


if __name__ == "__main__":
    unittest.main()
