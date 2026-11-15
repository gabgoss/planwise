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
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import check_section_citations

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
# tests/ -> plugin repo -> cloned-repos -> project root
OUTER_ROOT = Path(__file__).resolve().parents[3]
OUTER_RULES = OUTER_ROOT / ".claude" / "rules"
OUTER_CLAUDE_MD = OUTER_ROOT / "CLAUDE.md"

BAD_VERDICTS = ("dangling", "unresolved-target", "unreadable")

# Tree label: plugin 2928264 + session edits, 2026-10-20, check_section_citations.py
# Pinned total: 2404 findings (ok 2270, dangling 59, redirected 72, unresolved-target 3).
# Re-pin whenever the corpus grows or shrinks.
FINDINGS_FLOOR = 2163  # floor(0.9 * 2404)
# Instrument check: an empty or near-empty scan must not pass.
INSTRUMENT_MIN = 100

# Reviewed plugin findings. Each entry is (file relative to the plugin root,
# snippet, citation as the finding prints it). The snippet is a run of text
# found on exactly one line of that file, so the entry names its line by
# content and no line number is stored. `_resolved` finds the line at run time
# and rebuilds the `(file, line, citation)` key, the same three-field key as a
# `path:line:citation` ledger entry, so a new citation added to a reviewed
# line fails instead of hiding behind the line. A line inserted above the
# reviewed line moves nothing here. An edit that removes or repeats the
# snippet fails the entry by name.
# Reason codes: HISTORY = provenance or history note naming a past layout;
# EXAMPLE = quoted or worked example citation; LABEL = a check title or label,
# not a pointer; CONSUMER = a section of a document the consumer generates.
LEDGERED_PLUGIN = (
    ("references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md", "(2026-09-06) because", "§12"),  # HISTORY: extraction note
    ("references/agent-orchestration-delegated-Part-4-DeliveryLivenessAndRemediation.md", "Verify-Before-Acting", "§12"),  # HISTORY: extraction note
    ("references/agent-orchestration-delegated.md", "dispatch discipline,", "§12"),  # HISTORY: frontmatter provenance
    ("references/agent-orchestration-delegated.md", "Operational dispatch", "§12"),  # HISTORY: provenance of the extraction
    ("references/agent-orchestration-delegated.md", "Verify-Before-Acting", "§12"),  # HISTORY: extraction note
    ("references/discovery-and-exit-criteria.md", "into the two sibling", "§16"),  # HISTORY: records the three-way split
    ("references/discovery-and-exit-criteria.md", "into the two sibling", "§17"),  # HISTORY: records the three-way split
    ("references/discovery-and-exit-criteria.md", "into the two sibling", "§21"),  # HISTORY: records the three-way split
    ("references/dispatch-edit-surface-sweep.md", "incremental Recovery", "§4.A"),  # EXAMPLE: quoted citation in a callout table
    ("references/dispatch-edit-surface-sweep.md", "| `Follow §4.B below", "§4.B"),  # EXAMPLE: quoted citation in a callout table
    ("references/ei-citation-and-token-reconciliation.md", "citation propagation", "§5"),  # HISTORY: frontmatter provenance
    ("references/ei-citation-and-token-reconciliation.md", "citation propagation", "§8"),  # HISTORY: frontmatter provenance
    ("references/ei-citation-and-token-reconciliation.md", "3. Record in task Ke", "§10"),  # EXAMPLE: template text naming a design output's section
    ("references/ei-completeness.md", "cluster enumeration,", "§9"),  # HISTORY: frontmatter provenance
    ("references/ei-fidelity.md", "threshold alignment,", "§5"),  # HISTORY: records sections that left the file
    ("references/ei-fidelity.md", "threshold alignment,", "§11"),  # HISTORY: records sections that left the file
    ("references/ei-fidelity.md", "`ei-fidelity.md` was", "§9.1"),  # EXAMPLE: example citation forms
    ("references/ei-fidelity.md", "`ei-fidelity.md` was", "§10.2"),  # EXAMPLE: example citation forms
    ("references/ei-source-promise-integrity.md", "a brief that cites a", "§10"),  # HISTORY: frontmatter provenance
    ("references/ei-source-promise-integrity.md", "a brief that cites a", "§11"),  # HISTORY: frontmatter provenance
    ("handlers/plan-Part-3-VerifyConfirmAndReview.md", "ecisions (Locked). R", "§ Decisions"),  # CONSUMER: a section of the generated master plan
    ("agents/plan-reviewer.md", "16 Cross-Layer Cohor", "§15"),  # LABEL: check title copied from its canonical heading
    ("agents/review-discovery.md", "be measured, it gets", "§4"),  # CONSUMER: a section of the generated fact sheet
    ("agents/review-discovery.md", "number of rows measu", "§4"),  # CONSUMER: a section of the generated fact sheet
    ("references/exit-criteria-fidelity.md", "Reviewer Check 045 —", "§15"),  # LABEL: the canonical check-title heading
    ("references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "as fragments land (a", "§1"),  # EXAMPLE: sample value with stand-in file names
    ("references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "as fragments land (a", "§2"),  # EXAMPLE: sample value with stand-in file names
    ("references/lessons-promote-batch-workflow-Part-2-DraftAndWrite.md", "**and** `applied-as:", "§1"),  # EXAMPLE: sample value with stand-in file names
    ("references/read-confirm-act-protocol.md", "points into §9; body", "§11"),  # EXAMPLE: a wrong example about another document's sections
    ("references/read-confirm-act-protocol.md", "points into §9; body", "§12"),  # EXAMPLE: a wrong example about another document's sections
    ("references/read-confirm-act-protocol.md", "points into §9; body", "§13"),  # EXAMPLE: a wrong example about another document's sections
    ("references/read-confirm-act-protocol.md", "points into §9; body", "§9"),  # EXAMPLE: a wrong example about another document's sections
    ("references/read-confirm-act-protocol.md", "| read the **shipped", "§1.15"),  # EXAMPLE: quotes a wrong entry in an incident table
    ("references/read-confirm-act-protocol.md", "| read the **shipped", "§1.18"),  # EXAMPLE: quotes a wrong entry in an incident table
    ("references/task-content-fidelity.md", "An item the evidence", "§3"),  # EXAMPLE: sample status cell citing an example artifact
    ("references/verify-anchor-against-artifact.md", "file carries its own", "§9.B"),  # LABEL: names a numbering series, not a pointer
    ("references/verify-anchor-against-artifact.md", "lifted verbatim from", "§1.18"),  # EXAMPLE: incident narrative quoting lifted citations
    ("references/verify-anchor-against-artifact.md", "lifted verbatim from", "§1.22"),  # EXAMPLE: incident narrative quoting lifted citations
    ("references/verify-anchor-against-artifact.md", "lifted verbatim from", "§11.2"),  # EXAMPLE: incident narrative quoting lifted citations
)

# Reviewed outer findings, keyed the way the checker names an outer file
# ("rules/<name>.md", not ".claude/rules/<name>.md"), with the same three
# fields: file, snippet, citation. The snippet works as it does for the plugin
# list above. The outer roots are `.claude/rules/` (minus
# `.claude/rules/planwise/`) and `CLAUDE.md`.
_SYNC_73 = (
    "§ Read Gates and Large-File Read Tactics` rather than `§13`. "
    "A refactor that moves a section between files renumbers one tree and not the other"
)
LEDGERED_OUTER = (
    ("rules/hook-deny-contract.md", "source specification", "§4"),  # CONSUMER: provenance note naming a file outside every root
    ("rules/hook-deny-contract.md", "source specification", "§6"),  # CONSUMER: provenance note naming a file outside every root
    ("rules/plugin-identifier-isolation.md", "a lesson (LL-XXX) or", "§1.4"),  # EXAMPLE: example of a forbidden citation form
    ("rules/promotion-sync-target-scoping.md", "sibling plugin files", "§13"),  # EXAMPLE: the rule's own worked example of a dead anchor
    ("rules/promotion-sync-target-scoping.md", "The dev tree is what", "§12"),  # EXAMPLE: the rule's own worked example of a dead anchor
    ("rules/promotion-sync-target-scoping.md", "The dev tree is what", "§13"),  # EXAMPLE: the rule's own worked example of a dead anchor
    ("rules/promotion-sync-target-scoping.md", "numbered one** where", _SYNC_73),  # EXAMPLE: example of the heading-text citation form
    ("rules/promotion-sync-target-scoping.md", "a plan review caught", "§13"),  # EXAMPLE: the rule's own worked example of a dead anchor
)

# One live example per citation form the checker parses, as (form, file,
# snippet). The snippet names the example line by content, as in the ledgers
# above. A regression that stops parsing a form leaves its example line without
# a finding. These entries assert that a line still yields some finding, they
# subtract nothing, so no citation can hide behind them.
FORM_EXAMPLES = (
    ("file in code span then section", "handlers/backlog.md", "items, or multi-item"),
    ("plain path-prefixed", "agents/plan-reviewer.md", "ndocumented Design E"),
    ("link text", "references/session-planning-protocol.md", "echo across all plan"),
    ("link then section", "references/gate-old-home-citation-sweep.md", "after a renumbering,"),
    ("table cell", "references/agent-orchestration-delegated.md", "| Dispatch mechanics"),
    ("en-dash range", "handlers/harvest.md", "estration-delegated."),
    ("heading words", "handlers/doctor-Part-3-TokenSaverAndBookkeepingReadGates.md", "never restates them:"),
    ("heading words holding a comma", "handlers/lessons.md", "hub) and display its"),
    ("stage heading", "references/session-context-budget.md", "yet be unreadable in"),
    ("step heading with a dash title", "agents/rule-comparator.md", "`confidence` = worst"),
    ("three-level number", "references/agent-orchestration-delegated-Part-2-DispatchMechanicsAndReturns.md", "dispatch discipline,"),
    ("letter series", "references/verify-against-shipped-artifact.md", "regenerated when the"),
    ("letter series with a number", "references/verify-before-cite.md", "the general rule and"),
    ("letter series with a suffix", "references/verify-backlog-citation-freshness.md", "that both operate on"),
    ("bare continuation", "agents/plan-reviewer.md", "16 Cross-Layer Cohor"),
    ("section then file", "references/gate-predicate-discrimination.md", "the pattern and once"),
    ("wrapped across a line break", "handlers/init.md", "Inference Defaults ("),
    ("frontmatter description", "references/gate-old-home-citation-sweep.md", "An old-home citation"),
)


def _bad(findings):
    return [f for f in findings if f.verdict in BAD_VERDICTS]


def _key(finding):
    """The three-field key of a reviewed entry: file, line, printed citation."""
    return (finding.file, finding.line, finding.citation)


def _resolve(path, snippet):
    """The 1-based line of `path` that holds `snippet`.

    Lines are split the way the checker splits them (CRLF and lone CR become
    LF, then split on LF), so the number matches a finding's `line`. Raises
    ValueError when no line or more than one line holds the snippet.
    """
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    hits = [n for n, line in enumerate(text.split("\n"), start=1) if snippet in line]
    if not hits:
        raise ValueError("snippet matches no line")
    if len(hits) > 1:
        raise ValueError(f"snippet is not unique, it matches lines {hits}")
    return hits[0]


def _resolved(entries, paths):
    """Map `(file, snippet, citation)` entries to `(file, line, citation)` keys.

    `paths` maps a finding's `file` to its absolute `path`. Every entry that
    cannot resolve (file not scanned, snippet absent, snippet repeated) is
    collected, and one AssertionError names them all.
    """
    keys = set()
    problems = []
    for name, snippet, citation in entries:
        if name not in paths:
            problems.append(f"  ({name!r}, {snippet!r}, {citation!r}): file not scanned")
            continue
        try:
            keys.add((name, _resolve(paths[name], snippet), citation))
        except ValueError as exc:
            problems.append(f"  ({name!r}, {snippet!r}, {citation!r}): {exc}")
    if problems:
        raise AssertionError("reviewed entries that cannot resolve:\n" + "\n".join(problems))
    return keys


def _describe(findings):
    return "\n".join(
        f"  {f.file}:{f.line}  {f.citation!r}  {f.verdict}" for f in findings
    )


def _form_lines(paths):
    """FORM_EXAMPLES resolved to `(form, file, line)` rows."""
    entries = [(name, snippet, form) for form, name, snippet in FORM_EXAMPLES]
    return sorted((form, name, line) for name, line, form in _resolved(entries, paths))


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

        paths = {f.file: f.path for f in findings}
        ledgered = _resolved(LEDGERED_PLUGIN, paths)
        bad = _bad(findings)
        unledgered = [f for f in bad if _key(f) not in ledgered]
        self.assertEqual(
            [],
            unledgered,
            "dangling or unresolved citations not in the reviewed list:\n"
            + _describe(unledgered),
        )

        # A stale constant entry must fail, so the list cannot rot.
        seen = {_key(f) for f in bad}
        stale = sorted(ledgered - seen)
        self.assertEqual(
            [], stale, f"reviewed entries that no longer produce a finding: {stale}"
        )

        # Form coverage: every listed form still produces a finding on its example line.
        seen_any = {(f.file, f.line) for f in findings}
        dropped = [
            f"{form} ({name}:{line})"
            for form, name, line in _form_lines(paths)
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

        paths = {f.file: f.path for f in findings}
        ledgered_outer = _resolved(LEDGERED_OUTER, paths)
        ledgered = _resolved(LEDGERED_PLUGIN, paths) | ledgered_outer
        bad = _bad(findings)
        unledgered = [f for f in bad if _key(f) not in ledgered]
        self.assertEqual(
            [],
            unledgered,
            "dangling or unresolved citations not in the reviewed list:\n"
            + _describe(unledgered),
        )

        seen = {_key(f) for f in bad}
        stale = sorted(ledgered_outer - seen)
        self.assertEqual(
            [], stale, f"reviewed outer entries that no longer produce a finding: {stale}"
        )
        # The outer roots were scanned, not silently dropped.
        outer_files = {f.file for f in findings if f.file.startswith("rules/")}
        self.assertTrue(outer_files, "no finding came from the outer rules root")


_FakeFinding = namedtuple("_FakeFinding", "file line citation verdict")


class SnippetResolverTests(unittest.TestCase):
    """The snippet resolver, on a temporary file, in both directions."""

    NAME = "references/sample.md"
    SNIPPET = "the reviewed line"

    def _write(self, tmp, lines):
        path = Path(tmp) / "sample.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {self.NAME: str(path)}

    def test_inserted_line_above_moves_line_by_one_and_entry_resolves(self):
        entry = [(self.NAME, self.SNIPPET, "§9")]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(tmp, ["intro", f"{self.SNIPPET} cites §9", "tail"])
            self.assertEqual({(self.NAME, 2, "§9")}, _resolved(entry, paths))
            paths = self._write(
                tmp, ["intro", "an inserted line", f"{self.SNIPPET} cites §9", "tail"]
            )
            self.assertEqual({(self.NAME, 3, "§9")}, _resolved(entry, paths))

    def test_edited_away_snippet_fails_naming_the_entry(self):
        entry = [(self.NAME, self.SNIPPET, "§9")]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(tmp, ["intro", "the line was reworded, cites §9", "tail"])
            with self.assertRaises(AssertionError) as ctx:
                _resolved(entry, paths)
        message = str(ctx.exception)
        self.assertIn(self.NAME, message)
        self.assertIn(self.SNIPPET, message)
        self.assertIn("§9", message)
        self.assertIn("matches no line", message)

    def test_snippet_on_two_lines_fails_as_not_unique(self):
        entry = [(self.NAME, self.SNIPPET, "§9")]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(
                tmp, [f"{self.SNIPPET} cites §9", "middle", f"{self.SNIPPET} again"]
            )
            with self.assertRaises(AssertionError) as ctx:
                _resolved(entry, paths)
        message = str(ctx.exception)
        self.assertIn(self.NAME, message)
        self.assertIn("not unique", message)

    def test_resolved_entry_without_a_matching_bad_finding_is_stale(self):
        entries = [(self.NAME, self.SNIPPET, "§9"), (self.NAME, self.SNIPPET, "§10")]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(tmp, ["intro", f"{self.SNIPPET} cites §9", "tail"])
            ledgered = _resolved(entries, paths)
        # Only the §9 citation still produces a finding on the resolved line.
        bad = [_FakeFinding(self.NAME, 2, "§9", "dangling")]
        seen = {_key(f) for f in bad}
        self.assertEqual([(self.NAME, 2, "§10")], sorted(ledgered - seen))


if __name__ == "__main__":
    unittest.main()
