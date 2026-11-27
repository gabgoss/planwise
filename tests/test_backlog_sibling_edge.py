#!/usr/bin/env python3
"""Pins for the sibling-dependency edge direction in the backlog planner and author.

A sub-item that waits on a sibling is filed with the edge on the prerequisite:
the prerequisite's `blocks:` lists the dependent, never the other way round.
Two groups of tests pin that:

  SiblingEdgeTextPins   the new wording on six shipped plugin files
  SiblingEdgeLoopRun    the backlog loop on a two-sibling result, in two shapes
  BlockerInTheSameRun   a blocked item queues behind a blocker in the same run
  BlockerGateAtNext     `--next` skips an item while one of its blockers is open
  WaitingSection        `--init` lists the blocked items it leaves out of the run

Fixture items (the parent is 020, the siblings are A = 021 and B = 022, B waits for A):

  correct   021 blocks [020, 022], 022 blocks [020]   -> queue 021 then 022
  inverted  021 blocks [020], 022 blocks [020, 021]   -> queue 022 then 021, with a note

The inverted shape is the one the incident items had. The two runs differ, so the
loop test can fail.

Run with:  python -m pytest tests/test_backlog_sibling_edge.py -q
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_loop
import generate_backlog_index
from test_backlog_loop import CONFIG_YAML_FIXTURE, _LoopFixtureBase, item_filename

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# file under the plugin root -> (literals it holds, literals it must not hold)
PINS = {
    "agents/backlog-planner.md": (
        (
            "| {criteria} | {after}",
            "earlier `SUB_ITEMS` line only",
            "for every sub-item that waits on a sibling",
            "unlanded_blockers",
        ),
        ("The parts are independent",),
    ),
    "agents/backlog-preflight.md": (("unlanded_blockers",), ()),
    "agents/backlog-author.md": (
        (
            "File every sub-item first",
            "prerequisite's `blocks:`",
            "Never add the prerequisite to the dependent's own `blocks:`",
        ),
        (),
    ),
    "templates/backlog-item.md": (("B waits for A", "in A's file"), ()),
    "references/backlog-schema.md": (("B waits for A", "in A's file", "unlanded_blockers"), ()),
    "references/backlog-creation-process.md": (("prerequisite sibling", "unlanded_blockers"), ()),
    "handlers/backlog-Part-2-LoopMode.md": (
        ("prerequisite sibling", "unlanded_blockers", "dispatch no author", "first run the Refine step again"),
        (),
    ),
}


class SiblingEdgeTextPins(unittest.TestCase):
    def test_each_file_holds_its_literals(self):
        for rel, (present, absent) in PINS.items():
            text = (PLUGIN / rel).read_text(encoding="utf-8")
            for literal in present:
                with self.subTest(file=rel, holds=literal):
                    self.assertIn(literal, text)
            for literal in absent:
                with self.subTest(file=rel, lacks=literal):
                    self.assertNotIn(literal, text)


class _SiblingFixture(_LoopFixtureBase):
    def add_item(self, item_id: str, blocks: list[str]) -> Path:
        """Write one open item with a `blocks:` line and append its hub row."""
        cell = "[" + ", ".join(blocks) + "]" if blocks else ""
        lines = [
            "---",
            f"id: {item_id}",
            "status: NOT_STARTED",
            f"blocks: {cell or '[]'}",
            "---",
            "",
            f"# Item {item_id}",
            "",
            "A small, well-bounded change to one helper.",
        ]
        path = self.backlog_dir / item_filename(item_id)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        index = self.backlog_dir / "00-Index-Backlog.md"
        row = (
            f"| {item_id} | Fixture {item_id} | Low | NOT_STARTED | INFRA | 2026-10-01 | "
            f"{cell} | 0 | [01]({item_filename(item_id)}) |\n"
        )
        index.write_text(index.read_text(encoding="utf-8") + row, encoding="utf-8")
        return path


class SiblingEdgeLoopRun(_SiblingFixture):
    def run_siblings(self, a_blocks: list[str], b_blocks: list[str]) -> dict:
        self.add_item("020", [])
        self.add_item("021", a_blocks)
        self.add_item("022", b_blocks)
        code, _text, payload = self.loop(
            "--init", "--mode", "specific", "--items", "021,022", "--dry-run"
        )
        self.assertEqual(code, 0, payload)
        return payload

    def test_the_dependent_is_queued_behind_its_prerequisite(self):
        payload = self.run_siblings(["020", "022"], ["020"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["021", "022"])
        self.assertEqual(payload["warnings"], [])

    def test_an_inverted_edge_runs_the_dependent_first_and_says_so(self):
        payload = self.run_siblings(["020"], ["020", "021"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["022", "021"])
        self.assertEqual(
            payload["warnings"],
            [
                (
                    "note: 021 is queued after 022, which you named later. "
                    "If 021 must land first, check the blocks: direction."
                ),
            ],
        )


class DropWarningNamesBlockers(_SiblingFixture):
    """The `--init` drop warning names the open blockers, or says the item is on hold."""

    def run_named(self, items: str) -> dict:
        code, _text, payload = self.loop("--init", "--mode", "specific", "--items", items, "--dry-run")
        self.assertEqual(code, 0, payload)
        return payload

    def test_the_three_items_as_filed_queue_the_blockers_first_and_name_the_direction(self):
        # 728 and 729 each list 727, and 727 lists nothing: the inverted shape.
        self.add_item("727", [])
        self.add_item("728", ["727"])
        self.add_item("729", ["727"])
        payload = self.run_named("727,728,729")
        self.assertEqual([q["id"] for q in payload["queue"]], ["728", "729", "727"])
        self.assertEqual(
            payload["warnings"],
            [
                (
                    "note: 727 is queued after 728, 729, which you named later. "
                    "If 727 must land first, check the blocks: direction."
                ),
            ],
        )

    def test_a_blocker_that_is_not_named_gets_no_direction_note(self):
        self.add_item("020", [])
        self.add_item("021", ["022"])
        self.add_item("022", [])
        payload = self.run_named("020,022")
        self.assertEqual(payload["warnings"], ["warning: item 022 dropped: blocked by 021 (open)"])

    def test_a_held_item_says_on_hold_with_its_status(self):
        path = self.add_item("030", [])
        path.write_text(path.read_text(encoding="utf-8").replace("NOT_STARTED", "BLOCKED"), encoding="utf-8", newline="\n")
        index = self.backlog_dir / "00-Index-Backlog.md"
        text = index.read_text(encoding="utf-8")
        index.write_text(text.replace("| 030 | Fixture 030 | Low | NOT_STARTED", "| 030 | Fixture 030 | Low | BLOCKED"), encoding="utf-8")
        self.add_item("031", [])
        payload = self.run_named("030,031")
        self.assertEqual(payload["warnings"], ["warning: item 030 dropped: on hold (status BLOCKED)"])
        self.assertEqual([q["id"] for q in payload["queue"]], ["031"])


OPEN_QUESTION = (
    "\n## Open Questions\n\n### Q1. Which helper owns the change?\n\n"
    "Options: (A) the reader (B) the writer\n"
    "Recommendation: A. The reader holds the state.\nAnswer:\n"
)


def note_for(item_id: str, blockers: str) -> str:
    return (
        f"note: {item_id} is queued after {blockers}, which you named later. "
        f"If {item_id} must land first, check the blocks: direction."
    )


class BlockerInTheSameRun(_SiblingFixture):
    """`--init` queues a blocked item behind its blockers when every one is in the run."""

    def dry(self, *argv: str) -> dict:
        code, _text, payload = self.loop("--init", *argv, "--dry-run")
        self.assertEqual(code, 0, payload)
        return payload

    def named(self, items: str) -> dict:
        return self.dry("--mode", "specific", "--items", items)

    def ask(self, item_id: str) -> None:
        """Give an item one unanswered question, which keeps it out of every queue."""
        path = self.backlog_dir / item_filename(item_id)
        path.write_text(path.read_text(encoding="utf-8") + OPEN_QUESTION, encoding="utf-8", newline="\n")

    def hold(self, item_id: str) -> None:
        """Put an item on hold in its file and on its hub row."""
        path = self.backlog_dir / item_filename(item_id)
        path.write_text(
            path.read_text(encoding="utf-8").replace("NOT_STARTED", "BLOCKED"), encoding="utf-8", newline="\n"
        )
        index = self.backlog_dir / "00-Index-Backlog.md"
        row = f"| {item_id} | Fixture {item_id} | Low | "
        index.write_text(
            index.read_text(encoding="utf-8").replace(row + "NOT_STARTED", row + "BLOCKED"), encoding="utf-8"
        )

    def test_a_chain_named_backwards_is_written_to_the_run_file(self):
        self.add_item("041", ["042"])
        self.add_item("042", ["043"])
        self.add_item("043", [])

        payload = self.init("--mode", "specific", "--items", "043,042,041")

        self.assertEqual([q["id"] for q in payload["queue"]], ["041", "042", "043"])
        notes = [note_for("043", "042"), note_for("042", "041")]
        self.assertEqual(payload["warnings"], notes)
        run = self.read_run(payload)
        self.assertEqual(run["queue"], ["041", "042", "043"])
        self.assertEqual(run["warnings"], notes)
        self.assertEqual(run["queue_meta"]["042"]["blocked_by_at_init"], ["041"])
        self.assertEqual(run["queue_meta"]["043"]["blocked_by_at_init"], ["042"])
        self.assertNotIn("blocked_by_at_init", run["queue_meta"]["041"])

    def test_the_parent_waits_for_its_sub_items(self):
        # 090 is the parent. 091 and 092 are its sub-items, and 092 waits for 091.
        self.add_item("090", [])
        self.add_item("091", ["090", "092"])
        self.add_item("092", ["090"])

        payload = self.named("090,091,092")

        self.assertEqual([q["id"] for q in payload["queue"]], ["091", "092", "090"])

    def test_a_named_blocker_that_is_dropped_keeps_its_dependant_out(self):
        self.add_item("051", ["052"])
        self.add_item("052", [])
        self.add_item("053", [])
        self.ask("051")

        payload = self.named("051,052,053")

        self.assertEqual([q["id"] for q in payload["queue"]], ["053"])
        self.assertEqual(
            payload["warnings"],
            [
                "warning: item 051 dropped: open questions unanswered",
                "warning: item 052 dropped: blocked by 051 (open)",
            ],
        )

    def test_a_blocker_on_hold_keeps_its_dependant_out(self):
        self.add_item("061", ["062"])
        self.add_item("062", [])
        self.hold("061")

        payload = self.named("061,062,007")

        self.assertEqual([q["id"] for q in payload["queue"]], ["007"])
        self.assertEqual(
            payload["warnings"],
            [
                "warning: item 061 dropped: on hold (status BLOCKED)",
                "warning: item 062 dropped: blocked by 061 (open)",
            ],
        )

    def test_a_dependant_that_fails_its_own_gate_is_dropped_with_that_reason(self):
        self.add_item("051", ["052"])
        self.add_item("052", [])
        self.ask("052")

        payload = self.named("051,052")

        self.assertEqual([q["id"] for q in payload["queue"]], ["051"])
        self.assertEqual(payload["warnings"], ["warning: item 052 dropped: open questions unanswered"])

    def test_mode_all_queues_a_dependant_behind_its_blocker(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])

        ids = [q["id"] for q in self.dry("--mode", "all")["queue"]]

        self.assertIn("072", ids)
        self.assertLess(ids.index("071"), ids.index("072"))
        # 005 waits for 004, which is on hold and so never in a run.
        self.assertNotIn("005", ids)

    def test_mode_n_takes_a_dependant_with_its_blocker_or_not_at_all(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])
        whole = [q["id"] for q in self.dry("--mode", "all")["queue"]]

        for n in range(1, len(whole) + 1):
            with self.subTest(n=n):
                ids = [q["id"] for q in self.dry("--mode", "n", "--n", str(n))["queue"]]
                self.assertLessEqual(len(ids), n)
                if "072" in ids:
                    self.assertLess(ids.index("071"), ids.index("072"))

    def test_the_refine_cap_goes_to_unblocked_items_first(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])

        capped = {q["id"]: q["disposition"] for q in self.dry("--mode", "all", "--refine-max", "1")["queue"]}
        roomy = {q["id"]: q["disposition"] for q in self.dry("--mode", "all", "--refine-max", "50")["queue"]}

        self.assertEqual(list(capped.values()).count("refine"), 1)
        self.assertEqual(capped["072"], "run")
        # With room left over, the dependant takes a refine slot like any other item.
        self.assertEqual(roomy["072"], "refine")


class BlockerGateAtNext(_SiblingFixture):
    """`--next` skips an item while a blocker is open, and reads the blocker's own file."""

    def setUp(self):
        super().setUp()
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.run_payload = self.init("--mode", "specific", "--items", "071,072")
        self.run_id = self.run_payload["run"]

    def pop(self) -> dict:
        code, _text, payload = self.loop("--next", "--run", self.run_id)
        self.assertEqual(code, 0, payload)
        return payload

    def close(self, item_id: str, outcome: str) -> None:
        extra = ("--note", "fixture skip") if outcome == "SKIPPED" else ()
        code, _text, payload = self.loop("--mark", "--run", self.run_id, "--id", item_id, "--outcome", outcome, *extra)
        self.assertEqual(code, 0, payload)

    def item_path(self, item_id: str) -> Path:
        return self.backlog_dir / item_filename(item_id)

    def flip(self, item_id: str, status: str) -> None:
        path = self.item_path(item_id)
        path.write_text(
            path.read_text(encoding="utf-8").replace("status: NOT_STARTED", f"status: {status}"),
            encoding="utf-8",
            newline="\n",
        )

    def archive(self, item_id: str) -> None:
        archive_dir = self.backlog_dir / "Archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.item_path(item_id)), str(archive_dir / item_filename(item_id)))

    def drop_hub_row(self, item_id: str) -> None:
        index = self.backlog_dir / "00-Index-Backlog.md"
        kept = [
            line for line in index.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.startswith(f"| {item_id} |")
        ]
        index.write_text("".join(kept), encoding="utf-8")

    def test_a_skipped_blocker_skips_its_dependant(self):
        self.assertEqual(self.pop()["next"], "071")
        self.close("071", "SKIPPED")

        popped = self.pop()

        self.assertIsNone(popped["next"])
        self.assertEqual(popped["skipped"], ["072"])
        record = self.read_run(self.run_payload)["items"]["072"]
        self.assertEqual((record["outcome"], record["note"]), ("SKIPPED", "blocker-open"))
        self.assertEqual(record["blocked_by"], ["071"])
        # The skip happens before the item is touched, so its file is as it was.
        self.assertIn("status: NOT_STARTED", self.item_path("072").read_text(encoding="utf-8"))

    def test_the_item_file_decides_not_the_run_record(self):
        self.pop()
        # The run file says COMPLETE, and the blocker's own file still says open.
        self.close("071", "COMPLETE")

        self.assertEqual(self.pop()["skipped"], ["072"])

    def test_a_closed_blocker_file_releases_the_dependant_on_a_stale_index(self):
        self.pop()
        self.close("071", "COMPLETE")
        self.flip("071", "COMPLETE")

        popped = self.pop()

        self.assertEqual((popped["next"], popped["skipped"]), ("072", []))

    def test_an_archived_blocker_releases_the_dependant_on_a_stale_index(self):
        self.pop()
        self.close("071", "COMPLETE")
        self.flip("071", "COMPLETE")
        self.archive("071")

        popped = self.pop()

        self.assertEqual((popped["next"], popped["skipped"]), ("072", []))

    def test_an_archived_blocker_releases_the_dependant_on_a_fresh_index(self):
        self.pop()
        self.close("071", "COMPLETE")
        self.flip("071", "COMPLETE")
        self.archive("071")
        self.drop_hub_row("071")

        popped = self.pop()

        self.assertEqual((popped["next"], popped["skipped"]), ("072", []))

    def test_the_summary_names_what_the_skipped_item_waits_for(self):
        self.pop()
        self.close("071", "SKIPPED")
        self.pop()

        code, text, _payload = self.loop("--end", "--run", self.run_id)

        self.assertEqual(code, 0)
        self.assertIn("  blocker-open:", text)
        self.assertIn("    072  (waits for 071)", text)

    def test_a_run_file_from_before_the_new_keys_still_runs(self):
        path = self.run_path(self.run_payload)
        run = json.loads(path.read_text(encoding="utf-8"))
        del run["warnings"]
        for meta in run["queue_meta"].values():
            meta.pop("blocked_by_at_init", None)
        path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")

        self.assertEqual(self.pop()["next"], "071")
        self.close("071", "SKIPPED")
        self.assertEqual(self.pop()["skipped"], ["072"])
        code, _text, _payload = self.loop("--end", "--run", self.run_id)
        self.assertEqual(code, 0)


