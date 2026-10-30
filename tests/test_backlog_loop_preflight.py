#!/usr/bin/env python3
"""Tests for the `backlog_loop.py --init` pre-flight, `--dry-run`, `--mark --check`
and the two end-summary blocks (`Skipped (by reason):`, `Checks:`).

Each test builds on the `_LoopFixtureBase` temp tree of `test_backlog_loop.py`
and adds the items it needs inside that tree:

  010  Low  a legacy `## Loop Decision Needed` section  -> `decision pending`
  011  Low  its body creates a file under `.claude/rules/` -> `placement`

The end-to-end tests drive the CLI steps in the order the loop orchestrator
runs them: `--init`, `--next`, the three `--mark --phase` calls, the
`--mark --check` calls, the closing `--mark --outcome`, then `--boundary`.
No fix-agent runs; the CLI calls stand in for it.

Run with:  python -m pytest tests/test_backlog_loop_preflight.py -q
"""

import contextlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_loop
import scoped_rules
from backlog_loop import (
    DECISION_PENDING_REASON,
    MARKER_FORMAT,
    NEEDS_PLAN_REASON,
    PLACEMENT_REASON,
)
from test_backlog_loop import _LoopFixtureBase, item_filename

LEGACY_SECTION = [
    "## Loop Decision Needed",
    "",
    "> [!question] Loop decision (run 20261001-090000)",
    "Which helper owns the change?",
    "<!-- loop-decision-end -->",
]
PLACEMENT_LINE = "Add `.claude/rules/fixture-new-rule.md` to hold the new convention."
UNANSWERED = ["## Open Questions", "", "### Q1. Which helper owns the change?", "", "Answer:"]


class _PreflightBase(_LoopFixtureBase):
    def add_item(self, item_id: str, body: list[str], needs_plan: bool = False) -> Path:
        """Write one short item file and append its hub row (Low, open)."""
        head = ["---", f"id: {item_id}", "status: NOT_STARTED"]
        if needs_plan:
            head.append("needs_plan: true")
        lines = head + ["---", "", f"# Item {item_id}", "", "A small, well-bounded change to one helper.", ""]
        path = self.backlog_dir / item_filename(item_id)
        path.write_text("\n".join(lines + body) + "\n", encoding="utf-8", newline="\n")
        index = self.backlog_dir / "00-Index-Backlog.md"
        row = (
            f"| {item_id} | Fixture {item_id} | Low | NOT_STARTED | INFRA | 2026-10-01 | "
            f" | 0 | [01]({item_filename(item_id)}) |\n"
        )
        index.write_text(index.read_text(encoding="utf-8") + row, encoding="utf-8")
        return path

    def add_both(self) -> None:
        self.add_item("010", LEGACY_SECTION)
        self.add_item("011", [PLACEMENT_LINE])

    def reasons(self, payload: dict) -> dict:
        return {entry["id"]: entry["reason"] for entry in payload["excluded"]}


class TestInitPreflight(_PreflightBase):
    def test_init_excludes_decision_pending_and_placement(self):
        self.add_both()
        payload = self.init("--mode", "all")

        reasons = self.reasons(payload)
        self.assertEqual(reasons["010"], DECISION_PENDING_REASON)
        self.assertEqual(reasons["011"], PLACEMENT_REASON)
        queued = {q["id"] for q in payload["queue"]}
        self.assertTrue({"010", "011"}.isdisjoint(queued))
        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "002", "006", "007"])
        # A decision-pending item is excluded before its route is computed.
        by_id = {entry["id"]: entry for entry in payload["excluded"]}
        self.assertIsNone(by_id["010"]["route"])
        self.assertEqual(by_id["011"]["route"], "A")

    def test_a_doubly_excluded_item_shows_the_first_reason(self):
        cases = [
            ("012", LEGACY_SECTION, True, NEEDS_PLAN_REASON),
            ("013", LEGACY_SECTION + ["", PLACEMENT_LINE], False, DECISION_PENDING_REASON),
            ("014", [PLACEMENT_LINE, ""] + UNANSWERED, False, PLACEMENT_REASON),
        ]
        for item_id, body, needs_plan, _reason in cases:
            self.add_item(item_id, body, needs_plan=needs_plan)
        reasons = self.reasons(self.init("--mode", "all"))
        for item_id, _body, _needs_plan, reason in cases:
            with self.subTest(item=item_id):
                self.assertEqual(reasons[item_id], reason)

    def test_specific_mode_drops_each_with_a_warning_naming_the_reason(self):
        self.add_both()
        code, text, payload = self.loop("--init", "--mode", "specific", "--items", "001,010,011")

        self.assertEqual(code, 0, payload)
        self.assertEqual([q["id"] for q in payload["queue"]], ["001"])
        self.assertIn(f"warning: item 010 dropped: {DECISION_PENDING_REASON}", payload["warnings"])
        self.assertIn(f"warning: item 011 dropped: {PLACEMENT_REASON}", payload["warnings"])
        self.assertIn(f"warning: item 011 dropped: {PLACEMENT_REASON}", text)


