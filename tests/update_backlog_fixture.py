"""Shared fixture for the update_backlog test files.

`_UpdateBacklogFixtureBase` builds an isolated temp planwise tree and drives
update_backlog.main() through an injected argv. test_update_backlog.py,
test_update_backlog_create.py and test_update_backlog_fixed_in.py all build
on it. The name carries no `test_` prefix, so pytest does not collect it.
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

import update_backlog
from parse_backlog import parse_backlog_table

CONFIG_YAML_FIXTURE = """project:
  name: "UpdateBacklogFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

INDEX_HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Score | Files |\n"
    "|-----|---------|----------|--------|--------|-------|-------|\n"
)


class _UpdateBacklogFixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="update_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

    def write_index(self, rows_markdown: str) -> Path:
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_text(INDEX_HEADER + rows_markdown, encoding="utf-8")
        return path

    def write_item_file(
        self, filename: str, status: str, archived: bool = False, item_id: str = "X"
    ) -> Path:
        """Write an item file with `item_id` in its own frontmatter `id:`.

        `update_backlog.py` now locates an item's file by matching this
        field against `--id`, never by the hub's Files column -- a caller
        that wants `--status`/`--create` to find the file MUST pass the
        real numeric id the test exercises. The "X" default only serves
        fixtures that never drive a lookup by id.
        """
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(
            f"---\nid: {item_id}\nstatus: {status}\ncreated: 2026-07-06\n---\n\n# {filename}\n",
            encoding="utf-8",
        )
        return path

    def run_update(self, item_id: str, status: str) -> str:
        """Invoke update_backlog.main() via an injected argv; return stdout."""
        saved_argv = sys.argv
        sys.argv = [
            "update_backlog",
            "--config",
            str(self.config_path),
            "--id",
            item_id,
            "--status",
            status,
        ]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                update_backlog.main()
        finally:
            sys.argv = saved_argv
        return buf.getvalue()

    def _run_main(self, argv_tail: list[str]) -> tuple[str, str, object]:
        """Invoke update_backlog.main() with a raw argv tail.

        Returns (stdout, stderr, exit_code). exit_code is None when main()
        returned normally instead of calling sys.exit().
        """
        saved_argv = sys.argv
        sys.argv = ["update_backlog"] + argv_tail
        out, err = io.StringIO(), io.StringIO()
        exit_code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    update_backlog.main()
                except SystemExit as e:
                    exit_code = e.code
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue(), exit_code

    def read_index_text(self) -> str:
        return (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")

    def row(self, item_id: str) -> dict:
        rows = parse_backlog_table(self.read_index_text())
        return next(r for r in rows if r["id"] == item_id)
