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

def _fake_run(calls, update_stdout="", update_code=0, update_stderr="update failed"):
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["plugin", "update"]:
            return subprocess.CompletedProcess(cmd, update_code, stdout=update_stdout, stderr=update_stderr)
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


# --- a git linked worktree: the main checkout's install applies there --------------

def _linked_worktree(base: Path, pin: str) -> "tuple[Path, Path]":
    """A real main checkout with a committed planwise config, and a real linked worktree nested
    in it. git writes the worktree's `.git` file, so the lookup reads the producer's own bytes."""
    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@example.test", "-c", "commit.gpgsign=false", *args],
            cwd=main, check=True, capture_output=True,
        )

    main = base.resolve() / "main"
    (main / "planwise").mkdir(parents=True)
    (main / "planwise" / "config.yaml").write_text(
        f"# planwise configuration\nplugin_version: {pin}\nplans_dir: planwise/Plans\n", encoding="utf-8"
    )
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    linked = main / ".claude" / "worktrees" / "wt"
    git("worktree", "add", "-q", str(linked), "-b", "wt")
    return main, linked


def test_check_in_a_linked_worktree_reads_the_main_checkout_install(tmp_path, monkeypatch):
    config = _home(tmp_path, clone_version="1.0.9")
    running = _cache(config, "1.0.8")
    main, linked = _linked_worktree(tmp_path, "1.0.8")
    _install(config, [_entry("project", running, "1.0.8", main)])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    in_main = update_check.check(running, main)
    in_worktree = update_check.check(running, linked)
    assert (in_main["verdict"], in_main["scope"]) == (update_check.PLUGIN_BEHIND, "project")
    assert (in_worktree["verdict"], in_worktree["scope"], in_worktree["installed"]) == (
        update_check.PLUGIN_BEHIND, "project", "1.0.8")
    # The pin still comes from the worktree's own config, not from the main checkout's.
    assert Path(in_worktree["config_path"]) == linked / "planwise" / "config.yaml"


def test_update_in_a_linked_worktree_runs_in_the_main_checkout(tmp_path, monkeypatch):
    config = _home(tmp_path, clone_version="1.0.9")
    running = _cache(config, "1.0.8")
    main, linked = _linked_worktree(tmp_path, "1.0.8")  # real git, before subprocess.run is stubbed
    _install(config, [_entry("project", running, "1.0.8", main)])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout='{"status":"updated"}'))
    code, report = update_check.update(running, linked)
    assert code == update_check.EXIT_UPDATED and report["scope"] == "project"
    assert calls[1][0] == ["claude", "plugin", "update", f"planwise@{MARKET}", "--scope", "project", "--json"]
    # The CLI updates the install recorded for its working directory: the main checkout.
    assert calls[1][1]["cwd"] == str(main)


def test_update_runs_in_a_folder_that_exists_when_the_record_spells_it_oddly(env, monkeypatch):
    config, running, project = env(clone="1.0.9")
    # The record matches the project after normalising, in a spelling that may not open here.
    odd = str(project).replace("/", "\\").upper() + "\\"
    _install(config, [{"scope": "project", "projectPath": odd, "installPath": str(running), "version": "1.0.8"}])
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout='{"status":"updated"}'))
    code, _report = update_check.update(running, project)
    assert code == update_check.EXIT_UPDATED
    assert os.path.samefile(calls[1][1]["cwd"], project)


