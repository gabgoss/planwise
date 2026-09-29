#!/usr/bin/env python3
"""Unit tests for plans-index drift detection and reconciliation.

`reconcile_plans.detect_drift(config)` compares the plans index on disk with
the index the generator would render from the Master Plans. A row that exists
on both sides with a differing field is a `stale-row` (one finding per field),
a Master Plan the index lacks is a `missing-row`, and an index row whose Master
Plan is gone is an `orphan-row` anomaly. `reconcile_plans.reconcile(config)`
re-reads the index fresh and hands the write to the generator, so it never
computes a cell itself. A row a concurrent writer healed since a prior detect
is not counted and not rewritten.

The CLI never prints an all-clear over a comparison it could not make: zero
compared rows exits 3, a partial parse exits 3, and a hand-authored (legacy)
index exits 2.

Each test builds an isolated temp planwise tree (config.yaml + Plans index +
Master Plan files) under a unittest tempfile fixture; none read or mutate the
live project's Plans index.

Run with:  python -m pytest -q -c cloned-repos/planwise/pytest.ini cloned-repos/planwise/tests/test_reconcile_plans.py
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

# Allow imports whether pytest is launched from the repo root
# (python -m pytest scripts/test_...) or from inside scripts/.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import config_loader
import generate_plans_index
from generate_plans_index import TABLE_SEPARATOR, render_plans_index
from reconcile_plans import (
    LegacyIndexError,
    WriteRefusedError,
    base_token,
    detect_drift,
    main,
    parse_plans_index,
    reconcile,
    resolve_master_plan_path,
)

# A minimal config.yaml the fixture tree can resolve via
# config_loader.load_config's explicit --config path.
CONFIG_YAML_FIXTURE = """project:
  name: "ReconcileFixtureProject"
  plans_dir: "Plans"
  index_files:
    plans: "00-Index-Plans.md"
