#!/usr/bin/env python3
"""Tests for backlog_questions.py, the open-question block writer.

  * append_question inserts `## Open Questions` at the template position,
    numbers blocks, is a no-op on a same-run retry, and replaces `None.`.
  * --fold moves both legacy `## Loop Decision Needed` shapes into blocks,
    is idempotent, and writes nothing under --dry-run.
  * --answer fills the empty `Answer:` line; every refusal leaves the bytes.
  * --list prints exactly the unanswered blocks and the legacy count.
  * The fold is route-neutral: only the open-questions state moves.

The two legacy shapes are copied from real item files: the dated callout
shape an early loop run wrote, and the marker-bounded shape of the retired
writer (hash line and end marker).

Run with:  python -m pytest tests/test_backlog_questions.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_questions
import score_backlog
from test_backlog_loop import CONFIG_YAML_FIXTURE, HUB_HEADER

LEGACY = "## Loop Decision Needed"
RUN_1, RUN_2 = "20261020-101500", "20261021-101500"

# The dated shape, copied from a real item (run 20261012-222015).
DATED_SECTION = (
    "## Loop Decision Needed\n"
    "\n"
    "<!-- loop-decision run=20261012-222015 -->\n"
    "> [!gate] User input needed\n"
    "> Loop run 20261012-222015, 2026-10-12. The loop skipped this item without working it. "
    "Answer the question below, then triage it again.\n"
    "\n"
    "Item 555 asks for three things from a feedback issue. The filing note says the repository "
    "claims were not re-verified, and the loop's premise probe found two of them do not hold as "
    "written. Route is B, score 25, matching route_at_init, with no route_hint. Choose: (A) confirm "
    "the item as written; (B) split it so the reference passage lands first; or (C) name a "
    "different approach.\n"
)
# The marker-bounded shape the retired writer emitted.
MARKED_SECTION = (
    "## Loop Decision Needed\n"
    "\n"
    "<!-- loop-decision run=20261018-090000 -->\n"
    "<!-- loop-decision-hash=0123456789abcdef -->\n"
    "> [!gate] User input needed\n"
    "> Loop run 20261018-090000, 2026-10-18. The loop skipped this item without working it. "
    "Answer under ## Notes, outside this section, then triage it again. A later run replaces this section.\n"
    "> Earlier runs: 20261017-090000\n"
    "\n"
    "Question: keep the helper or drop it?\n"
    "Options: (A) keep (B) drop\n"
    "Evidence: the probe found two callers.\n"
    "\n"
    "<!-- loop-decision-end -->\n"
)


def item_body(item_id: str, tail: str = "", questions: str = "") -> str:
    """An item in the template's section order; `tail` follows the footer."""
    lines = [
        "---", f"id: {item_id}", "title: \"Fixture item\"", "priority: Medium", "status: NOT_STARTED",
        "abbrev: DOC", "created: 2026-10-11", "blocks: []", "---", "",
        f"# BB-{item_id}-DOC: Fixture item", "", "## Summary", "",
    ]
    lines.extend(f"Summary line {n} about the helper." for n in range(1, 41))
    lines.extend(["", "## Proposed Solution", "", "1. Read the helper.", "2. Adjust the helper.", ""])
    lines.extend(["## Acceptance Criteria", "", "- [ ] The helper is adjusted.", ""])
    if questions:
        lines.extend(["## Open Questions", "", questions, ""])
    lines.extend(["## Related", "", "- Nothing related.", "", "---", "", "*Created: 2026-10-11*", ""])
    text = "\n".join(lines)
    return text + ("\n" + tail if tail else "")


