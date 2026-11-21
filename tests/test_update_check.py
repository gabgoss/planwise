"""update_check.py: the session-start update verdict and the plugin update."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import install_check
import update_check
import version_notice

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "update_check.py"
MARKET = "planwise-marketplace"
GITHUB = {"source": "github", "repo": "example-owner/planwise"}
FIELDS = {"verdict", "running", "installed", "clone", "latest", "pin", "marketplace", "scope",
          "repo", "auto_update", "config_path", "pending", "opt_out"}


# --- fixtures, in the shape of tests/test_install_check.py -------------------

def _plugin(root: Path, version: str) -> Path:
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "planwise", "version": version}), encoding="utf-8"
    )
    return root


def _home(base: Path, clone_version: str = "1.0.8", source=GITHUB, auto_update=True, record=True) -> Path:
    """A config dir with known_marketplaces.json and a marketplace clone."""
    config = base / "claude"
    plugins = config / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
    clone = plugins / "marketplaces" / MARKET
    (clone / ".claude-plugin").mkdir(parents=True)
    (clone / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": MARKET, "plugins": [{"name": "planwise", "source": "./plugins/planwise"}]}),
        encoding="utf-8",
    )
    _plugin(clone / "plugins" / "planwise", clone_version)
    known = {}
    if record:
        rec = {"installLocation": str(clone), "lastUpdated": "2026-11-01T00:00:00.000Z"}
        if source is not None:
            rec["source"] = source
        if auto_update is not None:
            rec["autoUpdate"] = auto_update
        known[MARKET] = rec
    (plugins / "known_marketplaces.json").write_text(json.dumps(known), encoding="utf-8")
    return config


def _cache(config: Path, version: str) -> Path:
    return _plugin(config / "plugins" / "cache" / MARKET / "planwise" / version, version)


def _install(config: Path, entries: list) -> None:
    (config / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {f"planwise@{MARKET}": entries}}), encoding="utf-8"
    )


def _entry(scope: str, install_path: Path, version: str, project=None):
    entry = {"scope": scope, "installPath": str(install_path), "version": version,
             "lastUpdated": "2026-11-01T00:00:00.000Z"}
    if project is not None:
        entry["projectPath"] = str(project)
    return entry


def _project(base: Path, pin=None) -> Path:
    project = base / "proj"
    project.mkdir(parents=True, exist_ok=True)
    if pin is not None:
        (project / "planwise").mkdir(exist_ok=True)
        (project / "planwise" / "config.yaml").write_text(
            f"# planwise configuration\nplugin_version: {pin}\nplans_dir: planwise/Plans\n", encoding="utf-8"
        )
    return project


def _setup(base: Path, running="1.0.8", installed=None, clone="1.0.8", pin=None, scope="project", **home):
    """A config dir, a running cache copy and a project. `installed` names a
    second cache copy that the install entry points at; default: the running copy."""
    config = _home(base, clone_version=clone, **home)
    running_root = _cache(config, running)
    project = _project(base, pin)
    target = _cache(config, installed) if installed else running_root
    _install(config, [_entry(scope, target, installed or running, None if scope == "user" else project)])
    return config, running_root, project


@pytest.fixture(autouse=True)
def _config_lookup(monkeypatch):
    """Point version_notice's config lookup at the fixture's planwise/config.yaml.

    The lookup's planwise-marker test lives in config_loader, outside this
    test's fixtures. The pin itself is still read by version_notice's real
    `_pinned_version()`, and the live `check` run reads a real project config.
    """
    def resolve(project_root):
        path = Path(project_root) / "planwise" / "config.yaml"
        return path if path.is_file() else None

    monkeypatch.setattr(version_notice, "resolve_config", resolve)


@pytest.fixture
def env(tmp_path, monkeypatch):
    def build(**kwargs):
        config, running_root, project = _setup(tmp_path, **kwargs)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
        return config, running_root, project
    return build


# --- verdict rows of the design's section 3 ----------------------------------

def test_row1_pin_newer_is_current_even_when_clone_is_newer(env):
    _, running, project = env(running="1.0.8", clone="1.0.9", pin="1.0.9")
    result = update_check.check(running, project)
    assert result["verdict"] == update_check.CURRENT
    assert result["pin"] == "1.0.9" and result["latest"] == "1.0.9"


def test_row2_restart_when_applicable_install_is_newer_than_running(env):
    _, running, project = env(running="1.0.7", installed="1.0.8", clone="1.0.8", pin="1.0.6")
    result = update_check.check(running, project)
    assert result["verdict"] == update_check.RESTART  # wins over PROJECT_BEHIND below it
    assert result["installed"] == "1.0.8" and result["running"] == "1.0.7"


def test_row2_not_restart_when_other_install_is_older(env):
    _, running, project = env(running="1.0.8", installed="1.0.7", clone="1.0.8")
    assert update_check.check(running, project)["verdict"] == update_check.CURRENT


def test_row3_plugin_behind_from_the_clone(env):
    _, running, project = env(running="1.0.8", clone="1.0.9", pin="1.0.7")
    result = update_check.check(running, project)
    assert result["verdict"] == update_check.PLUGIN_BEHIND  # wins over PROJECT_BEHIND below it
    assert result["latest"] == "1.0.9" and result["clone"] == "1.0.9"


def test_row3_plugin_behind_from_latest_tag(env):
    _, running, project = env(running="1.0.8", clone="1.0.8")
    result = update_check.check(running, project, latest="planwise--v1.0.10")
    assert result["verdict"] == update_check.PLUGIN_BEHIND
    assert result["latest"] == "1.0.10"


def test_row4_project_behind(env):
    _, running, project = env(running="1.0.8", clone="1.0.8", pin="1.0.7")
    result = update_check.check(running, project)
    assert result["verdict"] == update_check.PROJECT_BEHIND
    assert result["config_path"] == (project / "planwise" / "config.yaml").as_posix()


def test_row5_current_when_all_match(env):
    _, running, project = env(running="1.0.8", clone="1.0.8", pin="1.0.8")
    result = update_check.check(running, project)
    assert result["verdict"] == update_check.CURRENT
    assert set(result) == FIELDS
    assert result["marketplace"] == MARKET and result["scope"] == "project"


def test_no_config_reads_null_pin(env):
    _, running, project = env(running="1.0.8", clone="1.0.8")
    result = update_check.check(running, project)
    assert result["pin"] is None and result["config_path"] is None
    assert result["verdict"] == update_check.CURRENT


def test_no_config_still_reports_plugin_behind(env):
    _, running, project = env(running="1.0.8", clone="1.0.9")
    assert update_check.check(running, project)["verdict"] == update_check.PLUGIN_BEHIND


def test_prerelease_latest_is_never_latest(env):
    _, running, project = env(running="1.0.8", clone="1.0.8")
    result = update_check.check(running, project, latest="planwise--v9.9.9-rc1")
    assert result["latest"] == "1.0.8"
    assert result["verdict"] == update_check.CURRENT


def test_bare_four_part_latest(env):
    _, running, project = env(running="1.0.5.4", clone="1.0.5.4")
    result = update_check.check(running, project, latest="1.0.5.5")
    assert result["verdict"] == update_check.PLUGIN_BEHIND and result["latest"] == "1.0.5.5"


def test_plugin_dir_running_root_cannot_restart_or_plugin_behind(tmp_path, monkeypatch):
    config = _home(tmp_path, clone_version="1.0.9")
    installed = _cache(config, "1.0.8")
    dev = _plugin(tmp_path / "dev" / "planwise", "1.0.7")
    project = _project(tmp_path, "1.0.7")
    _install(config, [_entry("project", installed, "1.0.8", project)])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    result = update_check.check(dev, project, latest="1.0.10")
    assert result["verdict"] == update_check.CURRENT
    assert result["installed"] == "1.0.8" and result["latest"] == "1.0.10"


def test_plugin_dir_running_root_still_reports_project_behind(tmp_path, monkeypatch):
    config = _home(tmp_path, clone_version="1.0.9")
    installed = _cache(config, "1.0.9")
    dev = _plugin(tmp_path / "dev" / "planwise", "1.0.8")
    project = _project(tmp_path, "1.0.6")
    _install(config, [_entry("project", installed, "1.0.9", project)])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert update_check.check(dev, project)["verdict"] == update_check.PROJECT_BEHIND


def test_no_install_record_is_current_with_nulls(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    dev = _plugin(tmp_path / "dev" / "planwise", "1.0.8")
    result = update_check.check(dev, _project(tmp_path))
    assert result["verdict"] == update_check.CURRENT
    assert result["marketplace"] is None and result["installed"] is None and result["repo"] is None


# --- repo and auto_update from known_marketplaces.json -------------------------

def test_repo_from_github_source(env):
    _, running, project = env()
    result = update_check.check(running, project)
    assert result["repo"] == "example-owner/planwise"
    assert result["auto_update"] is True


def test_repo_null_for_directory_source(env):
    _, running, project = env(source={"source": "directory", "path": "C:/market"}, auto_update=False)
    result = update_check.check(running, project)
    assert result["repo"] is None
    assert result["auto_update"] is False


def test_repo_null_for_missing_record(env):
    _, running, project = env(record=False)
    result = update_check.check(running, project)
    assert result["repo"] is None and result["auto_update"] is None and result["clone"] is None


# --- check reads files only ------------------------------------------------------

def test_check_starts_no_process(env, monkeypatch, capsys):
    _, running, project = env(clone="1.0.9")

    def boom(*args, **kwargs):
        raise AssertionError("check must not start a process")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    code = update_check.main(["check", "--running-root", str(running), "--project-root", str(project)])
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["verdict"] == update_check.PLUGIN_BEHIND


def test_cli_check_prints_one_json_line(tmp_path):
    # No config here: a child process does not see the in-process lookup stub.
    config, running, project = _setup(tmp_path, running="1.0.8", clone="1.0.8")
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "check", "--running-root", str(running),
         "--project-root", str(project), "--latest", "planwise--v1.0.9"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "CLAUDE_CONFIG_DIR": str(config)},
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert set(data) == FIELDS
    assert data["verdict"] == update_check.PLUGIN_BEHIND and data["latest"] == "1.0.9"


def test_cli_usage_error_exits_2():
    with pytest.raises(SystemExit) as exc:
        update_check.main(["check", "--project-root", "x"])
    assert exc.value.code == 2


# --- update, with subprocess.run stubbed -----------------------------------------

def _fake_run(calls, update_stdout="", update_code=0):
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["plugin", "update"]:
            return subprocess.CompletedProcess(cmd, update_code, stdout=update_stdout, stderr="update failed")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run


def test_update_argv_scope_and_cwd(env, monkeypatch, tmp_path):
    _, running, project = env(clone="1.0.9")
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout='{"status":"updated"}'))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    code, report = update_check.update(running, project, data_dir=data_dir)
    assert code == update_check.EXIT_UPDATED and report["result"] == update_check.UPDATED
    assert [c[0] for c in calls] == [
        ["claude", "plugin", "marketplace", "update", MARKET],
        ["claude", "plugin", "update", f"planwise@{MARKET}", "--scope", "project", "--json"],
    ]
    assert calls[1][1]["cwd"] == str(project)
    assert calls[1][1]["timeout"] == 300
    assert all("-y" not in c[0] and "--yes" not in c[0] for c in calls)
    assert list(data_dir.iterdir()) == []  # the store branch writes no marker file


def test_update_needs_confirm(env, monkeypatch, capsys):
    _, running, project = env()
    calls = []
    out = json.dumps({"confirmCommand": "claude plugin install helper@other"})
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout=out))
    code = update_check.main(["update", "--running-root", str(running), "--project-root", str(project)])
    data = json.loads(capsys.readouterr().out)
    assert code == update_check.EXIT_NEEDS_CONFIRM == 3
    assert data["result"] == update_check.NEEDS_CONFIRM
    assert data["command"] == "claude plugin install helper@other"


def test_update_failure_exits_1(env, monkeypatch):
    _, running, project = env()
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_code=1))
    code, report = update_check.update(running, project)
    assert code == update_check.EXIT_FAILED and report["detail"] == "exit 1: update failed"


def test_update_refresh_failure_still_updates(env, monkeypatch):
    _, running, project = env()
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        code = 1 if cmd[1:3] == ["plugin", "marketplace"] else 0
        return subprocess.CompletedProcess(cmd, code, stdout="", stderr="network unreachable")

    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", run)
    code, report = update_check.update(running, project)
    assert code == update_check.EXIT_UPDATED
    assert report["refresh"] == "exit 1: network unreachable"
    assert len(calls) == 2


def test_update_without_claude_exits_1(env, monkeypatch):
    _, running, project = env()
    monkeypatch.setattr(shutil_mod(), "which", lambda name: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no run")))
    code, report = update_check.update(running, project)
    assert code == update_check.EXIT_FAILED and "claude is not on PATH" in report["detail"]


def test_update_without_install_runs_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no run")))
    dev = _plugin(tmp_path / "dev" / "planwise", "1.0.8")
    code, report = update_check.update(dev, _project(tmp_path))
    assert code == update_check.EXIT_FAILED and report["argv"] is None


def shutil_mod():
    return update_check.shutil


# --- loops over keys: one subTest per key ------------------------------------------

class TestKeyedCases(unittest.TestCase):
    def test_tag_shapes(self):
        cases = {
            "planwise--v1.0.9": "1.0.9",
            "1.0.5.4": "1.0.5.4",
            "1.0.9": "1.0.9",
            "planwise--v1.0.9-rc1": None,
            "1.0.9-rc1": None,
            "v1.0.9": None,
            "latest": None,
            "": None,
            None: None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(update_check.parse_version(text), expected)

    def test_highest_and_zero_pad(self):
        cases = {
            ("1.0.5.4", "1.0.5"): "1.0.5.4",
            ("planwise--v1.0.10", "1.0.9"): "1.0.10",
            ("1.0.9-rc1", "1.0.8"): "1.0.8",
            (None, None): None,
        }
        for args, expected in cases.items():
            with self.subTest(args=args):
                self.assertEqual(update_check.highest(*args), expected)
        self.assertTrue(update_check.newer("1.0.5.1", "1.0.5"))
        self.assertFalse(update_check.newer("1.0.5.0", "1.0.5"))
        self.assertEqual(install_check.compare_versions("1.0.5.0", "1.0.5"), 0)

    def test_update_cwd_per_scope(self):
        for scope, wants_cwd in (("project", True), ("local", True), ("user", False)):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                config, running, project = _setup(Path(tmp), scope=scope)
                calls = []
                with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config)}), \
                        mock.patch.object(update_check.shutil, "which", lambda name: "claude"), \
                        mock.patch.object(subprocess, "run", _fake_run(calls)):
                    code, report = update_check.update(running, project)
                self.assertEqual(code, update_check.EXIT_UPDATED)
                self.assertEqual(report["scope"], scope)
                self.assertEqual(calls[1][0][-3:], ["--scope", scope, "--json"])
                self.assertEqual(calls[1][1]["cwd"], str(project) if wants_cwd else None)

    def test_pending_and_opt_out_are_null_on_store_and_userconfig(self):
        self.assertEqual((update_check.MARKER_HOME, update_check.OPT_OUT_HOME), ("store", "userConfig"))
        rows = {
            "current": {},
            "project_behind": {"pin": "1.0.7"},
            "plugin_behind": {"clone": "1.0.9"},
            "restart": {"running": "1.0.7", "installed": "1.0.8"},
        }
        for name, kwargs in rows.items():
            with self.subTest(row=name), tempfile.TemporaryDirectory() as tmp:
                config, running, project = _setup(Path(tmp), **kwargs)
                data_dir = Path(tmp) / "data"
                data_dir.mkdir()
                with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config)}):
                    result = update_check.check(running, project, data_dir=str(data_dir))
                self.assertIsNone(result["pending"])
                self.assertIsNone(result["opt_out"])
                self.assertEqual(list(data_dir.iterdir()), [])
