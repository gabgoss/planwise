#!/usr/bin/env python3
"""Selftests for the result-envelope parser (harness/envelope.py).

Pure-function module, no subprocess involved — every fixture here is a
synthesized JSON array, never a live `claude` CLI capture. Covers: a valid
array (init + result), 0-byte stdout, malformed JSON, an array missing the
result event (degenerate), the recorded init-event shape (7 namespaced
agents) round-tripping through the accessors, and that the invoke-layer
"timeout" outcome and this module's "no-envelope" / "degenerate" outcomes
are three pairwise-distinct codes.

Run with:
  C:/Python314/python.exe -m pytest -c evals/pytest.ini evals/selftest/test_envelope.py
"""

import json
import subprocess
import unittest
from unittest.mock import patch

from harness import envelope

# The recorded init-event shape (EI Part 1 Section 3), verbatim field names.
# 7/7 planwise:-namespaced agents alongside the built-in, unnamespaced ones —
# these arrays are machine-wide, never plugin-scoped, so membership is what
# a caller asserts, never array equality.
INIT_EVENT = {
    "type": "system",
    "subtype": "init",
    "cwd": r"C:\Users\dev\case-1",
    "session_id": "abc123",
    "claude_code_version": "2.1.234",
    "model": "claude-opus-4-8[1m]",
    "permissionMode": "default",
    "slash_commands": ["help", "planwise:planwise"],
    "agents": [
        "claude", "Explore", "general-purpose", "Plan",
        "planwise:backlog-planner", "planwise:fix-agent", "planwise:plan-reviewer",
        "planwise:review-discovery", "planwise:rule-comparator",
        "planwise:structural-reviewer", "planwise:task-runner", "statusline-setup",
    ],
    "skills": ["deep-research", "planwise:planwise"],
    "plugins": [
        {"name": "planwise", "path": r"C:\case-1\plugins\planwise",
         "source": "planwise@inline", "version": "1.0.5"},
    ],
}

RESULT_EVENT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 12842,
    "duration_api_ms": 12742,
    "num_turns": 1,
    "total_cost_usd": 0.0394,
    "usage": {"cache_read_input_tokens": 30705, "cache_creation_input_tokens": 0},
    "result": "…prose…",
}

ASSISTANT_EVENT = {
    "type": "assistant",
    "message": {
        "content": [
            {"type": "text", "text": "Let me check."},
            {"type": "tool_use", "id": "toolu_01", "name": "Read", "input": {"file_path": "x.py"}},
        ],
    },
}

USER_TOOL_RESULT_EVENT = {
    "type": "user",
    "message": {
        "content": [
            {"type": "tool_result", "tool_use_id": "toolu_01", "content": "file contents"},
        ],
    },
}

VALID_ENVELOPE = [INIT_EVENT, RESULT_EVENT]
FULL_ENVELOPE = [INIT_EVENT, ASSISTANT_EVENT, USER_TOOL_RESULT_EVENT, RESULT_EVENT]


class TestValidEnvelope(unittest.TestCase):
    """A valid array (init + result) parses to outcome "ok"."""

    def test_valid_array_parses_ok_with_both_boundary_events(self):
        env = envelope.parse(json.dumps(VALID_ENVELOPE))
        self.assertEqual(env.outcome, "ok")
        self.assertEqual(env.init_event, INIT_EVENT)
        self.assertEqual(env.result_event, RESULT_EVENT)
        self.assertEqual(env.events, VALID_ENVELOPE)

    def test_init_is_data_zero_result_is_data_minus_one_with_middle_events(self):
        env = envelope.parse(json.dumps(FULL_ENVELOPE))
        self.assertEqual(env.outcome, "ok")
        self.assertEqual(env.init_event, env.events[0])
        self.assertEqual(env.result_event, env.events[-1])
        self.assertEqual(len(env.events), 4)


class TestParseGuard(unittest.TestCase):
    """0-byte / non-JSON stdout is its own outcome: "no-envelope"."""

    def test_zero_byte_stdout_is_no_envelope(self):
        env = envelope.parse("")
        self.assertEqual(env.outcome, "no-envelope")
        self.assertIsNone(env.init_event)
        self.assertIsNone(env.result_event)
        self.assertEqual(env.events, [])

    def test_whitespace_only_stdout_is_no_envelope(self):
        env = envelope.parse("   \n  ")
        self.assertEqual(env.outcome, "no-envelope")

    def test_malformed_json_is_no_envelope(self):
        # The A2 fail arm's stderr text, not stdout — confirms a non-JSON
        # payload never raises out of parse().
        env = envelope.parse("error: unknown option --this-flag-does-not-exist")
        self.assertEqual(env.outcome, "no-envelope")


