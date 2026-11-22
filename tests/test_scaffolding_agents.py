#!/usr/bin/env python3
"""Contract pins for the three scaffolding agents.

The orchestrator hands a sprint to the extractor, the extractor's status block
feeds the scaffolder, and the harmonizer grades the whole pass. The agents are
prose, so the field names one party writes and the next reads can drift apart
with no error. These tests pin the model and effort values, the prohibitions
every agent states in words, the status-block fields, the handoff fields each
agent reads, the template headings the scaffolder carries, and the gate the
harmonizer names. PlanAuthorContractTests pins the plan-author agent's bodies-file
contract the same way, because the plan handler reads its status block.

Test-only override: the environment variable PLANWISE_TEST_AGENTS_DIR
redirects ONLY the agents directory, so a mutation run reads a scratch copy.
It is unset in a normal run, and the default run reads the real agents folder.
The templates are always read from their real path. The status-block fields
and the handoff fields live in literal tables in this file, so no run skips them.

Run with:  python -m pytest tests/test_scaffolding_agents.py -q
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import lint_execution_input as lint_ei
import lint_execution_input_plan as lint_plan

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
AGENTS = Path(os.environ.get("PLANWISE_TEST_AGENTS_DIR") or PLUGIN / "agents")
TEMPLATES = PLUGIN / "templates"

EXTRACTOR = AGENTS / "ei-extractor.md"
SCAFFOLDER = AGENTS / "sprint-scaffolder.md"
HARMONIZER = AGENTS / "scaffold-harmonizer.md"
PLAN_AUTHOR = AGENTS / "plan-author.md"
ALL_AGENTS = [EXTRACTOR, SCAFFOLDER, HARMONIZER]

# agent file -> (model, effort)
PINNED = {
    EXTRACTOR: ("opus", "high"),
    SCAFFOLDER: ("opus", "high"),
    HARMONIZER: ("sonnet", "medium"),
}

TEMPLATE_FILES = ("orchestration.md", "sprint-plan.md", "recovery.md", "task-file.md")

# These tables pin the scaffolding pipeline's handoff contract. A change to an
# agent's status block or inputs updates them in the same commit.
STATUS_FIELDS = {
    EXTRACTOR: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "EI_SECTION_MAP", "SOURCE_TOKENS",
        "EI_TOKENS", "DEFERRED_TOKENS", "RETENTION_PCT", "EMPTY_SECTIONS", "OPEN_QUESTIONS",
        "KEY_FINDINGS", "ISSUES",
    ),
    SCAFFOLDER: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "FILL_REMAINING", "STRAY_H2",
        "SPAN_ROWS_REPOINTED", "OPEN_QUESTIONS", "KEY_FINDINGS", "ISSUES",
    ),
    HARMONIZER: (
        "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "DEVIATIONS_BEFORE",
        "DEVIATIONS_AFTER", "EDITS_APPLIED", "STRAY_H2", "FILL_REMAINING", "KEY_FINDINGS", "ISSUES",
    ),
}

# (field, agent whose file must name it): one pair per field an agent reads.
AGENT_READS = (
    ("plugin_root", EXTRACTOR),
    ("plugin_root", SCAFFOLDER),
    ("plugin_root", HARMONIZER),
    ("planwise_root", SCAFFOLDER),
    ("abbrev", EXTRACTOR),
    ("abbrev", SCAFFOLDER),
    ("abbrev", HARMONIZER),
    ("sprint_id", EXTRACTOR),
    ("sprint_id", SCAFFOLDER),
    ("sprint_folder", EXTRACTOR),
    ("sprint_folder", SCAFFOLDER),
    ("meta_root", EXTRACTOR),
    ("plan_root", HARMONIZER),
    ("sprint_ids", HARMONIZER),
    ("spec_path", EXTRACTOR),
    ("spec_path", SCAFFOLDER),
    ("source_map", EXTRACTOR),
    ("ei_sections", EXTRACTOR),
    ("deferred_targets", EXTRACTOR),
    ("ei_paths", SCAFFOLDER),
    ("ei_section_map", SCAFFOLDER),
    ("write_set", SCAFFOLDER),
    ("cross_sprint_markers", SCAFFOLDER),
    ("naming_scheme", SCAFFOLDER),
    ("lessons_dir", SCAFFOLDER),
    ("EI_SECTION_MAP", SCAFFOLDER),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter_keys(path: Path) -> dict:
    """Return the top-level `key: value` pairs of the YAML frontmatter block.

    Comment lines are skipped. A folded or literal block (`key: >` or `key: |`)
    takes its indented continuation lines, joined by single spaces.
    """
    lines = _read(path).splitlines()
    assert lines and lines[0].strip() == "---", f"{path.name} has no frontmatter"
    keys = {}
    block_key = None
    for line in lines[1:]:
        if line.strip() == "---":
            return keys
        if line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            if block_key is not None and line.strip():
                keys[block_key] = f"{keys[block_key]} {line.strip()}".strip()
            continue
        block_key = None
        if ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if value[:1] in (">", "|"):
                block_key, value = key, ""
            keys[key] = value
    raise AssertionError(f"{path.name} frontmatter is not closed")


def _tool_list(value: str) -> list:
    """Split a frontmatter tool line such as `Read, Write, Glob` into names."""
    return [name.strip() for name in value.split(",") if name.strip()]


def _section(text: str, heading: str) -> str:
    """Return the body under `heading` up to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.rstrip() == heading:
            break
    else:
        raise AssertionError(f"heading {heading!r} not found")
    body = []
    for line in lines[start + 1:]:
        stripped = line.lstrip("#")
        line_level = len(line) - len(stripped)
        if 0 < line_level <= level and stripped.startswith(" "):
            break
        body.append(line)
    return "\n".join(body)


