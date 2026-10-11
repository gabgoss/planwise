#!/usr/bin/env python3
"""Unit tests for flip_plan_status.py, the guarded writer for a Master Plan's
`**Status:**` token.

The load-bearing property is the REFUSALS and the byte discipline: only the
token span moves, the trailing prose / leading emoji / line endings stay, and
every flip is read back through `parse_plans.normalize_status` so the writer
and the reader agree.

Every fixture is built with `write_bytes`, never `write_text`, so CRLF survives.

Run with:  python -m pytest tests/test_flip_plan_status.py -q
"""

import contextlib
import datetime
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from flip_plan_status import main, parse_map
from parse_plans import normalize_status, read_master_plan_fields

CONFIG_YAML_FIXTURE = (
    b'project:\n'
    b'  name: "FlipPlanStatusFixtureProject"\n'
    b'  plans_dir: "Plans"\n'
    b'plan_statuses:\n'
    b'- NOT_STARTED\n'
    b'- IN_PROGRESS\n'
    b'- BLOCKED\n'
    b'- NEEDS_FIXES\n'
    b'- COMPLETE\n'
)

TODAY = datetime.datetime.now().astimezone().date().isoformat()


class FlipPlanStatusTestCase(unittest.TestCase):
    """Base fixture: an isolated temp planwise tree (config.yaml + Plans/)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.planwise_dir = self.tmp_path / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_bytes(CONFIG_YAML_FIXTURE)

    def write_plan(
        self, name: str, status_value: str, *, crlf: bool = False, header: bool = True,
        footer: bool = True, filename: str | None = None, dated: bool = True,
    ) -> Path:
        """Write one Master Plan fixture byte-for-byte."""
        directory = self.plans_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        text = f"# {name} Master Plan\n\n**Status:** {status_value}\n**Created:** 2026-01-01\n"
        if header:
            text += "**Last Updated:** 2026-01-02\n"
        text += "\nBody paragraph that must not change.\n"
        if footer:
            text += "\n---\n\n*Last Updated: 2026-01-03*\n"
        if not dated:
            text = text.replace("2026-01-02", "soon").replace("2026-01-03", "soon")
        if crlf:
            text = text.replace("\n", "\r\n")
        path = directory / (filename or f"{name}-Master-Plan.md")
        path.write_bytes(text.encode("utf-8"))
        return path

    def make_dir_link(self, link: Path, target: Path) -> None:
        """Make `link` a directory symlink, else a Windows junction (which needs no privilege)."""
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except (OSError, NotImplementedError):
            pass
        made = (subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                               capture_output=True, check=False) if os.name == "nt" else None)
        if made is None or made.returncode != 0:
            self.skipTest("neither a symlink nor a junction can be made here")

    def _write_map(self, content: str) -> Path:
        path = self.tmp_path / "map.txt"
        path.write_bytes(content.encode("utf-8"))
        return path

    def _argv(self, map_path: Path, *extra: str) -> list[str]:
        return ["--config", str(self.config_path), str(map_path), *extra]

    def _run_main(self, argv: list[str]):
        """Invoke main() with an injected sys.argv, capturing stdout."""
        old_argv = sys.argv
        sys.argv = ["flip_plan_status.py"] + argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = main()
        finally:
            sys.argv = old_argv
        return code, out.getvalue()

    def flip(self, plan: str, want: str, *extra: str):
        return self._run_main(self._argv(self._write_map(f"{plan}/: {want}\n"), *extra))

    def assert_reader_agrees(self, path: Path, want: str):
        self.assertEqual(read_master_plan_fields(path).status_token, want)
        self.assertEqual(normalize_status(read_master_plan_fields(path).status_raw), want)


class TestTrailingProsePreserved(FlipPlanStatusTestCase):
    def test_only_the_token_changes(self):
        path = self.write_plan("Alpha", "NEEDS_REDESIGN — long narrative, commit abc1234 (2026-03-04).")
        before = path.read_bytes().decode("utf-8")

        code, _ = self.flip("Alpha", "NEEDS_FIXES")

        self.assertEqual(code, 0)
        after = path.read_bytes().decode("utf-8")
        self.assertIn("**Status:** NEEDS_FIXES — long narrative, commit abc1234 (2026-03-04).\n", after)
        self.assertIn("Body paragraph that must not change.", after)
        self.assertEqual(len(before.splitlines()), len(after.splitlines()))
        self.assert_reader_agrees(path, "NEEDS_FIXES")


class TestIdempotentSkip(FlipPlanStatusTestCase):
    def test_already_at_target_is_unchanged_and_not_rewritten(self):
        path = self.write_plan("Alpha", "COMPLETE — done")
        before = path.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)
        self.assertNotIn("regenerate the index", out)
        self.assertEqual(path.read_bytes(), before)


class TestUnmatchedPath(FlipPlanStatusTestCase):
    def test_unknown_path_is_refused(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        code, out = self.flip("Missing", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("no Master Plan", out)
        self.assertEqual(path.read_bytes(), before)


class TestAmbiguousPath(FlipPlanStatusTestCase):
    def test_two_plans_for_one_path_is_refused(self):
        one = self.write_plan("Alpha", "IN_PROGRESS")
        two = self.write_plan("Alpha", "IN_PROGRESS", filename="Beta-Master-Plan.md")
        before = (one.read_bytes(), two.read_bytes())

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("2 Master Plans", out)
        self.assertEqual((one.read_bytes(), two.read_bytes()), before)


class TestInvalidStatus(FlipPlanStatusTestCase):
    def test_value_outside_plan_statuses_is_refused(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        code, out = self.flip("Alpha", "FINISHED")

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("plan_statuses", out)
        self.assertEqual(path.read_bytes(), before)


class TestLineEndingsPreserved(FlipPlanStatusTestCase):
    def test_crlf_in_crlf_out(self):
        path = self.write_plan("Alpha", "IN_PROGRESS — prose", crlf=True)
        before = path.read_bytes()

        code, _ = self.flip("Alpha", "BLOCKED")

        self.assertEqual(code, 0)
        after = path.read_bytes()
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"), "no bare LF may appear")
        self.assertIn(b"**Status:** BLOCKED \xe2\x80\x94 prose\r\n", after)
        self.assert_reader_agrees(path, "BLOCKED")

    def test_lf_stays_lf(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")

        self.flip("Alpha", "BLOCKED")

        self.assertNotIn(b"\r", path.read_bytes())


class TestUnknownFlagRefused(FlipPlanStatusTestCase):
    def test_misspelled_dry_run_is_not_swallowed(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        for flag in ("--dryrun", "--dry"):
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    self.flip("Alpha", "COMPLETE", flag)
                self.assertNotEqual(ctx.exception.code, 0)
            self.assertEqual(path.read_bytes(), before)


class TestDryRun(FlipPlanStatusTestCase):
    def test_nothing_is_written(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE", "--dry-run")

        self.assertEqual(code, 0)
        self.assertIn("would change: 1", out)
        self.assertNotIn("regenerate the index", out)
        self.assertEqual(path.read_bytes(), before)


class TestRegenerateCommandPrinted(FlipPlanStatusTestCase):
    def test_hint_printed_after_a_real_change(self):
        self.write_plan("Alpha", "IN_PROGRESS")

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("regenerate the index: python ", out)
        self.assertIn("generate_plans_index.py", out)
        self.assertIn(f'--config "{self.config_path}" --write', out)


class TestLastUpdatedBumped(FlipPlanStatusTestCase):
    def test_footer_wins_over_header(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")

        self.flip("Alpha", "COMPLETE")

        text = path.read_bytes().decode("utf-8")
        self.assertIn(f"*Last Updated: {TODAY}*", text)
        self.assertIn("**Last Updated:** 2026-01-02", text)
        self.assertEqual(read_master_plan_fields(path).last_updated, TODAY)

    def test_header_used_when_no_footer(self):
        path = self.write_plan("Alpha", "IN_PROGRESS", footer=False)

        self.flip("Alpha", "COMPLETE")

        self.assertIn(f"**Last Updated:** {TODAY}", path.read_bytes().decode("utf-8"))
        self.assertEqual(read_master_plan_fields(path).last_updated, TODAY)

    def test_no_dated_line_leaves_dates_alone_and_says_so(self):
        path = self.write_plan("Alpha", "IN_PROGRESS", header=False, footer=False)

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("dates left alone", out)
        self.assertNotIn(TODAY, path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "COMPLETE")


class TestTitleCaseValueReplaced(FlipPlanStatusTestCase):
    def test_title_case_becomes_upper_case(self):
        path = self.write_plan("Alpha", "Complete — x")

        code, _ = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("**Status:** COMPLETE — x\n", path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "COMPLETE")

    def test_mixed_case_run_is_replaced_whole(self):
        path = self.write_plan("Alpha", "ON_hold since March")

        self.flip("Alpha", "BLOCKED")

        self.assertIn("**Status:** BLOCKED since March\n", path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "BLOCKED")


class TestEmojiPrefixKept(FlipPlanStatusTestCase):
    def test_leading_emoji_stays(self):
        path = self.write_plan("Alpha", "✅ IN_PROGRESS — prose")

        code, _ = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("**Status:** ✅ COMPLETE — prose\n", path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "COMPLETE")

    def test_bold_wrapper_and_trailing_underscores_are_kept(self):
        # The writer replaces the run without its trailing underscores, so the
        # closing italic underscore stays; the reader strips it either way.
        path = self.write_plan("Alpha", "**IN_PROGRESS_** now")

        self.flip("Alpha", "COMPLETE")

        self.assertIn("**Status:** **COMPLETE_** now\n", path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "COMPLETE")


class TestMultiWordValueRefused(FlipPlanStatusTestCase):
    def test_in_progress_with_a_space_is_refused(self):
        path = self.write_plan("Alpha", "IN PROGRESS")
        before = path.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("multi-word", out)
        self.assertEqual(path.read_bytes(), before)

    def test_value_with_no_token_is_refused(self):
        path = self.write_plan("Alpha", "✅")
        before = path.read_bytes()

        code, _ = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertEqual(path.read_bytes(), before)


class TestMixedMapContinuesAfterRefusal(FlipPlanStatusTestCase):
    def test_good_entry_still_flips_when_another_is_refused(self):
        good = self.write_plan("Alpha", "IN_PROGRESS")
        map_file = self._write_map("# comment\nMissing/: COMPLETE\n\nAlpha: COMPLETE  # no trailing slash\n")

        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertIn("Alpha/: IN_PROGRESS -> COMPLETE", out)
        self.assert_reader_agrees(good, "COMPLETE")


class TestSpanContinuationRule(FlipPlanStatusTestCase):
    """Only end-of-value, or whitespace then a non-alphanumeric, may follow the span."""

    REFUSED = ("Not started", "IN-PROGRESS", "IN  PROGRESS", "In review", "IN_PROGRESS/x", "COMPLETE.x")
    KEPT = (" — x", " (shipped)", " - note", " [x]", " : x", " , x", " – x")

    def test_corrupting_values_are_refused_with_bytes_unchanged(self):
        for value in self.REFUSED:
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)
                before = path.read_bytes()

                code, out = self.flip("Alpha", "BLOCKED")

                self.assertEqual(code, 1)
                self.assertIn("REFUSED", out)
                self.assertEqual(path.read_bytes(), before)

    def test_non_alphanumeric_continuations_are_kept_as_prose(self):
        for suffix in self.KEPT:
            with self.subTest(suffix=suffix):
                path = self.write_plan("Alpha", f"IN_PROGRESS{suffix}")

                code, _ = self.flip("Alpha", "COMPLETE")

                self.assertEqual(code, 0)
                self.assertIn(f"**Status:** COMPLETE{suffix}\n", path.read_bytes().decode("utf-8"))
                self.assert_reader_agrees(path, "COMPLETE")

    DIGIT_KEPT = (" 2026-10-01", " 2026-10-01 — shipped", " 3 of 5 tasks", " 1.5", " 12/10 (x)")
    DIGIT_REFUSED = ("IN 2 PROGRESS", "COMPLETE 2026-10-01 PROGRESS")

    def test_a_number_or_date_after_the_token_is_prose_and_stays_byte_for_byte(self):
        for suffix in self.DIGIT_KEPT:
            with self.subTest(suffix=suffix):
                path = self.write_plan("Alpha", f"COMPLETE{suffix}")

                code, out = self.flip("Alpha", "BLOCKED")

                self.assertEqual(code, 0, out)
                self.assertIn(f"**Status:** BLOCKED{suffix}\n", path.read_bytes().decode("utf-8"))
                self.assert_reader_agrees(path, "BLOCKED")

    def test_a_number_between_status_words_stays_refused(self):
        for value in self.DIGIT_REFUSED:
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)
                before = path.read_bytes()

                code, out = self.flip("Alpha", "BLOCKED")

                self.assertEqual(code, 1)
                self.assertIn("multi-word", out)
                self.assertEqual(path.read_bytes(), before)

    def test_title_case_with_non_alphanumeric_continuation_is_replaced(self):
        path = self.write_plan("Alpha", "Complete (shipped)")

        code, _ = self.flip("Alpha", "BLOCKED")

        self.assertEqual(code, 0)
        self.assertIn("**Status:** BLOCKED (shipped)\n", path.read_bytes().decode("utf-8"))
        self.assert_reader_agrees(path, "BLOCKED")


class TestTrailingUnderscoresKept(FlipPlanStatusTestCase):
    """The closing italic `_` is markup, not part of the token: it stays."""

    CASES = (
        ("_IN_PROGRESS_", "_COMPLETE_"),
        ("**_IN_PROGRESS_** now", "**_COMPLETE_** now"),
        ("IN_PROGRESS_ — x", "COMPLETE_ — x"),
        ("**IN_PROGRESS_**", "**COMPLETE_**"),
    )

    def test_closing_underscores_survive_the_flip(self):
        for value, expected in self.CASES:
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)

                code, _ = self.flip("Alpha", "COMPLETE")

                self.assertEqual(code, 0)
                self.assertIn(f"**Status:** {expected}\n", path.read_bytes().decode("utf-8"))
                self.assert_reader_agrees(path, "COMPLETE")

    def test_target_already_reached_with_underscores_is_unchanged(self):
        path = self.write_plan("Alpha", "_COMPLETE_")
        before = path.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)
        self.assertEqual(path.read_bytes(), before)


class TestMarkupMustBalanceAndWrapTheToken(FlipPlanStatusTestCase):
    """Closing markup is skipped only when it mirrors the opening markup."""

    REFUSED = (
        "**IN** PROGRESS", "**Not** started", "*IN* PROGRESS", "`IN` PROGRESS",
        "**Not** started yet", "COMPLETE** now", "**COMPLETE* now", "**COMPLETE***",
    )
    KEPT = (
        ("**IN_PROGRESS**", "**BLOCKED**"),
        ("**IN_PROGRESS** now", "**BLOCKED** now"),
        ("**IN_PROGRESS** — x", "**BLOCKED** — x"),
        ("`IN_PROGRESS` (x)", "`BLOCKED` (x)"),
        ("✅ **IN_PROGRESS** - x", "✅ **BLOCKED** - x"),
    )

    def test_partly_bolded_multi_word_values_are_refused_with_bytes_unchanged(self):
        for value in self.REFUSED:
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)
                before = path.read_bytes()

                code, out = self.flip("Alpha", "BLOCKED")

                self.assertEqual(code, 1)
                self.assertIn("REFUSED", out)
                self.assertEqual(path.read_bytes(), before)

    def test_balanced_markup_around_an_identifier_token_is_flipped(self):
        for value, expected in self.KEPT:
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)

                code, _ = self.flip("Alpha", "BLOCKED")

                self.assertEqual(code, 0)
                self.assertIn(f"**Status:** {expected}\n", path.read_bytes().decode("utf-8"))
                self.assert_reader_agrees(path, "BLOCKED")


class TestStatusValueRefusal(FlipPlanStatusTestCase):
    """`status_value_refusal` is the writer's own span decision, side-effect free."""

    ACCEPTED = (
        "IN_PROGRESS", "✅ IN_PROGRESS — prose", "Complete (shipped)", "**IN_PROGRESS_** now",
        "_IN_PROGRESS_", "ON_hold since March", "COMPLETE", "**COMPLETE**",
        "COMPLETE 2026-10-01", "DONE 2026-10-01 — shipped", "BLOCKED 3 of 5 tasks",
    )
    REFUSED = (
        ("IN PROGRESS", "multi-word"),
        ("Not started", "multi-word"),
        ("In review", "multi-word"),
        ("**IN** PROGRESS", "multi-word"),
        ("IN 2 PROGRESS", "a number between"),
        ("COMPLETE 2026-10-01 PROGRESS", "a number between"),
        ("IN-PROGRESS", "glues"),
        ("COMPLETE.x", "glues"),
        ("COMPLETE** now", "glues"),
        ("✅", "cannot find a status token"),
        ("—", "cannot find a status token"),
    )

    def test_none_when_the_writer_can_flip_the_value(self):
        import flip_plan_status

        for value in self.ACCEPTED:
            with self.subTest(value=value):
                self.assertIsNone(flip_plan_status.status_value_refusal(value))

    def test_reason_string_when_it_cannot(self):
        import flip_plan_status

        for value, fragment in self.REFUSED:
            with self.subTest(value=value):
                reason = flip_plan_status.status_value_refusal(value)
                self.assertIsInstance(reason, str)
                self.assertIn(fragment, reason)

    def test_agrees_with_the_writer_on_every_value(self):
        import flip_plan_status

        for value in (*self.ACCEPTED, *(v for v, _ in self.REFUSED)):
            with self.subTest(value=value):
                path = self.write_plan("Alpha", value)
                before = path.read_bytes()
                verdict = flip_plan_status.status_value_refusal(value)

                code, out = self.flip("Alpha", "BLOCKED")

                if verdict is None:
                    self.assertEqual(code, 0, out)
                else:
                    self.assertEqual(code, 1, out)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertIn(verdict, out)

    def test_has_no_side_effects(self):
        import flip_plan_status

        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        flip_plan_status.status_value_refusal("IN_PROGRESS")

        self.assertEqual(path.read_bytes(), before)


