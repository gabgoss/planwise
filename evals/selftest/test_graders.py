#!/usr/bin/env python3
"""Selftests for the grader catalog (harness/graders.py).

One `TestCase` class per grader (12, matching `graders.py`'s 12 functions --
the mechanical identity a later sweep task checks: grader-function count ==
arm-pair count here). Every class carries at least a pass arm and a fail
arm; several carry more than one distinct fail arm per the both-arms
inventory in EI Part 2 Section 6. All fixtures are synthesized JSON event
arrays or on-disk tempdirs -- $0, no live `claude` CLI anywhere in this
file.

`TestA11FieldLine` is A11's ratification: its three arms (pass, wrong
value, string-in-prose-not-a-field-line) are what EI Part 2 Section 4
requires before any case may cite A11 -- take the arm count from that
section, never from a shorthand elsewhere that only names the two fail
arms.

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_graders.py
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import envelope as envelope_mod
from harness import graders

MARKER = "doctor-line-marker-9f2c"

# ---------------------------------------------------------------------------
# Synthesized init events (EI Part 1 Section 3, verbatim field shape)
# ---------------------------------------------------------------------------
INIT_EVENT_FULL = {
    "type": "system",
    "subtype": "init",
    "slash_commands": ["help", "planwise:planwise"],
    "agents": [
        "claude", "Explore", "general-purpose", "Plan",
        "planwise:backlog-planner", "planwise:fix-agent", "planwise:plan-reviewer",
        "planwise:review-discovery", "planwise:rule-comparator",
        "planwise:structural-reviewer", "planwise:task-runner", "statusline-setup",
    ],
    "skills": ["planwise:planwise"],
    "plugins": [{"name": "planwise", "path": r"C:\fake\plugins\planwise",
                 "source": "planwise@inline", "version": "1.0.5"}],
}

INIT_EVENT_GENERIC = {
    "type": "system",
    "subtype": "init",
    "slash_commands": ["help"],
    "agents": ["claude", "Explore", "general-purpose", "Plan", "statusline-setup"],
    "skills": [],
    "plugins": [],
}


def _result_event(is_error=False, subtype="success", result_text="ok"):
    return {"type": "result", "is_error": is_error, "subtype": subtype, "result": result_text}


def _envelope_from_events(events: list) -> envelope_mod.Envelope:
    return envelope_mod.parse(json.dumps(events))


def _assistant_dispatch_event(dispatches: list[tuple[str, str]]) -> dict:
    """An assistant event carrying one `tool_use` block per (id, subagent_type)."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": tool_id, "name": "Agent",
                 "input": {"subagent_type": subagent_type}}
                for tool_id, subagent_type in dispatches
            ]
        },
    }


def _completion_event(agent_type: str, status: str = "completed", content_text: str | None = None) -> dict:
    tool_use_result = {"status": status, "agentType": agent_type, "agentId": "agent-1"}
    if content_text is not None:
        tool_use_result["content"] = [{"type": "text", "text": content_text}]
    return {"type": "user", "tool_use_result": tool_use_result}


