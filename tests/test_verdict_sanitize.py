#!/usr/bin/env python3
"""Tests for the agent-verdict sanitizer and its loader call.

An agent SUBSET verdict that carries `tolerated_fragments` has its `notes`
rewritten to the joined fragments, so prose commentary can never route a clean
SUBSET to the customization path. An entry without the key keeps legacy
behaviour, and a HAS_UNIQUE entry is never rewritten. An entry whose list is
empty while `notes` holds prose is contradictory and is ignored.

Run with:  python -m unittest tests/test_verdict_sanitize.py
"""

import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import rule_divergence
import upgrade_io
from verdict_sanitize import sanitize_agent_entry

PROSE = "older copy of grown shipped body"


def _agent_entry(classification="SUBSET", **extra):
    entry = {
        "classification": classification,
        "confidence": "contained",
        "unique_blocks": [],
        "home_hints": {},
        "source": "agent",
        "notes": PROSE,
    }
    entry.update(extra)
    return entry


class TestSanitizeAgentEntry(unittest.TestCase):
    def test_fragments_present_notes_is_the_joined_fragments(self):
        entry = _agent_entry(tolerated_fragments=["alpha line", "beta line"])
        before = copy.deepcopy(entry)

        result = sanitize_agent_entry(entry)

        self.assertEqual(result["notes"], "alpha line\nbeta line")
        self.assertEqual(entry, before, "the cached entry must not be mutated")

    def test_empty_fragments_gives_empty_notes(self):
        result = sanitize_agent_entry(_agent_entry(notes="", tolerated_fragments=[]))

        self.assertEqual(result["notes"], "")

    def test_blank_fragments_are_dropped_before_the_join(self):
        for fragments in ([""], ["   "], ["", ""]):
            with self.subTest(fragments=fragments):
                result = sanitize_agent_entry(_agent_entry(notes="", tolerated_fragments=fragments))

                self.assertEqual(result["notes"], "")
        result = sanitize_agent_entry(_agent_entry(tolerated_fragments=["keep", "  ", "this"]))
        self.assertEqual(result["notes"], "keep\nthis")

    def test_prose_notes_with_no_real_fragments_is_contradictory(self):
        for fragments in ([], [""], ["   "], ["", ""]):
            with self.subTest(fragments=fragments):
                self.assertIsNone(sanitize_agent_entry(_agent_entry(tolerated_fragments=fragments)))

    def test_prose_notes_with_empty_fragments_on_a_not_clean_entry_is_unchanged(self):
        cases = {
            "unique_blocks present": _agent_entry(tolerated_fragments=[], unique_blocks=["# Extra"]),
            "confidence unique": _agent_entry(tolerated_fragments=[], confidence="unique"),
            "blank fragments, unique_blocks": _agent_entry(
                tolerated_fragments=["  "], unique_blocks=["# Extra"]),
        }
        for label, entry in cases.items():
            with self.subTest(label):
                result = sanitize_agent_entry(entry)

                self.assertIsNotNone(result)
                self.assertEqual(result["notes"], PROSE, "prose notes stay so the file transfers")

    def test_key_absent_keeps_legacy_notes(self):
        cases = {
            "subset without the key": _agent_entry(),
            "has_unique with the key": _agent_entry(
                "HAS_UNIQUE", tolerated_fragments=["x"], unique_blocks=["# Extra"]),
            "has_unique with the key and empty list": _agent_entry(
                "HAS_UNIQUE", tolerated_fragments=[], unique_blocks=["# Extra"]),
            "source Agent (case differs)": _agent_entry(source="Agent", tolerated_fragments=[]),
            "source missing": {
                k: v for k, v in _agent_entry(tolerated_fragments=[]).items() if k != "source"},
        }
        for label, entry in cases.items():
            with self.subTest(label):
                result = sanitize_agent_entry(entry)

                self.assertEqual(result["notes"], PROSE)

    def test_non_list_fragments_is_rejected(self):
        for bad in ("a string", None, [1, 2], {"k": "v"}):
            with self.subTest(bad=bad):
                self.assertIsNone(
                    sanitize_agent_entry(_agent_entry(tolerated_fragments=bad)))

    def test_rationale_never_reaches_the_dataclass(self):
        result = sanitize_agent_entry(
            _agent_entry(notes="", tolerated_fragments=[], rationale="free commentary"))

        self.assertNotIn("rationale", result)


class TestLoaderReportsNormalisation(unittest.TestCase):
    RAW = "# Rule\n\nInstalled body.\n"

    def _load(self, entry):
        entry = dict(entry, installed_sha256=upgrade_io._installed_hash(self.RAW))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            verdict = upgrade_io._load_verdict_override(
                {"fixture-rule.md": entry}, "fixture-rule.md", self.RAW)
        return verdict, err.getvalue()

    def test_loader_reports_the_normalisation_on_stderr(self):
        verdict, err = self._load(_agent_entry(tolerated_fragments=["kept text"]))

        self.assertEqual(verdict.notes, "kept text")
        self.assertIn("fixture-rule.md", err)
        self.assertIn("notes differ, fragments used", err)
        self.assertIn(PROSE[:80], err)

        bad_verdict, bad_err = self._load(_agent_entry(tolerated_fragments="prose"))

        self.assertIsNone(bad_verdict)
        self.assertIn("tolerated_fragments", bad_err)
        self.assertIn("fixture-rule.md", bad_err)

    def test_loader_is_silent_when_nothing_was_lost(self):
        for label, entry in {
            "clean": _agent_entry(notes="", tolerated_fragments=[], rationale="why"),
            "notes already equal the fragments": _agent_entry(
                notes="a\nb", tolerated_fragments=["a", "b"]),
        }.items():
            with self.subTest(label):
                verdict, err = self._load(entry)

                self.assertIsNotNone(verdict)
                self.assertEqual(err, "")

    def test_prose_notes_with_empty_fragments_warns_and_falls_back(self):
        long_prose = "x" * 200
        verdict, err = self._load(_agent_entry(notes=long_prose, tolerated_fragments=[]))

        self.assertIsNone(verdict)
        self.assertIn("fixture-rule.md", err)
        self.assertIn("x" * 80, err)
        self.assertNotIn("x" * 81, err)

    def test_contradictory_entry_is_never_destructively_removable(self):
        clean, _ = self._load(_agent_entry(notes="", tolerated_fragments=[]))
        self.assertTrue(rule_divergence._destructively_removable(clean), "positive control")

        override, _ = self._load(_agent_entry(tolerated_fragments=[]))

        self.assertIsNone(override, "the inline primitive must decide")
        self.assertFalse(
            override is not None and rule_divergence._destructively_removable(override))

    def test_not_clean_subset_with_prose_and_empty_fragments_loads_with_prose_and_no_warning(self):
        for extra in ({"unique_blocks": ["# Extra"]}, {"confidence": "unique"}):
            with self.subTest(extra=extra):
                verdict, err = self._load(_agent_entry(tolerated_fragments=[], **extra))

                self.assertIsNotNone(verdict)
                self.assertEqual(verdict.notes, PROSE)
                self.assertFalse(rule_divergence._destructively_removable(verdict))
                self.assertEqual(err, "")

    def test_has_unique_entry_keeps_its_notes_through_the_loader(self):
        verdict, err = self._load(_agent_entry(
            "HAS_UNIQUE", confidence="unique", unique_blocks=["# Extra"],
            tolerated_fragments=[]))

        self.assertEqual(verdict.notes, PROSE)
        self.assertFalse(rule_divergence._destructively_removable(verdict))
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
