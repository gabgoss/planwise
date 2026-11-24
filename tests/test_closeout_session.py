#!/usr/bin/env python3
"""Tests for scripts/closeout_session.py, the guarded writer for `/planwise run` Phase 4.

Every fixture file is built from the shipped template of the file it stands for
(recovery, orchestration, sprint plan, Master Plan), so the writer is tested
against the shapes the producers emit and not against shapes invented here.
The Master Plan is written CRLF.
"""

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from check_prior_sprint_outputs import resolve_complete_outputs_dirs
from closeout_session import main

TEMPLATES = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "templates"
TODAY = "2026-11-23"
SESSION = "ALP-S01-01"

CONFIG_YAML_FIXTURE = (
    b"project:\n"
    b'  name: "CloseoutFixtureProject"\n'
    b'  plans_dir: "Plans"\n'
    b"plan_statuses:\n"
    b"- NOT_STARTED\n"
    b"- IN_PROGRESS\n"
    b"- BLOCKED\n"
    b"- NEEDS_FIXES\n"
    b"- COMPLETE\n"
)

FLAG_TABLE_HEAD = (
    "|--------|-------------|---------------------|-------------|---------------------|\n"
    "| - | - | - | - | - |"
)


def template_body(name: str) -> str:
    """The fenced markdown block of a shipped template, as LF text."""
    text = (TEMPLATES / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("```markdown\n") + len("```markdown\n")
    return text[start : text.rindex("\n```")] + "\n"


def strip_section(text: str, heading: str) -> str:
    """Remove one `## heading` section, through the line before the next `## ` heading."""
    pattern = re.compile(rf"^## {re.escape(heading)}[^\n]*\n.*?(?=^## )", re.MULTILINE | re.DOTALL)
    stripped, count = pattern.subn("", text, count=1)
    assert count == 1, heading
    return stripped


def fill(text: str, sprint: str, session: str = "01") -> str:
    return (
        text.replace("{ABBREV}", "ALP").replace("{Abbrev}", "ALP").replace("{XX}", sprint).replace("{YY}", session)
    )


def flag_row(number: int, source: str, consumer: str, observation: str = "Keep the order.") -> str:
    return f"| {number} | {source} | {consumer} | {observation} | Route it first. |"


class CloseoutFixture(unittest.TestCase):
    """An isolated planwise tree holding one plan that is built from the shipped templates."""

    flags = (
        flag_row(1, "ALP-S01-01-02", "ALP-S01-02-01"),
        flag_row(2, "ALP-S01-01-03", "ALP-S02-01"),
        flag_row(3, "ALP-S01-01-01", "follow-up plan Beta"),
    )
    keep_carried_forward = False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.planwise = self.root / "planwise"
        self.plans = self.planwise / "Plans"
        self.config = self.planwise / "config.yaml"
        self.planwise.mkdir()
        self.config.write_bytes(CONFIG_YAML_FIXTURE)
        self.build_plan()

    def build_plan(self):
        plan = self.plans / "Alpha"
        self.sprint1 = plan / "Sprint-01-Build"
        self.sprint2 = plan / "Sprint-02-Later"
        self.session1 = self.sprint1 / "Session-01-Core"
        self.session2 = self.sprint1 / "Session-02-Next"
        for folder in (self.session1, self.session2, self.sprint2):
            folder.mkdir(parents=True)

        master = fill(template_body("master-plan.md"), "01")
        master = master.replace(
            "| Sprint-01 | Session-01-{Name} | ⏳ NOT STARTED | - | - |",
            "| Sprint-01 | Session-01-Core | ⏳ NOT STARTED | - | - |\n| Sprint-01 | Session-02-Next | ⏳ NOT STARTED | - | - |",
        )
        if not self.keep_carried_forward:
            master = strip_section(master, "Carried-Forward Coordination Flags")
        self.master = plan / "ALP-Master-Plan.md"
        self.write_crlf(self.master, master)

        sprint = template_body("sprint-plan.md")
        sprint1_text = fill(sprint, "01")
        sprint2_text = fill(sprint, "02")
        if not self.keep_carried_forward:
            sprint1_text = strip_section(sprint1_text, "Carried-Forward Coordination Flags")
            sprint2_text = strip_section(sprint2_text, "Carried-Forward Coordination Flags")
        self.sprint_plan1 = self.sprint1 / "ALP-S01-Sprint-Plan.md"
        self.sprint_plan2 = self.sprint2 / "ALP-S02-Sprint-Plan.md"
        self.sprint_plan1.write_text(sprint1_text, encoding="utf-8", newline="\n")
        self.sprint_plan2.write_text(sprint2_text, encoding="utf-8", newline="\n")

        orchestration = template_body("orchestration.md")
        self.orch1 = self.session1 / "ALP-S01-01-Orchestration.md"
        self.orch2 = self.session2 / "ALP-S01-02-Orchestration.md"
        for path, session in ((self.orch1, "01"), (self.orch2, "02")):
            text = strip_section(fill(orchestration, "01", session), "Pre-Known Cross-Task Coordination Flags")
            path.write_text(text, encoding="utf-8", newline="\n")

        self.recovery = self.session1 / "ALP-S01-01-Recovery.md"
        self.write_recovery(self.flags)

    def write_crlf(self, path: Path, text: str):
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

    def write_recovery(self, rows):
        text = fill(template_body("recovery.md"), "01")
        self.assertIn(FLAG_TABLE_HEAD, text)
        head = FLAG_TABLE_HEAD.split("\n")[0]
        text = text.replace(FLAG_TABLE_HEAD, head + "\n" + "\n".join(rows), 1)
        self.recovery.write_text(text, encoding="utf-8", newline="\n")

    def snapshot(self) -> dict[Path, bytes]:
        return {p: p.read_bytes() for p in sorted(self.plans.rglob("*")) if p.is_file()}

    def run_main(self, *args: str):
        argv = ["closeout_session.py", "--config", str(self.config), "--session", SESSION, "--date", TODAY, *args]
        old_argv = sys.argv
        sys.argv = argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = main()
        finally:
            sys.argv = old_argv
        return code, out.getvalue()

    def apply(self, *args: str):
        return self.run_main("--apply", "--sprint-status", "IN_PROGRESS", "--master-status", "IN_PROGRESS", *args)

    def text(self, path: Path) -> str:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")

    def status(self, path: Path, label: str = "Status") -> str:
        match = re.search(rf"^\*\*{label}:\*\*[ \t]*(\S+)", self.text(path), re.MULTILINE)
        self.assertIsNotNone(match, f"{path.name} has no {label} line")
        return match.group(1)


class TestHelp(CloseoutFixture):
    def test_help_names_the_flags_and_says_a_dry_run_writes_nothing(self):
        out = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["closeout_session.py", "--help"]
        try:
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as raised:
                main()
        finally:
            sys.argv = old_argv
        self.assertEqual(raised.exception.code, 0)
        text = " ".join(out.getvalue().split())
        for flag in ("--config", "--session", "--apply"):
            self.assertIn(flag, text)
        self.assertIn("writes nothing", text)


class TestDryRun(CloseoutFixture):
    def test_dry_run_leaves_every_fixture_byte_unchanged(self):
        before = self.snapshot()
        code, out = self.run_main("--sprint-status", "IN_PROGRESS", "--master-status", "IN_PROGRESS")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("would change", out)
        self.assertNotIn("changed: 0", out)


class TestApply(CloseoutFixture):
    def test_apply_writes_every_surface(self):
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.status(self.recovery, "Session Status"), "COMPLETE")
        self.assertEqual(self.status(self.orch1), "COMPLETE")
        self.assertEqual(self.status(self.sprint_plan1), "IN_PROGRESS")
        self.assertEqual(self.status(self.master), "IN_PROGRESS")

        master = self.text(self.master)
        self.assertIn(
            f"| Sprint-01 | Session-01-Core | ✅ COMPLETE | `Sprint-01-Build/Session-01-Core/Outputs/{SESSION}-Summary.md` | {TODAY} |",
            master,
        )
        self.assertIn("| Sprint-01 | Session-02-Next | ⏳ NOT STARTED | - | - |", master)

    def test_a_flag_for_a_scaffolded_session_lands_in_its_orchestration_file(self):
        self.apply()
        text = self.text(self.orch2)
        self.assertIn("## Pre-Known Cross-Task Coordination Flags", text)
        self.assertEqual(text.count(f"### From {SESSION} — recorded {TODAY}"), 1)
        self.assertIn("| 1 | ALP-S01-01-02 | ALP-S01-02-01 | Keep the order. | Route it first. | pending |", text)
        self.assertNotIn("ALP-S01-01-03", text)
        self.assertNotIn("follow-up plan Beta", text)

    def test_a_flag_for_an_unscaffolded_session_lands_in_its_sprint_plan(self):
        self.apply()
        text = self.text(self.sprint_plan2)
        self.assertIn("## Carried-Forward Coordination Flags", text)
        self.assertIn("| 2 | ALP-S01-01-03 | ALP-S02-01 | Keep the order. | Route it first. |", text)

    def test_a_flag_for_a_follow_up_plan_lands_in_the_master_plan(self):
        self.apply()
        text = self.text(self.master)
        self.assertIn("## Carried-Forward Coordination Flags", text)
        self.assertIn("| 3 | ALP-S01-01-01 | follow-up plan Beta | Keep the order. | Route it first. |", text)

    def test_the_report_names_each_flags_destination(self):
        _, out = self.apply()
        self.assertIn("flag 1 -> ", out)
        self.assertIn("ALP-S01-02-Orchestration.md", out)
        self.assertIn("ALP-S02-Sprint-Plan.md", out)
        self.assertIn("ALP-Master-Plan.md", out)

    def test_the_tracking_row_is_one_the_prior_outputs_guard_reads(self):
        complete_dirs, uncovered = resolve_complete_outputs_dirs(self.plans)
        self.assertEqual((len(complete_dirs), uncovered), (0, 0))
        self.apply()
        complete_dirs, uncovered = resolve_complete_outputs_dirs(self.plans)
        self.assertEqual(uncovered, 0)
        self.assertEqual(list(complete_dirs), [(self.session1 / "Outputs").resolve()])


