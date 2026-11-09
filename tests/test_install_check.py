"""install_check.py: is the running planwise copy the project's marketplace install?"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import install_check

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "install_check.py"
MARKET = "planwise-marketplace"


def _plugin(root: Path, version: str) -> Path:
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "planwise", "version": version}), encoding="utf-8"
    )
    return root


def _home(tmp_path: Path, entries: list, clone_version: str = "1.0.5.5") -> Path:
    """A config dir with installed_plugins.json, known_marketplaces.json and a clone."""
    config = tmp_path / "claude"
    plugins = config / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {f"planwise@{MARKET}": entries}}), encoding="utf-8"
    )
    clone = plugins / "marketplaces" / MARKET
    (clone / ".claude-plugin").mkdir(parents=True)
    (clone / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": MARKET, "plugins": [{"name": "planwise", "source": "./plugins/planwise"}]}),
        encoding="utf-8",
    )
    _plugin(clone / "plugins" / "planwise", clone_version)
    (plugins / "known_marketplaces.json").write_text(
        json.dumps({MARKET: {"installLocation": str(clone), "lastUpdated": "2026-11-01T00:00:00.000Z"}}),
        encoding="utf-8",
    )
    return config


def _cache(config: Path, version: str) -> Path:
    return _plugin(config / "plugins" / "cache" / MARKET / "planwise" / version, version)


def _entry(scope: str, install_path: Path, version: str, project=None, updated="2026-11-01T00:00:00.000Z"):
    entry = {"scope": scope, "installPath": str(install_path), "version": version, "lastUpdated": updated}
    if project is not None:
        entry["projectPath"] = str(project)
    return entry


def test_running_install_matches_project_entry_is_ok(tmp_path):
    config = _home(tmp_path, [])
    running = _cache(config, "1.0.5.5")
    project = tmp_path / "proj"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [_entry("project", running, "1.0.5.5", project)]}}
    ), encoding="utf-8")
    result = install_check.check(running, project, config)
    assert result["verdict"] == install_check.OK
    assert result["scope"] == "project"


def test_behind_marketplace(tmp_path):
    config = _home(tmp_path, [], clone_version="9.9.9")
    running = _cache(config, "1.0.5.5")
    project = tmp_path / "proj"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [_entry("project", running, "1.0.5.5", project)]}}
    ), encoding="utf-8")
    result = install_check.check(running, project, config)
    assert result["verdict"] == install_check.BEHIND_MARKETPLACE
    line = install_check.format_line(result)
    assert line.startswith("INSTALL_CHECK: BEHIND_MARKETPLACE running=1.0.5.5 marketplace=9.9.9 ")


def test_synced_copy_is_not_marketplace_install(tmp_path):
    config = _home(tmp_path, [])
    installed = _cache(config, "1.0.5.5")
    synced = _plugin(config / "plugins" / "synced" / "abc123" / "planwise", "1.0.4")
    project = tmp_path / "proj"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [_entry("project", installed, "1.0.5.5", project)]}}
    ), encoding="utf-8")
    result = install_check.check(synced, project, config)
    assert result["verdict"] == install_check.NOT_MARKETPLACE_INSTALL
    assert result["running_version"] == "1.0.4"
    assert result["marketplace"] == MARKET  # the single planwise@* key names it


def test_no_entry_for_this_project(tmp_path):
    config = _home(tmp_path, [])
    running = _cache(config, "1.0.5.5")
    other = tmp_path / "other"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [_entry("project", running, "1.0.5.5", other)]}}
    ), encoding="utf-8")
    result = install_check.check(running, tmp_path / "proj", config)
    assert result["verdict"] == install_check.NOT_MARKETPLACE_INSTALL
    assert "applies to this project" in result["reason"]


def test_precedence_local_before_project_before_user(tmp_path):
    config = _home(tmp_path, [])
    local_copy = _cache(config, "1.0.5.5")
    project_copy = _cache(config, "1.0.5.4")
    user_copy = _cache(config, "1.0.5.3")
    project = tmp_path / "proj"
    entries = [
        _entry("user", user_copy, "1.0.5.3"),
        _entry("project", project_copy, "1.0.5.4", project),
        _entry("local", local_copy, "1.0.5.5", project),
    ]
    assert install_check.applicable_entry(entries, project)["scope"] == "local"
    assert install_check.applicable_entry(entries[:2], project)["scope"] == "project"
    assert install_check.applicable_entry(entries[:1], project)["scope"] == "user"
    # A local entry for a different project does not apply.
    other_local = [_entry("local", local_copy, "1.0.5.5", tmp_path / "x"), entries[0]]
    assert install_check.applicable_entry(other_local, project)["scope"] == "user"


def test_mixed_case_backslash_project_path_matches(tmp_path):
    config = _home(tmp_path, [])
    running = _cache(config, "1.0.5.5")
    project = tmp_path / "Proj"
    odd_project = str(project).replace("/", "\\").upper() + "\\"
    odd_install = str(running).replace("/", "\\").swapcase()
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [
            {"scope": "project", "projectPath": odd_project, "installPath": odd_install, "version": "1.0.5.5"}
        ]}}
    ), encoding="utf-8")
    result = install_check.check(running, project, config)
    assert result["verdict"] == install_check.OK


def test_missing_installed_plugins_is_not_marketplace_install(tmp_path):
    config = tmp_path / "empty"
    running = _plugin(tmp_path / "dev" / "planwise", "1.0.5.5")
    result = install_check.check(running, tmp_path / "proj", config)
    assert result["verdict"] == install_check.NOT_MARKETPLACE_INSTALL
    assert "installed_plugins.json" in result["reason"]


def test_refresh_failure_still_returns_a_verdict(tmp_path, monkeypatch, capsys):
    config = _home(tmp_path, [])
    running = _cache(config, "1.0.5.5")
    project = tmp_path / "proj"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {f"planwise@{MARKET}": [_entry("project", running, "1.0.5.5", project)]}}
    ), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network unreachable")

    monkeypatch.setattr(install_check.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(install_check.subprocess, "run", fake_run)
    code = install_check.main([
        "--project-root", str(project), "--running-root", str(running),
        "--config-dir", str(config), "--refresh",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert calls == [["claude", "plugin", "marketplace", "update", MARKET]]
    assert "refresh failed: exit 1: network unreachable" in out
    assert "lastUpdated=2026-11-01T00:00:00.000Z" in out
    assert "INSTALL_CHECK: OK " in out


def test_check_without_refresh_runs_no_subprocess(tmp_path, monkeypatch, capsys):
    config = _home(tmp_path, [])
    running = _cache(config, "1.0.5.5")

    def boom(*args, **kwargs):
        raise AssertionError("check must not spawn a process without --refresh")

    monkeypatch.setattr(install_check.subprocess, "run", boom)
    install_check.main(["--project-root", str(tmp_path), "--running-root", str(running),
                        "--config-dir", str(config)])
    assert capsys.readouterr().out.startswith("INSTALL_CHECK: NOT_MARKETPLACE_INSTALL ")


def test_cli_prints_one_install_check_line(tmp_path):
    config = _home(tmp_path, [])
    running = _plugin(tmp_path / "dev" / "planwise", "1.0.5.5")
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--project-root", str(tmp_path / "proj"),
         "--running-root", str(running), "--config-dir", str(config)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert proc.returncode == 0
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("INSTALL_CHECK:")]
    assert len(lines) == 1
    assert lines[0].startswith("INSTALL_CHECK: NOT_MARKETPLACE_INSTALL running=1.0.5.5 ")
