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
    ends = [rest.index(b) for b in (PLANS_BANNER, BACKLOG_BANNER, BODY_BANNER, LESSONS_BANNER) if b in rest]
    return rest[: min(ends)] if ends else rest


def test_all_clear_prints_four_banners_and_verdicts(tmp_path, capsys):
    cfg, planwise = make_project(tmp_path)
    write_generated_plans_index(planwise)
    (planwise / "Backlog" / "BB-001-open.md").write_text(item("BB-001", "OPEN"), encoding="utf-8")
    out = run(cfg, capsys)
    assert out.count("planwise doctor —") == 4
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
    assert out.count("planwise doctor —") == 4
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
    assert out.count("planwise doctor —") == 4
    assert out.count("the check failed: the ") == 3
    assert "No drift detected" not in out


def test_no_config_yaml_prints_a_failure_line_per_stage(tmp_path, capsys):
    root = tmp_path / "bare"
    root.mkdir()
    cfg = SimpleNamespace(project_root=root, planwise_root="planwise")
    out = run(cfg, capsys)
    assert out.count("planwise doctor —") == 4
    assert out.count("config.yaml could not be loaded (no config.yaml found)") == 4


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
