#!/usr/bin/env python3
"""Regression tests for the retired team tools.

The shipped tree no longer instructs any agent to call `TeamCreate` or
`TeamDelete`, to pass `team_name`, or to address a message to `team-lead`.
These tests scan the shipped files on disk (not a git diff), so a defect that
predates any diff is still caught.

Two controls keep the scan honest:

* a positive control proves the scan reaches the agent files and sees the
  `disallowedTools:` lines it is meant to exempt, and
* mutation controls prove the scan flags an inserted instruction and that the
  `disallowedTools:` exemption is narrow.

Run with:  python -m pytest tests/test_team_tool_retirement.py -q
"""

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

RETIRED_TOOL_RE = re.compile(r"TeamCreate|TeamDelete|team_name")
TEAM_LEAD_RE = re.compile(r"team-lead")

# The one reference line that may name the retired tools: the tool-availability
# matrix row that marks them absent. It states absence, never an instruction.
# (relative path, excerpt substring, reason)
RETIRED_TOOL_ALLOWLIST = [
    (
        "references/agent-orchestration.md",
        "| TeamCreate, TeamDelete | NO | NO | NO |",
        (
            "tool-availability matrix row marking both tools absent (NO); "
            "a statement that the tools are absent, not an instruction to call them"
        ),
    ),
]

# Every remaining `team-lead` line in the shipped tree. Each one records the
# legacy address as a measured fact or a historical incident.
# (relative path, excerpt substring, reason)
TEAM_LEAD_ALLOWLIST = [
    (
        "references/agent-orchestration.md",
        "| `team-lead` | Legacy address |",
        (
            "address-table row: measured record that the legacy address arrives "
            "after the orchestrator's turn ends, marked Never"
        ),
    ),
    (
        "references/agent-orchestration.md",
        "3 of 3 sends to `team-lead` arrived only after its turn ended",
        (
            "constraint row: measured record naming the legacy address as the "
            "one that arrives late"
        ),
    ),
    (
        "references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md",
        'to="team-lead"',
        (
            "historical incident record: the blocks arrived only after an explicit "
            "instruction that used the legacy address"
        ),
    ),
    (
        "references/measure-from-the-record.md",
        "delivered to team-lead via SendMessage",
        (
            "historical incident record: reports that named the legacy address "
            "and never routed"
        ),
    ),
]


def _read_lines(path: Path) -> list[str]:
    """Return the file's lines, decoded as UTF-8 with carriage returns removed."""
    text = path.read_bytes().decode("utf-8", errors="replace").replace("\r", "")
    return text.split("\n")


def _frontmatter_line_count(lines: list[str]) -> int:
    """Return how many leading lines form the YAML frontmatter block (0 if none)."""
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


def _scan_with_text(root: Path, pattern: re.Pattern) -> list[tuple[str, int, str, str]]:
    """Return (relative path, line number, token, line text) for every hit."""
    hits = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(_read_lines(path), start=1):
            for match in pattern.finditer(line):
                hits.append((relative, number, match.group(0), line))
    return hits


def scan(root: Path, pattern: re.Pattern) -> list[tuple[str, int, str]]:
    """Return (relative path, line number, token) for every hit under root."""
    return [(rel, num, tok) for rel, num, tok, _ in _scan_with_text(root, pattern)]


def _is_denylist_line(root: Path, relative: str, number: int, line: str) -> bool:
    """True for a `disallowedTools:` line inside an agent file's frontmatter."""
    parts = relative.split("/")
    if len(parts) != 2 or parts[0] != "agents":
        return False
    if not line.startswith("disallowedTools:"):
        return False
    lines = _read_lines(root / relative)
    return number <= _frontmatter_line_count(lines)


def _allowed(relative: str, line: str, allowlist: list[tuple[str, str, str]]) -> bool:
    return any(rel == relative and excerpt in line for rel, excerpt, _ in allowlist)


def retired_tool_offenders(root: Path) -> list[tuple[str, int, str]]:
    """Return retired-tool hits that are neither a denylist line nor allowlisted."""
    offenders = []
    for relative, number, token, line in _scan_with_text(root, RETIRED_TOOL_RE):
        if _is_denylist_line(root, relative, number, line):
            continue
        if _allowed(relative, line, RETIRED_TOOL_ALLOWLIST):
            continue
        offenders.append((relative, number, token))
    return offenders


