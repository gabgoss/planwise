#!/usr/bin/env python3
"""Unit tests for scripts/list_plans.py (the /planwise list renderer).

Each test builds an isolated temp planwise tree (config.yaml, a generated-shape
plans index and Master Plan files). None read or write the live project.

Run from the project root:
    python -B -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_list_plans.py
"""

import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import list_plans
import reconcile_plans
from generate_plans_index import TABLE_SEPARATOR, render_plans_index

CONFIG_YAML = """project:
  name: "ListPlansFixtureProject"
  plans_dir: "Plans"
  index_files:
    plans: "00-Index-Plans.md"
"""

NO_DRIFT = "No drift detected. All index rows match their Master Plan status."
MARKER = "PLANWISE_LIST_FALLBACK:"
HEADER_RAN = "planwise list — plans index drift audit"
HEADER_COULD_NOT_RUN = "planwise list — plans index drift audit could not run"
HEADER_LEGACY = "planwise list — legacy-shaped plans index — run /planwise upgrade"
EMPTY_ACTIVE = "No active plans found (status PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, NEEDS_FIXES or IN_PROGRESS)."
ACTIVE_SUMMARY = (
    "{n} active plan(s) shown (filtered to PLANNING, READY_TO_EXECUTE, REVIEWED, APPROVED, "
    "NEEDS_FIXES and IN_PROGRESS). Run `/planwise list` to see all."
)


