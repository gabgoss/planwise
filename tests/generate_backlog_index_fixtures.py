#!/usr/bin/env python3
"""Shared fixtures for the backlog-index generator's test modules.

This is a helper, not a test module: its name matches neither `test_*.py` nor
`*_test.py`, so pytest never collects it. The `test_generate_backlog_index*.py`
modules and several other test files import these names from here, so no test
module serves as another's fixture library.

It holds the `sys.path` bootstrap to the shipped scripts, the config fixture,
the pure in-memory backlog directory, the already-scanned item builder, and
the base class that builds an isolated temp planwise tree.
"""

import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi

CONFIG_YAML_FIXTURE = """project:
  name: "GeneratorFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

# A backlog_dir for the pure in-memory rendering tests below, which never
# touch a filesystem -- split_items_to_budget/render_table_body only need a
# Path to compute a relative File-cell link, never to read or write.
_PURE_BACKLOG_DIR = Path("Backlog")


def _make_item(item_id, *, blocks=None, title="Fixture item", priority="Medium",
                status="NOT_STARTED", abbrev="BUG", created="2026-01-01", score="10"):
    """Build an already-scanned item dict, matching what scan_backlog would
    have produced, for tests that exercise rendering/sharding directly."""
    id_str = f"{item_id:03d}"
    return {
        "id": id_str,
        "title": title,
        "priority": priority,
        "status": status,
        "abbrev": abbrev,
        "created": created,
        "blocks": blocks or [],
        "score": score,
        "_path": _PURE_BACKLOG_DIR / f"BB-{id_str}-01-{abbrev}-Fixture.md",
    }


class _GeneratorFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree: config.yaml + Backlog/ +
    Backlog/Archive/, so the generator's CLI runs against a hermetic copy
    instead of the live project's backlog.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def write_item(self, item_id, *, title="Fixture item", priority="Medium",
                   status="NOT_STARTED", abbrev="BUG", created="2026-01-01",
                   blocks=None, archived=False, filename=None,
                   extra_frontmatter="", body=""):
        """Write one synthetic item file with valid frontmatter. `body` is appended
        after the title line, for a test that needs section prose."""
        blocks = blocks or []
        blocks_yaml = "[]" if not blocks else "[" + ", ".join(blocks) + "]"
        content = (
            "---\n"
            f"id: {item_id}\n"
            f"title: {title}\n"
            f"priority: {priority}\n"
            f"status: {status}\n"
            f"abbrev: {abbrev}\n"
            f"created: {created}\n"
            f"blocks: {blocks_yaml}\n"
            f"{extra_frontmatter}"
            "---\n\n"
            f"# {title}\n"
            f"{body}"
        )
        target_dir = self.archive_dir if archived else self.backlog_dir
        name = filename or f"BB-{item_id}-01-{abbrev}-Fixture.md"
        path = target_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def run_main(self, *extra_args):
        """Invoke main() against the fixture config, capturing stdout/stderr."""
        sys.argv = ["test_generate_backlog_index", "--config", str(self.config_path), *extra_args]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gbi.main()
        return code, out.getvalue(), err.getvalue()
