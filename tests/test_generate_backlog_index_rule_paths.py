#!/usr/bin/env python3
"""An item title that names a file under `.claude/rules/planwise/` names a
dead destination. That folder holds the plugin's machine-managed installed
rules, and an upgrade replaces or removes every file in it, so a backlog item
that says it produces a file there describes something that will not stay.

The generator reports such a title as an anomaly, the same way it reports an
inverted `blocks:` edge: `--check` and the default report mode exit 1, and
`--write` prints the anomaly and still writes. A title that names only the
bare folder is a maintenance item about the folder itself, and it raises
nothing.

The fixtures reuse the generator suite's isolated temp planwise tree.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index_rule_paths.py
"""

import json
import sys
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import generate_backlog_index_fixtures as tgb

PLANTED_TITLE = "Extend .claude/rules/planwise/gate-control.md with a new section"
BARE_FOLDER_TITLE = "Sweep index rows that still describe dead .claude/rules/planwise/ destinations"


class TestInstalledRulePathTitles(unittest.TestCase):
    """The pure check over already-scanned item dicts."""

    FLAGGED = (
        "Extend .claude/rules/planwise/gate-control.md section 5",
        "Write `.claude/rules/planwise/x.md` from the lesson",
        'Move "/.claude/rules/planwise/rule-authoring.md" content',
        "Promote a lesson into .claude/rules/planwise/a.md and .claude/rules/planwise/b.md",
    )
    NOT_FLAGGED = (
        BARE_FOLDER_TITLE,
        "Prune stale copies under .claude/rules/planwise",
        "Extend .claude/rules/plugin-distribution-hygiene.md section 5",
        "Ship references/verification-gate-evidence.md section 14",
        "Write .claude/rules/planwise/notes.txt",
    )

    def test_a_title_naming_a_file_under_the_folder_is_flagged(self):
        for title in self.FLAGGED:
            with self.subTest(title=title):
                entries = gbi._installed_rule_path_anomalies([tgb._make_item(1, title=title)])
                self.assertEqual([e["id"] for e in entries], ["001"])
                self.assertIn("installed-rule destination -- 001", entries[0]["reason"])

    def test_a_title_naming_no_file_under_the_folder_is_not_flagged(self):
        for title in self.NOT_FLAGGED:
            with self.subTest(title=title):
                self.assertEqual(gbi._installed_rule_path_anomalies([tgb._make_item(1, title=title)]), [])

    def test_the_reason_names_every_matched_file_once(self):
        title = "Promote into .claude/rules/planwise/a.md, then .claude/rules/planwise/a.md again"
        (entry,) = gbi._installed_rule_path_anomalies([tgb._make_item(7, title=title)])

        self.assertEqual(entry["reason"].count(".claude/rules/planwise/a.md"), 1)


class TestInstalledRulePathCli(tgb._GeneratorFixtureBase):
    """The check wired into the default mode, `--check` and `--write`."""

    def test_dry_run_exits_one_and_names_the_item(self):
        self.write_item("041", title=PLANTED_TITLE)
        self.write_item("042", title="An ordinary item")

        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("Anomaly: installed-rule destination -- 041", err)
        self.assertIn(".claude/rules/planwise/gate-control.md", err)
        self.assertNotIn("-- 042", err)

    def test_write_reports_the_title_and_still_writes(self):
        self.write_item("041", title=PLANTED_TITLE)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertIn("Anomaly: installed-rule destination -- 041", err)
        self.assertTrue((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_check_exits_one_after_a_clean_write_and_lists_it_in_json(self):
        self.write_item("041", title=PLANTED_TITLE)
        self.run_main("--write")

        code, out, err = self.run_main("--check", "--json")

        self.assertEqual(code, 1)
        self.assertIn("installed-rule destination -- 041", err)
        anomaly_ids = [entry["id"] for entry in json.loads(out)["anomaly"]]
        self.assertIn("041", anomaly_ids)

    def test_a_bare_folder_title_passes_every_mode(self):
        self.write_item("209", title=BARE_FOLDER_TITLE)

        dry_code, _out, dry_err = self.run_main("--dry-run")
        write_code, _out, write_err = self.run_main("--write")
        check_code, _out, check_err = self.run_main("--check")

        self.assertEqual((dry_code, write_code, check_code), (0, 0, 0))
        for err in (dry_err, write_err, check_err):
            self.assertNotIn("installed-rule destination", err)


if __name__ == "__main__":
    unittest.main()
