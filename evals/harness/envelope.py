"""Result-envelope parser — turns `claude --output-format json` stdout (a
JSON ARRAY of stream events, despite `claude --help` reading "json (single
result)") into a structured `Envelope`.

`data[0]` is the init event (`type:"system", subtype:"init"`); `data[-1]` is
the result event (`type:"result"`); everything between varies in count and
shape and is never assumed fixed. Two guards sit in front of the accessors:

  * a PARSE guard — 0 bytes, whitespace-only, or non-JSON stdout — reported
    as its own outcome ("no-envelope"), never collapsed into "assertion
    failed" (a CLI-level failure can exit non-zero with literally nothing
    to parse).
  * a DEGENERATE guard — stdout parses as JSON but the array is empty, or is
    missing a recognizable init or result event — reported as "degenerate",
    a capture failure and never a pass. A clean-looking envelope missing
    either boundary event told the caller nothing useful happened, even
    though the bytes technically parsed.

Pure function, no subprocess — unit-testable with synthesized fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Envelope:
    """A parsed result envelope.

    `outcome` is one of "ok", "no-envelope", "degenerate". `events` is the
    full parsed array (empty on a parse failure). `init_event` /
    `result_event` are `None` whenever the corresponding boundary event
    could not be recognized — callers must check `outcome`, not just
    truthiness of these fields, before trusting them.
    """

    outcome: str
    events: list = field(default_factory=list)
    init_event: dict | None = None
    result_event: dict | None = None


def _looks_like_init_event(candidate) -> bool:
    return (
        isinstance(candidate, dict)
        and candidate.get("type") == "system"
        and candidate.get("subtype") == "init"
    )


def _looks_like_result_event(candidate) -> bool:
    return isinstance(candidate, dict) and candidate.get("type") == "result"


def parse(stdout: str) -> Envelope:
    """Parse captured stdout into an `Envelope`. Never raises."""
    if not stdout or not stdout.strip():
        return Envelope(outcome="no-envelope")

    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return Envelope(outcome="no-envelope")

    if not isinstance(data, list) or not data:
        # Parsed as JSON but not the expected non-empty event array — no
        # init/result boundary event is even possible from this shape.
        return Envelope(outcome="degenerate", events=data if isinstance(data, list) else [])

    init_event = data[0] if _looks_like_init_event(data[0]) else None
    result_event = data[-1] if _looks_like_result_event(data[-1]) else None

    if init_event is None or result_event is None:
        return Envelope(
            outcome="degenerate", events=data,
            init_event=init_event, result_event=result_event,
        )

    return Envelope(
        outcome="ok", events=data,
        init_event=init_event, result_event=result_event,
    )


def agent_tool_uses(envelope: Envelope) -> list:
    """The `tool_use` content blocks across every assistant event.

    Dispatch-evidence layer: which tools the agent actually invoked, in
    order. Consumed by the graders — an `is_error:false` exit with a clean
    result event is not, by itself, proof the right tool ran.
    """
    uses = []
    for event in envelope.events:
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        content = (event.get("message") or {}).get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append(block)
    return uses


def tool_use_results(envelope: Envelope) -> list:
    """The `tool_result` content blocks across every user event.

    Pairs with `agent_tool_uses` via `tool_use_id` for the dispatch-evidence
    layer consumed by the graders.
    """
    results = []
    for event in envelope.events:
        if not isinstance(event, dict) or event.get("type") != "user":
            continue
        content = (event.get("message") or {}).get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append(block)
    return results
