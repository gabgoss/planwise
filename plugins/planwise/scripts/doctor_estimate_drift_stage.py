#!/usr/bin/env python3
"""Doctor's Estimate Drift stage — read-only, advisory.

`run_estimate_drift_stage(cfg)` runs the `estimate_reconcile` check in process over
each active plan and prints what it finds under the plan's name: each MISMATCH line
verbatim, then the check's own summary line verbatim. The unread figures print as
the count on that summary line only. A plan with no mismatch and no unread figure
prints one "no drift" line. A plan whose check raises prints one line with the
error, and the other plans still report. Paths resolve against the project root that
the config names, as they do in the write-back.

An active plan is resolved as the read-gate stage resolves it: each plan whose
plans-index status is `IN_PROGRESS`. The stage compares figures and passes no
judgement on the size of a session. It asks no question, writes no file and offers
no fix. The caller wraps the stage, so an exception never changes doctor's exit
status.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from doctor_audits import _load_project_config
from doctor_read_gate_stage import _active_plan_dirs
from estimate_reconcile import error_text, reconcile
from token_saver_scan import config_project_root


def run_estimate_drift_stage(cfg) -> None:
    """Print the estimate drift of each active plan. Read-only."""
    config, load_error = _load_project_config(cfg)
    if config is not None:
        plans_dir = Path(config["_plans_dir"])
        if not plans_dir.is_dir():
            print(f"No plans folder at {plans_dir.name}/; no estimate to check.")
            return
    plans, reason = _active_plan_dirs(config)
    if not plans:
        print(f"Active plan: none ({load_error or reason}); no estimate to check.")
        return
    project_root = cfg.project_root if config is None else config_project_root(config)
    for abbrev, plan_dir in plans:
        try:
            report = reconcile(plan_dir, project_root)
        except Exception as exc:  # noqa: BLE001 -- one plan's failure never hides a later plan
            print(f"  {abbrev}: not checked ({error_text(exc)})")
            continue
        if not report.mismatches and not report.unread:
            print(f"  {abbrev}: no drift ({report.sessions} session(s) checked)")
            continue
        print(f"  {abbrev}:")
        for line in (*report.mismatches, report.summary):
            print(f"      {line}")
