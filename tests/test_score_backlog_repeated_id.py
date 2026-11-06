#!/usr/bin/env python3
"""A repeated backlog-index row id is refused by score_backlog.py's report modes.

`parse_backlog.py` and `backlog_loop.py` already exit 1 on a repeated row id.
`score_backlog.main()` reads the same index and must do the same, because
`--id` and `--route --id` would otherwise report on whichever copy comes first.

Run with:  python -m pytest tests/test_score_backlog_repeated_id.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import score_backlog

CONFIG_YAML_FIXTURE = """project:
  name: "ScoreBacklogRepeatedIdFixture"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

_9COL_HEADER = (
    "|" + "|".join(
        f" {c} " for c in
        ("ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File")
    ) + "|\n"
    + "|" + "|".join(["---"] * 9) + "|\n"
)

_ROW_001 = (
    "| 001 | Only item | Low | NOT_STARTED | DOC | 2020-01-01 |  | 0 | "
    "[001](BB-001-01-DOC-Item.md) |\n"
)


class TestRepeatedRowId(unittest.TestCase):
    """Every report mode refuses a repeated `001` row and names the id."""

    def _write_fixture(self, rows: int) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="score_backlog_repeated_id_test_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        planwise_dir = tmp / "planwise"
        backlog_dir = planwise_dir / "Backlog"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        config_path = planwise_dir / "config.yaml"
        config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")
        (backlog_dir / "BB-001-01-DOC-Item.md").write_text(
            "---\nid: 001\ntitle: \"Only item\"\npriority: Low\n"
            "status: NOT_STARTED\nabbrev: DOC\ncreated: 2020-01-01\n"
            "blocks: []\n---\n\n# Body\n",
            encoding="utf-8",
        )
        (backlog_dir / "00-Index-Backlog.md").write_text(
            _9COL_HEADER + _ROW_001 * rows, encoding="utf-8",
        )
        return config_path

    def _run(self, config_path: Path, extra_args: list[str]) -> tuple[str, str, int | None]:
        saved_argv = sys.argv
        sys.argv = ["score_backlog", "--config", str(config_path), *extra_args]
        out, err = io.StringIO(), io.StringIO()
        code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    score_backlog.main()
                except SystemExit as exc:
                    code = exc.code
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue(), code

    def _assert_refused(self, extra_args: list[str]):
        config_path = self._write_fixture(rows=2)
        _out, err, code = self._run(config_path, extra_args)
        self.assertEqual(code, 1)
        self.assertIn("duplicate row id(s) in the backlog index: 001, 001", err)

    def test_id_refuses_a_repeated_row_id(self):
        self._assert_refused(["--id", "001"])

    def test_route_id_refuses_a_repeated_row_id(self):
        self._assert_refused(["--route", "--id", "001"])

    def test_dry_run_refuses_a_repeated_row_id(self):
        self._assert_refused(["--dry-run"])

    def test_baseline_index_still_reports_all_three_modes(self):
        config_path = self._write_fixture(rows=1)
        expectations = (
            (["--id", "001"], "001  score"),
            (["--route", "--id", "001"], "001  route"),
            (["--dry-run"], "ID 001"),
        )
        for extra_args, expected in expectations:
            with self.subTest(args=extra_args):
                out, err, code = self._run(config_path, extra_args)
                self.assertIsNone(code)
                self.assertNotIn("duplicate row id", err)
                self.assertIn(expected, out)


if __name__ == "__main__":
    unittest.main()