class _QuestionsFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backlog_questions_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backlog_dir = self.tmp / "planwise" / "Backlog"
        self.backlog_dir.mkdir(parents=True)
        self.config_path = self.tmp / "planwise" / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        self.rows: list[str] = []

    def add_item(self, item_id: str, text: str) -> Path:
        path = self.backlog_dir / f"{item_id}-DOC-fixture.md"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.rows.append(
            f"| {item_id} | Fixture | Medium | NOT_STARTED | DOC | 2026-10-11 |  | 0 | [01]({path.name}) |\n"
        )
        (self.backlog_dir / "00-Index-Backlog.md").write_text(HUB_HEADER + "".join(self.rows), encoding="utf-8")
        return path

    def run_cli(self, *argv: str) -> tuple[int, str, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = backlog_questions.main(["--config", str(self.config_path), *argv])
        text = out.getvalue()
        return code, text, json.loads(text.splitlines()[-1])

    def raw(self, path: Path) -> str:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()


class TestAppendQuestion(_QuestionsFixture):
    def test_inserts_section_before_related_then_numbers_and_dedupes(self):
        path = self.add_item("100", item_body("100"))

        self.assertEqual(backlog_questions.append_question(path, RUN_1, "Question: A or B?"), "appended")
        after = self.raw(path)
        self.assertIn(
            "## Open Questions\n\n"
            f"### Q1. Loop decision (run {RUN_1})\n"
            f"<!-- loop-decision run={RUN_1} -->\n"
            "Question: A or B?\n\nAnswer:\n\n## Related\n",
            after,
        )
        self.assertIn("- [ ] The helper is adjusted.\n\n## Open Questions\n", after)

        self.assertEqual(backlog_questions.append_question(path, RUN_1, "Question: A or B?"), "same_run")
        self.assertEqual(self.raw(path), after)

        self.assertEqual(backlog_questions.append_question(path, RUN_2, "Question: C or D?"), "appended")
        second = self.raw(path)
        self.assertIn(f"Answer:\n\n### Q2. Loop decision (run {RUN_2})\n", second)
        self.assertEqual(second.count("## Open Questions"), 1)
        self.assertLess(second.index("### Q1."), second.index("### Q2."), "blocks out of order")

    def test_none_section_is_replaced(self):
        path = self.add_item("100", item_body("100", questions="None."))

        backlog_questions.append_question(path, RUN_1, "Question: A or B?")

        after = self.raw(path)
        self.assertNotIn("None.", after)
        self.assertIn(f"## Open Questions\n\n### Q1. Loop decision (run {RUN_1})\n", after)

    def test_footer_break_is_the_fallback_position_and_crlf_is_kept(self):
        text = item_body("100").replace("## Related\n\n- Nothing related.\n\n", "").replace("\n", "\r\n")
        path = self.add_item("100", text)

        backlog_questions.append_question(path, RUN_1, "Question: A or B?")

        raw = path.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF entered a CRLF file")
        self.assertIn(b"Answer:\r\n\r\n---\r\n\r\n*Created: 2026-10-11*", raw)

    def test_legacy_section_is_left_unchanged(self):
        path = self.add_item("100", item_body("100", tail=MARKED_SECTION))

        backlog_questions.append_question(path, RUN_1, "Question: A or B?")

        after = self.raw(path)
        self.assertTrue(after.endswith(MARKED_SECTION), "the legacy section changed")
        self.assertEqual(after.count(LEGACY), 1)

    def test_refusals_write_nothing(self):
        path = self.add_item("100", item_body("100"))
        before = path.read_bytes()
        for text in ("Q\n### Sub heading", "Q\n## Heading", "Q\n```text\nopen", "", "e" * 1201):
            with self.subTest(text=text[:20]), self.assertRaises(backlog_questions.QuestionError):
                backlog_questions.append_question(path, RUN_1, text)
        open_fence = self.add_item("101", item_body("101") + "```text\nnever closed\n")
        fenced_before = open_fence.read_bytes()
        with self.assertRaises(backlog_questions.QuestionError):
            backlog_questions.append_question(open_fence, RUN_1, "Question: A or B?")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(open_fence.read_bytes(), fenced_before)


class TestFold(_QuestionsFixture):
    def test_fold_both_shapes_is_idempotent(self):
        dated = self.add_item("100", item_body("100", tail=DATED_SECTION))
        marked = self.add_item("101", item_body("101", tail=MARKED_SECTION + "\nText after the marker.\n"))

        code, text, payload = self.run_cli("--fold", "--all")

        self.assertEqual(code, 0, payload)
        self.assertEqual((payload["folded"], payload["refused"]), (2, []))
        self.assertIn("Folded 100: 1 section(s), runs 20261012-222015", text)
        first = self.raw(dated)
        self.assertNotIn(LEGACY, first)
        self.assertIn("### Q1. Loop decision (run 20261012-222015)\n<!-- loop-decision run=20261012-222015 -->\n", first)
        self.assertIn("Choose: (A) confirm the item as written;", first)
        self.assertNotIn("> [!gate]", first)
        self.assertTrue(first.endswith("*Created: 2026-10-11*\n"))
        second = self.raw(marked)
        self.assertNotIn(LEGACY, second)
        self.assertIn(
            "<!-- loop-decision run=20261018-090000 -->\nQuestion: keep the helper or drop it?\n"
            "Options: (A) keep (B) drop\nEvidence: the probe found two callers.\n\nAnswer:\n",
            second,
        )
        for gone in ("loop-decision-hash", "loop-decision-end", "Earlier runs"):
            self.assertNotIn(gone, second)
        self.assertTrue(second.endswith("*Created: 2026-10-11*\n\nText after the marker.\n"))

        code, _text, again = self.run_cli("--fold", "--all")
        self.assertEqual((code, again["folded"]), (0, 0))
        self.assertEqual((self.raw(dated), self.raw(marked)), (first, second))

    def test_dry_run_writes_nothing(self):
        path = self.add_item("100", item_body("100", tail=DATED_SECTION).replace("\n", "\r\n"))
        before = path.read_bytes()

        code, text, payload = self.run_cli("--fold", "--id", "100", "--dry-run")

        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["items"][0]["status"], "planned")
        self.assertIn("Would fold 100: 1 section(s)", text)
        self.assertEqual(path.read_bytes(), before)

    def test_two_sections_become_two_blocks_and_crlf_is_kept(self):
        untagged = DATED_SECTION.replace("<!-- loop-decision run=20261012-222015 -->\n", "")
        path = self.add_item("100", item_body("100", tail=untagged + "\n" + MARKED_SECTION).replace("\n", "\r\n"))

        code, _text, payload = self.run_cli("--fold", "--id", "100")

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["items"][0]["runs"], ["unknown", "20261018-090000"])
        raw = path.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF entered a CRLF file")
        self.assertIn(b"### Q1. Loop decision (run unknown)\r\n", raw)
        self.assertIn(b"### Q2. Loop decision (run 20261018-090000)\r\n", raw)
        self.assertNotIn(LEGACY.encode(), raw)

    def test_open_fence_item_is_refused_and_the_fold_continues(self):
        bad = self.add_item("100", item_body("100", tail=DATED_SECTION + "\n```text\nnever closed\n"))
        good = self.add_item("101", item_body("101", tail=MARKED_SECTION))
        before = bad.read_bytes()

        code, text, payload = self.run_cli("--fold", "--all")

        self.assertEqual(code, 1)
        self.assertEqual((payload["refused"], payload["folded"]), (["100"], 1))
        self.assertIn("Refused 100:", text)
        self.assertEqual(bad.read_bytes(), before)
        self.assertNotIn(LEGACY, self.raw(good))

    def test_fold_needs_one_target(self):
        self.add_item("100", item_body("100", tail=DATED_SECTION))
        for argv in (("--fold",), ("--fold", "--all", "--id", "100"), ("--fold", "--id", "999")):
            with self.subTest(argv=argv):
                code, _text, payload = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("error", payload)


