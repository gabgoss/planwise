"""Tests for scripts/resolve_next_session.py and the run closeout text it feeds.

The resolver ends a `/planwise run` session with a copy-ready command for the
next session, resolved from the Master Plan tracking table across sprint
boundaries. The text pins hold run.md Step 4.6 and the summary template to
the same contract.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "planwise"
SCRIPT = PLUGIN_ROOT / "scripts" / "resolve_next_session.py"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from resolve_next_session import resolve

TABLE_HEAD = (
    "## Session Completion Tracking\n\n"
    "| Sprint | Session | Status | Summary File | Completed |\n"
    "|--------|---------|--------|--------------|-----------|\n"
)


class _PlanTree:
    """A throwaway project: <root>/planwise/Plans/Demo/ with a Master Plan."""

    def __init__(self, root: Path):
        self.root = root
        self.plan_dir = root / "planwise" / "Plans" / "Demo"
        self.plan_dir.mkdir(parents=True)

    def master(self, rows: list[tuple[str, str, str]] | None) -> None:
        body = "# DEM Master Plan\n\n**Status:** IN_PROGRESS\n\n"
        if rows is not None:
            body += TABLE_HEAD + "".join(
                f"| {sprint} | {session} | {status} | - | - |\n"
                for sprint, session, status in rows
            )
        (self.plan_dir / "DEM-Master-Plan.md").write_text(body, encoding="utf-8")

    def orch(self, sprint: int, session: int, status: str = "NOT_STARTED") -> Path:
        folder = (
            self.plan_dir
            / f"Sprint-{sprint:02d}-Phase{sprint}"
            / f"Session-{session:02d}-Work{session}"
        )
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"DEM-S{sprint:02d}-{session:02d}-Orchestration.md"
        path.write_text(f"# Orchestration\n\n**Status:** {status}\n", encoding="utf-8")
        return path

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()


class ResolveNextSessionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = _PlanTree(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _resolve(self, orchestration: Path) -> list[str]:
        return resolve(orchestration.resolve(), self.tree.root)

    def test_mid_sprint_next(self):
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "🔄 IN PROGRESS"),
            ("Sprint-01", "Session-02-Work2", "⏳ NOT STARTED"),
        ])
        current = self.tree.orch(1, 1)
        nxt = self.tree.orch(1, 2)
        self.assertEqual(
            self._resolve(current),
            [f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}"],
        )

    def test_cross_sprint_boundary(self):
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "✅ COMPLETE"),
            ("Sprint-01", "Session-02-Work2", "🔄 IN PROGRESS"),
            ("Sprint-02", "Session-01-Work1", "⏳ NOT STARTED"),
        ])
        self.tree.orch(1, 1, "COMPLETE")
        current = self.tree.orch(1, 2)
        nxt = self.tree.orch(2, 1)
        lines = self._resolve(current)
        self.assertEqual(lines, [f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}"])
        self.assertIn("Sprint-02-Phase2/Session-01-Work1/DEM-S02-01", lines[0])

    def test_skips_later_rows_already_complete(self):
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "🔄 IN PROGRESS"),
            ("Sprint-01", "Session-02-Work2", "✅ COMPLETE (superseded)"),
            ("Sprint-02", "Session-01-Work1", "⏳ NOT STARTED"),
        ])
        current = self.tree.orch(1, 1)
        self.tree.orch(1, 2, "COMPLETE")
        nxt = self.tree.orch(2, 1)
        self.assertEqual(
            self._resolve(current),
            [f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}"],
        )

    def test_all_complete_gives_none(self):
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "✅ COMPLETE"),
            ("Sprint-02", "Session-01-Work1", "🔄 IN PROGRESS"),
        ])
        self.tree.orch(1, 1, "COMPLETE")
        current = self.tree.orch(2, 1)
        self.assertEqual(self._resolve(current), ["NEXT: none"])

    def test_next_row_unscaffolded(self):
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "🔄 IN PROGRESS"),
            ("Sprint-02", "Session-01-Later", "⏳ NOT STARTED"),
        ])
        current = self.tree.orch(1, 1)
        self.assertEqual(
            self._resolve(current),
            ["NEXT_UNSCAFFOLDED: Sprint-02 Session-01-Later"],
        )

    def test_abbrev_session_cell_shape(self):
        # Some tracking tables name the session as "{Abbrev}-S{XX}-{YY} {Name}".
        self.tree.master([
            ("Sprint-01", "DEM-S01-01 Work1", "🔄 IN PROGRESS"),
            ("Sprint-02", "DEM-S02-01 Work1", "⏳ NOT STARTED"),
        ])
        current = self.tree.orch(1, 1)
        nxt = self.tree.orch(2, 1)
        self.assertEqual(
            self._resolve(current),
            [f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}"],
        )

    def test_no_table_falls_back_to_file_order(self):
        self.tree.master(None)
        current = self.tree.orch(1, 2, "IN_PROGRESS")
        self.tree.orch(1, 1, "COMPLETE")
        self.tree.orch(2, 1, "COMPLETE")
        nxt = self.tree.orch(2, 2)
        lines = self._resolve(current)
        self.assertEqual(lines[0], f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("Coverage: no Session Completion Tracking table"))

    def test_no_table_last_session_gives_none(self):
        self.tree.master(None)
        self.tree.orch(1, 1, "COMPLETE")
        current = self.tree.orch(1, 2, "IN_PROGRESS")
        lines = self._resolve(current)
        self.assertEqual(lines[0], "NEXT: none")
        self.assertTrue(lines[1].startswith("Coverage:"))

    def test_cli_prints_outcome_and_exits_zero(self):
        (self.tree.root / "planwise" / "config.yaml").write_text(
            "project:\n  planwise_root: planwise\n  plans_dir: Plans\n", encoding="utf-8"
        )
        self.tree.master([
            ("Sprint-01", "Session-01-Work1", "🔄 IN PROGRESS"),
            ("Sprint-02", "Session-01-Work1", "⏳ NOT STARTED"),
        ])
        current = self.tree.orch(1, 1)
        nxt = self.tree.orch(2, 1)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [
                sys.executable, "-B", str(SCRIPT),
                "--config", str(self.tree.root / "planwise" / "config.yaml"),
                "--orchestration", str(current),
            ],
            capture_output=True, text=True, encoding="utf-8", env=env, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            f"NEXT: /planwise:planwise run @{self.tree.rel(nxt)}",
        )


def _section(text: str, heading: str) -> str:
    """Return the body of one `### ` section, up to the next `##`-level heading."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = re.search(r"^#{2,3} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


class CloseoutTextPins(unittest.TestCase):
    def setUp(self):
        self.run_md = (PLUGIN_ROOT / "handlers" / "run.md").read_text(encoding="utf-8")

    def test_step_4_6_ends_with_fenced_run_command(self):
        body = _section(self.run_md, "### Step 4.6: Output Completion")
        self.assertRegex(body, r"```\s*\n\s*/planwise:planwise run @\{path\}\s*\n\s*```")
        self.assertIn("Plan status:", body)
        self.assertNotIn('"Sprint complete"', body)

    def test_step_4_1_calls_the_resolver(self):
        body = _section(self.run_md, "### Step 4.1: Generate Session Summary")
        self.assertIn("scripts/resolve_next_session.py", body)
        self.assertIn("--orchestration", body)
        self.assertNotIn("Sprint plan dependencies", body)

    def test_summary_template_carries_next_run(self):
        text = (PLUGIN_ROOT / "templates" / "summary-template.md").read_text(encoding="utf-8")
        section = text[text.index("## Next Session"):]
        self.assertIn("**Next run:**", section)
        self.assertNotIn("Session-{YY+1}", text)


if __name__ == "__main__":
    unittest.main()
