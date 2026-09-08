#!/usr/bin/env python3
"""config.yaml resolution must never read a foreign project's config.

`find_config_upward()` walks every ancestor of the invocation directory and
each ancestor's immediate children. From a directory with no planwise config
(a temp dir, a fresh checkout) that chain crosses directories the project
does not own, and any `config.yaml` an unrelated tool left there used to be
resolved and read as this project's — a plausible plans table for the wrong
project, with no warning. These tests pin the documented gate: a) direct,
b) one level down, a planwise marker on every accepted candidate, and a
fail-loud exit when nothing qualifies.

Run with:  python -m unittest tests/test_config_resolution.py
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402

PLANWISE_CONFIG = (
    "project:\n"
    "  name: Fixture\n"
    "  planwise_root: planwise\n"
    "  plans_dir: Plans\n"
    "  backlog_dir: Backlog\n"
    "  lessons_dir: LessonsLearned\n"
)
FOREIGN_CONFIG = "tool: something-else\nverbose: true\n"


class _ResolutionFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cfg_resolution_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class TestFindConfigUpward(_ResolutionFixture):
    def test_no_config_anywhere_returns_none(self):
        start = self.tmp / "work" / "deeper"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start, stop_at=self.tmp))

    def test_foreign_config_in_the_chain_is_skipped(self):
        """The defect: a config.yaml with no planwise marker sits on an
        ancestor. It must be skipped, not resolved."""
        self.write("config.yaml", FOREIGN_CONFIG)
        self.write("sibling-tool/config.yaml", FOREIGN_CONFIG)
        start = self.tmp / "work" / "deeper"
        start.mkdir(parents=True)
        self.assertIsNone(config_loader.find_config_upward(start, stop_at=self.tmp))

    def test_planwise_config_one_level_down_is_found(self):
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        found = config_loader.find_config_upward(self.tmp, stop_at=self.tmp)
        self.assertEqual(found, expected)

    def test_planwise_config_in_an_ancestor_is_found(self):
        """The documented upward search survives: invoking from a
        subdirectory of the project still resolves the project's config."""
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        start = self.tmp / "src" / "pkg"
        start.mkdir(parents=True)
        self.assertEqual(config_loader.find_config_upward(start, stop_at=self.tmp), expected)

    def test_planwise_config_wins_over_a_foreign_sibling(self):
        self.write("other-tool/config.yaml", FOREIGN_CONFIG)
        expected = self.write("planwise/config.yaml", PLANWISE_CONFIG)
        self.assertEqual(config_loader.find_config_upward(self.tmp, stop_at=self.tmp), expected)

    def test_marker_accepts_bom_and_trailing_comment(self):
        bom = self.write("a/config.yaml", "﻿project:  # the project block\n  name: X\n")
        self.assertTrue(config_loader._is_planwise_config(bom))

    def test_marker_rejects_nested_or_prose_project_key(self):
        nested = self.write("b/config.yaml", "settings:\n  project: nope\n")
        self.assertFalse(config_loader._is_planwise_config(nested))
        unreadable = self.tmp / "c" / "config.yaml"
        unreadable.parent.mkdir(parents=True)
        unreadable.write_bytes(b"\xff\xfe\x00not text")
        self.assertFalse(config_loader._is_planwise_config(unreadable))


class TestLoadConfigFailsLoud(_ResolutionFixture):
    def test_no_resolvable_config_exits_nonzero_with_the_init_hint(self):
        """With nothing resolvable, load_config() must exit 1 and say so —
        never fall through to a config found by inference."""
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["script.py"]), \
             mock.patch.object(config_loader, "find_config_upward", return_value=None), \
             contextlib.redirect_stderr(stderr), \
             self.assertRaises(SystemExit) as ctx:
            config_loader.load_config(script_path=self.tmp / "scripts" / "x.py")
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("config.yaml not found", stderr.getvalue())
        self.assertIn("/planwise init", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
