#!/usr/bin/env python3
"""Tests for `doctor_audits.py`: doctor's scripted plans and backlog index audits.

Every fixture is a throwaway project under `tmp_path`. Nothing here reads or
writes the live project. Each stage has an all-clear case and a drift case,
and the fail-safe paths (a missing directory, a config with no `project:`
block, no config at all) are asserted to print a line and return.

Run with:  python -m pytest tests/test_doctor_audits.py -q
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import config_loader
import doctor_audits as da
import generate_lessons_index as gli
import generate_plans_index as gen
import lessons_index_run as lr

CONFIG = "project:\n  name: Fixture\n  plans_dir: Plans\n  backlog_dir: Backlog\nplugin_version: 1.0.0\n"

PLANS_BANNER = "planwise doctor — plans index drift audit"
BACKLOG_BANNER = "planwise doctor — backlog index archival drift audit"
BODY_BANNER = "planwise doctor — backlog item body-status drift audit"
LESSONS_BANNER = "planwise doctor — lessons index drift audit"
BACKLOG_SHAPE_BANNER = "planwise doctor — backlog index shape audit"
LESSONS_SHAPE_BANNER = "planwise doctor — lessons index shape audit"
PLANS_SHAPE_BANNER = "planwise doctor — plans index shape audit"
BANNERS = (
    PLANS_BANNER, BACKLOG_BANNER, BODY_BANNER, LESSONS_BANNER,
    BACKLOG_SHAPE_BANNER, LESSONS_SHAPE_BANNER, PLANS_SHAPE_BANNER,
)
STAGE_COUNT = len(BANNERS)

LEGACY_INDEX = (
    "# Plans Index\n\n| Abbrev | Name | Status | Created | Last Updated | Path |\n"
    "|--------|------|--------|---------|--------------|------|\n"
    "| ALP | Alpha | COMPLETE | 2026-01-10 | 2026-01-20 | Alpha/ |\n\n"
    "## Status Legend\n\n| Status | Meaning |\n|--------|---------|\n"
    "| NOT_STARTED | Plan created but no work begun |\n"
)


def master_plan(title, status):
    return (
        f"# {title} Master Plan\n\n**Status:** {status}\n**Created:** 2026-01-10\n\n"
        "Body.\n\n*Last Updated: 2026-01-20*\n"
    )


def item(item_id, status, body_status=None):
    header = f"**Status:** {body_status}\n" if body_status else ""
    return f"---\nid: {item_id}\nstatus: {status}\n---\n# {item_id} Title\n\n{header}\n## Notes\n\nText.\n"


def make_project(tmp_path, config=CONFIG, plans=True, backlog=True, backlog_index=True):
    """Build `tmp_path/proj/planwise/` and return `(cfg, planwise_root)`."""
    root = tmp_path / "proj"
    planwise = root / "planwise"
    planwise.mkdir(parents=True)
    (planwise / "config.yaml").write_text(config, encoding="utf-8")
    if plans:
        (planwise / "Plans" / "Alpha").mkdir(parents=True)
        (planwise / "Plans" / "Alpha" / "ALP-Master-Plan.md").write_text(
            master_plan("Alpha", "COMPLETE"), encoding="utf-8"
        )
    if backlog:
        (planwise / "Backlog" / "Archive").mkdir(parents=True)
        if backlog_index:
            (planwise / "Backlog" / "00-Index-Backlog.md").write_text("# Backlog Index\n", encoding="utf-8")
    return SimpleNamespace(project_root=root, planwise_root="planwise"), planwise


def write_generated_plans_index(planwise):
    config = config_loader.load_config(SCRIPTS / "x.py", config_path=planwise / "config.yaml")
    result = gen.write_plans_index(config)
    assert result.refusal is None
    return config["_plans_index"]


def run(cfg, capsys):
    da.run_index_audits(cfg)
    return capsys.readouterr().out


def stage_text(out, banner):
    """The text of one stage: from its banner to the next banner (or the end)."""
    start = out.index(banner)
    rest = out[start + len(banner):]
    ends = [rest.index(b) for b in BANNERS if b in rest]
    return rest[: min(ends)] if ends else rest


def test_all_clear_prints_every_banner_and_verdicts(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    (planwise / "Backlog" / "BB-001-open.md").write_text(item("BB-001", "OPEN"), encoding="utf-8")
    out = run(cfg, capsys)
    assert out.count("planwise doctor —") == STAGE_COUNT
    assert "No drift detected" in stage_text(out, PLANS_BANNER)
    assert "1 of 1 rows compared." in stage_text(out, PLANS_BANNER)
    assert "No archival drift detected" in stage_text(out, BACKLOG_BANNER)
    assert "No body status drift detected" in stage_text(out, BODY_BANNER)
    assert "recommend:" not in out
    assert "the check failed" not in out


def test_output_is_deterministic_and_carries_no_temp_path(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    first = run(cfg, capsys)
    second = run(cfg, capsys)
    assert first == second
    assert str(tmp_path) not in first
    assert "JSON:" not in first


def test_stage_11_stale_row_prints_drift_and_recommend(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    index = write_generated_plans_index(planwise)
    text = index.read_text(encoding="utf-8")
    assert "COMPLETE" in text
    index.write_text(text.replace("| COMPLETE |", "| IN_PROGRESS |", 1), encoding="utf-8")
    section = stage_text(run(cfg, capsys), PLANS_BANNER)
    assert "Drift detected (1 row(s) out of sync with Master Plan status):" in section
    assert "ALP: index=IN_PROGRESS -> Master Plan=COMPLETE" in section
    assert "recommend: Regenerate the plans index" in section
    assert "drops 0 orphan row(s)." in section
    assert "No drift detected" not in section


def test_stage_11_could_not_run_never_says_no_drift(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    index = write_generated_plans_index(planwise)
    text = index.read_text(encoding="utf-8")
    index.write_text(text.replace("Alpha/", "Zeta/"), encoding="utf-8")
    section = stage_text(run(cfg, capsys), PLANS_BANNER)
    assert "Drift audit could not run: 0 of 1 rows compared" in section
    assert "No index row matched a Master Plan on disk." in section
    assert "No drift detected" not in section
    assert "recommend: Regenerate the plans index" in section


def test_stage_11_legacy_index_routes_exit_2_text_to_stdout(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    (planwise / "Plans" / "00-Index-Plans.md").write_text(LEGACY_INDEX, encoding="utf-8")
    captured = run(cfg, capsys)
    section = stage_text(captured, PLANS_BANNER)
    assert "is a hand-authored plans index — run /planwise upgrade to migrate it before auditing it" in section
    assert "No drift detected" not in section
    assert "recommend:" not in section


def test_stage_11_missing_index_routes_exit_1_text_to_stdout(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path, plans=False)
    (planwise / "Plans").mkdir()
    section = stage_text(run(cfg, capsys), PLANS_BANNER)
    assert "Error: Plans index not found at" in section
    assert "No drift detected" not in section


def test_stage_12_closed_item_outside_archive(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    (planwise / "Backlog" / "BB-002-done.md").write_text(item("BB-002", "COMPLETE"), encoding="utf-8")
    (planwise / "Backlog" / "BB-001-done.md").write_text(item("BB-001", "COMPLETE"), encoding="utf-8")
    section = stage_text(run(cfg, capsys), BACKLOG_BANNER)
    assert "Archival drift detected (2 closed item file(s) not in Archive/):" in section
    assert section.index("BB-001-done.md") < section.index("BB-002-done.md")
    assert "closed item file not in Archive/" in section
    assert "recommend: Archive 2 closed item file(s) — move them into `Archive/`?" in section


def test_stage_19_redundant_body_status_line(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    (planwise / "Backlog" / "BB-003-open.md").write_text(item("BB-003", "OPEN", "OPEN"), encoding="utf-8")
    (planwise / "Backlog" / "BB-004-open.md").write_text(item("BB-004", "OPEN", "BLOCKED"), encoding="utf-8")
    section = stage_text(run(cfg, capsys), BODY_BANNER)
    assert "Body status drift detected (2 header-block status line(s) to strip):" in section
    assert "BB-003 (OPEN): BB-003-open.md line 7 — body says OPEN (redundant)" in section
    assert "BB-004 (OPEN): BB-004-open.md line 7 — body says BLOCKED (disagrees)" in section
    assert section.index("BB-003-open.md") < section.index("BB-004-open.md")
    assert "(1 disagree with frontmatter, 1 redundant)? Frontmatter is not changed." in section
    assert "recommend: Strip 2 body status line(s)" in section


def test_missing_plans_directory_prints_failure_line_and_continues(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path, plans=False)
    out = run(cfg, capsys)
    assert "Plans index drift audit: the check failed: the plans directory does not exist" in out
    assert out.count("planwise doctor —") == STAGE_COUNT
    assert "No archival drift detected" in stage_text(out, BACKLOG_BANNER)
    assert "No body status drift detected" in stage_text(out, BODY_BANNER)


def test_missing_backlog_directory_prints_failure_lines_for_both_backlog_stages(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path, backlog=False)
    write_generated_plans_index(planwise)
    out = run(cfg, capsys)
    assert "Backlog archival drift audit: the check failed: the backlog directory does not exist" in out
    assert "Backlog body-status drift audit: the check failed: the backlog directory does not exist" in out
    assert "No drift detected" in stage_text(out, PLANS_BANNER)


def test_missing_backlog_index_prints_the_cli_error_line_for_both_backlog_stages(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path, backlog_index=False)
    index = planwise / "Backlog" / "00-Index-Backlog.md"
    out = run(cfg, capsys)
    for banner in (BACKLOG_BANNER, BODY_BANNER):
        section = stage_text(out, banner)
        assert f"Error: Backlog index not found at {index}" in section
        assert "No archival drift detected" not in section
        assert "No body status drift detected" not in section
        assert "recommend:" not in section


def test_plugin_version_only_config_runs_every_stage_to_a_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path, config="plugin_version: 1.0.0\n", plans=False, backlog=False)
    out = run(cfg, capsys)
    assert out.count("planwise doctor —") == STAGE_COUNT
    # plans drift, both backlog drift stages, backlog shape and plans shape; lessons are unconfigured
    assert out.count("the check failed: the ") == 5
    assert "No drift detected" not in out


def test_no_config_yaml_prints_a_failure_line_per_stage(tmp_path, capsys):
    root = tmp_path / "bare"
    root.mkdir()
    cfg = SimpleNamespace(project_root=root, planwise_root="planwise")
    out = run(cfg, capsys)
    assert out.count("planwise doctor —") == STAGE_COUNT
    assert out.count("config.yaml could not be loaded (no config.yaml found)") == STAGE_COUNT


LESSONS_CONFIG = CONFIG.replace("backlog_dir: Backlog\n", "backlog_dir: Backlog\n  lessons_dir: LessonsLearned\n")


def make_lessons_project(tmp_path, legacy=False):
    """A project whose lessons index is generated (or a legacy hub) over one lesson."""
    cfg, planwise = make_project(tmp_path, config=LESSONS_CONFIG)
    lessons = planwise / "LessonsLearned"
    lessons.mkdir()
    fields = (
        "id: LL-001\ntitle: Fixture\ncategory: process\nseverity: medium\nlanguage: [python]\n"
        "technology: [x]\ndomain: [PROC]\nsource: s\nstatus: documented\n"
    )
    (lessons / "LL-001-PROC-Fixture1.md").write_text(f"---\n{fields}---\n\n# Fixture\n", encoding="utf-8")
    hub = lessons / "00-Index-LessonsLearned.md"
    if legacy:
        hub.write_text("# Lessons Learned Index\n\n## Master Table\n\n| ID | Title |\n|----|----|\n", encoding="utf-8")
    else:
        run_generator(planwise, "--write")
    return cfg, hub


def run_generator(planwise, *args):
    old_argv = sys.argv
    sys.argv = ["generate_lessons_index.py", "--config", str(planwise / "config.yaml"), *args]
    try:
        return gli.main()
    finally:
        sys.argv = old_argv


def test_stage_13_not_configured_prints_the_skip_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path)
    section = stage_text(run(cfg, capsys), LESSONS_BANNER)
    assert "Lessons index: not configured — audit skipped" in section
    assert "No drift detected" not in section


def test_stage_13_all_clear(tmp_path, capsys):
    cfg, _hub = make_lessons_project(tmp_path)
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_BANNER)
    assert "No drift detected. The index matches lesson frontmatter." in section
    assert "the check failed" not in section


def test_stage_13_stale_counter_finding(tmp_path, capsys):
    cfg, hub = make_lessons_project(tmp_path)
    text = hub.read_text(encoding="utf-8")
    assert "**Next available ID:** LL-002" in text
    hub.write_bytes(text.replace("**Next available ID:** LL-002", "**Next available ID:** LL-001").encode("utf-8"))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_BANNER)
    assert "Drift detected (1 finding(s) out of sync with frontmatter):" in section
    assert "[stale-counter]" in section
    assert "No drift detected" not in section


def test_stage_13_legacy_hub_prints_the_upgrade_line_and_no_all_clear(tmp_path, capsys):
    cfg, _hub = make_lessons_project(tmp_path, legacy=True)
    section = stage_text(run(cfg, capsys), LESSONS_BANNER)
    assert "is a hand-authored lessons index — run /planwise upgrade to migrate it" in section
    assert "No drift detected" not in section
    assert "recommend:" not in section


def test_stage_13_missing_lessons_directory_prints_a_failure_line(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path, config=LESSONS_CONFIG)
    assert not (planwise / "LessonsLearned").exists()
    out = run(cfg, capsys)
    assert "Lessons index drift audit: the check failed: the lessons directory does not exist" in out
    assert "No drift detected" not in stage_text(out, LESSONS_BANNER)


def test_stage_13_legacy_hub_also_prints_duplicate_id_findings(tmp_path, capsys):
    cfg, hub = make_lessons_project(tmp_path, legacy=True)
    lessons = hub.parent
    text = (lessons / "LL-001-PROC-Fixture1.md").read_text(encoding="utf-8")
    (lessons / "LL-001-PROC-Fixture2.md").write_text(text, encoding="utf-8")
    section = stage_text(run(cfg, capsys), LESSONS_BANNER)
    assert "is a hand-authored lessons index — run /planwise upgrade to migrate it" in section
    assert "[duplicate-id]" in section
    assert "No drift detected. The index matches" not in section
    assert "the check failed" not in section


def test_generator_check_calls_the_shared_helper(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    planwise = cfg.project_root / cfg.planwise_root
    sentinel = [{"class": "sentinel-class", "id": "SENTINEL-ID", "detail": "from the helper"}]
    fake = {"findings": sentinel, "shape": "generated", "code": 1, "report": {"files": [], "truncated_ids": []}}
    monkeypatch.setattr(lr, "check_lessons_index", lambda config: fake)
    capsys.readouterr()
    assert run_generator(planwise, "--check", "--json") == 1
    payload = json.loads(capsys.readouterr().out)
    assert "SENTINEL-ID" in json.dumps(payload)


def test_a_raising_stage_is_contained_and_the_next_stage_runs(tmp_path, capsys, monkeypatch):
    cfg, _planwise = make_project(tmp_path)

    def boom(config):
        raise ValueError("boom")

    monkeypatch.setattr(da, "_stage_11", boom)
    out = run(cfg, capsys)
    assert "Plans index drift audit: the check failed: boom" in out
    assert "No archival drift detected" in stage_text(out, BACKLOG_BANNER)


# --- Stages 20-22: the index shape audits ---


def backlog_report(**over):
    report = {
        "shape": "generated", "detail": "", "index": "x/00-Index-Backlog.md", "changelog": "populated",
        "items": {"total": 3, "without_frontmatter": 0, "partial_frontmatter": 0,
                  "unreferenced_without_frontmatter": 0},
        "dependencies": {"bare_edges": 0, "edges_missing_from_blocks": 0, "soft_dependency_bullets": 0,
                         "unrecognised_lines": 0},
        "row_mismatches": 0, "parked_ambiguous": {"units": 0, "bytes": 0}, "ready_with_all_repairs": True,
        "would_refuse": [], "questions": [],
        "changelog_files": [{"path": "x/Changelog.md", "tokens": 100, "level": "OK"}],
        "changelog_over_budget": False,
    }
    report.update(over)
    return report


def lessons_report(**over):
    report = {
        "shape": "generated", "detail": "", "index": "x/00-Index-LessonsLearned.md", "changelog": "populated",
        "promotion_log": "populated", "companion": "generated", "changelog_resplit": "within_budget",
        "changelog_renumber": False, "changelog_oversized": [],
        "lessons": {"total": 0, "without_frontmatter": 0, "partial_frontmatter": 0,
                    "titles_needing_quotes": 0, "status_mismatches": 0},
        "cells": {"rows_with_over_title_units": 0, "units": 0}, "prose_sections": {"drop": 0, "relocate": 0},
        "ready_with_all_repairs": True, "would_refuse": [], "questions": [],
    }
    report.update(over)
    return report


def plans_report(**over):
    report = {
        "shape": "generated", "detail": "", "index": "x/00-Index-Plans.md", "rows": 0, "comments": 0,
        "narrative_cells": 0, "attributable": 0, "unattributed": 0, "uncarried_lines": 0, "root_path_rows": 0,
        "prefixed_rows": 0, "status_changes": 0, "append_targets": [], "ready": False, "would_refuse": [],
        "questions": [],
    }
    report.update(over)
    return report


def patch_backlog(monkeypatch, report):
    import migrate_backlog_index as mb

    monkeypatch.setattr(mb, "build_report", lambda config, index_path: report)


def patch_lessons(monkeypatch, report):
    import migrate_lessons_index as ml

    monkeypatch.setattr(ml, "_safe_report", lambda config, index_path: report)


def patch_plans(monkeypatch, report):
    import migrate_plans_index as mp

    monkeypatch.setattr(mp, "_safe_report", lambda config, index_path: report)


def test_stage_20_generated_prints_fields_and_nothing_to_do(tmp_path, capsys, monkeypatch):
    cfg, _planwise = make_project(tmp_path)
    patch_backlog(monkeypatch, backlog_report())
    section = stage_text(run(cfg, capsys), BACKLOG_SHAPE_BANNER)
    for line in ("shape: generated", "changelog: populated", "items.without_frontmatter: 0",
                 "dependencies.soft_dependency_bullets: 0", "row_mismatches: 0",
                 "ready_with_all_repairs: True", "would_refuse: none"):
        assert line in section
    assert "generated shape, nothing to do" in section
    assert "changelog file" not in section


def test_stage_20_over_budget_prints_warn_and_over_rows_and_no_all_clear(tmp_path, capsys, monkeypatch):
    cfg, _planwise = make_project(tmp_path)
    files = [{"path": "x/Changelog-Part-02.md", "tokens": 30000, "level": "OVER"},
             {"path": "x/Changelog.md", "tokens": 19000, "level": "WARN"},
             {"path": "x/Changelog-Part-03.md", "tokens": 100, "level": "OK"}]
    patch_backlog(monkeypatch, backlog_report(changelog_files=files, changelog_over_budget=True))
    section = stage_text(run(cfg, capsys), BACKLOG_SHAPE_BANNER)
    assert "changelog file Changelog-Part-02.md: OVER (30000 tokens)" in section
    assert "changelog file Changelog.md: WARN (19000 tokens)" in section
    assert "Part-03" not in section
    assert "changelog file(s) over the read budget" in section
    assert "--split-changelog" in section
    assert "nothing to do" not in section


def test_stage_20_legacy_prints_counts_and_upgrade_line(tmp_path, capsys, monkeypatch):
    cfg, _planwise = make_project(tmp_path)
    legacy = backlog_report(shape="legacy", ready_with_all_repairs=False, row_mismatches=2)
    legacy["items"]["without_frontmatter"] = 4
    legacy["dependencies"]["edges_missing_from_blocks"] = 5
    patch_backlog(monkeypatch, legacy)
    section = stage_text(run(cfg, capsys), BACKLOG_SHAPE_BANNER)
    assert "shape: legacy" in section
    assert "items.without_frontmatter: 4" in section
    assert "dependencies.edges_missing_from_blocks: 5" in section
    assert "row_mismatches: 2" in section
    assert "run `/planwise upgrade` to migrate automatically; backups land under `upgrade-backups/`" in section
    assert "nothing to do" not in section


def test_stage_20_unrecognized_prints_the_reason_and_left_untouched(tmp_path, capsys, monkeypatch):
    cfg, _planwise = make_project(tmp_path)
    patch_backlog(monkeypatch, backlog_report(shape="unrecognized", detail="no table found",
                                              would_refuse=["no table found"]))
    section = stage_text(run(cfg, capsys), BACKLOG_SHAPE_BANNER)
    assert "no table found" in section
    assert "left untouched; see the migrator's `--report` output" in section
    assert "nothing to do" not in section


def test_stage_20_corrupt_index_prints_the_failure_line_and_the_run_continues(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    (planwise / "Backlog" / "00-Index-Backlog.md").write_bytes(b"\xff\xfe\x00\x80 not a table \xc3\x28")
    out = run(cfg, capsys)
    section = stage_text(out, BACKLOG_SHAPE_BANNER)
    assert "shape: unknown" in section
    assert "the shape report failed:" in section
    assert "nothing to do" not in section
    assert "generated shape, nothing to do" in stage_text(out, PLANS_SHAPE_BANNER)
    assert str(tmp_path) not in out


def test_stage_20_missing_index_prints_the_error_line_and_no_verdict(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path, backlog_index=False)
    section = stage_text(run(cfg, capsys), BACKLOG_SHAPE_BANNER)
    assert f"Error: Backlog index not found at {planwise / 'Backlog' / '00-Index-Backlog.md'}" in section
    assert "shape:" not in section
    assert "nothing to do" not in section


def test_stage_20_missing_backlog_directory_prints_a_failure_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path, backlog=False)
    out = run(cfg, capsys)
    assert "Backlog index shape audit: the check failed: the backlog directory does not exist" in out
    assert "shape:" not in stage_text(out, BACKLOG_SHAPE_BANNER)


def test_stage_21_generated_prints_fields_and_nothing_to_do(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    patch_lessons(monkeypatch, lessons_report())
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    for line in ("shape: generated", "changelog_resplit: within_budget", "changelog_renumber: False",
                 "changelog_oversized: none", "promotion_log: populated", "companion: generated",
                 "lessons.without_frontmatter: 0", "cells.units: 0", "prose_sections: drop=0, relocate=0",
                 "would_refuse: none"):
        assert line in section
    assert "generated shape, nothing to do" in section


def test_stage_21_legacy_prints_counts_and_upgrade_line(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    legacy = lessons_report(shape="legacy", changelog_resplit="not_applicable", ready_with_all_repairs=False)
    legacy["lessons"]["without_frontmatter"] = 7
    legacy["cells"]["units"] = 3
    patch_lessons(monkeypatch, legacy)
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "lessons.without_frontmatter: 7" in section
    assert "cells.units: 3" in section
    assert "run `/planwise upgrade` to migrate automatically; backups land under `upgrade-backups/`" in section
    assert "nothing to do" not in section


def test_stage_21_unrecognized_prints_the_reason_and_left_untouched(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    patch_lessons(monkeypatch, lessons_report(shape="unrecognized", detail="no master table",
                                              changelog_resplit="not_applicable"))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "no master table" in section
    assert "left untouched" in section
    assert "nothing to do" not in section


def test_stage_21_would_split_prints_the_resplit_line_and_the_renumber_variant(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="would_split"))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "the next `/planwise upgrade` re-splits the changelog; backups land under `upgrade-backups/`" in section
    assert "nothing to do" not in section
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="would_split", changelog_renumber=True))
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "renumbers the changelog entries by position (the oldest becomes Entry 1)" in section
    assert "re-splits the changelog" not in section


def test_stage_21_converged_prints_nothing_to_do_and_each_oversized_entry(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    oversized = [{"file": "Changelog-Part-02.md", "entry": 9, "tokens": 40000, "budget": 20000},
                 {"file": "Changelog.md", "entry": 3, "tokens": 25000, "budget": 20000}]
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="converged", changelog_oversized=oversized))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "generated shape, nothing to do" in section
    assert "oversized entry: Changelog-Part-02.md entry 9: 40000 tokens, budget 20000" in section
    assert "oversized entry: Changelog.md entry 3: 25000 tokens, budget 20000" in section


def test_stage_21_oversized_entries_carry_no_absolute_path_and_print_once(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    oversized = [{"file": str(tmp_path / "Lessons" / "Changelog.md"), "entry": 3, "tokens": 25000, "budget": 20000},
                 {"file": str(tmp_path / "Lessons" / "Changelog-Part-02.md"), "entry": 9, "tokens": 40000,
                  "budget": 20000}]
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="converged", changelog_oversized=oversized))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert str(tmp_path) not in section
    assert "oversized entry: Changelog.md entry 3: 25000 tokens, budget 20000" in section
    assert "changelog_oversized:" not in section
    assert section.count("Changelog-Part-02.md") == 1


def test_stage_21_oversized_field_renders_file_names_deterministically(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    oversized = [{"tokens": 40000, "entry": 9, "budget": 20000, "file": str(tmp_path / "Lessons" / "B.md")},
                 {"tokens": 25000, "entry": 3, "budget": 20000, "file": str(tmp_path / "Lessons" / "A.md")}]
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="would_split", changelog_oversized=oversized))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert str(tmp_path) not in section
    assert ("changelog_oversized: budget=20000 entry=3 file=A.md tokens=25000, "
            "budget=20000 entry=9 file=B.md tokens=40000") in section


def test_stage_21_refused_prints_the_reason_and_no_all_clear(tmp_path, capsys, monkeypatch):
    cfg, _hub = make_lessons_project(tmp_path)
    patch_lessons(monkeypatch, lessons_report(changelog_resplit="refused", ready_with_all_repairs=False,
                                              would_refuse=["line 12 is not inside an entry"]))
    capsys.readouterr()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "line 12 is not inside an entry" in section
    assert "`/planwise upgrade` will refuse until that changelog line is fixed" in section
    assert "nothing to do" not in section


def test_stage_21_not_configured_prints_the_skip_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path)
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert "Lessons index: not configured — audit skipped" in section
    assert "shape:" not in section


def test_stage_21_missing_index_prints_the_error_line_and_no_verdict(tmp_path, capsys):
    cfg, hub = make_lessons_project(tmp_path)
    hub.unlink()
    section = stage_text(run(cfg, capsys), LESSONS_SHAPE_BANNER)
    assert f"Error: Lessons index not found at {hub}" in section
    assert "shape:" not in section
    assert "nothing to do" not in section


def test_stage_21_missing_lessons_directory_prints_a_failure_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path, config=LESSONS_CONFIG)
    out = run(cfg, capsys)
    assert "Lessons index shape audit: the check failed: the lessons directory does not exist" in out
    assert "shape:" not in stage_text(out, LESSONS_SHAPE_BANNER)


def test_stage_22_generated_prints_fields_and_nothing_to_do(tmp_path, capsys, monkeypatch):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    patch_plans(monkeypatch, plans_report())
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    for line in ("shape: generated", "index: 00-Index-Plans.md", "rows: 0", "append_targets: none",
                 "ready: False", "would_refuse: none"):
        assert line in section
    assert "generated shape, nothing to do" in section


def test_stage_22_legacy_prints_counts_and_upgrade_line(tmp_path, capsys, monkeypatch):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    patch_plans(monkeypatch, plans_report(shape="legacy", rows=4, root_path_rows=1, ready=True,
                                          append_targets=["Beta/B-Master-Plan.md", "Alpha/A-Master-Plan.md"]))
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    assert "rows: 4" in section
    assert "root_path_rows: 1" in section
    assert "append_targets: Alpha/A-Master-Plan.md, Beta/B-Master-Plan.md" in section
    assert "run `/planwise upgrade` to migrate automatically; backups land under `upgrade-backups/`" in section
    assert "nothing to do" not in section


def test_stage_22_unrecognized_prints_the_reason_and_left_untouched(tmp_path, capsys, monkeypatch):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    patch_plans(monkeypatch, plans_report(shape="unrecognized", detail="the header row is not the plans table"))
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    assert section.count("the header row is not the plans table") == 1
    assert "left untouched" in section
    assert "nothing to do" not in section


def test_stage_22_absent_prints_no_plans_index_found(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    index = write_generated_plans_index(planwise)
    index.write_text("", encoding="utf-8")
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    assert "shape: absent" in section
    assert "no plans index found" in section
    assert "nothing to do" not in section


def test_stage_22_missing_index_file_prints_the_error_line_and_no_verdict(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path)
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    assert "Error: Plans index not found at" in section
    assert "shape:" not in section
    assert "nothing to do" not in section


def test_stage_22_missing_plans_directory_prints_a_failure_line(tmp_path, capsys):
    cfg, _planwise = make_project(tmp_path, plans=False)
    out = run(cfg, capsys)
    assert "Plans index shape audit: the check failed: the plans directory does not exist" in out
    assert "shape:" not in stage_text(out, PLANS_SHAPE_BANNER)


def test_stage_22_report_error_prints_the_failure_line(tmp_path, capsys, monkeypatch):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    patch_plans(monkeypatch, {"shape": "unknown", "index": "x", "error": "ValueError('boom')"})
    section = stage_text(run(cfg, capsys), PLANS_SHAPE_BANNER)
    assert "the shape report failed: ValueError('boom')" in section
    assert "nothing to do" not in section
