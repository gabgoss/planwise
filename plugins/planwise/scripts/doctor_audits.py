#!/usr/bin/env python3
"""Doctor's scripted index audits: plans drift, backlog archival drift,
backlog item body-status drift and lessons index drift.

`run_index_audits(cfg)` loads the project's config.yaml once, then runs each
audit in process by calling the reconcile scripts' read-only detect functions.
Each stage prints the banner and the verdict lines the doctor handler and the
index-drift-audit reference specify. A reconcile script's stderr texts (the
exit-1 and exit-2 messages) are routed onto stdout under the banner, and the
consent prompt prints as a `recommend:` line. Nothing here asks a question or
writes a file.

Every stage is fail-safe: an exception inside a stage prints one
`<stage>: the check failed: <reason>` line and the next stage still runs, so
the audits never change doctor's exit status. Findings are sorted, and neither
a timestamp nor the CLI's temp-file `JSON:` line is printed, so two runs over
one tree print the same bytes.
"""

import contextlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader

_PLANS_BANNER = "planwise doctor — plans index drift audit"
_BACKLOG_BANNER = "planwise doctor — backlog index archival drift audit"
_BODY_STATUS_BANNER = "planwise doctor — backlog item body-status drift audit"
_LESSONS_BANNER = "planwise doctor — lessons index drift audit"


def _resolve_config_path(cfg) -> "Path | None":
    """Locate config.yaml the way doctor's Config Gate does: the default
    planwise root first, then any `*/config.yaml` one level down from the
    project root. Returns None when no config is found. Read-only."""
    primary = cfg.project_root / cfg.planwise_root / "config.yaml"
    if primary.exists():
        return primary
    for candidate in sorted(cfg.project_root.glob("*/config.yaml")):
        return candidate
    return None


def _sort_key(record: dict) -> tuple:
    """Order by row identifier, then file or path, then the whole record."""
    ident = str(record.get("id") or record.get("abbrev") or "")
    place = str(record.get("file") or record.get("path") or "")
    return ident, place, json.dumps(record, sort_keys=True, default=str)


def _sorted_result(result: dict) -> dict:
    """A copy of a detect result whose two finding lists are in a stable order."""
    ordered = dict(result)
    ordered["drifts"] = sorted(result["drifts"], key=_sort_key)
    ordered["anomalies"] = sorted(result["anomalies"], key=_sort_key)
    return ordered


def _require_dir(path: Path, label: str) -> None:
    if not Path(path).is_dir():
        raise FileNotFoundError(f"the {label} directory does not exist")


def _backlog_index_present(config: dict) -> bool:
    """True when the backlog index exists. When it is missing, print the CLI's
    exit-1 line and return False, so the stage prints no all-clear."""
    index_path = config["_index_path"]
    if Path(index_path).exists():
        return True
    print(f"Error: Backlog index not found at {index_path}")
    return False


def _stage_11(config: dict) -> None:
    """Plans index drift: `reconcile_plans.detect_drift` and its report."""
    import reconcile_plans as rp

    _require_dir(config["_plans_dir"], "plans")
    index_path = rp.plans_index_path(config)
    result = _sorted_result(rp.detect_drift(config))
    # The script reports exit-1 and exit-2 texts on stderr. Route them here.
    with contextlib.redirect_stderr(sys.stdout):
        rp._report_detect(result, index_path, False)
    rows = len({d["path"] for d in result["drifts"]})
    orphans = sum(1 for a in result["anomalies"] if a["class"] == "orphan-row")
    missing = any(d["class"] == "missing-row" for d in result["drifts"])
    if result["status"] == "ran" and result["drifts"]:
        print(
            f"recommend: Regenerate the plans index from its Master Plans to resolve {rows} "
            f"drifted row(s)? `--write` regenerates the whole index and drops {orphans} orphan row(s)."
        )
    elif result["status"] == "could-not-run" and missing:
        print(
            "recommend: Regenerate the plans index with `reconcile_plans.py --write`. "
            "It regenerates the whole file and drops every line the render does not produce: "
            "unparsed lines, prose and comments in the table region, and duplicate rows."
        )


def _stage_12(config: dict) -> None:
    """Backlog archival drift: `reconcile_backlog.detect_drift` and its report."""
    import reconcile_backlog as rb

    _require_dir(config["_backlog_dir"], "backlog")
    if not _backlog_index_present(config):
        return
    result = _sorted_result(rb.detect_drift(config))
    print(rb._format_report(result))
    count = len(result["drifts"])
    if count:
        print(f"recommend: Archive {count} closed item file(s) — move them into `Archive/`?")


def _stage_19(config: dict) -> None:
    """Backlog body-status drift: `reconcile_backlog.detect_body_status` and its report."""
    import reconcile_backlog as rb

    _require_dir(config["_backlog_dir"], "backlog")
    if not _backlog_index_present(config):
        return
    result = _sorted_result(rb.detect_body_status(config))
    print(rb._format_body_status_report(result))
    drifts = result["drifts"]
    if drifts:
        disagree = sum(1 for d in drifts if d["kind"] == "disagrees")
        print(
            f"recommend: Strip {len(drifts)} body status line(s) from backlog item files "
            f"({disagree} disagree with frontmatter, {len(drifts) - disagree} redundant)? "
            "Frontmatter is not changed."
        )


def _stage_13(config: dict) -> None:
    """Lessons index drift: `lessons_index_run.check_lessons_index` and its report."""
    if config["_lessons_dir"] is None:
        print("Lessons index: not configured — audit skipped")
        return
    _require_dir(config["_lessons_dir"], "lessons")
    import lessons_index_run as lr
    from lessons_index_drift import _format_lessons_check_report

    result = lr.check_lessons_index(config)
    findings = sorted(result["findings"], key=_sort_key)
    if result["code"] == lr.LessonsDisposition.REFUSED:
        print(lr.legacy_hub_message(config["_lessons_index"]))
        # The same findings make a later `--write` refuse, so they print with the upgrade line.
        blocking = [f for f in findings if f["class"] in lr._WRITE_REFUSAL_CLASSES]
        if blocking:
            print(_format_lessons_check_report(blocking))
        return
    print(_format_lessons_check_report(findings))


def _load_project_config(cfg):
    """Return `(config, None)`, or `(None, reason)` when config.yaml cannot be loaded."""
    try:
        config_path = _resolve_config_path(cfg)
        if config_path is None:
            return None, "no config.yaml found"
        return config_loader.load_config(Path(__file__), config_path=config_path), None
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- the audits never change doctor's exit status
        return None, str(exc) or exc.__class__.__name__


def run_index_audits(cfg) -> None:
    """Run the four index audits in order. Read-only, and never raises."""
    config, reason = _load_project_config(cfg)
    stages = (
        ("Plans index drift audit", _PLANS_BANNER, _stage_11),
        ("Backlog archival drift audit", _BACKLOG_BANNER, _stage_12),
        ("Backlog body-status drift audit", _BODY_STATUS_BANNER, _stage_19),
        ("Lessons index drift audit", _LESSONS_BANNER, _stage_13),
    )
    for name, banner, stage in stages:
        print()
        print(banner)
        print()
        try:
            if config is None:
                raise RuntimeError(f"config.yaml could not be loaded ({reason})")
            stage(config)
        except Exception as exc:  # noqa: BLE001 -- a stage must never change doctor's exit status
            print(f"{name}: the check failed: {exc}")
