#!/usr/bin/env python3
"""Tests for the loop's conservatism controls and its two item-file writers.

  * `--init` splits the Route C exclusion: a strong scope signal keeps the
    `plans deferred in loop mode` reason, the conservative default branch
    gets `needs refine`, and the summary prints one header per reason.
  * `--mark --outcome SKIPPED --needs-plan` writes `needs_plan: true` into the
    item file through `update_backlog.set_frontmatter_key`, the same writer
    `update_backlog.py --mark-needs-plan` uses.
  * `--resolution-file` appends a `## Resolution` section to a closed item,
    from the loop and from `update_backlog.py --status COMPLETE`.
  * `--decision` is capped at 1200 characters, and a skip in a later run
    adds the next `### Q` block under `## Open Questions`.
  * `--mark --outcome` without `--route` records the item's `route_at_init`.

The fixture subclass adds item 010, a conservative-default Route C item, in
its own setUp, so the shared fixture base keeps its literals.

Run with:  python -m pytest tests/test_backlog_loop_gates.py -q
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import backlog_loop
import backlog_questions
import update_backlog
from test_backlog_loop import _LoopFixtureBase, item_filename, item_text

HEADING = "## Loop Decision Needed"
RESOLUTION = "## Resolution"
DECISION = "Question: route A or B?\nOptions: (A) patch, (B) refactor.\nEvidence: the probe found two callers."
RECORD = "Closed 2026-10-21: every acceptance criterion was already met.\n\n1. The helper exists -- MET"
OLD_RUNS = ("20261001-090000", "20261002-090000")


def old_section(run_id: str, eol: str = "\n") -> str:
    """A section in the shape the earlier append-only writer left behind."""
    return eol.join([
        "",
        HEADING,
        "",
        f"<!-- loop-decision run={run_id} -->",
        "> [!gate] User input needed",
        f"> Loop run {run_id}, 2026-10-01. The loop skipped this item without working it.",
        "",
        f"Question from run {run_id}?",
        "",
    ])


class _GatesFixtureBase(_LoopFixtureBase):
    """The shared loop fixture plus item 010, a conservative-default Route C item."""

    def setUp(self):
        super().setUp()
        # 50 filler lines, no numbered list, no keyword: route C, no strong signal.
        self.write_item("010", "NOT_STARTED", "default_c")
        hub = self.backlog_dir / "00-Index-Backlog.md"
        with open(hub, "a", encoding="utf-8", newline="") as handle:
            handle.write(
                f"| 010 | Default C | Low | NOT_STARTED | INFRA | 2026-10-01 | "
                f" | 0 | [01]({item_filename('010')}) |\n"
            )
        self.archive_dir = self.backlog_dir / "Archive"

    def item_file(self, item_id: str) -> Path:
        return self.backlog_dir / item_filename(item_id)

    def pop_and_select(self, run_id: str, item_id: str) -> None:
        """Pop the next item and flip it IN_PROGRESS, as the handler's Phase 2 does."""
        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual((code, popped["next"]), (0, item_id))
        self.write_item(item_id, "IN_PROGRESS", "short")

    def write_resolution(self, text: str = RECORD) -> Path:
        path = self.tmp / "resolution.md"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def update(self, *argv: str) -> tuple[str, str, object]:
        """Run update_backlog.main(); returns (stdout, stderr, exit code or None)."""
        saved = sys.argv
        sys.argv = ["update_backlog", "--config", str(self.config_path), *argv]
        out, err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    update_backlog.main()
                except SystemExit as exc:
                    code = exc.code
        finally:
            sys.argv = saved
        return out.getvalue(), err.getvalue(), code


