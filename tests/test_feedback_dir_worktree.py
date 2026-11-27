#!/usr/bin/env python3
"""Tests for the feedback folder of a project that sits in a git linked worktree.

`load_config` used to build `_feedback_dir` under the planwise root of the tree
it was started in. A linked worktree then got its own drafts folder, and
removing the worktree deleted the drafts. The loader now takes the base from
`install_check.main_checkout_root`, so a worktree and its main checkout share
one folder. Every reader of `_feedback_dir` follows the loader.

The fixture is a real git repository with a real linked worktree, so the loader
reads the `.git` file that `git worktree add` writes.

Run with:  python -m pytest tests/test_feedback_dir_worktree.py -q
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import artifact_upgrade
import config_loader
import doctor_probes as dp
import feedback_drafts
import init_project

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

FEEDBACK_REL = Path("Feedback") / "Feedback-Drafts"


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"


def _config_text(feedback_dir=None) -> str:
    lines = ['plugin_version: "1.0.4"', "project:", "  name: Fixture", "  backlog_dir: Backlog", "  plans_dir: Plans"]
    if feedback_dir is not None:
        lines.append(f"  feedback_dir: {feedback_dir}")
    return "\n".join(lines) + "\n"


def _write_project(root: Path, feedback_dir=None) -> Path:
    """Write a minimal planwise project under `root` and return its config path."""
    planwise = root / "planwise"
    for name in ("Backlog", "Plans"):
        (planwise / name).mkdir(parents=True)
        (planwise / name / ".gitkeep").write_text("", encoding="utf-8")
    config_path = planwise / "config.yaml"
    config_path.write_text(_config_text(feedback_dir), encoding="utf-8")
    return config_path


def _make_pair(tmp_path: Path, feedback_dir=None):
    """A committed main checkout and one linked worktree. Return both config paths."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init")
    main_config = _write_project(main, feedback_dir)
    _git(main, "add", "-A")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-b", "wt-branch", str(wt))
    return main_config, wt / "planwise" / "config.yaml"


def _feedback_dir(config_path: Path) -> Path:
    return Path(config_loader.load_config(config_path=config_path)["_feedback_dir"]).resolve()


def _run(func, config):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(config)
    return buf.getvalue()


def _stage_17_folder(out: str) -> Path:
    """The folder the stage's `feedback directory:` line names."""
    for line in out.splitlines():
        if line.strip().startswith("feedback directory:"):
            return Path(line.split(":", 1)[1].strip()).resolve()
    raise AssertionError(f"no `feedback directory:` line in:\n{out}")


def test_worktree_feedback_dir_is_the_main_checkouts(tmp_path):
    main_config, wt_config = _make_pair(tmp_path)
    expected = (main_config.parent / FEEDBACK_REL).resolve()
    assert _feedback_dir(wt_config) == expected


def test_plain_checkout_feedback_dir_is_unchanged(tmp_path):
    main_config, _ = _make_pair(tmp_path)
    assert _feedback_dir(main_config) == (main_config.parent / FEEDBACK_REL).resolve()


def test_folder_outside_git_is_unchanged(tmp_path):
    plain = tmp_path / "plain"
    config_path = _write_project(plain)
    # A repository above the temp folder must not be found.
    with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(tmp_path)}):
        assert _feedback_dir(config_path) == (plain / "planwise" / FEEDBACK_REL).resolve()


def test_stage_17_in_a_worktree_names_the_main_checkouts_folder(tmp_path):
    main_config, wt_config = _make_pair(tmp_path)
    config = config_loader.load_config(config_path=wt_config)
    out = _run(dp._stage_17, config)
    assert _stage_17_folder(out) == (main_config.parent / FEEDBACK_REL).resolve()
    assert "(the check failed:" not in out


def test_legacy_layout_folders_in_a_worktree_find_nothing_on_the_default(tmp_path):
    _, wt_config = _make_pair(tmp_path)
    config = config_loader.load_config(config_path=wt_config)
    assert dp._legacy_layout_folders(config) == []