def _row(abbrev, name, status, created="2026-01-01", last_updated="2026-01-01", path=None):
    return f"| {abbrev} | {name} | {status} | {created} | {last_updated} | {path or name + '/'} |\n"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="list_plans_test_")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True)
        (self.planwise_dir / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        self.config_path = self.planwise_dir / "config.yaml"
        self.config = config_loader.load_config(config_path=self.config_path)

        saved_cwd = Path.cwd()
        self.addCleanup(os.chdir, saved_cwd)
        os.chdir(self.tmp)

    def index_text(self, rows_markdown, generated=True):
        frame = render_plans_index(self.config).frame
        text = frame.replace(TABLE_SEPARATOR + "\n", TABLE_SEPARATOR + "\n" + rows_markdown, 1)
        if not generated:
            text = "\n".join(ln for ln in text.split("\n") if not ln.startswith("Generated:"))
        return text

    def write_index(self, rows_markdown, generated=True):
        path = self.plans_dir / "00-Index-Plans.md"
        path.write_text(self.index_text(rows_markdown, generated), encoding="utf-8")
        return path

    def write_master_plan(self, name, abbrev, status, created="2026-01-01", last_updated="2026-01-01"):
        mp_dir = self.plans_dir / name
        mp_dir.mkdir(parents=True, exist_ok=True)
        body = f"# {abbrev} Master Plan\n\n**Status:** {status}\n**Created:** {created}\n\n*Last Updated: {last_updated}*\n"
        (mp_dir / f"{abbrev}-Master-Plan.md").write_text(body, encoding="utf-8")

    def run_list(self, *flags, config=True):
        args = list(flags)
        if config:
            args = ["--config", str(self.config_path), *args]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = list_plans.main(args)
        return code, out.getvalue(), err.getvalue()

    def table_rows(self, stdout):
        """Data rows of the rendered table: pipe lines minus the header and separator."""
        lines = [ln for ln in stdout.split("\n") if ln.startswith("|")]
        return lines[2:]


class TestRendering(_Base):
    def test_five_columns_no_path_row_count_matches(self):
        written = [("AAA", "Alpha", "COMPLETE"), ("BBB", "Beta", "IN_PROGRESS"), ("CCC", "Gamma", "PLANNING")]
        self.write_index("".join(_row(a, n, s) for a, n, s in written))
        code, out, _err = self.run_list("--no-check")
        self.assertEqual(code, 0)
        header = next(ln for ln in out.split("\n") if ln.startswith("| Abbrev"))
        self.assertEqual([c.strip() for c in header.strip("|").split("|")], list(list_plans.COLUMNS))
        self.assertNotIn("Path", header)
        rows = self.table_rows(out)
        self.assertEqual(len(rows), len(written))
        for row in rows:
            self.assertEqual(len(row.strip("|").split("|")), 5)
            self.assertNotIn("/", row)  # the Path column values end in "/"
        self.assertIn("3 plan(s) shown. Run `/planwise plan` to create a new plan.", out)

    def test_pipe_in_a_cell_stays_escaped_and_the_row_keeps_five_cells(self):
        self.write_index(_row("AAA", "Foo \\| Bar", "COMPLETE"))
        code, out, _err = self.run_list("--no-check")
        self.assertEqual(code, 0)
        rows = self.table_rows(out)
        self.assertEqual(len(rows), 1)
        self.assertIn("| Foo \\| Bar |", rows[0])
        self.assertEqual(len(re.split(r"(?<!\\)\|", rows[0].strip())[1:-1]), 5)

    def test_interleaved_comment_and_blank_lines_do_not_truncate(self):
        rows = [("AAA", "Alpha", "COMPLETE"), ("BBB", "Beta", "COMPLETE"), ("CCC", "Gamma", "COMPLETE")]
        text = _row(*rows[0]) + "<!-- note -->\n\n" + _row(*rows[1]) + _row(*rows[2])
        for abbrev, name, status in rows:
            self.write_master_plan(name, abbrev, status)
        self.write_index(text)

        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.table_rows(out)), 3)
        self.assertEqual(reconcile_plans.detect_drift(self.config)["compared"], 3)
        self.assertIn("3 of 3 rows compared.", out)

        # Discrimination: a naive "stop at the first non-pipe line after the separator" count sees 1 row.
        lines = self.index_text(text).split("\n")
        start = next(i for i, ln in enumerate(lines) if ln.startswith("|") and set(ln) <= set("|- ")) + 1
        naive = 0
        for ln in lines[start:]:
            if not ln.startswith("|"):
                break
            naive += 1
        self.assertEqual(naive, 1)

    def test_active_filter_keeps_the_six_active_statuses(self):
        kept = [
            ("A01", "Planning", "PLANNING"),
            ("A02", "Ready", "READY_TO_EXECUTE"),
            ("A03", "Reviewed", "REVIEWED"),
            ("A04", "Approved", "APPROVED"),
            ("A05", "Fixes", "NEEDS_FIXES"),
            ("A06", "Going", "IN_PROGRESS"),
            ("A07", "Noted", "IN_PROGRESS — note"),
        ]
        dropped = [
            ("D01", "NotStarted", "NOT_STARTED"),
            ("D02", "Blocked", "BLOCKED"),
            ("D03", "Done", "COMPLETE"),
            ("D04", "Closed", "CLOSED"),
            ("D05", "Held", "ON_HOLD"),
        ]
        self.write_index("".join(_row(a, n, s) for a, n, s in kept + dropped))
        code, out, _err = self.run_list("--active", "--no-check")
        self.assertEqual(code, 0)
        rows = self.table_rows(out)
        self.assertEqual(len(rows), len(kept))
        for abbrev, _name, _status in kept:
            self.assertTrue(any(f"| {abbrev} |" in r for r in rows), abbrev)
        for abbrev, _name, _status in dropped:
            self.assertFalse(any(f"| {abbrev} |" in r for r in rows), abbrev)
        self.assertTrue(any("IN_PROGRESS — note" in r for r in rows))
        self.assertIn(ACTIVE_SUMMARY.format(n=len(kept)), out)

    def test_active_statuses_are_exactly_the_six(self):
        self.assertEqual(
            list_plans.ACTIVE_STATUSES,
            {"PLANNING", "READY_TO_EXECUTE", "REVIEWED", "APPROVED", "NEEDS_FIXES", "IN_PROGRESS"},
        )

    def test_active_empty_prints_two_line_text_and_zero_summary(self):
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        code, out, _err = self.run_list("--active", "--no-check")
        self.assertEqual(code, 0)
        self.assertIn(EMPTY_ACTIVE, out)
        self.assertIn("Use `/planwise list` to see all plans.", out)
        self.assertEqual(self.table_rows(out), [])
        self.assertIn(ACTIVE_SUMMARY.format(n=0), out)


