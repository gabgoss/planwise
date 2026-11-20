#!/usr/bin/env python3
"""Tests for the move of an older install's working folders into the current layout.

`plan-build/` moves to `{plans_dir}/Plan-Build/`. `feedback-drafts/` and the loose
files in `Feedback/` move to `Feedback/Feedback-Drafts/`. `layout_migrate` does the
move for `/planwise init` and `/planwise upgrade`, and every consumer who updates the
plugin gets it, so the cases below follow the situations an unseen install can be in.

Pinned here:
  - a missing folder is created, and an old folder is moved with every file;
  - a file is never overwritten and never deleted: a clash, a locked file and a failed
    rename leave the file where it was and list it in the report;
  - a second run changes nothing;
  - a custom `project.feedback_dir` is kept, and the key is rewritten only from a legacy value;
  - the config each case starts from comes from the real generator, not from typed text;
  - every scanner of the plans folder skips `Plan-Build`, and still finds a real plan beside it.

Run with:  python -m pytest tests/test_layout_migrate.py -q
"""
import inspect
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import change_closeout
import config_loader
import constants
import doctor_probes
import init_project
import layout_migrate
import parse_plans
import plan_build
import plan_preflight
from config_gen import ConfigResult, InitConfig, generate_config, get_plugin_root


def _project(tmp_path, plans_dir="Plans", feedback_value="Feedback/Feedback-Drafts"):
    """A project whose config.yaml the real generator wrote, with `feedback_dir` set as asked.

    `feedback_value` None removes the key, which is how a config that predates it reads.
    """
    cfg = InitConfig(project_name="p", project_root=tmp_path, plugin_root=get_plugin_root(), plans_dir=plans_dir)
    (tmp_path / cfg.planwise_root).mkdir()
    result, _ = generate_config(cfg)
    assert result == ConfigResult.CREATED
    path = tmp_path / cfg.planwise_root / "config.yaml"
    _set_feedback_key(path, feedback_value)
    return cfg, tmp_path / cfg.planwise_root, path


def _set_feedback_key(path, value):
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^([ \t]+)feedback_dir:.*$", re.MULTILINE)
    assert pattern.search(text), "the generated config carries no feedback_dir line"
    new = pattern.sub("", text) if value is None else pattern.sub(lambda m: f'{m.group(1)}feedback_dir: "{value}"', text)
    path.write_text(new, encoding="utf-8")


def _key(path):
    return (yaml.safe_load(path.read_text(encoding="utf-8")).get("project") or {}).get("feedback_dir")