class TestNeedsRefine(_GatesFixtureBase):
    def test_init_excludes_default_branch_c_with_needs_refine(self):
        payload = self.init("--mode", "all")

        self.assertEqual([q["id"] for q in payload["queue"]], ["001", "002", "006", "007"])
        reasons = {e["id"]: (e["reason"], e["large_scope"]) for e in payload["excluded"]}
        self.assertEqual(reasons["003"], ("plans deferred in loop mode", True))
        self.assertEqual(reasons["010"], ("needs refine", False))
        self.assertEqual(self.read_run(payload)["excluded"][-1]["reason"], "needs refine")

    def test_init_specific_warns_with_the_refine_reason(self):
        # --mode specific refines every named unrefined item, so the two
        # Route C items queue as `refine` and no `needs refine` warning is
        # left; a named needs_plan item still warns with its own reason.
        code, text, payload = self.loop("--init", "--mode", "specific", "--items", "010,003,009,001")

        self.assertEqual(code, 0)
        self.assertEqual([q["id"] for q in payload["queue"]], ["010", "003", "001"])
        self.assertEqual({q["disposition"] for q in payload["queue"]}, {"refine"})
        self.assertEqual(payload["warnings"], ["warning: item 009 dropped: marked for a planning session"])
        self.assertNotIn("needs refine", text)

    def test_summary_groups_excluded_by_reason(self):
        payload = self.init("--mode", "n", "--n", "2")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan")
        self.loop("--next", "--run", run_id)
        resolution = self.write_resolution()
        code, _text, _marked = self.loop(
            "--mark", "--run", run_id, "--id", "002", "--outcome", "COMPLETE",
            "--resolution-file", str(resolution),
        )
        self.assertEqual(code, 0)

        code, text, _payload = self.loop("--end", "--run", run_id)

        self.assertEqual(code, 0)
        lines = text.splitlines()
        deferred = lines.index("Excluded (plans deferred in loop mode):")
        refine = lines.index("Excluded (needs refine):")
        planning = lines.index("Marked for a planning session:")
        unattended = lines.index("Closed unattended (criteria already met; see ## Resolution):")
        self.assertTrue(lines[deferred + 1].startswith("  003 "))
        self.assertTrue(lines[refine + 1].startswith("  010 "))
        self.assertEqual(lines[planning + 1], "  001")
        self.assertEqual(lines[unattended + 1], "  002")
        self.assertLess(max(deferred, refine), planning)
        self.assertLess(planning, unattended)


class TestNeedsPlan(_GatesFixtureBase):
    def test_mark_needs_plan_writes_frontmatter_record_and_note(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")

        code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan",
        )

        self.assertEqual(code, 0)
        self.assertTrue(marked["needs_plan_written"])
        self.assertEqual(marked["restored_status"], "NOT_STARTED")
        frontmatter = self.item_file("001").read_text(encoding="utf-8").split("---")[1]
        self.assertIn("needs_plan: true", frontmatter)
        self.assertIn("status: NOT_STARTED", frontmatter)
        record = self.read_run(payload)["items"]["001"]
        self.assertTrue(record["needs_plan"])
        self.assertEqual(record["note"], "marked for a planning session")
        self.assertEqual(record["outcome"], "SKIPPED")

    def test_needs_plan_requires_skipped(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        before = self.run_path(payload).read_bytes()

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE", "--needs-plan",
        )
        self.assertEqual(code, 1)
        self.assertIn("SKIPPED only", error["error"])
        code, _text, _error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--phase", "acting", "--needs-plan",
        )
        self.assertEqual(code, 1)
        self.assertNotIn("needs_plan", self.item_file("001").read_text(encoding="utf-8"))

        # An item file with no frontmatter: exit 1, nothing recorded.
        self.item_file("001").write_text("# Item 001\n\nNo frontmatter.\n", encoding="utf-8", newline="\n")
        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan",
        )
        self.assertEqual(code, 1)
        self.assertIn("no_frontmatter", error["error"])
        # No item file at all: exit 1, nothing recorded.
        self.item_file("001").unlink()
        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan",
        )
        self.assertEqual(code, 1)
        self.assertIn("--needs-plan could not find the item file for 001", error["error"])
        self.assertEqual(self.run_path(payload).read_bytes(), before)

    def test_update_backlog_mark_needs_plan_cli(self):
        out, err, code = self.update("--id", "007", "--mark-needs-plan")

        self.assertIsNone(code, err)
        self.assertIn("Marked item 007 needs_plan: true (frontmatter only", out)
        text = self.item_file("007").read_text(encoding="utf-8")
        self.assertIn("needs_plan: true", text.split("---")[1])

        _out, _err, code = self.update("--id", "007", "--mark-needs-plan")
        self.assertIsNone(code)
        self.assertEqual(self.item_file("007").read_text(encoding="utf-8").count("needs_plan:"), 1)

        _out, _err, code = self.update("--id", "007", "--mark-needs-plan", "--status", "COMPLETE")
        self.assertEqual(code, 1)
        _out, _err, code = self.update("--id", "999", "--mark-needs-plan")
        self.assertEqual(code, 1)