@pytest.mark.parametrize("old", ["feedback-drafts", "Feedback"])
def test_legacy_layout_folders_in_a_worktree_still_name_a_legacy_config(tmp_path, old):
    # The config, not the resolved folder, names the legacy layout, so a worktree
    # reports it the way a plain checkout does.
    main_config, wt_config = _make_pair(tmp_path, feedback_dir=old)
    for config_path in (main_config, wt_config):
        config = config_loader.load_config(config_path=config_path)
        assert dp._legacy_layout_folders(config) == [(f"{old}/", "Feedback/Feedback-Drafts/")]


def _init_cfg(config_path: Path) -> "init_project.InitConfig":
    """The init settings for the project that holds `config_path`."""
    return init_project.InitConfig(
        project_name="Fixture",
        project_root=config_path.parent.parent,
        plugin_root=Path(init_project.__file__).resolve().parent.parent,
        planwise_root="planwise",
        plans_dir="Plans",
        backlog_dir="Backlog",
        lessons_dir="LessonsLearned",
        feedback_dir=FEEDBACK_REL.as_posix(),
        install_scope=init_project.InstallScope.PROJECT,
        plan_tier="pro",
        plugin_version="0.0.0",
        token_saver=False,
    )


def test_create_directories_in_a_worktree_makes_the_main_checkouts_folder(tmp_path):
    main_config, wt_config = _make_pair(tmp_path)
    expected = (main_config.parent / FEEDBACK_REL).resolve()
    created = init_project.create_directories(_init_cfg(wt_config))
    assert expected.is_dir()
    assert not (wt_config.parent / FEEDBACK_REL).exists()
    assert expected in [Path(c).resolve() for c in created if Path(c).is_absolute()]


def test_upgrade_in_a_worktree_makes_and_reports_the_main_checkouts_folder(tmp_path):
    main_config, wt_config = _make_pair(tmp_path)
    expected = (main_config.parent / FEEDBACK_REL).resolve()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        artifact_upgrade._apply_feedback_dir(_init_cfg(wt_config), wt_config)
    assert expected.is_dir()
    assert not (wt_config.parent / FEEDBACK_REL).exists()
    prefix = "Feedback directory: created ("
    reported = [line for line in buf.getvalue().splitlines() if line.startswith(prefix)]
    assert len(reported) == 1, buf.getvalue()
    assert Path(reported[0][len(prefix):-1]).resolve() == expected


def test_create_directories_in_a_plain_checkout_reports_a_relative_path(tmp_path):
    main_config, _ = _make_pair(tmp_path)
    created = init_project.create_directories(_init_cfg(main_config))
    assert (main_config.parent / FEEDBACK_REL).is_dir()
    assert Path("planwise") / FEEDBACK_REL in [Path(c) for c in created]


def _feedback_dir_command(config_path: Path):
    """Run `feedback-dir --config <path>` and return its exit code and stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = feedback_drafts.main(["feedback-dir", "--config", str(config_path)])
    return code, buf.getvalue()


def test_feedback_dir_command_in_a_worktree_prints_the_main_checkouts_folder(tmp_path):
    main_config, wt_config = _make_pair(tmp_path)
    expected = (main_config.parent / FEEDBACK_REL).resolve()
    code, out = _feedback_dir_command(wt_config)
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 1
    assert Path(lines[0]).resolve() == expected
    assert not expected.exists()  # the command writes nothing


def test_feedback_dir_command_on_the_main_config_prints_the_same_folder(tmp_path):
    main_config, _ = _make_pair(tmp_path)
    code, out = _feedback_dir_command(main_config)
    assert code == 0
    assert Path(out.strip()).resolve() == (main_config.parent / FEEDBACK_REL).resolve()


def test_feedback_dir_command_on_a_missing_config_exits_1_with_no_stdout(tmp_path):
    code, out = _feedback_dir_command(tmp_path / "no-such" / "config.yaml")
    assert code == 1
    assert out == ""
