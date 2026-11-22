"""User-scope paths follow CLAUDE_CONFIG_DIR, and fall back to `Path.home()/.claude` when it is unset.

Six sites resolve the user-level Claude config folder: the style-rule folder and the rules-tree search
in `style_rules`, the user settings path in `upgrade_preflight` (which `upgrade_apply` and
`upgrade_run` read), `init_project.get_settings_path` and `get_thrifty_sonic_paths`, and
`doctor_cli._sweep_thrifty_sonic`. Each one must resolve through `install_check.default_config_dir()`.

Every test redirects the home folder through the conftest's `_isolated_home`. The scratch config folder
sits under `tmp_path`, is not `Path.home() / ".claude"`, and is named `.claude` so the user-settings
write guard in `upgrade_run` accepts it. A shipped-path test also asserts that the redirected home
holds no `.claude` folder afterwards, so a leak into the home tree fails by name.

Run with:  python -m pytest -q tests/test_config_dir_resolution.py
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import doctor_cli
import init_project as ip
import style_rules as sr
import upgrade_apply
import upgrade_card_project as ucp
import upgrade_preflight as up

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"
LANGUAGE, PRESENTATION = "plain-language.md", "plain-presentation.md"
THRIFTY = "CLAUDE_CODE_THRIFTY_SONIC"


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch) -> Path:
    """A scratch config folder named `.claude`, set as CLAUDE_CONFIG_DIR, that is not the home config."""
    scratch = tmp_path / "scratch" / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(scratch))
    assert scratch != Path.home() / ".claude"
    return scratch


@pytest.fixture
def e2e_cfg_dir(tmp_path, monkeypatch) -> Path:
    """`cfg_dir` for a test that builds whole projects: the builders' patches first, then the variable."""
    ucp.isolate(monkeypatch)
    scratch = tmp_path / "scratch" / ".claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(scratch))
    return scratch


def make_cfg(tmp_path: Path, scope: str = "user"):
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return ip.InitConfig(project_name="CfgDirFixture", project_root=project, plugin_root=PLUGIN_ROOT,
                         install_scope=ip.InstallScope(scope))


def write_settings(path: Path, value: str | None) -> None:
    """A settings file whose env carries the thrifty-sonic key at `value`, or no key when None."""
    path.parent.mkdir(parents=True, exist_ok=True)
    env = {} if value is None else {THRIFTY: value}
    path.write_text(json.dumps({"env": env}), encoding="utf-8")


def sweep_user_path(cfg) -> Path:
    """The user-level path the doctor sweep names: its second target, after the project's."""
    return doctor_cli._sweep_thrifty_sonic(cfg)[1]["settings_path"]


# (site, the resolved path as the site returns it, its location under the config folder)
SITES = [
    pytest.param(lambda cfg: sr.style_rule_dir(cfg), "rules/planwise", id="style_rule_dir"),
    pytest.param(lambda cfg: sr._rules_trees(cfg)[1], "rules", id="rules_trees_home"),
    pytest.param(lambda cfg: up.resolve_user_settings(None)[0], "settings.json", id="resolve_user_settings"),
    pytest.param(lambda cfg: ip.get_settings_path(cfg), "settings.json", id="get_settings_path"),
    pytest.param(lambda cfg: ip.get_thrifty_sonic_paths(cfg)[1], "settings.json", id="get_thrifty_sonic_paths"),
    pytest.param(sweep_user_path, "settings.json", id="sweep_thrifty_sonic"),
]


@pytest.mark.parametrize("site, rel", SITES)
def test_site_resolves_under_the_config_dir(tmp_path, cfg_dir, site, rel):
    assert site(make_cfg(tmp_path)) == cfg_dir.joinpath(*rel.split("/"))


@pytest.mark.parametrize("site, rel", SITES)
def test_site_falls_back_to_the_home_config_when_unset(tmp_path, monkeypatch, site, rel):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert site(make_cfg(tmp_path)) == (Path.home() / ".claude").joinpath(*rel.split("/"))


@pytest.mark.parametrize("site, rel", SITES)
def test_site_treats_an_empty_variable_as_unset(tmp_path, monkeypatch, site, rel):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")
    assert site(make_cfg(tmp_path)) == (Path.home() / ".claude").joinpath(*rel.split("/"))


def test_user_scope_style_install_writes_under_the_config_dir(tmp_path, cfg_dir):
    installed, _skipped = sr.install_style_rules(make_cfg(tmp_path))
    assert installed == [LANGUAGE, PRESENTATION]
    for name in (LANGUAGE, PRESENTATION):
        written = cfg_dir / "rules" / "planwise" / name
        assert written.read_bytes() == (PLUGIN_ROOT / "references" / name).read_bytes(), name
    assert not (Path.home() / ".claude").exists()