class TestDegenerateGuard(unittest.TestCase):
    """Parses, but missing a boundary event -> "degenerate", never a pass."""

    def test_array_missing_result_event_is_degenerate(self):
        env = envelope.parse(json.dumps([INIT_EVENT]))
        self.assertEqual(env.outcome, "degenerate")
        self.assertIsNotNone(env.init_event)
        self.assertIsNone(env.result_event)

    def test_array_missing_init_event_is_degenerate(self):
        env = envelope.parse(json.dumps([ASSISTANT_EVENT, RESULT_EVENT]))
        self.assertEqual(env.outcome, "degenerate")
        self.assertIsNone(env.init_event)
        self.assertIsNotNone(env.result_event)

    def test_empty_array_is_degenerate(self):
        env = envelope.parse(json.dumps([]))
        self.assertEqual(env.outcome, "degenerate")

    def test_non_array_json_is_degenerate(self):
        # `claude --help` reads "json (single result)" — a caller who
        # forgets this is an array and gets handed an object anyway must
        # not have it silently misread as a one-element list.
        env = envelope.parse(json.dumps({"type": "result"}))
        self.assertEqual(env.outcome, "degenerate")

    def test_degenerate_is_never_treated_as_a_pass(self):
        env = envelope.parse(json.dumps([INIT_EVENT]))
        self.assertNotEqual(env.outcome, "ok")


class TestInitEventRoundTrip(unittest.TestCase):
    """The recorded init-event shape (7 namespaced agents) round-trips."""

    def test_seven_namespaced_agents_round_trip_through_the_accessor(self):
        env = envelope.parse(json.dumps(VALID_ENVELOPE))
        self.assertEqual(env.outcome, "ok")
        namespaced = [a for a in env.init_event["agents"] if a.startswith("planwise:")]
        self.assertEqual(len(namespaced), 7)
        self.assertEqual(
            set(namespaced),
            {
                "planwise:backlog-planner", "planwise:fix-agent", "planwise:plan-reviewer",
                "planwise:review-discovery", "planwise:rule-comparator",
                "planwise:structural-reviewer", "planwise:task-runner",
            },
        )

    def test_slash_commands_and_plugins_membership_round_trip(self):
        env = envelope.parse(json.dumps(VALID_ENVELOPE))
        self.assertIn("planwise:planwise", env.init_event["slash_commands"])
        self.assertEqual(env.init_event["plugins"][0]["version"], "1.0.5")


class TestDispatchEvidenceHelpers(unittest.TestCase):
    """agent_tool_uses / tool_use_results extract dispatch evidence."""

    def test_agent_tool_uses_extracts_tool_use_blocks(self):
        env = envelope.parse(json.dumps(FULL_ENVELOPE))
        uses = envelope.agent_tool_uses(env)
        self.assertEqual(len(uses), 1)
        self.assertEqual(uses[0]["name"], "Read")
        self.assertEqual(uses[0]["id"], "toolu_01")

    def test_tool_use_results_extracts_tool_result_blocks(self):
        env = envelope.parse(json.dumps(FULL_ENVELOPE))
        results = envelope.tool_use_results(env)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tool_use_id"], "toolu_01")

    def test_helpers_return_empty_on_a_degenerate_envelope(self):
        env = envelope.parse(json.dumps([INIT_EVENT]))
        self.assertEqual(envelope.agent_tool_uses(env), [])
        self.assertEqual(envelope.tool_use_results(env), [])


class TestCrossModuleOutcomeDistinctness(unittest.TestCase):
    """Timeout (invoke.py) / no-envelope / degenerate (envelope.py) must be
    three pairwise-DISTINCT outcome codes — a capture failure from either
    layer must never collapse into the other layer's outcome."""

    def test_timeout_no_envelope_degenerate_are_pairwise_distinct(self):
        from harness import invoke

        with patch.object(invoke.os, "name", "posix"), \
             patch.object(invoke.shutil, "which", return_value="/usr/bin/claude"), \
             patch.object(invoke.subprocess, "run",
                           side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60)):
            timeout_outcome = invoke.run_case(
                prompt="/planwise help", plugin_dir="/plugins/planwise",
                cwd="/case-1", tier="T1",
            ).outcome

        no_envelope_outcome = envelope.parse("").outcome
        degenerate_outcome = envelope.parse(json.dumps([INIT_EVENT])).outcome

        self.assertNotEqual(timeout_outcome, no_envelope_outcome)
        self.assertNotEqual(timeout_outcome, degenerate_outcome)
        self.assertNotEqual(no_envelope_outcome, degenerate_outcome)


if __name__ == "__main__":
    unittest.main()