class TestBanner(_Base):
    def test_ran_complete_prints_header_all_clear_and_compared_line(self):
        self.write_master_plan("Alpha", "AAA", "COMPLETE")
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[0], HEADER_RAN)
        self.assertEqual(out.split("\n")[1], "")
        self.assertIn(NO_DRIFT, out)
        self.assertIn("1 of 1 rows compared.", out)

    def test_ran_with_drift_prints_header_and_drift_line_not_all_clear(self):
        self.write_master_plan("Drifty", "DRF", "COMPLETE")
        self.write_index(_row("DRF", "Drifty", "IN_PROGRESS"))
        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[0], HEADER_RAN)
        self.assertIn("Drift detected", out)
        self.assertIn("  - DRF: index=IN_PROGRESS -> Master Plan=COMPLETE", out)
        self.assertNotIn("No drift detected", out)

    def test_could_not_run_prints_could_not_run_header(self):
        # The index holds a row but no Master Plan exists on disk, so no row is compared.
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        result = reconcile_plans.detect_drift(self.config)
        self.assertEqual(result["status"], "could-not-run")
        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[0], HEADER_COULD_NOT_RUN)
        self.assertIn("Drift audit could not run: 0 of 1 rows compared", out)
        self.assertIn("No index row matched a Master Plan on disk.", out)
        self.assertNotIn("No drift detected", out)

    def test_could_not_run_names_missing_row_count_only_when_present(self):
        # A Master Plan exists with no index row, and the one index row matches no plan: compared is 0.
        self.write_master_plan("Alpha", "AAA", "COMPLETE")
        self.write_index(_row("ZZZ", "Zed", "COMPLETE"))
        result = reconcile_plans.detect_drift(self.config)
        self.assertEqual(result["status"], "could-not-run")
        self.assertEqual([d["class"] for d in result["drifts"]], ["missing-row"])
        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertIn("1 Master Plan(s) on disk have no row in the index (missing-row).", out)
        # Without missing-row records the line is absent.
        base = {"status": "could-not-run", "compared": 0, "total": 2, "drifts": [], "anomalies": []}
        text = "\n".join(list_plans.render_banner(base, self.plans_dir / "00-Index-Plans.md"))
        self.assertNotIn("missing-row", text)

    def test_could_not_run_with_index_missing_text(self):
        lines = list_plans.render_banner(
            {"status": "could-not-run", "compared": 0, "total": 4, "drifts": [], "anomalies": []},
            self.plans_dir / "absent-index.md",
        )
        self.assertEqual(lines[0], HEADER_COULD_NOT_RUN)
        self.assertEqual(lines[1], "")
        self.assertIn("Drift audit could not run: 0 of 4 rows compared", lines)
        self.assertIn("The index is missing and the tree holds 4 Master Plans.", lines)

    def test_incomplete_prints_could_not_run_header_and_unparsed_lines(self):
        result = {
            "status": "incomplete",
            "compared": 1,
            "total": 2,
            "drifts": [],
            "anomalies": [{"class": "unparsed-rows", "lines": [{"line": 9, "reason": "five cells"}]}],
        }
        lines = list_plans.render_banner(result, self.plans_dir / "00-Index-Plans.md")
        self.assertEqual(lines[0], HEADER_COULD_NOT_RUN)
        self.assertIn("Drift audit incomplete: 1 of 2 rows compared", lines)
        self.assertIn("  - line 9: table-shaped but yields no row (five cells)", lines)
        self.assertNotIn("No drift detected", "\n".join(lines))

    def test_ran_with_uncompared_rows_is_treated_as_incomplete(self):
        result = {"status": "ran", "compared": 1, "total": 2, "drifts": [], "anomalies": []}
        lines = list_plans.render_banner(result, self.plans_dir / "00-Index-Plans.md")
        self.assertEqual(lines[0], HEADER_COULD_NOT_RUN)
        self.assertIn("Drift audit incomplete: 1 of 2 rows compared", lines)
        self.assertNotIn("No drift detected", "\n".join(lines))

    def test_legacy_shape_prints_legacy_header_and_message(self):
        self.write_master_plan("Alpha", "AAA", "COMPLETE")
        index = self.write_index(_row("AAA", "Alpha", "COMPLETE"), generated=False)
        code, out, _err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[0], HEADER_LEGACY)
        self.assertIn(reconcile_plans._legacy_message(index), out)
        self.assertIn("hand-authored plans index", out)
        self.assertNotIn("No drift detected", out)
        self.assertNotIn(MARKER, out)

    def test_index_missing_prints_only_the_fallback_line_with_no_header(self):
        missing = self.plans_dir / "00-Index-Plans.md"
        result = {"status": "index-missing", "compared": 0, "total": 0, "drifts": [], "anomalies": []}
        lines = list_plans.render_banner(result, missing)
        self.assertEqual(lines, [f"{MARKER} Plans index not found at {missing}"])
        # End to end, the missing index stops the run before the banner is built.
        code, out, err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out.strip(), lines[0])
        self.assertNotIn("drift audit", out)

    def test_all_clear_appears_only_for_a_complete_ran(self):
        base = {"compared": 2, "total": 2, "drifts": [], "anomalies": []}
        path = self.plans_dir / "00-Index-Plans.md"
        for status in ("could-not-run", "incomplete", "legacy-shape", "index-missing"):
            with self.subTest(status=status):
                text = "\n".join(list_plans.render_banner({**base, "status": status}, path))
                self.assertNotIn("No drift detected", text)
        self.assertIn("No drift detected", "\n".join(list_plans.render_banner({**base, "status": "ran"}, path)))

    def test_no_check_prints_neither(self):
        self.write_master_plan("Alpha", "AAA", "COMPLETE")
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        code, out, _err = self.run_list("--no-check")
        self.assertEqual(code, 0)
        self.assertNotIn("drift audit", out)
        self.assertNotIn("No drift detected", out)


