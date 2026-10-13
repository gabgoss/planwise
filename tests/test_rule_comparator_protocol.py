#!/usr/bin/env python3
"""Text-pin tests for the rule-comparator agent protocol.

The comparator may read a bounded set of sibling files named by the shipped
text (Step 3b). These tests pin the protocol prose so a later edit cannot
widen that read silently: the bound, the depth, the turn budget, the
single-pair exception sentence, and the tool prohibition that keeps the agent
from walking a tree.

They pin protocol text only. They do not run a comparator, so they do not show
that a live comparator classifies a split fixture correctly.

Run with:  python -m pytest tests/test_rule_comparator_protocol.py -q
"""

import re
import unittest
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
AGENT = _PLUGIN / "agents" / "rule-comparator.md"


def _read_agent() -> str:
    return AGENT.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    return parts[1] if len(parts) >= 3 else ""


def _frontmatter_line(text: str, key: str) -> str:
    for line in _frontmatter(text).splitlines():
        if line.startswith(key + ":"):
            return line
    return ""


class RuleComparatorProtocolTests(unittest.TestCase):
    def test_frontmatter_still_disallows_glob(self):
        text = _read_agent()
        disallowed = _frontmatter_line(text, "disallowedTools")
        tools = _frontmatter_line(text, "tools")
        self.assertTrue(disallowed, "disallowedTools line missing")
        self.assertTrue(tools, "tools line missing")
        self.assertRegex(disallowed, r"\bGlob\b")
        self.assertNotRegex(tools, r"\bGlob\b")

    def test_sibling_step_names_its_bound_and_depth(self):
        text = _read_agent()
        match = re.search(r"^## Step 3b\b.*$", text, re.MULTILINE)
        self.assertIsNotNone(match, "no Step 3b heading in the agent body")
        start = match.end()
        nxt = re.search(r"^## ", text[start:], re.MULTILINE)
        section = text[start : start + nxt.start()] if nxt else text[start:]
        self.assertRegex(section, r"at most 3 sibling")
        self.assertRegex(section, r"(?i)\bdepth\b")

    def test_max_turns_is_at_least_16(self):
        line = _frontmatter_line(_read_agent(), "maxTurns")
        match = re.match(r"maxTurns:\s*(\d+)\s*$", line)
        self.assertIsNotNone(match, f"maxTurns line not parseable: {line!r}")
        self.assertGreaterEqual(int(match.group(1)), 16)

    def test_single_pair_sentence_carries_the_sibling_exception(self):
        text = _read_agent()
        match = re.search(r"You compare exactly this one pair[^\n]*", text)
        self.assertIsNotNone(match, "single-pair sentence missing")
        sentence = match.group(0)
        self.assertIn("Step 3b", sentence)
        self.assertIn("Do NOT walk the tree", sentence)

    def _step_3b(self) -> str:
        text = _read_agent()
        match = re.search(r"^## Step 3b\b.*$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        start = match.end()
        nxt = re.search(r"^## ", text[start:], re.MULTILINE)
        return text[start : start + nxt.start()] if nxt else text[start:]

    def test_trigger_is_limited_to_the_split_family(self):
        section = self._step_3b()
        self.assertIn("-Part-", section)
        self.assertRegex(section, r"stem")
        self.assertRegex(section, r"(?i)held in")
        self.assertRegex(section, r"(?i)any other (reference|file)")

    def test_sibling_path_is_built_from_the_shipped_directory(self):
        section = self._step_3b()
        self.assertRegex(section, r"directory of `shipped_path`")
        self.assertRegex(section, r"never the directory of `installed_path`")
        self.assertIn("`..`", section)
        self.assertRegex(section, r"does not count toward the 3")

    def test_grep_is_confined_to_named_files(self):
        section = self._step_3b()
        self.assertIn(
            "Never use Grep on a directory; use Grep only on installed_path, "
            "shipped_path, or a sibling you already read.",
            section,
        )

    def test_step_states_reorg_does_not_stop_the_refresh(self):
        section = self._step_3b()
        self.assertRegex(section, r"(?i)does not stop the upgrade")

    def test_step_5_lists_every_extra_key(self):
        text = _read_agent()
        match = re.search(r"^## Step 5\b.*$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        body = text[match.end() :].lstrip()
        first_para = body.split("\n\n", 1)[0]
        for key in ("home_hints", "tolerated_fragments", "rationale", "relocated_blocks"):
            self.assertIn(key, first_para)
        self.assertNotIn("Use `{}` when none moved", self._step_3b())
        self.assertRegex(self._step_3b(), r"(?i)only\s+when\s+Step 3b ran")


class UpgradeHandlerWiringTests(unittest.TestCase):
    def test_spawn_prompt_names_every_extra_key(self):
        text = (_PLUGIN / "handlers" / "upgrade.md").read_text(encoding="utf-8")
        start = text.index("planwise:rule-comparator\",")
        prompt = text[start : text.index("\n)\n", start)]
        for key in ("relocated_blocks", "tolerated_fragments", "rationale"):
            self.assertIn(key, prompt)

    def test_summary_lists_every_relocation(self):
        path = _PLUGIN / "handlers" / "upgrade-Part-3-BannerAndConflictResolution.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("{file}: {disposition}; {block} now in {sibling}", text)
        self.assertIn("late-verdicts.md", text)


if __name__ == "__main__":
    unittest.main()