class TestDryRun(_PreflightBase):
    def test_dry_run_writes_nothing_and_prints_the_same_queue(self):
        self.add_both()
        code, text, dry = self.loop("--init", "--mode", "all", "--dry-run")

        self.assertEqual(code, 0, dry)
        self.assertFalse(self.runs_dir.exists())
        self.assertTrue(dry["dry_run"])
        self.assertNotIn("run", dry)
        self.assertNotIn("state", dry)
        lines = text.splitlines()
        self.assertEqual(lines[0], "Loop dry run: mode=all queue=4 excluded=5 (no run file written)")
        self.assertIn(f"  010  route -  {DECISION_PENDING_REASON}", lines)
        self.assertIn(f"  011  route A  {PLACEMENT_REASON}", lines)

        real = self.init("--mode", "all")
        self.assertEqual(real["queue"], dry["queue"])
        self.assertEqual(real["excluded"], dry["excluded"])
        self.assertEqual(len(list(self.runs_dir.glob("*.json"))), 1)

    def test_dry_run_with_an_empty_queue_still_exits_1(self):
        code, _text, payload = self.loop("--init", "--mode", "specific", "--items", "009", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("error", payload)
        self.assertFalse(self.runs_dir.exists())

    def test_dry_run_with_an_empty_queue_prints_the_excluded_report(self):
        self.add_both()
        code, text, payload = self.loop("--init", "--mode", "specific", "--items", "010", "--dry-run")

        self.assertEqual(code, 1, payload)
        self.assertIn("error", payload)
        self.assertTrue(payload["dry_run"])
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("Loop dry run: mode=specific queue=0"), lines[0])
        self.assertIn("Excluded:", lines)
        self.assertIn(f"  010  route -  {DECISION_PENDING_REASON}", lines)
        self.assertFalse(self.runs_dir.exists())

    def test_decision_pending_names_the_way_out_once(self):
        hint = "decision pending: run scripts/backlog_questions.py --fold, then --answer each question"
        self.add_both()
        _code, text, _payload = self.loop("--init", "--mode", "all", "--dry-run")
        self.assertEqual(text.splitlines().count(hint), 1)
        _code, text, payload = self.loop("--init", "--mode", "specific", "--items", "001,010", "--dry-run")
        self.assertEqual(text.splitlines().count(hint), 1)
        self.assertIn(hint, payload["warnings"])

    def test_init_without_decision_pending_prints_no_hint(self):
        self.add_item("011", [PLACEMENT_LINE])
        _code, text, _payload = self.loop("--init", "--mode", "all", "--dry-run")
        self.assertNotIn("backlog_questions.py --fold", text)

    def test_rule_scopes_load_once_per_init(self):
        calls: list = []
        real = scoped_rules.load_rule_scopes

        def counting(root):
            calls.append(root)
            return real(root)

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(scoped_rules, "load_rule_scopes", counting))
            if hasattr(backlog_loop, "load_rule_scopes"):
                stack.enter_context(mock.patch.object(backlog_loop, "load_rule_scopes", counting))
            code, _text, payload = self.loop("--init", "--mode", "all", "--dry-run")

        self.assertEqual(code, 0, payload)
        self.assertGreaterEqual(len(payload["queue"]), 2)
        self.assertEqual(len(calls), 1)

    def test_dry_run_without_init_is_a_usage_error(self):
        for argv in (["--next", "--run", "x"], ["--end", "--run", "x"], ["--status"]):
            with self.subTest(argv=argv):
                code, _text, payload = self.loop(*argv, "--dry-run")
                self.assertEqual(code, 1)
                self.assertIn("--dry-run", payload["error"])
        self.assertFalse(self.runs_dir.exists())