class TestAnswer(_QuestionsFixture):
    def answer_file(self, text: str) -> Path:
        path = self.tmp / "answer.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_answer_fills_the_line_and_the_shape_reads_answered(self):
        path = self.add_item("100", item_body("100"))
        backlog_questions.append_question(path, RUN_1, "Question: A or B?")
        before = score_backlog.compute_item_shape(score_backlog.read_item_frontmatter(path))
        self.assertEqual(before["open_questions"], "unanswered")

        code, _text, payload = self.run_cli(
            "--answer", "--id", "100", "--q", "1", "--text-file", str(self.answer_file("Option A.\nSecond line.")),
        )

        self.assertEqual(code, 0, payload)
        today = datetime.now().astimezone().date().isoformat()
        self.assertIn(f"Answer: {today}: Option A.\n  Second line.\n", self.raw(path))
        after = score_backlog.compute_item_shape(score_backlog.read_item_frontmatter(path))
        self.assertEqual(after["open_questions"], "answered")

    def test_each_refusal_exits_1_and_leaves_the_bytes(self):
        path = self.add_item("100", item_body("100"))
        backlog_questions.append_question(path, RUN_1, "Question: A or B?")
        self.run_cli("--answer", "--id", "100", "--q", "1", "--text-file", str(self.answer_file("Done.")))
        backlog_questions.append_question(path, RUN_2, "Question: C or D?")
        before = path.read_bytes()
        cases = {
            "already answered": ("1", "Again."),
            "absent block": ("9", "Text."),
            "heading line": ("2", "Text.\n## Heading"),
            "unclosed fence": ("2", "Text.\n```text\nopen"),
            "empty file": ("2", "  \n"),
        }
        for name, (number, text) in cases.items():
            with self.subTest(case=name):
                code, _text, payload = self.run_cli(
                    "--answer", "--id", "100", "--q", number, "--text-file", str(self.answer_file(text)),
                )
                self.assertEqual(code, 1, payload)
                self.assertIn("error", payload)
                self.assertEqual(path.read_bytes(), before)


