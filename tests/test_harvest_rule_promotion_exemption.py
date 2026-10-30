#!/usr/bin/env python3
"""Text-pin tests for the rule-file promotion exemption.

A lesson promoted into a rule file produces a backlog item whose destination
sits under `.claude/rules/`. The scoped-rule gate used to send every such item
to Route C, which ends at PLANNING, so harvest stage 4 landed nothing. The fix
spans `handlers/backlog.md` (Phase 3 step 7), `handlers/harvest.md` (Failure
Classification, Stage 3 Route A, Stage 4) and `agents/backlog-planner.md`. These
tests pin the exemption, its two conditions, the run-end report, and the planner
sentence that landing a lesson is not a resolution step, so a later edit cannot silently restore the unconditional escalation.

Run with:  python -m pytest tests/test_harvest_rule_promotion_exemption.py -q
"""

import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
BACKLOG_HANDLER = PLUGIN / "handlers" / "backlog.md"
HARVEST_HANDLER = PLUGIN / "handlers" / "harvest.md"
BACKLOG_PLANNER = PLUGIN / "agents" / "backlog-planner.md"

# Both handlers must state the same two exemption conditions.
CONDITION_LITERALS = [
    "`promoted-to:`",
    "`promotion-target:` includes `rule`",
    "any destination",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _span_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    return text[start:text.index(end_marker, start)]


class BacklogStepSevenExemptionTests(unittest.TestCase):
    def setUp(self):
        text = _read(BACKLOG_HANDLER)
        self.step7 = _span_between(
            text, "7. **Scoped-rule pre-delegation check", "8. Present the scope assessment"
        )

    def test_exemption_paragraph_appears_once(self):
        self.assertEqual(self.step7.count("**Promotion exemption.**"), 1)

    def test_exemption_states_both_conditions(self):
        for literal in CONDITION_LITERALS:
            with self.subTest(literal=literal):
                self.assertIn(literal, self.step7)

    def test_exempt_item_gets_rule_injection_and_keeps_verify(self):
        self.assertIn("agent-orchestration-delegated.md` §1.6", self.step7)
        self.assertIn("self-containment grep", self.step7)

    def test_auto_mode_escalation_is_conditional(self):
        self.assertIn("a `placement` verdict **auto-escalates to Route C**", self.step7)


class HarvestExemptionTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(HARVEST_HANDLER)

    def test_failure_classification_splits_the_scoped_rule_row(self):
        table = _span_between(self.text, "### Step 5: Failure Classification", "### Step 6")
        self.assertIn("| scoped-rule verdict placement |", table)
        self.assertIn("| scoped-rule verdict inject |", table)
        self.assertNotIn("| scoped-rule conflict, item not exempt |", table)

    def test_harvest_states_the_same_conditions_as_triage(self):
        table = _span_between(self.text, "### Step 5: Failure Classification", "### Step 6")
        for literal in CONDITION_LITERALS:
            with self.subTest(literal=literal):
                self.assertIn(literal, table)

    def test_inherited_gates_paragraph_names_the_exemption(self):
        self.assertIn(
            "a `placement` verdict auto-escalates directly to Route C, and an `inject` verdict",
            self.text,
        )

    def test_route_a_prompt_carries_matching_rules_for_exempt_items(self):
        stage3 = _span_between(self.text, "**Route behaviour:**", "#### Stage 4: Land")
        self.assertIn("carries the content of every rule the `scoped_rules` block lists", stage3)

    def test_stage_four_reports_unlanded_lessons_and_names_the_lander(self):
        stage4 = _span_between(self.text, "#### Stage 4: Land", "### Step 5: Failure Classification")
        self.assertIn("**Run-end report:**", stage4)
        self.assertIn("/planwise lessons curate", stage4)
        self.assertNotIn("lands on a later run", stage4)


class BacklogPlannerSentenceTests(unittest.TestCase):
    def test_planner_is_told_landing_is_not_a_resolution_step(self):
        text = _read(BACKLOG_PLANNER)
        decide = _span_between(text, "## 3. DECIDE", "## 4. WRITE")
        self.assertIn("Landing a lesson is not a resolution step.", decide)
        self.assertIn("harvest closeout", decide)


if __name__ == "__main__":
    unittest.main()