def _h2_set(text: str) -> set:
    """Return every `## ` heading line of `text`, with a trailing marker comment stripped."""
    found = set()
    for line in text.splitlines():
        if line.startswith("## "):
            found.add(re.sub(r"\s*<!--.*?-->\s*$", "", line).strip())
    return found


class ScaffoldingAgentContractTests(unittest.TestCase):
    def test_pinned_model_and_effort_per_agent(self):
        for path, (model, effort) in PINNED.items():
            keys = _frontmatter_keys(path)
            with self.subTest(agent=path.name):
                self.assertEqual(keys.get("model"), model)
                self.assertEqual(keys.get("effort"), effort)
                self.assertNotIn("background", keys)
                self.assertTrue(keys.get("description"), "folded description parsed empty")

    def test_no_agent_names_the_question_tool_or_plan_mode(self):
        for path in ALL_AGENTS:
            text = _read(path)
            for literal in ("AskUserQuestion", "EnterPlanMode"):
                with self.subTest(agent=path.name, literal=literal):
                    self.assertNotIn(literal, text)

    def test_status_block_fields(self):
        for path, fields in STATUS_FIELDS.items():
            status_block = _section(_read(path), "## Status Block")
            for field in fields:
                with self.subTest(agent=path.name, field=field):
                    self.assertRegex(status_block, rf"(?m)^{field}:")

    def test_handoff_fields_named_by_reader(self):
        for field, path in AGENT_READS:
            with self.subTest(agent=path.name, field=field):
                self.assertRegex(_read(path), re.compile(re.escape(field), re.IGNORECASE))

    def test_scaffolder_carries_template_headers(self):
        carried = _h2_set(_read(SCAFFOLDER))
        for name in TEMPLATE_FILES:
            wanted = _h2_set(_read(TEMPLATES / name))
            self.assertTrue(wanted, f"{name} yielded no headings")
            for heading in sorted(wanted):
                with self.subTest(template=name, heading=heading):
                    self.assertIn(heading, carried)

    def test_harmonizer_names_the_gate(self):
        text = _read(HARMONIZER)
        self.assertIn("scripts/scaffold_deviations.py", text)
        self.assertIn("deviations: A=", text)

    def test_scaffolder_file_cap_and_handler_no_status_block_route(self):
        """The agent cannot see its turn counter, so a file cap and a skip rule stand
        in for the `maxTurns` row, and the handler routes a dispatch that returns no block."""
        agent = _read(SCAFFOLDER)
        self.assertIn("Fill at most 8 files per dispatch", agent)
        self.assertIn("skip a rendered file whose `<!-- FILL:` count is already 0", agent)
        self.assertNotIn("exceed `maxTurns`", agent)
        handler = _read(PLUGIN / "handlers" / "plan-scaffolding.md")
        gate = handler.split("**Scaffolder gate**", 1)[1].split("**Harmonizer gate**", 1)[0]
        self.assertIn("no status block", gate)
        self.assertIn("references/dispatch-boundary-evidence.md", gate)

    def test_extractor_and_harmonizer_write_as_they_go_and_each_gate_routes_no_block(self):
        """The agents cannot see their turn counter, so each leaves resumable state on disk
        and the handler gives each gate its own route for a dispatch that returns no block."""
        extractor = _read(EXTRACTOR)
        harmonizer = _read(HARMONIZER)
        for name, text in (("extractor", extractor), ("harmonizer", harmonizer)):
            with self.subTest(agent=name):
                self.assertNotIn("exceed `maxTurns`", text)
                self.assertNotIn("turn budget", text)
        self.assertIn("EI-PENDING", extractor)
        # The marker must not read as a scaffolder work-set marker.
        self.assertNotIn("<!-- FILL", extractor.replace("`<!-- FILL:`", ""))
        tools_line = next(line for line in extractor.splitlines() if line.startswith("tools:"))
        self.assertRegex(tools_line, r"\bEdit\b")
        self.assertIn("as soon as the gate names it", harmonizer)
        handler = _read(PLUGIN / "handlers" / "plan-scaffolding.md")
        extractor_gate = handler.split("**Extractor gate**", 1)[1].split("**Scaffolder gate**", 1)[0]
        scaffolder_gate = handler.split("**Scaffolder gate**", 1)[1].split("**Harmonizer gate**", 1)[0]
        harmonizer_gate = handler.split("**Harmonizer gate**", 1)[1].split("**Stalled re-dispatch.**", 1)[0]
        self.assertIn("no status block", extractor_gate)
        self.assertIn("EI-PENDING", extractor_gate)
        self.assertIn("no status block", harmonizer_gate)
        self.assertIn("scripts/scaffold_deviations.py", harmonizer_gate)
        self.assertNotIn("ei-extractor", scaffolder_gate)
        self.assertNotIn("turn budget", handler)

    def test_fill_count_searches_the_marker_not_the_bare_word(self):
        """The Sprint Plan template prose names the word FILL ("CONSUMES FILL"), so a count
        of the bare word reads template prose as a remaining marker. Every file that counts
        markers names `<!-- FILL:` as the search pattern."""
        handler = _read(PLUGIN / "handlers" / "plan-scaffolding.md")
        files = {"harmonizer": _read(HARMONIZER), "scaffolder": _read(SCAFFOLDER), "handler": handler}
        for name, text in files.items():
            with self.subTest(file=name):
                self.assertIn("`<!-- FILL:`", text)
                self.assertNotRegex(
                    text, r"(?i)(literal|for|count|search)\s+`FILL`(?!_)|`FILL`\s+(count|search)"
                )
        self.assertIn("literal `<!-- FILL:`", files["harmonizer"])
        self.assertIn("(CONSUMES FILL)", _read(PLUGIN / "templates" / "sprint-plan.md"))

    def test_extractor_reconcile_states_the_cross_tier_note_the_lint_reads(self):
        """Lint rule cross-tier-note blocks a Cross-References section cited from sources of
        different tiers when no Note paragraph in the same Part names them all. The extractor
        states that rule in Step 3, and its Note label is the one the lint matches."""
        reconcile = _section(_read(EXTRACTOR), "## Step 3: RECONCILE")
        paragraph = next(
            (p for p in reconcile.split("\n\n") if p.startswith("**Cross-tier Note.**")), ""
        )
        self.assertTrue(paragraph, "Step 3 has no Cross-tier Note paragraph")
        label = "**Note (cross-tier duplicate preserved):**"
        self.assertIn(label, paragraph)
        self.assertTrue(lint_ei.NOTE_RE.search(label), "the extractor's label no longer matches the lint")
        self.assertIn("`Spec #{N} ({filename.md})`", paragraph)
        self.assertIn("different tiers", paragraph)
        self.assertIn("same Part", paragraph)
        self.assertIn("no blank line inside", paragraph)
        self.assertIn("references/ei-citation-and-token-reconciliation.md", paragraph)
        # the lint reads a Note to its first blank line, so the stated form must be what it reads
        note = f"{label} Spec #1 (A.md) and Spec #2 (B.md) cite this finding."
        self.assertEqual(len(lint_ei._note_paragraphs([note, "", "other"])), 1)

    def test_scaffolder_cross_sprint_marker_rule_places_the_step_one_gate(self):
        """Lint rule cross-sprint-touch reads only the first line that begins `1.` under
        `## Execution Steps` of the first writing task, and wants a MUST NOT run concurrently
        line for an unordered pair. The scaffolder states where each one goes."""
        rule = next(
            (ln for ln in _read(SCAFFOLDER).splitlines() if ln.startswith("- **Cross-sprint markers.**")), ""
        )
        self.assertTrue(rule, "the scaffolding rules have no Cross-sprint markers bullet")
        self.assertIn("Execution Step `1.`", rule)
        self.assertIn("first line that begins `1.` under `## Execution Steps`", rule)
        self.assertIn("cross-sprint-touch", rule)
        self.assertIn("`### Cross-Sprint Prerequisite Grep Gate` H3", rule)
        self.assertIn("code fence", rule)
        self.assertIn("`Grep`", rule)
        self.assertIn("HALT", rule)
        self.assertIn("first task id in the file's Write-Set row", rule)
        self.assertIn("first writing task of both sprints", rule)
        # the stated MUST NOT line is one the lint's own pattern finds
        self.assertTrue(lint_plan.NOT_CONCURRENT_RE.search("MUST NOT run concurrently"))
        self.assertIn("`MUST NOT run concurrently`", rule)
        # the step the rule describes is one the lint's first-step pattern selects
        self.assertTrue(lint_plan.FIRST_STEP_RE.match("1. Grep the prior sprint's marker"))


