"""Pin the route of `/planwise plan --scaffold` when no Consolidated Context part exists.

`handlers/plan.md` Step 0 carries a Scaffolding precondition. With zero parts
under `Meta-{Abbrev}/Outputs/` every route into Scaffolding falls to the
Standard path and prints a route confirmation block. `handlers/plan-scaffolding.md`
Step 1 carries the matching empty-set branch and a `Route:` line in its own
confirmation template.
"""

from __future__ import annotations

import unittest
from pathlib import Path

HANDLERS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "handlers"


def _read(name: str) -> str:
    return (HANDLERS / name).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    """Return the text from the first `start` to the first `end` after it."""
    i = text.index(start)
    return text[i : text.index(end, i)]


class TestPlanStep0Precondition(unittest.TestCase):
    def setUp(self) -> None:
        step0 = _between(_read("plan.md"), "### Step 0: Detect Mode", "#### No Mode Detected")
        self.step0 = step0

    def test_precondition_paragraph_present(self) -> None:
        self.assertIn("**Scaffolding precondition:**", self.step0)

    def test_route_standard_line_present(self) -> None:
        self.assertIn("Route: Standard", self.step0)

    def test_premise_document_line_present(self) -> None:
        self.assertIn("Premise document:", self.step0)

    def test_precondition_follows_the_explicit_flag_row(self) -> None:
        # The check must come after the row that routes `--scaffold` to Scaffolding.
        self.assertLess(
            self.step0.index("`--scaffold` flag present"),
            self.step0.index("**Scaffolding precondition:**"),
        )


class TestScaffoldingHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _read("plan-scaffolding.md")

    def test_route_line_inside_context_confirmation_template(self) -> None:
        template = _between(
            self.text,
            "> [!template] Scaffolding Context Confirmation",
            "Next Action:",
        )
        self.assertIn("Route: Scaffolding", template)

    def test_empty_set_branch_precedes_confirm_block(self) -> None:
        self.assertLess(
            self.text.index("**Empty-set branch:**"),
            self.text.index("**CONFIRM block"),
        )

    def test_empty_set_branch_returns_to_the_precondition(self) -> None:
        branch = _between(self.text, "**Empty-set branch:**", "**CONFIRM block")
        self.assertIn("Scaffolding precondition", branch)
        self.assertIn("Standard", branch)


if __name__ == "__main__":
    unittest.main()
