#!/usr/bin/env python3
"""Tests for the init-side feedback answers.

A fresh init writes `--feedback-drafts` and `--feedback-enabled` into the
config it just generated, through the same splice writer the upgrade uses.
Every other mode refuses the two flags. The init handler asks the same two
questions as the upgrade handler, word for word.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_gen
import init_project
from config_gen import ConfigResult, InitConfig, generate_config, get_plugin_root
from upgrade_preflight import FEEDBACK_DRAFTS_QUESTION, FEEDBACK_ENABLED_QUESTION

PLUGIN = Path(init_project.__file__).resolve().parent.parent
SCRIPT = str(PLUGIN / "scripts" / "init_project.py")


def _fresh_config(tmp_path, drafts=None, enabled=False):
    cfg = InitConfig(project_name="p", project_root=tmp_path, plugin_root=get_plugin_root(),
                     feedback_drafts=drafts, feedback_enabled=enabled)
    (tmp_path / cfg.planwise_root).mkdir()
    result, _ = generate_config(cfg)
    assert result == ConfigResult.CREATED
    return cfg, tmp_path / cfg.planwise_root / "config.yaml"


def _feedback(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["feedback"]


def test_answers_are_written_and_read_back(tmp_path):
    cfg, path = _fresh_config(tmp_path, drafts="quiet", enabled=True)
    line = init_project._apply_init_feedback_answers(cfg, path)
    assert line == "Feedback keys: feedback.drafts: quiet, feedback.enabled: true (answered)"
    block = _feedback(path)
    assert block["drafts"] == "quiet" and block["enabled"] is True
    assert "Feedback drafting:" not in line


def test_off_answer_keeps_posting_off(tmp_path):
    cfg, path = _fresh_config(tmp_path, drafts="off")
    line = init_project._apply_init_feedback_answers(cfg, path)
    assert line == "Feedback keys: feedback.drafts: off, feedback.enabled: false (answered)"
    assert _feedback(path)["enabled"] is False


def test_no_answer_keeps_the_template_defaults_and_writes_nothing(tmp_path):
    cfg, path = _fresh_config(tmp_path)
    before = path.read_bytes()
    line = init_project._apply_init_feedback_answers(cfg, path)
    assert line == ("Feedback keys: feedback.drafts: notify, feedback.enabled: false "
                    "(template defaults, no answer passed)")
    assert path.read_bytes() == before


def test_the_splice_keeps_the_template_comments(tmp_path):
    cfg, path = _fresh_config(tmp_path, drafts="quiet", enabled=True)
    comments = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.lstrip().startswith("#")]
    init_project._apply_init_feedback_answers(cfg, path)
    after = path.read_text(encoding="utf-8").splitlines()
    assert [ln for ln in after if ln.lstrip().startswith("#")] == comments


def test_a_refused_edit_is_reported_as_not_written(tmp_path, monkeypatch, capsys):
    cfg, path = _fresh_config(tmp_path, drafts="quiet")

    def locked(config_path, text):
        raise PermissionError(f"{config_path} is locked")

    monkeypatch.setattr(config_gen, "write_config_checked", locked)
    line = init_project._apply_init_feedback_answers(cfg, path)
    assert line.endswith("(answer NOT written, see the warning above)")
    assert "feedback.drafts: notify" in line
    assert capsys.readouterr().err.startswith("Warning: feedback keys left unchanged: ")


def test_help_no_longer_says_a_fresh_init_ignores_the_flags():
    out = subprocess.run([sys.executable, "-B", SCRIPT, "--help"],
                         capture_output=True, text=True, check=True).stdout
    assert "ignores it" not in out
    assert out.count("fresh init or --upgrade") == 2


@pytest.mark.parametrize("mode", [["--migrate", "--name", "p"], ["--doctor"], ["--list-diverged"]])
def test_other_modes_refuse_the_flags(tmp_path, mode):
    proc = subprocess.run(
        [sys.executable, "-B", SCRIPT, "--project-root", str(tmp_path), *mode, "--feedback-drafts", "quiet"],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "apply only to a fresh init or --upgrade, not with " + mode[0] in proc.stderr
    assert list(tmp_path.iterdir()) == []


def test_fresh_init_run_writes_both_answers(tmp_path):
    # HOME and USERPROFILE point at the scratch root, so the user-scope settings
    # init writes land there and never in the real home directory.
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}
    project = tmp_path / "proj"
    project.mkdir()
    proc = subprocess.run(
        [sys.executable, "-B", SCRIPT, "--name", "p", "--project-root", str(project),
         "--feedback-drafts", "quiet", "--feedback-enabled"],
        capture_output=True, text=True, check=False, env=env, timeout=300)
    assert proc.returncode == 0, proc.stderr
    assert "Feedback keys: feedback.drafts: quiet, feedback.enabled: true (answered)" in proc.stdout
    block = _feedback(project / "planwise" / "config.yaml")
    assert block["drafts"] == "quiet" and block["enabled"] is True


@pytest.mark.parametrize("question", [FEEDBACK_DRAFTS_QUESTION, FEEDBACK_ENABLED_QUESTION])
@pytest.mark.parametrize("handler", ["init.md", "upgrade.md"])
def test_both_handlers_quote_the_question_verbatim(handler, question):
    text = (PLUGIN / "handlers" / handler).read_text(encoding="utf-8")
    assert question in text
