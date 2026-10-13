#!/usr/bin/env python3
"""Tests for the `--list-diverged` pre-scan row builder.

Every row names the set the writer will treat it as (`installed`, `descoped`
or `style`), and diverged style rules are listed from the same population the
writer dispositions. The pre-scan is read-only.

Run with:  python -m pytest -q -c <plugin repo>/pytest.ini <plugin repo>/tests/test_list_diverged.py
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_cli
from constants import InstallScope

from conftest import _snapshot_tree, _UpgradeArtifactsFixtureBase


class _ListDivergedBase(_UpgradeArtifactsFixtureBase):
    """The upgrade fixture base, plus doctor_cli's own rule-table bindings."""

    DESCOPED_FILENAME = "aaa-descoped-fixture.md"
    STYLE_FILENAME = "plain-language.md"

    def setUp(self):
        super().setUp()
        # doctor_cli holds its own INSTALLED_RULES / DESCOPED_RULES bindings; the
        # base patches only artifact_upgrade and doctor_sweeps.
        for name, value in (
            ("INSTALLED_RULES", [(self.RULE_FILENAME, self.RULE_PATHS_TEMPLATE)]),
            ("DESCOPED_RULES", [(self.DESCOPED_FILENAME, "{plans_path}")]),
        ):
            patcher = mock.patch.object(doctor_cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_pair(self, filename: str, shipped: str, installed: str, installed_dir: Path | None = None) -> Path:
        (self.refs_dir / filename).write_text(shipped, encoding="utf-8")
        dst_dir = installed_dir or self.rules_dst_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / filename
        dst.write_text(installed, encoding="utf-8")
        return dst

    def rows(self) -> list[dict]:
        return doctor_cli._list_diverged_rows(self.cfg)


class TestListDivergedSets(_ListDivergedBase):
    def test_installed_rule_row_carries_set_installed(self):
        self.write_pair(self.RULE_FILENAME, "shipped body\n", "edited body\n")
        rows = self.rows()
        self.assertEqual([r["filename"] for r in rows], [self.RULE_FILENAME])
        self.assertEqual(rows[0]["set"], "installed")

    def test_descoped_rule_row_carries_set_descoped(self):
        self.write_pair(self.DESCOPED_FILENAME, "shipped body\n", "edited body\n")
        rows = self.rows()
        self.assertEqual([r["filename"] for r in rows], [self.DESCOPED_FILENAME])
        self.assertEqual(rows[0]["set"], "descoped")

    def test_diverged_style_rule_is_listed_with_set_style(self):
        self.write_pair(self.STYLE_FILENAME, "shipped style\n", "edited style\n")
        rows = self.rows()
        self.assertEqual([r["filename"] for r in rows], [self.STYLE_FILENAME])
        self.assertEqual(rows[0]["set"], "style")
        self.assertEqual(rows[0]["kind"], "rule")
        self.assertEqual(rows[0]["installed"], f".claude/rules/planwise/{self.STYLE_FILENAME}")
        self.assertEqual(rows[0]["shipped"], f"references/{self.STYLE_FILENAME}")

    def test_identical_copy_yields_no_row(self):
        with self.subTest("identical copy"):
            self.write_pair(self.RULE_FILENAME, "same body\n", "same body\n")
            self.assertEqual(self.rows(), [])
        with self.subTest("style rule with an other-scope managed copy"):
            self.write_pair(self.STYLE_FILENAME, "shipped style\n", "edited style\n")
            other = Path.home() / ".claude" / "rules" / "planwise"
            other.mkdir(parents=True, exist_ok=True)
            (other / self.STYLE_FILENAME).write_text("home copy\n", encoding="utf-8")
            self.assertEqual(self.rows(), [])

    def test_unreadable_installed_file_is_skipped(self):
        bad = self.write_pair(self.RULE_FILENAME, "shipped body\n", "edited body\n")
        self.write_pair(self.DESCOPED_FILENAME, "shipped body\n", "edited body\n")
        real_read_text = Path.read_text

        def fake_read_text(path, *args, **kwargs):
            if path == bad:
                raise OSError("unreadable")
            return real_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", fake_read_text):
            rows = self.rows()
        self.assertEqual([r["filename"] for r in rows], [self.DESCOPED_FILENAME])

    def test_rows_are_stable_sorted_by_filename(self):
        # The scan walks the installed rule before the descoped one, so a sorted
        # result needs the descoped name to sort first.
        self.write_pair(self.RULE_FILENAME, "shipped body\n", "edited body\n")
        self.write_pair(self.DESCOPED_FILENAME, "shipped body\n", "edited body\n")
        names = [r["filename"] for r in self.rows()]
        self.assertEqual(names, [self.DESCOPED_FILENAME, self.RULE_FILENAME])

    def test_prescan_is_read_only(self):
        self.write_pair(self.RULE_FILENAME, "shipped body\n", "edited body\n")
        self.write_pair(self.DESCOPED_FILENAME, "shipped body\n", "edited body\n")
        self.write_pair(self.STYLE_FILENAME, "shipped style\n", "edited style\n")
        before = _snapshot_tree(self.tmp)
        self.rows()
        self.assertEqual(_snapshot_tree(self.tmp), before)

    def test_non_utf8_style_copy_yields_no_row_and_no_exception(self):
        dst = self.write_pair(self.STYLE_FILENAME, "shipped style\n", "edited style\n")
        dst.write_bytes(b"\xff\xfe\x00bad \x80 bytes\n")
        self.assertEqual(self.rows(), [])

    def test_user_scope_style_row_uses_an_absolute_installed_path(self):
        self.cfg.install_scope = InstallScope.USER
        home_dir = Path.home() / ".claude" / "rules" / "planwise"
        dst = self.write_pair(self.STYLE_FILENAME, "shipped style\n", "edited style\n", installed_dir=home_dir)
        rows = self.rows()
        self.assertEqual([r["filename"] for r in rows], [self.STYLE_FILENAME])
        self.assertEqual(rows[0]["set"], "style")
        self.assertEqual(rows[0]["installed"], dst.as_posix())
        self.assertTrue(Path(rows[0]["installed"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