class TestIdempotent(CloseoutFixture):
    def test_a_second_apply_reports_zero_changes_and_leaves_identical_bytes(self):
        self.apply()
        after_first = self.snapshot()
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.snapshot(), after_first)
        self.assertIn("changed: 0", out)

    def test_a_later_flag_adds_only_its_own_row_to_the_existing_block(self):
        self.apply()
        self.write_recovery((*self.flags, flag_row(4, "ALP-S01-01-02", "ALP-S01-02-02", "A second hand-off.")))
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        text = self.text(self.orch2)
        self.assertEqual(text.count(f"### From {SESSION} — recorded"), 1)
        self.assertEqual(len(re.findall(r"^\| \d+ \| ALP-S01-01-02 \|", text, re.MULTILINE)), 2)
        self.assertIn("| 4 | ALP-S01-01-02 | ALP-S01-02-02 | A second hand-off. | Route it first. | pending |", text)


class TestLineEndings(CloseoutFixture):
    def test_the_crlf_master_plan_reads_zero_bare_lf_after_apply(self):
        self.apply()
        data = self.master.read_bytes()
        crlf = data.count(b"\r\n")
        self.assertGreater(crlf, 0)
        self.assertEqual(data.count(b"\n") - crlf, 0)

    def test_an_lf_file_stays_lf(self):
        self.apply()
        self.assertEqual(self.orch2.read_bytes().count(b"\r"), 0)