class TestResolutionFile(_GatesFixtureBase):
    def test_mark_complete_resolution_file_appends_record_and_finds_archived_item(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")
        _out, err, code = self.update("--id", "001", "--status", "COMPLETE")
        self.assertIsNone(code, err)
        archived = self.archive_dir / item_filename("001")
        self.assertTrue(archived.exists())
        self.assertFalse(self.item_file("001").exists())

        code, text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE",
            "--resolution-file", str(self.write_resolution()),
        )

        self.assertEqual(code, 0, marked)
        self.assertTrue(marked["resolution_written"])
        self.assertIn("Resolution: appended", text)
        body = archived.read_text(encoding="utf-8")
        self.assertEqual(body.count(RESOLUTION), 1)
        self.assertIn("every acceptance criterion was already met", body)
        record = self.read_run(payload)["items"]["001"]
        self.assertTrue(record["unattended_close"])
        self.assertTrue(record["resolution_written"])

    def test_resolution_file_appends_dated_block_when_section_exists(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        path = self.item_file("001")
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("\n## Resolution\n\nClosed earlier.\n\n## Notes\n\nKeep this note.\n")
        before = path.read_text(encoding="utf-8")

        code, text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE",
            "--resolution-file", str(self.write_resolution()),
        )

        self.assertEqual(code, 0)
        self.assertTrue(marked["resolution_written"])
        self.assertIn("Resolution: section present, dated close block appended", text)
        body = path.read_text(encoding="utf-8")
        today = backlog_loop.datetime.now().astimezone().date().isoformat()
        # The block sits at the end of the section: after the earlier text,
        # before the next heading, and the section is not repeated.
        self.assertEqual(body.count(RESOLUTION), 1)
        self.assertTrue(body.startswith(before.split("\n## Notes")[0]))
        block = f"### Closed {today}\n\n{RECORD}\n"
        self.assertIn(block, body)
        self.assertLess(body.index("Closed earlier."), body.index(block))
        self.assertLess(body.index(block), body.index("## Notes"))
        self.assertTrue(body.endswith("## Notes\n\nKeep this note.\n"))
        record = self.read_run(payload)["items"]["001"]
        self.assertTrue(record["unattended_close"])
        self.assertTrue(record["resolution_written"])
        # A retry with the same record finds it and writes nothing.
        after = path.read_bytes()
        self.assertEqual(update_backlog.append_resolution_section(path, RECORD).outcome, "exists")
        self.assertEqual(path.read_bytes(), after)

        # A heading inside a fenced block is not a section.
        fenced = self.tmp / "fenced.md"
        with open(fenced, "w", encoding="utf-8", newline="") as handle:
            handle.write("---\nid: 099\n---\n\n```markdown\n## Resolution\n```\n")
        self.assertEqual(update_backlog.append_resolution_section(fenced, RECORD).outcome, "appended")
        self.assertEqual(update_backlog.append_resolution_section(fenced, RECORD).outcome, "exists")

    def test_resolution_substring_of_section_still_appends_block(self):
        path = self.tmp / "substring.md"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("---\nid: 099\n---\n\n## Resolution\n\nDone. The helper moved.\n\n## Notes\n\nDone.\n")

        # "Done." appears inside the section's text but is not that text.
        self.assertEqual(update_backlog.append_resolution_section(path, "Done.").outcome, "closed_block")
        body = path.read_text(encoding="utf-8")
        today = backlog_loop.datetime.now().astimezone().date().isoformat()
        self.assertIn(f"### Closed {today}\n\nDone.\n", body)
        self.assertLess(body.index("### Closed"), body.index("## Notes"))
        # The same record again matches the dated block and writes nothing.
        after = path.read_bytes()
        self.assertEqual(update_backlog.append_resolution_section(path, "Done.").outcome, "exists")
        self.assertEqual(path.read_bytes(), after)

    def test_resolution_file_missing_or_empty_is_usage_error(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)
        before_run = self.run_path(payload).read_bytes()
        before_item = self.item_file("001").read_bytes()
        mark = ("--mark", "--run", run_id, "--id", "001")

        code, _text, error = self.loop(
            *mark, "--outcome", "COMPLETE", "--resolution-file", str(self.tmp / "absent.md"),
        )
        self.assertEqual(code, 1)
        self.assertIn("could not be read", error["error"])
        code, _text, error = self.loop(
            *mark, "--outcome", "COMPLETE", "--resolution-file", str(self.write_resolution("  \n")),
        )
        self.assertEqual(code, 1)
        self.assertIn("empty", error["error"])
        resolution = str(self.write_resolution())
        code, _text, error = self.loop(*mark, "--outcome", "SKIPPED", "--resolution-file", resolution)
        self.assertEqual(code, 1)
        self.assertIn("COMPLETE only", error["error"])
        code, _text, error = self.loop(*mark, "--lessons", "L-1", "--resolution-file", resolution)
        self.assertEqual(code, 1)
        self.assertIn("--lessons stands alone", error["error"])
        code, _text, error = self.loop(*mark, "--lessons", "L-1", "--needs-plan")
        self.assertEqual(code, 1)
        self.assertIn("--lessons stands alone", error["error"])

        self.assertEqual(self.run_path(payload).read_bytes(), before_run)
        self.assertEqual(self.item_file("001").read_bytes(), before_item)

    def test_update_backlog_status_complete_with_resolution_file(self):
        resolution = str(self.write_resolution())
        archived = self.archive_dir / item_filename("007")

        out, err, code = self.update("--id", "007", "--status", "COMPLETE", "--resolution-file", resolution)
        self.assertIsNone(code, err)
        self.assertIn("Resolution: appended", out)
        self.assertEqual(archived.read_text(encoding="utf-8").count(RESOLUTION), 1)

        # A retry after a partial close is idempotent and still reports.
        out, err, code = self.update("--id", "007", "--status", "COMPLETE", "--resolution-file", resolution)
        self.assertIsNone(code, err)
        self.assertIn("already has status COMPLETE. No change.", out)
        self.assertIn("Resolution: section already present, left unchanged", out)
        self.assertEqual(archived.read_text(encoding="utf-8").count(RESOLUTION), 1)

        # An item already COMPLETE with no section gets the record appended.
        self.write_item("006", "COMPLETE", "short")
        out, err, code = self.update("--id", "006", "--status", "COMPLETE", "--resolution-file", resolution)
        self.assertIsNone(code, err)
        self.assertIn("Resolution: appended", out)
        self.assertIn(RESOLUTION, (self.archive_dir / item_filename("006")).read_text(encoding="utf-8"))

        # The flag needs --status COMPLETE.
        _out, _err, code = self.update("--id", "001", "--status", "NOT_STARTED", "--resolution-file", resolution)
        self.assertEqual(code, 1)