class TestBlockIntegrity(_QuestionsFixture):
    """Every write keeps the item readable: no stray fence, no section cut short."""

    def answer_file(self, text: str) -> Path:
        path = self.tmp / "answer.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_an_answer_that_would_leave_a_fence_open_is_refused(self):
        path = self.add_item("100", item_body("100"))
        backlog_questions.append_question(path, RUN_1, "Question: A or B?")
        before = path.read_bytes()

        code, _text, payload = self.run_cli(
            "--answer", "--id", "100", "--q", "1", "--text-file", str(self.answer_file("```text\ncode\n```")),
        )

        self.assertEqual(code, 1, payload)
        self.assertIn("error", payload)
        self.assertEqual(path.read_bytes(), before)

    def test_an_answer_with_a_thematic_break_is_refused(self):
        path = self.add_item("100", item_body("100"))
        backlog_questions.append_question(path, RUN_1, "Question: A or B?")
        before = path.read_bytes()

        code, _text, payload = self.run_cli(
            "--answer", "--id", "100", "--q", "1", "--text-file", str(self.answer_file("Option A.\n---\nMore.")),
        )

        self.assertEqual(code, 1, payload)
        self.assertIn("error", payload)
        self.assertEqual(path.read_bytes(), before)

    def test_a_question_with_a_thematic_break_or_an_answer_line_is_refused(self):
        path = self.add_item("100", item_body("100"))
        before = path.read_bytes()
        refused = (
            "Q?\n---\nmore", "Q?\n***", "Q?\n_ _ _",
            "Q?\nAnswer: yes", "Q?\n- **Answer**: B", "Q?\nAnswer:",
        )
        for text in refused:
            with self.subTest(text=text), self.assertRaises(backlog_questions.QuestionError):
                backlog_questions.append_question(path, RUN_1, text)
        self.assertEqual(path.read_bytes(), before)
        # Inside a fence the same lines are content, not structure.
        fenced = "Question: which?\n```text\n---\nAnswer: x\n```"
        self.assertEqual(backlog_questions.append_question(path, RUN_1, fenced), "appended")

    def test_fold_refuses_a_legacy_question_that_would_end_the_block_and_continues(self):
        for line in ("---", "Answer: keep it."):
            with self.subTest(line=line):
                self.rows.clear()
                bad_section = MARKED_SECTION.replace("\n<!-- loop-decision-end -->", f"{line}\n\n<!-- loop-decision-end -->")
                bad = self.add_item("100", item_body("100", tail=bad_section))
                good = self.add_item("101", item_body("101", tail=MARKED_SECTION))
                before = bad.read_bytes()

                code, text, payload = self.run_cli("--fold", "--all")

                self.assertEqual(code, 1, payload)
                self.assertEqual((payload["refused"], payload["folded"]), (["100"], 1))
                self.assertIn("Refused 100:", text)
                self.assertEqual(bad.read_bytes(), before)
                self.assertNotIn(LEGACY, self.raw(good))

    def test_fold_keeps_a_user_blockquote_after_the_loop_callout(self):
        quote = "> A quoted line the user wrote."
        shapes = (
            ("dated", DATED_SECTION + "\n" + quote + "\n"),
            ("marked", MARKED_SECTION.replace("\n<!-- loop-decision-end -->", f"{quote}\n\n<!-- loop-decision-end -->")),
        )
        for name, section in shapes:
            with self.subTest(shape=name):
                self.rows.clear()
                path = self.add_item("100", item_body("100", tail=section))

                code, _text, payload = self.run_cli("--fold", "--id", "100")

                self.assertEqual(code, 0, payload)
                after = self.raw(path)
                self.assertNotIn(LEGACY, after)
                self.assertIn(quote, after)
                self.assertNotIn("> [!gate]", after)
                self.assertNotIn("> Loop run", after)

    def test_an_unclosed_frontmatter_is_never_written_above(self):
        text = "---\nid: 100\nstatus: NOT_STARTED\n\nBody line.\n"
        path = self.add_item("100", text)
        before = path.read_bytes()

        with self.assertRaises(backlog_questions.QuestionError):
            backlog_questions.append_question(path, RUN_1, "Question: A or B?")

        self.assertEqual(path.read_bytes(), before)


