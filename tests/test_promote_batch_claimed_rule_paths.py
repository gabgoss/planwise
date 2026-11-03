#!/usr/bin/env python3
"""The claimed-path check in the promote-batch workflow finds absent claimed rules.

Part 1 of the promote-batch workflow, section 4.5, pins one search pattern that
lists every `.claude/rules/` path a backlog item names. This test extracts that
pattern from the reference text itself, then runs it over a fixture backlog on
`tmp_path`. The fixture holds one open item and one archived completed item. They
claim three paths between them, and one of the three exists on disk. The check
must report exactly the two claimed paths that are absent.

Dev-only: lives in tests/, which does not ship.

Run with:  python -m pytest tests/test_promote_batch_claimed_rule_paths.py -q
"""

import re
from pathlib import Path

PART_1 = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "planwise"
    / "references"
    / "lessons-promote-batch-workflow-Part-1-ResolveAndGroup.md"
)
HEADING = "### 4.5 Existing-rule check"


def _section_45() -> str:
    """Return section 4.5: from its heading to the next `---` line."""
    lines = PART_1.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(HEADING))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "---")
    return "\n".join(lines[start:end])


def _pinned_pattern() -> re.Pattern:
    """Pull the single pinned `pattern='...'` string out of section 4.5."""
    found = re.findall(r"pattern='([^']+)'", _section_45())
    assert len(found) == 1, f"section 4.5 must hold exactly one pinned pattern, found {len(found)}"
    return re.compile(found[0])


def test_fixture_backlog_reports_both_absent_claimed_paths(tmp_path):
    pattern = _pinned_pattern()

    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "existing.md").write_text("# existing\n", encoding="utf-8")

    backlog = tmp_path / "backlog"
    (backlog / "Archive").mkdir(parents=True)
    (backlog / "BB-900-01-DOC-A.md").write_text(
        "---\nstatus: NOT_STARTED\n---\n\n"
        "Deliverable: `.claude/rules/absent-a.md` and `.claude/rules/existing.md`.\n",
        encoding="utf-8",
    )
    (backlog / "Archive" / "BB-901-01-DOC-B.md").write_text(
        "---\nstatus: COMPLETE\n---\n\nDeliverable: `.claude/rules/planwise/absent-b.md`.\n",
        encoding="utf-8",
    )

    sources = sorted(backlog.rglob("BB-*.md"))
    assert len(sources) == 2, "the walk must see both fixture items, Archive included"

    claimed = set()
    for source in sources:
        claimed.update(pattern.findall(source.read_text(encoding="utf-8")))
    assert len(claimed) == 3, "the pattern must see all three claimed paths before the disk filter"

    absent = {
        path[len(".claude/rules/") : -len(".md")]
        for path in claimed
        if not (tmp_path / path).exists()
    }
    assert absent == {"absent-a", "planwise/absent-b"}


def test_pattern_ignores_placeholder_paths():
    pattern = _pinned_pattern()
    assert pattern.search("`.claude/rules/{path}.md`") is None
    assert pattern.search("`.claude/rules/...md`") is None
