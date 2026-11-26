#!/usr/bin/env python3
"""Tests for the `feedback` branch of scripts/skill_preflight.py.

The router runs as a subprocess, as the skill runs it, with `cwd` set to a temp
fixture root. The fixture holds a config and model drafts that the real
`feedback_post.py card` reads. Nothing here reaches the real `gh`, and nothing
reads or writes the live project.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_skill_preflight_feedback.py
"""

import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "plugins" / "planwise" / "scripts"
SCRIPT = SCRIPTS_DIR / "skill_preflight.py"
SKILL_MD = REPO_DIR / "plugins" / "planwise" / "skills" / "planwise" / "SKILL.md"

sys.path.insert(0, str(SCRIPTS_DIR))

import skill_preflight

BEGIN = "<!-- planwise:feedback:begin -->"
END = "<!-- planwise:feedback:end -->"
FALLBACK = "PLANWISE_FEEDBACK_FALLBACK:"
CONFIG_YAML = 'project:\n  name: "FeedbackPreflightFixture"\n  planwise_root: "planwise"\n'
SIZE_LIMIT = 30000


def _stamp(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_draft(folder: Path, number: int, kind: str, title: str, body: str, days_ago: int = 1) -> Path:
    created = _stamp(days_ago)
    name = f"{created[:10]}-draft-{kind}-{title.lower().replace(' ', '-')}-{number}.md"
    text = (
        "---\n"
        f"draft_id: d-{number:04d}\n"
        f"created_at: {created}\n"
        "drafted_by: model\n"
        f"kind: {kind}\n"
        f'title: "{title}"\n'
        "status: queued\n"
        "---\n"
        f"{body}\n"
    )
    path = folder / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _hash_tree(folder: Path) -> dict[str, str]:
    """A sha256 of the bytes of every file under the folder, keyed by relative path."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


def run_router(args, cwd):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd),
        timeout=120,
        check=False,
    )


class FeedbackFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fbpre-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "planwise").mkdir()
        (self.root / "planwise" / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        self.folder = self.root / "planwise" / "Feedback" / "Feedback-Drafts"
        self.folder.mkdir(parents=True)

    def queue_three(self):
        _write_draft(self.folder, 1, "bug", "List skips a queued draft", "### What happened\n\nThe list command skipped a draft.")
        _write_draft(self.folder, 2, "lesson", "Name the key the class uses", "### Lesson\n\nCount by the key citers use.", days_ago=5)
        _write_draft(self.folder, 3, "idea", "Preview the card body", "### Idea\n\nShow the body in the card.", days_ago=0)


class TestFeedbackBlock(FeedbackFixture):
    def test_markers_fields_and_next_lines(self):
        self.queue_three()
        proc = run_router(["feedback"], self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        lines = out.splitlines()
        self.assertEqual(lines[0], BEGIN)
        self.assertEqual(lines[-1], END)
        self.assertEqual(out.count(BEGIN), 1)
        self.assertEqual(out.count(END), 1)
        self.assertNotIn(FALLBACK, out)
        # The card's fields, computed by the real producer in this run.
        self.assertRegex(out, r"Queued drafts \(3\) in ")
        self.assertIn("Posting state: absent", out)
        for draft_id in ("d-0001", "d-0002", "d-0003"):
            self.assertRegex(out, rf"(?m)^{draft_id}\t")
            self.assertIn(f"--- draft {draft_id}: ", out)
        self.assertIn("The list command skipped a draft.", out)
        self.assertIn("Count by the key citers use.", out)
        self.assertIn("Show the body in the card.", out)
        # The NEXT block names the computed count, ids and state, and each branch.
        next_at = lines.index("NEXT:")
        nxt = "\n".join(lines[next_at:])
        # Ids appear in the card's own row order, which is file-name order.
        self.assertIn("the card listed 3 queued draft(s) (d-0002, d-0001, d-0003)", nxt)
        self.assertIn("posting state (absent)", nxt)
        self.assertIn("`--post <id>`", nxt)
        self.assertIn("If the id is not one of d-0002, d-0001, d-0003, say that no queued draft has that id and stop.", nxt)
        self.assertIn("`--drafts` without `--all`: ask the user one question per queued draft, for 3 question(s)", nxt)
        self.assertIn("any other `feedback` form, `--drafts --all` included: ignore this block and follow the feedback handler", nxt)
        for forbidden in ("Do not Read the feedback handler", "Do not run `list`", "Do not Read a draft file", "Do not run `promote`", "Do not call `gh`"):
            self.assertIn(forbidden, nxt)
        # The block names each card-route command with the scripts folder and the config path resolved.
        self.assertIn(f'"{SCRIPTS_DIR / "feedback_post.py"}" post --config "', nxt)
        self.assertIn(f'"{SCRIPTS_DIR / "feedback_drafts.py"}" discard <id> --config "', nxt)
        self.assertIn("enable-posting", nxt)  # the fixture's posting state is absent
        self.assertIn("**Post**, **Discard** and **Keep**", nxt)
        config_value = re.search(r'feedback_post\.py" post --config "([^"]+)"', nxt)
        self.assertIsNotNone(config_value, nxt)
        self.assertTrue(Path(config_value.group(1)).samefile(self.root / "planwise" / "config.yaml"))

    def test_enabled_state_names_no_enable_step(self):
        nxt = "\n".join(skill_preflight.feedback_next_lines(1, ["d-0001"], "enabled", SCRIPTS_DIR, Path("cfg/config.yaml")))
        self.assertNotIn("enable-posting", nxt)
        self.assertNotIn("Posting state is", nxt)
        self.assertIn(f'"{SCRIPTS_DIR / "feedback_post.py"}" post --config "{Path("cfg/config.yaml")}"', nxt)
        self.assertIn(f'"{SCRIPTS_DIR / "feedback_drafts.py"}" discard <id> --config "{Path("cfg/config.yaml")}"', nxt)

    def test_post_and_drafts_tokens_print_the_same_block(self):
        self.queue_three()
        plain = run_router(["feedback"], self.root).stdout
        self.assertEqual(run_router(["feedback", "--post", "d-0002"], self.root).stdout, plain)
        self.assertEqual(run_router(["feedback", "--drafts"], self.root).stdout, plain)

    def test_empty_queue_prints_nothing(self):
        proc = run_router(["feedback"], self.root)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_only_an_expired_draft_prints_nothing(self):
        _write_draft(self.folder, 9, "bug", "Old draft", "### What happened\n\nOld.", days_ago=45)
        proc = run_router(["feedback"], self.root)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_missing_config_prints_one_fallback_line_and_the_end_marker(self):
        empty = self.root / "empty"
        empty.mkdir()
        proc = run_router(["feedback"], empty)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], BEGIN)
        self.assertEqual(lines[-1], END)
        fallback = [ln for ln in lines if ln.startswith(FALLBACK)]
        self.assertEqual(len(fallback), 1)
        self.assertIn("config.yaml not found", fallback[0])
        self.assertNotIn("NEXT:", proc.stdout)

    def test_nonzero_card_exit_prints_the_fallback_line(self):
        fake = SimpleNamespace(returncode=2, stdout="No queued draft with id x.\n", stderr="")
        with mock.patch.object(skill_preflight.subprocess, "run", return_value=fake):
            block = skill_preflight.feedback_block(self.root)
        self.assertEqual(len(block), 3)
        self.assertEqual((block[0], block[2]), (BEGIN, END))
        self.assertTrue(block[1].startswith(FALLBACK))
        self.assertIn("exited 2", block[1])

    def test_card_failure_on_unreadable_folder_prints_the_fallback_line(self):
        fake = SimpleNamespace(returncode=1, stdout="", stderr="cannot read drafts folder\n")
        with mock.patch.object(skill_preflight.subprocess, "run", return_value=fake):
            block = skill_preflight.feedback_block(self.root)
        self.assertTrue(block[1].startswith(FALLBACK))
        self.assertIn("exited 1", block[1])

    def test_unrecognised_card_output_prints_the_fallback_line(self):
        fake = SimpleNamespace(returncode=0, stdout="something else\n", stderr="")
        with mock.patch.object(skill_preflight.subprocess, "run", return_value=fake):
            block = skill_preflight.feedback_block(self.root)
        self.assertTrue(block[1].startswith(FALLBACK))

    def test_the_branch_writes_no_file_and_changes_no_byte(self):
        self.queue_three()
        _write_draft(self.folder, 8, "bug", "Expired draft", "### What happened\n\nOld.", days_ago=45)
        before = _hash_tree(self.folder)
        config_before = (self.root / "planwise" / "config.yaml").read_bytes()
        self.assertEqual(len(before), 4)
        for args in (["feedback"], ["feedback", "--post", "d-0001"], ["feedback", "--drafts"]):
            run_router(args, self.root)
        self.assertEqual(_hash_tree(self.folder), before)
        self.assertEqual((self.root / "planwise" / "config.yaml").read_bytes(), config_before)
        # The expired draft stays on disk and is not listed.
        self.assertNotIn("d-0008", run_router(["feedback"], self.root).stdout)

    def test_ten_realistic_drafts_stay_under_the_size_limit(self):
        paragraph = (
            "The preflight printed the list of plans, and the model then ran the list command a second time to "
            "check which drafts were queued. That repeated a call the block had already answered. "
        )
        for number in range(1, 11):
            body = "### What happened\n\n" + paragraph * 4 + "\n\n### What I expected\n\n" + paragraph * 2
            _write_draft(self.folder, number, "bug", f"Realistic draft number {number}", body, days_ago=number)
        out = run_router(["feedback"], self.root).stdout
        self.assertIn("Queued drafts (10) in ", out)
        print(f"ten drafts: {len(out)} characters")
        self.assertGreater(len(out), 5000)
        self.assertLess(len(out), SIZE_LIMIT)


HANDLER_MD = REPO_DIR / "plugins" / "planwise" / "handlers" / "feedback.md"
PART2_MD = REPO_DIR / "plugins" / "planwise" / "references" / "feedback-submission-Part-2-LocalDraftPipelines.md"

# Each "done" claim of the NEXT block, mapped to the card field that answers it and to
# the call the fallback route makes for the same fact.
DONE_CLAIMS = {
    "the card listed": ("Queued drafts (", "list --json"),
    "read the posting state": ("Posting state:", "posting-state --config"),
    "printed each queued draft's body": ("--- draft ", "body below its frontmatter"),
}
# Each "do not" item of the NEXT block, mapped to the text that names that call. The card
# route must never name it.
DO_NOT_CALLS = {
    "Read the feedback handler on the `--post` and `--drafts` branches": "handlers/feedback.md",
    "run `list`": "`list",
    "Read a draft file": "Read the draft",
    "run `promote`": "promote",
    "call `gh`": "`gh issue",
}
# The config path the NEXT block is built with, and each command the Part 2 card route
# names, keyed by a marker its backticked span holds and mapped to its script (None when
# the span names no script).
CONFIG = Path("fixture/planwise/config.yaml")
CARD_ROUTE_COMMANDS = {
    'feedback_post.py" post': "feedback_post.py",
    'feedback_drafts.py" discard': "feedback_drafts.py",
    "enable-posting --config": None,
}


def _section(text: str, heading: str) -> str:
    """The body under one heading, up to the next heading of the same or a higher level."""
    text = text.replace("\r\n", "\n")
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index("\n" + heading + "\n") + len(heading) + 2
    stop = re.search(rf"(?m)^#{{1,{level}}} ", text[start:])
    return text[start : start + stop.start()] if stop else text[start:]


class TestNextBlockMatchesTheCardRoute(unittest.TestCase):
    """The NEXT block's claims hold against the card route the handler and Part 2 describe."""

    def setUp(self):
        self.next_lines = skill_preflight.feedback_next_lines(2, ["d-0002", "d-0001"], "absent", SCRIPTS_DIR, CONFIG)
        handler = HANDLER_MD.read_text(encoding="utf-8")
        part2 = PART2_MD.read_text(encoding="utf-8")
        self.handler_route = _section(handler, "#### Card Route for `--drafts` and `--post`")
        self.part2_route = _section(part2, "#### Card Route")
        self.fallback = _section(part2, "#### Fallback: Without the Preflight Block") + _section(part2, "### Listing")

    def test_each_done_claim_names_a_step_the_card_fields_make_unnecessary(self):
        done = next(ln for ln in self.next_lines if ln.startswith("- Done by this block:"))
        claims = [c for c in DONE_CLAIMS if c in done]
        self.assertEqual(len(claims), len(DONE_CLAIMS), f"a done claim is unmapped or gone: {done}")
        for claim, (field, replaced_call) in DONE_CLAIMS.items():
            with self.subTest(claim=claim):
                # The card route reads the field, and the fallback makes the call it replaces.
                self.assertIn(field, self.handler_route + self.part2_route)
                self.assertIn(replaced_call, self.fallback)
                self.assertNotIn(replaced_call, self.handler_route + self.part2_route)

    def test_each_do_not_item_names_a_call_the_card_route_never_needs(self):
        do_not = next(ln for ln in self.next_lines if ln.startswith("- Do not"))
        items = re.findall(r"Do not ([^.]+)\.", do_not)
        self.assertEqual(sorted(items), sorted(DO_NOT_CALLS), "a do-not item is unmapped or gone")
        for item, call in DO_NOT_CALLS.items():
            with self.subTest(item=item):
                self.assertNotIn(call, self.handler_route)
                self.assertNotIn(call, self.part2_route)

    def test_drafts_all_follows_the_handler_and_no_card_branch_takes_it(self):
        branches = [ln for ln in self.next_lines if ln.startswith("  - ")]
        handler_branch = [ln for ln in branches if "follow the feedback handler" in ln]
        self.assertEqual(len(handler_branch), 1)
        self.assertIn("`--drafts --all`", handler_branch[0])
        # Every line that sends `--drafts` to the card excludes `--all`.
        card_drafts = [ln for ln in self.next_lines if "--drafts" in ln and ln not in handler_branch and ln.startswith("  - ")]
        self.assertEqual(len(card_drafts), 1)
        self.assertIn("`--drafts` without `--all`", card_drafts[0])
        for line in self.next_lines:
            if line not in handler_branch:
                with self.subTest(line=line[:40]):
                    self.assertNotIn("--drafts --all", line)
        # The handler and Part 2 agree: `--drafts --all` takes the engine route.
        self.assertIn("`--drafts` without `--all`", self.handler_route)
        self.assertIn("`--drafts --all` take the engine route", self.handler_route)
        self.assertIn("`--drafts` without `--all`", self.part2_route)

    def test_the_card_route_makes_one_call_per_answer(self):
        for route in (self.handler_route, self.part2_route):
            with self.subTest(route=route[:40]):
                self.assertIn("feedback_post.py", route)
                self.assertIn("discard", route)
                self.assertIn("ARGUMENTS:", route)
                self.assertIn("PLANWISE_FEEDBACK_FALLBACK:", route)
                self.assertIn("**Keep**", route)

    def test_next_block_commands_match_the_card_route(self):
        joined = "\n".join(self.next_lines)
        spans = re.findall(r"`([^`\n]+)`", self.part2_route)
        found_total = 0
        for marker, script in CARD_ROUTE_COMMANDS.items():
            with self.subTest(command=marker):
                found = [s for s in spans if marker in s]
                # Exactly one span per command, so a Part 2 rewording fails here instead of matching nothing.
                self.assertEqual(len(found), 1, f"Part 2 card route spans holding {marker!r}: {found}")
                found_total += 1
                tail = found[0].split(f'{script}" ', 1)[1] if script else found[0]
                tail = tail.replace('"{planwise_root}/config.yaml"', f'"{CONFIG}"').replace("{draft_id}", "<id>")
                self.assertIn(tail, joined)
                if script:
                    self.assertIn(f'"{SCRIPTS_DIR / script}" ' + tail, joined)
        self.assertEqual(found_total, len(CARD_ROUTE_COMMANDS))


class TestSkillWiringUnchanged(unittest.TestCase):
    def setUp(self):
        self.text = SKILL_MD.read_text(encoding="utf-8")

    def test_arguments_still_declares_only_sub(self):
        self.assertRegex(self.text, r"(?m)^arguments: sub\r?$")

    def test_the_bang_line_still_passes_only_the_subcommand(self):
        bang = [ln for ln in self.text.splitlines() if ln.startswith("!`")]
        self.assertEqual(len(bang), 1)
        self.assertEqual(re.findall(r"'\$([A-Za-z_]\w*)'", bang[0]), ["sub"])

    def test_feedback_rule_and_routing_row_exist(self):
        self.assertIn("\n## Feedback\n", self.text.replace("\r\n", "\n"))
        self.assertIn("<!-- planwise:feedback:begin -->", self.text)
        self.assertIn("PLANWISE_FEEDBACK_FALLBACK:", self.text)
        row = next(ln for ln in self.text.splitlines() if ln.startswith("| `feedback` |"))
        self.assertIn("(#feedback)", row)


if __name__ == "__main__":
    unittest.main()
