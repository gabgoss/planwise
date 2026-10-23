#!/usr/bin/env python3
"""Regression tests for the loop's item-file writers and its queue guards.

  * A `## Loop Decision Needed` line inside a fenced block is not a section,
    and a fenced `## ` line inside a real section does not end it.
  * `Earlier runs:` keeps every earlier run id, oldest first.
  * A section ends at its unfenced `<!-- loop-decision-end -->` line. A
    section a person edited anywhere from heading to end marker is kept,
    and the new section is written beside it; a later run replaces only the
    new one. Text after the end marker is not an edit.
  * A section with no end marker is never changed; the new section goes
    after the end of the file.
  * A retry in the same run writes nothing, wherever its tag sits.
  * One fence scanner: a fence closes only on the same character, at least
    as long, so every writer agrees on what is fenced.
  * `--decision` refuses a heading line of level 1 or 2, an unclosed fence
    and the end-marker string.
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
import scoped_rules
import update_backlog
from test_backlog_loop import item_filename, item_text
from test_backlog_loop_gates import (
    DECISION,
    HEADING,
    OLD_RUNS,
    RECORD,
    _GatesFixtureBase,
    old_section,
)

BOM = b"\xef\xbb\xbf"
RUN_1, RUN_2, RUN_3 = "20261001-090000", "20261002-090000", "20261003-090000"
END = "<!-- loop-decision-end -->"


def tag_of(run_id: str) -> str:
    return f"<!-- loop-decision run={run_id} -->"


class TestReviewRegressions(_GatesFixtureBase):
    def write_raw(self, path: Path, text: str) -> None:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def read_raw(self, path: Path) -> str:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def test_fenced_loop_heading_is_not_a_section(self):
        path = self.item_file("001")
        fenced = (
            "The loop writes this shape:\n\n"
            "```markdown\n"
            f"{HEADING}\n\n"
            "<!-- loop-decision run=YYYYMMDD-HHMMSS -->\n"
            "Question: {one question}\n"
            "```\n\n"
            "## Notes\n\n"
            "Keep this note.\n"
        )
        before = item_text("001", "NOT_STARTED", "short") + "\n" + fenced
        self.write_raw(path, before)

        backlog_loop.write_decision_section(path, RUN_3, DECISION)

        after = self.read_raw(path)
        self.assertTrue(after.startswith(before), "authored text before the new section changed")
        self.assertEqual(after.count(HEADING), 2)
        self.assertNotIn("Earlier runs:", after)
        self.assertEqual(after.count(f"<!-- loop-decision run={RUN_3} -->"), 1)

    def test_fenced_h2_inside_section_does_not_end_it(self):
        path = self.item_file("001")
        self.write_raw(path, item_text("001", "NOT_STARTED", "short"))
        old = "Question with an example:\n```text\n## not a heading\n```\nTail of the old section."
        backlog_loop.write_decision_section(path, RUN_1, old)
        self.assertIn("## not a heading", self.read_raw(path))

        backlog_loop.write_decision_section(path, RUN_2, DECISION)

        after = self.read_raw(path)
        self.assertNotIn("Tail of the old section.", after)
        self.assertNotIn("## not a heading", after)
        self.assertEqual(sum(1 for line in after.split("\n") if line.startswith("```")), 0)
        self.assertEqual(after.count(HEADING), 1)
        self.assertIn(f"> Earlier runs: {RUN_1}", after)

    def test_earlier_runs_accumulates_across_three_runs(self):
        # The CRLF case: three runs on a CRLF item file.
        path = self.item_file("001")
        self.write_raw(path, item_text("001", "NOT_STARTED", "short").replace("\n", "\r\n"))

        for run_id in (RUN_1, RUN_2, RUN_3):
            backlog_loop.write_decision_section(path, run_id, f"Question from run {run_id}?")

        raw = path.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF entered a CRLF file")
        self.assertEqual(raw.count(HEADING.encode()), 1)
        self.assertIn(f"> Earlier runs: {RUN_1}, {RUN_2}\r\n".encode(), raw)
        self.assertIn(f"Question from run {RUN_3}?".encode(), raw)
        self.assertNotIn(f"Question from run {RUN_2}?".encode(), raw)

    def test_edited_section_is_kept_and_new_question_appended(self):
        path = self.item_file("001")
        self.write_raw(path, item_text("001", "NOT_STARTED", "short").replace("\n", "\r\n"))
        backlog_loop.write_decision_section(path, RUN_1, "Question: keep or drop?")
        # The answer is typed inside the section, above its end marker.
        path.write_bytes(path.read_bytes().replace(END.encode(), b"My answer: keep it.\r\n" + END.encode()))
        edited = path.read_bytes()
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual((code, popped["next"]), (0, "001"))

        code, text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION,
        )

        self.assertEqual(code, 0)
        self.assertTrue(marked["decision_written"])
        self.assertIn(f"Loop Decision Needed section from run {RUN_1} was edited and kept", text)
        after = path.read_bytes()
        self.assertTrue(after.startswith(edited), "the edited section changed")
        self.assertEqual(after.count(HEADING.encode()), 2)
        self.assertIn(f"> Earlier runs: {RUN_1}\r\n".encode(), after)
        self.assertIn(b"Evidence: the probe found two callers.", after)
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"), "a bare LF entered a CRLF file")
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(record["outcome"], "SKIPPED")
        self.assertTrue(record["user_input_needed"])

        # A third run replaces only the new section; the edited one stays.
        outcome = backlog_loop.write_decision_section(path, RUN_3, "Question from run three?")
        third = path.read_bytes()
        self.assertEqual(outcome, (backlog_loop.DECISION_WRITTEN_BESIDE_EDITED, RUN_1))
        self.assertTrue(third.startswith(edited))
        self.assertEqual(third.count(HEADING.encode()), 2)
        self.assertNotIn(b"Evidence: the probe found two callers.", third)
        self.assertIn(b"Question from run three?", third)

    def test_unmarked_legacy_section_is_never_deleted(self):
        path = self.item_file("001")
        legacy = "".join(old_section(run) for run in OLD_RUNS) + "My answer typed into the old section.\n"
        before = item_text("001", "NOT_STARTED", "short") + legacy
        self.write_raw(path, before)

        outcome = backlog_loop.write_decision_section(path, RUN_3, DECISION)

        after = self.read_raw(path)
        self.assertEqual(outcome, (backlog_loop.DECISION_WRITTEN, None))
        self.assertTrue(after.startswith(before), "a section with no end marker changed")
        self.assertEqual(after.count(HEADING), 3)
        self.assertIn(f"> Earlier runs: {OLD_RUNS[0]}, {OLD_RUNS[1]}", after)
        lines = after.split("\n")
        tag_at = lines.index(tag_of(RUN_3))
        self.assertRegex(lines[tag_at + 1], r"^<!-- loop-decision-hash=[0-9a-f]{16} -->$")
        self.assertEqual(after.rstrip("\n").split("\n")[-1], END)
        self.assertIn("Answer under ## Notes, outside this section, then triage it again.", after)
        self.assertIn("A later run replaces this section.", after)

    def test_legacy_section_with_answer_is_kept_and_new_section_appended(self):
        path = self.item_file("001")
        legacy = old_section(OLD_RUNS[0]) + "My answer: option A.\n\n## Notes\n\nA note.\n"
        before = item_text("001", "NOT_STARTED", "short") + legacy
        self.write_raw(path, before)

        backlog_loop.write_decision_section(path, RUN_2, "Question from run two?")
        backlog_loop.write_decision_section(path, RUN_3, DECISION)

        after = self.read_raw(path)
        self.assertTrue(after.startswith(before), "the legacy section or the answer in it changed")
        self.assertEqual(after.count(HEADING), 2)
        self.assertNotIn("Question from run two?", after)
        self.assertEqual(after.count(END), 1)
        self.assertIn(f"> Earlier runs: {OLD_RUNS[0]}, {RUN_2}", after)
        self.assertEqual(after.rstrip("\n").split("\n")[-1], END)

    def test_same_run_retry_behind_unbalanced_fence_writes_once(self):
        path = self.item_file("001")
        unbalanced = "## Notes\n\n```text\nA fence nobody closed.\n"
        self.write_raw(path, item_text("001", "NOT_STARTED", "short") + unbalanced)
        backlog_loop.write_decision_section(path, RUN_1, DECISION)
        first = self.read_raw(path)

        outcome = backlog_loop.write_decision_section(path, RUN_1, DECISION)

        self.assertEqual(outcome, (backlog_loop.DECISION_SAME_RUN, None))
        self.assertEqual(self.read_raw(path), first)
        self.assertEqual(first.count(tag_of(RUN_1)), 1)

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

    def test_edit_above_tag_or_deleted_hash_keeps_section(self):
        path = self.item_file("001")
        base = item_text("001", "NOT_STARTED", "short")
        heading_line = f"{HEADING}\n"
        for edit in ("above the tag", "deleted hash line"):
            self.write_raw(path, base)
            backlog_loop.write_decision_section(path, RUN_1, DECISION)
            written = self.read_raw(path)
            if edit == "above the tag":
                edited = written.replace(heading_line, heading_line + "My answer: option A.\n", 1)
            else:
                lines = written.split("\n")
                edited = "\n".join(line for line in lines if "loop-decision-hash=" not in line)
            self.assertNotEqual(edited, written)
            self.write_raw(path, edited)

            outcome = backlog_loop.write_decision_section(path, RUN_2, "A second question?")

            after = self.read_raw(path)
            self.assertEqual(outcome, (backlog_loop.DECISION_WRITTEN_BESIDE_EDITED, RUN_1), edit)
            self.assertTrue(after.startswith(edited), edit)
            self.assertEqual(after.count(HEADING), 2, edit)
            self.assertIn("A second question?", after, edit)

            # A third run replaces only the new section.
            backlog_loop.write_decision_section(path, RUN_3, "A third question?")
            third = self.read_raw(path)
            self.assertTrue(third.startswith(edited), edit)
            self.assertEqual(third.count(HEADING), 2, edit)
            self.assertNotIn("A second question?", third, edit)
            self.assertIn(f"> Earlier runs: {RUN_1}, {RUN_2}", third, edit)

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

        path = self.item_file("001")
        self.write_raw(path, text)
        outcome = backlog_loop.write_decision_section(path, RUN_1, DECISION)
        after = self.read_raw(path)
        self.assertEqual(outcome, (backlog_loop.DECISION_WRITTEN, None))
        self.assertTrue(after.startswith(text), "the legacy section changed")
        self.assertEqual(after.count(HEADING), 2)
        self.assertIn("> Earlier runs: old", after)

    def test_edited_section_third_run_replaces_only_new_section(self):
        path = self.item_file("001")
        self.write_raw(path, item_text("001", "NOT_STARTED", "short"))
        backlog_loop.write_decision_section(path, RUN_1, "Question from run one?")
        edited = self.read_raw(path).replace(END, "My answer: option B.\n" + END)
        self.write_raw(path, edited)

        second = backlog_loop.write_decision_section(path, RUN_2, "Question from run two?")
        third = backlog_loop.write_decision_section(path, RUN_3, "Question from run three?")

        after = self.read_raw(path)
        self.assertEqual(second, (backlog_loop.DECISION_WRITTEN_BESIDE_EDITED, RUN_1))
        self.assertEqual(third, (backlog_loop.DECISION_WRITTEN_BESIDE_EDITED, RUN_1))
        self.assertTrue(after.startswith(edited), "the edited section changed")
        self.assertEqual(after.count(HEADING), 2)
        self.assertEqual(after.count(END), 2)
        self.assertNotIn("Question from run two?", after)
        self.assertNotIn(tag_of(RUN_2), after)
        self.assertIn("Question from run three?", after)
        self.assertIn(f"> Earlier runs: {RUN_1}, {RUN_2}", after)

    def test_text_after_end_marker_is_not_an_edit(self):
        path = self.item_file("001")
        self.write_raw(path, item_text("001", "NOT_STARTED", "short"))
        backlog_loop.write_decision_section(path, RUN_1, "Question from run one?")
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("\n---\n\nTrailer after the section.\n")

        outcome = backlog_loop.write_decision_section(path, RUN_2, DECISION)

        after = self.read_raw(path)
        self.assertEqual(outcome, (backlog_loop.DECISION_WRITTEN, None))
        self.assertEqual(after.count(HEADING), 1)
        self.assertNotIn("Question from run one?", after)
        self.assertIn(f"> Earlier runs: {RUN_1}", after)
        self.assertTrue(after.endswith(f"{END}\n\n---\n\nTrailer after the section.\n"))

    def test_update_backlog_and_loop_agree_on_fenced_resolution_heading(self):
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
        self.assertEqual(backlog_loop.write_decision_section(looped, RUN_1, DECISION)[0], "written")
        after = self.read_raw(looped)
        self.assertTrue(after.startswith(before), "the fenced example changed")
        self.assertEqual(after.count(HEADING), 2)

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