class TestRefusals(CloseoutFixture):
    def assert_refused_and_untouched(self, *args: str):
        before = self.snapshot()
        code, out = self.run_main("--apply", *args)
        self.assertEqual(code, 1, out)
        self.assertEqual(self.snapshot(), before, "a refused run must write nothing")
        return out

    def test_a_status_outside_the_vocabulary_exits_nonzero_with_nothing_written(self):
        out = self.assert_refused_and_untouched("--sprint-status", "DONE")
        self.assertIn("plan_statuses", out)

    def test_a_master_status_outside_the_vocabulary_is_refused_too(self):
        self.assert_refused_and_untouched("--master-status", "FINISHED")

    def test_an_unmatched_tracking_row_exits_1_with_nothing_written(self):
        text = self.text(self.master).replace("| Sprint-01 | Session-01-Core |", "| Sprint-09 | Session-01-Core |")
        self.write_crlf(self.master, text)
        out = self.assert_refused_and_untouched()
        self.assertIn("no Session Completion Tracking row", out)

    def test_an_unresolvable_downstream_consumer_exits_1_with_nothing_written(self):
        self.write_recovery((*self.flags, flag_row(4, "ALP-S01-01-02", "somebody")))
        out = self.assert_refused_and_untouched()
        self.assertIn("somebody", out)

    def test_a_consumer_session_with_no_orchestration_and_no_sprint_plan_is_refused(self):
        self.write_recovery((flag_row(1, "ALP-S01-01-02", "ALP-S07-01"),))
        self.assert_refused_and_untouched()

    def test_a_sprint_consumer_whose_sessions_are_scaffolded_is_refused(self):
        self.write_recovery((flag_row(1, "ALP-S01-01-02", "ALP-S01"),))
        out = self.assert_refused_and_untouched()
        self.assertIn("name the session", out)

    def test_a_duplicate_flag_id_is_refused(self):
        self.write_recovery((*self.flags, flag_row(2, "ALP-S01-01-03", "ALP-S02-01")))
        out = self.assert_refused_and_untouched()
        self.assertIn("duplicate", out)

    def test_an_older_list_shaped_block_for_the_same_session_is_refused_not_duplicated(self):
        older = (
            "## Pre-Known Cross-Task Coordination Flags\n\n"
            f"### From {SESSION} (Core) — recorded 2026-10-13\n\n"
            "1. **A hand-written entry.** Consumers: ALP-S01-02-01.\n\n---\n\n"
        )
        text = self.text(self.orch2).replace("## Post-Session Checklist", older + "## Post-Session Checklist", 1)
        self.orch2.write_text(text, encoding="utf-8", newline="\n")
        out = self.assert_refused_and_untouched()
        self.assertIn("no table to append to", out)

    def test_a_missing_recovery_file_is_refused(self):
        self.recovery.unlink()
        code, out = self.run_main("--apply")
        self.assertEqual(code, 1, out)
        self.assertIn("ALP-S01-01-Recovery.md", out)


class TestNoFlags(CloseoutFixture):
    flags = ()

    def test_the_empty_template_flag_table_leaves_every_flag_file_alone(self):
        text = fill(template_body("recovery.md"), "01")
        self.recovery.write_text(text, encoding="utf-8", newline="\n")
        before = self.snapshot()
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        after = self.snapshot()
        for path in (self.orch2, self.sprint_plan2):
            self.assertEqual(after[path], before[path])
        self.assertNotIn("Carried-Forward", self.text(self.master))


class TestExistingSectionIsKept(CloseoutFixture):
    keep_carried_forward = True

    def test_a_block_is_added_beside_the_template_example_block(self):
        code, out = self.apply()
        self.assertEqual(code, 0, out)
        text = self.text(self.sprint_plan2)
        self.assertEqual(text.count("## Carried-Forward Coordination Flags"), 1)
        self.assertIn("### From {source-session-id} — recorded {date}", text)
        self.assertEqual(text.count(f"### From {SESSION} — recorded {TODAY}"), 1)
        again, out = self.apply()
        self.assertEqual((again, self.text(self.sprint_plan2)), (0, text), out)


if __name__ == "__main__":
    unittest.main()
