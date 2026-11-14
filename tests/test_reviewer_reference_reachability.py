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


_DELEGATED_BLOCK_ANCHOR = "The DELEGATED dispatch discipline ships in"


def delegated_block(review_text: str) -> str:
    """Return the DELEGATED reviewer block: the anchor line through the next code fence."""
    text = review_text.replace("\r\n", "\n")
    start = text.find(_DELEGATED_BLOCK_ANCHOR)
    if start == -1:
        return ""
    end = text.find("\n```", start)
    return text[start : end if end != -1 else len(text)]


def missing_delegated_files(review_text: str, expected: list[str]) -> list[str]:
    """Return each expected file name the DELEGATED reviewer block does not name."""
    block = delegated_block(review_text)
    return [name for name in expected if name not in block]


class TestDelegatedReviewerBlockNamesEveryPart(unittest.TestCase):
    """The Task Reviewer spawn block in handlers/review.md names every
    agent-orchestration-delegated*.md file, so no part ships unread.
    Names only: the block's section ranges are reviewable subsets, not the
    part table's ranges."""

    def _expected(self) -> list[str]:
        names = sorted(p.name for p in (PLUGIN_ROOT / "references").glob("agent-orchestration-delegated*.md"))
        self.assertGreaterEqual(len(names), 3, "glob saw fewer than three delegated files")
        return names

    def test_review_block_names_every_delegated_file(self):
        review_text = (PLUGIN_ROOT / "handlers" / "review.md").read_text(encoding="utf-8")
        self.assertTrue(delegated_block(review_text), "DELEGATED reviewer block not found")
        self.assertEqual(missing_delegated_files(review_text, self._expected()), [])

    def test_a_dropped_delegated_file_fails(self):
        review_text = (PLUGIN_ROOT / "handlers" / "review.md").read_text(encoding="utf-8")
        expected = self._expected()
        dropped = expected[-1]
        self.assertIn(dropped, delegated_block(review_text))
        mutated = review_text.replace(dropped, "agent-orchestration-delegated-removed.md")
        self.assertEqual(missing_delegated_files(mutated, expected), [dropped])


_SPAWN_PROMPT_CHECK_NUMBER_RE = re.compile(r"Execute Checks? \d|checklist \(Checks \d")
_DESTRUCTIVE_SUB_ROLE = "Destructive-Path Reviewer"
_AGENT_CHECK_LINE_RE = re.compile(r"^- Check (\d+)\b", re.MULTILINE)
_REFERENCE_CHECK_HEADING_RE = re.compile(r"^#{2,5} Reviewer Check (\d+)\b", re.MULTILINE)


def spawn_prompt_check_number_lines(review_text: str) -> list[str]:
    """Return each line of handlers/review.md that names a check number in a spawn prompt."""
    text = review_text.replace("\r\n", "\n")
    return [line for line in text.split("\n") if _SPAWN_PROMPT_CHECK_NUMBER_RE.search(line)]


def sub_roles_missing_from_review(review_text: str, sub_roles: list[str]) -> list[str]:
    """Return each sub-role name that handlers/review.md never defers to by heading."""
    text = review_text.replace("\r\n", "\n")
    return [name for name in sub_roles if f"## Sub-role: {name}" not in text]


def sub_role_section(plan_reviewer_text: str, name: str) -> str:
    """Return the body of one `## Sub-role: {name}` section, up to the next `## ` heading."""
    text = plan_reviewer_text.replace("\r\n", "\n")
    match = re.search(rf"^## Sub-role:\s*{re.escape(name)}\b[^\n]*\n", text, re.MULTILINE)
    if match is None:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def agent_check_ids(plan_reviewer_text: str, name: str) -> set[str]:
    """Return the Check IDs listed as `- Check NNN` lines inside one sub-role section."""
    return set(_AGENT_CHECK_LINE_RE.findall(sub_role_section(plan_reviewer_text, name)))


def reference_check_ids(reference_text: str) -> set[str]:
    """Return the Check IDs of every `Reviewer Check NNN` heading in a reference file."""
    return set(_REFERENCE_CHECK_HEADING_RE.findall(reference_text.replace("\r\n", "\n")))


class TestSpawnPromptsNameNoCheckNumbers(unittest.TestCase):
    """The `## Sub-role:` sections of agents/plan-reviewer.md are the single
    check list. No spawn prompt in handlers/review.md names a check number,
    and each sub-role is named there so its prompt defers to its own section."""

    def _review_text(self) -> str:
        return (PLUGIN_ROOT / "handlers" / "review.md").read_text(encoding="utf-8")

    def test_no_check_numbers_and_every_sub_role_named(self):
        review_text = self._review_text()
        self.assertEqual(spawn_prompt_check_number_lines(review_text), [])
        sub_roles = _extract_sub_role_names(
            (PLUGIN_ROOT / "agents" / "plan-reviewer.md").read_text(encoding="utf-8")
        )
        self.assertTrue(sub_roles, "no '## Sub-role:' headings found in agents/plan-reviewer.md")
        self.assertEqual(sub_roles_missing_from_review(review_text, sub_roles), [])

    def test_a_reinserted_check_number_directive_fails(self):
        mutated = self._review_text() + "\n    Execute Checks 072-073 from your protocol.\n"
        self.assertEqual(
            spawn_prompt_check_number_lines(mutated),
            ["    Execute Checks 072-073 from your protocol."],
        )


class TestDestructivePathReferenceParity(unittest.TestCase):
    """The Destructive-Path sub-role lists exactly the Reviewer Check headings
    of references/destructive-change-requirements.md, so a check added to the
    reference cannot be dropped from the reviewer silently."""

    def _agent_text(self) -> str:
        return (PLUGIN_ROOT / "agents" / "plan-reviewer.md").read_text(encoding="utf-8")

    def _reference_ids(self) -> set[str]:
        reference = PLUGIN_ROOT / "references" / "destructive-change-requirements.md"
        ids = reference_check_ids(reference.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(ids), 3, "fewer than three Reviewer Check headings found")
        return ids

    def test_sub_role_checks_equal_reference_headings(self):
        agent_ids = agent_check_ids(self._agent_text(), _DESTRUCTIVE_SUB_ROLE)
        self.assertGreaterEqual(len(agent_ids), 3, "fewer than three '- Check' lines in the sub-role")
        self.assertEqual(agent_ids ^ self._reference_ids(), set())

    def test_a_dropped_check_line_is_reported(self):
        agent_text = self._agent_text().replace("\r\n", "\n")
        dropped_lines = [ln for ln in agent_text.split("\n") if ln.startswith("- Check 122 ")]
        self.assertEqual(len(dropped_lines), 1)
        mutated = agent_text.replace(dropped_lines[0] + "\n", "")
        agent_ids = agent_check_ids(mutated, _DESTRUCTIVE_SUB_ROLE)
        self.assertEqual(agent_ids ^ self._reference_ids(), {"122"})


if __name__ == "__main__":
    unittest.main()
