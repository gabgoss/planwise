#!/usr/bin/env python3
"""Guard tests for the plans drift audit that no input on disk can reach today.

`reconcile_plans._report_detect` refuses to print the all-clear when the run
compared fewer rows than it counted, even when the status is `ran` and there
is nothing to report. The status ladder in `detect_drift` makes that case
unreachable from a real tree: every uncompared row is an orphan, a duplicate
or an unparsed line, and each of those raises an anomaly. The printer's clause
is the last line of defence if the count ever regresses, so this file
simulates the regression by under-counting `compared` and asserts that no
all-clear prints.

Run with:  python -m pytest tests/test_plans_index_guards.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_plans_index
import reconcile_plans

ALL_CLEAR = "No drift detected. All index rows match their Master Plan status."


def _write_master_plan(plans_dir: Path, folder: str, abbrev: str) -> None:
    directory = plans_dir / folder
    directory.mkdir(parents=True)
    (directory / f"{abbrev}-Master-Plan.md").write_text(
        f"# {abbrev} Master Plan\n\n**Status:** IN_PROGRESS\n**Created:** 2026-01-01\n\n*Last Updated: 2026-01-02*\n",
        encoding="utf-8",
    )


@pytest.fixture
def generated_tree(tmp_path):
    """Two Master Plans and the index the generator writes for them. Returns the config path."""
    planwise = tmp_path / "planwise"
    plans_dir = planwise / "Plans"
    plans_dir.mkdir(parents=True)
    config_path = planwise / "config.yaml"
    config_path.write_text(
        'project:\n  name: "GuardFixture"\n  plans_dir: "Plans"\n  index_files:\n    plans: "00-Index-Plans.md"\n',
        encoding="utf-8",
    )
    _write_master_plan(plans_dir, "Alpha", "ALP")
    _write_master_plan(plans_dir, "Beta", "BET")
    result = generate_plans_index.write_plans_index(config_loader.load_config(config_path=config_path))
    assert (result.exit_code, result.written) == (0, True)
    return config_path


def _run_audit(config_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["reconcile_plans", "--config", str(config_path)])
    code = reconcile_plans.main()
    return code, capsys.readouterr().out


def test_the_generated_tree_audits_clean(generated_tree, monkeypatch, capsys):
    # Non-producing control: every row compared, so the all-clear prints.
    code, out = _run_audit(generated_tree, monkeypatch, capsys)

    assert code == 0
    assert out.splitlines() == [ALL_CLEAR, "2 of 2 rows compared."]


def test_an_under_counted_comparison_with_nothing_to_report_prints_no_all_clear(generated_tree, monkeypatch, capsys):
    # Producing: the row diff finds nothing but reports one comparison fewer
    # than the rows it saw, so a row went uncompared with no finding naming it.
    real_diff = reconcile_plans.diff_index_rows

    def under_counted(disk_rows, rendered_rows, disk_lines=None):
        findings = real_diff(disk_rows, rendered_rows, disk_lines)
        findings.compared -= 1
        return findings

    monkeypatch.setattr(reconcile_plans, "diff_index_rows", under_counted)

    code, out = _run_audit(generated_tree, monkeypatch, capsys)

    assert code == 3
    assert out.splitlines()[0] == "Drift audit incomplete: 1 of 2 rows compared"
    assert "No drift detected" not in out