def test_a_copy_under_the_config_dir_rules_is_a_home_tree_hit(tmp_path, cfg_dir):
    copy = cfg_dir / "rules" / LANGUAGE
    copy.parent.mkdir(parents=True)
    copy.write_bytes((PLUGIN_ROOT / "references" / LANGUAGE).read_bytes())
    cfg = make_cfg(tmp_path)
    assert sr.find_existing_copy(cfg, LANGUAGE) == (copy, "identical")
    installed, skipped = sr.install_style_rules(cfg)
    assert installed == [PRESENTATION]  # the home-tree copy blocks one rule and not the other
    assert [(name, path, verdict, wrote) for name, path, verdict, wrote in skipped] == \
        [(LANGUAGE, copy, "identical", False)]
    assert not (Path.home() / ".claude").exists()


def test_a_copy_under_the_home_config_is_not_found_when_the_variable_is_set(tmp_path, cfg_dir):
    stray = Path.home() / ".claude" / "rules" / LANGUAGE
    stray.parent.mkdir(parents=True)
    stray.write_bytes((PLUGIN_ROOT / "references" / LANGUAGE).read_bytes())
    assert sr.find_existing_copy(make_cfg(tmp_path), LANGUAGE) is None


def test_resolve_user_settings_flag_wins_over_the_variable(tmp_path, cfg_dir):
    flag = tmp_path / "elsewhere" / "settings.json"
    assert up.resolve_user_settings(str(flag)) == (flag, "step 1: --user-settings flag")


def test_resolve_user_settings_labels_its_source(tmp_path, monkeypatch, cfg_dir):
    path, label = up.resolve_user_settings(None)
    assert path == cfg_dir / "settings.json" and "CLAUDE_CONFIG_DIR" in label
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert up.resolve_user_settings(None) == (Path.home() / ".claude" / "settings.json", "step 2: home settings")


def test_thrifty_offer_reads_the_config_dir_settings(tmp_path, cfg_dir):
    cfg = make_cfg(tmp_path)
    write_settings(cfg_dir / "settings.json", "false")
    write_settings(Path.home() / ".claude" / "settings.json", "true")  # the home file must not be read
    found = up.offers(cfg, up.resolve_user_settings(None)[0])
    assert found["thrifty"]["user"] == "ok"


def test_doctor_sweep_reads_the_config_dir_settings(tmp_path, cfg_dir):
    cfg = make_cfg(tmp_path)
    write_settings(cfg.project_root / ".claude" / "settings.json", "false")
    write_settings(cfg_dir / "settings.json", "false")
    assert doctor_cli._sweep_thrifty_sonic(cfg) == []
    (cfg_dir / "settings.json").unlink()
    findings = doctor_cli._sweep_thrifty_sonic(cfg)
    assert [(f["settings_path"], f["klass"]) for f in findings] == [(cfg_dir / "settings.json", "missing")]


def test_init_thrifty_sonic_writes_the_config_dir_and_not_the_home(tmp_path, cfg_dir):
    cfg = make_cfg(tmp_path, "project")
    results = dict(ip.configure_thrifty_sonic(cfg))
    assert results[cfg_dir / "settings.json"] == "added"
    assert json.loads((cfg_dir / "settings.json").read_text(encoding="utf-8"))["env"][THRIFTY] == "false"
    assert not (Path.home() / ".claude").exists()


def test_upgrade_card_names_the_config_dir_settings(tmp_path, capsys, e2e_cfg_dir):
    root = ucp.make_project(tmp_path)
    capsys.readouterr()
    assert up.run(["upgrade", "--project-root", str(root)]) == 0
    card = capsys.readouterr().out
    line = next(line for line in card.splitlines() if line.startswith("user settings: "))
    assert line.startswith(f"user settings: {(e2e_cfg_dir / 'settings.json').as_posix()} (")
    assert "CLAUDE_CONFIG_DIR" in line
    assert "thrifty-sonic={project:ok, user:ok}" in card
    assert not (Path.home() / ".claude").exists()


def test_thrifty_sonic_add_writes_the_config_dir_settings(tmp_path, capsys, e2e_cfg_dir):
    box = ucp.upgraded(tmp_path)
    user = e2e_cfg_dir / "settings.json"
    ucp.drop_env_key(ucp.settings_path(box), THRIFTY)
    ucp.drop_env_key(user, THRIFTY)
    assert upgrade_apply.main(["--project-root", str(box), "--thrifty-sonic", "add"]) == 0, capsys.readouterr().out
    assert json.loads(user.read_text(encoding="utf-8-sig"))["env"][THRIFTY] == "false"
    assert not (Path.home() / ".claude").exists()
