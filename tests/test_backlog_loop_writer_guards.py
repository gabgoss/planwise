#!/usr/bin/env python3
"""Regression tests for the loop's item-file writers and its queue guards.

  * One fence scanner: a fence closes only on the same character, at least
    as long, so every writer agrees on what is fenced. A fenced end marker
    does not bound a legacy `## Loop Decision Needed` section.
  * `--decision` refuses a heading line of level 1, 2 or 3, an unclosed
    fence and the end-marker string, through the CLI, before any write.
  * `--decision` refuses an item file that leaves a fence open.
  * The question writer leaves a fenced example in the item unchanged.
  * A resolution file with a byte-order mark leaves no mark in the item.
  * `--needs-plan` clears the record's route, and the summary shows `-`.
  * `--init` never queues an item whose frontmatter says `needs_plan: true`.

Every fixture is written with `newline=""`, so the bytes on disk are the
bytes the test names.

Run with:  python -m pytest tests/test_backlog_loop_writer_guards.py -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_loop
import backlog_questions
import scoped_rules
import update_backlog
from test_backlog_loop import item_filename, item_text
from test_backlog_loop_gates import (
    DECISION,
    HEADING,
    RECORD,
    _GatesFixtureBase,
    old_section,
)

BOM = b"\xef\xbb\xbf"
RUN_1 = "20261001-090000"
END = "<!-- loop-decision-end -->"


class TestReviewRegressions(_GatesFixtureBase):
    def write_raw(self, path: Path, text: str) -> None:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def read_raw(self, path: Path) -> str:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def test_tilde_line_inside_backtick_fence_does_not_close_it(self):
        bodies = (
            "```markdown\n~~~\n## Loop Decision Needed\n```\n",
            "````markdown\n```\n## Loop Decision Needed\n````\n",
        )
        for fence in bodies:
            body = "Intro cites `src/keep.py`.\n\n" + fence + "\n## Notes\n\nNotes cite `src/notes.py`.\n"
            # Via the router's strip: nothing is a loop section, so nothing is removed.
            self.assertEqual(scoped_rules.strip_loop_sections(body), (body, 0))
            self.assertEqual(scoped_rules.loop_section_spans(body), [])
            # At the scanner: the opening fence holds until its own closing line.
            flags = scoped_rules.fence_flags(body)
            self.assertEqual(flags[2:7], [True, True, True, True, False])
        self.assertTrue(scoped_rules.fence_left_open("~~~\n```\n"))
        self.assertFalse(scoped_rules.fence_left_open("~~~~\n~~~\n~~~~~\n"))

    def test_decision_with_unclosed_fence_is_refused(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        item_before = self.item_file("001").read_bytes()
        run_before = self.run_path(payload).read_bytes()
        mark = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision")

        code, _text, error = self.loop(*mark, "Question: which route?\r\n```text\r\nexample, never closed")
        self.assertEqual(code, 1)
        self.assertIn("never closes", error["error"])
        code, _text, error = self.loop(*mark, f"Question: which route?\n{END}\nEvidence: none.")
        self.assertEqual(code, 1)
        self.assertIn(END, error["error"])
        self.assertEqual(self.item_file("001").read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

        code, _text, marked = self.loop(*mark, "Question: which route?\n```text\nexample\n```")
        self.assertEqual(code, 0)
        self.assertTrue(marked["decision_written"])

    def test_decision_with_h1_or_bare_h2_line_is_refused(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        item_before = self.item_file("001").read_bytes()
        run_before = self.run_path(payload).read_bytes()
        mark = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision")

        for line in ("# not a heading", "##", "##\tx", "#"):
            code, _text, error = self.loop(*mark, f"Question: x\n{line}\nOptions: (A)")
            self.assertEqual(code, 1, line)
            self.assertIn("heading line of level 1 or 2", error["error"])
        self.assertEqual(self.item_file("001").read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

    def test_decision_with_h3_line_is_refused(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        item_before = self.item_file("001").read_bytes()
        run_before = self.run_path(payload).read_bytes()
        mark = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision")

        for line in ("### Q2. A second question", "###", "###\tx"):
            code, _text, error = self.loop(*mark, f"Question: x\n{line}\nOptions: (A)")
            self.assertEqual(code, 1, line)
            self.assertIn("heading line of level 3", error["error"])
        self.assertEqual(self.item_file("001").read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

    def test_fenced_end_marker_does_not_bound_a_section(self):
        text = (
            "# T\n\n" + HEADING + "\n\n<!-- loop-decision run=old -->\nQ\n\n### Example\n\n"
            "```\n" + END + "\n## Fake\n```\n\nafter text\n\n## Notes\n"
        )
        start = text.index(HEADING)
        self.assertEqual(scoped_rules.loop_sections(text), [(start, text.index("## Notes"), False)])
        stripped, _removed = scoped_rules.strip_loop_sections(text)
        self.assertNotIn("## Fake", stripped)
        self.assertNotIn("```", stripped)
        self.assertEqual(stripped, "# T\n\n## Notes\n")

    def test_update_backlog_and_questions_agree_on_fenced_resolution_heading(self):
        fence = f"\n````markdown\n```\n## Resolution\n{HEADING}\n```\n````\n"
        before = item_text("001", "NOT_STARTED", "short") + fence
        self.assertIsNone(update_backlog._resolution_section_span(before))
        self.assertEqual(scoped_rules.loop_section_spans(before), [])

        resolved = self.tmp / "resolved.md"
        self.write_raw(resolved, before)
        self.assertEqual(update_backlog.append_resolution_section(resolved, RECORD).outcome, "appended")
        self.assertTrue(self.read_raw(resolved).startswith(before))

        looped = self.item_file("001")
        self.write_raw(looped, before)
        self.assertEqual(backlog_questions.append_question(looped, RUN_1, DECISION), "appended")
        after = self.read_raw(looped)
        self.assertTrue(after.startswith(before), "the fenced example changed")
        self.assertEqual(after.count(HEADING), 1)
        self.assertEqual(after.count("## Open Questions"), 1)

    def test_bom_resolution_file_leaves_no_bom_in_item(self):
        resolution = self.tmp / "bom-resolution.md"
        resolution.write_bytes(BOM + RECORD.replace("\n", "\r\n").encode("utf-8"))
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE",
            "--resolution-file", str(resolution),
        )
        self.assertEqual(code, 0, marked)
        looped = self.item_file("001").read_bytes()
        self.assertNotIn(BOM, looped)
        self.assertIn(b"\n## Resolution\n\nClosed 2026-10-21:", looped)

        _out, err, exit_code = self.update("--id", "007", "--status", "COMPLETE", "--resolution-file", str(resolution))
        self.assertIsNone(exit_code, err)
        updated = (self.archive_dir / item_filename("007")).read_bytes()
        self.assertNotIn(BOM, updated)
        self.assertIn(b"\n## Resolution\n\nClosed 2026-10-21:", updated)

    def test_needs_plan_clears_route_and_summary_shows_dash(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--route", "A")
        self.assertEqual(self.read_run(payload)["items"]["001"]["route"], "A")

        code, _text, _marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan",
        )

        self.assertEqual(code, 0)
        self.assertIsNone(self.read_run(payload)["items"]["001"]["route"])
        code, text, _payload = self.loop("--end", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertIn("| 001 | Short fix | - | SKIPPED | - |", text.splitlines())

    def test_decision_with_h2_line_is_refused(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        item_before = self.item_file("001").read_bytes()
        run_before = self.run_path(payload).read_bytes()
        decision = "Question: which route?\r\n## Options\r\n(A) patch (B) refactor"

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", decision,
        )

        self.assertEqual(code, 1)
        self.assertIn("may not start with `## `", error["error"])
        self.assertEqual(self.item_file("001").read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

    def test_init_excludes_needs_plan_item(self):
        marked = item_text("007", "NOT_STARTED", "short").replace("status: NOT_STARTED\n", "status: NOT_STARTED\nneeds_plan: true\n")
        self.write_raw(self.item_file("007"), marked)
        quoted = item_text("006", "NOT_STARTED", "short").replace("status: NOT_STARTED\n", 'status: NOT_STARTED\nneeds_plan: "TRUE"\n')
        self.write_raw(self.item_file("006"), quoted)

        payload = self.init("--mode", "all")

        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "002"])
        reasons = {e["id"]: e["reason"] for e in payload["excluded"]}
        self.assertEqual(reasons["007"], "marked for a planning session")
        self.assertEqual(reasons["006"], "marked for a planning session")
        code, text, specific = self.loop("--init", "--mode", "specific", "--items", "007,001")
        self.assertEqual(code, 0)
        self.assertEqual([q["id"] for q in specific["queue"]], ["001"])
        self.assertIn("warning: item 007 dropped: marked for a planning session", text)

    def test_needs_plan_yes_reads_as_marked(self):
        # The text a frontmatter read without PyYAML returns; the route's
        # shared reader takes the same YAML 1.1 spellings.
        for value in ("yes", "Y", "on", "True", '"TRUE"', True):
            with self.subTest(value=value):
                self.assertTrue(backlog_loop.marked_needs_plan({"needs_plan": value}))
        for value in ("no", "false", "", None, False):
            with self.subTest(value=value):
                self.assertFalse(backlog_loop.marked_needs_plan({"needs_plan": value}))

    def test_decision_append_refuses_or_closes_open_fence(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        path = self.item_file("001")
        # A person left a fence open inside the section, so its end marker
        # reads as fenced and the section as legacy.
        self.write_raw(path, self.read_raw(path) + old_section(RUN_1) + "```text\nhalf an example\n" + END + "\n")
        before_item = path.read_bytes()
        before_run = self.run_path(payload).read_bytes()

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION,
        )

        # Refused: exit 1, and neither the item file nor the run file changes.
        self.assertEqual(code, 1)
        self.assertIn("never closes", error["error"])
        self.assertEqual(path.read_bytes(), before_item)
        self.assertEqual(self.run_path(payload).read_bytes(), before_run)


if __name__ == "__main__":
    unittest.main()