def _write(folder, name, text="x"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    return folder / name


def _names(folder):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


# --------------------------------------------------------------------------- plan-build

def test_plan_build_is_created_when_no_old_folder_exists(tmp_path):
    _cfg, root, _ = _project(tmp_path)
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.state == "created"
    assert (root / "Plans" / "Plan-Build").is_dir()


def test_plan_build_move_keeps_every_file_and_removes_the_old_folder(tmp_path):
    _cfg, root, _ = _project(tmp_path)
    _write(root / "plan-build" / "Demo", "QZX-build-spec.json", "{}")
    _write(root / "plan-build" / "Demo", "QZX-bodies-plan.md", "# body")
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.state == "moved" and report.moved == 2 and report.left == []
    assert _names(root / "Plans" / "Plan-Build") == ["Demo/QZX-bodies-plan.md", "Demo/QZX-build-spec.json"]
    assert not (root / "plan-build").exists()


def test_plan_build_second_run_changes_nothing(tmp_path):
    _cfg, root, _ = _project(tmp_path)
    _write(root / "plan-build" / "Demo", "a.md")
    layout_migrate.migrate_plan_build(root, root / "Plans")
    before = _names(root)
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.state == "already present" and report.moved == 0
    assert _names(root) == before


def test_plan_build_merge_never_overwrites_and_reports_the_clash(tmp_path):
    _cfg, root, _ = _project(tmp_path)
    _write(root / "plan-build" / "Demo", "same.md", "old")
    _write(root / "plan-build" / "Demo", "only-old.md", "old")
    _write(root / "Plans" / "Plan-Build" / "Demo", "same.md", "new")
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.state == "merged" and report.moved == 1
    assert (root / "Plans" / "Plan-Build" / "Demo" / "same.md").read_text(encoding="utf-8") == "new"
    assert (root / "plan-build" / "Demo" / "same.md").read_text(encoding="utf-8") == "old"
    assert any("same.md" in item for item in report.left)
    assert (root / "Plans" / "Plan-Build" / "Demo" / "only-old.md").is_file()


def test_plan_build_follows_a_custom_plans_dir(tmp_path):
    cfg, root, _ = _project(tmp_path, plans_dir="MyPlans")
    _write(root / "plan-build" / "Demo", "a.md")
    plans_dir = tmp_path / config_loader.resolve_index_target(cfg, "plans")[0]
    assert plans_dir == root / "MyPlans"
    layout_migrate.migrate_plan_build(root, plans_dir)
    assert (root / "MyPlans" / "Plan-Build" / "Demo" / "a.md").is_file()
    assert not (root / "Plans").exists()


def test_a_failed_rename_falls_back_to_a_file_by_file_move(tmp_path, monkeypatch):
    _cfg, root, _ = _project(tmp_path)
    _write(root / "plan-build" / "Demo", "a.md")

    def locked(src, dst):
        raise PermissionError("folder is in use")

    monkeypatch.setattr(layout_migrate.os, "rename", locked)
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.state == "merged" and report.moved == 1
    assert (root / "Plans" / "Plan-Build" / "Demo" / "a.md").is_file()


def test_a_locked_file_stays_in_place_and_the_rest_move(tmp_path, monkeypatch):
    _cfg, root, _ = _project(tmp_path)
    _write(root / "plan-build" / "Demo", "locked.md")
    _write(root / "plan-build" / "Demo", "free.md")
    real_move = shutil.move

    def flaky(src, dst):
        if Path(src).name == "locked.md":
            raise PermissionError("in use by another process")
        return real_move(src, dst)

    monkeypatch.setattr(layout_migrate.os, "rename", lambda s, d: (_ for _ in ()).throw(OSError("no rename")))
    monkeypatch.setattr(layout_migrate.shutil, "move", flaky)
    report = layout_migrate.migrate_plan_build(root, root / "Plans")
    assert report.moved == 1 and len(report.left) == 1 and "locked.md" in report.left[0]
    assert (root / "plan-build" / "Demo" / "locked.md").is_file()
    assert (root / "Plans" / "Plan-Build" / "Demo" / "free.md").is_file()


# --------------------------------------------------------------------------- feedback drafts

def test_legacy_drafts_folder_moves_with_its_posted_markers_and_the_key_follows(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    _write(root / "feedback-drafts", "2026-01-01-bug-a.md")
    _write(root / "feedback-drafts", "2026-01-01-bug-a.md.posted")
    report = layout_migrate.migrate_feedback_drafts(root, path)
    assert report is not None and report.state == "moved" and report.moved == 2
    assert _names(root / "Feedback" / "Feedback-Drafts") == ["2026-01-01-bug-a.md", "2026-01-01-bug-a.md.posted"]
    assert not (root / "feedback-drafts").exists()
    assert _key(path) == "Feedback/Feedback-Drafts"


def test_loose_files_in_feedback_move_and_the_subfolder_is_not_a_source(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="Feedback")
    _write(root / "Feedback", "2026-01-01-idea-a.md")
    _write(root / "Feedback" / "Feedback-Drafts", "2026-02-02-bug-b.md")
    report = layout_migrate.migrate_feedback_drafts(root, path)
    assert report.moved == 1
    assert _names(root / "Feedback") == ["Feedback-Drafts/2026-01-01-idea-a.md", "Feedback-Drafts/2026-02-02-bug-b.md"]
    assert _key(path) == "Feedback/Feedback-Drafts"


def test_both_sources_merge_and_a_clash_is_left_and_reported(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    _write(root / "feedback-drafts", "a.md", "from-legacy")
    _write(root / "feedback-drafts", "clash.md", "from-legacy")
    _write(root / "Feedback", "b.md", "loose")
    _write(root / "Feedback", "clash.md", "loose")
    report = layout_migrate.migrate_feedback_drafts(root, path)
    drafts = root / "Feedback" / "Feedback-Drafts"
    assert report.state == "merged" and report.moved == 3
    assert sorted(p.name for p in drafts.iterdir()) == ["a.md", "b.md", "clash.md"]
    assert (drafts / "clash.md").read_text(encoding="utf-8") == "from-legacy"
    assert (root / "Feedback" / "clash.md").read_text(encoding="utf-8") == "loose"
    assert len(report.left) == 1 and "clash.md" in report.left[0]


def test_a_custom_feedback_dir_is_kept_and_nothing_moves(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="MyDrafts")
    _write(root / "feedback-drafts", "a.md")
    _write(root / "Feedback", "b.md")
    before = path.read_bytes()
    report = layout_migrate.migrate_feedback_drafts(root, path)
    assert report.state == "kept" and "custom project.feedback_dir kept" in report.note
    assert path.read_bytes() == before
    assert (root / "feedback-drafts" / "a.md").is_file() and (root / "Feedback" / "b.md").is_file()


def test_an_absent_key_moves_the_old_drafts_and_leaves_the_key_to_the_backfill(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value=None)
    _write(root / "feedback-drafts", "a.md")
    report = layout_migrate.migrate_feedback_drafts(root, path)
    assert report.moved == 1 and _key(path) is None
    assert (root / "Feedback" / "Feedback-Drafts" / "a.md").is_file()


def test_nothing_to_move_prints_nothing_and_a_second_run_changes_nothing(tmp_path):
    _cfg, root, path = _project(tmp_path)
    assert layout_migrate.migrate_feedback_drafts(root, path) is None
    _write(root / "feedback-drafts", "a.md")
    _set_feedback_key(path, "feedback-drafts")
    assert layout_migrate.migrate_feedback_drafts(root, path) is not None
    before = (path.read_bytes(), _names(root))
    assert layout_migrate.migrate_feedback_drafts(root, path) is None
    assert (path.read_bytes(), _names(root)) == before


def test_a_legacy_key_with_no_files_is_still_repointed(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="Feedback")
    report = layout_migrate.migrate_feedback_drafts(root, path)
    assert report is not None and "project.feedback_dir now" in report.note
    assert _key(path) == "Feedback/Feedback-Drafts"


def test_a_missing_config_still_moves_the_folders_and_never_raises(tmp_path):
    root = tmp_path / "planwise"
    _write(root / "feedback-drafts", "a.md")
    report = layout_migrate.migrate_feedback_drafts(root, root / "config.yaml")
    assert report.moved == 1


def test_the_key_rewrite_keeps_comments_and_still_parses(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    comments = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.lstrip().startswith("#")]
    _write(root / "feedback-drafts", "a.md")
    layout_migrate.migrate_feedback_drafts(root, path)
    after = path.read_text(encoding="utf-8").splitlines()
    assert [ln for ln in after if ln.lstrip().startswith("#")] == comments
    assert _key(path) == "Feedback/Feedback-Drafts"


# --------------------------------------------------------------------------- init and upgrade wiring

def test_init_moves_before_it_creates_so_no_empty_twin_is_left(tmp_path):
    cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    _write(root / "plan-build" / "Demo", "a.md")
    _write(root / "feedback-drafts", "d.md")
    reports = init_project._apply_layout_migration(cfg, path, create_plan_build=False)
    assert [r.state for r in reports] == ["moved", "moved"]
    created = init_project.create_directories(cfg)
    assert not any(c.endswith("Plan-Build") for c in created)
    assert not (root / "plan-build").exists() and not (root / "feedback-drafts").exists()
    assert (root / "Plans" / "Plan-Build" / "Demo" / "a.md").is_file()


def test_a_fresh_init_creates_both_new_folders_and_no_old_ones(tmp_path):
    cfg = InitConfig(project_name="p", project_root=tmp_path, plugin_root=get_plugin_root())
    (tmp_path / cfg.planwise_root).mkdir()
    created = init_project.create_directories(cfg)
    assert "planwise\\Plans\\Plan-Build" in [c.replace("/", "\\") for c in created]
    assert (tmp_path / "planwise" / "Feedback" / "Feedback-Drafts").is_dir()
    assert not (tmp_path / "planwise" / "plan-build").exists()
    assert not (tmp_path / "planwise" / "feedback-drafts").exists()


def test_the_backfill_writes_the_new_default_even_beside_an_old_folder(tmp_path):
    cfg, root, path = _project(tmp_path, feedback_value=None)
    _write(root / "feedback-drafts", "a.md")
    assert init_project._backfill_feedback_dir(cfg, path) is None
    assert _key(path) == "Feedback/Feedback-Drafts"


def test_upgrade_runs_the_move_at_both_exits_and_prints_one_line_per_folder(tmp_path, capsys):
    cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    _write(root / "plan-build" / "Demo", "a.md")
    _write(root / "feedback-drafts", "d.md")
    source = inspect.getsource(artifact_upgrade._run_upgrade)
    assert source.count("_apply_layout_migration(cfg, config_path)") == 2
    artifact_upgrade._apply_layout_migration(cfg, path)
    out = capsys.readouterr().out
    assert "Plan-Build directory: moved" in out and "Feedback drafts: moved" in out
    artifact_upgrade._apply_layout_migration(cfg, path)
    again = capsys.readouterr().out
    assert "Plan-Build directory: already present" in again and "Feedback drafts" not in again


# --------------------------------------------------------------------------- constants and resolution

def test_the_two_plan_build_names_agree_and_the_feedback_default_is_the_nested_path():
    assert constants.PLAN_BUILD_DIRNAME == config_loader.PLAN_BUILD_DIRNAME == "Plan-Build"
    assert config_loader.PROJECT_DIR_DEFAULTS["feedback_dir"] == layout_migrate.NEW_FEEDBACK_DIR
    assert InitConfig(project_name="p", project_root=Path("."), plugin_root=Path(".")).feedback_dir == layout_migrate.NEW_FEEDBACK_DIR


def test_load_config_resolves_both_new_folders(tmp_path):
    _cfg, root, path = _project(tmp_path, plans_dir="MyPlans")
    config = config_loader.load_config(config_path=path)
    assert config["_plan_build_dir"] == config["_plans_dir"] / "Plan-Build"
    assert config["_feedback_dir"] == root / "Feedback" / "Feedback-Drafts"


# --------------------------------------------------------------------------- scanners skip Plan-Build

def _plan_with_master(plans, name, abbrev):
    _write(plans / name, f"{abbrev}-Master-Plan.md", "**Status:** IN_PROGRESS\n")


def test_enumerate_master_plans_skips_plan_build_and_finds_the_plan_beside_it(tmp_path):
    plans = tmp_path / "Plans"
    _plan_with_master(plans, "Real", "RRR")
    _plan_with_master(plans, "Plan-Build", "BBB")
    paths = [entry.path for entry in parse_plans.enumerate_master_plans(plans)]
    assert paths == ["Real/"]


def test_change_closeout_skips_plan_build_and_still_finds_a_real_plan(tmp_path):
    plans = tmp_path / "Plans"
    _plan_with_master(plans, "Real", "RRR")
    _plan_with_master(plans / "Plan-Build", "Demo", "BBB")
    assert [p.name for p in change_closeout.find_plans(plans)] == ["Real"]
    _write(plans / "Plan-Build" / "Demo", "QZX-bodies-plan.md", "needle")
    _write(plans / "Real", "note.md", "needle")
    backlog = tmp_path / "Backlog"
    backlog.mkdir()
    result = change_closeout.scan(["needle"], plans, backlog)
    hit_paths = " ".join(str(hit[0]) for hit in result["hits"]) if result.get("hits") else ""
    assert "Plan-Build" not in hit_paths


def test_plan_preflight_skips_plan_build_abbreviations(tmp_path):
    plans = tmp_path / "Plans"
    _plan_with_master(plans, "Real", "RRR")
    _plan_with_master(plans / "Plan-Build", "Demo", "BBB")
    assert plan_preflight.folder_abbreviations(plans) == {"RRR"}


def test_plan_build_refuses_a_plan_named_plan_build(tmp_path):
    config = _write(tmp_path, "config.yaml")
    bodies = tmp_path / "bodies"
    bodies.mkdir()

    def args(out):
        return SimpleNamespace(date=None, config=str(config), bodies_dir=str(bodies), out=str(out))

    assert plan_build.build_inputs_refusal(args(tmp_path / "Plans" / "Plan-Build")).startswith("REFUSED: Plan-Build")
    assert plan_build.build_inputs_refusal(args(tmp_path / "Plans" / "Real")) is None


# --------------------------------------------------------------------------- doctor

def test_doctor_names_a_legacy_layout_and_stays_quiet_for_a_current_one_or_a_custom_key(tmp_path):
    _cfg, root, path = _project(tmp_path, feedback_value="feedback-drafts")
    _write(root / "plan-build" / "Demo", "a.md")
    found = doctor_probes._legacy_layout_folders(config_loader.load_config(config_path=path))
    assert found == [("plan-build/", "Plans/Plan-Build/"), ("feedback-drafts/", "Feedback/Feedback-Drafts/")]
    layout_migrate.migrate_plan_build(root, root / "Plans")
    layout_migrate.migrate_feedback_drafts(root, path)
    assert doctor_probes._legacy_layout_folders(config_loader.load_config(config_path=path)) == []
    _set_feedback_key(path, "MyDrafts")
    assert doctor_probes._legacy_layout_folders(config_loader.load_config(config_path=path)) == []