def team_lead_offenders(root: Path) -> list[tuple[str, int, str]]:
    """Return `team-lead` hits that no allowlist entry covers."""
    offenders = []
    for relative, number, token, line in _scan_with_text(root, TEAM_LEAD_RE):
        if _allowed(relative, line, TEAM_LEAD_ALLOWLIST):
            continue
        offenders.append((relative, number, token))
    return offenders


def _format(offenders: list[tuple[str, int, str]]) -> str:
    return "\n".join(f"{rel}:{num} ({tok})" for rel, num, tok in offenders)


def test_scan_reaches_the_agent_denylist_lines():
    """Positive control: a scan that cannot see the agent files fails here."""
    hit_paths = {
        rel
        for rel, num, _, line in _scan_with_text(PLUGIN_ROOT, RETIRED_TOOL_RE)
        if rel.startswith("agents/") and line.startswith("disallowedTools:")
    }
    expected_paths = set()
    for path in sorted((PLUGIN_ROOT / "agents").glob("*.md")):
        for line in _read_lines(path):
            if line.startswith("disallowedTools:") and "TeamCreate" in line:
                expected_paths.add(f"agents/{path.name}")
    assert expected_paths, "independent loop found no denylist lines: the control is blind"
    assert hit_paths == expected_paths


def test_shipped_tree_has_no_retired_tool_instruction():
    offenders = retired_tool_offenders(PLUGIN_ROOT)
    assert offenders == [], "retired team tool named outside the denylist:\n" + _format(
        offenders
    )


def test_team_lead_addresses_are_only_the_ledgered_leave_rows():
    offenders = team_lead_offenders(PLUGIN_ROOT)
    assert offenders == [], "unlisted `team-lead` address:\n" + _format(offenders)


def test_mutation_control_inserted_instruction_is_flagged(tmp_path):
    source = PLUGIN_ROOT / "handlers" / "review.md"
    target_dir = tmp_path / "handlers"
    target_dir.mkdir()
    original = source.read_bytes().decode("utf-8", errors="replace").replace("\r", "")
    copy = target_dir / "review.md"

    copy.write_bytes(original.encode("utf-8"))
    assert retired_tool_offenders(tmp_path) == []

    mutated = original + '\nTeamCreate(team_name: "x")\n'
    copy.write_bytes(mutated.encode("utf-8"))
    assert len(retired_tool_offenders(tmp_path)) >= 1


def test_mutation_control_denylist_exemption_is_narrow(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent = agents_dir / "x.md"

    agent.write_bytes(
        b"---\nname: x\ndisallowedTools: TeamCreate, TeamDelete\n---\n\nBody text.\n"
    )
    assert retired_tool_offenders(tmp_path) == []

    agent.write_bytes(
        b"---\nname: x\ndescription: sample\n---\n\nCall TeamCreate, TeamDelete here.\n"
    )
    assert len(retired_tool_offenders(tmp_path)) >= 1


def test_agent_orchestration_frozen_anchors():
    lines = _read_lines(PLUGIN_ROOT / "references" / "agent-orchestration.md")
    sections = [line for line in lines if re.match(r"^## [0-9]+\. ", line)]
    rows_11_12 = [line for line in lines if re.match(r"^\| 1[12] ", line)]
    row_1 = [line for line in lines if re.match(r"^\| 1 \| No sub-subagent spawning", line)]
    assert len(sections) == 11
    assert len(rows_11_12) == 2
    assert len(row_1) == 1


def test_review_crossover_quote_matches_reference():
    review = "\n".join(_read_lines(PLUGIN_ROOT / "handlers" / "review.md"))
    reference = "\n".join(_read_lines(PLUGIN_ROOT / "references" / "agent-orchestration.md"))
    match = re.search(r'§8, "([^"]+)"', review)
    assert match, "no §8 crossover quote found in handlers/review.md"
    quote = match.group(1).replace("*", "")
    flat_reference = reference.replace("*", "")
    assert quote in flat_reference
    mutated = quote + " (altered)"
    assert (mutated in flat_reference) is False