class TestDuplicateMapPaths(FlipPlanStatusTestCase):
    def test_conflicting_statuses_are_refused_naming_both_lines(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        other = self.write_plan("Bravo", "IN_PROGRESS")
        before = path.read_bytes()

        map_file = self._write_map("Alpha/: COMPLETE\nBravo/: COMPLETE\nAlpha/: BLOCKED\n")
        code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertRegex(out, r"Alpha/: REFUSED: .*line 1.*line 3")
        self.assertEqual(path.read_bytes(), before)
        self.assert_reader_agrees(other, "COMPLETE")

    def test_slash_and_no_slash_are_the_same_path(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        code, out = self._run_main(self._argv(self._write_map("Alpha: COMPLETE\nAlpha/: BLOCKED\n")))

        self.assertEqual(code, 1)
        self.assertRegex(out, r"REFUSED: .*line 1.*line 2")
        self.assertEqual(path.read_bytes(), before)

    def test_exact_duplicate_is_applied_once_with_a_note(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")

        code, out = self._run_main(self._argv(self._write_map("Alpha/: COMPLETE\n# c\nAlpha: COMPLETE\n")))

        self.assertEqual(code, 0)
        self.assertIn("changed: 1", out)
        self.assertEqual(out.count("IN_PROGRESS -> COMPLETE"), 1)
        self.assertRegex(out, r"duplicate.*line 3.*line 1")
        self.assert_reader_agrees(path, "COMPLETE")

    def test_parse_map_drops_a_conflicted_path_and_keeps_a_duplicate_once(self):
        mapping = parse_map(self._write_map("A/: COMPLETE\nA: BLOCKED\nB/: COMPLETE\nB/: COMPLETE\n"))

        self.assertEqual(mapping, {"B/": "COMPLETE"})


class TestPerFileWriteDiscipline(FlipPlanStatusTestCase):
    def _three(self):
        paths = {name: self.write_plan(name, "IN_PROGRESS — x") for name in ("Alpha", "Bravo", "Charlie")}
        return paths, self._write_map("Alpha/: COMPLETE\nBravo/: COMPLETE\nCharlie/: COMPLETE\n")

    def test_write_error_on_second_plan_does_not_stop_the_rest(self):
        import flip_plan_status

        paths, map_file = self._three()
        bravo_before = paths["Bravo"].read_bytes()
        real_write = flip_plan_status.write_text_preserving_newlines
        calls = []

        def flaky(path, content):
            calls.append(path)
            if len(calls) == 2:
                raise PermissionError("locked by another process")
            real_write(path, content)

        with mock.patch.object(flip_plan_status, "write_text_preserving_newlines", flaky):
            code, out = self._run_main(self._argv(map_file))

        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)
        self.assert_reader_agrees(paths["Alpha"], "COMPLETE")
        self.assert_reader_agrees(paths["Charlie"], "COMPLETE")
        self.assertEqual(paths["Bravo"].read_bytes(), bravo_before)
        self.assertIn("changed: 2", out)
        self.assertIn("failed: 1", out)
        self.assertRegex(out, r"Bravo/: FAILED: .*locked by another process")
        self.assertIn("regenerate the index: python ", out)

    def test_file_changed_since_read_is_refused(self):
        import flip_plan_status

        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()
        real_read = flip_plan_status._read_bytes
        calls = []

        def drifting(p):
            calls.append(p)
            return real_read(p) if len(calls) == 1 else b"edited meanwhile"

        with mock.patch.object(flip_plan_status, "_read_bytes", drifting):
            code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("changed since read", out)
        self.assertIn("changed: 0", out)
        self.assertNotIn("regenerate the index", out)
        self.assertEqual(path.read_bytes(), before)

    def test_detected_link_is_refused(self):
        import flip_plan_status

        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        with mock.patch.object(flip_plan_status.recovery_surfaces, "is_link", lambda p: True):
            code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("symlink or junction", out)
        self.assertEqual(path.read_bytes(), before)

    def test_the_writer_asks_the_shared_link_check_about_the_file_and_each_folder_above_it(self):
        import flip_plan_status

        self.write_plan("Alpha", "IN_PROGRESS")
        asked = []

        def record(p):
            asked.append(Path(p))
            return False

        with mock.patch.object(flip_plan_status.recovery_surfaces, "is_link", record):
            code, _out = self.flip("Alpha", "COMPLETE", "--dry-run")

        self.assertEqual(code, 0)
        self.assertIn(self.plans_dir / "Alpha", asked)
        self.assertIn(self.plans_dir / "Alpha" / "Alpha-Master-Plan.md", asked)
        self.assertNotIn(self.plans_dir, asked)  # the configured plans directory itself may be a link

    def test_a_junctioned_plan_folder_is_refused_and_the_real_file_is_untouched(self):
        real = self.write_plan("Alpha", "IN_PROGRESS")
        moved = self.tmp_path / "elsewhere" / "Alpha"
        moved.parent.mkdir()
        real.parent.rename(moved)
        self.make_dir_link(self.plans_dir / "Alpha", moved)
        target = moved / "Alpha-Master-Plan.md"
        before = target.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("symlink or junction", out)
        self.assertEqual(target.read_bytes(), before)

    def test_real_symlink_is_refused_and_not_replaced(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        real = self.tmp_path / "real-master-plan.md"
        path.replace(real)
        try:
            os.symlink(real, path)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create a symlink here: {exc}")
        before = real.read_bytes()

        code, out = self.flip("Alpha", "COMPLETE")

        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertTrue(os.path.islink(path), "the link must not be replaced by a regular file")
        self.assertEqual(real.read_bytes(), before)


class TestPlanPathRefusal(FlipPlanStatusTestCase):
    """`plan_path_refusal` is the writer's own Path decision, side-effect free: the same entry lookup and the
    same link check `main` runs, so a caller can predict a Path refusal without writing."""

    def refusal(self, path: str):
        import flip_plan_status

        return flip_plan_status.plan_path_refusal(self.plans_dir, path)

    def test_none_for_a_plain_plan_with_or_without_the_trailing_slash(self):
        self.write_plan("Alpha", "IN_PROGRESS")

        self.assertIsNone(self.refusal("Alpha/"))
        self.assertIsNone(self.refusal("Alpha"))

    def test_a_path_with_no_master_plan_is_refused(self):
        self.write_plan("Alpha", "IN_PROGRESS")

        self.assertIn("no Master Plan", self.refusal("Missing/"))

    def test_two_master_plans_on_one_path_are_refused(self):
        self.write_plan("Alpha", "IN_PROGRESS")
        self.write_plan("Alpha", "IN_PROGRESS", filename="ALT-Master-Plan.md")

        self.assertIn("2 Master Plans", self.refusal("Alpha/"))

    def test_a_junctioned_plan_folder_is_refused(self):
        real = self.write_plan("Alpha", "IN_PROGRESS")
        moved = self.tmp_path / "elsewhere" / "Alpha"
        moved.parent.mkdir()
        real.parent.rename(moved)
        self.make_dir_link(self.plans_dir / "Alpha", moved)

        self.assertIn("symlink or junction", self.refusal("Alpha/"))

    def test_a_linked_master_plan_file_is_refused(self):
        self.write_plan("Alpha", "IN_PROGRESS")
        import flip_plan_status

        def only_files(p):  # a stand-in for a linked file
            return Path(p).is_file()

        with mock.patch.object(flip_plan_status.recovery_surfaces, "is_link", only_files):
            self.assertIn("symlink or junction", self.refusal("Alpha/"))

    def test_an_unreadable_entry_is_a_refusal_not_a_crash(self):
        self.write_plan("Alpha", "IN_PROGRESS")
        import flip_plan_status

        def broken(_p):
            raise PermissionError("denied")

        with mock.patch.object(flip_plan_status.recovery_surfaces, "is_link", broken):
            self.assertIn("denied", self.refusal("Alpha/"))

    def test_agrees_with_the_writer_for_every_path_shape(self):
        self.write_plan("Alpha", "IN_PROGRESS")
        self.write_plan("Bravo", "IN_PROGRESS")
        self.write_plan("Bravo", "IN_PROGRESS", filename="ALT-Master-Plan.md")
        for path in ("Alpha/", "Bravo/", "Missing/"):
            with self.subTest(path=path):
                verdict = self.refusal(path)

                code, out = self.flip(path.rstrip("/"), "COMPLETE", "--dry-run")

                if verdict is None:
                    self.assertEqual(code, 0, out)
                else:
                    self.assertEqual(code, 1, out)
                    self.assertIn(verdict, out)

    def test_has_no_side_effects(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        before = path.read_bytes()

        self.refusal("Alpha/")

        self.assertEqual(path.read_bytes(), before)


class TestMapParsing(FlipPlanStatusTestCase):
    def test_bom_prefixed_map_is_accepted(self):
        path = self.write_plan("Alpha", "IN_PROGRESS")
        map_file = self.tmp_path / "map.txt"
        map_file.write_bytes(b"\xef\xbb\xbfAlpha/: COMPLETE\r\n")

        code, _ = self._run_main(self._argv(map_file))

        self.assertEqual(code, 0)
        self.assert_reader_agrees(path, "COMPLETE")

    def test_hash_inside_a_path_is_not_a_comment(self):
        self.assertEqual(parse_map(self._write_map("C#Port/: COMPLETE\n")), {"C#Port/": "COMPLETE"})
        path = self.write_plan("C#Port", "IN_PROGRESS")

        code, out = self.flip("C#Port", "COMPLETE")

        self.assertEqual((code, out.count("REFUSED")), (0, 0), out)
        self.assert_reader_agrees(path, "COMPLETE")

    def test_comments_are_whole_line_or_space_hash_after_the_entry(self):
        text = "# top\n   # indented\nA/: COMPLETE  # trailing\nB/: BLOCKED\t# tab\nC#x/: NEEDS_FIXES\n\n"

        self.assertEqual(
            parse_map(self._write_map(text)),
            {"A/": "COMPLETE", "B/": "BLOCKED", "C#x/": "NEEDS_FIXES"},
        )

    def test_utf16_map_exits_one_with_a_named_message_and_no_traceback(self):
        map_file = self.tmp_path / "map16.txt"
        map_file.write_bytes("Alpha/: COMPLETE\n".encode("utf-16"))

        with self.assertRaises(SystemExit) as ctx:
            self._run_main(self._argv(map_file))

        message = str(ctx.exception.code)
        self.assertIn("map16.txt", message)
        self.assertIn("UTF-8", message)
        self.assertEqual(message.count("\n"), 0)
        self.assertNotIsInstance(ctx.exception.code, int)


if __name__ == "__main__":
    unittest.main()
