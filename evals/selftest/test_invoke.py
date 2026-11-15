#!/usr/bin/env python3
"""Selftests for the headless invocation driver (harness/invoke.py).

Every test monkeypatches `subprocess.run` at module level — never a live
`claude` CLI invocation. Covers the Windows console-attachment wrapper shape,
the POSIX argv shape, the never-raise outcome codes (ok / timeout / oserror /
empty-stdout / bad-tier), per-tier timeout selection, and the Windows
single-quote prompt/path escaping (a quote-bearing prompt must reach the CLI
as one intact argument, never truncated or shell-expanded).

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_invoke.py
"""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from harness import invoke


def _ok_proc(stdout: str = "[]", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = ""
    return proc


def _decode_ps_single_quoted_value(inner: str, flag: str) -> str:
    """Extract and decode a `<flag> '...'` PowerShell single-quoted literal
    out of a constructed inner command string.

    Deliberately NOT implemented by calling `invoke._ps_single_quote` in
    reverse — it is an independently written decoder, so a bug in the
    encoder under test (e.g. forgetting to double an embedded quote, or
    double-escaping) shows up as a mismatch here instead of being masked by
    reusing the same logic on both sides. Scans forward from the opening
    quote; `''` decodes to one literal `'` (PowerShell's own escape rule),
    any other `'` closes the literal.
    """
    marker = f"{flag} '"
    start = inner.index(marker) + len(marker)
    chars = []
    i = start
    while i < len(inner):
        ch = inner[i]
        if ch == "'":
            if inner[i:i + 2] == "''":
                chars.append("'")
                i += 2
                continue
            break  # unescaped closing quote
        chars.append(ch)
        i += 1
    return "".join(chars)


class TestWindowsInvocationShape(unittest.TestCase):
    """Windows: powershell.exe wrapper; drive-letter --plugin-dir preserved."""

    def test_windows_routes_through_powershell_with_drive_letter_path(self):
        with patch.object(invoke.os, "name", "nt"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help",
                plugin_dir=r"C:\Users\dev\plugins\planwise",
                cwd=r"C:\Users\dev\case-1",
                tier="T1",
            )

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "powershell.exe")
        self.assertIn("-NoProfile", cmd)
        self.assertIn("-Command", cmd)
        inner = cmd[-1]
        self.assertIn(
            r"C:\Users\dev\plugins\planwise", inner,
            "the drive-letter --plugin-dir path must be preserved verbatim",
        )
        self.assertNotIn("/c/", inner, "must never be converted to the POSIX-rooted form")
        self.assertIn("--output-format json", inner)
        self.assertFalse(mock_run.call_args[1].get("shell"))

    def test_windows_stdin_devnull_explicit_cwd_and_utf8_encoding(self):
        with patch.object(invoke.os, "name", "nt"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help",
                plugin_dir=r"C:\plugins\planwise",
                cwd=r"C:\case-1",
                tier="T1",
            )

        call_kwargs = mock_run.call_args[1]
        self.assertEqual(call_kwargs.get("stdin"), subprocess.DEVNULL)
        self.assertEqual(call_kwargs.get("cwd"), r"C:\case-1")
        self.assertEqual(
            call_kwargs.get("encoding"), "utf-8",
            "capture must pin UTF-8 explicitly, not the platform locale default "
            "(the fix for PowerShell's output-encoding mangling trap)",
        )


class TestPosixInvocationShape(unittest.TestCase):
    """POSIX: shutil.which resolution, argv list, no shell."""

    def test_posix_uses_resolved_binary_as_argv_list(self):
        fake_bin = "/usr/local/bin/claude"
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value=fake_bin), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help",
                plugin_dir="/home/dev/plugins/planwise",
                cwd="/home/dev/case-1",
                tier="T1",
            )

        cmd = mock_run.call_args[0][0]
        self.assertEqual(
            cmd,
            [fake_bin, "-p", "/planwise help", "--plugin-dir",
             "/home/dev/plugins/planwise", "--output-format", "json"],
        )
        self.assertFalse(mock_run.call_args[1].get("shell"))

    def test_posix_falls_back_to_bare_claude_when_unresolved(self):
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value=None), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help",
                plugin_dir="/home/dev/plugins/planwise",
                cwd="/home/dev/case-1",
                tier="T1",
            )

        self.assertEqual(mock_run.call_args[0][0][0], "claude")


class TestOutcomeCodes(unittest.TestCase):
    """The never-raise outcome codes: ok / timeout / oserror / empty-stdout."""

    def test_timeout_expired_yields_timeout_outcome(self):
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60)):
            result = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T1",
            )
        self.assertEqual(result.outcome, "timeout")
        self.assertIsNone(result.returncode)

    def test_oserror_yields_oserror_outcome(self):
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", side_effect=OSError("binary not found")):
            result = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T1",
            )
        self.assertEqual(result.outcome, "oserror")
        self.assertIsNone(result.returncode)

    def test_empty_stdout_yields_empty_stdout_outcome(self):
        # The A2 fail arm: exit 1, stdout 0 bytes — not even an init event.
        proc = _ok_proc(stdout="", returncode=1)
        proc.stderr = "error: unknown option --this-flag-does-not-exist"
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", return_value=proc):
            result = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T1",
            )
        self.assertEqual(result.outcome, "empty-stdout")
        self.assertEqual(result.returncode, 1)

    def test_nonempty_stdout_yields_ok_outcome_regardless_of_returncode(self):
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()):
            result = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T1",
            )
        self.assertEqual(result.outcome, "ok")

    def test_outcome_codes_are_pairwise_distinct(self):
        """Timeout / oserror / empty-stdout must never collapse into one
        another as an undifferentiated "capture failure"."""
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60)):
            timeout_outcome = invoke.run_case(
                prompt="p", plugin_dir="/plugins/planwise", cwd="/case-1", tier="T1",
            ).outcome

        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", side_effect=OSError("gone")):
            oserror_outcome = invoke.run_case(
                prompt="p", plugin_dir="/plugins/planwise", cwd="/case-1", tier="T1",
            ).outcome

        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc(stdout="", returncode=1)):
            empty_stdout_outcome = invoke.run_case(
                prompt="p", plugin_dir="/plugins/planwise", cwd="/case-1", tier="T1",
            ).outcome

        self.assertNotEqual(timeout_outcome, oserror_outcome)
        self.assertNotEqual(timeout_outcome, empty_stdout_outcome)
        self.assertNotEqual(oserror_outcome, empty_stdout_outcome)