# The refusals below are real output of `claude plugin ... --json` on CLI 2.1.330, taken on
# 2026-11-23 with no -y and with stdout piped, so the CLI could only display the declared command.
# Each run exited 1. Human lines come first and the JSON result is the last line. The two install
# refusals declared `python` with no argument, because the field that carries arguments did not
# exist. The update refusal declared one argument and its `shownCommand.command` holds the whole
# line. A PowerShell capture showed an em dash as mojibake, so the text here uses the real one.
_REFUSED_COMMAND_SOURCE_STDOUT = (
    '"cmdplug" is installed by running a command from marketplace "upb-confirm-cmd" on this machine:\n'
    "  python\n"
    '  (mode "copy": its output directory is copied into the plugin cache)\n'
    "Not an interactive terminal, so the command was only displayed, not accepted. "
    "Re-run in a terminal to confirm it, or pass -y/--yes to accept the command shown above.\n"
    '{"command":"install","outcome":"failed","plugin":"cmdplug@upb-confirm-cmd","scope":"user",'
    '"message":"cmdplug@upb-confirm-cmd is installed by running a command on this machine (`python`) '
    "that has not been reviewed yet, so it was not run. Review and accept it from its /plugin details "
    'pane, or in a terminal: run `claude plugin install cmdplug@upb-confirm-cmd`.",'
    '"failureCode":"command_source_refused","shownCommand":{"kind":"command_source",'
    '"pluginId":"cmdplug@upb-confirm-cmd","command":"python","mode":"copy",'
    '"catalogRevision":"sha256:727de8e4d47b8152c0726d84410de1d1551053b2124003c47d8da3a66f045d67",'
    '"sha256":"074fdbda5cb401cfa4dd1193374be82511ebc52184463afd5e293c16b4c08c9c"}}\n'
)
_REFUSED_COMMAND_SOURCE_STDERR = (
    "cmdplug@upb-confirm-cmd is installed by running a command on this machine (`python`) that has not "
    "been reviewed yet, so it was not run. Review and accept it from its /plugin details pane, or in a "
    "terminal: run `claude plugin install cmdplug@upb-confirm-cmd`.\n"
)
_REFUSED_ENTRY_HELPER_STDOUT = (
    "Fetching this plugin's archive sends helper-minted headers to https://example.invalid/arcplug.zip; "
    "the local command it runs (headersHelper) is: C:/Users/gabgo/.claude/scratch/upb-confirm/hh.cmd\n"
    "Not an interactive terminal, so the command was only displayed, not accepted. "
    "Re-run in a terminal to confirm it, or pass -y/--yes to accept the command shown above.\n"
    '{"command":"install","outcome":"failed","plugin":"arcplug@upb-confirm-arc","scope":"user",'
    '"message":"Aborted \u2014 the command was not run.","failureCode":"entry_helper_unconfirmed",'
    '"shownCommand":{"kind":"entry_helper","pluginId":"arcplug@upb-confirm-arc",'
    '"command":"C:/Users/gabgo/.claude/scratch/upb-confirm/hh.cmd",'
    '"archiveUrl":"https://example.invalid/arcplug.zip",'
    '"catalogRevision":"sha256:119b92aaa986cb317150d9d3d3576ef61362ed56567111c5655d79c6e0c93f8c",'
    '"sha256":"533ef218aa4bfa97232ac80d17bf122a2e596bee3870bd1928f67606da1e4774"}}\n'
)
# `claude plugin update planwise@<mp> --scope user --json` on an installed command-source plugin
# whose marketplace then changed the declared command. Exit 1, and the command did not run.
# `previousAcceptance` is only on the update refusal.
_REFUSED_UPDATE_STDOUT = (
    '"planwise" is installed by running a command from marketplace "upb-confirm-upd" on this machine'
    " \u2014 and that command (or how its output is used) CHANGED since you accepted it:\n"
    "  python C:/Users/gabgo/.claude/scratch/upb-confirm/upd/make_plugin.py changed\n"
    '  (mode "copy": its output directory is copied into the plugin cache)\n'
    "Not an interactive terminal, so the command was only displayed, not accepted. "
    "Re-run in a terminal to confirm it, or pass -y/--yes to accept the command shown above.\n"
    '{"command":"update","outcome":"failed","plugin":"planwise@upb-confirm-upd","scope":"user",'
    '"message":"planwise@upb-confirm-upd\'s marketplace changed the command that installs it, or how its '
    "output is used (now `python C:/Users/gabgo/.claude/scratch/upb-confirm/upd/make_plugin.py changed`), "
    "since it was accepted, so it was not run. Review and accept the new command: run "
    "`claude plugin update planwise@upb-confirm-upd` in a terminal "
    '(add `--scope` for a project/local install).",'
    '"failureCode":"command_source_refused","shownCommand":{"kind":"command_source",'
    '"pluginId":"planwise@upb-confirm-upd",'
    '"command":"python C:/Users/gabgo/.claude/scratch/upb-confirm/upd/make_plugin.py changed",'
    '"mode":"copy",'
    '"catalogRevision":"sha256:75d536de0bc103cd16c5677fa5950da4c4b24744709fbabe5bca33217e04aab3",'
    '"previousAcceptance":"changed",'
    '"sha256":"14a45fe604699488081f2fa8205081a99a7e29fa7db616ddb82ca5d29c9b0247"}}\n'
)
_REFUSED_UPDATE_STDERR = (
    "planwise@upb-confirm-upd's marketplace changed the command that installs it, or how its output is "
    "used (now `python C:/Users/gabgo/.claude/scratch/upb-confirm/upd/make_plugin.py changed`), since it "
    "was accepted, so it was not run. Review and accept the new command: run "
    "`claude plugin update planwise@upb-confirm-upd` in a terminal (add `--scope` for a project/local install).\n"
)
_REFUSED_UPDATE_COMMAND = "python C:/Users/gabgo/.claude/scratch/upb-confirm/upd/make_plugin.py changed"
# The same install with only its version bumped and its declared command unchanged. The CLI re-ran the
# accepted command, asked nothing and exited 0.
_UPDATED_COMMAND_SOURCE_RESULT = {
    "command": "update", "outcome": "ok", "plugin": "planwise@upb-confirm-upd",
    "pluginId": "planwise@upb-confirm-upd", "scope": "user",
    "message": 'Plugin "planwise" updated from 1.0.0-c1e43c81a9bf to 1.0.1-66071fe36363 for scope user. '
               "Restart to apply changes.",
    "updateOutcome": "updated", "oldVersion": "1.0.0-c1e43c81a9bf", "newVersion": "1.0.1-66071fe36363",
}
# The one measured `claude plugin update --json` success (CLI 2.1.330, 2026-11-21). Its `command`
# key names the CLI subcommand, which is not a command to run.
_UPDATED_RESULT = {
    "command": "update", "outcome": "ok", "plugin": "planwise@planwise-marketplace",
    "pluginId": "planwise@planwise-marketplace", "scope": "user",
    "message": 'Plugin "planwise" updated from 9.9.0 to 9.9.1 for scope user. Restart to apply changes.',
    "updateOutcome": "updated", "oldVersion": "9.9.0", "newVersion": "9.9.1",
}


