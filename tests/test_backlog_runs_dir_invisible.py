#!/usr/bin/env python3
"""Regression tests: `Backlog-Runs/` is invisible to every backlog reader.

Loop mode keeps one JSON run file per run under `{backlog_dir}/Backlog-Runs/`.
No guard code protects the folder: every backlog reader walks the backlog
directory with a top-level `*.md` glob (or `iterdir()` plus an index-name
check), so a `.json` file in a subfolder is invisible by construction. These
tests pin that fact so a future recursive walk fails loudly.

A `.json` file alone could not fail a `*.md` reader, recursive or not. Each
test therefore also plants a copy of one open item file, renamed to an unused
id with the fixture's file-name pattern, inside `Backlog-Runs/`. A recursive
`*.md` walk would see that copy and change the reader's result.

One test per reader:
  - backlog_index_scan._iter_item_files
  - parse_backlog's selectable item set, through its hub-family enumeration
  - reconcile_backlog.detect_drift

Run with:  python -m pytest tests/test_backlog_runs_dir_invisible.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import backlog_index_scan
import config_loader
import parse_backlog
import reconcile_backlog

CONFIG_YAML_FIXTURE = """project:
  name: "BacklogRunsInvisibleFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

HUB = (
    "| ID | Title | Priority | Status | Domain | Created | Blocks | Score | File |\n"
    "|----|-------|----------|--------|--------|---------|--------|-------|------|\n"
    "| 048 | In flight | Medium | IN_PROGRESS | INFRA | 2026-10-01 |  | 0 | [01](048-INFRA-open-item.md) |\n"
    "| 049 | Not started | Low | NOT_STARTED | INFRA | 2026-10-01 |  | 0 | [01](049-INFRA-second-item.md) |\n"
)

ITEM_FILES = {
    "048-INFRA-open-item.md": ("048", "IN_PROGRESS"),
    "049-INFRA-second-item.md": ("049", "NOT_STARTED"),
    # A closed item stranded outside Archive/: drift for detect_drift to report.
    "046-INFRA-stranded-item.md": ("046", "COMPLETE"),
}

PLANTED_ITEM_NAME = "099-INFRA-planted-copy.md"


class _RunsDirFixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backlog_runs_invisible_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.runs_dir = self.backlog_dir / "Backlog-Runs"
        self.index_path = self.backlog_dir / "00-Index-Backlog.md"
        self.backlog_dir.mkdir(parents=True)
        self.archive_dir.mkdir()
        (self.planwise_dir / "config.yaml").write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        self.index_path.write_text(HUB, encoding="utf-8")
        for filename, (item_id, status) in ITEM_FILES.items():
            (self.backlog_dir / filename).write_text(
                f"---\nid: {item_id}\nstatus: {status}\n---\n\n# {filename}\n", encoding="utf-8"
            )

        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = ["test_backlog_runs_dir_invisible", "--config", str(self.planwise_dir / "config.yaml")]
        self.config = config_loader.load_config()

    def plant_runs_dir(self) -> None:
        """Plant a run file and an item-file copy under Backlog-Runs/."""
        self.runs_dir.mkdir()
        (self.runs_dir / "20261007-000000.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
        source = (self.backlog_dir / "048-INFRA-open-item.md").read_text(encoding="utf-8")
        (self.runs_dir / PLANTED_ITEM_NAME).write_text(
            source.replace("id: 048", "id: 099"), encoding="utf-8"
        )
        self.assertTrue((self.runs_dir / PLANTED_ITEM_NAME).is_file())


class TestRunsDirInvisible(_RunsDirFixtureBase):
    def test_iter_item_files_ignores_runs_dir(self):
        def walk() -> list[str]:
            found = backlog_index_scan._iter_item_files(
                self.backlog_dir, self.archive_dir, self.index_path
            )
            return [str(path.relative_to(self.backlog_dir)) for path in found]

        before = walk()
        self.assertEqual(len(before), 3)

        self.plant_runs_dir()

        self.assertEqual(walk(), before)

    def test_parse_backlog_enumeration_ignores_runs_dir(self):
        naming = parse_backlog._index_naming(self.index_path)

        def selectable_ids() -> list[str]:
            rows: list[dict] = []
            for path in parse_backlog._enumerate_generated_files(self.backlog_dir, naming):
                rows.extend(parse_backlog._read_backlog_items(path))
            blocked_by = parse_backlog.build_blocked_by_map([], rows)
            selectable, _held = parse_backlog.filter_items(
                rows, parse_backlog.FilterCriteria(), blocked_by
            )
            return [row["id"] for row in selectable]

        before = selectable_ids()
        self.assertEqual(before, ["048", "049"])

        self.plant_runs_dir()
        # The enumerator matches generated index names, so a copy of the hub
        # is the planted file a recursive walk could pick up.
        shutil.copyfile(self.index_path, self.runs_dir / self.index_path.name)

        self.assertEqual(selectable_ids(), before)

    def test_detect_drift_ignores_runs_dir(self):
        before = reconcile_backlog.detect_drift(self.config)
        self.assertEqual([d["id"] for d in before["drifts"]], ["046"])
        self.assertEqual(before["anomalies"], [])

        self.plant_runs_dir()

        self.assertEqual(reconcile_backlog.detect_drift(self.config), before)


if __name__ == "__main__":
    unittest.main()
