#!/usr/bin/env python3
"""Tests for the measured-value check (66), the paste-ready check (67) and the
``MUST be N`` / ``expect: N`` expectation spellings in the gate linter.

Every fixture is a real task file in the shape ``_write_task`` in
``test_lint_verification_gates.py`` writes: a ``## Verification Commands``
section holding a ``[!verify]`` callout whose ``**Before:**`` / ``**After:**``
labels each claim one fenced block. Table and column names are invented.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lint_verification_gates as lint_module
from lint_verification_gates import (
    LintContext,
    _check67_gate_rejects_paste_ready_block,
    _parse_expectation,
    extract_commands,
    lint_plan,
)

CLASS1_GATE = (
    "grep -vE '^\\s*--' db/orders.sql | grep -cE '^\\s*ALTER TABLE app\\.orders ADD '   # MUST be 0"
)
COLUMNS = ("col_a", "col_b", "col_c", "col_d", "col_e")
TWO_LINE_GUARDS = [
    line
    for name in COLUMNS
    for line in (
        f"IF COL_LENGTH('app.orders','{name}') IS NULL",
        f"    ALTER TABLE app.orders ADD {name} INT NULL;",
    )
]
ONE_LINE_GUARDS = [
    f"IF COL_LENGTH('app.orders','{name}') IS NULL ALTER TABLE app.orders ADD {name} INT NULL;"
    for name in COLUMNS
]
# A real tracking-table row shape, copied from templates/master-plan.md.
TRACKING_HEADER = (
    "## Session Completion Tracking\n\n"
    "| Sprint | Session | Status | Summary File | Completed |\n"
    "|--------|---------|--------|--------------|-----------|\n"
)


def _fence(block_lines, label=None):
    """The ``_write_task`` blockquote shape for one labelled fenced block."""
    head = f"> **{label}:** *(runner)*\n" if label else ""
    body = "".join(f"> {line}\n" for line in block_lines)
    return head + "> ```bash\n" + body + "> ```\n"


def _task_text(before=(), after=(), preamble=""):
    text = "# Task: Fixture\n\n" + preamble
    text += "## Verification Commands\n\n> [!verify] Before / After Commands\n"
    if before:
        text += _fence(before, "Before")
    if after:
        text += _fence(after, "After")
    return text


def _paste_ready(target, block_lines, lang="sql"):
    return (
        "## Execution Steps\n\n"
        f"<!-- paste-ready: {target} -->\n\n"
        f"```{lang}\n" + "".join(f"{line}\n" for line in block_lines) + "```\n\n"
    )


def _write(plan_root, text, name="TASK-01-Fixture.md", crlf=False):
    path = Path(plan_root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(data.encode("utf-8"))
    return path


def _of(findings, check):
    return [f for f in findings if f["check"] == check]


class TestParseExpectation(unittest.TestCase):
    def test_new_spellings(self):
        cases = {
            "# MUST be 0": (None, 0),
            "# MUST be >= 2": (">=", 2),
            "# expect: 3 hits": (None, 3),
            "# expect: >= 1": (">=", 1),
        }
        for note, (comparator, value) in cases.items():
            with self.subTest(note=note):
                parsed = _parse_expectation(note)
                self.assertIsNotNone(parsed, note)
                self.assertEqual((parsed.comparator, parsed.value), (comparator, value))

    def test_old_spellings_unchanged(self):
        cases = {
            "# expect 0": (None, 0),
            "# expect >=1": (">=", 1),
            "# pre-edit: 3 → expect 4": (None, 4),
            "# >=2": (">=", 2),
            "# 5": (None, 5),
            "# expect ≤ 7": ("<=", 7),
        }
        for note, (comparator, value) in cases.items():
            with self.subTest(note=note):
                parsed = _parse_expectation(note)
                self.assertEqual((parsed.comparator, parsed.value), (comparator, value))

    def test_prose_stays_unparsed(self):
        for note in ("# owner: runner", "# the value must be measured", "# expected none"):
            with self.subTest(note=note):
                self.assertIsNone(_parse_expectation(note))


class TestCheck67PasteReady(unittest.TestCase):
    def _lint(self, text, execute=True, crlf=False):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, text, crlf=crlf)
            return lint_plan(Path(tmp), execute=execute)

    def test_class1_two_line_guard_is_error_counting_five(self):
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)
        self.assertIn("counts 5", found[0]["message"])

    def test_class1_one_line_guard_gives_no_finding(self):
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=_paste_ready(
            "db/orders.sql", ONE_LINE_GUARDS))), 67)
        self.assertEqual(found, [])

    def test_crlf_task_file_still_errors(self):
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS)), crlf=True), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)
        self.assertIn("counts 5", found[0]["message"])

    def test_suffix_path_pairs(self):
        gate = CLASS1_GATE.replace("db/orders.sql", "src/db/orders.sql")
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"])

    def test_partial_segment_does_not_pair(self):
        gate = CLASS1_GATE.replace("db/orders.sql", "xdb/orders.sql")
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual(found, [])

    def test_awk_stage_is_uncertain(self):
        # No braces in the awk program: a {...} span marks a template placeholder,
        # and the linter skips a placeholder gate before any check reads it.
        gate = "grep -c 'ALTER' db/orders.sql | awk 'NR==1'   # MUST be 0"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual([f["severity"] for f in found], ["UNCERTAIN"], found)
        self.assertIn("awk", found[0]["message"])

    def test_unsimulated_flag_is_uncertain(self):
        gate = "grep -cw 'ADD' db/orders.sql   # MUST be 0"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual([f["severity"] for f in found], ["UNCERTAIN"], found)

    def test_prose_note_and_rg_stage_give_no_finding(self):
        # No parseable expectation, or an rg first stage: nothing to decide, no noise.
        for gate in ("grep -c 'ADD' db/orders.sql   # owner: runner",
                     "grep -n '^ALTER' db/orders.sql   # shows the headings",
                     "grep -c 'ADD' db/orders.sql   # expect: pass",
                     "rg -c 'ADD' db/orders.sql   # MUST be 0"):
            with self.subTest(gate=gate):
                found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
                    "db/orders.sql", TWO_LINE_GUARDS))), 67)
                self.assertEqual(found, [])

    def test_posix_bracket_classes_are_translated(self):
        import warnings

        lines = ["- a", "  - b", "- c"]
        for flag in ("-c", "-cE"):
            with self.subTest(flag=flag), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = lint_module._simulate_grep_pipeline(
                    [["grep", flag, "^[[:space:]]*- ", "f.md"]], lines)
                self.assertEqual(result, (3, None))
                self.assertEqual([w for w in caught if issubclass(w.category, FutureWarning)], [])
        count, reason = lint_module._simulate_grep_pipeline(
            [["grep", "-c", "^[[:xdigit:]]", "f.md"]], lines)
        self.assertIsNone(count)
        self.assertIn("xdigit", reason)

    def test_class_outside_a_bracket_and_equivalence_classes_are_uncertain(self):
        lines = ["- a", "  - b", "- c"]
        for pattern in ("[:space:]x", "[[=a=]]", "[[.a.]]"):
            with self.subTest(pattern=pattern):
                count, reason = lint_module._simulate_grep_pipeline(
                    [["grep", "-c", pattern, "f.md"]], lines)
                self.assertIsNone(count, reason)
                self.assertTrue(reason)

    def test_quoted_fence_ends_with_its_callout(self):
        alter = [f"ALTER TABLE app.orders ADD {name} INT NULL;" for name in COLUMNS]
        preamble = (
            "## Execution Steps\n\n> <!-- paste-ready: db/orders.sql -->\n>\n> ```sql\n"
            + "".join(f"> {line}\n" for line in alter[:2])
            + "\nProse that names " + alter[2] + "\n```\n\n"
        )
        gate = "grep -c 'ALTER' db/orders.sql   # MUST be <= 2"
        found = _of(self._lint(_task_text(after=[gate], preamble=preamble)), 67)
        self.assertEqual(found, [])

    def test_gate_counting_wrong_labels_is_paired(self):
        block = ["> WRONG — one", "> WRONG — two"]
        gate = "grep -c '^> WRONG' references/x.md   # expect 1"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready("references/x.md", block))), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)
        self.assertIn("counts 2", found[0]["message"])

    def test_plugin_root_target_pairs(self):
        gate = "grep -c 'ADD' {plugin_root}/references/x.md   # MUST be 0"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
            "{plugin_root}/references/x.md", TWO_LINE_GUARDS))), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)

    def test_blockquoted_marker_and_fence_are_read(self):
        body = "".join(f"> {line}\n" for line in TWO_LINE_GUARDS)
        preamble = ("## Execution Steps\n\n> <!-- paste-ready: db/orders.sql -->\n>\n"
                    "> ```sql\n" + body + "> ```\n\n")
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)

    def test_blockquoted_fence_suppresses_its_markers(self):
        preamble = (
            "## Execution Steps\n\n> ```text\n> <!-- paste-ready: db/orders.sql -->\n> ```\n\n"
            "```sql\n" + "".join(f"{line}\n" for line in TWO_LINE_GUARDS) + "```\n\n"
        )
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual(found, [])

    def test_closing_fence_takes_no_info_string(self):
        alter = [f"ALTER TABLE app.orders ADD {name} INT NULL;" for name in COLUMNS]
        preamble = (
            "## Execution Steps\n\n<!-- paste-ready: db/orders.sql -->\n\n```sql\n"
            + "".join(f"{line}\n" for line in alter[:2]) + "```text\n"
            + "".join(f"{line}\n" for line in alter[2:]) + "```\n\n"
        )
        gate = "grep -c 'ALTER' db/orders.sql   # MUST be <= 3"
        found = _of(self._lint(_task_text(after=[gate], preamble=preamble)), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)
        self.assertIn("counts 5", found[0]["message"])

    def test_pre_edit_plus_block_is_warning(self):
        block = ["ALTER TABLE app.orders ADD col_a INT NULL;", "ALTER TABLE app.orders ADD col_b INT NULL;"]
        gate = "grep -c 'ADD' db/orders.sql   # pre-edit: 4 → expect <= 5"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready("db/orders.sql", block))), 67)
        self.assertEqual([f["severity"] for f in found], ["WARNING"], found)
        self.assertIn("gives 6", found[0]["message"])

    def test_before_gate_is_not_paired(self):
        found = _of(self._lint(_task_text(before=[CLASS1_GATE], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS))), 67)
        self.assertEqual(found, [])

    def test_marker_without_block_is_warning_at_marker_line(self):
        preamble = "## Execution Steps\n\n<!-- paste-ready: db/orders.sql -->\n\nProse, no block.\n\n"
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual([(f["severity"], f["line"]) for f in found], [("WARNING", 5)], found)

    def test_marker_inside_fence_is_ignored(self):
        preamble = (
            "## Execution Steps\n\n```text\n<!-- paste-ready: db/orders.sql -->\n```\n\n"
            "```sql\n" + "".join(f"{line}\n" for line in TWO_LINE_GUARDS) + "```\n\n"
        )
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual(found, [])

    def test_marker_in_inline_code_span_is_ignored(self):
        preamble = (
            "## Execution Steps\n\nWrite `<!-- paste-ready: db/orders.sql -->` above the block.\n\n"
            "```sql\n" + "".join(f"{line}\n" for line in TWO_LINE_GUARDS) + "```\n\n"
        )
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual(found, [])

    def test_marker_mid_sentence_is_ignored(self):
        preamble = (
            "## Execution Steps\n\nPut <!-- paste-ready: db/orders.sql --> before the block.\n\n"
            "```sql\n" + "".join(f"{line}\n" for line in TWO_LINE_GUARDS) + "```\n\n"
        )
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=preamble)), 67)
        self.assertEqual(found, [])

    def test_gate_in_another_task_file_is_not_paired(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "# Task: Block\n\n" + _paste_ready("db/orders.sql", TWO_LINE_GUARDS))
            _write(tmp, _task_text(after=[CLASS1_GATE]), name="TASK-02-Fixture.md")
            found = _of(lint_plan(Path(tmp)), 67)
        self.assertEqual(found, [])

    def test_non_integer_pre_edit_skips_the_additive_warning(self):
        # A whole-file write marks its gate "pre-edit: replaced", so no sum applies.
        block = ["ALTER TABLE app.orders ADD col_a INT NULL;", "ALTER TABLE app.orders ADD col_b INT NULL;"]
        gate = "grep -c 'ADD' db/orders.sql   # pre-edit: replaced → expect <= 5"
        found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready("db/orders.sql", block))), 67)
        self.assertEqual(found, [])

    def test_indented_fence_in_numbered_step_strips_indentation(self):
        body = "".join(f"   ALTER TABLE app.orders ADD {name} INT NULL;\n" for name in COLUMNS)
        preamble = (
            "## Execution Steps\n\n1. Append the columns.\n\n"
            "   <!-- paste-ready: db/orders.sql -->\n\n   ```sql\n" + body + "   ```\n\n"
        )
        gate = "grep -c '^ALTER TABLE app' db/orders.sql   # MUST be 0"
        found = _of(self._lint(_task_text(after=[gate], preamble=preamble)), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"], found)
        self.assertIn("counts 5", found[0]["message"])

    def test_display_only_and_wrong_lines_are_not_paired(self):
        for gate in ("grep -n 'ADD' db/orders.sql",
                     "grep -c 'ADD' db/orders.sql   # WRONG: MUST be 0"):
            with self.subTest(gate=gate):
                found = _of(self._lint(_task_text(after=[gate], preamble=_paste_ready(
                    "db/orders.sql", TWO_LINE_GUARDS))), 67)
                self.assertEqual(found, [])

    def test_no_execute_keeps_check67(self):
        found = _of(self._lint(_task_text(after=[CLASS1_GATE], preamble=_paste_ready(
            "db/orders.sql", TWO_LINE_GUARDS)), execute=False), 67)
        self.assertEqual([f["severity"] for f in found], ["ERROR"])

    def test_check67_spawns_nothing(self):
        def boom(*args, **kwargs):
            raise AssertionError("Check 67 spawned a process")

        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, _task_text(after=[CLASS1_GATE], preamble=_paste_ready(
                "db/orders.sql", TWO_LINE_GUARDS)))
            context = LintContext(plan_root=Path(tmp), execute=True, commands=extract_commands(Path(tmp)))
            with patch.object(subprocess, "run", boom), patch.object(subprocess, "Popen", boom):
                found = _check67_gate_rejects_paste_ready_block(context)
        self.assertEqual([f["severity"] for f in found], ["ERROR"])


WRONG_AFTER = [
    "grep -c 'X' notes.md   # owner: runner. pre-edit: 3 → invariant: 2",
    "grep -c 'X' notes.md   # pre-edit: 1 → expect 4",
]
RIGHT_AFTER = [
    "grep -c 'X' notes.md   # owner: runner. pre-edit: 3 → invariant: 3",
    "grep -c 'X' notes.md   # pre-edit: 3 → expect 4",
]
WRONG_BEFORE = ["grep -c 'X' notes.md   # expect: 7"]
RIGHT_BEFORE = ["grep -c 'X' notes.md   # expect: 3"]


class TestCheck66MeasuredValues(unittest.TestCase):
    def _plan(self, tmp, text, task_name="TASK-01-Fixture.md", row_status=None):
        root = Path(tmp)
        task = _write(root, text, name=task_name)
        (task.parent / "notes.md").write_bytes(b"X\nX\nX\n")
        (root / "notes.md").write_bytes(b"X\nX\nX\n")
        if row_status is not None:
            (root / "TST-Master-Plan.md").write_text(
                "# Master Plan\n\n" + TRACKING_HEADER
                + f"| Sprint-01 | Session-01-Beta | {row_status} | - | - |\n",
                encoding="utf-8",
            )
        return root

    def test_three_wrong_values_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = _of(lint_plan(self._plan(tmp, _task_text(WRONG_BEFORE, WRONG_AFTER))), 66)
        self.assertEqual([f["severity"] for f in found], ["ERROR"] * 3, found)
        messages = " | ".join(f["message"] for f in found)
        for stated in ("'invariant: 2'", "'pre-edit: 1'", "the expectation '7'"):
            self.assertIn(stated, messages)

    def test_three_correct_values_are_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = _of(lint_plan(self._plan(tmp, _task_text(RIGHT_BEFORE, RIGHT_AFTER))), 66)
        self.assertEqual(found, [])

    def test_before_baseline_stays_with_check7(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = lint_plan(self._plan(tmp, _task_text(["grep -c 'X' notes.md   # baseline: 7"])))
        self.assertEqual(_of(findings, 66), [])
        self.assertEqual(len(_of(findings, 7)), 1)

    def test_complete_session_is_silent_and_not_started_fires(self):
        task_name = "Sprint-01-Alpha/Session-01-Beta/TST-S01-01-01-Fixture.md"
        text = _task_text(WRONG_BEFORE, WRONG_AFTER)
        for status, expected in (("✅ COMPLETE", 0), ("⏳ NOT STARTED", 3)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = self._plan(tmp, text, task_name=task_name, row_status=status)
                found = _of(lint_plan(root), 66)
                self.assertEqual(len(found), expected, found)

    def test_non_integer_annotation_is_silent(self):
        after = ["grep -c 'X' notes.md   # pre-edit: no file → expect 4",
                 "grep -c 'X' notes.md   # pre-edit: 2.5 → invariant: the same three lines"]
        with tempfile.TemporaryDirectory() as tmp:
            found = _of(lint_plan(self._plan(tmp, _task_text(after=after))), 66)
        self.assertEqual(found, [])

    def test_refused_command_is_silent_and_keeps_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = lint_plan(self._plan(tmp, _task_text(after=["cat notes.md   # pre-edit: 9 → expect 1"])))
        self.assertEqual(_of(findings, 66), [])
        refusals = [f for f in findings if f["check"] is None]
        self.assertEqual([f["severity"] for f in refusals], ["UNCERTAIN"])

    def test_no_execute_silences_check66(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = _of(lint_plan(self._plan(tmp, _task_text(WRONG_BEFORE, WRONG_AFTER)), execute=False), 66)
        self.assertEqual(found, [])

    def test_backslash_pattern_skipped_on_windows_only(self):
        # The stated 9 contradicts every reading of the pattern: a shell reads 3,
        # and an MSYS argv path that drops the backslash reads 0. So the
        # non-Windows arm fires on either runner, and only the patch decides.
        gate = "grep -c 'X\\|Y' notes.md   # pre-edit: 9 → expect 4"
        for windows, expected in ((True, 0), (False, 1)):
            with self.subTest(windows=windows), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(lint_module, "_on_windows", return_value=windows):
                found = _of(lint_plan(self._plan(tmp, _task_text(after=[gate]))), 66)
                self.assertEqual(len(found), expected, found)

    def test_session_status_decides_the_comparison(self):
        # Only a NOT STARTED session holds the pre-task tree, so only it compares.
        task_name = "Sprint-01-Alpha/Session-01-Beta/TST-S01-01-01-Fixture.md"
        text = _task_text(WRONG_BEFORE, WRONG_AFTER)
        for status, expected in (("🔄 IN PROGRESS", 0), ("🚫 BLOCKED", 0), ("⏳ NOT STARTED", 3)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = self._plan(tmp, text, task_name=task_name, row_status=status)
                self.assertEqual(len(_of(lint_plan(root), 66)), expected)

    def test_any_producer_lowers_every_kind_to_warning(self):
        # A producer may edit the target before this task runs, so every stated
        # value may project its edits. No producer keeps ERROR.
        task_name = "Sprint-01-Alpha/Session-01-Beta/TST-S01-01-02-Fixture.md"
        invariant_gate = ["grep -c 'X' notes.md   # owner: runner. pre-edit: 3 → invariant: 2"]
        cases = (
            ("01", WRONG_BEFORE, [], ["WARNING"]),
            ("cross-sprint: TST-S00-01-04", [], invariant_gate, ["WARNING"]),
            ("01 (writes notes.md)", WRONG_BEFORE, WRONG_AFTER, ["WARNING"] * 3),
            ("cross-session: TST-S01-02-01", WRONG_BEFORE, WRONG_AFTER, ["WARNING"] * 3),
            ("none", WRONG_BEFORE, WRONG_AFTER, ["ERROR"] * 3),
            ("-", WRONG_BEFORE, WRONG_AFTER, ["ERROR"] * 3),
            # Real no-producer forms with extra words keep ERROR.
            ("none (first dispatch of the session)", WRONG_BEFORE, WRONG_AFTER, ["ERROR"] * 3),
            ("- (reads `Outputs/x.md`, which the plan already holds)", WRONG_BEFORE, WRONG_AFTER,
             ["ERROR"] * 3),
            ("- <!-- a task number such as 01, or cross-sprint: TST-S00-01-04 -->", WRONG_BEFORE,
             WRONG_AFTER, ["ERROR"] * 3),
            # A separator inside a parenthesis does not split the entry.
            ("- (parallel-safe; batch member alongside 01, 02, 04)", WRONG_BEFORE, WRONG_AFTER,
             ["ERROR"] * 3),
            ("- (reads x, 01 output)", WRONG_BEFORE, WRONG_AFTER, ["ERROR"] * 3),
            ("01, 02 (writes Y)", WRONG_BEFORE, [], ["WARNING"]),
            ("01 (writes X)", WRONG_BEFORE, [], ["WARNING"]),
            ("cross-sprint: BGD-S01-01-04", WRONG_BEFORE, [], ["WARNING"]),
        )
        for depends, before, after, expected in cases:
            text = _task_text(before, after, preamble=f"**Depends On:** {depends}\n\n")
            with self.subTest(depends=depends), tempfile.TemporaryDirectory() as tmp:
                root = self._plan(tmp, text, task_name=task_name, row_status="⏳ NOT STARTED")
                found = _of(lint_plan(root), 66)
                self.assertEqual(sorted(f["severity"] for f in found), expected, found)

    def test_backslash_in_any_grep_token_is_skipped_on_windows(self):
        gate = "grep -c -m 5 'a\\|b' notes.md   # pre-edit: 3 → expect 4"
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(lint_module, "_on_windows", return_value=True):
            found = _of(lint_plan(self._plan(tmp, _task_text(after=[gate]))), 66)
        self.assertEqual(found, [])

    def test_no_backslash_still_fires_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(lint_module, "_on_windows", return_value=True):
            found = _of(lint_plan(self._plan(tmp, _task_text(WRONG_BEFORE, WRONG_AFTER))), 66)
        self.assertEqual(len(found), 3, found)

    def test_thousands_separator_reads_whole_number(self):
        self.assertEqual(lint_module._stated_pre_edit("# pre-edit: 89,787 bytes"), 89787)
        self.assertIsNone(lint_module._stated_pre_edit("# pre-edit: 2.5"))
        self.assertIsNone(lint_module._stated_invariant("# invariant: the same three lines"))


class TestCliForm(unittest.TestCase):
    """The linter runs as ``__main__``: both checks must work from the CLI."""

    def _run(self, root, *flags):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "lint_verification_gates.py"), str(root), *flags],
            capture_output=True, env=env, check=False,
        )

    def test_cli_reports_both_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, _task_text(WRONG_BEFORE, [CLASS1_GATE], preamble=_paste_ready(
                "db/orders.sql", TWO_LINE_GUARDS)))
            (root / "notes.md").write_bytes(b"X\nX\nX\n")
            result = self._run(root)
        stdout = result.stdout.decode("utf-8")
        self.assertIn("[ERROR] Check 66", stdout, result.stderr.decode("utf-8"))
        self.assertIn("[ERROR] Check 67", stdout)
        self.assertEqual(result.returncode, lint_module.EXIT_ERROR_PRESENT)


if __name__ == "__main__":
    unittest.main()