@pytest.mark.parametrize("stdout, stderr, declared", [
    (_REFUSED_COMMAND_SOURCE_STDOUT, _REFUSED_COMMAND_SOURCE_STDERR, "python"),
    (_REFUSED_ENTRY_HELPER_STDOUT, "", "C:/Users/gabgo/.claude/scratch/upb-confirm/hh.cmd"),
    (_REFUSED_UPDATE_STDOUT, _REFUSED_UPDATE_STDERR, _REFUSED_UPDATE_COMMAND),
], ids=["command_source", "entry_helper", "command_source_update"])
def test_update_needs_confirm(env, monkeypatch, capsys, stdout, stderr, declared):
    _, running, project = env()
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout=stdout, update_code=1, update_stderr=stderr))
    code = update_check.main(["update", "--running-root", str(running), "--project-root", str(project)])
    data = json.loads(capsys.readouterr().out)
    assert code == update_check.EXIT_NEEDS_CONFIRM == 3
    assert data["result"] == update_check.NEEDS_CONFIRM
    assert data["command"] == declared  # the marketplace's command, for the person to review
    assert data["retry"] == f"claude plugin update planwise@{MARKET} --scope project"
    assert all("-y" not in c[0] and "--yes" not in c[0] and "--accept-command" not in c[0] for c in calls)


def test_update_with_an_unchanged_accepted_command_needs_no_confirmation(env, monkeypatch):
    """The CLI re-runs a command that the person already accepted, so an update reads UPDATED."""
    _, running, project = env()
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    stdout = json.dumps(_UPDATED_COMMAND_SOURCE_RESULT) + "\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout=stdout))
    code, report = update_check.update(running, project)
    assert code == update_check.EXIT_UPDATED and report["result"] == update_check.UPDATED
    assert report["command"] is None and report["retry"] is None


def test_confirm_command_reads_only_the_shown_command():
    parsed = update_check._last_json(_REFUSED_COMMAND_SOURCE_STDOUT)
    assert parsed is not None and parsed["command"] == "install"  # the subcommand, never the answer
    assert update_check.confirm_command(parsed) == "python"
    update_parsed = update_check._last_json(_REFUSED_UPDATE_STDOUT)
    assert update_parsed is not None and update_parsed["command"] == "update"
    assert update_check.confirm_command(update_parsed) == _REFUSED_UPDATE_COMMAND
    assert update_check.confirm_command(update_check._last_json(_REFUSED_ENTRY_HELPER_STDOUT)) == (
        "C:/Users/gabgo/.claude/scratch/upb-confirm/hh.cmd"
    )


def test_confirm_command_known_bad_arm_subcommand_key(env, monkeypatch):
    """A guessed flag beside the measured success result must not turn `command` into a command."""
    for flag in ("needsConfirmation", "requiresConfirmation", "needs_confirmation"):
        assert update_check.confirm_command({**_UPDATED_RESULT, flag: True}) is None, flag
    for key in ("confirmCommand", "confirm_command", "commandToConfirm"):
        assert update_check.confirm_command({**_UPDATED_RESULT, key: "claude plugin install x@y"}) is None, key
    _, running, project = env()
    calls = []
    monkeypatch.setattr(shutil_mod(), "which", lambda name: "claude")
    stdout = json.dumps({**_UPDATED_RESULT, "needsConfirmation": True}) + "\n"
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, update_stdout=stdout))
    code, report = update_check.update(running, project)
    assert code == update_check.EXIT_UPDATED and report["result"] == update_check.UPDATED


def test_confirm_command_rejects_shapes_that_are_not_a_refusal():
    assert update_check.confirm_command(None) is None
    assert update_check.confirm_command(_UPDATED_RESULT) is None
    assert update_check.confirm_command({"shownCommand": "python"}) is None
    assert update_check.confirm_command({"shownCommand": {"command": "  "}}) is None
    assert update_check.confirm_command({"shownCommand": {"kind": "command_source"}}) is None
    # A success result that echoes the command it ran is not a request to confirm one.
    assert update_check.confirm_command({**_UPDATED_RESULT, "shownCommand": {"command": "python"}}) is None


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
