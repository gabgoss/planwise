#!/usr/bin/env python3
"""Tests for config_gen.probe_cli_version's candidate resolution.

The probe resolves `claude` through `shutil.which` (then `claude.cmd`, then
`claude.exe`, then the bare name) so a Windows npm shim that `subprocess`
cannot start by bare name is still found. Both `shutil.which` and
`subprocess.run` are patched, so no real CLI is run.

Run with:  python -m pytest tests/test_config_gen_cli_probe.py -q
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen


def _patch_which(monkeypatch, found: dict) -> None:
    monkeypatch.setattr(config_gen.shutil, "which", lambda name: found.get(name))


def test_first_which_path_runs_first_and_its_version_is_returned(monkeypatch):
    _patch_which(monkeypatch, {"claude": "/bin/claude", "claude.cmd": "/bin/claude.cmd"})
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="2.1.300 (Claude Code)\n")

    monkeypatch.setattr(config_gen.subprocess, "run", fake_run)
    assert config_gen.probe_cli_version() == "2.1.300"
    assert calls == [["/bin/claude", "--version"]]


def test_claude_cmd_path_runs_when_claude_is_absent(monkeypatch):
    _patch_which(monkeypatch, {"claude.cmd": "C:/npm/claude.cmd"})
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="2.1.301\n")

    monkeypatch.setattr(config_gen.subprocess, "run", fake_run)
    assert config_gen.probe_cli_version() == "2.1.301"
    assert calls[0] == ["C:/npm/claude.cmd", "--version"]


def test_second_candidate_version_is_returned_after_the_first_raises(monkeypatch):
    _patch_which(monkeypatch, {"claude": "/bin/claude", "claude.exe": "/bin/claude.exe"})

    def fake_run(cmd, **kwargs):
        if cmd[0] == "/bin/claude":
            raise FileNotFoundError(cmd[0])
        return SimpleNamespace(stdout="2.1.302\n")

    monkeypatch.setattr(config_gen.subprocess, "run", fake_run)
    assert config_gen.probe_cli_version() == "2.1.302"


def test_every_candidate_failing_returns_empty_string_without_raising(monkeypatch):
    _patch_which(
        monkeypatch,
        {"claude": "/bin/claude", "claude.cmd": "/bin/claude.cmd", "claude.exe": "/bin/claude.exe"},
    )

    def fake_run(cmd, **kwargs):
        if cmd[0] == "/bin/claude":
            raise OSError("cannot start")
        if cmd[0] == "/bin/claude.cmd":
            raise subprocess.TimeoutExpired(cmd, 5.0)
        return SimpleNamespace(stdout="no version here\n")

    monkeypatch.setattr(config_gen.subprocess, "run", fake_run)
    assert config_gen.probe_cli_version() == ""