class BlockerGateSkipsTheWholeChain(_SiblingFixture):
    def test_a_skipped_blocker_skips_every_item_behind_it(self):
        self.add_item("081", ["082"])
        self.add_item("082", ["083"])
        self.add_item("083", [])
        payload = self.init("--mode", "specific", "--items", "081,082,083")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        self.loop("--mark", "--run", run_id, "--id", "081", "--outcome", "SKIPPED", "--note", "fixture skip")

        code, _text, popped = self.loop("--next", "--run", run_id)

        self.assertEqual(code, 0)
        self.assertIsNone(popped["next"])
        self.assertEqual(popped["skipped"], ["082", "083"])
        items = self.read_run(payload)["items"]
        self.assertEqual(items["082"]["blocked_by"], ["081"])
        self.assertEqual(items["083"]["blocked_by"], ["082"])


# The refined sections, in the layout of templates/backlog-item.md.
DESIGN_SECTIONS = (
    "\n## Resolution\n\nChange the one helper.\n\n"
    "1. `a.py` -- change the reader.\n2. `b.py` -- add the test.\n\n"
    "## Verification\n\n```\npython -m pytest -q\n# expect: 0 failed\n```\n"
)


class RefineAheadAtNext(_SiblingFixture):
    """`--next` designs an undesigned dependant while every open blocker is refined."""

    def design(self, item_id: str, *, refined: bool = True) -> None:
        """Write a design on the item; `refined=False` is the decomposed-parent shape."""
        path = self.backlog_dir / item_filename(item_id)
        text = path.read_text(encoding="utf-8")
        if refined:
            text = text.replace("status: NOT_STARTED", "status: NOT_STARTED\nrefined: true", 1)
        path.write_text(text + DESIGN_SECTIONS, encoding="utf-8", newline="\n")

    def skip_each_blocker_then_pop(self, items: str, blockers: tuple[str, ...]) -> dict:
        self.run_payload = self.init("--mode", "specific", "--items", items)
        run_id = self.run_payload["run"]
        for blocker in blockers:
            _code, _text, popped = self.loop("--next", "--run", run_id)
            self.assertEqual(popped["next"], blocker, popped)
            code, _text, payload = self.loop(
                "--mark", "--run", run_id, "--id", blocker, "--outcome", "SKIPPED", "--note", "fixture skip"
            )
            self.assertEqual(code, 0, payload)
        code, _text, payload = self.loop("--next", "--run", run_id)
        self.assertEqual(code, 0, payload)
        return payload

    def assert_blocker_open(self, popped: dict, item_id: str) -> None:
        self.assertIsNone(popped["next"])
        self.assertEqual(popped["skipped"], [item_id])
        self.assertNotIn("unlanded_blockers", popped)
        record = self.read_run(self.run_payload)["items"][item_id]
        self.assertEqual(record["note"], "blocker-open")

    def test_a_dependant_behind_a_refined_blocker_is_popped_to_refine(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.design("071")

        popped = self.skip_each_blocker_then_pop("071,072", ("071",))

        self.assertEqual((popped["next"], popped["disposition"]), ("072", "refine"))
        self.assertEqual(popped["unlanded_blockers"], ["071"])
        record = self.read_run(self.run_payload)["items"]["072"]
        self.assertEqual((record["unlanded_blockers"], record["outcome"]), (["071"], None))

    def test_the_halt_line_repeats_the_unlanded_blockers_for_a_retry(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.design("071")
        self.skip_each_blocker_then_pop("071,072", ("071",))

        code, _text, halted = self.loop("--next", "--run", self.run_payload["run"])

        self.assertEqual((code, halted["item"]), (3, "072"))
        self.assertEqual(halted["unlanded_blockers"], ["071"])

    def test_an_unrefined_blocker_still_skips_its_dependant(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])

        popped = self.skip_each_blocker_then_pop("071,072", ("071",))

        self.assert_blocker_open(popped, "072")

    def test_one_unrefined_blocker_among_refined_ones_skips_the_dependant(self):
        self.add_item("071", ["073"])
        self.add_item("072", ["073"])
        self.add_item("073", [])
        self.design("071")

        popped = self.skip_each_blocker_then_pop("071,072,073", ("071", "072"))

        self.assert_blocker_open(popped, "073")

    def chain(self) -> None:
        """071 blocks 072 and 072 blocks 073."""
        self.add_item("071", ["072"])
        self.add_item("072", ["073"])
        self.add_item("073", [])

    def test_every_open_blocker_up_the_chain_is_listed(self):
        self.chain()
        self.design("071")
        self.design("072")

        popped = self.skip_each_blocker_then_pop("071,072,073", ("071",))

        self.assertEqual((popped["next"], popped["skipped"]), ("073", ["072"]))
        self.assertEqual(popped["unlanded_blockers"], ["072", "071"])

    def test_an_unrefined_blocker_further_up_the_chain_skips_the_dependant(self):
        self.chain()
        self.design("072")

        popped = self.skip_each_blocker_then_pop("071,072,073", ("071",))

        self.assertIsNone(popped["next"])
        self.assertEqual(popped["skipped"], ["072", "073"])

    def test_a_blocker_this_run_worked_and_left_open_skips_its_dependant(self):
        # Its changes may be half in the tree, so nothing is designed on top of them.
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.design("071")
        self.run_payload = self.init("--mode", "specific", "--items", "071,072")
        run_id = self.run_payload["run"]
        self.loop("--next", "--run", run_id)
        self.loop("--mark", "--run", run_id, "--id", "071", "--phase", "acting")
        code, _text, payload = self.loop(
            "--mark", "--run", run_id, "--id", "071", "--outcome", "SKIPPED", "--note", "halted-mid-item"
        )
        self.assertEqual(code, 0, payload)

        code, _text, popped = self.loop("--next", "--run", run_id)

        self.assertEqual(code, 0, popped)
        self.assert_blocker_open(popped, "072")

    def test_a_decomposed_parent_stays_behind_its_refined_sub_items(self):
        # The parent carries a numbered Resolution and no `refined`: a design is on file.
        self.add_item("090", [])
        self.add_item("091", ["090"])
        self.design("090", refined=False)
        self.design("091")

        popped = self.skip_each_blocker_then_pop("091,090", ("091",))

        self.assert_blocker_open(popped, "090")

    def test_an_unrefined_dependant_queued_as_run_keeps_the_skip(self):
        # With no refine cap an unrefined item is queued to run as it is.
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.design("071")
        self.run_payload = self.init("--mode", "all")
        run_id = self.run_payload["run"]
        self.assertEqual(self.read_run(self.run_payload)["queue_meta"]["072"]["disposition_at_init"], "run")

        popped: dict = {"skipped": []}
        while "072" not in popped["skipped"]:
            code, _text, popped = self.loop("--next", "--run", run_id)
            self.assertEqual(code, 0, popped)
            self.assertNotEqual(popped["next"], "072")
            if popped["next"] is not None:
                self.loop(
                    "--mark", "--run", run_id, "--id", popped["next"], "--outcome", "SKIPPED", "--note", "fixture skip"
                )

        self.assertEqual(self.read_run(self.run_payload)["items"]["072"]["note"], "blocker-open")

    def test_a_dependant_queued_as_run_never_runs_while_its_blocker_is_open(self):
        self.add_item("071", ["072"])
        self.add_item("072", [])
        self.design("071")
        self.design("072")

        popped = self.skip_each_blocker_then_pop("071,072", ("071",))

        self.assert_blocker_open(popped, "072")


WAITING_HEADING = "Waiting (a blocker is not in this run):"
# In the base fixture 005 waits for 004, and 004 is on hold, so never in a run.
WAITING_005 = [{"id": "005", "blocked_by": ["004"]}]


class WaitingSection(_SiblingFixture):
    """`--init` names the blocked items it leaves out of a mode `all` or `n` run."""

    def dry(self, *argv: str) -> tuple[str, dict]:
        code, text, payload = self.loop("--init", *argv, "--dry-run")
        self.assertEqual(code, 0, payload)
        return text, payload

    def test_mode_all_lists_the_blocked_item_with_what_it_waits_for(self):
        text, payload = self.dry("--mode", "all")

        self.assertEqual(payload["waiting"], WAITING_005)
        self.assertIn(WAITING_HEADING, text)
        self.assertIn("  005  (waits for 004)", text)

    def test_mode_n_lists_the_same_items(self):
        # 072 waits for 071. Only the limit passes it over, so it gets no record.
        self.add_item("071", ["072"])
        self.add_item("072", [])

        _text, payload = self.dry("--mode", "n", "--n", "1")

        self.assertEqual(payload["waiting"], WAITING_005)
        self.assertNotIn("072", [entry["id"] for entry in payload["queue"]])

    def test_an_item_on_hold_is_not_listed_as_waiting(self):
        _text, payload = self.dry("--mode", "all")

        self.assertNotIn("004", [entry["id"] for entry in payload["waiting"]])
        self.assertNotIn("004", [entry["id"] for entry in payload["queue"]])

    def test_mode_specific_has_no_waiting_key(self):
        text, payload = self.dry("--mode", "specific", "--items", "001,005")

        self.assertEqual(payload["warnings"], ["warning: item 005 dropped: blocked by 004 (open)"])
        self.assertNotIn("waiting", payload)
        self.assertNotIn(WAITING_HEADING, text)

    def test_the_run_file_stores_the_list_and_the_end_summary_repeats_it(self):
        payload = self.init("--mode", "all")

        self.assertEqual(self.read_run(payload)["waiting"], WAITING_005)
        code, text, _payload = self.loop("--end", "--run", payload["run"])
        self.assertEqual(code, 0)
        self.assertIn(WAITING_HEADING, text)
        self.assertIn("  005  (waits for 004)", text)

    def test_a_run_file_from_before_the_key_still_ends(self):
        payload = self.init("--mode", "all")
        path = self.run_path(payload)
        run = json.loads(path.read_text(encoding="utf-8"))
        del run["waiting"]
        path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8", newline="\n")

        code, text, _payload = self.loop("--end", "--run", payload["run"])

        self.assertEqual(code, 0)
        self.assertNotIn(WAITING_HEADING, text)

    def test_a_dependant_that_fails_its_own_gate_is_excluded_not_waiting(self):
        self.add_item("051", ["052"])
        self.add_item("052", [])
        path = self.backlog_dir / item_filename("052")
        path.write_text(path.read_text(encoding="utf-8") + OPEN_QUESTION, encoding="utf-8", newline="\n")

        _text, payload = self.dry("--mode", "all")

        self.assertIn("052", [entry["id"] for entry in payload["excluded"]])
        self.assertNotIn("052", [entry["id"] for entry in payload["waiting"]])


class GeneratedIndexFeedsTheLoop(unittest.TestCase):
    """The loop reads its edges from the hub the real index generator writes.

    The other classes here append a hand-written hub row. This one builds the
    hub with `generate_backlog_index.py --write`, so the Blocks cell has the
    producer's own shape.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backlog_loop_generated_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.backlog_dir = self.tmp / "planwise" / "Backlog"
        (self.backlog_dir / "Archive").mkdir(parents=True)
        self.config_path = self.tmp / "planwise" / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def write_item(self, item_id: str, blocks: list[str]) -> None:
        text = (
            "---\n"
            f"id: {item_id}\n"
            f"title: Fixture {item_id}\n"
            "priority: Low\n"
            "status: NOT_STARTED\n"
            "abbrev: BUG\n"
            "created: 2026-01-01\n"
            f"blocks: [{', '.join(blocks)}]\n"
            "---\n\n"
            f"# Fixture {item_id}\n\n"
            "A small, well-bounded change to one helper.\n"
        )
        path = self.backlog_dir / f"BB-{item_id}-01-BUG-Fixture.md"
        path.write_text(text, encoding="utf-8", newline="\n")

    def test_a_chain_from_a_generated_hub_queues_blocker_first(self):
        self.write_item("101", ["102"])
        self.write_item("102", ["103"])
        self.write_item("103", [])
        sink = io.StringIO()
        sys.argv = ["generate_backlog_index", "--config", str(self.config_path), "--write"]
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            code = generate_backlog_index.main()
        self.assertEqual(code, 0, sink.getvalue())
        hub = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        # The producer wrote the cell; nothing in this test typed it.
        self.assertIn("| [102] |", hub)

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = backlog_loop.main([
                "--config", str(self.config_path),
                "--init", "--mode", "specific", "--items", "103,102,101", "--dry-run",
            ])
        payload = json.loads(out.getvalue().splitlines()[-1])

        self.assertEqual(code, 0, payload)
        self.assertEqual([q["id"] for q in payload["queue"]], ["101", "102", "103"])
        self.assertEqual(payload["queue"][1]["blocked_by"], ["101"])


if __name__ == "__main__":
    unittest.main()
