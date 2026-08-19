"""Grader catalog -- the ratified assertion vocabulary for the eval harness.

Twelve pure grader functions, one per ID in EI Part 2 Section 1: A1, A2, A3,
A4, A4b, A5, A6, A7, A7n, A8, A9, A11. A10 (temporal write-order) is
deliberately NOT implemented here -- it is REJECTED-deferred, not retired,
and has no consumer in this catalog.

Every grader is a pure function over a parsed `Envelope` and/or a case
directory -- no grader shells out (the both-repo `git status --porcelain`
delta lives in `containment.py`, invoked by the case runner, never inside a
grader). A `GraderResult` always carries the OBSERVED value, not just a
boolean: a failing case must print what was actually seen, and a passing
case needs positive evidence of its own -- a bare boolean throws both away.

Non-negotiables baked in here (EI Part 2 Section 2):
  * A1 is membership-only -- never array equality or length (the init-event
    arrays are machine-wide, interleaving user-level content, not scoped to
    this plugin alone).
  * A3 is full set-equality of the relative-path write set -- never
    count-only, so a partial or renamed write is caught.
  * A5 indexes the parsed final `result` field ONLY, never raw stdout or
    mid-transcript tool-read noise -- a marker can appear there while
    absent from the final answer, which is exactly the contamination shape
    a passing A5 must reject.
  * A7/A7n key on the dispatch tool's actual runtime name (`DISPATCH_TOOL_NAME`
    below) -- some plugin-authored prose names a different tool; that is a
    documentation defect in the prose, never a contract to assert against.
  * A8 proves an agent *completed*, never what it did.
  * A9 reads the nested completion event's own content, never the top-level
    result field -- A5's technique at a nested JSON path.
  * A11 is a line-anchored Markdown field-line regex, never a free-text
    substring search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .containment import a4b_scan
from .envelope import Envelope, agent_tool_uses

# The dispatch tool's actual runtime name, keyed by every A7/A7n/A8 grader.
DISPATCH_TOOL_NAME = "Agent"

# The 7 planwise-namespaced agents the init event must carry, by membership
# (never equality -- the array also carries unnamespaced, user-level agents).
EXPECTED_7_AGENTS = frozenset({
    "planwise:backlog-planner",
    "planwise:fix-agent",
    "planwise:plan-reviewer",
    "planwise:review-discovery",
    "planwise:rule-comparator",
    "planwise:structural-reviewer",
    "planwise:task-runner",
})

EXPECTED_SLASH_COMMAND = "planwise:planwise"

# Sentinel: a config key that is ABSENT, distinct from present-but-wrong --
# `None` or `False` are legitimate real values a key could hold.
_MISSING = object()


@dataclass
class GraderResult:
    """One grader's verdict. `observed` always carries what was actually
    seen -- never collapse a result down to a bare boolean.
    """

    grader: str
    passed: bool
    observed: dict = field(default_factory=dict)
    detail: str = ""


# ---------------------------------------------------------------------------
# Layer 1 -- Registration
# ---------------------------------------------------------------------------
def a1_init_membership(envelope: Envelope) -> GraderResult:
    """Init-event membership: `planwise:planwise` in `slash_commands`, and
    the 7 expected agents a SUBSET of `agents`. Membership only.
    """
    init_event = envelope.init_event or {}
    slash_commands = set(init_event.get("slash_commands") or [])
    agents = set(init_event.get("agents") or [])
    command_present = EXPECTED_SLASH_COMMAND in slash_commands
    agents_present = EXPECTED_7_AGENTS <= agents
    passed = command_present and agents_present
    return GraderResult(
        grader="A1",
        passed=passed,
        observed={
            "command_present": command_present,
            "agents_present": agents_present,
            "missing_agents": sorted(EXPECTED_7_AGENTS - agents),
        },
        detail="init-event membership (slash_commands / agents)",
    )


def a2_result_envelope(envelope: Envelope, returncode: int | None = None) -> GraderResult:
    """Result-envelope health: the envelope parsed cleanly (`outcome ==
    "ok"` -- the parse guard's own outcome code already covers the
    no-stdout-at-all fail arm), `is_error is False`, `subtype ==
    "success"`, and -- when supplied -- the process exit code is 0.
    """
    if envelope.outcome != "ok":
        return GraderResult(
            grader="A2",
            passed=False,
            observed={"outcome": envelope.outcome, "returncode": returncode},
            detail=f"envelope outcome {envelope.outcome!r}, expected 'ok'",
        )
    result_event = envelope.result_event or {}
    is_error = result_event.get("is_error")
    subtype = result_event.get("subtype")
    passed = is_error is False and subtype == "success"
    if returncode is not None:
        passed = passed and returncode == 0
    return GraderResult(
        grader="A2",
        passed=passed,
        observed={
            "outcome": envelope.outcome,
            "is_error": is_error,
            "subtype": subtype,
            "returncode": returncode,
        },
        detail="result envelope health (is_error / subtype / exit code)",
    )


# ---------------------------------------------------------------------------
# Layer 3 -- Work products (on-disk)
# ---------------------------------------------------------------------------
def a3_write_set_present(case_dir: Path, expected_paths: Iterable[str]) -> GraderResult:
    """Full set-equality of the relative-path write set against
    `expected_paths` -- never count-only, so a partial or renamed write is
    caught.
    """
    expected = frozenset(expected_paths)
    actual = frozenset(
        str(p.relative_to(case_dir)).replace("\\", "/")
        for p in case_dir.rglob("*")
        if p.is_file()
    )
    passed = actual == expected
    return GraderResult(
        grader="A3",
        passed=passed,
        observed={
            "missing": sorted(expected - actual),
            "extra": sorted(actual - expected),
            "actual_count": len(actual),
        },
        detail="write-set presence (set-equality)",
    )


def a4_write_set_absent(case_dir: Path, paths: Iterable[str]) -> GraderResult:
    """None of `paths` exists under `case_dir`. Run against a dir the suite
    has NOT driven through the handler under test.
    """
    checked = list(paths)
    unexpectedly_present = [p for p in checked if (case_dir / p).exists()]
    passed = not unexpectedly_present
    return GraderResult(
        grader="A4",
        passed=passed,
        observed={"checked": checked, "unexpectedly_present": unexpectedly_present},
        detail="write-set absence",
    )


def a4b_containment(parent: Path, case_dir: Path, exclude: Iterable[Path] = ()) -> GraderResult:
    """No filesystem entry landed outside `case_dir`, scoped to its
    immediate `parent`. The `rglob` predicate itself lives in
    `containment.py` (`a4b_scan`) -- this wraps it into a `GraderResult`.
    For write-capable surfaces, pair with `containment.porcelain_delta` on
    both repos; a walk-up write can land outside `parent` entirely, which
    this parent-scoped predicate alone cannot see.

    `exclude` -- caller-declared known-legitimate siblings under `parent`
    (e.g. a shared scratch root's plugin-subtree copy, the `fx-initialized`
    template, other case dirs) that are NOT this case's output and must not
    be reported as leaks. This grader carries no hardcoded scratch-layout
    names; the caller that owns the scratch root supplies them. A stray
    file planted anywhere else is still caught regardless of `exclude`.
    """
    excluded = list(exclude)
    leaked = a4b_scan(parent, case_dir, exclude=excluded)
    passed = not leaked
    return GraderResult(
        grader="A4b",
        passed=passed,
        observed={
            "leaked_paths": sorted(str(p) for p in leaked),
            "excluded_count": len(excluded),
        },
        detail="containment (leak-arm) check",
    )


def a5_marker_in_result(envelope: Envelope, marker: str) -> GraderResult:
    """`marker` must be present in the parsed FINAL `result` field --
    `data[-1]["result"]` -- and nowhere else. A marker can appear in
    mid-transcript tool-read noise while absent from the final answer; that
    contamination shape is exactly what this grader must reject. Never
    treat a passing A5 as proof the plugin loaded on its own -- pair with
    A1.
    """
    result_event = envelope.result_event or {}
    final_text = result_event.get("result") or ""
    passed = marker in final_text
    return GraderResult(
        grader="A5",
        passed=passed,
        observed={"marker": marker, "final_field_text": final_text},
        detail="final-result marker (parsed field only, never raw stdout)",
    )


def a6_config_value(case_dir: Path, key: str, expected) -> GraderResult:
    """`planwise/config.yaml`'s `key` equals `expected`. A missing file, a
    malformed (unparseable) file, and a wrong value are three distinct
    failure signatures -- the caller can tell which occurred from
    `observed`. A handler that writes a syntactically broken config file is
    exactly the kind of defect this grader must REPORT, never let escape as
    an uncaught exception.
    """
    config_path = case_dir / "planwise" / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
    except OSError:
        return GraderResult(
            grader="A6",
            passed=False,
            observed={"config_path": str(config_path), "file_exists": False},
            detail="config file missing",
        )
    try:
        data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        return GraderResult(
            grader="A6",
            passed=False,
            observed={
                "config_path": str(config_path),
                "file_exists": True,
                "parse_error": str(exc),
            },
            detail="config file exists but is not valid YAML",
        )
    actual = data.get(key, _MISSING)
    if actual is _MISSING:
        return GraderResult(
            grader="A6",
            passed=False,
            observed={
                "config_path": str(config_path),
                "file_exists": True,
                "key": key,
                "key_present": False,
            },
            detail="key missing from an existing config file",
        )
    passed = actual == expected
    return GraderResult(
        grader="A6",
        passed=passed,
        observed={"key": key, "actual": actual, "expected": expected},
        detail="config-value assertion (structured read)",
    )


# ---------------------------------------------------------------------------
# Layer 2 -- Dispatch evidence
# ---------------------------------------------------------------------------
def _matching_dispatches(envelope: Envelope, agent: str) -> list[dict]:
    expected_subagent = f"planwise:{agent}"
    return [
        block
        for block in agent_tool_uses(envelope)
        if block.get("name") == DISPATCH_TOOL_NAME
        and (block.get("input") or {}).get("subagent_type") == expected_subagent
    ]


def a7_dispatch_issued(envelope: Envelope, agent: str) -> GraderResult:
    """At least one dispatch tool_use block names `planwise:{agent}` as its
    `subagent_type`.
    """
    matches = _matching_dispatches(envelope, agent)
    passed = bool(matches)
    return GraderResult(
        grader="A7",
        passed=passed,
        observed={"agent": agent, "match_count": len(matches)},
        detail="dispatch-issued (any)",
    )


def a7n_dispatch_count(envelope: Envelope, agent: str, expected_count: int) -> GraderResult:
    """Exact dispatch count for `planwise:{agent}` -- a counting MODE of
    A7. `expected_count` must come from the fixture's own scale class,
    never from a conditional Phase-2 role name.
    """
    matches = _matching_dispatches(envelope, agent)
    actual_count = len(matches)
    passed = actual_count == expected_count
    return GraderResult(
        grader="A7n",
        passed=passed,
        observed={"agent": agent, "actual_count": actual_count, "expected_count": expected_count},
        detail="dispatch count",
    )


def a8_dispatch_completed(envelope: Envelope, agent: str) -> GraderResult:
    """At least one `user`-type event's `tool_use_result` reports
    `agentType == "planwise:{agent}"` and `status == "completed"`. Proves
    an agent completed -- never what it did.
    """
    expected_type = f"planwise:{agent}"
    seen_types = []
    matches = []
    for event in envelope.events:
        if not isinstance(event, dict) or event.get("type") != "user":
            continue
        completion = event.get("tool_use_result")
        if not isinstance(completion, dict):
            continue
        seen_types.append(completion.get("agentType"))
        if completion.get("agentType") == expected_type and completion.get("status") == "completed":
            matches.append(completion)
    passed = bool(matches)
    return GraderResult(
        grader="A8",
        passed=passed,
        observed={"agent": agent, "match_count": len(matches), "agent_types_seen": seen_types},
        detail="dispatch-completed",
    )


def a9_final_message_mirror(envelope: Envelope, agent: str, marker: str) -> GraderResult:
    """`marker` present in ANY matching completion event's nested
    `tool_use_result["content"]` text blocks for `planwise:{agent}` -- A5's
    technique at a nested JSON path. Only meaningful for agents that report
    via their own final message; inherits A5's rule of pairing with A1.

    An agent can be dispatched more than once (a fan-out); every matching
    completion is examined rather than stopping at the first one, so a
    marker present only in a later dispatch's final message is not
    misreported as a failure.
    """
    expected_type = f"planwise:{agent}"
    completions_examined = 0
    for event in envelope.events:
        if not isinstance(event, dict) or event.get("type") != "user":
            continue
        completion = event.get("tool_use_result")
        if not isinstance(completion, dict) or completion.get("agentType") != expected_type:
            continue
        completions_examined += 1
        blocks = completion.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if marker in text:
            return GraderResult(
                grader="A9",
                passed=True,
                observed={
                    "agent": agent,
                    "completion_found": True,
                    "completions_examined": completions_examined,
                    "content_text": text,
                    "marker": marker,
                },
                detail="final-message content mirror",
            )
    if completions_examined == 0:
        return GraderResult(
            grader="A9",
            passed=False,
            observed={"agent": agent, "completion_found": False, "completions_examined": 0},
            detail="no completion event found for that agent",
        )
    return GraderResult(
        grader="A9",
        passed=False,
        observed={
            "agent": agent,
            "completion_found": True,
            "completions_examined": completions_examined,
            "marker": marker,
        },
        detail="marker not found in any matching completion's content",
    )


# ---------------------------------------------------------------------------
# Layer 3 -- Markdown field-line assertion (A11)
# ---------------------------------------------------------------------------
def a11_field_line(text: str, label: str, expected_value: str | None = None) -> GraderResult:
    r"""Line-anchored Markdown field-line regex: `^**{label}:** {value}$` at
    the START of a line (e.g. `^\*\*Token Saver:\*\* on$`). NEVER a
    free-text substring search -- `label`'s literal string may appear
    elsewhere in ordinary prose without being the field line itself, which
    is exactly the shape A11 exists to reject (the ratification protocol's
    second fail arm). When `expected_value` is None, only the field line's
    presence is asserted (any value), and the value actually found is
    reported back to the caller.
    """
    # [ \t]* rather than \s* on purpose: \s also matches newline, which lets
    # a greedy-then-backtracking match swallow the line's own trailing
    # newline into group(0) under MULTILINE -- this must stay a single-line
    # match, never crossing into the next line.
    escaped_label = re.escape(label)
    if expected_value is not None:
        pattern = re.compile(
            rf"^\*\*{escaped_label}:\*\*[ \t]*{re.escape(expected_value)}[ \t]*$",
            re.MULTILINE,
        )
    else:
        pattern = re.compile(rf"^\*\*{escaped_label}:\*\*[ \t]*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    passed = match is not None
    if match:
        observed_value = match.group(1).strip() if expected_value is None else expected_value
    else:
        observed_value = None
    return GraderResult(
        grader="A11",
        passed=passed,
        observed={
            "label": label,
            "expected_value": expected_value,
            "matched_line": match.group(0) if match else None,
            "observed_value": observed_value,
        },
        detail="line-anchored Markdown field-line assertion",
    )
