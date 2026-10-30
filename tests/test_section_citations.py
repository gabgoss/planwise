#!/usr/bin/env python3
"""Real-tree regression test for `§` section citations.

`check_section_citations.check_tree` resolves every `§` citation in the shipped
plugin tree against the headings of the file it names. A citation that points
at a section no file holds is a `dangling` finding. A citation whose named file
does not resolve is an `unresolved-target` finding.

This module reads the live shipped tree (no fixtures) and fails on any such
finding that is not in the reviewed constants below. The constants name the
citations that are deliberately not live pointers: history notes, quoted
examples, labels, and sections of a document the plugin does not ship. A
constant entry that no longer produces a finding fails too, so the list cannot
rot silently.

Dev-only: lives in tests/, which does not ship.

Run with:  python -m pytest tests/test_section_citations.py -q
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_section_citations

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
# tests/ -> plugin repo -> cloned-repos -> project root
OUTER_ROOT = Path(__file__).resolve().parents[3]
OUTER_RULES = OUTER_ROOT / ".claude" / "rules"
OUTER_CLAUDE_MD = OUTER_ROOT / "CLAUDE.md"

BAD_VERDICTS = ("dangling", "unresolved-target")

# Tree label: plugin 2928264 + session edits, 2026-10-20, check_section_citations.py
# Pinned total: 2404 findings (ok 2270, dangling 59, redirected 72, unresolved-target 3).
# Re-pin whenever the corpus grows or shrinks.
FINDINGS_FLOOR = 2163  # floor(0.9 * 2404)
# Instrument check: an empty or near-empty scan must not pass.
INSTRUMENT_MIN = 100

# Reviewed plugin findings. Each entry is (file relative to the plugin root, line).
# Reason codes: HISTORY = provenance or history note naming a past layout;
# EXAMPLE = quoted or worked example citation; LABEL = a check title or label,
# not a pointer; CONSUMER = a section of a document the consumer generates.
LEDGERED_PLUGIN = (
    ("references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md", 511),  # HISTORY: extraction note
    ("references/agent-orchestration-delegated-Part-3-CrossCuttingDispatchDiscipline.md", 537),  # HISTORY: extraction note
    ("references/agent-orchestration-delegated.md", 2),  # HISTORY: frontmatter provenance
    ("references/agent-orchestration-delegated.md", 8),  # HISTORY: provenance of the extraction
    ("references/agent-orchestration-delegated.md", 505),  # HISTORY: extraction note
    ("references/discovery-and-exit-criteria.md", 10),  # HISTORY: records the three-way split
    ("references/dispatch-batch-gate.md", 105),  # EXAMPLE: quotes a runner's internal pointer in an incident table
    ("references/dispatch-edit-surface-sweep.md", 100),  # EXAMPLE: worked example about another file's sections
    ("references/dispatch-edit-surface-sweep.md", 113),  # EXAMPLE: quoted citation in a callout table
    ("references/dispatch-edit-surface-sweep.md", 114),  # EXAMPLE: quoted citation in a callout table
    ("references/dispatch-edit-surface-sweep.md", 130),  # EXAMPLE: example section letters
    ("references/dispatch-edit-surface-sweep.md", 132),  # EXAMPLE: example section letters
    ("references/ei-citation-and-token-reconciliation.md", 2),  # HISTORY: frontmatter provenance
    ("references/ei-citation-and-token-reconciliation.md", 300),  # EXAMPLE: template text naming a design output's section
    ("references/ei-completeness.md", 2),  # HISTORY: frontmatter provenance
    ("references/ei-completeness.md", 180),  # EXAMPLE: prose about an example input's sections
    ("references/ei-completeness.md", 192),  # EXAMPLE: prose about an example input's sections
    ("references/ei-fidelity.md", 2),  # HISTORY: records sections that left the file
    ("references/ei-fidelity.md", 24),  # EXAMPLE: example citation forms
    ("references/ei-source-promise-integrity.md", 2),  # HISTORY: frontmatter provenance
    ("handlers/plan-Part-3-VerifyConfirmAndReview.md", 57),  # CONSUMER: a section of the generated master plan
    ("agents/plan-reviewer.md", 158),  # LABEL: check title copied from its canonical heading
    ("agents/review-discovery.md", 78),  # CONSUMER: a section of the generated fact sheet
    ("agents/review-discovery.md", 158),  # CONSUMER: a section of the generated fact sheet
    ("references/exit-criteria-fidelity.md", 397),  # LABEL: the canonical check-title heading
    ("references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", 348),  # EXAMPLE: sample value with stand-in file names
    ("references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", 364),  # EXAMPLE: sample value with stand-in file names
    ("references/measurement-discipline-Part-2-BehaviorChangeSurfaceSweeps.md", 315),  # HISTORY: names the former section numbering
    ("references/measurement-discipline.md", 9),  # HISTORY: provenance of the split
    ("references/measurement-discipline.md", 516),  # HISTORY: names the former section numbering
    ("references/read-confirm-act-protocol.md", 117),  # EXAMPLE: a wrong example about another document's sections
    ("references/read-confirm-act-protocol.md", 547),  # EXAMPLE: quotes a wrong entry in an incident table
    ("references/task-content-fidelity.md", 466),  # EXAMPLE: sample status cell citing an example artifact
    ("references/verification-gates.md", 48),  # EXAMPLE: quoted example citation form
    ("references/verify-anchor-against-artifact.md", 12),  # LABEL: names a numbering series, not a pointer
    ("references/verify-anchor-against-artifact.md", 60),  # EXAMPLE: incident narrative quoting lifted citations
)

# Reviewed outer findings, keyed the way the checker names an outer file
# ("rules/<name>.md", not ".claude/rules/<name>.md"). The outer roots are
# `.claude/rules/` (minus `.claude/rules/planwise/`) and `CLAUDE.md`.
LEDGERED_OUTER = (
    ("rules/hook-deny-contract.md", 214),  # CONSUMER: provenance note naming a file outside every root
    ("rules/plugin-identifier-isolation.md", 25),  # EXAMPLE: example of a forbidden citation form
    ("rules/promotion-sync-target-scoping.md", 36),  # EXAMPLE: the rule's own worked example of a dead anchor
    ("rules/promotion-sync-target-scoping.md", 43),  # EXAMPLE: the rule's own worked example of a dead anchor
    ("rules/promotion-sync-target-scoping.md", 73),  # EXAMPLE: example of the heading-text citation form
    ("rules/promotion-sync-target-scoping.md", 108),  # EXAMPLE: the rule's own worked example of a dead anchor
)

# One live (file, line) example per citation form the checker parses. A
# regression that stops parsing a form leaves its example without a finding.
FORM_EXAMPLES = (
    ("file in code span then section", "handlers/backlog.md", 186),
    ("plain path-prefixed", "agents/plan-reviewer.md", 181),
    ("link text", "references/session-planning-protocol.md", 313),
    ("link then section", "references/gate-old-home-citation-sweep.md", 76),
    ("table cell", "references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md", 14),
    ("en-dash range", "handlers/harvest.md", 51),
    ("heading words", "handlers/doctor-Part-3-TokenSaverAndBookkeepingReadGates.md", 74),
    ("heading words holding a comma", "handlers/lessons.md", 83),
    ("stage heading", "references/session-context-budget.md", 516),
    ("step heading with a dash title", "agents/rule-comparator.md", 73),
    ("three-level number", "references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md", 2),
    ("letter series", "references/verify-against-shipped-artifact.md", 393),
    ("letter series with a number", "references/verify-before-cite.md", 30),
    ("letter series with a suffix", "references/verify-backlog-citation-freshness.md", 8),
    ("bare continuation", "agents/plan-reviewer.md", 158),
    ("section then file", "references/gate-predicate-discrimination.md", 41),
    ("wrapped across a line break", "handlers/init.md", 54),
    ("frontmatter description", "references/gate-old-home-citation-sweep.md", 2),
)


def _bad(findings):
    return [f for f in findings if f.verdict in BAD_VERDICTS]


def _describe(findings):
    return "\n".join(
        f"  {f.file}:{f.line}  {f.citation!r}  {f.verdict}" for f in findings
    )


class SectionCitationRealTreeTests(unittest.TestCase):
    def test_shipped_tree_has_no_dangling_citation(self):
        findings = check_section_citations.check_tree(PLUGIN_ROOT)

        # Instrument check: an empty scan cannot pass.
        self.assertGreater(
            len(findings), INSTRUMENT_MIN, f"scan saw only {len(findings)} findings"
        )
        # Real floor, derived from the pinned tree total above.
        self.assertGreaterEqual(
            len(findings),
            FINDINGS_FLOOR,
            f"{len(findings)} findings is below the pinned floor {FINDINGS_FLOOR}; "
            "the scan lost files or forms (re-pin only if the corpus shrank on purpose)",
        )

        ledgered = set(LEDGERED_PLUGIN)
        bad = _bad(findings)
        unledgered = [f for f in bad if (f.file, f.line) not in ledgered]
        self.assertEqual(
            [],
            unledgered,
            "dangling or unresolved citations not in the reviewed list:\n"
            + _describe(unledgered),
        )

        # A stale constant entry must fail, so the list cannot rot.
        seen = {(f.file, f.line) for f in bad}
        stale = sorted(ledgered - seen)
        self.assertEqual(
            [], stale, f"reviewed entries that no longer produce a finding: {stale}"
        )

        # Form coverage: every listed form still produces a finding on its example line.
        seen_any = {(f.file, f.line) for f in findings}
        dropped = [
            f"{form} ({name}:{line})"
            for form, name, line in FORM_EXAMPLES
            if (name, line) not in seen_any
        ]
        self.assertEqual([], dropped, f"citation forms no longer parsed: {dropped}")

    @unittest.skipUnless(
        OUTER_RULES.is_dir() and OUTER_CLAUDE_MD.is_file(),
        "outer .claude/rules/ and CLAUDE.md not present (plugin repo checked out alone)",
    )
    def test_outer_roots_have_no_dangling_citation(self):
        findings = check_section_citations.check_tree(
            PLUGIN_ROOT,
            extra_roots=[OUTER_RULES, OUTER_CLAUDE_MD],
            exclude=[OUTER_RULES / "planwise"],
        )
        self.assertGreater(
            len(findings), INSTRUMENT_MIN, f"scan saw only {len(findings)} findings"
        )

        ledgered = set(LEDGERED_PLUGIN) | set(LEDGERED_OUTER)
        bad = _bad(findings)
        unledgered = [f for f in bad if (f.file, f.line) not in ledgered]
        self.assertEqual(
            [],
            unledgered,
            "dangling or unresolved citations not in the reviewed list:\n"
            + _describe(unledgered),
        )

        seen = {(f.file, f.line) for f in bad}
        stale = sorted(set(LEDGERED_OUTER) - seen)
        self.assertEqual(
            [], stale, f"reviewed outer entries that no longer produce a finding: {stale}"
        )
        # The outer roots were scanned, not silently dropped.
        outer_files = {f.file for f in findings if f.file.startswith("rules/")}
        self.assertTrue(outer_files, "no finding came from the outer rules root")


if __name__ == "__main__":
    unittest.main()