"""


def _row(abbrev, name, status, created, last_updated, path):
    return f"| {abbrev} | {name} | {status} | {created} | {last_updated} | {path} |\n"


class _ReconcileFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree: config.yaml + Plans index +
    per-row Master Plan files, so detect_drift/reconcile run against a
    hermetic copy instead of the live project's Plans index.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_plans_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.plans_dir = self.planwise_dir / "Plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML_FIXTURE, encoding="utf-8"
        )

        # load_config() reads --config from sys.argv rather than taking a
        # path argument; inject it for the duration of the test so the
        # fixture config is loaded instead of the real project's config.yaml.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_reconcile_plans",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()

    def index_text(self, rows_markdown: str, generated: bool = True) -> str:
        """The index file text: the generator's own frame with the rows inserted.

        The frame is `render_plans_index(...).frame`, so the title, the
        `Generated:` line, the intro, the header and the legend are the
        generated shape by construction. `generated=False` drops the
        `Generated:` line, which makes the file the hand-authored (legacy) shape.
        """
        frame = render_plans_index(self.config).frame
        text = frame.replace(TABLE_SEPARATOR + "\n", TABLE_SEPARATOR + "\n" + rows_markdown, 1)
        if not generated:
            text = "\n".join(line for line in text.split("\n") if not line.startswith("Generated:"))
        return text

    def write_index(self, rows_markdown: str, generated: bool = True) -> Path:
        """Write the Plans index file: the generated frame plus the given rows."""
        path = self.plans_dir / "00-Index-Plans.md"
        path.write_text(self.index_text(rows_markdown, generated), encoding="utf-8")
        return path

    def write_master_plan(
        self,
        rel_path: str,
        abbrev: str,
        status: str,
        last_updated: str | None = None,
        meta: bool = False,
        created: str = "2026-01-01",
    ) -> Path:
        """Write a Master Plan at Plans/{rel_path}/{abbrev}-Master-Plan.md.

        When meta=True, writes the Discovery/Meta filename convention
        {abbrev}-META-Master-Plan.md instead of {abbrev}-Master-Plan.md.
        The body carries a `**Created:**` line, so a fixture row matches the
        render on Created and a test asserts only the field it is about.
        """
        mp_dir = self.plans_dir / rel_path
        mp_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{abbrev}-META-Master-Plan.md" if meta else f"{abbrev}-Master-Plan.md"
        )
        mp_path = mp_dir / filename
        body = f"# {abbrev} Master Plan\n\n**Status:** {status}\n**Created:** {created}\n"
        if last_updated:
            body += f"\n*Last Updated: {last_updated}*\n"
        mp_path.write_text(body, encoding="utf-8")
        return mp_path

    def read_index_text(self) -> str:
        return (self.plans_dir / "00-Index-Plans.md").read_text(encoding="utf-8")

    def run_cli(self, *flags: str) -> tuple[int, str, str]:
        """Run `main()` in-process against the fixture config. Returns (exit code, stdout, stderr)."""
        saved = sys.argv
        sys.argv = ["reconcile_plans", "--config", str(self.planwise_dir / "config.yaml"), *flags]
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main()
        finally:
            sys.argv = saved
        return code, out.getvalue(), err.getvalue()


class TestReconcilePlans(_ReconcileFixtureBase):
    """Full detect_drift / reconcile test matrix."""

    def test_detect_finds_stale_terminal_row(self):
        # Reproduction: an index row still shows an execution status after
        # its Master Plan has actually completed.
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19", created="2026-03-19")

        result = detect_drift(self.config)

        self.assertEqual(len(result["drifts"]), 1)
        self.assertEqual(result["anomalies"], [])
        drift = result["drifts"][0]
        self.assertEqual(drift["abbrev"], "PRC")
        self.assertEqual(drift["index_status"], "READY_TO_EXECUTE")
        self.assertEqual(drift["mp_status"], "COMPLETE")
        self.assertEqual(drift["mp_last_updated"], "2026-03-19")

    def test_reconcile_writes_and_mirrors_date(self):
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19", created="2026-03-19")

        written = reconcile(self.config)

        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        self.assertEqual(prc["status"], "COMPLETE")
        # Mirrors the Master Plan's own Last Updated footer date — NOT today.
        self.assertEqual(prc["last_updated"], "2026-03-19")

    def test_gated_suffix_not_drift(self):
        # A trailing note suffix on the Master Plan's Status must not
        # register as drift when the base token still matches the index.
        self.write_index(
            "| FOO | Foo | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Foo/ |\n"
        )
        self.write_master_plan(
            "Foo/", "FOO", "IN_PROGRESS -- awaiting user transfer", "2026-01-01"
        )

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])

    def test_bolded_status_matching_index_not_drift(self):
        # Read-side symmetry: a Master Plan whose Status token is markdown-bolded
        # ("**COMPLETE**") against an index cell already holding the plain enum
        # token ("COMPLETE") must NOT register as drift. Without emphasis-
        # stripping in base_token, "**COMPLETE**" != "COMPLETE" and a fully-
        # reconciled row reads as false drift. This is the read/detect-side twin
        # of test_reconcile_bolded_status_writes_bare_token (which pins the write
        # side): a clean "COMPLETE" fixture would pass while masking the gap.
        self.write_index(
            "| BLD | Bold | COMPLETE | 2026-01-01 | 2026-01-01 | Bold/ |\n"
        )
        self.write_master_plan("Bold/", "BLD", "**COMPLETE**", "2026-01-01")

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])

    def test_missing_master_plan_is_anomaly(self):
        # A row whose Path does not resolve to an existing Master Plan file
        # must be reported as an anomaly, not drift. The generator owns the
        # write, and its render has no row for a plan that is gone, so
        # reconcile drops the orphan row.
        self.write_index(
            "| BAR | BarPlan | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Bar/ |\n"
        )
        # Intentionally do not write a Master Plan for BAR.

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        anomaly = result["anomalies"][0]
        self.assertEqual(anomaly["class"], "orphan-row")
        self.assertEqual(anomaly["abbrev"], "BAR")
        self.assertIn("not found", anomaly["reason"].lower())

        written = reconcile(self.config)
        self.assertEqual(written, 1)
        self.assertEqual(parse_plans_index(self.read_index_text()), [])

    def test_nonstandard_token_divergence(self):
        # A verbatim status divergence outside any documented enum must
        # still register as drift without raising.
        self.write_index(
            "| BAZ | Baz | REVIEWED | 2026-01-01 | 2026-01-01 | Baz/ |\n"
        )
        self.write_master_plan("Baz/", "BAZ", "APPROVED", "2026-01-01")

        result = detect_drift(self.config)

        self.assertEqual(len(result["drifts"]), 1)
        self.assertEqual(result["drifts"][0]["mp_status"], "APPROVED")

    def test_reconcile_only_still_drifted(self):
        # Race safety: a row detect_drift found drifted may already have
        # been healed on disk by a concurrent writer by the time reconcile
        # runs. reconcile must re-read and leave it untouched, not clobber
        # it back to a value computed from a stale prior detect() call.
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-07-01", created="2026-03-19")

        pre = detect_drift(self.config)
        # One finding per differing field: Status and Last Updated.
        self.assertEqual(len(pre["drifts"]), 2)

        # Simulate a concurrent writer healing the row before reconcile runs.
        self.write_index(
            "| PRC | PluginRootConfig | COMPLETE | 2026-03-19 | 2026-07-01 | PluginRootConfig/ |\n"
        )

        written = reconcile(self.config)

        self.assertEqual(written, 0)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        self.assertEqual(prc["status"], "COMPLETE")
        self.assertEqual(prc["last_updated"], "2026-07-01")

    def test_date_fallback_today(self):
        # A Master Plan with a Status field but no parseable Last Updated
        # footer has no date to mirror. The generator invents none: the cell
        # renders `-`, and the render carries a `missing-field` warning.
        self.write_index(
            "| QUX | Qux | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Qux/ |\n"
        )
        self.write_master_plan("Qux/", "QUX", "COMPLETE", last_updated=None)

        written = reconcile(self.config)

        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        qux = next(r for r in rows if r["abbrev"] == "QUX")
        self.assertEqual(qux["status"], "COMPLETE")
        self.assertEqual(qux["last_updated"], "-")
        self.assertNotEqual(qux["last_updated"], datetime.now().astimezone().date().isoformat())
        warnings = render_plans_index(self.config).warnings
        self.assertEqual([(w["class"], w["field"]) for w in warnings], [("missing-field", "last_updated")])

    def test_reconcile_writes_bare_token_not_annotated_status(self):
        # Real Master Plans annotate the Status line heavily
        # ("COMPLETE -- all sprints done 2026-06-01 (ref)"). Detection
        # normalizes to the base token, but the WRITE must also store only the
        # bare token, or the one-token index cell is corrupted with a whole
        # sentence (breaking exact-token --active filtering and re-parsing).
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan(
            "PluginRootConfig/",
            "PRC",
            "COMPLETE -- all sprints done 2026-06-01 (see notes)",
            "2026-03-19",
            created="2026-03-19",
        )

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"][0]["mp_status"], "COMPLETE")

        written = reconcile(self.config)
        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        # Bare enum token written to the cell, not the annotated sentence.
        self.assertEqual(prc["status"], "COMPLETE")
        self.assertEqual(prc["last_updated"], "2026-03-19")

    def test_reconcile_bolded_status_writes_bare_token(self):
        # A Master Plan whose Status token is markdown-bolded ("**COMPLETE**")
        # must reconcile to the plain enum token, not "**COMPLETE**".
        self.write_index(
            "| PPU | PluginUpgrade | IN_PROGRESS | 2026-05-01 | 2026-05-01 | PluginUpgrade/ |\n"
        )
        self.write_master_plan(
            "PluginUpgrade/",
            "PPU",
            "**COMPLETE** (2026-05-26) -- shipped v1.2.0",
            "2026-05-26",
            created="2026-05-01",
        )

        written = reconcile(self.config)
        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        ppu = next(r for r in rows if r["abbrev"] == "PPU")
        self.assertEqual(ppu["status"], "COMPLETE")
        self.assertEqual(ppu["last_updated"], "2026-05-26")

    def test_reconcile_mirrors_annotated_footer_date(self):
        # The Last Updated footer commonly annotates the date
        # ("*Last Updated: 2026-03-19 (plan COMPLETE)*"). The mirror must
        # capture the date and NOT fall back to today.
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan(
            "PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19 (plan COMPLETE)", created="2026-03-19"
        )

        written = reconcile(self.config)
        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        # Mirrors the date embedded in the annotated footer, not today.
        self.assertEqual(prc["last_updated"], "2026-03-19")

    def test_meta_plan_resolves_via_meta_fallback(self):
        # A Discovery/Meta plan carries a Meta-{ABBR}/ Path marker and names its
        # Master Plan {ABBR}-META-Master-Plan.md. The resolver must fall back to
        # that name so a well-formed Meta plan whose status matches the index
        # reports as neither anomaly nor drift (previously it reported a
        # standing "Master Plan not found" anomaly on every run).
        self.write_index(
            "| PRV | Review (Meta / Discovery) | READY_TO_EXECUTE | 2026-07-01 | 2026-07-01 | Review/Meta-PRV/ |\n"
        )
        self.write_master_plan(
            "Review/Meta-PRV/", "PRV", "READY_TO_EXECUTE", "2026-07-01", meta=True, created="2026-07-01"
        )

        result = detect_drift(self.config)

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(result["drifts"], [])

    def test_meta_plan_status_drift_detected_after_resolve(self):
        # Once resolved via the -META- fallback, a Meta plan is drift-checked
        # like any other row: a genuine status divergence must register as
        # drift (the fallback resolves the file; it does not exclude Meta rows
        # from the comparison).
        self.write_index(
            "| PRV | Review (Meta / Discovery) | READY_TO_EXECUTE | 2026-07-01 | 2026-07-01 | Review/Meta-PRV/ |\n"
        )
        self.write_master_plan(
            "Review/Meta-PRV/", "PRV", "COMPLETE", "2026-07-01", meta=True, created="2026-07-01"
        )

        result = detect_drift(self.config)

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(len(result["drifts"]), 1)
        self.assertEqual(result["drifts"][0]["abbrev"], "PRV")
        self.assertEqual(result["drifts"][0]["mp_status"], "COMPLETE")

    def test_meta_marked_row_missing_both_still_anomaly(self):
        # A Meta-marked row with NO Master Plan under either convention must
        # still report as an anomaly (no silent pass), and the expected_path
        # must name the -META- convention so the message is actionable.
        self.write_index(
            "| ZZZ | ZetaPlan | READY_TO_EXECUTE | 2026-07-01 | 2026-07-01 | Zeta/Meta-ZZZ/ |\n"
        )
        # Intentionally write no Master Plan under either name.

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        anomaly = result["anomalies"][0]
        self.assertEqual(anomaly["class"], "orphan-row")
        self.assertEqual(anomaly["abbrev"], "ZZZ")
        self.assertIn("not found", anomaly["reason"].lower())
        self.assertIn("META-Master-Plan.md", anomaly["expected_path"])

    def test_non_meta_missing_does_not_probe_meta_name(self):
        # The Path-marker gate keeps the fallback OFF for regular (non-Meta)
        # rows: a row missing {ABBR}-Master-Plan.md must still anomaly even if a
        # -META- file happens to exist alongside it, rather than silently
        # resolving to the wrong convention.
        self.write_index(
            "| REG | RegPlan | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Reg/ |\n"
        )
        # Only a -META- file exists, but the Path is NOT Meta-marked.
        self.write_master_plan("Reg/", "REG", "IN_PROGRESS", "2026-01-01", meta=True)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["abbrev"], "REG")

    def test_reconcile_preserves_crlf_line_endings(self):
        # A destructive write must preserve the file's original line endings.
        # Build a CRLF index explicitly (independent of the host platform),
        # reconcile a drifted row, and assert the bytes stay CRLF with the
        # target cell still reconciled.
        index_path = self.plans_dir / "00-Index-Plans.md"
        crlf_content = self.index_text(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        ).replace("\n", "\r\n")
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            f.write(crlf_content)
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19", created="2026-03-19")

        written = reconcile(self.config)
        self.assertEqual(written, 1)

        raw = index_path.read_bytes()
        self.assertIn(b"\r\n", raw)
        # No bare LF introduced: every LF must be part of a CRLF pair.
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        rows = parse_plans_index(raw.decode("utf-8"))
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        self.assertEqual(prc["status"], "COMPLETE")


class TestEscapedPipeRows(_ReconcileFixtureBase):
    """A plan Name cell may contain an escaped pipe. The rows are read through
    the shared table parser, so an escaped pipe never shifts a column. The Name
    comes from the plan folder, so a rewrite replaces it with the folder name."""

    ESCAPED_NAME = r"Filter via `ls \| wc -l`"

    def test_reconcile_writes_the_columns_it_names(self):
        self.write_index(
            f"| PRC | {self.ESCAPED_NAME} | READY_TO_EXECUTE | 2026-03-19 "
            "| 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-04-02", created="2026-03-19")

        # The escaped pipe does not shift a column: the audit names the Name field.
        fields = {d["field"]: d for d in detect_drift(self.config)["drifts"]}
        self.assertEqual(sorted(fields), ["last_updated", "name", "status"])
        self.assertEqual(fields["name"]["disk"], "Filter via `ls | wc -l`")

        written = reconcile(self.config)

        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        self.assertEqual(prc["status"], "COMPLETE")
        self.assertEqual(prc["last_updated"], "2026-04-02")
        # Neighbouring columns untouched, and the Name is the plan folder's.
        self.assertEqual(prc["created"], "2026-03-19")
        self.assertEqual(prc["path"], "PluginRootConfig/")
        self.assertEqual(prc["name"], "PluginRootConfig")
        self.assertNotIn(r"\|", self.read_index_text())

    def test_escaped_row_is_parsed_not_dropped(self):
        self.write_index(
            f"| PRC | {self.ESCAPED_NAME} | IN_PROGRESS | 2026-03-19 "
            "| 2026-03-19 | PluginRootConfig/ |\n"
            "| FOO | Plain | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Foo/ |\n"
        )
        rows = parse_plans_index(self.read_index_text())

        self.assertEqual([r["abbrev"] for r in rows], ["PRC", "FOO"])
        self.assertEqual(rows[0]["name"], "Filter via `ls | wc -l`")
        self.assertEqual(rows[0]["status"], "IN_PROGRESS")


class TestZeroComparisonAndShape(_ReconcileFixtureBase):
    """The audit never prints an all-clear over a comparison it could not make."""

    ALL_CLEAR = "No drift detected. All index rows match their Master Plan status."

    def test_all_clear_prints_only_when_every_row_was_compared(self):
        # Non-producing control for the exit-3 and exit-2 tests below: one row
        # that resolves and matches, in the generated shape.
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")

        code, out, _ = self.run_cli()

        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [self.ALL_CLEAR, "1 of 1 rows compared."])

    def test_root_path_row_over_an_exec_plan_exits_3(self):
        # A root Path row whose Master Plan sits in an Exec- child folder: the
        # row's Path resolves to no file, and the tree's Master Plan is at the child.
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/Exec-Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")

        code, out, _ = self.run_cli()

        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[0], "Drift audit could not run: 0 of 1 rows compared")
        self.assertNotIn("No drift detected", out)
        self.assertEqual(detect_drift(self.config)["status"], "could-not-run")

    def test_root_path_row_beside_a_resolving_row(self):
        self.write_index(
            _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/")
            + _row("BET", "Beta", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Beta/")
        )
        self.write_master_plan("Alpha/Exec-Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_master_plan("Beta/", "BET", "IN_PROGRESS", "2026-01-01")

        result = detect_drift(self.config)

        self.assertEqual(result["status"], "ran")
        self.assertEqual((result["compared"], result["total"]), (1, 2))
        self.assertEqual([(a["class"], a["path"]) for a in result["anomalies"]], [("orphan-row", "Alpha/")])
        self.assertEqual([(d["class"], d["path"]) for d in result["drifts"]], [("missing-row", "Alpha/Exec-Alpha/")])
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("1 of 2 rows compared.", out)
        self.assertNotIn("No drift detected", out)

    def test_write_heals_a_root_path_row(self):
        # --write delegates to the generator, so the healed index audits clean.
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/Exec-Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")

        code, out, _ = self.run_cli("--write")

        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "Reconciled 2 row(s).")
        self.assertEqual([r["path"] for r in parse_plans_index(self.read_index_text())], ["Alpha/Exec-Alpha/"])
        code, out, _ = self.run_cli()
        self.assertEqual((code, out.splitlines()[0]), (0, self.ALL_CLEAR))

    def test_write_exits_1_when_the_render_raises_an_anomaly(self):
        # An unknown Status is written as stated, and the shim reports the anomaly with exit 1.
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/", "ALP", "DONE", "2026-01-01")

        code, out, _ = self.run_cli("--write")

        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "Reconciled 1 row(s).")
        rows = parse_plans_index(self.read_index_text())
        self.assertEqual([(r["abbrev"], r["status"]) for r in rows], [("ALP", "DONE")])

    def test_plans_prefixed_paths_exit_3_and_a_legacy_shape_exits_2(self):
        # A generated-shape index whose rows read `Plans/{Name}/` joins the
        # plans directory twice and resolves nothing. The same rows in a
        # hand-authored index are the legacy shape, which exits 2.
        rows = _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Plans/Alpha/") + _row(
            "BET", "Beta", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Plans/Beta/"
        )
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_master_plan("Beta/", "BET", "IN_PROGRESS", "2026-01-01")

        self.write_index(rows)
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[0], "Drift audit could not run: 0 of 2 rows compared")
        expected = [a["expected_path"] for a in detect_drift(self.config)["anomalies"] if a["class"] == "orphan-row"]
        self.assertEqual(expected, ["Plans/Plans/Alpha/ALP-Master-Plan.md", "Plans/Plans/Beta/BET-Master-Plan.md"])

        self.write_index(rows, generated=False)
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("/planwise upgrade", err)
        self.assertNotIn("No drift detected", out)

    def test_emoji_status_is_the_same_value(self):
        # A Master Plan Status line of `✅ **COMPLETE (2026-08-12) — closed**`
        # states COMPLETE. An index cell of `COMPLETE` matches it, and a cell
        # holding only the emoji does not.
        status = "✅ **COMPLETE (2026-08-12) — closed**"
        self.write_master_plan("Alpha/", "ALP", status, "2026-08-12")

        self.write_index(_row("ALP", "Alpha", "COMPLETE", "2026-01-01", "2026-08-12", "Alpha/"))
        result = detect_drift(self.config)
        self.assertEqual((result["drifts"], result["anomalies"]), ([], []))

        self.write_index(_row("ALP", "Alpha", "✅", "2026-01-01", "2026-08-12", "Alpha/"))
        result = detect_drift(self.config)
        self.assertEqual(result["anomalies"], [])
        self.assertEqual([(d["class"], d["field"]) for d in result["drifts"]], [("stale-row", "status")])
        self.assertEqual((result["drifts"][0]["index_status"], result["drifts"][0]["mp_status"]), ("✅", "COMPLETE"))

    def test_legacy_shape_exits_2_and_write_writes_nothing(self):
        self.write_index(
            _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"), generated=False
        )
        self.write_master_plan("Alpha/", "ALP", "COMPLETE", "2026-01-01")
        index_path = self.plans_dir / "00-Index-Plans.md"
        before = index_path.read_bytes()

        code, out, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("/planwise upgrade", err)
        self.assertNotIn("No drift detected", out)
        result = detect_drift(self.config)
        self.assertEqual((result["status"], result["drifts"]), ("legacy-shape", []))
        self.assertEqual([a["class"] for a in result["anomalies"]], ["legacy-shape"])

        code, out, err = self.run_cli("--write")
        self.assertEqual(code, 2)
        self.assertIn("/planwise upgrade", err)
        self.assertNotIn("Reconciled", out)
        self.assertEqual(index_path.read_bytes(), before)
        with self.assertRaises(LegacyIndexError):
            reconcile(self.config)
        self.assertEqual(index_path.read_bytes(), before)

    def _drifted_index_under_a_tiny_budget(self):
        """A drifted index, and the byte string it holds, with the generator budget patched below the render."""
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/", "ALP", "COMPLETE", "2026-01-01")
        budget = mock.patch.object(generate_plans_index, "HUB_TOKEN_BUDGET", 10)
        budget.start()
        self.addCleanup(budget.stop)
        return (self.plans_dir / "00-Index-Plans.md").read_bytes()

    def test_write_over_budget_prints_no_reconciled_line(self):
        before = self._drifted_index_under_a_tiny_budget()

        code, out, err = self.run_cli("--write")

        self.assertEqual(code, 2)
        self.assertNotIn("Reconciled", out)
        self.assertIn("10-token budget", err)
        self.assertEqual((self.plans_dir / "00-Index-Plans.md").read_bytes(), before)

    def test_reconcile_raises_when_the_generator_refuses(self):
        before = self._drifted_index_under_a_tiny_budget()

        with self.assertRaises(WriteRefusedError) as raised:
            reconcile(self.config)

        self.assertIn("10-token budget", str(raised.exception))
        self.assertEqual((self.plans_dir / "00-Index-Plans.md").read_bytes(), before)

    def test_partial_parse_exits_3_and_names_the_line(self):
        # One five-cell row among good rows: the audit compared fewer rows than
        # the index holds, so it cannot say the index is clean.
        rows = (
            _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/")
            + "| BAD | Bad | IN_PROGRESS | 2026-01-01 | Bad/ |\n"
            + _row("BET", "Beta", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Beta/")
        )
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_master_plan("Beta/", "BET", "IN_PROGRESS", "2026-01-01")
        self.write_index(rows)
        bad_line = next(n for n, line in enumerate(self.read_index_text().split("\n"), 1) if line.startswith("| BAD"))

        code, out, _ = self.run_cli()

        self.assertEqual(code, 3)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Drift audit incomplete: 2 of 3 rows compared")
        self.assertIn(f"line {bad_line}", lines[1])
        self.assertNotIn("No drift detected", out)
        result = detect_drift(self.config)
        self.assertEqual(result["status"], "incomplete")
        unparsed = next(a for a in result["anomalies"] if a["class"] == "unparsed-rows")
        self.assertEqual(unparsed["lines"], [{"line": bad_line, "reason": "cell-count 5"}])
        self.assertIn(f"line {bad_line}", unparsed["reason"])

    def test_comments_between_rows_are_read_past(self):
        rows = (
            _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/")
            + "<!-- a note between two rows -->\n"
            + _row("BET", "Beta", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Beta/")
        )
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_master_plan("Beta/", "BET", "IN_PROGRESS", "2026-01-01")
        self.write_index(rows)

        code, out, _ = self.run_cli()

        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [self.ALL_CLEAR, "2 of 2 rows compared."])
        result = detect_drift(self.config)
        self.assertEqual((result["compared"], result["total"]), (2, 2))

    def test_rows_after_a_heading_between_rows_are_not_compared_silently(self):
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_master_plan("Beta/", "BET", "IN_PROGRESS", "2026-01-01")
        self.write_index(
            _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/")
            + "\n## Notes\n\n"
            + _row("BET", "Beta", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Beta/")
        )
        bet_line = next(n for n, line in enumerate(self.read_index_text().split("\n"), 1) if line.startswith("| BET"))

        code, out, _ = self.run_cli()

        self.assertEqual(code, 3)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Drift audit incomplete: 1 of 2 rows compared")
        self.assertIn(f"line {bet_line}", lines[1])
        self.assertNotIn("No drift detected", out)

    def test_a_row_after_the_legend_blocks_the_all_clear(self):
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        index_path = self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        index_path.write_text(
            index_path.read_text(encoding="utf-8") + _row("ZZZ", "Zed", "COMPLETE", "2026-01-09", "2026-01-09", "Zed/"),
            encoding="utf-8",
        )
        zed_line = next(n for n, line in enumerate(self.read_index_text().split("\n"), 1) if line.startswith("| ZZZ"))

        code, out, _ = self.run_cli()

        self.assertEqual(code, 3)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Drift audit incomplete: 1 of 2 rows compared")
        self.assertIn(f"line {zed_line}", lines[1])
        self.assertNotIn("No drift detected", out)

    def test_a_renamed_header_over_an_empty_tree_blocks_the_all_clear(self):
        index_path = self.write_index(_row("ZZZ", "Zed", "COMPLETE", "2026-01-09", "2026-01-09", "Zed/"))
        text = index_path.read_text(encoding="utf-8")
        self.assertIn("| Abbrev |", text)
        index_path.write_text(text.replace("| Abbrev |", "| Abbr |", 1), encoding="utf-8")

        code, out, _ = self.run_cli()

        self.assertEqual(code, 3)
        self.assertNotIn("No drift detected", out)
        self.assertNotIn("0 of 0", out)
        result = detect_drift(self.config)
        self.assertGreaterEqual(result["total"], 1)
        self.assertEqual(result["compared"], 0)

    def test_duplicate_row_is_an_anomaly_not_an_incomplete_audit(self):
        rows = _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/") * 2
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        self.write_index(rows)
        first = next(n for n, line in enumerate(self.read_index_text().split("\n"), 1) if line.startswith("| ALP"))

        code, out, _ = self.run_cli()

        self.assertEqual(code, 0)
        self.assertIn("Anomalies (1):", out)
        self.assertNotIn("No drift detected", out)
        anomaly = detect_drift(self.config)["anomalies"][0]
        self.assertEqual((anomaly["class"], anomaly["lines"]), ("duplicate-row", [first, first + 1]))

    def test_missing_index(self):
        self.write_master_plan("Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[0], "Drift audit could not run: 0 of 1 rows compared")
        self.assertIn("The index is missing", out)

        shutil.rmtree(self.plans_dir / "Alpha")
        code, out, err = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), f"Error: Plans index not found at {self.plans_dir / '00-Index-Plans.md'}")
        self.assertEqual(out, "")

    def test_json_keeps_the_old_keys_and_adds_the_counts(self):
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/", "ALP", "COMPLETE", "2026-01-01")

        code, out, _ = self.run_cli("--json")

        self.assertEqual(code, 0)
        json_path = Path(out.splitlines()[-1].removeprefix("JSON: "))
        self.addCleanup(shutil.rmtree, json_path.parent, ignore_errors=True)
        self.assertTrue(json_path.parent.name.startswith("reconcile-plans-"))
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(list(payload)[:2], ["drifts", "anomalies"])
        self.assertEqual((payload["compared"], payload["total"], payload["status"]), (1, 1, "ran"))
        self.assertEqual(payload["drifts"][0]["index_status"], "IN_PROGRESS")

    def test_exit_code_reaches_the_process(self):
        # main() returns the code and the script entry point passes it to sys.exit.
        self.write_index(_row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/"))
        self.write_master_plan("Alpha/Exec-Alpha/", "ALP", "IN_PROGRESS", "2026-01-01")

        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / "reconcile_plans.py"), "--config", str(self.planwise_dir / "config.yaml")],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout.splitlines()[0], "Drift audit could not run: 0 of 1 rows compared")


class TestDelegatedPublicNames(_ReconcileFixtureBase):
    """The kept public names delegate to `parse_plans` and keep their return shapes."""

    def test_parse_plans_index_keeps_the_zero_based_line_number(self):
        self.write_index(
            "<!-- a comment before the rows -->\n"
            + _row("ALP", "Alpha", "IN_PROGRESS", "2026-01-01", "2026-01-01", "Alpha/")
            + "<!-- a comment between the rows -->\n"
            + _row("BET", "Beta", "COMPLETE", "2026-01-02", "2026-01-03", "Beta/")
        )
        text = self.read_index_text()

        rows = parse_plans_index(text)

        self.assertEqual([r["abbrev"] for r in rows], ["ALP", "BET"])
        for row in rows:
            self.assertTrue(text.split("\n")[row["line_number"]].startswith(f"| {row['abbrev']} |"))
        self.assertEqual(
            sorted(rows[1]), ["abbrev", "created", "last_updated", "line_number", "name", "path", "status"]
        )

    def test_base_token(self):
        self.assertEqual(base_token("IN_PROGRESS -- awaiting user transfer"), "IN_PROGRESS")
        self.assertEqual(base_token("**COMPLETE** (2026-01-01) -- shipped"), "COMPLETE")
        self.assertEqual(base_token("✅ **COMPLETE (2026-08-12) — closed**"), "COMPLETE")
        self.assertEqual(base_token("✅"), "")
        self.assertEqual(base_token(""), "")

    def test_resolve_master_plan_path(self):
        row = {"abbrev": "PRV", "path": "Review/Meta-PRV/"}
        self.assertEqual(resolve_master_plan_path(self.config, row).name, "PRV-META-Master-Plan.md")
        self.write_master_plan("Review/Meta-PRV/", "PRV", "COMPLETE", "2026-01-01")
        self.assertEqual(resolve_master_plan_path(self.config, row).name, "PRV-Master-Plan.md")
        plain = {"abbrev": "ALP", "path": "Alpha/"}
        self.assertEqual(resolve_master_plan_path(self.config, plain), self.plans_dir / "Alpha" / "ALP-Master-Plan.md")


if __name__ == "__main__":
    unittest.main()