class PlanAuthorContractTests(unittest.TestCase):
    """The plan handler dispatches this agent and parses its status block."""

    def test_writes_one_bodies_file_per_session(self):
        text = _read(PLAN_AUTHOR)
        self.assertIn("`{Abbrev}-bodies-S{XX}-{YY}.md`", text)
        self.assertNotRegex(text, r"in one .Write.")
        self.assertIn("one block per file", text)
        self.assertIn("`{Abbrev}-bodies-S{XX}-{YY}-part{n}.md`", text)
        self.assertIn("compose that block again and write its own file whole", text)
        self.assertRegex(text, r"`partial` after the first write")
        self.assertRegex(text, r"(?m)^maxTurns: 80$")
        self.assertNotIn("exceed `maxTurns`", text)
        self.assertIn("After 5 document blocks written in one dispatch", text)
        self.assertIn("keys --spec {spec_path} --session S{XX}-{YY}", text)

    def test_handler_routes_a_no_status_block_dispatch(self):
        """The agent cannot see its turn counter, so the handler routes a dispatch that
        returns no status block as PARTIAL and resumes it."""
        handler = _read(PLUGIN / "handlers" / "plan-Part-2-GatherAndGenerate.md")
        self.assertIn("A return with no `TASK_STATUS:` line", handler)
        self.assertIn("--bodies-dir {bodies_dir} --session S{XX}-{YY}", handler)
        self.assertIn("keys --spec {spec_path} --session S{XX}-{YY}", handler)
        self.assertIn("`keys_missing=0 errors=0`", handler)
        self.assertIn("references/dispatch-boundary-evidence.md", handler)

    def test_runs_the_session_lint_and_reads_its_line(self):
        text = _read(PLAN_AUTHOR)
        self.assertRegex(
            text,
            r'python -B "\{plugin_root\}/scripts/plan_build\.py" lint --spec \S+ --bodies-dir \S+ '
            r"--session S\{XX\}-\{YY\}",
        )
        self.assertIn("session=S{XX}-{YY} keys_missing=<n> errors=<n>", text)

    def test_status_block_reports_keys_missing(self):
        status_block = _section(_read(PLAN_AUTHOR), "## Status Block")
        for field in (
            "TASK_STATUS", "TASK_ID", "OUTPUT_FILES", "LINES_PRODUCED", "KEYS_MISSING", "KEY_FINDINGS",
            "ISSUES", "NOTES_PATH", "OPEN_QUESTIONS",
        ):
            with self.subTest(field=field):
                self.assertRegex(status_block, rf"(?m)^{field}:")
        self.assertRegex(status_block, r"`COMPLETE` .*`keys_missing=0` and `errors=0`")

    def test_plan_specific_body_needs_the_heading_in_keys(self):
        text = _read(PLAN_AUTHOR)
        self.assertRegex(text, r"write that body only when `keys` lists that heading")
        self.assertRegex(text, r"Otherwise return `BLOCKED` and name the section in `ISSUES`")
        failures = _section(text, "## Failure Semantics")
        self.assertRegex(failures, r"`## Plan-Specific Sections` and `keys` does not list .*\| `BLOCKED`, naming the section")
        self.assertRegex(failures, r"`optional_sections` in the spec, then dispatches again")

    def test_old_task_file_contract_is_gone(self):
        text = _read(PLAN_AUTHOR)
        for literal in ("Write each task file whole", "Skeleton task files", "Grep the written file for `FILL`"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, text)

    def test_never_writes_a_task_file_or_the_master_plan(self):
        constraints = _section(_read(PLAN_AUTHOR), "## Constraints")
        self.assertRegex(constraints, r"Never write a task file\b.*the Master Plan")

    def test_frontmatter_keeps_the_dispatch_name_and_inherited_effort(self):
        keys = _frontmatter_keys(PLAN_AUTHOR)
        self.assertEqual(keys.get("name"), "plan-author")
        self.assertEqual(keys.get("model"), "opus")
        self.assertNotIn("effort", keys)
        self.assertNotIn("background", keys)
        self.assertIn("bodies file", keys.get("description", ""))


if __name__ == "__main__":
    unittest.main()