class TestList(_QuestionsFixture):
    QUESTIONS = (
        "### Q1. Which reader?\n\nOptions: (A) one (B) two\nAnswer: 2026-10-20: one.\n\n"
        "### Q2. Which writer?\n\nOptions: (A) left (B) right\nRecommendation: A. It is simpler.\nAnswer:\n\n"
        "### Q3. Which test?\n\nAnswer:"
    )

    def test_list_prints_exactly_the_unanswered_blocks_and_the_legacy_count(self):
        self.add_item("100", item_body("100", questions=self.QUESTIONS))
        self.add_item("101", item_body("101", tail=DATED_SECTION))

        code, text, payload = self.run_cli("--list")

        self.assertEqual(code, 0)
        self.assertEqual(
            [(q["id"], q["q"], q["question"], q["options"]) for q in payload["questions"]],
            [("100", 2, "Which writer?", "Options: (A) left (B) right"), ("100", 3, "Which test?", None)],
        )
        self.assertIn("100 Q2: Which writer?\n  Options: (A) left (B) right\n100 Q3: Which test?\n", text)
        self.assertNotIn("Which reader?", text)
        self.assertEqual((payload["legacy_sections"], payload["legacy_items"]), (1, ["101"]))
        self.assertIn("run --fold --all first", text)

    def test_list_names_the_loop_question_and_json_prints_one_line(self):
        path = self.add_item("100", item_body("100"))
        backlog_questions.append_question(path, RUN_1, "Question: A or B?\nOptions: (A) a (B) b")
        before = path.read_bytes()

        code, text, payload = self.run_cli("--list", "--id", "100", "--json")

        self.assertEqual(code, 0)
        self.assertEqual(len(text.splitlines()), 1)
        self.assertEqual(payload["questions"][0]["question"], "Question: A or B?")
        self.assertEqual(payload["questions"][0]["options"], "Options: (A) a (B) b")
        self.assertEqual(payload["legacy_sections"], 0)
        self.assertEqual(path.read_bytes(), before)


class TestRouteNeutrality(_QuestionsFixture):
    FIELDS = ("route", "step_count", "sub_items", "h2_count", "is_short")

    def signals(self, path: Path) -> tuple[dict, str]:
        frontmatter = score_backlog.read_item_frontmatter(path)
        signals = score_backlog.compute_route_signals({"id": "100", "abbrev": "DOC"}, frontmatter)
        return {field: signals[field] for field in self.FIELDS}, signals["shape"]["open_questions"]

    def test_fold_moves_only_the_open_questions_state(self):
        for name, section in (("dated", DATED_SECTION), ("marked", MARKED_SECTION)):
            with self.subTest(shape=name):
                path = self.add_item("100", item_body("100", tail=section))
                before, state_before = self.signals(path)

                code, _text, payload = self.run_cli("--fold", "--id", "100")

                self.assertEqual(code, 0, payload)
                after, state_after = self.signals(path)
                self.assertEqual(after, before)
                self.assertIn(state_before, ("absent", "empty"))
                self.assertEqual(state_after, "unanswered")
                self.rows.clear()


if __name__ == "__main__":
    unittest.main()
