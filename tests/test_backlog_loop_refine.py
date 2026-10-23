#!/usr/bin/env python3
"""Tests for the loop's refine step in backlog_loop.py.

  * `--init` decides each item's disposition: `refine` for an unrefined item
    inside the `--refine-max` cap or named by `--mode specific`, `run` for a
    refined item and for an unrefined Route A or B item past the cap. A
    refined Route C item, a `needs_plan` item and an item with unanswered
    `## Open Questions` are excluded with their own reasons.
  * `--next` reads the live file: it reports `refined` and `disposition`, and
    skips an item whose questions are unanswered without dispatching it.
  * `--mark --refined` records the refine outcome under its own history
    event, and the end summary groups the outcomes.

The fixture and driver come from test_backlog_loop.py. With a cap of 10 the
queue is 001, 003, 002, 006, 007 (scores 30, 30, 20, 10, 10).

Run with:  python -m pytest tests/test_backlog_loop_refine.py -q
"""

import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import backlog_loop
from test_backlog_loop import _LoopFixtureBase, item_filename, item_text

CAPPED = ("--mode", "all", "--refine-max", "10")
CAPPED_QUEUE = ["001", "003", "002", "006", "007"]
MULTI = "This work spans a multi-sprint effort."


class TestRefine(_LoopFixtureBase):
    def item_file(self, item_id: str) -> Path:
        return self.backlog_dir / item_filename(item_id)

    def write_text(self, item_id: str, text: str) -> None:
        self.item_file(item_id).write_text(text, encoding="utf-8", newline="\n")

    def refined_route_c(self, item_id: str) -> str:
        """A refined item whose body also carries a strong Route C signal."""
        return item_text(item_id, "NOT_STARTED", "refined").replace("## Resolution", f"{MULTI}\n\n## Resolution")

    def queued(self, payload: dict) -> dict:
        return {q["id"]: q["disposition"] for q in payload["queue"]}

    def mark(self, run_id: str, item_id: str, *extra: str) -> tuple[int, str, dict]:
        return self.loop("--mark", "--run", run_id, "--id", item_id, *extra)

    def test_init_queues_route_c_item_with_refined_false_as_refine(self):
        payload = self.init(*CAPPED)

        self.assertEqual([q["id"] for q in payload["queue"]], CAPPED_QUEUE)
        self.assertEqual([q["score"] for q in payload["queue"]], [30, 30, 20, 10, 10])
        self.assertEqual(self.queued(payload)["003"], "refine")
        self.assertEqual(set(self.queued(payload).values()), {"refine"})
        meta = self.read_run(payload)["queue_meta"]["003"]
        self.assertEqual(meta["route_at_init"], "C")
        self.assertEqual((meta["refined_at_init"], meta["disposition_at_init"]), (False, "refine"))

    def test_init_queues_refined_route_b_item_as_run(self):
        self.write_item("002", "NOT_STARTED", "refined")

        payload = self.init(*CAPPED)

        queue = {q["id"]: q for q in payload["queue"]}
        self.assertEqual((queue["002"]["route_at_init"], queue["002"]["disposition"]), ("B", "run"))
        self.assertEqual(self.queued(payload)["001"], "refine")
        meta = self.read_run(payload)["queue_meta"]["002"]
        self.assertEqual((meta["refined_at_init"], meta["disposition_at_init"]), (True, "run"))

    def test_init_excludes_refined_route_c_as_plans_deferred(self):
        self.write_text("003", self.refined_route_c("003"))

        payload = self.init(*CAPPED)

        self.assertNotIn("003", self.queued(payload))
        entry = {e["id"]: e for e in payload["excluded"]}["003"]
        self.assertEqual(entry["reason"], backlog_loop.EXCLUDED_REASON)
        self.assertEqual((entry["route"], entry["large_scope"], entry["refined"]), ("C", True, True))

    def test_refined_item_failing_shape_gate_is_refinable(self):
        # Refined, but with no ## Verification: the shape gate fails, so the
        # item routes C and is refined again rather than deferred to a plan.
        text = item_text("003", "NOT_STARTED", "refined")
        self.write_text("003", text.replace("## Verification", "## Checks"))

        payload = self.init(*CAPPED)

        self.assertEqual(self.queued(payload)["003"], "refine")
        meta = self.read_run(payload)["queue_meta"]["003"]
        self.assertEqual((meta["route_at_init"], meta["refined_at_init"]), ("C", True))
        self.loop("--next", "--run", payload["run"])
        self.mark(payload["run"], "001", "--outcome", "COMPLETE")
        _code, _text, popped = self.loop("--next", "--run", payload["run"])
        self.assertEqual((popped["next"], popped["refined"], popped["disposition"]), ("003", True, "refine"))
        named = self.init("--mode", "specific", "--items", "003")
        _code, _text, popped = self.loop("--next", "--run", named["run"])
        self.assertEqual((popped["next"], popped["refined"], popped["disposition"]), ("003", True, "refine"))

        capped = self.init("--mode", "all")

        self.assertNotIn("003", self.queued(capped))
        entry = {e["id"]: e for e in capped["excluded"]}["003"]
        self.assertEqual(entry["reason"], backlog_loop.NEEDS_REFINE_REASON)
        self.assertEqual((entry["route"], entry["large_scope"], entry["refined"]), ("C", False, True))

    def test_init_excludes_needs_plan_item(self):
        payload = self.init(*CAPPED)

        entry = {e["id"]: e for e in payload["excluded"]}["009"]
        self.assertEqual(entry["reason"], backlog_loop.NEEDS_PLAN_REASON)
        self.assertEqual(entry["reason"], "marked for a planning session")
        self.assertEqual((entry["route"], entry["large_scope"], entry["refined"]), (None, False, False))

    def test_init_excludes_unanswered_open_questions(self):
        for argv in (("--mode", "all"), CAPPED):
            with self.subTest(argv=argv):
                payload = self.init(*argv)

                self.assertNotIn("008", self.queued(payload))
                reasons = {e["id"]: e["reason"] for e in payload["excluded"]}
                self.assertEqual(reasons["008"], backlog_loop.OPEN_QUESTIONS_REASON)
                self.assertEqual(reasons["008"], "open questions unanswered")

    def test_init_queues_answered_open_questions(self):
        answered = item_text("008", "NOT_STARTED", "questions").replace("Answer:", "Answer: A, the reader.")
        self.write_text("008", answered)

        payload = self.init(*CAPPED)

        self.assertEqual(self.queued(payload)["008"], "refine")
        self.assertNotIn("008", {e["id"] for e in payload["excluded"]})

    def test_next_reports_live_refined_and_disposition(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]

        _code, _text, first = self.loop("--next", "--run", run_id)
        self.assertEqual((first["next"], first["refined"], first["disposition"]), ("001", False, "refine"))

        # 003 was refined after init: the live file wins over the init reading.
        self.mark(run_id, "001", "--outcome", "COMPLETE")
        self.write_item("003", "NOT_STARTED", "refined")
        _code, _text, second = self.loop("--next", "--run", run_id)
        self.assertEqual((second["next"], second["refined"], second["disposition"]), ("003", True, "run"))
        self.assertEqual(self.read_run(payload)["queue_meta"]["003"]["disposition_at_init"], "refine")

    def test_next_skips_unanswered_questions_without_dispatch(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        # After init, 001 gains an unanswered question.
        self.write_item("001", "NOT_STARTED", "questions")

        code, text, popped = self.loop("--next", "--run", run_id)

        self.assertEqual(code, 0)
        self.assertEqual((popped["next"], popped["skipped"]), ("003", ["001"]))
        self.assertIn(f"Skipped 001: {backlog_loop.OPEN_QUESTIONS_NOTE}", text)
        items = self.read_run(payload)["items"]
        self.assertEqual((items["001"]["outcome"], items["001"]["note"]), ("SKIPPED", "open-questions-unanswered"))
        self.assertIsNone(items["001"]["started"])
        self.assertNotIn("pre_status", items["001"])

    def test_mark_refined_records_outcome_and_history_event(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, marked = self.mark(run_id, "001", "--refined", "REFINED")

        self.assertEqual(code, 0)
        self.assertEqual(marked["refine"]["outcome"], "REFINED")
        run = self.read_run(payload)
        record = run["items"]["001"]
        self.assertEqual(record["refine"]["outcome"], "REFINED")
        self.assertEqual(record["refine"]["sub_items"], [])
        self.assertTrue(record["refine"]["at"])
        self.assertIsNone(record["outcome"])
        event = run["history"][-1]
        self.assertEqual((event["event"], event["id"], event["detail"]), ("refine", "001", "REFINED"))

    def test_mark_refined_stands_alone(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        resolution = self.tmp / "resolution.md"
        resolution.write_text("Closed: already met.\n", encoding="utf-8")
        before = self.run_path(payload).read_bytes()

        for extra in (
            ("--outcome", "COMPLETE"),
            ("--phase", "acting"),
            ("--note", "x"),
            ("--lessons", "L-1"),
            ("--needs-plan",),
            ("--resolution-file", str(resolution)),
        ):
            with self.subTest(extra=extra):
                code, _text, error = self.mark(run_id, "001", "--refined", "REFINED", *extra)

                self.assertEqual(code, 1)
                self.assertIn("--refined stands alone", error["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_mark_refined_decompose_requires_sub_items(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        before = self.run_path(payload).read_bytes()

        code, _text, error = self.mark(run_id, "001", "--refined", "DECOMPOSE")
        self.assertEqual(code, 1)
        self.assertIn("--sub-items", error["error"])
        code, _text, error = self.mark(run_id, "001", "--refined", "DECOMPOSE", "--sub-items", " , ")
        self.assertEqual(code, 1)
        code, _text, error = self.mark(run_id, "001", "--refined", "REFINED", "--sub-items", "011")
        self.assertEqual(code, 1)
        self.assertIn("DECOMPOSE only", error["error"])
        code, _text, error = self.mark(run_id, "001", "--outcome", "COMPLETE", "--sub-items", "011")
        self.assertEqual(code, 1)
        self.assertEqual(self.run_path(payload).read_bytes(), before)

        code, _text, marked = self.mark(run_id, "001", "--refined", "DECOMPOSE", "--sub-items", "011, 012")
        self.assertEqual(code, 0)
        self.assertEqual(marked["refine"]["sub_items"], ["011", "012"])
        self.assertEqual(self.read_run(payload)["history"][-1]["detail"], "DECOMPOSE sub_items=011,012")

    def test_mark_refined_rejects_unknown_outcome(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        before = self.run_path(payload).read_bytes()

        code, _text, error = self.mark(run_id, "001", "--refined", "DONE")
        self.assertEqual(code, 1)
        self.assertIn("error", error)
        # An item that was never popped is refused like --lessons.
        code, _text, error = self.mark(run_id, "002", "--refined", "REFINED")
        self.assertEqual(code, 1)
        self.assertIn("unknown item id", error["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_refine_event_keeps_boundary_recorded(self):
        payload = self.init(*CAPPED)
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        self.mark(run_id, "001", "--outcome", "COMPLETE")
        self.loop("--boundary", "--run", run_id)

        self.mark(run_id, "001", "--refined", "ALREADY_MET")

        run = self.read_run(payload)
        self.assertTrue(backlog_loop.boundary_recorded(run, "001"))
        self.assertEqual([e["event"] for e in run["history"] if e["id"] == "001"][-2:], ["boundary", "refine"])
        before = self.run_path(payload).read_bytes()
        self.loop("--boundary", "--run", run_id)
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_summary_groups_refine_outcomes(self):
        payload = self.init("--mode", "n", "--n", "3", "--refine-max", "10")
        run_id = payload["run"]
        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "003", "002"])
        for item_id, refine, outcome in (
            ("001", ("--refined", "QUESTIONS"), "SKIPPED"),
            ("003", ("--refined", "DECOMPOSE", "--sub-items", "011"), "SKIPPED"),
            ("002", ("--refined", "REFINED"), "COMPLETE"),
        ):
            _code, _text, popped = self.loop("--next", "--run", run_id)
            self.assertEqual(popped["next"], item_id)
            self.assertEqual(self.mark(run_id, item_id, *refine)[0], 0)
            self.assertEqual(self.mark(run_id, item_id, "--outcome", outcome)[0], 0)
            self.loop("--boundary", "--run", run_id)

        code, text, _payload = self.loop("--end", "--run", run_id)

        self.assertEqual(code, 0)
        lines = text.splitlines()
        self.assertIn("| ID | Feature | Route | Outcome | Refine |", lines)
        self.assertIn("| 001 | Short fix | A | SKIPPED | QUESTIONS |", lines)
        self.assertIn("| 002 | Stepwise change | B | COMPLETE | REFINED |", lines)
        at = lines.index("Refine outcomes:")
        self.assertEqual(lines[at + 1:at + 4], ["  REFINED: 002", "  QUESTIONS: 001", "  DECOMPOSE: 003"])
        written = lines.index("Open questions written (answer in each item's ## Open Questions):")
        self.assertEqual(lines[written + 1], "  001")
        # One excluded-list header per reason, each once.
        headers = [line for line in lines if line.startswith("Excluded (")]
        self.assertEqual(headers, [
            "Excluded (open questions unanswered):",
            "Excluded (marked for a planning session):",
        ])

    def test_specific_mode_warns_per_reason(self):
        self.write_text("003", self.refined_route_c("003"))

        code, text, payload = self.loop("--init", "--mode", "specific", "--items", "008,009,003,002")

        self.assertEqual(code, 0)
        self.assertEqual(self.queued(payload), {"002": "refine"})
        self.assertEqual(payload["warnings"], [
            "warning: item 008 dropped: open questions unanswered",
            "warning: item 009 dropped: marked for a planning session",
            "warning: item 003 dropped: route C is deferred in loop mode",
        ])
        self.assertIn("warning: item 008 dropped: open questions unanswered", text)

    def test_init_default_cap_queues_no_refine(self):
        # 006 becomes a conservative-default Route C item: no keyword, no steps.
        self.write_item("006", "NOT_STARTED", "default_c")

        payload = self.init("--mode", "all")

        self.assertEqual(self.queued(payload), {"001": "run", "002": "run", "007": "run"})
        self.assertEqual(self.read_run(payload)["refine_max"], 0)
        reasons = {e["id"]: e["reason"] for e in payload["excluded"]}
        self.assertEqual(reasons["003"], backlog_loop.EXCLUDED_REASON)
        self.assertEqual(reasons["006"], backlog_loop.NEEDS_REFINE_REASON)
        self.assertEqual(reasons["006"], "needs refine")

    def test_refine_max_caps_the_refine_queue(self):
        two = self.init("--mode", "all", "--refine-max", "2")
        # The two highest-scored unrefined items refine; the rest run as before.
        self.assertEqual([q["id"] for q in two["queue"]], CAPPED_QUEUE)
        self.assertEqual(
            self.queued(two), {"001": "refine", "003": "refine", "002": "run", "006": "run", "007": "run"}
        )

        one = self.init("--mode", "all", "--refine-max", "1")
        # 003 ties 001 at 30 and loses on id, so it falls past the cap and keeps
        # its strong-signal exclusion.
        self.assertEqual(self.queued(one), {"001": "refine", "002": "run", "006": "run", "007": "run"})
        self.assertEqual({e["id"]: e["reason"] for e in one["excluded"]}["003"], backlog_loop.EXCLUDED_REASON)

        code, _text, error = self.loop("--init", "--mode", "all", "--refine-max", "-1")
        self.assertEqual(code, 1)
        self.assertIn("--refine-max", error["error"])


if __name__ == "__main__":
    unittest.main()
