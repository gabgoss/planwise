"""Tests for the plan name caps: the `plan_names` config block, the Name cuts and the path cap.

The caps live in `config_loader.get_plan_names_config`. `scaffold_plan.cap_spec_names` cuts the
free-text Name parts, and `scaffold_plan.path_cap_lines` refuses a plan with a path over the cap.
Both `scaffold_plan.py render` and `plan_build.py` apply them.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import config_loader
import plan_build as pb
import scaffold_plan as sp
from test_plan_build import Build, bodies_set, index_of
from test_scaffold_plan import make_spec

SIXTY = "ReadThePathThroughTheLedgerAndCheckEveryRowTwiceBeforeAnyWrite"  # at least 60 characters
LONG_TASK = "ParseEveryLedgerRowThenCheckItAgainstTheSchemaAndReportEachMismatchInOneTable"  # more than 80 minus its prefix


def _long_spec():
    spec = make_spec()
    spec["sprints"][0]["sessions"][0]["name"] = SIXTY
    spec["sprints"][0]["sessions"][0]["tasks"][0]["name"] = LONG_TASK
    return spec


def _config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _names(root):
    """Every folder and file name under `root`, as a list of (kind, name)."""
    return [("dir" if p.is_dir() else "file", p.name) for p in Path(root).rglob("*")]


# ---- the config block

def test_the_defaults_are_forty_eighty_and_one_sixty():
    assert config_loader.get_plan_names_config({}) == {"folder_max": 40, "file_max": 80, "path_max": 160}


def test_the_template_block_states_the_defaults():
    text = (Path(sp.PLUGIN_ROOT) / "config.yaml.template").read_text(encoding="utf-8")
    block = config_gen.extract_top_level_block(text, "plan_names")
    assert block is not None
    for line in ("  folder_max: 40", "  file_max: 80", "  path_max: 160"):
        assert line in block.splitlines()
    assert "plan_names" in config_gen.MIGRATABLE_TOP_LEVEL_KEYS


def test_a_key_overrides_its_default_and_leaves_the_others():
    caps = config_loader.get_plan_names_config({"plan_names": {"folder_max": 30}})
    assert caps == {"folder_max": 30, "file_max": 80, "path_max": 160}


@pytest.mark.parametrize("bad", [0, -5, True, "wide", None, [40], {"a": 1}])
def test_a_value_that_is_no_positive_number_falls_back_to_the_default(bad):
    assert config_loader.get_plan_names_config({"plan_names": {"folder_max": bad}})["folder_max"] == 40


@pytest.mark.parametrize("block", [None, "forty", ["folder_max"], 7])
def test_a_block_that_is_no_mapping_falls_back_to_every_default(block):
    assert config_loader.get_plan_names_config({"plan_names": block}) == sp.DEFAULT_NAME_CAPS


def test_load_name_caps_reads_the_block_and_reports_an_unreadable_config(tmp_path):
    caps, note = sp.load_name_caps(_config(tmp_path, "plan_names:\n  file_max: 70\n"))
    assert (caps["file_max"], note) == (70, None)
    caps, note = sp.load_name_caps(tmp_path / "missing.yaml")
    assert caps == sp.DEFAULT_NAME_CAPS
    assert "default caps apply" in note
    assert sp.load_name_caps(None) == (sp.DEFAULT_NAME_CAPS, None)


def test_a_config_the_yaml_parser_rejects_reads_as_the_default_caps(tmp_path):
    caps, note = sp.load_name_caps(_config(tmp_path, "plans_dir: [unterminated\n"))
    assert caps == sp.DEFAULT_NAME_CAPS
    assert "default caps apply" in note


# ---- the cut

def test_a_name_inside_its_room_is_kept():
    assert sp.fit_name("ReadPath", 8) == "ReadPath"


@pytest.mark.parametrize("name, room, expected", [
    ("ReadThePathThroughTheLedger", 12, "ReadThePath"),
    ("ReadThePath", 4, "Read"),
    ("HTTPServerSetup", 11, "HTTPServer"),
    ("Sprint2Go", 7, "Sprint2"),
    ("Averyverylongsingleword", 6, "Averyv"),
])
def test_a_cut_ends_on_a_word_boundary_when_a_whole_word_fits(name, room, expected):
    assert sp.fit_name(name, room) == expected
    assert len(expected) <= room


def test_a_sixty_character_session_name_gives_a_folder_of_at_most_forty():
    assert len(SIXTY) >= 60
    capped, notes, errors = sp.cap_spec_names(_long_spec(), sp.DEFAULT_NAME_CAPS)
    assert errors == []
    session = capped["sprints"][0]["sessions"][0]
    folder = sp.session_dir(capped["sprints"][0], session).rsplit("/", 1)[-1]
    assert len(folder) <= 40
    assert any(f"name {SIXTY} cut to {session['name']}" in n for n in notes)


def test_a_long_task_name_gives_a_file_name_of_at_most_eighty():
    sprint0, session0 = make_spec()["sprints"][0], make_spec()["sprints"][0]["sessions"][0]
    head = f"{sp.task_id(make_spec(), sprint0, session0, session0['tasks'][0])}-Sonnet-"
    assert len(head) + len(LONG_TASK) + len(".md") > 80
    capped, notes, _errors = sp.cap_spec_names(_long_spec(), sp.DEFAULT_NAME_CAPS)
    sprint = capped["sprints"][0]
    session = sprint["sessions"][0]
    assert len(sp.task_filename(capped, sprint, session, session["tasks"][0])) <= 80
    assert any(f"name {LONG_TASK} cut to" in n for n in notes)


def test_a_cut_is_reported_once_and_leaves_the_input_spec_alone():
    spec = _long_spec()
    before = copy.deepcopy(spec)
    _capped, notes, _errors = sp.cap_spec_names(spec, sp.DEFAULT_NAME_CAPS)
    assert spec == before
    assert len([n for n in notes if "cut to" in n]) == 2


def test_a_spec_whose_names_all_fit_is_returned_unchanged_with_no_note():
    spec = make_spec()
    capped, notes, errors = sp.cap_spec_names(spec, sp.DEFAULT_NAME_CAPS)
    assert (capped, notes, errors) == (spec, [], [])


def test_a_spec_value_that_still_names_the_old_folder_is_reported():
    spec = _long_spec()
    old_folder = f"Sprint-01-LedgerCore/Session-01-{SIXTY}/Outputs/QZX-parse.md"
    spec["sprints"][0]["sessions"][0]["tasks"][1]["outputs"].append(old_folder)
    _capped, notes, _errors = sp.cap_spec_names(spec, sp.DEFAULT_NAME_CAPS)
    stale = [n for n in notes if "still name" in n]
    assert len(stale) == 1
    assert f"Session-01-{SIXTY}" in stale[0]


def test_a_cap_with_no_room_for_a_name_is_an_error_and_cuts_nothing_for_that_part():
    caps = {**sp.DEFAULT_NAME_CAPS, "folder_max": 10}
    capped, _notes, errors = sp.cap_spec_names(make_spec(), caps)
    assert errors and all("leaves no room for a Name" in e for e in errors)
    assert capped["sprints"][0]["name"] == "LedgerCore"


# ---- the path cap

def test_over_cap_paths_count_the_plan_folder_prefix():
    paths = ["a" * 20 + "/" + "b" * 20]
    assert sp.over_cap_paths(paths, "", 41) == []
    assert sp.over_cap_paths(paths, "plan", 41) == [("plan/" + "a" * 20 + "/" + "b" * 20, 46)]


def test_the_repo_prefix_is_empty_for_the_project_root_and_unmeasured_outside_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert sp.repo_prefix(tmp_path) == ("", True)
    assert sp.repo_prefix(tmp_path / "planwise" / "Plans" / "X") == ("planwise/Plans/X", True)
    assert sp.repo_prefix(tmp_path.parent) == ("", False)


# ---- scaffold_plan render and lint-spec

def _write_spec(tmp_path, spec):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_render_cuts_the_names_reports_them_and_every_generated_path_fits(tmp_path, capsys):
    spec = _write_spec(tmp_path, _long_spec())
    out = tmp_path / "plan"
    assert sp.main(["render", "--spec", str(spec), "--out", str(out)]) == 0
    stdout = capsys.readouterr().out
    assert stdout.count("NOTE: ") == 2
    rels = [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()]
    assert rels
    assert max(len(r) for r in rels) <= 160
    for kind, name in _names(out):
        assert len(name) <= (40 if kind == "dir" else 80) or name.endswith("-Sprint-Plan.md"), name


def test_render_takes_its_caps_from_the_config(tmp_path, capsys):
    spec = _write_spec(tmp_path, _long_spec())
    config = _config(tmp_path, "plan_names:\n  folder_max: 24\n")
    out = tmp_path / "plan"
    assert sp.main(["render", "--spec", str(spec), "--out", str(out), "--config", str(config)]) == 0
    capsys.readouterr()
    folders = [name for kind, name in _names(out) if kind == "dir" and name.startswith(("Sprint-", "Session-"))]
    assert folders and all(len(f) <= 24 for f in folders)


def test_render_refuses_a_path_over_the_cap_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _write_spec(tmp_path, make_spec())
    config = _config(tmp_path, "plan_names:\n  path_max: 80\n")
    out = tmp_path / "Exec-QZX"
    assert sp.main(["render", "--spec", str(spec), "--out", str(out), "--config", str(config)]) == 2
    stdout = capsys.readouterr().out
    # Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md is 74 characters, plus Exec-QZX/.
    assert "PATH-CAP: Exec-QZX/Sprint-01-LedgerCore/Session-01-ReadPath/QZX-S01-01-01-Sonnet-ParseRows.md is 83 characters, over the 80 cap" in stdout
    assert "REFUSED:" in stdout
    assert not out.exists()


def test_render_accepts_the_same_plan_when_the_cap_holds(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _write_spec(tmp_path, make_spec())
    config = _config(tmp_path, "plan_names:\n  path_max: 160\n")
    out = tmp_path / "Exec-QZX"
    assert sp.main(["render", "--spec", str(spec), "--out", str(out), "--config", str(config)]) == 0
    assert "rendered" in capsys.readouterr().out
    assert out.is_dir()


def test_render_refuses_a_cap_with_no_room_for_a_name(tmp_path, capsys):
    spec = _write_spec(tmp_path, make_spec())
    config = _config(tmp_path, "plan_names:\n  folder_max: 10\n")
    assert sp.main(["render", "--spec", str(spec), "--out", str(tmp_path / "plan"), "--config", str(config)]) == 2
    assert "leaves no room for a Name" in capsys.readouterr().out
    assert not (tmp_path / "plan").exists()


def test_lint_spec_prints_each_cut_as_a_note_and_stays_clean(tmp_path, capsys):
    spec = _write_spec(tmp_path, _long_spec())
    assert sp.main(["lint-spec", "--spec", str(spec)]) == 0
    stdout = capsys.readouterr().out
    assert stdout.count("NOTE: ") == 2
    assert "lint=clean" in stdout


def test_lint_spec_fails_a_cap_with_no_room_for_a_name(tmp_path, capsys):
    spec = _write_spec(tmp_path, make_spec())
    config = _config(tmp_path, "plan_names:\n  file_max: 20\n")
    assert sp.main(["lint-spec", "--spec", str(spec), "--config", str(config)]) == 1
    assert "lint_errors=" in capsys.readouterr().out


# ---- plan_build

def test_render_core_cuts_the_names_the_skeleton_is_built_from(tmp_path, capsys):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_long_spec()), encoding="utf-8")
    core, files, _index = pb.render_core(str(spec_path), sp.DEFAULT_TEMPLATES)
    session = core["sprints"][0]["sessions"][0]
    assert session["name"] != SIXTY
    assert capsys.readouterr().out.count("NOTE: ") == 2
    assert all(len(rel.split("/")[1]) <= 40 for rel in files if rel.count("/") >= 2)


def test_build_writes_names_inside_the_caps(tmp_path, capsys):
    spec = _long_spec()
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, spec)), spec)
    code, out = build.run()
    assert code == 0, out
    assert out.count("NOTE: ") >= 2
    folders = [p.name for p in build.out.iterdir() if p.is_dir() and p.name.startswith("Sprint-")]
    sessions = [p.name for p in build.out.glob("Sprint-*/Session-*") if p.is_dir()]
    assert folders and sessions and all(len(s) <= 40 for s in sessions)


def test_build_refuses_a_path_over_the_cap_before_it_writes(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build = Build(tmp_path, capsys, bodies_set(index_of(tmp_path, make_spec())))
    build.config.write_text("plans: plans\nplan_names:\n  path_max: 80\n", encoding="utf-8")
    code, out = build.run()
    assert code == 2
    assert "PATH-CAP: Exec-QZX/Sprint-01-LedgerCore/" in out
    assert "REFUSED:" in out
    assert not build.out.exists()
    assert not build.manifest.exists()