class TestMarkCheck(_PreflightBase):
    def popped_run(self) -> tuple[dict, str]:
        payload = self.init("--mode", "all")
        self.loop("--next", "--run", payload["run"])
        return payload, payload["run"]

    def test_check_records_into_checks_under_a_check_event(self):
        payload, run_id = self.popped_run()
        code, text, out = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--check", "python -m ruff check .", "--exit", "0"
        )

        self.assertEqual(code, 0, out)
        self.assertIn("Recorded check for 001: exit 0", text)
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(len(record["checks"]), 1)
        check = record["checks"][0]
        self.assertEqual((check["command"], check["exit"]), ("python -m ruff check .", 0))
        self.assertTrue(check["at"])
        last = self.read_run(payload)["history"][-1]
        self.assertEqual((last["event"], last["id"], last["detail"]), ("check", "001", "exit=0"))

    def test_each_check_refusal_exits_1_and_leaves_the_bytes_equal(self):
        payload, run_id = self.popped_run()
        base = ["--mark", "--run", run_id, "--id", "001", "--check", "python -m ruff check ."]
        cases = [
            ("missing --exit", []),
            ("--phase", ["--exit", "0", "--phase", "acting"]),
            ("--outcome", ["--exit", "0", "--outcome", "COMPLETE"]),
            ("--lessons", ["--exit", "0", "--lessons", "lesson-1"]),
            ("--refined", ["--exit", "0", "--refined", "REFINED"]),
            ("--decision", ["--exit", "0", "--decision", "Which helper owns the change?"]),
            ("--note", ["--exit", "0", "--note", "ran"]),
            ("--route", ["--exit", "0", "--route", "A"]),
        ]
        before = self.run_path(payload).read_bytes()
        for label, extra in cases:
            with self.subTest(case=label):
                code, _text, out = self.loop(*base, *extra)
                self.assertEqual(code, 1, out)
                self.assertIn("error", out)
                self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_exit_without_check_is_refused(self):
        payload, run_id = self.popped_run()
        before = self.run_path(payload).read_bytes()
        code, _text, out = self.loop("--mark", "--run", run_id, "--id", "001", "--exit", "0")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_check_on_an_ended_run_is_refused(self):
        payload, run_id = self.popped_run()
        self.loop("--end", "--run", run_id)
        before = self.run_path(payload).read_bytes()
        code, _text, out = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--check", "python -m ruff check .", "--exit", "0"
        )
        self.assertEqual(code, 1, out)
        self.assertIn("ended", out)
        self.assertEqual(self.run_path(payload).read_bytes(), before)