class TestDecisionCap(_GatesFixtureBase):
    def selected_run(self) -> tuple[dict, str]:
        payload = self.init("--mode", "all")
        self.pop_and_select(payload["run"], "001")
        return payload, payload["run"]

    def test_decision_at_cap_accepted_and_over_cap_refused(self):
        payload, run_id = self.selected_run()
        head = "Question: which route?\nOptions: (A) patch (B) refactor\nEvidence: "
        at_cap = head + "e" * (1200 - len(head))
        over_cap = at_cap + "e"
        self.assertEqual((len(at_cap), len(over_cap)), (1200, 1201))
        item_before = self.item_file("001").read_bytes()
        run_before = self.run_path(payload).read_bytes()

        code, _text, error = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", over_cap,
        )
        self.assertEqual(code, 1)
        self.assertIn("--decision is 1201 characters; the cap is 1200.", error["error"])
        self.assertEqual(self.item_file("001").read_bytes(), item_before)
        self.assertEqual(self.run_path(payload).read_bytes(), run_before)

        code, _text, marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", at_cap,
        )
        self.assertEqual(code, 0)
        self.assertTrue(marked["decision_written"])

    def test_same_run_repeat_is_noop(self):
        _payload, run_id = self.selected_run()
        args = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION)
        self.loop(*args)
        after_first = self.item_file("001").read_bytes()

        _code, _text, again = self.loop(*args)

        self.assertFalse(again["decision_written"])
        self.assertEqual(self.item_file("001").read_bytes(), after_first)
        self.assertEqual(after_first.count(b"### Q"), 1)

    def test_later_run_adds_the_next_block_and_keeps_crlf(self):
        _payload, run_id = self.selected_run()
        path = self.item_file("001")
        crlf = item_text("001", "IN_PROGRESS", "short").replace("\n", "\r\n")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(crlf)
        # Two earlier runs, each written by the loop's own writer.
        for run in OLD_RUNS:
            backlog_questions.append_question(path, run, f"Question from run {run}?")

        self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--decision", DECISION)

        raw = path.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF entered a CRLF file")
        self.assertNotIn(HEADING.encode(), raw)
        self.assertEqual(raw.count(b"## Open Questions"), 1)
        self.assertIn(f"### Q3. Loop decision (run {run_id})\r\n".encode(), raw)
        self.assertIn(f"Question from run {OLD_RUNS[0]}?\r\n".encode(), raw)

    def test_refused_decision_falls_back_to_note_skip(self):
        payload, run_id = self.selected_run()
        path = self.item_file("001")
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write("\n```bash\npython -m pytest -q\n")
        mark = ("--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED")

        code, _text, error = self.loop(*mark, "--decision", DECISION)
        self.assertEqual(code, 1)
        self.assertIn("Close the fence first", error["error"])
        self.assertIsNone(self.read_run(payload)["items"]["001"]["outcome"])

        # The documented fallback: skip with a short note so the run continues.
        code, _text, _marked = self.loop(*mark, "--note", "decision refused: open fence")
        self.assertEqual(code, 0)
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual((record["outcome"], record["note"]), ("SKIPPED", "decision refused: open fence"))
        self.assertIn("status: NOT_STARTED", path.read_text(encoding="utf-8"))
        code, _text, popped = self.loop("--next", "--run", run_id)
        self.assertEqual(code, 0)
        self.assertIsNotNone(popped["next"])


