"""Pair-contract lint: at most one labelled WRONG per section of every reference.

Every ``##`` to ``####`` section of every ``references/*.md`` file holds at
most one labelled WRONG outside fenced code. A section listed in
``PAIR_EXEMPTIONS`` may hold no more than its recorded count, and an entry
whose section measures one or fewer fails as stale until it is removed.

Fence rule (literal): a line whose first non-whitespace characters are three
backticks toggles the fence, so a ``> `` callout fence does not hide a label.
Sections come from ``markdown_parser.extract_headings``, which applies the same
rule. A four-backtick block holding a three-backtick block flips the state, and
``~~~`` is never a fence.

A label line matches ``^\\s*>?\\s*(\\*\\*)?WRONG\\b`` or ``\\bWRONG\\s*[—:-]``.
A label counts once per line, and heading lines are not scanned. The text
before the first heading is the ``(preamble)`` section.

The references directory comes from ``PAIR_CONTRACT_REFS_DIR`` when it is set,
else ``plugins/planwise/references`` resolved from this file. The stale check
for an exempted file that is missing runs only when the variable is unset.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from markdown_parser import extract_headings

_OVERRIDE = os.environ.get("PAIR_CONTRACT_REFS_DIR")
REFS_DIR = (
    Path(_OVERRIDE)
    if _OVERRIDE
    else Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "references"
)

PREAMBLE = "(preamble)"
_LABEL_RES = (
    re.compile(r"^\s*>?\s*(\*\*)?WRONG\b"),
    re.compile(r"\bWRONG\s*[—:-]"),
)

# Sections that held more than one WRONG label outside fences when measured.
# A compress task removes its entries in its own write-set. An entry whose
# section now measures at most 1 fails as STALE until removed. A new section
# with two labels is the author's regression, never an entry added without a
# recorded reason.
PAIR_EXEMPTIONS = {
    ("agent-authoring.md", "## 2b. Common Configuration Mistakes"): 3,  # @ becccfe (2026-10-20)
    ("agent-orchestration-delegated.md", "## 1.1 Mandatory Triggers"): 2,  # @ becccfe (2026-10-20)
    ("agent-orchestration-delegated.md", "## 1.6 Path-Scoped Rule Injection in Spawn Prompts"): 2,  # @ becccfe (2026-10-20)
    ("artifact-self-containment.md", "### 3.1 Rule body must inline, not cite the source lesson"): 3,  # @ becccfe (2026-10-20)
    ("dispatch-preflight-claim-expiry.md", "## 7. A Routed Flag Carries Decisions and Measurements: Classify Every Literal, Re-Measure the Cheap, De-Anchor the Expensive"): 2,  # @ becccfe (2026-10-20)
    ("ei-fidelity.md", "## 1. EI as Archival — Transform at Task Layer"): 2,  # @ becccfe (2026-10-20)
    ("ei-source-promise-integrity.md", "### 10.2 Pre-Extraction Verification Protocol (Task Execution)"): 2,  # @ becccfe (2026-10-20)
    ("execution-time-binding-rules.md", "## 19. Narrow Fix Reveals a Systemic Gap — Bounded Temp Fix That Seeds the Deferred Discovery (BINDING)"): 2,  # @ becccfe (2026-10-20)
    ("exit-criteria-fidelity.md", "#### 16.3 Extension — BLI-Cited Audit-Anchor Re-Verification"): 2,  # @ becccfe (2026-10-20)
    ("lessons-curate-workflow.md", "## 7. Constraints"): 3,  # @ becccfe (2026-10-20)
    ("lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "### 5.1a The delegated path (drafting dispatched to an authoring agent)"): 2,  # @ becccfe (2026-10-20)
    ("lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "### 5.2 The self-containment principle (BINDING)"): 4,  # @ becccfe (2026-10-20)
    ("lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "## 10. Constraints"): 8,  # @ becccfe (2026-10-20)
    ("measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md", "### 8.8 After a behavior change, sweep the surfaces that describe and call it"): 7,  # @ becccfe (2026-10-20)
    ("measurement-discipline.md", "### 8.2 A broad verification gate is authoritative over an audit's enumerated file list"): 2,  # @ becccfe (2026-10-20)
    ("measurement-discipline.md", "### 8.3 Sanity-check a projected headline metric against the fixed extraction scope before starting"): 2,  # @ becccfe (2026-10-20)
    ("measurement-discipline.md", "### 8.5 Normalize an authored-markdown field on BOTH read and write — and test it with annotated, not clean, fixtures"): 3,  # @ becccfe (2026-10-20)
    ("measurement-discipline.md", "### 8.7 Verify the gate's input set before trusting its predicate"): 3,  # @ becccfe (2026-10-20)
    ("measurement-discipline.md", "### 8.9 A gate's recorded figure needs its own verification, separate from its reading"): 2,  # @ becccfe (2026-10-20)
    ("read-confirm-act-protocol.md", "### 1.2 Structural Findings Beyond Literal Scope"): 2,  # @ becccfe (2026-10-20)
    ("read-confirm-act-protocol.md", "#### Audit-Trail Requirement"): 2,  # @ becccfe (2026-10-20)
    ("review-classification.md", "## The Three Claims in a Finding"): 3,  # @ becccfe (2026-10-20)
    ("rule-authoring.md", "## 2b. Common Frontmatter Mistakes"): 2,  # @ becccfe (2026-10-20)
    ("scaffolding-hygiene-Part-2-DerivationAndParallelism.md", "## 16. Declared Parallelism Requires a Computed Write-Set Intersection"): 3,  # @ becccfe (2026-10-20)
    ("session-execution-protocol.md", "### 6.1 A Refactor's Blast Radius Exceeds Its Edit Set"): 2,  # @ becccfe (2026-10-20)
    ("session-plan-requirements.md", "### Scaffolding Phase Requirements (Plan Writing)"): 3,  # @ becccfe (2026-10-20)
    ("skill-authoring.md", "## 5b. Forked Execution Mistakes"): 2,  # @ becccfe (2026-10-20)
    ("skill-authoring.md", "## 7b. Tool Restriction Mistakes"): 2,  # @ becccfe (2026-10-20)
    ("task-content-fidelity.md", "### 9.A.8 Token Saver Large-File Ladder"): 2,  # @ becccfe (2026-10-20)
    ("task-content-fidelity.md", "### 9.A.14 Measure every Required Context row at scaffold close"): 2,  # @ becccfe (2026-10-20)
    ("task-file-and-tracking-requirements.md", "### Task File Template"): 3,  # @ becccfe (2026-10-20)
    ("verify-before-cite.md", "### 9.B.2 Identifier reconciliation against the live contract"): 2,  # @ becccfe (2026-10-20)
}


def measure(content: str) -> list[tuple[str, int]]:
    """Return ``(heading text, WRONG label count)`` per section, in file order."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    starts = {h.line: h.raw for h in extract_headings(content) if 2 <= h.level <= 4}
    sections = [[PREAMBLE, 0]]
    in_fence = False
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if idx in starts:
            sections.append([starts[idx], 0])
            continue
        if any(rx.search(line) for rx in _LABEL_RES):
            sections[-1][1] += 1
    return [(heading, count) for heading, count in sections]