class TestEndToEnd(_PreflightBase):
    """Phase 4 to Phase 6 for one Route B item, as the orchestrator calls the CLI."""

    def drive_to_checks(self, exits: list[int]) -> tuple[dict, str]:
        payload = self.init("--mode", "specific", "--items", "002")
        self.assertEqual([(q["id"], q["route_at_init"]) for q in payload["queue"]], [("002", "B")])
        run_id = payload["run"]
        self.assertEqual(self.loop("--next", "--run", run_id)[0], 0)
        for phase in ("selected", "acting", "verifying"):
            self.assertEqual(self.loop("--mark", "--run", run_id, "--id", "002", "--phase", phase)[0], 0)
        for number, code in enumerate(exits, start=1):
            command = f"python -B tools/check_{number}.py"
            self.assertEqual(
                self.loop("--mark", "--run", run_id, "--id", "002", "--check", command, "--exit", str(code))[0], 0
            )
        return payload, run_id

    def marks(self, payload: dict) -> list[tuple[str, str]]:
        return [
            (event["event"], event["detail"]) for event in self.read_run(payload)["history"]
            if event["event"] in ("mark", "check", "boundary")
        ]

    def boundary(self, payload: dict, run_id: str) -> list[str]:
        code, text, out = self.loop("--boundary", "--run", run_id)
        self.assertEqual(code, 0, out)
        lines = text.splitlines()
        expected = MARKER_FORMAT.format(run=run_id, done="002", remaining=0, state=payload["state"])
        self.assertEqual(out["marker"], expected)
        self.assertEqual(lines[-2], expected)
        return lines

    def test_complete_with_two_passing_checks(self):
        payload, run_id = self.drive_to_checks([0, 0])
        self.assertEqual(self.loop("--mark", "--run", run_id, "--id", "002", "--outcome", "COMPLETE")[0], 0)
        lines = self.boundary(payload, run_id)

        record = self.read_run(payload)["items"]["002"]
        self.assertEqual(record["route"], "B")
        self.assertEqual([c["command"] for c in record["checks"]],
                         ["python -B tools/check_1.py", "python -B tools/check_2.py"])
        self.assertEqual(self.marks(payload), [
            ("mark", "phase=selected"), ("mark", "phase=acting"), ("mark", "phase=verifying"),
            ("check", "exit=0"), ("check", "exit=0"), ("mark", "outcome=COMPLETE"),
            ("boundary", "remaining=0"),
        ])
        self.assertIn("Checks:", lines)
        self.assertIn("  002: 2/2 passed", lines)
        self.assertNotIn("Skipped (by reason):", lines)
        self.assertLess(lines.index("Checks:"), len(lines) - 2)

    def test_failing_check_then_documented_skip(self):
        payload, run_id = self.drive_to_checks([0, 1])
        code, _text, out = self.loop(
            "--mark", "--run", run_id, "--id", "002", "--outcome", "SKIPPED",
            "--decision", "Which helper owns the failing check?",
        )
        self.assertEqual(code, 0, out)
        lines = self.boundary(payload, run_id)

        self.assertIn("Skipped (by reason):", lines)
        at = lines.index("Skipped (by reason):")
        self.assertEqual(lines[at + 1:at + 3], [f"  {backlog_loop.USER_INPUT_NOTE}:", "    002"])
        self.assertIn("  002: 1/2 passed", lines)
        self.assertIn("    exit 1: python -B tools/check_2.py", lines)
        self.assertNotIn("    exit 0: python -B tools/check_1.py", lines)
        self.assertLess(at, lines.index("Checks:"))
        item = (self.backlog_dir / item_filename("002")).read_text(encoding="utf-8")
        self.assertIn(f"### Q1. Loop decision (run {run_id})", item)
        self.assertIn("Which helper owns the failing check?", item)

    def test_a_refused_decision_exits_1_and_writes_nothing(self):
        payload, run_id = self.drive_to_checks([1])
        item_path = self.backlog_dir / item_filename("002")
        # A frontmatter that never closes: the block has no safe place to go.
        item_path.write_text("---\nid: 002\nstatus: NOT_STARTED\n\nBody line.\n", encoding="utf-8", newline="\n")
        item_before = item_path.read_bytes()
        run_before = self.run_path(payload).read_bytes()

        code, _text, out = self.loop(
            "--mark", "--run", run_id, "--id", "002", "--outcome", "SKIPPED", "--decision", "Which helper?",
        )

        self.assertEqual(code, 1, out)
        self.assertIn("error", out)
        self.assertEqual(item_path.read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

    def test_a_question_error_at_the_write_becomes_a_usage_error(self):
        payload, run_id = self.drive_to_checks([1])
        run_before = self.run_path(payload).read_bytes()

        with mock.patch.object(backlog_loop, "append_question",
                               side_effect=backlog_loop.QuestionError("refused at the write")):
            code, _text, out = self.loop(
                "--mark", "--run", run_id, "--id", "002", "--outcome", "SKIPPED", "--decision", "Which helper?",
            )

        self.assertEqual(code, 1, out)
        self.assertIn("refused at the write", out["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)


if __name__ == "__main__":
    unittest.main()