class TestSetFrontmatterKey(_GatesFixtureBase):
    def test_inserts_before_closing_fence_with_bom_and_crlf(self):
        fixture = b"\xef\xbb\xbf---\r\nid: 099\r\nstatus: NOT_STARTED\r\n---\r\n\r\n# item\r\n"
        path = self.tmp / "bom-crlf.md"
        path.write_bytes(fixture)

        result = update_backlog.set_frontmatter_key(path, "needs_plan", "true")

        self.assertEqual(result.outcome, "changed")
        expected = fixture.replace(b"NOT_STARTED\r\n---", b"NOT_STARTED\r\nneeds_plan: true\r\n---")
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(update_backlog.set_frontmatter_key(path, "needs_plan", "true").outcome, "unchanged")
        self.assertEqual(path.read_bytes(), expected)

    def test_replaces_existing_key(self):
        path = self.tmp / "replace.md"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("---\nid: 099\nneeds_plan: false\nstatus: NOT_STARTED\n---\n\n# item\n")

        result = update_backlog.set_frontmatter_key(path, "needs_plan", "true")

        self.assertEqual(result.outcome, "changed")
        self.assertEqual(
            path.read_bytes(),
            b"---\nid: 099\nneeds_plan: true\nstatus: NOT_STARTED\n---\n\n# item\n",
        )
        missing = self.tmp / "missing.md"
        self.assertEqual(update_backlog.set_frontmatter_key(missing, "needs_plan", "true").outcome, "absent_file")
        bare = self.tmp / "bare.md"
        bare.write_bytes(b"# item\n")
        self.assertEqual(update_backlog.set_frontmatter_key(bare, "needs_plan", "true").outcome, "no_frontmatter")
        self.assertEqual(bare.read_bytes(), b"# item\n")


class TestRouteDefault(_GatesFixtureBase):
    def test_outcome_without_route_records_route_at_init(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, _marked = self.loop("--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE")

        self.assertEqual(code, 0)
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual((record["route_at_init"], record["route"]), ("A", "A"))

    def test_explicit_route_wins_over_route_at_init(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.loop("--next", "--run", run_id)

        code, _text, _marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "COMPLETE", "--route", "B",
        )

        self.assertEqual(code, 0)
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual((record["route_at_init"], record["route"]), ("A", "B"))

    def test_needs_plan_suppresses_route_default(self):
        payload = self.init("--mode", "all")
        run_id = payload["run"]
        self.pop_and_select(run_id, "001")

        code, _text, _marked = self.loop(
            "--mark", "--run", run_id, "--id", "001", "--outcome", "SKIPPED", "--needs-plan",
        )

        self.assertEqual(code, 0)
        record = self.read_run(payload)["items"]["001"]
        self.assertEqual(record["route_at_init"], "A")
        self.assertIsNone(record["route"])


if __name__ == "__main__":
    unittest.main()
