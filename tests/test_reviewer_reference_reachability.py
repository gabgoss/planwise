#!/usr/bin/env python3
"""Reachability/wiring regression tests for plan-reviewer sub-roles and
references/ files.

Two independent classes of "authored but unreachable" defect motivate this
suite, both previously real in this tree:

1. `agents/plan-reviewer.md` defines review sub-roles as `## Sub-role: {name}`
   headings, but nothing enforced that `handlers/review.md` Phase 2 actually
   spawns each one. Prior to commit f85ebcb (2026-08-15), three of the five
   `(NEW)` sub-roles -- Destructive-Path Reviewer, Verification-Gate
   Reviewer, Change-Surface Reviewer -- were fully defined (checklists,
   Check IDs, `references/*.md` pointers) but had no `Your assigned role:
   {name}` spawn block anywhere in `handlers/review.md`: they were dead
   documentation the team lead could never dispatch. Measured directly
   against that pre-fix tree (`git show f85ebcb~1:plugins/planwise/handlers/
   review.md`): `grep -c "Your assigned role:"` returned 7 (Combined, EI,
   Task, Dependency, Coverage, Scaffolding Hygiene, Design-Extension) against
   5 defined `(NEW)`-tagged sub-roles needing 5 matching spawn lines (2 of the
   5 -- Scaffolding Hygiene, Design-Extension -- already had spawn sites; the
   other 3 did not). Now there are 10 total `Your assigned role:` lines,
   covering all 5 sub-roles.

2. A file dropped under `references/` is never loaded unless some handler,
   skill, or agent cites its filename. Prior to commit 5c5d456 (2026-08-16),
   `references/context-loading-and-conservation.md` had zero citations
   anywhere under `handlers/`, `skills/`, or `agents/` -- authored, never
   wired into a load path. `handlers/plan.md` now cites it at its Required
   Reference #6.

Both classes are wiring defects invisible to a reader who only opens the
authoring file (plan-reviewer.md, or the orphaned reference itself) -- the
break lives in the *absence* of a citation somewhere else in the tree. This
suite reads the live shipped tree directly (no fixtures) so it regresses the
moment either link goes stale again, and reports the specific unreachable
member(s) by name, not just a count.

Run with:  python -m pytest tests/test_reviewer_reference_reachability.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

# Matches "## Sub-role: {name}" headings in agents/plan-reviewer.md, e.g.
# "## Sub-role: Destructive-Path Reviewer (NEW)".
_SUB_ROLE_HEADING_RE = re.compile(r"^## Sub-role:\s*(.+?)\s*$", re.MULTILINE)
# Strips a trailing authoring-marker parenthetical like "(NEW)" -- not part
# of the role name the spawn prompt's "Your assigned role: {name}" line uses.
_TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _extract_sub_role_names(plan_reviewer_text: str) -> list[str]:
    names = []
    for match in _SUB_ROLE_HEADING_RE.finditer(plan_reviewer_text):
        raw_name = match.group(1)
        clean_name = _TRAILING_PARENTHETICAL_RE.sub("", raw_name).strip()
        names.append(clean_name)
    return names


def _read_markdown_tree(*dirs: Path) -> str:
    """Concatenate the text of every *.md file under the given directories."""
    chunks = []
    for directory in dirs:
        if not directory.exists():
            continue
        for md_path in sorted(directory.rglob("*.md")):
            chunks.append(md_path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


class TestSubRoleSpawnReachability(unittest.TestCase):
    """Every sub-role defined in agents/plan-reviewer.md must have a spawn
    site in handlers/review.md, or the team lead can never dispatch it."""

    def test_every_defined_sub_role_has_a_spawn_site(self):
        plan_reviewer_path = PLUGIN_ROOT / "agents" / "plan-reviewer.md"
        review_handler_path = PLUGIN_ROOT / "handlers" / "review.md"

        sub_roles = _extract_sub_role_names(
            plan_reviewer_path.read_text(encoding="utf-8")
        )
        self.assertTrue(
            sub_roles,
            "no '## Sub-role:' headings found in agents/plan-reviewer.md -- "
            "parser/fixture regression, not a genuine zero-sub-role state",
        )

        review_text = review_handler_path.read_text(encoding="utf-8")
        unreachable = [
            name for name in sub_roles
            if f"Your assigned role: {name}" not in review_text
        ]

        self.assertEqual(
            unreachable,
            [],
            "sub-role(s) defined in agents/plan-reviewer.md have no spawn "
            "site ('Your assigned role: {name}') in handlers/review.md "
            f"Phase 2: {unreachable}",
        )


class TestReferencesFileReachability(unittest.TestCase):
    """Every file under references/ must be named/cited by at least one file
    under handlers/, skills/, or agents/, or it ships as dead weight nobody
    ever loads."""

    def test_every_reference_file_is_cited_somewhere(self):
        references_dir = PLUGIN_ROOT / "references"
        reference_files = sorted(references_dir.glob("*.md"))
        self.assertTrue(
            reference_files,
            "no files found under references/ -- parser/fixture regression, "
            "not a genuine empty references/ state",
        )

        citing_text = _read_markdown_tree(
            PLUGIN_ROOT / "handlers",
            PLUGIN_ROOT / "skills",
            PLUGIN_ROOT / "agents",
        )

        unreachable = [
            ref_path.name for ref_path in reference_files
            if ref_path.name not in citing_text
        ]

        self.assertEqual(
            unreachable,
            [],
            "reference file(s) under references/ are not named/cited by any "
            f"file under handlers/, skills/, or agents/: {unreachable}",
        )


if __name__ == "__main__":
    unittest.main()
