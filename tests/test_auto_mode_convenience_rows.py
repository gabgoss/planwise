#!/usr/bin/env python3
"""Pins the Inference Defaults table to the convenience gates of the upgrade and doctor handlers.

`references/auto-mode-policy.md` § Inference Defaults is the single source for
every convenience default. Each `AUTO-MODE: convenience` site in the two
handler files below must cite its row by name. The check runs both ways:

  * Every site cites a row, and every cited row name starts a first cell of
    the table.
  * Every table row that names one of the two handlers is cited by a site.

The sites are found by their marker, not by line number. The set comparison
reads no count constant. A paragraph that holds a marker is the site's text.

Run with:  python -m pytest tests/test_auto_mode_convenience_rows.py -q
"""

import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
POLICY = PLUGIN / "references" / "auto-mode-policy.md"
HANDLERS = {
    "upgrade-Part-3": PLUGIN / "handlers" / "upgrade-Part-3-BannerAndConflictResolution.md",
    "doctor-Part-2": PLUGIN / "handlers" / "doctor-Part-2-RecoveryFeedbackAndOperationalAudits.md",
}

MARKER = "AUTO-MODE: convenience"
CITATION = re.compile(r'"([^"]+)" row of `references/auto-mode-policy\.md`')
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _flat(text: str) -> str:
    """Collapse every whitespace run, so a citation wrapped across lines still matches."""
    return re.sub(r"\s+", " ", text)


def convenience_sites(text: str) -> list[str]:
    """Return the paragraph that holds each marker, whitespace collapsed."""
    paragraphs = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    sites = []
    for paragraph in paragraphs:
        sites.extend(_flat(paragraph) for _ in range(paragraph.count(MARKER)))
    return sites


def policy_rows(text: str) -> list[str]:
    """Return the first cell of each Inference Defaults row."""
    text = text.replace("\r\n", "\n")
    start = text.index("### § Inference Defaults")
    end = text.find("\n## ", start)
    section = text[start : end if end != -1 else len(text)]
    firsts = []
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        first = UNESCAPED_PIPE.split(line)[1].strip()
        if first in ("Variable",) or set(first) <= {"-"}:
            continue
        firsts.append(first)
    return firsts


def problems(handler_texts: dict[str, str], policy_text: str) -> list[str]:
    """Return one line per mismatch between the sites and the table."""
    rows = policy_rows(policy_text)
    found: list[str] = []
    cited: set[str] = set()
    for handler, text in handler_texts.items():
        sites = convenience_sites(text)
        if not sites:
            found.append(f"{handler}: the walk found no convenience site")
        for site in sites:
            names = CITATION.findall(site)
            if not names:
                found.append(f"{handler}: a convenience site cites no row: {site[:90]}")
            for name in names:
                cited.add(name)
                if not any(row.startswith(name) for row in rows):
                    found.append(f"{handler}: cited row not in the table: {name}")
    for row in rows:
        names_a_handler = any(handler in row for handler in handler_texts)
        if names_a_handler and not any(row.startswith(name) for name in cited):
            found.append(f"table row cited by no site: {row[:90]}")
    return found


def _texts() -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in HANDLERS.items()}


class TestConvenienceRows(unittest.TestCase):
    def test_every_site_and_row_pair_up(self):
        self.assertEqual(problems(_texts(), POLICY.read_text(encoding="utf-8")), [])

    def test_the_walk_saw_the_table_and_the_sites(self):
        rows = policy_rows(POLICY.read_text(encoding="utf-8"))
        self.assertIn("Project name", rows)
        self.assertTrue(any("upgrade-Part-3" in row for row in rows))
        self.assertTrue(any("doctor-Part-2" in row for row in rows))
        for handler, text in _texts().items():
            with self.subTest(handler=handler):
                self.assertGreater(len(convenience_sites(text)), 0)

    def test_a_removed_row_fails(self):
        policy = POLICY.read_text(encoding="utf-8").replace("\r\n", "\n")
        kept = [line for line in policy.split("\n") if not line.startswith("| GitHub CLI install question")]
        self.assertEqual(len(kept), len(policy.split("\n")) - 1)
        found = problems(_texts(), "\n".join(kept))
        self.assertEqual(len(found), 1)
        self.assertIn("GitHub CLI install question", found[0])

    def test_a_renamed_citation_fails(self):
        texts = _texts()
        name = "Feedback directory creation question"
        self.assertIn(name, texts["doctor-Part-2"])
        texts["doctor-Part-2"] = texts["doctor-Part-2"].replace(name, "unnamed")
        found = problems(texts, POLICY.read_text(encoding="utf-8"))
        self.assertTrue(any("cited row not in the table: unnamed" in line for line in found))
        self.assertTrue(any("table row cited by no site" in line for line in found))

    def test_a_dropped_citation_phrase_fails(self):
        texts = _texts()
        phrase = " row of `references/auto-mode-policy.md`"
        self.assertIn(phrase, _flat(texts["doctor-Part-2"]))
        texts["doctor-Part-2"] = re.sub(r"\s+row\s+of\s+`references/auto-mode-policy\.md`", "", texts["doctor-Part-2"])
        found = problems(texts, POLICY.read_text(encoding="utf-8"))
        self.assertTrue(any("cites no row" in line for line in found))

    def test_a_planted_site_without_a_row_fails(self):
        texts = _texts()
        texts["upgrade-Part-3"] += f"\n\nAsk `AskUserQuestion` <!-- {MARKER} --> whether to proceed.\n"
        found = problems(texts, POLICY.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1)
        self.assertIn("cites no row", found[0])


if __name__ == "__main__":
    unittest.main()