def _corpus() -> dict[str, list[tuple[str, int]]]:
    return {p.name: measure(p.read_bytes().decode("utf-8")) for p in sorted(REFS_DIR.glob("*.md"))}


CORPUS = _corpus() if REFS_DIR.is_dir() else {}


def test_refs_dir_holds_markdown():
    print(f"PAIR_CONTRACT_REFS_DIR -> {REFS_DIR}")
    assert REFS_DIR.is_dir(), f"references directory not found: {REFS_DIR}"
    assert CORPUS, f"no *.md files in {REFS_DIR}"


def test_unexempted_sections_hold_at_most_one_wrong_label():
    failures = [
        f"FAIL {name} § {heading}: {count} WRONG labels, limit 1"
        for name, sections in CORPUS.items()
        for heading, count in sections
        if count > 1 and (name, heading) not in PAIR_EXEMPTIONS
    ]
    if failures:
        pytest.fail("\n".join(failures), pytrace=False)


def test_exempted_sections_do_not_exceed_recorded_count():
    failures = [
        f"EXCEEDS EXEMPTION {name} § {heading}: {count} > {PAIR_EXEMPTIONS[(name, heading)]}"
        for name, sections in CORPUS.items()
        for heading, count in sections
        if (name, heading) in PAIR_EXEMPTIONS and count > PAIR_EXEMPTIONS[(name, heading)]
    ]
    if failures:
        pytest.fail("\n".join(failures), pytrace=False)


def test_no_stale_exemptions():
    failures = []
    for name, heading in PAIR_EXEMPTIONS:
        if name not in CORPUS:
            if _OVERRIDE:
                continue
            measured = 0
        else:
            measured = max((c for h, c in CORPUS[name] if h == heading), default=0)
        if measured <= 1:
            failures.append(f"STALE EXEMPTION {name} § {heading}: measures {measured}, remove the entry")
    if failures:
        pytest.fail("\n".join(failures), pytrace=False)
