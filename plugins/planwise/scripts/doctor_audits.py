#!/usr/bin/env python3
"""Doctor's scripted index audits: plans drift, backlog archival drift,
backlog item body-status drift, lessons index drift and the backlog, lessons
and plans index shape audits.

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
_BACKLOG_SHAPE_BANNER = "planwise doctor — backlog index shape audit"
_LESSONS_SHAPE_BANNER = "planwise doctor — lessons index shape audit"
_PLANS_SHAPE_BANNER = "planwise doctor — plans index shape audit"


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


def _field(report: dict, dotted: str):
    """The value at a dotted key of a report, or None when any step is missing."""
    value = report
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _render_item(item) -> str:
    """One list member as text. A dict prints as sorted `key=value` pairs, and
    a `file` or `path` value prints as its file name, so no path reaches the output."""
    if not isinstance(item, dict):
        return str(item)
    return " ".join(
        f"{k}={Path(str(item[k])).name if k in ('file', 'path') else item[k]}" for k in sorted(item)
    )


def _print_fields(report: dict, keys) -> None:
    """One `key: value` line per key. Lists print sorted, and the index prints
    as its file name, so no temp path reaches the output."""
    for key in keys:
        value = _field(report, key)
        if key == "index" and value:
            value = Path(str(value)).name
        if isinstance(value, list):
            value = ", ".join(sorted(_render_item(v) for v in value)) or "none"
        elif isinstance(value, dict):
            value = ", ".join(f"{k}={value[k]}" for k in sorted(value))
        print(f"{key}: {value}")


def _report_failed(report: dict) -> bool:
    """True when the report carries an `error`. Prints the failure line and no shape verdict."""
    if "error" not in report:
        return False
    print(f"shape: {report.get('shape', 'unknown')}")
    print(f"the shape report failed: {report['error']}")
    return True


def _print_changelog_budget(report: dict) -> None:
    """Each changelog file at WARN or OVER, then the over-budget line."""
    files = [f for f in report.get("changelog_files", []) if f.get("level") in ("WARN", "OVER")]
    for entry in sorted(files, key=lambda f: Path(str(f.get("path", ""))).name):
        print(f"changelog file {Path(str(entry.get('path', ''))).name}: "
              f"{entry['level']} ({entry.get('tokens')} tokens)")
    if report.get("changelog_over_budget"):
        print("changelog file(s) over the read budget — `/planwise upgrade` re-splits them with backups, "
              "or run `migrate_backlog_index.py --config <planwise_root>/config.yaml --split-changelog`")


_LEGACY_VERDICT = "run `/planwise upgrade` to migrate automatically; backups land under `upgrade-backups/`"

_BACKLOG_FIELDS = (
    "shape", "changelog", "items.without_frontmatter", "items.partial_frontmatter",
    "dependencies.edges_missing_from_blocks", "dependencies.soft_dependency_bullets",
    "row_mismatches", "ready_with_all_repairs", "would_refuse",
)
_LESSONS_FIELDS = (
    "shape", "changelog", "changelog_resplit", "changelog_renumber", "changelog_oversized",
    "promotion_log", "companion", "lessons.without_frontmatter", "lessons.partial_frontmatter",
    "lessons.titles_needing_quotes", "lessons.status_mismatches", "cells.units", "prose_sections",
    "ready_with_all_repairs", "would_refuse",
)
_PLANS_FIELDS = (
    "shape", "detail", "index", "rows", "comments", "narrative_cells", "attributable", "unattributed",
    "uncarried_lines", "root_path_rows", "prefixed_rows", "status_changes", "append_targets", "ready",
    "would_refuse",
)


def _stage_20(config: dict) -> None:
    """Backlog index shape: `migrate_backlog_index.build_report`, wrapped so a corrupt index reports."""
    import migrate_backlog_index as mb

    _require_dir(config["_backlog_dir"], "backlog")
    if not _backlog_index_present(config):
        return
    try:
        report = mb.build_report(config, config["_index_path"])
    except Exception as exc:  # noqa: BLE001 -- a corrupt index becomes an unknown shape, not a crash
        report = {"shape": "unknown", "error": str(exc) or exc.__class__.__name__}
    if _report_failed(report):
        return
    _print_fields(report, _BACKLOG_FIELDS)
    _print_changelog_budget(report)
    shape = report.get("shape")
    if shape == "generated":
        if not report.get("changelog_over_budget"):
            print("generated shape, nothing to do")
    elif shape == "legacy":
        print(_LEGACY_VERDICT)
    elif shape == "unrecognized":
        print(report.get("detail", ""))
        print("left untouched; see the migrator's `--report` output")
    else:
        print(f"the shape {shape!r} is not one the audit knows")


def _stage_21(config: dict) -> None:
    """Lessons index shape: `migrate_lessons_index._safe_report`."""
    if config["_lessons_index"] is None:
        print("Lessons index: not configured — audit skipped")
        return
    _require_dir(config["_lessons_dir"], "lessons")
    index_path = config["_lessons_index"]
    if not Path(index_path).exists():
        print(f"Error: Lessons index not found at {index_path}")
        return
    import migrate_lessons_index as ml

    report = ml._safe_report(config, index_path)
    if _report_failed(report):
        return
    resplit = report.get("changelog_resplit")
    oversized = sorted(report.get("changelog_oversized") or [],
                       key=lambda o: (Path(str(o.get("file"))).name, str(o.get("entry"))))
    shape = report.get("shape")
    lists_oversized = shape == "generated" and resplit in ("within_budget", "converged")
    # The oversized-entry lines below carry the same data, so the field prints once.
    _print_fields(report, [k for k in _LESSONS_FIELDS if not (k == "changelog_oversized" and oversized and lists_oversized)])
    if shape == "generated":
        if lists_oversized:
            print("generated shape, nothing to do")
            for o in oversized:
                print(f"oversized entry: {Path(str(o.get('file'))).name} entry {o.get('entry')}: "
                      f"{o.get('tokens')} tokens, budget {o.get('budget')}")
        elif resplit == "would_split" and report.get("changelog_renumber"):
            print("the next `/planwise upgrade` renumbers the changelog entries by position "
                  "(the oldest becomes Entry 1); backups land under `upgrade-backups/`")
        elif resplit == "would_split":
            print("the next `/planwise upgrade` re-splits the changelog; backups land under `upgrade-backups/`")
        elif resplit == "refused":
            for reason in sorted(report.get("would_refuse") or []):
                print(reason)
            print("`/planwise upgrade` will refuse until that changelog line is fixed")
        else:
            print(f"the changelog_resplit value {resplit!r} is not one the audit knows")
    elif shape == "legacy":
        print(_LEGACY_VERDICT)
    elif shape == "unrecognized":
        print(report.get("detail", ""))
        print("left untouched")
    else:
        print(f"the shape {shape!r} is not one the audit knows")


def _stage_22(config: dict) -> None:
    """Plans index shape: `migrate_plans_index._safe_report`."""
    import generate_plans_index as gpi
    import migrate_plans_index as mp

    _require_dir(config["_plans_dir"], "plans")
    index_path = gpi.plans_index_path(config)
    if not Path(index_path).exists():
        print(f"Error: Plans index not found at {index_path}")
        return
    report = mp._safe_report(config, index_path)
    if _report_failed(report):
        return
    _print_fields(report, _PLANS_FIELDS)
    shape = report.get("shape")
    if shape == "generated":
        print("generated shape, nothing to do")
    elif shape == "legacy":
        print(_LEGACY_VERDICT)
    elif shape == "unrecognized":
        print("left untouched")
    elif shape == "absent":
        print("no plans index found")
    else:
        print(f"the shape {shape!r} is not one the audit knows")


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
    """Run the seven index audits in order. Read-only, and never raises."""
    config, reason = _load_project_config(cfg)
    stages = (
        ("Plans index drift audit", _PLANS_BANNER, _stage_11),
        ("Backlog archival drift audit", _BACKLOG_BANNER, _stage_12),
        ("Backlog body-status drift audit", _BODY_STATUS_BANNER, _stage_19),
        ("Lessons index drift audit", _LESSONS_BANNER, _stage_13),
        ("Backlog index shape audit", _BACKLOG_SHAPE_BANNER, _stage_20),
        ("Lessons index shape audit", _LESSONS_SHAPE_BANNER, _stage_21),
        ("Plans index shape audit", _PLANS_SHAPE_BANNER, _stage_22),
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