class _TempDirCase(unittest.TestCase):
    """Shared tempdir setup for the graders that read a case dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_graders_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# A1
# ---------------------------------------------------------------------------
class TestA1InitMembership(unittest.TestCase):
    def test_pass_full_init_event(self):
        env = _envelope_from_events([INIT_EVENT_FULL, _result_event()])
        result = graders.a1_init_membership(env)
        self.assertTrue(result.passed)
        self.assertTrue(result.observed["command_present"])
        self.assertTrue(result.observed["agents_present"])

    def test_fail_generic_init_event(self):
        env = _envelope_from_events([INIT_EVENT_GENERIC, _result_event()])
        result = graders.a1_init_membership(env)
        self.assertFalse(result.passed)
        self.assertFalse(result.observed["command_present"])
        self.assertFalse(result.observed["agents_present"])
        self.assertEqual(len(result.observed["missing_agents"]), 7)


# ---------------------------------------------------------------------------
# A2
# ---------------------------------------------------------------------------
class TestA2ResultEnvelope(unittest.TestCase):
    def test_pass_valid_envelope_returncode_0(self):
        env = _envelope_from_events([INIT_EVENT_FULL, _result_event()])
        result = graders.a2_result_envelope(env, returncode=0)
        self.assertTrue(result.passed)

    def test_fail_no_envelope_empty_stdout(self):
        env = envelope_mod.parse("")  # the A2 fail-arm shape: 0 stdout bytes at all
        result = graders.a2_result_envelope(env, returncode=1)
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["outcome"], "no-envelope")

    def test_fail_parseable_but_degenerate(self):
        env = _envelope_from_events([INIT_EVENT_FULL])  # missing the result event entirely
        result = graders.a2_result_envelope(env, returncode=0)
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["outcome"], "degenerate")


# ---------------------------------------------------------------------------
# A3
# ---------------------------------------------------------------------------
class TestA3WriteSetPresent(_TempDirCase):
    EXPECTED = frozenset({"planwise/config.yaml", "planwise/Plans/00-Index-Plans.md", ".claude/settings.json"})

    def _seed(self, paths):
        for rel in paths:
            target = self.tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")

    def test_pass_dir_with_expected_set(self):
        self._seed(self.EXPECTED)
        result = graders.a3_write_set_present(self.tmp, self.EXPECTED)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["missing"], [])
        self.assertEqual(result.observed["extra"], [])

    def test_fail_pristine_dir(self):
        result = graders.a3_write_set_present(self.tmp, self.EXPECTED)
        self.assertFalse(result.passed)
        self.assertEqual(sorted(result.observed["missing"]), sorted(self.EXPECTED))


# ---------------------------------------------------------------------------
# A4
# ---------------------------------------------------------------------------
class TestA4WriteSetAbsent(_TempDirCase):
    CHECKED = ["planwise/config.yaml"]

    def test_pass_pristine_dir(self):
        result = graders.a4_write_set_absent(self.tmp, self.CHECKED)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["unexpectedly_present"], [])

    def test_fail_file_present(self):
        target = self.tmp / "planwise" / "config.yaml"
        target.parent.mkdir(parents=True)
        target.write_text("plugin_version: 1.0.5", encoding="utf-8")
        result = graders.a4_write_set_absent(self.tmp, self.CHECKED)
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["unexpectedly_present"], self.CHECKED)


# ---------------------------------------------------------------------------
# A4b
# ---------------------------------------------------------------------------
class TestA4bContainment(_TempDirCase):
    def setUp(self):
        super().setUp()
        self.case_dir = self.tmp / "case-1"
        self.case_dir.mkdir()
        (self.case_dir / "inside.txt").write_text("ok", encoding="utf-8")

    def test_pass_clean_scenario(self):
        result = graders.a4b_containment(self.tmp, self.case_dir)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["leaked_paths"], [])

    def test_fail_synthesized_leak(self):
        stray = self.tmp / "stray-outside-case-dir.txt"
        stray.write_text("leaked", encoding="utf-8")
        result = graders.a4b_containment(self.tmp, self.case_dir)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.observed["leaked_paths"]), 1)
        self.assertIn("stray-outside-case-dir.txt", result.observed["leaked_paths"][0])

    def test_pass_declared_scaffolding_sibling_excluded(self):
        """A declared-legitimate scratch-root sibling (e.g. the plugin-copy
        every case shares) sits right alongside `case_dir` under `parent` --
        exactly where a real leak would -- and must NOT fail the grader.
        """
        plugin_copy = self.tmp / "plugin-copy"
        plugin_copy.mkdir()
        (plugin_copy / "handlers.md").write_text("x", encoding="utf-8")
        result = graders.a4b_containment(self.tmp, self.case_dir, exclude=[plugin_copy])
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["leaked_paths"], [])
        self.assertEqual(result.observed["excluded_count"], 1)


# ---------------------------------------------------------------------------
# A5
# ---------------------------------------------------------------------------
class TestA5MarkerInResult(unittest.TestCase):
    def test_pass_marker_in_final_result(self):
        env = _envelope_from_events([INIT_EVENT_FULL, _result_event(result_text=f"prose {MARKER} prose")])
        result = graders.a5_marker_in_result(env, MARKER)
        self.assertTrue(result.passed)

    def test_fail_marker_only_in_midtranscript_noise(self):
        """The contamination shape: the marker shows up in a mid-transcript
        tool_result block, but the FINAL result field never carries it. A5
        must index only `data[-1]["result"]`, so this must fail.
        """
        noisy_user_event = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": f"cache hit: {MARKER}"}]},
        }
        env = _envelope_from_events([
            INIT_EVENT_FULL, noisy_user_event, _result_event(result_text="unrelated final answer"),
        ])
        result = graders.a5_marker_in_result(env, MARKER)
        self.assertFalse(result.passed)
        self.assertNotIn(MARKER, result.observed["final_field_text"])


# ---------------------------------------------------------------------------
# A6
# ---------------------------------------------------------------------------
class TestA6ConfigValue(_TempDirCase):
    def _write_config(self, text: str):
        target = self.tmp / "planwise" / "config.yaml"
        target.parent.mkdir(parents=True)
        target.write_text(text, encoding="utf-8")

    def test_pass_expected_key(self):
        self._write_config("plugin_version: 1.0.5\n")
        result = graders.a6_config_value(self.tmp, "plugin_version", "1.0.5")
        self.assertTrue(result.passed)

    def test_fail_missing_file(self):
        result = graders.a6_config_value(self.tmp, "plugin_version", "1.0.5")
        self.assertFalse(result.passed)
        self.assertFalse(result.observed["file_exists"])

    def test_fail_wrong_value(self):
        self._write_config("plugin_version: 1.0.4\n")
        result = graders.a6_config_value(self.tmp, "plugin_version", "1.0.5")
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["actual"], "1.0.4")

    def test_fail_malformed_yaml_reports_instead_of_raising(self):
        """A handler that writes a syntactically broken config.yaml is
        exactly the defect this grader must REPORT, not crash on. Must
        raise nothing and must carry the parse error as observed evidence.
        """
        self._write_config("plugin_version: [unterminated\n")
        result = graders.a6_config_value(self.tmp, "plugin_version", "1.0.5")
        self.assertFalse(result.passed)
        self.assertTrue(result.observed["file_exists"])
        self.assertIn("parse_error", result.observed)
        self.assertTrue(result.observed["parse_error"])


# ---------------------------------------------------------------------------
# A7
# ---------------------------------------------------------------------------
class TestA7DispatchIssued(unittest.TestCase):
    def test_pass_one_dispatch(self):
        events = [INIT_EVENT_FULL, _assistant_dispatch_event([("t1", "planwise:review-discovery")]), _result_event()]
        result = graders.a7_dispatch_issued(_envelope_from_events(events), "review-discovery")
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["match_count"], 1)

    def test_fail_zero_dispatches(self):
        events = [INIT_EVENT_FULL, {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}, _result_event()]
        result = graders.a7_dispatch_issued(_envelope_from_events(events), "review-discovery")
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["match_count"], 0)


# ---------------------------------------------------------------------------
# A7n
# ---------------------------------------------------------------------------
class TestA7nDispatchCount(unittest.TestCase):
    def test_pass_n_dispatches(self):
        dispatches = [(f"t{i}", "planwise:task-runner") for i in range(3)]
        events = [INIT_EVENT_FULL, _assistant_dispatch_event(dispatches), _result_event()]
        result = graders.a7n_dispatch_count(_envelope_from_events(events), "task-runner", 3)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["actual_count"], 3)

    def test_fail_zero_dispatches(self):
        events = [INIT_EVENT_FULL, {"type": "assistant", "message": {"content": []}}, _result_event()]
        result = graders.a7n_dispatch_count(_envelope_from_events(events), "task-runner", 3)
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["actual_count"], 0)


# ---------------------------------------------------------------------------
# A8
# ---------------------------------------------------------------------------
class TestA8DispatchCompleted(unittest.TestCase):
    def test_pass_completed(self):
        events = [INIT_EVENT_FULL, _completion_event("planwise:review-discovery"), _result_event()]
        result = graders.a8_dispatch_completed(_envelope_from_events(events), "review-discovery")
        self.assertTrue(result.passed)

    def test_fail_no_completion_event(self):
        events = [INIT_EVENT_FULL, _result_event()]
        result = graders.a8_dispatch_completed(_envelope_from_events(events), "review-discovery")
        self.assertFalse(result.passed)
        self.assertEqual(result.observed["match_count"], 0)

    def test_fail_wrong_agent_type(self):
        events = [INIT_EVENT_FULL, _completion_event("planwise:fix-agent"), _result_event()]
        result = graders.a8_dispatch_completed(_envelope_from_events(events), "review-discovery")
        self.assertFalse(result.passed)
        self.assertIn("planwise:fix-agent", result.observed["agent_types_seen"])


# ---------------------------------------------------------------------------
# A9
# ---------------------------------------------------------------------------
class TestA9FinalMessageMirror(unittest.TestCase):
    def test_pass_marker_in_content(self):
        events = [
            INIT_EVENT_FULL,
            _completion_event("planwise:review-discovery", content_text=f"findings: {MARKER}"),
            _result_event(),
        ]
        result = graders.a9_final_message_mirror(_envelope_from_events(events), "review-discovery", MARKER)
        self.assertTrue(result.passed)

    def test_fail_marker_absent(self):
        events = [
            INIT_EVENT_FULL,
            _completion_event("planwise:review-discovery", content_text="findings: nothing notable"),
            _result_event(),
        ]
        result = graders.a9_final_message_mirror(_envelope_from_events(events), "review-discovery", MARKER)
        self.assertFalse(result.passed)
        self.assertTrue(result.observed["completion_found"])

    def test_pass_marker_in_second_of_two_dispatches(self):
        """An agent dispatched twice (a fan-out) -- the marker is absent
        from the FIRST completion's content and present only in the
        SECOND. Stopping at the first match (the pre-fix behaviour) would
        wrongly report `passed=False`; every matching completion must be
        examined.
        """
        events = [
            INIT_EVENT_FULL,
            _completion_event("planwise:review-discovery", content_text="first pass: nothing notable"),
            _completion_event("planwise:review-discovery", content_text=f"second pass: {MARKER}"),
            _result_event(),
        ]
        result = graders.a9_final_message_mirror(_envelope_from_events(events), "review-discovery", MARKER)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["completions_examined"], 2)

    def test_fail_marker_absent_from_both_of_two_dispatches(self):
        events = [
            INIT_EVENT_FULL,
            _completion_event("planwise:review-discovery", content_text="first pass: nothing notable"),
            _completion_event("planwise:review-discovery", content_text="second pass: also nothing"),
            _result_event(),
        ]
        result = graders.a9_final_message_mirror(_envelope_from_events(events), "review-discovery", MARKER)
        self.assertFalse(result.passed)
        self.assertTrue(result.observed["completion_found"])
        self.assertEqual(result.observed["completions_examined"], 2)


# ---------------------------------------------------------------------------
# A11 -- the ratification. Three arms, taken from EI Part 2 Section 4:
# pass, wrong value, and string-in-prose-but-not-a-field-line (the arm that
# discriminates A11 from A5-as-substring and is the reason A11 exists).
# ---------------------------------------------------------------------------
class TestA11FieldLine(unittest.TestCase):
    def test_pass_field_line_present_with_expected_value(self):
        text = "# Master Plan\n\n**Token Saver:** on\n\nBody text.\n"
        result = graders.a11_field_line(text, "Token Saver", "on")
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["matched_line"], "**Token Saver:** on")

    def test_fail_wrong_value(self):
        text = "# Master Plan\n\n**Token Saver:** off\n\nBody text.\n"
        result = graders.a11_field_line(text, "Token Saver", "on")
        self.assertFalse(result.passed)

    def test_fail_string_in_prose_not_field_line(self):
        """The ratification's reason to exist: the label text appears in
        ordinary prose, never as a `**Label:** value` field line. A
        free-text substring search (A5-style) would wrongly pass this; the
        line-anchored regex must not.
        """
        text = "# Master Plan\n\nRemember to turn Token Saver: on before the sprint starts.\n"
        result = graders.a11_field_line(text, "Token Saver", "on")
        self.assertFalse(result.passed)
        self.assertIsNone(result.observed["matched_line"])


if __name__ == "__main__":
    unittest.main()
