"""Shared helper rows and fixture base for the parse_backlog test files.

`_ParseBacklogFixtureBase` builds an isolated temp planwise tree and drives
parse_backlog.main() through an injected argv. The module also holds the index
headers and the row builders. test_parse_backlog.py and
test_parse_backlog_blockers.py both build on it. The name carries no `test_`
prefix, so pytest does not collect it.
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

import parse_backlog

HEADER = (
    "# Backlog Index\n\n"
    "## Backlog Items\n\n"
    "| ID  | Feature | Priority | Status | Abbrev | Files |\n"
    "|-----|---------|----------|--------|--------|-------|\n"
)

CONFIG_YAML_FIXTURE = """project:
  name: "ParseBacklogFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

GENERATED_9COL_HEADER = (
    "|" + "|".join(
        f" {c} " for c in
        ("ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File")
    ) + "|\n"
    + "|" + "|".join(["---"] * 9) + "|\n"
)


def _row(item_id: str, status: str = "NOT_STARTED", feature: str | None = None) -> str:
    feature = feature or f"Feature {item_id}"
    slug = item_id.replace("/", "-")
    return f"| {item_id} | {feature} | Low | {status} | DOC | [01](x-{slug}.md) |\n"


def _row9(
    item_id: str,
    status: str = "NOT_STARTED",
    feature: str | None = None,
    abbrev: str = "DOC",
    blocks: str = "",
    score: str = "0",
) -> str:
    """One 9-column generated-shape row, matching
    `generate_backlog_index.render_row`'s cell order (ID, Title, Priority,
    Status, Domain, Created, Blocks, Score, File)."""
    feature = feature or f"Feature {item_id}"
    return (
        f"| {item_id} | {feature} | Low | {status} | {abbrev} | 2024-01-01 | "
        f"{blocks} | {score} | [{item_id}](BB-{item_id}-x.md) |\n"
    )


class _ParseBacklogFixtureBase(unittest.TestCase):
    """CLI-path fixture: temp planwise tree + injected argv, mirroring
    update_backlog_fixture.py's `_UpdateBacklogFixtureBase` pattern."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

    def write_index(self, rows_markdown: str) -> Path:
        path = self.backlog_dir / "00-Index-Backlog.md"
        path.write_text(HEADER + rows_markdown, encoding="utf-8")
        return path

    def run_next_id(self) -> tuple[str, str]:
        """Invoke parse_backlog.main() with --next-id; return (stdout, stderr)."""
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path), "--next-id"]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue().strip(), err.getvalue()

    def run_parse(self, extra_args: list[str] | None = None) -> tuple[str, str]:
        """Invoke parse_backlog.main() with the plain CLI path; return (stdout, stderr)."""
        saved_argv = sys.argv
        sys.argv = ["parse_backlog", "--config", str(self.config_path), *(extra_args or [])]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parse_backlog.main()
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue()