class TestFallbacks(_Base):
    def marker_lines(self, out):
        return [ln for ln in out.split("\n") if ln.startswith(MARKER)]

    def test_missing_config_names_cwd_single_marker(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        os.chdir(empty)
        code, out, err = self.run_list(config=False)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = self.marker_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertIn(str(empty), lines[0])
        self.assertIn("config.yaml not found at", lines[0])
        self.assertEqual(out.strip(), lines[0])

    def test_missing_index_single_marker(self):
        code, out, err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = self.marker_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertIn("Plans index not found at", lines[0])
        self.assertEqual(out.strip(), lines[0])

    def test_cwd_bounded_resolution_does_not_walk_down_two_levels(self):
        nested = self.tmp / "outer" / "inner" / "planwise"
        nested.mkdir(parents=True)
        (nested / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
        os.chdir(self.tmp / "outer")
        code, out, _err = self.run_list(config=False)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.marker_lines(out)), 1)
        self.assertIn("config.yaml not found at", out)

    def test_cwd_one_level_above_config_resolves_without_flag(self):
        # Branch b): cwd/*/config.yaml. The tmp root holds planwise/config.yaml.
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        code, out, _err = self.run_list("--no-check", config=False)
        self.assertEqual(code, 0)
        self.assertEqual(out.count(MARKER), 0)
        self.assertEqual(len(self.table_rows(out)), 1)

    def test_planwise_config_wins_over_an_alphabetically_earlier_decoy(self):
        decoy = self.tmp / "app"
        decoy.mkdir()
        (decoy / "config.yaml").write_text(
            'project:\n  name: "Decoy"\n  plans_dir: "Elsewhere"\n  index_files:\n    plans: "x.md"\n',
            encoding="utf-8",
        )
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        code, out, _err = self.run_list("--no-check", config=False)
        self.assertEqual(code, 0)
        self.assertEqual(out.count(MARKER), 0)
        self.assertEqual(len(self.table_rows(out)), 1)

    def test_missing_option_value_still_exits_zero_with_one_marker(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = list_plans.main(["--config"])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.marker_lines(out.getvalue())), 1)

    def test_malformed_config_gives_parse_error_marker(self):
        self.config_path.write_text("project: [unclosed\n  - x: : :\n", encoding="utf-8")
        code, out, err = self.run_list()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = self.marker_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"config\.yaml parse error at .*config\.yaml: ")


class TestStderr(_Base):
    def test_stderr_empty_on_success_paths(self):
        self.write_master_plan("Alpha", "AAA", "COMPLETE")
        self.write_index(_row("AAA", "Alpha", "COMPLETE"))
        for flags in ((), ("--active",), ("--no-check",), ("--active", "--no-check")):
            with self.subTest(flags=flags):
                code, out, err = self.run_list(*flags)
                self.assertEqual(code, 0)
                self.assertEqual(err, "")
                self.assertNotRegex(out, re.escape(MARKER))


if __name__ == "__main__":
    unittest.main()
