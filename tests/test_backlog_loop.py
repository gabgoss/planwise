#!/usr/bin/env python3
"""Unit tests for backlog_loop.py, the loop-mode run-state writer.

Each test builds an isolated temp planwise tree (config.yaml, a generated hub
index, and item files whose contents steer the triage route) and drives
`backlog_loop.main()` with an injected argv. Every test asserts on the exit
code and on the final JSON line; the tests that name file bytes assert on the
run file's bytes too.

Fixture items (scores use the default weights: High 30, Medium 20, Low 10):

  001  High    route A   short file (under 50 lines)
  002  Medium  route B   50+ lines, three numbered steps, no exact-fix evidence
  003  High    route C   carries the word "multi-sprint"
  004  High    BLOCKED   held, never selectable
  005  Medium  blocked by 006 through the Blocks cell on 006's hub row
  006  Low     route A   short file; blocks 005
  007  Low     route A   short file
  008  Low     excluded  one `### Q1.` block with an empty `Answer:` (open questions unanswered)
  009  Low     excluded  `needs_plan: true` (marked for a planning session)

Every queued item is unrefined. With no --refine-max cap each one queues with
disposition `run` and 003 is excluded; with a cap of 5 or more the queue is
001, 003, 002, 006, 007, each with disposition `refine`. The `refined` kind of
`item_text` (50+ lines, three steps under `## Resolution`, a fenced
`## Verification`, `## Open Questions` holding `None.`) is used by the tests
that rewrite an item.

Run with:  python -m pytest tests/test_backlog_loop.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import backlog_loop
import parse_backlog
import score_backlog

CONFIG_YAML_FIXTURE = """project:
  name: "BacklogLoopFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

HUB_HEADER = (
    "| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
    "|----|-------|----------|--------|--------|---------|--------|-------|------|\n"
)

# (id, title, priority, status, blocks cell, kind)
FIXTURE_ITEMS = [
    ("001", "Short fix", "High", "NOT_STARTED", "", "short"),
    ("002", "Stepwise change", "Medium", "NOT_STARTED", "", "steps"),
    ("003", "Big plan", "High", "NOT_STARTED", "", "multi"),
    ("004", "Held item", "High", "BLOCKED", "", "short"),
    ("005", "Dependent item", "Medium", "NOT_STARTED", "", "short"),
    ("006", "Blocker item", "Low", "NOT_STARTED", "[005]", "short"),
    ("007", "Low extra", "Low", "NOT_STARTED", "", "short"),
    ("008", "Asked item", "Low", "NOT_STARTED", "", "questions"),
    ("009", "Needs plan", "Low", "NOT_STARTED", "", "needs_plan"),
]

RUN_ID = "20261007-120000"


def item_filename(item_id: str) -> str:
    return f"{item_id}-INFRA-fixture-item.md"


def item_text(item_id: str, status: str, kind: str) -> str:
    """A whole item file. Its newline count steers the route (50 is the cut)."""
    lines = ["---", f"id: {item_id}", f"status: {status}"]
    if kind == "refined":
        lines.append("refined: true")
    elif kind == "needs_plan":
        lines.append("needs_plan: true")
    lines.extend(["---", "", f"# Item {item_id}", ""])
    if kind in ("short", "questions", "needs_plan"):
        lines.append("A small, well-bounded change to one helper.")
        if kind == "questions":
            lines.extend([
                "", "## Open Questions", "", "### Q1. Which helper owns the change?", "",
                "Options: (A) the reader (B) the writer",
                "Recommendation: A. The reader holds the state.", "Answer:",
            ])
    else:
        lines.extend(f"Background note {n} about the widget." for n in range(1, 51))
        if kind == "steps":
            lines.extend(["", "1. Read the helper.", "2. Adjust the helper.", "3. Run the checks."])
        elif kind == "multi":
            lines.extend(["", "This work spans a multi-sprint effort."])
        elif kind == "refined":
            lines.extend([
                "", "## Resolution", "", "Approach: adjust the helper in place.", "",
                "1. Read the helper.", "2. Adjust the helper.", "3. Run the checks.",
                "", "## Verification", "", "```", "python -m pytest -q", "# expect: all pass", "```",
                "", "## Open Questions", "", "None.",
            ])
    return "\n".join(lines) + "\n"


