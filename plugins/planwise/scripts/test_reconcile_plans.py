#!/usr/bin/env python3
"""Unit tests for plans-index drift detection and reconciliation.

`reconcile_plans.detect_drift(config)` compares each Plans-index row's Status
column against its own Master Plan's `**Status:**` field (normalized to a
"base token" so a gated-completion note suffix does not register as false
drift), reporting out-of-sync rows as drift and rows whose Master Plan cannot
be resolved as anomalies. `reconcile_plans.reconcile(config)` re-reads the
index fresh and writes only rows still drifted, mirroring the Master Plan's
own Status and Last Updated footer date (falling back to today when no footer
date is parseable), and never touches anomaly rows.

These tests pin: the terminal-status-stale reproduction case (an index row
still showing an execution status after its Master Plan has completed), the
date-mirroring behavior on write, a gated-completion-suffix row correctly
registering as non-drift, a missing Master Plan correctly registering as an
anomaly (not drift, and never written by reconcile), a non-enum status
divergence detecting drift without raising, race-safety (reconcile re-reads
and will not clobber a row already healed on disk since detect ran), and the
today's-date fallback when a Master Plan has no parseable Last Updated
footer.

Each test builds an isolated temp planwise tree (config.yaml + Plans index +
Master Plan files) under a unittest tempfile fixture; none read or mutate the
live project's Plans index.

Run with:  python -m pytest scripts/test_reconcile_plans.py -q
"""

import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

# Allow imports whether pytest is launched from the repo root
# (python -m pytest scripts/test_...) or from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader  # noqa: E402
from reconcile_plans import detect_drift, parse_plans_index, reconcile  # noqa: E402


# A minimal config.yaml the fixture tree can resolve via
# config_loader.load_config's explicit --config path.
CONFIG_YAML_FIXTURE = """project:
  name: "ReconcileFixtureProject"
  plans_dir: "Plans"
  index_files:
    plans: "00-Index-Plans.md"
"""


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

    def write_index(self, rows_markdown: str) -> Path:
        """Write the Plans index file body (fixed header/separator + rows)."""
        content = (
            "# Plans Index\n\n"
            "| Abbrev | Name | Status | Created | Last Updated | Path |\n"
            "|--------|------|--------|---------|--------------|------|\n"
            + rows_markdown
        )
        path = self.plans_dir / "00-Index-Plans.md"
        path.write_text(content, encoding="utf-8")
        return path

    def write_master_plan(
        self, rel_path: str, abbrev: str, status: str, last_updated: str | None = None
    ) -> Path:
        """Write a Master Plan at Plans/{rel_path}/{abbrev}-Master-Plan.md."""
        mp_dir = self.plans_dir / rel_path
        mp_dir.mkdir(parents=True, exist_ok=True)
        mp_path = mp_dir / f"{abbrev}-Master-Plan.md"
        body = f"# {abbrev} Master Plan\n\n**Status:** {status}\n"
        if last_updated:
            body += f"\n*Last Updated: {last_updated}*\n"
        mp_path.write_text(body, encoding="utf-8")
        return mp_path

    def read_index_text(self) -> str:
        return (self.plans_dir / "00-Index-Plans.md").read_text(encoding="utf-8")


class TestReconcilePlans(_ReconcileFixtureBase):
    """Full detect_drift / reconcile test matrix."""

    def test_detect_finds_stale_terminal_row(self):
        # Reproduction: an index row still shows an execution status after
        # its Master Plan has actually completed.
        self.write_index(
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\n"
        )
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19")

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
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19")

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
            "| FOO | FooPlan | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Foo/ |\n"
        )
        self.write_master_plan(
            "Foo/", "FOO", "IN_PROGRESS -- awaiting user transfer", "2026-01-01"
        )

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])

    def test_missing_master_plan_is_anomaly(self):
        # A row whose Path does not resolve to an existing Master Plan file
        # must be reported as an anomaly, not drift, and reconcile must not
        # write it.
        self.write_index(
            "| BAR | BarPlan | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Bar/ |\n"
        )
        # Intentionally do not write a Master Plan for BAR.

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        anomaly = result["anomalies"][0]
        self.assertEqual(anomaly["abbrev"], "BAR")
        self.assertIn("not found", anomaly["reason"].lower())

        before = self.read_index_text()
        written = reconcile(self.config)
        self.assertEqual(written, 0)
        self.assertEqual(self.read_index_text(), before)

    def test_nonstandard_token_divergence(self):
        # A verbatim status divergence outside any documented enum must
        # still register as drift without raising.
        self.write_index(
            "| BAZ | BazPlan | REVIEWED | 2026-01-01 | 2026-01-01 | Baz/ |\n"
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
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19")

        pre = detect_drift(self.config)
        self.assertEqual(len(pre["drifts"]), 1)

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
        # footer must fall back to today's date, not raise or leave it
        # blank.
        self.write_index(
            "| QUX | QuxPlan | IN_PROGRESS | 2026-01-01 | 2026-01-01 | Qux/ |\n"
        )
        self.write_master_plan("Qux/", "QUX", "COMPLETE", last_updated=None)

        written = reconcile(self.config)

        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        qux = next(r for r in rows if r["abbrev"] == "QUX")
        self.assertEqual(qux["status"], "COMPLETE")
        self.assertEqual(qux["last_updated"], date.today().isoformat())

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
            "PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19 (plan COMPLETE)"
        )

        written = reconcile(self.config)
        self.assertEqual(written, 1)
        rows = parse_plans_index(self.read_index_text())
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        # Mirrors the date embedded in the annotated footer, not today.
        self.assertEqual(prc["last_updated"], "2026-03-19")

    def test_reconcile_preserves_crlf_line_endings(self):
        # A destructive write must preserve the file's original line endings.
        # Build a CRLF index explicitly (independent of the host platform),
        # reconcile a drifted row, and assert the bytes stay CRLF with the
        # target cell still reconciled.
        index_path = self.plans_dir / "00-Index-Plans.md"
        crlf_content = (
            "# Plans Index\r\n\r\n"
            "| Abbrev | Name | Status | Created | Last Updated | Path |\r\n"
            "|--------|------|--------|---------|--------------|------|\r\n"
            "| PRC | PluginRootConfig | READY_TO_EXECUTE | 2026-03-19 | 2026-03-19 | PluginRootConfig/ |\r\n"
        )
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            f.write(crlf_content)
        self.write_master_plan("PluginRootConfig/", "PRC", "COMPLETE", "2026-03-19")

        written = reconcile(self.config)
        self.assertEqual(written, 1)

        raw = index_path.read_bytes()
        self.assertIn(b"\r\n", raw)
        # No bare LF introduced: every LF must be part of a CRLF pair.
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        rows = parse_plans_index(raw.decode("utf-8"))
        prc = next(r for r in rows if r["abbrev"] == "PRC")
        self.assertEqual(prc["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