class TestPerTierTimeoutSelection(unittest.TestCase):
    """Per-tier timeout table — no flat `timeout=120` literal anywhere."""

    def test_declared_timeouts_match_the_per_tier_table(self):
        self.assertEqual(invoke.TIER_TIMEOUT_S["T1"], 60)
        self.assertEqual(invoke.TIER_TIMEOUT_S["T2"], 120)
        self.assertEqual(invoke.TIER_TIMEOUT_S["T3"], 240)
        self.assertEqual(invoke.TIER_TIMEOUT_S["T4"], 600)
        self.assertEqual(invoke.TIER_TIMEOUT_S["T5"], 1080)
        self.assertEqual(invoke.TIER_TIMEOUT_S["T6"], 2400)

    def test_run_case_passes_the_tier_specific_timeout_to_subprocess(self):
        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T4",
            )
        self.assertEqual(mock_run.call_args[1].get("timeout"), 600)

    def test_unknown_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            invoke.timeout_for_tier("T9")


class TestWindowsPromptEscaping(unittest.TestCase):
    """FIX regression: the Windows branch must survive a prompt/path
    carrying PowerShell-significant characters — double quotes, backtick,
    `$`, `;`, and a literal single quote — intact, as ONE argument, never
    truncated or expanded. Every real fixture-init prompt (`harness/
    fixtures.py`'s `_init_prompt`) is full of embedded double quotes; the
    prior double-quote-interpolation form truncated the command at the
    first one.
    """

    # The real fixture-init prompt shape, verbatim structure.
    INIT_PROMPT = (
        '/planwise init --name "planwise-eval-fixture" '
        r'--root "C:\Users\dev\.scratch\case-1\fx-initialized-template" '
        '--dirs "standard" --scope "project" --tier "standard" '
        '--token-saver "off"'
    )

    def test_quote_bearing_init_prompt_survives_intact_on_windows(self):
        with patch.object(invoke.os, "name", "nt"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt=self.INIT_PROMPT,
                plugin_dir=r"C:\Users\dev\.scratch\plugins\planwise",
                cwd=r"C:\Users\dev\.scratch\case-1",
                tier="T4",
            )

        inner = mock_run.call_args[0][0][-1]
        decoded_prompt = _decode_ps_single_quoted_value(inner, "-p")
        self.assertEqual(
            decoded_prompt, self.INIT_PROMPT,
            "the prompt must reach the CLI as one intact argument, not "
            "truncated at its first embedded double quote",
        )

    def test_backtick_and_dollar_and_semicolon_in_prompt_survive_intact(self):
        tricky_prompt = "/planwise help `whoami` and $env:USERPROFILE; done"
        with patch.object(invoke.os, "name", "nt"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt=tricky_prompt,
                plugin_dir=r"C:\plugins\planwise",
                cwd=r"C:\case-1",
                tier="T1",
            )

        inner = mock_run.call_args[0][0][-1]
        decoded_prompt = _decode_ps_single_quoted_value(inner, "-p")
        self.assertEqual(
            decoded_prompt, tricky_prompt,
            "backtick / $ / ; must not be expanded or split the command "
            "when embedded in the prompt",
        )

    def test_apostrophe_in_plugin_dir_is_doubled_and_survives(self):
        tricky_dir = r"C:\Users\o'brien\plugins\planwise"
        with patch.object(invoke.os, "name", "nt"), \
             patch.object(invoke.subprocess, "run", return_value=_ok_proc()) as mock_run:
            invoke.run_case(
                prompt="/planwise help",
                plugin_dir=tricky_dir,
                cwd=r"C:\case-1",
                tier="T1",
            )

        inner = mock_run.call_args[0][0][-1]
        decoded_dir = _decode_ps_single_quoted_value(inner, "--plugin-dir")
        self.assertEqual(decoded_dir, tricky_dir)


class TestBadTierOutcome(unittest.TestCase):
    """FIX regression: an unrecognized tier must yield an outcome, never
    raise `ValueError` out of `run_case` (the never-raise entry point)."""

    def test_unknown_tier_yields_bad_tier_outcome_not_a_raise(self):
        with patch.object(invoke.subprocess, "run") as mock_run:
            result = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T9",
            )
        self.assertEqual(result.outcome, "bad-tier")
        self.assertIsNone(result.returncode)
        mock_run.assert_not_called()

    def test_timeout_for_tier_itself_still_raises_for_direct_callers(self):
        # timeout_for_tier is a plain utility, not the never-raise entry
        # point — run_case (above) is what must never raise.
        with self.assertRaises(ValueError):
            invoke.timeout_for_tier("T9")


if __name__ == "__main__":
    unittest.main()