class _LoopFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree and a driver for main()."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backlog_loop_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.runs_dir = self.backlog_dir / "Backlog-Runs"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        rows = []
        for item_id, title, priority, status, blocks, kind in FIXTURE_ITEMS:
            self.write_item(item_id, status, kind)
            rows.append(
                f"| {item_id} | {title} | {priority} | {status} | INFRA | 2026-10-01 | "
                f"{blocks} | 0 | [01]({item_filename(item_id)}) |\n"
            )
        (self.backlog_dir / "00-Index-Backlog.md").write_text(
            HUB_HEADER + "".join(rows), encoding="utf-8"
        )

    def write_item(self, item_id: str, status: str, kind: str) -> Path:
        path = self.backlog_dir / item_filename(item_id)
        path.write_text(item_text(item_id, status, kind), encoding="utf-8", newline="\n")
        return path

    def loop(self, *argv: str) -> tuple[int, str, dict]:
        """Run main() with --config injected. Returns (exit code, stdout, last JSON)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = backlog_loop.main(["--config", str(self.config_path), *argv])
        text = out.getvalue()
        lines = text.splitlines()
        self.assertTrue(lines, "the command printed nothing")
        return code, text, json.loads(lines[-1])

    def init(self, *extra: str) -> dict:
        code, _text, payload = self.loop("--init", *extra)
        self.assertEqual(code, 0, payload)
        return payload

    def run_path(self, payload: dict) -> Path:
        return Path(payload["state"])

    def read_run(self, payload: dict) -> dict:
        return json.loads(self.run_path(payload).read_text(encoding="utf-8"))


class TestInit(_LoopFixtureBase):
    def test_init_all(self):
        payload = self.init("--mode", "all")

        queue = payload["queue"]
        # Queue order is (-score, id): High 001 (30), Medium 002 (20), then the
        # two Low items by id. 003 is route C, 004 is held, 005 is blocked.
        # No --refine-max cap: nothing is refined, so every item runs.
        self.assertEqual([q["id"] for q in queue], ["001", "002", "006", "007"])
        routes = {q["id"]: q["route_at_init"] for q in queue}
        self.assertEqual(routes["001"], "A")
        self.assertEqual(routes["002"], "B")
        self.assertEqual([q["score"] for q in queue], [30, 20, 10, 10])
        self.assertEqual({q["disposition"] for q in queue}, {"run"})

        self.assertEqual([e["id"] for e in payload["excluded"]], ["003", "008", "009"])
        excluded = payload["excluded"][0]
        self.assertEqual(excluded["reason"], "plans deferred in loop mode")
        self.assertEqual(excluded["route"], "C")
        self.assertTrue(excluded["large_scope"])
        reasons = {e["id"]: e["reason"] for e in payload["excluded"]}
        self.assertEqual(reasons["008"], backlog_loop.OPEN_QUESTIONS_REASON)
        self.assertEqual(reasons["009"], backlog_loop.NEEDS_PLAN_REASON)

        # Neither the BLOCKED item nor the item blocked by an open dependency
        # reaches the queue, and neither is reported as excluded.
        queued_ids = {q["id"] for q in queue}
        self.assertTrue({"004", "005"}.isdisjoint(queued_ids))
        self.assertTrue({"004", "005"}.isdisjoint({e["id"] for e in payload["excluded"]}))

        path = self.run_path(payload)
        self.assertEqual(path.parent, self.runs_dir.resolve())
        raw = path.read_bytes()
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertNotIn(b"\r", raw)
        run = json.loads(raw)
        self.assertEqual(run["queue"], ["001", "002", "006", "007"])
        self.assertEqual(run["mode"], "all")
        self.assertIsNone(run["current"])
        self.assertEqual(run["history"][0]["event"], "init")
        self.assertEqual(run["queue_meta"]["002"]["route_at_init"], "B")

    def test_init_n1(self):
        payload = self.init("--mode", "n", "--n", "1")

        self.assertEqual([q["id"] for q in payload["queue"]], ["001"])
        self.assertEqual(len(self.read_run(payload)["queue"]), 1)

    def test_init_specific_ineligible(self):
        code, text, payload = self.loop("--init", "--mode", "specific", "--items", "007,009,002")

        self.assertEqual(code, 0)
        # The user's order is kept; the needs_plan id is dropped with a warning.
        self.assertEqual([q["id"] for q in payload["queue"]], ["007", "002"])
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("009", payload["warnings"][0])
        self.assertIn("warning: item 009 dropped: marked for a planning session", text)

    def test_init_priority(self):
        everything = self.init("--mode", "all")
        narrowed = self.init("--mode", "all", "--priority", "High")

        self.assertGreater(len(everything["queue"]), 1)
        # High items: 001 (A), 003 (C, excluded), 004 (held).
        self.assertEqual([q["id"] for q in narrowed["queue"]], ["001"])
        self.assertEqual(self.read_run(narrowed)["filters"]["priority"], "High")


class TestRepeatedRowId(_LoopFixtureBase):
    """A repeated row id in the hub index is refused before anything keys rows
    by id, with the same message `parse_backlog.py` prints.

    Without the guard the loop keyed rows last-wins: the repeated id queued
    twice, and a copy with an empty Blocks cell dropped the edge the other
    copy carried.
    """

    def repeat_row(self, item_id: str, blocks: str | None = None) -> None:
        """Insert a second copy of an item's hub row directly after the first."""
        hub = self.backlog_dir / "00-Index-Backlog.md"
        out = []
        for line in hub.read_text(encoding="utf-8").splitlines(keepends=True):
            out.append(line)
            if line.startswith(f"| {item_id} |"):
                copy = line
                if blocks is not None:
                    cells = line.split("|")
                    cells[7] = f" {blocks} " if blocks else " "
                    copy = "|".join(cells)
                out.append(copy)
        hub.write_text("".join(out), encoding="utf-8")

    def run_files(self) -> list[Path]:
        return sorted(self.runs_dir.rglob("*")) if self.runs_dir.exists() else []

    def test_baseline_without_a_repeat_still_queues(self):
        payload = self.init("--mode", "all")

        # 005 stays held: 006's Blocks cell names it.
        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "002", "006", "007"])

    def test_init_refuses_a_repeated_id_and_writes_no_run_file(self):
        self.repeat_row("001", blocks="")

        code, _text, payload = self.loop("--init", "--mode", "all")

        self.assertEqual(code, 1)
        self.assertIn("duplicate row id(s) in the backlog index: 001, 001", payload["error"])
        self.assertIn("each id must appear on exactly one row", payload["error"])
        self.assertEqual(self.run_files(), [])

    def test_init_refuses_a_repeat_that_would_drop_a_blocks_edge(self):
        # 006's second copy has an empty Blocks cell. Last-wins keying released 005.
        self.repeat_row("006", blocks="")

        code, _text, payload = self.loop("--init", "--mode", "all")

        self.assertEqual(code, 1)
        self.assertIn("006", payload["error"])
        self.assertNotIn("007", payload["error"])
        self.assertEqual(self.run_files(), [])

    def test_next_refuses_a_repeated_id_and_leaves_the_run_file_alone(self):
        payload = self.init("--mode", "all")
        before = self.run_path(payload).read_bytes()
        self.repeat_row("001")

        code, _text, refused = self.loop("--next", "--run", payload["run"])

        self.assertEqual(code, 1)
        self.assertIn("duplicate row id(s) in the backlog index: 001, 001", refused["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_skipped_mark_refuses_a_repeated_id_and_leaves_the_run_file_alone(self):
        payload = self.init("--mode", "all")
        self.loop("--next", "--run", payload["run"])
        before = self.run_path(payload).read_bytes()
        self.repeat_row("001")

        code, _text, refused = self.loop(
            "--mark", "--run", payload["run"], "--id", "001", "--outcome", "SKIPPED"
        )

        self.assertEqual(code, 1)
        self.assertIn("001", refused["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_duplicate_row_ids_groups_spellings_of_one_id(self):
        rows = [{"id": "001"}, {"id": "002"}, {"id": "1"}, {"id": "003"}, {"id": "002"}]

        self.assertEqual(parse_backlog.duplicate_row_ids(rows), [["001", "1"], ["002", "002"]])
        self.assertEqual(parse_backlog.duplicate_row_ids(rows[:2] + rows[3:4]), [])


class TestInitArchivedBlockerInDependenciesTable(_LoopFixtureBase):
    """The loop shares `parse_backlog.build_blocked_by_map`, so a legacy
    `## Dependencies` edge from a COMPLETE blocker that lives only in an
    Archive shard must not keep its item out of the queue."""

    DEPENDENCIES = "\n## Dependencies\n\n| ID | Blocks |\n|----|--------|\n"

    def write_hub_with_dependency(self, blocker: str) -> None:
        rows = "".join(
            f"| {item_id} | {title} | {priority} | {status} | INFRA | 2026-10-01 | "
            f"{blocks} | 0 | [01]({item_filename(item_id)}) |\n"
            for item_id, title, priority, status, blocks, _kind in FIXTURE_ITEMS
            if item_id in ("001", "002")
        )
        (self.backlog_dir / "00-Index-Backlog.md").write_text(
            HUB_HEADER + rows + self.DEPENDENCIES + f"| {blocker} | 002 |\n", encoding="utf-8"
        )

    def write_archived_blocker(self) -> None:
        archive_dir = self.backlog_dir / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "Index-Backlog-100-100.md").write_text(
            HUB_HEADER
            + "| 100 | Closed blocker | Low | COMPLETE | INFRA | 2026-09-01 | | - | [01](100-INFRA-x.md) |\n",
            encoding="utf-8",
        )

    def test_archived_closed_blocker_does_not_hold_the_item_back(self):
        self.write_archived_blocker()
        self.write_hub_with_dependency("100")

        payload = self.init("--mode", "all")

        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "002"])

    def test_blocker_found_nowhere_still_holds_the_item_back(self):
        self.write_archived_blocker()
        self.write_hub_with_dependency("999")

        payload = self.init("--mode", "all")

        self.assertEqual([q["id"] for q in payload["queue"]], ["001"])


class TestNext(_LoopFixtureBase):
    def test_next_pops(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]

        code, _text, popped = self.loop("--next", "--run", run_id)

        self.assertEqual(code, 0)
        self.assertEqual(popped["next"], "001")
        self.assertEqual(popped["remaining"], 3)
        self.assertEqual((popped["refined"], popped["disposition"]), (False, "run"))
        self.assertEqual(popped["run"], run_id)
        self.assertEqual(popped["state"], payload["state"])
        run = self.read_run(payload)
        self.assertEqual(run["current"], "001")
        self.assertEqual(run["queue"], ["002", "006", "007"])
        self.assertEqual(run["items"]["001"]["route_at_init"], "A")
        self.assertEqual(run["items"]["001"]["score"], 30)

        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE")
        _code, _text, second = self.loop("--next", "--run", run_id)
        self.assertEqual((second["next"], second["remaining"]), ("002", 2))

    def test_next_skips_flipped_item(self):
        payload = self.init("--mode", "all")
        # 001 is queued first; its frontmatter flips to COMPLETE before the pop.
        self.write_item("001", "COMPLETE", "short")

        code, _text, popped = self.loop("--next", "--run", payload["run"])

        self.assertEqual(code, 0)
        self.assertEqual(popped["skipped"], ["001"])
        self.assertEqual((popped["next"], popped["remaining"]), ("002", 2))
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(record["outcome"], "SKIPPED")
        self.assertEqual(record["note"], "no-longer-selectable")
        self.assertEqual(record["phase"], "closed")

    def test_halt(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        for phase in ("acting", "verifying"):
            with self.subTest(phase=phase):
                self.loop("--mark", "--run", run_id, "--id", "001", "--phase", phase)
                before = self.run_path(payload).read_bytes()

                code, _text, halted = self.loop("--next", "--run", run_id)

                self.assertEqual(code, 3)
                self.assertTrue(halted["halt"])
                self.assertEqual((halted["item"], halted["phase"]), ("001", phase))
                self.assertEqual(self.run_path(payload).read_bytes(), before)


class TestMark(_LoopFixtureBase):
    def test_mark_outcome(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001",
            "--outcome", "COMPLETE", "--route", "A", "--note", "fixed",
        )

        self.assertEqual(code, 0)
        self.assertEqual((marked["phase"], marked["outcome"]), ("closed", "COMPLETE"))
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(record["phase"], "closed")
        self.assertEqual(record["outcome"], "COMPLETE")
        self.assertEqual((record["route"], record["note"]), ("A", "fixed"))
        self.assertTrue(record["closed"])

        before = self.run_path(payload).read_bytes()
        code, _text, error = self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "DONE")
        self.assertEqual(code, 1)
        self.assertIn("error", error)
        code, _text, error = self.loop("--mark", "--run", run_id, "--id", "999", "--outcome", "SKIPPED")
        self.assertEqual(code, 1)
        self.assertIn("error", error)
        self.assertEqual(self.run_path(payload).read_bytes(), before)


class TestBoundary(_LoopFixtureBase):
    def test_boundary(self):
        payload = self.init("--mode", "n", "--n", "2")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        # No outcome yet: refused with exit 3, nothing written.
        before = self.run_path(payload).read_bytes()
        code, _text, refused = self.loop("--boundary", "--run", run_id)
        self.assertEqual(code, 3)
        self.assertIn("error", refused)
        self.assertEqual(self.run_path(payload).read_bytes(), before)

        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE")
        code, text, first = self.loop("--boundary", "--run", run_id)
        expected = backlog_loop.MARKER_FORMAT.format(
            run=run_id, done="001", remaining=1, state=payload["state"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(first["marker"], expected)
        self.assertEqual(text.splitlines()[-2], expected)
        self.assertEqual(first["remaining"], 1)
        self.assertIsNone(self.read_run(payload)["ended"])

        self.loop("--next", "--run", run_id)
        self.loop("--mark", "--run", run_id, "--id", "002", "--outcome", "SKIPPED")
        code, text, last = self.loop("--boundary", "--run", run_id)
        expected = backlog_loop.MARKER_FORMAT.format(
            run=run_id, done="002", remaining=0, state=payload["state"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(last["marker"], expected)
        lines = text.splitlines()
        self.assertEqual(lines[-2], expected)
        # remaining 0 applies --end and prints the summary above the marker.
        summary_at = lines.index(f"Loop summary for run {run_id}")
        self.assertLess(summary_at, len(lines) - 2)
        self.assertTrue(any(line.startswith("| 001 |") and "COMPLETE" in line for line in lines))
        self.assertTrue(any(line.startswith("| 002 |") and "SKIPPED" in line for line in lines))
        run = self.read_run(payload)
        self.assertTrue(run["ended"])
        events = [event["event"] for event in run["history"]]
        self.assertEqual(events.count("boundary"), 2)
        self.assertEqual(events.count("end"), 1)

        # A second call prints the same text and changes no byte of the file.
        file_bytes = self.run_path(payload).read_bytes()
        code, again, _payload = self.loop("--boundary", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertEqual(again, text)
        self.assertEqual(self.run_path(payload).read_bytes(), file_bytes)


class TestRunFile(_LoopFixtureBase):
    def test_missing_run_file(self):
        for argv in (
            ("--next", "--run", "20200101-000000"),
            ("--boundary", "--run", "20200101-000000"),
            ("--end", "--run", "20200101-000000"),
            ("--status", "--run", "20200101-000000"),
        ):
            with self.subTest(argv=argv):
                code, _text, payload = self.loop(*argv)

                self.assertEqual(code, 2)
                self.assertIn("error", payload)
        self.assertFalse(self.runs_dir.exists())

    def test_corrupt_run_file(self):
        payload = self.init("--mode", "all")
        path = self.run_path(payload)
        path.write_bytes(b'{"schema_version": 1, "queue": [')
        before = path.read_bytes()

        for argv in (
            ("--next", "--run", payload["run"]),
            ("--mark", "--run", payload["run"], "--id", "001", "--phase", "acting"),
            ("--boundary", "--run", payload["run"]),
            ("--end", "--run", payload["run"]),
        ):
            with self.subTest(argv=argv):
                code, _text, error = self.loop(*argv)

                self.assertEqual(code, 2)
                self.assertIn("error", error)
                self.assertEqual(path.read_bytes(), before)

    def test_run_id_collision(self):
        with patch.object(backlog_loop, "run_id_now", return_value=RUN_ID):
            first = self.init("--mode", "all")
            first_bytes = self.run_path(first).read_bytes()
            second = self.init("--mode", "n", "--n", "1")

        self.assertEqual(first["run"], RUN_ID)
        self.assertEqual(second["run"], f"{RUN_ID}-2")
        self.assertTrue((self.runs_dir / f"{RUN_ID}.json").is_file())
        self.assertTrue((self.runs_dir / f"{RUN_ID}-2.json").is_file())
        # The first run file is never overwritten.
        self.assertEqual(self.run_path(first).read_bytes(), first_bytes)


class TestLoadScoredItems(_LoopFixtureBase):
    def test_load_scored_items_characterization(self):
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["backlog_loop", "--config", str(self.config_path)]
        config = score_backlog.load_config(Path(score_backlog.__file__))

        items, frontmatters, scores, open_ids = score_backlog.load_scored_items(config)

        self.assertEqual([item["id"] for item in items], [row[0] for row in FIXTURE_ITEMS])
        self.assertEqual(open_ids, {row[0] for row in FIXTURE_ITEMS})
        self.assertEqual(set(scores), open_ids)
        self.assertEqual(set(frontmatters), open_ids)
        # main() prints these totals; the extraction must return the same ones.
        for item_id in sorted(open_ids):
            with self.subTest(item_id=item_id):
                sys.argv = ["score_backlog", "--config", str(self.config_path), "--id", item_id]
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    score_backlog.main()
                self.assertEqual(out.getvalue().strip(), f"{item_id}  score {scores[item_id].total}")
        self.assertEqual(
            {item_id: scores[item_id].total for item_id in sorted(scores)},
            {"001": 30, "002": 20, "003": 30, "004": 30, "005": 20, "006": 10, "007": 10,
             "008": 10, "009": 10},
        )


if __name__ == "__main__":
    unittest.main()
